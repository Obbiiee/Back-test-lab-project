import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {candleTarget,playbackTarget,widenScale,tradeEvents,durationLabel,scrubRange,scrubFraction,scrubTarget,scrubKind,scrubStep,pendingTarget,SPEEDS,PLAY_INTERVAL_MS,timeframeLabel,utcLabel} from '../src/tickAlpha/replay.js';
import {spreadLabel} from '../src/tickAlpha/display.js';

const ns=iso=>String(BigInt(Date.parse(iso))*1000000n);
const last=iso=>String(BigInt(Date.parse(iso))*1000000n-1n); // last nanosecond before iso

// Next Candle targets the last nanosecond of the UTC bucket containing the cursor.
assert.equal(candleTarget(ns('2020-01-01T00:00:00Z'),'1m'),last('2020-01-01T00:01:00Z'));
assert.equal(candleTarget(ns('2020-01-01T00:00:30.500Z'),'1m'),last('2020-01-01T00:01:00Z'));
assert.equal(candleTarget(last('2020-01-01T00:01:00Z'),'1m'),last('2020-01-01T00:02:00Z'),'a completed bucket moves to the next one');
assert.equal(candleTarget(ns('2020-01-01T00:02:14Z'),'5m'),last('2020-01-01T00:05:00Z'));
assert.equal(candleTarget(ns('2020-01-01T00:02:14Z'),'1h'),last('2020-01-01T01:00:00Z'));
assert.equal(candleTarget(ns('2020-01-01T00:02:14Z'),'4h'),last('2020-01-01T04:00:00Z'));
assert.equal(candleTarget(ns('2020-01-03T21:59:00Z'),'D'),last('2020-01-04T00:00:00Z'),'daily bucket ends at UTC midnight');
assert.equal(candleTarget(last('2020-01-04T00:00:00Z'),'D'),last('2020-01-05T00:00:00Z'),'weekend gaps need no special case');
assert.equal(candleTarget(ns('2019-12-31T23:59:30Z'),'1m'),last('2020-01-01T00:00:00Z'));
for(const timeframe of ['1m','3m','5m','15m','30m','1h','2h','4h','D']){
  const size=BigInt({'1m':60,'3m':180,'5m':300,'15m':900,'30m':1800,'1h':3600,'2h':7200,'4h':14400,D:86400}[timeframe])*1000000000n;
  for(let seed=1n;seed<200n;seed++){
    const cursor=1577836800000000000n+seed*7919000000013n;
    const target=BigInt(candleTarget(String(cursor),timeframe));
    assert.ok(target>cursor,`${timeframe} moves forward`);
    assert.equal((target+1n)%size,0n,`${timeframe} ends on a bucket boundary`);
    assert.ok(target-cursor<=size,`${timeframe} never skips a bucket`);
  }
}
assert.throws(()=>candleTarget('x','1m'),/Invalid replay cursor/);
assert.throws(()=>candleTarget('1','7m'),/Unsupported timeframe/);
assert.equal(timeframeLabel('1h'),'H1');assert.equal(timeframeLabel('D'),'D1');
assert.equal(utcLabel(ns('2020-01-01T01:02:03Z')),'2020-01-01 01:02:03 UTC');

// Playback rate = market seconds per real second; one request per PLAY_INTERVAL_MS.
assert.deepEqual(SPEEDS,[0.5,1,2,5,10,20]);assert.equal(PLAY_INTERVAL_MS,500);
const base=ns('2020-01-01T00:00:00Z');
assert.equal(BigInt(playbackTarget(base,0.5))-BigInt(base),250000000n);
assert.equal(BigInt(playbackTarget(base,20))-BigInt(base),10000000000n);
assert.equal(BigInt(playbackTarget(base,2,4n))-BigInt(base),4000000000n);
assert.throws(()=>playbackTarget(base,3),/Unsupported replay speed/);
assert.equal(widenScale(1n,false,'1m',2),4n);assert.equal(widenScale(1000000n,false,'1m',2),60n);assert.equal(widenScale(16n,true,'1m',2),1n);

// Trade announcements come only from newly committed server rows.
{const mk=(orders,completed)=>({analysis:{status:'COMPLETE',orders,completed}});
const pend={id:'o1',status:'PENDING'},act={id:'o1',status:'ACTIVE',entryPrice:'1'},done={id:'o1',status:'CLOSED',net:'2.00'};
assert.deepEqual(tradeEvents(mk([pend],[]),mk([act],[])).map(e=>e.kind),['FILL']);
assert.deepEqual(tradeEvents(mk([act],[]),mk([],[done])).map(e=>e.kind),['EXIT']);
assert.deepEqual(tradeEvents(mk([pend],[]),mk([],[done])).map(e=>e.kind),['EXIT']);
assert.deepEqual(tradeEvents(mk([act],[]),mk([act],[])),[]);
assert.deepEqual(tradeEvents({analysis:{status:'UNAVAILABLE'}},mk([act],[])),[]);}
assert.equal(durationLabel('45000000000'),'45s');assert.equal(durationLabel('125000000000'),'2m 05s');assert.equal(durationLabel('x'),null);
assert.equal(spreadLabel('2003.23','2003.43'),'0.20');assert.equal(spreadLabel('1.1','1.1002'),'0.0002');assert.equal(spreadLabel('2','1'),null);assert.equal(spreadLabel('1e3','2'),null);

// Scrubber geometry and the server-owned pending target.
{const view={metadata:{startPeriod:'2020-01'},state:{throughNs:'1577923200000000000'}};const range=scrubRange(view);
assert.equal(String(range.startNs),'1577836800000000000');assert.equal(String(range.endNs),'1580515200000000000');
assert.equal(scrubFraction(range.startNs,range),0);assert.equal(scrubFraction(range.endNs,range),1);
assert.equal(scrubTarget(0,range),'1577836800000000000');assert.equal(scrubTarget(2,range),String(range.endNs));
assert.equal(scrubKind('1577923200000000000',view.state.throughNs),'REVEALED');assert.equal(scrubKind('1577923201000000000',view.state.throughNs),'FUTURE');
assert.equal(scrubStep(range.startNs,'1h',-1,range),String(range.startNs));assert.equal(scrubStep(range.endNs,'D',1,range),String(range.endNs));
assert.equal(scrubRange({metadata:{startPeriod:'bogus'}}),null);
assert.deepEqual(pendingTarget({pendingReplayTargetNs:'9',state:{throughNs:'5'}}),{kind:'ADVANCE',target:'9'},'observed Sessions report pendingReplayTargetNs');
assert.deepEqual(pendingTarget({state:{throughNs:'5',pendingTargetNs:'9'}}),{kind:'ADVANCE',target:'9'});
assert.equal(pendingTarget({pendingReplayTargetNs:'5',state:{throughNs:'5'}}),null);assert.equal(pendingTarget({pendingReplayTargetNs:null,state:{throughNs:'5'}}),null);assert.equal(pendingTarget({state:{throughNs:'5'}}),null);}

// Source contracts of the replay UI.
const controls=readFileSync(new URL('../src/tickAlpha/AlphaReplayControls.jsx',import.meta.url),'utf8');
assert.ok(controls.includes('onReplay(')&&controls.includes('onJump('),'every replay action goes through the Session owner (ADVANCE/SEEK or jump-next-event)');
assert.ok(controls.includes('clearTimeout(timer)')&&controls.includes("removeEventListener('keydown'"),'timers and listeners are released');
assert.ok(!/localStorage/.test(controls),'the unfinished target is the server\'s, never browser state');
assert.ok(controls.includes('pendingTarget(')&&controls.includes('Continue saved replay')&&controls.includes('Jump to Next Event')&&controls.includes('Cancel search'));
const scrubber=readFileSync(new URL('../src/tickAlpha/AlphaReplayScrubber.jsx',import.meta.url),'utf8');
assert.ok(scrubber.includes('onSeek(target)')&&!/onReplay|api[(]/.test(scrubber),'future time needs an explicit confirm and goes through the replay owner');
const owner=readFileSync(new URL('../src/tickAlpha/TickAlpha.jsx',import.meta.url),'utf8');
assert.ok(owner.includes('viewRef.current??view'),'chained replay calls read the latest committed view');
assert.ok(owner.includes('return {view:saved,reached,revealed}'));
console.log('PASS replay controls: UTC candle targets, playback rate, trade announcements, scrubber geometry, server pending target and source contracts.');
