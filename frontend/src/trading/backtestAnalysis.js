// Read-only projections of the canonical paper account. No candle/history input.
export const PNL_EPSILON = 1e-8;
export const sizeTolerance = size => Math.max(1e-9, size * 1e-9);
const validId = value => typeof value === 'string' && value.trim().length > 0;
const positive = value => Number.isFinite(value) && value > 0;
export function utcTime(value) {
  if (!Number.isFinite(value)) return null;
  const date = new Date(value * 1000);
  return Number.isFinite(date.getTime()) ? date.toISOString() : null;
}

export function analyzeAccount({ initialBalance, balance, trades = [], positions = [] }) {
  const issues = [];
  const issue = (scope, message) => issues.push({ scope, message });
  const groups = new Map(), active = new Set(positions.map(item => item?.id).filter(validId));
  const unknownActive = positions.some(item => !validId(item?.id));
  if (unknownActive) issue('Account', 'An active position has no valid identity; completion cannot be established.');
  let realizedPnl = 0, running = Number.isFinite(initialBalance) ? initialBalance : null;
  let peak = running, maxDrawdown = running == null ? null : 0, maxDrawdownPercent = running > 0 ? 0 : null;
  const balanceEvents = [{ sequence: 0, balance: running, drawdown: running == null ? null : 0, drawdownPercent: running > 0 ? 0 : null }];
  if (running == null) issue('Account', 'Initial balance is not finite.');
  if (!Number.isFinite(balance)) issue('Account', 'Current balance is not finite.');
  const exitIds = new Map();
  for (const row of trades) if (validId(row?.id)) exitIds.set(row.id, (exitIds.get(row.id) ?? 0) + 1);
  for (const [index, source] of trades.entries()) {
    const row = source && typeof source === 'object' ? source : {};
    const scope = `Exit ${index + 1}`;
    const key = validId(row.positionId) ? `position:${row.positionId}` : `legacy:${index}`;
    if (!groups.has(key)) groups.set(key, { key, positionId: validId(row.positionId) ? row.positionId : null, exits: [], errors: [] });
    const group = groups.get(key);
    const error = message => { group.errors.push(message); issue(scope, message); };
    group.exits.push({ record: row, sequence: index + 1 });
    if (!group.positionId) error('Missing positionId; legacy exit remains ungrouped.');
    if (!validId(row.id) || exitIds.get(row.id) > 1) error('Missing or duplicate exit identity.');
    if (!positive(row.size) || !positive(row.initialSize)) error('Exited size / initialSize is missing or invalid.');
    if (!positive(row.entry) || !positive(row.exit)) error('Entry / exit price is missing or invalid.');
    if (!utcTime(row.entryTime) || !utcTime(row.exitTime)) error('Entry / exit UTC timestamp is missing or invalid.');
    else if (row.exitTime < row.entryTime) error('Exit precedes actual entry; duration is invalid.');
    if (!Number.isFinite(row.pnl)) {
      error('P&L is not finite; realized totals and the subsequent balance curve are unavailable.');
      realizedPnl = null; running = null; maxDrawdown = null; maxDrawdownPercent = null;
    } else {
      if (realizedPnl != null) realizedPnl += row.pnl;
      if (running != null) running += row.pnl;
      if ((realizedPnl != null && !Number.isFinite(realizedPnl)) || (running != null && !Number.isFinite(running))) {
        error('P&L accumulation overflow; totals are unavailable.');
        realizedPnl = null; running = null; maxDrawdown = null; maxDrawdownPercent = null;
      }
    }
    if (running != null) peak = Math.max(peak, running);
    const drawdown = running == null ? null : peak - running;
    const drawdownPercent = running != null && peak > 0 ? 100 * drawdown / peak : null;
    if (maxDrawdown != null) maxDrawdown = Math.max(maxDrawdown, drawdown);
    if (drawdownPercent != null && maxDrawdown != null) maxDrawdownPercent = Math.max(maxDrawdownPercent ?? 0, drawdownPercent);
    balanceEvents.push({ sequence: index + 1, time: utcTime(row.exitTime), balance: running, drawdown, drawdownPercent });
  }
  const projected = [...groups.values()].map(group => {
    const rows = group.exits.map(exit => exit.record), first = rows[0], last = rows.at(-1);
    const size = rows.every(row => positive(row.size)) ? rows.reduce((sum, row) => sum + row.size, 0) : null;
    const totalPnl = rows.every(row => Number.isFinite(row.pnl)) ? rows.reduce((sum, row) => sum + row.pnl, 0) : null;
    if (totalPnl != null && !Number.isFinite(totalPnl)) { group.errors.push('Position P&L overflow.'); issue(group.positionId ?? group.key, 'Position P&L overflow.'); }
    const remaining = positions.find(position => position?.id === group.positionId)?.size;
    if (active.has(group.positionId) && (size == null || !positive(remaining) || !positive(first.initialSize) || Math.abs(size + remaining - first.initialSize) > sizeTolerance(first.initialSize))) {
      group.errors.push('Exited plus remaining size does not match initialSize.'); issue(group.positionId, 'Exited plus remaining size does not match initialSize.');
    }
    if (rows.some(row => row.initialSize !== first.initialSize || row.entry !== first.entry || row.entryTime !== first.entryTime || row.side !== first.side)) {
      group.errors.push('Inconsistent original position fields.'); issue(group.positionId ?? group.key, 'Inconsistent original position fields.');
    }
    if (rows.some((row, index) => index > 0 && row.exitTime < rows[index - 1].exitTime)) {
      group.errors.push('Exit timestamps are out of recorded order.'); issue(group.positionId ?? group.key, 'Exit timestamps are out of recorded order.');
    }
    if (size != null && positive(first.initialSize) && Math.abs(size - first.initialSize) > sizeTolerance(first.initialSize) && !active.has(group.positionId)) {
      group.errors.push('Total exited size does not match initialSize.'); issue(group.positionId ?? group.key, 'Total exited size does not match initialSize.');
    }
    if (size != null && positive(first.initialSize) && size > first.initialSize + sizeTolerance(first.initialSize)) {
      group.errors.push('Exited size exceeds initialSize.'); issue(group.positionId ?? group.key, 'Exited size exceeds initialSize.');
    }
    const complete = Boolean(group.positionId && !unknownActive && !active.has(group.positionId) && !group.errors.length && Number.isFinite(totalPnl) && size != null && Math.abs(size - first.initialSize) <= sizeTolerance(first.initialSize));
    const duration = utcTime(first.entryTime) && utcTime(last.exitTime) && last.exitTime >= first.entryTime ? last.exitTime - first.entryTime : null;
    return { ...group, status: complete ? 'Completed' : group.errors.length || unknownActive ? 'Incomplete / data issue' : 'Open / partial', entry: first.entry, entryTime: first.entryTime, finalExit: last.exit, finalExitTime: last.exitTime, side: first.side, initialSize: first.initialSize, exitedSize: size, totalPnl: Number.isFinite(totalPnl) ? totalPnl : null, duration };
  });
  const completedPositions = projected.filter(group => group.status === 'Completed');
  const winners = completedPositions.filter(group => group.totalPnl > PNL_EPSILON).length;
  const losers = completedPositions.filter(group => group.totalPnl < -PNL_EPSILON).length;
  // Gross totals use signed P&L, including tiny canonical amounts classified as BE.
  const grossProfit = completedPositions.reduce((sum, group) => sum + Math.max(0, group.totalPnl), 0);
  const grossLoss = completedPositions.reduce((sum, group) => sum + Math.max(0, -group.totalPnl), 0);
  const n = completedPositions.length, final = balanceEvents.at(-1);
  const reconciliationTolerance = Number.isFinite(balance) && Number.isFinite(initialBalance) && realizedPnl != null
    ? Math.max(PNL_EPSILON, Number.EPSILON * Math.max(1, Math.abs(balance), Math.abs(initialBalance), Math.abs(realizedPnl)) * Math.max(1, trades.length) * 8) : null;
  const difference = realizedPnl != null && Number.isFinite(balance) && Number.isFinite(initialBalance) ? balance - initialBalance - realizedPnl : null;
  const reconciled = difference != null && Math.abs(difference) <= reconciliationTolerance;
  if (!reconciled) issue('Account', difference == null ? 'Balance reconciliation is unavailable.' : 'Exit P&L does not reconcile with balance minus initial balance.');
  return { groups: projected, completedPositions, issues, balanceEvents, reconciliation: { reconciled, difference, tolerance: reconciliationTolerance }, summary: {
    completed: n, winners, losers, breakEven: n - winners - losers, exitRecords: trades.length, realizedPnl,
    winRate: n ? 100 * winners / n : null, grossProfit, grossLoss,
    averageWin: winners ? grossProfit / winners : null, averageLoss: losers ? grossLoss / losers : null,
    expectancy: n ? completedPositions.reduce((sum, group) => sum + group.totalPnl, 0) / n : null,
    profitFactor: grossLoss ? grossProfit / grossLoss : grossProfit ? Infinity : null,
    drawdown: final.drawdown, drawdownPercent: final.drawdownPercent, maxDrawdown, maxDrawdownPercent,
  } };
}
