"""Encrypted off-box backup, end to end on a disposable key and database: ciphertext only leaves, upload failure leaves no marker, restore from the ciphertext is equal."""
import hashlib
import os
import shutil
import subprocess
import tempfile
import unittest
import uuid
from pathlib import Path

import psycopg

from infrastructure import database as dbm
from tools import ops_backup

DSN = os.getenv("BTL_TEST_DATABASE_URL")
PG_BIN = os.getenv("BTL_PG_BIN", "")


@unittest.skipUnless(DSN and shutil.which("gpg"), "Real isolated PostgreSQL and gpg required; skip is not PASS")
class EncryptedBackup(unittest.TestCase):
    def test_round_trip_and_failure_semantics(self):
        dbm.migrate(DSN)
        with tempfile.TemporaryDirectory() as tmp:
            home, remote = Path(tmp) / "gnupg", Path(tmp) / "remote"
            home.mkdir(mode=0o700); remote.mkdir()
            env = {**os.environ, "GNUPGHOME": str(home)}
            subprocess.run(["gpg", "--batch", "--passphrase", "", "--quick-generate-key", "backup-test@example.invalid", "default", "default", "1d"], check=True, capture_output=True, env=env, timeout=120)
            marker = Path(tmp) / "marker"
            good = {**env, "BTL_DATABASE_URL": DSN, "BTL_BACKUP_RECIPIENT": "backup-test@example.invalid", "BTL_BACKUP_UPLOAD_CMD": f"cp {{file}} {remote}/",
                    "BTL_BACKUP_MARKER": str(marker), "BTL_BACKUP_WORKDIR": tmp, "BTL_PG_BIN": PG_BIN}
            os.environ["GNUPGHOME"] = str(home)
            try:
                bad = dict(good, BTL_BACKUP_UPLOAD_CMD="false {file}")
                with self.assertRaises(subprocess.CalledProcessError):
                    ops_backup.run_backup(bad)
                self.assertFalse(marker.exists(), "a failed upload must not refresh the backup marker")
                result = ops_backup.run_backup(good)
                self.assertTrue(marker.exists())
                files = sorted(p.name for p in remote.iterdir())
                self.assertEqual(files, [result["file"], result["file"] + ".sha256"])
                self.assertFalse(list(Path(tmp).glob("btl-backup-*")), "no temporary plaintext is left behind")
                cipher = (remote / result["file"]).read_bytes()
                self.assertEqual(hashlib.sha256(cipher).hexdigest(), result["sha256"])
                self.assertNotIn(b"PGDMP", cipher[:64], "the remote copy is ciphertext")
                # off-box restore: decrypt with the private key, check the plaintext hash, restore into an empty database, compare
                plain = Path(tmp) / "plain.dump"
                subprocess.run(["gpg", "--batch", "--yes", "--output", str(plain), "--decrypt", str(remote / result["file"])], check=True, capture_output=True, env=env, timeout=300)
                self.assertTrue(plain.read_bytes().startswith(b"PGDMP"))
                info = psycopg.conninfo.conninfo_to_dict(DSN)
                name = "btlrestore_" + uuid.uuid4().hex[:10]
                admin = dict(info, dbname="postgres")
                with psycopg.connect(**admin, autocommit=True) as a:
                    a.execute(f'CREATE DATABASE "{name}"')
                try:
                    target = psycopg.conninfo.make_conninfo(**dict(info, dbname=name))
                    dbm.restore(target, plain, dbm.fingerprint(plain.read_bytes()) if hasattr(dbm, "fingerprint") else result["plaintextDumpHash"], PG_BIN)
                    with psycopg.connect(DSN) as s, psycopg.connect(target) as d:
                        for table in ("users", "workspaces", "tick_events", "audit_events"):
                            self.assertEqual(s.execute(f"SELECT count(*) FROM btl.{table}").fetchone(), d.execute(f"SELECT count(*) FROM btl.{table}").fetchone(), table)
                finally:
                    with psycopg.connect(**admin, autocommit=True) as a:
                        a.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
            finally:
                os.environ.pop("GNUPGHOME", None)


if __name__ == "__main__":
    unittest.main()
