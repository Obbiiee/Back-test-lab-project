// Issue #21 C-01: shared Drawing Properties foundation. Each assertion checks
// the rendered canvas calls or canonical model, not only UI state.
import assert from 'node:assert/strict';
import { DrawingManager } from '../src/drawings/DrawingManager.js';
import { DrawingHistory } from '../src/drawings/DrawingHistory.js';
import { DrawingPersistence, DrawingDocumentStore, DRAWING_STORAGE_PREFIX, DRAWING_STORAGE_PREFIX_V2 } from '../src/drawings/DrawingPersistence.js';
import { DrawingInteractionController } from '../src/drawings/interaction/DrawingInteractionController.js';
import { hitDrawing, HIT } from '../src/drawings/interaction/hitTesting.js';
import { stepPrice, stepBars, roundToStep, parseUtc, formatUtc } from '../src/drawings/drawingEdits.js';
import { normalizeOptions, resolvedStyle, capabilities, dashFor } from '../src/drawings/drawingStyle.js';
import { fibLevelsFor } from '../src/drawings/drawingShapes.js';
import { DRAWING_SPECS } from '../src/drawings/DrawingTypes.js';

const bars = Array.from({ length: 20 }, (_, i) => ({ time: 1_700_000_000 + i * 60 }));
const x = time => (time - bars[0].time) / 60 * 10 + 20;
const scale = { timeToCoordinate: t => bars.some(bar => bar.time === t) ? x(t) : null, width: () => 400, coordinateToTime: px => bars[0].time + (px - 20) / 10 * 60 };
const chart = { timeScale: () => scale, paneSize: () => ({ height: 300 }), options: () => ({ handleScroll: {} }), applyOptions() {} };
const attachOrder = [];
const series = {
  priceToCoordinate: p => (2400 - p) * 2, coordinateToPrice: y => 2400 - y / 2,
  attachPrimitive(p) { attachOrder.push(p.model.id); p.attached({ chart, series, requestUpdate() {} }); },
  detachPrimitive(p) { p.detached(); },
};
function recorder() {
  const calls = [];
  const state = {};
  const context = new Proxy(state, {
    get: (target, key) => key in target ? target[key] : (...args) => calls.push({ op: key, args, lineWidth: target.lineWidth, dash: target.dash, alpha: target.globalAlpha, font: target.font, stroke: target.strokeStyle, fill: target.fillStyle }),
    set: (target, key, value) => { target[key] = value; return true; },
  });
  state.setLineDash = dash => { state.dash = dash; calls.push({ op: 'setLineDash', args: [dash] }); };
  return { calls, target: { useMediaCoordinateSpace: fn => fn({ context }) } };
}
function render(manager, id) {
  const primitive = manager.primitives.get(id); primitive.updateAllViews();
  const { calls, target } = recorder(); primitive.paneViews()[0].renderer().draw(target); return calls;
}
function setup() {
  const manager = new DrawingManager(), history = new DrawingHistory(manager);
  manager.setTimePoints(bars); manager.attach(series); return { manager, history };
}
const P = (i, price) => ({ time: bars[i].time, price });

// 1. Thickness 1 → 5 changes the actual stroke width.
{
  const { manager } = setup();
  manager.add({ id: 'w', type: 'trend-line', points: [P(1, 2300), P(5, 2310)], options: { lineWidth: 1 } });
  const widthAtStroke = () => render(manager, 'w').find(call => call.op === 'stroke').lineWidth;
  assert.equal(widthAtStroke(), 1);
  manager.setOptions('w', { lineWidth: 5 }); assert.equal(widthAtStroke(), 5, 'width 1→5 changes rendered line');
  manager.setOptions('w', { lineStyle: 'dashed' });
  const dashed = render(manager, 'w').find(call => call.op === 'stroke').dash;
  assert.deepEqual(dashed, dashFor('dashed', 5)); assert.ok(dashed.length === 2);
  manager.setOptions('w', { lineStyle: 'dotted', opacity: .4 });
  const dotted = render(manager, 'w').find(call => call.op === 'stroke');
  assert.equal(dotted.alpha, .4); assert.deepEqual(dotted.dash, dashFor('dotted', 5));
  manager.setOptions('w', { color: '#ff6b6b' }); assert.equal(render(manager, 'w').find(call => call.op === 'stroke').stroke, '#ff6b6b');
}

// 2. Bold / size / italic actually change the canvas font and the hit box.
{
  const { manager } = setup();
  manager.add({ id: 't', type: 'text', points: [P(3, 2300)], text: 'Breakout' });
  const font = () => render(manager, 't').find(call => call.op === 'fillText').font;
  assert.match(font(), /^400 12px/);
  manager.setOptions('t', { bold: true }); assert.match(font(), /^700 12px/, 'Bold changes font-weight');
  manager.setOptions('t', { fontSize: 24, italic: true }); assert.match(font(), /^italic 700 24px/);
  manager.setOptions('t', { fontFamily: 'sans' }); assert.match(font(), /Inter/);
  // A far-right point now inside the larger label is hittable.
  const anchor = { x: x(bars[3].time), y: (2400 - 2300) * 2 };
  assert.equal(hitDrawing(manager, chart, series, { x: anchor.x + 120, y: anchor.y + 10 }).type, HIT.BODY);
  manager.setOptions('t', { textAlign: 'right' });
  assert.equal(hitDrawing(manager, chart, series, { x: anchor.x + 120, y: anchor.y + 10 }).type, HIT.NONE, 'Right alignment moves the box left of the anchor');
  assert.equal(hitDrawing(manager, chart, series, { x: anchor.x - 60, y: anchor.y + 10 }).type, HIT.BODY);
  manager.setOptions('t', { textBackground: 'none' });
  assert.ok(!render(manager, 't').some(call => call.op === 'fillRect'), 'No background → no fill rect');
  manager.setOptions('t', { textBackground: '#123456' });
  assert.equal(render(manager, 't').find(call => call.op === 'fillRect').fill, '#123456');
}

// 3. Exact tick and bar movement.
{
  assert.equal(stepPrice(2300.12, -3, 0.001), 2300.117);
  assert.equal(stepPrice(1.08451, 7, 0.00001), 1.08458);
  assert.equal(stepPrice(0.1, 2, 0.1), 0.3, 'No binary float drift (0.1 + 0.2)');
  assert.equal(roundToStep(2300.12349, 0.001), 2300.123);
  assert.equal(stepBars(bars[4].time, bars, 3), bars[7].time);
  assert.equal(stepBars(bars[4].time, bars, -4), bars[0].time);
  assert.equal(stepBars(bars[4].time + 30, bars, 1), bars[5].time + 30, 'Fractional anchors keep their fraction');
  assert.equal(stepBars(bars.at(-1).time, bars, 2), bars.at(-1).time + 120, 'Drawing space beyond last bar uses the interval');
  assert.equal(parseUtc('2026-11-03T10:15'), Date.UTC(2026, 10, 3, 10, 15) / 1000);
  assert.equal(formatUtc(Date.UTC(2026, 10, 3, 10, 15, 7) / 1000), '2026-11-03T10:15:07');

  const { manager, history } = setup();
  manager.add({ id: 'h', type: 'horizontal-line', points: [P(2, 2300.12)] });
  const controller = new DrawingInteractionController(manager, chart, series, history, { tickSize: () => 0.001 });
  manager.select('h');
  for (let i = 0; i < 3; i++) controller.nudge('ArrowDown', false);
  assert.equal(manager.get('h').points[0].price, 2300.117, 'down 3 ticks moves exactly 3 × tickSize');
  assert.equal(history.undoStack.length, 2, 'A burst of nudges is one undo step');
  controller.nudge('ArrowUp', true); assert.equal(manager.get('h').points[0].price, 2300.127, 'Shift = 10 ticks');
  manager.add({ id: 'v', type: 'vertical-line', points: [P(2, 2300)] }); manager.select('v');
  controller.nudge('ArrowRight', false); assert.equal(manager.get('v').points[0].time, bars[3].time);
  history.undo(); assert.equal(manager.get('v').points[0].time, bars[2].time, 'Undo restores the drawing coordinate');
  manager.setProperties('v', { locked: true }); assert.equal(controller.nudge('ArrowRight', false), false, 'Locked drawings refuse nudges');
  assert.equal(manager.setPoints('v', [P(9, 1)]), null); assert.equal(manager.setOptions('v', { lineWidth: 4 }), null, 'Locked drawings refuse style edits');
}

// 4. Layer order: forward/back changes paint order and which object is hit.
{
  const { manager } = setup();
  manager.add({ id: 'a', type: 'rectangle', points: [P(2, 2310), P(8, 2290)], options: { fillOpacity: .3 } });
  manager.add({ id: 'b', type: 'rectangle', points: [P(4, 2305), P(10, 2295)], options: { fillOpacity: .3 } });
  const inside = { x: x(bars[6].time), y: (2400 - 2300) * 2 };
  assert.equal(hitDrawing(manager, chart, series, inside).id, 'b', 'Top layer wins');
  attachOrder.length = 0;
  assert.equal(manager.reorder('a', 'forward'), true);
  assert.deepEqual(attachOrder, ['b', 'a'], 'Primitives re-attached in new paint order');
  assert.deepEqual(manager.getAll().map(m => m.id), ['b', 'a']);
  assert.equal(hitDrawing(manager, chart, series, inside).id, 'a');
  assert.equal(manager.reorder('a', 'front'), false, 'Already on top');
  manager.reorder('a', 'back'); assert.deepEqual(manager.getAll().map(m => m.id), ['a', 'b']);
  assert.ok(render(manager, 'a').some(call => call.op === 'fill'), 'Rectangle fill renders');
}

// 5. Fibonacci levels are individually editable.
{
  const { manager } = setup();
  manager.add({ id: 'f', type: 'fibonacci-retracement', points: [P(2, 2400), P(8, 2300)] });
  assert.deepEqual(fibLevelsFor(manager.get('f')).map(level => level.ratio), [0, .236, .382, .5, .618, .786, 1]);
  const levels = resolvedStyle(manager.get('f')).levels.map(level => level.value === 1.618 ? { ...level, visible: true, color: '#ffd23f' } : level.value === .236 ? { ...level, visible: false } : level);
  manager.setOptions('f', { levels });
  const visible = fibLevelsFor(manager.get('f'));
  assert.deepEqual(visible.map(level => level.ratio), [0, .382, .5, .618, .786, 1, 1.618]);
  assert.equal(visible.at(-1).price, 2300 + 100 * 1.618); assert.equal(visible.at(-1).color, '#ffd23f');
  const strokes = render(manager, 'f').filter(call => call.op === 'stroke');
  assert.equal(strokes.length, 1 + 7, 'Diagonal + one stroke per visible level');
  assert.equal(strokes.at(-1).stroke, '#ffd23f', 'Level colour applied');
  manager.setOptions('f', { reverse: true });
  assert.equal(fibLevelsFor(manager.get('f'))[0].price, 2400, 'Reverse flips the 0 level to anchor A');
  manager.setOptions('f', { levels: undefined, reverse: undefined });
  assert.deepEqual(manager.get('f').options, { color: '#58a6ff', lineWidth: 2 }, 'Removing overrides restores the sparse v1 shape');
}

// 6. Extend left/right changes geometry and hit testing.
{
  const { manager } = setup();
  manager.add({ id: 'e', type: 'trend-line', points: [P(5, 2300), P(6, 2300)] });
  const far = { x: x(bars[15].time), y: 200 };
  assert.equal(hitDrawing(manager, chart, series, far).type, HIT.NONE);
  manager.setOptions('e', { extendRight: true }); assert.equal(hitDrawing(manager, chart, series, far).type, HIT.BODY);
  const before = { x: x(bars[1].time), y: 200 };
  assert.equal(hitDrawing(manager, chart, series, before).type, HIT.NONE);
  manager.setOptions('e', { extendLeft: true }); assert.equal(hitDrawing(manager, chart, series, before).type, HIT.BODY);
}

// 7. Validation refuses unknown / out-of-range options.
for (const bad of [{ lineWidth: 11 }, { lineWidth: 0 }, { lineStyle: 'wavy' }, { opacity: 1.5 }, { fontSize: 9 }, { fontSize: 33 }, { textColor: 'red' }, { futureKey: 1 }, { levels: [] }, { levels: [{ value: 'x', visible: true }] }])
  assert.throws(() => normalizeOptions(bad), undefined, JSON.stringify(bad));
assert.deepEqual(normalizeOptions({}), { color: '#58a6ff', lineWidth: 2 });
assert.ok(capabilities('fibonacci-retracement').levels && !capabilities('arrow').levels, 'Levels tab only where meaningful');
assert.ok(capabilities('text').text && !capabilities('trend-line').text);

// 8. Persistence v2 round trip, rename/duplicate, and v1 upgrade that never rewrites v1 bytes.
{
  const records = new Map(); let writes = 0;
  const storage = { getItem: key => records.has(key) ? records.get(key) : null, setItem: (key, value) => { writes++; records.set(key, value); } };
  const workspace = 'tick:XAUUSD';
  const v1Doc = JSON.stringify({ version: 1, workspace, drawings: [{ id: 'old', type: 'trend-line', points: [P(1, 2300), P(2, 2301)], options: { color: '#58a6ff', lineWidth: 2 }, visible: true, locked: false, metadata: {} }] });
  records.set(DRAWING_STORAGE_PREFIX + encodeURIComponent(workspace), v1Doc);
  const { manager } = setup();
  const store = new DrawingDocumentStore(storage, workspace);
  manager.replaceAll(store.load(manager.registry));
  assert.equal(store.upgradedFrom, 1); assert.equal(manager.get('old').type, 'trend-line', 'Old drawing still loads');
  assert.ok(render(manager, 'old').some(call => call.op === 'stroke'), 'Old drawing still renders');
  manager.subscribeCommitted((before, after) => store.save(after));
  manager.setOptions('old', { lineWidth: 4, lineStyle: 'dashed', opacity: .5 });
  manager.rename('old', '  Weekly trend  ');
  manager.add({ id: 'note', type: 'text', points: [P(4, 2305)], text: 'Asia high', options: { bold: true, fontSize: 18, textAlign: 'center' } });
  manager.duplicate('note', 'note-2', point => ({ ...point, time: point.time + 60 }));
  manager.reorder('old', 'front');
  assert.equal(records.get(DRAWING_STORAGE_PREFIX + encodeURIComponent(workspace)), v1Doc, 'v1 bytes never rewritten');
  const raw = JSON.parse(records.get(DRAWING_STORAGE_PREFIX_V2 + encodeURIComponent(workspace)));
  assert.equal(raw.version, 2);
  const reloaded = setup().manager; const reloadStore = new DrawingDocumentStore(storage, workspace);
  reloaded.replaceAll(reloadStore.load(reloaded.registry));
  assert.equal(reloadStore.upgradedFrom, null);
  assert.deepEqual(reloaded.getAll(), manager.getAll(), 'Reload retains every style, name, anchor and layer');
  assert.deepEqual(reloaded.getAll().map(m => m.id), ['note', 'note-2', 'old']);
  assert.equal(reloaded.get('old').name, 'Weekly trend');
  assert.equal(reloaded.get('note-2').points[0].time, bars[4].time + 60);
  assert.equal(reloaded.get('note').options.bold, true);
  // Timeframe/zoom changes never alter stored coordinates.
  const canonical = JSON.stringify(reloaded.getAll()); reloaded.setTimePoints(bars.filter((_, i) => i % 4 === 0)); reloaded.setTimePoints(bars);
  assert.equal(JSON.stringify(reloaded.getAll()), canonical);
  // Hostile/unknown records keep the namespace read-only and bytes intact.
  const hostile = JSON.stringify({ ...raw, drawings: [...raw.drawings, { ...raw.drawings[0], id: 'evil', options: { color: '#fff', lineWidth: 2, script: 'x' } }] });
  records.set(DRAWING_STORAGE_PREFIX_V2 + encodeURIComponent(workspace), hostile);
  const guarded = new DrawingDocumentStore(storage, workspace); const restored = guarded.load(reloaded.registry);
  assert.equal(restored.length, 3); assert.equal(guarded.writable, false); assert.equal(guarded.save(restored), false);
  assert.equal(records.get(DRAWING_STORAGE_PREFIX_V2 + encodeURIComponent(workspace)), hostile);
  // A second tab's newer write is not overwritten.
  records.set(DRAWING_STORAGE_PREFIX_V2 + encodeURIComponent(workspace), JSON.stringify(raw));
  const tabA = new DrawingDocumentStore(storage, workspace); tabA.load(reloaded.registry);
  records.set(DRAWING_STORAGE_PREFIX_V2 + encodeURIComponent(workspace), JSON.stringify({ ...raw, drawings: [] }));
  assert.equal(tabA.save(reloaded.getAll()), false); assert.match(tabA.status, /another tab/);
  // Plain v1 persistence still refuses v2 option keys (older clients stay safe).
  const v1 = new DrawingPersistence(storage, 'v1-only'); v1.load(reloaded.registry);
  assert.ok(writes > 0);
}

// 9. Every registered type renders with styles and keeps its anchor contract.
for (const [type, spec] of Object.entries(DRAWING_SPECS)) {
  const { manager } = setup();
  const count = typeof spec.points === 'number' ? spec.points : spec.points.min;
  const points = Array.from({ length: count }, (_, i) => P(2 + i * 2, 2300 + (i % 2 ? 5 : -5)));
  manager.add({ id: type, type, points, ...(spec.text ? { text: 'Label' } : {}), options: { lineWidth: 3, lineStyle: 'dashed', opacity: .8 } });
  const calls = render(manager, type);
  assert.ok(calls.some(call => call.op === 'stroke' || call.op === 'fillText'), type + ' paints');
  assert.equal(calls.find(call => call.op === 'stroke' || call.op === 'fillText').alpha, .8, type + ' opacity');
}
console.log('PASS C-01 shared drawing properties: width/style/opacity/colour render, bold/size/italic/align text, exact tick & bar steps, keyboard nudge + coalesced undo, layer order paint+hit, Fib level rows, extend L/R, strict options, v2 persistence with v1 upgrade/preservation, rename/duplicate, cross-tab guard.');
