"""Product archive + progress cold reads, using real reducers and mocked SQL."""
from unittest.mock import MagicMock
import unittest

from application.models import TrustedScope
from contracts.canonical import content_hash
from contracts.primitives import ContractError
from execution.observed_kernel import PRODUCT_ORDER_RETENTION_V1, seed_state, apply, validate_snapshot
from execution.observed_postgres import ObservedExecutionStore, PROGRESS_FORMAT, PROGRESS_BASE, PROGRESS_POINTER
from execution.observed_replay_progress import replace_progress, read_progress, progress_receipt
from execution.observed_state_delta_v3 import encode_compact_base
from execution.postgres import pack
from tests import test_observed_kernel as fixtures
from ticks.timeline_v2 import IndexedTickTimeline


class ProductProgressCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.fx = fixtures.ObservedKernelTests(); self.fx.setUp()
        self.addCleanup(self.fx.tearDown)
        self.fx.setup_stream([(0, '2300', '2300.1'), (10**9, '2301', '2301.1')])
        provider = self.fx.provider
        version = provider.dataset_version
        root = provider.describe_v2(provider.dataset_id, version)['root']
        pin = dict(schemaVersion=1, artifact='BTL-QA-SHARED-SOURCE-PIN-1', datasetId=provider.dataset_id,
            datasetVersion=version, manifestHash=version, rootHash=version, indexContentHash=root['indexContentHash'],
            archiveSha256='a'*64, qualificationReceiptSha256='b'*64)
        self.timeline = IndexedTickTimeline(provider, provider.dataset_id, version, '0',
            log_folder=self.fx.root/'shared', storage_mode='shared-source-v2', source_pin=pin)
        self.fx.handles.append(self.timeline)
        self.cp = self.timeline.checkpoint()
        self.policy = PRODUCT_ORDER_RETENTION_V1
        self.state = seed_state('session:product', self.fx.profile, self.fx.policy, self.cp,
            order_retention_policy=self.policy, product_order_archive_v1=True)
        self.scope = TrustedScope('workspace:test', 'actor:test')
        self.store = ObservedExecutionStore('unused', state_storage_format=PROGRESS_FORMAT,
            product_order_archive_v1=True, order_retention_policy=self.policy)

    def test_product_progress_round_trip_retry_and_financial_mutation_refusal(self):
        base = validate_snapshot(self.state, self.cp, order_retention_policy=self.policy)
        frame = self.timeline.advance_through(str(10**9), self.timeline.cursor)
        cp = self.timeline.checkpoint()
        command = dict(schemaVersion=1, artifact='BTL-OBSERVED-EXECUTION-COMMAND-1', sessionId='session:product',
            commandId='command:advance', expectedRevision=0, kind='ADVANCE', payload={'targetNs': str(10**9)})
        after, events, archive = apply(self.state, command, reveal=frame, checkpoint=cp,
            order_retention_policy=self.policy, product_order_archive_v1=True, archived_order_lookup=lambda _: None)
        self.assertEqual(archive, [])
        proposed = validate_snapshot(after, cp, order_retention_policy=self.policy)
        db = MagicMock()
        db.execute.side_effect = [MagicMock(**{'fetchone.return_value': (0,)}),
            MagicMock(**{'fetchone.return_value': None}), MagicMock()]
        receipt = replace_progress(db, self.scope, base, 'a'*64, command, proposed, events,
            order_retention_policy=self.policy)
        params = db.execute.call_args.args[1]
        reader = MagicMock()
        reader.execute.return_value.fetchone.return_value = params[2:]
        restored = read_progress(reader, self.scope, base, 'a'*64, order_retention_policy=self.policy)
        self.assertEqual(restored['state'], receipt['state'])
        self.assertEqual(restored['state']['orderArchive'], self.state['orderArchive'])
        self.assertEqual(progress_receipt(reader, self.scope, base, 'a'*64, command,
            order_retention_policy=self.policy), receipt)
        with self.assertRaises(ContractError):
            read_progress(reader, self.scope, base, 'a'*64)  # No implicit Product policy promotion.
        db = MagicMock()
        db.execute.side_effect = [MagicMock(**{'fetchone.return_value': (0,)}),
            MagicMock(**{'fetchone.return_value': None})]
        bad = dict(proposed, state=dict(after, balance='10001', initialBalance='10001'))
        with self.assertRaises(ContractError) as error:
            replace_progress(db, self.scope, base, 'a'*64, command, bad, events,
                order_retention_policy=self.policy)
        self.assertEqual(error.exception.code, 'REFUSED_FINANCIAL_PROGRESS')

    def database(self, archive_tip=None):
        base = encode_compact_base(self.state)
        base.update(artifact=PROGRESS_BASE, ordinal=0, recoveryRevision=0,
            chainHash=base['stateHash'], controller=self.cp)
        base_row = pack(base)
        pointer = pack(dict(schemaVersion=1, artifact=PROGRESS_POINTER, revision=0, checkpointHash=base_row[1]))
        db = MagicMock()
        def query(sql, params):
            cursor = MagicMock()
            if 'FROM btl.tick_sessions' in sql:
                cursor.fetchone.return_value = (*pointer, 0, self.state['datasetVersion'], self.state['profileHash'])
            elif 'FROM btl.tick_checkpoints' in sql:
                cursor.fetchone.return_value = base_row
                cursor.fetchall.return_value = []
            elif 'FROM btl.observed_replay_progress' in sql:
                cursor.fetchone.return_value = None
            elif 'FROM btl.tick_terminal_order_archive_v1' in sql:
                cursor.fetchone.return_value = archive_tip
            else:
                self.fail('Unexpected SQL: '+sql)
            return cursor
        db.execute.side_effect = query
        return db

    def test_product_cold_read_validates_policy_and_archive_tip(self):
        db = self.database()
        snapshot, format_, chain = self.store._read(db, self.scope.workspace_id, 'session:product', include_format=True)
        self.assertEqual(snapshot['state'], self.state)
        self.assertEqual(format_, PROGRESS_FORMAT)
        self.assertEqual(chain, content_hash(self.state))
        self.assertTrue(any('FROM btl.tick_terminal_order_archive_v1' in call.args[0]
            for call in db.execute.call_args_list))

    def test_product_cold_read_rejects_an_archive_tip_outside_the_summary(self):
        with self.assertRaises(ContractError) as error:
            self.store._read(self.database((0, 'b'*64)), self.scope.workspace_id, 'session:product')
        self.assertEqual(error.exception.field, 'archiveTip')
