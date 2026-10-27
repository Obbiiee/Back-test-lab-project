"""Literal observed-family proofs and refusal; no source/fill/durability claims."""
from copy import deepcopy
from dataclasses import FrozenInstanceError
from pathlib import Path
import json
import unittest

from execution.observed_profile import ObservedExecutionProfile
from execution.observed_finance import exit_amount, risk_size
from execution.profile_v2 import ExecutionProfileV2

VECTORS=json.loads((Path(__file__).parent/'fixtures/observed_profile_vectors.json').read_text())


class ObservedFinanceTests(unittest.TestCase):
    def profile(self):return ObservedExecutionProfile.from_wire(VECTORS['profiles'][0]['profile'])

    def test_literal_profile_bytes_hash_and_old_family_refusal(self):
        for v in VECTORS['profiles']:
            p=ObservedExecutionProfile.from_wire(v['profile'])
            self.assertEqual(p._bytes,v['canonical'].encode())
            self.assertEqual(p.profile_hash,v['sha256'])
            with self.assertRaises(ValueError):ExecutionProfileV2.from_wire(v['profile'])

    def test_fixed_assumptions_unknown_keys_types_and_synthetic_identity_refused(self):
        original=VECTORS['profiles'][0]['profile']
        for field,value in [('moneyScale',True),('schemaVersion',True),('tickSize','0.01'),('maxObservedSilenceNs','61000000000'),('commissionPerLotSide','1'),('maxLot','100.0'),('conversion',{}),('extra',None)]:
            with self.subTest(field=field),self.assertRaises(ValueError):
                ObservedExecutionProfile.from_wire(dict(original,**{field:value}))
        for field,value in [('providerSymbol','XAUUSDm'),('providerId','SYNTHETIC'),('datasetId','synthetic:fake'),('evidenceClass','SYNTHETIC_CONTRACT_ONLY'),('datasetVersion','ABC')]:
            v=deepcopy(original);v['primary'][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):ObservedExecutionProfile.from_wire(v)

    def test_canonical_bytes_immutability_and_copy_isolation(self):
        p=self.profile();raw=p.wire;raw['primary']['providerId']='changed';self.assertEqual(p.profile_hash,VECTORS['profiles'][0]['sha256'])
        with self.assertRaises(FrozenInstanceError):p._bytes=b'{}'
        with self.assertRaises(ValueError):ObservedExecutionProfile(json.dumps(p.wire,indent=2).encode())
        with self.assertRaises(ValueError):ObservedExecutionProfile(p._bytes[:-1]+b',"moneyScale":2}')
        with self.assertRaises(ValueError):ObservedExecutionProfile(b' '*16385)

    def test_seven_independent_literal_pnl_and_half_even_cases(self):
        for v in VECTORS['arithmetic']:
            with self.subTest(v=v):
                out=exit_amount(self.profile(),side=v['side'],entry_price=v['entry'],exit_price=v['exit'],lots=v['quantity'])
                self.assertEqual((out['grossExact'],out['grossPosted']),(v['expectedGross'],v['expectedPosted']))
                self.assertEqual(out['commissionPosted'],'0');self.assertFalse(out['committed'])
                self.assertEqual(out['model'],'CONDITIONAL_OBSERVED_TICK_SIMULATION')

    def test_literal_risk_budget_floor_and_exact_usage(self):
        v=VECTORS['risk'];out=risk_size(self.profile(),balance=v['balance'],risk_percent=v['riskPercent'],entry_price=v['entry'],stop_price=v['stop'])
        self.assertEqual((out['quantity'],out['riskUsedExact'],out['riskBudgetExact'],out['unusedRiskExact']),('0.08','98.76','100','1.24'))
        self.assertFalse(out['committed']);self.assertEqual(out['costBudgetPerLotExact'],'0')

    def test_off_grid_float_invalid_size_distance_and_risk_refuse(self):
        p=self.profile()
        for args in [dict(side='LONG',entry_price='2300.0001',exit_price='2301',lots='0.01'),dict(side='LONG',entry_price=2300.0,exit_price='2301',lots='0.01'),dict(side='LONG',entry_price='2300',exit_price='2301',lots='0.015'),dict(side='LONG',entry_price='2300',exit_price='2301',lots='101')]:
            with self.subTest(args=args),self.assertRaises(ValueError):exit_amount(p,**args)
        for balance,percent,stop in [('10000','1','2300'),('10000','101','2299'),('0.01','1','2200'),('100000000','100','2299')]:
            with self.subTest(balance=balance,percent=percent,stop=stop),self.assertRaises(ValueError):
                risk_size(p,balance=balance,risk_percent=percent,entry_price='2300',stop_price=stop)
