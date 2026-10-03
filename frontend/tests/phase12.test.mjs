import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { productionRegistry } from '../src/indicators/productionRegistry.js';
import { overlayRegistry } from '../src/indicators/overlayRegistry.js';
import { IndicatorRegistry } from '../src/indicators/IndicatorRegistry.js';
import { IndicatorEngine } from '../src/indicators/IndicatorEngine.js';
import { instanceConfig, revealedInput } from '../src/indicators/indicatorValidation.js';
import { rsi, macd, atr, stochastic } from '../src/indicators/paneCalculations.js';
import { pointFromPointer } from '../src/drawings/timeCoordinates.js';

const vector = closes => closes.map((close, i) => ({ time: 100 + i * 60, open: close, high: close + 1, low: close - 1, close }));
const near = (actual, expected) => assert.ok(Math.abs(actual - expected) < 1e-9, `${actual} != ${expected}`);
const values = (points, expected) => { assert.equal(points.length, expected.length); points.forEach((p, i) => near(p.value, expected[i])); };
const keys = ['SMA','EMA','BOLLINGER_BANDS','RSI','MACD','ATR','STOCHASTIC'];
assert.deepEqual(productionRegistry.types(), keys);
for (const type of overlayRegistry.types()) {
  assert.equal(productionRegistry.get(type).placement, 'price');
  assert.equal(productionRegistry.get(type).calculate, overlayRegistry.get(type).calculate);
}
values(rsi(vector([1,2,3,2,2,5]), { period: 2 }), [100,50,50,650/7]);
assert.equal(rsi(vector([1,2,3]), { period: 2 })[0].time, 220);
assert.deepEqual(rsi(vector([1,2]), { period: 2 }), []);
values(rsi(vector([3,2,1]), { period: 2 }), [0]);
values(rsi(vector([2,2,2,2]), { period: 2 }), [50,50]);
const macdBars = vector([1,2,3,10,4]);
const m = macd(macdBars, { fastPeriod: 2, slowPeriod: 3, signalPeriod: 2 });
values(m.macd, [.5,1.5,1/6]); values(m.signal, [1,4/9]); values(m.histogram, [.5,-5/18]);
assert.equal(m.macd[0].time,220); assert.equal(m.signal[0].time,280);
assert.deepEqual(macd(macdBars.slice(0,2), { fastPeriod: 2, slowPeriod: 3, signalPeriod: 2 }), {macd:[],signal:[],histogram:[]});
assert.equal(macd(macdBars.slice(0,3), { fastPeriod: 2, slowPeriod: 3, signalPeriod: 2 }).signal.length,0);
const atrBars = [{high:10,low:8,close:9},{high:13,low:11,close:12},{high:12,low:9,close:10},{high:15,low:14,close:14.5}].map((b,i)=>({...b,open:b.close,time:100+i*60}));
values(atr(atrBars,{period:1}),[2,4,3,5]); values(atr(atrBars,{period:2}),[3,3,4]);
assert.equal(atr(atrBars,{period:2})[0].time,160); assert.deepEqual(atr(atrBars.slice(0,1),{period:2}),[]);
const s = stochastic(vector([1,2,3,2,2,5]), { kPeriod: 2, dPeriod: 2 });
values(s.k,[200/3,200/3,100/3,50,80]); values(s.d,[200/3,50,125/3,65]);
assert.equal(s.k[0].time,160); assert.equal(s.d[0].time,220);
const flat=vector([2,2,2]).map(b=>({...b,high:2,low:2}));
values(stochastic(flat,{kPeriod:2,dPeriod:2}).k,[50,50]); values(stochastic(flat,{kPeriod:2,dPeriod:2}).d,[50]);
assert.deepEqual(stochastic(flat.slice(0,1),{kPeriod:2,dPeriod:2}),{k:[],d:[]});

const parameters={RSI:{period:2},MACD:{fastPeriod:2,slowPeriod:3,signalPeriod:2},ATR:{period:2},STOCHASTIC:{kPeriod:2,dPeriod:2}};
const bars=revealedInput(vector(Array.from({length:80},(_,i)=>20+Math.sin(i)*4+i/10))), original=JSON.stringify(bars);
assert.equal(rsi(bars,{period:14})[0].time,bars[14].time);
const defaultMacd=macd(bars,{fastPeriod:12,slowPeriod:26,signalPeriod:9});
assert.equal(defaultMacd.macd[0].time,bars[25].time);assert.equal(defaultMacd.signal[0].time,bars[33].time);
assert.equal(defaultMacd.histogram[0].time,bars[33].time);
assert.equal(atr(bars,{period:14})[0].time,bars[13].time);
const defaultStoch=stochastic(bars,{kPeriod:14,dPeriod:3});
assert.equal(defaultStoch.k[0].time,bars[13].time);assert.equal(defaultStoch.d[0].time,bars[15].time);
for (const type of Object.keys(parameters)) {
  const spec=productionRegistry.get(type), defaults=instanceConfig(productionRegistry,{id:type,type});
  assert.equal(spec.placement,'pane'); assert.deepEqual(Object.keys(defaults),['id','type','parameters','visible']);
  for(const [key,rule] of Object.entries(spec.parameters)) {
    assert.equal(defaults.parameters[key],rule.default);
    for(const invalid of [0,1001,2.5,Infinity,NaN,'14',rule.min-1])assert.throws(()=>instanceConfig(productionRegistry,{id:type,type,parameters:{...parameters[type],[key]:invalid}}));
  }
  const prefix=bars.slice(0,35), result=spec.calculate(prefix,parameters[type]);
  const mutated=bars.map((b,i)=>i<35?b:{...b,close:999999,high:9999999,low:-99999});
  assert.deepEqual(spec.calculate(revealedInput(mutated.slice(0,35)),parameters[type]),result);
  assert.deepEqual(spec.calculate(prefix,parameters[type]),result,'Deterministic');
  const next=spec.calculate(bars.slice(0,36),parameters[type]);
  const outputs=Array.isArray(result)?{value:result}:result, later=Array.isArray(next)?{value:next}:next;
  for(const [key,points] of Object.entries(outputs)) {
    assert.deepEqual(later[key].slice(0,points.length),points,'Causal '+type);
    assert.equal(later[key].at(-1).time,bars[35].time);
    assert.ok(points.every(p=>p.time<=bars[34].time&&Number.isFinite(p.value)));
    if(type==='RSI'||type==='STOCHASTIC')assert.ok(points.every(p=>p.value>=0&&p.value<=100));
  }
}
assert.equal(JSON.stringify(bars),original); assert.ok(bars.every(Object.isFrozen));
for(const [fastPeriod,slowPeriod] of [[12,12],[26,12],[1000,1000]])assert.throws(()=>instanceConfig(productionRegistry,{id:'x',type:'MACD',parameters:{fastPeriod,slowPeriod}}));
instanceConfig(productionRegistry,{id:'x',type:'MACD',parameters:{fastPeriod:999,slowPeriod:1000,signalPeriod:1000}});
instanceConfig(productionRegistry,{id:'x',type:'RSI',parameters:{period:1000}});
for(const patch of [{placement:'custom'},{references:[30]},{placement:'pane',references:[NaN]},{placement:'pane',range:[100,0]}])assert.throws(()=>new IndicatorRegistry().register({type:'BAD',warmup:0,parameters:{},output:'line',calculate:()=>[],...patch}));
assert.equal(pointFromPointer({}, {}, {paneIndex:1,point:{x:1,y:1}},[]),null,'Pane clicks cannot create price drawings');

function mockChart() {
  const panes=[],active=new Set(),price={paneIndex:()=>panes.indexOf(price),getSeries:()=>[...active].filter(s=>s.pane===price)};
  panes.push(price); let failure=null;
  return {panes:()=>panes,active,price,fail:(color)=>{failure=color;},applyOptions(){},
    addPane(preserve){assert.equal(preserve,true);const pane={paneIndex:()=>panes.indexOf(pane),setStretchFactor(value){assert.ok(value>0);},getSeries:()=>[...active].filter(s=>s.pane===pane)};panes.push(pane);return pane;},
    removePane(index){assert.ok(index>0);assert.equal(panes[index].getSeries().length,0,'Never destroy sibling-owned series');panes.splice(index,1);},
    addSeries(type,options,index=0){const pane=panes[index];assert.ok(pane);if(failure==='create')throw Error('add failure');
      const series={type,pane,options,points:[],lines:new Set(),getPane:()=>pane,
        setData(points){if(failure===options.color)throw Error('data failure');this.points=points;},applyOptions(patch){Object.assign(this.options,patch);},
        createPriceLine(options){const line={options,applyOptions(patch){Object.assign(this.options,patch);}};this.lines.add(line);return line;},removePriceLine(line){assert.ok(this.lines.delete(line));}};
      active.add(series);return series;},removeSeries(series){assert.equal(series.lines.size,0);assert.ok(active.delete(series));}};
}
const chart=mockChart(),engine=new IndicatorEngine(productionRegistry);engine.attach(chart);engine.setCandles(bars);
for(const type of keys)engine.create({id:type,type,...(parameters[type]?{parameters:parameters[type]}:{})});
engine.create({id:'RSI2',type:'RSI'});
assert.equal(chart.panes().length,6);assert.equal(chart.active.size,13);
const paneFor=id=>[...chart.active].find(s=>s.points===engine.output(id)||s.points===engine.output(id)?.macd)?.pane;
const macdPane=paneFor('MACD');assert.equal(macdPane.getSeries().length,3);assert.deepEqual(macdPane.getSeries().map(s=>s.type.type),['Line','Line','Histogram']);
const rsiSeries=[...chart.active].find(s=>s.points===engine.output('RSI'));
assert.deepEqual([...rsiSeries.lines].map(l=>l.options.price),[70,30]);assert.notEqual(rsiSeries.pane,chart.price);
engine.update('RSI',{visible:false});assert.equal(rsiSeries.options.visible,false);assert.ok([...rsiSeries.lines].every(l=>!l.options.lineVisible));
engine.update('RSI',{visible:true,parameters:{period:3}});assert.ok([...rsiSeries.lines].every(l=>l.options.lineVisible));
const before=engine.snapshot();assert.throws(()=>engine.update('MACD',{parameters:{fastPeriod:4,slowPeriod:3,signalPeriod:2}}));assert.deepEqual(engine.snapshot(),before);
engine.remove('MACD');assert.equal(chart.panes().length,5);assert.equal(chart.active.size,10);
assert.equal(paneFor('ATR').paneIndex(),2,'Middle removal reindexes');assert.equal(chart.panes()[0],chart.price);
engine.update('ATR',{parameters:{period:3}});engine.create({id:'MACD-new',type:'MACD',parameters:parameters.MACD});assert.equal(chart.panes().length,6);
engine.setCandles(bars.slice(0,40));assert.equal(engine.output('RSI').at(-1).time,bars[39].time);
engine.setCandles(bars.slice(0,39));assert.equal(engine.output('MACD-new').histogram.at(-1).time,bars[38].time);
engine.setCandles(bars.slice(10,39));engine.setCandles(bars.slice(0,39));
engine.setCandles(bars.filter((_,i)=>i%2===0));assert.equal(engine.output('STOCHASTIC').d.at(-1).time,bars[78].time);
assert.deepEqual(engine.errors(),{});
chart.fail('#f59e0b');engine.setCandles(bars);assert.ok(engine.errors()['MACD-new']);assert.equal(chart.panes().length,4,'Failed multi-output panes and siblings released');
assert.equal(engine.output('RSI').at(-1).time,bars.at(-1).time,'Other instance unaffected');
chart.fail(null);engine.setCandles(bars);assert.equal(chart.panes().length,6);assert.equal(chart.active.size,13);
const replacement=mockChart();engine.attach(replacement);assert.equal(chart.active.size,0);assert.equal(chart.panes().length,1);
for(let i=0;i<4;i++){engine.detach();assert.equal(replacement.active.size,0);assert.equal(replacement.panes().length,1);engine.attach(replacement);assert.equal(replacement.active.size,13);assert.equal(replacement.panes().length,6);}
engine.replaceInstances(engine.snapshot().map(c=>c.id==='RSI'?{id:c.id,type:'SMA'}:c));assert.equal(replacement.panes().length,5);
engine.dispose();assert.equal(replacement.active.size,0);assert.equal(replacement.panes().length,1);
const broken=mockChart(),failed=new IndicatorEngine(productionRegistry);failed.attach(broken);broken.fail('create');failed.create({id:'bad',type:'RSI'});assert.equal(broken.panes().length,1);assert.equal(broken.active.size,0);failed.dispose();

for(const file of readdirSync(new URL('../src/indicators/',import.meta.url))){const source=readFileSync(new URL('../src/indicators/'+file,import.meta.url),'utf8');assert.ok(!/from ['"].*(market|replay|trading|drawings|backend)|localStorage|document\.|window\.|fetch\(|VWAP|movingAverage|TEST_LINE/.test(source));}
const cc=readFileSync(new URL('../src/components/CandleChart.jsx',import.meta.url),'utf8');assert.ok(cc.includes('volumeSeriesRef.current?.setData(candles.map'));assert.ok(cc.includes('syncCandleSeries(series, isNewSession ? [] : previousCandlesRef.current, candles, transition);'));assert.ok(readFileSync(new URL('../src/market/replayTransitions.js',import.meta.url),'utf8').includes('series.setData(next);'));assert.ok(!cc.includes('moveToPane'));
console.log('PASS Phase 12 Wilder/EMA/SMA vectors, bounds/combination/warmup/ranges/prefix causality; official dedicated pane lifecycle/reindex/references/atomic errors/remount/price preservation and isolation.');
