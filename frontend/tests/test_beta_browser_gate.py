"""Safety refusals before any browser mutation or database startup."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).parent
spec = importlib.util.spec_from_file_location('browser_gate', ROOT/'beta_browser_gate.py')
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

    def test_external_plain_http_privileged_ports_and_credentials_refused_before_dependencies(self):
        for url in ('https://riksora.com/?page=beta', 'http://127.0.0.1:5449/?page=beta',
                    'https://127.0.0.1/?page=beta', 'https://user:password@127.0.0.1:5449/?page=beta',
                    'https://localhost:5449/?page=beta', 'https://127.0.0.1:5449/?page=beta#fragment'):
            with self.subTest(url=url):
                result = subprocess.run(['node', str(ROOT/'beta-browser-gate.mjs'), '--check-config'],
                    input=json.dumps(dict(url=url, nonce='a'*64))+'\n', text=True, capture_output=True, timeout=10)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('EXCLUSIVE_QA_TARGET_REQUIRED', result.stderr)
        valid = subprocess.run(['node', str(ROOT/'beta-browser-gate.mjs'), '--check-config'],
            input=json.dumps(dict(url='https://127.0.0.1:5449/?page=beta', nonce='a'*64))+'\n',
            text=True, capture_output=True, timeout=10)
        self.assertEqual(valid.returncode, 0, valid.stderr)

    def test_no_database_or_url_override_cli(self):
        for option in ('--dsn', '--url'):
            result = subprocess.run([sys.executable, str(ROOT/'beta_browser_gate.py'), option, 'forbidden'],
                                    capture_output=True, text=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('unrecognized arguments', result.stderr)

    def test_qa_code_tools_and_evidence_not_shipped(self):
        sys.path.insert(0, str(gate.REPOSITORY))
        from deploy.vps.package import allowed
        for path in ('frontend/tests/beta_browser_gate.py', 'frontend/tests/beta-browser-gate.mjs',
                     'frontend/tests/browser-tools/package.json',
                     'frontend/tests/browser-tools/package-lock.json',
                     'frontend/tests/artifacts/beta-browser-example/report.json'):
            self.assertFalse(allowed(path), path)


if __name__ == '__main__':
    unittest.main(verbosity=2)
