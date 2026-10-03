import { HORIZONTAL_LINE, VERTICAL_LINE } from '../DrawingTypes.js';
import { hitDrawing, HIT } from './hitTesting.js';
import { continuousPointFromPointer } from '../timeCoordinates.js';

export function isEditable(target) {
  return Boolean(target?.closest?.('input,textarea,select,[contenteditable]:not([contenteditable="false"]),[role="textbox"],[role="spinbutton"],[role="combobox"]'));
}
export class DrawingInteractionController {
  drag = null;
  constructor(manager, chart, series, history = null) { this.manager = manager; this.chart = chart; this.series = series; this.history = history; }
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
      return index === (drag.type === HIT.A ? 0 : 1) ? point : anchor;
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
      const hit = this.hit(pointer(event));
      cursor(hit.type === HIT.NONE ? '' : this.manager.get(hit.id)?.locked ? 'pointer' : hit.type === HIT.BODY ? 'move' : 'crosshair');
    };
    const up = event => { if (this.drag) { event.stopPropagation(); restore(false); } };
    const cancel = () => restore(true);
    const key = event => {
      if (isEditable(event.target)) return;
      const drawingFocus = element.contains(event.target) || event.target?.tagName === 'BODY' || event.target?.closest?.('.primitive-drawing-controls');
      if ((event.ctrlKey || event.metaKey) && ['z','y'].includes(event.key.toLowerCase()) && this.history && this.manager.historyFocus !== 'trading' && drawingFocus) {
        event.preventDefault(); event.stopImmediatePropagation(); restore(true);
        if (event.key.toLowerCase() === 'y' || event.shiftKey) this.history.redo(); else this.history.undo();
        return;
      }
      if (event.key === 'Escape' && (this.drag || this.manager.selectedId)) { event.stopImmediatePropagation(); if (this.drag) restore(true); else this.escape(); cursor(''); }
      if (['Delete', 'Backspace'].includes(event.key) && this.manager.selectedId) { event.preventDefault(); event.stopImmediatePropagation(); restore(true); this.deleteSelected(); }
    };
    root.addEventListener('pointerdown', down, true); root.addEventListener('pointermove', move, true);
    root.addEventListener('pointerup', up, true); root.addEventListener('pointercancel', cancel, true);
    root.addEventListener('lostpointercapture', cancel, true);
    window.addEventListener('keydown', key, true); window.addEventListener('blur', cancel);
    return () => {
      restore(true);
      root.removeEventListener('pointerdown', down, true); root.removeEventListener('pointermove', move, true);
      root.removeEventListener('pointerup', up, true); root.removeEventListener('pointercancel', cancel, true);
      root.removeEventListener('lostpointercapture', cancel, true);
      window.removeEventListener('keydown', key, true); window.removeEventListener('blur', cancel);
    };
  }
}
