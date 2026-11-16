"""Real accepted synthetic timelines, no caller-supplied quote authentication."""
from copy import deepcopy
import json
import unittest

from contracts.primitives import ContractError
from execution.finance_v2 import exit_proposal
from execution.profile_v2 import ExecutionProfileV2
from execution.sources_v2 import SourceJoinV2
from ticks.provider import SyntheticTickProvider, Cancellation
from tests.test_profile_v2 import vectors


def provider(rows, name, *, quality=True):
    return SyntheticTickProvider([dict(ordinal=str(i),timeNs=str(t),bid=b,ask=a,sequence=None)
                                  for i,(t,b,a) in enumerate(rows)],dataset_id="synthetic:"+name,
                                 chunk_size=1,execution_fixture=quality)


def setup(symbol="EURGBP", primary_rows=None, fx_rows=None, *, quality=True, age="60000000000"):
    primary=provider(primary_rows or [(100,"0.851","0.8512"),(110,"0.852","0.8522")],"primary")
    raw=deepcopy(next(v["input"] for v in vectors() if v["name"]==symbol))
    raw["primary"].update(datasetId=primary.dataset_id,datasetVersion=primary.dataset_version)
    fx=None
    if raw["conversion"] is not None:
        fx=provider(fx_rows or [(50,"1.25","1.251"),(105,"1.3","1.301"),(200,"999","1000")],"fx",quality=quality)
        raw["conversion"].update(datasetId=fx.dataset_id,datasetVersion=fx.dataset_version,maxAgeNs=age)
    return ExecutionProfileV2.from_wire(raw),primary,fx


class SourcesV2Tests(unittest.TestCase):
    def test_latest_complete_groups_are_causal_and_financial_proposals_use_them(self):
        p,primary,fx=setup();join=SourceJoinV2(p,primary,start_ns="100",conversion_provider=fx)
        result=join.reveal("110",join.checkpoint())
        times=[];cash=[]
        for pair in result["pairs"]:
            self.assertEqual(pair["conversionStatus"],"ELIGIBLE_SYNTHETIC")
            conv=result["conversionGroups"][pair["conversionGroupId"]]
            times.append(conv["timeNs"])
            q=exit_proposal(p,"LONG","0.85","1",pair["primaryGroup"]["timeNs"],pair["primaryGroup"],conversion_group=conv)
            cash.append(q["cashDelta"])
        self.assertEqual(times,["50","105"])
        self.assertEqual(cash,["125","260"])
        self.assertEqual(result["throughNs"],"110")
        serialized=json.dumps(result)
        self.assertNotIn('"999"',serialized)
        self.assertNotIn('"1000"',serialized)
        self.assertNotIn('"endOfDataset"',serialized)
        self.assertNotIn('"coverageCatalog"',serialized)
        for name in ("consumer","provider","manifest","sidecar","storage","eof"):
            self.assertFalse(hasattr(join,name))

    def test_cold_resume_exact_and_no_mutable_output_alias(self):
        p,primary,fx=setup();join=SourceJoinV2(p,primary,start_ns="100",conversion_provider=fx)
        first=join.reveal("100",join.checkpoint());checkpoint=join.checkpoint()
        cold=SourceJoinV2.resume(p,primary,checkpoint,conversion_provider=fx)
        live=join.reveal("110",checkpoint)
        self.assertEqual(cold.reveal("110",cold.checkpoint()),live)
        first["checkpoint"]["primary"]["advanceTargets"].append("999")
        first["pairs"][0]["primaryGroup"]["events"][0]["bid"]="999"
        self.assertEqual(join.checkpoint(),live["checkpoint"])

    def test_more_than_one_page_and_atomic_ties_never_choose_last_raw_row(self):
        rows=[(i,"1.25","1.251") for i in range(1,131)]+[(200,"9","10")]
        p,primary,fx=setup(primary_rows=[(130,"0.851","0.8512")],fx_rows=rows)
        join=SourceJoinV2(p,primary,start_ns="130",conversion_provider=fx)
        result=join.reveal("130",join.checkpoint())
        self.assertEqual(result["pairs"][0]["conversionStatus"],"ELIGIBLE_SYNTHETIC")
        self.assertEqual(len(result["checkpoint"]["conversion"]["advanceTargets"]),3)
        p,primary,fx=setup(fx_rows=[(50,"1.2","1.3"),(50,"1.25","1.3"),(200,"9","10")])
        join=SourceJoinV2(p,primary,start_ns="100",conversion_provider=fx)
        result=join.reveal("100",join.checkpoint())
        pair=result["pairs"][0]
        self.assertEqual(pair["conversionStatus"],"UNRESOLVED_FX_AMBIGUOUS")
        conv=result["conversionGroups"][pair["conversionGroupId"]]
        self.assertEqual(len(conv["events"]),2)
        self.assertEqual(conv["order"],"UNTRUSTED")

    def test_missing_stale_unknown_and_source_end_do_not_fall_back(self):
        cases=[(dict(fx_rows=[(200,"1.2","1.3")]),"UNRESOLVED_FX_MISSING"),
               (dict(age="10"),"UNRESOLVED_FX_MISSING"),
               (dict(quality=False),"UNRESOLVED_FX_QUALITY"),
               (dict(fx_rows=[(50,"1.2","1.3")]),"UNRESOLVED_FX_COVERAGE")]
        for args,expected in cases:
            with self.subTest(expected=expected):
                p,primary,fx=setup(**args);join=SourceJoinV2(p,primary,start_ns="100",conversion_provider=fx)
                result=join.reveal("100",join.checkpoint())
                self.assertEqual(result["pairs"][0]["conversionStatus"],expected)
                self.assertEqual(result["throughNs"],"100")

    def test_previous_eligible_group_becomes_stale_without_using_future_tick(self):
        p,primary,fx=setup(primary_rows=[(100,"0.851","0.8512"),(105,"0.851","0.8512"),(120,"0.851","0.8512")],
                           fx_rows=[(95,"1.25","1.251"),(200,"9","10")],age="10")
        join=SourceJoinV2(p,primary,start_ns="100",conversion_provider=fx)
        result=join.reveal("120",join.checkpoint())
        self.assertEqual([r["conversionStatus"] for r in result["pairs"]],
                         ["ELIGIBLE_SYNTHETIC","ELIGIBLE_SYNTHETIC","UNRESOLVED_FX_STALE"])
        self.assertEqual({g["timeNs"] for g in result["conversionGroups"].values()},{"95"})

    def test_usd_identity_does_not_open_or_require_conversion_source(self):
        p,primary,_=setup("EURUSD",primary_rows=[(100,"1.1","1.1002")])
        join=SourceJoinV2(p,primary,start_ns="100")
        result=join.reveal("100",join.checkpoint())
        self.assertEqual(result["pairs"][0]["conversionStatus"],"IDENTITY")
        self.assertEqual(result["conversionGroups"],{})
        self.assertIsNone(result["checkpoint"]["conversion"])
        with self.assertRaises(ValueError):SourceJoinV2(p,primary,start_ns="100",conversion_provider=primary)

    def test_cancellation_stale_checkpoint_and_budget_roll_back_both_timelines(self):
        p,primary,fx=setup();join=SourceJoinV2(p,primary,start_ns="100",conversion_provider=fx)
        before=join.checkpoint()
        with self.assertRaisesRegex(ValueError,"CANCELLED"):
            join.reveal("110",before,cancellation=Cancellation(True))
        self.assertEqual(join.checkpoint(),before)
        class DuringFx(Cancellation):
            def check(self):
                if join.checkpoint()["primary"]!=before["primary"]:
                    raise ContractError("CANCELLED","authored")
        with self.assertRaisesRegex(ValueError,"CANCELLED"):join.reveal("110",before,cancellation=DuringFx())
        self.assertEqual(join.checkpoint(),before)
        from unittest.mock import patch
        with patch("execution.sources_v2.MAX_SOURCE_STEPS",1):
            p,primary,fx=setup(primary_rows=[(130,"0.851","0.8512")],fx_rows=[(i,"1.2","1.3") for i in range(1,131)]+[(200,"1.2","1.3")])
            limited=SourceJoinV2(p,primary,start_ns="130",conversion_provider=fx);old=limited.checkpoint()
            with self.assertRaises(ValueError):limited.reveal("130",old)
            self.assertEqual(limited.checkpoint(),old)
        result=join.reveal("100",before)
        with self.assertRaisesRegex(ValueError,"STALE"):join.reveal("110",before)
        self.assertEqual(join.checkpoint(),result["checkpoint"])

    def test_future_source_mutation_changes_pins_but_not_revealed_prices(self):
        outputs=[]
        for future in ("9","999"):
            p,primary,fx=setup(fx_rows=[(50,"1.25","1.251"),(200,future,future)])
            join=SourceJoinV2(p,primary,start_ns="100",conversion_provider=fx)
            result=join.reveal("100",join.checkpoint())
            pair=result["pairs"][0];conv=result["conversionGroups"][pair["conversionGroupId"]]
            proposal=exit_proposal(p,"LONG","0.85","1","100",pair["primaryGroup"],conversion_group=conv)
            outputs.append((proposal["cashDelta"],[(r["bid"],r["ask"]) for r in conv["events"]]))
        self.assertEqual(outputs[0],outputs[1])

    def test_failed_restore_disables_controller_instead_of_claiming_clean_checkpoint(self):
        p,primary,fx=setup();join=SourceJoinV2(p,primary,start_ns="100",conversion_provider=fx)
        before=join.checkpoint()
        from unittest.mock import patch
        with patch.object(fx,"read_page",side_effect=ContractError("AUTHORED_SOURCE_FAILURE","provider")):
            with self.assertRaisesRegex(ValueError,"RECOVERY_FAILED"):join.reveal("110",before)
        with self.assertRaisesRegex(ValueError,"RECOVERY_FAILED"):join.checkpoint()
        cold=SourceJoinV2.resume(p,primary,before,conversion_provider=fx)
        self.assertEqual(cold.reveal("100",cold.checkpoint())["throughNs"],"100")

    def test_profile_dataset_and_cold_checkpoint_substitutions_refuse(self):
        p,primary,fx=setup();join=SourceJoinV2(p,primary,start_ns="100",conversion_provider=fx)
        result=join.reveal("100",join.checkpoint());checkpoint=result["checkpoint"]
        for mutate in (lambda c:c.update(profileHash="f"*64),
                       lambda c:c["conversion"]["cursor"].update(sessionStartNs="1"),
                       lambda c:c["conversion"]["cursor"].update(throughNs="200"),
                       lambda c:c["primary"]["cursor"].update(datasetVersion="f"*64)):
            bad=deepcopy(checkpoint);mutate(bad)
            with self.assertRaises(ValueError):SourceJoinV2.resume(p,primary,bad,conversion_provider=fx)
        foreign=provider([(100,"8","9")],"foreign")
        with self.assertRaises(ValueError):SourceJoinV2(p,foreign,start_ns="100",conversion_provider=fx)
        with self.assertRaises(ValueError):SourceJoinV2(p,primary,start_ns="99",conversion_provider=fx)
        with self.assertRaises(ValueError):SourceJoinV2(p,primary,start_ns="100")


    def test_risk_basis_uses_acknowledged_clock_and_cold_source_only(self):
        p,primary,fx=setup()
        join=SourceJoinV2(p,primary,start_ns="100",conversion_provider=fx)
        join.reveal("106",join.checkpoint())
        basis=join.risk_basis(join.checkpoint())
        self.assertEqual(basis["timeNs"],"106")
        self.assertEqual(basis["conversionGroup"]["timeNs"],"105")
        self.assertNotIn('"999"',json.dumps(basis))
        cold=SourceJoinV2.resume(p,primary,basis["checkpoint"],conversion_provider=fx)
        self.assertEqual(cold.risk_basis(cold.checkpoint()),basis)
        bad=deepcopy(basis["checkpoint"]);bad["profileHash"]="0"*64
        before=cold.checkpoint()
        with self.assertRaisesRegex(ContractError,"STALE_CHECKPOINT"):cold.risk_basis(bad)
        self.assertEqual(cold.checkpoint(),before)


if __name__ == "__main__":unittest.main()
