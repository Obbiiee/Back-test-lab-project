import json
import os
import subprocess
import sys
import tempfile
import time
import unittest

from contracts.canonical import canonical_bytes, content_hash
from execution.observed_state_delta_v3 import (QAStateDeltaStore,COMPACT_BASE,COMPACT_DELTA,
    encode_compact_base,encode_compact_delta,reconstruct_complete)


def state(revision,orders,balance='10000'):
    return dict(schemaVersion=1,artifact='AUTHORED-FULL-FINANCIAL-STATE-1',revision=revision,
                balance=balance,realizedGross='0',eventHash=('a'*63)+str(revision%10),orders=orders,
                quoteBasis={'bid':'1','ask':'2'},throughNs=str(revision))


class ObservedStateDeltaV3Tests(unittest.TestCase):
    def test_compact_v1_streaming_reconstruction_is_exact_and_fail_closed(self):
        initial=state(0,{})
        base=encode_compact_base(initial)
        self.assertEqual((base['formatVersion'],base['artifact']),(1,COMPACT_BASE))
        previous=initial;chain_hash=base['stateHash'];deltas=[]
        for revision in range(1,17):
            orders=dict(previous['orders'])
            orders[f'closed:{revision}']=dict(id=f'closed:{revision}',status='CLOSED',grossPosted='0')
            current=state(revision,orders)
            delta=encode_compact_delta(previous,current,chain_hash)
            self.assertEqual((delta['formatVersion'],delta['artifact']),(1,COMPACT_DELTA))
            chain_hash=delta['body']['recordHash'];deltas.append(delta);previous=current
        recovered=reconstruct_complete(base,(item for item in deltas),len(deltas))
        self.assertEqual(canonical_bytes(recovered),canonical_bytes(previous))
        self.assertEqual(content_hash(recovered),deltas[-1]['body']['stateHash'])
        with self.assertRaisesRegex(ValueError,'CORRUPT_RECORD'):
            reconstruct_complete(base,(item for item in deltas[:-1]),len(deltas))
        reordered=list(deltas);reordered[3],reordered[4]=reordered[4],reordered[3]
        with self.assertRaisesRegex(ValueError,'CORRUPT_RECORD'):
            reconstruct_complete(base,(item for item in reordered),len(reordered))
        corrupted=json.loads(json.dumps(deltas));corrupted[7]['body']['previousHash']='0'*64
        with self.assertRaisesRegex(ValueError,'CORRUPT_RECORD'):
            reconstruct_complete(base,(item for item in corrupted),len(corrupted))

    def test_snapshot_delta_exact_reconstruction_retry_and_corruption_detection(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=os.path.join(tmp,'qa.sqlite');store=QAStateDeltaStore(path);sid='session:qa-v3'
            initial=state(0,{});store.create(sid,initial)
            live=dict(id='active:1',status='ACTIVE',grossPosted='0')
            current=initial
            started=time.perf_counter()
            for revision in range(1,257):
                orders=dict(current['orders'])
                if revision<=255:orders[f'closed:{revision}']=dict(id=f'closed:{revision}',status='CLOSED',grossPosted='0')
                else:orders['active:1']=live
                proposed=state(revision,orders,balance='10000')
                command=dict(schemaVersion=1,artifact='QA-COMMAND-1',sessionId=sid,revision=revision,kind='AUTHORED_QA_CHANGE')
                store.append(sid,f'cmd:{revision}',command,proposed)
                current=proposed
            elapsed=time.perf_counter()-started
            resumed=store.recover(sid)
            self.assertEqual(canonical_bytes(resumed),canonical_bytes(current))
            self.assertEqual(sum(o['status']=='CLOSED' for o in resumed['orders'].values()),255)
            self.assertEqual(resumed['orders']['active:1']['status'],'ACTIVE')
            command=dict(schemaVersion=1,artifact='QA-COMMAND-1',sessionId=sid,revision=256,kind='AUTHORED_QA_CHANGE')
            row=store.append(sid,'cmd:256',command,current)
            self.assertEqual(row['body']['revision'],256)
            conflict=dict(command,kind='DIFFERENT')
            with self.assertRaisesRegex(ValueError,'REFUSED_IDEMPOTENCY_CONFLICT'):
                store.append(sid,'cmd:256',conflict,current)
            base,delta=store.sizes(sid)
            full_bytes=len(canonical_bytes(current))
            receipt_row=store.db.execute('SELECT payload,sha FROM qa3_delta WHERE session=? AND revision=256',(sid,)).fetchone()
            receipt_bytes=len(receipt_row[0])
            self.assertLess(receipt_bytes,full_bytes)
            bad=bytearray(receipt_row[0]);bad[-2]^=1
            with store.db:store.db.execute('UPDATE qa3_delta SET payload=? WHERE session=? AND revision=256',(bytes(bad),sid))
            with self.assertRaisesRegex(ValueError,'CORRUPT_RECORD'):
                store.recover(sid)
            self.result=dict(fullStateBytes=full_bytes,baseSnapshotBytes=base,totalDeltaBytes=delta,
                             finalReceiptBytes=receipt_bytes,reconstructionSeconds=elapsed,corruption='PASS',
                             parity='PASS',retry='PASS')

    def test_process_kill_after_committed_delta_and_identical_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=os.path.join(tmp,'qa.sqlite')
            store=QAStateDeltaStore(path);initial=state(0,{});store.create('session:crash',initial);store.db.close()
            code='''import os,sys\nfrom execution.observed_state_delta_v3 import QAStateDeltaStore\nfrom tests.test_observed_state_delta_v3 import state\np=sys.argv[1];s=QAStateDeltaStore(p);v=state(1,{"closed:1":{"id":"closed:1","status":"CLOSED","grossPosted":"0"}});s.append("session:crash","cmd:1",{"schemaVersion":1,"artifact":"QA-COMMAND-1","revision":1},v);os._exit(91)'''
            env=dict(os.environ,PYTHONPATH='backend')
            proc=subprocess.run([sys.executable,'-c',code,path],env=env,timeout=30)
            self.assertEqual(proc.returncode,91)
            recovered=QAStateDeltaStore(path);wanted=state(1,{'closed:1':dict(id='closed:1',status='CLOSED',grossPosted='0')})
            self.assertEqual(canonical_bytes(recovered.recover('session:crash')),canonical_bytes(wanted))
            again=recovered.append('session:crash','cmd:1',{'schemaVersion':1,'artifact':'QA-COMMAND-1','revision':1},wanted)
            self.assertEqual(again['body']['revision'],1)


if __name__=='__main__':unittest.main()
