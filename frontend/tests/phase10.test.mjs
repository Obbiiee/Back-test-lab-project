import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { IndicatorRegistry, defaultIndicatorRegistry } from '../src/indicators/IndicatorRegistry.js';
import { IndicatorEngine } from '../src/indicators/IndicatorEngine.js';
import { IndicatorSeriesAdapter } from '../src/indicators/IndicatorSeriesAdapter.js';
import { revealedInput, normalizedOutput } from '../src/indicators/indicatorValidation.js';

const bars = Array.from({ length: 5 }, (_, i) => ({ time: 100 + i * 60, open: i+10, high: i+12, low: i+9, close: i+11, volume: 3 }));
const original = JSON.stringify(bars);
let seen;
const spec = { type: 'TEST_LINE', output: 'line', warmup: 2, parameters: { offset: { default: 0, validate: value => value >= -10 && value <= 10 } },
  calculate: (candles, parameters) => { seen = candles; return candles.map(bar => ({ time: bar.time, value: bar.close + parameters.offset })); } };
const registry = new IndicatorRegistry().register(spec);
assert.equal(registry.get('TEST_LINE').output, 'line');
assert.throws(() => defaultIndicatorRegistry.get('TEST_LINE'));
assert.throws(() => registry.register(spec), /Duplicate/);
assert.throws(() => registry.get('constructor'), /Unknown/);
assert.throws(()=>new IndicatorRegistry().register({...spec,parameters:{offset:{default:NaN,validate:()=>true}}}));
for (const invalid of [{ ...spec, warmup: -1 }, { ...spec, output: 'pane' }, { ...spec, calculate: null }, { ...spec, parameters: { x: { default: {}, validate: () => true } } }]) assert.throws(() => new IndicatorRegistry().register(invalid));
function mockChart() {
  const active = new Set(), removed = [];
  return { active, removed, addSeries(type, options) { const series = { type, options, points: [], applyOptions(value) { Object.assign(this.options, value); }, setData(value) { this.points = [...value]; } }; active.add(series); return series; },
    removeSeries(series) { assert.ok(active.delete(series), 'Remove only live series'); removed.push(series); } };
}
const chart = mockChart(), adapter = new IndicatorSeriesAdapter(), engine = new IndicatorEngine(registry, adapter);
const config = engine.create({ id: 'one', type: 'TEST_LINE' });
assert.deepEqual(config.parameters, { offset: 0 }); assert.equal(config.visible, true);
assert.ok(Object.isFrozen(config) && Object.isFrozen(config.parameters));
assert.deepEqual(engine.output('one'), [], 'Warmup is explicit');
engine.attach(chart); assert.equal(chart.active.size, 1);
engine.attach(chart); assert.equal(chart.active.size, 1, 'Idempotent attach');
engine.setCandles(bars.slice(0, 3));
const prefix = engine.output('one');
assert.equal(prefix.length, 3); assert.equal(prefix.at(-1).time, bars[2].time);
assert.ok(Object.isFrozen(seen) && seen.every(Object.isFrozen));
assert.throws(() => { seen[0].close = 999; });
bars[4].close = 900; engine.setCandles(bars.slice(0, 3));
assert.deepEqual(engine.output('one'), prefix, 'Changing hidden future cannot change current prefix');
bars[4].close = 15;
engine.setCandles(bars); assert.deepEqual(engine.output('one').slice(0,3), prefix, 'Causal reference prefix remains identical after reveal');
assert.equal(engine.output('one').length, 5);
engine.setCandles(bars.slice(2)); engine.setCandles(bars); assert.equal(engine.output('one')[0].time, 100, 'Prepend recomputes ordered full output');
engine.setCandles(bars.filter((_,i) => i % 2 === 0)); assert.deepEqual(engine.output('one').map(point => point.time), [100,220,340]);
engine.setCandles(bars.slice(0,2)); assert.equal(engine.output('one').at(-1).time, 160, 'Rewind clears future');
engine.create({ id: 'two', type: 'TEST_LINE', parameters: { offset: 2 } }); assert.equal(chart.active.size,2);
assert.equal(engine.output('two')[0].value, engine.output('one')[0].value+2);
engine.update('one', { visible: false }); assert.equal([...chart.active][0].options.visible, false);
engine.update('one', { visible: true, parameters: { offset: 1 } }); assert.equal(engine.output('one')[0].value,12);
for (const invalid of [{ id: 'one', type: 'TEST_LINE' }, { id: 'bad', type: 'MISSING' }, { id: '', type: 'TEST_LINE' }, { id: 'bad', type: 'TEST_LINE', visible: 1 }, { id: 'bad', type: 'TEST_LINE', parameters: { offset: 11 } }, { id: 'bad', type: 'TEST_LINE', parameters: { offset: '1' } }, { id: 'bad', type: 'TEST_LINE', parameters: { unknown: 1 } }, { id:'bad',type:'TEST_LINE',pixels:[] }]) assert.throws(() => engine.create(invalid));
const before = engine.snapshot(); assert.throws(() => engine.update('one',{ parameters: { offset: NaN } })); assert.deepEqual(engine.snapshot(), before);
assert.throws(()=>engine.create({id:'null-parameters',type:'TEST_LINE',parameters:null}));
assert.throws(() => engine.replaceInstances([{ id: 'same', type:'TEST_LINE' }, { id:'same',type:'TEST_LINE' }])); assert.deepEqual(engine.snapshot(), before);
assert.throws(() => engine.setCandles([...bars].reverse()));
assert.throws(() => revealedInput([{ ...bars[0], close: NaN }]));
assert.deepEqual(normalizedOutput([{ time:160,value:2 },{ time:100,value:1 }],bars).map(point=>point.time),[100,160]);
for(const invalid of [[{time:999,value:1}],[{time:100,value:NaN}],[{time:100,value:1},{time:100,value:2}],[{time:100,value:1,pixel:3}]]) assert.throws(()=>normalizedOutput(invalid,bars));
registry.register({ ...spec,type:'FAIL',calculate:()=>{ throw Error('isolated failure'); } });
registry.register({ ...spec,type:'FUTURE',calculate:()=>[{time:999,value:1}] });
registry.register({ ...spec,type:'MUTATOR',calculate:input=>{input[0].close=100;return [];} });
engine.create({id:'fail',type:'FAIL'}); engine.create({id:'future',type:'FUTURE'}); engine.create({id:'mutator',type:'MUTATOR'});
assert.equal(chart.active.size,2); assert.equal(Object.keys(engine.errors()).length,3); assert.equal(engine.output('one').length,2);
engine.setCandles(bars); assert.equal(JSON.stringify(bars),original); assert.equal(seen.length,5);
const replacement=mockChart(); engine.attach(replacement); assert.equal(chart.active.size,0); assert.equal(replacement.active.size,2);
engine.detach(); assert.equal(replacement.active.size,0); engine.attach(replacement); assert.equal(replacement.active.size,2);
engine.remove('one'); assert.equal(replacement.active.size,1); assert.deepEqual(engine.output('one'),[]);
engine.replaceInstances([]); assert.equal(replacement.active.size,0);
registry.register({...spec,type:'TEST_HIST',output:'histogram'});engine.create({id:'hist',type:'TEST_HIST'});assert.equal(replacement.active.size,1);
engine.dispose(); engine.dispose(); assert.equal(replacement.active.size,0); assert.throws(()=>engine.create(config),/disposed/);
let fail = true;
registry.register({...spec,type:'RECOVERY',calculate:input=>{if(fail)throw Error('retry');return input.map(bar=>({time:bar.time,value:bar.close}));}});
const recoveryChart=mockChart(), recovery=new IndicatorEngine(registry);
recovery.attach(recoveryChart); recovery.setCandles(bars); recovery.create({id:'retry',type:'RECOVERY'});
assert.equal(recoveryChart.active.size,0); fail=false; recovery.setCandles(bars);
assert.equal(recoveryChart.active.size,1); assert.deepEqual(recovery.errors(),{}); recovery.dispose();
const adapterError=new IndicatorEngine(registry,{attach(){},detach(){},remove(){},sync(config){if(config.id==='bad-adapter')throw Error('adapter failure');}});
adapterError.setCandles(bars);adapterError.create({id:'bad-adapter',type:'TEST_LINE'});adapterError.create({id:'good-adapter',type:'TEST_LINE'});
assert.equal(adapterError.output('good-adapter').length,5);assert.equal(adapterError.output('bad-adapter').length,0);adapterError.dispose();
registry.register({...spec,type:'THROW_NULL',calculate:()=>{throw null;}});
const nullError=new IndicatorEngine(registry);nullError.setCandles(bars);nullError.create({id:'null',type:'THROW_NULL'});assert.equal(nullError.errors().null,'null');nullError.dispose();
assert.ok(!Object.hasOwn(revealedInput([{...bars[0],future:bars.slice(1)}])[0],'future'));
for(const file of readdirSync(new URL('../src/indicators/',import.meta.url))) {
  const source=readFileSync(new URL('../src/indicators/'+file,import.meta.url),'utf8');
  assert.ok(!/from ['"].*(trading|drawings|market)|localStorage|document\.|window\.|fetch\(/.test(source),'Indicator domain has no ownership crossover: '+file);
  // Phase 11 authorizes SMA/EMA/BB in the same foundation; legacy and excluded products remain forbidden.
  assert.ok(!/movingAverage|RSI|MACD|Stochastic|TEST_LINE/.test(source),'No legacy, excluded or reference product indicators');
}
const chartSource=readFileSync(new URL('../src/components/CandleChart.jsx',import.meta.url),'utf8');
assert.ok(/series\.setData\(candles\);\s+indicatorEngine\.setCandles\(candles\);/.test(chartSource));
assert.ok(chartSource.includes('volumeSeriesRef.current?.setData(candles.map'));
assert.ok(chartSource.indexOf('indicatorEngine.detach();') < chartSource.indexOf('chart.remove();'));
assert.ok(!/movingAverage|indicator:|DrawingsLayer/.test(chartSource));
for(const domain of ['market','trading','drawings']){
  const check=directory=>{for(const entry of readdirSync(directory,{withFileTypes:true})){const file=new URL(entry.name+(entry.isDirectory()?'/':''),directory);if(entry.isDirectory())check(file);else assert.ok(!/from ['"].*indicators\//.test(readFileSync(file,'utf8')),'Protected domain must not depend on indicators');}};
  check(new URL('../src/'+domain+'/',import.meta.url));
}
console.log('PASS Phase 10 registry/config validation, frozen revealed input, deterministic reference/prefix/anti-look-ahead, normalized output, warmup, append/rewind/prepend/timeframe, instances, visibility, isolation, lifecycle/remount/no leaks, protected boundaries and native Volume.');
