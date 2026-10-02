import { projectTimestamp } from '../timeCoordinates.js';

// Pointer and primitive media coordinates both use CSS pixels, independent of DPR.
export const BODY_TOLERANCE = 6;
export const HANDLE_TOLERANCE = 9;
export const HIT = Object.freeze({ A: 'ANCHOR_A', B: 'ANCHOR_B', BODY: 'BODY', NONE: 'NONE' });
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
export function hitDrawing(manager, chart, series, pointer) {
  const ordered = manager.getAll().filter(model => model.visible && model.type === 'trend-line');
  ordered.sort((a, b) => Number(a.id === manager.selectedId) - Number(b.id === manager.selectedId));
  for (const model of ordered.reverse()) {
    const points = model.points.map(p => {
      const x = projectTimestamp(chart.timeScale(), manager.bars, p.time), y = series.priceToCoordinate(p.price);
      return x == null || y == null ? null : { x, y };
    });
    const type = hitSegment(pointer, ...points, model.id === manager.selectedId);
    if (type !== HIT.NONE) return { id: model.id, type };
  }
  return { id: null, type: HIT.NONE };
}
