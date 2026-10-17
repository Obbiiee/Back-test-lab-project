"""Independent literal financial outcomes plus frozen completed-trade definitions."""
from copy import deepcopy
import os, unittest, uuid
from unittest.mock import patch
from contracts.primitives import ContractError
from execution.analysis_v2 import project, MAX_ANALYSIS_EVENTS
from tests.test_kernel_v2 import fixture, scene_system, opening

class AnalysisV2Tests(unittest.TestCase):
    def complete(self,case):
        h=scene_system(case["symbol"],case["primaryRows"],case["conversionRows"]);genesis=deepcopy(h.state)
        h.tick(100);h.apply("OPEN",opening(case["side"],case["quantity"]),"open");h.tick(110)
        h.apply("CLOSE",dict(orderId="open",quantity=None));h.tick(120)
        return h,genesis
    def test_all_literal_symbols_and_signed_loss_are_closed_once(self):
        for case in fixture()["scenes"]:
            with self.subTest(case=case["name"]):
                h,g=self.complete(case);before=deepcopy(h.state);r=project(h.state,iter(h.events),g)
                self.assertEqual(r["account"]["balance"],case["expected"]["balance"])
                self.assertEqual(r["metrics"]["tradeCount"],1)
                self.assertEqual(r["metrics"]["wins"],int(case["side"]=="LONG"))
                self.assertEqual(r["metrics"]["losses"],int(case["side"]=="SHORT"))
                self.assertEqual(r["metrics"]["rEligible"],0);self.assertIsNone(r["metrics"]["totalR"])
                self.assertFalse(r["markToMarketAvailable"]);self.assertEqual(h.state,before)
    def test_partial_fees_cash_and_completed_denominators(self):
        h=scene_system("EURUSD",[(100,"9","10"),(110,"9","10"),(120,"11","12"),(130,"11","12"),(140,"11","12")],fee="3.5");g=deepcopy(h.state)
        h.tick(100);h.apply("OPEN",opening(lots="1"),"open");h.tick(110)
        for index,lots in enumerate(("0.33","0.33",None)):
            h.apply("CLOSE",dict(orderId="open",quantity=lots));h.tick(120+10*index)
            r=project(h.state,iter(h.events),g)
            self.assertEqual(r["metrics"]["tradeCount"],int(index==2))
        self.assertEqual(r["metrics"]["realizedNetCompleted"],"99992.99")
        self.assertEqual(r["metrics"]["maxDrawdown"],"3.5")
        self.assertEqual(r["metrics"]["maxDrawdownRate"],dict(numerator="7",denominator="20000"))
        self.assertEqual(r["balanceCurve"][-1]["balance"],"109992.99")
        self.assertEqual(r["completed"][0]["durationNs"],"30")
    def test_empty_unresolved_and_no_retrospective_r(self):
        h=scene_system("EURUSD",[(100,"9","10"),(110,"9","10"),(110,"9","11")]);g=deepcopy(h.state)
        r=project(h.state,[],g);self.assertIsNone(r["metrics"]["winRate"]);self.assertIsNone(r["metrics"]["profitFactor"])
        h.tick(100);h.apply("OPEN",opening(),"open");h.tick(110)
        r=project(h.state,h.events,g);self.assertEqual(r["metrics"]["tradeCount"],0);self.assertEqual(r["metrics"]["unresolved"],1)
        self.assertEqual(r["account"]["netCashChange"],"0")
    def test_partial_profit_then_missing_fx_is_cash_not_completed_trade(self):
        h=scene_system("EURGBP",[(100,"9","10"),(110,"9","10"),(120,"11","12"),(130,"11","12")],[(100,"2","2"),(110,"2","2"),(120,"2","2")]);g=deepcopy(h.state)
        h.tick(100);h.apply("OPEN",opening(lots="0.02"),"open");h.tick(110)
        h.apply("CLOSE",dict(orderId="open",quantity="0.01"));h.tick(120)
        h.apply("CLOSE",dict(orderId="open",quantity=None));h.tick(130)
        r=project(h.state,h.events,g)
        self.assertEqual(r["metrics"]["tradeCount"],0);self.assertEqual(r["metrics"]["unresolved"],1)
        self.assertEqual(r["metrics"]["realizedNetCompleted"],"0")
        self.assertEqual(r["account"]["netCashChange"],"2000");self.assertEqual(r["account"]["balance"],"12000")

    def test_incomplete_corrupt_reordered_and_foreign_genesis_refuse(self):
        h,g=self.complete(fixture()["scenes"][0])
        for events in (h.events[:-1],list(reversed(h.events))):
            with self.assertRaisesRegex(ContractError,"CORRUPT_RECORD"):project(h.state,events,g)
        bad=deepcopy(h.events);bad[-1]["detail"]["cashDelta"]="1"
        with self.assertRaisesRegex(ContractError,"CORRUPT_RECORD"):project(h.state,bad,g)
        bad=deepcopy(g);bad["sessionId"]="foreign"
        with self.assertRaisesRegex(ContractError,"CORRUPT_RECORD"):project(h.state,h.events,bad)
    def test_limit_refuses_before_consuming_stream_and_curve_is_cash(self):
        h,g=self.complete(fixture()["scenes"][0]);bad=deepcopy(h.state);bad["nextEventIndex"]=MAX_ANALYSIS_EVENTS+1
        def forbidden():raise AssertionError("stream consumed");yield
        self.assertEqual(project(bad,forbidden(),g)["reason"],"REFUSED_ANALYSIS_LIMIT")
        r=project(h.state,h.events,g);self.assertEqual(r["curveBasis"],"COMMITTED_CASH_POSTINGS")
        self.assertNotIn("quote",r);self.assertNotIn("controller",r)

@unittest.skipUnless(os.getenv("BTL_TEST_DATABASE_URL"),"Requires isolated PostgreSQL; skip is not acceptance")
class AnalysisV2NativeTests(unittest.TestCase):
    def test_scoped_cold_read_only_projection_and_provider_outage(self):
        import tests.test_execution_v2_postgres as f
        from application.models import TrustedScope
        from execution.contracts import policy_from_wire
        from infrastructure.database import migrate
        migrate(f.DSN);scope=TrustedScope("statsqa:"+uuid.uuid4().hex,"fixture:actor")
        h=f.system(f.fixture()["scenes"][1]);c=f.controller(h);session="fixture:stats"
        c.create(scope,session,policy_from_wire(h.state["policy"]),start_ns="100")
        for rev,(kind,payload) in enumerate([("ADVANCE",dict(targetNs="100")),("OPEN",opening()),("ADVANCE",dict(targetNs="110")),("CLOSE",dict(orderId="stats:1",quantity=None)),("ADVANCE",dict(targetNs="120"))]):
            c.apply(scope,f.command(session,"stats:"+str(rev),rev,kind,payload))
        # More than256 events: this must reconstruct the full immutable ledger,
        # rather than treating the bounded inspection window as complete history.
        revision=5
        for index in range(127):
            oid="cancelled:"+str(index)
            c.apply(scope,f.command(session,oid,revision,"OPEN",opening()));revision+=1
            c.apply(scope,f.command(session,"cancel:"+str(index),revision,"CANCEL",dict(orderId=oid)));revision+=1
        before=c.inspect(scope,session,maximum=256)
        self.assertGreater(before["state"]["nextEventIndex"],256)
        with patch("execution.controller_v2.SourceJoinV2.resume",side_effect=AssertionError("No source read allowed")):
            r=f.controller(h).statistics(scope,session)
        self.assertEqual(r["account"]["balance"],"12000");self.assertEqual(r["metrics"]["tradeCount"],1)
        self.assertEqual(r,f.controller(h).statistics(scope,session));self.assertEqual(c.inspect(scope,session,maximum=256),before)
        with self.assertRaisesRegex(ContractError,"RESOURCE_UNAVAILABLE"):c.statistics(TrustedScope("outsider","fixture:actor"),session)
        fork=f.command("fixture:stats:child","fork",0,"FORK",dict(parentSessionId=session,parentRevision=3))
        c.apply(scope,fork)
        self.assertEqual(c.statistics(scope,"fixture:stats:child")["reason"],"UNSUPPORTED_LINEAGE")
