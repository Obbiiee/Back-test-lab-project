import { useEffect, useRef, useState } from 'react';
import { DrawingManager } from './DrawingManager.js';
import { TrendLineCreation } from './TrendLineCreation.js';
import { DRAWING_SPECS, TEXT } from './DrawingTypes.js';
import { DrawingInteractionController } from './interaction/DrawingInteractionController.js';
import { DrawingHistory } from './DrawingHistory.js';
import { DrawingDocumentStore } from './DrawingPersistence.js';
import { decimalsOf } from './drawingEdits.js';

// React integration is outside the manager/domain. Pointer previews update only
// the primitive; React receives completed objects and draft start/cancel events.
export default function useDrawingTools({ chart, series, candles, mode, onModeChange, timeframe, container, workspace, tickSize = 0.001 }) {
  const [{ manager, history }] = useState(() => {
    const manager = new DrawingManager();
    return { manager, history: new DrawingHistory(manager) };
  });
  const [textEditor, setTextEditor] = useState(null);
  const [propertiesId, setPropertiesId] = useState(null);
  const tickSizeRef = useRef(tickSize);
  useEffect(() => { tickSizeRef.current = tickSize; }, [tickSize]);
  useEffect(() => { manager.setPrecision(Math.min(12, decimalsOf(tickSize))); manager.setTickSize(tickSize); }, [manager, tickSize]);
  const persistenceRef = useRef(null);
  const creationRef = useRef(null);
  const [snapshot, setSnapshot] = useState({ objects: [], draftActive: false });
  useEffect(() => manager.subscribe((objects, draftActive) => setSnapshot({ objects, draftActive, selectedId: manager.selectedId, canUndo: history.canUndo, canRedo: history.canRedo, storageStatus: persistenceRef.current?.status ?? '' })), [manager, history]);
  useEffect(() => {
    const persistence = new DrawingDocumentStore(() => window.localStorage, workspace);
    persistenceRef.current = persistence;
    history.reset(persistence.load(manager.registry));
    return manager.subscribeCommitted((before, after) => persistence.save(after));
  }, [manager, history, workspace]);
  useEffect(() => {
    if (!['none', 'cursor-dot', 'cursor-arrow'].includes(mode)) manager.setHistoryFocus(DRAWING_SPECS[mode] ? 'drawing' : 'trading');
    if (!chart || !series || !container.current || !['none', 'cursor-dot', 'cursor-arrow'].includes(mode)) { manager.select(null); return; }
    return new DrawingInteractionController(manager, chart, series, history, { onOpen: id => setPropertiesId(id), tickSize: () => tickSizeRef.current }).bind(container.current);
  }, [manager, history, chart, series, mode, container, timeframe]);
  useEffect(() => {
    if (!chart || !series) return;
    manager.attach(series);
    return () => manager.detach();
  }, [manager, chart, series]);
  useEffect(() => {
    manager.setTimePoints(candles);
    if (creationRef.current) creationRef.current.bars = candles;
  }, [manager, candles]);
  useEffect(() => {
    if (!chart || !series || !DRAWING_SPECS[mode]) return;
    const creation = new TrendLineCreation(manager, chart, series, manager.bars, timeframe, () => onModeChange('none'), mode,
      (point, points) => setTextEditor({ point, points, type: mode, text: '', timeframe }));
    creationRef.current = creation;
    const spec = DRAWING_SPECS[mode];
    const keydown = event => {
      if (event.key === 'Escape') { creation.cancel(); setTextEditor(null); onModeChange('none'); return; }
      if (!spec.nodes || event.target?.closest?.('input,textarea,select,[contenteditable]')) return;
      if (event.key === 'Enter' && creation.nodeCount) { event.preventDefault(); if (!creation.finish()) onModeChange('none'); }
      if (event.key === 'Backspace' && creation.nodeCount) { event.preventDefault(); event.stopImmediatePropagation(); creation.removeLastNode(); }
    };
    const unbindFreehand = spec.freehand && container.current ? creation.bindFreehand(container.current) : null;
    const unbindTouch = !spec.freehand && container.current ? creation.bindTouchGuard(container.current) : null;
    if (!spec.freehand) { chart.subscribeClick(creation.click); chart.subscribeCrosshairMove(creation.move); }
    window.addEventListener('keydown', keydown, true);
    return () => {
      if (!spec.freehand) { chart.unsubscribeClick(creation.click); chart.unsubscribeCrosshairMove(creation.move); }
      unbindFreehand?.(); unbindTouch?.();
      window.removeEventListener('keydown', keydown, true); creation.cancel();
      creationRef.current = null; setTextEditor(null);
    };
  }, [manager, chart, series, mode, onModeChange, timeframe, container]);
  const focusDrawing = () => { manager.setHistoryFocus('drawing'); container.current?.focus({ preventScroll: true }); };
  const cancelText = () => { setTextEditor(null); creationRef.current?.cancel(); onModeChange('none'); focusDrawing(); };
  const saveText = text => {
    if (!textEditor || !text.trim()) return;
    if (textEditor.id) manager.setText(textEditor.id, text.trim());
    else {
      const type = textEditor.type ?? TEXT, defaults = DRAWING_SPECS[type]?.defaults;
      manager.add({ id: crypto.randomUUID(), type, points: textEditor.points ?? [textEditor.point], text: text.trim(), metadata: { createdOnTimeframe: textEditor.timeframe }, ...(defaults ? { options: { ...defaults } } : {}) });
    }
    cancelText();
  };
  const properties = propertiesId && snapshot.objects.some(object => object.id === propertiesId) ? propertiesId : null;
  const creationSpec = DRAWING_SPECS[mode];
  return { ...snapshot, textEditor, cancelText, saveText, tickSize, bars: candles, propertiesId: properties,
    creating: creationSpec ? { type: mode, name: creationSpec.name, nodes: Boolean(creationSpec.nodes), freehand: Boolean(creationSpec.freehand), anchors: typeof creationSpec.points === 'number' ? creationSpec.points : null } : null,
    finishPath: () => { const done = creationRef.current?.finish(); if (!done) onModeChange('none'); },
    undoNode: () => creationRef.current?.removeLastNode(),
    cancelCreation: () => { creationRef.current?.cancel(); setTextEditor(null); onModeChange('none'); },
    openProperties: id => { if (manager.get(id)) { manager.select(id); setPropertiesId(id); } },
    closeProperties: () => { setPropertiesId(null); focusDrawing(); },
    setOptions: (id, patch, coalesce) => manager.setOptions(id, patch, coalesce),
    setPoints: (id, points, coalesce) => manager.setPoints(id, points, coalesce),
    rename: (id, name) => manager.rename(id, name),
    setTextContent: (id, text) => manager.setText(id, text),
    reorder: (id, where) => manager.reorder(id, where),
    replaceModel: model => { const all = manager.getAll().map(item => item.id === model.id ? model : item); manager.replaceAll(all); },
    duplicate: id => {
      const step = candles.length > 1 ? candles.at(-1).time - candles.at(-2).time : 60;
      const copy = manager.duplicate(id, crypto.randomUUID(), point => ({ time: point.time + step, price: point.price }));
      if (copy) { manager.select(copy.id); if (properties) setPropertiesId(copy.id); }
      return copy;
    }, clearSelection: () => { manager.select(null); manager.setHistoryFocus('trading'); }, select: id => { focusDrawing(); manager.select(id); }, remove: id => { focusDrawing(); manager.remove(id); }, editText: id => {
    const model = manager.get(id);
    if (!model || !DRAWING_SPECS[model.type]?.text || model.locked) return;
    focusDrawing(); setTextEditor({ id, text: model.text });
  }, undo: () => { focusDrawing(); setTextEditor(null); creationRef.current?.cancel(); onModeChange('none'); history.undo(); }, redo: () => { focusDrawing(); setTextEditor(null); creationRef.current?.cancel(); onModeChange('none'); history.redo(); }, setProperties: (id, properties) => { focusDrawing(); manager.setProperties(id, properties); }, showHidden: () => {
    focusDrawing();
    const models = manager.getAll().map(model => ({ ...model, visible: true }));
    manager.replaceAll(models);
  } };
}
