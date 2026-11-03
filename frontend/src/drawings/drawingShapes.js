// One geometry description per drawing, shared by the canvas renderer and hit
// testing so what you see is exactly what you can click (Issue #21 C-01).
// All coordinates are transient CSS pixels; canonical TIME+PRICE anchors are
// never modified here.
import { RECTANGLE, HORIZONTAL_LINE, VERTICAL_LINE, FIBONACCI, ARROW, TEXT, MEASURE, RAY, TREND_LINE } from './DrawingTypes.js';
import { arrowHead, measurementLines, labelBounds } from './advancedGeometry.js';
import { rayEnd } from './rayGeometry.js';
import { resolvedStyle, withAlpha } from './drawingStyle.js';
import { extraShapes } from './professionalShapes.js';

export function fibLevelsFor(model) {
  const style = resolvedStyle(model), [a, b] = model.points;
  return style.levels.filter(level => level.visible).map(level => ({
    ratio: level.value, color: level.color ?? style.color,
    price: style.reverse ? a.price + (b.price - a.price) * level.value : b.price + (a.price - b.price) * level.value,
  }));
}

export function formatTimeLabel(time) {
  if (!Number.isFinite(time)) return '';
  return new Date(Math.round(time) * 1000).toISOString().slice(0, 16).replace('T', ' ');
}

function line(a, b) { return [a, b]; }

// env: { width, height, priceToY(price), bars, precision }
export function drawingShapes(model, projected, env) {
  const style = resolvedStyle(model);
  const shapes = [];
  const precision = env.precision ?? 3;
  const textStyle = { fontSize: style.fontSize, fontFamily: style.fontFamily, bold: style.bold, italic: style.italic, color: style.textColor,
    background: style.textBackground, border: style.textBorder, align: style.textAlign, position: style.labelPosition };
  const [a, b] = projected;
  const lines = segments => shapes.push({ kind: 'lines', segments });
  const text = (anchor, content, options = {}) => shapes.push({ kind: 'text', anchor, lines: content,
    style: { ...textStyle, ...options }, bounds: labelBounds(anchor, content, { ...textStyle, ...options }) });
  switch (model.type) {
    case TEXT:
      text(a, model.text.split('\n'), { frame: true });
      break;
    case RECTANGLE: {
      const c = projected[2], d = projected[3];
      if (style.extendLeft || style.extendRight) {
        const left = style.extendLeft ? 0 : Math.min(a.x, b.x), right = style.extendRight ? env.width : Math.max(a.x, b.x);
        const top = Math.min(a.y, b.y), bottom = Math.max(a.y, b.y);
        shapes.push({ kind: 'polygon', points: [{ x: left, y: top }, { x: right, y: top }, { x: right, y: bottom }, { x: left, y: bottom }],
          fill: style.fillOpacity > 0 ? withAlpha(style.fillColor, style.fillOpacity) : null });
      } else shapes.push({ kind: 'polygon', points: [a, c, b, d], fill: style.fillOpacity > 0 ? withAlpha(style.fillColor, style.fillOpacity) : null });
      break;
    }
    case HORIZONTAL_LINE:
      lines([line(a, b)]);
      if (style.showPriceLabels) text({ x: env.width, y: a.y }, [model.points[0].price.toFixed(precision)], { align: 'right', position: 'top', background: style.color, color: '#0b0f17' });
      break;
    case VERTICAL_LINE:
      lines([line(a, b)]);
      if (style.showTimeLabels) text({ x: a.x, y: env.height }, [formatTimeLabel(model.points[0].time) + ' UTC'], { align: 'center', position: 'top', background: style.color, color: '#0b0f17' });
      break;
    case TREND_LINE: case RAY: {
      let start = a, end = b;
      if (model.type === RAY || style.extendRight) end = rayEnd(a, b, env.width, env.height);
      if (model.type === TREND_LINE && style.extendLeft) start = rayEnd(b, a, env.width, env.height);
      lines([line(start, end)]);
      if (style.showPriceLabels) for (const [index, point] of projected.entries())
        text(point, [model.points[index].price.toFixed(precision)], { background: style.color, color: '#0b0f17', fontSize: Math.min(style.fontSize, 12) });
      break;
    }
    case ARROW:
      lines([line(a, b), ...arrowHead(a, b, 8 + style.lineWidth * 2).map(wing => line(b, wing))]);
      break;
    case MEASURE:
      lines([line(a, b), line(a, { x: b.x, y: a.y }), line({ x: b.x, y: a.y }, b)]);
      text({ x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }, measurementLines(model.points, env.bars));
      break;
    case FIBONACCI: {
      lines([line(a, b)]);
      const levels = fibLevelsFor(model).map(level => ({ ...level, y: env.priceToY(level.price) })).filter(level => Number.isFinite(level.y));
      const left = style.extendLeft ? 0 : Math.min(a.x, b.x), right = style.extendRight ? env.width : Math.max(a.x, b.x);
      if (style.fillOpacity > 0) {
        const sorted = [...levels].sort((x, y) => x.ratio - y.ratio);
        for (let i = 1; i < sorted.length; i++) shapes.push({ kind: 'polygon', stroke: false, fill: withAlpha(sorted[i].color, style.fillOpacity),
          points: [{ x: left, y: sorted[i - 1].y }, { x: right, y: sorted[i - 1].y }, { x: right, y: sorted[i].y }, { x: left, y: sorted[i].y }] });
      }
      for (const level of levels) {
        shapes.push({ kind: 'lines', segments: [line({ x: left, y: level.y }, { x: right, y: level.y })], color: level.color, level: true });
        if (style.showPriceLabels) text({ x: Math.max(a.x, b.x), y: level.y }, [level.ratio + ' · ' + level.price.toFixed(precision)],
          { background: 'none', color: level.color, fontSize: Math.min(style.fontSize, 14) });
      }
      break;
    }
    default:
      extraShapes(model, projected, env, { style, text, lines, shapes, precision });
  }
  return { shapes, style };
}
