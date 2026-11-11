"""Opt-in synthetic browser gate. Own cluster only; no target URL/DSN option."""
import argparse
from datetime import timedelta
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import queue as thread_queue
import re
import secrets
import signal
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from unittest.mock import patch

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


def sanitize_api_event(item):
    """Validate the browser's bounded API telemetry frame for the parent protocol."""
    event = item.get('apiEvent') if type(item) is dict else None
    if type(event) is not dict:
        return None
    method, path, status, duration = (event.get('method'), event.get('path'),
                                      event.get('status'), event.get('durationMs'))
    code = event.get('code')
    if (method not in ('GET', 'POST', 'PUT', 'PATCH', 'DELETE') or
            not isinstance(path, str) or not path.startswith('/api/v1/') or
            len(path) > 240 or '?' in path or '\n' in path or '\r' in path or
            type(status) is not int or not 100 <= status <= 599 or
            type(duration) not in (int, float) or not math.isfinite(duration) or
            duration < 0 or duration > 120000 or
            (code is not None and (not isinstance(code, str) or len(code) > 81 or
             not code.isascii() or not code.isupper() or
             not all(char.isalnum() or char == '_' for char in code)))):
        return None
    # Store only route/status/timing fields; response bodies and identity data
    # never cross the browser-parent QA protocol.
    return {'method': method, 'path': path, 'status': status,
            'code': code, 'durationMs': duration}


def _queue_job_timeline(dsn):
    """Private-QA-only durable queue timeline with no raw account/job/session IDs."""
    import json
    import psycopg
    from psycopg.rows import dict_row
    result=[]
    with psycopg.connect(dsn) as db:
        db.row_factory=dict_row
        rows=db.execute("""
            SELECT j.id::text AS job_id,j.actor_id::text AS actor_id,u.email,j.workspace_id,
                   j.operation,j.input,j.state,j.attempts,j.created_at,j.finished_at,
                   j.queue_metrics,j.worker_metrics
            FROM btl.research_jobs j JOIN btl.users u ON u.id=j.actor_id
            ORDER BY j.created_at,j.id
        """).fetchall()
        for row in rows:
            try:
                payload=json.loads(bytes(row['input']))
            except (TypeError,ValueError,UnicodeError):
                payload={}
            args=payload.get('args') if type(payload) is dict else None
            session_id=args[0] if type(args) is list and args and type(args[0]) is str else None
            request=args[1] if type(args) is list and len(args)>1 and type(args[1]) is dict else {}
            expected=request.get('expectedRevision')
            session_revision=None
            if session_id and row['operation'] in ('replay','replay_to'):
                stored=db.execute("SELECT revision FROM btl.tick_sessions WHERE workspace_id=%s AND session_id=%s",
                                  (str(row['workspace_id']),session_id)).fetchone()
                session_revision=stored['revision'] if stored else None
            queue_metrics=json.loads(bytes(row['queue_metrics'])) if row['queue_metrics'] else {}
            worker_metrics=json.loads(bytes(row['worker_metrics'])) if row['worker_metrics'] else {}
            wait_us=queue_metrics.get('waitMicroseconds')
            claimed_at=row['created_at']+timedelta(microseconds=wait_us) if type(wait_us) is int else None
            worker_wall=(worker_metrics.get('wallNs') if type(worker_metrics.get('wallNs')) is int else None)
            result.append({
                'jobDigest':hashlib.sha256(row['job_id'].encode()).hexdigest()[:20],
                'accountDigest':hashlib.sha256(row['email'].encode()).hexdigest(),
                'operation':row['operation'],'state':row['state'],'attempts':row['attempts'],
                'sessionDigest':hashlib.sha256(session_id.encode()).hexdigest()[:20] if session_id else None,
                'expectedRevision':expected if type(expected) is int else None,
                'storedRevisionAtSnapshot':session_revision,
                'createdAt':row['created_at'].isoformat(),
                'firstWorkerClaimAt':claimed_at.isoformat() if claimed_at else None,
                'finishedAt':row['finished_at'].isoformat() if row['finished_at'] else None,
                'queueWaitMicroseconds':wait_us,'workerWallNs':worker_wall,
                'workerCpuNs':worker_metrics.get('cpuNs') if type(worker_metrics.get('cpuNs')) is int else None,
                'workerPeakRssBytes':worker_metrics.get('processPeakRssBytes') if type(worker_metrics.get('processPeakRssBytes')) is int else None,
                'workerReadBytesDelta':worker_metrics.get('readBytesDelta') if type(worker_metrics.get('readBytesDelta')) is int else None,
                'workerWriteBytesDelta':worker_metrics.get('writeBytesDelta') if type(worker_metrics.get('writeBytesDelta')) is int else None,
            })
    return result


def run(tools, browser_cache, cohort_size=1, capacity_test=False, worker_count=1,
        auth_ip_limit=30):
    preflight(REPOSITORY, tools)
    parent = REPOSITORY/'frontend/tests/artifacts'
    if parent.is_symlink():
        raise ValueError('QA_ARTIFACT_SYMLINK_REFUSED')
    parent.mkdir(parents=True, exist_ok=True)
    evidence = Path(tempfile.mkdtemp(prefix='riksora-private-browser-', dir=parent))
    evidence.chmod(0o700)
    report = dict(schemaVersion=1, artifact='RIKSORA-PRIVATE-SYNTHETIC-BROWSER-GATE-1', status='FAIL',
                  classification='SYNTHETIC_QA_NOT_HISTORICAL_OR_PRODUCTION_ACCEPTANCE',
                  steps=[], progress=[], cohortSize=cohort_size, capacityTest=capacity_test,
                  authIpRateLimit=auth_ip_limit,
                  certificate='LOCAL_SELF_SIGNED_VERIFICATION_BYPASSED',
                  apiTransport='UNCHANGED_REAL_BACKEND_RESPONSES_FORWARDED', cleanup=False)
    report['qaHarnessSha256'] = digest_files(REPOSITORY, [Path(__file__),
        Path(__file__).with_name('riksora-browser-journey.mjs'),
        REPOSITORY/'deploy/vps/tests/run_private_pg.py'])
    report['playwrightVersion'] = VERSION
    began = time.monotonic()
    qa_root = None
    try:
        sys.path[:0] = [str(REPOSITORY), str(REPOSITORY/'backend')]
        from deploy.vps.tests.run_private_pg import private_postgres
        with private_postgres() as (_, environment):
            qa_root = Path(environment['BTL_QA_CLUSTER_ROOT'])
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
            run_browser(environment, tools, browser_cache, evidence, report, cohort_size,
                        capacity_test, worker_count, auth_ip_limit)
        report['cleanup'] = True
        report['status'] = 'PASS'
    except Exception as error:
        # Detailed browser/build logs remain inside the private evidence folder.
        report['failureTraceback'] = traceback.format_exc()
        report['failureType'] = type(error).__name__
        message = error.args[0] if error.args else None
        if isinstance(message, str) and message.isascii() and message.isidentifier():
            report['failureCode'] = message
    finally:
        if qa_root is not None:
            report['cleanup'] = not qa_root.exists()
        report['seconds'] = str(time.monotonic()-began)
        (evidence/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(dict(status=report['status'], evidence=str(evidence/'report.json'),
                          classification=report['classification'], cleanup=report['cleanup'],
                          steps=report['steps'], progress=report['progress'],
                          failureType=report.get('failureType'),
                          failureCode=report.get('failureCode'),
                          workerFailureCode=report.get('workerFailureCode'),
                          workerFailureOperation=report.get('workerFailureOperation'),
                          workerFailures=report.get('workerFailures', []),
                          failurePhase=report.get('failurePhase'),
                          syntheticFixture=report.get('syntheticFixture'),
                          browserFailureType=report.get('browserFailureType'),
                          browserFailureMessage=report.get('browserFailureMessage'),
                          screenState=report.get('screenState', []),
                          browserDiagnostics=report.get('browserDiagnostics'),
                          pageErrorCount=report.get('pageErrorCount'),
                          apiTrace=report.get('apiTrace', []),
                          capacity=report.get('capacity'),cohortFailure=report.get('cohortFailure'))))
    return 0 if report['status'] == 'PASS' else 1


def run_browser(environment, tools, browser_cache, evidence, report, cohort_size=1,
                capacity_test=False, worker_count=1, auth_ip_limit=30):
    import psycopg
    from psycopg import sql
    from psycopg.conninfo import make_conninfo, conninfo_to_dict
    import uvicorn
    from starlette.staticfiles import StaticFiles
    from deploy.vps.ops import migrate_and_grant
    from deploy.vps.google_staging import grant_google_demo_runtime
    from cloud.app import create_app
    from cloud import queue as research_queue
    from tests.test_identity import RecordingDelivery
    from contracts.canonical import canonical_bytes
    from execution.research_fixture import research_provider
    from market_data.monthly_parquet import write_monthly_parquet
    if capacity_test:
        if worker_count not in (1, 2):
            raise ValueError('QA_WORKER_COUNT_REFUSED')
        research_queue.WORKERS = worker_count
        report['workerCount'] = worker_count
    dsn = environment['BTL_TEST_DATABASE_URL']
    class SafeWorkerFailureCapture(logging.Handler):
        def emit(self, record):
            message = record.getMessage()
            marker = 'error_code='
            if 'research_job_failed ' in message and marker in message:
                code = message.split(marker, 1)[1].split()[0]
                if code.isascii() and code.isupper() and all(c.isalnum() or c == '_' for c in code):
                    report['workerFailureCode'] = code
                operation_marker = 'operation='
                operation=''
                if operation_marker in message:
                    operation = message.split(operation_marker, 1)[1].split()[0]
                    # Keep only the bounded operation label; never retain job,
                    # actor, workspace, or other values from the log record.
                    if operation in ('workspace', 'bootstrap', 'replay', 'replay_to', 'create_session',
                                     'apply', 'journal', 'method_analytics', 'session_page'):
                        report['workerFailureOperation'] = operation
                job_marker='job_id='
                job_id=message.split(job_marker,1)[1].split()[0] if job_marker in message else ''
                if re.fullmatch(r'[a-f0-9-]{36}',job_id,re.IGNORECASE):
                    item={'jobDigest':hashlib.sha256(job_id.encode()).hexdigest()[:20],
                          'errorCode':code if code.isascii() and code.isupper() and all(c.isalnum() or c=='_' for c in code) else None,
                          'atUnixMs':int(time.time()*1000)}
                    if operation in ('workspace','bootstrap','replay','replay_to','create_session','apply','journal','method_analytics','session_page'):
                        item['operation']=operation
                    try:
                        with psycopg.connect(dsn,connect_timeout=2) as diagnostic_db:
                            joined=diagnostic_db.execute("""
                                SELECT j.actor_id::text,u.email,j.workspace_id,j.input
                                FROM btl.research_jobs j JOIN btl.users u ON u.id=j.actor_id WHERE j.id=%s
                            """,(job_id,)).fetchone()
                            if joined:
                                payload=json.loads(bytes(joined[3]));args=payload.get('args',[])
                                session_id=args[0] if args and type(args[0]) is str else None
                                request=args[1] if len(args)>1 and type(args[1]) is dict else {}
                                item['accountDigest']=hashlib.sha256(joined[1].encode()).hexdigest()
                                if session_id:
                                    item['sessionDigest']=hashlib.sha256(session_id.encode()).hexdigest()[:20]
                                    current=diagnostic_db.execute(
                                        'SELECT revision FROM btl.tick_sessions WHERE workspace_id=%s AND session_id=%s',
                                        (str(joined[2]),session_id)).fetchone()
                                    item['storedRevisionAtFailure']=current[0] if current else None
                                expected=request.get('expectedRevision')
                                item['expectedRevision']=expected if type(expected) is int else None
                    except Exception as diagnostic_error:
                        item['diagnosticReadFailure']=type(diagnostic_error).__name__
                    report.setdefault('workerFailures',[]).append(item)
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
    app = create_app(runtime, secrets.token_urlsafe(48), delivery,
                     rate_limit=auth_ip_limit if capacity_test else 1200,
                     sandbox_reset_timezone='UTC')
    if capacity_test:
        app.state.qa_timing = True
        report['qaTimingEnabled'] = True
    # Session creation and replay are backed by the same authored tick fixture
    # used by the PostgreSQL queue integration tests. The executor receives a
    # pinned local Parquet manifest; no API response is mocked or substituted.
    monthly_temp = tempfile.TemporaryDirectory(prefix='riksora-browser-ticks-')
    monthly_root = Path(monthly_temp.name)/'dataset'
    source = research_provider()
    source_manifest = source.describe(source.dataset_id, source.dataset_version)
    events, token = [], None
    while True:
        page = source.read_page(source.dataset_id, source.dataset_version, token, 64)
        events.extend(page['events'])
        if page['endOfDataset']:
            break
        token = page['nextToken']
    monthly_manifest = write_monthly_parquet(str(monthly_root), iter(events),
        source_manifest,
        expected_version=source.dataset_version, row_group_size=128)
    tick_hash = hashlib.sha256()
    for event in events:
        tick_hash.update(canonical_bytes(event))
        tick_hash.update(b'\n')
    report['syntheticFixture'] = {
        'label': 'Synthetic/Test — authored deterministic ticks; not market history',
        'datasetId': source.dataset_id,
        'datasetVersion': source.dataset_version,
        'sourceManifestSha256': source.dataset_version,
        'canonicalTickRows': len(events),
        'canonicalTickRowsSha256': tick_hash.hexdigest(),
        'parquetManifestSha256': monthly_manifest['manifestHash'],
        'parquetBytes': sum(path.stat().st_size for path in monthly_root.rglob('*') if path.is_file()),
    }
    synthetic_pin = {
        'BTL_QA_SYNTHETIC_MONTHLY_ENABLE': '1',
        'BTL_QA_SYNTHETIC_MONTHLY_ROOT': str(monthly_root),
        'BTL_QA_SYNTHETIC_MONTHLY_DATASET_ID': source.dataset_id,
        'BTL_QA_SYNTHETIC_MONTHLY_DATASET_VERSION': source.dataset_version,
        'BTL_QA_SYNTHETIC_MONTHLY_MANIFEST_SHA256': monthly_manifest['manifestHash'],
        'BTL_TICK_SESSION_STORAGE_FORMAT': 'compact-v1',
    }
    previous_synthetic_env = {key: os.environ.get(key) for key in synthetic_pin}
    os.environ.update(synthetic_pin)
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
                proxy_headers=False, access_log=False, log_level='info'))
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
            if capacity_test:
                run_browser_cohort(environment, tools, browser_cache, evidence, report,
                                   url=f'https://127.0.0.1:{port}/?page=account', nonce=nonce,
                                   delivery=delivery, cohort_size=cohort_size)
                return
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
                        # The bounded API trace can include up to 128 sanitized
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
                        elif 'apiEvent' in item:
                            event = sanitize_api_event(item)
                            if event is None:
                                raise ValueError('QA_PROTOCOL_REFUSED')
                            api_trace = report.setdefault('apiTrace', [])
                            if len(api_trace) < 128:
                                api_trace.append(event)
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
                            failure_message = item.get('browserFailureMessage')
                            if (isinstance(failure_message, str) and len(failure_message) <= 300 and
                                    failure_message.isascii()):
                                report['browserFailureMessage'] = failure_message
                            screen_state = item.get('screenState', [])
                            allowed_states = {'NO_ORDERS','FILTERED_EMPTY','JOURNAL_ERROR','JOURNAL_LOADING',
                                              'CHOOSE_SESSION','SESSION_MISSING','ANALYTICS_ERROR',
                                              'ANALYTICS_LOADING','ANALYTICS_UNAVAILABLE'}
                            if isinstance(screen_state, list) and len(screen_state) <= 8 and all(
                                    state in allowed_states for state in screen_state):
                                report['screenState'] = screen_state
                            diagnostics = item.get('browserDiagnostics')
                            if (isinstance(diagnostics, dict) and
                                    diagnostics.get('routeScreen') in ('account','methods','method','method-new',
                                        'sessions','session','session-new','analytics','journal','catalog','help','replay',None) and
                                    type(diagnostics.get('journalLists')) is int and 0 <= diagnostics['journalLists'] <= 10 and
                                    type(diagnostics.get('journalRows')) is int and 0 <= diagnostics['journalRows'] <= 128 and
                                    diagnostics.get('journalError') in ('JOURNAL_SCHEMA','JOURNAL_CURSOR',
                                        'WORKSPACE_SCHEMA','BACKEND_REFUSAL','OTHER','NONE','UNAVAILABLE') and
                                    type(item.get('pageErrorCount')) is int and 0 <= item['pageErrorCount'] <= 32):
                                report['browserDiagnostics'] = diagnostics
                                report['pageErrorCount'] = item['pageErrorCount']
                            trace = item.get('apiTrace', [])
                            if isinstance(trace, list) and len(trace) <= 128:
                                report['apiTrace'] = [entry for entry in trace if
                                    isinstance(entry, dict) and
                                    entry.get('method') in ('GET', 'POST', 'PUT', 'PATCH', 'DELETE') and
                                    isinstance(entry.get('path'), str) and len(entry['path']) <= 240 and
                                    type(entry.get('status')) is int and 100 <= entry['status'] <= 599 and
                                    (entry.get('rows') is None or type(entry.get('rows')) is int and 0 <= entry['rows'] <= 128) and
                                    (entry.get('journalPage') is None or isinstance(entry.get('journalPage'), dict) and
                                     entry['journalPage'].get('artifact') in ('BTL-TICK-JOURNAL-PAGE-1','OTHER') and
                                     (entry['journalPage'].get('schemaVersion') is None or type(entry['journalPage']['schemaVersion']) is int and 0 <= entry['journalPage']['schemaVersion'] <= 10) and
                                     all(type(entry['journalPage'].get(key)) is bool for key in ('hasNotes','hasTotalOrders','hasComplete','paginationValid'))) and
                                    (entry.get('state') is None or entry.get('state') in
                                     ('QUEUED','RUNNING','SUCCEEDED','FAILED','CANCELLED','RECONCILE_REQUIRED')) and
                                    (entry.get('code') is None or
                                     isinstance(entry.get('code'), str) and
                                     entry['code'].isascii() and entry['code'].isupper() and
                                     all(c.isalnum() or c == '_' for c in entry['code']))]
                            failures = item.get('requestFailures', [])
                            if isinstance(failures, list) and len(failures) <= 32:
                                report['requestFailures'] = [entry for entry in failures if
                                    isinstance(entry, dict) and
                                    entry.get('method') in ('GET', 'POST', 'PUT', 'PATCH', 'DELETE') and
                                    isinstance(entry.get('path'), str) and len(entry['path']) <= 240 and
                                    (entry.get('error') == 'NETWORK_ERROR' or
                                     isinstance(entry.get('error'), str) and
                                     entry['error'].startswith('net::ERR_') and
                                     all(c.isupper() or c.isdigit() or c in ':_' for c in entry['error']))]
                        elif item.get('complete') is True:
                            report['browserVersion'] = item['browserVersion']
                            complete = True
                            break
                        else:
                            raise ValueError('QA_PROTOCOL_REFUSED')
                    if complete:
                        # The browser script emits completion only after every
                        # user journey assertion passed. Own process-group cleanup
                        # here so a stuck Chromium shutdown cannot erase that proof.
                        report['cohortResults'] = [dict(user=1, status='PASS',
                            apiTrace=report.get('apiTrace', []), pageErrorCount=item.get('pageErrorCount', 0),
                            failedRequests=item.get('failedRequests', 0), steps=item.get('steps', []))]
                        terminate()
                        process.wait(timeout=10)
                    else:
                        code = process.wait(timeout=10)
                    if not complete or tuple(report['steps']) != STEPS:
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
            for key, value in previous_synthetic_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
            monthly_temp.cleanup()


def _proc_snapshot(generator_roots, cgroup):
    """Bounded scope-only snapshot; RSS sums are explicitly not PSS."""
    result = {'generatorRssBytes': 0, 'generatorCpuTicks': 0,
              'serviceRssBytes': 0, 'serviceCpuTicks': 0,
              'postgresRssBytes': 0, 'postgresCpuTicks': 0,
              'generatorProcesses': 0, 'serviceProcesses': 0, 'postgresProcesses': 0}
    page_size = os.sysconf('SC_PAGE_SIZE')
    try:
        scope_pids={int(value) for value in (cgroup/'cgroup.procs').read_text().split()}
    except (OSError,ValueError) as error:
        raise RuntimeError('CAPACITY_CGROUP_PROCESS_LIST_UNAVAILABLE') from error
    process_rows={}
    for pid in scope_pids:
        entry=Path('/proc')/str(pid)
        try:
            raw = (entry/'stat').read_text()
            close = raw.rfind(')')
            fields = raw[close+2:].split()
            process_rows[pid]=(int(fields[1]),(entry/'comm').read_text().strip(),
                               int(fields[11])+int(fields[12]),max(0,int(fields[21]))*page_size)
        except (FileNotFoundError, PermissionError, ProcessLookupError, ValueError, IndexError):
            continue
    generator_pids=set(generator_roots)
    changed=True
    while changed:
        changed=False
        for pid,(parent,_name,_cpu,_rss) in process_rows.items():
            if parent in generator_pids and pid not in generator_pids:
                generator_pids.add(pid)
                changed=True
    for pid,(_parent,name,cpu_ticks,rss_bytes) in process_rows.items():
        if pid in generator_pids:
            prefix = 'generator'
        elif name == 'postgres':
            prefix = 'postgres'
        else:
            prefix = 'service'
        result[prefix+'RssBytes'] += rss_bytes
        result[prefix+'CpuTicks'] += cpu_ticks
        result[prefix+'Processes'] += 1
    return result


def _system_resources():
    memory = {}
    for line in Path('/proc/meminfo').read_text().splitlines():
        key, _, tail = line.partition(':')
        if key in ('MemAvailable', 'SwapTotal', 'SwapFree'):
            memory[key] = int(tail.strip().split()[0])*1024
    cgroup_relative = next((line.split(':', 2)[2] for line in
                            Path('/proc/self/cgroup').read_text().splitlines()
                            if line.startswith('0::')), None)
    cgroup = Path('/sys/fs/cgroup')/cgroup_relative.lstrip('/') if cgroup_relative else None
    cgroup_sample = {}
    if cgroup and cgroup.is_dir():
        for filename, key in (('memory.current','memoryCurrentBytes'),
                              ('memory.peak','memoryPeakBytes'),
                              ('pids.current','tasksCurrent')):
            try:
                cgroup_sample[key] = int((cgroup/filename).read_text().strip())
            except (FileNotFoundError, ValueError, PermissionError):
                pass
        try:
            cpu = {}
            for line in (cgroup/'cpu.stat').read_text().splitlines():
                name, value = line.split()
                cpu[name] = int(value)
            cgroup_sample['cpuUsageUsec'] = cpu.get('usage_usec')
            cgroup_sample['cpuThrottledUsec'] = cpu.get('throttled_usec')
        except (FileNotFoundError, ValueError, PermissionError):
            pass
        try:
            cgroup_sample['memoryMaxBytes']=int((cgroup/'memory.max').read_text().strip())
        except (FileNotFoundError,ValueError,PermissionError):
            pass
        try:
            quota,period=(cgroup/'cpu.max').read_text().split()
            cgroup_sample['cpuQuotaUsecPerPeriod']=None if quota=='max' else int(quota)
            cgroup_sample['cpuPeriodUsec']=int(period)
        except (FileNotFoundError,ValueError,PermissionError):
            pass
    disk_free = shutil.disk_usage(REPOSITORY).free
    return {'memAvailableBytes': memory.get('MemAvailable'),
            'swapTotalBytes': memory.get('SwapTotal'), 'swapFreeBytes': memory.get('SwapFree'),
            'diskFreeBytes': disk_free, 'cgroup': cgroup_sample,
            'cgroupPath':str(cgroup) if cgroup else None}


def _nearest_rank(values, percentile):
    ordered = sorted(values)
    if not ordered:
        return None
    return ordered[max(0, math.ceil(percentile*len(ordered))-1)]


def run_browser_cohort(environment, tools, browser_cache, evidence, report, *, url, nonce,
                       delivery, cohort_size):
    """Run independent product browsers concurrently against one API/worker/PG."""
    import psycopg
    from infrastructure.postgres_metrics import collect, collect_job_metrics

    dsn = environment['BTL_TEST_DATABASE_URL']
    baseline = _system_resources()
    if (baseline['memAvailableBytes'] is None or baseline['memAvailableBytes'] < 10*1024**3 or
            baseline['diskFreeBytes'] < 36*1024**3 or baseline['swapTotalBytes'] != 0):
        raise RuntimeError('CAPACITY_PREFLIGHT_REFUSED')
    cgroup=Path(baseline['cgroupPath']) if baseline['cgroupPath'] else None
    limits=baseline.get('cgroup',{})
    if (cgroup is None or not (cgroup/'cgroup.procs').is_file() or
            not isinstance(limits.get('memoryMaxBytes'),int) or
            limits['memoryMaxBytes'] > 5*1024**3 or
            not isinstance(limits.get('cpuQuotaUsecPerPeriod'),int) or
            limits.get('cpuPeriodUsec') != 100000 or
            limits['cpuQuotaUsecPerPeriod'] > 600000):
        raise RuntimeError('CAPACITY_RESOURCE_CGROUP_REQUIRED')
    db_before = collect(dsn)
    child_environment = {k: v for k, v in environment.items() if not k.startswith(('PG', 'BTL_'))}
    child_environment['PLAYWRIGHT_BROWSERS_PATH'] = str(browser_cache)
    events = thread_queue.Queue()
    processes = []
    logs = []
    users = []
    cohort_ready = set()
    auth_start_spacing_seconds = 20 if cohort_size >= 10 else 0
    activity_ramp_seconds = 1.5 if cohort_size >= 10 else 0
    for ordinal in range(1, cohort_size+1):
        user_dir = evidence/f'user-{ordinal:03d}'
        user_dir.mkdir(mode=0o700)
        user_dir.chmod(0o700)
        browser_environment = dict(child_environment)
        # The local dependency extraction and some minimal CI images do not
        # provide a system fontconfig cache. Give each Chromium process an
        # isolated cache so concurrent first-run cache writes cannot race.
        font_dir = os.environ.get('BTL_QA_FONT_DIR')
        if font_dir:
            font_path = Path(font_dir).resolve()
            if not font_path.is_dir():
                raise RuntimeError('QA_FONT_DIR_REQUIRED')
            font_cache = user_dir/'font-cache'
            font_cache.mkdir(mode=0o700)
            font_config = user_dir/'fonts.conf'
            font_config.write_text(
                '<fontconfig><dir>'+str(font_path)+'</dir><cachedir>'+str(font_cache)+
                '</cachedir></fontconfig>\n', encoding='utf-8')
            font_config.chmod(0o600)
            browser_environment['FONTCONFIG_FILE'] = str(font_config)
        email = f'load-{secrets.token_hex(12)}@example.com'
        password = 'Synthetic Load passphrase 2026 only'
        config = dict(url=url, nonce=nonce, email=email, password=password,
                      tools=str(tools), evidence=str(user_dir),
                      startDelayMs=(ordinal-1)*auth_start_spacing_seconds*1000,
                      cohortBarrier=cohort_size >= 10)
        log = (user_dir/'browser.log').open('x')
        process = subprocess.Popen(
            ['node', str(Path(__file__).with_name('riksora-browser-journey.mjs'))],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log, text=True,
            bufsize=1, env=browser_environment, start_new_session=True)
        process.stdin.write(json.dumps(config)+'\n')
        process.stdin.flush()
        processes.append(process)
        logs.append(log)
        users.append({'ordinal':ordinal,'emailDigest':hashlib.sha256(email.encode()).hexdigest(),
                      'status':'RUNNING','steps':[],'stepTimeline':[],'apiTrace':[],
                      'authStartDelaySeconds':(ordinal-1)*auth_start_spacing_seconds,
                      'activityRampDelaySeconds':(ordinal-1)*activity_ramp_seconds})

        def consume(index, child, account_email):
            try:
                for line in child.stdout:
                    item = json.loads(line)
                    if item.get('need') in ('verification','recovery'):
                        purpose = item['need']
                        if item.get('email') != account_email:
                            events.put((index, {'protocolError':'DELIVERY_IDENTITY_MISMATCH'}))
                            continue
                        child.stdin.write(json.dumps({'token':delivery.token(account_email,purpose)})+'\n')
                        child.stdin.flush()
                        continue
                    if item.get('need') == 'cohort_start':
                        events.put((index, {'cohortReady':True}))
                        continue
                    events.put((index,item))
                events.put((index,None))
            except Exception as error:
                events.put((index,{'protocolError':type(error).__name__}))

        threading.Thread(target=consume, args=(ordinal-1,process,email), daemon=True).start()

    start = time.monotonic()
    period_samples = []
    process_samples = []
    queue_samples = []
    generator_groups = {process.pid for process in processes}
    process_before = _proc_snapshot(generator_groups,cgroup)
    next_sample = start
    active = set(range(cohort_size))
    failure = None
    try:
        while active:
            now = time.monotonic()
            # A 5-user staged run can serialize through the explicitly bounded
            # one-worker queue. The test remains capped at ten minutes while
            # queue age and each individual worker deadline are enforced below.
            if now-start > 600:
                failure = 'BROWSER_COHORT_WATCHDOG'
                break
            try:
                index,item = events.get(timeout=.5)
            except thread_queue.Empty:
                index,item = None,None
            if index is not None:
                user = users[index]
                if item is None:
                    if index in active:
                        failure = 'BROWSER_COHORT_EXITED_EARLY'
                        break
                elif 'apiEvent' in item and type(item['apiEvent']) is dict:
                    if len(user['apiTrace'])<2048:
                        user['apiTrace'].append(item['apiEvent'])
                elif 'protocolError' in item:
                    user['status']='FAIL'
                    failure=item['protocolError']
                    break
                elif item.get('cohortReady') is True:
                    cohort_ready.add(index)
                    user['cohortReadySeconds']=round(time.monotonic()-start,3)
                    if len(cohort_ready) == cohort_size:
                        for child_index, child in enumerate(processes):
                            child.stdin.write(json.dumps({'start':True,
                                'delayMs':round(child_index*activity_ramp_seconds*1000)})+'\n')
                            child.stdin.flush()
                elif item.get('step') in STEPS:
                    user['steps'].append(item['step'])
                    if type(item.get('atUnixMs')) is int:
                        user['stepTimeline'].append({'step':item['step'],'atUnixMs':item['atUnixMs']})
                elif item.get('progress'):
                    pass
                elif item.get('complete') is True:
                    user['status']='PASS'
                    user['browserVersion']=item.get('browserVersion')
                    user['apiTrace']=item.get('apiTrace',user['apiTrace'])
                    user['apiResponseCount']=item.get('apiResponseCount')
                    user['transientBusyCount']=item.get('transientBusyCount',0)
                    user['pageErrorCount']=item.get('pageErrorCount')
                    user['failedRequests']=item.get('failedRequests')
                    if (tuple(item.get('steps',())) != STEPS or tuple(user['steps']) != STEPS or
                            item.get('pageErrorCount') != 0 or item.get('failedRequests') != 0):
                        user['status']='FAIL'
                        failure='BROWSER_JOURNEY_ASSERTION'
                        break
                    api=item.get('apiTrace',[])
                    transient_busy=lambda row:(row.get('status')==429 and row.get('code')=='RESEARCH_BUSY') or (
                        row.get('status')==503 and row.get('code')=='SERVICE_BUSY')
                    unrecovered_busy=[row for index,row in enumerate(api)
                        if transient_busy(row) and
                        not any(next_row.get('method')==row.get('method') and
                            next_row.get('path')==row.get('path') and 200<=next_row.get('status',0)<400
                            for next_row in api[index+1:])]
                    if item.get('apiResponseCount') != len(api) or any(type(row.get('durationMs')) not in (int,float) or
                           row.get('durationMs') < 0 or
                           (row.get('status') in (429,503) and not transient_busy(row)) or
                           row.get('status',0) >= 500 and not transient_busy(row) for row in api):
                        user['status']='FAIL'
                        failure='API_CAPACITY_ERROR'
                        break
                    if unrecovered_busy:
                        user['status']='FAIL'
                        failure='RESEARCH_BUSY_NOT_RECOVERED'
                        break
                    active.remove(index)
                    try:
                        os.killpg(processes[index].pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    processes[index].wait(timeout=10)
                elif item.get('failurePhase'):
                    user['status']='FAIL'
                    user['failurePhase']=item['failurePhase']
                    user['failureType']=item.get('failureType')
                    user['browserFailureMessage']=item.get('browserFailureMessage')
                    user['browserDiagnostics']=item.get('browserDiagnostics')
                    user['requestFailures']=item.get('requestFailures',[])
                    user['apiTrace']=item.get('apiTrace',user['apiTrace'])
                    failure='BROWSER_JOURNEY_FAILED'
                    break
                else:
                    failure='BROWSER_PROTOCOL_REFUSED'
                    break

            now=time.monotonic()
            if now>=next_sample:
                db_sample_start=time.monotonic()
                sample=_system_resources()
                if (sample['memAvailableBytes'] is None or sample['memAvailableBytes'] < 10*1024**3 or
                        sample['diskFreeBytes'] < 30*1024**3 or sample['swapTotalBytes'] != 0):
                    failure='CAPACITY_RESOURCE_STOP'
                    period_samples.append(sample)
                    break
                period_samples.append(sample)
                process_samples.append(_proc_snapshot(generator_groups,cgroup))
                with psycopg.connect(dsn,connect_timeout=2) as db:
                    row=db.execute("""
                        SELECT count(*) FILTER (WHERE state='QUEUED') AS queued,
                               count(*) FILTER (WHERE state='RUNNING') AS running,
                               count(*) FILTER (WHERE state IN ('FAILED','EXPIRED','RECONCILE_REQUIRED')) AS failed,
                               max(extract(epoch FROM (clock_timestamp()-created_at)))
                                 FILTER (WHERE state='QUEUED') AS oldest_queued_seconds
                        FROM btl.research_jobs
                    """).fetchone()
                    connections=db.execute("SELECT count(*) FROM pg_stat_activity WHERE datname=current_database()").fetchone()[0]
                    db_bytes=db.execute("SELECT pg_database_size(current_database())").fetchone()[0]
                queue_sample={'queued':row[0],'running':row[1],'failed':row[2],
                              'oldestQueuedSeconds':float(row[3]) if row[3] is not None else 0.0,
                              'connections':connections,'databaseBytes':db_bytes,
                              'sampleQueryRoundTripMs':round((time.monotonic()-db_sample_start)*1000,3)}
                queue_samples.append(queue_sample)
                if row[2] or (row[3] is not None and float(row[3]) >= 60):
                    failure='QUEUE_TTL_OR_JOB_FAILURE'
                    break
                next_sample=now+1.0
    finally:
        for index,process in enumerate(processes):
            if process.poll() is None:
                # The journey emits its structured failure before writing the
                # screenshot and sanitized page text. Let that evidence finish
                # before terminating other cohort members.
                if users[index]['status'] == 'FAIL':
                    try:
                        process.wait(timeout=8)
                    except subprocess.TimeoutExpired:
                        pass
            if process.poll() is None:
                try:
                    os.killpg(process.pid,signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=10)
            process.stdin.close()
            process.stdout.close()
            logs[index].close()

    if failure:
        report['cohortResults']=users
        report['cohortFailure']=failure
        report['capacitySamples']={'host':period_samples,'queue':queue_samples,
                                   'process':process_samples}
        report['jobTimeline']=_queue_job_timeline(dsn)
        raise RuntimeError(failure)

    # Let the queue drain before declaring a stable cohort; no arbitrary delay.
    with psycopg.connect(dsn,connect_timeout=2) as db:
        final_queue=db.execute("""
            SELECT count(*) FILTER (WHERE state='QUEUED'),
                   count(*) FILTER (WHERE state='RUNNING'),
                   count(*) FILTER (WHERE state IN ('FAILED','EXPIRED','RECONCILE_REQUIRED')),
                   count(*) FILTER (WHERE state='SUCCEEDED')
            FROM btl.research_jobs
        """).fetchone()
    if final_queue[0] or final_queue[1] or final_queue[2]:
        raise RuntimeError('QUEUE_NOT_DRAINED_OR_FAILED')
    job_metrics=collect_job_metrics(dsn,1000)
    report['jobTimeline']=_queue_job_timeline(dsn)
    worker_wall=job_metrics['worker']['wallNs']
    queue_wait=job_metrics['queueWaitMicroseconds']
    if worker_wall['maximum'] is not None and worker_wall['maximum'] > 30_000_000_000:
        raise RuntimeError('WORKER_DEADLINE_EXCEEDED')
    if queue_wait['maximum'] is not None and queue_wait['maximum'] > 60_000_000:
        raise RuntimeError('QUEUE_TTL_EXCEEDED')
    db_after=collect(dsn)
    api_rows=[row for user in users for row in user['apiTrace']]
    durations=[float(row['durationMs']) for row in api_rows]
    status_counts={}
    for row in api_rows:
        key=str(row['status'])
        status_counts[key]=status_counts.get(key,0)+1
    elapsed=time.monotonic()-start
    cgroup_samples=[sample.get('cgroup',{}) for sample in period_samples]
    cgroup_cpu_usec=max((sample.get('cpuUsageUsec',0) or 0 for sample in cgroup_samples),default=0)-\
        (baseline.get('cgroup',{}).get('cpuUsageUsec',0) or 0)
    cpu_seconds=max(0,cgroup_cpu_usec)/1_000_000
    elapsed=max(elapsed,.001)
    api_sample_rtts=[sample['sampleQueryRoundTripMs'] for sample in queue_samples]
    ticks_per_second=os.sysconf('SC_CLK_TCK')
    report['cohortResults']=users
    report['capacity']=dict(
        cohortSize=cohort_size,completedJourneys=sum(user['status']=='PASS' for user in users),
        completedClosedTrades=sum(1 for user in users if user['status']=='PASS'),
        holdSeconds=round(elapsed,3),browserGenerator='one isolated Chromium process group per trader',
        transientBusyResponses=sum(user.get('transientBusyCount',0) for user in users),
        browserApiCalls=len(api_rows),apiStatusCounts=status_counts,
        apiLatencyMs=dict(p50=_nearest_rank(durations,.50),p95=_nearest_rank(durations,.95),
                          p99=_nearest_rank(durations,.99),max=max(durations,default=None)),
        host=dict(memAvailableMinBytes=min((sample['memAvailableBytes'] for sample in period_samples),default=None),
                  diskFreeMinBytes=min((sample['diskFreeBytes'] for sample in period_samples),default=None),
                  swapTotalBytes=max((sample['swapTotalBytes'] for sample in period_samples),default=None),
                  cgroupMemoryPeakBytes=max((sample.get('cgroup',{}).get('memoryPeakBytes',0) or 0 for sample in period_samples),default=0),
                  cgroupCpuUsec=max(0,cgroup_cpu_usec),
                  cgroupCpuCoresAverage=round(cpu_seconds/elapsed,3),
                  cgroupCpuPercentOfHost=round(100*cpu_seconds/(elapsed*(os.cpu_count() or 1)),2),
                  cgroupCpuThrottledUsec=max(0,max((sample.get('cpuThrottledUsec',0) or 0 for sample in cgroup_samples),default=0)-
                                    (baseline.get('cgroup',{}).get('cpuThrottledUsec',0) or 0))),
        processRssPeakBytes=dict(browserGenerator=max((sample['generatorRssBytes'] for sample in process_samples),default=0),
                                 service=max((sample['serviceRssBytes'] for sample in process_samples),default=0),
                                 postgres=max((sample['postgresRssBytes'] for sample in process_samples),default=0)),
        processCpuTicksDelta=dict(browserGenerator=max(0,max((sample['generatorCpuTicks'] for sample in process_samples),default=0)-process_before['generatorCpuTicks']),
                                  service=max(0,max((sample['serviceCpuTicks'] for sample in process_samples),default=0)-process_before['serviceCpuTicks']),
                                  postgres=max(0,max((sample['postgresCpuTicks'] for sample in process_samples),default=0)-process_before['postgresCpuTicks'])),
        processCpuSeconds=dict(browserGenerator=round(max(0,max((sample['generatorCpuTicks'] for sample in process_samples),default=0)-process_before['generatorCpuTicks'])/ticks_per_second,3),
                               service=round(max(0,max((sample['serviceCpuTicks'] for sample in process_samples),default=0)-process_before['serviceCpuTicks'])/ticks_per_second,3),
                               postgres=round(max(0,max((sample['postgresCpuTicks'] for sample in process_samples),default=0)-process_before['postgresCpuTicks'])/ticks_per_second,3)),
        postgres=dict(databaseBytesBefore=db_before['databaseBytes'],databaseBytesAfter=db_after['databaseBytes'],
                      databaseGrowthBytes=db_after['databaseBytes']-db_before['databaseBytes'],
                      maxConnections=max((sample['connections'] for sample in queue_samples),default=0),
                      maxQueued=max((sample['queued'] for sample in queue_samples),default=0),
                      maxRunning=max((sample['running'] for sample in queue_samples),default=0),
                      sampleQueryRoundTripMs=dict(p50=_nearest_rank(api_sample_rtts,.50),p95=_nearest_rank(api_sample_rtts,.95),
                                                  p99=_nearest_rank(api_sample_rtts,.99)),
                      queueSamples=queue_samples,queueStates=dict(queued=final_queue[0],running=final_queue[1],
                          failed=final_queue[2],succeeded=final_queue[3]),jobMetrics=job_metrics),
        processMeasurement='per-process RSS sums can double-count shared pages; cgroup memory peak is aggregate actual usage',
        cpuMeasurement='process CPU in clock ticks; cgroup CPU usec is aggregate; browser generator is reported separately',
        durationMeasurement='one observed API request/response duration from Playwright, not server-only latency',
    )
    report['steps']=list(STEPS)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tools', type=Path, default=REPOSITORY/'frontend/tests/browser-tools')
    parser.add_argument('--browser-cache', type=Path)
    parser.add_argument('--capacity-cohort', type=int, choices=(1,2,5,10,20,50),
                        help='concurrent real-browser synthetic product users; requires bounded systemd cgroup')
    parser.add_argument('--worker-count', type=int, choices=(1,2), default=1,
                        help='bounded cloud job workers for capacity acceptance only')
    parser.add_argument('--auth-ip-limit', type=int, choices=tuple(range(30,1201)), default=30,
                        help='isolated QA auth/IP budget; default preserves the production default of 30/min')
    args = parser.parse_args()
    try:
        raise SystemExit(run(args.tools.resolve(), (args.browser_cache or args.tools/'browsers').resolve(),
                             args.capacity_cohort or 1, args.capacity_cohort is not None,
                             args.worker_count, args.auth_ip_limit))
    except Exception as error:
        print('BROWSER_GATE_REFUSED:'+type(error).__name__, file=sys.stderr)
        raise SystemExit(1) from None
