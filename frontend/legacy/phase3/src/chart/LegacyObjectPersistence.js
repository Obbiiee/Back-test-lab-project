// Keep the original timeframe/mode namespace and schema during trading separation.
// Unknown/invalid objects are retained verbatim, rather than silently discarded.
export class LegacyObjectPersistence {
  key = null;
  preserved = [];
  writable = false;

  load(storage, key, accepts) {
    this.key = key; this.preserved = []; this.writable = false;
    if (!key) return [];
    try {
      storage = typeof storage === 'function' ? storage() : storage;
      const raw = storage.getItem(key);
      const parsed = raw == null ? [] : JSON.parse(raw);
      if (!Array.isArray(parsed)) return [];
      const backupKey = key + ':before-trading-separation';
      if (raw != null && storage.getItem(backupKey) == null) storage.setItem(backupKey, raw);
      this.preserved = parsed.filter(object => !accepts(object));
      this.writable = true;
      return parsed.filter(accepts);
    } catch { return []; }
  }

  save(storage, key, objects) {
    if (!key || key !== this.key || !this.writable) return false;
    try {
      storage = typeof storage === 'function' ? storage() : storage;
      storage.setItem(key, JSON.stringify([...objects, ...this.preserved]));
      return true;
    } catch { return false; }
  }
}
