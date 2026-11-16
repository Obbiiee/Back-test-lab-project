"""Offline diagnostics tests; no root, provider, service or database mutation."""
from contextlib import redirect_stdout
from hashlib import sha256
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from types import SimpleNamespace
import json
import unittest
from deploy.vps.audit_native import secret_metadata, backup_summary, audit


class NativeAuditTests(unittest.TestCase):
    def test_private_file_metadata_and_symlink_refusal(self):
        with TemporaryDirectory() as t:
            p=Path(t)/'runtime.json';p.write_text('fixture-secret-not-real');p.chmod(0o600)
            result=secret_metadata(p)
            self.assertTrue(result['regular']);self.assertFalse(result['world_access'])
            link=Path(t)/'link';link.symlink_to(p)
            self.assertFalse(secret_metadata(link)['regular'])
            self.assertNotIn('fixture-secret-not-real',json.dumps(result))

    def test_backup_verified_without_restoring_or_disclosing_bytes(self):
        with TemporaryDirectory() as t:
            p=Path(t)/'sample.dump';raw=b'authored-backup-not-market-data';p.write_bytes(raw);p.chmod(0o600)
            p.with_suffix('.sha256').write_text(sha256(raw).hexdigest())
            with patch('deploy.vps.audit_native.subprocess.run',return_value=SimpleNamespace(returncode=0)) as run:
                result=backup_summary(t)
                self.assertTrue(result['latest_hash_matches']);self.assertTrue(result['latest_catalog_readable'])
                self.assertFalse(result['restore_drill_performed'])
                self.assertEqual(run.call_args.args[0][1],'--list')
                self.assertNotIn(raw.decode(),json.dumps(result))
                p.write_bytes(b'changed')
                self.assertFalse(backup_summary(t)['latest_hash_matches'])

    def test_runtime_error_never_emits_secret_or_traceback(self):
        out=StringIO()
        with patch('deploy.vps.audit_native.Path.read_text',side_effect=ValueError('fixture-secret-not-real')),redirect_stdout(out):
            result=audit()
        self.assertEqual(result['database_check_error_type'],'ValueError')
        self.assertNotIn('fixture-secret-not-real',json.dumps(result)+out.getvalue())

if __name__=='__main__':unittest.main()
