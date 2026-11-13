"""Local manual-trading app on the Claude engine (QA/prototype, single user, no PostgreSQL).

    py -m tools.claude_exp.local_trader.server --zip <Dukascopy XAUUSD monthly zip> --ticks 400000 --offset 0

Everything financial goes through the reference reducer (observed_kernel); this file only serves the UI. The browser never
receives a tick or candle after the session cursor (no look-ahead): candles are built server-side from revealed ticks only.
Prices are XAUUSD (profile fixture: contract size 100, tick 0.001). Execution model: observed quotes only, no slippage/commission.
"""
import argparse, hashlib, json, os, sys, tempfile, threading, time
from decimal import Decimal
from fractions import Fraction
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from common import *                        # noqa: E402  (stubs psycopg, adds backend to sys.path)
from claude_session import AdmittedSource, ClaudeSession    # noqa: E402
from market_data.compact_tick import write_compact          # noqa: E402
from contracts.primitives import ContractError              # noqa: E402
import numpy as np                                          # noqa: E402

LOCK = threading.Lock()
S = {}


def build_histdata(zip_path, pair, offset, ticks, cache):
    import re
    month = re.search(r"_T(\d{6})", Path(zip_path).name).group(1)
    mh = histdata_member_hash(zip_path)
    key = hashlib.sha256(f"{mh}|{pair}|{offset}|{ticks}".encode()).hexdigest()[:16]
    root = Path(cache) / key
    meta_path = root / "meta.json"
    if meta_path.exists():
        return root, json.loads(meta_path.read_text())
    rows = read_histdata_rows(zip_path, ticks, offset)
    print(f"[data] {pair} {len(rows)} HistData-UTC ticks -> compact (one time)", flush=True)
    ds = f"local:histdata-utc:{pair}:{month}:{mh[:24]}"
    dv = hashlib.sha256(f"{ds}|{offset}|{ticks}".encode()).hexdigest()
    root.mkdir(parents=True, exist_ok=True)
    m = write_compact(root / "compact", ({"timeNs": str(ts * 1_000_000), "bid": bid, "ask": ask, "rawOrdinal": str(i)}
                                         for i, (ts, ask, bid) in enumerate(rows)), parent=dict(datasetId=ds, datasetVersion=dv), scale=5)
    adm = dict(datasetId=ds, datasetVersion=dv, providerId="histdata", feedId="local-unverified:" + pair, instrumentId="histdata:" + pair,
               sourceId="histdata:utc:" + mh[:24], memberHash=mh, manifestHash=m["manifestHash"], scale=100000, kind="histdata-utc")
    meta = dict(adm=adm, start_ms=rows[0][0], end_ms=rows[-1][0], ticks=len(rows), seed=genesis_checkpoint(ds, dv, rows[0][0] * 10**6), pair=pair)
    meta_path.write_text(json.dumps(meta))
    return root, meta


def build_dataset(zip_path, offset, ticks, cache):
    key = hashlib.sha256(f"{Path(zip_path).name}|{offset}|{ticks}".encode()).hexdigest()[:16]
    root = Path(cache) / key
    meta_path = root / "meta.json"
    if meta_path.exists():
        return root, json.loads(meta_path.read_text())
    os.environ["XAU_TICK_ZIP"] = str(zip_path)
    rows = read_real_rows(offset + ticks)[offset:]
    print(f"[data] {len(rows)} real ticks -> compact (one time)", flush=True)
    root.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="lt-stub-"))
    prov, res, _ = ingest_engine(rows[:600], work)      # stub canonical store: only provides dataset identity + profile
    tl = IndexedTickTimeline(prov, prov.dataset_id, prov.dataset_version, str(rows[0][0] * 10**6), log_folder=work / "l")
    seed_cp = tl.checkpoint()
    fr = tl.advance_through(str(rows[3][0] * 10**6), tl.cursor)
    first = fr["groups"][0]["events"][0]
    tl.close()
    parent = dict(datasetId=first["datasetId"], datasetVersion=first["datasetVersion"])
    m = write_compact(root / "compact", ({"timeNs": str(ts * 1_000_000), "bid": bid, "ask": ask, "rawOrdinal": str(i)}
                                         for i, (ts, ask, bid) in enumerate(rows)), parent=parent, scale=3)
    meta = dict(adm=dict(datasetId=first["datasetId"], datasetVersion=first["datasetVersion"], providerId=first["providerId"],
                         feedId=first["feedId"], instrumentId=first["instrumentId"], sourceId=first["provenance"]["sourceId"],
                         memberHash=first["provenance"]["memberHash"], manifestHash=m["manifestHash"]),
                start_ms=rows[0][0], end_ms=rows[-1][0], ticks=len(rows), seed=seed_cp)
    meta_path.write_text(json.dumps(meta))
    return root, meta


def open_session(zip_path, offset, ticks, cache, pair="XAUUSD"):
    root, meta = build_dataset(zip_path, offset, ticks, cache) if pair == "XAUUSD" else build_histdata(zip_path, pair, offset, ticks, cache)
    meta.setdefault("pair", "XAUUSD")
    os.environ["XAU_TICK_ZIP"] = str(zip_path)
    # the stub store must carry the SAME dataset identity as the compact manifest parent; rebuild it deterministically
    adm = meta["adm"]
    src = AdmittedSource(root / "compact", adm, expected_manifest_hash=adm["manifestHash"], deep_verify=True)
    primary = dict(datasetId=adm["datasetId"], datasetVersion=adm["datasetVersion"], providerId=adm["providerId"],
                   feedId=adm["feedId"], feedInstrumentId=adm["instrumentId"], providerSymbol="XAUUSD", evidenceClass="PROVIDER_OBSERVATION")
    if pair == "XAUUSD":
        profile_raw = json.loads(json.dumps(PROFILE)); profile_raw["primary"] = primary
    else:
        import fx_profile
        fx_profile.install()
        profile_raw = fx_profile.fx_profile_wire(PROFILE, pair, primary)
    profile = ObservedExecutionProfile.from_wire(profile_raw)
    return src, profile, meta["seed"], meta


def session_json():
    cs, src = S["cs"], S["src"]
    st = cs.state
    k = int(st["nextGroupIndex"])
    bid = ask = None
    sc, dec = src.scale, len(str(src.scale)) - 1
    contract = Fraction(st["profile"]["contractSize"])
    if k:
        bid, ask = int(src.gbid[k - 1]), int(src.gask[k - 1])
    orders = []
    for oid, o in st["orders"].items():
        row = dict(id=oid, side=o["side"], type=o["orderType"], status=o["status"], lots=o["quantity"], entry=o["entry"], sl=o["sl"], tp=o["tp"],
                   fill=o["entryPrice"], pnl=o["grossPosted"], remaining=o["remaining"])
        if o["status"] == "ACTIVE" and bid is not None:
            px = Fraction(bid, sc) if o["side"] == "LONG" else Fraction(ask, sc)
            e = Fraction(o["entryPrice"])
            d = 1 if o["side"] == "LONG" else -1
            row["floating"] = f"{float((px - e) * d * contract * Fraction(o['remaining'])):.2f}"
        orders.append(row)
    thr = int(st["throughNs"])
    return dict(time=thr // 1_000_000, timeIso=time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(thr / 1e9)),
                balance=st["balance"], realized=st["realizedGross"], bid=None if bid is None else f"{bid/sc:.{dec}f}",
                ask=None if ask is None else f"{ask/sc:.{dec}f}", spread=None if bid is None else f"{(ask-bid)/sc:.{dec}f}",
                info=dict(symbol=S["meta"]["pair"], dec=dec, defSl="2" if dec == 3 else "0.0010", defTp="3" if dec == 3 else "0.0015", lot="0.01"),
                unresolved=st["unresolved"], ended=st["ended"], orders=orders,
                quoteFresh=bool(st["quoteBasis"] is not None and thr - int(st["quoteBasis"]["timeNs"]) <= int(st["profile"]["maxObservedSilenceNs"])),
                progress=dict(group=k, groups=src.ngroups, startMs=S["meta"]["start_ms"], endMs=S["meta"]["end_ms"]),
                atEnd=k >= src.ngroups, events=S["events"][-40:], trades=S["trades"][-40:], model="observed quotes only; no slippage/commission")


def candles(tf, n):
    cs, src = S["cs"], S["src"]
    k = int(cs.state["nextGroupIndex"])
    if k == 0:
        return []
    last_tick = int(src.gend[k - 1])                     # only ticks of groups already revealed
    ts = src.ts[:last_tick]
    lo = max(0, int(np.searchsorted(ts, ts[-1] - n * tf * 10**9)))
    t, bid = ts[lo:], src.bid[lo:last_tick]
    bucket = t // (tf * 10**9)
    first = np.flatnonzero(np.r_[True, bucket[1:] != bucket[:-1]])
    out = []
    for a, b in zip(first, np.r_[first[1:], len(t)]):
        seg = bid[a:b]
        out.append([int(bucket[a]) * tf, float(seg[0]) / src.scale, float(seg.max()) / src.scale, float(seg.min()) / src.scale, float(seg[-1]) / src.scale])
    return out[-n:]


def log_events(evs):
    for e in evs:
        if e["kind"] == "REPLAY_ADVANCED":
            continue
        d = e.get("detail") or {}
        d = d if isinstance(d, dict) else {}
        oid, now = e.get("orderId"), int(S["cs"].state["throughNs"]) // 1_000_000
        S["events"].append(dict(kind=e["kind"], orderId=oid, price=d.get("price"), reason=d.get("reason"), pnl=d.get("grossPosted"), timeMs=now))
        if e["kind"] == "ENTRY_FILL":
            S["meta_orders"].setdefault(oid, {})["entry"] = d.get("price")
        elif e["kind"] == "EXIT_FILL":
            m = S["meta_orders"].get(oid, {})
            S["trades"].append(dict(id=oid, side=m.get("side"), lots=d.get("quantity"), entry=m.get("entry"), exit=d.get("price"),
                                    pnl=d.get("grossPosted"), reason=d.get("reason"), timeMs=now))


def save():
    S["snap_path"].write_text(json.dumps(dict(snapshot=S["cs"].snapshot(), events=S["events"], trades=S["trades"], meta_orders=S["meta_orders"])))


def do_advance(seconds, until_event=False, max_seconds=6 * 3600):
    cs, src = S["cs"], S["src"]
    end = int(src.gts[-1])
    start = int(cs.state["throughNs"])
    live = lambda: any(o["status"] in ("PENDING", "ACTIVE") for o in cs.state["orders"].values())
    if until_event:
        step, limit, target0 = 5 * 10**9, start + max_seconds * 10**9, start
        while True:
            t = min(int(cs.state["throughNs"]) + step, limit, end)
            before = len(S["events"])
            evs = cs.advance_through(t); log_events(evs)
            if len(S["events"]) > before or cs.state["unresolved"] or t >= end or t >= limit or not live():
                break
            step = min(step * 2, 600 * 10**9)
        return
    t = min(start + int(seconds * 1e9), end)
    log_events(cs.advance_through(t))


def api(path, q, body):
    cs = S["cs"]
    if path == "/api/state":
        return session_json()
    if path == "/api/candles":
        tf = int(q.get("tf", ["60"])[0]); n = min(int(q.get("n", ["300"])[0]), 5000)
        return dict(tf=tf, candles=candles(tf, n))
    if path == "/api/advance":
        do_advance(float(body.get("seconds", 1)), bool(body.get("untilEvent")))
        save(); return session_json()
    if path == "/api/order":
        st = cs.state
        side = "LONG" if body["side"] == "BUY" else "SHORT"
        if st["quoteBasis"] is None:
            raise ContractError("NO_FRESH_QUOTE", "advance until a quote arrives")
        b = st["quoteBasis"]
        typ = body.get("type", "MARKET")
        d = 1 if side == "LONG" else -1
        if typ == "MARKET":
            entry = b["ask" if side == "LONG" else "bid"]; workflow = "QUICK"
        else:
            entry = f"{Decimal(str(body['entry'])):.{len(str(cs.src.scale)) - 1}f}"; workflow = "PLANNED"
        def lvl(k):
            v = body.get(k)
            return None if v in (None, "", 0) else f"{Decimal(str(v)):.{len(str(cs.src.scale)) - 1}f}"
        sl, tp = lvl("sl"), lvl("tp")
        if workflow == "PLANNED" and (sl is None or tp is None):
            raise ContractError("PLANNED_NEEDS_SL_TP", "pending orders need both SL and TP in this engine")
        pay = dict(side=side, orderType=typ, workflow=workflow, entry=entry, quantity=str(body.get("lots", "0.01")), sl=sl, tp=tp,
                   riskPercent="1", observations=[])
        S["serial"] = S.get("serial", 0) + 1
        S["meta_orders"][f"order:{S['serial']}"] = dict(side="BUY" if side == "LONG" else "SELL")
        cs.command("OPEN", pay, f"order:{S['serial']}"); save(); return session_json()
    if path in ("/api/close", "/api/cancel"):
        kind = "CLOSE" if path.endswith("close") else "CANCEL"
        pay = dict(orderId=body["orderId"], quantity=None) if kind == "CLOSE" else dict(orderId=body["orderId"])
        S["serial"] = S.get("serial", 0) + 1
        log_events(cs.command(kind, pay, f"{kind.lower()}:{body['orderId']}:{S['serial']}"))
        # a manual close fills on the NEXT revealed quote (reference semantics): advance the smallest step
        save(); return session_json()
    raise KeyError(path)


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _send(self, code, payload, ctype="application/json"):
        data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path in ("/", "/index.html"):
            return self._send(200, (HERE / "index.html").read_bytes(), "text/html; charset=utf-8")
        self._handle(u, {})

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        self._handle(urlparse(self.path), json.loads(self.rfile.read(n) or b"{}"))

    def _handle(self, u, body):
        with LOCK:
            try:
                self._send(200, api(u.path, parse_qs(u.query), body))
            except ContractError as e:
                self._send(400, dict(error=f"{e.code}: {e.field}"))
            except Exception as e:          # surface, never swallow
                self._send(500, dict(error=f"{type(e).__name__}: {e}"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", required=True); ap.add_argument("--ticks", type=int, default=400000); ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--pair", default="XAUUSD", help="XAUUSD (Dukascopy zip) or EURUSD/GBPUSD/AUDUSD/NZDUSD (HistData-UTC zip)"); ap.add_argument("--port", type=int, default=8765); ap.add_argument("--cache", default=str(Path(tempfile.gettempdir()) / "riksora_local_trader"))
    ap.add_argument("--fresh", action="store_true", help="ignore a saved session")
    a = ap.parse_args()
    src, profile, seed, meta = open_session(a.zip, a.offset, a.ticks, a.cache, a.pair)
    S.update(src=src, meta=meta, events=[], trades=[], meta_orders={})
    S["snap_path"] = Path(a.cache) / f"session_{meta['adm']['manifestHash'][:12]}.json"
    cs = ClaudeSession(src, profile, policy(), seed, archive=True)     # order archiving: constant-cost commands in long sessions
    if S["snap_path"].exists() and not a.fresh:
        saved = json.loads(S["snap_path"].read_text())
        cs = ClaudeSession.recover(src, profile, policy(), seed, saved["snapshot"]); S["events"] = saved["events"]; S["trades"] = saved.get("trades", []); S["meta_orders"] = saved.get("meta_orders", {})
        print("[session] resumed from verified snapshot (hash chain + state checked)")
    S["cs"] = cs
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), H)
    print(f"[ready] http://127.0.0.1:{a.port}  ({src.ngroups} tick groups)", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
