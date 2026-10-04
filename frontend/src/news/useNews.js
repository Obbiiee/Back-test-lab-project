import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { NewsRepository, validatePreferences } from './eventRepository.js';
import { NewsNavigationController } from './NewsNavigationController.js';
import { canonicalString, contentHash } from './eventValidation.js';
import { bucketTime } from '../market/candles.js';
const EMPTY = Object.freeze([]);
export default function useNews({ replay, trading, timeframe, setPlaying, chartCommand, openPanel }) {
  const [repository] = useState(() => new NewsRepository());
  const [navigator] = useState(() => new NewsNavigationController());
  const [record, setRecord] = useState(null), [preferences, setPreferences] = useState(() => validatePreferences(null));
  const [error, setError] = useState(''), [busy, setBusy] = useState(false), [navigation, setNavigation] = useState(''), [selected, setSelected] = useState(null);
  const cursor = replay.active ? replay.raw.at(-1)?.time : null;
  const [arrival, setArrival] = useState('');
  const [windowIdentity, setWindowIdentity] = useState(null);
  const windowKey = canonicalString(preferences.window);
  useEffect(() => { let active = true; contentHash(preferences.window).then(hash => { if (active) setWindowIdentity({ key: windowKey, hash }); }).catch(error => { if (active) setError(error.message); }); return () => { active = false; }; }, [preferences.window, windowKey]);
  const generation = useRef(0), preferenceGeneration = useRef(0), navigationEpoch = useRef(null);
  const cancel = useCallback(() => { navigator.cancel(); setNavigation(''); }, [navigator]);
  useEffect(() => {
    let active = true;
    const token = generation.current, preferenceToken = preferenceGeneration.current;
    repository.load().then(loaded => { if (active && generation.current === token) { setRecord(loaded.record); if (preferenceGeneration.current === preferenceToken) { setPreferences(loaded.preferences); setError(loaded.preferenceError); } } }).catch(error => { if (active && generation.current === token) setError(error.message); });
    const tokens = generation;
    const preferenceTokens = preferenceGeneration;
    return () => { active = false; tokens.current++; preferenceTokens.current++; navigator.cancel(); };
  }, [repository, navigator]);
  const replace = useCallback(async raw => {
    const token = ++generation.current; cancel(); setBusy(true); setError('');
    try { const imported = await repository.replace(raw); if (generation.current === token) { setRecord(imported); setSelected(null); } }
    catch (error) { if (generation.current === token) setError(error.message); }
    finally { if (generation.current === token) setBusy(false); }
  }, [repository, cancel]);
  const restore = useCallback(async () => {
    const token = ++generation.current; cancel(); setBusy(true); setError('');
    try { const restored = await repository.restorePrevious(); if (generation.current === token) { setRecord(restored); setSelected(null); } }
    catch (error) { if (generation.current === token) setError(error.message); }
    finally { if (generation.current === token) setBusy(false); }
  }, [repository, cancel]);
  const updatePreferences = useCallback(async value => {
    const token = ++preferenceGeneration.current; cancel(); setBusy(true);
    try { const next = validatePreferences(value); await repository.savePreferences(next); if (preferenceGeneration.current === token) { setPreferences(next); setError(''); } }
    catch (error) { if (preferenceGeneration.current === token) setError(error.message); }
    finally { if (preferenceGeneration.current === token) setBusy(false); }
  }, [repository, cancel]);
  const navigate = useCallback(direction => {
    if (!record || !Number.isFinite(cursor) || busy) return;
    const target = record.index.navigate(cursor, direction, preferences.filters);
    if (!target) { setError('No eligible event in that direction for the current filters and historical information.'); return; }
    const bounds = replay.bars;
    // Current loader has documented market bounds; unloaded forward chunks may extend normally.
    if (target.time < Date.parse('2016-10-03T00:00:00Z') / 1000 || target.time > Date.parse('2026-09-25T00:58:00Z') / 1000) { setError('Event is outside available market coverage.'); return; }
    setSelected(target.events[0].occurrenceId); setError(''); setArrival(''); setPlaying(false);
    if (target.time <= cursor) { if (target.time < bounds[0]?.time) { setError('Load older chart history before viewing this event.'); return; } chartCommand({ action: 'news-event', time: target.time }); return; }
    navigationEpoch.current = { revision: replay.transition.revision, timeframe, index: record.index };
    navigator.begin(target.time, { time: cursor }); setNavigation('Navigating with manual replay steps…');
  }, [record, cursor, busy, preferences.filters, replay.bars, replay.transition.revision, timeframe, setPlaying, chartCommand, navigator]);
  useEffect(() => {
    const frame = requestAnimationFrame(() => {
    if (navigator.target === null) return;
    if (timeframe !== navigationEpoch.current?.timeframe || record?.index !== navigationEpoch.current?.index || (replay.transition.revision !== navigationEpoch.current?.revision && ['start', 'stop', 'rewind'].includes(replay.transition.kind))) { cancel(); return; }
    const target = navigator.target;
    const status = navigator.commit({ time: cursor, revision: replay.transition.revision, settledTime: trading.account.lastTime, active: replay.active, loading: replay.loading, error: replay.error, atEnd: replay.atEnd, step: replay.step });
    if (status === 'arrived') { setNavigation(''); setArrival(`Arrived at ${new Date(cursor * 1000).toISOString()}; event ${new Date(target * 1000).toISOString()}. First settled raw M1 endpoint at or beyond the event; overshoot ${cursor - target} seconds.`); chartCommand({ action: 'news-event', time: target }); }
    if (status === 'cancelled') { setNavigation(''); setError(replay.error || 'News navigation cancelled.'); }
    if (status === 'waiting-for-history') setNavigation('Waiting for the existing market loader; Cancel is available.');
    });
    return () => cancelAnimationFrame(frame);
  }, [navigator, navigation, cursor, timeframe, record, replay.transition, replay.active, replay.loading, replay.error, replay.atEnd, replay.step, trading.account.lastTime, cancel, chartCommand]);
  const windowHash = windowIdentity?.key === windowKey ? windowIdentity.hash : 'pending';
  const context = useMemo(() => ({ index: record?.index ?? null, identity: record ? `${record.dataset.datasetId}/${record.dataset.version}/${record.hash}` : 'none', queryVersion: 1, windowHash, filters: preferences.filters, window: preferences.window, cursor }), [record, preferences, cursor, windowHash]);
  const getEvents = useCallback((from, to) => record && Number.isFinite(cursor) ? record.index.range(from, Math.min(to, cursor + .001), cursor, preferences.filters, { limit: 500 }) : EMPTY, [record, cursor, preferences.filters]);
  const hasMinute = useCallback(time => {
    const target = Math.floor(time / 60) * 60, bars = replay.raw; let lo = 0, hi = bars.length;
    while (lo < hi) { const mid = (lo + hi) >>> 1; if (bars[mid].time < target) lo = mid + 1; else hi = mid; }
    return bars[lo]?.time === target;
  }, [replay.raw]);
  const buckets = useMemo(() => new Set(replay.candles.map(bar => bar.time)), [replay.candles]);
  const canMap = useCallback(time => Number.isFinite(time) && time <= cursor && hasMinute(time) && buckets.has(bucketTime(time, timeframe)), [cursor, hasMinute, buckets, timeframe]);
  const chart = useMemo(() => ({ getEvents, hasMinute, cursor, timeframe, select: events => { setSelected(events[0]?.occurrenceId ?? null); openPanel?.(true); } }), [getEvents, hasMinute, cursor, timeframe, openPanel]);
  return { record, preferences, error, arrival, canMap, reportError: setError, busy, navigation, selected, setSelected, cursor, replace, restore, updatePreferences, navigate, cancel, context, chart };
}
