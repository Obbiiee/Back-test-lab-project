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
CHART_TAIL = re.compile(rb'"count":(\d+),"hasMore":(true|false),"nextBefore":(\d+|null)')
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


class Chart:
    """Chart traffic of one trader against the chart service: 9 timeframes x up to 5,000 candles of history at session open, then
    forming-candle polls and timeframe switches while the trader works (QA/measurement only, loopback HTTP, prototype auth)."""
    TFS = ("M1", "M3", "M5", "M15", "M30", "H1", "H2", "H4", "D1")

    def __init__(self, n, host, port, stats, rng, hist):
        self.n, self.host, self.port, self.stats, self.rng, self.hist = n, host, port, stats, rng, hist
        self.conn = None; self.stop = threading.Event(); self.candles = {}

    def _get(self, path, route, method='GET'):
        for attempt in (0, 1):
            t0 = time.perf_counter()
            try:
                if self.conn is None:
                    self.conn = http.client.HTTPConnection(self.host, self.port, timeout=60)
                self.conn.request(method, path, headers={'Authorization': f'Bearer tok-{self.n}'} if method == 'GET' else {})
                r = self.conn.getresponse(); data = r.read(); status = r.status
                break
            except Exception as error:
                self.conn = None
                if attempt == 0:
                    continue
                self.stats.record(route, 0, (time.perf_counter() - t0) * 1000, type(error).__name__, True)
                return 0, None
        self.stats.record(route, status, (time.perf_counter() - t0) * 1000, None, True)
        if method != 'GET' or not data:
            return status, None
        # Only the paging fields are read: the browser (not this generator) would decode the candles, so a full json.loads of
        # 5,000-candle pages in Python would charge client CPU to the server host.
        m = CHART_TAIL.search(data[-4000:] if len(data) > 4000 else data)
        if not m:
            return status, None
        return status, dict(count=int(m.group(1)), hasMore=m.group(2) == b'true', nextBefore=None if m.group(3) == b'null' else int(m.group(3)))

    def load_tf(self, tf):
        total, before, pages = 0, None, 0
        while total < self.hist:
            q = f'session=s-{self.n}&tf={tf}&limit={512 if before is None else 1000}' + ('' if before is None else f'&before={before}')
            status, d = self._get('/v1/chart/bars?' + q, 'CHART first page 512' if before is None else 'CHART older page 1000')
            if status != 200 or not d:
                return False
            total += d['count']; pages += 1; before = d['nextBefore']
            if not d['hasMore'] or before is None:
                break
        self.candles[tf] = total
        return True

    def run(self):
        t0 = time.perf_counter(); ok = all(self.load_tf(tf) for tf in self.TFS)
        self.stats.record_job('CHART initial load 9 timeframes', (time.perf_counter() - t0) * 1000, None if ok else 'chart_load_failed')
        tf, last_switch = 'M5', time.monotonic()
        while not self.stop.wait(2.0 + self.rng.random() * 0.5):
            self._get(f'/v1/chart/bars?session=s-{self.n}&tf={tf}&limit=1', 'CHART forming-candle poll')
            if time.monotonic() - last_switch > 15:
                tf = self.rng.choice(self.TFS); last_switch = time.monotonic()
                self.load_tf(tf)

    def advance(self, seconds):
        self._get(f'/__qa/advance?session=s-{self.n}&seconds={seconds}', 'CHART qa-advance (not user traffic)', method='POST')


class Trader:
    def __init__(self, n, host, port, template, think_ms, stats):
        self.n, self.host, self.port, self.template, self.think = n, host, port, template, think_ms
        self.stats = stats
        self.email = f'load-{uuid.uuid4().hex[:20]}@example.com'
        self.ip = f'10.{(n >> 16) & 255}.{(n >> 8) & 255}.{n & 255}'
        self.token = None
        self.conn = None
        self.rng = random.Random(n)
        self.chart = None
        self._auth_phase = True
        self.journey_port = None
        self.conns = {}
        self.max_retries = dict(QUEUE_CAPACITY=45, RESEARCH_BUSY=8, SERVICE_BUSY=8)
        self.recovered = 0

    def _conn(self):
        port = self.port if (self.journey_port is None or self._auth_phase) else self.journey_port
        c = self.conns.get(port)
        if c is None:
            c = self.conns[port] = http.client.HTTPSConnection(self.host, port, timeout=100, context=ssl._create_unverified_context())
        self.conn = c
        return c

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
            reused = (self.port if (self.journey_port is None or self._auth_phase) else self.journey_port) in self.conns
            try:
                c = self._conn()
                c.request(method, path, body.encode() if isinstance(body, str) else body, headers)
                r = c.getresponse(); data = r.read(); status = r.status; self.retry_after = r.getheader('Retry-After')
                break
            except Exception as error:
                self.conns = {k: v for k, v in self.conns.items() if v is not self.conn}
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

    def patience(self, detail):
        # Frontend policy is 45 (QUEUE_CAPACITY) / 8 retries; a patient trader keeps waiting (about 5 minutes) when --patient is set.
        return self.max_retries.get(detail, 8)

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

    def submit(self, step, path, body, job):
        """POST/GET with the frontend's busy policy (same job id on RESEARCH_BUSY/QUEUE_CAPACITY/SERVICE_BUSY), patience set by max_retries."""
        retries = 0
        while True:
            status, value = self.call(step['method'], path, body, step['contentType'], job=job)
            detail = value.get('detail') if isinstance(value, dict) else None
            if status in (429, 503) and detail in ('RESEARCH_BUSY', 'QUEUE_CAPACITY', 'SERVICE_BUSY'):
                with self.stats.l:
                    self.stats.busy[detail] = self.stats.busy.get(detail, 0) + 1
                if retries < self.patience(detail):
                    try:
                        hint = min(3.0, max(0.0, float(self.retry_after)))
                    except (TypeError, ValueError):
                        hint = 0.0
                    time.sleep(max(hint, min(0.8, 0.05 * 2 ** retries)) + self.rng.random() * 0.025); retries += 1
                    continue
                with self.stats.l:
                    self.stats.busy_unrecovered += 1
            return status, value

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
            t_first = time.perf_counter()
            status, value = self.submit(step, path, body, job)
            if step['job']:
                recoveries = 0
                while True:
                    if status != 202 or not isinstance(value, dict) or value.get('jobId') != job:
                        return False, f'step{index}:{route_key(step["method"], path)}:submit:{status}'
                    value, error, wait_ms = self.wait_job(path.split('/research/')[0] + '/research', value)
                    if error == 'poll:404' and recoveries < 3:
                        # The finished job row was pruned (queue keeps the 15 newest finished jobs) before this trader polled it.
                        # Client-side recovery, NOT current frontend behaviour: resubmit the same request with the same job/command ids;
                        # the financial commands are idempotent by command/request id (permanent receipts).
                        recoveries += 1; self.recovered += 1
                        with self.stats.l:
                            self.stats.recoveries[route_key(step['method'], path)] = self.stats.recoveries.get(route_key(step['method'], path), 0) + 1
                        status, value = self.submit(step, path, body, job)
                        continue
                    break
                logical_ms = (time.perf_counter() - t_first) * 1000
                self.stats.record_job(route_key(step['method'], path), logical_ms, error)
                if error:
                    return False, f'step{index}:{route_key(step["method"], path)}:{error}'
                if self.chart and 'jump-next-event' in path:
                    self.chart.advance(60)      # the replay owner moved the cursor: tell the chart service (QA-only endpoint)
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
        self.chart_errors = 0
        self.recoveries = {}

    def record(self, route, status, ms, err, timed):
        if not timed or self.t_start is None:
            return
        with self.l:
            if route.startswith('CHART') and status != 200:
                self.chart_errors += 1
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
    ap.add_argument('--api-ports', default=''); ap.add_argument('--patient', action='store_true'); ap.add_argument('--chart-url', default=None); ap.add_argument('--chart-history', type=int, default=5000)
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
    extra_ports = [int(x) for x in a.api_ports.split(',') if x]
    for t in traders:
        t._auth_phase = False
        if extra_ports:                       # spread traders over the main instance and the extra instances
            allp = [u.port] + extra_ports
            t.journey_port = allp[t.n % len(allp)]
    barrier = threading.Barrier(a.traders + 1)

    if a.patient:
        for t in traders:
            t.max_retries = dict(QUEUE_CAPACITY=400, RESEARCH_BUSY=400, SERVICE_BUSY=400)
    chart_threads = []
    if a.chart_url:
        cu = urllib.parse.urlsplit(a.chart_url)
        for t in traders:
            t.chart = Chart(t.n, cu.hostname, cu.port, stats, random.Random(1000 + t.n), a.chart_history)

    def work(t):
        barrier.wait()
        time.sleep(t.n * a.stagger_ms / 1000)
        if t.chart:
            ct = threading.Thread(target=t.chart.run, daemon=True); ct.start()
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
    for t in traders:
        if t.chart:
            t.chart.stop.set()
    wall = time.perf_counter() - stats.t_start
    emit({'summary': {
        'status': 'DONE', 'traders': a.traders, 'cyclesPerTrader': a.cycles, 'thinkMs': a.think_ms, 'staggerMs': a.stagger_ms,
        'wallSeconds': round(wall, 2), 'completedCycles': stats.completed, 'failedTraders': len(stats.failures),
        'chartEnabled': bool(a.chart_url), 'chartErrors': stats.chart_errors, 'retentionRecoveries': stats.recoveries, 'chartCandlesLoadedPerTimeframe': (traders[0].chart.candles if a.chart_url else None), 'failures': stats.failures[:10], 'busyRefusals': stats.busy, 'busyUnrecovered': stats.busy_unrecovered, 'statusCounts': stats.status, 'transportErrors': stats.errors,
        'journeysPerMinute': round(stats.completed / wall * 60, 2),
        'cycleSeconds': {'p50': pct([x / 1000 for x in stats.cycle_ms], 50), 'p95': pct([x / 1000 for x in stats.cycle_ms], 95),
                         'max': round(max(stats.cycle_ms) / 1000, 2) if stats.cycle_ms else None},
        'httpLatencyMs': {k: {'n': len(v), 'p50': pct(v, 50), 'p95': pct(v, 95), 'p99': pct(v, 99), 'max': round(max(v), 1)} for k, v in sorted(stats.lat.items())},
        'jobEndToEndMs': {k: {'n': len(v), 'p50': pct(v, 50), 'p95': pct(v, 95), 'p99': pct(v, 99), 'max': round(max(v), 1)} for k, v in sorted(stats.jobs.items())},
        'jobErrors': stats.job_errors}})


if __name__ == '__main__':
    main()
