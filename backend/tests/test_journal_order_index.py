import json
import unittest

from contracts.primitives import ContractError
from execution.journal_order_index import (append, references, PROJECTION_ARTIFACT,
                                           _new_order, _apply_order_event)
from contracts.canonical import canonical_bytes, content_hash
from execution.analysis import project
from execution.postgres import pack
from execution.research import ResearchApplication
from types import SimpleNamespace
from unittest.mock import patch
from tests.test_execution_goldens import goldens
from tests.test_tick_execution import exercise


def event(kind, sequence, order_id=None, **detail):
    return dict(schemaVersion=1, kind=kind, sequence=sequence, eventId=f'{sequence:064x}',
                sessionId='session:a', orderId=order_id, detail=detail)


class JournalOrderIndexTests(unittest.TestCase):
    def test_incremental_order_projection_matches_every_financial_golden(self):
        for case in goldens()['scenarios']:
            with self.subTest(case=case['id']):
                harness = exercise(case)
                state = harness.state
                events = harness.store.events[(harness.scope.workspace_id, harness.session)]
                indexed_orders = {}
                for event_record in events:
                    for order_id, _sequence, _event_id, _kind in references([event_record]):
                        if event_record['kind'] == 'ORDER_ACCEPTED':
                            indexed_orders[order_id] = _new_order(harness.session, order_id, event_record)
                        else:
                            indexed_orders[order_id] = _apply_order_event(
                                indexed_orders[order_id], event_record)
                full = project(state, events, None)
                expected = {}
                for order in full['orders']:
                    base = dict(order)
                    base.pop('exitRequested', None)
                    base.pop('unrealizedIndicative', None)
                    expected[order['id']] = base
                self.assertEqual(indexed_orders, expected)

    def test_references_cover_order_lifecycle_and_global_unresolved_events(self):
        events = [
            event('ORDER_ACCEPTED', 0, 'order:one', plan={}),
            event('ENTRY_FILL', 1, 'order:one', price='10'),
            event('UNRESOLVED', 2, None, affectedOrderIds=['order:one', 'order:two']),
        ]
        self.assertEqual(references(events), [
            ('order:one', 0, f'{0:064x}', 'ORDER_ACCEPTED'),
            ('order:one', 1, f'{1:064x}', 'ENTRY_FILL'),
            ('order:one', 2, f'{2:064x}', 'UNRESOLVED'),
            ('order:two', 2, f'{2:064x}', 'UNRESOLVED'),
        ])

    def test_missing_head_refuses_partial_index_claim_for_legacy_session(self):
        class DB:
            def __init__(self):
                self.statements = []

            def execute(self, query, params):
                self.statements.append((query, params))

                class Result:
                    def fetchone(self):
                        return None

                return Result()

        db = DB()
        state = {'nextEventIndex': 4, 'eventHash': 'a' * 64}
        self.assertFalse(append(db, 'workspace:a', 'session:a', state, state, []))
        self.assertEqual(len(db.statements), 1)

    def test_append_requires_exact_prior_head_then_advances_atomically(self):
        class Result:
            def __init__(self, row=None, rows=None):
                self.row = row
                self.rows = rows or []

            def fetchone(self):
                return self.row

            def fetchall(self):
                return self.rows

        class DB:
            def __init__(self, row):
                self.row = row
                self.statements = []

            def execute(self, query, params):
                self.statements.append((query, params))
                if 'SELECT through_sequence,event_hash,order_count' in query:
                    return Result(self.row)
                return Result(rows=[])

        prior = {'nextEventIndex': 7, 'eventHash': 'b' * 64}
        following = {'nextEventIndex': 10, 'eventHash': 'c' * 64}
        rows = [
            event('ORDER_ACCEPTED', 7, 'order:a', plan={'quantity': '1', 'side': 'LONG'}),
            event('ENTRY_FILL', 8, 'order:a', quantity='1', price='10', commission='0',
                  balanceDelta='0', evidence={'timeNs': '10', 'groupId': 'g:entry',
                                              'eventIds': ['tick:entry']}),
            event('EXIT_FILL', 9, 'order:a', entryFillRef=f'{8:064x}', quantity='1', price='11',
                  remaining='0', gross='0', commission='0', balanceDelta='0',
                  reason='MANUAL', evidence={'timeNs': '20', 'groupId': 'g:exit',
                                            'eventIds': ['tick:exit']}),
        ]
        db = DB((7, 'b' * 64, 0))
        self.assertTrue(append(db, 'workspace:a', 'session:a', prior, following, rows))
        self.assertEqual(len(db.statements), 7)  # head, row lookup, three refs, projection, head advance
        projection_write = next(item for item in db.statements
                                if 'INSERT INTO btl.tick_journal_order_projection' in item[0])
        projection = json.loads(projection_write[1][6])
        self.assertEqual(projection['artifact'], PROJECTION_ARTIFACT)
        self.assertEqual(projection['order']['status'], 'CLOSED')
        self.assertEqual(projection['order']['net'], '0')
        self.assertEqual(projection['contentHash'], content_hash(
            {key: value for key, value in projection.items() if key != 'contentHash'}))
        self.assertEqual(canonical_bytes(projection), projection_write[1][6])
        self.assertIn('UPDATE btl.tick_journal_projection_heads', db.statements[-1][0])
        self.assertEqual(db.statements[-1][1], (10, 'c' * 64, 1, 'workspace:a', 'session:a'))

        mismatched = DB((6, 'a' * 64, 0))
        with self.assertRaises(ContractError):
            append(mismatched, 'workspace:a', 'session:a', prior, following, rows)
        self.assertEqual(len(mismatched.statements), 1)

    def test_indexed_page_uses_only_the_selected_order_projection(self):
        session_id = 'session:a'
        order_id = 'order:a'
        accepted = event('ORDER_ACCEPTED', 0, order_id, plan={'quantity': '1', 'side': 'LONG'})
        cancelled = event('ORDER_CANCELLED', 1, order_id)
        cancelled.update(datasetId='dataset:a', datasetVersion='v1', profileHash='f' * 64,
                         methodHash='e' * 64, engineVersion='engine:v1')
        cancelled['eventId'] = content_hash({key: value for key, value in cancelled.items()
                                             if key != 'eventId'})
        base = _new_order(session_id, order_id, accepted)
        order = _apply_order_event(base, cancelled)
        projection = dict(schemaVersion=1, formatVersion=1,
            artifact=PROJECTION_ARTIFACT, sessionId=session_id, orderId=order_id,
            lastSequence=1, eventId=cancelled['eventId'], order=order)
        projection['contentHash'] = content_hash(projection)
        projection_raw, projection_digest = pack(projection)
        event_raw, event_digest = pack(cancelled)
        page_row = (order_id, 'CANCELLED', 1, cancelled['eventId'], projection_raw,
                    projection_digest, 'ORDER_CANCELLED', projection['contentHash'],
                    event_raw, event_digest)

        class Result:
            def __init__(self, row=None, rows=None):
                self.row = row
                self.rows = rows or []

            def fetchone(self):
                return self.row

            def fetchall(self):
                return self.rows

        class DB:
            def execute(self, query, _params):
                if 'FROM btl.tick_journal_projection_heads' in query:
                    return Result((1, 2, cancelled['eventId'], 1))
                if 'FROM btl.tick_journal_order_projection p' in query:
                    return Result(rows=[page_row])
                raise AssertionError('indexed path must not scan the financial event ledger')

        app = ResearchApplication.__new__(ResearchApplication)
        app.scope = SimpleNamespace(workspace_id='workspace:a')
        state = dict(sessionId=session_id, revision=2, nextEventIndex=2,
            eventHash=cancelled['eventId'], unresolved=False, throughNs='10',
            datasetId='dataset:a', datasetVersion='v1', engineVersion='engine:v1',
            profileHash='f' * 64, policy={'definitionHash': 'e' * 64},
            profile={'contractSize': '1'}, orders={}, parent=None)
        with patch.object(app, '_quote', return_value=None), \
             patch.object(app, '_research_risk'), \
             patch('execution.research.project', side_effect=AssertionError('full ledger fold')):
            result = app._indexed_journal_page(DB(), state, None, None, 32)

        self.assertEqual(result['total'], 1)
        self.assertFalse(result['more'])
        expected_order = dict(order, excursionReason='POSITION_NOT_COMPLETED')
        self.assertEqual(result['analysis']['orders'], [expected_order])


if __name__ == '__main__':
    unittest.main()
