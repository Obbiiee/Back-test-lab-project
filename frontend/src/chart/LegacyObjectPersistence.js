// Keep the original timeframe/mode namespace and schema during trading separation.
// Unknown/invalid objects are retained verbatim, rather than silently discarded.
export class LegacyObjectPersistence {
  key = null;
  preserved = [];
  writable = false;
  records = [];
  accepts = () => false;
  serialized = '[]';

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
      this.records = parsed;
      this.accepts = accepts;
      this.serialized = JSON.stringify(parsed);
      this.writable = true;
      return parsed.filter(accepts);
    } catch { return []; }
  }

  save(storage, key, objects) {
    if (!key || key !== this.key || !this.writable) return false;
    try {
      storage = typeof storage === 'function' ? storage() : storage;
      // Replace only accepted trading slots. Retired/unknown records keep their
      // original order and fields, even when all active objects are deleted.
      const remaining = [...objects];
      const merged = this.records.flatMap(record => {
        if (!this.accepts(record)) return [record];
        const index = remaining.findIndex(object => object.id === record.id);
        return index < 0 ? [] : remaining.splice(index, 1);
      });
      merged.push(...remaining);
      const serialized = JSON.stringify(merged);
      // A load/reload must preserve the exact original bytes, including spacing.
      if (serialized === this.serialized) return true;
      storage.setItem(key, serialized);
      this.records = merged;
      this.serialized = serialized;
      return true;
    } catch { return false; }
  }
}
