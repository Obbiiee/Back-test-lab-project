"""Evaluate one stage against the PROPOSED (not owner-approved) SLO and financial parity vs the idle-server references. Exit 0 = PASS, 1 = FAIL."""
import glob, json, sys
from pathlib import Path

RUNS = Path.home() / 'bench' / 'cap' / 'runs'
SLO = dict(journalP95=8.0, analyticsP95=8.0, jumpAcceptP95=2.0, stepAcceptP95=2.0, summaryP95=2.0, queueWaitP95=5.0, genLagP95Ms=50.0, genCpuMax=0.8, refusalRate=0.01, maxQueuedFence=16)

def refs():
    table = {}
    for p in ('swing', 'scalper', 'impulsive', 'averaging', 'hedging', 'multipair', 'researcher'):
        fs = [f for f in sorted(glob.glob(str(RUNS / f'ref-{p}-*/result.json'))) if 'idleBaseline' in json.load(open(f))]
        d = json.load(open(fs[-1]))
        for r in d['driver']['results']:
            if r.get('result'):
                table[(r['persona'], r['seed'])] = r['result']
    return table

def analyze(path):
    d = json.load(open(path)); dr = d.get('driver', {}); m = dr.get('metrics', {}); lat = m.get('latencySeconds', {})
    ref = refs(); ok_par, bad_par, compared, errors = 0, [], 0, []
    for r in dr.get('results', []):
        if 'error' in r: errors.append(r); continue
        if not r.get('result'): errors.append(dict(r, error='script returned None')); continue
        compared += 1
        want = ref.get((r['persona'], r['seed']))
        if want == r['result']: ok_par += 1
        else: bad_par.append((r['persona'], r['seed']))
    p95 = lambda k: (lat.get(k) or {}).get('p95')
    reqs = max(1, m.get('requests', 1)); adm = sum((m.get('admissionRefusals') or {}).values())
    q = d.get('queue', {}); gen = dr.get('generator', {}); secs = max(1, d.get('wallSeconds', 1))
    checks = {
        'parity': not bad_par and not errors, 'journalP95': (p95('journal') or 0) <= SLO['journalP95'], 'analyticsP95': (p95('analytics') or 0) <= SLO['analyticsP95'],
        'jumpAcceptP95': (p95('jump') or 0) <= SLO['jumpAcceptP95'], 'stepAcceptP95': (p95('step') or 0) <= SLO['stepAcceptP95'], 'summaryP95': (p95('summary') or 0) <= SLO['summaryP95'],
        'queueWaitP95': (q.get('waitSeconds', {}).get('p95') or 0) <= SLO['queueWaitP95'], 'generatorLag': (gen.get('eventLoopLagMs', {}).get('p95') or 0) <= SLO['genLagP95Ms'],
        'generatorCpu': gen.get('cpuSeconds', 0) / secs <= SLO['genCpuMax'], 'admissionRate': adm / reqs <= SLO['refusalRate'], 'noGate': not d.get('stoppedByGate'),
        'queueFence': q.get('maxQueued', 0) <= SLO['maxQueuedFence'] and not any(k for k in (q.get('jobStates') or {}) if k not in ('SUCCEEDED',) and (q['jobStates'][k] > 0)),
    }
    idle = d['idleBaseline']['sutCpuSeconds'] / d['idleBaseline']['seconds']
    out = dict(name=d['name'], traders=d['driver']['traders'], wall=d['wallSeconds'], scripts=compared, parityEqual=ok_par, parityBad=bad_par[:5], errors=[e.get('error') for e in errors][:4],
               sutCpuCores=round(d['sut']['cpuSecondsTotal'] / secs, 2), sutNetCores=round(d['sut']['cpuSecondsTotal'] / secs - idle, 2), throttled=d['sut'].get('nrThrottled'), sutPeakMb=d['sut']['memoryPeakMb'],
               byComponent=d['sut']['byComponentCpuSeconds'], p95={k: p95(k) for k in ('journal', 'analytics', 'jump', 'step', 'summary', 'view', 'export.csv', 'step.complete', 'play.complete', 'order.confirm', 'close')},
               queue=dict(maxQueued=q.get('maxQueued'), maxAge=q.get('maxOldestQueuedAgeSeconds'), wait=q.get('waitSeconds'), states=q.get('jobStates')),
               admissionRefusals=m.get('admissionRefusals'), recoveries=m.get('clientRecoveries'), requests=m.get('requests'), reqPerSec=round(reqs / secs, 1), expectedRefusals=m.get('expectedRefusals'),
               generator=gen, hostMaxCpu=max([s['hostCpu'] or 0 for s in d.get('hostSeries', [])] or [0]), hostMinMemGiB=min([s['memAvailGiB'] for s in d.get('hostSeries', [])] or [0]),
               stoppedByGate=d.get('stoppedByGate'), checks=checks, PASS=all(checks.values()))
    return out

if __name__ == '__main__':
    r = analyze(sys.argv[1]); print(json.dumps(r, indent=1, default=str)); sys.exit(0 if r['PASS'] else 1)
