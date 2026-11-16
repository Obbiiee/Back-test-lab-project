"""Runner unit tests and opt-in checks against an empty disposable database.

Exercises the actual Python runner with both published migration histories.
No existing database or deployment ledger is queried by this test.
"""
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from contracts.primitives import ContractError
from infrastructure.database import MIGRATIONS, connect, migrate


P0_ONLY = frozenset((
    '023_observed_replay_progress.sql',
    '024_observed_progress_consolidation.sql',
    '025_product_terminal_order_archive.sql',
    '032_tick_method_metric_projections.sql',
))
INTEGRATION_ONLY = frozenset((
    '023_account_identities.sql', '024_tick_terminal_order_archive.sql',
    '025_tick_compact_recovery_bases.sql', '026_tick_journal_order_index.sql',
    '027_tick_session_analytics_counts.sql', '028_tick_session_metric_projection.sql',
    '029_tick_session_analytics_coverage.sql', '030_tick_journal_c_keyset_order.sql',
    '031_tick_analytics_closed_order_keyset.sql',
))
DSN = os.getenv('BTL_MIGRATION_RECONCILIATION_DSN')


class MigrationRunnerIdentityTests(unittest.TestCase):
    def run_migrations(self, directory, recorded):
        statements = []

        class Database:
            def execute(self, sql, params=None):
                statements.append((sql, params))
                return self

            def fetchall(self):
                return list(recorded.items())

        @contextmanager
        def connection(_dsn):
            yield Database()

        with patch('infrastructure.database.connect', connection):
            migrate('unused', directory)
        return statements

    def test_equal_numeric_prefix_keeps_distinct_names_and_lf_checksums(self):
        from hashlib import sha256
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            (directory/'023_a.sql').write_bytes(b'SELECT 1;\r\n')
            (directory/'023_b.sql').write_bytes(b'SELECT 2;\n')
            existing = {'023_a.sql': sha256(b'SELECT 1;\n').hexdigest()}
            statements = self.run_migrations(directory, existing)
            self.assertNotIn(('SELECT 1;\n', None), statements)
            self.assertIn(('SELECT 2;\n', None), statements)
            inserts = [args for sql, args in statements if sql.startswith('INSERT INTO public.btl_migrations')]
            self.assertEqual(inserts, [('023_b.sql', sha256(b'SELECT 2;\n').hexdigest())])

    def test_renaming_an_applied_file_is_drift_even_with_identical_sql(self):
        from hashlib import sha256
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            (directory/'031_renamed.sql').write_text('SELECT 1;\n')
            with self.assertRaises(ContractError) as error:
                self.run_migrations(directory, {'023_original.sql': sha256(b'SELECT 1;\n').hexdigest()})
            self.assertEqual(error.exception.code, 'MIGRATION_DRIFT')

    def test_editing_an_applied_file_is_drift(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            (directory/'023_original.sql').write_text('SELECT 2;\n')
            with self.assertRaises(ContractError) as error:
                self.run_migrations(directory, {'023_original.sql': '0'*64})
            self.assertEqual(error.exception.code, 'MIGRATION_DRIFT')


@unittest.skipUnless(DSN, 'requires a fresh disposable migration harness database')
class MigrationReconciliationTests(unittest.TestCase):
    def test_upgrade_preserves_both_ledgers_and_financial_guards(self):
        history = os.environ['BTL_MIGRATION_RECONCILIATION_HISTORY']
        self.assertIn(history, ('fresh', 'pr44', 'pr48'))
        # Refuse to operate on an existing application database, even in tests.
        with connect(DSN) as db:
            self.assertIsNone(db.execute("SELECT to_regnamespace('btl')").fetchone()[0])
            self.assertIsNone(db.execute("SELECT to_regclass('public.btl_migrations')").fetchone()[0])
        excluded = P0_ONLY if history == 'pr44' else INTEGRATION_ONLY
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            if history != 'fresh':
                for source in MIGRATIONS.glob('[0-9][0-9][0-9]_*.sql'):
                    if source.name not in excluded:
                        shutil.copyfile(source, directory / source.name)
                migrate(DSN, directory)
                with connect(DSN) as db:
                    before = dict(db.execute('SELECT version,checksum FROM public.btl_migrations').fetchall())
                    db.execute("INSERT INTO btl.tick_sessions SELECT 'ws',id,repeat('a',64),repeat('a',64),0,decode('01','hex'),repeat('b',64) FROM unnest(ARRAY['legacy','progress']) id")
                    db.execute('INSERT INTO btl.tick_checkpoints SELECT workspace_id,session_id,revision,payload,content_hash FROM btl.tick_sessions')
                    if history == 'pr48':
                        db.execute("INSERT INTO btl.observed_replay_progress VALUES ('ws','progress',0,repeat('b',64),4,200,2,decode('01','hex'),repeat('b',64))")
            else:
                before = {}
            migrate(DSN)
            migrate(DSN)  # Repeat is a no-op, including duplicate numeric prefixes.
            with connect(DSN) as db:
                after = dict(db.execute('SELECT version,checksum FROM public.btl_migrations').fetchall())
                self.assertEqual({k: after[k] for k in before}, before)
                self.assertEqual(set(after), {p.name for p in MIGRATIONS.glob('[0-9][0-9][0-9]_*.sql')})
                for table in ('account_identities','tick_terminal_orders','tick_recovery_bases',
                              'tick_journal_order_projection','tick_session_metric_projections',
                              'tick_method_metric_projections','observed_replay_progress','tick_terminal_order_archive_v1'):
                    self.assertIsNotNone(db.execute('SELECT to_regclass(%s)', ('btl.'+table,)).fetchone()[0])
                if history == 'fresh':
                    db.execute("INSERT INTO btl.tick_sessions SELECT 'ws',id,repeat('a',64),repeat('a',64),0,decode('01','hex'),repeat('b',64) FROM unnest(ARRAY['legacy','progress']) id")
                    db.execute('INSERT INTO btl.tick_checkpoints SELECT workspace_id,session_id,revision,payload,content_hash FROM btl.tick_sessions')
                if history != 'pr48':
                    db.execute("INSERT INTO btl.observed_replay_progress VALUES ('ws','progress',0,repeat('b',64),4,200,2,decode('01','hex'),repeat('b',64))")
                self.assertEqual(db.execute("SELECT revision,through_ns,next_group_index FROM btl.observed_replay_progress WHERE session_id='progress'").fetchone(), (4, 200, 2))
                db.execute("CREATE ROLE migration_runtime; GRANT USAGE ON SCHEMA btl TO migration_runtime; GRANT SELECT,UPDATE ON btl.tick_sessions TO migration_runtime; SET ROLE migration_runtime")
                db.execute("UPDATE btl.tick_sessions SET revision=1 WHERE session_id='legacy'")
                db.execute('RESET ROLE')
            # Without immutable checkpoint+receipt, a revision jump must fail.
            with self.assertRaises(Exception):
                with connect(DSN) as db:
                    db.execute("UPDATE btl.tick_sessions SET revision=5 WHERE session_id='progress'")
            commit_sql = "INSERT INTO btl.tick_checkpoints VALUES ('ws','progress',5,decode('02','hex'),repeat('c',64)); INSERT INTO btl.tick_commands VALUES ('ws','progress','financial',5,repeat('c',64),decode('02','hex'),repeat('c',64)); UPDATE btl.tick_sessions SET revision=5 WHERE session_id='progress';"
            with self.assertRaisesRegex(RuntimeError, 'rollback probe'):
                with connect(DSN) as db:
                    db.execute(commit_sql)
                    raise RuntimeError('rollback probe')
            with connect(DSN) as db:
                self.assertEqual(db.execute('SELECT count(*) FROM btl.observed_replay_progress').fetchone()[0], 1)
                self.assertEqual(db.execute('SELECT count(*) FROM btl.tick_commands').fetchone()[0], 0)
                db.execute(commit_sql)
            with connect(DSN) as db:
                self.assertEqual(db.execute('SELECT count(*) FROM btl.observed_replay_progress').fetchone()[0], 0)
                self.assertEqual(db.execute("SELECT revision FROM btl.tick_sessions WHERE session_id='progress'").fetchone()[0], 5)
            for table in ('tick_terminal_orders', 'tick_terminal_order_archive_v1', 'tick_recovery_bases'):
                with self.assertRaises(Exception):
                    with connect(DSN) as db:
                        db.execute('TRUNCATE btl.'+table)
            # Never repair a historical checksum by renaming or modifying SQL.
            for source in MIGRATIONS.glob('[0-9][0-9][0-9]_*.sql'):
                shutil.copyfile(source, directory / source.name)
            changed = directory / '023_observed_replay_progress.sql'
            changed.write_text(changed.read_text()+'\n-- unauthorized drift\n')
            with self.assertRaises(ContractError) as error:
                migrate(DSN, directory)
            self.assertEqual(error.exception.code, 'MIGRATION_DRIFT')
            changed.unlink()  # Only the test-owned temporary copy.
            with self.assertRaises(ContractError) as error:
                migrate(DSN, directory)
            self.assertEqual(error.exception.code, 'MIGRATION_DRIFT')


if __name__ == '__main__':
    unittest.main()
