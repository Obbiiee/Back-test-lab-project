"""BTL-CHART-HISTORY-PAGE-1: authenticated, cursor-bound chart history from precomputed OHLC objects (additive; BTL-PAST-CHART-CONTEXT-1 unchanged)."""
import json
import tempfile
import unittest
from pathlib import Path

from cloud.chart_history import ChartHistory
from contracts.primitives import ContractError
from market_data.compact_tick import write_compact, CompactTickReader
from tools.claude_exp.ohlc import engine, service as svc
from tools.claude_exp.ohlc.store import LocalObjectStore
from tools.claude_exp.ohlc.test_service import make_ticks, ts, NS, SCALE

DATASET_ID = "local:test:chartpage"


def world():
    ticks = [t for t in make_ticks() if t[0] < ts("2026-05-08T12:00:00")]
    root = Path(tempfile.mkdtemp(prefix="ch-t-")) / "c"
    m = write_compact(root, ({"timeNs": str(t), "bid": b, "ask": a, "rawOrdinal": str(i)} for i, (t, b, a) in enumerate(ticks)),
                      parent=dict(datasetId="local:test:ch", datasetVersion="b" * 64), scale=SCALE)
    reader = CompactTickReader(root, expected_manifest_hash=m["manifestHash"])
    store_dir = tempfile.mkdtemp(prefix="ch-s-")
    store = LocalObjectStore(store_dir)
    for month in ("2026-04", "2026-05"):
        engine.publish_month(store, reader, "TESTUSD", month, basis="BID", rights="SYNTHETIC")
    return reader, store_dir, m["manifestHash"]


class ChartHistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reader, cls.store_dir, cls.source = world()

    def history(self, cursor_ns, *, owners=None, revision=None, dataset_id=DATASET_ID):
        self.calls = dict(authorize=0, cursor=0)
        self.state = dict(revision=revision or 1, through=cursor_ns)
        owners = owners if owners is not None else {("w1", "s1"): "alice"}

        def authorize(actor, workspace, session):
            self.calls["authorize"] += 1
            if owners.get((str(workspace), str(session))) != str(actor):
                raise ContractError("RESOURCE_UNAVAILABLE", "session")      # a foreign or unknown Session answers the same
            return self.state["revision"]

        def cursor_loader(actor, workspace, session):
            self.calls["cursor"] += 1
            return dict(revision=self.state["revision"], throughNs=str(self.state["through"]), datasetId=dataset_id, datasetVersion="v")
        registry = dict(schemaVersion=1, store=self.store_dir, basis="BID",
                        rules=[dict(datasetIdPrefix="local:test:", instrument="TESTUSD", sourceHashes=[self.source], tickRoot=None)])
        chart = ChartHistory(registry, authorize=authorize, cursor_loader=cursor_loader)
        chart.tick_reader = lambda rule, ns: self.reader
        return chart

    def reference(self, cursor_ns, tf, **kw):
        """The prototype core with its own token map, as an independent route to the same bars."""
        s = svc.Session("s", "u", "TESTUSD", self.source, "BID", cursor_ns)
        service = svc.ChartService(LocalObjectStore(self.store_dir), {"TESTUSD": self.reader}, {"s": s}, {"t": "u"})
        return service.bars("t", "s", tf, kw.get("limit"), kw.get("before"))

    def test_first_page_has_only_completed_bars_and_a_forming_bar_from_revealed_ticks(self):
        T = ts("2026-05-06T01:07:31.250")           # inside the synthetic day's tick activity, so a forming bar exists
        chart = self.history(T)
        page = chart.page("alice", "w1", "s1", timeframe="5m")
        self.assertEqual(page["artifact"], "BTL-CHART-HISTORY-PAGE-1")
        self.assertFalse(page["executionAuthority"])
        self.assertEqual(page["evidence"], "DERIVED_NON_AUTHORITATIVE_DISPLAY_ONLY")
        self.assertEqual(page["cursorNs"], str(T))
        self.assertLessEqual(len(page["candles"]), 512)
        self.assertTrue(all(c["time"] * NS + 300 * NS <= T for c in page["candles"]), "a bar that ends after the cursor left the trust boundary")
        want = self.reference(T, "M5")
        self.assertEqual([c["time"] for c in page["candles"]], [t // NS for t in want["bars"]["t"]][-len(page["candles"]):])
        self.assertIsNotNone(page["forming"])
        self.assertEqual(page["forming"]["time"], want["active"]["t"] // NS)
        self.assertNotIn("ohlc/", json.dumps(page), "no object key may reach the client")

    def test_paging_reaches_the_end_and_says_so(self):
        T = ts("2026-05-06T10:07:31.250")
        chart = self.history(T)
        bars, before, pages = [], None, 0
        while True:
            page = chart.page("alice", "w1", "s1", timeframe="15m", limit=100, before=before)
            bars = page["candles"] + bars
            pages += 1
            self.assertLess(pages, 200)
            if not page["hasMore"]:
                self.assertTrue(page["historyExhausted"]); self.assertIsNone(page["nextBefore"]); break
            self.assertFalse(page["historyExhausted"]); before = page["nextBefore"]
        times = [c["time"] for c in bars]
        self.assertEqual(times, sorted(set(times)), "pages must tile without gaps, overlap or reordering")
        self.assertEqual(len(times), len(self.reference(T, "M15", limit=1000)["bars"]["t"]) if len(times) <= 1000 else len(times))

    def test_foreign_and_unknown_sessions_are_refused_identically_before_any_cursor_read(self):
        T = ts("2026-05-06T10:07:31.250")
        chart = self.history(T)
        for actor, session in (("mallory", "s1"), ("alice", "s-unknown")):
            with self.assertRaises(ContractError) as refused:
                chart.page(actor, "w1", session, timeframe="1h")
            self.assertEqual((refused.exception.code, refused.exception.field), ("RESOURCE_UNAVAILABLE", "session"))
        self.assertEqual(self.calls["cursor"], 0, "the durable cursor must not be read for an unauthorised caller")

    def test_cursor_is_cached_per_revision_and_follows_a_revision_change(self):
        chart = self.history(ts("2026-05-05T10:07:00"))
        first = chart.page("alice", "w1", "s1", timeframe="1h")
        chart.page("alice", "w1", "s1", timeframe="1h")
        self.assertEqual(self.calls["cursor"], 1, "same revision must reuse the pinned cursor")
        self.state.update(revision=2, through=ts("2026-05-06T15:00:00"))
        later = chart.page("alice", "w1", "s1", timeframe="1h")
        self.assertEqual(self.calls["cursor"], 2)
        self.assertGreater(later["candles"][-1]["time"], first["candles"][-1]["time"])
        self.assertEqual(later["revision"], 2)

    def test_hostile_parameters_are_refused(self):
        T = ts("2026-05-06T10:07:31.250")
        chart = self.history(T)
        bad = [dict(timeframe="7m"), dict(timeframe="1h", limit=0), dict(timeframe="1h", limit=1001), dict(timeframe="1h", limit="5"),
               dict(timeframe="1h", before=-1), dict(timeframe="1h", before=(T // NS) + 10_000)]       # `before` after the cursor
        for kwargs in bad:
            with self.assertRaises(ContractError, msg=str(kwargs)):
                chart.page("alice", "w1", "s1", **kwargs)

    def test_dataset_without_a_registry_rule_is_refused_not_served_from_another_source(self):
        chart = self.history(ts("2026-05-06T10:07:31.250"), dataset_id="other:dataset:1")
        with self.assertRaises(ContractError) as refused:
            chart.page("alice", "w1", "s1", timeframe="1h")
        self.assertEqual(refused.exception.field, "chartSource")


if __name__ == "__main__":
    unittest.main()
