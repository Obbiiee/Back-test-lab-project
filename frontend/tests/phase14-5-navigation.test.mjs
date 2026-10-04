import assert from 'node:assert/strict';
import { NewsNavigationController } from '../src/news/NewsNavigationController.js';
import { initialAccount, placeOrder } from '../src/trading/simulator.js';
import { settleReplay } from '../src/trading/replaySettlement.js';
import { advanceReplayIndex } from '../src/market/replayTransitions.js';
const bars = Array.from({ length: 120 }, (_, i) => ({ time: 1700000000 + 60 * i, open: 2000, high: 2002 + i / 100, low: 1998 - i / 100, close: 2000 + i / 100, volume: i + 1 }));
for (const timeframe of ['1m', '15m', '1h']) {
  const originalUuid = crypto.randomUUID; let identity = 0;
  crypto.randomUUID = () => 'event-' + ++identity;
  let account = { ...initialAccount(), lastTime: bars[0].time };
  account = placeOrder(account, { side: 'Buy', type: 'Limit', entry: 1999, sl: 1998, tp: 2002, size: 1 }, bars[0]);
  const nav = new NewsNavigationController(); let index = 0, revision = 0, previous = [bars[0]], requests = 0;
  const target = bars[50].time;
  nav.begin(target, { time: bars[0].time });
  const reference = []; let manualIndex = 0;
  while (bars[manualIndex].time < target) { manualIndex = advanceReplayIndex(bars, manualIndex, timeframe, 1); reference.push(manualIndex); }
  let stepCount = 0;
  while (nav.target !== null) {
    const before = revision;
    const snapshot = { time: bars[index].time, revision, settledTime: account.lastTime, active: true, loading: false, error: '', atEnd: index === bars.length - 1 };
    const result = nav.commit({ ...snapshot, step: () => { requests++; } });
    if (result === 'arrived') break;
    assert.equal(result, 'stepping');
    assert.equal(nav.commit({ ...snapshot, step: () => { requests++; } }), 'waiting');
    assert.equal(requests, stepCount + 1, 'No duplicate requests before acknowledgment.');
    index = advanceReplayIndex(bars, index, timeframe, 1); revision++;
    assert.equal(index, reference[stepCount++]);
    const revealed = bars.slice(0, index + 1);
    // Cursor commit alone cannot request the next step before settlement.
    assert.equal(nav.commit({ ...snapshot, time: bars[index].time, revision, step: () => { requests++; } }), 'waiting');
    account = settleReplay(account, revealed, previous, { kind: 'forward', revision, timeframe }); previous = revealed;
    assert.ok(revision > before);
  }
  identity = 0;
  let manual = placeOrder({ ...initialAccount(), lastTime: bars[0].time }, { side: 'Buy', type: 'Limit', entry: 1999, sl: 1998, tp: 2002, size: 1 }, bars[0]);
  let prefix = [bars[0]];
  reference.forEach((cursor, i) => { const next = bars.slice(0, cursor + 1); manual = settleReplay(manual, next, prefix, { kind: 'forward', revision: i + 1, timeframe }); prefix = next; });
  assert.deepEqual(account, manual);
  crypto.randomUUID = originalUuid;
}
console.log('PASS navigation request/settlement ordering and exact manual account equivalence for 1m/15m/1h.');
// Chunk extension changes available history, never the revealed prefix/account.
const chunkNavigation = new NewsNavigationController();
let available = bars.slice(0, 20), chunkIndex = 0, chunkRevision = 0, chunkRequests = 0;
chunkNavigation.begin(bars[50].time, { time: bars[0].time });
while (chunkNavigation.target !== null) {
  const state = { time: available[chunkIndex].time, settledTime: available[chunkIndex].time, revision: chunkRevision, active: true, loading: false, error: '', atEnd: chunkIndex === available.length - 1, step: () => chunkRequests++ };
  const result = chunkNavigation.commit(state);
  if (result === 'arrived') break;
  if (result === 'waiting-for-history') { assert.equal(chunkRequests, chunkIndex); available = bars; continue; }
  assert.equal(result, 'stepping'); chunkIndex++; chunkRevision++;
}
assert.equal(chunkIndex, 50); assert.equal(chunkRequests, 50);
chunkNavigation.begin(bars[80].time, { time: bars[50].time }); chunkNavigation.cancel();
assert.equal(chunkNavigation.commit({ step: () => { throw Error('Cancelled run requested another step'); } }), 'idle');
console.log('PASS chunk-boundary waiting/extension, unchanged revealed prefix and cancellation.');
