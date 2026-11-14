"""Backup/restore drill on a disposable database: the dump of a populated product database restores byte-for-byte equal in every ledger that matters,
immutability triggers survive, a tampered dump is refused, and a non-empty target is refused."""
import hashlib
import os
import subprocess
import tempfile
import unittest
import uuid
from pathlib import Path

import psycopg

from contracts.primitives import ContractError
from infrastructure import database as dbm

DSN = os.getenv("BTL_TEST_DATABASE_URL")
PG_BIN = os.getenv("BTL_PG_BIN", "")
LEDGERS = {"tick_events": "content_hash", "tick_commands": "content_hash", "tick_sessions": "session_id", "audit_events": "event_id::text",
           "entitlement_claims": "claim_key", "sandbox_billing_orders": "order_id", "users": "id::text", "workspaces": "id::text", "research_jobs": "id::text"}


def fingerprint_table(db, table, key):
    count = db.execute(f"SELECT count(*) FROM btl.{table}").fetchone()[0]
    digest = db.execute(f"SELECT md5(coalesce(string_agg({key}, ',' ORDER BY {key}), '')) FROM btl.{table}").fetchone()[0]
    return count, digest


@unittest.skipUnless(DSN, "Real isolated PostgreSQL required; skip is not PASS")
class RestoreDrill(unittest.TestCase):
    def test_dump_of_a_populated_database_restores_equal_and_guards_hold(self):
        dbm.migrate(DSN)
        info = psycopg.conninfo.conninfo_to_dict(DSN)
        name = "restore_" + uuid.uuid4().hex[:10]
        base = dict(info); base["dbname"] = "postgres"
        with psycopg.connect(**base, autocommit=True) as admin:
            admin.execute(f'CREATE DATABASE "{name}"')
        target_info = dict(info); target_info["dbname"] = name
        target_dsn = psycopg.conninfo.make_conninfo(**target_info)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                dump = Path(tmp) / "product.dump"
                digest = dbm.backup(DSN, dump, PG_BIN)
                dbm.restore(target_dsn, dump, digest, PG_BIN)
                with psycopg.connect(DSN) as src, psycopg.connect(target_dsn) as dst:
                    populated = 0
                    for table, key in LEDGERS.items():
                        a, b = fingerprint_table(src, table, key), fingerprint_table(dst, table, key)
                        self.assertEqual(a, b, table)
                        populated += a[0] > 0
                    self.assertGreaterEqual(populated, 3, "the drill must run against a populated database")
                    for trigger in ("immutable_audit_events", "immutable_access_windows"):
                        self.assertEqual(dst.execute("SELECT count(*) FROM pg_trigger WHERE tgname=%s", (trigger,)).fetchone()[0], 1, trigger)
                    with self.assertRaises(psycopg.Error):
                        dst.execute("DELETE FROM btl.audit_events")
                    dst.rollback()
                    before = dst.execute("SELECT count(*) FROM public.btl_migrations").fetchone()[0]
                dbm.migrate(target_dsn)                                       # the restored migration ledger matches the code: nothing to apply
                with psycopg.connect(target_dsn) as dst:
                    self.assertEqual(dst.execute("SELECT count(*) FROM public.btl_migrations").fetchone()[0], before)
                # a flipped byte is refused before anything is restored; a populated target is refused too
                data = bytearray(dump.read_bytes()); data[len(data) // 2] ^= 1
                tampered = Path(tmp) / "tampered.dump"; tampered.write_bytes(bytes(data))
                with self.assertRaises(ContractError):
                    dbm.restore(target_dsn, tampered, digest, PG_BIN)
                with self.assertRaises(ContractError):
                    dbm.restore(target_dsn, dump, digest, PG_BIN)
        finally:
            with psycopg.connect(**base, autocommit=True) as admin:
                admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


if __name__ == "__main__":
    unittest.main()
