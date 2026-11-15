"""Active-trader HTTP driver for the VPS1 economic-capacity benchmark (SYNTHETIC / TEST ONLY).

Real HTTP to the product API on loopback (no TLS, no reverse proxy: labelled as such), one account per trader with its own X-Forwarded-For address,
personas with seeded action scripts and think times. Runs in its OWN cgroup; reports its own CPU/RSS and event-loop lag so generator
saturation is visible. Every admission refusal (429 / 503 SERVICE_BUSY / QUEUE_CAPACITY) is counted, retries are reported separately as
CLIENT RECOVERY (bounded like the existing frontend: 8 for SERVICE_BUSY, 45 for QUEUE_CAPACITY).

Financial parity: each script instance is (persona, seed). Its FACTS (final balances/trades/order statuses per session, outcome-class trace hash)
must equal the reference measured alone on an idle server (`--mode ref`); think time never changes state.
"""
import argparse
import asyncio
import collections
import hashlib
import json
import os
import random
import resource
import sys
import time
import uuid
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tests.test_research_sessions import method  # noqa: E402  (synthetic Method record)

PASSWORD = 'Synthetic Load passphrase 2026 only'
STEP_NS = 60_000_000_000
PERSONAS = ('swing', 'scalper', 'impulsive', 'averaging', 'hedging', 'multipair', 'researcher')
PERSONA_THINK = dict(swing=(20, 45), scalper=(2, 6), impulsive=(1, 4), averaging=(10, 30), hedging=(10, 30), multipair=(8, 20), researcher=(5, 15))
ACTIONS_PER_SCRIPT = dict(swing=18, scalper=24, impulsive=24, averaging=16, hedging=16, multipair=20, researcher=16)
ADMISSION = ('SERVICE_BUSY', 'QUEUE_CAPACITY', 'RESEARCH_BUSY')


def pct(values, p):
    values = sorted(values)
    return None if not values else round(values[min(len(values) - 1, int(p / 100 * (len(values) - 1) + 0.5))], 4)


class Metrics:
    def __init__(self):
        self.lat = collections.defaultdict(list)          # kind -> seconds (user-perceived, incl. client recovery)
        self.count = collections.Counter()                # (kind, outcome)
        self.admission = collections.Counter()            # refusals by code (each attempt)
        self.recovered = collections.Counter()            # successful completions after >=1 refusal
        self.unsupported = collections.Counter()
        self.ticks = 0
        self.trades = 0
        self.jumps = 0
        self.requests = 0
        self.bytes_in = 0
        self.bytes_out = 0
        self.expected_refusals = collections.Counter()
        self.persona_lat = collections.defaultdict(list)
        self.conn_retries = collections.Counter()

    def summary(self):
        return dict(
            latencySeconds={k: dict(n=len(v), p50=pct(v, 50), p95=pct(v, 95), p99=pct(v, 99), max=round(max(v), 3)) for k, v in sorted(self.lat.items())},
            outcomes={f'{k}:{o}': n for (k, o), n in sorted(self.count.items())}, admissionRefusals=dict(self.admission), clientRecoveries=dict(self.recovered),
            unsupported=dict(self.unsupported), connectionRetries=dict(self.conn_retries), expectedRefusals=dict(self.expected_refusals), ticksAdvanced=self.ticks, trades=self.trades, jumps=self.jumps,
            requests=self.requests, bytesIn=self.bytes_in, bytesOut=self.bytes_out)


class Trader:
    def __init__(self, client, outbox, index, persona, base_seed, metrics, source, think_scale, ip):
        self.c, self.outbox, self.i, self.persona, self.m, self.src = client, outbox, index, persona, metrics, source
        self.think_scale, self.ip = think_scale, ip
        self.headers, self.root, self.method_id = {}, None, None
        self.rng = random.Random(base_seed)
        self.chart_unsupported = False
        self.trace = []                  # outcome classes, deterministic per (persona, seed)
        self.facts = []

    # ---------------- plumbing ----------------
    async def req(self, kind, verb, url, *, json_body=None, data=None, headers=None, job=None, ok=(200, 202)):
        """One user-perceived request with bounded client recovery on admission refusals. Returns httpx.Response."""
        h = {'X-Forwarded-For': self.ip, 'X-Forwarded-Proto': 'https', **self.headers, **(headers or {})}
        if job:
            h['X-BTL-Job'] = job
        t0, attempts, refused = time.monotonic(), 0, False
        limit = 8
        while True:
            attempts += 1
            body = json.dumps(json_body, separators=(',', ':')).encode() if json_body is not None else None
            if body is not None:
                h['Content-Type'] = 'application/json'
                self.m.bytes_out += len(body)
            try:
                r = await self.c.request(verb, url, content=body, data=data, headers=h)
            except (httpx.ReadError, httpx.RemoteProtocolError, httpx.ConnectError, httpx.WriteError) as error:
                self.m.conn_retries[type(error).__name__] += 1          # client recovery (stale keep-alive); same job/command ids make the retry idempotent
                if attempts <= 3:
                    await asyncio.sleep(0.2 * attempts)
                    continue
                raise
            self.m.requests += 1
            self.m.bytes_in += len(r.content)
            code = None
            if r.status_code in (429, 503):
                try:
                    code = r.json().get('detail')
                except ValueError:
                    code = 'HTTP' + str(r.status_code)
                if r.status_code == 429 and not code:
                    code = 'RATE_LIMIT'
            if code and (code in ADMISSION or r.status_code == 429):
                self.m.admission[code] += 1
                refused = True
                limit = 45 if code == 'QUEUE_CAPACITY' else 8
                if attempts <= limit:
                    try:
                        wait = float(r.headers.get('Retry-After', '1'))
                    except ValueError:
                        wait = 1.0
                    await asyncio.sleep(min(5.0, wait) + 0.05 * attempts)
                    continue
            break
        dt = time.monotonic() - t0
        self.m.lat[kind].append(dt)
        outcome = 'ok' if r.status_code in ok else f'http{r.status_code}'
        self.m.count[(kind, outcome)] += 1
        if refused and outcome == 'ok':
            self.m.recovered[kind] += 1
        return r

    async def wait_job(self, kind, r):
        """Resolve the documented immediate-or-durable-job response; returns result body or None."""
        if r.status_code == 200:
            return r.json()
        if r.status_code != 202:
            return None
        job = r.json().get('jobId')
        t0, interval = time.monotonic(), 0.4
        while time.monotonic() - t0 < 600:
            await asyncio.sleep(interval)
            interval = min(2.0, interval * 1.3)
            j = await self.req(kind + '.poll', 'GET', f'{self.root}/jobs/{job}')
            if j.status_code != 200:
                return None
            b = j.json()
            if b.get('state') == 'SUCCEEDED':
                self.m.lat[kind + '.complete'].append(time.monotonic() - t0)
                return b
            if b.get('state') not in ('QUEUED', 'RUNNING'):
                self.m.count[(kind, 'job_' + str(b.get('state')))] += 1
                return None
        return None

    async def think(self):
        lo, hi = PERSONA_THINK[self.persona]
        await asyncio.sleep(self.rng.uniform(lo, hi) * self.think_scale)

    # ---------------- account ----------------
    async def setup(self):
        email = f'{uuid.uuid4().hex}@example.com'
        h = {'X-Forwarded-For': self.ip, 'X-Forwarded-Proto': 'https'}
        r = await self.c.post('/api/v1/auth/register', json={'email': email, 'password': PASSWORD}, headers=h)
        assert r.status_code == 201, r.text
        token = None
        for _ in range(100):
            if self.outbox.exists():
                for line in self.outbox.read_text().splitlines()[-400:]:
                    v = json.loads(line)
                    if v['email'] == email and v['purpose'] == 'verification':
                        token = v['token']
            if token:
                break
            await asyncio.sleep(0.1)
        assert token, 'verification token missing'
        assert (await self.c.post('/api/v1/auth/verify', json={'token': token}, headers=h)).status_code == 200
        r = await self.c.post('/api/v1/auth/login', data={'username': email, 'password': PASSWORD}, headers=h)
        assert r.status_code == 200, r.text
        self.headers = {'Authorization': 'Bearer ' + r.json()['access_token']}
        ws = (await self.c.post('/api/v1/workspaces', json={'name': f'cap-{self.i}'}, headers={**h, **self.headers})).json()['id']
        self.root = f'/api/v1/workspaces/{ws}/research'
        record = method()
        assert (await self.req('method.create', 'POST', self.root + '/methods', json_body=record)).status_code == 200
        self.method_id = record['id']

    # ---------------- product actions ----------------
    async def summary(self, sid, kind='summary'):
        r = await self.req(kind, 'GET', f'{self.root}/sessions/{sid}/summary')
        return r.json() if r.status_code == 200 else None

    async def create_session(self):
        sid = 'session:' + uuid.uuid4().hex
        r = await self.req('session.create', 'POST', self.root + '/sessions', job=str(uuid.uuid4()),
                           json_body={'id': sid, 'name': f'{self.persona}-{self.i}', 'methodId': self.method_id, 'initialBalance': '10000', 'startPeriod': '2020-01'})
        if await self.wait_job('session.create', r) is None:
            self.trace.append('create_failed'); return None
        st = await self.summary(sid)
        await self.command(sid, 'ADVANCE', {'targetNs': self.src['startNs']}, st['revision'], kind='advance')
        self.trace.append('create_ok')
        return sid

    async def command(self, sid, kind_cmd, payload, revision, kind='command'):
        cmd = {'schemaVersion': 1, 'artifact': 'BTL-TICK-EXECUTION-COMMAND-1', 'sessionId': sid, 'commandId': 'command:' + uuid.uuid4().hex,
               'expectedRevision': revision, 'kind': kind_cmd, 'payload': payload}
        r = await self.req(kind, 'POST', f'{self.root}/sessions/{sid}/commands', json_body=cmd, job=str(uuid.uuid4()))
        if r.status_code in (200, 202):
            body = await self.wait_job(kind, r)
            return body is not None
        self.m.expected_refusals[f'{kind_cmd}:{r.status_code}'] += 1
        return False

    async def step(self, sid, ticks):
        st = await self.summary(sid)
        if not st:
            return None
        target = min(int(st['throughNs']) + ticks * STEP_NS, int(self.src['endNs']) - 1)
        if target <= int(st['throughNs']):
            self.trace.append('at_end'); return st
        ok = await self.command(sid, 'ADVANCE', {'targetNs': str(target)}, st['revision'], kind='step')
        self.m.ticks += ticks if ok else 0
        self.trace.append('step_ok' if ok else 'step_refused')
        return await self.summary(sid)

    async def play(self, sid, ticks):
        st = await self.summary(sid)
        if not st:
            return None
        target = min(int(st['throughNs']) + ticks * STEP_NS, int(self.src['endNs']) - 1)
        if target <= int(st['throughNs']):
            self.trace.append('at_end'); return st
        run, rev, seg = uuid.uuid4().hex, st['revision'], 0
        t0 = time.monotonic()
        while True:
            body = {'schemaVersion': 1, 'artifact': 'BTL-REPLAY-RUN-1', 'runId': run, 'segment': seg, 'sessionId': sid, 'expectedRevision': rev, 'targetNs': str(target)}
            r = await self.req('play', 'POST', f'{self.root}/sessions/{sid}/replay-run', json_body=body, job=str(uuid.uuid5(uuid.NAMESPACE_URL, f'{sid}:{run}:{seg}')))
            res = await self.wait_job('play', r)
            if res is None:
                self.trace.append('play_failed'); return None
            nxt = (res.get('result') or {}).get('continuationJobId')
            if not nxt:
                break
            seg += 1
            rev = (res.get('result') or {}).get('revision', rev)
            # follow the server-chained continuation job
            while True:
                await asyncio.sleep(0.5)
                j = await self.req('play.poll', 'GET', f'{self.root}/jobs/{nxt}')
                b = j.json() if j.status_code == 200 else {}
                if b.get('state') == 'SUCCEEDED':
                    res = b; nxt = (b.get('result') or {}).get('continuationJobId')
                    if not nxt:
                        break
                    continue
                if b.get('state') not in ('QUEUED', 'RUNNING'):
                    self.trace.append('play_failed'); return None
            break
        self.m.lat['play.complete'].append(time.monotonic() - t0)
        self.m.ticks += ticks
        self.trace.append('play_ok')
        return await self.summary(sid)

    async def jump(self, sid):
        st = await self.summary(sid)
        if not st:
            return None
        body = {'schemaVersion': 1, 'artifact': 'BTL-JUMP-NEXT-EVENT-1', 'requestId': uuid.uuid4().hex, 'sessionId': sid, 'expectedRevision': st['revision'], 'timeframe': '1m'}
        r = await self.req('jump', 'POST', f'{self.root}/sessions/{sid}/jump-next-event', json_body=body, job=str(uuid.uuid4()))
        res = await self.wait_job('jump', r)
        ok = res is not None
        self.m.jumps += 1 if ok else 0
        self.trace.append('jump_ok' if ok else 'jump_refused')
        return await self.summary(sid)

    async def order(self, sid, side='LONG', market=True, qty='0.1', entry='2000', sl=None, tp=None, order_id=None, dup=False):
        st = await self.summary(sid)
        if not st:
            return None
        rid = order_id or 'order:' + uuid.uuid4().hex
        draft = dict(side=side, orderType='MARKET' if market else 'LIMIT', workflow='QUICK' if market else 'PLANNED', entry=entry if not market else '2000', quantity=qty,
                     sl=sl, tp=tp, riskPercent='1', observations=[])
        review = dict(sessionId=sid, requestId=rid, expectedRevision=st['revision'], planId=None if market else 'plan:cap', planRevision=None if market else 0, draft=draft)
        r = await self.req('order.review', 'POST', f'{self.root}/reviews', json_body=review)
        if r.status_code != 200:
            self.m.expected_refusals[f'review:{r.status_code}'] += 1
            self.trace.append('review_refused'); return None
        confirm = {'reviewId': rid, 'reviewHash': r.json()['reviewHash']}
        c = await self.req('order.confirm', 'POST', f'{self.root}/sessions/{sid}/confirm', json_body=confirm, job=str(uuid.uuid4()))
        if dup:                                   # double click: identical retry must not create a second order
            await self.req('order.confirm', 'POST', f'{self.root}/sessions/{sid}/confirm', json_body=confirm, job=str(uuid.uuid4()))
        ok = c.status_code in (200, 202)
        if c.status_code == 202:
            ok = (await self.wait_job('order.confirm', c)) is not None
        if not ok:
            self.m.expected_refusals[f'confirm:{c.status_code}'] += 1
        self.trace.append('order_ok' if ok else 'order_refused')
        return rid if ok else None

    async def close(self, sid, order_id):
        st = await self.summary(sid)
        if not st:
            return False
        ok = await self.command(sid, 'CLOSE', {'orderId': order_id, 'quantity': None}, st['revision'], kind='close')
        self.trace.append('close_ok' if ok else 'close_refused')
        return ok

    async def cancel(self, sid, order_id):
        st = await self.summary(sid)
        if not st:
            return False
        ok = await self.command(sid, 'CANCEL', {'orderId': order_id}, st['revision'], kind='cancel')
        self.trace.append('cancel_ok' if ok else 'cancel_refused')
        return ok

    async def reads(self, sid, which):
        if which == 'view':
            await self.req('view', 'GET', f'{self.root}/sessions/{sid}')
        elif which == 'journal':
            await self.req('journal', 'GET', f'{self.root}/sessions/{sid}/journal/pages?limit=32')
        elif which == 'analytics':
            await self.req('analytics', 'GET', f'{self.root}/sessions/{sid}/analytics/pages?limit=32&offset=0')
        elif which == 'export':
            await self.req('export.csv', 'GET', f'{self.root}/sessions/{sid}/export?format=csv')
        elif which == 'pdf':
            r = await self.req('export.pdf', 'GET', f'{self.root}/sessions/{sid}/export?format=pdf')
            if r.status_code >= 400:
                self.m.unsupported['pdf'] += 1
        elif which == 'sessions':
            await self.req('sessions.list', 'GET', f'{self.root}/sessions')
        elif which == 'chart':
            tf = self.rng.choice(['1m', '5m', '15m', '1h', '4h'])          # always drawn: the action sequence must not depend on other traders
            if not self.chart_unsupported:
                r = await self.req('chart-bars', 'GET', f'{self.root}/sessions/{sid}/chart-bars?timeframe={tf}&limit=512')
                if r.status_code >= 400:
                    self.chart_unsupported = True
                    self.m.unsupported['chart-bars'] += 1
            await self.req('view', 'GET', f'{self.root}/sessions/{sid}')
        elif which == 'entitlements':
            await self.req('entitlements', 'GET', f'{self.root}/entitlements')

    async def finish(self, sid):
        st = await self.summary(sid, 'final.summary')
        jr = await self.req('final.journal', 'GET', f'{self.root}/sessions/{sid}/journal/pages?limit=32')
        orders = []
        if jr.status_code == 200:
            orders = [(o['status'], o.get('entryPrice'), o.get('exitPrice'), o.get('net')) for o in jr.json().get('orders', [])]
        if st:
            self.facts.append(dict(balance=st['balance'], trades=st['completedTrades'], net=st['netCashChange'], orders=sorted(orders, key=str)))
            self.m.trades += int(st['completedTrades'])

    # ---------------- personas ----------------
    async def script(self):
        """One bounded script instance; returns facts + trace hash."""
        n = ACTIONS_PER_SCRIPT[self.persona]
        sid = await self.create_session()
        if not sid:
            return None
        sessions, openo = [sid], []
        if self.persona == 'swing':
            await self.order(sid, 'LONG', market=False, qty='0.01', entry='1998.90', sl='1998.00', tp='1999.50')
        for k in range(n):
            await self.think()
            p, s = self.persona, self.rng
            if p == 'swing':
                a = s.choice(['view', 'play', 'step', 'jump', 'journal', 'analytics', 'view'])
                if a == 'play': await self.play(sid, s.randint(500, 3000))
                elif a == 'step': await self.step(sid, s.randint(5, 20))
                elif a == 'jump': await self.jump(sid)
                else: await self.reads(sid, a)
            elif p == 'scalper':
                o = await self.order(sid, s.choice(['LONG', 'SHORT']), qty='0.1')
                await self.step(sid, 1)
                await self.step(sid, s.randint(1, 5))
                if o: await self.close(sid, o)
                await self.step(sid, 1)
                if k % 6 == 5: await self.reads(sid, 'view')
            elif p == 'impulsive':
                a = s.choice(['buy', 'sell', 'close', 'cancel', 'dup', 'bad_close', 'step', 'view'])
                if a in ('buy', 'sell', 'dup'):
                    o = await self.order(sid, 'LONG' if a == 'buy' else 'SHORT', qty='0.1', dup=(a == 'dup'))
                    if o: openo.append(o)
                    await self.step(sid, 1)
                elif a == 'close' and openo: await self.close(sid, openo.pop())
                elif a == 'cancel':
                    o = await self.order(sid, 'LONG', market=False, qty='0.01', entry='1990', sl='1985', tp='1995')
                    if o: await self.cancel(sid, o)
                elif a == 'bad_close': await self.close(sid, 'order:' + uuid.uuid4().hex)          # valid refusal path
                elif a == 'step': await self.step(sid, s.randint(1, 8))
                else: await self.reads(sid, 'view')
            elif p == 'averaging':
                if len(openo) < 4:
                    o = await self.order(sid, 'LONG', qty='0.1')
                    if o: openo.append(o)
                    await self.step(sid, s.randint(2, 10))
                else:
                    for o in openo: await self.close(sid, o)
                    openo = []
                    await self.step(sid, 1)
            elif p == 'hedging':
                a = await self.order(sid, 'LONG', qty='0.1')
                b = await self.order(sid, 'SHORT', qty='0.1')          # simultaneous opposite side: accepted or validly refused
                await self.step(sid, s.randint(2, 8))
                for o in (a, b):
                    if o: await self.close(sid, o)
                await self.step(sid, 1)
            elif p == 'multipair':
                if len(sessions) < 3 and s.random() < 0.3:
                    ns = await self.create_session()
                    if ns: sessions.append(ns)
                sid = s.choice(sessions)
                a = s.choice(['chart', 'chart', 'play', 'step', 'view', 'journal'])
                if a == 'play': await self.play(sid, s.randint(200, 1500))
                elif a == 'step': await self.step(sid, s.randint(3, 15))
                else: await self.reads(sid, a)
            else:                                                      # researcher
                a = s.choice(['journal', 'analytics', 'export', 'pdf', 'sessions', 'chart', 'play', 'entitlements'])
                if a == 'play': await self.play(sid, s.randint(1000, 4000))
                else: await self.reads(sid, a)
        for sid_ in sessions:
            await self.finish(sid_)
        return dict(trace=hashlib.sha256('|'.join(self.trace).encode()).hexdigest()[:16], facts=self.facts)


async def lag_probe(samples, stop):
    while not stop.is_set():
        t = time.monotonic(); await asyncio.sleep(0.1); samples.append(max(0.0, time.monotonic() - t - 0.1))


async def run_trader(i, persona, offset, a, outbox, client, metrics, source, results, deadline):
    ip = f'10.{(i >> 8) & 255}.{i & 255}.{7 + (i % 200)}'
    instance = 0
    t = None
    try:
        while True:
            seed = a.seed * 1000 + PERSONAS.index(persona) * 10 + ((instance + offset) % a.seed_variants)
            t = Trader(client, outbox, i, persona, seed, metrics, source, a.think_scale, ip)
            if instance == 0:
                await t.setup()
            else:                                    # reuse account of the first instance
                t.headers, t.root, t.method_id = first.headers, first.root, first.method_id
            if instance == 0:
                first = t
            res = await t.script()
            results.append(dict(persona=persona, trader=i, seed=seed, instance=instance, result=res))
            instance += 1
            if a.mode == 'ref' or time.monotonic() >= deadline:
                break
    except Exception as error:                        # noqa: BLE001 - reported, never hidden
        results.append(dict(persona=persona, trader=i, error=f'{type(error).__name__}: {str(error)[:300]}'))


async def main_async(a):
    source = json.loads(Path(a.source).read_text())
    mix = []
    for part in a.spec.split(','):
        name, count = part.split(':')
        mix += [name] * int(count)
    metrics, results, lag = Metrics(), [], []
    limits = httpx.Limits(max_connections=400, max_keepalive_connections=200)
    stop = asyncio.Event()
    t_start = time.monotonic()
    cpu0 = time.process_time()
    async with httpx.AsyncClient(base_url=f'http://127.0.0.1:{a.port}', timeout=httpx.Timeout(120.0), limits=limits) as client:
        probe = asyncio.create_task(lag_probe(lag, stop))
        deadline = time.monotonic() + a.duration
        tasks = []
        seen = collections.Counter()
        for i, persona in enumerate(mix):
            offset = seen[persona]; seen[persona] += 1
            tasks.append(asyncio.create_task(run_trader(i, persona, offset, a, Path(a.outbox), client, metrics, source, results, deadline)))
            await asyncio.sleep(a.ramp / max(1, len(mix)))          # staggered arrival over the ramp
        await asyncio.gather(*tasks)
        stop.set(); await probe
    out = dict(spec=a.spec, mode=a.mode, seed=a.seed, durationRequested=a.duration, wallSeconds=round(time.monotonic() - t_start, 1),
               traders=len(mix), metrics=metrics.summary(), results=results,
               generator=dict(cpuSeconds=round(time.process_time() - cpu0, 2), peakRssMb=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
                              eventLoopLagMs=dict(p50=round(1000 * (pct(lag, 50) or 0), 1), p95=round(1000 * (pct(lag, 95) or 0), 1), max=round(1000 * max(lag or [0]), 1))))
    Path(a.out).write_text(json.dumps(out, indent=1, default=str))
    print('DRIVER_DONE', a.out, flush=True)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, required=True); ap.add_argument('--source', required=True); ap.add_argument('--outbox', required=True)
    ap.add_argument('--spec', required=True, help='persona:count,... e.g. swing:2,scalper:2')
    ap.add_argument('--mode', choices=('ref', 'load'), default='load'); ap.add_argument('--seed', type=int, default=1); ap.add_argument('--seed-variants', type=int, default=3)
    ap.add_argument('--duration', type=float, default=120); ap.add_argument('--ramp', type=float, default=10); ap.add_argument('--think-scale', type=float, default=1.0)
    ap.add_argument('--out', required=True)
    asyncio.run(main_async(ap.parse_args()))
