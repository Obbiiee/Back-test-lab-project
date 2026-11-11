"""Safety refusals before any browser mutation or database startup."""
import importlib.util
import hashlib
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
    def test_api_telemetry_frame_is_accepted_and_strips_untrusted_fields(self):
        event = {'apiEvent': {'method': 'GET', 'path': '/api/v1/auth/providers',
            'status': 200, 'code': None, 'durationMs': 12.5,
            'email': 'private@example.com', 'responseBody': {'token': 'secret'}}}
        self.assertEqual(gate.sanitize_api_event(event), {
            'method': 'GET', 'path': '/api/v1/auth/providers', 'status': 200,
            'code': None, 'jumpStatus': None, 'durationMs': 12.5})
        self.assertIsNone(gate.sanitize_api_event({'apiEvent': {
            'method': 'GET', 'path': '/api/v1/auth/login?email=private@example.com',
            'status': 200, 'durationMs': 1}}))

    def test_demo_tick_fixture_has_pinned_synthetic_identity_and_hash(self):
        sys.path.insert(0, str(gate.REPOSITORY/'backend'))
        from contracts.canonical import canonical_bytes
        from execution.research_fixture import research_provider

        source = research_provider()
        self.assertEqual(source.dataset_id, 'synthetic:local-alpha-v1')
        self.assertEqual(source.dataset_version,
                         'e39482a3a1325ecf8aaee8c787f9cf4e996c30be068616bfecd8f6e15bfabc32')
        digest = hashlib.sha256()
        count = 0
        token = None
        while True:
            page = source.read_page(source.dataset_id, source.dataset_version, token, 64)
            for event in page['events']:
                digest.update(canonical_bytes(event))
                digest.update(b'\n')
                count += 1
            if page['endOfDataset']:
                break
            token = page['nextToken']
        self.assertEqual(count, 2048)
        self.assertEqual(digest.hexdigest(),
                         '5d2eefc52ceb9b613be7de7a11749dd479be267927268035fe991282699e1fad')

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
        self.assertNotIn('BTL_DOMAIN=riksora.com', example)

    def test_browser_uses_complete_staging_runtime_grants(self):
        operator = (gate.REPOSITORY/'deploy/vps/ops.py').read_text()
        self.assertIn('grant_execution_runtime', operator)
        self.assertIn('migrate_and_grant(dsn)', (ROOT/'riksora_browser_gate.py').read_text())


if __name__ == '__main__':
    unittest.main(verbosity=2)
