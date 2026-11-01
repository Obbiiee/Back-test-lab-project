"""Durable, fail-closed CP6A-10 shared-source week/month/year QA pipeline."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone

REPOSITORY = Path(__file__).resolve().parents[2]
PYTHON = Path('/tmp/riksora-vps-candidate-venv/bin/python')
EVIDENCE_PARENT = Path('/home/riksora/riksora-qa-evidence')
SOURCE = Path('/home/riksora/riksora-qa-evidence/beta-checkpoints-20261025-jtbqjj1o/xau-binary-recovery-20261026/verified-serving-snapshot/archive.sqlite')
PROOF = Path('/home/riksora/riksora-qa-evidence/beta-checkpoints-20261025-jtbqjj1o/xau-binary-recovery-20261026/resumable-parity/final-report.json')
EXPECTED_SOURCE_SHA256 = 'b8f45551f408021514ab92599bd227eb4bfa9097c865d0084e0a91999c155b94'
EXPECTED_PROOF_SHA256 = '1ace74978391741f66078b8969a1784229a7c17f07b32f63b7e9e41e148cbb29'
ANNUAL_GROUPS = 56_208_511
MIN_FREE = 30 * 1024**3
ANNUAL_ARTIFACT_BUDGET = 8 * 1024**3
ANNUAL_WALL_BUDGET = 72 * 3600


def _write(path, value):
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, sort_keys=True, indent=2) + '\n')
    os.chmod(temp, 0o600)
    temp.replace(path)


def _cgroup_limits():
    rows = Path('/proc/self/cgroup').read_text().splitlines()
    unified = next((row.split('::', 1)[1].lstrip('/') for row in rows if row.startswith('0::')), None)
    if unified is None:
        raise RuntimeError('RESOURCE_PREFLIGHT_REQUIRES_CGROUP_V2')
    root = Path('/sys/fs/cgroup') / unified
    cpu = (root / 'cpu.max').read_text().strip().split()
    memory = int((root / 'memory.max').read_text().strip())
    swap = int((root / 'memory.swap.max').read_text().strip())
    if len(cpu) != 2 or cpu[0] == 'max':
        raise RuntimeError('RESOURCE_PREFLIGHT_CPU_QUOTA_MISSING')
    quota, period = map(int, cpu)
    if quota <= 0 or period <= 0 or not 0.99 <= quota / period <= 1.0:
        raise RuntimeError('RESOURCE_PREFLIGHT_CPU_QUOTA_NOT_ONE_CPU')
    if memory > 1024**3 or swap != 0:
        raise RuntimeError('RESOURCE_PREFLIGHT_MEMORY_LIMIT_MISMATCH')
    return dict(path=str(root), cpuQuotaMicroseconds=quota, cpuPeriodMicroseconds=period,
                cpuEquivalent=quota / period, memoryMaxBytes=memory, memorySwapMaxBytes=swap)


def _check_report(path, days, order_bound):
    report_path = path / 'report.json'
    report = json.loads(report_path.read_text())
    checks = {
        'status': report.get('status') == 'PASS',
        'days': report.get('continuousDays') == days,
        'sharedSource': report.get('timelineStorageMode') == 'shared-source-v1',
        'sourceIdentity': report.get('datasetId') == 'local:hf-community:XAUUSD:2024:53011f22a5887999a2c883a2',
        'sourcePin': report.get('archiveSha256') == EXPECTED_SOURCE_SHA256,
        'allTimestampGroups': report.get('tickCount') == report.get('timestampGroupCount') and report.get('timestampGroupCount', 0) > 0,
        'independentSourceWalk': report.get('independentVerification', {}).get('status') == 'PASS' and
            report.get('independentVerification', {}).get('independentTimestampGroups') == report.get('timestampGroupCount'),
        'fillReconciliation': report.get('independentVerification', {}).get('independentlyMatchedFills') ==
            report.get('independentVerification', {}).get('entryFills', 0) + report.get('independentVerification', {}).get('exitFills', 0),
        'coldResume': report.get('coldResume', {}).get('status') == 'PASS' and report.get('coldResume', {}).get('processRestarted') is True,
        'idempotency': report.get('idempotencyRetry') == 'PASS',
        'orderBound': report.get('cumulativeOrderHistory', {}).get('retainedOrderCount', order_bound + 1) <= order_bound and
            report.get('cumulativeOrderHistory', {}).get('activeHotOrderCount', 129) <= 128 and
            report.get('cumulativeOrderHistory', {}).get('allOrderIdsMatchState') is True and
            report.get('cumulativeOrderHistory', {}).get('noHistoricalOrderPruning') is True,
        'rightsAndEligibility': report.get('sourceRights') == 'UNKNOWN' and report.get('executionEligibility') == 'NOT_GRANTED',
        'noExternalMutation': report.get('productionChanged') is False and report.get('sourceChanged') is False,
    }
    if not all(checks.values()):
        raise RuntimeError('ACCEPTANCE_REPORT_GATE_FAILED:' + ','.join(key for key, value in checks.items() if not value))
    return dict(status='PASS', reportPath=str(report_path), checks=checks,
                groups=report['timestampGroupCount'], orders=report['cumulativeOrderHistory']['retainedOrderCount'],
                storage=report['storage'], measured=report['measured'],
                independentVerification=report['independentVerification'],
                coldResume=report['coldResume'], sourceRights=report['sourceRights'],
                executionEligibility=report['executionEligibility'])


def _run_logged(name, argv, env, output, state, timeout_seconds=None):
    _write(state, dict(status='RUNNING', stage=name, startedUtc=datetime.now(timezone.utc).isoformat(),
                       command=argv, outputPath=str(output)))
    started = time.monotonic()
    with output.open('wb') as stream:
        process = subprocess.Popen(argv, cwd=REPOSITORY, env=env, stdout=stream, stderr=subprocess.STDOUT,
                                  start_new_session=True)
        while process.poll() is None:
            elapsed = time.monotonic() - started
            if timeout_seconds and elapsed > timeout_seconds:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    pass
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                raise RuntimeError('BOUNDED_GATE_TIMEOUT:' + name)
            row = dict(status='RUNNING', stage=name, pid=process.pid,
                       elapsedSeconds=round(elapsed, 1), outputPath=str(output))
            progress_path = output.parent / name / 'progress.json'
            if progress_path.is_file():
                try:
                    row['replayProgress'] = json.loads(progress_path.read_text())
                except (OSError, json.JSONDecodeError):
                    row['replayProgress'] = dict(status='UPDATING')
            _write(state, row)
            time.sleep(15)
        code = process.returncode
    _write(state, dict(status='PASS' if code == 0 else 'FAIL', stage=name, returnCode=code,
                       elapsedSeconds=round(time.monotonic() - started, 3), outputPath=str(output)))
    if code != 0:
        raise RuntimeError('STAGE_COMMAND_FAILED:' + name + ':' + str(code))


def _stage_env(root, days, start, run_id):
    return dict(os.environ,
        PYTHONPATH=str(REPOSITORY / 'backend'), PYTHONDONTWRITEBYTECODE='1',
        BTL_QA_HISTORICAL_DAYS=str(days), BTL_QA_HISTORICAL_START_DAY=start,
        BTL_QA_HISTORICAL_BATCH_GROUPS='256', BTL_QA_SHARED_CANONICAL_SOURCE_V1='1',
        BTL_QA_ANNUAL_ORDER_SCHEDULE_V1='1', BTL_QA_ORDER_ARCHIVE_V1='1',
        BTL_HISTORICAL_QA_RUN_ID=run_id, BTL_HISTORICAL_QA_ROOT=str(root))


def _annual_preflight(root, month):
    free = shutil.disk_usage(root).free
    limits = _cgroup_limits()
    if free < MIN_FREE + ANNUAL_ARTIFACT_BUDGET:
        raise RuntimeError('ANNUAL_PREFLIGHT_DISK_RESERVE_OR_ARTIFACT_BUDGET_FAIL')
    memory_available = int(next(line.split()[1] for line in Path('/proc/meminfo').read_text().splitlines()
                                if line.startswith('MemAvailable:'))) * 1024
    if memory_available < 2 * 1024**3:
        raise RuntimeError('ANNUAL_PREFLIGHT_HOST_MEMORY_HEADROOM_FAIL')
    if not SOURCE.is_file() or not PROOF.is_file():
        raise RuntimeError('ANNUAL_PREFLIGHT_PINNED_SOURCE_MISSING')
    proof_raw = PROOF.read_bytes()
    proof = json.loads(proof_raw)
    proof_hash = hashlib.sha256(proof_raw).hexdigest()
    if (proof_hash != EXPECTED_PROOF_SHA256 or proof.get('status') != 'PASS' or
            proof.get('rows') != ANNUAL_GROUPS or proof.get('snapshotSha256') != EXPECTED_SOURCE_SHA256):
        raise RuntimeError('ANNUAL_PREFLIGHT_QUALIFICATION_PIN_MISMATCH')
    source_before = SOURCE.stat()
    digest = hashlib.sha256()
    with SOURCE.open('rb') as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(chunk)
    source_hash = digest.hexdigest()
    source_after = SOURCE.stat()
    source_fingerprint_before = (source_before.st_dev, source_before.st_ino, source_before.st_size, source_before.st_mtime_ns)
    source_fingerprint_after = (source_after.st_dev, source_after.st_ino, source_after.st_size, source_after.st_mtime_ns)
    if source_fingerprint_before != source_fingerprint_after:
        raise RuntimeError('ANNUAL_PREFLIGHT_SOURCE_CHANGED_DURING_HASH')
    if source_hash != EXPECTED_SOURCE_SHA256:
        raise RuntimeError('ANNUAL_PREFLIGHT_SOURCE_ARCHIVE_HASH_MISMATCH')
    month_groups = int(month['groups'])
    month_wall = float(month['measured']['elapsedSeconds'])
    month_artifacts = int(month['storage']['totalQaArtifactBytes'])
    if month_groups <= 0:
        raise RuntimeError('ANNUAL_PREFLIGHT_MONTH_GROUP_COUNT_MISSING')
    group_ratio = ANNUAL_GROUPS / month_groups
    projected_wall = max(56.2 * 3600, month_wall * group_ratio) * 1.25
    projected_artifacts = max(5_559_049_371, month_artifacts * group_ratio * 1.25)
    if projected_wall > ANNUAL_WALL_BUDGET:
        raise RuntimeError('ANNUAL_PREFLIGHT_RUNTIME_PROJECTION_EXCEEDS_72_HOURS')
    if projected_artifacts > ANNUAL_ARTIFACT_BUDGET:
        raise RuntimeError('ANNUAL_PREFLIGHT_ARTIFACT_PROJECTION_EXCEEDS_8_GIB')
    return dict(status='PASS', checkedUtc=datetime.now(timezone.utc).isoformat(),
        sourcePath=str(SOURCE), sourceBytes=source_after.st_size, sourceSha256=source_hash,
        sourceFingerprint=dict(device=source_after.st_dev, inode=source_after.st_ino,
                               sizeBytes=source_after.st_size, modifiedNs=source_after.st_mtime_ns),
        qualificationPath=str(PROOF), qualificationSha256=proof_hash,
        qualificationRows=proof['rows'], currentFreeBytes=free, minimumFreeBytes=MIN_FREE,
        annualArtifactBudgetBytes=ANNUAL_ARTIFACT_BUDGET, memoryAvailableBytes=memory_available,
        cgroup=limits, annualGroups=ANNUAL_GROUPS, monthGroups=month_groups,
        monthElapsedSeconds=month_wall, groupRatio=round(group_ratio, 6),
        projectedAnnualWallSeconds=round(projected_wall, 1),
        projectedAnnualArtifactBytes=round(projected_artifacts),
        annualWallBudgetSeconds=ANNUAL_WALL_BUDGET,
        annualScheduleMaximumOrders=1469, annualOrderLimit=4096,
        sourceRights='UNKNOWN', executionEligibility='NOT_GRANTED')


def resume_annual(evidence_root, attempt_number):
    evidence_root = Path(evidence_root).resolve(strict=True)
    lock_path = evidence_root/'annual-resume.lock'
    lock_fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as error:
        os.close(lock_fd)
        raise RuntimeError('ANNUAL_RESUME_ALREADY_ACTIVE') from error
    old_unit=subprocess.run(['systemctl','--user','is-active','--quiet',
        'riksora-cp6a10-shared-source-20261101.service'],check=False)
    if old_unit.returncode==0:
        raise RuntimeError('ANNUAL_RESUME_ORIGINAL_RUNNER_STILL_ACTIVE')
    old_report_path = evidence_root/'stage-runner-report.json'
    old_report = json.loads(old_report_path.read_text())
    for name in ('week','month','annualResourcePreflight'):
        if old_report.get('stages',{}).get(name,{}).get('status') != 'PASS':
            raise RuntimeError('ANNUAL_RESUME_PRIOR_GATE_NOT_PASS:' + name)
    for days,bound in ((7,33),(30,125)):
        stage='week' if days==7 else 'month'
        _check_report(evidence_root/stage,days,bound)
    if old_report.get('status') != 'STOPPED' or old_report.get('currentStage') != 'annual':
        raise RuntimeError('ANNUAL_RESUME_PRIOR_RUNNER_STATE_INVALID')
    if (evidence_root/'year'/'report.json').exists():
        raise RuntimeError('ANNUAL_RESUME_FINAL_REPORT_ALREADY_EXISTS')
    year_root=evidence_root/'year'
    progress=json.loads((year_root/'progress.json').read_text())
    if (progress.get('status')!='RUNNING' or
            progress.get('sessionId')!='session:hist-v2:cp6a10-year-20261101' or
            progress.get('revision')!=548 or progress.get('nextGroupIndex')!='137708'):
        raise RuntimeError('ANNUAL_RESUME_CHECKPOINT_IDENTITY_UNEXPECTED')
    preflight=json.loads((evidence_root/'annual-resource-preflight.json').read_text())
    if (preflight.get('status')!='PASS' or preflight.get('sourceRights')!='UNKNOWN' or
            preflight.get('executionEligibility')!='NOT_GRANTED' or
            preflight.get('annualGroups')!=ANNUAL_GROUPS or
            preflight.get('annualScheduleMaximumOrders')!=1469 or
            preflight.get('annualOrderLimit')!=4096):
        raise RuntimeError('ANNUAL_RESUME_PREFLIGHT_EVIDENCE_INVALID')
    source=Path(preflight['sourcePath'])
    source_stat=source.stat()
    fingerprint=preflight['sourceFingerprint']
    observed=(source_stat.st_dev,source_stat.st_ino,source_stat.st_size,source_stat.st_mtime_ns)
    expected=(fingerprint['device'],fingerprint['inode'],fingerprint['sizeBytes'],fingerprint['modifiedNs'])
    if observed!=expected:
        raise RuntimeError('ANNUAL_RESUME_SOURCE_FINGERPRINT_MISMATCH')
    digest=hashlib.sha256()
    with source.open('rb') as stream:
        for chunk in iter(lambda:stream.read(8*1024*1024),b''):
            digest.update(chunk)
    if digest.hexdigest()!=preflight['sourceSha256'] or digest.hexdigest()!=EXPECTED_SOURCE_SHA256:
        raise RuntimeError('ANNUAL_RESUME_SOURCE_HASH_MISMATCH')
    free=shutil.disk_usage(evidence_root).free
    if free<MIN_FREE+ANNUAL_ARTIFACT_BUDGET:
        raise RuntimeError('ANNUAL_RESUME_DISK_RESERVE_OR_ARTIFACT_BUDGET_FAIL')
    limits=_cgroup_limits()
    if limits['memoryMaxBytes']!=1024**3 or limits['memorySwapMaxBytes']!=0:
        raise RuntimeError('ANNUAL_RESUME_CGROUP_LIMIT_MISMATCH')
    memory_available=int(next(line.split()[1] for line in Path('/proc/meminfo').read_text().splitlines()
                              if line.startswith('MemAvailable:')))*1024
    if memory_available<2*1024**3:
        raise RuntimeError('ANNUAL_RESUME_HOST_MEMORY_HEADROOM_FAIL')
    attempt_root=evidence_root/f'annual-resume-attempt-{attempt_number}'
    attempt_root.mkdir(mode=0o700)
    status_path=attempt_root/'state.json'
    report_path=attempt_root/'report.json'
    annual_log=attempt_root/'runner.log'
    started_utc=datetime.now(timezone.utc).isoformat()
    preflight_time=datetime.fromisoformat(preflight['checkedUtc'])
    stopped_time=datetime.fromisoformat(old_report['stoppedUtc'])
    prior_elapsed=max(0.0,(stopped_time-preflight_time).total_seconds())
    attempt=dict(status='RUNNING',stage='annual-resume',startedUtc=started_utc,
        evidenceRoot=str(evidence_root),sessionId=progress['sessionId'],
        recoveredFromRevision=progress['revision'],recoveredFromGroupIndex=progress['nextGroupIndex'],
        recoveredThroughNs=progress['throughNs'],priorElapsedSeconds=round(prior_elapsed,3),
        priorCpuSeconds=progress.get('cpuSeconds'),sourceSha256=digest.hexdigest(),
        freeBytes=free,minimumFreeBytes=MIN_FREE,cgroup=limits,
        sourceRights='UNKNOWN',executionEligibility='NOT_GRANTED',outputPath=str(annual_log))
    _write(status_path,attempt)
    env=_stage_env(year_root,366,'2024-01-01','cp6a10-year-20261101')
    env.update(BTL_QA_HISTORICAL_RESUME_EXISTING='1',
        BTL_QA_HISTORICAL_PRIOR_ELAPSED_SECONDS=str(prior_elapsed),
        BTL_QA_HISTORICAL_PRIOR_CPU_SECONDS=str(progress.get('cpuSeconds',0)),
        BTL_QA_HISTORICAL_INITIAL_FREE_BYTES=str(preflight['currentFreeBytes']))
    try:
        _run_logged('year',[str(PYTHON),'-B','-m','tests.qa_historical_day_v2'],env,
                    annual_log,status_path,timeout_seconds=max(1,int(ANNUAL_WALL_BUDGET-prior_elapsed))+300)
        summary=_check_report(year_root,366,1469)
        result=dict(status='PASS_ADVANCING',stage='annual',completedUtc=datetime.now(timezone.utc).isoformat(),
            recoveredFromRevision=progress['revision'],recoveredFromGroupIndex=progress['nextGroupIndex'],
            finalSessionId=progress['sessionId'],annual=summary,
            nextStage='multi-user acceptance (not currently automated)',
            sourceRights='UNKNOWN',executionEligibility='NOT_GRANTED',
            evidencePaths=[str(report_path),str(year_root/'report.json'),str(annual_log)])
        _write(report_path,result)
        _write(status_path,result)
    except Exception as error:
        latest=json.loads((year_root/'progress.json').read_text())
        result=dict(status='FAILED_SAFELY',stage='annual-resume',errorCode=str(error),
            stoppedUtc=datetime.now(timezone.utc).isoformat(),sessionId=progress['sessionId'],
            lastKnownRevision=latest.get('revision'),lastKnownGroupIndex=latest.get('nextGroupIndex'),
            evidencePaths=[str(status_path),str(annual_log),str(year_root/'progress.json')],
            sourceRights='UNKNOWN',executionEligibility='NOT_GRANTED')
        _write(report_path,result)
        _write(status_path,result)
        raise
    finally:
        os.close(lock_fd)


def run(evidence_root):
    if evidence_root.exists():
        raise RuntimeError('EVIDENCE_ROOT_MUST_BE_NEW')
    evidence_root.mkdir(mode=0o700, parents=False)
    os.chmod(evidence_root, 0o700)
    state_path = evidence_root / 'runner-state.json'
    started_utc = datetime.now(timezone.utc).isoformat()
    report = dict(artifact='RIKSORA-CP6A-10-STAGE-RUNNER-1', startedUtc=started_utc,
                  status='RUNNING', currentStage='preflight', evidenceRoot=str(evidence_root),
                  stages={}, sourceRights='UNKNOWN', executionEligibility='NOT_GRANTED')
    _write(evidence_root / 'stage-runner-report.json', report)
    _write(state_path, dict(status='RUNNING', stage='initial-preflight'))
    limits = _cgroup_limits()
    free = shutil.disk_usage(evidence_root).free
    if free < MIN_FREE + 1536 * 1024**2:
        raise RuntimeError('INITIAL_PREFLIGHT_WEEKLY_ARTIFACT_BUDGET_WOULD_BREACH_30_GIB_RESERVE')
    report['initialPreflight'] = dict(status='PASS', freeBytes=free, minimumFreeBytes=MIN_FREE, cgroup=limits)

    tests_log = evidence_root / 'source-regression-tests.log'
    test_env = dict(os.environ, PYTHONPATH=str(REPOSITORY / 'backend'), PYTHONDONTWRITEBYTECODE='1')
    _run_logged('shared-source-and-schedule-regressions',
        [str(PYTHON), '-B', '-m', 'unittest', 'tests.test_tick_storage_v2.SharedSourceTimelineTests',
         'tests.test_qa_annual_order_schedule', '-v'], test_env, tests_log, state_path, timeout_seconds=900)
    report['stages']['regressions'] = dict(status='PASS', logPath=str(tests_log))
    _write(evidence_root / 'stage-runner-report.json', report)

    stages = [
        ('week', 7, '2024-01-02', 33, 'cp6a10-week-20261101', 5400),
        ('month', 30, '2024-01-02', 125, 'cp6a10-month-20261101', 18000),
    ]
    summaries = {}
    for name, days, start, order_bound, run_id, wall in stages:
        stage_root = evidence_root / name
        env = _stage_env(stage_root, days, start, run_id)
        output = evidence_root / (name + '-runner.log')
        _write(state_path, dict(status='RUNNING', stage=name, evidencePath=str(stage_root), outputPath=str(output)))
        _run_logged(name, [str(PYTHON), '-B', '-m', 'tests.qa_historical_day_v2'], env, output, state_path,
                    timeout_seconds=wall + 300)
        summaries[name] = _check_report(stage_root, days, order_bound)
        report['stages'][name] = summaries[name]
        report['currentStage'] = 'month' if name == 'week' else 'annual-resource-preflight'
        _write(evidence_root / 'stage-runner-report.json', report)

    preflight = _annual_preflight(evidence_root, summaries['month'])
    report['stages']['annualResourcePreflight'] = preflight
    _write(evidence_root / 'annual-resource-preflight.json', preflight)
    report['currentStage'] = 'annual'
    _write(evidence_root / 'stage-runner-report.json', report)

    annual_root = evidence_root / 'year'
    annual_env = _stage_env(annual_root, 366, '2024-01-01', 'cp6a10-year-20261101')
    annual_log = evidence_root / 'year-runner.log'
    _write(state_path, dict(status='RUNNING', stage='year', evidencePath=str(annual_root), outputPath=str(annual_log)))
    _run_logged('year', [str(PYTHON), '-B', '-m', 'tests.qa_historical_day_v2'], annual_env, annual_log,
                state_path, timeout_seconds=ANNUAL_WALL_BUDGET + 300)
    summaries['year'] = _check_report(annual_root, 366, 1469)
    report['stages']['year'] = summaries['year']
    report['status'] = 'PASS'
    report['currentStage'] = 'complete'
    report['completedUtc'] = datetime.now(timezone.utc).isoformat()
    _write(evidence_root / 'stage-runner-report.json', report)
    _write(state_path, dict(status='PASS', stage='complete', completedUtc=report['completedUtc']))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--evidence-root', required=True, type=Path)
    parser.add_argument('--resume-annual', action='store_true')
    parser.add_argument('--resume-attempt', type=int, default=1)
    args = parser.parse_args()
    try:
        if args.resume_annual:
            resume_annual(args.evidence_root,args.resume_attempt)
        else:
            run(args.evidence_root)
    except Exception as error:
        root = args.evidence_root
        if root.exists():
            try:
                stopped=dict(status='STOPPED_NEEDS_OWNER',stage='annual-resume' if args.resume_annual else 'pipeline',
                             errorCode=str(error),stoppedUtc=datetime.now(timezone.utc).isoformat(),
                             evidenceRoot=str(root))
                if args.resume_annual:
                    report_path=root/f'annual-resume-attempt-{args.resume_attempt}'/'report.json'
                    existing=json.loads(report_path.read_text()) if report_path.exists() else {}
                    existing.update(stopped)
                    if 'errorCode' not in existing:existing['errorCode']=str(error)
                    _write(report_path,existing)
                    _write(root/f'annual-resume-attempt-{args.resume_attempt}'/'state.json',existing)
                else:
                    report_path = root / 'stage-runner-report.json'
                    failure = json.loads(report_path.read_text()) if report_path.exists() else {}
                    failure.update(status='STOPPED', errorCode=str(error), stoppedUtc=stopped['stoppedUtc'],
                                   evidenceRoot=str(root))
                    _write(report_path, failure)
                    _write(root / 'runner-state.json', failure)
            except Exception:
                pass
        print('CP6A-10 STOP:', str(error), file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
