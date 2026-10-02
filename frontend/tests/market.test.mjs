import assert from 'node:assert/strict';
import {aggregateCandles,addQuote,bucketTime,parseQuote} from '../src/market/candles.js';
import {positionStats} from '../src/drawings/position.js';
import {parseHistDataCSV, mergeHistory, validateHistory, decodeHistoryRows} from '../src/market/history.js';
import {readFileSync} from 'node:fs';
let bars=[];
for(const [time,price] of [[0,100],[30,105],[60,98],[120,110]]) bars=addQuote(bars,{time,price});
assert.deepEqual(aggregateCandles(bars,'3m'),[{time:0,open:100,high:110,low:98,close:110,volume:0}]);
assert.equal(bucketTime(Date.parse('2026-03-31T23:59:00Z')/1000,'M'),Date.parse('2026-03-01T00:00:00Z')/1000);
assert.equal(bucketTime(Date.parse('2026-04-01T00:00:00Z')/1000,'M'),Date.parse('2026-04-01T00:00:00Z')/1000);
assert.equal(bucketTime(Date.parse('2026-10-04T12:00:00Z')/1000,'W'),Date.parse('2026-09-28T00:00:00Z')/1000);
assert.throws(()=>parseQuote({symbol:'XAU',price:0,updatedAt:'bad'}));
for(const type of ['long-position','short-position']) {
  const direction=type==='long-position'?1:-1;
  const d={type,points:[{price:2000},{price:2000-10*direction},{price:2000+30*direction}],accountSize:10000,riskValue:1,leverage:100,lotSize:100};
  const v=positionStats(d,2000+5*direction);
  assert.equal(v.ratio,3);assert.equal(v.quantity,0.1);assert.equal(v.loss,100);assert.equal(v.profit,300);assert.equal(v.openPnl,50);
  assert.equal(v.targetBalance,10300);assert.equal(v.stopBalance,9900);
  assert.equal(positionStats({...d,riskMode:'cash',riskValue:100},2000).quantity,0.1);
  assert.equal(positionStats({...d,points:[{price:2000},{price:2000},{price:2030}]},2000).valid,false);
}
console.log('PASS: OHLC aggregation, calendar months/weeks, quotes and long/short risk sizing.');
const converted = parseHistDataCSV('20260901 000000;4000;4005;3995;4002;0\n20260901 000100;4002;4006;4001;4004;0');
assert.equal(converted[0].time, Date.parse('2026-09-01T05:00:00Z') / 1000);
assert.throws(() => parseHistDataCSV('20260901 000000;4000;3990;3995;4002;0'));
const history = [{time:0,open:10,high:11,low:9,close:10,volume:0},{time:60,open:10,high:12,low:9,close:11,volume:0},{time:120,open:11,high:14,low:10,close:13,volume:0}];
const live = [{time:120,open:20,high:21,low:19,close:20,volume:0}];
const joined = mergeHistory(history,live,'1m');
assert.deepEqual(joined.candles.map(b=>b.time),[0,60,120]);
assert.equal(joined.candles[2].open,20);
assert.equal(joined.historicalCount,2);
// A 3m candle spanning both sources must come entirely from live, not mixed prices.
assert.equal(mergeHistory(history,live,'3m').candles[0].open,20);
assert.equal(mergeHistory(history,live,'3m').candles[0].low,19);
assert.equal(mergeHistory(history,[],'1m').historicalCount,3);
assert.equal(mergeHistory([],live,'1m').liveCount,1);
const snapshot = validateHistory(JSON.parse(readFileSync(new URL('../public/market/xauusd-history.json',import.meta.url),'utf8')));
assert.equal(snapshot.count,snapshot.candles.length);
assert.equal(snapshot.first,snapshot.candles[0].time);
assert.equal(snapshot.last,snapshot.candles.at(-1).time);
assert.throws(()=>validateHistory({...snapshot,candles:[snapshot.candles[0],snapshot.candles[0]]}));
for(const timeframe of ['1m','3m','5m','15m','30m','1h','2h','4h','D','W','M']) {
  const latest = [{...live[0],time:snapshot.last+10*86400}];
  const grouped = mergeHistory(snapshot.candles,latest,timeframe).candles;
  assert.ok(grouped.every((bar,i)=>i===0||bar.time>grouped[i-1].time));
  assert.ok(grouped.length >= 2);
}
console.log(`PASS: EST-to-UTC, historical validation, provider seam and all timeframes; ${snapshot.count} actual historical candles.`);
const root=new URL('../public/market/decade/',import.meta.url);
const catalog=JSON.parse(readFileSync(new URL('manifest.json',root),'utf8'));
let total=0;
for(const [frame,chunks] of Object.entries(catalog.frames)) {
  let previous=-Infinity;
  for(const chunk of chunks) {
    const candles=decodeHistoryRows(JSON.parse(readFileSync(new URL(chunk.path,root),'utf8')),frame);
    assert.equal(candles.length,chunk.count);
    assert.equal(candles[0].time,chunk.first);
    assert.equal(candles.at(-1).time,chunk.last);
    assert.ok(chunk.first>previous,`Overlapping ${frame} chunks`);
    previous=chunk.last;
    if(frame==='1m')total+=candles.length;
  }
}
assert.equal(total,catalog.count);
assert.equal(catalog.frames['1m'].length,120);
assert.equal(catalog.frames['1m'][0].first,catalog.first);
assert.equal(catalog.frames['1m'].at(-1).last,catalog.last);
console.log(`PASS: all decade chunks, OHLC integrity and non-overlapping timestamps across 11 timeframes; ${total} M1 candles.`);
