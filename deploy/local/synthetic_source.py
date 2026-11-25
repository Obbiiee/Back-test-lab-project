"""Deterministic, repository-authored SYNTHETIC Monthly Parquet source (no market data) shared by the public-site provisioning and the local stack.

The source starts exactly at the product fixture's start (`execution.research_fixture.START_NS`, 2020-01-01 00:00 UTC), one tick per minute. A Session's
cursor starts at that fixture start, so the first tick is reachable immediately and the first full UTC months (January, February, ...) have data.
Idempotent: an existing source with the same tick count is reused."""
import json
import os
from pathlib import Path

DEFAULT_TICKS = 131072        # January + February + March 2020 in full (about three months at one tick per minute)


def _generator(profile):
    """(build_manifest(ticks), iter_events(ticks, manifest), default ticks, seconds per tick, directory prefix) of a source profile."""
    if profile == 'financial-active':
        from execution.research_fixture import START_NS
        from tests.synthetic_financial_monthly import build_manifest, iter_events
        return (lambda t: build_manifest(t, start_ns=START_NS), lambda t, m: iter_events(t, m, start_ns=START_NS), DEFAULT_TICKS, 60, '')
    if profile == 'visual':
        from deploy.local import visual_source as v
        return (lambda t: v.build_manifest(t), lambda t, m: v.iter_events(t, m), v.DEFAULT_TICKS, 12, 'visual-')
    raise SystemExit(f'unknown source profile {profile!r}')


def ensure_source(data_dir, ticks=None, log=print, source_format='compact', profile='financial-active'):
    """Create (or reuse) the source under `<data_dir>/<ticks>/` and return {ticks, datasetId, version, manifestHash, monthly, accepted}.

    source_format='compact' (DEFAULT, owner decision 2026-11-25) stores the ticks ONLY as plain Compact Tick Parquet under `<data_dir>/<ticks>-compact/`;
    'parquet' keeps the older canonical Monthly Parquet under `<data_dir>/<ticks>/` (used by tests and fixtures)."""
    build, events, default_ticks, step_seconds, prefix = _generator(profile)
    ticks = ticks or default_ticks
    if source_format == 'compact':
        return _ensure_compact_source(data_dir, ticks, log, profile)
    if source_format != 'parquet':
        raise SystemExit(f'unknown source format {source_format!r}')
    from contracts.canonical import content_hash
    from market_data.monthly_parquet import MonthlyParquetProvider, write_monthly_parquet
    from ticks import source_acceptance
    base = Path(data_dir) / f'{prefix}{ticks}'
    info_file = base / 'source.json'
    monthly, accepted = base / 'monthly', base / 'accepted'
    manifest, _m, _q = build(ticks)
    version = content_hash(manifest)
    if info_file.exists():
        info = json.loads(info_file.read_text())
        if info.get('version') == version:
            return {**info, 'monthly': str(monthly), 'accepted': str(accepted)}
        raise SystemExit(f'{info_file} holds another dataset version; remove {base} to regenerate')
    base.mkdir(parents=True, exist_ok=True)
    log(f'Generating the synthetic source ({ticks} ticks); this is a one-time step...')
    parquet = write_monthly_parquet(str(monthly), events(ticks, manifest), manifest, expected_version=version, row_group_size=8192)
    provider = MonthlyParquetProvider(str(monthly), expected_dataset_id=manifest['datasetId'], expected_dataset_version=version,
                                      expected_manifest_hash=parquet['manifestHash'])
    source_acceptance.accept_offline(provider, manifest['datasetId'], version, str(accepted))
    info = dict(ticks=ticks, datasetId=manifest['datasetId'], version=version, manifestHash=parquet['manifestHash'], profile=profile, stepSeconds=step_seconds)
    info_file.write_text(json.dumps(info))
    return {**info, 'monthly': str(monthly), 'accepted': str(accepted)}


def _ensure_compact_source(data_dir, ticks, log, profile='financial-active'):
    import shutil
    from contracts.canonical import content_hash
    from market_data.compact_monthly_provider import CompactBackedMonthlyProvider, admission_record, write_adopted_manifest
    from market_data.compact_tick import write_compact
    from market_data.monthly_parquet import write_monthly_parquet
    from ticks import source_acceptance
    build, events, _default, step_seconds, prefix = _generator(profile)
    base = Path(data_dir) / f'{prefix}{ticks}-compact'
    info_file, root, accepted = base / 'source.json', base / 'compact', base / 'accepted'
    manifest, _m, quality = build(ticks)
    version = content_hash(manifest)
    if info_file.exists():
        info = json.loads(info_file.read_text())
        if info.get('version') == version:
            return {**info, 'monthly': str(root), 'accepted': str(accepted)}
        raise SystemExit(f'{info_file} holds another dataset version; remove {base} to regenerate')
    base.mkdir(parents=True, exist_ok=True)
    log(f'Generating the synthetic source as plain Compact Tick Parquet ({ticks} ticks); this is a one-time step...')
    scratch = base / 'reference-monthly'     # temporary: only to compute the canonical row-group hashes; deleted below
    reference = write_monthly_parquet(str(scratch), events(ticks, manifest), manifest, expected_version=version, row_group_size=8192)
    compact = write_compact(str(root), events(ticks, manifest), parent=dict(datasetId=manifest['datasetId'], datasetVersion=version),
                            scale=2, evidence_class='SYNTHETIC_CONTRACT_ONLY', rights={'class': 'SYNTHETIC', 'evidenceHash': None})
    adopted = write_adopted_manifest(root, json.loads((scratch / 'manifest.json').read_bytes()), compact)
    assert reference['manifestHash'] != adopted['manifestHash']            # storage identity differs, canonical authority is identical
    shutil.rmtree(scratch)                                                 # no Monthly Parquet copy is kept
    provider = CompactBackedMonthlyProvider(str(root), admission=admission_record(quality), expected_manifest_hash=adopted['manifestHash'],
                                            expected_compact_manifest_hash=compact['manifestHash'], expected_dataset_id=manifest['datasetId'],
                                            expected_dataset_version=version)
    source_acceptance.accept_offline(provider, manifest['datasetId'], version, str(accepted))
    info = dict(ticks=ticks, datasetId=manifest['datasetId'], version=version, manifestHash=adopted['manifestHash'], format='compact',
                compactManifestHash=compact['manifestHash'], qualityHash=quality, profile=profile, stepSeconds=step_seconds)
    info_file.write_text(json.dumps(info))
    return {**info, 'monthly': str(root), 'accepted': str(accepted)}


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
        **({'BTL_QA_SYNTHETIC_COMPACT_MANIFEST_SHA256': info['compactManifestHash'], 'BTL_QA_SYNTHETIC_COMPACT_QUALITY_SHA256': info['qualityHash']}
           if info.get('format') == 'compact' else {}),
    }
