"""Authored synthetic financial vectors, no financial commits/provider claims."""
from copy import deepcopy
from fractions import Fraction
import unittest

from execution.finance_v2 import entry_proposal, exit_proposal, planned_risk, allocate_entry_cost
from execution.profile_v2 import ExecutionProfileV2
from ticks.contracts import event_id
from ticks.timeline import make_group
from tests.test_profile_v2 import vectors


def profile(symbol, fee="0"):
    raw = deepcopy(next(v["input"] for v in vectors() if v["name"] == symbol))
    if fee != "0": raw.update(commissionModel="FIXED_PER_LOT_SIDE", commissionPerLotSide=fee)
    return ExecutionProfileV2.from_wire(raw)


def group(p, bid, ask, *, conversion=False, time="100", count=1):
    source = p.wire["conversion" if conversion else "primary"]
    rows = []
    for i in range(count):
        rows.append(dict(schemaVersion=1, artifact="BTL-CANONICAL-TICK-1", datasetId=source["datasetId"],
            datasetVersion=source["datasetVersion"], providerId=source["providerId"], feedId=source["feedId"],
            instrumentId=source["feedInstrumentId"], eventId=event_id(source["providerId"],source["feedId"],"c"*64,str(i)),
            timeNs=time, resolutionNs="1", bid=bid, ask=ask, rawOrdinal=str(i), trustedSequence=None,
            provenance=dict(sourceId="synthetic:authored", memberHash="c"*64, originalTimestamp="AUTHORED_NS:"+time),
            quality=dict(evidenceHash="d"*64, quote="VALID", freshness="CONFIRMED", gapBefore="NONE", duplicateOf=None)))
    return make_group(rows, source["datasetVersion"])


class FinanceV2Tests(unittest.TestCase):
    def test_all_sixteen_profile_quote_routes_execute_only_authored_proposals(self):
        for vector in vectors():
            p=profile(vector["name"])
            quote=p.wire["quoteCurrency"]
            fx=None if quote=="USD" else group(p,"2","2",conversion=True)
            proposal=exit_proposal(p,"LONG","10","0.01","100",group(p,"11","12"),conversion_group=fx)
            base=1 if vector["name"]=="XAUUSD" else 1000
            expected=base if quote=="USD" else base*2 if quote in ("GBP","NZD") else base//2
            self.assertEqual(proposal["cashDelta"],str(expected),vector["name"])
            self.assertEqual(proposal["model"],"AUTHORED_SYNTHETIC_ONLY")

    def test_entry_long_ask_short_bid_and_usd_commission_once(self):
        p = profile("EURUSD", "3.5");g = group(p,"1.1","1.1002")
        for side, expected in (("LONG","1.1002"),("SHORT","1.1")):
            result = entry_proposal(p,side,"0.5","100",g)
            self.assertEqual(result["price"], expected)
            self.assertEqual(result["cashDelta"], "-1.75")
            self.assertEqual(result["commissionExact"], dict(numerator="7",denominator="4"))

    def test_direct_gbp_gain_bid_loss_ask_and_no_double_entry_fee(self):
        p=profile("EURGBP","3.5");fx=group(p,"1.25","1.251",conversion=True)
        gain=exit_proposal(p,"LONG","0.85","1","100",group(p,"0.851","0.8512"),conversion_group=fx)
        self.assertEqual((gain["grossPosted"],gain["commissionPosted"],gain["cashDelta"]),("125","3.5","121.5"))
        loss=exit_proposal(p,"LONG","0.85","1","100",group(p,"0.849","0.8492"),conversion_group=fx)
        self.assertEqual((loss["grossPosted"],loss["cashDelta"]),("-125.1","-128.6"))
        self.assertEqual(loss["conversion"]["evidence"]["side"],"ask")

    def test_inverse_jpy_signed_and_short_exit_ask(self):
        p=profile("EURJPY");fx=group(p,"150","151",conversion=True)
        gain=exit_proposal(p,"LONG","160","0.1","100",group(p,"160.1","160.101"),conversion_group=fx)
        self.assertEqual(gain["grossQuoteExact"],dict(numerator="1000",denominator="1"))
        self.assertEqual(gain["grossUsdExact"],dict(numerator="1000",denominator="151"))
        self.assertEqual(gain["cashDelta"],"6.62")
        loss=exit_proposal(p,"SHORT","160","0.1","100",group(p,"160.099","160.1"),conversion_group=fx)
        self.assertEqual(loss["cashDelta"],"-6.67")
        self.assertEqual(loss["conversion"]["evidence"]["side"],"bid")

    def test_usd_exit_half_even_preserves_exact_before_post(self):
        p=profile("EURUSD");g=group(p,"1.10001","1.10002")
        result=exit_proposal(p,"LONG","1.1","0.01","100",g)
        self.assertEqual(result["grossUsdExact"],dict(numerator="1",denominator="100"))
        self.assertEqual(result["cashDelta"],"0.01")
        with self.assertRaises(ValueError):exit_proposal(p,"LONG","1.1","0.01","100",g,conversion_group={})
        foreign=profile("EURGBP");fx=group(foreign,"0.5","0.5",conversion=True)
        for lots,expected in (("0.01","0"),("0.03","0.02"),("0.05","0.02"),("0.07","0.04")):
            rounded=exit_proposal(foreign,"LONG","0.85",lots,"100",group(foreign,"0.85001","0.85002"),conversion_group=fx)
            self.assertEqual(rounded["grossPosted"],expected)


    def test_exact_partial_cost_allocations_and_final_remainder(self):
        first=allocate_entry_cost("3.5","1","0","0.33",dict(numerator="0",denominator="1"))
        self.assertEqual(first,dict(numerator="231",denominator="200"))
        second=allocate_entry_cost("3.5","1","0.33","0.33",first)
        last=allocate_entry_cost("3.5","1","0.66","0.34",dict(numerator="231",denominator="100"))
        values=[Fraction(int(v["numerator"]),int(v["denominator"])) for v in (first,second,last)]
        self.assertEqual(values,[Fraction(231,200),Fraction(231,200),Fraction(119,100)])
        self.assertEqual(sum(values),Fraction(7,2))
        for prior in (dict(numerator="1",denominator="1"),dict(numerator="00",denominator="1"),dict(numerator="0",denominator="0"),dict(numerator="2",denominator="2")):
            with self.assertRaises(ValueError):allocate_entry_cost("3.5","1","0","0.33",prior)
        with self.assertRaises(ValueError):allocate_entry_cost("3.5","1","0.9","0.2",dict(numerator="63",denominator="20"))

    def test_risk_uses_adverse_signed_conversion_and_lot_floor(self):
        p=profile("EURGBP");fx=group(p,"1.2","1.25",conversion=True)
        result=planned_risk(p,"LONG","0.85","0.8499","100","100",conversion_group=fx)
        self.assertEqual(result["quantity"],"8")
        self.assertEqual(result["hypotheticalPostedRiskUsd"],"100")
        self.assertEqual(result["lossPerLotUsdExact"],dict(numerator="25",denominator="2"))
        self.assertEqual(result["conversion"]["evidence"]["side"],"ask")
        rounded_profile=profile("EURGBP","0.006")
        rounded=planned_risk(rounded_profile,"LONG","0.85","0.84999","1.017","100",
                             conversion_group=group(rounded_profile,"1.004","1.005",conversion=True))
        self.assertEqual(rounded["quantity"],"0.98")
        self.assertEqual(rounded["hypotheticalPostedRiskUsd"],"1")
        tiny=profile("EURGBP","0.6")
        with self.assertRaises(ValueError):
            planned_risk(tiny,"LONG","0.85","0.84999","0.01206","100",
                         conversion_group=group(tiny,"0.005","0.006",conversion=True))
        p=profile("EURJPY");fx=group(p,"150","151",conversion=True)
        result=planned_risk(p,"SHORT","160","160.1","100","100",conversion_group=fx)
        self.assertEqual(result["quantity"],"1.5")
        self.assertEqual(result["conversion"]["evidence"]["side"],"bid")

    def test_primary_and_conversion_uncertainty_future_and_bounds_refuse(self):
        p=profile("EURGBP");g=group(p,"0.851","0.8512");fx=group(p,"1.25","1.251",conversion=True)
        for field,value in (("freshness","UNKNOWN"),("gapBefore","UNKNOWN_SILENCE")):
            bad=deepcopy(g);bad["events"][0]["quality"][field]=value
            with self.assertRaises(ValueError):exit_proposal(p,"LONG","0.85","1","100",bad,conversion_group=fx)
        for time in ("99","101"):
            with self.assertRaises(ValueError):exit_proposal(p,"LONG","0.85","1","100",group(p,"0.851","0.8512",time=time),conversion_group=fx)
        with self.assertRaises(ValueError):exit_proposal(p,"LONG","0.85","1","100",g)
        with self.assertRaises(ValueError):exit_proposal(p,"LONG","0.85","1","100",g,conversion_group=group(p,"1.25","1.251",conversion=True,time="101"))
        for qty in ("0","0.001","101"):
            with self.assertRaises(ValueError):entry_proposal(p,"LONG",qty,"100",g)
        with self.assertRaises(ValueError):entry_proposal(p,"LONG","1","100",group(p,"0.851001","0.851201"))
        with self.assertRaises(ValueError):entry_proposal(p,"LONG","1","100",group(p,"0.851001","0.8512"))

    def test_ambiguous_primary_ties_rejected_and_equivalent_refs_retained(self):
        p=profile("EURUSD");g=group(p,"1.1","1.1002",count=2)
        before=deepcopy(g)
        result=entry_proposal(p,"LONG","1","100",g)
        self.assertEqual(len(result["evidence"]["eventIds"]),2)
        self.assertEqual(g,before)
        g["events"][1]["ask"]="1.1003";g=make_group(g["events"],p.wire["primary"]["datasetVersion"])
        with self.assertRaisesRegex(ValueError,"AMBIGUOUS"):entry_proposal(p,"LONG","1","100",g)

    def test_risk_invalid_geometry_minimum_costs_and_input_ownership(self):
        p=profile("EURUSD","3.5")
        result=planned_risk(p,"LONG","1.1","1.099","100","100")
        self.assertEqual(result["quantity"],"0.93")
        self.assertEqual(result["hypotheticalPostedRiskUsd"],"99.52")
        for side,stop,budget in (("LONG","1.101","100"),("SHORT","1.099","100"),("LONG","1.1","100"),("LONG","1.099","0.01")):
            with self.assertRaises(ValueError):planned_risk(p,side,"1.1",stop,budget,"100")
        with self.assertRaises(ValueError):entry_proposal(p.wire,"LONG","1","100",group(p,"1.1","1.1002"))


if __name__ == "__main__":unittest.main()
