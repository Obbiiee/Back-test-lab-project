import { memo, useState } from 'react';
import { money } from './format';
import { utcTime } from './backtestAnalysis';
import { downloadCsv, exportCompletedPositions, exportExitRecords } from './backtestExport';
const cash = value => Number.isFinite(value) ? money(value) : '—';
const number = value => value === Infinity ? '∞' : Number.isFinite(value) ? value.toFixed(2) : '—';
const percent = value => Number.isFinite(value) ? `${value.toFixed(2)}%` : '—';
const time = value => utcTime(value)?.replace('T', ' ') ?? 'Unavailable';
function BalanceCurve({ events }) {
  const valid = events.every(event => Number.isFinite(event.balance));
  if (!valid) return <p>Balance curve unavailable: inspect data issues.</p>;
  const low = events.reduce((value, event) => Math.min(value, event.balance), Infinity), high = events.reduce((value, event) => Math.max(value, event.balance), -Infinity), range = high - low || 1;
  const points = events.map((event, index) => `${35 + 720 * index / Math.max(1, events.length - 1)},${20 + 95 * (high - event.balance) / range}`).join(' ');
  return <figure className="analysis-curve"><figcaption>Realized balance curve · USD · exit sequence</figcaption>
    <svg viewBox="0 0 790 145" role="img" aria-label={`Realized balance after ${events.length - 1} exit records`}><title>Balance after each recorded exit; excludes floating P&amp;L</title><path d="M35 15V120H755" fill="none" stroke="currentColor" opacity=".3"/><polyline points={points} fill="none" stroke="#39b9a4" strokeWidth="2"/><text x="35" y="140">0 · initial</text><text x="755" y="140" textAnchor="end">{events.length - 1} · exits</text></svg>
    <small>{cash(events[0].balance)} initial → {cash(events.at(-1).balance)} final. Intrabar/floating equity is not represented.</small></figure>;
}
function BacktestAnalysis({ trades, analysis, onNotes }) {
  const [selected, setSelected] = useState(null), [exportError, setExportError] = useState('');
  const s = analysis.summary, detail = analysis.groups.find(group => group.key === selected);
  const save = (contents, name) => { try { downloadCsv(contents, name); setExportError(''); } catch { setExportError('CSV download unavailable. Your account has not changed.'); } };
  const stats = [['Completed positions', s.completed], ['Winners', s.winners], ['Losers', s.losers], ['Break-even', s.breakEven], ['Realized P&L · all exits', cash(s.realizedPnl)], ['Win rate · completed', percent(s.winRate)], ['Average win', cash(s.averageWin)], ['Average loss', cash(s.averageLoss)], ['Expectancy · USD / position', cash(s.expectancy)], ['Profit factor', number(s.profitFactor)], ['Current balance drawdown', cash(s.drawdown)], ['Current drawdown %', percent(s.drawdownPercent)], ['Max balance drawdown', cash(s.maxDrawdown)], ['Max drawdown %', percent(s.maxDrawdownPercent)]];
  return <div className="backtest-analysis" aria-label="Backtest Analysis">
    <div className="analysis-actions"><strong>Current paper account · USD</strong><button onClick={()=>save(exportExitRecords(trades), 'backtest-exit-records.csv')}>Export exit records CSV</button><button onClick={()=>save(exportCompletedPositions(analysis), 'backtest-completed-positions.csv')}>Export completed positions CSV</button></div>
    <p className="analysis-caption">{s.exitRecords} exit records ≠ {s.completed} completed positions. Open-position partial profits contribute to realized P&amp;L; win rate uses completed positions only. Execution costs follow the existing simulator.</p>
    {exportError&&<p role="alert">{exportError}</p>}
    <dl className="analysis-stats">{stats.map(([label, value])=><div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
    <p className="analysis-reconciliation">{analysis.reconciliation.reconciled ? 'Reconciled: exit P&L = balance − initial balance.' : 'Balance reconciliation failed or unavailable.'}</p>
    {analysis.issues.length>0&&<details className="analysis-issues" open><summary>Data issues ({analysis.issues.length})</summary><ul>{analysis.issues.map((issue, index)=><li key={index}>{issue.scope}: {issue.message}</li>)}</ul></details>}
    <BalanceCurve events={analysis.balanceEvents}/>
    <h3>Completed positions and partial / incomplete records</h3>
    {!analysis.groups.length&&<p>No exit records yet.</p>}
    <div className="analysis-position-list">{analysis.groups.slice().reverse().map(group=><button key={group.key} aria-pressed={selected===group.key} onClick={()=>setSelected(group.key)}><span>{group.side??'Unknown side'} · {group.status} · {group.exits.length} exit(s)</span><strong>{cash(group.totalPnl)}</strong></button>)}</div>
    {detail&&<section className="analysis-detail" aria-label="Position detail"><h3>{detail.side??'Unknown side'} · {detail.status}</h3><p>Entry {detail.entry??'Unavailable'} · {time(detail.entryTime)} · Original size {detail.initialSize??'Unavailable'}</p><p>Last recorded exit {detail.finalExit??'Unavailable'} · {time(detail.finalExitTime)} · {detail.status==='Completed'?'Duration':'Recorded elapsed time'} {detail.duration==null?'Unavailable':`${detail.duration} seconds`} · Total {cash(detail.totalPnl)}</p>
      {detail.exits.map((exit, index)=><div className="analysis-exit" key={exit.sequence}><strong>{detail.status==='Completed'&&index===detail.exits.length-1?'Final exit':'Exit'} {index+1} · {exit.record.reason??'Unknown reason'}</strong><span>{time(exit.record.exitTime)} · Price {exit.record.exit??'Unavailable'} · Size {exit.record.size??'Unavailable'} · {cash(exit.record.pnl)}</span><span>Tags: {exit.record.tags??'Unavailable'} · Strategy: {exit.record.strategy??'Unavailable'}</span><label>Journal notes for exit {index+1}<textarea aria-label={`Journal notes for exit ${index+1}`} value={exit.record.notes??''} disabled={typeof exit.record.id!=='string'||detail.errors.some(error=>error.includes('identity'))} onChange={event=>onNotes(exit.record.id,event.target.value)}/></label></div>)}
    </section>}
  </div>;
}
export default memo(BacktestAnalysis);
