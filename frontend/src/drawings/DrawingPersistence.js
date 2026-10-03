import { TEXT } from './DrawingTypes.js';
export const DRAWING_STORAGE_PREFIX = 'backtest-drawing-manager-v1:';
const allowedKeys = (value, keys) => value && typeof value === 'object' && !Array.isArray(value) && Object.keys(value).every(key => keys.includes(key));
function understood(record) {
  return allowedKeys(record, ['id','type','points','options','visible','locked','metadata', ...(record.type === TEXT ? ['text'] : [])]) &&
    Array.isArray(record.points) && record.points.every(point => allowedKeys(point,['time','price'])) &&
    allowedKeys(record.options,['color','lineWidth']) && allowedKeys(record.metadata,['createdOnTimeframe']) &&
    typeof record.options.color === 'string' && Number.isFinite(record.options.lineWidth) &&
    (record.metadata.createdOnTimeframe === undefined || typeof record.metadata.createdOnTimeframe === 'string') &&
    typeof record.visible === 'boolean' && typeof record.locked === 'boolean';
}
// Separate adapter; never reads or writes legacy keys. Invalid/future data is
// preserved byte-for-byte by making that namespace read-only for this lifetime.
export class DrawingPersistence {
  writable = false;
  status = '';
  constructor(storage, workspace) {
    this.storage = storage; this.workspace = workspace;
    this.key = DRAWING_STORAGE_PREFIX + encodeURIComponent(workspace);
  }
  access() { return typeof this.storage === 'function' ? this.storage() : this.storage; }
  load(registry) {
    this.registry = registry;
    this.writable = false; this.status = '';
    try {
      const raw = this.access().getItem(this.key);
      if (raw == null) { this.writable = true; return []; }
      const parsed = JSON.parse(raw);
      if (!allowedKeys(parsed,['version','workspace','drawings']) || parsed.version !== 1 || parsed.workspace !== this.workspace || !Array.isArray(parsed.drawings)) throw new Error('Unsupported drawing document');
      const models = [], ids = new Set(); let damaged = false;
      for (const record of parsed.drawings) {
        try {
          if (!understood(record)) throw new Error('Unknown or malformed fields');
          const model = registry.get(record.type).model(record);
          if (ids.has(model.id)) throw new Error('Duplicate id');
          ids.add(model.id); models.push(model);
        } catch { damaged = true; }
      }
      this.writable = !damaged;
      if (damaged) this.status = 'Drawing storage contains unsupported records; valid drawings restored. Changes remain in memory to preserve the original data.';
      return models;
    } catch {
      this.status = 'Drawing storage unavailable or invalid; changes remain in memory. Original data preserved.';
      return [];
    }
  }
  save(models) {
    if (!this.writable) return false;
    try {
      const canonical = models.map(model => this.registry.get(model.type).model(model));
      this.access().setItem(this.key, JSON.stringify({ version: 1, workspace: this.workspace, drawings: canonical }));
      this.status = ''; return true;
    } catch { this.status = 'Drawing save failed; changes remain in memory.'; return false; }
  }
}
