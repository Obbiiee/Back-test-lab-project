"""Admission registry and the research Session route over admitted months."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
import uuid

from application.models import TrustedScope
from contracts.canonical import content_hash
from contracts.primitives import ContractError
from execution.registry_v2 import Registry, main as build_registry
from execution.research_fixture_v2 import catalogue as fixture_catalogue
from tests.test_admission_v2 import ns
from tests.test_execution_v2_postgres import command
from tests.test_research_sessions import method
from ticks.histdata_v2 import HistDataIngestion

DSN = os.getenv("BTL_TEST_DATABASE_URL")


def intake(root, symbol, period, rows):
    """Full-file intake exactly as the operator CLI writes it: store plus report JSON."""
    source = root / f"{symbol}_{period}.csv.gz"
    source.write_bytes(gzip.compress(("timestamp_utc,bid,ask\n" + "".join(f"{t},{b},{a}\n" for t, b, a in rows)).encode(), mtime=0))
    store, report = root / f"store-{symbol}-{period}", root / f"report-{symbol}-{period}.json"
    with HistDataIngestion(source, store, symbol, first_rows=None, packing=(2, 1, 2)) as job:
        report.write_text(json.dumps(job.run()))
    return str(store), str(report)


class RegistryFixture:
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        nov = intake(self.root, "EURUSD", "2024-11", [
            ("2024-11-01T05:00:00.000Z", "1.10000", "1.10002"),
            ("2024-11-01T05:01:00.000Z", "1.10010", "1.10012"),
            ("2024-11-29T21:00:00.000Z", "1.10400", "1.10402")])
        dec = intake(self.root, "EURUSD", "2024-12", [
            ("2024-12-02T00:00:00.000Z", "1.10500", "1.10502"),
            ("2024-12-02T00:00:15.000Z", "1.10600", "1.10602"),
            ("2024-12-02T00:00:30.000Z", "1.10700", "1.10702")])
        self.path = self.root / "private" / "registry.json"; self.path.parent.mkdir()
        build_registry(["--out", str(self.path), "--entry", "EURUSD", *nov, *dec])
        self.registry = Registry(self.path)

    def tearDown(self):
        self.registry.close(); self.tmp.cleanup()


class RegistryTests(RegistryFixture, unittest.TestCase):
    def test_without_registry_only_the_unchanged_demos_exist(self):
        empty = Registry()
        self.assertEqual(empty.catalogue(), fixture_catalogue())
        b = empty.session_bundle("EURUSD", "2020-01")
        self.assertEqual(empty.binding(b.profile.wire).profile.profile_hash, b.profile.profile_hash)
        with self.assertRaises(ContractError) as error:
            empty.session_bundle("EURUSD", "2024-11")
        self.assertEqual(error.exception.code, "REFUSED_FIXTURE_PERIOD")

    def test_catalog_lists_admitted_months_and_keeps_other_demos(self):
        rows = {r["symbol"]: r for r in self.registry.catalogue()}
        self.assertEqual(rows["EURUSD"]["periods"], ["2024-11", "2024-12"])
        self.assertEqual((rows["EURUSD"]["model"], rows["EURUSD"]["dataLabel"]), ("HISTORICAL_ADMITTED_V1", "Historical · beta"))
        self.assertEqual(rows["GBPUSD"], next(r for r in fixture_catalogue() if r["symbol"] == "GBPUSD"))
        self.assertNotIn(str(self.root), json.dumps(self.registry.catalogue()))
        stored = json.loads(self.path.read_text())["entries"][0]
        self.assertTrue(all(not Path(f).is_absolute() for f in stored["folders"]))
        report = (self.root / "report-EURUSD-2024-11.json").read_bytes()
        self.assertEqual(stored["record"]["months"][0]["validationReportHash"], hashlib.sha256(report).hexdigest())

    def test_session_bundle_starts_at_the_chosen_month_and_binding_is_pinned(self):
        b = self.registry.session_bundle("EURUSD", "2024-12")
        self.assertEqual(b.start_ns, ns("2024-12-02T00:00:00Z"))
        self.assertEqual(self.registry.binding(b.profile.wire).profile.profile_hash, b.profile.profile_hash)
        self.assertTrue(self.registry.period_allowed(b.profile.wire, "2024-11"))
        self.assertFalse(self.registry.period_allowed(b.profile.wire, "2025-01"))
        for period in ("2025-01", "2020-01"):
            with self.assertRaises(ContractError) as error:
                self.registry.session_bundle("EURUSD", period)
            self.assertEqual(error.exception.code, "REFUSED_HISTDATA_PERIOD")
        with self.assertRaises(ContractError) as error:
            Registry().binding(b.profile.wire)
        self.assertEqual(error.exception.code, "SOURCE_VERSION_UNAVAILABLE")

    def test_builder_refuses_prefix_reports_and_missing_routes(self):
        store, report = intake(self.root, "EURJPY", "2024-11", [("2024-11-01T05:00:00.000Z", "160.000", "160.002")])
        with self.assertRaises(ContractError) as error:
            build_registry(["--out", str(self.root / "jpy.json"), "--entry", "EURJPY", store, report])
        self.assertEqual(error.exception.code, "REFUSED_ADMISSION_ROUTE")
        raw = json.loads(Path(report).read_text()); raw["sourceSelection"]["kind"] = "FIRST_COMPLETE_TIMESTAMP_GROUPS"
        Path(report).write_text(json.dumps(raw))
        with self.assertRaises(ContractError) as error:
            build_registry(["--out", str(self.root / "prefix.json"), "--entry", "USDJPY", store, report])
        self.assertEqual(error.exception.code, "REFUSED_ADMISSION_REPORT")
        tampered = json.loads(self.path.read_text()); tampered["entries"][0]["record"]["months"][0]["period"] = "2024-10"
        (self.root / "private" / "bad.json").write_text(json.dumps(tampered))
        with self.assertRaises(ContractError):
            Registry(self.root / "private" / "bad.json").session_bundle("EURUSD", "2024-10")


class RouteRegistryTests(unittest.TestCase):
    def test_cross_symbol_binds_its_admitted_route(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fx = intake(root, "USDJPY", "2024-11", [("2024-11-01T05:00:00.000Z", "150.000", "150.002")])
            cross = intake(root, "EURJPY", "2024-11", [("2024-11-01T05:00:00.000Z", "160.000", "160.002"),
                                                       ("2024-11-01T05:00:10.000Z", "160.010", "160.012")])
            build_registry(["--out", str(root / "r.json"), "--entry", "EURJPY", *cross, "--entry", "USDJPY", *fx])
            registry = Registry(root / "r.json")
            try:
                rows = {r["symbol"]: r for r in registry.catalogue()}
                self.assertEqual((rows["EURJPY"]["model"], rows["USDJPY"]["model"]), ("HISTORICAL_ADMITTED_V1",) * 2)
                b = registry.session_bundle("EURJPY", "2024-11")
                self.assertEqual(b.profile.wire["conversion"]["symbol"], "USDJPY")
                join = b.join(b.profile, b.primary, start_ns=str(b.start_ns), conversion_provider=b.conversion)
                frame = join.reveal(str(b.start_ns), join.checkpoint())
                self.assertEqual(frame["pairs"][0]["conversionStatus"], "ELIGIBLE_ADMITTED")
                self.assertEqual(registry.binding(b.profile.wire).conversion, b.conversion)
            finally:
                registry.close()


@unittest.skipUnless(DSN, "Requires isolated native PostgreSQL; skip is not acceptance")
class AdmittedSessionRouteTests(RegistryFixture, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from infrastructure.database import migrate
        migrate(DSN)

    def test_session_on_an_admitted_month_trades_and_survives_a_cold_reload(self):
        from execution.research_v2 import ResearchApplicationV2
        scope = TrustedScope("admitted:" + uuid.uuid4().hex, "fixture:actor")
        app = ResearchApplicationV2(DSN, scope, self.registry)
        m = method(); app.create_method(m)
        sid = "session:admitted"
        meta = app.create_session(dict(id=sid, name="Dec", methodId=m["id"], initialBalance="10000", startPeriod="2024-12", symbol="EURUSD"))
        self.assertTrue(meta["datasetId"].startswith("admitted:histdata:EURUSD:2024-11:2024-12"))
        with self.assertRaises(ContractError):
            app.create_session(dict(id="session:bad", name="Oct", methodId=m["id"], initialBalance="10000", startPeriod="2024-10", symbol="EURUSD"))
        rev = 0
        def call(kind, payload=None):
            nonlocal rev
            result = app.apply(sid, command(sid, "command:" + str(rev), rev, kind, payload)); rev = result["state"]["revision"]
            return result
        call("ADVANCE", dict(targetNs=str(ns("2024-12-02T00:00:00Z"))))
        review = app.review(sid, dict(id="order:one", expectedRevision=rev, payload=dict(
            side="LONG", orderType="MARKET", workflow="QUICK", entry="999", quantity="1", sl=None, tp="1.107", riskPercent="1", observations=[])))
        self.assertEqual(review["command"]["payload"]["entry"], "1.10502")
        rev = app.confirm(sid, dict(reviewId=review["id"], reviewHash=content_hash(review)))["state"]["revision"]
        call("ADVANCE", dict(targetNs=str(ns("2024-12-02T00:00:15Z"))))
        state = call("ADVANCE", dict(targetNs=str(ns("2024-12-02T00:00:30Z"))))["state"]
        self.assertEqual(state["orders"]["order:one"]["status"], "CLOSED")
        reloaded = Registry(self.path); self.addCleanup(reloaded.close)
        cold = ResearchApplicationV2(DSN, scope, reloaded)
        view = cold.inspect(sid)
        self.assertEqual((view["displayStatus"], view["metadata"]["startPeriod"]), ("REVEALED_PREFIX", "2024-12"))
        self.assertIn("not broker fills", view["label"])
        self.assertEqual(view["state"]["balance"], state["balance"])
        self.assertIn("HISTORICAL", cold.catalog()["label"])
        # Withdrawing the registry keeps stored Sessions readable; only display degrades.
        bare = ResearchApplicationV2(DSN, scope, Registry())
        self.assertEqual(bare.catalog()["sessions"][0]["id"], sid)
        self.assertEqual(bare.inspect(sid)["displayStatus"], "SOURCE_DISPLAY_UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
