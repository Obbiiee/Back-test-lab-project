"""Independent QA decoder/auditor. Does not import the DAG writer or its cache."""
import hashlib,json,zlib
from fractions import Fraction
from contracts.canonical import canonical_bytes,content_hash
from execution.observed_kernel import validate_snapshot


def decode(payload,expected,objects=None):
    payload=bytes(payload)
    if objects is None:raw=payload
    else:
        prefix=b'QA6-DAG-ROOT-1\0';node_prefix=b'QA6-DAG-ZLIB-1\0'
        if not payload.startswith(prefix) or len(payload)!=len(prefix)+32:raise ValueError('ROOT_FORMAT')
        visiting=set();budget=[0]
        def visit(value,depth=0):
            budget[0]+=1
            if budget[0]>16384 or depth>32:raise ValueError('DECODE_LIMIT')
            if not isinstance(value,dict):return value
            if len(value)!=1:raise ValueError('NODE_SHAPE')
            if 'r' in value:
                digest=bytes.fromhex(value['r'])
                if len(digest)!=32 or digest in visiting or digest not in objects:raise ValueError('MISSING_OR_CYCLIC_OBJECT')
                packed=objects[digest]
                if not packed.startswith(node_prefix):raise ValueError('OBJECT_FORMAT')
                inflater=zlib.decompressobj();body=inflater.decompress(packed[len(node_prefix):],1048577)
                if len(body)>1048576 or not inflater.eof or inflater.unused_data or inflater.unconsumed_tail:raise ValueError('INFLATION_OR_TRAILING')
                if hashlib.sha256(body).digest()!=digest:raise ValueError('OBJECT_HASH')
                node=json.loads(body)
                if json.dumps(node,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()!=body:raise ValueError('OBJECT_CANONICAL')
                visiting.add(digest);result=visit(node,depth);visiting.remove(digest);return result
            if 'd' in value:
                result={};keys=[]
                for key,child in value['d']:
                    if not isinstance(key,str) or key in result:raise ValueError('DUPLICATE_KEY')
                    result[key]=visit(child,depth+1);keys.append(key)
                if keys!=sorted(keys):raise ValueError('KEY_ORDER')
                return result
            if 'l' in value:return [visit(child,depth+1) for child in value['l']]
            raise ValueError('UNKNOWN_NODE')
        raw=canonical_bytes(visit({'r':payload[len(prefix):].hex()}))
    if len(raw)>1048576 or hashlib.sha256(raw).hexdigest()!=expected:raise ValueError('LOGICAL_HASH')
    value=json.loads(raw)
    if canonical_bytes(value)!=raw:raise ValueError('LOGICAL_CANONICAL')
    return value,raw


def fetch(db,workspace,session,compact):
    objects=None
    if compact:objects={bytes(k):bytes(v) for k,v in db.execute('SELECT hash,body FROM public.qa6_objects')}
    args=(workspace,session)
    return dict(objects=objects,
        commands=db.execute('SELECT revision,command_id,command_hash,payload,content_hash FROM btl.tick_commands WHERE workspace_id=%s AND session_id=%s ORDER BY revision',args).fetchall(),
        checkpoints=db.execute('SELECT revision,payload,content_hash FROM btl.tick_checkpoints WHERE workspace_id=%s AND session_id=%s ORDER BY revision',args).fetchall(),
        events=db.execute('SELECT sequence,event_id,payload,content_hash FROM btl.tick_events WHERE workspace_id=%s AND session_id=%s ORDER BY sequence',args).fetchall(),
        tip=db.execute('SELECT payload,content_hash FROM btl.tick_sessions WHERE workspace_id=%s AND session_id=%s',args).fetchone())


def audit(data,commands,seed,cycles,oracle=None):
    objects=data['objects'];receipts=[];events=[];checkpoints=[];stream=hashlib.sha256()
    if len(data['commands'])!=len(commands) or len(data['checkpoints'])!=len(commands)+1:raise ValueError('HISTORY_LENGTH')
    for expected_revision,(row,command) in enumerate(zip(data['commands'],commands),1):
        revision,cid,intent_hash,payload,sha=row;value,raw=decode(payload,sha,objects)
        if revision!=expected_revision or cid!=command['commandId'] or intent_hash!=content_hash(command) or value['commandHash']!=intent_hash or value['commandId']!=cid:raise ValueError('COMMAND_ORDER_IDENTITY')
        if value['state']['revision']!=revision or value['durable'] is not True:raise ValueError('RECEIPT_STATE')
        stream.update(len(raw).to_bytes(4,'big'));stream.update(raw);receipts.append(value)
    for revision,(actual,payload,sha) in enumerate(data['checkpoints']):
        value,raw=decode(payload,sha,objects)
        if actual!=revision:raise ValueError('CHECKPOINT_ORDER')
        validate_snapshot(value['state'],value['controller'])
        if revision and value['state']!=receipts[revision-1]['state']:raise ValueError('CHECKPOINT_RECEIPT')
        if not revision and value!=seed:raise ValueError('SEED_CHANGED')
        checkpoints.append(value)
    previous=seed['state']['eventHash'];cash=Fraction(seed['state']['balance']);entries={};reasons={'TP':0,'SL':0}
    for expected_sequence,(sequence,eid,payload,sha) in enumerate(data['events']):
        event,raw=decode(payload,sha,objects)
        if sequence!=expected_sequence or event['sequence']!=sequence or event['eventId']!=eid or event['previousHash']!=previous or content_hash({k:v for k,v in event.items() if k!='eventId'})!=eid:raise ValueError('EVENT_CHAIN')
        previous=eid;events.append(event)
        if event['kind']=='ORDER_ACCEPTED':
            state=receipts[next(i for i,c in enumerate(commands) if c['commandId']==event['orderId'])]['state']
            if state['orders'][event['orderId']]['status']!='PENDING':raise ValueError('ORDER_NOT_PENDING')
            entries[event['orderId']]=event['detail']['availableNs']
        if event['kind']=='ENTRY_FILL':
            limit='limit' in event['orderId'];price='2299' if limit else '2302.1'
            if event['detail']['price']!=price or int(event['detail']['evidence']['timeNs'])<=int(entries[event['orderId']]):raise ValueError('PENDING_EXECUTION_ORACLE')
        if event['kind']=='EXIT_FILL':
            limit='limit' in event['orderId'];reason='TP' if limit else 'SL';expected=Fraction(2) if limit else Fraction('-2.2')
            if event['detail']['reason']!=reason or event['detail']['price']!=('2301' if limit else '2299.9') or Fraction(event['detail']['grossPosted'])!=expected or event['detail']['commission']!='0':raise ValueError('FINANCIAL_ORACLE')
            reasons[reason]+=1;cash+=Fraction(event['detail']['balanceDelta'])
    flattened=[e for receipt in receipts for e in receipt['events']]
    if flattened!=events:raise ValueError('EVENT_COMPLETENESS')
    final=checkpoints[-1]['state'];tip,_=decode(data['tip'][0],data['tip'][1],objects)
    if tip!=checkpoints[-1] or bytes(data['tip'][0])!=bytes(data['checkpoints'][-1][1]):raise ValueError('IMMUTABLE_TIP')
    oracle=oracle or dict(TP=cycles,SL=cycles,balance=Fraction(10000)-Fraction(cycles,5),orders=cycles*2)
    if reasons!={'TP':oracle['TP'],'SL':oracle['SL']} or cash!=Fraction(oracle['balance']) or Fraction(final['balance'])!=cash or final['eventHash']!=previous or final['nextEventIndex']!=len(events):raise ValueError('FINAL_FINANCIAL_RECONCILIATION')
    if final['unresolved'] or len(final['orders'])!=oracle['orders'] or any(o['status']!='CLOSED' for o in final['orders'].values()):raise ValueError('FINAL_ORDERS')
    return dict(status='PASS',receipts=len(receipts),events=len(events),checkpoints=len(checkpoints),TP=reasons['TP'],SL=reasons['SL'],balance=final['balance'],receiptStreamHash=stream.hexdigest(),finalStateHash=content_hash(final))
