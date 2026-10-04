import { memo, useContext, useMemo } from 'react';
import { NewsContext } from './NewsContext.js';
import { contextAt } from './researchContext.js';
function TradeNewsContext({ detail }) {
  const news = useContext(NewsContext);
  const index = news?.index, filters = news?.filters, window = news?.window;
  const eligibleThrough = Number.isFinite(news?.cursor) ? Math.min(news.cursor, detail.finalExitTime ?? detail.entryTime) : null;
  const rows = useMemo(() => {
    if (!index) return [];
    return [{ label: 'Entry', time: detail.entryTime }, ...detail.exits.map((exit, i) => ({ label: `Exit ${i + 1}`, time: exit.record.exitTime }))].map(row => ({ ...row, context: contextAt(index, row.time, eligibleThrough, filters, window) }));
  }, [index, detail, eligibleThrough, filters, window]);
  if (!news?.index) return <p>News context unavailable: import an economic-event dataset from News.</p>;
  return <section aria-label="Derived news context"><h4>News context · strict as-of entry / exit</h4><small>Derived only · dataset {news.identity} · query v{news.queryVersion} · window v{news.window.version} SHA-256 {news.windowHash} · {JSON.stringify(news.window)}. Financial results and CSV are unchanged.</small>{rows.map((row, i) => <div key={i}><strong>{row.label} · coverage {row.context.status}</strong>{row.context.matches.length ? <ul>{row.context.matches.map(event => <li key={event.occurrenceId}>{event.fields.name?.value ?? 'Name unavailable'} · {event.fields.currency?.value ?? 'Unknown currency'} · {event.fields.category?.value ?? 'Unknown category'} · {event.fields.impact?.value ?? 'Unknown impact'} · {event.window} · {event.delta}s · {event.occurrenceId}{event.occurrenceId === row.context.nearest?.occurrenceId ? ' · nearest within window' : ''}</li>)}</ul> : <p>{row.context.status === 'complete' ? 'No matching eligible events in this window.' : 'No matches; news coverage is incomplete or unknown.'}</p>}</div>)}</section>;
}
export default memo(TradeNewsContext);
