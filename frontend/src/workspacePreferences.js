import {instanceConfig} from './indicators/indicatorValidation.js';

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

// Research presentation only. Session identity isolates this from v1, drawings,
// market data and financial state; unknown bytes and other-tab edits survive.
export class IndicatorPreferences {
  writable = false;
  status = '';
  constructor(storage, workspace, registry) {
    this.storage = storage; this.workspace = workspace; this.registry = registry;
    this.key = 'backtest-indicators-v1:' + encodeURIComponent(workspace);
  }
  access() { return typeof this.storage === 'function' ? this.storage() : this.storage; }
  normalize(value) {
    if (!Array.isArray(value) || value.length > 16) throw Error('Indicator limit');
    const configs = value.map(item => {
      if (typeof item?.id !== 'string' || item.id.length > 128) throw Error('Indicator identity');
      return instanceConfig(this.registry, item);
    });
    if (new Set(configs.map(item => item.id)).size !== configs.length) throw Error('Duplicate indicator');
    return configs;
  }
  load() {
    this.writable = false;
    try {
      this.raw = this.access().getItem(this.key);
      let instances = [];
      if (this.raw !== null) {
        if (typeof this.raw !== 'string' || this.raw.length > 32768) throw Error('Preference size');
        const document = JSON.parse(this.raw);
        if (!document || document.version !== 1 || document.workspace !== this.workspace ||
          Object.keys(document).some(key => !['version','workspace','instances'].includes(key))) throw Error('Unsupported preferences');
        instances = this.normalize(document.instances);
      }
      this.writable = true; this.status = ''; return instances;
    } catch {
      this.status = 'Stored indicators are unavailable or unsupported. Original data is preserved; changes stay in memory.';
      return [];
    }
  }
  save(instances) {
    if (!this.writable) return false;
    try {
      const next = JSON.stringify({version:1,workspace:this.workspace,instances:this.normalize(instances)});
      if (next.length > 32768) throw Error('Preference size');
      if (this.access().getItem(this.key) !== this.raw) {
        this.writable = false;
        this.status = 'Indicators changed in another tab. Original data is preserved; reload to use that version.';
        return false;
      }
      this.access().setItem(this.key, next); this.raw = next; this.status = ''; return true;
    } catch {
      this.status = 'Indicator save failed; changes stay in memory.'; return false;
    }
  }
}
