import { useEffect, useRef, useState } from 'react';
import { DrawingManager } from './DrawingManager.js';
import { TrendLineCreation } from './TrendLineCreation.js';
import { CORE_DRAWINGS } from './DrawingTypes.js';
import { DrawingInteractionController } from './interaction/DrawingInteractionController.js';
import { DrawingHistory } from './DrawingHistory.js';
import { DrawingPersistence } from './DrawingPersistence.js';

// React integration is outside the manager/domain. Pointer previews update only
// the primitive; React receives completed objects and draft start/cancel events.
export default function useDrawingTools({ chart, series, candles, mode, onModeChange, timeframe, container, workspace }) {
  const [{ manager, history }] = useState(() => {
    const manager = new DrawingManager();
    return { manager, history: new DrawingHistory(manager) };
  });
  const persistenceRef = useRef(null);
  const creationRef = useRef(null);
  const [snapshot, setSnapshot] = useState({ objects: [], draftActive: false });
  useEffect(() => manager.subscribe((objects, draftActive) => setSnapshot({ objects, draftActive, selectedId: manager.selectedId, canUndo: history.canUndo, canRedo: history.canRedo, storageStatus: persistenceRef.current?.status ?? '' })), [manager, history]);
  useEffect(() => {
    const persistence = new DrawingPersistence(() => window.localStorage, workspace);
    persistenceRef.current = persistence;
    history.reset(persistence.load(manager.registry));
    return manager.subscribeCommitted((before, after) => persistence.save(after));
  }, [manager, history, workspace]);
  useEffect(() => {
    if (!['none', 'cursor-dot', 'cursor-arrow'].includes(mode)) manager.setHistoryFocus(CORE_DRAWINGS[mode] ? 'drawing' : 'trading');
    if (!chart || !series || !container.current || !['none', 'cursor-dot', 'cursor-arrow'].includes(mode)) { manager.select(null); return; }
    return new DrawingInteractionController(manager, chart, series, history).bind(container.current);
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
    if (!chart || !series || !CORE_DRAWINGS[mode]) return;
    const creation = new TrendLineCreation(manager, chart, series, manager.bars, timeframe, () => onModeChange('none'), mode);
    creationRef.current = creation;
    const keydown = event => {
      if (event.key === 'Escape') { creation.cancel(); onModeChange('none'); }
    };
    chart.subscribeClick(creation.click); chart.subscribeCrosshairMove(creation.move);
    window.addEventListener('keydown', keydown);
    return () => {
      chart.unsubscribeClick(creation.click); chart.unsubscribeCrosshairMove(creation.move);
      window.removeEventListener('keydown', keydown); creation.cancel();
      creationRef.current = null;
    };
  }, [manager, chart, series, mode, onModeChange, timeframe]);
  const focusDrawing = () => { manager.setHistoryFocus('drawing'); container.current?.focus({ preventScroll: true }); };
  return { ...snapshot, undo: () => { focusDrawing(); creationRef.current?.cancel(); onModeChange('none'); history.undo(); }, redo: () => { focusDrawing(); creationRef.current?.cancel(); onModeChange('none'); history.redo(); }, setProperties: (id, properties) => { focusDrawing(); manager.setProperties(id, properties); }, showHidden: () => {
    focusDrawing();
    const models = manager.getAll().map(model => ({ ...model, visible: true }));
    manager.replaceAll(models);
  } };
}
