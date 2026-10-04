import { useState } from 'react';
import { NEWS_FIELDS } from './eventValidation.js';
const stamp = time => Number.isFinite(time) ? new Date(time * 1000).toISOString() : String(time ?? 'Unavailable');
function PreferenceForm({ news }) {
  const [filters, setFilters] = useState(news.preferences.filters), [window, setWindow] = useState(news.preferences.window);
  return <form onSubmit={event => { event.preventDefault(); news.updatePreferences({ filters, window }); }}>
    <div className="news-filters">{['currency', 'impact', 'category'].map(key => <label key={key}>{key}{key === 'impact' ? <select aria-label="News impact filter" value={filters[key]} onChange={event => setFilters({ ...filters, [key]: event.target.value })}>{['All', 'High', 'Medium', 'Low', 'Unknown'].map(value => <option key={value}>{value}</option>)}</select> : <input aria-label={`News ${key} filter`} value={filters[key]} onChange={event => setFilters({ ...filters, [key]: event.target.value })}/>}</label>)}</div>
    <p>Currency: All, Unknown, or a three-letter code. Category: All or an imported category.</p><h3>Research windows</h3><p>Pre [−A, −B), During [−B, C), Post [C, D). Version 1. Initial preset −60 to +60 minutes, with the first minute During.</p>
    {['A', 'B', 'C', 'D'].map(key => <label key={key}>{key === 'A' ? 'Before (minutes)' : key === 'D' ? 'After (minutes)' : key === 'B' ? 'During lead (seconds)' : 'During lag (seconds)'}<input aria-label={`News window ${key}`} type="number" step="any" min="0" max={31 * 86400 / (key === 'A' || key === 'D' ? 60 : 1)} value={window[key] / (key === 'A' || key === 'D' ? 60 : 1)} onChange={event => setWindow({ ...window, [key]: Number(event.target.value) * (key === 'A' || key === 'D' ? 60 : 1) })}/></label>)}<button disabled={news.busy}>Apply filters and windows</button>
  </form>;
}
export default function NewsPanel({ news, onClose }) {
  const [mode, setMode] = useState('Strict'), [offset, setOffset] = useState(0);
  const index = news.record?.index, cursor = news.cursor, retrospective = mode === 'Retrospective';
  const queryTime = Number.isFinite(cursor) ? cursor : retrospective ? news.record?.dataset.coverage[0]?.from : null;
  const from = (queryTime ?? 0) + offset * 86400 - 86400, to = from + 3 * 86400;
  const events = index && Number.isFinite(queryTime) ? index.range(from, to, queryTime, news.preferences.filters, { retrospective, limit: 100 }) : [];
  const coarse = index && Number.isFinite(queryTime) ? index.dateOnly(queryTime, news.preferences.filters, 20, retrospective) : [];
  const detail = index && news.selected ? index.project(news.selected, queryTime, retrospective) : null;
  const load = async event => {
    const file = event.target.files?.[0]; event.target.value = ''; if (!file) return;
    if (file.size > 64 * 1024 * 1024) { news.reportError('News JSON exceeds the 64 MiB import limit. Existing dataset preserved.'); return; }
    try { await news.replace(await file.text()); } catch (error) { news.reportError('Cannot read news file: ' + error.message); }
  };
  return <aside className="news-panel" aria-label="Economic News"><header><strong>Economic News</strong><button aria-label="Close News" onClick={onClose}>×</button></header>
    <label>Import canonical JSON<input aria-label="Import economic news JSON" type="file" accept=".json,application/json" disabled={news.busy} onChange={load}/></label><button disabled={news.busy} onClick={news.restore}>Restore previous dataset</button>
    {news.error && <p role="alert">{news.error}</p>}{news.busy && <p>Validating and saving…</p>}
    {news.arrival && <p role="status">{news.arrival}</p>}
    {news.record ? <details><summary>Dataset / provenance / coverage</summary><p>{news.record.dataset.datasetId} · {news.record.dataset.version}<br/>SHA-256 {news.record.hash}</p><p>{news.record.dataset.provenance.source} · {news.record.dataset.provenance.license}</p>{news.record.dataset.coverage.map((row, i) => <p key={i}>{stamp(row.from)} → {stamp(row.to)} · {row.status} · {row.currencies.join(', ')} / {row.categories.join(', ')}</p>)}</details> : <p>No economic-event dataset loaded. User imports stay local; no external service is required.</p>}
    <label>Knowledge mode<select aria-label="News knowledge mode" value={mode} onChange={event => { news.cancel(); setMode(event.target.value); news.setSelected(null); }}><option>Strict</option><option>Retrospective</option></select></label>
    <p>{retrospective ? 'RETROSPECTIVE RESEARCH — includes later/unknown information. Cannot navigate replay or create strict markers.' : `Strict replay · ${stamp(cursor)}. Unknown availability fields remain hidden.`}</p>
    <div className="news-navigation"><button disabled={retrospective || !Number.isFinite(cursor) || !!news.navigation || news.busy} onClick={() => news.navigate(-1)}>Previous Economic Event</button><button disabled={retrospective || !Number.isFinite(cursor) || !!news.navigation || news.busy} onClick={() => news.navigate(1)}>Next Economic Event</button>{news.navigation && <><p>{news.navigation}</p><button onClick={news.cancel}>Cancel navigation</button></>}</div>
    <div><button onClick={() => { setOffset(offset - 3); news.setSelected(null); }}>Earlier list window</button><button onClick={() => { setOffset(0); news.setSelected(null); }}>Around replay time</button><button onClick={() => { setOffset(offset + 3); news.setSelected(null); }}>Later list window</button><small>List window {stamp(from)} → {stamp(to)}. Up to 100 events; narrow filters for dense groups.</small></div>
    {Number.isFinite(queryTime) && <p>Coverage at query time: {index?.coverageAt(queryTime, news.preferences.filters) ?? 'unknown'}. Filtered results are not proof that no other news occurred.</p>}
    <div className="news-event-list">{[...events, ...coarse].map(event => <button key={event.occurrenceId} aria-pressed={news.selected === event.occurrenceId} onClick={() => news.setSelected(event.occurrenceId)}><strong>{event.fields.name?.value ?? 'Name unavailable'}</strong><span>{stamp(event.fields.schedule?.value)} · {event.fields.currency?.value ?? 'Unknown'} · {event.fields.impact?.value ?? 'Unknown'}{event.fields.schedule?.precision === 'day' ? ' · date only / no navigation' : !news.canMap(event.fields.schedule?.value) ? ' · unmapped to revealed market coverage' : ' · chart mapped'}</span></button>)}{!events.length && !coarse.length && <p>No matching eligible events shown. Consult explicit coverage; absence is unknown outside complete scope.</p>}</div>
    {detail && <section aria-label="Economic event details"><h3>{detail.fields.name?.value ?? 'Name unavailable'}</h3><small>{detail.occurrenceId} · {mode}</small><dl>{NEWS_FIELDS.map(key => { const fact = detail.fields[key]; return <div key={key}><dt>{key}</dt><dd>{fact ? `${key === 'schedule' || key === 'releaseTime' ? stamp(fact.value) : fact.value ?? 'Explicitly unavailable'} ${fact.unit ?? ''}` : 'Hidden: availability or release evidence insufficient'}{fact && <small>version {fact.version} · available {stamp(fact.availableAt)} · {fact.evidence ?? 'No historical evidence'} · {fact.precision}/{fact.availabilityPrecision}</small>}</dd></div>; })}</dl></section>}
    <PreferenceForm key={JSON.stringify(news.preferences)} news={news}/>
  </aside>;
}
