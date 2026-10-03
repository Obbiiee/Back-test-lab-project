import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { aggregateCandles, bucketTime, TIMEFRAMES } from '../src/market/candles.js';
import { advanceReplayIndex, forwardChange, syncCandleSeries } from '../src/market/replayTransitions.js';
import { PlaybackScheduler, PLAYBACK_SPEEDS } from '../src/market/PlaybackScheduler.js';
import { settleReplay } from '../src/trading/replaySettlement.js';
import { initialAccount, placeOrder, processCandle } from '../src/trading/simulator.js';
import { IndicatorEngine } from '../src/indicators/IndicatorEngine.js';
import { productionRegistry } from '../src/indicators/productionRegistry.js';

const bars = Array.from({ length: 2400 }, (_, i) => {
  const close = 2000 + Math.sin(i / 7) * 9 + i / 500;
  return Object.freeze({ time: 1717372800 + i * 60, open: close - .1, high: close + 2, low: close - 2, close, volume: i % 80 });
});
const forward = { kind: 'forward' };
function referenceIndex(bars, index, frame, direction) {
  if (index < 0) return index;
  const bucket = bucketTime(bars[index].time, frame); let next = index;
  if (direction > 0) {
    while (next < bars.length - 1 && bucketTime(bars[next].time, frame) === bucket) next++;
    const nextBucket = bucketTime(bars[next].time, frame);
    while (next < bars.length - 1 && bucketTime(bars[next + 1].time, frame) === nextBucket) next++;
  } else {
    next = Math.max(0, next - 1); const previous = bucketTime(bars[next].time, frame);
    while (next > 0 && bucketTime(bars[next - 1].time, frame) === previous) next--;
  }
  return next;
}
for (const frame of Object.keys(TIMEFRAMES)) for (const index of [-1, 0, 1, 29, 150, 2300, 2399]) for (const direction of [-1, 1]) {
  assert.equal(advanceReplayIndex(bars, index, frame, direction), referenceIndex(bars, index, frame, direction));
}
function series() {
  return { points: [], full: 0, updates: 0,
    setData(points) { this.points = structuredClone(points); this.full++; },
    update(point) { const last = this.points.at(-1); assert.ok(!last || point.time >= last.time); if (last?.time === point.time) this.points[this.points.length - 1] = { ...point }; else this.points.push({ ...point }); this.updates++; } };
}
function referenceAccount(current, candles) {
  const quote = candles.at(-1); if (!quote) return current;
  if (quote.time < current.lastTime && !current.positions.length && !current.orders.length && !current.trades.length) return { ...current, lastTime: quote.time };
  let result = current;
  for (const candle of candles) if (current.lastTime != null && candle.time > current.lastTime) result = processCandle(result, candle);
  return current.lastTime == null ? { ...current, lastTime: quote.time } : result;
}
// Simulator UUIDs identify the same deterministic event independently in both paths.
function deterministic(run) { const original = crypto.randomUUID; let id = 0; crypto.randomUUID = () => 'event-' + ++id; try { return run(); } finally { crypto.randomUUID = original; } }
function engine() {
  const value = new IndicatorEngine(productionRegistry, { attach() {}, detach() {}, remove() {}, sync() {} });
  for (const type of productionRegistry.types()) value.create({ id: type, type });
  return value;
}
const optimized = series(), reference = series(), indicators = engine(), referenceIndicators = engine();
let previous = [], rawPrevious = [], account = initialAccount(), refAccount = initialAccount(), incremental = 0, full = 0;
function transition(raw, frame, hint) {
  const candles = aggregateCandles(raw, frame);
  const mode = syncCandleSeries(optimized, previous, candles, hint); reference.setData(candles);
  if (mode === 'incremental') incremental++; else full++;
  assert.deepEqual(optimized.points, reference.points);
  assert.deepEqual(optimized.points.at(-1), candles.at(-1));
  const volume = candles.map(bar => ({ time: bar.time, value: bar.volume }));
  assert.deepEqual(volume, reference.points.map(bar => ({ time: bar.time, value: bar.volume })));
  indicators.setCandles(candles); referenceIndicators.setCandles(reference.points);
  for (const type of productionRegistry.types()) assert.deepEqual(indicators.output(type), referenceIndicators.output(type));
  account = deterministic(() => settleReplay(account, raw, rawPrevious, hint));
  refAccount = deterministic(() => referenceAccount(refAccount, raw));
  assert.deepEqual(account, refAccount, 'Full account/balance/orders/positions/trades equivalence');
  previous = candles; rawPrevious = raw;
}
transition(bars.slice(100, 180), '15m', { kind: 'start' });
for (const order of [
  { id: 'market', side: 'Buy', type: 'Market', size: .2, sl: bars[179].close - 3, tp: bars[179].close + 5 },
  { id: 'limit', side: 'Buy', type: 'Limit', size: .1, entry: bars[179].close - 1, sl: bars[179].close - 5, tp: bars[179].close + 4 },
  { id: 'stop', side: 'Sell', type: 'Stop', size: .1, entry: bars[179].close - 1, sl: bars[179].close + 5, tp: bars[179].close - 4 }
]) { account = placeOrder(account, order, bars[179]); refAccount = placeOrder(refAccount, order, bars[179]); }
for (let end = 181; end < 600; end++) transition(bars.slice(100, end), '15m', forward);
transition(bars.slice(0, 600), '15m', { kind: 'prepend' });
transition(bars.slice(0, 620), '1h', { kind: 'timeframe' });
transition(bars.slice(0, 621), '1h', forward);
// Malformed/misleading hints and historical changes cannot bypass full replacement.
const changed = bars.slice(0, 622).map((bar, i) => i === 10 ? { ...bar, high: bar.high + 50 } : bar);
transition(changed, '1h', forward);
assert.equal(forwardChange(previous, aggregateCandles(bars.slice(0, 623), '1h'), forward), null);
transition(bars.slice(0, 623), '1h', { kind: 'invalid' });
account = initialAccount(); refAccount = initialAccount();
transition(bars.slice(0, 200), '15m', { kind: 'reset' });
transition(bars.slice(0, 180), '15m', { kind: 'rewind' });
transition(bars.slice(0, 201), '15m', forward);
transition([], '15m', { kind: 'stop' });
transition(bars.slice(0, 100), '1m', { kind: 'start' });
for (let end = 101; end <= 260; end++) transition(bars.slice(0, end), '1m', forward);
assert.ok(incremental > 550 && full >= 8);
// A failed incremental API call recovers even after partial successful updates.
const recovery = series(); recovery.setData(bars.slice(0, 2)); const update = recovery.update.bind(recovery); let calls = 0;
recovery.update = point => { if (++calls === 2) throw Error('API failure'); update(point); };
assert.equal(syncCandleSeries(recovery, bars.slice(0, 2), bars.slice(0, 5), forward), 'full');
assert.deepEqual(recovery.points, bars.slice(0, 5));
for (const hint of [null, {}, { kind: 'rewind' }, { kind: 'prepend' }, { kind: 'start' }]) assert.equal(forwardChange(bars.slice(0, 2), bars.slice(0, 3), hint), null);
assert.equal(forwardChange(bars.slice(0, 2), [bars[0], bars[1], bars[0]], forward), null);
// Hidden OHLC/volume mutations cannot affect any revealed consumer or cursor.
const hiddenChanged = bars.map((bar, i) => i < 300 ? bar : { ...bar, open: 10, close: 15, high: 20, low: 5, volume: 999999 });
const controls = data => ({ active: true, atEnd: 299 >= data.length - 1, index: 299, latestQuote: data[299], transition: { kind: 'forward', revision: 300, timeframe: '15m' } });
assert.deepEqual(controls(bars), controls(hiddenChanged));
for (const frame of ['1m', '15m', '1h', 'D', 'W', 'M']) {
  const a = aggregateCandles(bars.slice(0, 300), frame), b = aggregateCandles(hiddenChanged.slice(0, 300), frame);
  assert.deepEqual(a, b); assert.equal(advanceReplayIndex(bars, 100, frame), advanceReplayIndex(hiddenChanged, 100, frame));
  indicators.setCandles(a); referenceIndicators.setCandles(b);
  for (const type of productionRegistry.types()) assert.deepEqual(indicators.output(type), referenceIndicators.output(type));
  assert.deepEqual(referenceAccount(initialAccount(), bars.slice(0, 300)), settleReplay(initialAccount(), hiddenChanged.slice(0, 300)));
}
indicators.dispose(); referenceIndicators.dispose();

let timers = new Map(), nextId = 0, delays = [], steps = 0, revision = 0;
const scheduler = new PlaybackScheduler({ set(fn, delay) { const id = ++nextId; timers.set(id, fn); delays.push(delay); return id; }, clear(id) { timers.delete(id); } });
const commit = (enabled = true, speed = 1) => scheduler.commit({ enabled, speed, revision, step() { steps++; } });
const fire = () => { assert.equal(timers.size, 1); const [id, fn] = [...timers][0]; timers.delete(id); fn(); };
for (const speed of PLAYBACK_SPEEDS) {
  commit(true, speed); assert.equal(delays.at(-1), 1000 / speed); fire();
  const before = steps; commit(true, speed); commit(true, 20); assert.equal(timers.size, 0); assert.equal(steps, before);
  revision++; commit(true, speed); assert.equal(timers.size, 1);
  // Pause cancels queued timer; resume schedules one, never duplicates.
  commit(false, speed); assert.equal(timers.size, 0); commit(true, speed); assert.equal(timers.size, 1);
}
const stale = [...timers.values()][0]; scheduler.dispose(); stale(); assert.equal(timers.size, 0); assert.equal(steps, 5);
commit(true, 20); fire(); revision++; commit(false, 20); assert.equal(timers.size, 0); // replay end
scheduler.dispose(); commit(true, 1); assert.equal(timers.size, 1); scheduler.dispose(); assert.equal(timers.size, 0); // remount
const workspace = readFileSync(new URL('../src/FigmaWorkspace.jsx', import.meta.url), 'utf8');
assert.ok(!workspace.includes('setInterval('));
assert.ok(workspace.includes('trading.account.positions.length>0||trading.account.orders.length>0||trading.account.trades.length>0'));
const replaySource = readFileSync(new URL('../src/market/useReplayMarket.js', import.meta.url), 'utf8');
assert.match(replaySource, /const transition=useMemo\(\(\)=>\(\{kind:state.kind,revision:state.revision,timeframe\}\)/);
console.log(`PASS Phase 13: ${incremental} incremental/${full} full transitions; exact chart/quote/Volume/seven-indicator/account differential equality; causal hidden mutation invariance; cursor reference semantics; all speeds/commit backpressure/cancellation/pause/resume/end/remount and unchanged rewind boundary.`);
