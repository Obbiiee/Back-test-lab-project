"""Operator catalog pinning and public projection; does not open market sources."""
import hashlib
import json
import os
import stat
import sys
from types import ModuleType, SimpleNamespace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from execution import observed_catalog
from execution.observed_catalog import ObservedCatalog
from execution.observed_profile import ObservedExecutionProfile
from contracts.canonical import canonical_bytes

BASE=json.loads((Path(__file__).parent/'fixtures/observed_profile_vectors.json').read_text())['profiles'][0]['profile']


class ObservedCatalogTests(unittest.TestCase):
    def setUp(self):
        platform_os=SimpleNamespace(**os.__dict__,O_NOFOLLOW=getattr(os,'O_NOFOLLOW',0),
                                    O_NONBLOCK=getattr(os,'O_NONBLOCK',0))
        if os.name=='nt':
            native_fstat=os.fstat
            def windows_fstat(fd):
                native=native_fstat(fd)
                mode=0o600 if stat.S_IMODE(native.st_mode)&stat.S_IWRITE else 0o400
                return SimpleNamespace(st_mode=stat.S_IFREG|mode,st_size=native.st_size)
            platform_os.fstat=windows_fstat
        self.os_patch=patch.object(observed_catalog,'os',platform_os)
        self.os_patch.start()
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

    def pin_catalog(self, value):
        self.path.chmod(0o600)
        raw=canonical_bytes(value)
        self.path.write_bytes(raw)
        self.path.chmod(0o400)
        self.sha=hashlib.sha256(raw).hexdigest()

    def tearDown(self):
        self.path.chmod(0o600); self.tmp.cleanup()
        self.os_patch.stop()

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

    def test_shared_source_v2_is_explicitly_pinned_and_operator_only(self):
        self.pin_catalog(dict(schemaVersion=1,artifact='BTL-OBSERVED-OPERATOR-CATALOG-1',
                              timelineStorageMode='shared-source-v2',sources=[self.record]))
        catalog=ObservedCatalog(self.path,self.sha)
        admitted=type('Admitted',(),{'assert_current':lambda _self:None})()
        factory=Mock(return_value=admitted)
        module=ModuleType('execution.observed_admission');module.AdmittedObservedSource=factory
        with patch.dict(sys.modules,{'execution.observed_admission':module}):
            self.assertIs(catalog.resolve(self.profile.profile_hash),admitted)
        self.assertEqual(factory.call_args.kwargs['timeline_storage_mode'],'shared-source-v2')
        self.assertTrue(factory.call_args.kwargs['allow_product_shared_source_v2'])
        self.assertNotIn('timelineStorageMode',json.dumps(catalog.public()))

    def test_unknown_operator_timeline_mode_fails_closed(self):
        self.pin_catalog(dict(schemaVersion=1,artifact='BTL-OBSERVED-OPERATOR-CATALOG-1',
                              timelineStorageMode='shared-source-v1',sources=[self.record]))
        with self.assertRaisesRegex(ValueError, 'REFUSED_OPERATOR_CATALOG'):
            ObservedCatalog(self.path,self.sha)


if __name__ == '__main__':
    unittest.main()
