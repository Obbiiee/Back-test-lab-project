"""Owner-admitted HistData months: authored stores, pure kernel transitions."""
from copy import deepcopy
from datetime import datetime, timezone
import gzip
from pathlib import Path
import tempfile
import unittest

from contracts.models import MethodPolicy
from contracts.primitives import ContractError
from execution.admission_v2 import AdmittedSource, AdmittedSourceJoin, admission_record, admitted_source_pin
from execution.kernel_v2 import advance, seed_state, submit, validate_snapshot
from execution.profile_v2 import ADMITTED_MODEL, ExecutionProfileV2
from tests.test_profile_v2 import vectors
from ticks.histdata_v2 import HistDataIngestion

REPORT = "c" * 64


def ns(text):
    return int(datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()) * 10**9


def write_month(root, symbol, period, rows):
    path = root / f"{symbol}_{period}.csv.gz"
    body = "timestamp_utc,bid,ask\n" + "".join(f"{t},{b},{a}\n" for t, b, a in rows)
    path.write_bytes(gzip.compress(body.encode(), mtime=0))
    with HistDataIngestion(path, root / f"store-{period}", symbol, first_rows=None, packing=(2, 1, 2)) as intake:
        report = intake.run()
    return dict(period=period, datasetId=report["datasetId"], datasetVersion=report["datasetVersion"],
                validationReportHash=REPORT), root / f"store-{period}"


def profile_for(record, symbol="EURUSD"):
    raw = deepcopy(next(v["input"] for v in vectors() if v["name"] == symbol))
    raw.update(model=ADMITTED_MODEL, primary=admitted_source_pin(record))
    return ExecutionProfileV2.from_wire(raw)


def opening(entry, side="LONG", lots="0.01", tp=None, sl=None):
    return dict(side=side, orderType="MARKET", workflow="QUICK", entry=entry, quantity=lots, sl=sl, tp=tp,
                riskPercent="1", observations=[])


class Harness:
    def __init__(self, profile, source, start):
        self.profile, self.source = profile, source
        self.checkpoint = AdmittedSourceJoin(profile, source, start_ns=str(start)).checkpoint()
        self.state = seed_state("fixture:admitted", profile, MethodPolicy("fixture:free", "0" * 64, "FREE_STYLE", False, ()),
                                self.checkpoint)
        self.events = []

    def apply(self, kind, payload=None, cid=None):
        cmd = dict(schemaVersion=1, artifact="BTL-TICK-EXECUTION-COMMAND-2", sessionId=self.state["sessionId"],
                   commandId=cid or "cmd:" + str(self.state["revision"]), expectedRevision=self.state["revision"],
                   kind=kind, payload=payload or {})
        join = basis = None
        if kind in ("OPEN", "ADVANCE"):
            join = AdmittedSourceJoin.resume(self.profile, self.source, self.checkpoint)
            if kind == "OPEN":
                basis = join.risk_basis(join.checkpoint())
        proposed, events = submit(self.state, cmd, basis)
        cp = self.checkpoint
        if kind == "ADVANCE":
            frame = join.reveal(payload["targetNs"], join.checkpoint())
            proposed, more = advance(proposed, frame, payload["targetNs"]); events += more; cp = frame["checkpoint"]
        elif kind == "OPEN":
            cp = basis["checkpoint"]
        proposed["revision"] += 1
        validate_snapshot(proposed, cp)
        self.state, self.checkpoint = proposed, cp
        self.events += events
        return frame if kind == "ADVANCE" else None

    def tick(self, t):
        return self.apply("ADVANCE", dict(targetNs=str(t)))


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        nov, nov_folder = write_month(self.root, "EURUSD", "2024-11", [
            ("2024-11-01T05:00:00.000Z", "1.10000", "1.10002"),
            ("2024-11-01T05:01:00.000Z", "1.10010", "1.10012"),
            ("2024-11-01T05:02:00.000Z", "1.10100", "1.10102"),
            ("2024-11-01T05:03:00.000Z", "1.10200", "1.10202"),
            ("2024-11-01T05:03:00.000Z", "1.10300", "1.10302"),
            ("2024-11-29T21:00:00.000Z", "1.10400", "1.10402")])
        dec, dec_folder = write_month(self.root, "EURUSD", "2024-12", [
            ("2024-12-02T00:00:00.000Z", "1.10500", "1.10502"),
            ("2024-12-02T00:01:00.000Z", "1.10600", "1.10602")])
        self.record = admission_record("EURUSD", [nov, dec])
        self.source = AdmittedSource(self.record, [nov_folder, dec_folder])
        self.profile = profile_for(self.record)
        self.start = ns("2024-11-01T05:00:00Z")

    def tearDown(self):
        self.source.close(); self.tmp.cleanup()

    def test_profile_accepts_only_the_admission_overlay(self):
        self.assertEqual(self.profile.wire["primary"]["evidenceClass"], "ADMITTED_OBSERVATION")
        raw = deepcopy(self.profile.wire)
        for change in (dict(evidenceClass="PROVIDER_OBSERVATION"), dict(datasetId=self.record["months"][0]["datasetId"]),
                       dict(feedInstrumentId="histdata:GBPUSD")):
            bad = deepcopy(raw); bad["primary"].update(change)
            with self.assertRaises(ContractError) as error:
                ExecutionProfileV2.from_wire(bad)
            self.assertEqual(error.exception.code, "REFUSED_V2_REAL_SOURCE")
        synthetic = deepcopy(raw); synthetic["model"] = "AUTHORED_SYNTHETIC_ONLY"
        with self.assertRaises(ContractError):
            ExecutionProfileV2.from_wire(synthetic)
        usdjpy = deepcopy(next(v["input"] for v in vectors() if v["name"] == "USDJPY"))
        record = dict(self.record, symbol="USDJPY")
        usdjpy.update(model=ADMITTED_MODEL, primary=admitted_source_pin(record))
        with self.assertRaises(ContractError):
            ExecutionProfileV2.from_wire(usdjpy)

    def test_admission_record_refuses_gaps_prefixes_and_unhashed_reports(self):
        nov, dec = self.record["months"]
        cases = [[nov, dict(dec, period="2025-01")], [dict(nov, datasetId=nov["datasetId"] + ":first:10")],
                 [dict(nov, validationReportHash="nothex")], []]
        for months in cases:
            with self.subTest(months=months), self.assertRaises(ContractError):
                admission_record("EURUSD", months)
        self.assertEqual(admission_record("EURUSD", [nov, dec]), self.record)

    def test_source_refuses_wrong_symbol_or_store(self):
        nov, dec = self.record["months"]
        with self.assertRaises(ContractError):
            AdmittedSource(admission_record("GBPUSD", [nov, dec]), [self.root / "store-2024-11", self.root / "store-2024-12"])
        with self.assertRaises(ContractError):
            AdmittedSource(self.record, [self.root / "store-2024-12", self.root / "store-2024-11"])
        self.assertEqual(self.source.start_for_period("2024-12"), ns("2024-12-02T00:00:00Z"))
        with self.assertRaises(ContractError):
            self.source.start_for_period("2024-10")

    def test_market_order_fills_and_take_profit_from_admitted_ticks(self):
        h = Harness(self.profile, self.source, self.start)
        frame = h.tick(self.start)
        self.assertEqual(len(frame["pairs"]), 1)
        row = frame["pairs"][0]["primaryGroup"]["events"][0]
        self.assertEqual((row["datasetId"], row["quality"]["freshness"], row["quality"]["gapBefore"]),
                         (self.profile.wire["primary"]["datasetId"], "CONFIRMED", "NONE"))
        self.assertEqual((row["bid"], row["ask"]), ("1.1", "1.10002"))
        h.apply("OPEN", opening("1.10002", lots="1", tp="1.101"), "open")
        h.tick(ns("2024-11-01T05:01:00Z"))
        self.assertEqual(h.state["orders"]["open"]["entryPrice"], "1.10012")
        h.tick(ns("2024-11-01T05:02:00Z"))
        self.assertEqual(h.state["orders"]["open"]["status"], "CLOSED")
        self.assertEqual(h.state["balance"], "10088")
        self.assertFalse(h.state["unresolved"])
        fills = [e for e in h.events if e["classification"] == "SIMULATED_FILL"]
        self.assertEqual(len(fills), 2)
        self.assertTrue(all(e["datasetId"].startswith("admitted:histdata:EURUSD:") for e in h.events))

    def test_replay_crosses_admitted_months_and_stops_at_the_end(self):
        h = Harness(self.profile, self.source, self.start)
        frame = h.tick(ns("2024-12-02T00:00:30Z"))
        self.assertEqual(len(frame["pairs"]), 6)
        self.assertEqual(frame["primaryCoverage"][0]["status"], "DECLARED_COMPLETE")
        self.assertFalse(h.state["unresolved"])
        before = deepcopy(h.state)
        with self.assertRaises(ContractError) as error:
            h.tick(ns("2024-12-31T00:00:00Z"))
        self.assertEqual(error.exception.code, "REFUSED_V2_SOURCE_WINDOW")
        self.assertEqual(h.state, before)

    def test_equal_time_differing_quotes_never_fill_silently(self):
        h = Harness(self.profile, self.source, self.start)
        h.tick(ns("2024-11-01T05:02:00Z"))
        h.apply("OPEN", opening("1.10102", lots="1", tp="1.1025"), "open")
        h.tick(ns("2024-11-01T05:03:00Z"))
        self.assertTrue(h.state["unresolved"])
        self.assertTrue(any(e["kind"] == "UNRESOLVED" and e["detail"]["reason"] == "UNRESOLVED_EQUAL_TIME_ORDER" for e in h.events))

    def test_cold_resume_and_tampered_checkpoint(self):
        h = Harness(self.profile, self.source, self.start)
        h.tick(ns("2024-11-01T05:02:00Z"))
        resumed = AdmittedSourceJoin.resume(self.profile, self.source, h.checkpoint)
        self.assertEqual(resumed.checkpoint(), h.checkpoint)
        self.assertEqual([g["timeNs"] for g in resumed.past_primary(h.checkpoint, 2)],
                         [str(ns("2024-11-01T05:01:00Z")), str(ns("2024-11-01T05:02:00Z"))])
        forged = deepcopy(h.checkpoint); forged["primary"]["cursor"]["lastGroupId"] = "f" * 64
        with self.assertRaises(ContractError):
            AdmittedSourceJoin.resume(self.profile, self.source, forged)
        other = profile_for(admission_record("EURUSD", self.record["months"][:1]))
        with self.assertRaises(ContractError):
            AdmittedSourceJoin(other, self.source, start_ns=str(self.start))

    def test_group_budget_continues_with_pending_target(self):
        rows = [(f"2025-01-02T{h:02d}:{m:02d}:00.000Z", f"1.2{h:02d}{m:02d}", f"1.2{h:02d}{m + 1:02d}") for h in range(2) for m in range(40)]
        jan, folder = write_month(self.root, "EURUSD", "2025-01", rows)
        record = admission_record("EURUSD", [jan])
        with AdmittedSourceGuard(record, [folder]) as source:
            profile = profile_for(record)
            start = ns("2025-01-02T00:00:00Z")
            h = Harness(profile, source, start)
            target = ns("2025-01-02T01:39:00Z")
            first = h.tick(target)
            self.assertEqual((len(first["pairs"]), first["exhaustedThroughBoundary"]), (64, False))
            second = h.tick(target)
            self.assertEqual((len(second["pairs"]), second["exhaustedThroughBoundary"]), (16, True))
            self.assertEqual(h.state["nextGroupIndex"], "80")


class AdmittedSourceGuard:
    def __init__(self, record, folders):
        self.source = AdmittedSource(record, folders)

    def __enter__(self):
        return self.source

    def __exit__(self, *_):
        self.source.close()


if __name__ == "__main__":
    unittest.main()
