// Endpoint normalization adapted from deepentropy/lightweight-charts-drawing
// src/core/scene/lines.ts:sceneExtendedSegment at 72290d3165682ec7bd28f96af7f9354184982dda.
// MIT Copyright (c) 2026 deepentropy; distribution license/notice in public/licenses.
// BTL adaptation: account for offscreen anchors when extending past the pane.
// Only transient screen coordinates are extended; canonical TIME+PRICE is untouched.
export function rayEnd(a, b, width, height) {
  const dx = b.x - a.x, dy = b.y - a.y;
  const len = Math.hypot(dx, dy) || 1;
  const extent = 2 * (width + height + Math.abs(a.x) + Math.abs(a.y) + Math.abs(b.x) + Math.abs(b.y));
  return {x:b.x + dx / len * extent, y:b.y + dy / len * extent};
}
