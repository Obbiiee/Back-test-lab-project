"""Safety refusals before any browser mutation or database startup."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import shutil
from unittest.mock import patch

ROOT = Path(__file__).parent
spec = importlib.util.spec_from_file_location('browser_gate', ROOT/'riksora_browser_gate.py')
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class BrowserGateSafetyTests(unittest.TestCase):
    def test_root_refused_before_paths_or_subprocesses(self):
        with patch.object(gate.os, 'geteuid', return_value=0), patch.object(gate.shutil, 'which') as lookup:
            with self.assertRaisesRegex(ValueError, 'ORDINARY_USER_REQUIRED'):
                gate.preflight(Path('/does-not-exist'), Path('/does-not-exist'))
            lookup.assert_not_called()

    def test_build_symlink_refused_and_target_preserved(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root/'frontend').mkdir()
            target = root/'must-remain'
            target.mkdir()
            (target/'proof').write_text('original')
            (root/'frontend/dist').symlink_to(target, target_is_directory=True)
            with patch.object(gate.os, 'geteuid', return_value=1000), patch.object(gate.shutil, 'which', return_value='/test'):
                with self.assertRaisesRegex(ValueError, 'QA_BUILD_SYMLINK_REFUSED'):
                    gate.preflight(root, root)
            self.assertEqual((target/'proof').read_text(), 'original')

    @unittest.skipUnless(shutil.which('node'), 'Node.js is installed by the browser CI job')
    def test_external_plain_http_privileged_ports_and_credentials_refused_before_dependencies(self):
        for url in ('https://riksora.com/?page=beta', 'http://127.0.0.1:5449/?page=account',
                    'https://127.0.0.1/?page=account', 'https://user:password@127.0.0.1:5449/?page=account',
                    'https://localhost:5449/?page=account', 'https://127.0.0.1:5449/?page=account#fragment'):
            with self.subTest(url=url):
                result = subprocess.run(['node', str(ROOT/'riksora-browser-journey.mjs'), '--check-config'],
                    input=json.dumps(dict(url=url, nonce='a'*64))+'\n', text=True, capture_output=True, timeout=10)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('EXCLUSIVE_QA_TARGET_REQUIRED', result.stderr)
        valid = subprocess.run(['node', str(ROOT/'riksora-browser-journey.mjs'), '--check-config'],
            input=json.dumps(dict(url='https://127.0.0.1:5449/?page=account', nonce='a'*64))+'\n',
            text=True, capture_output=True, timeout=10)
        self.assertEqual(valid.returncode, 0, valid.stderr)

    def test_no_database_or_url_override_cli(self):
        for option in ('--dsn', '--url'):
            result = subprocess.run([sys.executable, str(ROOT/'riksora_browser_gate.py'), option, 'forbidden'],
                                    capture_output=True, text=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('unrecognized arguments', result.stderr)

    def test_qa_code_tools_and_evidence_not_shipped(self):
        sys.path.insert(0, str(gate.REPOSITORY))
        from deploy.vps.package import allowed
        for path in ('frontend/tests/riksora_browser_gate.py', 'frontend/tests/riksora-browser-journey.mjs',
                     'frontend/tests/browser-tools/package.json',
                     'frontend/tests/browser-tools/package-lock.json',
                     'frontend/tests/artifacts/riksora-private-example/report.json'):
            self.assertFalse(allowed(path), path)
        self.assertTrue(allowed('deploy/vps/compose.staging.yaml'))
        self.assertTrue(allowed('deploy/vps/Caddyfile.staging'))
        self.assertTrue(allowed('deploy/vps/.env.staging.example'))

    def test_staging_overlay_isolated_and_auth_gated(self):
        root = gate.REPOSITORY/'deploy/vps'
        caddy = (root/'Caddyfile.staging').read_text()
        compose = (root/'compose.staging.yaml').read_text()
        example = (root/'.env.staging.example').read_text()
        self.assertIn('basic_auth {$BTL_STAGING_AUTH_USER} {$BTL_STAGING_AUTH_HASH}', caddy)
        self.assertIn('staging_database:/var/lib/postgresql/data', compose)
        self.assertIn('BTL_DOMAIN=staging.example.invalid', example)
        self.assertIn('BTL_DOMAIN=staging.example.invalid', example)
        self.assertNotIn('BTL_DOMAIN=riksora.com', example)


if __name__ == '__main__':
    unittest.main(verbosity=2)
