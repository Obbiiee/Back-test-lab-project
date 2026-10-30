"""Project identical validated SQL history to fresh QA DBs; measure actual file blocks."""
import hashlib,json,re,subprocess,time
from pathlib import Path
from tests import qa_range_checkpoint5 as h


def measure(dsn,data):
    with h.psycopg.connect(dsn) as db:
        tables=db.execute("SELECT c.oid,c.relname,c.reltoastrelid,pg_total_relation_size(c.oid) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE (n.nspname='btl' AND c.relname IN ('tick_sessions','tick_checkpoints','tick_commands','tick_events')) OR (n.nspname='public' AND c.relname='qa5_commits') ORDER BY c.relname").fetchall()
        result=[]
        for oid,name,toast,reported in tables:
            parents=[oid]+([toast] if toast else [])
            indexes=[r[0] for r in db.execute('SELECT indexrelid FROM pg_index WHERE indrelid=ANY(%s)',(parents,))]
            paths=[r[0] for r in db.execute('SELECT pg_relation_filepath(x) FROM unnest(%s::oid[]) x',(parents+indexes,))]
            files=[]
            for relative in paths:
                path=data/relative;pattern=re.compile(re.escape(path.name)+r'(?:_(?:fsm|vm|init))?(?:\.\d+)?$')
                for file in path.parent.iterdir():
                    if pattern.fullmatch(file.name):files.append(dict(path=str(file.relative_to(data)),size=file.stat().st_size,allocated=file.stat().st_blocks*512))
            if sum(f['size'] for f in files)!=reported:raise ValueError('RELATION_FILE_ACCOUNTING')
            result.append(dict(table=name,postgresReportedBytes=reported,filesystemAllocatedBytes=sum(f['allocated'] for f in files),files=files))
        return dict(relations=result,filesystemAllocatedBytes=sum(r['filesystemAllocatedBytes'] for r in result))


def main():
    h.imports();start=time.monotonic()
    from psycopg.conninfo import conninfo_to_dict,make_conninfo
    ci=conninfo_to_dict(json.loads((h.E/'annual-xau2024-20261030/private-connection.json').read_text())['database'])
    sock=Path('/tmp/rx5-physical');sock.mkdir(mode=0o700);ci.update(host=str(sock),port='55743');data=h.ROOT/'pgdata'
    subprocess.run([str(h.BIN/'pg_ctl'),'-D',str(data),'-l',str(h.ROOT/'postgres-physical.log'),'-o',f"-c listen_addresses='' -k {sock} -p 55743 -c shared_buffers=32MB -c max_connections=30 -c unix_socket_permissions=0700",'-w','start'],check=True,capture_output=True,text=True,timeout=60)
    try:
        import sqlite3,zlib
        with sqlite3.connect((h.ROOT/'prototype/ranges.sqlite').resolve().as_uri()+'?mode=ro',uri=True) as db:
            binding=json.loads(db.execute('SELECT body FROM binding').fetchone()[0]);schedule=[json.loads(zlib.decompress(r[0])) for r in db.execute('SELECT body FROM prepared ORDER BY seq')]
        ci['dbname']='qa5_prototype';source=make_conninfo(**ci);scope=h.Scope(binding['workspace'],'qa5:actor');sid=binding['sessionId']
        with h.psycopg.connect(source) as db:
            checkpoints=[json.loads(bytes(r[0])) for r in db.execute('SELECT payload FROM btl.tick_checkpoints WHERE workspace_id=%s AND session_id=%s ORDER BY revision',(scope.workspace_id,sid))]
            receipts=[bytes(r[0]) for r in db.execute('SELECT payload FROM btl.tick_commands WHERE workspace_id=%s AND session_id=%s ORDER BY revision',(scope.workspace_id,sid))]
            references=h.refs(source,scope,sid)
        if len(receipts)!=37 or len(checkpoints)!=38:raise ValueError('SQL_PROJECTION_INPUT')
        projected={};admin=make_conninfo(**ci)
        for proto,name in [(False,'qa5_physical_base'),(True,'qa5_physical_range')]:
            dsn=h.create_database(admin,name,proto);store=h.Store(dsn);store.create(scope,checkpoints[0]['state'],checkpoints[0]['controller'])
            for index,(raw,record) in enumerate(zip(receipts,schedule)):
                expected=json.loads(raw);command=dict(schemaVersion=1,artifact='BTL-OBSERVED-EXECUTION-COMMAND-1',sessionId=sid,commandId=record['commandId'],expectedRevision=index,kind='ADVANCE',payload=dict(targetNs=record['targetNs']))
                if h.content_hash(command)!=expected['commandHash']:raise ValueError('PROJECTED_COMMAND_HASH')
                before,prior=store.prepare(scope,command)
                if proto:
                    with h.atomic_reference(scope,command,references[index][2]):actual=store.commit(scope,command,before,expected['state'],checkpoints[index+1]['controller'],expected['events'],expected['replay'])
                else:actual=store.commit(scope,command,before,expected['state'],checkpoints[index+1]['controller'],expected['events'],expected['replay'])
                if h.canonical_bytes(actual)!=raw:raise ValueError('PROJECTED_ORIGINAL_RECEIPT_BYTES')
            with h.psycopg.connect(dsn,autocommit=True) as db:db.execute('CHECKPOINT')
            projected['prototype' if proto else 'baseline']=measure(dsn,data);h.guard()
        for arm,file in [('baseline',h.ROOT/'baseline/engine/timeline.sqlite'),('prototype',h.ROOT/'prototype/ranges.sqlite')]:
            projected[arm]['sqliteAllocatedBytes']=file.stat().st_blocks*512
            projected[arm]['sessionAllocatedBytes']=projected[arm]['filesystemAllocatedBytes']+file.stat().st_blocks*512
        a=projected['baseline']['sessionAllocatedBytes'];b=projected['prototype']['sessionAllocatedBytes']
        h.save('physical-allocation.json',dict(status='PASS',method='same original validated SQL receipts/events/checkpoints through existing Store.commit into fresh isolated databases; fsynced CHECKPOINT; relation/TOAST/index/fork file stat accounting',arms=projected,savingBytes=a-b,savingPercent=100*(a-b)/a,wallSeconds=time.monotonic()-start,resources=h.cgroup()))
        print(json.dumps(dict(status='PASS',baseline=a,prototype=b,savingPercent=100*(a-b)/a)),flush=True)
    finally:
        subprocess.run([str(h.BIN/'pg_ctl'),'-D',str(data),'-m','fast','-w','stop'],check=True,capture_output=True,text=True,timeout=60);sock.rmdir()
    h.guard()


if __name__=='__main__':main()
