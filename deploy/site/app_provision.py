"""One-time/idempotent provisioning of the public application's SYNTHETIC data and database grants (operator runs it on the VPS).

Generates the deterministic repository-authored synthetic monthly Parquet (TICKS ticks) under ~/prod/data, records the offline source acceptance,
writes the NON-secret application environment ~/prod/app.env, and applies the product's own migrate_and_grant (execution, sandbox-access, support
and identity grants; the runtime role stays restricted and owns nothing)."""
import json, os, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'backend')]
HOME = Path.home()
TICKS = int(os.environ.get('RIKSORA_SYNTH_TICKS', '65536'))
DATA = HOME / 'prod' / 'data'


def main():
    os.umask(0o077)
    from contracts.canonical import content_hash
    from market_data.monthly_parquet import MonthlyParquetProvider, write_monthly_parquet
    from tests.synthetic_financial_monthly import build_manifest, iter_events
    from ticks import source_acceptance
    manifest, _m, _q = build_manifest(TICKS)
    version = content_hash(manifest)
    info_file = DATA / str(TICKS) / 'source.json'
    if not info_file.exists():
        (DATA / str(TICKS)).mkdir(parents=True, exist_ok=True)
        parquet = write_monthly_parquet(str(DATA / str(TICKS) / 'monthly'), iter_events(TICKS, manifest), manifest, expected_version=version, row_group_size=8192)
        prov = MonthlyParquetProvider(str(DATA / str(TICKS) / 'monthly'), expected_dataset_id=manifest['datasetId'], expected_dataset_version=version, expected_manifest_hash=parquet['manifestHash'])
        source_acceptance.accept_offline(prov, manifest['datasetId'], version, str(DATA / str(TICKS) / 'accepted'))
        info_file.write_text(json.dumps(dict(ticks=TICKS, datasetId=manifest['datasetId'], version=version, manifestHash=parquet['manifestHash'])))
    info = json.loads(info_file.read_text())
    (HOME / 'prod' / 'app.env').write_text('\n'.join([
        'BTL_PRODUCT_PROFILE=staging', 'BTL_ENTITLEMENT_ENFORCE=1', 'BTL_ENTITLEMENT_RESET_TIMEZONE=UTC', 'BTL_RESEARCH_WORKERS=3',
        'BTL_QA_SYNTHETIC_MONTHLY_ENABLE=1', f'BTL_QA_SYNTHETIC_MONTHLY_ROOT={DATA / str(TICKS) / "monthly"}', f'BTL_QA_SYNTHETIC_MONTHLY_DATASET_ID={info["datasetId"]}',
        f'BTL_QA_SYNTHETIC_MONTHLY_DATASET_VERSION={info["version"]}', f'BTL_QA_SYNTHETIC_MONTHLY_MANIFEST_SHA256={info["manifestHash"]}',
        'BTL_TICK_SESSION_STORAGE_FORMAT=compact-v1', f'BTL_SOURCE_ACCEPTANCE_DIR={DATA / str(TICKS) / "accepted"}', '']))
    db = dict(line.split('=', 1) for line in (HOME / '.config' / 'riksora-db.env').read_text().split() if '=' in line)
    from deploy.vps.ops import migrate_and_grant
    migrate_and_grant(f"host=127.0.0.1 port=54450 dbname=btl user=btl_owner password={db['PG_OWNER_PASSWORD']}")
    print(f'APPLICATION_DATA_AND_GRANTS_READY synthetic ticks={TICKS} (no market data)')


if __name__ == '__main__':
    main()
