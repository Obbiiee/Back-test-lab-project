"""Run one hosted synthetic virtual-trader journey cohort on owned QA PostgreSQL.

This is a functional isolation gate, not a concurrent load or capacity test.
Each invocation creates and removes a private local PostgreSQL16 cluster.
"""
import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY))

from tests.virtual_traders import COHORT_SIZES
from deploy.vps.tests.run_private_pg import private_postgres


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--users', type=int, choices=COHORT_SIZES, required=True,
                        help='functional synthetic cohort size; not simultaneous worker count')
    parser.add_argument('--run-id', type=uuid.UUID,
                        help='reuse one UUID across stages to derive disjoint deterministic identities')
    args = parser.parse_args(argv)
    run_id = args.run_id or uuid.uuid4()

    with private_postgres() as (repository, environment):
        environment['BTL_QA_VIRTUAL_TRADER_USERS'] = str(args.users)
        environment['BTL_QA_VIRTUAL_TRADER_RUN_ID'] = str(run_id)
        result = subprocess.run(
            [sys.executable, '-B', '-m', 'unittest',
             'tests.test_cloud_research.CloudResearchTests.test_virtual_traders_complete_isolated_authenticated_journey',
             '-v'],
            cwd=repository, env=environment, timeout=900,
        )

    print(json.dumps({
        'schemaVersion': 1,
        'artifact': 'BTL-VIRTUAL-TRADER-FUNCTIONAL-COHORT-RESULT-1',
        'runId': str(run_id),
        'requestedUsers': args.users,
        'status': 'PASS' if result.returncode == 0 else 'FAIL',
        'executionMode': 'SEQUENTIAL_FUNCTIONAL_JOURNEY',
        'capacityStatus': 'NOT_MEASURED',
        'workerConcurrency': 'NOT_EXERCISED',
        'qaDatabase': 'PRIVATE_TEMPORARY_POSTGRESQL16_REMOVED_AFTER_RUN',
    }, sort_keys=True))
    return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
