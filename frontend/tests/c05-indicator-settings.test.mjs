// Issue #21 C-05: indicator Style / Placement / pane order / persistence.
import assert from 'node:assert/strict';
import { productionRegistry } from '../src/indicators/productionRegistry.js';
import { IndicatorEngine } from '../src/indicators/IndicatorEngine.js';
import { instanceConfig } from '../src/indicators/indicatorValidation.js';
import { seriesOptions, outputStyle, colorWithOpacity } from '../src/indicators/IndicatorSeriesAdapter.js';
import { IndicatorPreferences } from '../src/workspacePreferences.js';

const bars = Array.from({ length: 120 }, (_, i) => ({ time: 1736121600 + i * 900, open: 100 + Math.sin(i / 5), high: 101 + Math.sin(i / 5), low: 99 + Math.sin(i / 5), close: 100 + Math.sin(i / 4) }));
const cfg = value => instanceConfig(productionRegistry, value);

// --- validation: sparse, strict -------------------------------------------
const plain = cfg({ id: 'a', type: 'EMA' });
assert.deepEqual(Object.keys(plain), ['id', 'type', 'parameters', 'visible'], 'Configs without presentation keep the pre-C-05 shape');
const styled = cfg({ id: 'a', type: 'MACD', style: { macd: { color: '#ff0000', lineWidth: 3, lineStyle: 'dashed', opacity: 0.5 }, histogram: { positiveColor: '#00ff00', negativeColor: '#0000ff' } }, paneHeight: 0.5, references: [0, 1] });
assert.equal(styled.style.macd.lineWidth, 3); assert.equal(styled.paneHeight, 0.5); assert.deepEqual([...styled.references], [0, 1]);
for (const bad of [
  { style: { macd: { color: 'red' } } }, { style: { macd: { lineWidth: 6 } } }, { style: { macd: { lineWidth: 0 } } },
  { style: { macd: { lineStyle: 'wavy' } } }, { style: { macd: { opacity: 1.2 } } }, { style: { nope: { color: '#ffffff' } } },
  { style: { macd: { positiveColor: '#ffffff' } } }, { style: { macd: { extra: 1 } } },
  { placement: 'price' }, { placement: 'floating' }, { paneHeight: 0.05 }, { paneHeight: 2 },
  { references: [1, 1] }, { references: [NaN] }, { references: [1, 2, 3, 4, 5, 6, 7] },
]) assert.throws(() => cfg({ id: 'x', type: 'MACD', ...bad }), undefined, JSON.stringify(bad));
const moved = cfg({ id: 'b', type: 'SMA', placement: 'pane', references: [100] });
assert.equal(moved.placement, 'pane', 'An overlay can move to its own pane');
assert.throws(() => cfg({ id: 'b', type: 'SMA', references: [100] }), undefined, 'References need a pane');
assert.equal(cfg({ id: 'b', type: 'SMA', placement: 'price' }).placement, undefined, 'Default placement is stored sparsely');

// --- presentation mapping --------------------------------------------------
assert.equal(colorWithOpacity('#ff8000', 0.25), 'rgba(255, 128, 0, 0.25)');
assert.equal(colorWithOpacity('#ff8000', 1), '#ff8000');
const macdSpec = productionRegistry.get('MACD'), macdLine = macdSpec.outputs.find(o => o.key === 'macd');
assert.deepEqual(seriesOptions(macdSpec, styled, macdLine), { visible: true, color: 'rgba(255, 0, 0, 0.5)', lineWidth: 3, lineStyle: 2 });
assert.equal(outputStyle(macdSpec, cfg({ id: 'h', type: 'MACD', style: { signal: { visible: false } } }), macdSpec.outputs[1]).visible, false);
assert.equal(seriesOptions(macdSpec, cfg({ id: 'h', type: 'MACD', visible: false }), macdLine).visible, false, 'Instance hide wins');
const psar = productionRegistry.get('PSAR');
assert.equal(seriesOptions(psar, cfg({ id: 'p', type: 'PSAR' }), psar.outputs[0]).pointMarkersVisible, true, 'PSAR renders as dots');

// --- engine with a chart that supports pane.moveTo ------------------------
function chartMock() {
  const panes = [], series = new Set();
  const mkPane = () => { const pane = { stretch: null, paneIndex: () => panes.indexOf(pane), setStretchFactor(v) { this.stretch = v; }, getStretchFactor() { return this.stretch; },
    moveTo(index) { panes.splice(panes.indexOf(pane), 1); panes.splice(index, 0, pane); }, getSeries: () => [...series].filter(s => s.pane === pane) }; return pane; };
  panes.push(mkPane());
  return { panes, series, applyOptions() {}, addPane() { const p = mkPane(); panes.push(p); return p; },
    removePane(i) { panes.splice(i, 1); },
    addSeries(type, options, index = 0) { const s = { pane: panes[index], options: { ...options }, lines: new Set(), data: [],
      setData(d) { this.data = d; }, applyOptions(p) { Object.assign(this.options, p); },
      createPriceLine(o) { const l = { options: o, applyOptions(p) { Object.assign(this.options, p); } }; this.lines.add(l); return l; }, removePriceLine(l) { this.lines.delete(l); } };
      series.add(s); return s; },
    removeSeries(s) { series.delete(s); } };
}
const chart = chartMock(), engine = new IndicatorEngine(productionRegistry);
engine.attach(chart); engine.setCandles(bars);
engine.create({ id: 'rsi', type: 'RSI' }); engine.create({ id: 'macd', type: 'MACD' }); engine.create({ id: 'sma', type: 'SMA' });
const engine_pane = id => chart.panes.findIndex(p => p.getSeries().some(s => ownedBy(s, id)));
const tag = new Map(); for (const s of chart.series) tag.set(s, s.pane === chart.panes[1] ? 'rsi' : s.pane === chart.panes[2] ? 'macd' : 'sma');
const ownedBy = (s, id) => tag.get(s) === id;
assert.equal(chart.panes.length, 3);
assert.equal(engine_pane('rsi'), 1); assert.equal(engine_pane('macd'), 2);

// Style edit updates the live series without recreating it.
const rsiSeries = [...chart.series].find(s => ownedBy(s, 'rsi'));
engine.update('rsi', { style: { value: { color: '#123456', lineWidth: 4, lineStyle: 'dotted' } } });
assert.ok(chart.series.has(rsiSeries)); assert.equal(rsiSeries.options.color, '#123456'); assert.equal(rsiSeries.options.lineWidth, 4); assert.equal(rsiSeries.options.lineStyle, 1);
// Pane height.
engine.update('rsi', { paneHeight: 0.6 }); assert.equal(chart.panes[1].stretch, 0.6);
// Reference lines replaced, not duplicated.
engine.update('rsi', { references: [80, 50, 20] });
assert.deepEqual([...rsiSeries.lines].map(l => l.options.price), [80, 50, 20]);
// Move pane: array order is pane order.
engine.replaceInstances([engine.snapshot()[1], engine.snapshot()[0], engine.snapshot()[2]]);
assert.equal(engine_pane('macd'), 1, 'MACD moved up'); assert.equal(engine_pane('rsi'), 2, 'RSI moved down');
assert.deepEqual(engine.snapshot().map(c => c.id), ['macd', 'rsi', 'sma']);
// Overlay → own pane → back to overlay.
engine.update('sma', { placement: 'pane' });
const smaSeries = [...chart.series].filter(s => !tag.has(s)); assert.equal(smaSeries.length, 1); assert.equal(smaSeries[0].pane.paneIndex(), 3, 'SMA got its own pane');
engine.update('sma', { placement: undefined }); assert.equal(chart.panes.length, 3, 'Pane released when SMA returns to the price chart');
assert.equal([...chart.series].filter(s => !tag.has(s)).at(-1).pane.paneIndex(), 0);
// Histogram rising/falling colours recolour every bar by sign.
engine.update('macd', { style: { histogram: { positiveColor: '#00ff00', negativeColor: '#ff0000' } } });
const hist = [...chart.series].find(s => ownedBy(s, 'macd') && s.data.some(p => p.color));
assert.ok(hist.data.every(p => p.color === (p.value >= 0 ? '#00ff00' : '#ff0000')));
engine.dispose();

// --- persistence round trip -----------------------------------------------
const store = new Map(); const storage = { getItem: k => store.has(k) ? store.get(k) : null, setItem: (k, v) => store.set(k, v) };
const prefs = new IndicatorPreferences(storage, 'acct:session-1', productionRegistry);
assert.deepEqual(prefs.load(), []);
const saved = [cfg({ id: 'm', type: 'MACD', style: { macd: { color: '#abcdef', opacity: 0.8 } }, paneHeight: 0.4, references: [0] }),
  cfg({ id: 'k', type: 'KELTNER', style: { upper: { lineStyle: 'dashed' } } }), cfg({ id: 's', type: 'SUPERTREND', placement: 'pane' })];
assert.equal(prefs.save(saved), true);
const reread = new IndicatorPreferences(storage, 'acct:session-1', productionRegistry).load();
assert.deepEqual(JSON.parse(JSON.stringify(reread)), JSON.parse(JSON.stringify(saved)), 'Style, placement, height, references and order survive reload');
store.set('backtest-indicators-v1:' + encodeURIComponent('acct:session-1'), JSON.stringify({ version: 1, workspace: 'acct:session-1', instances: [{ id: 'm', type: 'MACD', style: { macd: { lineWidth: 99 } } }] }));
const hostile = new IndicatorPreferences(storage, 'acct:session-1', productionRegistry);
assert.deepEqual(hostile.load(), []); assert.equal(hostile.writable, false, 'Invalid stored style keeps the namespace read-only');

console.log('c05 indicator settings: validation, live style, pane order/height/placement, histogram colours, persistence ok');
