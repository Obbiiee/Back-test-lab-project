// Geometry for the professional tool catalog (Issue #21 C-03, D10–D25).
// Returns render+hit shapes in transient CSS pixels; see drawingShapes.js.
import {
  EXTENDED_LINE, HORIZONTAL_RAY, CROSS_LINE, PARALLEL_CHANNEL, REGRESSION_TREND, FIB_EXTENSION, FIB_CHANNEL,
  ROTATED_RECTANGLE, ELLIPSE, POLYLINE, BRUSH, HIGHLIGHTER, ANCHORED_TEXT, CALLOUT, PRICE_RANGE, DATE_RANGE,
} from './DrawingTypes.js';
import { rayEnd } from './rayGeometry.js';
import { arrowHead } from './advancedGeometry.js';
import { withAlpha } from './drawingStyle.js';
import { extendedShapes } from './extendedShapes.js';
import { regressionFit, normalOffset, verticalOffset, formatDuration, barsBetween, priceRangeStats } from './professionalGeometry.js';

const shift = (p, dy) => ({ x: p.x, y: p.y + dy });
const fillOf = style => style.fillOpacity > 0 ? withAlpha(style.fillColor, style.fillOpacity) : null;
const fmtTime = time => new Date(Math.round(time) * 1000).toISOString().slice(0, 16).replace('T', ' ');

// Extend a segment according to the drawing's extend flags.
function extended(a, b, style, env) {
  return [style.extendLeft ? rayEnd(b, a, env.width, env.height) : a, style.extendRight ? rayEnd(a, b, env.width, env.height) : b];
}

export function fibExtensionLevels(model, levels) {
  const [a, b, c] = model.points;
  return levels.filter(level => level.visible).map(level => ({ ratio: level.value, color: level.color, price: c.price + (b.price - a.price) * level.value }));
}

export function extraShapes(model, projected, env, { style, text, lines, shapes, precision }) {
  const [a, b, c] = projected;
  const tag = { background: style.color, color: '#0b0f17', fontSize: Math.min(style.fontSize, 12) };
  const priceTag = (point, price, options = {}) => text(point, [price.toFixed(precision)], { ...tag, ...options });
  switch (model.type) {
    case EXTENDED_LINE:
      lines([[rayEnd(b, a, env.width, env.height), rayEnd(a, b, env.width, env.height)]]);
      if (style.showPriceLabels) projected.forEach((point, i) => priceTag(point, model.points[i].price));
      break;
    case HORIZONTAL_RAY:
      lines([[a, { x: Math.max(env.width, a.x), y: a.y }]]);
      if (style.showPriceLabels) priceTag({ x: env.width, y: a.y }, model.points[0].price, { align: 'right', position: 'top' });
      break;
    case CROSS_LINE:
      lines([[{ x: 0, y: a.y }, { x: env.width, y: a.y }], [{ x: a.x, y: 0 }, { x: a.x, y: env.height }]]);
      if (style.showPriceLabels) priceTag({ x: env.width, y: a.y }, model.points[0].price, { align: 'right', position: 'top' });
      if (style.showTimeLabels) text({ x: a.x, y: env.height }, [fmtTime(model.points[0].time) + ' UTC'], { ...tag, align: 'center', position: 'top' });
      break;
    case PARALLEL_CHANNEL: {
      const off = verticalOffset(a, b, c);
      const [s, e] = extended(a, b, style, env);
      if (fillOf(style)) shapes.push({ kind: 'polygon', stroke: false, fill: fillOf(style), points: [s, e, shift(e, off), shift(s, off)] });
      lines([[s, e], [shift(s, off), shift(e, off)]]);
      if (style.showMiddle) shapes.push({ kind: 'lines', segments: [[shift(s, off / 2), shift(e, off / 2)]], dash: [4, 4], width: 1 });
      break;
    }
    case REGRESSION_TREND: {
      const fit = regressionFit(env.bars ?? [], model.points[0].time, model.points[1].time);
      if (!fit) { shapes.push({ kind: 'lines', segments: [[a, b]], dash: [3, 4] }); break; }
      const [s, e] = extended(a, b, { ...style, extendLeft: false }, env);
      const off = (env.priceToY(fit.priceAt(model.points[0].time) + style.deviation * fit.sd) ?? a.y) - a.y;
      if (style.deviation > 0 && Number.isFinite(off)) {
        if (fillOf(style)) shapes.push({ kind: 'polygon', stroke: false, fill: fillOf(style), points: [shift(s, off), shift(e, off), shift(e, -off), shift(s, -off)] });
        shapes.push({ kind: 'lines', segments: [[shift(s, off), shift(e, off)], [shift(s, -off), shift(e, -off)]], width: Math.max(1, style.lineWidth - 1) });
      }
      lines([[s, e]]);
      break;
    }
    case FIB_EXTENSION: {
      shapes.push({ kind: 'lines', segments: [[a, b], [b, c]], dash: [4, 4], width: 1 });
      const span = Math.max(40, Math.abs(b.x - a.x));
      const left = style.extendLeft ? 0 : c.x, right = style.extendRight ? env.width : c.x + span;
      const levels = fibExtensionLevels(model, style.levels).map(level => ({ ...level, color: level.color ?? style.color, y: env.priceToY(level.price) })).filter(level => Number.isFinite(level.y));
      if (fillOf(style)) {
        const sorted = [...levels].sort((x, y) => x.ratio - y.ratio);
        for (let i = 1; i < sorted.length; i++) shapes.push({ kind: 'polygon', stroke: false, fill: withAlpha(sorted[i].color, style.fillOpacity),
          points: [{ x: left, y: sorted[i - 1].y }, { x: right, y: sorted[i - 1].y }, { x: right, y: sorted[i].y }, { x: left, y: sorted[i].y }] });
      }
      for (const level of levels) {
        shapes.push({ kind: 'lines', segments: [[{ x: left, y: level.y }, { x: right, y: level.y }]], color: level.color, level: true });
        if (style.showPriceLabels) text({ x: right, y: level.y }, [level.ratio + ' · ' + level.price.toFixed(precision)], { background: 'none', color: level.color, fontSize: Math.min(style.fontSize, 14) });
      }
      break;
    }
    case FIB_CHANNEL: {
      const off = verticalOffset(a, b, c);
      const [s, e] = extended(a, b, style, env);
      const levels = style.levels.filter(level => level.visible).map(level => ({ ratio: level.value, color: level.color ?? style.color, dy: off * level.value }));
      if (fillOf(style)) {
        const sorted = [...levels].sort((x, y) => x.ratio - y.ratio);
        for (let i = 1; i < sorted.length; i++) shapes.push({ kind: 'polygon', stroke: false, fill: withAlpha(sorted[i].color, style.fillOpacity),
          points: [shift(s, sorted[i - 1].dy), shift(e, sorted[i - 1].dy), shift(e, sorted[i].dy), shift(s, sorted[i].dy)] });
      }
      for (const level of levels) {
        shapes.push({ kind: 'lines', segments: [[shift(s, level.dy), shift(e, level.dy)]], color: level.color, level: true });
        if (style.showPriceLabels) text(shift(b, level.dy), [String(level.ratio)], { background: 'none', color: level.color, fontSize: Math.min(style.fontSize, 14) });
      }
      break;
    }
    case ROTATED_RECTANGLE: {
      const { nx, ny, distance } = normalOffset(a, b, c);
      const lift = p => ({ x: p.x + nx * distance, y: p.y + ny * distance });
      shapes.push({ kind: 'polygon', points: [a, b, lift(b), lift(a)], fill: fillOf(style) });
      break;
    }
    case ELLIPSE:
      shapes.push({ kind: 'ellipse', center: { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }, rx: Math.abs(b.x - a.x) / 2, ry: Math.abs(b.y - a.y) / 2, fill: fillOf(style) });
      break;
    case POLYLINE:
      shapes.push(fillOf(style) && projected.length > 2 ? { kind: 'polygon', points: projected, fill: fillOf(style) } : { kind: 'path', points: projected });
      break;
    case BRUSH: case HIGHLIGHTER:
      shapes.push({ kind: 'path', points: projected, join: 'round' });
      break;
    case ANCHORED_TEXT: {
      const top = { x: a.x, y: a.y - 10 };
      shapes.push({ kind: 'lines', segments: [[a, top]], width: 1 });
      shapes.push({ kind: 'ellipse', center: a, rx: 3, ry: 3, fill: style.color, stroke: false });
      text(top, (model.text ?? '').split('\n'), { frame: true });
      break;
    }
    case CALLOUT:
      lines([[a, b]]);
      shapes.push({ kind: 'ellipse', center: a, rx: 3, ry: 3, fill: style.color, stroke: false });
      text(b, (model.text ?? '').split('\n'), { frame: true, position: 'center', align: b.x >= a.x ? 'left' : 'right' });
      break;
    case PRICE_RANGE: {
      const stats = priceRangeStats(model.points[0], model.points[1], env.tickSize);
      const mid = (a.x + b.x) / 2, from = { x: mid, y: a.y }, to = { x: mid, y: b.y };
      shapes.push({ kind: 'polygon', stroke: false, hitInside: true, fill: fillOf(style), points: [{ x: a.x, y: a.y }, { x: b.x, y: a.y }, { x: b.x, y: b.y }, { x: a.x, y: b.y }] });
      lines([[{ x: a.x, y: a.y }, { x: b.x, y: a.y }], [{ x: a.x, y: b.y }, { x: b.x, y: b.y }], [from, to], ...arrowHead(from, to, 6 + style.lineWidth * 2).map(w => [to, w])]);
      const sign = stats.delta > 0 ? '+' : '';
      text({ x: mid, y: b.y }, [`${sign}${stats.delta.toFixed(precision)} (${stats.percent == null ? 'n/a' : sign + stats.percent.toFixed(2) + '%'})`, `${stats.ticks == null ? '' : sign + stats.ticks + ' ticks'}`].filter(Boolean),
        { align: 'center', position: b.y <= a.y ? 'top' : 'bottom', background: style.color, color: '#0b0f17' });
      break;
    }
    case DATE_RANGE: {
      const mid = (a.y + b.y) / 2, from = { x: a.x, y: mid }, to = { x: b.x, y: mid };
      const count = barsBetween(env.bars ?? [], model.points[0].time, model.points[1].time);
      shapes.push({ kind: 'polygon', stroke: false, hitInside: true, fill: fillOf(style), points: [{ x: a.x, y: a.y }, { x: b.x, y: a.y }, { x: b.x, y: b.y }, { x: a.x, y: b.y }] });
      lines([[{ x: a.x, y: a.y }, { x: a.x, y: b.y }], [{ x: b.x, y: a.y }, { x: b.x, y: b.y }], [from, to], ...arrowHead(from, to, 6 + style.lineWidth * 2).map(w => [to, w])]);
      text({ x: (a.x + b.x) / 2, y: Math.max(a.y, b.y) }, [`${count} bars · ${formatDuration(model.points[1].time - model.points[0].time)}`],
        { align: 'center', position: 'bottom', background: style.color, color: '#0b0f17' });
      break;
    }
    default:
      extendedShapes(model, projected, env, { style, text, lines, shapes, precision });
  }
}
