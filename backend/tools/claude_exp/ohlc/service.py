"""Authenticated, cursor-bound chart delivery (Claude candidate). The browser never sees an object key, URL or byte range of the store.

Rules enforced here, server-side, on every request:
  * identity: bearer token -> user; the session must belong to that user (a foreign or unknown session answers the SAME 404)
  * pins: dataset (source manifest hash), price basis and Session revision come from the Session record, not from the request
  * no-lookahead: only bars with end <= cursor T leave the trust boundary; the forming bar is rebuilt from M1 bars that ended <= T
    plus the tick prefix of the current minute (ts <= T); nothing newer is read into the response
  * bounds: limit 1..1000 (default first page 512), `before` is an exclusive bar start that must be <= T
  * paging is backward only, so `hasMore`/`nextBefore` describe older history and cannot reveal a future gap, EOF or candle
"""
import json
import threading
import time
from collections import OrderedDict

import numpy as np

from . import engine
from .engine import Aggregator, COLUMNS, NS, TIMEFRAMES, from_parquet_bytes, tick_rows

TF_SECONDS = dict(TIMEFRAMES)
FIRST_PAGE = 512
MAX_PAGE = 1000


class ServiceError(Exception):
    def __init__(self, status, code):
        super().__init__(code)
        self.status, self.code = status, code


class Session:
    def __init__(self, session_id, user, instrument, source_hash, basis, cursor_ns, entitled_from_ns=0, revision=0):
        self.id, self.user, self.instrument, self.source_hash = session_id, user, instrument, source_hash
        self.basis, self.cursor_ns, self.entitled_from_ns, self.revision = basis, cursor_ns, entitled_from_ns, revision


class ChartService:
    def __init__(self, store, readers, sessions, tokens, cache_objects=64):
        self.store, self.readers, self.sessions, self.tokens = store, readers, sessions, tokens
        self.lock = threading.RLock()
        self.cache = OrderedDict()          # decoded month/timeframe columns, bounded
        self.cache_objects = cache_objects
        self.catalog = {}                   # (instrument, source16, basis) -> {month: manifest}
        self.hits = self.misses = 0

    # ---- catalog and decoded objects ------------------------------------------------------------------------------------
    def months(self, instrument, source_hash, basis):
        key = (instrument, source_hash[:16], basis)
        with self.lock:
            if key not in self.catalog:
                prefix = f"ohlc/{engine.TRANSFORM_VERSION}/{instrument}/{source_hash[:16]}/{basis}/"
                found = {}
                for k in self.store.list(prefix):
                    if k.endswith("/manifest.json"):
                        m = json.loads(self.store.get(k))
                        found[m["month"]] = m
                self.catalog[key] = found
            return self.catalog[key]

    def columns(self, manifest, tf):
        obj = manifest["objects"][tf]
        key = obj["key"]
        with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key)
                self.hits += 1
                return self.cache[key]
            self.misses += 1
        cols = from_parquet_bytes(self.store.get(key))
        with self.lock:
            self.cache[key] = cols
            while len(self.cache) > self.cache_objects:
                self.cache.popitem(last=False)
        return cols

    # ---- request handling -----------------------------------------------------------------------------------------------
    def _session(self, token, session_id):
        user = self.tokens.get(token)
        if user is None:
            raise ServiceError(401, "UNAUTHENTICATED")
        s = self.sessions.get(session_id)
        if s is None or s.user != user:
            raise ServiceError(404, "NOT_FOUND")                       # identical for unknown and foreign sessions
        return s

    def bars(self, token, session_id, tf, limit=None, before=None, rev=None):
        s = self._session(token, session_id)
        if tf not in TF_SECONDS:
            raise ServiceError(400, "INVALID_REQUEST")
        if limit is not None and not (type(limit) is int and 1 <= limit <= MAX_PAGE):
            raise ServiceError(400, "INVALID_REQUEST")
        if before is not None and not (type(before) is int and 0 < before <= s.cursor_ns):
            raise ServiceError(400, "INVALID_REQUEST")
        if rev is not None and rev != s.revision:
            raise ServiceError(409, "STALE_REVISION")
        T, width = s.cursor_ns, TF_SECONDS[tf] * NS
        limit = limit or FIRST_PAGE
        catalog = self.months(s.instrument, s.source_hash, s.basis)
        if not catalog:
            raise ServiceError(404, "NOT_FOUND")
        newest_allowed = T - width                                       # bar start such that start + tf <= T
        bound = newest_allowed if before is None else min(newest_allowed, before - 1)
        taken, remaining, older = [], limit, False
        months_desc = sorted(catalog, reverse=True)
        stop = len(months_desc)
        for idx, month in enumerate(months_desc):
            m = catalog[month]
            obj = m["objects"][tf]
            if obj["count"] == 0 or obj["firstBarNs"] > bound or obj["lastBarNs"] < s.entitled_from_ns:
                continue                      # nothing eligible here: all bars are newer than the cursor bound or older than the entitlement
            c = self.columns(m, tf)
            hi = int(np.searchsorted(c["t"], bound, side="right"))
            lo = int(np.searchsorted(c["t"], s.entitled_from_ns, side="left"))
            if hi <= lo:
                continue
            take = min(remaining, hi - lo)
            taken.append({k: c[k][hi - take:hi] for k in COLUMNS})
            remaining -= take
            if hi - take > lo:
                older = True
            if remaining == 0:
                stop = idx + 1
                break
        if remaining == 0 and not older:      # page filled exactly: is any eligible bar left in an earlier month?
            older = any(catalog[mm]["objects"][tf]["count"] and catalog[mm]["objects"][tf]["lastBarNs"] >= s.entitled_from_ns
                        for mm in months_desc[stop:])
        rows = {k: np.concatenate([p[k] for p in reversed(taken)]) if taken else np.empty(0, dtype=np.int64) for k in COLUMNS}
        out = dict(schemaVersion=1, session=s.id, revision=s.revision, cursorNs=T, tf=tf, basis=s.basis, den=catalog[next(iter(catalog))]["priceScaleDenominator"],
                   source=dict(manifestHash=s.source_hash, transform=engine.TRANSFORM_VERSION, rules=engine.RULES_VERSION),
                   volume="NONE", bars={k: [int(x) for x in rows[k]] for k in ("t", "o", "h", "l", "c", "n")},
                   count=int(len(rows["t"])), hasMore=bool(older), nextBefore=int(rows["t"][0]) if len(rows["t"]) else None)
        if before is None:
            out["active"] = self.active(s, tf)
        return out

    def active(self, s, tf):
        """Forming bar from information revealed at the cursor only."""
        T, width = s.cursor_ns, TF_SECONDS[tf] * NS
        b0 = T - (T % width)
        minute0 = T - (T % (60 * NS))
        agg = Aggregator(TF_SECONDS[tf])
        catalog = self.months(s.instrument, s.source_hash, s.basis)
        if tf != "M1" and minute0 > b0:
            for month in sorted(catalog, reverse=True):
                m = catalog[month]
                o = m["objects"]["M1"]
                if o["count"] == 0 or o["lastBarNs"] < b0 or o["firstBarNs"] >= minute0:
                    continue
                c = self.columns(m, "M1")
                lo, hi = int(np.searchsorted(c["t"], b0, "left")), int(np.searchsorted(c["t"], minute0, "left"))
                if hi > lo:
                    agg.feed({k: c[k][lo:hi] for k in COLUMNS})
        reader = self.readers[s.instrument]
        minute_rows = None
        for block in reader.iter_blocks(minute0, T + 1, atomic=False):
            r = tick_rows(block, s.basis)
            minute_rows = r if minute_rows is None else {k: np.concatenate((minute_rows[k], r[k])) for k in r}
        if minute_rows is not None:
            m1 = Aggregator(60)
            m1.feed(minute_rows)
            agg.feed(m1.finish())
        res = agg.finish()
        keep = [i for i in range(len(res["t"])) if int(res["t"][i]) == b0]
        if not keep:
            return None
        i = keep[0]
        return {k: int(res[k][i]) for k in ("t", "o", "h", "l", "c", "n", "first", "last")}

    def advance(self, session_id, cursor_ns):
        """Replay owner (the financial engine) moves the cursor; every move bumps the revision."""
        s = self.sessions[session_id]
        if cursor_ns < s.cursor_ns:
            raise ServiceError(400, "CURSOR_BACKWARDS")
        s.cursor_ns, s.revision = cursor_ns, s.revision + 1


# ---- HTTP layer ---------------------------------------------------------------------------------------------------------
def make_handler(service, metrics):
    from http.server import BaseHTTPRequestHandler
    from urllib.parse import parse_qs, urlparse

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, status, body):
            data = json.dumps(body, separators=(",", ":")).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "private, no-store")      # no shared cache may hold cursor-bound pages
            self.end_headers()
            self.wfile.write(data)
            return len(data)

        def do_GET(self):
            t0 = time.perf_counter()
            u = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            token = self.headers.get("Authorization", "")[7:] if self.headers.get("Authorization", "").startswith("Bearer ") else None
            try:
                if u.path != "/v1/chart/bars":
                    raise ServiceError(404, "NOT_FOUND")

                def num(name):
                    if name not in q:
                        return None
                    if not q[name].isascii() or not q[name].isdigit():
                        raise ServiceError(400, "INVALID_REQUEST")
                    return int(q[name])
                n = self._send(200, service.bars(token, q.get("session", ""), q.get("tf", ""), num("limit"), num("before"), num("rev")))
                status = 200
            except ServiceError as e:
                status = e.status
                n = self._send(e.status, dict(error=e.code))
            metrics.append((status, n, time.perf_counter() - t0))
    return H
