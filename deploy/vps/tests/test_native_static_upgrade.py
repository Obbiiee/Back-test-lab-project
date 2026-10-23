import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from deploy.vps.native_static_upgrade import digest, validate, prepare, switch, verify_switch


class StaticUpgradeTests(unittest.TestCase):
    def archive(self, files):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as z:
            for name, raw in files.items():
                z.writestr(name, raw)
            z.writestr('manifest.json', json.dumps({'sourceCommit': 'a'*40,
                'mode': 'STAGING_UI_NOT_VISUAL_ACCEPTANCE',
                'files': {name: digest(raw) for name, raw in files.items()}}))
        return stream.getvalue()

    def test_strict_manifest_path_and_hash(self):
        files = {'login/index.html': b'<html>login</html>', 'assets/ui.js': b'ui'}
        raw = self.archive(files)
        self.assertEqual(validate(raw, digest(raw), 'a'*40), files)
        for invalid in [dict(files, **{'../bad': b'x'}), dict(files, **{'assets/no.html': b'x'})]:
            bad = self.archive(invalid)
            with self.assertRaises(ValueError): validate(bad, digest(bad), 'a'*40)
        with self.assertRaises(ValueError): validate(raw, '0'*64, 'a'*40)
        with self.assertRaises(ValueError): validate(raw, digest(raw), 'b'*40)

    def test_prepare_preserves_landing_and_atomic_rollback(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp); old = base/'old'; old.mkdir(); (old/'index.html').write_bytes(b'landing')
            (old/'assets').mkdir(); (old/'assets/old.js').write_bytes(b'keep')
            new = base/'new'; link = base/'current'; link.symlink_to(old)
            prepare(old, new, {'login/index.html': b'<html>new</html>', 'assets/ui.js': b'ui'})
            self.assertEqual((new/'index.html').read_bytes(), b'landing')
            self.assertEqual((new/'assets/old.js').read_bytes(), b'keep')
            self.assertEqual(new.stat().st_mode & 0o777, 0o755)
            switch(link, new, old); self.assertEqual(link.resolve(), new)
            with self.assertRaises(ValueError): switch(link, old, old)
            switch(link, old, new); self.assertEqual(link.resolve(), old)

    def test_public_failure_restores_pointer(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp); old = base/'old'; new = base/'new'
            old.mkdir(); new.mkdir(); link = base/'current'; link.symlink_to(old)
            with self.assertRaises(ValueError):
                verify_switch(link, new, old, b'expected', lambda: b'wrong')
            self.assertEqual(link.resolve(), old)
            verify_switch(link, new, old, b'expected', lambda: b'expected')
            self.assertEqual(link.resolve(), new)

    def test_collision_and_symlink_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp); old = base/'old'; old.mkdir(); (old/'index.html').write_bytes(b'landing')
            (old/'assets').mkdir(); (old/'assets/ui.js').write_bytes(b'old')
            with self.assertRaises(ValueError): prepare(old, base/'new', {'assets/ui.js': b'changed'})
            self.assertFalse((base/'new').exists())
            (old/'link').symlink_to(base)
            with self.assertRaises(ValueError): prepare(old, base/'new', {})


if __name__ == '__main__': unittest.main()
