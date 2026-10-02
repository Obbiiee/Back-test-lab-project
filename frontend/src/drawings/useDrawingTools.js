import { useEffect, useRef, useState } from 'react';
import { DrawingManager } from './DrawingManager.js';
import { TrendLineCreation } from './TrendLineCreation.js';
import { TREND_LINE } from './DrawingTypes.js';

// React integration is outside the manager/domain. Pointer previews update only
// the primitive; React receives completed objects and draft start/cancel events.
export default function useDrawingTools({ chart, series, candles, mode, onModeChange, timeframe }) {
  const [manager] = useState(() => new DrawingManager());
  const creationRef = useRef(null);
  const [snapshot, setSnapshot] = useState({ objects: [], draftActive: false });
  useEffect(() => manager.subscribe((objects, draftActive) => setSnapshot({ objects, draftActive })), [manager]);
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
    if (!chart || !series || mode !== TREND_LINE) return;
    const creation = new TrendLineCreation(manager, chart, series, manager.bars, timeframe, () => onModeChange('none'));
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
  return snapshot;
}
