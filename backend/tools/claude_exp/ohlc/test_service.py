"""No-lookahead, tenant isolation and abuse tests against the REAL HTTP chart API (stdlib server on a loopback port).

    python -m unittest tools.claude_exp.ohlc.test_service        (from backend/, project-pinned Python)

The expected answer for every cursor is computed by the independent oracle from ticks <= T only. A "canary" regime of future ticks carries
a price that exists nowhere before the cursor; the canary price must never appear in any byte served for an earlier cursor.
The object store is the local SIMULATION (not Cloudflare R2).
"""
import json
import random
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timezone
from fractions import Fraction
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from market_data.compact_tick import write_compact, CompactTickReader     # noqa: E402
from tools.claude_exp.ohlc import oracle, engine, service as svc         # noqa: E402
from tools.claude_exp.ohlc.store import LocalObjectStore                  # noqa: E402

NS = 10**9
SCALE = 5
CANARY_BID, CANARY_ASK = "7.77770", "7.77790"        # mid 7.77780 = 777780 in scale-5 units, 1555560 on the 2S grid
CANARY_2S = 1555560


def ts(text):
    base, _, frac = text.partition(".")
    return int(datetime.fromisoformat(base).replace(tzinfo=timezone.utc).timestamp()) * NS + int(frac.ljust(9, "0")[:9] or 0)


def make_ticks():
    """Mid-April to mid-May 2026: weekday activity with weekend gaps, a month boundary, equal timestamps, and canary ticks after CUT."""
    rnd = random.Random(11)
    ticks, p = [], 1.1
    day = ts("2026-04-27T00:00:00")
    for d in range(18):
        start = day + d * 86400 * NS
        if datetime.fromtimestamp(start // NS, timezone.utc).weekday() >= 5:
            continue
        t = start + 60 * NS
        for _ in range(900):
            t += rnd.choice([0, 1, 5, 30, 400]) * 10**8
            p = min(1.2, max(1.0, p + rnd.uniform(-0.0004, 0.0004)))
            ticks.append((t, f"{p:.5f}", f"{p + 0.00012:.5f}"))
    return ticks


def build_world():
    ticks = make_ticks()
    cut = ts("2026-05-08T12:00:00")
    # future canary: from CUT onward every tick is the canary quote (a spike no real tick resembles)
    ticks = [t for t in ticks if t[0] < cut] + [(cut + i * 7 * NS, CANARY_BID, CANARY_ASK) for i in range(1, 60)]
    root = Path(tempfile.mkdtemp(prefix="svc-t-")) / "c"
    m = write_compact(root, ({"timeNs": str(t), "bid": b, "ask": a, "rawOrdinal": str(i)} for i, (t, b, a) in enumerate(ticks)),
                      parent=dict(datasetId="local:test:svc", datasetVersion="b" * 64), scale=SCALE)
    reader = CompactTickReader(root, expected_manifest_hash=m["manifestHash"])
    store = LocalObjectStore(tempfile.mkdtemp(prefix="svc-s-"))
    for month in ("2026-04", "2026-05"):
        engine.publish_month(store, reader, "TESTUSD", month, rights="SYNTHETIC")
    return ticks, cut, reader, store, m["manifestHash"]


class World(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ticks, cls.cut, cls.reader, cls.store, cls.src = build_world()
        cls.sessions = {"s-alice": svc.Session("s-alice", "alice", "TESTUSD", cls.src, "MID", ts("2026-05-06T10:07:31.250")),
                        "s-bob": svc.Session("s-bob", "bob", "TESTUSD", cls.src, "MID", ts("2026-05-05T03:00:00"))}
        cls.service = svc.ChartService(cls.store, {"TESTUSD": cls.reader}, cls.sessions, {"tok-alice": "alice", "tok-bob": "bob"})
        cls.metrics = []
        cls.http = ThreadingHTTPServer(("127.0.0.1", 0), svc.make_handler(cls.service, cls.metrics))
        cls.port = cls.http.server_address[1]
        threading.Thread(target=cls.http.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()

    def get(self, query, token="tok-alice"):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/v1/chart/bars?{query}", headers={"Authorization": f"Bearer {token}"} if token else {})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, r.read(), dict(r.headers)
        except urllib.error.HTTPError as e:
            return e.code, e.read(), dict(e.headers)

    def page_all(self, session, tf, T):
        """Follow nextBefore until the history ends; returns the concatenated bars (oldest first) and every raw body."""
        bodies, rows, before = [], [], None
        while True:
            q = f"session={session}&tf={tf}&limit=1000" + (f"&before={before}" if before else "")
            status, raw, _ = self.get(q)
            self.assertEqual(status, 200, raw)
            bodies.append(raw)
            j = json.loads(raw)
            rows = [dict(zip("tohlcn", v)) for v in zip(*[j["bars"][k] for k in "tohlcn"])] + rows
            if not j["hasMore"]:
                return rows, bodies, j
            before = j["nextBefore"]

    def expected(self, tf, T, basis="MID"):
        seconds = dict(oracle.TIMEFRAMES)[tf]
        done, active = oracle.at_cursor(self.ticks, seconds, T, basis)
        return done, active

    def as_ints(self, bar, scale=SCALE):
        den = 2 * 10 ** scale
        f = lambda x: int(x * den)
        return dict(t=bar["t"], o=f(bar["o"]), h=f(bar["h"]), l=f(bar["l"]), c=f(bar["c"]), n=bar["n"])


class NoLookahead(World):
    def test_every_timeframe_matches_oracle_at_many_cursors(self):
        cursors = [ts("2026-04-27T00:01:00"), ts("2026-04-28T09:30:00"), ts("2026-05-01T00:00:00"), ts("2026-05-04T22:17:41.5"),
                   ts("2026-05-06T10:07:31.25"), ts("2026-05-08T11:59:59.999"), self.cut - 1, ts("2026-05-02T12:00:00")]
        for T in cursors:
            sess = svc.Session("s-x", "alice", "TESTUSD", self.src, "MID", T)
            self.sessions["s-x"] = sess
            for tf, _ in oracle.TIMEFRAMES:
                rows, bodies, last = self.page_all("s-x", tf, T)
                done, _ = self.expected(tf, T)
                self.assertEqual(rows, [self.as_ints(b) for b in done], f"{tf} T={T}")
                status, raw, _ = self.get(f"session=s-x&tf={tf}")
                first = json.loads(raw)
                _, active = self.expected(tf, T)
                if active is None:
                    self.assertIsNone(first["active"], f"{tf} T={T}")
                else:
                    got = first["active"]
                    exp = self.as_ints(active)
                    self.assertEqual({k: got[k] for k in "tohlcn"}, exp, f"active {tf} T={T}")
                    self.assertEqual((got["first"], got["last"]), (active["first"], active["last"]))
                for raw in bodies + [raw]:
                    j = json.loads(raw)
                    self.assertTrue(all(t + dict(oracle.TIMEFRAMES)[tf] * NS <= T for t in j["bars"]["t"]), "a served bar ends after the cursor")
            del self.sessions["s-x"]

    def test_canary_future_price_never_leaks(self):
        before_cut = [ts("2026-05-08T11:59:59"), ts("2026-05-08T00:00:00"), ts("2026-05-07T23:59:59.999"), ts("2026-05-08T11:30:00")]
        for T in before_cut:
            self.sessions["s-c"] = svc.Session("s-c", "alice", "TESTUSD", self.src, "MID", T)
            for tf, _ in oracle.TIMEFRAMES:
                for q in (f"session=s-c&tf={tf}", f"session=s-c&tf={tf}&limit=1000"):
                    status, raw, _ = self.get(q)
                    j = json.loads(raw)
                    values = [v for col in ("o", "h", "l", "c") for v in j["bars"][col]] + ([j["active"][c] for c in "ohlc"] if j["active"] else [])
                    self.assertNotIn(CANARY_2S, values, f"canary leaked in {tf} at T={T}")
                    self.assertTrue(all(v < 400000 for v in values), "an implausible future value appeared")
            del self.sessions["s-c"]
        # once the cursor passes the canary regime it IS revealed (control: the test can detect the canary)
        self.sessions["s-c"] = svc.Session("s-c", "alice", "TESTUSD", self.src, "MID", self.cut + 30 * NS)
        status, raw, _ = self.get("session=s-c&tf=M1")
        j = json.loads(raw)
        self.assertIn(CANARY_2S, j["bars"]["o"] + j["bars"]["h"] + [j["active"]["h"]])
        del self.sessions["s-c"]

    def test_replay_resume_and_repeated_timeframe_switching(self):
        rnd = random.Random(5)
        self.sessions["s-r"] = svc.Session("s-r", "alice", "TESTUSD", self.src, "MID", ts("2026-04-28T00:00:00"))
        T = self.sessions["s-r"].cursor_ns
        for step in range(40):
            T += rnd.choice([1, 59, 3000, 20_000, 400_000]) * NS // rnd.choice([1, 1000])
            if T >= self.cut:
                break
            self.service.advance("s-r", T)
            tf = rnd.choice([n for n, _ in oracle.TIMEFRAMES])
            status, raw, _ = self.get(f"session=s-r&tf={tf}&limit=50")
            j = json.loads(raw)
            done, active = self.expected(tf, T)
            self.assertEqual([dict(zip("tohlcn", v)) for v in zip(*[j["bars"][k] for k in "tohlcn"])], [self.as_ints(b) for b in done[-50:]])
            self.assertEqual(j["revision"], self.sessions["s-r"].revision)
        del self.sessions["s-r"]

    def test_cursor_cannot_move_backwards_and_stale_revision_is_refused(self):
        self.sessions["s-v"] = svc.Session("s-v", "alice", "TESTUSD", self.src, "MID", ts("2026-05-05T10:00:00"))
        with self.assertRaises(svc.ServiceError):
            self.service.advance("s-v", ts("2026-05-05T09:00:00"))
        self.service.advance("s-v", ts("2026-05-05T10:00:01"))
        status, raw, _ = self.get("session=s-v&tf=M5&rev=0")
        self.assertEqual((status, json.loads(raw)["error"]), (409, "STALE_REVISION"))
        status, _, _ = self.get("session=s-v&tf=M5&rev=1")
        self.assertEqual(status, 200)
        del self.sessions["s-v"]

    def test_first_page_is_512_and_pages_are_bounded(self):
        self.sessions["s-p"] = svc.Session("s-p", "alice", "TESTUSD", self.src, "MID", self.cut - NS)
        j = json.loads(self.get("session=s-p&tf=M1")[1])
        self.assertEqual(j["count"], 512)
        j2 = json.loads(self.get(f"session=s-p&tf=M1&limit=1000&before={j['nextBefore']}")[1])
        total = len(self.expected("M1", self.cut - NS)[0])
        self.assertGreater(total, 512)
        self.assertEqual(j["hasMore"], total > 512)
        self.assertEqual(j2["count"], min(1000, total - 512))
        self.assertNotIn("active", j2)
        self.assertLess(j2["bars"]["t"][-1], j["bars"]["t"][0])
        del self.sessions["s-p"]


class Attacks(World):
    def test_authentication_and_tenant_isolation(self):
        status, raw, _ = self.get("session=s-alice&tf=M1", token=None)
        self.assertEqual(status, 401)
        self.assertEqual(self.get("session=s-alice&tf=M1", token="forged")[0], 401)
        foreign = self.get("session=s-alice&tf=M1", token="tok-bob")
        unknown = self.get("session=s-nope&tf=M1", token="tok-bob")
        self.assertEqual((foreign[0], foreign[1]), (unknown[0], unknown[1]))      # existence is not revealed
        self.assertEqual(foreign[0], 404)
        self.assertEqual(self.get("session=s-bob&tf=M1", token="tok-bob")[0], 200)

    def test_malformed_and_hostile_parameters(self):
        bad = ["tf=M2", "tf=m1", "tf=W1", "tf=MN1", "tf=M1%3Bdrop", "tf=../../etc", "tf=", "tf=M1&limit=0", "tf=M1&limit=1001", "tf=M1&limit=-5",
               "tf=M1&limit=abc", "tf=M1&limit=1e3", "tf=M1&limit=99999999999999999999", "tf=M1&before=0", "tf=M1&before=-1", "tf=M1&before=abc",
               "tf=M1&rev=x", "tf=M1&before=%EF%BC%91%EF%BC%92"]
        for q in bad:
            status, raw, _ = self.get(f"session=s-alice&{q}")
            self.assertEqual(status, 400, q)
            self.assertEqual(json.loads(raw), {"error": "INVALID_REQUEST"})
        for sid in ("../s-alice", "s-alice%2F..", "%00", "s-alice%20", ""):
            self.assertEqual(self.get(f"session={sid}&tf=M1")[0], 404, sid)
        self.assertEqual(self.get("session=s-alice&tf=M1&x=y")[0], 200)

    def test_before_in_the_future_is_refused_not_clamped(self):
        T = self.sessions["s-alice"].cursor_ns
        self.assertEqual(self.get(f"session=s-alice&tf=M1&before={T + 1}")[0], 400)
        self.assertEqual(self.get(f"session=s-alice&tf=M1&before={self.cut}")[0], 400)
        self.assertEqual(self.get(f"session=s-alice&tf=M1&before={T}")[0], 200)

    def test_session_pins_cannot_be_overridden_by_the_request(self):
        for extra in ("basis=BID", "source=deadbeef", "cursor=999999999999999999", "instrument=OTHER", "T=1", "user=bob"):
            a = json.loads(self.get("session=s-alice&tf=H1")[1])
            b = json.loads(self.get(f"session=s-alice&tf=H1&{extra}")[1])
            self.assertEqual(a, b, extra)
            self.assertEqual((b["basis"], b["cursorNs"]), ("MID", self.sessions["s-alice"].cursor_ns))

    def test_no_cache_headers_and_no_object_keys_in_responses(self):
        status, raw, headers = self.get("session=s-alice&tf=D1")
        self.assertIn("no-store", headers["Cache-Control"])
        self.assertNotIn(b"ohlc/", raw)
        self.assertNotIn(b".parquet", raw)
        self.assertNotIn(b"s3://", raw)
        self.assertEqual(self.get("session=s-alice&tf=D1&limit=2")[0], 200)
        self.assertEqual(urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{self.port}/v1/chart/bars?session=s-alice&tf=D1", headers={"Authorization": "Bearer tok-alice"})).status, 200)
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{self.port}/v1/chart/object?key=ohlc/x")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 404)

    def test_error_bodies_do_not_leak_end_of_data_or_future_gaps(self):
        j = json.loads(self.get("session=s-alice&tf=M1&limit=1000")[1])
        self.assertEqual(set(j), {"schemaVersion", "session", "revision", "cursorNs", "tf", "basis", "den", "source", "volume", "bars", "count", "hasMore", "nextBefore", "active"})
        self.assertEqual(j["volume"], "NONE")

    def test_parallel_requests_keep_cursor_binding(self):
        results, errors = [], []

        def worker(user, token, sid):
            try:
                for _ in range(20):
                    j = json.loads(self.get(f"session={sid}&tf=M5&limit=100", token=token)[1])
                    results.append((user, j["cursorNs"]))
            except Exception as e:
                errors.append(e)
        ts_ = [threading.Thread(target=worker, args=a) for a in (("alice", "tok-alice", "s-alice"), ("bob", "tok-bob", "s-bob")) * 3]
        [t.start() for t in ts_]
        [t.join() for t in ts_]
        self.assertFalse(errors)
        for user, cursor in results:
            self.assertEqual(cursor, self.sessions["s-alice" if user == "alice" else "s-bob"].cursor_ns)


class ObjectStoreAdapter(unittest.TestCase):
    def test_s3_adapter_semantics_against_a_stub_client(self):
        from tools.claude_exp.ohlc.store import S3ObjectStore, Conflict

        class Err(Exception):
            response = {"Error": {"Code": "404"}}

        class Stub:
            def __init__(self):
                self.o, self.calls = {}, []

            def head_object(self, Bucket, Key):
                self.calls.append("HEAD")
                if Key not in self.o:
                    raise Err()
                d, m = self.o[Key]
                return {"ContentLength": len(d), "Metadata": m}

            def put_object(self, Bucket, Key, Body, IfNoneMatch, Metadata):
                self.calls.append("PUT")
                assert IfNoneMatch == "*"
                self.o[Key] = (Body, Metadata)

            def get_object(self, Bucket, Key, Range=None):
                self.calls.append("GET")
                d = self.o[Key][0]
                if Range:
                    a, b = Range[6:].split("-")
                    d = d[int(a):int(b) + 1]
                import io
                return {"Body": io.BytesIO(d)}

        c = Stub()
        s = S3ObjectStore(c, "bucket")
        self.assertTrue(s.put_immutable("k", b"abc"))
        self.assertFalse(s.put_immutable("k", b"abc"))
        with self.assertRaises(Conflict):
            s.put_immutable("k", b"abd")
        self.assertEqual(s.get_range("k", 1, 2), b"bc")
        self.assertEqual(c.calls.count("PUT"), 1)
        self.assertFalse(s.simulation)



class MultiDatasetCatalog(unittest.TestCase):
    """Product storage is one dataset per instrument-month (each with its own source hash): history must read across them exactly like one dataset."""

    def test_history_and_forming_bar_across_per_month_datasets_equal_a_single_dataset(self):
        cut = ts("2026-05-08T12:00:00")
        ticks = [t for t in make_ticks() if t[0] < cut]
        month = lambda ns: datetime.fromtimestamp(ns // NS, timezone.utc).strftime("%Y-%m")

        def compact(rows, name, fill):
            root = Path(tempfile.mkdtemp(prefix="svc-m-")) / "c"
            m = write_compact(root, ({"timeNs": str(t), "bid": b, "ask": a, "rawOrdinal": str(i)} for i, (t, b, a) in enumerate(rows)),
                              parent=dict(datasetId=f"local:test:{name}", datasetVersion=fill * 64), scale=SCALE)
            return CompactTickReader(root, expected_manifest_hash=m["manifestHash"]), m["manifestHash"]
        r_apr, h_apr = compact([t for t in ticks if month(t[0]) == "2026-04"], "apr", "a")
        r_may, h_may = compact([t for t in ticks if month(t[0]) == "2026-05"], "may", "c")
        r_all, h_all = compact(ticks, "all", "d")
        store, ref_store = LocalObjectStore(tempfile.mkdtemp(prefix="svc-s-")), LocalObjectStore(tempfile.mkdtemp(prefix="svc-s-"))
        engine.publish_month(store, r_apr, "TESTUSD", "2026-04", rights="SYNTHETIC")
        engine.publish_month(store, r_may, "TESTUSD", "2026-05", rights="SYNTHETIC")
        for m_ in ("2026-04", "2026-05"):
            engine.publish_month(ref_store, r_all, "TESTUSD", m_, rights="SYNTHETIC")
        for T in (ts("2026-05-06T10:07:31.250"), ts("2026-05-01T00:00:30"), ts("2026-04-30T23:59:59.500")):     # mid-May, just after and just before the boundary
            multi = svc.ChartService(store, {"TESTUSD": lambda ns: r_may if month(ns) == "2026-05" else r_apr},
                                     {"s": svc.Session("s", "u", "TESTUSD", h_may, "MID", T, source_hashes=(h_may, h_apr))}, {"tok": "u"})
            ref = svc.ChartService(ref_store, {"TESTUSD": r_all}, {"s": svc.Session("s", "u", "TESTUSD", h_all, "MID", T)}, {"tok": "u"})
            for tf in svc.TF_SECONDS:
                got, want = self._all(multi, tf), self._all(ref, tf)
                self.assertEqual(got, want, f"{tf} at {T}")
                self.assertGreater(len(got[0]["t"]), 0)

    @staticmethod
    def _all(service, tf):
        pages, before, active = [], None, None
        while True:
            out = service.bars("tok", "s", tf, 1000, before)
            if before is None:
                active = out.get("active")
            pages.append(out["bars"])
            if not out["hasMore"]:
                break
            before = out["nextBefore"]
        cols = {k: [x for p in reversed(pages) for x in p[k]] for k in pages[0]}
        return cols, active

if __name__ == "__main__":
    unittest.main()
