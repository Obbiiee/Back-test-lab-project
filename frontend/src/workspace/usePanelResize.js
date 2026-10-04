import { useEffect, useRef, useState } from 'react';
export const COLLAPSED_HEIGHT = 24;
export const COMPACT_HEIGHT = 144;
export const panelBounds = (viewportHeight, viewportWidth = 1280) => ({ min: COLLAPSED_HEIGHT, max: Math.max(COMPACT_HEIGHT, viewportHeight - (viewportWidth <= 720 ? 356 : 328)) });
export const clampPanel = (height, viewportHeight, viewportWidth = 1280) => {
  const value = Number.isFinite(height) ? height : COMPACT_HEIGHT;
  return value <= (COLLAPSED_HEIGHT + COMPACT_HEIGHT) / 2 ? COLLAPSED_HEIGHT
    : Math.max(COMPACT_HEIGHT, Math.min(panelBounds(viewportHeight, viewportWidth).max, value));
};
export const panelState = height => height === COLLAPSED_HEIGHT ? 'COLLAPSED' : height <= COMPACT_HEIGHT ? 'COMPACT' : 'EXPANDED';
export const keyboardPanelHeight = (height, key, shift, viewportHeight, viewportWidth = 1280, restoreHeight = 150) => {
  const bounds = panelBounds(viewportHeight, viewportWidth), step = shift ? 50 : 10;
  const next = key === 'Home' ? bounds.min : key === 'End' ? bounds.max
    : key === 'Enter' || key === ' ' ? height === bounds.min ? restoreHeight : bounds.min
    : key === 'ArrowUp' ? height === bounds.min ? COMPACT_HEIGHT : height + step
    : key === 'ArrowDown' ? height <= COMPACT_HEIGHT ? bounds.min : Math.max(COMPACT_HEIGHT, height - step)
    : height;
  return clampPanel(next, viewportHeight, viewportWidth);
};
export default function usePanelResize(initialHeight = 150) {
  const [height, setHeight] = useState(() => clampPanel(initialHeight, window.innerHeight, window.innerWidth));
  const cleanup = useRef(() => {});
  const restoreHeight = useRef(initialHeight);
  useEffect(() => { if (height > COLLAPSED_HEIGHT) restoreHeight.current = height; }, [height]);
  useEffect(() => {
    const resize = () => setHeight(current => clampPanel(current, window.innerHeight, window.innerWidth));
    window.addEventListener('resize', resize);
    return () => { window.removeEventListener('resize', resize); cleanup.current(); };
  }, []);
  const start = event => {
    if (event.button !== 0) return;
    event.preventDefault(); event.currentTarget.focus(); cleanup.current();
    const startY = event.clientY, startHeight = height;
    const move = point => setHeight(clampPanel(startHeight + startY - point.clientY, window.innerHeight, window.innerWidth));
    const end = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', end); window.removeEventListener('pointercancel', end); window.removeEventListener('blur', end); cleanup.current = () => {}; };
    cleanup.current = end;
    window.addEventListener('pointermove', move); window.addEventListener('pointerup', end); window.addEventListener('pointercancel', end); window.addEventListener('blur', end);
  };
  const keyDown = event => {
    if (!['ArrowUp', 'ArrowDown', 'Home', 'End', 'Enter', ' '].includes(event.key)) return;
    event.preventDefault();
    setHeight(current => keyboardPanelHeight(current, event.key, event.shiftKey, window.innerHeight, window.innerWidth, restoreHeight.current));
  };
  const restore = () => setHeight(clampPanel(restoreHeight.current, window.innerHeight, window.innerWidth));
  return { height, state: panelState(height), start, keyDown, restore, ...panelBounds(window.innerHeight, window.innerWidth) };
}
