import { utcTime } from './backtestAnalysis.js';
const cell = value => `"${String(value ?? '').replaceAll('"', '""')}"`;
const csv = (headers, rows) => '\uFEFF' + [headers, ...rows].map(row => row.map(cell).join(',')).join('\r\n') + '\r\n';
const timestamp = value => utcTime(value) ?? (value == null ? '' : `Invalid UTC timestamp: ${value}`);
export function exportExitRecords(trades) {
  return csv(['exit_id', 'position_id', 'side', 'order_type', 'entry', 'entry_utc', 'exit', 'exit_utc', 'size', 'initial_size', 'pnl_usd', 'commission', 'reason', 'tags', 'strategy', 'notes'],
    trades.map(source => { const row = source ?? {}; return [row.id, row.positionId, row.side, row.type, row.entry, timestamp(row.entryTime), row.exit, timestamp(row.exitTime), row.size, row.initialSize, row.pnl, row.commission, row.reason, row.tags, row.strategy, row.notes]; }));
}
export function exportCompletedPositions(analysis) {
  return csv(['position_id', 'status', 'side', 'entry', 'entry_utc', 'final_exit', 'final_exit_utc', 'initial_size', 'exited_size', 'exit_count', 'duration_seconds', 'pnl_usd', 'tags_by_exit', 'strategy_by_exit', 'notes_by_exit'],
    analysis.completedPositions.map(group => [group.positionId, group.status, group.side, group.entry, timestamp(group.entryTime), group.finalExit, timestamp(group.finalExitTime), group.initialSize, group.exitedSize, group.exits.length, group.duration, group.totalPnl,
      ...['tags', 'strategy', 'notes'].map(key => JSON.stringify(group.exits.map(exit => ({ exitId: exit.record.id, value: exit.record[key] ?? null }))))]));
}
export function downloadCsv(contents, filename) {
  const url = URL.createObjectURL(new Blob([contents], { type: 'text/csv;charset=utf-8' }));
  const link = document.createElement('a'); link.href = url; link.download = filename;
  document.body.append(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
