import { useEffect, useRef, useState } from 'react';
export const panelBounds = viewportHeight => ({ min: 95, max: Math.max(95, viewportHeight - 328) });
export const clampPanel = (height, viewportHeight) => Math.max(95, Math.min(panelBounds(viewportHeight).max, height));
export default function usePanelResize(initialHeight = 150) {
  const [height, setHeight] = useState(() => clampPanel(initialHeight, window.innerHeight));
  const cleanup = useRef(() => {});
  useEffect(() => {
    const resize = () => setHeight(current => clampPanel(current, window.innerHeight));
    window.addEventListener('resize', resize);
    return () => { window.removeEventListener('resize', resize); cleanup.current(); };
  }, []);
  const start = event => {
    if (event.button !== 0) return;
    event.preventDefault(); cleanup.current();
    const startY = event.clientY, startHeight = height;
    const move = point => setHeight(clampPanel(startHeight + startY - point.clientY, window.innerHeight));
    const end = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', end); window.removeEventListener('pointercancel', end); window.removeEventListener('blur', end); cleanup.current = () => {}; };
    cleanup.current = end;
    window.addEventListener('pointermove', move); window.addEventListener('pointerup', end); window.addEventListener('pointercancel', end); window.addEventListener('blur', end);
  };
  const keyDown = event => {
    const bounds = panelBounds(window.innerHeight), step = event.shiftKey ? 50 : 10;
    if (!['ArrowUp', 'ArrowDown', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    setHeight(current => clampPanel(event.key === 'Home' ? bounds.min : event.key === 'End' ? bounds.max : current + (event.key === 'ArrowUp' ? step : -step), window.innerHeight));
  };
  return { height, start, keyDown, ...panelBounds(window.innerHeight) };
}
