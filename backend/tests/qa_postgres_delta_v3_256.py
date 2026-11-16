"""Run the isolated legacy-vs-QA-v3 256-order PostgreSQL scale gate."""
import io
import json
import os
from pathlib import Path
import shutil
import sys
import unittest

from deploy.vps.tests.run_private_pg import private_postgres


def main():
    root_text = os.environ.get('BTL_QA_DELTA_V3_SCALE_ROOT')
    if not root_text:
        raise RuntimeError('SET_BTL_QA_DELTA_V3_SCALE_ROOT_TO_NEW_EMPTY_PATH')
    root = Path(root_text)
    if root.exists():
        raise RuntimeError('QA_ROOT_MUST_NOT_EXIST')
    if shutil.disk_usage(root.parent).free < 30 * 1024**3:
        raise RuntimeError('PREFLIGHT_DISK_RESERVE_BELOW_30_GIB')
    root.mkdir(mode=0o700, parents=False)
    os.chmod(root, 0o700)
    affinity = sorted(os.sched_getaffinity(0)) if hasattr(os, 'sched_getaffinity') else None
    if affinity:
        os.sched_setaffinity(0, {affinity[0]})
    (root / 'preflight.json').write_text(json.dumps(dict(
        availableDiskBytes=shutil.disk_usage(root).free,
        cpuAffinity=sorted(os.sched_getaffinity(0)) if hasattr(os, 'sched_getaffinity') else None,
        artifactLimitBytes=512 * 1024 * 1024, ramLimitBytes=1024 * 1024 * 1024,
        wallLimitSeconds=900, diskReserveBytes=30 * 1024**3), sort_keys=True, indent=2) + '\n')
    output = io.StringIO()
    status = 1
    try:
        with private_postgres(keep=True, root_dir=root / 'postgres') as (repository, environment):
            os.environ.update(environment)
            os.environ['BTL_QA_DELTA_V3_SCALE_ROOT'] = str(root)
            os.environ['BTL_QA_DELTA_V3_SCALE_REPORT'] = str(root / 'evidence.json')
            os.environ['BTL_QA_DELTA_V3_REPORT'] = str(root / 'small-financial-regression.json')
            from tests.test_observed_postgres_256_order import ObservedDeltaV3OrderScaleTests
            from tests.test_observed_postgres import ObservedPostgresTests
            suite = unittest.TestSuite([
                ObservedDeltaV3OrderScaleTests('test_256_order_legacy_vs_qa_v3_with_cold_resume_and_post_commit_kill'),
                ObservedDeltaV3OrderScaleTests('test_qa_v3_short_sl_matches_legacy_and_cold_resume'),
                ObservedPostgresTests('test_qa_v3_postgres_delta_atomic_financial_parity_and_recovery'),
            ])
            result = unittest.TextTestRunner(stream=output, verbosity=2).run(suite)
            status = 0 if result.wasSuccessful() else 1
        (root / 'result.txt').write_text(output.getvalue())
    except BaseException as exc:
        (root / 'result.txt').write_text(output.getvalue() +
            f'\nRUNNER_ERROR={type(exc).__name__}: {exc}\n')
        raise
    print(output.getvalue(), end='')
    print('EVIDENCE_ROOT=' + str(root), flush=True)
    return status


if __name__ == '__main__':
    raise SystemExit(main())
