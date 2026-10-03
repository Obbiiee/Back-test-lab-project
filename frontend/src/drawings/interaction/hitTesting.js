import { projectGeometry } from '../projectGeometry.js';
import { RECTANGLE, FIBONACCI, ARROW, TEXT, MEASURE } from '../DrawingTypes.js';

import { fibonacciLevels, arrowHead, measurementLines, labelBounds, insideLabel } from '../advancedGeometry.js';

// Pointer and primitive media coordinates both use CSS pixels, independent of DPR.
export const BODY_TOLERANCE = 6;
export const HANDLE_TOLERANCE = 9;
export const HIT = Object.freeze({ A: 'ANCHOR_A', B: 'ANCHOR_B', C: 'CORNER_C', D: 'CORNER_D', BODY: 'BODY', NONE: 'NONE' });
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
  const ordered = manager.getAll().filter(model => model.visible);
  ordered.sort((a, b) => Number(a.id === manager.selectedId) - Number(b.id === manager.selectedId));
  for (const model of ordered.reverse()) {
    const points = projectGeometry(model, chart, series, manager.bars);
    if (points.length < (model.type === TEXT ? 1 : 2) || points.some(p => !p || !Number.isFinite(p.x + p.y))) continue;
    let type;
    if (model.type === TEXT) {
      const distance = Math.hypot(pointer.x-points[0].x,pointer.y-points[0].y);
      type = model.id === manager.selectedId && distance <= HANDLE_TOLERANCE ? HIT.A :
        distance <= BODY_TOLERANCE || insideLabel(pointer,labelBounds(points[0],model.text.split('\n'))) ? HIT.BODY : HIT.NONE;
    } else if (model.type === RECTANGLE) {
      const [a, b] = points;
      const index = model.id === manager.selectedId ? points.findIndex(p => Math.hypot(pointer.x-p.x, pointer.y-p.y) <= HANDLE_TOLERANCE) : -1;
      type = index >= 0 ? [HIT.A, HIT.B, HIT.C, HIT.D][index] :
        pointer.x >= Math.min(a.x,b.x)-BODY_TOLERANCE && pointer.x <= Math.max(a.x,b.x)+BODY_TOLERANCE &&
        pointer.y >= Math.min(a.y,b.y)-BODY_TOLERANCE && pointer.y <= Math.max(a.y,b.y)+BODY_TOLERANCE ? HIT.BODY : HIT.NONE;
      // Additional projected corners are transient, never canonical anchors.
    } else type = hitSegment(pointer, points[0], points[1], model.points.length === 2 && model.id === manager.selectedId);
    if (type === HIT.NONE && model.type === FIBONACCI) {
      for(const level of fibonacciLevels(model.points)) {
        const y=series.priceToCoordinate(level.price);
        if(!Number.isFinite(y)) continue;
        if(hitSegment(pointer,{x:points[0].x,y},{x:points[1].x,y})!==HIT.NONE ||
          insideLabel(pointer,labelBounds({x:Math.max(points[0].x,points[1].x),y},[level.ratio+' · '+level.price.toFixed(3)]))) {type=HIT.BODY;break;}
      }
    }
    if (type === HIT.NONE && model.type === ARROW && arrowHead(...points).some(wing=>hitSegment(pointer,points[1],wing)!==HIT.NONE)) type=HIT.BODY;
    if (type === HIT.NONE && model.type === MEASURE) {
      const [a,b]=points, corner={x:b.x,y:a.y};
      if(hitSegment(pointer,a,corner)!==HIT.NONE || hitSegment(pointer,corner,b)!==HIT.NONE ||
        insideLabel(pointer,labelBounds({x:(a.x+b.x)/2,y:(a.y+b.y)/2},measurementLines(model.points,manager.bars)))) type=HIT.BODY;
    }
    if (type !== HIT.NONE) return { id: model.id, type };
  }
  return { id: null, type: HIT.NONE };
}
