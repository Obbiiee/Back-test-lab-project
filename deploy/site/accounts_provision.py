"""One-time provisioning of the accounts database for the Google-only public API (run by the operator on the VPS; idempotent).

Creates a SEPARATE PostgreSQL 17 cluster (127.0.0.1:54450, scram-sha-256, strong generated passwords kept in ~/.config/riksora-db.env, mode 0600),
roles btl_owner (migrations) and btl_app (runtime, no superuser/bypass/owner membership), runs the migrations and grants ONLY identity, Google and
workspace-metadata permissions. No research, execution, billing or support grants: the public API composition cannot reach those tables.
"""
import os, secrets, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'backend')]
HOME = Path.home()
PG = HOME / 'tools' / 'pg17' / 'bin'
DATA, PORT, ENVF, SECRET = HOME / 'prod' / 'pg', 54450, HOME / '.config' / 'riksora-db.env', HOME / '.config' / 'riksora-auth-secret'


def dsn(user, password, dbname='btl'):
    return f'host=127.0.0.1 port={PORT} dbname={dbname} user={user} password={password}'


def main():
    os.umask(0o077)
    (HOME / 'prod').mkdir(exist_ok=True); (HOME / '.config').mkdir(exist_ok=True)
    if not ENVF.exists():
        ENVF.write_text(''.join(f'{k}={secrets.token_urlsafe(32)}\n' for k in ('PG_SUPER_PASSWORD', 'PG_OWNER_PASSWORD', 'PG_APP_PASSWORD')))
        ENVF.chmod(0o600)
    if not SECRET.exists():
        SECRET.write_text(secrets.token_urlsafe(72)); SECRET.chmod(0o600)
    pw = dict(line.split('=', 1) for line in ENVF.read_text().split() if '=' in line)
    env = dict(os.environ, PATH=f'{PG}:{os.environ["PATH"]}')
    fresh = not DATA.exists()
    if fresh:
        pwfile = HOME / 'prod' / '.pw'; pwfile.write_text(pw['PG_SUPER_PASSWORD']); pwfile.chmod(0o600)
        subprocess.run([str(PG / 'initdb'), '-D', str(DATA), '-U', 'postgres', '--auth=scram-sha-256', '--pwfile', str(pwfile), '-E', 'UTF8'], check=True, env=env, stdout=subprocess.DEVNULL)
        pwfile.unlink()
        with (DATA / 'postgresql.conf').open('a') as conf:
            conf.write(f"\nlisten_addresses='127.0.0.1'\nport={PORT}\nunix_socket_directories='{HOME / 'prod'}'\nmax_connections=60\npassword_encryption='scram-sha-256'\nlog_connections=off\n")
    running = subprocess.run([str(PG / 'pg_ctl'), '-D', str(DATA), 'status'], capture_output=True, env=env).returncode == 0
    if not running:
        subprocess.run([str(PG / 'pg_ctl'), '-D', str(DATA), '-w', '-l', str(HOME / 'prod' / 'pg.log'), 'start'], check=True, env=env, stdout=subprocess.DEVNULL)
    try:
        import psycopg
        from psycopg import sql
        with psycopg.connect(dsn('postgres', pw['PG_SUPER_PASSWORD'], 'postgres'), autocommit=True) as db:
            have = {r[0] for r in db.execute('SELECT rolname FROM pg_roles')}
            if 'btl_owner' not in have:
                db.execute(sql.SQL('CREATE ROLE btl_owner LOGIN PASSWORD {}').format(sql.Literal(pw['PG_OWNER_PASSWORD'])))
            if 'btl_app' not in have:
                db.execute(sql.SQL('CREATE ROLE btl_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD {}').format(sql.Literal(pw['PG_APP_PASSWORD'])))
            if not db.execute("SELECT 1 FROM pg_database WHERE datname='btl'").fetchone():
                db.execute('CREATE DATABASE btl OWNER btl_owner')
        owner = dsn('btl_owner', pw['PG_OWNER_PASSWORD'])
        from infrastructure.database import migrate, grant_identity_runtime
        from identity.google_store import grant_google_runtime
        from deploy.vps.google_staging import grant_workspace_metadata
        migrate(owner)
        grant_identity_runtime(owner, 'btl_app')
        grant_google_runtime(owner, 'btl_app')
        grant_workspace_metadata(owner, 'btl_app')
        print('ACCOUNTS_DATABASE_READY (identity + Google + workspace metadata only)')
    finally:
        if not running:                                   # systemd runs the long-lived server; stop the helper instance
            subprocess.run([str(PG / 'pg_ctl'), '-D', str(DATA), '-m', 'fast', '-w', 'stop'], env=env, stdout=subprocess.DEVNULL)


if __name__ == '__main__':
    main()
