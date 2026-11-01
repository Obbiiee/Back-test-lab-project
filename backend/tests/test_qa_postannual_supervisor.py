import json
import os
from pathlib import Path
import tempfile
import unittest

from tests.qa_postannual_supervisor import MIN_FREE_BYTES, SOURCE_ID, SOURCE_SHA256, poll_once


def annual_reports(root):
    root = Path(root)
    handoff = root/'annual-handoff.json'
    annual = root/'annual.json'
    handoff.write_text(json.dumps(dict(status='PASS_ADVANCING',stage='annual',
        sourceRights='UNKNOWN',executionEligibility='NOT_GRANTED')))
    annual.write_text(json.dumps(dict(status='PASS',continuousDays=366,
        tickCount=56_208_511,timestampGroupCount=56_208_511,
        timelineStorageMode='shared-source-v1',datasetId=SOURCE_ID,archiveSha256=SOURCE_SHA256,
        sessionId='synthetic:fixture',revision=11,sourceRights='UNKNOWN',executionEligibility='NOT_GRANTED',
        independentVerification=dict(status='PASS',independentTimestampGroups=56_208_511,
            tradeFinancialReconciliation='PASS',independentlyMatchedFills=3,entryFills=1,exitFills=2),
        replayBatch=dict(durableReceiptVerification=dict(status='PASS',commands=11,ledgerSha256='receipt-hash')),
        coldResume=dict(status='PASS',processRestarted=True),idempotencyRetry='PASS',
        parity=dict(receiptLedgerSha256='receipt-hash',eventTranscriptSha256='event-hash'),
        measured=dict(cpuSeconds=1234),completedTradeCount=17,
        storage=dict(totalQaArtifactBytes=1000,perSessionTimelineAllocatedBytes=100,
                     sharedCanonicalDatasetAllocatedBytes=2000))))
    # Test-specific value is validated through the pass path; never written to the live evidence root.
    data=json.loads(annual.read_text());data['datasetId']=SOURCE_ID
    annual.write_text(json.dumps(data))
    return handoff, annual


class PostannualSupervisorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='riksora-postannual-test-')
        self.root = Path(self.temp.name)
        self.handoff, self.annual = annual_reports(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def show(self, active='active', result='success'):
        return lambda _unit, prop: active if prop == 'ActiveState' else result

    def test_active_annual_waits_and_does_not_launch_load(self):
        def forbidden(*_args, **_kwargs):
            raise AssertionError('load stage must not start while annual is active')
        state=poll_once(self.root/'state', 'annual.service', self.handoff, self.annual,
                        '/missing/runner', self.show(active='active'), forbidden)
        self.assertEqual(state['status'],'RUNNING')
        self.assertEqual(state['stage'],'waiting-annual')

    def test_annual_failure_stops_without_running_load(self):
        state=poll_once(self.root/'state','annual.service',self.handoff,self.annual,
                        '/missing/runner',self.show(active='failed',result='exit-code'))
        self.assertEqual(state['status'],'STOPPED_NEEDS_OWNER')
        self.assertEqual(state['errorCode'],'ANNUAL_SYSTEMD_RESULT_NOT_SUCCESS')

    def test_systemd_success_without_independent_pass_stops(self):
        data=json.loads(self.annual.read_text());data['timestampGroupCount']-=1
        self.annual.write_text(json.dumps(data))
        state=poll_once(self.root/'state','annual.service',self.handoff,self.annual,
                        '/missing/runner',self.show(active='inactive'))
        self.assertEqual(state['status'],'STOPPED_NEEDS_OWNER')
        self.assertEqual(state['errorCode'],'ANNUAL_SOURCE_GROUP_COVERAGE_MISMATCH')

    def test_annual_pass_runs_only_sequential_verified_load_stages_once(self):
        runner=self.root/'load-runner';runner.write_text('#!/bin/sh\nexit 0\n');runner.chmod(0o700)
        invocations=[]
        def run(argv,**kwargs):
            users=int(argv[3]);invocations.append(users)
            report=Path(argv[5])/'report.json'
            report.write_text(json.dumps(dict(status='PASS',concurrentSessions=users,
                sharedSourceMode='shared-source-v1',sourceDatasetId=SOURCE_ID,sourceSha256=SOURCE_SHA256,
                sessionIsolation='PASS',financialIntegrity='PASS',
                eventIntegrity='PASS',coldRecovery='PASS',failedRequests=0,
                minimumFreeBytesObserved=MIN_FREE_BYTES,cpuLimitCores=1,memoryLimitBytes=1024**3,
                swapLimitBytes=0,cpuSeconds=users,peakRamBytes=users*1000,postgresBytes=users*100,
                postgresContentionMs=0.5,
                incrementalDiskBytes=users*50,commandLatencyMs=dict(p50=1.0,p95=2.0))))
            return type('Result',(),{'returncode':0})()
        state=poll_once(self.root/'state','annual.service',self.handoff,self.annual,
                        runner,self.show(active='inactive'),run)
        self.assertEqual(invocations,[10,50,100])
        self.assertEqual(state['status'],'COMPLETE_PENDING_OWNER_REVIEW')
        second=poll_once(self.root/'state','annual.service',self.handoff,self.annual,
                         runner,self.show(active='inactive'),run)
        self.assertEqual(second['status'],'COMPLETE_PENDING_OWNER_REVIEW')
        self.assertEqual(invocations,[10,50,100])
        self.assertTrue((self.root/'state'/'unit-economics.json').is_file())
        self.assertTrue((self.root/'state'/'status.md').is_file())
        self.assertTrue((self.root/'state'/'supervisor.log').is_file())

    def test_corrupt_load_report_stops_before_next_concurrency(self):
        runner=self.root/'load-runner';runner.write_text('#!/bin/sh\nexit 0\n');runner.chmod(0o700)
        invocations=[]
        def run(argv,**kwargs):
            users=int(argv[3]);invocations.append(users)
            Path(argv[5],'report.json').write_text(json.dumps(dict(status='FAIL',concurrentSessions=users)))
            return type('Result',(),{'returncode':0})()
        state=poll_once(self.root/'state','annual.service',self.handoff,self.annual,
                        runner,self.show(active='inactive'),run)
        self.assertEqual(invocations,[10])
        self.assertEqual(state['status'],'STOPPED_NEEDS_OWNER')

    def test_lock_prevents_duplicate_supervisor(self):
        state_root=self.root/'state';state_root.mkdir()
        fd=os.open(state_root/'supervisor.lock',os.O_RDWR|os.O_CREAT,0o600)
        import fcntl
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:
            with self.assertRaisesRegex(RuntimeError,'ALREADY_ACTIVE'):
                poll_once(state_root,'annual.service',self.handoff,self.annual,
                          '/missing/runner',self.show())
        finally:
            os.close(fd)


if __name__ == '__main__':
    unittest.main()
