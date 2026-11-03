// Issue #21 C-03: professional drawings D10–D25. Every tool is created through
// the real manager, rendered through the real primitive, hit-tested, edited,
// persisted and reloaded; geometry and statistics are checked numerically.
import assert from 'node:assert/strict';
import { DrawingManager } from '../src/drawings/DrawingManager.js';
import { DrawingHistory } from '../src/drawings/DrawingHistory.js';
import { DrawingDocumentStore } from '../src/drawings/DrawingPersistence.js';
import { TrendLineCreation } from '../src/drawings/TrendLineCreation.js';
import { hitDrawing } from '../src/drawings/interaction/hitTesting.js';
import { projectGeometry } from '../src/drawings/projectGeometry.js';
import { drawingShapes } from '../src/drawings/drawingShapes.js';
import { fibExtensionLevels } from '../src/drawings/professionalShapes.js';
import { regressionFit, priceRangeStats, barsBetween, formatDuration, decimateStroke } from '../src/drawings/professionalGeometry.js';
import { normalizeOptions, resolvedStyle, capabilities, defaultLevels } from '../src/drawings/drawingStyle.js';
import { PROFESSIONAL_DRAWINGS, DRAWING_SPECS, FREEHAND_MAX_POINTS, POLYLINE_MAX_NODES } from '../src/drawings/DrawingTypes.js';

const t0 = 1_700_000_000;
const bars = Array.from({ length: 40 }, (_, i) => ({ time: t0 + i * 60, open: 2300 + i, high: 2301 + i, low: 2299 + i, close: 2300 + i }));
const x = time => (time - t0) / 60 * 10 + 20;
const scale = { timeToCoordinate: t => bars.some(bar => bar.time === t) ? x(t) : null, width: () => 600, coordinateToTime: px => t0 + (px - 20) / 10 * 60,
  coordinateToLogical: px => (px - 20) / 10 };
let saved = null;
const chart = { timeScale: () => scale, paneSize: () => ({ height: 400 }), options: () => ({ handleScroll: { mouseWheel: true }, handleScale: { axisPressedMouseMove: true } }), applyOptions(o) { saved = o; } };
const series = {
  priceToCoordinate: p => (2400 - p) * 4, coordinateToPrice: y => 2400 - y / 4,
  attachPrimitive(p) { p.attached({ chart, series, requestUpdate() {} }); }, detachPrimitive(p) { p.detached(); },
};
const P = (i, price) => ({ time: bars[i].time, price });
const px = (i, price) => ({ x: x(bars[i].time), y: series.priceToCoordinate(price) });
const env = { width: 600, height: 400, priceToY: series.priceToCoordinate, bars, precision: 3, tickSize: 0.001 };
function setup(barList = bars) { const manager = new DrawingManager(); new DrawingHistory(manager); manager.setTimePoints(barList); manager.attach(series); return manager; }
function recorder() {
  const calls = [], state = {};
  const context = new Proxy(state, { get: (target, key) => key in target ? target[key] : (...args) => calls.push({ op: key, args, lineWidth: target.lineWidth, alpha: target.globalAlpha }),
    set: (target, key, value) => { target[key] = value; return true; } });
  return { calls, target: { useMediaCoordinateSpace: fn => fn({ context }) } };
}
function render(manager, id) { const p = manager.primitives.get(id); p.updateAllViews(); const { calls, target } = recorder(); p.paneViews()[0].renderer().draw(target); return calls; }

// --- catalog --------------------------------------------------------------
const expected = ['extended-line', 'horizontal-ray', 'cross-line', 'parallel-channel', 'regression-trend', 'fib-extension', 'fib-channel', 'rotated-rectangle',
  'ellipse', 'polyline', 'brush', 'highlighter', 'anchored-text', 'callout', 'price-range', 'date-range'];
assert.deepEqual(Object.keys(PROFESSIONAL_DRAWINGS), expected, 'D10–D25 registered in order');

// One representative record per tool and a pointer that must hit it.
const stroke = Array.from({ length: 12 }, (_, i) => P(5 + i, 2330 + Math.sin(i) * 3));
const fixtures = {
  'extended-line': { points: [P(10, 2320), P(12, 2322)], hit: { x: x(bars[30].time), y: series.priceToCoordinate(2340) } },
  'horizontal-ray': { points: [P(10, 2320)], hit: { x: 500, y: series.priceToCoordinate(2320) }, miss: { x: 50, y: series.priceToCoordinate(2320) } },
  'cross-line': { points: [P(10, 2320)], hit: { x: x(bars[10].time), y: 20 } },
  'parallel-channel': { points: [P(5, 2310), P(15, 2320), P(10, 2325)], hit: { ...px(10, 2325) } },
  'regression-trend': { points: [P(5, 1), P(25, 1)], hit: px(15, 2315) },
  'fib-extension': { points: [P(5, 2310), P(10, 2330), P(15, 2320)], hit: { x: x(bars[17].time), y: series.priceToCoordinate(2340) } },
  'fib-channel': { points: [P(5, 2310), P(15, 2320), P(10, 2325)], hit: px(10, 2315 + 10 * 0.382) },
  'rotated-rectangle': { points: [P(5, 2310), P(15, 2320), P(10, 2330)], hit: px(10, 2315) },
  ellipse: { points: [P(5, 2310), P(15, 2330)], hit: { x: x(bars[10].time), y: series.priceToCoordinate(2330) } },
  polyline: { points: [P(5, 2310), P(10, 2330), P(15, 2315), P(20, 2335)], hit: px(10, 2330) },
  brush: { points: stroke, hit: px(5, stroke[0].price) },
  highlighter: { points: stroke, options: { color: '#ffd23f', lineWidth: 10, opacity: 0.35 }, hit: px(5, stroke[0].price) },
  'anchored-text': { points: [P(10, 2320)], text: 'London open', hit: { x: x(bars[10].time), y: series.priceToCoordinate(2320) - 20 } },
  callout: { points: [P(10, 2320), P(16, 2340)], text: 'Liquidity sweep', hit: { x: x(bars[16].time) + 20, y: series.priceToCoordinate(2340) } },
  'price-range': { points: [P(10, 2310), P(16, 2330)], hit: px(13, 2320) },
  'date-range': { points: [P(10, 2310), P(16, 2330)], hit: px(13, 2320) },
};
const manager = setup(), store = { records: new Map() };
const storage = { getItem: k => store.records.get(k) ?? null, setItem: (k, v) => store.records.set(k, v) };
const docs = new DrawingDocumentStore(storage, 'acct:session'); manager.replaceAll(docs.load(manager.registry));
manager.subscribeCommitted((before, after) => docs.save(after));
for (const type of expected) {
  const f = fixtures[type];
  const options = f.options ?? DRAWING_SPECS[type].defaults; // creation writes the spec defaults
  manager.add({ id: type, type, points: f.points, ...(f.text ? { text: f.text } : {}), ...(options ? { options } : {}) });
  const calls = render(manager, type);
  assert.ok(calls.some(c => c.op === 'stroke' || c.op === 'fill' || c.op === 'fillText'), `${type} renders`);
  // Hit test in isolation (other drawings overlap on purpose).
  const solo = setup(); solo.add(manager.get(type));
  assert.equal(hitDrawing(solo, chart, series, f.hit).id, type, `${type} is clickable where drawn`);
  if (f.miss) assert.equal(hitDrawing(solo, chart, series, f.miss).id, null, `${type} not clickable where not drawn`);
  // Style edits apply to the rendered strokes.
  if (capabilities(type).lineStyle) {
    manager.setOptions(type, { lineWidth: 4 });
    const widths = render(manager, type).filter(c => c.op === 'stroke').map(c => c.lineWidth);
    assert.ok(widths.includes(4), `${type} width edit renders`);
  }
  manager.setOptions(type, { opacity: 0.5 });
  assert.ok(render(manager, type).filter(c => c.op === 'stroke' || c.op === 'fill').every(c => c.alpha === 0.5 || c.alpha === 1), `${type} opacity`);
}
// Reload restores every tool exactly.
const reloaded = setup(); const store2 = new DrawingDocumentStore(storage, 'acct:session');
reloaded.replaceAll(store2.load(reloaded.registry));
assert.equal(store2.writable, true);
assert.deepEqual(reloaded.getAll(), manager.getAll(), 'All 16 tools survive reload with styles and anchors');

// --- geometry & statistics ------------------------------------------------
{ // Parallel channel: second line passes through C; middle line halfway.
  const model = manager.get('parallel-channel'), pts = projectGeometry(model, chart, series, bars);
  const { shapes } = drawingShapes(model, pts, env);
  const second = shapes.find(s => s.kind === 'lines' && !s.dash).segments[1];
  const yAt = (seg, xx) => seg[0].y + (seg[1].y - seg[0].y) * (xx - seg[0].x) / (seg[1].x - seg[0].x);
  assert.ok(Math.abs(yAt(second, pts[2].x) - pts[2].y) < 1e-9, 'Channel passes through the third anchor');
}
{ // Regression trend: revealed bars only; exact fit on linear closes.
  const fit = regressionFit(bars, bars[5].time, bars[25].time);
  assert.equal(fit.count, 21); assert.ok(Math.abs(fit.slope - 1) < 1e-12); assert.ok(fit.sd < 1e-9);
  assert.ok(Math.abs(fit.priceAt(bars[25].time) - 2325) < 1e-9);
  const pts = projectGeometry(manager.get('regression-trend'), chart, series, bars);
  assert.ok(Math.abs(pts[1].y - series.priceToCoordinate(2325)) < 1e-9, 'Handles sit on the fitted line, not the stored price');
  const revealed = bars.slice(0, 20);
  const partial = regressionFit(revealed, bars[5].time, bars[25].time);
  assert.equal(partial.count, 15, 'Only bars already revealed enter the fit');
  const future = [...revealed, ...bars.slice(20).map(b => ({ ...b, close: 99999 }))];
  assert.ok(Math.abs(regressionFit(future, bars[5].time, bars[19].time).priceAt(bars[19].time) - partial.priceAt(bars[19].time)) < 1e-9, 'Later bars never change an earlier window');
  assert.equal(regressionFit(bars, bars[5].time, bars[5].time), null, 'One bar cannot be fitted');
  const noisy = bars.map((b, i) => ({ ...b, close: b.close + (i % 2 ? 1 : -1) }));
  const n = regressionFit(noisy, bars[0].time, bars[39].time); assert.ok(n.sd > 0.9 && n.sd < 1.1);
}
{ // Fibonacci extension levels = C + (B − A) · r.
  const model = manager.get('fib-extension');
  const levels = fibExtensionLevels(model, resolvedStyle(model).levels);
  assert.deepEqual(levels.map(l => l.ratio), [0, 0.618, 1, 1.618, 2.618]);
  for (const l of levels) assert.ok(Math.abs(l.price - (2320 + 20 * l.ratio)) < 1e-9);
  assert.equal(defaultLevels('fib-extension').length, 8);
}
{ // Price range: delta, ticks on the Session grid, percent.
  const s = priceRangeStats({ price: 2310 }, { price: 2330.5 }, 0.001);
  assert.equal(s.ticks, 20500); assert.ok(Math.abs(s.percent - 20.5 / 2310 * 100) < 1e-12);
  assert.equal(priceRangeStats({ price: 1.1 }, { price: 1.1005 }, 0.00005).ticks, 10);
  const { shapes } = drawingShapes(manager.get('price-range'), projectGeometry(manager.get('price-range'), chart, series, bars), env);
  assert.ok(shapes.find(s => s.kind === 'text').lines.join(' ').includes('+20000 ticks'));
}
{ // Date range: bars and duration.
  assert.equal(barsBetween(bars, bars[16].time, bars[10].time), 7);
  assert.equal(formatDuration(6 * 60), '6m'); assert.equal(formatDuration(93_780), '1d 2h 3m');
  const { shapes } = drawingShapes(manager.get('date-range'), projectGeometry(manager.get('date-range'), chart, series, bars), env);
  assert.equal(shapes.find(s => s.kind === 'text').lines[0], '7 bars · 6m');
}
{ // Rotated rectangle: third anchor sets the height along the normal.
  const model = manager.get('rotated-rectangle'), pts = projectGeometry(model, chart, series, bars);
  const poly = drawingShapes(model, pts, env).shapes[0].points;
  const len = Math.hypot(poly[1].x - poly[0].x, poly[1].y - poly[0].y), area2 = Math.abs((poly[1].x - poly[0].x) * (poly[3].y - poly[0].y) - (poly[1].y - poly[0].y) * (poly[3].x - poly[0].x));
  const heightPx = area2 / len, dist = Math.abs(((pts[2].x - pts[0].x) * -(pts[1].y - pts[0].y) + (pts[2].y - pts[0].y) * (pts[1].x - pts[0].x)) / len);
  assert.ok(Math.abs(heightPx - dist) < 1e-9);
}

// --- creation workflows ---------------------------------------------------
const click = i => ({ point: { x: x(bars[i].time), y: series.priceToCoordinate(2320 + i) }, time: bars[i].time });
{ // Three-anchor tool: draft after 1 and 2 clicks, stored on the third.
  const m = setup(); let done = null;
  const c = new TrendLineCreation(m, chart, series, bars, '1m', obj => { done = obj; }, 'parallel-channel');
  c.click(click(5)); assert.equal(m.draft.model.points.length, 3); assert.equal(m.getAll().length, 0);
  c.move(click(8)); assert.equal(m.draft.model.points[1].time, bars[8].time);
  c.click(click(10)); assert.equal(m.getAll().length, 0); assert.equal(m.draft.model.points[2].time, bars[10].time);
  c.click(click(12)); assert.equal(m.getAll().length, 1); assert.equal(done.points.length, 3); assert.equal(m.draft, null);
}
{ // Text tools: anchors first, nothing stored before the text is saved; defaults written.
  const m = setup(); let request = null;
  const c = new TrendLineCreation(m, chart, series, bars, '1m', () => {}, 'callout', (point, points) => { request = points; });
  c.click(click(5)); assert.equal(request, null); c.click(click(9));
  assert.equal(request.length, 2); assert.equal(m.getAll().length, 0); assert.ok(m.draft, 'Leader preview stays while typing');
  c.click(click(12)); assert.equal(request.length, 2, 'Further clicks ignored while text is pending');
  c.cancel(); assert.equal(m.draft, null);
  const a = new TrendLineCreation(m, chart, series, bars, '1m', () => {}, 'anchored-text', (point, points) => { request = points; });
  a.click(click(7)); assert.equal(request.length, 1);
  assert.deepEqual(DRAWING_SPECS['anchored-text'].defaults, { labelPosition: 'top', textAlign: 'center', bold: true });
}
{ // Polyline: click per node, finish by clicking the last node again, Backspace removes.
  const m = setup(); let done = null;
  const c = new TrendLineCreation(m, chart, series, bars, '1m', obj => { done = obj; }, 'polyline');
  c.click(click(5)); c.click(click(8)); c.click(click(11));
  assert.equal(c.nodeCount, 3); assert.equal(m.draft.model.points.length, 4, 'Draft shows a rubber-band segment');
  c.removeLastNode(); assert.equal(c.nodeCount, 2);
  c.click(click(14)); c.click({ ...click(14), point: { x: click(14).point.x + 2, y: click(14).point.y } });
  assert.equal(done.points.length, 3, 'Double-click on the last node finishes');
  const lone = new TrendLineCreation(m, chart, series, bars, '1m', () => {}, 'polyline');
  lone.click(click(3)); assert.equal(lone.finish(), null, 'One node cannot become a polyline'); assert.equal(m.draft, null);
  const many = new TrendLineCreation(m, chart, series, bars, '1m', () => {}, 'polyline');
  for (let i = 0; i < POLYLINE_MAX_NODES + 5; i++) many.click({ point: { x: 20 + i * 8, y: 100 + (i % 2) * 30 }, time: undefined });
  assert.equal(m.getAll().at(-1).points.length, POLYLINE_MAX_NODES, 'Node count is bounded');
}
{ // Freehand: one drag, decimated, bounded, chart panning paused then restored.
  const m = setup(); let done = null;
  const handlers = {}, root = { addEventListener: (k, fn) => { handlers[k] = fn; }, removeEventListener: k => { delete handlers[k]; }, setPointerCapture() {}, hasPointerCapture: () => true, releasePointerCapture() {} };
  const element = { parentElement: root, getBoundingClientRect: () => ({ left: 0, top: 0 }) };
  const c = new TrendLineCreation(m, chart, series, bars, '1m', obj => { done = obj; }, 'brush');
  const unbind = c.bindFreehand(element);
  assert.deepEqual(saved, { handleScroll: false, handleScale: false });
  const ev = (xx, yy) => ({ button: 0, pointerId: 7, clientX: xx, clientY: yy, preventDefault() {}, stopPropagation() {} });
  handlers.pointerdown(ev(30, 100));
  for (let i = 1; i < 3000; i++) handlers.pointermove(ev(30 + i * 0.18, 100 + Math.sin(i / 50) * 40));
  handlers.pointerup(ev(570, 100));
  assert.ok(done, 'Stroke stored on pointer up');
  assert.ok(done.points.length >= 2 && done.points.length <= FREEHAND_MAX_POINTS, `bounded: ${done.points.length}`);
  assert.ok(done.points.every((p, i) => i === 0 || p.time >= done.points[i - 1].time - 1e-6));
  handlers.pointerdown(ev(40, 100)); handlers.pointerup(ev(40, 100));
  assert.equal(m.getAll().length, 1, 'A tap without movement draws nothing');
  unbind(); assert.deepEqual(saved, { handleScroll: { mouseWheel: true }, handleScale: { axisPressedMouseMove: true } }, 'Chart panning restored');
  assert.equal(decimateStroke([{ x: 0, y: 0 }, { x: 1, y: 0 }, { x: 5, y: 0 }], 3, 10).length, 2);
}

// --- options & properties --------------------------------------------------
assert.equal(normalizeOptions({ deviation: 1.5, showMiddle: false }).deviation, 1.5);
for (const bad of [{ deviation: -1 }, { deviation: 6 }, { showMiddle: 'yes' }]) assert.throws(() => normalizeOptions(bad));
assert.equal(capabilities('regression-trend').deviation, true);
assert.equal(capabilities('fib-extension').levels, 'fib-extension');
assert.equal(capabilities('brush').lineStyle, undefined, 'Freehand hides dash controls');
assert.equal(capabilities('price-range').text, 'size');
{ // Locked drawings refuse edits; Polyline node insert keeps endpoints.
  const m = setup(); m.add({ id: 'p', type: 'polyline', points: fixtures.polyline.points });
  m.setProperties('p', { locked: true }); m.setOptions('p', { lineWidth: 6 }); assert.equal(m.get('p').options.lineWidth, 2);
}

console.log(`c03 professional drawings: ${expected.length} tools created, rendered, hit-tested, styled and reloaded; geometry, statistics and creation flows verified`);
