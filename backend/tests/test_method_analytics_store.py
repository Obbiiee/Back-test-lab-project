"""Synthetic transaction contracts for durable Method Analytics rows."""
import hashlib
import json
import unittest
from unittest.mock import patch

from contracts.primitives import ContractError
from execution.method_analytics_projection import MethodAnalyticsAccumulator
from execution.method_analytics_store import (
    add_session, invalidate_local_session, load_rollup, replace_session,
)


def codec(value):
    raw = json.dumps(value, sort_keys=True, separators=(',', ':')).encode()
    return raw, hashlib.sha256(raw).hexdigest()


def decode(raw, digest):
    raw = bytes(raw)
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ContractError('record', 'CORRUPT_RECORD')
    return json.loads(raw)


def item(session_id, *, revision=1, trade_count=1, net='1'):
    win = trade_count if net != '0' else 0
    breakeven = trade_count if net == '0' else 0
    projection = dict(tradeCount=trade_count, wins=win, losses=0,
        breakeven=breakeven, positive=net, negative='0', net=net,
        durationNs=str(10 * trade_count))
    session = dict(sessionId=session_id, revision=revision,
        datasetId='dataset:one', datasetVersion='d' * 64,
        profileHash='profile:one', engineVersion='observed:v1',
        eventHead='e' * 64, tradeCount=trade_count)
    return dict(unit=('profile:one', 'observed:v1', 'USD'),
        projection=projection, session=session)


class Cursor:
    rowcount = 1

    def __init__(self, row=None):
        self.row = row

    def fetchone(self):
        return self.row


class FakeDb:
    def __init__(self, accumulator):
        payload, digest = codec(accumulator.snapshot())
        self.row = [1, 'READY', accumulator.included_count + accumulator.excluded_count,
                    payload, digest]

    def execute(self, sql, params):
        if sql.startswith('SELECT format_version'):
            return Cursor(tuple(self.row))
        if sql.startswith('UPDATE btl.tick_method_metric_projections'):
            state, count, payload, digest, _workspace, _method = params
            self.row = [1, state, count, payload, digest]
            return Cursor()
        raise AssertionError(sql)


class MethodAnalyticsStoreTests(unittest.TestCase):
    def test_local_session_advance_invalidates_method_rollup_in_same_transaction(self):
        class Db:
            def __init__(self):
                self.statements = []

            def execute(self, sql, params):
                self.statements.append((sql, params))
                if sql.startswith('SELECT method_id'):
                    return Cursor(('method:one',))
                return Cursor()

        db = Db()
        self.assertTrue(invalidate_local_session(db, 'workspace:one', 'session:one'))
        self.assertEqual(len(db.statements), 2)
        self.assertIn("rollup_state='REBUILD_REQUIRED'", db.statements[1][0])
        self.assertEqual(db.statements[1][1], ('workspace:one', 'method:one'))

    def test_unregistered_session_does_not_invalidate_an_unrelated_method(self):
        class Db:
            def __init__(self):
                self.statements = []

            def execute(self, sql, params):
                self.statements.append((sql, params))
                return Cursor(None)

        db = Db()
        self.assertFalse(invalidate_local_session(db, 'workspace:one', 'session:orphan'))
        self.assertEqual(len(db.statements), 1)

    def test_new_session_updates_ready_rollup_in_same_transaction(self):
        accumulator = MethodAnalyticsAccumulator('method:one', 'a' * 64)
        db = FakeDb(accumulator)
        with patch('execution.method_analytics_store._codec', return_value=(codec, decode)):
            self.assertTrue(add_session(db, 'workspace:one', 'method:one', 'a' * 64,
                                        item('session:one')))
            loaded = load_rollup(db, 'workspace:one', 'method:one', 'a' * 64)
        self.assertEqual(loaded['sessionCount'], 1)
        self.assertEqual(loaded['accumulator'].result()['completedTradeNet'], '1')

    def test_session_commit_replaces_one_rollup_contribution(self):
        accumulator = MethodAnalyticsAccumulator('method:one', 'a' * 64)
        accumulator.include(item('session:one'))
        db = FakeDb(accumulator)
        with patch('execution.method_analytics_store._codec', return_value=(codec, decode)):
            self.assertTrue(replace_session(db, 'workspace:one', 'method:one', 'a' * 64,
                item('session:one'), item('session:one', revision=2, trade_count=2, net='3')))
            loaded = load_rollup(db, 'workspace:one', 'method:one', 'a' * 64)
        self.assertEqual(loaded['sessionCount'], 1)
        self.assertEqual(loaded['accumulator'].result()['completedTradeNet'], '3')
        self.assertEqual(loaded['accumulator'].result()['metrics']['tradeCount'], 2)

    def test_rebuild_required_rows_do_not_accept_incremental_updates(self):
        accumulator = MethodAnalyticsAccumulator('method:one', 'a' * 64)
        db = FakeDb(accumulator)
        db.row = [1, 'REBUILD_REQUIRED', 4, None, None]
        with patch('execution.method_analytics_store._codec', return_value=(codec, decode)):
            self.assertFalse(add_session(db, 'workspace:one', 'method:one', 'a' * 64,
                                         item('session:new')))
        self.assertEqual(db.row[1:3], ['REBUILD_REQUIRED', 4])

    def test_snapshot_session_count_mismatch_fails_closed(self):
        accumulator = MethodAnalyticsAccumulator('method:one', 'a' * 64)
        accumulator.include(item('session:one'))
        db = FakeDb(accumulator)
        db.row[2] = 2
        with patch('execution.method_analytics_store._codec', return_value=(codec, decode)):
            with self.assertRaises(ContractError):
                load_rollup(db, 'workspace:one', 'method:one', 'a' * 64)


if __name__ == '__main__':
    unittest.main()
