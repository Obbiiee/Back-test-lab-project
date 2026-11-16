// Deterministic SYNTHETIC UI-QA harness for the tick-alpha HTTP contract (NOT a trading engine).
// It exists only so browser QA can run without PostgreSQL. It reveals a seeded synthetic
// tick stream with the same bounded-advance semantics as the real timeline (64 groups per
// call, pendingTargetNs must be resumed with the SAME target). Nothing here is evidence of
// backend/financial correctness; those gates belong to the Python test suite.
import http from 'node:http';

const PORT = Number(process.env.MOCK_PORT || 5188);
const START_NS = BigInt(Date.UTC(2020, 0, 1, 0, 0, 0)) * 1000000n;
const MAX_TICKS = 400000;
const hash = n => { let x = (n ^ 0x9e3779b9) >>> 0; x = Math.imul(x ^ (x >>> 16), 0x85ebca6b) >>> 0; x = Math.imul(x ^ (x >>> 13), 0xc2b2ae35) >>> 0; return (x ^ (x >>> 16)) >>> 0; };
const open = ms => { const d = new Date(ms), w = d.getUTCDay(), h = d.getUTCHours();
  if (w === 6) return false; if (w === 5 && h >= 22) return false; if (w === 0 && h < 22) return false; return true; };
const times = [], mids = []; let seq = 0;
function ensure(n) {
  let ms = times.length ? Number(times.at(-1) / 1000000n) : Number(START_NS / 1000000n) - 1000, price = mids.length ? mids.at(-1) : 2000;
  while (times.length < n) {
    ms += 1000;
    while (!open(ms)) ms += 60000;
    const i = seq++;
    if (hash(i * 7 + 1) % 10 >= 6) continue;
    price = Math.max(1000, price + ((hash(i + 99) % 2001) - 1000) / 10000);
    times.push(BigInt(ms) * 1000000n); mids.push(Math.round(price * 100) / 100);
  }
}
ensure(MAX_TICKS);
const sessions = new Map(), methods = new Map([['m:free', { id: 'm:free', name: 'Free Style test', kind: 'FREE_STYLE', checklistOn: false, conditions: [], riskPercent: null, rr: null }]]);
const TF = { '1m': 60, '3m': 180, '5m': 300, '15m': 900, '30m': 1800, '1h': 3600, '2h': 7200, '4h': 14400, D: 86400 };
const SPREAD = 0.2;
const quote = s => { const i = s.next - 1; if (i < 0) return null; const t = times[i]; return { timeNs: String(t), bid: (mids[i] - SPREAD / 2).toFixed(2), ask: (mids[i] + SPREAD / 2).toFixed(2) }; };
function chart(s, tf) {
  const dur = BigInt(TF[tf]), bars = [];
  for (let i = Math.max(0, s.next - 30000); i < s.next; i++) {
    const b = Number(times[i] / 1000000000n / dur * dur), m = mids[i].toFixed(2), last = bars.at(-1);
    if (last && last.time === b) { last.high = Math.max(last.high, m); last.low = Math.min(last.low, m); last.close = m; }
    else bars.push({ time: b, open: m, high: m, low: m, close: m });
  }
  const out = bars.slice(-512), through = Number(BigInt(s.through) / 1000000000n);
  if (out.length) out.at(-1).incomplete = through < out.at(-1).time + Number(dur) - 1;
  return { schemaVersion: 1, timeframe: tf, priceBasis: 'EXACT_REVEALED_MID_DISPLAY_ONLY', volumeAvailable: false, windowStartGroup: '0', candles: out.map(b => ({ ...b, high: String(b.high), low: String(b.low) })) };
}
function metrics(s) {
  const c = s.completed, wins = c.filter(o => Number(o.net) > 0).length, losses = c.filter(o => Number(o.net) < 0).length;
  const r = (n, d) => ({ numerator: String(n), denominator: String(d) });
  return { tradeCount: c.length, wins, losses, breakeven: c.length - wins - losses, winRate: c.length ? r(wins, c.length) : null, averageWin: null, averageLoss: null, expectancy: null, profitFactor: null,
    maxWinStreak: 0, maxLossStreak: 0, maxDrawdown: '0.00', maxDrawdownRate: null, unresolved: 0, expired: 0, averageR: null, rEligible: 0, rExcluded: 0, equityWindowStart: 0 };
}
function view(s, tf) {
  const q = quote(s);
  const annotations = [...s.completed, ...s.orders].filter(o => o.entryTimeNs).map(o => ({ eventId: 'fill:' + o.id, timeNs: o.entryTimeNs, price: o.entryPrice, side: o.side, kind: 'ENTRY_FILL', chronologyLimited: false }));
  return { schemaVersion: 1, artifact: 'BTL-LOCAL-SESSION-VIEW-1', label: 'SYNTHETIC / TEST ONLY', metadata: { id: s.id, name: s.name, startPeriod: '2020-01' },
    method: methods.get(s.methodId), quote: q, events: [], eventWindowStart: 0,
    state: { revision: String(s.revision), throughNs: s.through, nextGroupIndex: String(s.next), unresolved: false, ended: s.next >= times.length, balance: s.balance, initialBalance: s.initial,
      profile: { tickSize: '0.01' }, profileHash: 'p', eventHash: 'e' + s.revision, datasetId: 'mock', datasetVersion: 'mock-1' },
    chart: chart(s, tf),
    analysis: { status: 'COMPLETE', annotations, orders: s.orders, completed: s.completed, equity: [], metrics: metrics(s),
      account: { balance: s.balance, netCashChange: '0.00', commission: '0.00', unrealizedIndicative: null, equityIndicative: null }, provenance: { eventHead: 'e' + s.revision, revision: String(s.revision) } } };
}
function reveal(s, target) {
  if (s.pending && s.pending !== target) throw new Error('ADVANCE_IN_PROGRESS');
  if (BigInt(target) < BigInt(s.through)) throw new Error('BACKWARD_ADVANCE');
  let groups = 0, i = s.next;
  while (i < times.length && times[i] <= BigInt(target) && groups < 64) { s.last = times[i]; i++; groups++; settle(s, i - 1); }
  s.next = i;
  const done = !(i < times.length && times[i] <= BigInt(target));
  s.through = done ? target : String(s.last); s.pending = done ? null : target; s.revision++;
  return done;
}
function settle(s, i) {
  const bid = mids[i] - SPREAD / 2, ask = mids[i] + SPREAD / 2;
  for (const o of [...s.orders]) {
    if (o.status === 'PENDING' && (o.orderType === 'MARKET' || (o.orderType === 'LIMIT' && (o.side === 'LONG' ? ask <= +o.entry : bid >= +o.entry)))) { o.status = 'ACTIVE'; o.entryPrice = (o.side === 'LONG' ? ask : bid).toFixed(2); o.entryTimeNs = String(times[i]); o.entryFillRef = 'fill:' + o.id; }
    else if (o.status === 'ACTIVE') {
      const px = o.side === 'LONG' ? bid : ask, hitSl = o.sl && (o.side === 'LONG' ? px <= +o.sl : px >= +o.sl), hitTp = o.tp && (o.side === 'LONG' ? px >= +o.tp : px <= +o.tp);
      if (hitSl || hitTp || o.exitRequested) close(s, o, px, times[i], hitSl ? 'SL' : hitTp ? 'TP' : 'MANUAL');
    }
  }
}
function close(s, o, px, t, reason) {
  const gross = ((o.side === 'LONG' ? px - +o.entryPrice : +o.entryPrice - px) * 100 * +o.quantity);
  Object.assign(o, { status: 'CLOSED', exitPrice: px.toFixed(2), exitTimeNs: String(t), exitReason: reason, gross: gross.toFixed(2), net: gross.toFixed(2), commission: '0.00', remaining: '0', exitFillRef: 'exit:' + o.id, mae: null, mfe: null, durationNs: String(t - BigInt(o.entryTimeNs)) });
  s.orders = s.orders.filter(x => x !== o); s.completed.push(o); s.balance = (+s.balance + gross).toFixed(2);
}
const reviews = new Map();
const send = (res, code, body) => { res.writeHead(code, { 'content-type': 'application/json', 'access-control-allow-origin': '*', 'access-control-allow-headers': '*', 'access-control-allow-methods': '*' }); res.end(JSON.stringify(body)); };
const catalog = () => ({ schemaVersion: 1, label: 'SYNTHETIC / TEST ONLY', startPeriod: '2020-01', methods: [...methods.values()], sessions: [...sessions.values()].map(s => ({ id: s.id, name: s.name, methodId: s.methodId })) });
let delay = 0, failN = 0, failCode = 'RATE_LIMITED';
http.createServer(async (req, res) => {
  if (req.method === 'OPTIONS') return send(res, 204, {});
  const url = new URL(req.url, 'http://x'); let body = ''; for await (const c of req) body += c; body = body ? JSON.parse(body) : undefined;
  const path = url.pathname.replace('/api/v1/tick-alpha', '');
  if (delay) await new Promise(r => setTimeout(r, delay));
  try {
    let m;
    if (path === '/__fail') { failN = Number(url.searchParams.get('n') || 0); failCode = url.searchParams.get('code') || 'RATE_LIMITED'; return send(res, 200, { schemaVersion: 1, failN }); }
    if (path === '/__delay') { delay = Number(url.searchParams.get('ms') || 0); return send(res, 200, { schemaVersion: 1, delay }); }
    if (path === '/catalog') return send(res, 200, catalog());
    if (path === '/methods') { methods.set(body.id, { ...body }); return send(res, 200, { schemaVersion: 1 }); }
    if (path === '/sessions') { const s = { id: body.id, name: body.name, methodId: body.methodId, balance: body.initialBalance, initial: body.initialBalance, revision: 1, next: 0, through: String(START_NS), pending: null, orders: [], completed: [], last: START_NS };
      sessions.set(s.id, s); return send(res, 200, view(s, '1m')); }
    if (path === '/reviews') { const s = sessions.get(body.sessionId), d = body.draft; const command = { commandId: 'cmd:' + body.requestId, payload: { side: d.side, orderType: d.orderType, entry: d.entry, sl: d.sl ?? null, tp: d.tp ?? null, quantity: d.quantity ?? '0.1', riskPercent: d.riskPercent ?? null, observations: d.observations ?? [] } };
      reviews.set(command.commandId, { sessionId: s.id, command }); return send(res, 200, { schemaVersion: 1, reviewHash: 'h:' + command.commandId, review: { command, riskBasis: s.balance, researchRisk: null } }); }
    if ((m = path.match(/^\/sessions\/([^/]+)\/(view|confirm|commands|journal|bootstrap)$/))) {
      const s = sessions.get(decodeURIComponent(m[1])); if (!s) return send(res, 404, { detail: 'NOT_FOUND' });
      if (m[2] === 'view') return send(res, 200, view(s, body?.timeframe || '1m'));
      if (m[2] === 'journal') return send(res, 200, { schemaVersion: 1, provenance: { revision: String(s.revision) }, notes: [], orders: [...s.orders, ...s.completed].map(o => ({ id: o.id, side: o.side, status: o.status, entryFillRef: o.entryFillRef ?? null, exitFillRef: o.exitFillRef ?? null })) });
      if (m[2] === 'confirm') { const r = reviews.get(body.reviewId), p = r.command.payload; s.orders.push({ id: 'order:' + (s.orders.length + s.completed.length + 1), status: 'PENDING', side: p.side, orderType: p.orderType, entry: p.entry, sl: p.sl, tp: p.tp, quantity: p.quantity, remaining: p.quantity, entryPrice: null, entryTimeNs: null });
        s.revision++; return send(res, 200, { schemaVersion: 1 }); }
      if (m[2] === 'commands') {
        if (failN > 0) { failN--; return send(res, 429, { detail: failCode }); }
        if (String(body.expectedRevision) !== String(s.revision)) return send(res, 409, { detail: 'REFUSED_STALE_REVISION' });
        if (body.kind === 'ADVANCE' || body.kind === 'SEEK') { if (body.kind === 'SEEK' && BigInt(body.payload.targetNs) < BigInt(s.through)) return send(res, 409, { detail: 'REFUSED_REWIND_REQUIRES_FORK' }); let done = reveal(s, body.payload.targetNs); while (body.kind === 'SEEK' && !done) done = reveal(s, body.payload.targetNs); /* real timeline.seek loops internally */ return send(res, 200, { schemaVersion: 1, replay: { throughNs: s.through, exhaustedThroughBoundary: done } }); }
        const o = s.orders.find(x => x.id === body.payload.orderId);
        if (body.kind === 'CANCEL' && o) s.orders = s.orders.filter(x => x !== o); if (body.kind === 'CLOSE' && o) o.exitRequested = true; s.revision++; return send(res, 200, { schemaVersion: 1 });
      }
      return send(res, 200, { schemaVersion: 1 });
    }
    return send(res, 404, { detail: 'NOT_FOUND ' + path });
  } catch (e) { return send(res, 409, { detail: e.message }); }
}).listen(PORT, '127.0.0.1', () => console.log('mock tick-alpha on', PORT));
