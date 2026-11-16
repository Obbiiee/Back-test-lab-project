"""Run one real financial PostgreSQL delta-v3 lifecycle in a private cluster."""
from pathlib import Path
import os
import unittest

from deploy.vps.tests.run_private_pg import private_postgres


def main():
    root=Path(os.environ.get('BTL_QA_DELTA_V3_ROOT','/home/riksora/riksora-qa-evidence/cp6a3-postgres-delta-v3'))
    if root.exists():raise RuntimeError('QA_ROOT_MUST_NOT_EXIST')
    root.mkdir(mode=0o700,parents=True)
    os.environ['BTL_QA_DELTA_V3_REPORT']=str(root/'evidence.json')
    with private_postgres(keep=True,root_dir=root/'postgres') as (repository,environment):
        os.environ.update(environment)
        from tests.test_observed_postgres import ObservedPostgresTests
        # The focused integration test runs alongside this store's legacy PG
        # regressions so the opt-in QA path cannot mask a v1 behavior change.
        suite=unittest.defaultTestLoader.loadTestsFromTestCase(ObservedPostgresTests)
        result=unittest.TextTestRunner(verbosity=2).run(suite)
        (root/'result.txt').write_text(f'testsRun={result.testsRun}\nfailures={len(result.failures)}\nerrors={len(result.errors)}\n')
        if not result.wasSuccessful():return 1
    return 0


if __name__=='__main__':raise SystemExit(main())
