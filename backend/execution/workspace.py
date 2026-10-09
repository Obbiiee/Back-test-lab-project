"""Controller-only immutable fixture cache and revealed display aggregation.

No financial reducer, historical storage format, or consumer provider capability.
"""
from collections import OrderedDict
from dataclasses import dataclass
from fractions import Fraction
import json
from threading import RLock

from application.models import TrustedScope
from contracts.canonical import canonical_bytes, content_hash
from contracts.primitives import require, identifier
from ticks.timeline import TickTimeline
from .contracts import text, MAX_STEPS
from .research_fixture import research_provider

WINDOW_GROUPS = 1024
TIMEFRAMES = {'1m':60, '3m':180, '5m':300, '15m':900, '30m':1800,
              '1h':3600, '2h':7200, '4h':14400, 'D':86400}


@dataclass
class _Entry:
    timeline: TickTimeline
    checkpoint: bytes
    groups: tuple


class FixtureTimelineCache:
    """Four private entries; exact durable checkpoint is always the lookup key.

    Speculative mutation removes the prior key first. A transaction rollback
    cannot use its successor against the unchanged durable checkpoint. Readers
    hold the same lock and receive decoded past groups, never a mutable timeline.
    """
    def __init__(self, provider):
        require(provider is research_provider(), 'cacheProvider', 'REFUSED_NON_FIXTURE_MODE')
        self.__provider = provider
        self.__entries = OrderedDict()
        self.__lock = RLock()

    def _key(self, scope, session, checkpoint):
        require(type(scope) is TrustedScope, 'scope', 'SCOPE_REQUIRED')
        identifier(session, 'sessionId')
        require(len(checkpoint['advanceTargets']) <= MAX_STEPS, 'steps', 'REFUSED_RECOVERY_LIMIT')
        raw = canonical_bytes({'schemaVersion':1,'artifact':'BTL-PRIVATE-TIMELINE-CACHE-1','checkpoint':checkpoint})
        return (scope.workspace_id, session, content_hash({'schemaVersion':1,'artifact':'BTL-PRIVATE-CACHE-KEY-1','checkpoint':checkpoint})), raw

    def _past(self, timeline):
        consumer = timeline.consumer()
        end = int(consumer.cursor['nextGroupIndex'])
        index = max(0, end-WINDOW_GROUPS)
        values = []
        while index < end:
            page = consumer.read_revealed(str(index), min(64, end-index))
            require(bool(page), 'cacheWindow', 'CORRUPT_RECORD')
            values.extend(page); index += len(page)
        return tuple(canonical_bytes({'schemaVersion':1,'artifact':'BTL-PRIVATE-PAST-GROUP-1','group':group}) for group in values)

    def _publish(self, scope, session, timeline, groups):
        key, raw = self._key(scope, session, timeline.checkpoint())
        self.__entries[key] = _Entry(timeline, raw, tuple(groups[-WINDOW_GROUPS:]))
        self.__entries.move_to_end(key)
        while len(self.__entries) > 4:
            self.__entries.popitem(last=False)

    def _entry(self, scope, session, checkpoint):
        key, raw = self._key(scope, session, checkpoint)
        entry = self.__entries.get(key)
        if entry is None:
            timeline = TickTimeline.resume(self.__provider, checkpoint)
            self._publish(scope, session, timeline, self._past(timeline))
            entry = self.__entries[key]
        require(entry.checkpoint == raw and entry.timeline.checkpoint() == checkpoint, 'cachePins', 'CORRUPT_RECORD')
        self.__entries.move_to_end(key)
        return key, entry

    def seed(self, scope, session, timeline):
        # Called only after the actual seed transaction commits.
        with self.__lock:
            self._publish(scope, session, timeline, self._past(timeline))

    def reveal(self, scope, session, checkpoint, target, *, seek=False):
        with self.__lock:
            key, entry = self._entry(scope, session, checkpoint)
            del self.__entries[key]
            timeline = entry.timeline
            if seek:
                ack = timeline.seek(target)
                groups = self._past(timeline)
            else:
                ack = timeline.advance_through(target, timeline.cursor)
                groups = entry.groups + tuple(canonical_bytes({'schemaVersion':1,'artifact':'BTL-PRIVATE-PAST-GROUP-1','group':group}) for group in ack['groups'])
            self._publish(scope, session, timeline, groups)
            return ack, timeline.checkpoint()

    def window(self, scope, session, checkpoint, *, last_only=False):
        with self.__lock:
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
