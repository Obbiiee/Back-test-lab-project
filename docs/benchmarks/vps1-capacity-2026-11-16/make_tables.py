"""Builds the comparison tables for RIKSORA-VPS1-MAXIMUM-ECONOMIC-CAPACITY.md from ~/bench/cap/runs/*/analysis.json (reproducible; no number is typed by hand)."""
import glob, json, re, shutil, sys
from pathlib import Path
RUNS = Path.home() / 'bench' / 'cap' / 'runs'
OUT = Path(__file__).resolve().parent
CONFIG = {
 'lad-t3': 'baseline (3 slots, DB 12, API 8)', 'm0': 'baseline (3 slots, DB 12, API 8)', 'm1': 'client request reduction', 'm2': 'timeline cache 64', 'm3': 'DB budget 16',
 'm4': 'DB budget 24', 'm5': 'DB 16 + API 12/24', 'm6': 'DB 24 + API 16/32', 'm7': 'DB 32 + API 24/48', 'm8': 'pool (BEFORE advisory-lock fix; invalid)', 'm9': 'pool+client+cache (BEFORE fix; invalid)',
 'm10': '4 slots + DB 24 + API 16', 'm11': '6 slots + DB 24 + API 16', 'm8b': 'DB pool only (after fix)', 'm12': 'pool+client+cache64+DB 24+API 16',
 'off6': 'official 6-core budget, m6 config', 'off6sus': 'official 6-core, sustained 15 min, m6 config', 'off6rush': 'official 6-core, rush, m6 config', 'off6w4': 'official 6-core, 4 workers, m6 config',
 'fin1': 'FINAL A: 6 slots + 4 workers + DB 24 + API 16 (6-core budget)', 'fin2': 'FINAL B: A + pool + client + cache 64 (6-core budget)', 'finrush': 'FINAL rush', 'sus-t3': 'baseline sustained 15 min', 'sus-u3': 'baseline sustained 15 min'}
rows = []
for f in sorted(glob.glob(str(RUNS / '*/analysis.json'))):
    name = Path(f).parent.name
    m = re.match(r'(.+)-n(\d+)-2026\d{4}-\d{6}$', name)
    if not m: continue
    tag, n = m.group(1), int(m.group(2)); a = json.load(open(f))
    shutil.copy(f, OUT / f'{tag}-n{n}.analysis.json')
    ad = a.get('admissionRefusals') or {}; req = a.get('requests') or 1; q = a['queue']; p = a.get('latencyP50P95P99') or {}
    bad = [k for k, v in a['checks'].items() if not v]
    rows.append(dict(tag=tag, n=n, pass_=a['PASS'], bad=bad, cores=a['sutCpuCores'], adm=sum(ad.values()) / req, qwait=(q.get('wait') or {}).get('p95'), qcap=ad.get('QUEUE_CAPACITY', 0),
                     summary=(p.get('summary') or [None, None])[1], journal=(p.get('journal') or [None, None])[1], jump=(p.get('jump') or [None, None])[1], step=(p.get('step') or [None, None])[1],
                     parity=f"{a['parityEqual']}/{a['scripts']}", success=a.get('journeySuccessRate'), pg=a.get('pgConnectionsMax'), util=a.get('directSlotUtilisation'), wall=a['wall']))
def fmt(x, d=2): return '-' if x is None else (f'{x:.{d}f}' if isinstance(x, float) else str(x))
lines = ['| Config | Tag | N | Result | Failed checks | SUT cores | Refusal rate | QUEUE_CAPACITY | Queue wait p95 s | summary p95 s | journal p95 s | jump p95 s | step p95 s | Parity | Journey success |', '|---|---|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|']
order = ['lad-t3', 'm0', 'm1', 'm2', 'm3', 'm4', 'm5', 'm6', 'm7', 'm10', 'm11', 'm8', 'm9', 'm8b', 'm12', 'sus-u3', 'sus-t3', 'off6', 'off6sus', 'off6rush', 'off6w4', 'fin1', 'fin2', 'finrush']
for tag in order + sorted({r['tag'] for r in rows} - set(order)):
    for r in sorted([x for x in rows if x['tag'] == tag], key=lambda x: x['n']):
        lines.append(f"| {CONFIG.get(tag, tag)} | {tag} | {r['n']} | {'PASS' if r['pass_'] else 'FAIL'} | {', '.join(r['bad']) or '-'} | {fmt(r['cores'])} | {r['adm']:.2%} | {r['qcap']} | {fmt(r['qwait'])} | {fmt(r['summary'])} | {fmt(r['journal'])} | {fmt(r['jump'])} | {fmt(r['step'])} | {r['parity']} | {fmt(r['success'])} |")
(OUT / 'tables.md').write_text('\n'.join(lines) + '\n')
print(len(rows), 'stages written to', OUT / 'tables.md')
