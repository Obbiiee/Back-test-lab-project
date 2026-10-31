"""QA-only snapshot-plus-delta encoding for complete observed financial states.

The financial reducer still consumes/validates the full logical order map.
Only the durable representation stores the first full snapshot and subsequent
order-map changes. Not mounted by the application or production stores.
"""
from copy import deepcopy
import hashlib
import json

from contracts.canonical import canonical_bytes, content_hash
from contracts.primitives import require

ARTIFACT = 'BTL-QA-OBSERVED-STATE-DELTA-3'
ARTIFACT_V4 = 'BTL-QA-OBSERVED-STATE-DELTA-4'


def encode_base(state):
    raw=canonical_bytes(state)
    return dict(schemaVersion=1,formatVersion=3,artifact=ARTIFACT+'-BASE',revision=state['revision'],state=state,
                stateHash=hashlib.sha256(raw).hexdigest())


def encode_delta(previous,state,previous_hash):
    require(state['revision']==previous['revision']+1,'revision','CORRUPT_RECORD')
    old=previous['orders'];new=state['orders']
    changed={k:v for k,v in new.items() if k not in old or json.dumps(old[k],sort_keys=True,separators=(',',':'))!=json.dumps(v,sort_keys=True,separators=(',',':'))}
    removed=sorted(set(old)-set(new))
    scalars={k:deepcopy(v) for k,v in state.items() if k!='orders'}
    core=dict(schemaVersion=3,artifact=ARTIFACT,revision=state['revision'],previousHash=previous_hash,
              scalarState=scalars,orderUpserts=changed,orderDeletes=removed)
    core['stateHash']=hashlib.sha256(canonical_bytes(state)).hexdigest()
    core['recordHash']=content_hash(dict(schemaVersion=1,artifact=ARTIFACT+'-RECORD',body=core))
    return dict(schemaVersion=1,formatVersion=3,artifact=ARTIFACT+'-DELTA',body=core)


def encode_delta_v4(previous,state,previous_hash):
    """Sparse scalar/order transition; immutable base fields are not recopied."""
    require(state['revision']==previous['revision']+1,'revision','CORRUPT_RECORD')
    def same(left,right):
        return json.dumps(left,sort_keys=True,separators=(',',':'),ensure_ascii=False)==json.dumps(right,sort_keys=True,separators=(',',':'),ensure_ascii=False)
    old={k:v for k,v in previous.items() if k!='orders'}
    new={k:v for k,v in state.items() if k!='orders'}
    scalar_upserts={k:deepcopy(v) for k,v in new.items()
                    if k not in old or not same(old[k],v)}
    scalar_deletes=sorted(set(old)-set(new))
    old_orders=previous['orders'];new_orders=state['orders']
    order_upserts={k:deepcopy(v) for k,v in new_orders.items()
                   if k not in old_orders or not same(old_orders[k],v)}
    core=dict(schemaVersion=4,artifact=ARTIFACT_V4,revision=state['revision'],previousHash=previous_hash,
              scalarUpserts=scalar_upserts,scalarDeletes=scalar_deletes,
              orderUpserts=order_upserts,orderDeletes=sorted(set(old_orders)-set(new_orders)))
    core['stateHash']=hashlib.sha256(canonical_bytes(state)).hexdigest()
    core['recordHash']=content_hash(dict(schemaVersion=1,artifact=ARTIFACT_V4+'-RECORD',body=core))
    return dict(schemaVersion=1,formatVersion=4,artifact=ARTIFACT_V4+'-DELTA',body=core)


def reconstruct(base,deltas):
    require(base.get('schemaVersion')==1 and base.get('formatVersion')==3
            and base.get('artifact') in (ARTIFACT+'-BASE','BTL-OBSERVED-EXECUTION-CHECKPOINT-BASE-3'),
            'base','CORRUPT_RECORD')
    state=deepcopy(base['state']);prev=base['stateHash']
    require(hashlib.sha256(canonical_bytes(state)).hexdigest()==prev,'baseHash','CORRUPT_RECORD')
    for row in deltas:
        core=row.get('body',{})
        body={k:v for k,v in core.items() if k!='recordHash'}
        if row.get('formatVersion')==3 and row.get('artifact')==ARTIFACT+'-DELTA':
            require(core['recordHash']==content_hash(dict(schemaVersion=1,artifact=ARTIFACT+'-RECORD',body=body)),
                    'deltaChain','CORRUPT_RECORD')
        elif row.get('formatVersion')==4 and row.get('artifact')==ARTIFACT_V4+'-DELTA':
            require(core['schemaVersion']==4 and core['artifact']==ARTIFACT_V4 and
                    core['recordHash']==content_hash(dict(schemaVersion=1,artifact=ARTIFACT_V4+'-RECORD',body=body)),
                    'deltaChain','CORRUPT_RECORD')
        else:
            require(False,'deltaVersion','CORRUPT_RECORD')
        require(core['previousHash']==prev and core['revision']==state['revision']+1,
                'deltaChain','CORRUPT_RECORD')
        orders=state['orders']
        for oid in core['orderDeletes']:
            require(oid in orders,'missingDeleteTarget','CORRUPT_RECORD');del orders[oid]
        for oid,value in core['orderUpserts'].items():orders[oid]=deepcopy(value)
        if row['formatVersion']==3:
            require(core['scalarState']['revision']==core['revision'],'revision','CORRUPT_RECORD')
            state=deepcopy(core['scalarState']);state['orders']=orders
        else:
            scalars={k:deepcopy(v) for k,v in state.items() if k!='orders'}
            for key in core['scalarDeletes']:
                require(key in scalars,'missingScalarDeleteTarget','CORRUPT_RECORD');del scalars[key]
            scalars.update(deepcopy(core['scalarUpserts']))
            require(scalars.get('revision')==core['revision'],'revision','CORRUPT_RECORD')
            state=scalars;state['orders']=orders
        require(hashlib.sha256(canonical_bytes(state)).hexdigest()==core['stateHash'],'stateHash','CORRUPT_RECORD')
        prev=core['recordHash']
    return state


def reconstruct_complete(base,deltas,expected_revision):
    require(type(expected_revision) is int and expected_revision>=0 and len(deltas)==expected_revision,
            'deltaCount','CORRUPT_RECORD')
    state=reconstruct(base,deltas)
    require(state['revision']==expected_revision,'deltaRevision','CORRUPT_RECORD')
    return state


class QAStateDeltaStore:
    """Small private SQLite-backed oracle for atomic snapshot/delta recovery."""
    def __init__(self,path):
        import sqlite3
        self.db=sqlite3.connect(path)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript('''CREATE TABLE IF NOT EXISTS qa3_base(session TEXT PRIMARY KEY,payload BLOB NOT NULL,sha TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS qa3_delta(session TEXT NOT NULL,revision INTEGER NOT NULL,command_id TEXT NOT NULL,command_hash TEXT NOT NULL,payload BLOB NOT NULL,sha TEXT NOT NULL,PRIMARY KEY(session,revision),UNIQUE(session,command_id));''')

    @staticmethod
    def _pack(row):
        raw=canonical_bytes(row);return raw,hashlib.sha256(raw).hexdigest()

    def create(self,session,state):
        base=encode_base(state);raw,sha=self._pack(base)
        with self.db:self.db.execute('INSERT INTO qa3_base VALUES(?,?,?)',(session,raw,sha))

    def append(self,session,command_id,command,state):
        ch=content_hash(command)
        existing=self.db.execute('SELECT command_hash,payload,sha FROM qa3_delta WHERE session=? AND command_id=?',(session,command_id)).fetchone()
        if existing:
            require(existing[0]==ch,'retry','REFUSED_IDEMPOTENCY_CONFLICT')
            raw=bytes(existing[1]);require(hashlib.sha256(raw).hexdigest()==existing[2],'receiptHash','CORRUPT_RECORD')
            return json.loads(raw)
        previous=self.recover(session)
        base_raw,base_sha=self.db.execute('SELECT payload,sha FROM qa3_base WHERE session=?',(session,)).fetchone()
        base=json.loads(base_raw);deltas=[json.loads(r[0]) for r in self.db.execute('SELECT payload FROM qa3_delta WHERE session=? ORDER BY revision',(session,))]
        prior_hash=deltas[-1]['body']['recordHash'] if deltas else base['stateHash']
        row=encode_delta(previous,state,prior_hash);raw,sha=self._pack(row)
        with self.db:self.db.execute('INSERT INTO qa3_delta VALUES(?,?,?,?,?,?)',(session,state['revision'],command_id,ch,raw,sha))
        return row

    def recover(self,session):
        row=self.db.execute('SELECT payload,sha FROM qa3_base WHERE session=?',(session,)).fetchone()
        require(row is not None,'base','CORRUPT_RECORD');raw,sha=row
        require(hashlib.sha256(bytes(raw)).hexdigest()==sha,'baseReceipt','CORRUPT_RECORD')
        base=json.loads(raw);deltas=[]
        for revision,payload,expected in self.db.execute('SELECT revision,payload,sha FROM qa3_delta WHERE session=? ORDER BY revision',(session,)):
            require(hashlib.sha256(bytes(payload)).hexdigest()==expected,'deltaReceipt','CORRUPT_RECORD')
            item=json.loads(payload);require(item['body']['revision']==revision,'deltaRevision','CORRUPT_RECORD');deltas.append(item)
        return reconstruct(base,deltas)

    def sizes(self,session):
        base=self.db.execute('SELECT length(payload) FROM qa3_base WHERE session=?',(session,)).fetchone()[0]
        delta=self.db.execute('SELECT coalesce(sum(length(payload)),0) FROM qa3_delta WHERE session=?',(session,)).fetchone()[0]
        return int(base),int(delta)
