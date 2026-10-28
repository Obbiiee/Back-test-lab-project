"""Pure bounded wire validation for the replay queue's frozen families."""
import unittest

from cloud.queue import replay_command, replay_to_request
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
        self.assertEqual(replay_command(command, command['sessionId']), command)

    def test_observed_replay_command_uses_observed_frozen_schema(self):
        command = self.command('BTL-OBSERVED-EXECUTION-COMMAND-1')
        self.assertEqual(replay_command(command, command['sessionId']), command)

    def test_observed_command_cannot_seek_or_cross_session_scope(self):
        command = self.command('BTL-OBSERVED-EXECUTION-COMMAND-1', 'SEEK')
        with self.assertRaises(ContractError):
            replay_command(command, command['sessionId'])
        command = self.command('BTL-OBSERVED-EXECUTION-COMMAND-1')
        with self.assertRaises(ContractError):
            replay_command(command, 'session:other')

    def test_observed_replay_to_request_is_bounded_and_session_scoped(self):
        raw=dict(schemaVersion=1,artifact='BTL-OBSERVED-REPLAY-TO-1',requestId='a'*32,
                 sessionId='session:2024-01',expectedRevision=3,targetNs='1700000000000000000',timeframe='1m')
        self.assertEqual(replay_to_request(raw,raw['sessionId']),raw)
        invalid=dict(raw,targetNs='01700000000000000000')
        with self.assertRaises(ContractError):replay_to_request(invalid,raw['sessionId'])
        with self.assertRaises(ContractError):replay_to_request(raw,'session:other')


if __name__ == '__main__':
    unittest.main()
