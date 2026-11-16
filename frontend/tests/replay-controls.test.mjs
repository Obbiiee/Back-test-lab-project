import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {tradeEvents,durationLabel,isLimitError,limitDelayMs,pause,candleTarget,playbackTarget,widenScale,eventSignature,hasWatchedOrders,SPEEDS,PLAY_INTERVAL_MS,timeframeLabel,utcLabel} from '../src/tickAlpha/replay.js';
import {spreadLabel} from '../src/tickAlpha/display.js';
import {readPending,writePending,readTimeframe,writeTimeframe} from '../src/tickAlpha/replayPending.js';

const ns=iso=>String(BigInt(Date.parse(iso))*1000000n);
const last=iso=>String(BigInt(Date.parse(iso))*1000000n-1n); // last nanosecond before iso

// Next Candle targets the last nanosecond of the UTC bucket containing the cursor.
assert.equal(candleTarget(ns('2020-01-01T00:00:00Z'),'1m'),last('2020-01-01T00:01:00Z'));
assert.equal(candleTarget(ns('2020-01-01T00:00:30.500Z'),'1m'),last('2020-01-01T00:01:00Z'));
// Already at the end of a completed bucket -> the next whole bucket.
assert.equal(candleTarget(last('2020-01-01T00:01:00Z'),'1m'),last('2020-01-01T00:02:00Z'));
assert.equal(candleTarget(ns('2020-01-01T00:02:14Z'),'5m'),last('2020-01-01T00:05:00Z'));
assert.equal(candleTarget(ns('2020-01-01T00:02:14Z'),'1h'),last('2020-01-01T01:00:00Z'));
assert.equal(candleTarget(ns('2020-01-01T00:02:14Z'),'4h'),last('2020-01-01T04:00:00Z'));
// Daily boundary is UTC midnight; a Friday cursor never skips Saturday/Sunday logic (calendar time only).
assert.equal(candleTarget(ns('2020-01-03T21:59:00Z'),'D'),last('2020-01-04T00:00:00Z'));
assert.equal(candleTarget(last('2020-01-04T00:00:00Z'),'D'),last('2020-01-05T00:00:00Z'));
// Month / year boundary.
assert.equal(candleTarget(ns('2019-12-31T23:59:30Z'),'1m'),last('2020-01-01T00:00:00Z'));
// Property: strictly forward, aligned to bucket end, never more than one bucket ahead.
for(const timeframe of ['1m','3m','5m','15m','30m','1h','2h','4h','D']){
  const size=BigInt({'1m':60,'3m':180,'5m':300,'15m':900,'30m':1800,'1h':3600,'2h':7200,'4h':14400,D:86400}[timeframe])*1000000000n;
  for(let seed=1n;seed<200n;seed++){
    const cursor=1577836800000000000n+seed*7919000000013n;
    const target=BigInt(candleTarget(String(cursor),timeframe));
    assert.ok(target>cursor,`${timeframe} must move forward`);
    assert.equal((target+1n)%size,0n,`${timeframe} must end on a bucket boundary`);
    assert.ok(target-cursor<=size,`${timeframe} must not skip a bucket`);
  }
}
assert.throws(()=>candleTarget('x','1m'),/Invalid replay cursor/);
assert.throws(()=>candleTarget('1','7m'),/Unsupported timeframe/);
assert.equal(timeframeLabel('1h'),'H1');assert.equal(timeframeLabel('D'),'D1');assert.equal(timeframeLabel('5m'),'M5');
assert.equal(utcLabel(ns('2020-01-01T01:02:03Z')),'2020-01-01 01:02:03 UTC');

// Playback rate is market time per real second; one request per PLAY_INTERVAL_MS.
assert.deepEqual(SPEEDS,[0.5,1,2,5,10,20]);
assert.equal(PLAY_INTERVAL_MS,500);
const base=ns('2020-01-01T00:00:00Z');
assert.equal(BigInt(playbackTarget(base,1))-BigInt(base),500000000n);
assert.equal(BigInt(playbackTarget(base,20))-BigInt(base),10000000000n);
assert.equal(BigInt(playbackTarget(base,2,4n))-BigInt(base),4000000000n);
assert.equal(BigInt(playbackTarget(base,0.5))-BigInt(base),250000000n);
assert.throws(()=>playbackTarget(base,3),/Unsupported replay speed/);
// A gap widens the next request 4x up to one candle and resets as soon as ticks are revealed.
assert.equal(widenScale(1n,false,'1m',2),4n);
assert.equal(widenScale(4n,false,'1m',2),16n);
assert.equal(widenScale(1000000n,false,'1m',2),60n);
assert.equal(widenScale(16n,true,'1m',2),1n);

// A trading event is any committed order change; candles alone never create one.
const view=(orders,completed=0,revision='1')=>({state:{revision},analysis:{status:'COMPLETE',orders,completed:Array(completed).fill({})}});
const pending={id:'o1',status:'PENDING',remaining:'0.1'};
const active={id:'o1',status:'ACTIVE',remaining:'0.1'};
assert.notEqual(eventSignature(view([pending])),eventSignature(view([active])));
assert.notEqual(eventSignature(view([active])),eventSignature(view([],1)));
assert.equal(eventSignature(view([pending])),eventSignature(view([pending],0,'9')));
assert.equal(hasWatchedOrders(view([pending])),true);
assert.equal(hasWatchedOrders(view([])),false);
assert.equal(hasWatchedOrders({state:{},analysis:{status:'UNAVAILABLE'}}),false);

// Pending replay target persistence: strict shape, memory-safe when storage is denied.
const store=new Map();
globalThis.localStorage={getItem:key=>store.get(key)??null,setItem:(key,value)=>store.set(key,value),removeItem:key=>store.delete(key)};
assert.equal(readPending('k'),null);
writePending('k',{kind:'ADVANCE',target:'123'});
assert.deepEqual(readPending('k'),{kind:'ADVANCE',target:'123'});
writePending('k',{kind:'DELETE',target:'123'});
assert.deepEqual(readPending('k'),{kind:'ADVANCE',target:'123'},'invalid writes are ignored');
store.set('k','{"kind":"ADVANCE","target":"-1"}');assert.equal(readPending('k'),null);
store.set('k','not json');assert.equal(readPending('k'),null);
writePending('k',null);assert.equal(readPending('k'),null);
globalThis.localStorage={getItem(){throw Error('denied');},setItem(){throw Error('denied');},removeItem(){throw Error('denied');}};
assert.equal(readPending('k'),null);writePending('k',{kind:'SEEK',target:'5'});

// Transient service limits are retried with bounded back-off; other errors are not.
assert.equal(isLimitError('RATE_LIMITED'),true);assert.equal(isLimitError('LOCAL_BUSY'),true);assert.equal(isLimitError('REFUSED_STALE_REVISION'),false);
assert.deepEqual([0,1,2,5,9].map(retry=>limitDelayMs('LOCAL_BUSY',retry)),[500,1000,2000,10000,10000]);
assert.equal(limitDelayMs('RATE_LIMITED',0),1500);
await pause(5,undefined);
const controller=new AbortController();const waiting=pause(60000,controller.signal);controller.abort();
await assert.rejects(()=>waiting,/Cancelled/);
await assert.rejects(()=>pause(5,AbortSignal.abort()),/Cancelled/);

// Timeframe preference: only known timeframes are stored or read.
{const kv=new Map();globalThis.localStorage={getItem:key=>kv.get(key)??null,setItem:(key,value)=>kv.set(key,value),removeItem:key=>kv.delete(key)};
assert.equal(readTimeframe('t'),null);writeTimeframe('t','1h');assert.equal(readTimeframe('t'),'1h');
writeTimeframe('t','7m');assert.equal(readTimeframe('t'),'1h');kv.set('t','bogus');assert.equal(readTimeframe('t'),null);}

// Trade announcements come only from newly committed server rows.
{const mk=(orders,completed)=>({analysis:{status:'COMPLETE',orders,completed}});
const pend={id:'o1',status:'PENDING'},act={id:'o1',status:'ACTIVE',entryPrice:'1'},done={id:'o1',status:'CLOSED',net:'2.00'};
assert.deepEqual(tradeEvents(mk([pend],[]),mk([act],[])).map(e=>e.kind),['FILL']);
assert.deepEqual(tradeEvents(mk([act],[]),mk([],[done])).map(e=>e.kind),['EXIT']);
assert.deepEqual(tradeEvents(mk([pend],[]),mk([],[done])).map(e=>e.kind),['EXIT'],'fill and exit inside one step announce the exit');
assert.deepEqual(tradeEvents(mk([act],[]),mk([act],[])),[],'unchanged state announces nothing');
assert.deepEqual(tradeEvents(mk([],[done]),mk([],[done])),[]);
assert.deepEqual(tradeEvents({analysis:{status:'UNAVAILABLE'}},mk([act],[])),[]);}
assert.equal(durationLabel('45000000000'),'45s');assert.equal(durationLabel('125000000000'),'2m 05s');
assert.equal(durationLabel('7500000000000'),'2h 5m');assert.equal(durationLabel('200000000000000'),'2d 7h');assert.equal(durationLabel('x'),null);
// Spread is exact decimal arithmetic on wire strings.
assert.equal(spreadLabel('2003.23','2003.43'),'0.20');assert.equal(spreadLabel('1.1','1.1002'),'0.0002');
assert.equal(spreadLabel('2','1'),null);assert.equal(spreadLabel('1e3','2'),null);assert.equal(spreadLabel(undefined,'2'),null);

// Source contracts of the replay UI (no second engine, no OHLC settlement, cleanup).
const controls=readFileSync(new URL('../src/tickAlpha/AlphaReplayControls.jsx',import.meta.url),'utf8');
assert.ok(controls.includes("onAdvance('ADVANCE'")&&controls.includes("onAdvance('SEEK'"),'every replay action is a backend ADVANCE/SEEK');
assert.ok(controls.includes('clearTimeout(timer)')&&controls.includes("removeEventListener('keydown'"),'timers and listeners are released');
assert.ok(!/\b(high|low|open|close)\b\s*[<>]=?/.test(controls),'no candle comparison in replay controls');
assert.ok(controls.includes('abort.current?.abort()'));
const workspace=readFileSync(new URL('../src/tickAlpha/TickAlpha.jsx',import.meta.url),'utf8');
assert.ok(workspace.includes('flight.current')&&workspace.includes('savePending(sessionId,{kind,target:targetNs})'));
assert.ok(workspace.includes('isLimitError(error.message)')&&workspace.includes('REFUSED_STALE_REVISION'),'limits are retried and a stale revision is reconciled, never blindly replayed');
assert.ok(workspace.includes("unfinished?.kind==='ADVANCE'")&&controls.includes('const blocked='),'an unfinished ADVANCE target is never overwritten and blocks other replay actions');
assert.ok(workspace.includes('Replay made no progress'),'a stalled partial advance is refused, not retried forever');
console.log('PASS replay controls: UTC candle targets (all timeframes, gaps, boundaries), playback-rate semantics, event detection, pending-target persistence and source contracts.');
