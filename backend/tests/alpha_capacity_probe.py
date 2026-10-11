"""Reproducible INTERNAL Windows/local probe, not Linux reference certification.

Creates a new QA database; never resets existing data. Run separately from full
regression. Report contains aggregate timing/outcome only, never account tokens.
"""
from concurrent.futures import ThreadPoolExecutor
import ctypes
import json
import os
from pathlib import Path
import platform
import time
import uuid
from unittest.mock import patch

import psycopg
from psycopg import sql
from application.models import TrustedScope
from cloud import queue
from cloud.worker import run
from contracts.canonical import canonical_bytes
from contracts.primitives import ContractError
from execution.research import ResearchApplication
from execution.research_fixture import STEP_NS
from infrastructure.database import connect, migrate
from tests import test_cloud_research as fixture
from tests.test_research_sessions import method, review_request


def host_memory():
    """Read-only host snapshot, not process RSS or a peak-memory certificate."""
    if os.name!='nt':return None
    class Status(ctypes.Structure):
        _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[(name,ctypes.c_ulonglong) for name in ('total','available','pageTotal','pageAvailable','virtualTotal','virtualAvailable','extendedAvailable')]
    status=Status();status.length=ctypes.sizeof(status)
    if not ctypes.WinDLL('kernel32').GlobalMemoryStatusEx(ctypes.byref(status)):return None
    return dict(totalBytes=status.total,availableBytes=status.available,usedPercent=status.load)


def main():
    original=os.environ['BTL_TEST_DATABASE_URL']
    name='btl_capacity_qa_'+uuid.uuid4().hex
    with connect(original) as db:
        db.autocommit=True
        db.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
    dsn=psycopg.conninfo.make_conninfo(original,dbname=name)
    migrate(dsn)
    sessions=[];clients=[];api_times=[];worker_observations=[]
    with patch.object(fixture,'DSN',dsn):
        for _ in range(10):
            f=fixture.CloudResearchTests('test_member_read_only_then_revocation_and_logout')
            f.setUp();clients.append(f.client)
            app=ResearchApplication(dsn,TrustedScope(f.workspace,f.actor));m=method()
            app.create_method(m);session='session:'+uuid.uuid4().hex
            view=app.create_session(dict(id=session,name='Internal capacity QA',methodId=m['id'],initialBalance='10000',startPeriod='2020-01'))
            request=review_request(view,True)
            request['draft'].update(side='LONG',orderType='LIMIT',workflow='PLANNED',entry='2006',sl='2005',tp='2008',quantity=None,riskPercent='1')
            reviewed=app.review(request)
            app.confirm(session,dict(reviewId=request['requestId'],reviewHash=reviewed['reviewHash']))
            before=app.inspect(session)
            command=dict(schemaVersion=1,artifact='BTL-TICK-EXECUTION-COMMAND-1',sessionId=session,
                         commandId='command:'+uuid.uuid4().hex,expectedRevision=before['state']['revision'],kind='ADVANCE',
                         payload={'targetNs':str(int(before['state']['throughNs'])+24*STEP_NS)})
            sessions.append((f,app,session,command,str(uuid.uuid4())))
    try:
        memory_before=host_memory()
        start=time.monotonic()
        for f,app,session,command,job in sessions:
            now=time.monotonic()
            accepted=f.client.post(f.root+'/sessions/'+session+'/commands',headers={**f.headers,'X-BTL-Job':job},json=command)
            api_times.append(time.monotonic()-now)
            assert accepted.status_code==202,(accepted.status_code,accepted.text)
            assert accepted.json()['state']=='QUEUED'
        with connect(dsn) as db:
            assert db.execute("SELECT count(*) FROM btl.research_jobs WHERE state='QUEUED'").fetchone()[0]==10
        def observed_run(*args,**kwargs):
            began=time.monotonic()
            try:
                result=run(*args,**kwargs)
                worker_observations.append(dict(seconds=str(time.monotonic()-began),outcome='RESULT'))
                return result
            except ContractError as error:
                worker_observations.append(dict(seconds=str(time.monotonic()-began),outcome=error.code,field=error.field))
                raise
        def drain():
            while queue.work_one(dsn,observed_run):pass
        with ThreadPoolExecutor(max_workers=2) as workers:
            list(workers.map(lambda _:drain(),range(2)))
        elapsed=time.monotonic()-start
        memory_after=host_memory()
        mismatches=0;successful=0;states={}
        for f,app,session,command,job in sessions:
            result=queue.inspect(dsn,uuid.UUID(f.actor),uuid.UUID(f.workspace),job)
            states[result['state']]=states.get(result['state'],0)+1
            if result['state']!='SUCCEEDED':continue
            assert result['result']['state']['balance']=='9900'
            cold=ResearchApplication(dsn,app.scope)
            if canonical_bytes(cold.apply(session,command))!=canonical_bytes(result['result']):mismatches+=1
            assert app.workspace(session,{'timeframe':'1m'})['analysis']['metrics']['tradeCount']==1
            successful+=1
        with connect(dsn) as db:
            pending=db.execute("SELECT count(*) FROM btl.research_jobs WHERE state='QUEUED'").fetchone()[0]
            timings=db.execute("SELECT extract(epoch FROM finished_at-created_at) FROM btl.research_jobs ORDER BY created_at").fetchall()
        values=sorted(api_times)
        report=dict(schemaVersion=1,artifact='BTL-INTERNAL-CAPACITY-PROBE-1',host=platform.system(),
                    interpretation='INTERNAL in-process authenticated API/native worker probe; not Linux reference, external release, full worst-case bootstrap or network/browser latency certification.',
                    sessions=10,workers=2,globalQueueLimit=16,perActorQueueLimit=2,
                    queueAfter=pending,successful=successful,deterministicMismatches=mismatches,
                    states=states,
                    workerObservations=worker_observations,
                    hostMemorySnapshots=dict(before=memory_before,after=memory_after,interpretation='Endpoint host snapshots only; not sampled peak RSS or resource certification.'),
                    workload='Ten distinct verified OWNER workspaces; one reviewed Limit Long with canonical SL exit and 24 fifteen-second intervals (six minutes) per Session; exact cold duplicate receipt for successful jobs.',
                    workloadWallSeconds=str(elapsed),minimumPerSessionVirtualSpeed=str(24*STEP_NS/1000000000/elapsed),
                    apiAcknowledgementSeconds=dict(p95=str(values[9]),p99=str(values[9])),
                    queueCompletionSeconds=[str(row[0]) for row in timings],
                    externalReferenceGate='NOT_CERTIFIED',rawDatasetUsed=False)
        path=Path(__file__).parents[2]/'frontend/tests/artifacts/alpha-local-tls-qa/internal-capacity-probe.json'
        path.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(report,indent=2))
        assert pending==0 and successful==10 and mismatches==0, 'Internal capacity probe failed; aggregate evidence retained'
    finally:
        for client in clients:client.close()
        for _,app,*_ in sessions:app.close()


if __name__=='__main__':main()
