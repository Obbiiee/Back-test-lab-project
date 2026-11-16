"""Independent integrated QA verifier; no writer indexes, codec decoder or caches."""
import hashlib,json,sqlite3,zlib
from contextlib import closing
from fractions import Fraction
from contracts.canonical import canonical_bytes,content_hash
from ticks.contracts_v2 import canonical_v2_bytes,hash_v2
from ticks.timeline_v2 import IndexedTickTimeline
from execution.observed_kernel import apply,validate_snapshot
from tests.qa_pg_verify6 import decode
from tests.qa_range_verifier5 import source_groups


def inflate(packed):
    z=zlib.decompressobj();raw=z.decompress(bytes(packed),1048577)
    if len(raw)>1048576 or not z.eof or z.unused_data or z.unconsumed_tail:raise ValueError('ENCODING')
    value=json.loads(raw)
    if canonical_bytes(value)!=raw:raise ValueError('CANONICAL')
    return value,raw


def history(data,path,binding,committed,candidate):
    with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)) as db:
        stored=db.execute('SELECT hash,body FROM binding').fetchall()
        if stored!=[(content_hash(binding),canonical_bytes(binding))]:raise ValueError('BINDING')
        intents={}
        for cid,sha,packed in db.execute('SELECT id,hash,body FROM intents'):
            value,raw=inflate(packed)
            if hashlib.sha256(raw).hexdigest()!=sha or value['commandId']!=cid:raise ValueError('INTENT_HASH')
            intents[cid]=(sha,value)
        prepared={}
        for sha,seq,packed in db.execute('SELECT hash,seq,body FROM prepared'):
            value,raw=inflate(packed)
            if hashlib.sha256(raw).hexdigest()!=sha or value['seq']!=seq or sha in prepared:raise ValueError('RANGE_HASH')
            prepared[sha]=value
    if candidate and len(committed)!=len(data['commands']):raise ValueError('COMMIT_COUNT')
    commands=[];ranges=[];previous=None;end='0'
    for index,row in enumerate(data['commands'],1):
        revision,cid,sha,_,_=row
        if revision!=index or cid not in intents or intents[cid][0]!=sha:raise ValueError('COMMAND_SEQUENCE')
        command=intents[cid][1]
        if command['expectedRevision']!=index-1:raise ValueError('COMMAND_REVISION')
        commands.append(command)
        if candidate:
            rrev,rcid,rsha=committed[index-1]
            if rrev!=index or rcid!=cid or rsha not in prepared:raise ValueError('MISSING_PREPARE')
            obj=prepared[rsha]
            if obj['schemaVersion']!=1 or obj['seq']!=index or obj['format']!='RIKSORA-QA-INTEGRATED-SESSION-1' or obj['bindingHash']!=content_hash(binding) or obj['previousHash']!=previous or obj['commandId']!=cid or obj['commandHash']!=sha or obj['kind']!=command['kind'] or obj['targetNs']!=command['payload'].get('targetNs'):raise ValueError('RANGE_CHAIN')
            if obj['groupStart']!=end or int(obj['groupEnd'])<int(end):raise ValueError('RANGE_CONTINUITY')
            previous=rsha;end=obj['groupEnd'];ranges.append(obj)
    return commands,ranges


def verify(data,path,binding,committed,candidate,provider,scratch):
    commands,ranges=history(data,path,binding,committed,candidate)
    if len(data['checkpoints'])!=len(commands)+1:raise ValueError('CHECKPOINT_COUNT')
    seed,_=decode(data['checkpoints'][0][1],data['checkpoints'][0][2],data['objects']);validate_snapshot(seed['state'],seed['controller'])
    if seed['state']['datasetId']!=provider.dataset_id or seed['state']['datasetVersion']!=provider.dataset_version or seed['state']['profileHash']!=binding['profileHash']:raise ValueError('SOURCE_PROFILE')
    engine=IndexedTickTimeline(provider,provider.dataset_id,provider.dataset_version,seed['state']['startNs'],log_folder=scratch,log_codec='zlib-1')
    source=source_groups(provider,seed['state']['startNs']);state=seed['state'];old=seed['controller'];events=[];groups=0;ticks=0;zero=0;receipts_hash=hashlib.sha256();group_hash=hashlib.sha256()
    try:
        for i,(command,row) in enumerate(zip(commands,data['commands'])):
            receipt,raw=decode(row[3],row[4],data['objects']);receipts_hash.update(len(raw).to_bytes(4,'big'));receipts_hash.update(raw)
            kwargs={};frame=None
            if command['kind']=='ADVANCE':
                frame=engine.advance_through(command['payload']['targetNs'],engine.cursor);kwargs=dict(reveal=frame,checkpoint=engine.checkpoint())
                if not frame['groups']:zero+=1
            cp=engine.checkpoint();state,produced=apply(state,command,**kwargs)
            checkpoint,_=decode(data['checkpoints'][i+1][1],data['checkpoints'][i+1][2],data['objects'])
            if checkpoint['state']!=state or checkpoint['controller']!=cp or data['checkpoints'][i+1][0]!=i+1:raise ValueError('CHECKPOINT_REPLAY')
            if receipt['state']!=state or receipt['events']!=produced or receipt['commandHash']!=content_hash(command):raise ValueError('FINANCIAL_RECEIPT')
            proof=hashlib.sha256(b'RIKSORA-QA-POSITIONS-1\0');first=None
            for offset,group in enumerate(frame['groups'] if frame else []):
                position,actual=next(source)
                if actual!=group or int(actual['timeNs'])>int(cp['cursor']['throughNs']):raise ValueError('SOURCE_GROUP')
                if first is None:first=position
                record=dict(groupIndex=str(int(old['cursor']['nextGroupIndex'])+offset),position=position,groupId=actual['groupId'],successorCursorHash=hash_v2(cp['cursor']))
                body=canonical_v2_bytes(dict(schemaVersion=2,artifact='RIKSORA-QA-POSITION-COMMIT-1',record=record));proof.update(len(body).to_bytes(4,'big'));proof.update(body)
                group_hash.update(json.dumps(actual,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode());groups+=1;ticks+=len(group['events'])
            if candidate:
                obj=ranges[i]
                expected=dict(beforeCursorHash=hash_v2(old['cursor']),afterCursorHash=hash_v2(cp['cursor']),groupStart=old['cursor']['nextGroupIndex'],groupEnd=cp['cursor']['nextGroupIndex'],firstPosition=first,positionCommitment=proof.hexdigest(),advanceLogHash=cp['advanceLogHash'],positionLogHash=cp['positionLogHash'])
                if any(obj[k]!=v for k,v in expected.items()):raise ValueError('SOURCE_RANGE_PROOF')
            old=cp;events.extend(produced)
        sql_events=[];previous=seed['state']['eventHash'];cash=Fraction(seed['state']['balance'])
        for seq,row in enumerate(data['events']):
            event,_=decode(row[2],row[3],data['objects'])
            if row[0]!=seq or event['sequence']!=seq or event['previousHash']!=previous or event['eventId']!=row[1] or event['eventId']!=content_hash({k:v for k,v in event.items() if k!='eventId'}):raise ValueError('EVENT_CHAIN')
            previous=event['eventId'];sql_events.append(event)
            if event['classification']=='SIMULATED_FILL':cash+=Fraction(event['detail']['balanceDelta'])
        tip,_=decode(data['tip'][0],data['tip'][1],data['objects'])
        if sql_events!=events or cash!=Fraction(state['balance']) or state['eventHash']!=previous or tip['state']!=state or tip['controller']!=old or bytes(data['tip'][0])!=bytes(data['checkpoints'][-1][1]):raise ValueError('CROSS_STORE_FINANCIAL_TIP')
        return dict(status='PASS',commands=len(commands),events=len(events),groups=groups,ticks=ticks,zeroRevealAdvances=zero,
                    balance=state['balance'],orders=len(state['orders']),closedOrders=sum(o['status']=='CLOSED' for o in state['orders'].values()),
                    TP=sum(e['kind']=='EXIT_FILL' and e['detail']['reason']=='TP' for e in events),SL=sum(e['kind']=='EXIT_FILL' and e['detail']['reason']=='SL' for e in events),
                    checkpoint=old,stateHash=content_hash(state),receiptStreamHash=receipts_hash.hexdigest(),groupHash=group_hash.hexdigest())
    finally:engine.close()
