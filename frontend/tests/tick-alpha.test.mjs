import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {api,command,sessionPath} from '../src/tickAlpha/client.js';
import {displayBars,replayTarget,seekTarget} from '../src/tickAlpha/display.js';

const calls=[];
globalThis.fetch=async(url,options)=>{calls.push({url,options});return {ok:true,json:async()=>({schemaVersion:1,reviewHash:'pinned'})};};
const exact='0.123456789012345678';
await api('/reviews',{draft:{quantity:exact},expectedRevision:7});
assert.equal(JSON.parse(calls[0].options.body).draft.quantity,exact);
assert.equal(calls[0].options.credentials,'omit');
assert.equal(calls[0].options.cache,'no-store');
assert.equal(calls[0].options.headers['X-BTL-Local'],'1');
await api('/catalog');
assert.equal(calls[1].options.method,'GET');assert.ok(!Object.hasOwn(calls[1].options,'body'));
assert.equal(sessionPath('session:α'),'/sessions/session%3A%CE%B1');
const raw=command({metadata:{id:'session:one'},state:{revision:7}},'ADVANCE',{targetNs:'1577838600000000000'});
assert.equal(raw.expectedRevision,7);assert.equal(raw.payload.targetNs,'1577838600000000000');
assert.notEqual(raw.commandId,command({metadata:{id:'session:one'},state:{revision:7}},'ADVANCE',raw.payload).commandId);
globalThis.fetch=async()=>({ok:false,json:async()=>({detail:'REFUSED_STALE_REVISION'})});
await assert.rejects(()=>api('/reviews',{}),/REFUSED_STALE_REVISION/);
globalThis.fetch=async()=>({ok:true,json:async()=>({schemaVersion:2})});
await assert.rejects(()=>api('/catalog'),/Unsupported local response/);
const ui=readFileSync(new URL('../src/tickAlpha/TickAlpha.jsx',import.meta.url),'utf8');
for(const prohibited of ['useTrading','prototypeModel','localStorage','simulate trigger','manage('])assert.ok(!ui.includes(prohibited),'Alpha must not adopt a second financial truth: '+prohibited);
assert.ok(ui.includes('review.reviewHash')&&ui.includes("+'/confirm'"));
assert.ok(ui.includes('flight.current')&&ui.includes('loadWorkspace(view.metadata.id)'));
const main=readFileSync(new URL('../src/main.jsx',import.meta.url),'utf8');
assert.ok(main.includes("get('tick-alpha')==='local'"));assert.ok(main.includes('localOrigin?<TickAlphaEntry/>'));
console.log('PASS tick-alpha transport exact strings, explicit revision/command identity, local-only opt-in and durable-review UI boundary.');

const view={state:{throughNs:'1577838600000000000'},chart:{timeframe:'1m',priceBasis:'EXACT_REVEALED_MID_DISPLAY_ONLY',volumeAvailable:false,candles:[
  {time:1577838540,open:'2000.015',high:'2001.015',low:'1999.015',close:'2000.515',event_count:4,incomplete:false,partialWindow:false},
]}};
const bars=displayBars(view);
assert.equal(bars[0].open,2000.015);assert.ok(!Object.hasOwn(bars[0],'volume'));
assert.deepEqual(Object.keys(bars[0]),['time','open','high','low','close']);
assert.equal(view.chart.candles[0].open,'2000.015');
assert.equal(replayTarget(view,4),'1577838660000000000');
assert.equal(seekTarget('2020-01-01T00:30'),'1577838600000000000');
assert.throws(()=>replayTarget(view,1000));assert.throws(()=>seekTarget('2020-01-01T00:30Z'));
const future=structuredClone(view);future.chart.candles[0].time=1577838660;
assert.throws(()=>displayBars(future),/Unrevealed/);
const bad=structuredClone(view);bad.chart.candles[0].open=2000.015;
assert.throws(()=>displayBars(bad),/display price/);
const volume=structuredClone(view);volume.chart.volumeAvailable=true;
assert.throws(()=>displayBars(volume),/Invalid revealed/);
console.log('PASS revealed-only display projection, no fabricated volume, immutable exact wire prices and exact tick/UTC targets.');
