"""Private V2 dataset composition; the existing reducer alone owns finances.

No source path, storage handle, root, index, EOF, or future evidence is projected.
Source quality is preserved verbatim; structural publication is not certification.
"""
from collections import OrderedDict
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import json
import re
from threading import RLock

from contracts.canonical import canonical_bytes, content_hash
from contracts.primitives import require
from ticks.contracts import keys
from ticks.contracts_v2 import canonical_v2_bytes
from ticks.storage_v2 import ArtifactStore, DiskTickProvider
from ticks.timeline_v2 import IndexedTickTimeline
from .fixture_demo import fixture_profile
from .workspace import WINDOW_GROUPS


class HistoricalSource:
    def __init__(self, folder, version, *, log_root):
        self.folder, self.version, self.log_root = Path(folder), version, Path(log_root)
        with_provider = DiskTickProvider(self.folder, version)
        try:
            root = with_provider.describe_v2(with_provider.dataset_id, version)['root']
            require(root['providerId'] == 'exness' and root['providerSymbol'] == 'XAUUSDm'
                    and root['evidenceClass'] == 'PROVIDER_OBSERVATION', 'historicalSource', 'REFUSED_HISTORICAL_SOURCE')
            self.dataset_id = root['datasetId']
            self.start_ns = int(root['range']['startNs'])
            self.start_period = datetime.fromtimestamp(self.start_ns//1000000000, timezone.utc).strftime('%Y-%m')
            # Explicit research model inherited from QUOTE_BASELINE, not broker specs.
            self.profile = dict(fixture_profile(), providerId=root['providerId'], feedId=root['feedId'],
                                feedInstrumentId=root['instrumentId'], tickSize='0.001', priceScale='1000')
        finally:
            with_provider.close()
        self.dataset_version = version
        self.label = 'EXNESS LOCAL / COVERAGE AND FRESHNESS UNKNOWN'
        if ':first:' in self.dataset_id:
            self.label = 'EXNESS LOCAL / FIRST '+self.dataset_id.rsplit(':first:',1)[1]+' ROWS (ATOMIC GROUPS) / COVERAGE AND FRESHNESS UNKNOWN'

    def provider(self):
        return DiskTickProvider(self.folder, self.version, allow_threads=True)

    def start_for_period(self, period):
        """Operator-selected new Session start; index/EOF stay controller-private."""
        require(type(period) is str and re.fullmatch(r'[0-9]{4}-(0[1-9]|1[0-2])', period) is not None
                and period[:4] == self.start_period[:4], 'period', 'REFUSED_HISTORICAL_PERIOD')
        date = datetime(int(period[:4]), int(period[5:]), 1, tzinfo=timezone.utc)
        days = (date-datetime(1970,1,1,tzinfo=timezone.utc)).days
        target = max(self.start_ns, days*86400*1000000000)
        provider = self.provider()
        try:
            located = provider.locate_v2(self.dataset_id, self.version, str(target))
            require(located['position'] is not None, 'period', 'REFUSED_HISTORICAL_PERIOD')
            start = int(located['groupTimeNs'])
            observed_period = datetime.fromtimestamp(start//1000000000, timezone.utc).strftime('%Y-%m')
            require(observed_period == period, 'period', 'REFUSED_HISTORICAL_PERIOD')
            return start
        finally:
            provider.close()


class IndexedTimelineCache:
    """Four locked private entries; PostgreSQL checkpoint is the accepted tip.

Immutable disk log blocks may remain orphaned after CAS/transaction refusal.
Reconstruction follows only the exact hashes in the committed checkpoint.
"""
    indexed = True

    def __init__(self, source):
        self.source = source
        self._lock = RLock()
        self._entries = OrderedDict()
        self._creating = {}
        self._window_key = None
        self._window_rows = None

    def validate_checkpoint(self, checkpoint):
        keys(checkpoint, 'schemaVersion artifact cursor advanceLogHash positionLogHash')
        require(checkpoint['artifact'] == 'BTL-TICK-CHECKPOINT-2', 'checkpoint', 'CORRUPT_RECORD')
        canonical_v2_bytes(checkpoint)
        require(checkpoint['cursor']['datasetId'] == self.source.dataset_id and
                checkpoint['cursor']['datasetVersion'] == self.source.version, 'dataset', 'REFUSED_DATASET_VERSION')

    def _folder(self, scope, session):
        name = content_hash(dict(schemaVersion=1, artifact='BTL-PRIVATE-SESSION-LOG-1',
                                 workspace=scope.workspace_id, session=session, datasetVersion=self.source.version))
        return self.source.log_root/name

    def _key(self, scope, session, checkpoint):
        self.validate_checkpoint(checkpoint)
        return (scope.workspace_id, session, canonical_v2_bytes(checkpoint))

    def new_timeline(self, scope, session, start):
        with self._lock:
            provider = self.source.provider()
            try:
                timeline = IndexedTickTimeline(provider, self.source.dataset_id, self.source.version, str(start),
                                               log_folder=self._folder(scope, session), allow_threads=True)
            except BaseException:
                provider.close(); raise
            self._creating[id(timeline)] = provider
            return timeline

    def discard(self, timeline):
        with self._lock:
            timeline.close()
            provider = self._creating.pop(id(timeline), None)
            if provider is not None:
                provider.close()

    def _publish(self, scope, session, timeline, provider):
        key = self._key(scope, session, timeline.checkpoint())
        # Replace an older speculative generation for this same Session.
        for old in list(self._entries):
            if old[:2] == key[:2]:
                prior_t, prior_p = self._entries.pop(old)
                if prior_t is not timeline:
                    prior_t.close(); prior_p.close()
        self._entries[key] = (timeline, provider)
        while len(self._entries) > 4:
            _, (old_t, old_p) = self._entries.popitem(last=False)
            old_t.close(); old_p.close()

    def seed(self, scope, session, timeline):
        with self._lock:
            self._publish(scope, session, timeline, self._creating.pop(id(timeline)))

    def _entry(self, scope, session, checkpoint):
        key = self._key(scope, session, checkpoint)
        if key not in self._entries:
            provider = self.source.provider()
            try:
                timeline = IndexedTickTimeline.resume(provider, checkpoint, log_folder=self._folder(scope, session),
                                                       allow_threads=True)
            except BaseException:
                provider.close(); raise
            self._publish(scope, session, timeline, provider)
        self._entries.move_to_end(key)
        entry = self._entries[key]
        require(entry[0].checkpoint() == checkpoint, 'checkpoint', 'CORRUPT_RECORD')
        return key, entry

    def reveal(self, scope, session, checkpoint, target, *, seek=False):
        with self._lock:
            key, (timeline, provider) = self._entry(scope, session, checkpoint)
            del self._entries[key]
            try:
                result = timeline.seek(target) if seek else timeline.advance_through(target, timeline.cursor)
                next_checkpoint = timeline.checkpoint()
                self._publish(scope, session, timeline, provider)
                return result, next_checkpoint
            except BaseException:
                timeline.close(); provider.close(); raise

    def window(self, scope, session, checkpoint, *, last_only=False):
        with self._lock:
            key, (timeline, _) = self._entry(scope, session, checkpoint)
            # One bounded, already validated immutable prefix. A timeframe
            # change must not reread/rehash 1,024 groups from disk. The exact
            # committed checkpoint remains the key; callers receive copies.
            if key == self._window_key:
                return deepcopy(self._window_rows[-1:] if last_only else self._window_rows)
            consumer = timeline.consumer()
            end = int(consumer.cursor['nextGroupIndex'])
            start = max(0, end-(1 if last_only else WINDOW_GROUPS))
            result = []
            total_bytes = 0
            while start < end:
                rows = consumer.read_revealed(str(start), min(64, end-start))
                require(bool(rows), 'revealed', 'CORRUPT_RECORD')
                total_bytes += sum(len(json.dumps(group,ensure_ascii=False,separators=(",", ":"),allow_nan=False).encode("utf-8")) for group in rows)
                require(total_bytes <= 8*1048576, 'revealedWindow', 'REFUSED_CHART_WINDOW_LIMIT')
                result.extend(rows); start += len(rows)
            require(all(int(g['timeNs']) <= int(checkpoint['cursor']['throughNs']) for g in result),
                    'future', 'UNREVEALED_INDEX')
            if not last_only:
                self._window_key, self._window_rows = key, result
            return deepcopy(result)

    def close(self):
        with self._lock:
            for timeline, provider in self._entries.values():
                timeline.close(); provider.close()
            self._entries.clear()
            self._window_key, self._window_rows = None, None


def published_version(folder):
    """Operator-selected store only. Never import/continue it implicitly on startup."""
    store = ArtifactStore(folder)
    try:
        versions = store.db.execute('SELECT version FROM publications LIMIT 2').fetchall()
        require(len(versions) == 1, 'publication', 'INCOMPLETE_INGESTION')
        return versions[0][0]
    finally:
        store.close()
