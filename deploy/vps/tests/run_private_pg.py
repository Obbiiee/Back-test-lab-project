"""Run one native gate in a newly owned Unix-socket-only PostgreSQL cluster.

Never accepts a DSN or uses an existing cluster. Requires installed PostgreSQL16
tools and the repository Python dependencies. No sudo/service operations.
"""
import argparse
from contextlib import contextmanager
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile

GROUPS = {
    'functional': ['tests.test_functional_journey'],
    'workspace': ['deploy.vps.tests.test_google_staging'],
    'upgrade': ['deploy.vps.tests.test_native_upgrade'],
    'regression': ['tests.test_google_identity', 'tests.test_workspace',
                   'tests.test_cloud_research', 'tests.test_sandbox_v2',
                   'tests.test_local_reliability'],
}


@contextmanager
def private_postgres(*, keep=False):
    if os.geteuid() == 0:
        raise ValueError('RUN_AS_ORDINARY_USER_WITHOUT_SUDO')
    repository = Path(__file__).resolve().parents[3]
    binaries = Path('/usr/lib/postgresql/16/bin')
    for name in ('initdb', 'pg_ctl', 'pg_dump', 'pg_restore'):
        if not (binaries/name).is_file():
            raise ValueError('POSTGRESQL16_TOOLS_REQUIRED')
    root = Path(tempfile.mkdtemp(prefix='riksora-exclusive-qa-'))
    root.chmod(0o700)
    socket = root/'socket'
    socket.mkdir(mode=0o700)
    password = root/'password'
    descriptor = os.open(password, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    value = secrets.token_urlsafe(32)
    with os.fdopen(descriptor, 'w') as stream:
        stream.write(value)
    environment = {k: v for k, v in os.environ.items()
                   if not k.startswith(('PG', 'BTL_'))}
    environment.update(PYTHONDONTWRITEBYTECODE='1', PYTHONPATH=str(repository/'backend'))
    data = root/'data'
    started = False
    def pg(args):
        # Logs/errors remain private; do not accidentally print DSNs or SQL data.
        return subprocess.run(args, env=environment, check=True, timeout=60,
                              stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        pg([str(binaries/'initdb'), '-D', str(data), '-U', 'qa_root',
            '--pwfile', str(password), '--auth', 'scram-sha-256',
            '--no-locale', '--encoding=UTF8'])
        pg([str(binaries/'pg_ctl'), '-D', str(data), '-l', str(root/'server.log'),
            '-o', f"-c listen_addresses='' -k {socket} -p 55439 "
                  '-c shared_buffers=32MB -c max_connections=50', '-w', 'start'])
        started = True
        from psycopg.conninfo import make_conninfo
        environment.update(BTL_TEST_DATABASE_URL=make_conninfo(
            host=str(socket), port=55439, dbname='postgres', user='qa_root', password=value),
            BTL_PG_BIN=str(binaries))
        yield repository, environment
    finally:
        stopped = not started and not (data/'postmaster.pid').exists()
        if not stopped:
            pg([str(binaries/'pg_ctl'), '-D', str(data), '-m', 'fast', '-w', 'stop'])
            stopped = True
        if stopped and not keep:
            shutil.rmtree(root)
        print('EXCLUSIVE_QA_STOPPED; ' + ('PRIVATE_FILES_RETAINED' if keep else 'OWN_FIXTURES_REMOVED'))


def run(group, *, keep=False):
    with private_postgres(keep=keep) as (repository, environment):
        return subprocess.run([sys.executable, '-B', '-m', 'unittest', *GROUPS[group], '-q'],
                              env=environment, cwd=repository, timeout=900).returncode


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--group', choices=GROUPS, required=True)
    parser.add_argument('--keep', action='store_true', help='retain only this private QA cluster after stopping')
    args = parser.parse_args()
    try:
        raise SystemExit(run(args.group, keep=args.keep))
    except Exception as error:
        print('EXCLUSIVE_QA_REFUSED:' + type(error).__name__, file=sys.stderr)
        raise SystemExit(1) from None
