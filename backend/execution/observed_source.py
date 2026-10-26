"""Controller-private, readonly replay selection for explicitly pinned observations.

No financial profile or admission is synthesized. Dataset ranges, index/EOF,
storage handles and source pins never become a consumer projection here.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re

from contracts.primitives import digest, identifier, require
from ticks.storage_v2 import DiskTickProvider

EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


@dataclass(frozen=True)
class ObservedDatasetPin:
    dataset_id: str
    dataset_version: str
    provider_id: str
    feed_id: str
    instrument_id: str
    provider_symbol: str

    def __post_init__(self):
        for field in ('dataset_id', 'provider_id', 'feed_id', 'instrument_id', 'provider_symbol'):
            identifier(getattr(self, field), field)
        digest(self.dataset_version, 'datasetVersion')


class ObservedReplaySource:
    """An operator-selected observation source for IndexedTimelineCache only.

    A successful constructor proves published identity/reader compatibility,
    not rights, completeness, freshness, broker terms or financial eligibility.
    The existing Session service is not mounted or modified by this helper.
    """
    execution_eligibility = 'NOT_GRANTED'

    def __init__(self, folder, pin, *, log_root):
        require(type(pin) is ObservedDatasetPin, 'sourcePin')
        self._folder = Path(folder)
        self._pin = pin
        self.log_root = Path(log_root)
        require(not self.log_root.resolve().is_relative_to(self._folder.resolve()),
                'logRoot', 'SOURCE_LOG_OVERLAP')
        self.dataset_id, self.version = pin.dataset_id, pin.dataset_version
        provider = self.provider()
        try:
            root = provider.describe_v2(self.dataset_id, self.version)['root']
            expected = dict(datasetId=pin.dataset_id, providerId=pin.provider_id, feedId=pin.feed_id,
                            instrumentId=pin.instrument_id, providerSymbol=pin.provider_symbol)
            require(all(root[k] == v for k, v in expected.items()),
                    'sourcePin', 'OBSERVED_SOURCE_IDENTITY_MISMATCH')
            require(root['evidenceClass'] == 'PROVIDER_OBSERVATION',
                    'evidenceClass', 'REFUSED_OBSERVED_SOURCE')
            self._start_ns = int(root['range']['startNs'])
            self._end_ns = int(root['range']['endNs'])
        finally:
            provider.close()

    def provider(self):
        # Only the controller receives this handle. Never silently open a live
        # WAL stage or enable writer/schema startup to make a source usable.
        return DiskTickProvider(self._folder, self.version, allow_threads=True, read_only=True)

    def start_for_period(self, period):
        """Select an observed atomic group within the requested UTC month.

        An index hit in a later month is unavailable, not a shifted selection.
        This method makes no inference about missing days or complete coverage.
        """
        require(type(period) is str and re.fullmatch(r'[0-9]{4}-(0[1-9]|1[0-2])', period), 'period')
        year, month = map(int, period.split('-'))
        try:
            first = datetime(year, month, 1, tzinfo=timezone.utc)
            after = datetime(year+1, 1, 1, tzinfo=timezone.utc) if month == 12 else datetime(year, month+1, 1, tzinfo=timezone.utc)
        except ValueError:
            require(False, 'period')
        low = (first-EPOCH).days*86400*10**9
        high = (after-EPOCH).days*86400*10**9
        target = max(low, self._start_ns)
        require(0 <= target < high and low < self._end_ns,
                'period', 'OBSERVED_PERIOD_UNAVAILABLE')
        provider = self.provider()
        try:
            located = provider.locate_v2(self.dataset_id, self.version, str(target))
            require(located['position'] is not None, 'period', 'OBSERVED_PERIOD_UNAVAILABLE')
            observed = int(located['groupTimeNs'])
            require(target <= observed < high, 'period', 'OBSERVED_PERIOD_UNAVAILABLE')
            return observed
        finally:
            provider.close()
