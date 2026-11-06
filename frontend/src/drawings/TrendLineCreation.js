import { TREND_LINE, DRAWING_SPECS } from './DrawingTypes.js';
import { pointFromPointer, continuousPointFromPointer } from './timeCoordinates.js';
import { decimateStroke } from './professionalGeometry.js';

// Shared transient creation workflow for every research drawing.
// - fixed tools: one click per anchor (1, 2 or 3), live draft for the rest;
// - text tools: anchors first, then the text editor (nothing stored until saved);
// - node tools (Polyline): click per node, finish with Done / Enter / double-click,
//   Backspace removes the last node;
// - freehand tools (Brush, Highlighter): one pointer drag, decimated and bounded.
// Defaults preserve Trend Line callers.
export const NODE_FINISH_DISTANCE = 5;
export const FREEHAND_MIN_DISTANCE = 3;

export class TrendLineCreation {
  anchors = [];
  pixels = [];
  textPending = false;
  constructor(manager, chart, series, bars, timeframe, onComplete, type = TREND_LINE, onTextRequest = null) {
    Object.assign(this, { manager, chart, series, bars, timeframe, onComplete, type, onTextRequest });
  }
  get spec() { return DRAWING_SPECS[this.type]; }
  get anchor() { return this.anchors[0] ?? null; }
  input(points, id) {
    const defaults = this.spec.defaults;
    return { id, type: this.type, points, metadata: { createdOnTimeframe: this.timeframe }, ...(defaults ? { options: { ...defaults } } : {}) };
  }
  #draft(points) {
    // Text tools preview their leader/anchor with a placeholder; the real text
    // is only stored when the user saves it.
    const input = { ...this.input(points, 'draft-' + this.type), ...(this.spec.text ? { text: '…' } : {}) };
    if (this.manager.draft) this.manager.updateDraft(input); else this.manager.startDraft(input);
  }
  #padded(current) {
    const count = this.spec.points;
    return [...this.anchors, ...Array(Math.max(0, count - this.anchors.length)).fill(current)];
  }
  #complete(points) {
    const object = this.manager.add(this.input(points, crypto.randomUUID()));
    this.cancel(); this.onComplete?.(object);
    return object;
  }
  suppressedUntil = 0;
  click = param => {
    const spec = this.spec;
    if (spec.freehand || this.textPending || this.gesture?.multi || Date.now() < this.suppressedUntil) return;
    const point = pointFromPointer(this.chart, this.series, param, this.bars);
    if (!point) return;
    if (spec.nodes) {
      const last = this.pixels.at(-1);
      if (last && param.point && Math.hypot(param.point.x - last.x, param.point.y - last.y) <= NODE_FINISH_DISTANCE) { this.finish(); return; }
      this.anchors.push(point); this.pixels.push(param.point ?? null);
      if (this.anchors.length >= spec.points.max) { this.finish(); return; }
      this.#draft([...this.anchors, point]);
      return;
    }
    this.anchors.push(point);
    if (this.anchors.length >= spec.points) {
      if (spec.text) {
        this.textPending = true;
        if (this.anchors.length > 1) this.#draft([...this.anchors]);
        this.onTextRequest?.(point, [...this.anchors]);
        return;
      }
      this.#complete([...this.anchors]);
      return;
    }
    this.#draft(this.#padded(point));
  };
  move = param => {
    if (!this.anchors.length || this.textPending) return;
    const point = pointFromPointer(this.chart, this.series, param, this.bars);
    if (!point) return;
    this.#draft(this.spec.nodes ? [...this.anchors, point] : this.#padded(point));
  };
  // Polyline: Done / Enter / double-click. Fewer than two nodes cancels.
  finish() {
    if (!this.spec.nodes) return null;
    const nodes = [...this.anchors];
    if (nodes.length < this.spec.points.min) { this.cancel(); return null; }
    return this.#complete(nodes);
  }
  removeLastNode() {
    if (!this.spec.nodes || !this.anchors.length) return;
    this.anchors.pop(); this.pixels.pop();
    if (!this.anchors.length) { this.manager.cancelDraft(); return; }
    this.#draft([...this.anchors, this.anchors.at(-1)]);
  }
  get nodeCount() { return this.spec.nodes ? this.anchors.length : 0; }
  // Two-finger pinch/pan must never place anchors: any anchor added since the
  // gesture's first finger is rolled back and clicks stay ignored until all
  // fingers lift (plus a short settle time for the synthetic click).
  bindTouchGuard(element) {
    const root = element.parentElement;
    const start = event => {
      if (!this.gesture) this.gesture = { anchors: this.anchors.length, multi: false };
      if (event.touches.length > 1 && !this.gesture.multi) {
        this.gesture.multi = true;
        if (this.anchors.length > this.gesture.anchors) {
          this.anchors = this.anchors.slice(0, this.gesture.anchors); this.pixels = this.pixels.slice(0, this.gesture.anchors);
          if (!this.anchors.length) this.manager.cancelDraft();
        }
      }
    };
    const end = event => {
      if (event.touches.length) return;
      if (this.gesture?.multi) this.suppressedUntil = Date.now() + 400;
      this.gesture = null;
    };
    root.addEventListener('touchstart', start, { capture: true, passive: true });
    root.addEventListener('touchend', end, { capture: true, passive: true });
    root.addEventListener('touchcancel', end, { capture: true, passive: true });
    return () => {
      root.removeEventListener('touchstart', start, { capture: true });
      root.removeEventListener('touchend', end, { capture: true });
      root.removeEventListener('touchcancel', end, { capture: true });
      this.gesture = null;
    };
  }
  // Freehand strokes are bound to raw pointer events for one continuous drag.
  // Chart panning/zoom is paused while the tool is active and restored after.
  bindFreehand(element) {
    const root = element.parentElement, chart = this.chart;
    const saved = { handleScroll: chart.options?.().handleScroll, handleScale: chart.options?.().handleScale };
    chart.applyOptions?.({ handleScroll: false, handleScale: false });
    const touchAction = root.style?.touchAction ?? '';
    if (root.style) root.style.touchAction = 'none'; // a finger drag draws instead of scrolling
    let stroke = null;
    const local = event => { const rect = element.getBoundingClientRect(); return { x: event.clientX - rect.left, y: event.clientY - rect.top }; };
    const inside = p => p.x >= 0 && p.y >= 0 && p.x <= chart.timeScale().width() && p.y <= chart.paneSize().height;
    const preview = () => {
      const points = decimateStroke(stroke.pixels, FREEHAND_MIN_DISTANCE, this.spec.points.max)
        .map(p => continuousPointFromPointer(chart, this.series, p, this.bars)).filter(Boolean);
      if (points.length >= 2) this.#draft(points);
      return points;
    };
    const down = event => {
      if (event.button !== 0) return;
      const p = local(event);
      if (!inside(p)) return;
      event.preventDefault(); event.stopPropagation();
      stroke = { id: event.pointerId, pixels: [p] };
      root.setPointerCapture?.(event.pointerId);
    };
    const move = event => {
      if (!stroke || event.pointerId !== stroke.id) return;
      event.preventDefault(); event.stopPropagation();
      if (stroke.pixels.length < this.spec.points.max * 4) stroke.pixels.push(local(event));
      preview();
    };
    const up = event => {
      if (!stroke || event.pointerId !== stroke.id) return;
      event.preventDefault(); event.stopPropagation();
      const points = preview();
      if (root.hasPointerCapture?.(stroke.id)) root.releasePointerCapture(stroke.id);
      stroke = null;
      if (points.length >= this.spec.points.min) this.#complete(points); else this.cancel();
    };
    const cancel = () => { if (stroke) { stroke = null; this.cancel(); } };
    root.addEventListener('pointerdown', down, true); root.addEventListener('pointermove', move, true);
    root.addEventListener('pointerup', up, true); root.addEventListener('pointercancel', cancel, true);
    return () => {
      cancel();
      root.removeEventListener('pointerdown', down, true); root.removeEventListener('pointermove', move, true);
      root.removeEventListener('pointerup', up, true); root.removeEventListener('pointercancel', cancel, true);
      if (root.style) root.style.touchAction = touchAction;
      chart.applyOptions?.({ ...(saved.handleScroll !== undefined ? { handleScroll: saved.handleScroll } : {}), ...(saved.handleScale !== undefined ? { handleScale: saved.handleScale } : {}) });
    };
  }
  cancel() { this.textPending = false; this.anchors = []; this.pixels = []; this.manager.cancelDraft(); }
}
