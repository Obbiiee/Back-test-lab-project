// Geometry for the extended professional tools (Issue #21 C-04).
// Screen-space constructions (fans, circles, arcs, Gann angles) depend on the
// chart's current price/time scaling, as on any chart; canonical TIME+PRICE
// anchors never change. Pattern tools are manual labelled pivots only.
import { DRAWING_SPECS } from './DrawingTypes.js';
import { rayEnd } from './rayGeometry.js';
import { arrowHead } from './advancedGeometry.js';
import { withAlpha } from './drawingStyle.js';
import { formatDuration, barsBetween, priceRangeStats } from './professionalGeometry.js';

const fillOf = style => style.fillOpacity > 0 ? withAlpha(style.fillColor, style.fillOpacity) : null;
const mid = (p, q) => ({ x: (p.x + q.x) / 2, y: (p.y + q.y) / 2 });
const add = (p, v, k = 1) => ({ x: p.x + v.x * k, y: p.y + v.y * k });
const visibleLevels = style => style.levels.filter(level => level.visible).map(level => ({ ratio: level.value, color: level.color ?? style.color }));
const fmtTime = time => new Date(Math.round(time) * 1000).toISOString().slice(0, 16).replace('T', ' ');
const ratioText = r => Number.isFinite(r) ? r.toFixed(3).replace(/0+$/, '').replace(/\.$/, '') : 'n/a';
const gannLabel = r => r >= 1 ? `${Math.round(r)}×1` : `1×${Math.round(1 / r)}`;

// Pitchfork origin per variant (A = pivot, B/C = reaction pivots).
export function pitchforkOrigin(type, a, b) {
  if (type === 'schiff-pitchfork') return { x: a.x, y: (a.y + b.y) / 2 };
  if (type === 'modified-schiff-pitchfork') return mid(a, b);
  return a;
}

// Price ratio |leg2| / |leg1| between consecutive pivot legs (canonical prices).
export function legRatio(p0, p1, p2) {
  const first = Math.abs(p1.price - p0.price);
  return first === 0 ? null : Math.abs(p2.price - p1.price) / first;
}

// Polygon outline for a marker glyph of the given size centred on c.
export function iconPolygon(icon, c, size) {
  const r = size / 2, pts = [];
  switch (icon) {
    case 'square': return [{ x: c.x - r, y: c.y - r }, { x: c.x + r, y: c.y - r }, { x: c.x + r, y: c.y + r }, { x: c.x - r, y: c.y + r }];
    case 'diamond': return [{ x: c.x, y: c.y - r }, { x: c.x + r, y: c.y }, { x: c.x, y: c.y + r }, { x: c.x - r, y: c.y }];
    case 'triangle-up': return [{ x: c.x, y: c.y - r }, { x: c.x + r, y: c.y + r * 0.8 }, { x: c.x - r, y: c.y + r * 0.8 }];
    case 'triangle-down': return [{ x: c.x, y: c.y + r }, { x: c.x + r, y: c.y - r * 0.8 }, { x: c.x - r, y: c.y - r * 0.8 }];
    case 'star':
      for (let i = 0; i < 10; i++) { const angle = -Math.PI / 2 + i * Math.PI / 5, rr = i % 2 ? r * 0.45 : r; pts.push({ x: c.x + Math.cos(angle) * rr, y: c.y + Math.sin(angle) * rr }); }
      return pts;
    case 'flag': return [{ x: c.x - r * 0.6, y: c.y + r }, { x: c.x - r * 0.6, y: c.y - r }, { x: c.x + r, y: c.y - r * 0.55 }, { x: c.x - r * 0.6, y: c.y - r * 0.1 }];
    case 'cross': {
      const t = r * 0.32;
      return [[-t, -r], [t, -r], [t, -t], [r, -t], [r, t], [t, t], [t, r], [-t, r], [-t, t], [-r, t], [-r, -t], [-t, -t]].map(([dx, dy]) => ({ x: c.x + dx, y: c.y + dy }));
    }
    default:
      for (let i = 0; i < 24; i++) { const angle = i / 24 * Math.PI * 2; pts.push({ x: c.x + Math.cos(angle) * r, y: c.y + Math.sin(angle) * r }); }
      return pts;
  }
}

export function extendedShapes(model, projected, env, { style, text, lines, shapes, precision }) {
  const [a, b, c] = projected;
  const small = Math.min(style.fontSize, 12);
  const levelText = (anchor, label, color, options = {}) => text(anchor, [label], { background: 'none', color, fontSize: small, ...options });
  const pivotLabels = labels => projected.forEach((point, i) => {
    if (!labels[i]) return;
    const prev = projected[i - 1] ?? projected[i + 1], next = projected[i + 1] ?? projected[i - 1];
    const high = point.y <= Math.min(prev.y, next.y);
    text(point, [labels[i]], { align: 'center', position: high ? 'top' : 'bottom', background: style.color, color: '#0b0f17', fontSize: style.fontSize, bold: true });
  });
  const ratioOn = (p, q, value) => { if (style.showPriceLabels && value != null) levelText(mid(p, q), ratioText(value), style.color, { align: 'center', position: 'center', background: '#10141b' }); };
  switch (model.type) {
    case 'pitchfork': case 'schiff-pitchfork': case 'modified-schiff-pitchfork': {
      const origin = pitchforkOrigin(model.type, a, b), m = mid(b, c), dir = { x: m.x - origin.x, y: m.y - origin.y };
      const half = { x: (b.x - c.x) / 2, y: (b.y - c.y) / 2 };
      const far = p => rayEnd(p, add(p, dir), env.width, env.height);
      const end = p => style.extendRight ? far(p) : add(p, dir);
      if (fillOf(style)) shapes.push({ kind: 'polygon', stroke: false, fill: fillOf(style), points: [b, end(b), end(c), c] });
      lines([[origin, end(m)], [b, end(b)], [c, end(c)], [b, c]]);
      for (const level of visibleLevels(style)) {
        if (level.ratio === 1 || level.ratio === 0) continue;
        for (const sign of [1, -1]) { const start = add(m, half, sign * level.ratio); shapes.push({ kind: 'lines', segments: [[start, end(start)]], color: level.color, width: 1, level: true }); }
      }
      if (model.type !== 'pitchfork') shapes.push({ kind: 'lines', segments: [[a, origin]], dash: [3, 3], width: 1 });
      break;
    }
    case 'fib-time-zone': case 'trend-fib-time': {
      const base = model.type === 'fib-time-zone' ? a : c, span = b.x - a.x, timeSpan = model.points[1].time - model.points[0].time;
      if (model.type === 'trend-fib-time') shapes.push({ kind: 'lines', segments: [[a, b], [b, c]], dash: [4, 4], width: 1 });
      for (const level of visibleLevels(style)) {
        const xx = base.x + span * level.ratio;
        shapes.push({ kind: 'lines', segments: [[{ x: xx, y: 0 }, { x: xx, y: env.height }]], color: level.color, level: true });
        levelText({ x: xx, y: 12 }, String(level.ratio), level.color);
        if (style.showTimeLabels) levelText({ x: xx, y: env.height - 18 }, fmtTime(model.points[model.type === 'fib-time-zone' ? 0 : 2].time + timeSpan * level.ratio), level.color);
      }
      break;
    }
    case 'fib-fan': {
      const rays = visibleLevels(style).map(level => ({ ...level, to: { x: b.x, y: a.y + (b.y - a.y) * level.ratio } }));
      if (fillOf(style)) for (let i = 1; i < rays.length; i++) shapes.push({ kind: 'polygon', stroke: false, fill: withAlpha(rays[i].color, style.fillOpacity),
        points: [a, rayEnd(a, rays[i - 1].to, env.width, env.height), rayEnd(a, rays[i].to, env.width, env.height)] });
      shapes.push({ kind: 'lines', segments: [[a, b]], dash: [3, 4], width: 1 });
      for (const ray of rays) {
        shapes.push({ kind: 'lines', segments: [[a, b.x === a.x ? ray.to : rayEnd(a, ray.to, env.width, env.height)]], color: ray.color, level: true });
        if (style.showPriceLabels) levelText(ray.to, String(ray.ratio), ray.color);
      }
      break;
    }
    case 'fib-circles': case 'fib-arcs': case 'fib-wedge': {
      const center = model.type === 'fib-arcs' ? b : model.type === 'fib-circles' ? mid(a, b) : a;
      const radius = model.type === 'fib-circles' ? Math.hypot(b.x - a.x, b.y - a.y) / 2 : Math.hypot(b.x - a.x, b.y - a.y);
      // Arcs: half circle around B facing A (crossing B→A at each ratio).
      // Wedge: the smaller sweep between rays A→B and A→C.
      let start = 0, endAngle = Math.PI * 2, labelAngle = 0;
      if (model.type === 'fib-arcs') { labelAngle = Math.atan2(a.y - b.y, a.x - b.x); start = labelAngle - Math.PI / 2; endAngle = labelAngle + Math.PI / 2; }
      if (model.type === 'fib-wedge') {
        const angB = Math.atan2(b.y - a.y, b.x - a.x), angC = Math.atan2(c.y - a.y, c.x - a.x);
        let sweep = angC - angB; while (sweep > Math.PI) sweep -= Math.PI * 2; while (sweep <= -Math.PI) sweep += Math.PI * 2;
        start = sweep >= 0 ? angB : angC; endAngle = start + Math.abs(sweep); labelAngle = endAngle;
      }
      const anticlockwise = false;
      shapes.push({ kind: 'lines', segments: model.type === 'fib-wedge' ? [[a, b], [a, c]] : [[a, b]], dash: model.type === 'fib-wedge' ? undefined : [3, 4], width: model.type === 'fib-wedge' ? undefined : 1 });
      const levels = visibleLevels(style);
      for (const level of levels) {
        const r = radius * level.ratio;
        if (model.type === 'fib-circles') shapes.push({ kind: 'ellipse', center, rx: r, ry: r, color: level.color, level: true });
        else shapes.push({ kind: 'arc', center, radius: r, start, end: endAngle, anticlockwise, color: level.color, level: true });
        if (style.showPriceLabels) levelText({ x: center.x + r * Math.cos(labelAngle), y: center.y + r * Math.sin(labelAngle) }, String(level.ratio), level.color);
      }
      if (model.type === 'fib-wedge' && fillOf(style) && levels.length) {
        const r = radius * Math.max(...levels.map(l => l.ratio)), steps = 24, pts = [a];
        for (let i = 0; i <= steps; i++) { const angle = start + (endAngle - start) * i / steps; pts.push({ x: a.x + Math.cos(angle) * r, y: a.y + Math.sin(angle) * r }); }
        shapes.unshift({ kind: 'polygon', stroke: false, fill: fillOf(style), points: pts });
      }
      break;
    }
    case 'gann-fan': {
      const v = { x: b.x - a.x, y: b.y - a.y };
      for (const level of visibleLevels(style)) {
        // value = price per time relative to 1×1: >1 steeper, <1 flatter.
        const to = level.ratio >= 1 ? { x: a.x + v.x, y: a.y + v.y * level.ratio } : { x: a.x + v.x / level.ratio, y: a.y + v.y };
        shapes.push({ kind: 'lines', segments: [[a, rayEnd(a, to, env.width, env.height)]], color: level.color, level: true, width: level.ratio === 1 ? style.lineWidth + 1 : undefined });
        if (style.showPriceLabels) levelText(to, gannLabel(level.ratio), level.color);
      }
      break;
    }
    case 'gann-box': {
      const left = Math.min(a.x, b.x), right = Math.max(a.x, b.x), top = Math.min(a.y, b.y), bottom = Math.max(a.y, b.y);
      shapes.push({ kind: 'polygon', points: [{ x: left, y: top }, { x: right, y: top }, { x: right, y: bottom }, { x: left, y: bottom }], fill: fillOf(style), hitInside: true });
      for (const level of visibleLevels(style)) {
        const xx = a.x + (b.x - a.x) * level.ratio, yy = a.y + (b.y - a.y) * level.ratio;
        shapes.push({ kind: 'lines', segments: [[{ x: xx, y: top }, { x: xx, y: bottom }], [{ x: left, y: yy }, { x: right, y: yy }]], color: level.color, width: 1, level: true });
        if (style.showPriceLabels) { levelText({ x: xx, y: bottom }, String(level.ratio), level.color, { align: 'center', position: 'bottom' }); levelText({ x: right, y: yy }, String(level.ratio), level.color); }
      }
      shapes.push({ kind: 'lines', segments: [[a, b], [{ x: a.x, y: b.y }, { x: b.x, y: a.y }]], dash: [4, 4], width: 1 });
      break;
    }
    case 'abcd-pattern': case 'xabcd-pattern': {
      const labels = DRAWING_SPECS[model.type].labels, pts = model.points;
      if (model.type === 'xabcd-pattern' && fillOf(style)) {
        shapes.push({ kind: 'polygon', stroke: false, fill: fillOf(style), points: [projected[0], projected[1], projected[2]] });
        shapes.push({ kind: 'polygon', stroke: false, fill: fillOf(style), points: [projected[2], projected[3], projected[4]] });
      }
      shapes.push({ kind: 'path', points: projected });
      const off = model.type === 'xabcd-pattern' ? 1 : 0;
      const guides = [];
      if (off) guides.push([0, 2, legRatio(pts[0], pts[1], pts[2])]);
      guides.push([off, off + 2, legRatio(pts[off], pts[off + 1], pts[off + 2])]);
      guides.push([off + 1, off + 3, legRatio(pts[off + 1], pts[off + 2], pts[off + 3])]);
      if (off) { const xa = Math.abs(pts[1].price - pts[0].price); guides.push([0, 4, xa === 0 ? null : Math.abs(pts[4].price - pts[1].price) / xa]); }
      for (const [i, j, value] of guides) { shapes.push({ kind: 'lines', segments: [[projected[i], projected[j]]], dash: [3, 4], width: 1 }); ratioOn(projected[i], projected[j], value); }
      pivotLabels(labels);
      break;
    }
    case 'head-shoulders': {
      shapes.push({ kind: 'path', points: projected });
      const [n1, n2] = [projected[2], projected[4]];
      const neck = style.extendRight || style.extendLeft ? [style.extendLeft ? rayEnd(n2, n1, env.width, env.height) : n1, style.extendRight ? rayEnd(n1, n2, env.width, env.height) : n2] : [projected[0], projected[6]].map(p => ({ x: p.x, y: n1.y + (n2.y - n1.y) * (p.x - n1.x) / ((n2.x - n1.x) || 1) }));
      shapes.push({ kind: 'lines', segments: [neck], dash: [5, 4] });
      pivotLabels(DRAWING_SPECS[model.type].labels);
      break;
    }
    case 'triangle-pattern': {
      const [p0, p1, p2, p3] = projected;
      const ext = (p, q) => style.extendRight ? rayEnd(p, q, env.width, env.height) : q;
      if (fillOf(style)) shapes.push({ kind: 'polygon', stroke: false, fill: fillOf(style), points: [p0, p2, p3, p1] });
      shapes.push({ kind: 'path', points: projected });
      lines([[p0, ext(p0, p2)], [p1, ext(p1, p3)]]);
      pivotLabels(DRAWING_SPECS[model.type].labels);
      break;
    }
    case 'elliott-impulse': case 'elliott-correction':
      shapes.push({ kind: 'path', points: projected });
      pivotLabels(DRAWING_SPECS[model.type].labels);
      break;
    case 'cyclic-lines': {
      const step = b.x - a.x;
      const count = Math.abs(step) < 2 ? 1 : style.repeats;
      const segments = [];
      for (let k = 0; k <= count; k++) { const xx = a.x + step * k; if (xx < -step || xx > env.width + Math.abs(step)) break; segments.push([{ x: xx, y: 0 }, { x: xx, y: env.height }]); }
      lines(segments);
      levelText({ x: b.x, y: 12 }, formatDuration(model.points[1].time - model.points[0].time), style.color);
      break;
    }
    case 'date-price-range': {
      const stats = priceRangeStats(model.points[0], model.points[1], env.tickSize);
      const count = barsBetween(env.bars ?? [], model.points[0].time, model.points[1].time);
      const box = [{ x: a.x, y: a.y }, { x: b.x, y: a.y }, { x: b.x, y: b.y }, { x: a.x, y: b.y }];
      shapes.push({ kind: 'polygon', points: box, fill: fillOf(style), hitInside: true });
      const vFrom = { x: (a.x + b.x) / 2, y: a.y }, vTo = { x: (a.x + b.x) / 2, y: b.y }, hFrom = { x: a.x, y: (a.y + b.y) / 2 }, hTo = { x: b.x, y: (a.y + b.y) / 2 };
      lines([[vFrom, vTo], [hFrom, hTo], ...arrowHead(vFrom, vTo, 6 + style.lineWidth * 2).map(w => [vTo, w]), ...arrowHead(hFrom, hTo, 6 + style.lineWidth * 2).map(w => [hTo, w])]);
      const sign = stats.delta > 0 ? '+' : '';
      text({ x: (a.x + b.x) / 2, y: Math.max(a.y, b.y) }, [
        `${sign}${stats.delta.toFixed(precision)} (${stats.percent == null ? 'n/a' : sign + stats.percent.toFixed(2) + '%'})${stats.ticks == null ? '' : ' · ' + sign + stats.ticks + ' ticks'}`,
        `${count} bars · ${formatDuration(model.points[1].time - model.points[0].time)}`,
      ], { align: 'center', position: 'bottom', background: style.color, color: '#0b0f17' });
      break;
    }
    case 'icon-marker':
      shapes.push({ kind: 'polygon', points: iconPolygon(style.icon, a, style.markerSize), fill: style.color, hitInside: true, width: 1 });
      break;
    case 'arrow-marker': {
      const size = style.markerSize, dir = style.direction === 'up' ? 1 : -1;
      // Tip touches the anchor; the body sits below (up arrow) or above (down arrow).
      const tip = a, base = { x: a.x, y: a.y + dir * size * 1.6 }, head = size * 0.6, neck = { x: a.x, y: a.y + dir * head };
      const w = size * 0.5, stem = size * 0.18;
      shapes.push({ kind: 'polygon', fill: style.color, hitInside: true, width: 1, points: [tip, { x: a.x + w, y: neck.y }, { x: a.x + stem, y: neck.y }, { x: a.x + stem, y: base.y }, { x: a.x - stem, y: base.y }, { x: a.x - stem, y: neck.y }, { x: a.x - w, y: neck.y }] });
      break;
    }
    case 'price-label': {
      const label = model.points[0].price.toFixed(precision);
      shapes.push({ kind: 'ellipse', center: a, rx: 3, ry: 3, fill: style.color, stroke: false });
      text({ x: a.x + 4, y: a.y }, [label], { background: style.color, color: '#0b0f17', frame: true, position: 'center' });
      break;
    }
    default:
  }
}
