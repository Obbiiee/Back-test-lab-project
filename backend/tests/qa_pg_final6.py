"""Read-only independent byte parity and explicit financial corruption probes on QA DBs."""
import json,subprocess,time
from pathlib import Path
import psycopg
from psycopg.conninfo import conninfo_to_dict,make_conninfo
from tests import qa_pg_checkpoint6 as h
from tests.qa_pg_verify6 import fetch,decode,audit


def main():
    start=time.monotonic();workload=json.loads((h.ROOT/'workload.json').read_text());seed=workload['seed'];commands=workload['commands']
    ci=conninfo_to_dict(json.loads((h.E/'annual-xau2024-20261030/private-connection.json').read_text())['database'])
    sock=Path('/tmp/rx6-final');sock.mkdir(mode=0o700);ci.update(host=str(sock),port='55841');data=h.ROOT/'pgdata'
    subprocess.run([str(h.BIN/'pg_ctl'),'-D',str(data),'-l',str(h.ROOT/'postgres-final.log'),'-o',f"-c listen_addresses='' -k {sock} -p 55841 -c shared_buffers=32MB -c max_connections=30 -c unix_socket_permissions=0700",'-w','start'],check=True,capture_output=True,text=True,timeout=60)
    try:
        parity={};small=None;settings=None
        for size in h.SIZES:
            pair=[]
            for compact in (False,True):
                ci['dbname']='qa6_'+('c' if compact else 'b')+str(size)
                with psycopg.connect(make_conninfo(**ci)) as db:
                    pair.append(fetch(db,h.SCOPE.workspace_id,h.SID,compact))
                    settings=dict(db.execute("SELECT name,setting FROM pg_settings WHERE name IN ('fsync','synchronous_commit','full_page_writes','autovacuum')").fetchall())
            a,b=pair;checked={}
            for table,payload_index,hash_index in [('commands',3,4),('events',2,3),('checkpoints',1,2)]:
                if len(a[table])!=len(b[table]):raise ValueError('ROW_COUNTS')
                total=0
                for left,right in zip(a[table],b[table]):
                    if left[:payload_index]!=right[:payload_index] or left[hash_index]!=right[hash_index]:raise ValueError('ROW_IDENTITY_HASH')
                    _,original=decode(left[payload_index],left[hash_index],None);_,restored=decode(right[payload_index],right[hash_index],b['objects'])
                    if original!=restored:raise ValueError('EXACT_ORIGINAL_BYTES')
                    total+=len(original)
                checked[table]=dict(rows=len(a[table]),originalBytesCompared=total)
            _,left=decode(a['tip'][0],a['tip'][1],None);_,right=decode(b['tip'][0],b['tip'][1],b['objects'])
            if left!=right:raise ValueError('TIP_BYTES')
            parity[str(size)]=checked
            if size==16:small=b
            h.guard()
        exits=[];entries=[]
        for index,row in enumerate(small['events']):
            value,_=decode(row[2],row[3],small['objects'])
            if value['kind']=='EXIT_FILL':exits.append(index)
            if value['kind']=='ENTRY_FILL':entries.append(index)
        if len(exits)!=4 or len(entries)!=4:raise ValueError('FINANCIAL_TEST_INPUT')
        cases={
            'missing_TP_fill':dict(small,events=[r for i,r in enumerate(small['events']) if i!=exits[0]]),
            'missing_SL_fill':dict(small,events=[r for i,r in enumerate(small['events']) if i!=exits[1]]),
            'missing_entry_fill':dict(small,events=[r for i,r in enumerate(small['events']) if i!=entries[0]]),
            'missing_receipt':dict(small,commands=small['commands'][:-1])}
        reordered=list(small['events']);reordered[exits[0]],reordered[exits[1]]=reordered[exits[1]],reordered[exits[0]]
        cases['reordered_financial_fills']=dict(small,events=reordered)
        substituted=list(small['events']);old=list(substituted[exits[0]]);old[2]=small['events'][entries[0]][2];substituted[exits[0]]=tuple(old)
        cases['substituted_financial_payload']=dict(small,events=substituted)
        results={}
        for name,case in cases.items():
            try:audit(case,commands[:16],seed,2)
            except Exception:results[name]='PASS_REJECTED'
            else:raise ValueError('FINANCIAL_CORRUPTION_ACCEPTED:'+name)
        h.save('independent-final.json',dict(status='PASS',directByteParity=parity,financialAdversarial=results,postgresSettings=settings,wallSeconds=time.monotonic()-start,cgroup=h.cg()))
        print('PASS direct byte parity at all sizes and six financial adversarial probes',flush=True)
    finally:
        subprocess.run([str(h.BIN/'pg_ctl'),'-D',str(data),'-m','fast','-w','stop'],check=True,capture_output=True,text=True,timeout=60);sock.rmdir()
    h.guard()


if __name__=='__main__':main()
