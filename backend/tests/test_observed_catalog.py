"""Operator catalog pinning and public projection; does not open market sources."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from execution.observed_catalog import ObservedCatalog
from execution.observed_profile import ObservedExecutionProfile
from contracts.canonical import canonical_bytes
from tests.test_observed_kernel import BASE


class ObservedCatalogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        profile = dict(BASE)
        profile['primary'] = dict(datasetId='exness:xauusd:2025-01', datasetVersion='a'*64,
            providerId='EXNESS', feedId='EXNESS:XAUUSD', feedInstrumentId='EXNESS:XAUUSD',
            providerSymbol='XAUUSD', evidenceClass='PROVIDER_OBSERVATION')
        self.profile = ObservedExecutionProfile.from_wire(profile)
        self.record = dict(key='source:2025-01', period='2025-01', label='Exness XAUUSD · 2025-01',
            profile=self.profile.wire, folder=str(self.root/'private-source'),
            receiptPath=str(self.root/'private-proof.json'), receiptSha256='b'*64,
            logRoot=str(self.root/'private-logs'))
        raw = canonical_bytes(dict(schemaVersion=1, artifact='BTL-OBSERVED-OPERATOR-CATALOG-1', sources=[self.record]))
        self.path = self.root/'catalog.json'; self.path.write_bytes(raw); self.path.chmod(0o400)
        self.sha = hashlib.sha256(raw).hexdigest()

    def tearDown(self):
        self.path.chmod(0o600); self.tmp.cleanup()

    def test_public_projection_is_source_key_only_and_period_pinned(self):
        catalog = ObservedCatalog(self.path, self.sha)
        public = catalog.public()
        self.assertEqual([(item['key'], item['period']) for item in public], [('source:2025-01', '2025-01')])
        encoded = json.dumps(public)
        for private in ('private-source', 'private-proof.json', 'private-logs', self.record['receiptSha256']):
            self.assertNotIn(private, encoded)
        self.assertEqual(catalog.selection('source:2025-01', '2025-01').profile_hash, self.profile.profile_hash)
        with self.assertRaisesRegex(ValueError, 'OBSERVED_PERIOD_UNAVAILABLE'):
            catalog.selection('source:2025-01', '2025-02')
        with self.assertRaisesRegex(ValueError, 'OBSERVED_PERIOD_UNAVAILABLE'):
            catalog.selection('unknown:source', '2025-01')

    def test_changed_pin_or_unsafe_mode_is_refused_before_source_resolution(self):
        with self.assertRaisesRegex(ValueError, 'SOURCE_PIN_CHANGED'):
            ObservedCatalog(self.path, 'c'*64)
        self.path.chmod(0o600)
        with self.assertRaisesRegex(ValueError, 'REFUSED_OPERATOR_CATALOG'):
            ObservedCatalog(self.path, self.sha)


if __name__ == '__main__':
    unittest.main()
