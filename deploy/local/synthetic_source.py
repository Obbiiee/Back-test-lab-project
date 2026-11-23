"""Deterministic, repository-authored SYNTHETIC Monthly Parquet source (no market data) shared by the public-site provisioning and the local stack.

The source starts exactly at the product fixture's start (`execution.research_fixture.START_NS`, 2020-01-01 00:00 UTC), one tick per minute. A Session's
cursor starts at that fixture start, so the first tick is reachable immediately and the first full UTC months (January, February, ...) have data.
Idempotent: an existing source with the same tick count is reused."""
import json
import os
from pathlib import Path

DEFAULT_TICKS = 131072        # January + February + March 2020 in full (about three months at one tick per minute)


def ensure_source(data_dir, ticks=DEFAULT_TICKS, log=print):
    """Create (or reuse) the source under `<data_dir>/<ticks>/` and return {ticks, datasetId, version, manifestHash, monthly, accepted}."""
    from contracts.canonical import content_hash
    from execution.research_fixture import START_NS
    from market_data.monthly_parquet import MonthlyParquetProvider, write_monthly_parquet
    from tests.synthetic_financial_monthly import build_manifest, iter_events
    from ticks import source_acceptance
    base = Path(data_dir) / str(ticks)
    info_file = base / 'source.json'
    monthly, accepted = base / 'monthly', base / 'accepted'
    manifest, _m, _q = build_manifest(ticks, start_ns=START_NS)
    version = content_hash(manifest)
    if info_file.exists():
        info = json.loads(info_file.read_text())
        if info.get('version') == version:
            return {**info, 'monthly': str(monthly), 'accepted': str(accepted)}
        raise SystemExit(f'{info_file} holds another dataset version; remove {base} to regenerate')
    base.mkdir(parents=True, exist_ok=True)
    log(f'Generating the synthetic source ({ticks} ticks); this is a one-time step...')
    parquet = write_monthly_parquet(str(monthly), iter_events(ticks, manifest, start_ns=START_NS), manifest, expected_version=version, row_group_size=8192)
    provider = MonthlyParquetProvider(str(monthly), expected_dataset_id=manifest['datasetId'], expected_dataset_version=version,
                                      expected_manifest_hash=parquet['manifestHash'])
    source_acceptance.accept_offline(provider, manifest['datasetId'], version, str(accepted))
    info = dict(ticks=ticks, datasetId=manifest['datasetId'], version=version, manifestHash=parquet['manifestHash'])
    info_file.write_text(json.dumps(info))
    return {**info, 'monthly': str(monthly), 'accepted': str(accepted)}


def source_environment(info):
    """The non-secret application environment that pins this source (same variables the public site uses)."""
    return {
        'BTL_QA_SYNTHETIC_MONTHLY_ENABLE': '1',
        'BTL_QA_SYNTHETIC_MONTHLY_ROOT': info['monthly'],
        'BTL_QA_SYNTHETIC_MONTHLY_DATASET_ID': info['datasetId'],
        'BTL_QA_SYNTHETIC_MONTHLY_DATASET_VERSION': info['version'],
        'BTL_QA_SYNTHETIC_MONTHLY_MANIFEST_SHA256': info['manifestHash'],
        'BTL_SOURCE_ACCEPTANCE_DIR': info['accepted'],
        'BTL_TICK_SESSION_STORAGE_FORMAT': 'compact-v1',
    }
