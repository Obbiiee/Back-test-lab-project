"""Bounded, dependency-light tests for the Product V1 order archive wire."""
from copy import deepcopy
import unittest

from contracts.primitives import ContractError
from execution.observed_order_archive_v1 import (
    ARTIFACT,
    PRODUCT_ARTIFACT,
    advance,
    append,
    summary,
    verify_complete,
    verify_record,
)


def terminal(gross='0'):
    return dict(status='CANCELLED', grossPosted=gross, sourceAnchor='event:fixture')


class ProductOrderArchiveContractTests(unittest.TestCase):
    def test_more_than_legacy_limit_round_trips_as_compact_summary(self):
        current = summary(artifact=PRODUCT_ARTIFACT)
        rows = []
        for index in range(4097):
            row = append(
                current,
                session_id='session:product:bounded-test',
                revision=index + 1,
                order_id=f'order:product:{index:04d}',
                order=terminal('1.25'),
                artifact=PRODUCT_ARTIFACT,
            )
            rows.append(row)
            current = advance(current, [row])

        verified = verify_complete(iter(rows), current)
        self.assertEqual(verified['count'], 4097)
        self.assertEqual(verified['summary'], current)
        self.assertEqual(current['grossPosted'], '5121.25')
        self.assertEqual(current['artifact'], PRODUCT_ARTIFACT + '-SUMMARY')

    def test_integrity_and_order_are_checked_on_cold_verification(self):
        current = summary(artifact=PRODUCT_ARTIFACT)
        rows = []
        for index in range(3):
            row = append(current, session_id='session:product:chain', revision=index + 1,
                         order_id=f'order:product:chain:{index}', order=terminal(),
                         artifact=PRODUCT_ARTIFACT)
            rows.append(row)
            current = advance(current, [row])

        for invalid_rows in (rows[:2], [rows[1], rows[0], rows[2]]):
            with self.assertRaises(ContractError):
                verify_complete(invalid_rows, current)

        changed = deepcopy(rows[1])
        changed['order']['grossPosted'] = '9'
        with self.assertRaises(ContractError):
            verify_record(changed)

    def test_qa_artifact_version_is_unchanged(self):
        self.assertEqual(summary()['artifact'], ARTIFACT + '-SUMMARY')


if __name__ == '__main__':
    unittest.main()
