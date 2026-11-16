import { logicalForTimestamp } from './timeCoordinates.js';
export const FIB_LEVELS = Object.freeze([0, 0.236, 0.382, 0.5, 0.618, 0.786, 1]);
export function fibonacciLevels([a, b]) {
  return FIB_LEVELS.map(ratio => ({ ratio, price: b.price + (a.price - b.price) * ratio }));
}
export function arrowHead(a, b, size = 12) {
  const dx = b.x-a.x, dy = b.y-a.y, distance = Math.hypot(dx,dy);
  if (distance < 1e-9) return [];
  const length = Math.min(size, distance), ux = dx/distance, uy = dy/distance;
  return [ { x: b.x-length*ux+length*.5*uy, y: b.y-length*uy-length*.5*ux },
    { x: b.x-length*ux-length*.5*uy, y: b.y-length*uy+length*.5*ux } ];
}
export function measurement([a,b], bars) {
  const start = logicalForTimestamp(bars,a.time), end = logicalForTimestamp(bars,b.time);
  return { priceDelta:b.price-a.price, percentage:a.price===0?null:(b.price-a.price)/a.price*100,
    seconds:b.time-a.time, bars:start==null||end==null?null:end-start };
}
export function measurementLines(points, bars) {
  const m = measurement(points,bars);
  return [ 'Δ ' + m.priceDelta.toFixed(3) + ' (' + (m.percentage==null?'n/a':m.percentage.toFixed(2)+'%') + ')',
    m.seconds.toFixed(0) + 's · ' + (m.bars==null?'bars n/a':m.bars.toFixed(2)+' bars') ];
}
// Match the renderer's fixed 12px monospace font. Bounds are transient CSS pixels.
// Style-aware since Issue #21: font size scales the box, align/position move it.
export function labelBounds(anchor, lines, style = {}) {
  const size = style.fontSize ?? 12, charWidth = size * .6 * (style.bold ? 1.05 : 1), lineHeight = Math.round(size * 4 / 3);
  const width = Math.max(...lines.map(line=>Array.from(line).length))*charWidth+12, height = lines.length*lineHeight+8;
  const x = style.align === 'center' ? anchor.x - width / 2 : style.align === 'right' ? anchor.x - width - 6 : anchor.x + 6;
  const y = style.position === 'top' ? anchor.y - height - 4 : style.position === 'bottom' ? anchor.y + 6 : anchor.y - 4;
  return { x, y, width, height, lineHeight };
}
export function insideLabel(point, bounds) {
  return point.x>=bounds.x && point.x<=bounds.x+bounds.width && point.y>=bounds.y && point.y<=bounds.y+bounds.height;
}
