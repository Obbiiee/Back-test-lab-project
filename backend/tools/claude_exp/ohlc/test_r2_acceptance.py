"""r2_acceptance logic against an in-memory S3 fake (NOT a real bucket): proves the script's checks, prefixing, cleanup and secret handling."""
import io
import json
import os
import stat
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.claude_exp.ohlc import r2_acceptance as acc            # noqa: E402
from tools.claude_exp.ohlc.test_service import build_world        # noqa: E402


class Err(Exception):
    def __init__(self, code):
        self.response = {"Error": {"Code": code}}


class FakeS3:
    def __init__(self):
        self.o = {}

    def head_object(self, Bucket, Key):
        if Key not in self.o:
            raise Err("404")
        d, m = self.o[Key]
        return {"ContentLength": len(d), "Metadata": m}

    def put_object(self, Bucket, Key, Body, IfNoneMatch=None, Metadata=None):
        assert IfNoneMatch == "*" and Key not in self.o
        self.o[Key] = (Body, Metadata)

    def get_object(self, Bucket, Key, Range=None):
        return {"Body": io.BytesIO(self.o[Key][0])}

    def list_objects_v2(self, Bucket, Prefix, ContinuationToken=None):
        return {"Contents": [{"Key": k} for k in sorted(self.o) if k.startswith(Prefix)]}

    def delete_objects(self, Bucket, Delete):
        for x in Delete["Objects"]:
            self.o.pop(x["Key"])


class T(unittest.TestCase):
    def test_pass_prefix_and_cleanup(self):
        _, _, reader, _, _ = build_world()
        fake = FakeS3()
        fake.o["other/keep.txt"] = (b"x", {})
        boto3 = types.SimpleNamespace(client=lambda *a, **k: fake)
        botocore = types.ModuleType("botocore"); cfg = types.ModuleType("botocore.config"); cfg.Config = lambda **k: None
        env = dict(BTL_R2_ENDPOINT="https://e", BTL_R2_BUCKET="b", BTL_R2_ACCESS_KEY_ID="AKIA-SECRET-ID", BTL_R2_SECRET_ACCESS_KEY="SECRET-VALUE-XYZ")
        out = io.StringIO()
        src = reader.root if hasattr(reader, "root") else None
        with mock.patch.dict(sys.modules, {"boto3": boto3, "botocore": botocore, "botocore.config": cfg}), \
                mock.patch.dict(os.environ, env), mock.patch.object(acc, "CompactTickReader", lambda s: reader), \
                mock.patch.object(sys, "argv", ["x", "--src", "-", "--month", "2026-05", "--cleanup"]), mock.patch("sys.stdout", out):
            with self.assertRaises(SystemExit) as ex:
                acc.main()
        self.assertEqual(ex.exception.code, 0, out.getvalue())
        res = json.loads(out.getvalue())
        self.assertEqual(res["status"], "PASS")
        self.assertEqual((res["firstPublish"]["put"], res["cleanedObjects"]), (10, 10 + 0))
        self.assertEqual(list(fake.o), ["other/keep.txt"])                       # cleanup touched only its own prefix
        self.assertNotIn("SECRET-VALUE-XYZ", out.getvalue())
        self.assertNotIn("AKIA-SECRET-ID", out.getvalue())

    def test_env_file_permissions_enforced(self):
        d = tempfile.mkdtemp(); p = Path(d) / "r2.env"; p.write_text("BTL_R2_BUCKET=b\n"); p.chmod(0o644)
        with mock.patch.dict(os.environ, {"BTL_R2_ENV_FILE": str(p)}):
            with self.assertRaises(SystemExit):
                acc.load_env()
        p.chmod(0o600)
        with mock.patch.dict(os.environ, {"BTL_R2_ENV_FILE": str(p)}):
            self.assertEqual(acc.load_env()["BTL_R2_BUCKET"], "b")


if __name__ == "__main__":
    unittest.main()
