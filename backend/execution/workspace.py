"""Controller-only immutable fixture cache and revealed display aggregation.

No financial reducer, historical storage format, or consumer provider capability.
"""
from collections import OrderedDict
from dataclasses import dataclass
from fractions import Fraction
import json
from threading import Lock, RLock
from time import perf_counter_ns

from application.models import TrustedScope
from contracts.canonical import canonical_bytes, content_hash
from contracts.primitives import require, identifier
from ticks.timeline import TickTimeline
from qa_timing import record_qa_timing
from .contracts import text, MAX_STEPS
from .research_fixture import research_provider

WINDOW_GROUPS = 1024
FIXTURE_CACHE_ENTRIES = 16
TIMEFRAMES = {'1m':60, '3m':180, '5m':300, '15m':900, '30m':1800,
              '1h':3600, '2h':7200, '4h':14400, 'D':86400}

# API requests construct short-lived ResearchApplication adapters. Keep the
# small immutable synthetic timeline index across those adapters so each
# request does not cold-resume and reread the same committed revealed prefix.
# The key still includes workspace, Session, dataset identity, and exact
# checkpoint; the cache remains a disposable controller-side accelerator.
_FIXTURE_ENTRIES = OrderedDict()
_FIXTURE_LOCK = RLock()
_FIXTURE_RESTORE_GATES = {}


@dataclass
class _RestoreGate:
    lock: Lock
    users: int = 0


@dataclass
class _Entry:
    timeline: TickTimeline
    checkpoint: bytes
    groups: tuple


class FixtureTimelineCache:
    """Bounded private entries; exact durable checkpoint is always the lookup key.

    Speculative mutation removes the prior key first. A transaction rollback
    cannot use its successor against the unchanged durable checkpoint. Readers
    hold the same lock and receive decoded past groups, never a mutable timeline.
    """
    def __init__(self, provider, *, allow_injected_synthetic=False):
        require(provider is research_provider() or allow_injected_synthetic,
                'cacheProvider', 'REFUSED_NON_FIXTURE_MODE')
        self.__provider = provider
        self.__entries = _FIXTURE_ENTRIES
        self.__lock = _FIXTURE_LOCK
        self.__provider_identity = (provider.dataset_id, provider.dataset_version,
            content_hash(provider.describe(provider.dataset_id, provider.dataset_version)))

    def _key(self, scope, session, checkpoint):
        require(type(scope) is TrustedScope, 'scope', 'SCOPE_REQUIRED')
        identifier(session, 'sessionId')
        require(len(checkpoint['advanceTargets']) <= MAX_STEPS, 'steps', 'REFUSED_RECOVERY_LIMIT')
        raw = canonical_bytes({'schemaVersion':1,'artifact':'BTL-PRIVATE-TIMELINE-CACHE-1','checkpoint':checkpoint})
        return (self.__provider_identity, scope.workspace_id, session,
                content_hash({'schemaVersion':1,'artifact':'BTL-PRIVATE-CACHE-KEY-1','checkpoint':checkpoint})), raw

    def _past(self, timeline):
        started = perf_counter_ns()
        consumer = timeline.consumer()
        end = int(consumer.cursor['nextGroupIndex'])
        index = max(0, end-WINDOW_GROUPS)
        values = []
        while index < end:
            page = consumer.read_revealed(str(index), min(64, end-index))
            require(bool(page), 'cacheWindow', 'CORRUPT_RECORD')
            values.extend(page); index += len(page)
        result = tuple(canonical_bytes({'schemaVersion':1,'artifact':'BTL-PRIVATE-PAST-GROUP-1','group':group}) for group in values)
        record_qa_timing('fixturePastReadNs', perf_counter_ns() - started)
        return result

    def _publish(self, scope, session, timeline, groups):
        key, raw = self._key(scope, session, timeline.checkpoint())
        self.__entries[key] = _Entry(timeline, raw, tuple(groups[-WINDOW_GROUPS:]))
        self.__entries.move_to_end(key)
        while len(self.__entries) > FIXTURE_CACHE_ENTRIES:
            self.__entries.popitem(last=False)

    def _entry(self, scope, session, checkpoint):
        key, raw = self._key(scope, session, checkpoint)
        lock_started = perf_counter_ns()
        with self.__lock:
            record_qa_timing('fixtureCacheLockWaitNs', perf_counter_ns() - lock_started)
            entry = self.__entries.get(key)
            if entry is not None:
                self.__entries.move_to_end(key)
                require(entry.checkpoint == raw, 'cachePins', 'CORRUPT_RECORD')
                return key, entry
            gate = _FIXTURE_RESTORE_GATES.get(key)
            if gate is None:
                gate = _RestoreGate(Lock())
                _FIXTURE_RESTORE_GATES[key] = gate
            gate.users += 1

        # Deduplicate an exact checkpoint restore without serializing unrelated Sessions.
        acquired = False
        try:
            gate_started = perf_counter_ns()
            gate.lock.acquire()
            record_qa_timing('fixtureRestoreGateWaitNs', perf_counter_ns() - gate_started)
            acquired = True
            with self.__lock:
                entry = self.__entries.get(key)
                if entry is not None:
                    self.__entries.move_to_end(key)
            if entry is None:
                resume_started = perf_counter_ns()
                timeline = TickTimeline.resume(self.__provider, checkpoint)
                record_qa_timing('fixtureTimelineResumeNs', perf_counter_ns() - resume_started)
                try:
                    groups = self._past(timeline)
                except BaseException:
                    timeline.close()
                    raise
                with self.__lock:
                    entry = self.__entries.get(key)
                    if entry is None:
                        self._publish(scope, session, timeline, groups)
                        entry = self.__entries[key]
                    else:
                        timeline.close()
                    self.__entries.move_to_end(key)
            require(entry.checkpoint == raw, 'cachePins', 'CORRUPT_RECORD')
            return key, entry
        finally:
            if acquired:
                gate.lock.release()
            with self.__lock:
                gate.users -= 1
                if gate.users == 0 and _FIXTURE_RESTORE_GATES.get(key) is gate:
                    del _FIXTURE_RESTORE_GATES[key]

    def seed(self, scope, session, timeline):
        # Called only after the actual seed transaction commits.
        groups = self._past(timeline)
        with self.__lock:
            self._publish(scope, session, timeline, groups)

    def reveal(self, scope, session, checkpoint, target, *, seek=False):
        key, entry = self._entry(scope, session, checkpoint)
        with self.__lock:
            # The immutable group tuple may still be used by readers that got it
            # immediately before removal. Timeline mutation stays outside this lock.
            del self.__entries[key]
        timeline = entry.timeline
        if seek:
            ack = timeline.seek(target)
            groups = self._past(timeline)
        else:
            ack = timeline.advance_through(target, timeline.cursor)
            groups = entry.groups + tuple(canonical_bytes({'schemaVersion':1,'artifact':'BTL-PRIVATE-PAST-GROUP-1','group':group}) for group in ack['groups'])
        with self.__lock:
            self._publish(scope, session, timeline, groups)
        return ack, timeline.checkpoint()

    def preview(self, checkpoint, target):
        """Read one bounded controller-private page without changing the accepted cache tip."""
        timeline = TickTimeline.resume(self.__provider, checkpoint)
        return timeline.advance_through(target, timeline.cursor)

    def window(self, scope, session, checkpoint, *, last_only=False):
        indexed_reader = getattr(self.__provider, 'read_revealed_window', None)
        if callable(indexed_reader):
            # Monthly Parquet can seek to verified row groups and clip at the
            # committed frontier. This is display-only; execution still uses
            # TickTimeline and the canonical reducer.
            groups = indexed_reader(int(checkpoint['cursor']['throughNs']),
                                    1 if last_only else WINDOW_GROUPS)
            require(len(groups) <= (1 if last_only else WINDOW_GROUPS) and
                    all(int(group['timeNs']) <= int(checkpoint['cursor']['throughNs'])
                        for group in groups),
                    'futureWindow', 'UNREVEALED_INDEX')
            return groups
        _, entry = self._entry(scope, session, checkpoint)
        blobs = entry.groups[-1:] if last_only else entry.groups
        groups = [json.loads(raw)['group'] for raw in blobs]
        through = int(checkpoint['cursor']['throughNs'])
        require(all(int(g['timeNs']) <= through for g in groups), 'futureWindow', 'UNREVEALED_INDEX')
        return groups


def display_candles(groups, through_ns, timeframe, window_start):
    require(type(timeframe) is str and timeframe in TIMEFRAMES, 'timeframe', 'REFUSED_TIMEFRAME')
    require(type(groups) is list and len(groups) <= WINDOW_GROUPS and type(window_start) is int and window_start >= 0, 'displayBounds')
    duration = TIMEFRAMES[timeframe]
    through = int(through_ns)
    bars = []
    previous = -1
    for group in groups:
        stamp = int(group['timeNs'])
        require(previous < stamp <= through, 'futureCandle', 'UNREVEALED_INDEX')
        previous = stamp
        for event in group['events']:
            stamp = int(event['timeNs'])
            require(stamp == int(group['timeNs']) and stamp <= through, 'futureCandle', 'UNREVEALED_INDEX')
            mid = (Fraction(event['bid'])+Fraction(event['ask']))/2
            bucket = (stamp//1000000000//duration)*duration
            if not bars or bars[-1]['time'] != bucket:
                bars.append(dict(time=bucket,open=mid,high=mid,low=mid,close=mid,event_count=1))
            else:
                bar = bars[-1]
                bar.update(high=max(bar['high'],mid),low=min(bar['low'],mid),close=mid,event_count=bar['event_count']+1)
    for i, bar in enumerate(bars):
        for field in ('open','high','low','close'):
            bar[field] = text(bar[field])
        bar['incomplete'] = (bar['time']+duration)*1000000000 > through
        bar['partialWindow'] = window_start > 0 and i == 0 and int(groups[0]['timeNs']) > bar['time']*1000000000
    return dict(timeframe=timeframe,priceBasis='EXACT_REVEALED_MID_DISPLAY_ONLY',volumeAvailable=False,
                windowStartGroup=str(window_start),candles=bars[-512:])
