"""Actual snapshot restore/ACL rollback plus safe filesystem/archive refusal."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from contextlib import ExitStack
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch
import zipfile

import psycopg
from psycopg import sql

from deploy.vps import native_demo_upgrade as upgrade
from deploy.vps.google_staging import grant_google_demo_runtime
from deploy.vps.package import archive
from infrastructure.database import migrate
from identity.google_store import grant_google_runtime
from deploy.vps import runtime as native_runtime
from deploy.vps import google_staging
from deploy.vps import operator_bootstrap


class UpgradeFilesystemTests(unittest.TestCase):
    def test_bootstrap_freezes_pinned_plan_and_archive_without_importing_home_code(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'source';(source/'deploy/vps').mkdir(parents=True)
            names=['deploy/__init__.py','deploy/vps/__init__.py','deploy/vps/package.py',
                   'deploy/vps/native_demo_upgrade.py','deploy/vps/google_staging.py']
            for name in names:(source/name).write_text('# authored fixture, never executed')
            bundle=root/'source.zip';archive(source,names,bundle,'a'*40)
            plan=root/'plan.json';plan.write_text(json.dumps({'archive':str(bundle),
                'archiveHash':upgrade.digest(bundle),'sourceCommit':'a'*40}))
            sha=upgrade.digest(plan)
            frozen,copied=operator_bootstrap.stage(plan,sha,root)
            self.assertEqual(upgrade.digest(frozen/'source.zip'),upgrade.digest(bundle))
            self.assertEqual((copied/'deploy/vps/native_demo_upgrade.py').read_bytes(),
                             (source/'deploy/vps/native_demo_upgrade.py').read_bytes())
            (source/'deploy/vps/native_demo_upgrade.py').write_text('changed home file')
            self.assertNotEqual((copied/'deploy/vps/native_demo_upgrade.py').read_bytes(),
                                (source/'deploy/vps/native_demo_upgrade.py').read_bytes())
            plan.write_text('{}')
            with self.assertRaisesRegex(ValueError,'PLAN_CHANGED'):
                operator_bootstrap.stage(plan,sha,root)

    def test_apply_failure_restores_files_link_acl_and_only_restarts_scoped_services(self):
        # Full control-flow rehearsal on a fake filesystem; all DB/service/network
        # operations are replaced, never redirected to a real system or database.
        for failure in ('restart', 'health', 'reload', None):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
                root = Path(folder)
                real_path, real_stat = Path, Path.stat
                def mapped(value):
                    text = str(value)
                    if text.startswith(('/opt/', '/etc/', '/srv/', '/var/')):
                        return root/text.lstrip('/')
                    return real_path(value)
                def root_stat(path, *args, **kwargs):
                    values = list(real_stat(path, *args, **kwargs));values[4] = 0
                    return os.stat_result(values)
                base = mapped('/opt/riksora-beta')
                (base/'verified-baseline/backend').mkdir(parents=True)
                (base/'verified-baseline/backend/requirements.lock').write_bytes(b'fixture lock')
                (base/'beta-server.py').write_bytes(b'original api')
                (base/'beta-server.py').chmod(0o644)
                caddy = mapped('/etc/caddy/Caddyfile');caddy.parent.mkdir(parents=True);caddy.write_bytes(b'original caddy')
                caddy.chmod(0o644)
                config = mapped('/etc/riksora-beta');config.mkdir()
                (config/'runtime.json').write_text(json.dumps({'database': 'runtime-fixture'}))
                (config/'operator.json').write_text(json.dumps({'database': 'owner-fixture'}))
                releases = mapped('/srv/riksora/releases');releases.mkdir(parents=True)
                old = releases/'old';old.mkdir();(old/'index.html').write_bytes(b'landing')
                (old/'login').mkdir();(old/'login/index.html').write_bytes(b'old login')
                current = mapped('/srv/riksora/current');current.symlink_to(old)
                mapped('/var/backups/riksora-beta').mkdir(parents=True)
                source = root/'source';(source/'deploy/vps').mkdir(parents=True);(source/'backend').mkdir()
                (source/'deploy/vps/google_staging.py').write_text('# authored fixture')
                (source/'backend/requirements.lock').write_bytes(b'fixture lock')
                bundle = root/'source.zip'
                archive(source, ['deploy/vps/google_staging.py','backend/requirements.lock'], bundle, 'a'*40)
                payload = root/'static';(payload/'login').mkdir(parents=True);(payload/'assets').mkdir()
                (payload/'login/index.html').write_bytes(b'new login');(payload/'assets/demo.js').write_bytes(b'fixture js')
                candidate = root/'Caddyfile';candidate.write_bytes(b'candidate caddy')
                plan = {'archive': str(bundle), 'archiveHash': upgrade.digest(bundle), 'sourceCommit': 'a'*40,
                        'static': str(payload), 'staticFiles': upgrade.static_files(payload),
                        'caddy': str(candidate), 'caddyHash': upgrade.digest(candidate),
                        'expectedServerHash': upgrade.digest(base/'beta-server.py'),
                        'expectedCaddyHash': upgrade.digest(caddy), 'expectedRelease': str(old)}
                plan_file=root/'plan.json';plan_file.write_text(json.dumps(plan))
                before={'table': [], 'column': []};state=deepcopy(before);calls=[];failed=False
                def operation(args, **kwargs):
                    nonlocal failed
                    calls.append(args)
                    if failure in ('restart','reload') and args[:2] == ['systemctl', failure] and not failed:
                        failed=True;raise OSError('authored service failure')
                def grant(dsn):state['table']=[['workspaces','INSERT']]
                def revoke(db, prior, after):state.update(deepcopy(prior))
                class Connection:
                    def __enter__(self):return self
                    def __exit__(self,*args):return False
                    def execute(self,*args):return SimpleNamespace(fetchone=lambda: [True])
                stack.enter_context(patch.object(upgrade, 'Path', side_effect=mapped))
                stack.enter_context(patch.object(real_path, 'stat', root_stat))
                stack.enter_context(patch.object(upgrade.os, 'geteuid', return_value=0))
                stack.enter_context(patch.object(upgrade, 'regular'))
                stack.enter_context(patch.object(upgrade, 'check_dependencies'))
                stack.enter_context(patch.object(upgrade, 'run', side_effect=operation))
                stack.enter_context(patch.object(upgrade, 'backup_and_verify', return_value={'restore_verified': True}))
                stack.enter_context(patch.object(upgrade, 'acl_snapshot', side_effect=lambda db: deepcopy(state)))
                stack.enter_context(patch.object(upgrade, 'restore_added_acl', side_effect=revoke))
                stack.enter_context(patch.object(psycopg, 'connect', return_value=Connection()))
                stack.enter_context(patch.object(psycopg.conninfo, 'conninfo_to_dict', side_effect=lambda value: {
                    'host':'127.0.0.1','port':'5432','dbname':'riksora_beta',
                    'user':'btl_owner' if value=='owner-fixture' else 'btl_app'}))
                stack.enter_context(patch.object(native_runtime,'database_guard'))
                stack.enter_context(patch.object(google_staging,'grant_google_demo_runtime',side_effect=grant))
                stack.enter_context(patch.object(upgrade,'health',side_effect=OSError('authored health failure') if failure=='health' else None))
                if failure:
                    with self.assertRaises(OSError):upgrade.apply(plan_file)
                    self.assertEqual((base/'beta-server.py').read_bytes(),b'original api')
                    self.assertEqual(caddy.read_bytes(),b'original caddy')
                    self.assertEqual(current.resolve(),old)
                    self.assertEqual(state,before)
                else:
                    upgrade.apply(plan_file)
                    self.assertNotEqual(current.resolve(),old)
                    self.assertEqual((current/'login/index.html').read_bytes(),b'new login')
                    snapshot=next(mapped('/var/backups/riksora-beta').glob('upgrade-*'))
                    upgrade.rollback(snapshot)
                    self.assertEqual(current.resolve(),old)
                    self.assertEqual(state,before)
                    self.assertEqual((base/'beta-server.py').read_bytes(),b'original api')
                    self.assertTrue(json.loads((snapshot/'rollback-result.json').read_text())['rolledBack'])
                self.assertEqual((old/'index.html').read_bytes(),b'landing')
                for args in calls:
                    if args[0]=='systemctl' and args[1] in ('restart','reload'):
                        self.assertIn(args, [['systemctl','restart','riksora-beta'],['systemctl','reload','caddy']])

    def test_archive_manifest_hashes_and_symlink_refusal(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root/'source'
            (source/'deploy/vps').mkdir(parents=True)
            (source/'deploy/vps/google_staging.py').write_text('authored archive fixture')
            output = root/'candidate.zip'
            archive(source, ['deploy/vps/google_staging.py'], output, 'a'*40)
            self.assertEqual(upgrade.verify_archive(output, upgrade.digest(output))['sourceCommit'], 'a'*40)
            with self.assertRaisesRegex(ValueError, 'HASH_MISMATCH'):
                upgrade.verify_archive(output, '0'*64)
            with zipfile.ZipFile(output, 'a') as bundle:
                bundle.writestr('../outside', b'hostile')
            with self.assertRaisesRegex(ValueError, 'ARCHIVE_FILE_SET'):
                upgrade.verify_archive(output, upgrade.digest(output))
            (source/'alias').symlink_to(source/'deploy/vps/google_staging.py')
            with self.assertRaisesRegex(ValueError, 'STATIC_SYMLINK'):
                upgrade.static_files(source)

    def test_atomic_replacement_and_link_restore_do_not_delete_old_release(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            old, new = root/'old', root/'new'
            old.mkdir(); new.mkdir()
            (old/'index.html').write_text('landing preserved')
            current = root/'current'
            current.symlink_to(old)
            upgrade.switch_link(current, new)
            self.assertEqual(current.resolve(), new)
            upgrade.switch_link(current, old)
            self.assertEqual((current/'index.html').read_text(), 'landing preserved')
            target = root/'entry.py'
            upgrade.atomic(target, b'first')
            with patch.object(upgrade.os, 'replace', side_effect=OSError('authored failure')):
                with self.assertRaises(OSError):
                    upgrade.atomic(target, b'second')
            self.assertEqual(target.read_bytes(), b'first')
            self.assertEqual(list(root.glob('*.next-*')), [])


class NativeUpgradeRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dsn = os.environ.get('BTL_TEST_DATABASE_URL')
        if not cls.dsn:
            raise RuntimeError('FRESH_EXCLUSIVE_POSTGRESQL_REQUIRED')
        migrate(cls.dsn)
        with psycopg.connect(cls.dsn, autocommit=True) as db:
            db.execute('CREATE ROLE btl_owner NOLOGIN')
            db.execute('CREATE ROLE btl_app NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS')
        grant_google_runtime(cls.dsn, 'btl_app')

    def test_late_grant_failure_rolls_back_every_new_permission(self):
        with psycopg.connect(self.dsn) as db:
            before=upgrade.acl_snapshot(db)
            db.execute('ALTER TABLE btl.v2_access_windows RENAME TO upgrade_hidden_windows')
        try:
            with self.assertRaises(psycopg.errors.UndefinedTable):
                grant_google_demo_runtime(self.dsn)
        finally:
            with psycopg.connect(self.dsn) as db:
                db.execute('ALTER TABLE btl.upgrade_hidden_windows RENAME TO v2_access_windows')
        with psycopg.connect(self.dsn) as db:
            self.assertEqual(upgrade.acl_snapshot(db),before)

    def test_snapshot_dump_restore_survives_concurrent_source_write(self):
        with psycopg.connect(self.dsn) as db:
            db.execute('CREATE TABLE btl.upgrade_qa (id integer PRIMARY KEY, value text NOT NULL)')
            db.execute("INSERT INTO btl.upgrade_qa VALUES (1,'authored original')")
        created = []
        def create(name):
            with psycopg.connect(self.dsn, autocommit=True) as db:
                db.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
            created.append(name)
        def drop(name):
            self.assertIn(name, created)
            with psycopg.connect(self.dsn, autocommit=True) as db:
                db.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(name)))
        real_run = upgrade.run
        wrote = False
        def with_writer(args, **kwargs):
            nonlocal wrote
            if str(args[0]).endswith('/pg_dump') and not wrote:
                with psycopg.connect(self.dsn) as db:
                    db.execute("INSERT INTO btl.upgrade_qa VALUES (2,'concurrent authored row')")
                wrote = True
            return real_run(args, **kwargs)
        with tempfile.TemporaryDirectory() as folder, patch.object(upgrade, 'run', side_effect=with_writer):
            proof = upgrade.backup_and_verify(self.dsn, Path(folder)/'backup', create, drop)
            self.assertTrue(proof['restore_verified'])
            self.assertGreaterEqual(proof['tables_equal'], 35)
            self.assertEqual(json.loads((Path(folder)/'backup/restore-proof.json').read_text()), proof)
        with psycopg.connect(self.dsn) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM btl.upgrade_qa').fetchone()[0], 2)
            self.assertFalse(db.execute('SELECT EXISTS(SELECT 1 FROM pg_database WHERE datname=ANY(%s))', (created,)).fetchone()[0])

    def test_demo_acl_grant_and_exact_reversal_preserve_prior_google_permissions(self):
        with psycopg.connect(self.dsn) as db:
            before = upgrade.acl_snapshot(db)
        grant_google_demo_runtime(self.dsn)
        with psycopg.connect(self.dsn) as db:
            after = upgrade.acl_snapshot(db)
            self.assertNotEqual(after, before)
            for table, privilege in [('sandbox_access_events', 'INSERT'), ('memberships', 'DELETE'), ('resources', 'INSERT')]:
                self.assertFalse(db.execute('SELECT has_table_privilege(%s,%s,%s)', ('btl_app', 'btl.'+table, privilege)).fetchone()[0])
            upgrade.restore_added_acl(db, before, after)
        with psycopg.connect(self.dsn) as db:
            self.assertEqual(upgrade.acl_snapshot(db), before)
