"""Read-only native staging diagnostics. No credentials, IDs or token output.

Run with the installed /opt/riksora-beta/venv/bin/python as an operator. Never
installs, restarts, migrates, grants, restores, or writes files. Owner access
cannot be inferred from an email, DB-owner role or is_superuser flag here.
"""
from pathlib import Path
from hashlib import sha256
import json
import os
import stat
import subprocess


def secret_metadata(path):
    p = Path(path)
    try:
        s = p.lstat()
        return {'exists': True, 'regular': stat.S_ISREG(s.st_mode),
                'root_owned': s.st_uid == 0, 'mode': oct(stat.S_IMODE(s.st_mode)),
                'world_access': bool(s.st_mode & 0o007)}
    except PermissionError:
        return {'readable': False}
    except FileNotFoundError:
        return {'exists': False}


def backup_summary(directory):
    files = sorted(Path(directory).glob('*.dump'), key=lambda p: p.stat().st_mtime)
    out = {'dump_count': len(files), 'latest_hash_matches': False, 'latest_catalog_readable': False}
    if not files:
        return out
    latest = files[-1]
    if latest.is_symlink() or not latest.is_file():
        return out
    sidecar = latest.with_suffix('.sha256')
    if sidecar.is_file() and not sidecar.is_symlink():
        digest = sha256()
        with latest.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024*1024), b''):
                digest.update(chunk)
        out['latest_hash_matches'] = digest.hexdigest() == sidecar.read_text().strip()
    out['latest_bytes'] = latest.stat().st_size
    out['latest_world_access'] = bool(latest.stat().st_mode & 0o007)
    r = subprocess.run(['/usr/lib/postgresql/16/bin/pg_restore', '--list', str(latest)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15, check=False)
    out['latest_catalog_readable'] = r.returncode == 0
    out['restore_drill_performed'] = False
    return out


def database_summary(owner_dsn, app_dsn):
    import psycopg
    from psycopg.conninfo import conninfo_to_dict
    for dsn, user in [(owner_dsn, 'btl_owner'), (app_dsn, 'btl_app')]:
        fields = conninfo_to_dict(dsn)
        if fields.get('host') != '127.0.0.1' or fields.get('port', '5432') != '5432' or fields.get('dbname') != 'riksora_beta' or fields.get('user') != user:
            raise ValueError('Unexpected local database identity')
    options = '-c default_transaction_read_only=on -c statement_timeout=10000 -c lock_timeout=3000'
    with psycopg.connect(owner_dsn, connect_timeout=5, options=options) as db:
        read_only = db.execute('SHOW transaction_read_only').fetchone()[0] == 'on'
        rows = db.execute('SELECT u.is_active,u.is_verified,u.password_enabled,u.is_superuser, '
                          'EXISTS(SELECT 1 FROM btl.google_identities g WHERE g.user_id=u.id) '
                          'FROM btl.users u WHERE lower(u.email)=%s', ('riksoralabs@gmail.com',)).fetchall()
        out = {'read_only': read_only, 'target_user_count': len(rows), 'global_owner_not_inferred': True}
        if len(rows) == 1:
            active, verified, password, superuser, subject = rows[0]
            out.update(active=active, verified=verified, password_enabled=password,
                       google_subject_bound=subject, canonical_superuser_flag=superuser)
        codes = ('GOOGLE_USER_CREATED', 'GOOGLE_IDENTITY_VERIFIED', 'SESSION_CREATED', 'SESSION_REVOKED', 'ALL_SESSIONS_REVOKED')
        out['target_audit_event_counts'] = dict(db.execute(
            'SELECT e.code,count(*) FROM btl.security_events e JOIN btl.users u ON u.id=e.user_id '
            'WHERE lower(u.email)=%s AND e.code=ANY(%s) GROUP BY e.code',
            ('riksoralabs@gmail.com', list(codes))).fetchall())
    with psycopg.connect(app_dsn, connect_timeout=5, options=options) as db:
        flags = db.execute('SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls '
                           'FROM pg_roles WHERE rolname=current_user').fetchone()
        out['runtime_no_privileged_role_flags'] = flags is not None and not any(flags)
        out['runtime_not_owner_member'] = not db.execute("SELECT pg_has_role(current_user,'btl_owner','MEMBER')").fetchone()[0]
        out['runtime_owns_no_application_tables'] = db.execute(
            "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname='btl' AND c.relowner=(SELECT oid FROM pg_roles WHERE rolname=current_user)").fetchone()[0] == 0
    return out


def audit():
    directory = Path('/etc/riksora-beta')
    report = {'mode': 'READ_ONLY_DIAGNOSTICS', 'files': {name: secret_metadata(directory/name)
              for name in ['runtime.json', 'operator.json']}}
    try:
        runtime_meta, operator_meta = report['files']['runtime.json'], report['files']['operator.json']
        if not all(m.get('regular') and m.get('root_owned') and not m.get('world_access') for m in [runtime_meta, operator_meta]) or operator_meta.get('mode') != '0o600':
            raise ValueError('Unsafe secret metadata')
        cfg = json.loads((directory/'runtime.json').read_text())
        owner = json.loads((directory/'operator.json').read_text())
        report['google_configuration_present'] = bool(cfg.get('googleClientId') and cfg.get('googleClientSecret'))
        report['database'] = database_summary(owner['database'], cfg['database'])
    except Exception as error:
        report['database_check_error_type'] = type(error).__name__
    try:
        report['backup'] = backup_summary('/var/backups/riksora-beta')
    except Exception as error:
        report['backup_check_error_type'] = type(error).__name__
    return report


if __name__ == '__main__':
    if os.geteuid() != 0:
        print(json.dumps({'mode': 'READ_ONLY_DIAGNOSTICS', 'operator_privilege_required': True}))
        raise SystemExit(1)
    print(json.dumps(audit(), indent=2))
