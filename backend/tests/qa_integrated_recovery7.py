"""C7 closure: continue from independently rebuilt logs, retaining writer scratch."""
import json,subprocess,time
from pathlib import Path
import psycopg
from psycopg.conninfo import conninfo_to_dict,make_conninfo
from application.models import TrustedScope
from execution.observed_postgres import ObservedExecutionStore
from ticks.timeline_v2 import IndexedTickTimeline
from tests import qa_integrated_checkpoint7 as q


def main():
    # Supplement belongs to the SAME cumulative C7 budget and deadline.
    q.START=time.monotonic()-(time.time()-(q.ROOT/'PLAN.json').stat().st_mtime)
    q.guard();data=q.ROOT/'pgdata';sock=Path('/tmp/rx7-main')
    status=subprocess.check_output([str(q.BIN/'pg_controldata'),str(data)],text=True)
    if 'Database cluster state:               shut down' not in status:raise ValueError('QA_NOT_STOPPED')
    ci=conninfo_to_dict(json.loads((q.E/'annual-xau2024-20261030/private-connection.json').read_text())['database']);ci.update(host=str(sock),port='55940');admin=make_conninfo(**ci)
    sock.mkdir(mode=0o700)
    subprocess.run([str(q.BIN/'pg_ctl'),'-D',str(data),'-l',str(q.ROOT/'postgres.log'),'-o',f"-c listen_addresses='' -k {sock} -p 55940 -c shared_buffers=32MB -c max_connections=30 -c unix_socket_permissions=0700",'-w','start'],check=True,capture_output=True,text=True,timeout=30)
    try:
        with psycopg.connect(admin) as db:
            durability={name:db.execute('SHOW '+name).fetchone()[0] for name in ('fsync','synchronous_commit','full_page_writes','listen_addresses')}
        if any(durability[k]!='on' for k in ('fsync','synchronous_commit','full_page_writes')):raise ValueError('DURABILITY')
        assets=json.loads((q.ROOT/'assets.json').read_text());rechecked={}
        # Revalidate final schema/revision checks on every retained main history.
        for key,dbkey in [('xau','real'),('financial','financial')]:
            asset=assets[key];scope=TrustedScope('qa7:'+asset['name'],'qa7:actor')
            for candidate in (False,True):
                dsn=make_conninfo(admin,dbname='qa7_'+dbkey+('_c' if candidate else '_b'));folder=q.ROOT/(asset['name']+('-candidate' if candidate else '-baseline'))
                records=q.load_data(dsn,scope,asset,candidate);committed=q.refs(dsn,scope,asset['seed']['state']['sessionId']) if candidate else []
                commands,_=q.history(records,folder/'session.sqlite',q.binding(asset,scope),committed,candidate);rechecked[folder.name]=len(commands)
        asset=assets['financial'];dsn=q.create_session_db(admin,'qa7_rebuilt_c',True);scope=TrustedScope('qa7:rebuilt','qa7:actor');folder=q.ROOT/'verified-continuation'
        q.seed_prefix(dsn,asset,True,scope,folder)
        _,_,before=q.verify_case(dsn,asset,True,scope,folder,'rebuilt')
        original={str(p):q.stamp(p) for p in (folder/'engine').rglob('*') if p.is_file()}
        p=q.source(asset,True);start=time.monotonic();cpu=q.cg()['cpuUsec']
        engine=IndexedTickTimeline.resume(p,before['checkpoint'],log_folder=folder/'rebuilt')
        try:
            with q.context(True):
                for command in asset['commands'][3:8]:
                    q.execute(ObservedExecutionStore(dsn),scope,folder,asset,command,True,timeline=engine);q.guard()
        finally:engine.close();p.close()
        continuation=time.monotonic()-start;used=(q.cg()['cpuUsec']-cpu)/1e6
        if any(q.stamp(Path(path))!=stamp for path,stamp in original.items()):raise ValueError('WRITER_SCRATCH_USED')
        records,_,after=q.verify_case(dsn,asset,True,scope,folder,'independent-after-continuation')
        oracle=q.audit(records,asset['commands'][:8],asset['seed'],None,oracle=dict(TP=1,SL=1,balance='9999.8',orders=2))
        q.save('verified-continuation.json',dict(status='PASS',writerScratchUnchanged=True,originalWriterLogsNotUsedForContinuation=True,fromRevision=3,toRevision=8,continuedSeconds=continuation,continuedCgroupCPUSeconds=used,before=before,after=after,financialOracle=oracle,finalHistoryChecks=rechecked,durability=durability,resources=dict(cgroup=q.cg(),totalElapsedSincePlanSeconds=time.monotonic()-q.START,newArtifactAllocatedBytes=q.allocated(q.ROOT))))
    finally:
        subprocess.run([str(q.BIN/'pg_ctl'),'-D',str(data),'-m','fast','-w','stop'],check=True,capture_output=True,text=True,timeout=30);sock.rmdir()
    q.guard()


if __name__=='__main__':main()
