"""Additional independent cold recovery and future-truncation probes, QA only."""
import hashlib,json,os,sqlite3,subprocess,time,zlib
from pathlib import Path
from tests import qa_range_checkpoint5 as h


def main():
    h.imports();h.guard();start=time.monotonic()
    from psycopg.conninfo import conninfo_to_dict,make_conninfo
    ci=conninfo_to_dict(json.loads((h.E/'annual-xau2024-20261030/private-connection.json').read_text())['database'])
    sock=Path('/tmp/rx5-extra');sock.mkdir(mode=0o700);ci.update(host=str(sock),port='55741')
    data=h.ROOT/'pgdata'
    subprocess.run([str(h.BIN/'pg_ctl'),'-D',str(data),'-l',str(h.ROOT/'postgres-extra.log'),'-o',f"-c listen_addresses='' -k {sock} -p 55741 -c shared_buffers=32MB -c max_connections=30 -c unix_socket_permissions=0700",'-w','start'],check=True,capture_output=True,text=True,timeout=60)
    try:
        dsn=make_conninfo(**ci);sid=json.loads(h.SNAP.read_text())['state']['sessionId']
        with h.psycopg.connect(dsn) as db:
            workspace=db.execute('SELECT workspace_id FROM btl.tick_sessions WHERE session_id=%s',(sid,)).fetchone()[0]
            seed=json.loads(bytes(db.execute('SELECT payload FROM btl.tick_checkpoints WHERE workspace_id=%s AND session_id=%s AND revision=0',(workspace,sid)).fetchone()[0]))
        ci['dbname']='qa5_prototype';dsn=make_conninfo(**ci)
        checked={}
        for phase in ('after_prepare','before_sql_commit','after_sql_commit','after_finalize'):
            folder=h.ROOT/('crash-'+phase);scope=h.Scope('qa5:'+phase,'qa5:actor')
            with sqlite3.connect((folder/'ranges.sqlite').resolve().as_uri()+'?mode=ro',uri=True) as db:
                binding=json.loads(db.execute('SELECT body FROM binding').fetchone()[0]);physical=db.execute('SELECT hash,seq,body FROM prepared ORDER BY seq,hash').fetchall()
            committed=h.refs(dsn,scope,sid)
            obj=json.loads(zlib.decompress(physical[0][2]));cmd=dict(schemaVersion=1,artifact='BTL-OBSERVED-EXECUTION-COMMAND-1',sessionId=sid,commandId=obj['commandId'],expectedRevision=0,kind='ADVANCE',payload=dict(targetNs=obj['targetNs']))
            with h.psycopg.connect(dsn) as db:receipt=json.loads(bytes(db.execute('SELECT payload FROM btl.tick_commands WHERE workspace_id=%s AND session_id=%s',(scope.workspace_id,sid)).fetchone()[0]))
            p=h.Provider(h.DATASET,seed['state']['datasetVersion'],read_only=True)
            try:
                verified=h.verify(binding,physical,committed,[cmd],seed,[receipt],p,h.ROOT/('cold-verify-'+phase))
                if verified['state']!=receipt['state']:raise ValueError('COLD_RECOVERY_STATE')
                checked[phase]=dict(status='PASS',groups=verified['groups'],revision=verified['state']['revision'])
            finally:p.close()
        checkpoint=json.loads((h.ROOT/'prototype-verification.json').read_text())['checkpoint'];p=h.Provider(h.DATASET,seed['state']['datasetVersion'],read_only=True)
        try:
            iterator=h.source_groups(p,seed['state']['startNs']);digest=hashlib.sha256();last=None
            for _ in range(2222):
                pos,group=next(iterator);digest.update(json.dumps(group,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode());last=int(pos['globalOrdinal'])+len(group['events'])-1
            class Truncated:
                dataset_id=p.dataset_id;dataset_version=p.dataset_version
                def locate_v2(self,*args):return p.locate_v2(*args)
                def read_page_v2(self,dataset_id,version,position,maximum):
                    page=p.read_page_v2(dataset_id,version,position,maximum);count=max(0,min(len(page['events']),last-int(position['globalOrdinal'])+1))
                    if count<len(page['events']):page=dict(page,events=page['events'][:count],nextPosition=None,endOfDataset=True)
                    return page
            truncated=Truncated();full=h.consumer(p,seed['state']['startNs'],checkpoint);clipped=h.consumer(truncated,seed['state']['startNs'],checkpoint)
            for offset,maximum in [('0',64),('2176',46),('2221',1),('2222',1)]:
                if full.read_revealed(offset,maximum)!=clipped.read_revealed(offset,maximum):raise ValueError('FUTURE_TRUNCATION_DIFF')
            for view in (full,clipped):
                try:view.read_revealed('2223',1)
                except ValueError:pass
                else:raise ValueError('FUTURE_LEAK')
            expected='caec2ffedfebc4f58d48a4b5dba235091d479a80636e91b8ceb2a1b99b49b9e2'
            if digest.hexdigest()!=expected:raise ValueError('SOURCE_PREFIX_HASH')
            future=dict(status='PASS',futureRows='removed at provider-page boundary in a QA projection',lastCommittedGlobalOrdinal=last,revealedGroups=2222,prefixHash=digest.hexdigest(),unrevealedRead='REFUSED')
        finally:p.close()
        h.save('extra-verification.json',dict(status='PASS',coldCrashRecovery=checked,futureTruncation=future,wallSeconds=time.monotonic()-start,resources=h.cgroup()))
        print('PASS four independent cold crash recoveries and future truncation',flush=True)
    finally:
        subprocess.run([str(h.BIN/'pg_ctl'),'-D',str(data),'-m','fast','-w','stop'],check=True,capture_output=True,text=True,timeout=60);sock.rmdir()
    h.guard()


if __name__=='__main__':main()
