"""One-time/idempotent provisioning of the public application's SYNTHETIC data and database grants (operator runs it on the VPS).

Generates the deterministic repository-authored synthetic ticks as plain Compact Tick Parquet (TICKS ticks) under ~/prod/data, records the offline source acceptance,
writes the NON-secret application environment ~/prod/app.env, and applies the product's own migrate_and_grant (execution, sandbox-access, support
and identity grants; the runtime role stays restricted and owns nothing)."""
import json, os, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'backend')]
HOME = Path.home()
TICKS = int(os.environ.get('RIKSORA_SYNTH_TICKS', '131072'))
DATA = HOME / 'prod' / 'data'


PROFILE_ENV = {'BTL_PRODUCT_PROFILE': 'staging', 'BTL_ENTITLEMENT_ENFORCE': '1', 'BTL_ENTITLEMENT_RESET_TIMEZONE': 'UTC', 'BTL_RESEARCH_WORKERS': '3'}
COMPACT_KEYS = ('BTL_QA_SYNTHETIC_COMPACT_MANIFEST_SHA256', 'BTL_QA_SYNTHETIC_COMPACT_QUALITY_SHA256')


def managed_env(info):
    """The environment this script owns: product profile + the pinned synthetic source (Compact pins only when the source is Compact)."""
    from deploy.local.synthetic_source import source_environment
    return {**PROFILE_ENV, **source_environment(info)}


def merge_env(existing_text, managed):
    """Keys this script does not own survive a re-run (for example BTL_TICK_CHECKPOINT_FORMAT set by v2_promote.sh); stale Compact pins never do."""
    kept = {}
    for line in existing_text.splitlines():
        if '=' in line:
            key, value = line.split('=', 1)
            if key not in managed and key not in COMPACT_KEYS:
                kept[key] = value
    return {**managed, **kept}


def main():
    os.umask(0o077)
    from deploy.local.synthetic_source import ensure_source
    info = ensure_source(DATA, TICKS)       # plain Compact Tick Parquet by default; starts at the product fixture start (2020-01-01)
    env_file = HOME / 'prod' / 'app.env'
    merged = merge_env(env_file.read_text() if env_file.exists() else '', managed_env(info))
    env_file.write_text('\n'.join(f'{k}={v}' for k, v in merged.items()) + '\n')
    db = dict(line.split('=', 1) for line in (HOME / '.config' / 'riksora-db.env').read_text().split() if '=' in line)
    from deploy.vps.ops import migrate_and_grant
    migrate_and_grant(f"host=127.0.0.1 port=54450 dbname=btl user=btl_owner password={db['PG_OWNER_PASSWORD']}")
    print(f'APPLICATION_DATA_AND_GRANTS_READY synthetic ticks={TICKS} (no market data)')


if __name__ == '__main__':
    main()
