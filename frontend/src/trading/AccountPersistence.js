import { initialAccount } from './simulator.js';
export const ACCOUNT_KEY = 'backtest-paper-account-v1';
const record = value => value && typeof value === 'object' && !Array.isArray(value);
// Validate storage safety, not financial interpretation. Incomplete legacy trade
// evidence still belongs to the existing analysis quality checks; valid bytes are
// returned unchanged, including unknown metadata, notes and partial-exit identity.
export function validateStoredAccount(account) {
  if (!record(account) || !Number.isFinite(account.balance) || (account.schemaVersion != null && account.schemaVersion !== 1)) throw Error('Unsupported account record.');
  for (const field of ['initialBalance', 'lastTime']) if (account[field] != null && !Number.isFinite(account[field])) throw Error('Invalid account numeric field.');
  for (const key of ['orders', 'positions', 'trades']) {
    const rows = account[key];
    if (!Array.isArray(rows) || rows.length > 50000) throw Error('Invalid or oversized account collection.');
    const ids = new Set();
    for (const row of rows) {
      if (!record(row) || !Number.isFinite(row.size)) throw Error('Invalid account row or size.');
      if (key !== 'trades') {
        if (!((typeof row.id === 'string' && row.id.length > 0) || Number.isFinite(row.id)) || ids.has(row.id) || !['Buy', 'Sell'].includes(row.side) || !['Market', 'Limit', 'Stop'].includes(row.type) || !Number.isFinite(row.entry) || row.entry <= 0 || row.size <= 0) throw Error('Invalid active order/position.');
        ids.add(row.id);
        if (row.partials != null && (!Array.isArray(row.partials) || row.partials.length > 100 || row.partials.some(item => !record(item) || !Number.isFinite(item.price) || !Number.isFinite(item.percent)))) throw Error('Invalid partial targets.');
      }
      for (const field of ['entry', 'exit', 'sl', 'tp', 'pnl', 'commission', 'initialSize', 'entryTime', 'exitTime', 'placedTime']) if (row[field] != null && !Number.isFinite(row[field])) throw Error('Invalid account row number.');
      if (row.notes != null && typeof row.notes !== 'string') throw Error('Invalid journal text.');
      for (const field of ['id', 'positionId']) if (row[field] != null && typeof row[field] !== 'string' && !Number.isFinite(row[field])) throw Error('Invalid account identity.');
      for (const field of ['side', 'type', 'reason']) if (row[field] != null && typeof row[field] !== 'string') throw Error('Invalid account row text.');
      for (const field of ['tags', 'strategy']) if (row[field] != null && typeof row[field] !== 'string' && !(Array.isArray(row[field]) && row[field].every(value => typeof value === 'string'))) throw Error('Invalid research metadata text.');
    }
  }
  return account;
}
export class AccountPersistence {
  constructor(storage = () => globalThis.localStorage) { this.storage = storage; this.writable = true; this.status = ''; this.listeners = new Set(); this.savedBytes = null; }
  access() { return typeof this.storage === 'function' ? this.storage() : this.storage; }
  subscribe = listener => { this.listeners.add(listener); return () => this.listeners.delete(listener); };
  snapshot = () => this.status;
  report(status) { if (this.status === status) return; this.status = status; for (const listener of this.listeners) listener(); }
  load() {
    try {
      const raw = this.access().getItem(ACCOUNT_KEY);
      this.savedBytes = raw;
      if (raw === null) return initialAccount();
      if (typeof raw !== 'string' || raw.length > 8 * 1024 * 1024) throw Error('Account exceeds local read limit.');
      return validateStoredAccount(JSON.parse(raw));
    } catch {
      this.writable = false;
      this.report('Stored account is unavailable, malformed or unsupported. Original data is preserved; this session uses a temporary account and changes stay in memory.');
      return initialAccount();
    }
  }
  save(account) {
    if (!this.writable) return false;
    try {
      validateStoredAccount(account);
      const storage = this.access();
      if (storage.getItem(ACCOUNT_KEY) !== this.savedBytes) { this.writable = false; this.report('Stored account changed outside this workspace. Changes here stay in memory; reload to adopt the stored account.'); return false; }
      const raw = JSON.stringify(account);
      if (raw.length > 8 * 1024 * 1024) throw Error('Account exceeds local save limit.');
      storage.setItem(ACCOUNT_KEY, raw); this.savedBytes = raw; this.report(''); return true;
    }
    catch { this.report('Account could not be saved. Changes remain in memory; stored data was not replaced. Keep this tab open and retry after restoring browser storage.'); return false; }
  }
}
