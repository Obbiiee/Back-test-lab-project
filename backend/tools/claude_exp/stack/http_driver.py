"""HTTP-level synthetic trader driver (QA/measurement only, no browser).

Replays the API journey that ONE real browser trader performed against the real product backend (recorded by the opt-in
RIKSORA_QA_RECORD_API hook of riksora-browser-journey.mjs, trimmed into api_journey_template.json). Every trader gets fresh client ids,
its own account, and its own X-Forwarded-For address (as a trusted reverse proxy would supply), so the per-IP limits behave as they would
for distinct users. Server-issued ids/hashes are learned from the live responses by aligning them with the recorded responses.

Protocol with the parent (frontend/tests/http_load_cohort.py): JSON lines on stdout/stdin.
  child -> {"need":"verification","email":...}   parent -> {"email":...,"token":...}
  child -> {"summary": {...}} as the last line.
Loopback to the harness's own self-signed server only; certificate verification is disabled for that reason.
"""
import argparse, http.client, json, queue, random, re, ssl, sys, threading, time, urllib.parse, uuid
from pathlib import Path

TEMPLATE = Path(__file__).with_name('api_journey_template.json')
PASSWORD = 'Synthetic Load passphrase 2026 only'
UUID = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
CLIENT_ID = re.compile(r'\b(session|method|command|order):(' + UUID + ')')
REQUEST_ID = re.compile(r'"requestId":"([0-9a-f]{32})"')
lock = threading.Lock()
pending = {}
out_lock = threading.Lock()


def emit(obj):
    with out_lock:
        print(json.dumps(obj), flush=True)


def stdin_reader():
    for line in sys.stdin:
        try:
            item = json.loads(line)
            ev = pending.get(item.get('email'))
            if ev:
                ev[1] = item.get('token'); ev[0].set()
        except ValueError:
            pass


def flatten(value, path=''):
    if isinstance(value, dict):
        for k, v in value.items():
            yield from flatten(v, f'{path}/{k}')
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from flatten(v, f'{path}[{i}]')
    else:
        yield path, value


def route_key(method, path):
    p = urllib.parse.urlsplit(path).path
    p = re.sub(UUID, '{id}', p)
    p = re.sub(r'/(session|method)%3A\{id\}', r'/{\1}', p)
    return f'{method} {p}'


class Trader:
    def __init__(self, n, host, port, template, think_ms, stats):
        self.n, self.host, self.port, self.template, self.think = n, host, port, template, think_ms
        self.stats = stats
        self.email = f'load-{uuid.uuid4().hex[:20]}@example.com'
        self.ip = f'10.{(n >> 16) & 255}.{(n >> 8) & 255}.{n & 255}'
        self.token = None
        self.conn = None
        self.rng = random.Random(n)

    def _conn(self):
        if self.conn is None:
            self.conn = http.client.HTTPSConnection(self.host, self.port, timeout=100, context=ssl._create_unverified_context())
        return self.conn

    def call(self, method, path, body=None, ctype=None, job=None, auth=True, timed=True):
        headers = {'X-Forwarded-For': self.ip, 'X-Forwarded-Proto': 'https'}
        if auth and self.token:
            headers['Authorization'] = 'Bearer ' + self.token
        if job:
            headers['X-BTL-Job'] = job
        if body is not None:
            headers['Content-Type'] = ctype or 'application/json'
        t0 = time.perf_counter()
        for attempt in (0, 1):
            reused = self.conn is not None
            try:
                c = self._conn()
                c.request(method, path, body.encode() if isinstance(body, str) else body, headers)
                r = c.getresponse(); data = r.read(); status = r.status; self.retry_after = r.getheader('Retry-After')
                break
            except Exception as error:
                self.conn = None
                # A kept-alive connection the server already closed while idle: reconnect once (browsers do the same).
                if attempt == 0 and reused and isinstance(error, (http.client.RemoteDisconnected, ConnectionResetError, BrokenPipeError)):
                    continue
                self.stats.record(route_key(method, path), 0, (time.perf_counter() - t0) * 1000, type(error).__name__, timed)
                return 0, None
        ms = (time.perf_counter() - t0) * 1000
        self.stats.record(route_key(method, path), status, ms, None, timed)
        try:
            parsed = json.loads(data) if data else None
        except ValueError:
            parsed = None
        return status, parsed

    def auth(self):
        s, _ = self.call('POST', '/api/v1/auth/register', json.dumps({'email': self.email, 'password': PASSWORD}), auth=False, timed=False)
        if s != 201:
            return f'register:{s}'
        ev = [threading.Event(), None]; pending[self.email] = ev
        emit({'need': 'verification', 'email': self.email})
        if not ev[0].wait(60):
            return 'verify:no_token'
        s, _ = self.call('POST', '/api/v1/auth/verify', json.dumps({'token': ev[1]}), auth=False, timed=False)
        if s != 200:
            return f'verify:{s}'
        return self.login()

    def login(self):
        form = urllib.parse.urlencode({'username': self.email, 'password': PASSWORD})
        s, b = self.call('POST', '/api/v1/auth/login', form, 'application/x-www-form-urlencoded', auth=False, timed=False)
        if s != 200 or not b:
            return f'login:{s}'
        self.token = b['access_token']
        return None

    def wait_job(self, root, first):
        jid = first['jobId']; attempt = 0; t0 = time.perf_counter()
        value = first
        while value.get('state') in ('QUEUED', 'RUNNING'):
            time.sleep((min(3000, 1000 + attempt * 500) + self.rng.randint(0, 250)) / 1000); attempt += 1
            s, value = self.call('GET', f'{root}/jobs/{jid}')
            if s != 200 or not isinstance(value, dict):
                return None, f'poll:{s}', (time.perf_counter() - t0) * 1000
        ms = (time.perf_counter() - t0) * 1000
        if value.get('state') == 'SUCCEEDED':
            return value.get('result'), None, ms
        return None, 'job:' + str(value.get('state')) + ':' + str((value.get('result') or {}).get('detail') or (value.get('result') or {}).get('error') or ''), ms

    def cycle(self, fresh_session):
        """One full recorded trader journey (workspace .. journal). Returns (ok, reason)."""
        mapping = {}
        for step in self.template:
            for text in (step['body'] or '', step['path']):
                for kind, ident in CLIENT_ID.findall(urllib.parse.unquote(text)):
                    mapping.setdefault(f'{kind}:{ident}', f'{kind}:{uuid.uuid4()}')
                for rid in REQUEST_ID.findall(text):
                    mapping.setdefault(rid, uuid.uuid4().hex)
        root_rec = None
        for index, step in enumerate(self.template):
            time.sleep(self.rng.uniform(0.3, 1.0) * self.think / 1000)
            path, body = step['path'], step['body']
            for k in sorted(mapping, key=len, reverse=True):
                v = mapping[k]
                path = path.replace(urllib.parse.quote(k, safe=''), urllib.parse.quote(v, safe='')).replace(k, v)
                if body:
                    body = body.replace(k, v)
            job = str(uuid.uuid4()) if step['job'] else None
            t0 = time.perf_counter()
            retries = 0
            while True:
                status, value = self.call(step['method'], path, body, step['contentType'], job=job)
                detail = value.get('detail') if isinstance(value, dict) else None
                if status in (429, 503) and detail in ('RESEARCH_BUSY', 'QUEUE_CAPACITY', 'SERVICE_BUSY'):
                    # Same policy as the frontend client: explicit pre-admission refusal, retry with the same job id.
                    with self.stats.l:
                        self.stats.busy[detail] = self.stats.busy.get(detail, 0) + 1
                    if retries < (45 if detail == 'QUEUE_CAPACITY' else 8):
                        try:
                            hint = min(3.0, max(0.0, float(self.retry_after)))
                        except (TypeError, ValueError):
                            hint = 0.0
                        time.sleep(max(hint, min(0.8, 0.05 * 2 ** retries)) + self.rng.random() * 0.025); retries += 1
                        continue
                    with self.stats.l:
                        self.stats.busy_unrecovered += 1
                break
            logical_ms = (time.perf_counter() - t0) * 1000
            if step['job']:
                if status != 202 or not isinstance(value, dict) or value.get('jobId') != job:
                    return False, f'step{index}:{route_key(step["method"], path)}:submit:{status}'
                value, error, wait_ms = self.wait_job(path.split('/research/')[0] + '/research', value)
                logical_ms = (time.perf_counter() - t0) * 1000
                self.stats.record_job(route_key(step['method'], path), logical_ms, error)
                if error:
                    return False, f'step{index}:{route_key(step["method"], path)}:{error}'
            elif status != step['status']:
                detail = value.get('detail') if isinstance(value, dict) else None
                return False, f'step{index}:{route_key(step["method"], path)}:{status}:{str(detail)[:40]}'
            rec, live = dict(flatten(step['result'])), dict(flatten(value))
            for p, rv in rec.items():
                lv = live.get(p)
                if isinstance(rv, str) and isinstance(lv, str) and len(rv) >= 16 and rv != lv and rv not in mapping:
                    mapping[rv] = lv
            for p in ('/totalOrders',):
                if p in rec and live.get(p) != rec[p]:
                    return False, f'step{index}:journal_mismatch:{rec[p]}!={live.get(p)}'
        return True, None


class Stats:
    def __init__(self):
        self.lat, self.status, self.errors, self.jobs, self.job_errors = {}, {}, {}, {}, {}
        self.l = threading.Lock()
        self.t_start = None
        self.cycle_ms, self.failures, self.completed = [], [], 0
        self.busy, self.busy_unrecovered = {}, 0

    def record(self, route, status, ms, err, timed):
        if not timed or self.t_start is None:
            return
        with self.l:
            self.lat.setdefault(route, []).append(ms)
            self.status[str(status)] = self.status.get(str(status), 0) + 1
            if err:
                self.errors[err] = self.errors.get(err, 0) + 1

    def record_job(self, route, ms, error):
        with self.l:
            self.jobs.setdefault(route, []).append(ms)
            if error:
                self.job_errors[error] = self.job_errors.get(error, 0) + 1


def pct(xs, p):
    xs = sorted(xs)
    return round(xs[max(0, min(len(xs) - 1, -(-len(xs) * p // 100) - 1))], 1) if xs else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--url', required=True); ap.add_argument('--traders', type=int, required=True)
    ap.add_argument('--cycles', type=int, default=3); ap.add_argument('--think-ms', type=int, default=1000)
    ap.add_argument('--stagger-ms', type=int, default=0)
    a = ap.parse_args()
    u = urllib.parse.urlsplit(a.url)
    template = json.loads(TEMPLATE.read_text())
    threading.Thread(target=stdin_reader, daemon=True).start()
    stats = Stats()
    traders = [Trader(i + 1, u.hostname, u.port, template, a.think_ms, stats) for i in range(a.traders)]
    setup_fail = []
    sem = threading.Semaphore(4)

    def setup(t):
        with sem:
            e = t.auth()
        if e:
            setup_fail.append(e)
    th = [threading.Thread(target=setup, args=(t,)) for t in traders]
    t_setup = time.perf_counter()
    [x.start() for x in th]; [x.join() for x in th]
    emit({'progress': 'setup_done', 'seconds': round(time.perf_counter() - t_setup, 1), 'failures': setup_fail[:5]})
    if setup_fail:
        emit({'summary': {'status': 'SETUP_FAILED', 'failures': setup_fail[:10]}}); return
    barrier = threading.Barrier(a.traders + 1)

    def work(t):
        barrier.wait()
        time.sleep(t.n * a.stagger_ms / 1000)
        for c in range(a.cycles):
            t0 = time.perf_counter()
            ok, why = t.cycle(c)
            ms = (time.perf_counter() - t0) * 1000
            with stats.l:
                if ok:
                    stats.completed += 1; stats.cycle_ms.append(ms)
                else:
                    stats.failures.append(why)
                    break
    th = [threading.Thread(target=work, args=(t,)) for t in traders]
    [x.start() for x in th]
    emit({'progress': 'ready'})
    stats.t_start = time.perf_counter()
    barrier.wait()
    [x.join() for x in th]
    wall = time.perf_counter() - stats.t_start
    emit({'summary': {
        'status': 'DONE', 'traders': a.traders, 'cyclesPerTrader': a.cycles, 'thinkMs': a.think_ms, 'staggerMs': a.stagger_ms,
        'wallSeconds': round(wall, 2), 'completedCycles': stats.completed, 'failedTraders': len(stats.failures),
        'failures': stats.failures[:10], 'busyRefusals': stats.busy, 'busyUnrecovered': stats.busy_unrecovered, 'statusCounts': stats.status, 'transportErrors': stats.errors,
        'journeysPerMinute': round(stats.completed / wall * 60, 2),
        'cycleSeconds': {'p50': pct([x / 1000 for x in stats.cycle_ms], 50), 'p95': pct([x / 1000 for x in stats.cycle_ms], 95),
                         'max': round(max(stats.cycle_ms) / 1000, 2) if stats.cycle_ms else None},
        'httpLatencyMs': {k: {'n': len(v), 'p50': pct(v, 50), 'p95': pct(v, 95), 'p99': pct(v, 99), 'max': round(max(v), 1)} for k, v in sorted(stats.lat.items())},
        'jobEndToEndMs': {k: {'n': len(v), 'p50': pct(v, 50), 'p95': pct(v, 95), 'p99': pct(v, 99), 'max': round(max(v), 1)} for k, v in sorted(stats.jobs.items())},
        'jobErrors': stats.job_errors}})


if __name__ == '__main__':
    main()
