import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { performance } from 'node:perf_hooks';
import { overlayRegistry } from '../src/indicators/overlayRegistry.js';
import { IndicatorRegistry } from '../src/indicators/IndicatorRegistry.js';
import { IndicatorEngine } from '../src/indicators/IndicatorEngine.js';
import { instanceConfig, revealedInput, normalizedIndicatorOutput } from '../src/indicators/indicatorValidation.js';
import { sma, ema, bollinger } from '../src/indicators/overlayCalculations.js';

const candleVector = values => values.map((close,index)=>({time:100+index*60,open:close,high:close+1,low:close-1,close}));
const bars=revealedInput(candleVector([1,2,3,10,4])), unchanged=JSON.stringify(bars);
const close=(actual,expected)=>assert.ok(Math.abs(actual-expected)<=1e-10*Math.max(1,Math.abs(expected)),`${actual} != ${expected}`);
const values=points=>points.map(point=>point.value);
assert.deepEqual(overlayRegistry.types(),['SMA','EMA','BOLLINGER_BANDS']);
for(const type of ['TEST_LINE','RSI','MACD','ATR','STOCHASTIC','VWAP'])assert.throws(()=>overlayRegistry.get(type));
assert.deepEqual(values(sma(bars,{period:3})),[2,5,17/3]);
assert.deepEqual(values(ema(bars,{period:3})),[2,6,5]);
assert.equal(ema(bars,{period:3})[0].time,bars[2].time,'EMA seed occurs at candle period');
assert.equal(ema(bars,{period:3})[0].value,sma(bars,{period:3})[0].value,'SMA seed, not first close');
assert.deepEqual(values(ema(bars,{period:1})),bars.map(bar=>bar.close));
assert.deepEqual(values(sma(bars,{period:1})),bars.map(bar=>bar.close));
const bb=bollinger(bars,{period:3,multiplier:2});
assert.deepEqual(values(bb.basis),[2,5,17/3]);
const deviations=[Math.sqrt(2/3),Math.sqrt(38/3),Math.sqrt(86/9)];
bb.basis.forEach((point,index)=>{close(bb.upper[index].value,point.value+2*deviations[index]);close(bb.lower[index].value,point.value-2*deviations[index]);});
const two=bollinger(revealedInput(candleVector([1,3])),{period:2,multiplier:2});
assert.deepEqual([two.basis[0].value,two.upper[0].value,two.lower[0].value],[2,4,0],'Population N, not sample N-1');
const flat=bollinger(revealedInput(candleVector([2300,2300,2300])),{period:2,multiplier:2});
assert.deepEqual(flat.upper,flat.basis);assert.deepEqual(flat.lower,flat.basis);
for(const type of overlayRegistry.types()){
  const config=instanceConfig(overlayRegistry,{id:type,type}); assert.equal(config.parameters.period,20);
  if(type==='BOLLINGER_BANDS')assert.equal(config.parameters.multiplier,2);
  const min=type==='BOLLINGER_BANDS'?2:1;
  for(const period of [min,1000])assert.equal(instanceConfig(overlayRegistry,{id:'p',type,parameters:{period}}).parameters.period,period);
  for(const period of [min-1,1001,2.5,NaN,Infinity,'20'])assert.throws(()=>instanceConfig(overlayRegistry,{id:'p',type,parameters:{period}}));
  const short=overlayRegistry.get(type).calculate(bars,{period:20,multiplier:2});
  assert.ok((Array.isArray(short)?[short]:Object.values(short)).every(output=>output.length===0),'No early warmup point');
  const spec=overlayRegistry.get(type), parameters={period:3,...(type==='BOLLINGER_BANDS'?{multiplier:2}:{})};
  const first=normalizedIndicatorOutput(spec,spec.calculate(bars.slice(0,3),parameters),bars.slice(0,3));
  assert.deepEqual(first,normalizedIndicatorOutput(spec,spec.calculate(bars.slice(0,3),parameters),bars.slice(0,3)));
  const full=candleVector([1,2,3,10,4]); full[3].close=900;full[4].close=-900;
  assert.deepEqual(first,normalizedIndicatorOutput(spec,spec.calculate(revealedInput(full.slice(0,3)),parameters),full.slice(0,3)),'Hidden future mutation: '+type);
  const later=normalizedIndicatorOutput(spec,spec.calculate(bars,parameters),bars);
  if(Array.isArray(later))assert.deepEqual(later.slice(0,first.length),first);else for(const key of Object.keys(later))assert.deepEqual(later[key].slice(0,first[key].length),first[key]);
}
for(const multiplier of [0,-1,20.01,NaN,Infinity,'2'])assert.throws(()=>instanceConfig(overlayRegistry,{id:'bb',type:'BOLLINGER_BANDS',parameters:{multiplier}}));
for(const multiplier of [0.001,20])assert.equal(instanceConfig(overlayRegistry,{id:'bb',type:'BOLLINGER_BANDS',parameters:{multiplier}}).parameters.multiplier,multiplier);
assert.equal(JSON.stringify(bars),unchanged);assert.ok(bars.every(Object.isFrozen));
assert.throws(()=>normalizedIndicatorOutput(overlayRegistry.get('BOLLINGER_BANDS'),{basis:[],upper:[]},bars));
assert.throws(()=>normalizedIndicatorOutput(overlayRegistry.get('BOLLINGER_BANDS'),{basis:[],upper:[],lower:[{time:999,value:1}]},bars));
for(const outputs of [[],[{key:'same',outputType:'line'},{key:'same',outputType:'line'}],[{key:'bad',outputType:'pane'}],[{key:'bad',outputType:'line',options:{priceScaleId:'new-pane'}}]])assert.throws(()=>new IndicatorRegistry().register({type:'INVALID',warmup:0,parameters:{},outputs,calculate:()=>({})}));

function chartMock(){
  const active=new Set(), removed=[];let failAt=null;
  return {active,removed,failAt(index){failAt=index;},addSeries(type,options){const series={type,options,points:[],applyOptions(patch){Object.assign(this.options,patch);},setData(points){if(failAt===options.color)throw Error('series update failure');this.points=[...points];}};active.add(series);return series;},removeSeries(series){assert.ok(active.delete(series));removed.push(series);}};
}
const chart=chartMock(), engine=new IndicatorEngine(overlayRegistry);engine.attach(chart);engine.setCandles(bars);
engine.create({id:'sma-1',type:'SMA',parameters:{period:3}});engine.create({id:'sma-2',type:'SMA',parameters:{period:1}});engine.create({id:'ema',type:'EMA',parameters:{period:3}});engine.create({id:'bb',type:'BOLLINGER_BANDS',parameters:{period:3}});
assert.equal(chart.active.size,6);assert.deepEqual(engine.output('bb'),bb);
engine.update('bb',{visible:false});assert.equal([...chart.active].filter(series=>!series.options.visible).length,3);
engine.update('bb',{visible:true,parameters:{period:2,multiplier:1}});assert.deepEqual(engine.output('bb'),bollinger(bars,{period:2,multiplier:1}));
const configs=engine.snapshot();assert.throws(()=>engine.update('bb',{parameters:{period:1}}));assert.deepEqual(engine.snapshot(),configs);
engine.setCandles(bars.slice(0,3));assert.equal(engine.output('ema').at(-1).time,bars[2].time);assert.equal(engine.output('bb').basis.at(-1).time,bars[2].time);
engine.setCandles(bars);assert.equal(engine.output('bb').basis.length,4);
engine.setCandles(bars.slice(2));engine.setCandles(bars);assert.equal(engine.output('bb').basis[0].time,bars[1].time,'Prepend');
engine.setCandles([bars[0],bars[2],bars[4]]);assert.deepEqual(engine.output('bb').basis.map(point=>point.time),[220,340],'Timeframe replacement');
const newChart=chartMock();engine.attach(newChart);assert.equal(chart.active.size,0);assert.equal(newChart.active.size,6);
engine.detach();assert.equal(newChart.active.size,0);engine.attach(newChart);assert.equal(newChart.active.size,6);
engine.remove('bb');assert.equal(newChart.active.size,3);engine.create({id:'bb',type:'BOLLINGER_BANDS',parameters:{period:2}});
newChart.failAt('#38bdf8');engine.setCandles(bars);assert.equal(newChart.active.size,3,'Failed sibling clears all Bollinger series');assert.deepEqual(engine.output('bb'),{basis:[],upper:[],lower:[]});assert.ok(engine.errors().bb);assert.equal(engine.output('sma-1').length,3);
newChart.failAt(null);engine.setCandles(bars);assert.equal(newChart.active.size,6);assert.equal(engine.errors().bb,undefined);
engine.replaceInstances(engine.snapshot().map(config=>config.id==='bb'?{id:'bb',type:'SMA',parameters:{period:2}}:config));assert.equal(newChart.active.size,4,'Type replacement releases every old output');
engine.dispose();assert.equal(newChart.active.size,0);
const badRegistry=new IndicatorRegistry().register({type:'BAD_BANDS',warmup:0,parameters:{},outputs:overlayRegistry.get('BOLLINGER_BANDS').outputs,calculate:()=>({basis:[{time:100,value:1}],upper:[{time:999,value:2}],lower:[]})});
badRegistry.register({type:'GOOD_LINE',warmup:0,parameters:{},output:'line',calculate:input=>input.map(bar=>({time:bar.time,value:bar.close}))});
const badChart=chartMock(),badEngine=new IndicatorEngine(badRegistry);badEngine.attach(badChart);badEngine.setCandles(bars);badEngine.create({id:'good',type:'GOOD_LINE'});badEngine.create({id:'bad',type:'BAD_BANDS'});assert.equal(badChart.active.size,1);assert.ok(badEngine.errors().bad);assert.equal(badEngine.output('good').length,bars.length);assert.equal(badEngine.errors().good,undefined);badEngine.dispose();assert.equal(badChart.active.size,0);
// Nested instance/output identity avoids delimiter collisions.
const collision=new IndicatorEngine(overlayRegistry),collisionChart=chartMock();collision.attach(collisionChart);collision.setCandles(bars);collision.create({id:'a:basis',type:'SMA',parameters:{period:1}});collision.create({id:'a',type:'BOLLINGER_BANDS',parameters:{period:2}});assert.equal(collisionChart.active.size,4);collision.remove('a');assert.equal(collisionChart.active.size,1);collision.dispose();
const stressBars=revealedInput(candleVector(Array.from({length:5000},(_,i)=>2300+Math.sin(i/7)*20+i/1000)));
const stress=new IndicatorEngine(overlayRegistry),stressChart=chartMock();stress.attach(stressChart);stress.setCandles(stressBars);const started=performance.now();
for(let i=0;i<12;i++)stress.create({id:'stress'+i,type:overlayRegistry.types()[i%3],parameters:{period:20+i*5}});
assert.equal(stressChart.active.size,20);assert.deepEqual(stress.errors(),{});stress.setCandles(stressBars.slice(0,-1));assert.deepEqual(stress.errors(),{});const elapsed=performance.now()-started;stress.dispose();assert.equal(stressChart.active.size,0);
for(const file of readdirSync(new URL('../src/indicators/',import.meta.url))){const source=readFileSync(new URL('../src/indicators/'+file,import.meta.url),'utf8');assert.ok(!/from ['"].*(market|replay|trading|drawings)|localStorage|document\.|window\.|fetch\(|movingAverage|TEST_LINE/.test(source));}
const workspace=readFileSync(new URL('../src/FigmaWorkspace.jsx',import.meta.url),'utf8');assert.ok(workspace.includes('indicatorRegistry={overlayRegistry} indicatorInstances={indicatorInstances}'));assert.ok(workspace.includes('<IndicatorControls'));
const candleChart=readFileSync(new URL('../src/components/CandleChart.jsx',import.meta.url),'utf8');assert.ok(candleChart.includes('volumeSeriesRef.current?.setData(candles.map'));assert.ok(!/movingAverage|indicator:/.test(candleChart));
console.log(`PASS Phase 11 known vectors/SMA-seeded EMA/population BB, defaults/bounds/warmup, causal prefix/frozen input, multi-output atomics/failure recovery/lifecycle/no leaks, production types/isolation; stress 12 instances, 5000 bars: ${elapsed.toFixed(1)}ms (non-gating measurement).`);
