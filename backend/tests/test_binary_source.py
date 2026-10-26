"""Authored scalar/metadata/projection compatibility and actual disk acceptance."""
from copy import deepcopy
import json
from pathlib import Path
import struct
import tempfile
import unittest

from contracts.canonical import canonical_bytes
from contracts.primitives import ContractError
from ticks.contracts import (BINARY64_POLICY, BINARY64_TIME, binary64_price_text,
                            utc_ms_projection, validate_source_policy, validate_source_projection)
from ticks.provider import SyntheticTickProvider
from ticks.storage_v2 import DatasetBuilder, DiskTickProvider, validate_sources
from ticks.contracts_v2 import ZERO_VERSION


class BinarySourceTests(unittest.TestCase):
    def test_materialized_independent_vectors(self):
        vectors=json.loads((Path(__file__).parent/'fixtures/binary_source_vectors.json').read_text())
        for v in vectors['prices']:
            scalar=struct.unpack('>d',bytes.fromhex(v['bits']))[0]
            self.assertEqual(binary64_price_text(scalar),v['text'])
            self.assertEqual(struct.pack('>d',float(v['text'])).hex(),v['bits'])
        for v in vectors['timestamps']:
            self.assertEqual(utc_ms_projection(int(v['ms'])),(v['ns'],v['iso']))
        with self.assertRaises(ContractError):canonical_bytes(dict(schemaVersion=1,value=0.1))

    def test_refuses_ambiguous_invalid_scalars_and_timestamp_types(self):
        for value in (None,True,1,'1',0.0,-0.0,-1.0,float('nan'),float('inf'),float('-inf')):
            with self.subTest(value=value),self.assertRaises(ContractError):binary64_price_text(value)
        for value in (True,0.0,'0',-1,253402300800000):
            with self.subTest(value=value),self.assertRaises(ContractError):utc_ms_projection(value)

    def fixture(self):
        p=SyntheticTickProvider([dict(ordinal='0',timeNs='1000000',bid='0.1',ask='1.01',sequence=None)])
        m=p.describe(p.dataset_id,p.dataset_version)
        meta={k:m[k] for k in ('datasetId','providerId','feedId','instrumentId','providerSymbol','evidenceClass','adapterVersion','validatorVersion','ordering')}
        meta['evidenceClass']='PROVIDER_OBSERVATION'
        sources=deepcopy(m['sources'])
        sources[0].update(originalScalePolicy=BINARY64_POLICY,timestampConvention=BINARY64_TIME,resolutionNs='1000000')
        row=p.read_page(p.dataset_id,p.dataset_version,None,1)['events'][0]
        row.update(datasetVersion=ZERO_VERSION,resolutionNs='1000000')
        row['provenance']['originalTimestamp']='1970-01-01T00:00:00.001Z'
        return meta,sources,row

    def test_source_policy_is_explicit_and_raw_text_unchanged(self):
        meta,sources,_=self.fixture();s=sources[0]
        validate_source_policy(s,'PROVIDER_OBSERVATION')
        for changed,kind in ((dict(s,originalScalePolicy='FLOAT64'),'PROVIDER_OBSERVATION'),
                             (dict(s,resolutionNs='1'),'PROVIDER_OBSERVATION'),
                             (dict(s,timestampConvention='UTC guessed'),'PROVIDER_OBSERVATION'),
                             (s,'SYNTHETIC_CONTRACT_ONLY')):
            with self.assertRaises(ContractError):validate_source_policy(changed,kind)
        validate_source_policy(dict(s,originalScalePolicy='PRESERVE_RAW_TEXT',resolutionNs='1',timestampConvention='old raw description'),'SYNTHETIC_CONTRACT_ONLY')

    def test_projection_refuses_nonroundtrip_text_and_timestamp_mutation(self):
        _,sources,row=self.fixture();s=sources[0]
        validate_source_projection(s,row)
        for wrong in (dict(row,bid='0.10000000000000001'),dict(row,bid=None),dict(row,timeNs='2000000'),dict(row,resolutionNs='1')):
            with self.assertRaises(ContractError):validate_source_projection(s,wrong)
        # Raw-text source still preserves a longer exact decimal lexeme.
        validate_source_projection(dict(s,originalScalePolicy='PRESERVE_RAW_TEXT'),dict(row,bid='0.10000000000000001'))

    def test_actual_v2_publication_pages_and_unknown_evidence(self):
        meta,sources,row=self.fixture()
        with tempfile.TemporaryDirectory() as folder:
            b=DatasetBuilder(folder,meta,sources,{'authored':True})
            try:
                b.append(row);v=b.finish()
            finally:b.store.close()
            p=DiskTickProvider(folder,v)
            try:
                d=p.describe_v2(p.dataset_id,v)
                self.assertEqual(d['root']['evidenceClass'],'PROVIDER_OBSERVATION')
                page=p.read_page_v2(p.dataset_id,v,p.locate_v2(p.dataset_id,v,'0')['position'])
                self.assertEqual(page['events'][0],dict(row,datasetVersion=v))
                self.assertEqual(page['events'][0]['quality']['freshness'],'UNKNOWN')
                self.assertIsNone(page['events'][0]['trustedSequence'])
            finally:p.close()

    def test_invalid_projection_never_enters_identity_table(self):
        meta,sources,row=self.fixture()
        with tempfile.TemporaryDirectory() as folder:
            b=DatasetBuilder(folder,meta,sources,{'authored':True})
            try:
                with self.assertRaises(ContractError):b.append(dict(row,bid='0.10000000000000001'))
                self.assertEqual(b.store.db.execute('SELECT count(*) FROM identities').fetchone()[0],0)
                self.assertEqual(b.store.db.execute('SELECT count(*) FROM publications').fetchone()[0],0)
            finally:b.store.close()
