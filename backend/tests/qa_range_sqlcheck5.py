"""Independent SQL receipt/event/checkpoint completeness checks on QA clone only."""
import hashlib,json,os,subprocess,time
from pathlib import Path
from tests import qa_range_checkpoint5 as h


def main():
    h.imports();start=time.monotonic()
    from psycopg.conninfo import conninfo_to_dict,make_conninfo
    ci=conninfo_to_dict(json.loads((h.E/'annual-xau2024-20261030/private-connection.json').read_text())['database'])
    sock=Path('/tmp/rx5-sql');sock.mkdir(mode=0o700);ci.update(host=str(sock),port='55742');data=h.ROOT/'pgdata'
    subprocess.run([str(h.BIN/'pg_ctl'),'-D',str(data),'-l',str(h.ROOT/'postgres-sqlcheck.log'),'-o',f"-c listen_addresses='' -k {sock} -p 55742 -c shared_buffers=32MB -c max_connections=30 -c unix_socket_permissions=0700",'-w','start'],check=True,capture_output=True,text=True,timeout=60)
    try:
        sid=json.loads(h.SNAP.read_text())['state']['sessionId'];results={};comparisons={}
        for name in ('qa5_baseline','qa5_prototype'):
            ci['dbname']=name;dsn=make_conninfo(**ci)
            with h.psycopg.connect(dsn) as db:
                scopes=db.execute('SELECT workspace_id FROM btl.tick_sessions WHERE session_id=%s ORDER BY workspace_id',(sid,)).fetchall()
                for (scope,) in scopes:
                    commands=db.execute('SELECT revision,payload,content_hash FROM btl.tick_commands WHERE workspace_id=%s AND session_id=%s ORDER BY revision',(scope,sid)).fetchall()
                    events=db.execute('SELECT sequence,payload,content_hash FROM btl.tick_events WHERE workspace_id=%s AND session_id=%s ORDER BY sequence',(scope,sid)).fetchall()
                    checkpoints=db.execute('SELECT revision,payload,content_hash FROM btl.tick_checkpoints WHERE workspace_id=%s AND session_id=%s ORDER BY revision',(scope,sid)).fetchall()
                    expected=[];receipts=[]
                    for expected_revision,(revision,raw,sha) in enumerate(commands,1):
                        raw=bytes(raw);obj=json.loads(raw)
                        if revision!=expected_revision or hashlib.sha256(raw).hexdigest()!=sha or h.canonical_bytes(obj)!=raw:raise ValueError('COMMAND_RECEIPT_HASH')
                        expected.extend(obj['events']);receipts.append(raw)
                    actual=[]
                    for expected_seq,(sequence,raw,sha) in enumerate(events):
                        raw=bytes(raw);obj=json.loads(raw)
                        if sequence!=expected_seq or hashlib.sha256(raw).hexdigest()!=sha or h.canonical_bytes(obj)!=raw:raise ValueError('EVENT_HASH_OR_ORDER')
                        actual.append(obj)
                    if expected!=actual or len(checkpoints)!=len(commands)+1:raise ValueError('MISSING_OR_EXTRA_EVENT_CHECKPOINT')
                    for expected_revision,(revision,raw,sha) in enumerate(checkpoints):
                        raw=bytes(raw);obj=json.loads(raw)
                        if revision!=expected_revision or hashlib.sha256(raw).hexdigest()!=sha or h.canonical_bytes(obj)!=raw:raise ValueError('CHECKPOINT_HASH')
                        if revision and obj['state']!=json.loads(receipts[revision-1])['state']:raise ValueError('CHECKPOINT_RECEIPT_STATE')
                    tip=db.execute('SELECT payload,content_hash FROM btl.tick_sessions WHERE workspace_id=%s AND session_id=%s',(scope,sid)).fetchone()
                    if bytes(tip[0])!=bytes(checkpoints[-1][1]) or tip[1]!=checkpoints[-1][2]:raise ValueError('TIP_CHECKPOINT')
                    if not scope.startswith('qa5:'):comparisons[name]=(receipts,actual)
                    results[name+':'+scope]=dict(status='PASS',commands=len(commands),events=len(actual),checkpoints=len(checkpoints))
        if comparisons['qa5_baseline']!=comparisons['qa5_prototype']:raise ValueError('CROSS_ARM_SQL_LOGICAL_PARITY')
        h.save('sql-events-verification.json',dict(status='PASS',scopes=results,exactMainReceiptsEventsParity=True,wallSeconds=time.monotonic()-start,resources=h.cgroup()))
        print('PASS independent SQL receipt/event/checkpoint completeness and both-arm parity',flush=True)
    finally:
        subprocess.run([str(h.BIN/'pg_ctl'),'-D',str(data),'-m','fast','-w','stop'],check=True,capture_output=True,text=True,timeout=60);sock.rmdir()
    h.guard()


if __name__=='__main__':main()
