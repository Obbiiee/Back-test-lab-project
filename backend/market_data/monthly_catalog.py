"""Operator-pinned, versioned catalog for shared immutable Monthly Parquet.

Public selectors are opaque keys and UTC months. Local/object-store paths,
manifest pins, and rights evidence remain server-side configuration.
"""
import hashlib
import json
import os
from collections import OrderedDict
from pathlib import Path
import re
import stat
from threading import RLock

from contracts.canonical import canonical_bytes
from contracts.primitives import digest, identifier, require

CATALOG_ARTIFACT = 'BTL-MONTHLY-PARQUET-SOURCE-CATALOG-1'
MAX_CATALOG_BYTES = 1_048_576
MAX_SOURCES = 4096
MAX_PROVIDER_CACHE = 16
MAX_SYNTHETIC_SOURCE_BYTES = 16 * 1_048_576


class MonthlyParquetCatalog:
    def __init__(self, path, sha256):
        digest(sha256, 'catalogHash')
        path = Path(path)
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            require(stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o400 and
                    1 <= info.st_size <= MAX_CATALOG_BYTES,
                    'monthlyCatalog', 'REFUSED_OPERATOR_CATALOG')
            raw = stream.read(MAX_CATALOG_BYTES + 1)
        require(len(raw) <= MAX_CATALOG_BYTES and hashlib.sha256(raw).hexdigest() == sha256,
                'monthlyCatalog', 'SOURCE_PIN_CHANGED')
        def unique_pairs(pairs):
            result = {}
            for key, item in pairs:
                require(key not in result, 'monthlyCatalog', 'REFUSED_OPERATOR_CATALOG')
                result[key] = item
            return result
        value = json.loads(raw, object_pairs_hook=unique_pairs)
        require(type(value) is dict and set(value) == {
            'schemaVersion', 'artifact', 'catalogVersion', 'sources'} and
            value['schemaVersion'] == 1 and value['artifact'] == CATALOG_ARTIFACT and
            value['catalogVersion'] == 1 and type(value['sources']) is list and
            1 <= len(value['sources']) <= MAX_SOURCES,
            'monthlyCatalog', 'REFUSED_OPERATOR_CATALOG')
        require(canonical_bytes(value) == raw,
                'monthlyCatalog', 'REFUSED_OPERATOR_CATALOG')
        self.catalog_hash = sha256
        self._entries = {}
        self._providers = OrderedDict()
        self._lock = RLock()
        for entry in value['sources']:
            require(type(entry) is dict and set(entry) == {
                'key', 'period', 'label', 'root', 'datasetId', 'datasetVersion',
                'manifestSha256', 'eligibility', 'eligibilityEvidenceSha256'},
                'monthlySource', 'REFUSED_OPERATOR_CATALOG')
            identifier(entry['key'], 'sourceKey')
            require(type(entry['period']) is str and re.fullmatch(
                r'\d{4}-(0[1-9]|1[0-2])', entry['period']) is not None,
                'period', 'REFUSED_OPERATOR_CATALOG')
            require(type(entry['label']) is str and 1 <= len(entry['label']) <= 128 and
                    not any(ord(char) < 32 for char in entry['label']),
                    'label', 'REFUSED_OPERATOR_CATALOG')
            require(type(entry['root']) is str and len(entry['root']) <= 4096 and
                    (entry['root'].startswith('s3://') or Path(entry['root']).is_absolute()),
                    'monthlyRoot', 'REFUSED_OPERATOR_CATALOG')
            identifier(entry['datasetId'], 'datasetId')
            digest(entry['datasetVersion'], 'datasetVersion')
            digest(entry['manifestSha256'], 'manifestHash')
            eligibility = entry['eligibility']
            require(eligibility in ('SYNTHETIC', 'RIGHTS_EVIDENCE_PINNED'),
                    'eligibility', 'REFUSED_SOURCE')
            if eligibility == 'SYNTHETIC':
                require(entry['eligibilityEvidenceSha256'] is None,
                        'eligibilityEvidence', 'REFUSED_OPERATOR_CATALOG')
            else:
                digest(entry['eligibilityEvidenceSha256'], 'eligibilityEvidence')
            key = (entry['key'], entry['period'])
            require(key not in self._entries, 'sourceKey', 'REFUSED_OPERATOR_CATALOG')
            self._entries[key] = dict(entry)

    def selection(self, key, period):
        identifier(key, 'sourceKey')
        require(type(period) is str and re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', period),
                'period', 'INVALID_INPUT')
        entry = self._entries.get((key, period))
        require(entry is not None, 'source', 'REFUSED_SOURCE_NOT_AVAILABLE')
        return dict(entry)

    def resolve(self, key, period, *, verify_file=True):
        entry = self.selection(key, period)
        cache_key = (entry['root'], entry['datasetId'], entry['datasetVersion'],
                     entry['manifestSha256'])
        with self._lock:
            provider = self._providers.get(cache_key)
            if provider is None:
                # Keep catalog admission and public selector reads independent
                # of Arrow; only the worker that opens the immutable source
                # needs the Parquet runtime.
                from .monthly_parquet import MonthlyParquetProvider
                provider = MonthlyParquetProvider(entry['root'],
                    expected_dataset_id=entry['datasetId'],
                    expected_dataset_version=entry['datasetVersion'],
                    expected_manifest_hash=entry['manifestSha256'])
                manifest = provider.manifest
                require(any(item['month'] == period for item in manifest['files']),
                        'monthlyPeriod', 'REFUSED_SOURCE_NOT_AVAILABLE')
                rights = manifest['sourceRights']
                if entry['eligibility'] == 'SYNTHETIC':
                    selected_file = next(item for item in manifest['files']
                                         if item['month'] == period)
                    require(rights['class'] == 'SYNTHETIC' and
                            manifest['sourceManifest']['evidenceClass'] == 'SYNTHETIC_CONTRACT_ONLY' and
                            manifest['eventCount'] <= 4096 and not manifest['diagnostics'] and
                            selected_file['bytes'] <= MAX_SYNTHETIC_SOURCE_BYTES,
                            'monthlyEligibility', 'REFUSED_SOURCE')
                    from execution.research_fixture import research_profile
                    profile = research_profile()
                    require((manifest['providerId'], manifest['feedId'], manifest['instrumentId']) ==
                            (profile['providerId'], profile['feedId'], profile['feedInstrumentId']),
                            'monthlyProfile', 'REFUSED_SOURCE')
                else:
                    require(rights['class'] == 'PUBLIC_GRANTED' and
                            rights.get('evidenceHash') is not None and
                            entry['eligibilityEvidenceSha256'] == rights['evidenceHash'] and
                            manifest['sourceManifest']['evidenceClass'] != 'SYNTHETIC_CONTRACT_ONLY',
                            'monthlyEligibility', 'REFUSED_SOURCE')
                self._providers[cache_key] = provider
                while len(self._providers) > MAX_PROVIDER_CACHE:
                    self._providers.popitem(last=False)
            self._providers.move_to_end(cache_key)
            if verify_file:
                provider.verify_file_hash(period)
            return provider

    def public(self):
        return [dict(key=key, period=period, label=entry['label'],
                     layout='MONTHLY_PARQUET_ZSTD', eligibility='SYNTHETIC',
                     model='SYNTHETIC_FIXTURE')
                for (key, period), entry in sorted(self._entries.items(), key=lambda item: item[0])
                if entry['eligibility'] == 'SYNTHETIC']

    def close(self):
        with self._lock:
            self._providers.clear()
