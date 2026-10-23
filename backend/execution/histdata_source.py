"""Pinned private HistData replay composition; no financial source admission.

Reuses the existing indexed timeline/cache and bounded indicator context. Never
relabels HistData as Exness/synthetic or asserts provider rights/freshness.
"""
from datetime import datetime, timezone
from pathlib import Path
import re

from contracts.canonical import content_hash
from contracts.primitives import require
from market_data.instruments import instrument
from market_data.tick_context import load_tick_context
from ticks.histdata_v2 import ADAPTER
from ticks.storage_v2 import DiskTickProvider


class HistDataReplaySource:
    def __init__(self, folder, version, symbol, *, log_root):
        instrument(symbol)
        provider = DiskTickProvider(folder, version)
        try:
            root = provider.describe_v2(provider.dataset_id, version)['root']
            require(root['providerId'] == 'histdata' and root['providerSymbol'] == symbol
                    and root['feedId'] == 'local-unverified:'+symbol
                    and root['instrumentId'] == 'histdata:'+symbol
                    and root['evidenceClass'] == 'PROVIDER_OBSERVATION'
                    and root['adapterVersion'] == ADAPTER,
                    'source', 'REFUSED_HISTDATA_REPLAY_SOURCE')
            require(':first:' not in root['datasetId'], 'selection', 'REFUSED_PREFIX_AS_FULL_SOURCE')
            self.folder, self.log_root = Path(folder), Path(log_root)
            self.version, self.dataset_id, self.symbol = version, root['datasetId'], symbol
            self.start_ns, self.end_ns = int(root['range']['startNs']), int(root['range']['endNs'])
            self.binding_hash = content_hash(dict(schemaVersion=1,
                artifact='BTL-HISTDATA-REPLAY-BINDING-1', datasetId=self.dataset_id,
                datasetVersion=version, symbol=symbol, kind='PRIVATE_REPLAY_REFERENCE_ONLY'))
        finally:
            provider.close()
        self.label = 'HISTDATA OBSERVATIONS / COVERAGE, FRESHNESS AND RIGHTS UNKNOWN'

    def provider(self):
        provider = DiskTickProvider(self.folder, self.version, allow_threads=True)
        try:
            require(provider.dataset_id == self.dataset_id, 'source', 'REFUSED_DATASET_VERSION')
        except BaseException:
            provider.close(); raise
        return provider

    def start_for_period(self, period):
        """Controller-only observed start selection, never a coverage assertion."""
        require(type(period) is str and re.fullmatch(r'[0-9]{4}-(0[1-9]|1[0-2])', period),
                'period', 'REFUSED_HISTDATA_PERIOD')
        try:
            date = datetime(int(period[:4]), int(period[5:]), 1, tzinfo=timezone.utc)
        except ValueError:
            require(False, 'period', 'REFUSED_HISTDATA_PERIOD')
        target = max(self.start_ns, (date-datetime(1970,1,1,tzinfo=timezone.utc)).days*86400*10**9)
        provider = self.provider()
        try:
            located = provider.locate_v2(self.dataset_id, self.version, str(target))
            require(located['position'] is not None, 'period', 'REFUSED_HISTDATA_PERIOD')
            start = int(located['groupTimeNs'])
            observed = datetime.fromtimestamp(start//10**9, timezone.utc).strftime('%Y-%m')
            require(observed == period, 'period', 'REFUSED_HISTDATA_PERIOD')
            return start
        finally:
            provider.close()

    def context(self, plan, *, trusted_start_ns, **budgets):
        provider = self.provider()
        try:
            return load_tick_context(provider, plan, trusted_start_ns=trusted_start_ns, **budgets)
        finally:
            provider.close()
