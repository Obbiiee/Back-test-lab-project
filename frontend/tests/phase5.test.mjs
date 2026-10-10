import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { DrawingManager } from '../src/drawings/DrawingManager.js';
import { createDrawingRegistry } from '../src/drawings/DrawingRegistry.js';
import { TrendLine } from '../src/drawings/models/TrendLine.js';
import { TrendLineCreation } from '../src/drawings/TrendLineCreation.js';
import { logicalForTimestamp, projectTimestamp, pointFromPointer } from '../src/drawings/timeCoordinates.js';
import { RiskRewardController } from '../src/trading/RiskRewardController.js';
import { aggregateCandles } from '../src/market/candles.js';

const origin = Date.parse('2024-06-03T00:00:00Z') / 1000;
const bars = Array.from({ length: 40 }, (_, i) => ({ time: origin + i * 900, open: 2300, high: 2303, low: 2298, close: 2301, volume: 10 }));
const input = { id: 'line', type: 'trend-line', points: [{ time: origin + 900, price: 2300 }, { time: origin + 4500, price: 2310 }], metadata: { createdOnTimeframe: '15m' } };
const risk = new RiskRewardController(); risk.replace([{ id: 'risk', type: 'long-position', points: input.points }]);
const manager = new DrawingManager();
assert.deepEqual([...manager.registry.entries.keys()], ['trend-line', 'horizontal-line', 'vertical-line', 'rectangle', 'ray', 'fibonacci-retracement', 'arrow', 'text', 'measure']);
assert.throws(() => createDrawingRegistry().register('trend-line', {}), /already registered/);
for (const type of ['unknown', 'constructor', 'long-position', 'short-position']) assert.throws(() => manager.add({ ...input, type }), /Unknown drawing type/);
const model = manager.add(input);
input.points[0].price = 9000;
assert.equal(model.points[0].price, 2300, 'Input mutations cannot change canonical state');
assert.equal(manager.get('line'), model);
assert.deepEqual(manager.getAll(), [model]);
assert.throws(() => manager.add(model), /Duplicate drawing id/);
for (const points of [[], model.points.slice(0, 1), [...model.points, model.points[0]], [{ time: NaN, price: 2 }, model.points[1]]]) {
  assert.throws(() => TrendLine({ ...model, points }));
}
const canonical = TrendLine({ ...model, points: model.points.map(p => ({ ...p, x: 12, y: 45, clientX: 99 })) });
assert.deepEqual(canonical.points, model.points);
assert.ok(!JSON.stringify(canonical).includes('clientX'));
assert.ok(canonical.points.every(p => Object.keys(p).join(',') === 'time,price'));

let currentBars = bars, spacing = 10, offset = 0, priceMultiplier = 2, requests = 0, attached = 0, detached = 0;
const scale = {
  timeToCoordinate: time => { const index = currentBars.findIndex(bar => bar.time === time); return index < 0 ? null : index * spacing + offset; },
  logicalToCoordinate: value => value * spacing + offset,
  coordinateToLogical: value => (value - offset) / spacing,
  coordinateToTime: value => currentBars[Math.round((value - offset) / spacing)]?.time ?? null,
};
const chart = { timeScale: () => scale };
const series = {
  attachPrimitive(p) { attached++; p.attached({ chart, series, requestUpdate: () => requests++ }); },
  detachPrimitive(p) { detached++; p.detached(); },
  priceToCoordinate: value => (2400 - value) * priceMultiplier,
  coordinateToPrice: y => 2400 - y / priceMultiplier,
  setData() { throw new Error('Drawing must never modify market series'); },
};
manager.setTimePoints(bars); manager.attach(series); manager.attach(series);
assert.equal(attached, 1, 'Repeated attachment does not duplicate primitives');
const primitive = manager.primitives.get('line');
assert.equal(primitive.chart, chart);
assert.equal(primitive.paneViews()[0].zOrder(), 'top');
const anchors = JSON.stringify(manager.getAll());
primitive.updateAllViews();
assert.deepEqual(primitive.views[0].projected, [{ x: 10, y: 200 }, { x: 50, y: 180 }]);
spacing = 20; offset = -15; priceMultiplier = 3;
primitive.updateAllViews();
assert.deepEqual(primitive.views[0].projected, [{ x: 5, y: 300 }, { x: 85, y: 270 }], 'Official redraw lifecycle reprojects zoom, pan and price scaling');
let strokes = 0; const path = [];
primitive.paneViews()[0].renderer().draw({ useMediaCoordinateSpace(fn) { fn({ context: {
  save() {}, restore() {}, setLineDash() {}, beginPath() {},
  moveTo: (x, y) => path.push([x, y]), lineTo: (x, y) => path.push([x, y]), stroke() { strokes++; },
} }); } });
assert.equal(strokes, 1); assert.deepEqual(path, [[5, 300], [85, 270]]);

currentBars = aggregateCandles(bars, '1h'); manager.setTimePoints(currentBars); primitive.updateAllViews();
assert.equal(scale.timeToCoordinate(model.points[0].time), null, '5.2.1 exact timestamp absent on H1');
assert.equal(logicalForTimestamp(currentBars, model.points[0].time), .25);
assert.equal(primitive.views[0].projected[0].x, -.25 * 40, 'Missing timestamp maps to fractional logical coordinate');
assert.equal(projectTimestamp(scale, currentBars, model.points[1].time), 10);
currentBars = bars; manager.setTimePoints(bars); primitive.updateAllViews();
assert.equal(JSON.stringify(manager.getAll()), anchors, 'M15 → H1 → M15 preserves exact canonical times and prices');
manager.setTimePoints([...bars, { ...bars.at(-1), time: bars.at(-1).time + 900 }]);
assert.equal(JSON.stringify(manager.getAll()), anchors, 'Replay progression cannot rewrite source anchors');
currentBars = [{ ...bars[0], time: origin - 900 }, ...bars]; manager.setTimePoints(currentBars); primitive.updateAllViews();
assert.equal(JSON.stringify(manager.getAll()), anchors, 'Older history prepending preserves model');
assert.equal(primitive.views[0].projected[0].x, 25);
assert.equal(logicalForTimestamp([], origin), null);
assert.equal(logicalForTimestamp([{ time: origin }], origin + 1), null);
assert.equal(logicalForTimestamp([{ time: 100 }, { time: 400 }], 250), .5);
assert.equal(logicalForTimestamp([{ time: 100 }, { time: 400 }], 700), 2);
assert.equal(projectTimestamp({ timeToCoordinate: t => ({ 100: 40, 400: 100 })[t] ?? null, logicalToCoordinate() { throw new Error('Global indices must not be assumed'); } }, [{ time: 100 }, { time: 400 }], 250), 70, 'Interpolate actual chart timestamps even when global indices differ from the series array');

currentBars = bars; manager.setTimePoints(bars);
assert.deepEqual(pointFromPointer(chart, series, { point: { x: 5, y: 300 } }, bars), { time: bars[1].time, price: 2300 });
const creation = new TrendLineCreation(manager, chart, series, bars, '15m', () => {});
let notifications = 0; const unsubscribe = manager.subscribe(() => notifications++);
creation.click({ point: { x: 5, y: 300 } });
assert.equal(manager.getAll().length, 1, 'Draft stays outside completed collection');
assert.ok(manager.draft?.draft);
const beforePreview = notifications;
creation.move({ point: { x: 25, y: 280 } });
assert.equal(notifications, beforePreview, 'Pointer preview updates requestUpdate without notifying React');
assert.equal(manager.getAll().length, 1);
creation.cancel(); assert.equal(manager.draft, null);
creation.click({ point: { x: 5, y: 300 } }); creation.click({ point: { x: 25, y: 280 } });
assert.equal(manager.getAll().length, 2); assert.equal(manager.draft, null);
assert.equal(manager.getAll()[1].points.length, 2);
manager.detach(); assert.equal(primitive.chart, null); assert.equal(primitive.requestUpdate, null);
assert.equal(manager.getAll().length, 2, 'Detach clears attachment, not canonical models');
manager.attach(series); assert.ok(requests > 0 && detached > 0);
assert.equal(manager.remove('absent'), false); assert.equal(manager.remove('line'), true);
manager.clear(); assert.deepEqual(manager.getAll(), []);
unsubscribe();
assert.equal(risk.objects[0].id, 'risk', 'Risk/Reward ownership untouched');

for (const name of ['DrawingManager.js', 'DrawingRegistry.js', 'DrawingTypes.js', 'TrendLineCreation.js', 'timeCoordinates.js', 'models/TrendLine.js', 'primitives/TrendLinePrimitive.js']) {
  const source = readFileSync(new URL('../src/drawings/' + name, import.meta.url), 'utf8');
  assert.ok(!/localStorage|sessionStorage|\.setData\(|from ['"][^'"]*(trading|legacy|react)/.test(source), name + ' has no storage, trading, React or market mutations');
}
const before = readFileSync(new URL('../../docs/PHASE4_STORAGE_BEFORE.json', import.meta.url), 'utf8');
const after = readFileSync(new URL('../../docs/PHASE4_STORAGE_AFTER.json', import.meta.url), 'utf8');
assert.equal(before, after, 'Existing storage snapshot remains byte-preserved');
console.log('PASS: manager CRUD/registry/isolation, immutable canonical model, primitive lifecycle/canvas, zoom/pan/price scaling, H1 interpolation, replay/history, ephemeral draft, A/B creation and legacy storage preservation.');
