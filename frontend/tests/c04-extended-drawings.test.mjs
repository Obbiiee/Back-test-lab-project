// Issue #21 C-04: extended professional tools (pitchforks, Fib time/fan/circles/
// arcs/wedge, Gann, manual patterns, Elliott labels, cycles, markers).
import assert from 'node:assert/strict';
import { DrawingManager } from '../src/drawings/DrawingManager.js';
import { DrawingHistory } from '../src/drawings/DrawingHistory.js';
import { DrawingDocumentStore } from '../src/drawings/DrawingPersistence.js';
import { TrendLineCreation } from '../src/drawings/TrendLineCreation.js';
import { hitDrawing } from '../src/drawings/interaction/hitTesting.js';
import { projectGeometry } from '../src/drawings/projectGeometry.js';
import { drawingShapes } from '../src/drawings/drawingShapes.js';
import { pitchforkOrigin, legRatio, iconPolygon } from '../src/drawings/extendedShapes.js';
import { normalizeOptions, capabilities, defaultLevels, ICONS } from '../src/drawings/drawingStyle.js';
import { EXTENDED_DRAWINGS, DRAWING_SPECS } from '../src/drawings/DrawingTypes.js';

const t0 = 1_700_000_000;
const bars = Array.from({ length: 60 }, (_, i) => ({ time: t0 + i * 60, open: 2300, high: 2301, low: 2299, close: 2300 }));
const x = time => (time - t0) / 60 * 10 + 20;
const scale = { timeToCoordinate: t => bars.some(bar => bar.time === t) ? x(t) : null, width: () => 700, coordinateToTime: px => t0 + (px - 20) / 10 * 60 };
const chart = { timeScale: () => scale, paneSize: () => ({ height: 400 }), options: () => ({ handleScroll: {} }), applyOptions() {} };
const series = { priceToCoordinate: p => (2400 - p) * 4, coordinateToPrice: y => 2400 - y / 4,
  attachPrimitive(p) { p.attached({ chart, series, requestUpdate() {} }); }, detachPrimitive(p) { p.detached(); } };
const P = (i, price) => ({ time: bars[i].time, price });
const px = (i, price) => ({ x: x(bars[i].time), y: series.priceToCoordinate(price) });
const env = { width: 700, height: 400, priceToY: series.priceToCoordinate, bars, precision: 3, tickSize: 0.001 };
const setup = () => { const m = new DrawingManager(); new DrawingHistory(m); m.setTimePoints(bars); m.attach(series); return m; };
const shapesOf = model => drawingShapes(model, projectGeometry(model, chart, series, bars), env).shapes;
function render(manager, id) {
  const p = manager.primitives.get(id); p.updateAllViews(); const calls = [], state = {};
  const context = new Proxy(state, { get: (t, k) => k in t ? t[k] : (...args) => calls.push({ op: k, args }), set: (t, k, v) => { t[k] = v; return true; } });
  p.paneViews()[0].renderer().draw({ useMediaCoordinateSpace: fn => fn({ context }) }); return calls;
}

const expected = ['pitchfork', 'schiff-pitchfork', 'modified-schiff-pitchfork', 'fib-time-zone', 'trend-fib-time', 'fib-fan', 'fib-circles', 'fib-arcs', 'fib-wedge',
  'gann-fan', 'gann-box', 'abcd-pattern', 'xabcd-pattern', 'head-shoulders', 'triangle-pattern', 'elliott-impulse', 'elliott-correction', 'cyclic-lines',
  'date-price-range', 'icon-marker', 'price-label', 'arrow-marker'];
assert.deepEqual(Object.keys(EXTENDED_DRAWINGS), expected);
assert.equal(Object.keys(DRAWING_SPECS).length, 9 + 16 + 22, '47 research drawing tools');

const zig = n => Array.from({ length: n }, (_, i) => P(5 + i * 5, 2320 + (i % 2 ? 15 : 0) + i));
const fixtures = {
  pitchfork: { points: [P(5, 2300), P(15, 2330), P(20, 2310)], hit: () => px(15, 2330) },
  'schiff-pitchfork': { points: [P(5, 2300), P(15, 2330), P(20, 2310)], hit: () => px(15, 2330) },
  'modified-schiff-pitchfork': { points: [P(5, 2300), P(15, 2330), P(20, 2310)], hit: () => px(15, 2330) },
  'fib-time-zone': { points: [P(5, 2320), P(8, 2320)], hit: () => ({ x: x(bars[5].time) + 30 * 2, y: 200 }) },
  'trend-fib-time': { points: [P(5, 2300), P(10, 2330), P(15, 2310)], hit: () => ({ x: x(bars[15].time) + 50, y: 300 }) },
  'fib-fan': { points: [P(5, 2300), P(15, 2340)], hit: () => px(15, 2340) },
  'fib-circles': { points: [P(10, 2300), P(20, 2320)], hit: () => px(10, 2300) }, // ratio 1 passes through A and B
  'fib-arcs': { points: [P(5, 2300), P(15, 2320)], hit: () => px(5, 2300) }, // ratio-1 arc around B passes through A
  'fib-wedge': { points: [P(5, 2300), P(15, 2330), P(15, 2310)], hit: () => px(15, 2330) },
  'gann-fan': { points: [P(5, 2300), P(10, 2310)], hit: () => px(10, 2310) },
  'gann-box': { points: [P(5, 2300), P(25, 2340)], hit: () => px(15, 2320) },
  'abcd-pattern': { points: zig(4), hit: () => px(5, 2320) },
  'xabcd-pattern': { points: zig(5), options: { fillOpacity: 0.1 }, hit: () => px(5, 2320) },
  'head-shoulders': { points: [P(5, 2300), P(10, 2320), P(15, 2305), P(20, 2335), P(25, 2306), P(30, 2321), P(35, 2299)], hit: () => px(20, 2335) },
  'triangle-pattern': { points: [P(5, 2340), P(10, 2300), P(20, 2330), P(25, 2310)], hit: () => px(5, 2340) },
  'elliott-impulse': { points: zig(6), hit: () => px(5, 2320) },
  'elliott-correction': { points: zig(4), hit: () => px(5, 2320) },
  'cyclic-lines': { points: [P(5, 2320), P(10, 2320)], hit: () => ({ x: x(bars[15].time), y: 50 }) },
  'date-price-range': { points: [P(10, 2310), P(20, 2330)], hit: () => px(15, 2320) },
  'icon-marker': { points: [P(10, 2320)], options: { icon: 'star', markerSize: 24 }, hit: () => px(10, 2320) },
  'price-label': { points: [P(10, 2320)], hit: () => ({ x: x(bars[10].time) + 20, y: series.priceToCoordinate(2320) }) },
  'arrow-marker': { points: [P(10, 2320)], options: { direction: 'up', markerSize: 20 }, hit: () => ({ x: x(bars[10].time), y: series.priceToCoordinate(2320) + 15 }) },
};
const records = new Map(), storage = { getItem: k => records.get(k) ?? null, setItem: (k, v) => records.set(k, v) };
const manager = setup(), docs = new DrawingDocumentStore(storage, 'acct:c04');
manager.replaceAll(docs.load(manager.registry)); manager.subscribeCommitted((b, a) => docs.save(a));
for (const type of expected) {
  const f = fixtures[type];
  manager.add({ id: type, type, points: f.points, ...(f.options ? { options: f.options } : {}) });
  assert.ok(render(manager, type).some(c => ['stroke', 'fill', 'fillText'].includes(c.op)), `${type} renders`);
  if (f.hit) { const solo = setup(); solo.add(manager.get(type)); assert.equal(hitDrawing(solo, chart, series, f.hit()).id, type, `${type} clickable where drawn`); }
  if (capabilities(type).levels) {
    const levels = defaultLevels(type).map(level => ({ ...level, visible: true }));
    manager.setOptions(type, { levels }); assert.equal(manager.get(type).options.levels.length, levels.length, `${type} level rows editable`);
  }
}
const reloaded = setup(), docs2 = new DrawingDocumentStore(storage, 'acct:c04');
reloaded.replaceAll(docs2.load(reloaded.registry)); assert.equal(docs2.writable, true);
assert.deepEqual(reloaded.getAll(), manager.getAll(), 'All 22 extended tools survive reload');

// --- geometry --------------------------------------------------------------
{ // Pitchfork median runs from the variant origin through the midpoint of B–C.
  const a = { x: 0, y: 0 }, b = { x: 100, y: -60 }, c = { x: 140, y: 20 };
  assert.deepEqual(pitchforkOrigin('pitchfork', a, b), a);
  assert.deepEqual(pitchforkOrigin('schiff-pitchfork', a, b), { x: 0, y: -30 });
  assert.deepEqual(pitchforkOrigin('modified-schiff-pitchfork', a, b), { x: 50, y: -30 });
  for (const type of ['pitchfork', 'schiff-pitchfork', 'modified-schiff-pitchfork']) {
    const model = manager.get(type), pts = projectGeometry(model, chart, series, bars), origin = pitchforkOrigin(type, pts[0], pts[1]);
    const median = shapesOf(model).find(s => s.kind === 'lines' && !s.level && !s.dash).segments[0];
    const m = { x: (pts[1].x + pts[2].x) / 2, y: (pts[1].y + pts[2].y) / 2 };
    const cross = (median[1].x - median[0].x) * (m.y - median[0].y) - (median[1].y - median[0].y) * (m.x - median[0].x);
    assert.deepEqual(median[0], origin); assert.ok(Math.abs(cross) < 1e-6, `${type} median through BC midpoint`);
  }
}
{ // Fib time zones at A + span·{0,1,2,3,5,8,…}.
  const xs = shapesOf(manager.get('fib-time-zone')).filter(s => s.level).map(s => s.segments[0][0].x);
  const a = x(bars[5].time), span = x(bars[8].time) - a;
  assert.deepEqual(xs.slice(0, 6).map(v => Math.round((v - a) / span)), [0, 1, 2, 3, 5, 8]);
}
{ // Gann fan: 1×1 passes through B; 2×1 is twice as steep, 1×2 half.
  const model = manager.get('gann-fan'), [a, b] = projectGeometry(model, chart, series, bars);
  const slope = seg => (seg[1].y - seg[0].y) / (seg[1].x - seg[0].x), base = (b.y - a.y) / (b.x - a.x);
  const rays = shapesOf(model).filter(s => s.level).map(s => slope(s.segments[0]));
  const levels = defaultLevels('gann-fan').map(l => l.value);
  levels.forEach((r, i) => assert.ok(Math.abs(rays[i] - base * r) < 1e-9, `gann ${r}`));
}
{ // Gann box grid lines at the configured ratios in both directions.
  const lines = shapesOf(manager.get('gann-box')).filter(s => s.level);
  assert.equal(lines.length, 7); // all 7 rows made visible above
  const v = lines.map(s => s.segments[0][0].x); assert.equal(v[3], (x(bars[5].time) + x(bars[25].time)) / 2);
}
{ // ABCD / XABCD ratios use canonical prices.
  assert.ok(Math.abs(legRatio({ price: 100 }, { price: 110 }, { price: 103.82 }) - 0.618) < 1e-9);
  assert.equal(legRatio({ price: 1 }, { price: 1 }, { price: 2 }), null);
  const texts = shapesOf(manager.get('xabcd-pattern')).filter(s => s.kind === 'text').map(s => s.lines[0]);
  for (const label of ['X', 'A', 'B', 'C', 'D']) assert.ok(texts.includes(label), 'XABCD pivot label ' + label);
  assert.equal(texts.filter(t => /^\d/.test(t)).length, 4, 'four ratio labels (AB/XA, BC/AB, CD/BC, AD/XA)');
  const abcd = shapesOf(manager.get('abcd-pattern')).filter(s => s.kind === 'text');
  const labelB = abcd.find(s => s.lines[0] === 'B'), labelC = abcd.find(s => s.lines[0] === 'C');
  assert.equal(labelB.style.position, 'top', 'swing high labelled above'); assert.equal(labelC.style.position, 'bottom', 'swing low labelled below');
}
{ // Head & shoulders: LS/H/RS labels and a neckline through both neck pivots.
  const shapes = shapesOf(manager.get('head-shoulders')), labels = shapes.filter(s => s.kind === 'text').map(s => s.lines[0]);
  assert.deepEqual(labels, ['LS', 'H', 'RS']);
  assert.ok(shapes.some(s => s.kind === 'lines' && s.dash?.[0] === 5));
}
{ // Cyclic lines: equal spacing = A→B, bounded by repeats.
  manager.setOptions('cyclic-lines', { repeats: 4 });
  const segs = shapesOf(manager.get('cyclic-lines')).find(s => s.kind === 'lines').segments.map(seg => seg[0].x);
  assert.equal(segs.length, 5); segs.slice(1).forEach((v, i) => assert.ok(Math.abs(v - segs[i] - 50) < 1e-9));
}
{ // Date & price range: price/ticks/% and bars/duration in one label.
  const label = shapesOf(manager.get('date-price-range')).find(s => s.kind === 'text').lines;
  assert.equal(label[0], '+20.000 (+0.87%) · +20000 ticks'); assert.equal(label[1], '11 bars · 10m');
}
{ // Markers: every glyph is a closed polygon centred on the anchor; arrow tip on the anchor.
  for (const icon of ICONS) { const pts = iconPolygon(icon, { x: 100, y: 100 }, 20); assert.ok(pts.length >= 3, icon); assert.ok(pts.every(p => Math.abs(p.x - 100) <= 10.01 && Math.abs(p.y - 100) <= 10.01), icon + ' bounded'); }
  const up = shapesOf(manager.get('arrow-marker'))[0].points, anchor = px(10, 2320);
  assert.deepEqual(up[0], anchor); assert.ok(up[3].y > anchor.y, 'up arrow body below its tip');
  manager.setOptions('arrow-marker', { direction: 'down' }); assert.ok(shapesOf(manager.get('arrow-marker'))[0].points[3].y < anchor.y);
  assert.equal(shapesOf(manager.get('price-label')).find(s => s.kind === 'text').lines[0], '2320.000');
}
// Manual patterns: N clicks, nothing auto-detected.
{
  const m = setup(), c = new TrendLineCreation(m, chart, series, bars, '1m', () => {}, 'head-shoulders');
  for (let i = 0; i < 6; i++) c.click({ point: px(5 + i * 5, 2300 + i), time: bars[5 + i * 5].time });
  assert.equal(m.getAll().length, 0); assert.equal(m.draft.model.points.length, 7);
  c.click({ point: px(40, 2300), time: bars[40].time }); assert.equal(m.getAll()[0].points.length, 7);
}
// Options validation.
for (const bad of [{ icon: 'logo' }, { markerSize: 4 }, { markerSize: 64 }, { direction: 'left' }, { repeats: 0 }, { repeats: 101 }, { levels: [{ value: 101, visible: true }] }]) assert.throws(() => normalizeOptions(bad), undefined, JSON.stringify(bad));
assert.equal(normalizeOptions({ levels: [{ value: 89, visible: true }] }).levels[0].value, 89, 'Fib time zone 89 is a valid level');
assert.equal(capabilities('icon-marker').lineStyle, undefined); assert.equal(capabilities('arrow-marker').direction, true);

console.log(`c04 extended drawings: ${expected.length} tools created, rendered, hit-tested, level-edited and reloaded; pitchfork, Fib time, Gann, pattern ratios, cycles, ranges and markers verified`);
