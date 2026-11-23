"""One-time/idempotent provisioning of the public application's SYNTHETIC data and database grants (operator runs it on the VPS).

Generates the deterministic repository-authored synthetic monthly Parquet (TICKS ticks) under ~/prod/data, records the offline source acceptance,
writes the NON-secret application environment ~/prod/app.env, and applies the product's own migrate_and_grant (execution, sandbox-access, support
and identity grants; the runtime role stays restricted and owns nothing)."""
import json, os, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'backend')]
HOME = Path.home()
TICKS = int(os.environ.get('RIKSORA_SYNTH_TICKS', '131072'))
DATA = HOME / 'prod' / 'data'


def main():
    os.umask(0o077)
    from deploy.local.synthetic_source import ensure_source
    info = ensure_source(DATA, TICKS)       # starts at the product fixture start (2020-01-01), so the first month has data from the first tick
    managed = {
        'BTL_PRODUCT_PROFILE': 'staging', 'BTL_ENTITLEMENT_ENFORCE': '1', 'BTL_ENTITLEMENT_RESET_TIMEZONE': 'UTC', 'BTL_RESEARCH_WORKERS': '3',
        'BTL_QA_SYNTHETIC_MONTHLY_ENABLE': '1', 'BTL_QA_SYNTHETIC_MONTHLY_ROOT': info['monthly'], 'BTL_QA_SYNTHETIC_MONTHLY_DATASET_ID': info['datasetId'],
        'BTL_QA_SYNTHETIC_MONTHLY_DATASET_VERSION': info['version'], 'BTL_QA_SYNTHETIC_MONTHLY_MANIFEST_SHA256': info['manifestHash'],
        'BTL_TICK_SESSION_STORAGE_FORMAT': 'compact-v1', 'BTL_SOURCE_ACCEPTANCE_DIR': info['accepted']}
    env_file = HOME / 'prod' / 'app.env'
    kept = {}                                  # keys this script does not own (for example BTL_TICK_CHECKPOINT_FORMAT set by v2_promote.sh) survive a re-run
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if '=' in line and line.split('=', 1)[0] not in managed:
                kept[line.split('=', 1)[0]] = line.split('=', 1)[1]
    env_file.write_text('\n'.join([f'{k}={v}' for k, v in {**managed, **kept}.items()]) + '\n')
    db = dict(line.split('=', 1) for line in (HOME / '.config' / 'riksora-db.env').read_text().split() if '=' in line)
    from deploy.vps.ops import migrate_and_grant
    migrate_and_grant(f"host=127.0.0.1 port=54450 dbname=btl user=btl_owner password={db['PG_OWNER_PASSWORD']}")
    print(f'APPLICATION_DATA_AND_GRANTS_READY synthetic ticks={TICKS} (no market data)')


if __name__ == '__main__':
    main()
