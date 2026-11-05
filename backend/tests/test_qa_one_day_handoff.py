from copy import deepcopy
import unittest
from tests.qa_one_day_handoff import baseline_gate


class OneDayHandoffTests(unittest.TestCase):
    def fixture(self):
        parity={'financialStateSha256':'a'*64,'semanticFinancialEventSha256':'b'*64}
        result=dict(status='PASS',dayGroups=137108,canonicalHash='c'*64,transactionParity=parity)
        report=dict(status='PASS',timestampGroupCount=137108,coldResume={'status':'PASS'},
                    idempotencyRetry='PASS',independentVerification={'status':'PASS'},parity=parity)
        return result,{k:deepcopy(report) for k in ['sqlite','single','daily']},dict(dayGroups=137108,canonicalDayHash='c'*64)

    def test_active_worker_always_waits(self):
        self.assertEqual(baseline_gate(True,None,{},{}),'WAIT')

    def test_synthetic_complete_fixture_passes_without_real_state_mutation(self):
        self.assertEqual(baseline_gate(False,*self.fixture()),'PASS')

    def test_exit_without_pass_is_refused(self):
        with self.assertRaisesRegex(ValueError,'NOT_PASS'):baseline_gate(False,None,{}, {})

    def test_financial_difference_is_refused(self):
        result,reports,manifest=self.fixture();reports['daily']['parity']['financialStateSha256']='d'*64
        with self.assertRaisesRegex(ValueError,'TRANSACTION_HASH_FAILED'):baseline_gate(False,result,reports,manifest)

    def test_missing_recovery_gate_is_refused(self):
        result,reports,manifest=self.fixture();reports['single']['coldResume']['status']='FAIL'
        with self.assertRaisesRegex(ValueError,'GATE'):baseline_gate(False,result,reports,manifest)
