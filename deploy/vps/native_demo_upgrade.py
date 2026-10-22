"""Narrow, explicit native demo upgrade. Never installs packages or migrates.

Only the audited existing riksora-beta service, its static release, minimum demo
ACL additions and Caddy are in scope. Requires root in the operator's terminal.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import sys
import time
import uuid
import zipfile


class UpgradeRefusal(ValueError):
    pass


def need(value, code):
    if not value:
        raise UpgradeRefusal(code)


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            result.update(block)
    return result.hexdigest()


def freeze_file(source, destination, expected, *, maximum=100000000):
    """Freeze verified bytes root-side; never execute an editable home payload."""
    descriptor = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    checksum = hashlib.sha256()
    total = 0
    with os.fdopen(descriptor, 'rb') as incoming, Path(destination).open('xb') as outgoing:
        need(stat.S_ISREG(os.fstat(incoming.fileno()).st_mode), 'PAYLOAD_REGULAR_FILE')
        for chunk in iter(lambda: incoming.read(1048576), b''):
            total += len(chunk)
            need(total <= maximum, 'PAYLOAD_SIZE')
            outgoing.write(chunk)
            checksum.update(chunk)
        outgoing.flush()
        os.fsync(outgoing.fileno())
    need(checksum.hexdigest() == expected, 'PAYLOAD_CHANGED_WHILE_FREEZING')
    Path(destination).chmod(0o600)


def regular(path, mode=None):
    info = Path(path).lstat()
    need(stat.S_ISREG(info.st_mode) and info.st_uid == 0, 'ROOT_REGULAR_FILE_REQUIRED')
    need(not info.st_mode & 0o007, 'WORLD_ACCESS_REFUSED')
    if mode is not None:
        need(stat.S_IMODE(info.st_mode) == mode, 'FILE_MODE_DRIFT')


def check_dependencies(path):
    from importlib.metadata import version
    for line in Path(path).read_text().splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        parts=line.strip().split('==')
        need(len(parts)==2 and all(parts),'PINNED_DEPENDENCY_REQUIRED')
        need(version(parts[0])==parts[1],'INSTALLED_DEPENDENCY_DRIFT')


def run(args, *, env=None, timeout=60):
    return subprocess.run(args, check=True, env=env, timeout=timeout,
                          stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def atomic(path, raw, mode=0o644):
    path = Path(path)
    temporary = path.with_name(path.name + '.next-' + uuid.uuid4().hex)
    try:
        with temporary.open('xb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(mode)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def switch_link(path, target):
    path = Path(path)
    temporary = path.with_name(path.name + '.next-' + uuid.uuid4().hex)
    temporary.symlink_to(target)
    os.replace(temporary, path)


def verify_archive(path, expected_hash):
    need(digest(path) == expected_hash, 'ARCHIVE_HASH_MISMATCH')
    from deploy.vps.package import allowed
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        need(len(names) == len(set(names)) and len(names) <= 2000, 'ARCHIVE_DIRECTORY')
        need(archive.getinfo('RELEASE_MANIFEST.json').file_size <= 1048576, 'ARCHIVE_MANIFEST_SIZE')
        manifest = json.loads(archive.read('RELEASE_MANIFEST.json'))
        need(set(names) == set(manifest['files']) | {'RELEASE_MANIFEST.json'}, 'ARCHIVE_FILE_SET')
        need(len(manifest['sourceCommit']) == 40 and all(c in '0123456789abcdef' for c in manifest['sourceCommit']), 'COMMIT_FORMAT')
        total = 0
        for name, expected in manifest['files'].items():
            item = archive.getinfo(name)
            need(allowed(name) and not PurePosixPath(name).is_absolute(), 'ARCHIVE_PATH_REFUSED')
            need(stat.S_IFMT(item.external_attr >> 16) in (0, stat.S_IFREG), 'ARCHIVE_LINK_REFUSED')
            total += item.file_size
            need(item.file_size <= 25000000 and total <= 100000000, 'ARCHIVE_SIZE')
            need(hashlib.sha256(archive.read(name)).hexdigest() == expected, 'ARCHIVE_FILE_HASH')
        need('deploy/vps/google_staging.py' in manifest['files'], 'MISSING_COMPOSITION')
        return manifest


def static_files(directory):
    directory = Path(directory)
    need(directory.is_dir() and not directory.is_symlink(), 'STATIC_DIRECTORY')
    result = {}
    for path in directory.rglob('*'):
        need(not path.is_symlink(), 'STATIC_SYMLINK')
        if path.is_file():
            relative = path.relative_to(directory).as_posix()
            need(not any(part.startswith('.') for part in path.relative_to(directory).parts), 'STATIC_HIDDEN_FILE')
            result[relative] = digest(path)
        else:
            need(path.is_dir(), 'STATIC_SPECIAL_FILE')
    return result


def fingerprints(db):
    """Bounded private restore proof; never returns row contents."""
    from psycopg import sql
    tables = db.execute("SELECT schemaname,tablename FROM pg_tables WHERE schemaname='btl' "
                        "OR (schemaname='public' AND tablename='btl_migrations') ORDER BY 1,2").fetchall()
    need(bool(tables), 'NO_APPLICATION_TABLES')
    result = {}
    for schema, name in tables:
        query = sql.SQL('SELECT row_to_json(t)::text FROM {}.{} t ORDER BY row_to_json(t)::text').format(
            sql.Identifier(schema), sql.Identifier(name))
        checksum = hashlib.sha256()
        count = 0
        with db.cursor(name='restore_proof_' + uuid.uuid4().hex) as cursor:
            cursor.itersize = 100
            cursor.execute(query)
            for (row,) in cursor:
                count += 1
                need(count <= 100000 and len(row) <= 16777216, 'RESTORE_PROOF_CAPACITY')
                checksum.update(row.encode('utf-8') + b'\n')
        result[schema + '.' + name] = [count, checksum.hexdigest()]
    return result


def backup_and_verify(owner_dsn, directory, create_database, drop_database):
    """Exported snapshot pins the dump and fingerprint despite concurrent users."""
    import psycopg
    from psycopg import sql
    from infrastructure.database import _libpq_env, restore
    directory = Path(directory)
    directory.mkdir(mode=0o700, exist_ok=False)
    dump = directory/'database.dump'
    target_name = 'riksora_restore_' + uuid.uuid4().hex
    created = False
    try:
        with psycopg.connect(owner_dsn, options='-c statement_timeout=60000 -c lock_timeout=3000') as db:
            db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
            db.execute("SET LOCAL TIME ZONE 'UTC'")
            snapshot = db.execute('SELECT pg_export_snapshot()').fetchone()[0]
            before = fingerprints(db)
            run(['/usr/lib/postgresql/16/bin/pg_dump', '--format=custom', '--no-owner', '--no-acl',
                 '--snapshot=' + snapshot, '--file=' + str(dump)], env=_libpq_env(owner_dsn), timeout=120)
        dump.chmod(0o600)
        sha = digest(dump)
        (directory/'database.sha256').write_text(sha + '\n')
        create_database(target_name)
        created = True
        target = psycopg.conninfo.make_conninfo(owner_dsn, dbname=target_name)
        with psycopg.connect(target) as db:
            db.execute(sql.SQL('REVOKE CONNECT ON DATABASE {} FROM PUBLIC').format(sql.Identifier(target_name)))
        restore(target, dump, sha, '/usr/lib/postgresql/16/bin')
        with psycopg.connect(target, options='-c statement_timeout=60000') as db:
            db.execute('SET TRANSACTION READ ONLY')
            db.execute("SET LOCAL TIME ZONE 'UTC'")
            need(fingerprints(db) == before, 'RESTORED_DATA_MISMATCH')
        proof = {'dump_sha256': sha, 'tables_equal': len(before), 'restore_verified': True,
                 'production_rows_modified': False}
        (directory/'restore-proof.json').write_text(json.dumps(proof, indent=2) + '\n')
        return proof
    finally:
        if created:
            # Only this invocation's newly created restore copy; never the source.
            drop_database(target_name)


def acl_snapshot(db):
    table = db.execute("SELECT table_name,privilege_type FROM information_schema.role_table_grants "
                       "WHERE table_schema='btl' AND grantee='btl_app'").fetchall()
    column = db.execute("SELECT table_name,column_name,privilege_type FROM information_schema.column_privileges "
                        "WHERE table_schema='btl' AND grantee='btl_app'").fetchall()
    return {'table': sorted(map(list, table)), 'column': sorted(map(list, column))}


def restore_added_acl(db, before, after):
    from psycopg import sql
    permitted = {'SELECT', 'INSERT', 'UPDATE', 'DELETE', 'REFERENCES', 'TRIGGER', 'TRUNCATE'}
    for table, privilege in sorted(set(map(tuple, after['table'])) - set(map(tuple, before['table']))):
        need(privilege in permitted, 'ACL_PRIVILEGE')
        db.execute(sql.SQL('REVOKE {} ON btl.{} FROM btl_app').format(sql.SQL(privilege), sql.Identifier(table)))
    for table, column, privilege in sorted(set(map(tuple, after['column'])) - set(map(tuple, before['column']))):
        need(privilege in {'SELECT', 'INSERT', 'UPDATE', 'REFERENCES'}, 'ACL_COLUMN_PRIVILEGE')
        db.execute(sql.SQL('REVOKE {}({}) ON btl.{} FROM btl_app').format(
            sql.SQL(privilege), sql.Identifier(column), sql.Identifier(table)))
    need(acl_snapshot(db) == before, 'ACL_ROLLBACK_MISMATCH')


def launcher(source):
    return ("from pathlib import Path\nimport sys,os,json\n"
            f"ROOT=Path({str(source)!r});sys.path[:0]=[str(ROOT),str(ROOT/'backend')]\n"
            "def main():\n"
            " from deploy.vps.runtime import database_guard\n"
            " from deploy.vps.google_staging import create_google_demo_app\n"
            " cfg=json.loads(Path('/etc/riksora-beta/runtime.json').read_text())\n"
            " database_guard(cfg['database'])\n"
            " app=create_google_demo_app(cfg['database'],cfg['authSecret'],google_client_id=cfg['googleClientId'],google_client_secret=cfg['googleClientSecret'],google_redirect_uri=cfg['googleRedirectUri'])\n"
            " import uvicorn\n"
            " uvicorn.run(app,host='127.0.0.1',port=8001,proxy_headers=True,forwarded_allow_ips='127.0.0.1',access_log=False,workers=1)\n"
            "if __name__=='__main__':\n"
            " try:main()\n"
            " except Exception as error:print('DEMO_START_REFUSED:'+type(error).__name__,file=sys.stderr);raise SystemExit(1) from None\n").encode()


def health():
    import urllib.request
    import urllib.error
    for _ in range(20):
        try:
            request = urllib.request.Request('http://127.0.0.1:8001/api/v1/auth/providers',
                                             headers={'X-Forwarded-Proto': 'https'})
            with urllib.request.urlopen(request, timeout=3) as response:
                value = json.loads(response.read(4096))
                need(value.get('demoConfigured') is True and value['googleConfigured']
                     and not value['password'] and not value['billingConfigured'], 'WRONG_API_MODE')
            break
        except (urllib.error.URLError, OSError):
            time.sleep(1)
    else:
        raise ValueError('API_HEALTH_FAILED')
    request = urllib.request.Request('http://127.0.0.1:8001/api/v1/workspaces',
                                     headers={'X-Forwarded-Proto': 'https'})
    try:
        urllib.request.urlopen(request, timeout=3)
        raise ValueError('UNAUTHENTICATED_ACCESS')
    except urllib.error.HTTPError as error:
        error.close()
        need(error.code == 401, 'WORKSPACE_GATE_FAILED')


def apply(plan_path):
    need(os.geteuid() == 0, 'OPERATOR_AUTHENTICATION_REQUIRED')
    os.umask(0o077)
    plan = json.loads(Path(plan_path).read_text())
    need(set(plan) == {'archive', 'archiveHash', 'static', 'staticFiles', 'caddy', 'caddyHash',
                       'expectedServerHash', 'expectedCaddyHash', 'expectedRelease', 'sourceCommit'}, 'PLAN_KEYS')
    base = Path('/opt/riksora-beta')
    need(base.is_dir() and not base.is_symlink(), 'INSTALLATION_DIRECTORY')
    server = base/'beta-server.py'
    caddy = Path('/etc/caddy/Caddyfile')
    link = Path('/srv/riksora/current')
    for path in (server, caddy):
        need(path.is_file() and not path.is_symlink(), 'LIVE_REGULAR_FILE')
        need(path.stat().st_uid == 0 and not path.stat().st_mode & 0o022, 'LIVE_FILE_OWNERSHIP')
    need(digest(server) == plan['expectedServerHash'] and digest(caddy) == plan['expectedCaddyHash'], 'LIVE_VERSION_DRIFT')
    need(link.is_symlink() and str(link.resolve()) == plan['expectedRelease'], 'LIVE_RELEASE_DRIFT')
    need(link.resolve().is_relative_to(Path('/srv/riksora/releases')), 'RELEASE_OUTSIDE_ROOT')
    old_static = static_files(link.resolve())
    for name in ('runtime.json', 'operator.json'):
        regular(Path('/etc/riksora-beta')/name, 0o640 if name == 'runtime.json' else 0o600)
    configuration_hashes = {name:digest(Path('/etc/riksora-beta')/name)
                            for name in ('runtime.json','operator.json')}
    cfg = json.loads(Path('/etc/riksora-beta/runtime.json').read_text())
    owner = json.loads(Path('/etc/riksora-beta/operator.json').read_text())
    import psycopg
    for value, user in ((cfg['database'], 'btl_app'), (owner['database'], 'btl_owner')):
        fields = psycopg.conninfo.conninfo_to_dict(value)
        need(fields.get('host') == '127.0.0.1' and fields.get('port', '5432') == '5432'
             and fields.get('dbname') == 'riksora_beta' and fields.get('user') == user, 'DATABASE_IDENTITY')
    for service in ('riksora-beta', 'caddy', 'postgresql'):
        run(['systemctl', 'is-active', '--quiet', service])
    # Freeze every mutable operator input before validation/use. Never validate a
    # home file and later reopen different bytes as root after a long restore test.
    snapshot = Path('/var/backups/riksora-beta')/('upgrade-' + uuid.uuid4().hex)
    snapshot.mkdir(mode=0o700)
    (snapshot/'old-static.json').write_text(json.dumps(old_static,indent=2))
    freeze_file(plan['archive'], snapshot/'source.zip', plan['archiveHash'])
    need(static_files(plan['static']) == plan['staticFiles'], 'STATIC_PAYLOAD_DRIFT')
    frozen_static = snapshot/'static'
    frozen_static.mkdir(mode=0o700)
    for name, sha in plan['staticFiles'].items():
        need(name == 'login/index.html' or (name.startswith('assets/') and len(PurePosixPath(name).parts)==2), 'STATIC_OVERLAY_PATH')
        destination=frozen_static/name
        destination.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        freeze_file(Path(plan['static'])/name,destination,sha,maximum=25000000)
    freeze_file(plan['caddy'],snapshot/'candidate.Caddyfile',plan['caddyHash'],maximum=100000)
    plan={**plan,'archive':str(snapshot/'source.zip'),'static':str(frozen_static),
          'caddy':str(snapshot/'candidate.Caddyfile')}
    (snapshot/'plan.json').write_text(json.dumps(plan,indent=2))
    manifest = verify_archive(plan['archive'], plan['archiveHash'])
    need(manifest['sourceCommit'] == plan['sourceCommit'], 'SOURCE_COMMIT_DRIFT')
    need(static_files(plan['static']) == plan['staticFiles'], 'STATIC_PAYLOAD_DRIFT')
    need(digest(plan['caddy']) == plan['caddyHash'], 'CADDY_CANDIDATE_DRIFT')
    run(['caddy', 'validate', '--config', plan['caddy'], '--adapter', 'caddyfile'])
    source = base/'releases'/plan['sourceCommit']
    release = Path('/srv/riksora/releases')/(plan['sourceCommit'][:12] + '-synthetic-demo')
    need(not source.exists() and not release.exists(), 'CANDIDATE_ALREADY_EXISTS')
    if not source.parent.exists():
        source.parent.mkdir(mode=0o755)
        source.parent.chmod(0o755)
    need(source.parent.is_dir() and not source.parent.is_symlink()
         and source.parent.stat().st_uid == 0 and not source.parent.stat().st_mode & 0o022
         and source.parent.stat().st_mode & 0o005 == 0o005, 'SOURCE_PARENT_PERMISSIONS')
    source.mkdir(mode=0o755)
    source.chmod(0o755)
    with zipfile.ZipFile(plan['archive']) as archive:
        for name in manifest['files']:
            target = source/name
            target.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
            target.write_bytes(archive.read(name))
            target.chmod(0o644)
    # umask affects intermediate directories; make only this new source readable.
    for directory in source.rglob('*'):
        if directory.is_dir():
            directory.chmod(0o755)
    need((source/'backend/requirements.lock').read_bytes() == (base/'verified-baseline/backend/requirements.lock').read_bytes(), 'DEPENDENCY_DRIFT')
    check_dependencies(source/'backend/requirements.lock')
    sys.path[:0] = [str(source), str(source/'backend')]
    from deploy.vps.runtime import database_guard
    from deploy.vps.google_staging import grant_google_demo_runtime
    database_guard(cfg['database'])
    def create_restore(name):
        run(['runuser', '-u', 'postgres', '--', '/usr/lib/postgresql/16/bin/createdb',
             '--host=/var/run/postgresql', '--port=5432', '--username=postgres', '-O', 'btl_owner', name],
            env={k:v for k,v in os.environ.items() if not k.startswith(('PG','BTL_'))})
    def drop_restore(name):
        need(name.startswith('riksora_restore_') and len(name) == len('riksora_restore_') + 32, 'RESTORE_NAME')
        run(['runuser', '-u', 'postgres', '--', '/usr/lib/postgresql/16/bin/dropdb',
             '--host=/var/run/postgresql', '--port=5432', '--username=postgres', name],
            env={k:v for k,v in os.environ.items() if not k.startswith(('PG','BTL_'))})
    backup_and_verify(owner['database'], snapshot/'backup', create_restore, drop_restore)
    shutil.copytree(link.resolve(), release, symlinks=False)
    need(static_files(release) == old_static, 'LANDING_COPY_DRIFT')
    for name, sha in plan['staticFiles'].items():
        need(name == 'login/index.html' or (name.startswith('assets/') and len(PurePosixPath(name).parts) == 2), 'STATIC_OVERLAY_PATH')
        target = release/name
        if name != 'login/index.html' and target.exists():
            need(digest(target) == sha, 'ASSET_COLLISION')
        target.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
        target.write_bytes((Path(plan['static'])/name).read_bytes())
    for path in release.rglob('*'):
        path.chmod(0o755 if path.is_dir() else 0o644)
    release.chmod(0o755)
    old_server, old_caddy = server.read_bytes(), caddy.read_bytes()
    (snapshot/'beta-server.py').write_bytes(old_server)
    (snapshot/'Caddyfile').write_bytes(old_caddy)
    (snapshot/'previous-release').write_text(str(link.resolve()) + '\n')
    with psycopg.connect(owner['database']) as db:
        need(db.execute("SELECT EXISTS(SELECT 1 FROM pg_namespace n "
                        "CROSS JOIN LATERAL aclexplode(n.nspacl) a JOIN pg_roles r ON r.oid=a.grantee "
                        "WHERE n.nspname='btl' AND r.rolname='btl_app' AND a.privilege_type='USAGE')").fetchone()[0],
             'EXISTING_DIRECT_SCHEMA_USAGE_REQUIRED')
        before = acl_snapshot(db)
    (snapshot/'acl-before.json').write_text(json.dumps(before, indent=2))
    after = before
    touched = False
    try:
        need(digest(server)==plan['expectedServerHash'] and digest(caddy)==plan['expectedCaddyHash']
             and str(link.resolve())==plan['expectedRelease'], 'LIVE_CHANGED_DURING_PREPARATION')
        need(all(digest(Path('/etc/riksora-beta')/name)==sha
                 for name,sha in configuration_hashes.items()),'CONFIG_CHANGED_DURING_PREPARATION')
        grant_google_demo_runtime(owner['database'])
        with psycopg.connect(owner['database']) as db:
            after = acl_snapshot(db)
        (snapshot/'acl-after.json').write_text(json.dumps(after, indent=2))
        touched = True
        atomic(server, launcher(source))
        run(['systemctl', 'restart', 'riksora-beta'])
        health()
        atomic(caddy, Path(plan['caddy']).read_bytes())
        run(['systemctl', 'reload', 'caddy'])
        switch_link(link, release)
        need(digest(release/'index.html') == old_static['index.html'], 'LANDING_CHANGED')
        (snapshot/'result.json').write_text(json.dumps({'mode': 'SHORT_SYNTHETIC_DEMO',
            'sourceCommit': plan['sourceCommit'], 'installed': True, 'fiveYearCoverage': False}))
    except BaseException:
        if touched:
            atomic(server, old_server)
            switch_link(link, plan['expectedRelease'])
            atomic(caddy, old_caddy)
        with psycopg.connect(owner['database']) as db:
            current = acl_snapshot(db)
            need(current == after, 'CONCURRENT_ACL_CHANGE_REQUIRES_OPERATOR')
            restore_added_acl(db, before, after)
        if touched:
            run(['systemctl', 'restart', 'riksora-beta'])
            run(['systemctl', 'reload', 'caddy'])
        raise
    print('DEMO_UPGRADE_APPLIED; NOT_REAL_HISTORY_OR_SALES_ACCEPTANCE')
    print('Private backup/rollback snapshot:', snapshot)


def rollback(snapshot_path):
    """Revert only this exact deployment; retain all saved customer/demo data."""
    need(os.geteuid()==0,'OPERATOR_AUTHENTICATION_REQUIRED')
    snapshot=Path(snapshot_path)
    need(snapshot.is_dir() and not snapshot.is_symlink()
         and snapshot.resolve().is_relative_to(Path('/var/backups/riksora-beta'))
         and snapshot.name.startswith('upgrade-'),'ROLLBACK_SNAPSHOT_PATH')
    for name in ('plan.json','result.json','beta-server.py','Caddyfile','acl-before.json','acl-after.json','old-static.json'):
        regular(snapshot/name)
    plan=json.loads((snapshot/'plan.json').read_text())
    result=json.loads((snapshot/'result.json').read_text())
    need(result.get('installed') is True and result['sourceCommit']==plan['sourceCommit'],'ROLLBACK_NOT_INSTALLED')
    base=Path('/opt/riksora-beta');server=base/'beta-server.py'
    caddy=Path('/etc/caddy/Caddyfile');link=Path('/srv/riksora/current')
    source=base/'releases'/plan['sourceCommit']
    release=Path('/srv/riksora/releases')/(plan['sourceCommit'][:12]+'-synthetic-demo')
    need(digest(server)==hashlib.sha256(launcher(source)).hexdigest()
         and digest(caddy)==plan['caddyHash'] and link.resolve()==release,'ROLLBACK_LIVE_VERSION_DRIFT')
    need(digest(snapshot/'beta-server.py')==plan['expectedServerHash']
         and digest(snapshot/'Caddyfile')==plan['expectedCaddyHash'],'ROLLBACK_SNAPSHOT_DRIFT')
    old=Path(plan['expectedRelease'])
    need(old.resolve().is_relative_to(Path('/srv/riksora/releases'))
         and static_files(old)==json.loads((snapshot/'old-static.json').read_text()),'ROLLBACK_OLD_RELEASE_CHANGED')
    regular(Path('/etc/riksora-beta/operator.json'),0o600)
    owner=json.loads(Path('/etc/riksora-beta/operator.json').read_text())
    before=json.loads((snapshot/'acl-before.json').read_text())
    after=json.loads((snapshot/'acl-after.json').read_text())
    import psycopg
    identity=psycopg.conninfo.conninfo_to_dict(owner['database'])
    need(identity.get('host')=='127.0.0.1' and identity.get('port','5432')=='5432'
         and identity.get('dbname')=='riksora_beta' and identity.get('user')=='btl_owner','ROLLBACK_DATABASE_IDENTITY')
    with psycopg.connect(owner['database']) as db:
        need(acl_snapshot(db)==after,'ROLLBACK_CONCURRENT_ACL_CHANGE')
    run(['caddy','validate','--config',str(snapshot/'Caddyfile'),'--adapter','caddyfile'])
    run(['systemctl','stop','riksora-beta'])
    try:
        atomic(server,(snapshot/'beta-server.py').read_bytes())
        atomic(caddy,(snapshot/'Caddyfile').read_bytes())
        switch_link(link,old)
        with psycopg.connect(owner['database']) as db:
            restore_added_acl(db,before,after)
        run(['systemctl','reload','caddy'])
    finally:
        run(['systemctl','start','riksora-beta'])
    run(['systemctl','is-active','--quiet','riksora-beta'])
    (snapshot/'rollback-result.json').write_text(json.dumps({'rolledBack':True,'databaseRowsDeleted':False}))
    print('DEMO_ROLLBACK_COMPLETE; SAVED_DATABASE_ROWS_PRESERVED')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    modes=parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--apply-plan')
    modes.add_argument('--rollback-snapshot')
    args = parser.parse_args()
    try:
        need(os.geteuid() == 0, 'OPERATOR_AUTHENTICATION_REQUIRED')
        with open('/run/riksora-demo-upgrade.lock', 'a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if args.apply_plan:
                apply(args.apply_plan)
            else:
                rollback(args.rollback_snapshot)
    except Exception as error:
        print('DEMO_UPGRADE_REFUSED:' + (str(error) if isinstance(error, UpgradeRefusal) else type(error).__name__), file=sys.stderr)
        raise SystemExit(1) from None
