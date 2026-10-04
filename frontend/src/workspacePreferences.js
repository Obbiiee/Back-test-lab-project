export const FAVORITES_KEY = 'backtest-favorites-v1';
export const DEFAULT_FAVORITES = Object.freeze(['Trend Line', 'Long Position', 'Short Position']);
export function readFavorites(storage = () => globalThis.localStorage) {
  try {
    const raw = (typeof storage === 'function' ? storage() : storage).getItem(FAVORITES_KEY);
    if (raw === null) return { value: [...DEFAULT_FAVORITES], writable: true, status: '' };
    if (typeof raw !== 'string' || raw.length > 32768) throw Error('Oversized preferences');
    const value = JSON.parse(raw);
    if (!Array.isArray(value) || value.length > 256 || value.some(name => typeof name !== 'string' || !name.trim() || name.length > 128) || new Set(value).size !== value.length) throw Error('Invalid favorites');
    return { value, writable: true, status: '' };
  } catch {
    return { value: [...DEFAULT_FAVORITES], writable: false, status: 'Stored favorite tools are unavailable or invalid. Original preferences are preserved; changes stay in memory.' };
  }
}
