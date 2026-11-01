"""Fail-closed CP6A-10 post-annual QA handoff. One poll per systemd timer tick."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone

ANNUAL_GROUPS = 56_208_511
SOURCE_ID = 'local:hf-community:XAUUSD:2024:53011f22a5887999a2c883a2'
SOURCE_SHA256 = 'b8f45551f408021514ab92599bd227eb4bfa9097c865d0084e0a91999c155b94'
SOURCE_PATH = Path('/home/riksora/riksora-qa-evidence/beta-checkpoints-20261025-jtbqjj1o/xau-binary-recovery-20261026/verified-serving-snapshot/archive.sqlite')
MIN_FREE_BYTES = 30 * 1024**3
STAGES = (10, 50, 100)
STAGE_TIMEOUT_SECONDS = {10: 4 * 3600, 50: 4 * 3600, 100: 4 * 3600}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _atomic_json(path, value):
    path = Path(path)
    temp = path.with_name(path.name + f'.tmp-{os.getpid()}')
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)
    directory = os.open(path.parent, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def _append_log(path, value):
    with Path(path).open('a') as stream:
        stream.write(json.dumps(value, sort_keys=True)+'\n')
        stream.flush()
        os.fsync(stream.fileno())


def _record_state(root, state):
    _atomic_json(Path(root)/'state.json', state)
    rows=['# CP6A-10 Post-Annual Supervisor', '',
          f"- Status: `{state.get('status')}`",
          f"- Stage: `{state.get('stage')}`",
          f"- Checked: {state.get('checkedUtc')}",
          f"- Error: `{state.get('errorCode','none')}`",
          f"- Evidence: `{state.get('evidencePath',root)}`", '']
    path=Path(root)/'status.md'
    temp=path.with_name(path.name+f'.tmp-{os.getpid()}')
    fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as stream:
        stream.write('\n'.join(rows));stream.flush();os.fsync(stream.fileno())
    os.replace(temp,path)
    directory=os.open(path.parent,os.O_RDONLY|getattr(os,'O_DIRECTORY',0))
    try:os.fsync(directory)
    finally:os.close(directory)


def verify_annual(annual_report_path, handoff_report_path, service_result):
    """Require both PASS artifacts and every specified annual integrity gate."""
    if service_result != 'success':
        raise RuntimeError('ANNUAL_SYSTEMD_RESULT_NOT_SUCCESS')
    handoff = json.loads(Path(handoff_report_path).read_text())
    annual = json.loads(Path(annual_report_path).read_text())
    if handoff.get('status') != 'PASS_ADVANCING' or handoff.get('stage') != 'annual':
        raise RuntimeError('ANNUAL_HANDOFF_REPORT_NOT_PASS')
    if handoff.get('sourceRights') != 'UNKNOWN' or handoff.get('executionEligibility') != 'NOT_GRANTED':
        raise RuntimeError('ANNUAL_SOURCE_CLASSIFICATION_CHANGED')
    if annual.get('status') != 'PASS' or annual.get('continuousDays') != 366:
        raise RuntimeError('ANNUAL_ACCEPTANCE_REPORT_NOT_PASS')
    if annual.get('tickCount') != ANNUAL_GROUPS or annual.get('timestampGroupCount') != ANNUAL_GROUPS:
        raise RuntimeError('ANNUAL_SOURCE_GROUP_COVERAGE_MISMATCH')
    if annual.get('timelineStorageMode') != 'shared-source-v1':
        raise RuntimeError('ANNUAL_SHARED_SOURCE_MODE_MISMATCH')
    if annual.get('datasetId') != SOURCE_ID or annual.get('archiveSha256') != SOURCE_SHA256:
        raise RuntimeError('ANNUAL_CANONICAL_SOURCE_IDENTITY_MISMATCH')
    independent = annual.get('independentVerification', {})
    if (independent.get('status') != 'PASS' or
            independent.get('independentTimestampGroups') != ANNUAL_GROUPS or
            independent.get('tradeFinancialReconciliation') != 'PASS' or
            independent.get('independentlyMatchedFills') !=
            independent.get('entryFills', 0) + independent.get('exitFills', 0)):
        raise RuntimeError('ANNUAL_INDEPENDENT_FINANCIAL_OR_GROUP_GATE_FAILED')
    receipts = annual.get('replayBatch', {}).get('durableReceiptVerification', {})
    if receipts.get('status') != 'PASS' or receipts.get('commands') != annual.get('revision'):
        raise RuntimeError('ANNUAL_RECEIPT_LEDGER_FAILED')
    if annual.get('parity', {}).get('receiptLedgerSha256') != receipts.get('ledgerSha256'):
        raise RuntimeError('ANNUAL_RECEIPT_LEDGER_HASH_MISMATCH')
    if annual.get('coldResume', {}).get('status') != 'PASS' or annual.get('coldResume', {}).get('processRestarted') is not True:
        raise RuntimeError('ANNUAL_COLD_RECOVERY_FAILED')
    if annual.get('idempotencyRetry') != 'PASS':
        raise RuntimeError('ANNUAL_IDEMPOTENCY_FAILED')
    if annual.get('parity', {}).get('eventTranscriptSha256') is None or annual.get('parity', {}).get('receiptLedgerSha256') is None:
        raise RuntimeError('ANNUAL_EVENT_OR_RECEIPT_HASH_MISSING')
    if annual.get('sourceRights') != 'UNKNOWN' or annual.get('executionEligibility') != 'NOT_GRANTED':
        raise RuntimeError('ANNUAL_SOURCE_CLASSIFICATION_CHANGED')
    return dict(status='PASS', sessionId=annual.get('sessionId'), revision=annual.get('revision'),
                timestampGroups=annual['timestampGroupCount'], sourceId=SOURCE_ID,
                sourceSha256=SOURCE_SHA256, financial='PASS', coldResume='PASS', idempotency='PASS')


def validate_load_report(path, expected_users):
    report = json.loads(Path(path).read_text())
    latency=report.get('commandLatencyMs',{})
    required = {
        'status': report.get('status') == 'PASS',
        'users': report.get('concurrentSessions') == expected_users,
        'sharedSource': report.get('sharedSourceMode') == 'shared-source-v1',
        'sourceIdentity': report.get('sourceDatasetId') == SOURCE_ID and report.get('sourceSha256') == SOURCE_SHA256,
        'sessionIsolation': report.get('sessionIsolation') == 'PASS',
        'financial': report.get('financialIntegrity') == 'PASS',
        'events': report.get('eventIntegrity') == 'PASS',
        'recovery': report.get('coldRecovery') == 'PASS',
        'failures': report.get('failedRequests') == 0,
        'diskReserve': report.get('minimumFreeBytesObserved', 0) >= MIN_FREE_BYTES,
        'cpuBound': report.get('cpuLimitCores') == 1,
        'ramBound': report.get('memoryLimitBytes') == 1024**3,
        'swapBound': report.get('swapLimitBytes') == 0,
        'cpuMeasurement': isinstance(report.get('cpuSeconds'), (int, float)) and report['cpuSeconds'] >= 0,
        'ramMeasurement': isinstance(report.get('peakRamBytes'), int) and 0 < report['peakRamBytes'] <= 1024**3,
        'databaseMeasurement': isinstance(report.get('postgresBytes'), int) and report['postgresBytes'] >= 0 and
                               isinstance(report.get('postgresContentionMs'), (int, float)) and report['postgresContentionMs'] >= 0,
        'storageMeasurement': isinstance(report.get('incrementalDiskBytes'), int) and report['incrementalDiskBytes'] >= 0,
        'latency': isinstance(latency.get('p50'), (int, float)) and isinstance(latency.get('p95'), (int, float)) and
                   latency['p50'] >= 0 and latency['p95'] >= latency['p50'],
    }
    if not all(required.values()):
        raise RuntimeError('MULTIUSER_REPORT_GATE_FAILED:' + ','.join(k for k,v in required.items() if not v))
    return dict(status='PASS', users=expected_users, reportPath=str(path), checks=required)


def _systemd_show(unit, prop):
    result = subprocess.run(['systemctl', '--user', 'show', unit, '--property=' + prop, '--value'],
                            capture_output=True, text=True, timeout=10, check=False)
    if result.returncode:
        raise RuntimeError('SYSTEMD_STATUS_UNAVAILABLE:' + unit)
    return result.stdout.strip()


def poll_once(root, annual_unit, annual_handoff_report, annual_report, load_runner=None,
              systemd_show=_systemd_show, runner=None):
    root = Path(root).resolve()
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(root, 0o700)
    lock_fd = os.open(root/'supervisor.lock', os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as error:
        os.close(lock_fd)
        raise RuntimeError('POSTANNUAL_SUPERVISOR_ALREADY_ACTIVE') from error
    try:
        return _poll_locked(root, annual_unit, annual_handoff_report, annual_report,
                            load_runner, systemd_show, runner)
    finally:
        os.close(lock_fd)


def _poll_locked(root, annual_unit, annual_handoff_report, annual_report, load_runner,
                 systemd_show, runner):
    state_path = root/'state.json'
    log_path = root/'supervisor.log'
    previous = json.loads(state_path.read_text()) if state_path.exists() else {}
    if previous.get('status') in ('COMPLETE_PENDING_OWNER_REVIEW', 'STOPPED_NEEDS_OWNER'):
        return previous
    service_active = systemd_show(annual_unit, 'ActiveState')
    if service_active in ('active', 'activating', 'reloading'):
        state = dict(status='RUNNING', stage='waiting-annual', checkedUtc=_now(),
                     annualUnit=annual_unit, nextCheckSeconds=60,
                     evidencePath=str(root), annualProgressPath=str(Path(annual_report).parent/'progress.json'))
        _record_state(root, state)
        _append_log(log_path, state)
        return state
    result = systemd_show(annual_unit, 'Result')
    try:
        annual_evidence = verify_annual(annual_report, annual_handoff_report, result)
    except Exception as error:
        state = dict(status='STOPPED_NEEDS_OWNER', stage='annual-verification', checkedUtc=_now(),
                     errorCode=str(error), annualUnit=annual_unit,
                     evidencePaths=[str(annual_handoff_report), str(annual_report), str(log_path)])
        _record_state(root, state)
        _append_log(log_path, state)
        return state
    previous_stages = previous.get('completedLoadStages', [])
    if (not isinstance(previous_stages, list) or
            previous_stages != [users for users in STAGES if users in previous_stages] or
            previous_stages != list(STAGES[:len(previous_stages)])):
        return _stop(root,state_path,log_path,'POSTANNUAL_STAGE_STATE_INVALID',[],annual_evidence)
    runner_path = Path(load_runner).resolve() if load_runner else None
    if runner_path is None or not runner_path.is_file():
        state = dict(status='STOPPED_NEEDS_OWNER', stage='load-10-preflight', checkedUtc=_now(),
                     errorCode='VERIFIED_SHARED_SOURCE_MULTIUSER_RUNNER_MISSING',
                     annual=annual_evidence, completedLoadStages=previous_stages,
                     requiredRunner=str(runner_path) if runner_path else None,
                     evidencePaths=[str(annual_handoff_report), str(annual_report), str(log_path)])
        _record_state(root, state)
        _append_log(log_path, state)
        return state
    run = runner or subprocess.run
    completed = list(previous_stages)
    for users in STAGES:
        if users in completed:
            try:
                validate_load_report(root/f'load-{users}'/'report.json', users)
            except Exception as error:
                return _stop(root,state_path,log_path,'COMPLETED_STAGE_EVIDENCE_INVALID:'+str(error),completed,annual_evidence)
            continue
        free = shutil.disk_usage(root).free
        if free < MIN_FREE_BYTES:
            return _stop(root, state_path, log_path, 'DISK_RESERVE_BELOW_30_GIB', completed, annual_evidence)
        stage_root = root/f'load-{users}'
        stage_root.mkdir(mode=0o700, exist_ok=True)
        report_path = stage_root/'report.json'
        if not report_path.exists():
            log_file = stage_root/'runner.log'
            with log_file.open('ab') as stream:
                try:
                    result = run([sys.executable, str(runner_path), '--users', str(users), '--evidence-root', str(stage_root)],
                                 stdout=stream, stderr=subprocess.STDOUT, timeout=STAGE_TIMEOUT_SECONDS[users],
                                 check=False, start_new_session=True)
                except subprocess.TimeoutExpired:
                    return _stop(root, state_path, log_path, f'LOAD_{users}_TIMEOUT', completed, annual_evidence)
            if result.returncode != 0:
                return _stop(root, state_path, log_path, f'LOAD_{users}_COMMAND_FAILED:{result.returncode}', completed, annual_evidence)
        try:
            accepted = validate_load_report(report_path, users)
        except Exception as error:
            return _stop(root, state_path, log_path, str(error), completed, annual_evidence)
        completed.append(users)
        _record_state(root, dict(status='PASS_ADVANCING', stage=f'load-{users}', checkedUtc=_now(),
            annual=annual_evidence, completedLoadStages=completed, latestLoad=accepted,
            stageEvidence=str(report_path)))
    economics = root/'unit-economics.json'
    if not economics.exists():
        annual = json.loads(Path(annual_report).read_text())
        load_reports = {str(users): json.loads((root/f'load-{users}'/'report.json').read_text())
                        for users in STAGES}
        cpu_seconds = annual.get('measured', {}).get('cpuSeconds')
        trades = annual.get('completedTradeCount')
        groups = annual.get('timestampGroupCount')
        _atomic_json(economics, dict(
            status='PASS', measuredFrom='annual acceptance and verified multi-user reports',
            annual=dict(timestampGroups=groups, cpuSeconds=cpu_seconds, completedTrades=trades,
                        cpuSecondsPerTimestampGroup=(cpu_seconds/groups if groups else None),
                        cpuSecondsPerCompletedTrade=(cpu_seconds/trades if trades else None),
                        retainedSessionStorageBytes=annual.get('storage',{}).get('totalQaArtifactBytes'),
                        sharedSourceSha256=SOURCE_SHA256),
            concurrency={users: dict(cpuSeconds=report.get('cpuSeconds'),
                peakRamBytes=report.get('peakRamBytes'),postgresBytes=report.get('postgresBytes'),
                incrementalDiskBytes=report.get('incrementalDiskBytes'),
                p50CommandLatencyMs=report.get('commandLatencyMs',{}).get('p50'),
                p95CommandLatencyMs=report.get('commandLatencyMs',{}).get('p95'))
                for users,report in load_reports.items()},
            sharedDataset=dict(sourceSha256=SOURCE_SHA256,
                allocatedBytes=(SOURCE_PATH.stat().st_blocks*512 if SOURCE_PATH.is_file() else None),
                logicalBytes=(SOURCE_PATH.stat().st_size if SOURCE_PATH.is_file() else None)),
            storageRetentionScenarios=dict(
                oneSessionBytes=annual.get('storage',{}).get('totalQaArtifactBytes'),
                tenSessionBytes=annual.get('storage',{}).get('totalQaArtifactBytes',0)+
                                10*annual.get('storage',{}).get('perSessionTimelineAllocatedBytes',0),
                fiftySessionBytes=annual.get('storage',{}).get('totalQaArtifactBytes',0)+
                                  50*annual.get('storage',{}).get('perSessionTimelineAllocatedBytes',0),
                oneHundredSessionBytes=annual.get('storage',{}).get('totalQaArtifactBytes',0)+
                                       100*annual.get('storage',{}).get('perSessionTimelineAllocatedBytes',0)),
            pricing=dict(monthlyIdr=87000,annualIdr=400000,annualMonthlyEquivalentIdr=400000/12,
                documentedVpsMonthlyBillIdr=None,
                formula='actual monthly infrastructure bill / monthly active paying traders',
                maximumMonthlyInfrastructureAllocationPerUserIdr=dict(
                    monthlyPlan=87000,annualPlanMonthlyEquivalent=400000/12),
                profitClaim='NOT_ESTABLISHED'),
            qaOverhead='Annual replay and load acceptance costs are QA evidence and must not be treated as per-user production demand.'))
    state = dict(status='COMPLETE_PENDING_OWNER_REVIEW', stage='complete', checkedUtc=_now(),
                 annual=annual_evidence, completedLoadStages=completed,
                 unitEconomicsPath=str(economics), evidencePath=str(root))
    _record_state(root, state)
    _append_log(log_path, state)
    return state


def _stop(root, state_path, log_path, reason, completed, annual_evidence):
    state = dict(status='STOPPED_NEEDS_OWNER', stage='post-annual', checkedUtc=_now(),
                 errorCode=reason, annual=annual_evidence, completedLoadStages=completed,
                 evidencePath=str(root))
    _record_state(root, state)
    _append_log(log_path, state)
    return state


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--evidence-root', required=True, type=Path)
    parser.add_argument('--annual-unit', required=True)
    parser.add_argument('--annual-handoff-report', required=True, type=Path)
    parser.add_argument('--annual-report', required=True, type=Path)
    parser.add_argument('--load-runner', type=Path)
    parser.add_argument('--stop-timer-on-terminal', action='store_true')
    args = parser.parse_args()
    try:
        rows=Path('/proc/self/cgroup').read_text().splitlines()
        rel=next((row.split('::',1)[1].lstrip('/') for row in rows if row.startswith('0::')),None)
        if rel is None:
            raise RuntimeError('RESOURCE_PREFLIGHT_REQUIRES_CGROUP_V2')
        cg=Path('/sys/fs/cgroup')/rel
        quota,period=map(int,(cg/'cpu.max').read_text().split())
        if quota<=0 or period<=0 or quota/period>1.0 or int((cg/'memory.max').read_text())>1024**3 or int((cg/'memory.swap.max').read_text())!=0:
            raise RuntimeError('RESOURCE_PREFLIGHT_LIMITS_NOT_MAINTAINED')
        state = poll_once(args.evidence_root, args.annual_unit, args.annual_handoff_report,
                          args.annual_report, args.load_runner)
        print(json.dumps(state, sort_keys=True))
        if args.stop_timer_on_terminal and state['status'] in ('COMPLETE_PENDING_OWNER_REVIEW','STOPPED_NEEDS_OWNER'):
            subprocess.run(['systemctl','--user','disable','--now','riksora-cp6a10-postannual.timer'],
                           capture_output=True,text=True,timeout=15,check=False)
        return 0 if state['status'] in ('RUNNING', 'PASS_ADVANCING', 'COMPLETE_PENDING_OWNER_REVIEW') else 1
    except Exception as error:
        print('POSTANNUAL_SUPERVISOR_STOP:' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
