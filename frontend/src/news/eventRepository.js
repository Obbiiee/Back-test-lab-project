import { importDataset } from './eventValidation.js';
import { EventIndex } from './eventIndex.js';
import { validateWindow, DEFAULT_WINDOW } from './researchContext.js';
import { DEFAULT_FILTERS } from './eventIndex.js';
const requestResult = request => new Promise((resolve, reject) => { request.onsuccess = () => resolve(request.result); request.onerror = () => reject(request.error); });
const transactionDone = tx => new Promise((resolve, reject) => { tx.oncomplete = resolve; tx.onerror = () => reject(tx.error ?? new Error('News transaction failed.')); tx.onabort = () => reject(tx.error ?? new Error('News transaction aborted.')); });
export function validatePreferences(value) {
  const filters = value?.filters ?? DEFAULT_FILTERS;
  if (!filters || !['currency', 'impact', 'category'].every(key => typeof filters[key] === 'string' && filters[key].length > 0 && filters[key].length <= 128) || !['All', 'High', 'Medium', 'Low', 'Unknown'].includes(filters.impact) || !/^(All|Unknown|[A-Z]{3})$/.test(filters.currency)) throw new Error('Invalid news filter preferences.');
  return { filters: { currency: filters.currency, impact: filters.impact, category: filters.category }, window: validateWindow(value?.window ?? DEFAULT_WINDOW) };
}
export class NewsRepository {
  constructor(factory = globalThis.indexedDB, name = 'backtest-economic-news-v1') { this.factory = factory; this.name = name; }
  async open() {
    if (!this.factory) throw new Error('IndexedDB unavailable. Your existing account is unchanged.');
    return new Promise((resolve, reject) => {
      const request = this.factory.open(this.name, 1); let blocked = false;
      request.onupgradeneeded = () => { const db = request.result; db.createObjectStore('datasets'); db.createObjectStore('settings'); };
      request.onsuccess = () => { const db = request.result; if (blocked) { db.close(); return; } db.onversionchange = () => db.close(); resolve(db); };
      request.onerror = () => reject(request.error ?? new Error('News storage unavailable.'));
      request.onblocked = () => { blocked = true; reject(new Error('News storage blocked by another tab. Close that tab and retry; no dataset was replaced.')); };
    });
  }
  async load({ previous = false } = {}) {
    const db = await this.open();
    try {
      const tx = db.transaction(['datasets', 'settings'], 'readonly'), done = transactionDone(tx);
      // Attach immediately: an early request failure must not leave an unhandled transaction rejection.
      done.catch(() => {});
      const settings = tx.objectStore('settings');
      const pointer = await requestResult(settings.get(previous ? 'previous' : 'active'));
      const record = pointer ? await requestResult(tx.objectStore('datasets').get(pointer)) : null;
      const prefs = await requestResult(settings.get('preferences'));
      await done;
      let preferences, preferenceError = '';
      try { preferences = validatePreferences(prefs); } catch (error) { preferences = validatePreferences(null); preferenceError = error.message + ' Stored preference bytes were preserved.'; }
      if (!pointer) return { record: null, preferences, preferenceError };
      if (!record || record.schemaVersion !== 1 || typeof record.raw !== 'string') throw new Error('Stored news dataset is missing or unsupported. Records preserved; restore previous or reimport.');
      const imported = await importDataset(record.raw);
      if (record.hash !== imported.hash || record.sourceHash !== imported.sourceHash) throw new Error('Stored news hash mismatch. Records preserved; restore previous or reimport.');
      return { record: { ...imported, raw: record.raw, key: pointer, index: new EventIndex(imported.dataset) }, preferences, preferenceError };
    } finally { db.close(); }
  }
  async replace(raw) {
    const imported = await importDataset(raw), index = new EventIndex(imported.dataset);
    const key = JSON.stringify([imported.dataset.datasetId, imported.dataset.version]);
    const record = { schemaVersion: 1, hash: imported.hash, sourceHash: imported.sourceHash, raw };
    const db = await this.open();
    try {
      const tx = db.transaction(['datasets', 'settings'], 'readwrite'), done = transactionDone(tx);
      const store = tx.objectStore('datasets'), settings = tx.objectStore('settings');
      const existingRequest = store.get(key), activeRequest = settings.get('active');
      existingRequest.onsuccess = () => {
        if (existingRequest.result && existingRequest.result.hash !== record.hash) { tx.abort(); return; }
        store.put(record, key);
      };
      activeRequest.onsuccess = () => { if (activeRequest.result && activeRequest.result !== key) settings.put(activeRequest.result, 'previous'); settings.put(key, 'active'); };
      try { await done; } catch (error) { throw new Error(`News dataset not replaced: ${error.message}. Check reused dataset ID/version, available storage and other tabs.`, { cause: error }); }
      return { ...imported, raw, key, index };
    } finally { db.close(); }
  }
  async restorePrevious() {
    const loaded = await this.load({ previous: true });
    if (!loaded.record) throw new Error('No previous valid news dataset is available. Reimport your source file.');
    // Revalidate bytes before replacement. A competing dataset write remains atomic.
    return this.replace(loaded.record.raw);
  }
  async savePreferences(value) {
    const preferences = validatePreferences(value), db = await this.open();
    try { const tx = db.transaction('settings', 'readwrite'), done = transactionDone(tx); tx.objectStore('settings').put(preferences, 'preferences'); await done; }
    finally { db.close(); }
  }
}
