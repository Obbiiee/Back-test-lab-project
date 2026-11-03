import { projectGeometry } from '../projectGeometry.js';
import { RECTANGLE, TEXT, HORIZONTAL_LINE, VERTICAL_LINE } from '../DrawingTypes.js';
import { insideLabel } from '../advancedGeometry.js';
import { drawingShapes } from '../drawingShapes.js';
import { minimumAnchors } from '../primitives/TrendLinePrimitive.js';

// Pointer and primitive media coordinates both use CSS pixels, independent of DPR.
export const BODY_TOLERANCE = 6;
export const HANDLE_TOLERANCE = 9;
export const HIT = Object.freeze({ A: 'ANCHOR_A', B: 'ANCHOR_B', C: 'CORNER_C', D: 'CORNER_D', BODY: 'BODY', NONE: 'NONE' });
export const anchorHit = index => index === 0 ? HIT.A : index === 1 ? HIT.B : 'ANCHOR_' + index;
export function anchorIndex(type) {
  if (type === HIT.A) return 0;
  if (type === HIT.B) return 1;
  const match = /^ANCHOR_(\d+)$/.exec(type ?? '');
  return match ? Number(match[1]) : null;
}
export function hitSegment(pointer, a, b, selected = false) {
  if (!pointer || !a || !b) return HIT.NONE;
  const distance = p => Math.hypot(pointer.x - p.x, pointer.y - p.y);
  if (selected && distance(a) <= HANDLE_TOLERANCE) return HIT.A;
  if (selected && distance(b) <= HANDLE_TOLERANCE) return HIT.B;
  const dx = b.x - a.x, dy = b.y - a.y, length = dx * dx + dy * dy;
  if (length < 1e-12) return distance(a) <= BODY_TOLERANCE ? HIT.BODY : HIT.NONE;
  const t = ((pointer.x - a.x) * dx + (pointer.y - a.y) * dy) / length;
  if (t < 0 || t > 1) return HIT.NONE;
  return distance({ x: a.x + t * dx, y: a.y + t * dy }) <= BODY_TOLERANCE ? HIT.BODY : HIT.NONE;
}
function insidePolygon(pointer, points) {
  let inside = false;
  for (let i = 0, j = points.length - 1; i < points.length; j = i++) {
    const a = points[i], b = points[j];
    if ((a.y > pointer.y) !== (b.y > pointer.y) && pointer.x < (b.x - a.x) * (pointer.y - a.y) / (b.y - a.y) + a.x) inside = !inside;
  }
  return inside;
}
function hitShape(pointer, shape) {
  const edge = (a, b) => hitSegment(pointer, a, b) !== HIT.NONE;
  if (shape.kind === 'text') return insideLabel(pointer, shape.bounds);
  if (shape.kind === 'lines') return shape.segments.some(([a, b]) => edge(a, b));
  if (shape.kind === 'polygon' || shape.kind === 'path') {
    const closed = shape.kind === 'polygon';
    for (let i = 1; i < shape.points.length; i++) if (edge(shape.points[i - 1], shape.points[i])) return true;
    if (closed && shape.points.length > 2 && edge(shape.points.at(-1), shape.points[0])) return true;
    return closed && (shape.fill || shape.hitInside) ? insidePolygon(pointer, shape.points) : false;
  }
  if (shape.kind === 'ellipse') {
    const cos = Math.cos(-(shape.rotation ?? 0)), sin = Math.sin(-(shape.rotation ?? 0));
    const dx = pointer.x - shape.center.x, dy = pointer.y - shape.center.y;
    const x = dx * cos - dy * sin, y = dx * sin + dy * cos;
    const rx = Math.max(1, shape.rx), ry = Math.max(1, shape.ry);
    const r = Math.hypot(x / rx, y / ry), scale = Math.min(rx, ry);
    return Math.abs(r - 1) * scale <= BODY_TOLERANCE || (Boolean(shape.fill) && r < 1);
  }
  if (shape.kind === 'arc') {
    const d = Math.hypot(pointer.x - shape.center.x, pointer.y - shape.center.y);
    if (Math.abs(d - shape.radius) > BODY_TOLERANCE) return false;
    let angle = Math.atan2(pointer.y - shape.center.y, pointer.x - shape.center.x);
    const [start, end] = shape.anticlockwise ? [shape.end, shape.start] : [shape.start, shape.end];
    while (angle < start) angle += Math.PI * 2;
    return angle <= end + 1e-9 || end - start >= Math.PI * 2 - 1e-9;
  }
  return false;
}
export function hitDrawing(manager, chart, series, pointer) {
  const ordered = manager.getAll().filter(model => model.visible);
  ordered.sort((a, b) => Number(a.id === manager.selectedId) - Number(b.id === manager.selectedId));
  const env = { width: chart.timeScale().width?.() ?? 0, height: chart.paneSize?.().height ?? 0,
    priceToY: price => series.priceToCoordinate(price), bars: manager.bars, precision: manager.precision ?? 3 };
  for (const model of ordered.reverse()) {
    const points = projectGeometry(model, chart, series, manager.bars);
    if (points.length < minimumAnchors(model.type) || points.some(p => !p || !Number.isFinite(p.x + p.y))) continue;
    const selected = model.id === manager.selectedId;
    let type = HIT.NONE, index = null;
    if (selected && ![HORIZONTAL_LINE, VERTICAL_LINE].includes(model.type)) {
      // Handles remain the canonical anchors (plus the two transient rectangle corners).
      const found = points.findIndex(p => Math.hypot(pointer.x - p.x, pointer.y - p.y) <= HANDLE_TOLERANCE);
      if (found >= 0) {
        if (model.type === RECTANGLE) type = [HIT.A, HIT.B, HIT.C, HIT.D][found];
        else { type = anchorHit(found); index = found; }
      }
    }
    if (type === HIT.NONE && model.type === TEXT && Math.hypot(pointer.x - points[0].x, pointer.y - points[0].y) <= BODY_TOLERANCE) type = HIT.BODY;
    if (type === HIT.NONE) {
      const { shapes } = drawingShapes(model, points, env);
      if (model.type === RECTANGLE) {
        const [a, b] = points;
        if (pointer.x >= Math.min(a.x, b.x) - BODY_TOLERANCE && pointer.x <= Math.max(a.x, b.x) + BODY_TOLERANCE &&
          pointer.y >= Math.min(a.y, b.y) - BODY_TOLERANCE && pointer.y <= Math.max(a.y, b.y) + BODY_TOLERANCE) type = HIT.BODY;
      }
      if (type === HIT.NONE && shapes.some(shape => hitShape(pointer, shape))) type = HIT.BODY;
    }
    if (type !== HIT.NONE) return { id: model.id, type, ...(index != null ? { index } : {}) };
  }
  return { id: null, type: HIT.NONE };
}
