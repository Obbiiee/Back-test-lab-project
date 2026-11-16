"""Pure transition harness only; native durable tests are separate acceptance."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from contracts.models import MethodPolicy
from execution.kernel_v2 import seed_state, submit, advance, validate_state, validate_snapshot, command_wire
from execution.profile_v2 import ExecutionProfileV2
from execution.sources_v2 import SourceJoinV2
from tests.test_profile_v2 import vectors
from tests.test_sources_v2 import provider


def fixture():
    return json.loads((Path(__file__).parent/"fixtures/execution_v2.json").read_text())


def scene_system(symbol,primary_rows,fx_rows=None,fee="0",policy=None):
    primary=provider(primary_rows,"v2-primary:"+symbol)
    raw=deepcopy(next(v["input"] for v in vectors() if v["name"]==symbol))
    raw["primary"].update(datasetId=primary.dataset_id,datasetVersion=primary.dataset_version)
    fx=None
    if raw["conversion"] is not None:
        fx=provider(fx_rows,"v2-fx:"+symbol)
        raw["conversion"].update(datasetId=fx.dataset_id,datasetVersion=fx.dataset_version)
    if fee!="0":raw.update(commissionModel="FIXED_PER_LOT_SIDE",commissionPerLotSide=fee)
    profile=ExecutionProfileV2.from_wire(raw)
    return Harness(profile,primary,fx,policy)


class Harness:
    def __init__(self,profile,primary,fx=None,policy=None):
        self.profile,self.primary,self.fx=profile,primary,fx
        source=SourceJoinV2(profile,primary,start_ns="100",conversion_provider=fx)
        self.checkpoint=source.checkpoint()
        self.state=seed_state("fixture:session-v2",profile,policy or MethodPolicy("fixture:free-v2","0"*64,"FREE_STYLE",False,()),self.checkpoint)
        self.events=[]

    def apply(self,kind,payload=None,cid=None):
        cmd=dict(schemaVersion=1,artifact="BTL-TICK-EXECUTION-COMMAND-2",sessionId=self.state["sessionId"],
                 commandId=cid or "cmd:"+str(self.state["revision"]),expectedRevision=self.state["revision"],kind=kind,payload=payload or {})
        source=None;basis=None
        if kind in ("OPEN","ADVANCE"):
            source=SourceJoinV2.resume(self.profile,self.primary,self.checkpoint,conversion_provider=self.fx)
            if kind=="OPEN":basis=source.risk_basis(source.checkpoint())
        proposed,events=submit(self.state,cmd,basis)
        cp=self.checkpoint
        if kind=="ADVANCE":
            frame=source.reveal(payload["targetNs"],source.checkpoint())
            proposed,more=advance(proposed,frame,payload["targetNs"]);events+=more;cp=source.checkpoint()
        elif kind=="OPEN":cp=basis["checkpoint"]
        proposed["revision"]+=1;validate_snapshot(proposed,cp)
        self.state,self.checkpoint=proposed,cp;self.events+=events
        return deepcopy(proposed)

    def tick(self,t):return self.apply("ADVANCE",dict(targetNs=str(t)))


def opening(side="LONG",lots="0.01",entry="10",sl=None,tp=None,kind="MARKET",workflow="QUICK",observations=None):
    return dict(side=side,orderType=kind,workflow=workflow,entry=entry,quantity=lots,sl=sl,tp=tp,riskPercent="1",observations=observations or [])


class KernelV2Tests(unittest.TestCase):
    def test_seventeen_literal_financial_scenes_all_sixteen_symbols(self):
        for case in fixture()["scenes"]:
            with self.subTest(name=case["name"]):
                h=scene_system(case["symbol"],case["primaryRows"],case["conversionRows"])
                h.tick(100);h.apply("OPEN",opening(case["side"],case["quantity"]),"open")
                h.tick(110);h.apply("CLOSE",dict(orderId="open",quantity=None));h.tick(120)
                for key in ("balance","realizedGross","commission"):self.assertEqual(h.state[key],case["expected"][key])
                self.assertEqual(h.state["orders"]["open"]["status"],case["expected"]["status"])
                self.assertEqual(sum(e["classification"]=="SIMULATED_FILL" for e in h.events),case["expected"]["simulatedFills"])

    def test_literal_partial_closes_reconcile_posted_cash_and_exact_entry_allocation(self):
        case=fixture()["additional"]["partialFees"]
        h=scene_system("EURUSD",[(100,"9","10"),(110,"9","10"),(120,"11","12"),(130,"11","12"),(140,"11","12")],fee=case["feePerLotSide"])
        h.tick(100);h.apply("OPEN",opening(lots="1"),"open");h.tick(110)
        self.assertEqual(h.state["balance"],"9996.5")
        for i,lots in enumerate(case["closingLots"]):
            h.apply("CLOSE",dict(orderId="open",quantity=lots if i<2 else None));h.tick(120+i*10)
            self.assertEqual(h.state["balance"],case["balances"][i])
        for key in ("balance","realizedGross","commission"):self.assertEqual(h.state[key],case["expected"][key])
        allocations=[e["detail"]["entryCostAllocationExact"] for e in h.events if e["kind"]=="EXIT_FILL"]
        self.assertEqual([[a["numerator"],a["denominator"]] for a in allocations],case["entryCostAllocationRatios"])

    def test_protocol_literal_risk_rr_checklist_and_manual_action_refusal(self):
        case=fixture()["additional"]["protocol"]
        policy=MethodPolicy("fixture:protocol-v2","0"*64,"PROTOCOL",True,("trend","zone"),"1","2")
        h=scene_system(case["symbol"],case["primaryRows"],case["conversionRows"],policy=policy)
        h.tick(100)
        payload=opening(lots=case["quantity"],entry=case["entry"],sl=case["sl"],tp=case["tp"],kind="LIMIT",workflow="PLANNED",
                        observations=[dict(conditionId=c,outcome="PASS") for c in ("trend","zone")])
        bad=deepcopy(payload);bad["observations"][0]["outcome"]="FAIL"
        before=deepcopy(h.state)
        with self.assertRaisesRegex(ValueError,"PROTOCOL"):h.apply("OPEN",bad,"bad")
        self.assertEqual(h.state,before)
        h.apply("OPEN",payload,"open");h.tick(110)
        with self.assertRaisesRegex(ValueError,"PROTOCOL"):h.apply("CLOSE",dict(orderId="open",quantity=None))
        h.tick(120)
        self.assertEqual(h.state["orders"]["open"]["risk"]["recommendedQuantity"],"0.8")
        for key in ("balance","realizedGross","commission"):self.assertEqual(h.state[key],case["expected"][key])

    def test_current_fx_coverage_failure_never_posts_partial_foreign_close(self):
        h=scene_system("EURGBP",[(100,"9","10"),(110,"9","10"),(120,"11","12")],[(100,"2","2"),(110,"2","2")])
        h.tick(100);h.apply("OPEN",opening(),"open");h.tick(110)
        h.apply("CLOSE",dict(orderId="open",quantity=None));h.tick(120)
        expected=fixture()["additional"]["unavailableFx"]["expected"]
        for key in ("balance","realizedGross","commission"):self.assertEqual(h.state[key],expected[key])
        self.assertEqual(h.state["orders"]["open"]["status"],"UNRESOLVED")
        self.assertEqual(h.events[-1]["detail"]["reason"],expected["reason"])
        self.assertEqual(sum(e["kind"]=="EXIT_FILL" for e in h.events),0)

    def test_ambiguous_primary_group_and_session_end_never_invent_exits(self):
        h=scene_system("EURUSD",[(100,"9","10"),(110,"9","10"),(110,"9","11"),(120,"11","12")])
        h.tick(100);h.apply("OPEN",opening(),"open");h.tick(110)
        self.assertEqual(h.state["balance"],"10000");self.assertTrue(h.state["unresolved"])
        self.assertEqual(h.state["orders"]["open"]["entryPrice"],None)
        h.apply("END");self.assertTrue(h.state["ended"])
        h=scene_system("EURUSD",[(100,"9","10"),(110,"9","10"),(120,"11","12")])
        h.tick(100);h.apply("OPEN",opening(),"open");h.tick(110);h.apply("END")
        self.assertTrue(h.state["unresolved"]);self.assertEqual(h.state["balance"],"10000")
        self.assertEqual(sum(e["kind"]=="EXIT_FILL" for e in h.events),0)

    def test_root_currency_cash_and_source_mutation_future_frames_refused(self):
        h=scene_system("EURUSD",[(100,"9","10"),(110,"9","10"),(120,"11","12")]);h.tick(100)
        for mutate in (lambda s:s.update(balance="9999"),lambda s:s.update(engineVersion="BTL-TICK-EXECUTION-1"),
                       lambda s:s["profile"].update(accountCurrency="EUR")):
            bad=deepcopy(h.state);mutate(bad)
            with self.assertRaises(ValueError):validate_state(bad)
        source=SourceJoinV2.resume(h.profile,h.primary,h.checkpoint)
        frame=source.reveal("110",source.checkpoint());bad=deepcopy(frame);bad["pairs"][0]["primaryGroup"]["timeNs"]="120"
        before=deepcopy(h.state)
        with self.assertRaises(ValueError):advance(h.state,bad,"110")
        self.assertEqual(h.state,before)
        bad=deepcopy(frame);bad["conversionGroups"]["f"*64]={}
        with self.assertRaises(ValueError):advance(h.state,bad,"110")
        cmd=dict(schemaVersion=1,artifact="BTL-TICK-EXECUTION-COMMAND-1",sessionId=h.state["sessionId"],commandId="x",expectedRevision=0,kind="END",payload={})
        with self.assertRaises(ValueError):command_wire(cmd)

    def test_free_style_actual_quantity_risk_does_not_force_protocol_sizing(self):
        h=scene_system("EURUSD",[(100,"1.1","1.1002"),(110,"1.1","1.1002"),(120,"1.101","1.1012")])
        h.tick(100);h.apply("OPEN",opening(lots="2",entry="1.1002",sl="1.0992"),"open")
        risk=h.state["orders"]["open"]["risk"]
        self.assertIsNone(risk["recommendedQuantity"])
        self.assertTrue(risk["exceedsBudget"])
        self.assertEqual(risk["plannedRequestedLossUsdExact"],dict(numerator="200",denominator="1"))


    def test_limit_stop_gaps_short_targets_and_cancel_are_quote_based(self):
        # Literal independent prices/outcomes; a crossed threshold fills the quote,
        # not the requested threshold or a candle-derived intrabar path.
        scenes=[
            ("LONG","LIMIT","10","8","12",[(100,"10","11"),(110,"9","10"),(120,"8","9")],"SL","8000"),
            ("LONG","STOP","11","9","12",[(100,"9","10"),(110,"11","12")],"SL","10000"),
            ("SHORT","STOP","9","11","7",[(100,"10","11"),(110,"8","9"),(120,"6","7")],"TP","11000"),
            ("SHORT","LIMIT","11","13","9",[(100,"9","10"),(110,"11","12"),(120,"8","9")],"TP","12000"),
        ]
        for side,kind,entry,sl,tp,rows,reason,balance in scenes:
            if side=="LONG" and kind=="STOP":
                # Entry12 then a real gap to bid8: loss4000, not the SL9.
                rows=rows+[(120,"8","9")];balance="6000"
            with self.subTest(side=side,kind=kind):
                h=scene_system("EURUSD",rows);h.tick(100)
                h.apply("OPEN",opening(side=side,lots="0.01",entry=entry,sl=sl,tp=tp,kind=kind,workflow="PLANNED"),"open")
                h.tick(110);h.tick(120)
                self.assertEqual(h.state["balance"],balance)
                self.assertEqual(h.events[-1]["detail"]["reason"],reason)
                self.assertEqual(h.state["orders"]["open"]["status"],"CLOSED")
        h=scene_system("EURUSD",[(100,"9","10"),(110,"9","10")]);h.tick(100)
        h.apply("OPEN",opening(),"open");h.apply("CANCEL",dict(orderId="open"));h.tick(110)
        self.assertEqual(h.state["balance"],"10000")
        self.assertFalse(any(e["classification"]=="SIMULATED_FILL" for e in h.events))


if __name__ == "__main__":unittest.main()
