"""Opt-in synthetic browser gate. Own cluster only; no target URL/DSN option."""
import argparse
import hashlib
import json
import logging
import os
from pathlib import Path
import secrets
import signal
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time

REPOSITORY = Path(__file__).resolve().parents[2]
VERSION = '1.64.1'
STEPS = ('login_screen', 'login_workspace', 'method', 'session_replay',
         'order_receipt', 'committed_trade_journal_analytics', 'logout_login_resume')


def preflight(repository, tools):
    if os.geteuid() == 0:
        raise ValueError('ORDINARY_USER_REQUIRED')
    for executable in ('node', 'npm', 'openssl'):
        if not shutil.which(executable):
            raise ValueError('QA_EXECUTABLE_REQUIRED')
    frontend = repository/'frontend'
    if frontend.is_symlink() or (frontend/'dist').is_symlink():
        raise ValueError('QA_BUILD_SYMLINK_REFUSED')
    for package in ('playwright', '@playwright/test'):
        path = tools/'node_modules'/package/'package.json'
        if not path.is_file() or json.loads(path.read_text()).get('version') != VERSION:
            raise ValueError('PINNED_PLAYWRIGHT_REQUIRED')


def digest_files(root, paths):
    digest = hashlib.sha256()
    for path in sorted(paths):
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError('QA_INPUT_SYMLINK_REFUSED')
        digest.update(str(path.relative_to(root)).encode()+b'\0')
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def run(tools, browser_cache):
    preflight(REPOSITORY, tools)
    parent = REPOSITORY/'frontend/tests/artifacts'
    if parent.is_symlink():
        raise ValueError('QA_ARTIFACT_SYMLINK_REFUSED')
    parent.mkdir(parents=True, exist_ok=True)
    evidence = Path(tempfile.mkdtemp(prefix='riksora-private-browser-', dir=parent))
    evidence.chmod(0o700)
    report = dict(schemaVersion=1, artifact='RIKSORA-PRIVATE-SYNTHETIC-BROWSER-GATE-1', status='FAIL',
                  classification='SYNTHETIC_QA_NOT_HISTORICAL_OR_PRODUCTION_ACCEPTANCE',
                  steps=[], progress=[], certificate='LOCAL_SELF_SIGNED_VERIFICATION_BYPASSED',
                  apiTransport='UNCHANGED_REAL_BACKEND_RESPONSES_FORWARDED', cleanup=False)
    report['qaHarnessSha256'] = digest_files(REPOSITORY, [Path(__file__),
        Path(__file__).with_name('riksora-browser-journey.mjs'),
        REPOSITORY/'deploy/vps/tests/run_private_pg.py'])
    report['playwrightVersion'] = VERSION
    began = time.monotonic()
    try:
        sys.path[:0] = [str(REPOSITORY), str(REPOSITORY/'backend')]
        from deploy.vps.tests.run_private_pg import private_postgres
        with private_postgres() as (_, environment):
            with (evidence/'build.log').open('x') as log:
                subprocess.run(['npm', 'run', 'build'], cwd=REPOSITORY/'frontend',
                               env=environment, check=True, stdout=log, stderr=log, timeout=120)
            frontend = REPOSITORY/'frontend'
            inputs = [p for p in (frontend/'src').rglob('*') if p.is_file()]
            inputs += [frontend/n for n in ('package.json', 'package-lock.json', 'vite.config.js', 'index.html')]
            report['frontendInputSha256'] = digest_files(frontend, inputs)
            report['buildSha256'] = digest_files(frontend/'dist',
                [p for p in (frontend/'dist').rglob('*') if p.is_file()])
            report['sourceCommit'] = subprocess.check_output(
                ['git', 'rev-parse', 'HEAD'], cwd=REPOSITORY, text=True).strip()
            report['workingTreeDirty'] = bool(subprocess.check_output(
                ['git', 'status', '--porcelain'], cwd=REPOSITORY))
            run_browser(environment, tools, browser_cache, evidence, report)
        report['cleanup'] = True
        report['status'] = 'PASS'
    except Exception as error:
        # Detailed browser/build logs remain inside the private evidence folder.
        report['failureType'] = type(error).__name__
        message = error.args[0] if error.args else None
        if isinstance(message, str) and message.isascii() and message.isidentifier():
            report['failureCode'] = message
    finally:
        report['seconds'] = str(time.monotonic()-began)
        (evidence/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(dict(status=report['status'], evidence=str(evidence/'report.json'),
                          classification=report['classification'], cleanup=report['cleanup'],
                          steps=report['steps'], progress=report['progress'],
                          failureType=report.get('failureType'),
                          failureCode=report.get('failureCode'),
                          workerFailureCode=report.get('workerFailureCode'),
                          failurePhase=report.get('failurePhase'),
                          browserFailureType=report.get('browserFailureType'),
                          apiTrace=report.get('apiTrace', []))))
    return 0 if report['status'] == 'PASS' else 1


def run_browser(environment, tools, browser_cache, evidence, report):
    import psycopg
    from psycopg import sql
    from psycopg.conninfo import make_conninfo, conninfo_to_dict
    import uvicorn
    from starlette.staticfiles import StaticFiles
    from deploy.vps.ops import migrate_and_grant
    from deploy.vps.google_staging import grant_google_demo_runtime
    from cloud.app import create_app
    from tests.test_identity import RecordingDelivery
    dsn = environment['BTL_TEST_DATABASE_URL']
    class SafeWorkerFailureCapture(logging.Handler):
        def emit(self, record):
            message = record.getMessage()
            marker = 'error_code='
            if 'research_job_failed ' in message and marker in message:
                code = message.split(marker, 1)[1].split()[0]
                if code.isascii() and code.isupper() and all(c.isalnum() or c == '_' for c in code):
                    report['workerFailureCode'] = code
    queue_logger = logging.getLogger('cloud.queue')
    capture = SafeWorkerFailureCapture()
    prior_level = queue_logger.level
    queue_logger.setLevel(logging.WARNING)
    queue_logger.addHandler(capture)
    password = secrets.token_urlsafe(32)
    with psycopg.connect(dsn) as db:
        db.execute('CREATE ROLE btl_owner NOLOGIN')
        db.execute(sql.SQL('CREATE ROLE btl_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE '
                           'NOREPLICATION NOBYPASSRLS PASSWORD {}').format(sql.Literal(password)))
    # Exercise the same restricted runtime grants as a staging migration,
    # including existing Product V1 read-model and execution tables.
    migrate_and_grant(dsn)
    grant_google_demo_runtime(dsn)
    runtime = make_conninfo(**{**conninfo_to_dict(dsn), 'user': 'btl_app', 'password': password})
    with psycopg.connect(runtime) as db:
        report['runtimeMethodProjectionSelect'] = db.execute(
            "SELECT has_table_privilege(current_user,'btl.tick_method_metric_projections','SELECT')"
        ).fetchone()[0]
        if not report['runtimeMethodProjectionSelect']:
            raise PermissionError('QA_METHOD_PROJECTION_GRANT_MISSING')
    delivery = RecordingDelivery()
    app = create_app(runtime, secrets.token_urlsafe(48), delivery, rate_limit=1200,
                     sandbox_reset_timezone='UTC')
    nonce = secrets.token_hex(32)

    @app.get('/__qa/browser-proof/'+nonce)
    def proof():
        return dict(purpose='RIKSORA_EXCLUSIVE_SYNTHETIC_QA', nonce=nonce)

    app.mount('/', StaticFiles(directory=REPOSITORY/'frontend/dist', html=True))
    server = None
    thread = None
    sock = socket.socket()
    # Keep TLS key and certificate outside retained evidence.
    with tempfile.TemporaryDirectory(prefix='riksora-browser-tls-') as tls:
        tls = Path(tls)
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
                        '-keyout', str(tls/'key.pem'), '-out', str(tls/'cert.pem'), '-days', '1',
                        '-subj', '/CN=localhost', '-addext', 'subjectAltName=IP:127.0.0.1'],
                       env=environment, check=True, capture_output=True, timeout=30)
        try:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
            server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port,
                ssl_certfile=str(tls/'cert.pem'), ssl_keyfile=str(tls/'key.pem'),
                proxy_headers=False, access_log=False, log_level='critical'))
            thread = threading.Thread(target=server.run, kwargs={'sockets': [sock]}, daemon=True)
            thread.start()
            for _ in range(200):
                if server.started:
                    break
                if not thread.is_alive():
                    raise RuntimeError('QA_SERVER_FAILED')
                time.sleep(.05)
            if not server.started:
                raise RuntimeError('QA_SERVER_TIMEOUT')
            email = 'browser-'+secrets.token_hex(8)+'@example.com'
            config = dict(url=f'https://127.0.0.1:{port}/?page=account', nonce=nonce,
                          email=email, password='Authored QA passphrase 2026 only',
                          tools=str(tools), evidence=str(evidence))
            child_environment = {k: v for k, v in environment.items() if not k.startswith(('PG', 'BTL_'))}
            child_environment['PLAYWRIGHT_BROWSERS_PATH'] = str(browser_cache)
            with (evidence/'browser.log').open('x') as log:
                process = subprocess.Popen(['node', str(Path(__file__).with_name('riksora-browser-journey.mjs'))],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log,
                    text=True, env=child_environment, start_new_session=True)
                def terminate():
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                timer = threading.Timer(240, terminate)
                timer.start()
                complete = False
                try:
                    process.stdin.write(json.dumps(config)+'\n')
                    process.stdin.flush()
                    for line in process.stdout:
                        # The bounded API trace can include up to 64 sanitized
                        # method/path/status tuples; keep a hard 16 KiB ceiling.
                        if len(line) > 16384:
                            raise ValueError('QA_PROTOCOL_LIMIT')
                        item = json.loads(line)
                        if item.get('need') == 'verification' and item.get('email') == email:
                            process.stdin.write(json.dumps(dict(token=delivery.token(email, 'verification')))+'\n')
                            process.stdin.flush()
                        elif item.get('need') == 'recovery' and item.get('email') == email:
                            process.stdin.write(json.dumps(dict(token=delivery.token(email, 'recovery')))+'\n')
                            process.stdin.flush()
                        elif item.get('step') in STEPS:
                            report['steps'].append(item['step'])
                        elif isinstance(item.get('progress'), str) and item['progress'].isidentifier():
                            report['progress'].append(item['progress'])
                        elif (isinstance(item.get('failurePhase'), str) and
                              item['failurePhase'].isidentifier() and
                              isinstance(item.get('failureType'), str) and
                              item['failureType'].isidentifier()):
                            report['failurePhase'] = item['failurePhase']
                            report['browserFailureType'] = item['failureType']
                            trace = item.get('apiTrace', [])
                            if isinstance(trace, list) and len(trace) <= 64:
                                report['apiTrace'] = [entry for entry in trace if
                                    isinstance(entry, dict) and
                                    entry.get('method') in ('GET', 'POST', 'PUT', 'PATCH', 'DELETE') and
                                    isinstance(entry.get('path'), str) and len(entry['path']) <= 240 and
                                    type(entry.get('status')) is int and 100 <= entry['status'] <= 599 and
                                    (entry.get('state') is None or entry.get('state') in
                                     ('QUEUED','RUNNING','SUCCEEDED','FAILED','CANCELLED','RECONCILE_REQUIRED')) and
                                    (entry.get('code') is None or
                                     isinstance(entry.get('code'), str) and
                                     entry['code'].isascii() and entry['code'].isupper() and
                                     all(c.isalnum() or c == '_' for c in entry['code']))]
                        elif item.get('complete') is True:
                            report['browserVersion'] = item['browserVersion']
                            complete = True
                        else:
                            raise ValueError('QA_PROTOCOL_REFUSED')
                    code = process.wait(timeout=10)
                    if code or not complete or tuple(report['steps']) != STEPS:
                        raise RuntimeError('BROWSER_ACCEPTANCE_FAILED')
                finally:
                    timer.cancel()
                    if process.poll() is None or not complete:
                        terminate()
                        process.wait(timeout=10)
                    process.stdin.close()
                    process.stdout.close()
        finally:
            if server:
                server.should_exit = True
            if thread:
                thread.join(timeout=20)
                if thread.is_alive():
                    raise RuntimeError('QA_HTTP_CLEANUP_FAILED')
            sock.close()
            queue_logger.removeHandler(capture)
            queue_logger.setLevel(prior_level)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tools', type=Path, default=REPOSITORY/'frontend/tests/browser-tools')
    parser.add_argument('--browser-cache', type=Path)
    args = parser.parse_args()
    try:
        raise SystemExit(run(args.tools.resolve(), (args.browser_cache or args.tools/'browsers').resolve()))
    except Exception as error:
        print('BROWSER_GATE_REFUSED:'+type(error).__name__, file=sys.stderr)
        raise SystemExit(1) from None
