"""Real PostgreSQL gates. Set BTL_TEST_DATABASE_URL to an isolated QA DB."""
import os
import shutil
import tempfile
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import psycopg
from psycopg import sql

from application.models import TrustedScope
from application.service import IntakeApplication
from contracts.models import Passport, LineageEntry, ReviewedRequest
from contracts.primitives import ContractError
from infrastructure.codec import pack, unpack, fingerprint
from infrastructure.database import migrate, connect, backup, restore, grant_runtime, MIGRATIONS
from infrastructure.postgres import PostgresWorkflow, ProvenanceStore
from tests.application_fakes import sample, FixedClock, FixedIds, H, NOW
from tests.test_application import assertions

DSN = os.getenv("BTL_TEST_DATABASE_URL")


class CodecTests(unittest.TestCase):
    def test_context_roundtrip_and_corruption(self):
        for kind, on in (("FREE_STYLE", False), ("PROTOCOL", False), ("PROTOCOL", True)):
            context, _ = sample(kind, on)
            payload = pack(context)
            self.assertEqual(unpack(payload, fingerprint(payload), type(context)), context)
            with self.assertRaisesRegex(ContractError, "CORRUPT_RECORD"):
                unpack(payload + b" ", fingerprint(payload), type(context))


@unittest.skipUnless(DSN, "Real PostgreSQL gate requires BTL_TEST_DATABASE_URL; not a release PASS")
class PostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        migrate(DSN)

    def setUp(self):
        context, command = sample()
        self.workspace = "w" + uuid.uuid4().hex
        self.scope = TrustedScope(self.workspace, "actor")
        self.context, self.command = replace(context, workspace_id=self.workspace), replace(command, workspace_id=self.workspace)
        self.workflow = PostgresWorkflow(DSN)
        self.workflow.create_context(self.scope, self.context)
        self.app = IntakeApplication(self.workflow, FixedClock(), FixedIds())

    def test_durable_retry_concurrent_and_context_advance(self):
        review = self.app.review_command(self.scope, self.command)
        with ThreadPoolExecutor(max_workers=8) as pool:
            outcomes = list(pool.map(lambda _: self.app.confirm_review(self.scope, assertions(review)), range(24)))
        self.assertEqual(sum(not x.duplicate for x in outcomes), 1)
        self.assertTrue(all(x.receipt == outcomes[0].receipt and x.event == outcomes[0].event for x in outcomes))
        self.workflow.advance_context(self.scope, replace(self.context, session_revision=5, quote_revision=8), 4, 7)
        # New adapter/connection has no memory state and recovers exact old outcome.
        fresh = IntakeApplication(PostgresWorkflow(DSN), FixedClock(), FixedIds())
        recovered = fresh.confirm_review(self.scope, assertions(review))
        self.assertTrue(recovered.duplicate)
        self.assertEqual(recovered.confirmed, outcomes[0].confirmed)
        with self.assertRaisesRegex(ContractError, "IDEMPOTENCY_CONFLICT"):
            fresh.confirm_review(self.scope, replace(assertions(review), payload_hash="b" * 64))
        with self.assertRaisesRegex(ContractError, "STALE_REVISION"):
            fresh.review_command(self.scope, replace(self.command, request_id="stale"))

    def test_failure_after_staging_rolls_back_both_and_sequence(self):
        review = self.app.review_command(self.scope, self.command)
        def broken(unit):
            def fail_after(confirmed, receipt, event):
                from infrastructure.postgres import PostgresUnit
                PostgresUnit.commit_intake(unit, confirmed, receipt, event)
                raise RuntimeError("injected precommit failure")
            unit.commit_intake = fail_after
            return unit
        class BrokenWorkflow:
            def run(_, scope, session_id, operation):
                return self.workflow.run(scope, session_id, lambda unit: operation(broken(unit)))
        broken_app = IntakeApplication(BrokenWorkflow(), FixedClock(), FixedIds())
        with self.assertRaises(RuntimeError): broken_app.confirm_review(self.scope, assertions(review))
        with connect(DSN) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM btl.intakes WHERE workspace_id=%s", (self.workspace,)).fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT count(*) FROM btl.evidence WHERE workspace_id=%s", (self.workspace,)).fetchone()[0], 0)
        outcome = self.app.confirm_review(self.scope, assertions(review))
        self.assertEqual(outcome.event.sequence, 0)

    def test_append_only_and_atomic_foreign_keys(self):
        review = self.app.review_command(self.scope, self.command)
        self.app.confirm_review(self.scope, assertions(review))
        for table in ("command_reviews", "intakes", "evidence"):
            for operation in ("UPDATE", "DELETE"):
                with self.subTest(table=table, operation=operation), self.assertRaises(psycopg.IntegrityError):
                    with connect(DSN) as db:
                        statement = (sql.SQL("UPDATE btl.{} SET content_hash=content_hash WHERE workspace_id=%s") if operation == "UPDATE" else
                                     sql.SQL("DELETE FROM btl.{} WHERE workspace_id=%s")).format(sql.Identifier(table))
                        db.execute(statement, (self.workspace,))
        with self.assertRaises(psycopg.IntegrityError):
            with connect(DSN) as db:
                db.execute("INSERT INTO btl.intakes SELECT workspace_id,session_id,'orphan','orphan-r','orphan-e',payload,content_hash FROM btl.intakes WHERE workspace_id=%s", (self.workspace,))

    def test_scope_parameterization_and_stale_cas(self):
        review = self.app.review_command(self.scope, self.command)
        with self.assertRaisesRegex(ContractError, "RESOURCE_UNAVAILABLE"):
            self.app.confirm_review(TrustedScope("foreign", "actor"), assertions(review))
        with self.assertRaisesRegex(ContractError, "STALE_REVISION"):
            self.workflow.advance_context(self.scope, replace(self.context, quote_revision=8), 4, 6)
        with self.assertRaises(ContractError):
            self.workflow.advance_context(self.scope, replace(self.context, method=replace(self.context.method, definition_hash="b"*64), quote_revision=8), 4, 7)
        self.assertIsNone(self.workflow.run(self.scope, "session", lambda unit: unit.find_review("x' OR 1=1 --")))

    def test_passport_lineage_versions_scope_and_append_only(self):
        store = ProvenanceStore(DSN)
        passport = Passport("experiment", self.workspace, "dataset", "v1", H, H, H, H, "engine1", "calc1", "XAUUSD", "feed", NOW, NOW, 4, "trial")
        store.append_passport(self.scope, passport)
        store.append_passport(self.scope, passport)
        with self.assertRaisesRegex(ContractError, "IDEMPOTENCY_CONFLICT"):
            store.append_passport(self.scope, replace(passport, input_hash="b"*64))
        revised = replace(passport, passport_revision=1, input_hash="b"*64)
        store.append_passport(self.scope, revised)
        self.assertEqual(store.get_passport(self.scope, "experiment", 0), passport)
        self.assertEqual(store.get_passport(self.scope, "experiment", 1), revised)
        with self.assertRaisesRegex(ContractError, "RESOURCE_UNAVAILABLE"):
            store.get_passport(TrustedScope("foreign", "actor"), "experiment", 0)
        parent = LineageEntry("parent", self.workspace, "experiment", "family", H, "EXPLORATORY", "ABANDONED", NOW)
        child = replace(parent, trial_id="child", parent_trial_id="parent", disposition="FAILED")
        store.append_lineage(self.scope, parent); store.append_lineage(self.scope, child)
        store.append_lineage(self.scope, child)
        self.assertEqual(store.get_lineage(self.scope, "child"), child)
        with self.assertRaisesRegex(ContractError, "IDEMPOTENCY_CONFLICT"):
            store.append_lineage(self.scope, replace(child, disposition="COMPLETED"))
        for table in ("passports", "lineage"):
            with self.assertRaises(psycopg.IntegrityError):
                with connect(DSN) as db:
                    db.execute(sql.SQL("DELETE FROM btl.{} WHERE workspace_id=%s").format(sql.Identifier(table)), (self.workspace,))

    def test_migration_idempotence_and_checksum_refusal(self):
        migrate(DSN)
        with tempfile.TemporaryDirectory() as folder:
            for source in MIGRATIONS.glob("*.sql"):
                shutil.copy(source, folder)
            first = sorted(Path(folder).glob("*.sql"))[0]
            first.write_bytes(first.read_bytes().replace(b"\n", b"\r\n"))
            migrate(DSN, Path(folder))  # Platform checkout line endings are not drift.
            first.write_bytes(first.read_bytes() + b"\n-- changed historical migration\n")
            with self.assertRaisesRegex(ContractError, "MIGRATION_DRIFT"):
                migrate(DSN, Path(folder))

    def test_runtime_role_cannot_migrate_drop_or_mutate_evidence(self):
        role = "btl_runtime_" + uuid.uuid4().hex
        with connect(DSN) as db:
            db.execute(sql.SQL("CREATE ROLE {} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE").format(sql.Identifier(role)))
        grant_runtime(DSN, role)
        review = self.app.review_command(self.scope, self.command)
        self.app.confirm_review(self.scope, assertions(review))
        for statement in ("DROP TABLE btl.intakes", "DELETE FROM btl.command_reviews", "CREATE TABLE btl.unauthorized(x int)"):
            with self.subTest(statement=statement), self.assertRaises(psycopg.errors.InsufficientPrivilege):
                with connect(DSN) as db:
                    db.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(role)))
                    db.execute(statement)
        with connect(DSN) as db:
            db.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(role)))
            self.assertEqual(db.execute("SELECT count(*) FROM btl.intakes WHERE workspace_id=%s", (self.workspace,)).fetchone()[0], 1)

    def test_real_dump_restore_empty_target_and_receipt_recovery(self):
        bin_directory = os.environ["BTL_PG_BIN"]
        review = self.app.review_command(self.scope, self.command)
        first = self.app.confirm_review(self.scope, assertions(review))
        info = psycopg.conninfo.conninfo_to_dict(DSN)
        restored_name = "btl_restore_" + uuid.uuid4().hex
        with psycopg.connect(DSN, autocommit=True) as admin:
            admin.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(sql.Identifier(restored_name)))
        restore_dsn = psycopg.conninfo.make_conninfo(**{**info, "dbname": restored_name})
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "evidence.dump"
            digest = backup(DSN, target, bin_directory)
            with self.assertRaisesRegex(ContractError, "CORRUPT_RECORD"):
                restore(restore_dsn, target, "b"*64, bin_directory)
            restore(restore_dsn, target, digest, bin_directory)
            with self.assertRaisesRegex(ContractError, "NONEMPTY_RESTORE_TARGET"):
                restore(restore_dsn, target, digest, bin_directory)
            restored = IntakeApplication(PostgresWorkflow(restore_dsn), FixedClock(), FixedIds())
            recovered = restored.confirm_review(self.scope, assertions(review))
            self.assertEqual(recovered.receipt, first.receipt)
            self.assertEqual(recovered.event, first.event)
            self.assertEqual(pack(recovered.confirmed), pack(first.confirmed))
            with connect(DSN) as original, connect(restore_dsn) as copy:
                for table in ("command_reviews", "intakes", "evidence", "passports", "lineage"):
                    query = sql.SQL("SELECT content_hash,encode(payload,'hex') FROM btl.{} ORDER BY content_hash").format(sql.Identifier(table))
                    self.assertEqual(original.execute(query).fetchall(), copy.execute(query).fetchall())
        # Never drop or overwrite a database: QA cluster is disposable outside Git.


if __name__ == "__main__":
    unittest.main()
