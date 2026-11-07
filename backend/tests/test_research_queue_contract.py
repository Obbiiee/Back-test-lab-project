"""Pure bounded wire validation for the replay queue's frozen families."""
import unittest

from cloud.queue import _persisted_session_artifact, replay_command, replay_to_request
from contracts.canonical import canonical_bytes
from contracts.primitives import ContractError


class ReplayQueueContractTests(unittest.TestCase):
    def command(self, artifact, kind='ADVANCE'):
        payload = {'targetNs': '1700000000000000000'} if kind in ('ADVANCE', 'SEEK') else {}
        return {
            'schemaVersion': 1,
            'artifact': artifact,
            'sessionId': 'session:2024-01',
            'commandId': 'command:2024-01:advance',
            'expectedRevision': 0,
            'kind': kind,
            'payload': payload,
        }

    def test_legacy_replay_command_remains_accepted(self):
        command = self.command('BTL-TICK-EXECUTION-COMMAND-1', 'SEEK')
        self.assertEqual(replay_command(command, command['sessionId'], 'BTL-LOCAL-SESSION-1'), command)

    def test_observed_replay_command_uses_observed_frozen_schema(self):
        command = self.command('BTL-OBSERVED-EXECUTION-COMMAND-1')
        self.assertEqual(replay_command(command, command['sessionId'], 'BTL-OBSERVED-RESEARCH-SESSION-1'), command)

    def test_observed_command_cannot_seek_or_cross_session_scope(self):
        command = self.command('BTL-OBSERVED-EXECUTION-COMMAND-1', 'SEEK')
        with self.assertRaises(ContractError):
            replay_command(command, command['sessionId'], 'BTL-OBSERVED-RESEARCH-SESSION-1')
        command = self.command('BTL-OBSERVED-EXECUTION-COMMAND-1')
        with self.assertRaises(ContractError):
            replay_command(command, 'session:other', 'BTL-OBSERVED-RESEARCH-SESSION-1')

    def test_session_metadata_selects_dialect_and_unknown_models_fail_closed(self):
        legacy = self.command('BTL-TICK-EXECUTION-COMMAND-1')
        observed = self.command('BTL-OBSERVED-EXECUTION-COMMAND-1')
        with self.assertRaises(ContractError):
            replay_command(legacy, legacy['sessionId'], 'BTL-OBSERVED-RESEARCH-SESSION-1')
        with self.assertRaises(ContractError):
            replay_command(observed, observed['sessionId'], 'BTL-LOCAL-SESSION-1')
        for raw, model in ((legacy, 'BTL-UNKNOWN-SESSION-1'),
                           (legacy, 'BTL-OBSERVED-RESEARCH-SESSION-1')):
            with self.assertRaises(ContractError):
                replay_command(raw, raw['sessionId'], model)

    def test_observed_replay_to_request_is_bounded_and_session_scoped(self):
        raw=dict(schemaVersion=1,artifact='BTL-OBSERVED-REPLAY-TO-1',requestId='a'*32,
                 sessionId='session:2024-01',expectedRevision=3,targetNs='1700000000000000000',timeframe='1m')
        self.assertEqual(replay_to_request(raw,raw['sessionId']),raw)
        invalid=dict(raw,targetNs='01700000000000000000')
        with self.assertRaises(ContractError):replay_to_request(invalid,raw['sessionId'])
        with self.assertRaises(ContractError):replay_to_request(raw,'session:other')

    def test_command_family_is_resolved_only_from_hash_verified_workspace_session(self):
        import hashlib

        class DB:
            def __init__(self, metadata, claimed_hash=None):
                payload = canonical_bytes(metadata)
                self.row = {'payload': payload, 'content_hash': claimed_hash or hashlib.sha256(payload).hexdigest()}
            def execute(self, query, params):
                self.asserted = (query, params)
                return self
            def fetchone(self):
                return self.row

        for artifact in ('BTL-LOCAL-SESSION-1', 'BTL-OBSERVED-RESEARCH-SESSION-1'):
            db = DB({'schemaVersion': 1, 'artifact': artifact, 'id': 'session:qa'})
            self.assertEqual(_persisted_session_artifact(db, 'workspace:qa', 'session:qa'), artifact)
            self.assertEqual(db.asserted[1], ('workspace:qa', 'session:qa'))
        unsupported = DB({'schemaVersion': 1, 'artifact': 'BTL-UNKNOWN-SESSION-1', 'id': 'session:qa'})
        with self.assertRaises(ContractError):
            _persisted_session_artifact(unsupported, 'workspace:qa', 'session:qa')
        corrupt = DB({'schemaVersion': 1, 'artifact': 'BTL-LOCAL-SESSION-1', 'id': 'session:qa'}, '0' * 64)
        with self.assertRaises(ContractError):
            _persisted_session_artifact(corrupt, 'workspace:qa', 'session:qa')


if __name__ == '__main__':
    unittest.main()
