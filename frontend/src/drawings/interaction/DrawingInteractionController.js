import { HORIZONTAL_LINE, VERTICAL_LINE } from '../DrawingTypes.js';
import { hitDrawing, HIT, anchorIndex } from './hitTesting.js';
import { continuousPointFromPointer } from '../timeCoordinates.js';
import { stepPrice, stepBars } from '../drawingEdits.js';

export function isEditable(target) {
  return Boolean(target?.closest?.('.primitive-text-editor,input,textarea,select,[contenteditable]:not([contenteditable="false"]),[role="textbox"],[role="spinbutton"],[role="combobox"]'));
}
export class DrawingInteractionController {
  drag = null;
  constructor(manager, chart, series, history = null, options = {}) { this.manager = manager; this.chart = chart; this.series = series; this.history = history; this.options = options; }
  // Keyboard nudge of the selected drawing: one tick / one bar, Shift = 10×.
  nudge(key, large) {
    const model = this.manager.get(this.manager.selectedId);
    if (!model || model.locked) return false;
    const factor = large ? 10 : 1, tick = this.options.tickSize?.() ?? 0.001;
    const ticks = key === 'ArrowUp' ? factor : key === 'ArrowDown' ? -factor : 0;
    const bars = key === 'ArrowRight' ? factor : key === 'ArrowLeft' ? -factor : 0;
    const points = model.points.map(point => ({ time: bars ? stepBars(point.time, this.manager.bars, bars) : point.time, price: ticks ? stepPrice(point.price, ticks, tick) : point.price }));
    this.manager.setPoints(model.id, points, 'nudge');
    return true;
  }
  hit(point) { return hitDrawing(this.manager, this.chart, this.series, point); }
  point(pointer) { return continuousPointFromPointer(this.chart, this.series, pointer, this.manager.bars); }
  begin(hit, pointer) {
    this.manager.select(hit.id);
    const model = this.manager.get(hit.id), start = this.point(pointer);
    if (!model || model.locked || !start) return false;
    this.drag = { id: model.id, type: hit.type, drawingType: model.type, original: model.points, start };
    return true;
  }
  move(pointer) {
    const drag = this.drag, point = this.point(pointer);
    if (!drag || !point) return;
    if (point.time === drag.start.time && point.price === drag.start.price) { this.manager.update(drag.id, drag.original, false); return; }
    const points = drag.original.map((anchor, index) => {
      if (drag.drawingType === HORIZONTAL_LINE) return { time: anchor.time, price: anchor.price + (point.price - drag.start.price) };
      if (drag.drawingType === VERTICAL_LINE) return { time: anchor.time + (point.time - drag.start.time), price: anchor.price };
      if (drag.type === HIT.C) return index === 0 ? { ...anchor, price: point.price } : { ...anchor, time: point.time };
      if (drag.type === HIT.D) return index === 0 ? { ...anchor, time: point.time } : { ...anchor, price: point.price };
      if (drag.type === HIT.BODY) return { time: anchor.time + (point.time - drag.start.time), price: anchor.price + (point.price - drag.start.price) };
      return index === anchorIndex(drag.type) ? point : anchor;
    });
    this.manager.update(drag.id, points, false);
  }
  finish(cancel = false) {
    if (!this.drag) return;
    if (cancel) this.manager.update(this.drag.id, this.drag.original, false);
    this.drag = null; this.manager.commit(); this.manager.notify();
  }
  escape() {
    if (this.drag) this.finish(true);
    else this.manager.select(null);
  }
  deleteSelected() { this.finish(true); this.manager.remove(this.manager.selectedId); }
  bind(element) {
    const root = element.parentElement;
    let captureId = null, savedScroll = null;
    const cursor = value => { element.style.cursor = value; };
    const restore = cancel => {
      this.finish(cancel);
      if (savedScroll) { this.chart.applyOptions({ handleScroll: savedScroll }); savedScroll = null; }
      const id = captureId; captureId = null;
      if (id != null && root.hasPointerCapture(id)) root.releasePointerCapture(id);
      cursor('');
    };
    const pointer = event => {
      const rect = element.getBoundingClientRect();
      return { x: event.clientX - rect.left, y: event.clientY - rect.top };
    };
    const trading = event => Boolean(event.target.closest?.('[data-drawing-type],.trading-levels'));
    const down = event => {
      if (trading(event)) { this.manager.historyFocus = 'trading'; return; }
      if (event.button !== 0 || !element.contains(event.target)) return;
      this.manager.historyFocus = 'drawing';
      const point = pointer(event);
      if (point.x < 0 || point.y < 0 || point.x > this.chart.timeScale().width() || point.y > this.chart.paneSize().height) return;
      const hit = this.hit(point);
      if (!hit.id) { this.manager.select(null); cursor(''); return; }
      const draggable = this.begin(hit, point);
      element.focus({ preventScroll: true });
      if (!draggable) { event.stopPropagation(); return; }
      savedScroll = { ...this.chart.options().handleScroll };
      this.chart.applyOptions({ handleScroll: { pressedMouseMove: false, horzTouchDrag: false, vertTouchDrag: false } });
      event.preventDefault(); event.stopPropagation();
      captureId = event.pointerId; root.setPointerCapture(captureId); cursor('grabbing');
    };
    const move = event => {
      if (this.drag) { event.preventDefault(); event.stopPropagation(); this.move(pointer(event)); return; }
      if (trading(event) || !element.contains(event.target)) { cursor(''); return; }
      const point = pointer(event);
      if (point.y < 0 || point.y > this.chart.paneSize(0).height) { cursor(''); return; }
      const hit = this.hit(point);
      cursor(hit.type === HIT.NONE ? '' : this.manager.get(hit.id)?.locked ? 'pointer' : hit.type === HIT.BODY ? 'move' : 'crosshair');
    };
    const up = event => { if (this.drag) { event.stopPropagation(); restore(false); } };
    const cancel = () => restore(true);
    const key = event => {
      if (isEditable(event.target) || event.target?.closest?.('.drawing-properties')) return;
      const drawingFocus = element.contains(event.target) || event.target?.tagName === 'BODY' || event.target?.closest?.('.primitive-drawing-controls');
      if ((event.ctrlKey || event.metaKey) && ['z','y'].includes(event.key.toLowerCase()) && this.history && this.manager.historyFocus !== 'trading' && drawingFocus) {
        event.preventDefault(); event.stopImmediatePropagation(); restore(true);
        if (event.key.toLowerCase() === 'y' || event.shiftKey) this.history.redo(); else this.history.undo();
        return;
      }
      if (event.key === 'Escape' && (this.drag || this.manager.selectedId)) { event.stopImmediatePropagation(); if (this.drag) restore(true); else this.escape(); cursor(''); }
      if (['Delete', 'Backspace'].includes(event.key) && this.manager.selectedId) { event.preventDefault(); event.stopImmediatePropagation(); restore(true); this.deleteSelected(); }
      if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(event.key) && this.manager.selectedId && !this.drag && drawingFocus && !event.ctrlKey && !event.metaKey && !event.altKey) {
        if (this.nudge(event.key, event.shiftKey)) { event.preventDefault(); event.stopImmediatePropagation(); }
      }
    };
    const dblclick = event => {
      // Pointer capture retargets dblclick to the root, so test the pane rectangle.
      if (trading(event)) return;
      const point = pointer(event);
      if (point.x < 0 || point.y < 0 || point.x > this.chart.timeScale().width() || point.y > this.chart.paneSize().height) return;
      const hit = this.hit(point);
      if (hit.id) { event.preventDefault(); event.stopPropagation(); this.manager.select(hit.id); this.options.onOpen?.(hit.id); }
    };
    // Touch: while a drawing is selected the browser must not claim the gesture
    // for panning, or it cancels the handle drag (pointercancel). Page and chart
    // panning return as soon as nothing is selected.
    const syncTouch = () => { if (root.style) root.style.touchAction = this.manager.selectedId ? 'none' : ''; };
    const unsubscribeTouch = this.manager.subscribe?.(syncTouch); syncTouch();
    root.addEventListener('dblclick', dblclick, true);
    root.addEventListener('pointerdown', down, true); root.addEventListener('pointermove', move, true);
    root.addEventListener('pointerup', up, true); root.addEventListener('pointercancel', cancel, true);
    root.addEventListener('lostpointercapture', cancel, true);
    window.addEventListener('keydown', key, true); window.addEventListener('blur', cancel);
    return () => {
      restore(true);
      root.removeEventListener('pointerdown', down, true); root.removeEventListener('pointermove', move, true);
      root.removeEventListener('pointerup', up, true); root.removeEventListener('pointercancel', cancel, true);
      root.removeEventListener('lostpointercapture', cancel, true);
      root.removeEventListener('dblclick', dblclick, true);
      unsubscribeTouch?.(); if (root.style) root.style.touchAction = '';
      window.removeEventListener('keydown', key, true); window.removeEventListener('blur', cancel);
    };
  }
}
