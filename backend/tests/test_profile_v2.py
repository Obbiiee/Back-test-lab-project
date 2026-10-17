"""Literal synthetic profile goldens with independent Node byte/hash reference."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from execution.profile_v2 import ExecutionProfileV2
from execution.contracts import profile_wire, ENGINE_VERSION
from tests.test_execution_goldens import goldens


def vectors():
    return json.loads((Path(__file__).parent / "fixtures/execution_profiles_v2.json").read_text())["vectors"]


class ProfileV2Tests(unittest.TestCase):
    def test_all_sixteen_independent_canonical_byte_hash_vectors(self):
        self.assertEqual(len(vectors()), 16)
        for case in vectors():
            with self.subTest(symbol=case["name"]):
                p = ExecutionProfileV2.from_wire(case["input"])
                self.assertEqual(p._bytes.decode(), case["canonical"])
                self.assertEqual(p.profile_hash, case["sha256"])
                self.assertEqual(p.wire, case["input"])

    def test_v1_unchanged_and_no_cross_version_acceptance(self):
        before = deepcopy(goldens()["profile"])
        self.assertEqual(profile_wire(before), before)
        self.assertEqual(ENGINE_VERSION, "BTL-TICK-EXECUTION-1")
        with self.assertRaises(ValueError): ExecutionProfileV2.from_wire(before)
        with self.assertRaises(ValueError): profile_wire(vectors()[0]["input"])

    def test_profile_owns_all_nested_bytes(self):
        raw = deepcopy(vectors()[1]["input"])
        profile = ExecutionProfileV2.from_wire(raw)
        before = profile.wire
        raw["primary"]["datasetVersion"] = "f" * 64
        raw["conversion"]["datasetVersion"] = "f" * 64
        output = profile.wire
        output["conversion"]["maxAgeNs"] = "1"
        self.assertEqual(profile.wire, before)
        with self.assertRaises(ValueError): ExecutionProfileV2(b'{}')
        with self.assertRaises(ValueError): ExecutionProfileV2((json.dumps(before) + "\n").encode())

    def test_versions_currency_costs_lots_precision_and_real_sources_refused(self):
        raw = vectors()[1]["input"]
        changes = {"schemaVersion": True, "engineVersion": "BTL-TICK-EXECUTION-1", "model": "REAL_PROVIDER",
            "symbol": "BTCUSD", "baseCurrency": "GBP", "quoteCurrency": "USD", "accountCurrency": "EUR",
            "tickSize": "0.000001", "priceScale": "3", "contractSize": "100", "lotStep": "0.03",
            "minLot": "0.001", "maxLot": "0.001", "moneyScale": True,
            "commissionModel": "UNKNOWN", "commissionPerLotSide": "-1", "commissionCurrency": "GBP",
            "slippageModel": "ASSUMED", "latencyModel": "INSTANT", "conversion": None}
        for field, value in changes.items():
            with self.subTest(field=field), self.assertRaises(ValueError):
                ExecutionProfileV2.from_wire(dict(raw, **{field: value}))
        for field in ("tickSize", "priceScale", "contractSize", "lotStep", "minLot", "maxLot", "commissionPerLotSide"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                ExecutionProfileV2.from_wire(dict(raw, **{field: "1.00"}))
        for field, value in (("evidenceClass", "PROVIDER_OBSERVATION"), ("providerId", "dukascopy"), ("datasetId", "local:csv")):
            bad = deepcopy(raw); bad["primary"][field] = value
            with self.assertRaises(ValueError): ExecutionProfileV2.from_wire(bad)

    def test_conversion_identity_age_and_unknown_fields_refused(self):
        raw = vectors()[1]["input"]
        for field, value in (("currency", "JPY"), ("symbol", "EURGBP"), ("maxAgeNs", "0"),
                             ("maxAgeNs", "60000000001"), ("datasetVersion", "bad"), ("providerId", "dukascopy")):
            bad = deepcopy(raw); bad["conversion"][field] = value
            with self.assertRaises(ValueError): ExecutionProfileV2.from_wire(bad)
        bad = deepcopy(raw);bad["conversion"]["futureTicks"] = []
        with self.assertRaises(ValueError): ExecutionProfileV2.from_wire(bad)
        with self.assertRaises(ValueError): ExecutionProfileV2.from_wire(dict(raw, futureTicks=[]))
        bad = deepcopy(vectors()[0]["input"]);bad["conversion"] = raw["conversion"]
        with self.assertRaises(ValueError): ExecutionProfileV2.from_wire(bad)

    def test_explicit_usd_fixed_commission_and_precision_limits(self):
        raw = deepcopy(vectors()[0]["input"])
        raw.update(commissionModel="FIXED_PER_LOT_SIDE", commissionPerLotSide="3.5")
        self.assertEqual(ExecutionProfileV2.from_wire(raw).wire["commissionPerLotSide"], "3.5")
        raw["commissionPerLotSide"] = "1e37"
        with self.assertRaises(ValueError): ExecutionProfileV2.from_wire(raw)


if __name__ == "__main__": unittest.main()
