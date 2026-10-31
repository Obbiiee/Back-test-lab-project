"""Separate observed-family transactional boundary on existing opaque tick tables.

No migration or old-family dispatch changes. Market work happens outside row
locks; only validated proposals after CAS become published SIMULATED_FILLs.
"""
from copy import deepcopy
from fractions import Fraction

from contracts.canonical import canonical_bytes,content_hash
from contracts.primitives import require,revision
from ticks.contracts import keys
from infrastructure.database import connect
from .postgres import pack,unpack,scoped
from .observed_profile import ENGINE_VERSION,MODEL
from .observed_kernel import command_wire,validate_state,validate_snapshot,order_limits,MAX_EVENTS
from .observed_state_delta_v3 import encode_base,encode_delta,encode_delta_v4,reconstruct_complete

PAGE_EVENTS=64
EVENT_FIELDS='schemaVersion artifact engineVersion model sessionId datasetId datasetVersion profileHash methodHash sequence previousHash kind classification orderId detail eventId'
CLASSIFICATIONS={**{k:'SIMULATED_FILL' for k in ('ENTRY_FILL','EXIT_FILL')},**{k:'UNRESOLVED' for k in ('UNRESOLVED','UNUSABLE_OBSERVATION','EXPIRED_NO_QUOTE')},**{k:'ACCEPTED_COMMAND' for k in ('ORDER_ACCEPTED','ORDER_CANCELLED','EXIT_REQUESTED','SESSION_ENDED')},**{k:'OBSERVED_FEED_EVENT' for k in ('REPLAY_ADVANCED','CHRONOLOGY_LIMITATION','DATA_GAP_LIMITATION','STALE_QUOTE')}}
QA3_CHECKPOINT='BTL-OBSERVED-EXECUTION-CHECKPOINT-3'
QA3_CHECKPOINT_BASE='BTL-OBSERVED-EXECUTION-CHECKPOINT-BASE-3'
QA3_CHECKPOINT_DELTA='BTL-OBSERVED-EXECUTION-CHECKPOINT-DELTA-3'
QA3_RESULT='BTL-OBSERVED-EXECUTION-RESULT-3'


def read_snapshot(raw,sha,*,order_retention_policy=None):
    value=unpack(raw,sha);keys(value,'schemaVersion artifact state controller')
    require(type(value['schemaVersion']) is int and value['schemaVersion']==1 and value['artifact']=='BTL-OBSERVED-EXECUTION-CHECKPOINT-1','snapshot','CORRUPT_RECORD')
    validate_snapshot(value['state'],value['controller'],order_retention_policy=order_retention_policy);return value


def check_events(events,state,start,previous):
    require(type(events) is list and len(events)<=MAX_EVENTS,'events')
    for e in events:
        keys(e,EVENT_FIELDS)
        require(type(e['schemaVersion']) is int and e['schemaVersion']==1 and e['artifact']=='BTL-OBSERVED-EXECUTION-EVENT-1'
                and e['engineVersion']==ENGINE_VERSION and e['model']==state['model'],'event','CORRUPT_RECORD')
        require(type(e['sequence']) is int and e['sequence']==start and e['previousHash']==previous
                and e['eventId']==content_hash({k:v for k,v in e.items() if k!='eventId'}),'eventChain','CORRUPT_RECORD')
        require(all(e[k]==state[k] for k in ('sessionId','datasetId','datasetVersion','profileHash')) and e['methodHash']==state['policy']['definitionHash'],'eventIdentity','CORRUPT_RECORD')
        require(e['kind'] in CLASSIFICATIONS and e['classification']==CLASSIFICATIONS[e['kind']],'classification','CORRUPT_RECORD')
        previous=e['eventId'];start+=1
    return start,previous


def checked_result(raw,sha,command,*,order_retention_policy=None):
    result=unpack(raw,sha);keys(result,'schemaVersion artifact commandId commandHash state events eventCount eventFromSequence eventsComplete nextEventSequence replay durable model')
    require(type(result['schemaVersion']) is int and result['schemaVersion']==1 and result['artifact']=='BTL-OBSERVED-EXECUTION-RESULT-1' and result['durable'] is True and result['model']==result['state']['model']
            and result['commandId']==command['commandId'] and result['commandHash']==content_hash(command),'receipt','CORRUPT_RECORD')
    if result['replay'] is not None:
        keys(result['replay'],'throughNs exhaustedThroughBoundary');require(command['kind']=='ADVANCE' and type(result['replay']['exhaustedThroughBoundary']) is bool and result['replay']['throughNs']==result['state']['throughNs'],'replay','CORRUPT_RECORD')
    else:require(command['kind']!='ADVANCE','replay')
    state=result['state'];validate_state(state,order_retention_policy=order_retention_policy);require(state['sessionId']==command['sessionId'],'session')
    total=result['eventCount'];start=result['eventFromSequence'];revision(start)
    require(type(total) is int and 0<=total<=MAX_EVENTS and start+total==state['nextEventIndex'] and len(result['events'])==min(total,PAGE_EVENTS),'receipt','CORRUPT_RECORD')
    previous=result['events'][0]['previousHash'] if result['events'] else state['eventHash'];end,head=check_events(result['events'],state,start,previous)
    require(result['eventsComplete'] is (total==len(result['events'])) and result['nextEventSequence']==(None if result['eventsComplete'] else end),'receipt')
    if result['eventsComplete']:require(head==state['eventHash'],'receipt','CORRUPT_RECORD')
    return result


def compact_qa3_checkpoint(state,controller,chain_hash):
    return dict(schemaVersion=1,formatVersion=3,artifact=QA3_CHECKPOINT,revision=state['revision'],
                stateHash=content_hash(state),chainHash=chain_hash,controller=deepcopy(controller))


def compact_qa3_checkpoint_delta(state,controller,delta):
    return dict(schemaVersion=1,formatVersion=3,artifact=QA3_CHECKPOINT_DELTA,revision=state['revision'],
                stateHash=content_hash(state),chainHash=delta['body']['recordHash'],
                previousHash=delta['body']['previousHash'],delta=delta,controller=deepcopy(controller))


def compact_qa3_receipt(result,state_hash,chain_hash):
    return dict(schemaVersion=1,formatVersion=3,artifact=QA3_RESULT,commandId=result['commandId'],commandHash=result['commandHash'],
                stateRevision=result['state']['revision'],stateHash=state_hash,chainHash=chain_hash,
                events=deepcopy(result['events']),eventCount=result['eventCount'],
                eventFromSequence=result['eventFromSequence'],eventsComplete=result['eventsComplete'],
                nextEventSequence=result['nextEventSequence'],replay=deepcopy(result['replay']),
                durable=True,model=result['model'])


def expand_qa3_receipt(record,command,state,chain_hash,*,order_retention_policy=None):
    keys(record,'schemaVersion formatVersion artifact commandId commandHash stateRevision stateHash chainHash events eventCount eventFromSequence eventsComplete nextEventSequence replay durable model')
    require(record['schemaVersion']==1 and record['formatVersion']==3 and record['artifact']==QA3_RESULT and record['durable'] is True,
            'receiptVersion','CORRUPT_RECORD')
    require(record['commandId']==command['commandId'] and record['commandHash']==content_hash(command),
            'receipt','CORRUPT_RECORD')
    require(record['stateRevision']==state['revision'] and record['stateHash']==content_hash(state)
            and record['chainHash']==chain_hash and record['model']==state['model'],
            'receiptState','CORRUPT_RECORD')
    result=dict(schemaVersion=1,artifact='BTL-OBSERVED-EXECUTION-RESULT-1',commandId=record['commandId'],
                commandHash=record['commandHash'],state=state,events=record['events'],eventCount=record['eventCount'],
                eventFromSequence=record['eventFromSequence'],eventsComplete=record['eventsComplete'],
                nextEventSequence=record['nextEventSequence'],replay=record['replay'],durable=True,model=record['model'])
    raw,sha=pack(result)
    return checked_result(raw,sha,command,order_retention_policy=order_retention_policy)


class ObservedExecutionStore:
    def __init__(self,dsn,*,order_retention_policy=None,qa_state_delta_v3=False):
        order_limits(order_retention_policy)
        require(type(qa_state_delta_v3) is bool,'qaStateDeltaV3')
        self.dsn=dsn;self.order_retention_policy=deepcopy(order_retention_policy);self.qa_state_delta_v3=qa_state_delta_v3

    def _has_qa_base(self,db,workspace,session):
        if not self.qa_state_delta_v3:return False
        if db.execute("SELECT to_regclass('public.btl_qa_state_base_v3')").fetchone()[0] is None:return False
        return db.execute('SELECT 1 FROM public.btl_qa_state_base_v3 WHERE workspace_id=%s AND session_id=%s',(workspace,session)).fetchone() is not None

    def _qa_reconstruct(self,db,workspace,session,*,upto_revision=None,require_tip=False):
        base_row=db.execute('SELECT payload,content_hash FROM btl.tick_checkpoints WHERE workspace_id=%s AND session_id=%s AND revision=0',(workspace,session)).fetchone()
        require(base_row is not None,'qaDeltaBase','CORRUPT_RECORD')
        base_record=unpack(*base_row)
        if base_record.get('artifact')==QA3_CHECKPOINT_BASE:
            keys(base_record,'schemaVersion formatVersion artifact revision state stateHash chainHash controller')
            require(base_record['schemaVersion']==1 and base_record['formatVersion']==3 and base_record['revision']==0
                    and base_record['stateHash']==content_hash(base_record['state'])==base_record['chainHash'],
                    'qaDeltaBase','CORRUPT_RECORD')
            if upto_revision is None:
                delta_rows=db.execute('SELECT revision,payload,content_hash FROM btl.tick_checkpoints WHERE workspace_id=%s AND session_id=%s AND revision>0 ORDER BY revision',(workspace,session)).fetchall()
                target_revision=len(delta_rows)
            else:
                revision(upto_revision)
                delta_rows=db.execute('SELECT revision,payload,content_hash FROM btl.tick_checkpoints WHERE workspace_id=%s AND session_id=%s AND revision>0 AND revision<=%s ORDER BY revision',(workspace,session,upto_revision)).fetchall()
                target_revision=upto_revision
            if require_tip:
                total=db.execute('SELECT count(*) FROM btl.tick_checkpoints WHERE workspace_id=%s AND session_id=%s AND revision>0',(workspace,session)).fetchone()[0]
                require(total==target_revision,'qaDeltaRevision','CORRUPT_RECORD')
            require(len(delta_rows)==target_revision,'qaDeltaRevision','CORRUPT_RECORD')
            deltas=[];previous_hash=base_record['chainHash']
            for n,(rev,payload,sha) in enumerate(delta_rows,1):
                checkpoint=unpack(payload,sha)
                keys(checkpoint,'schemaVersion formatVersion artifact revision stateHash chainHash previousHash delta controller')
                delta=checkpoint['delta'];body=delta.get('body',{})
                require(checkpoint['schemaVersion']==1 and checkpoint['formatVersion']==3
                        and checkpoint['artifact']==QA3_CHECKPOINT_DELTA and checkpoint['revision']==rev==n
                        and checkpoint['previousHash']==previous_hash and body.get('revision')==rev
                        and checkpoint['stateHash']==body.get('stateHash')
                        and checkpoint['chainHash']==body.get('recordHash'),
                        'qaCheckpointDelta','CORRUPT_RECORD')
                deltas.append(delta);previous_hash=checkpoint['chainHash']
            rebuilt=reconstruct_complete(base_record,deltas,target_revision)
            require(rebuilt['revision']==target_revision,'qaDeltaState','CORRUPT_RECORD')
            return rebuilt,previous_hash

        # CP6A-3 compatibility: its full-state checkpoints were accompanied by
        # a separate v3 delta table. Keep reading/verifying that established form.
        require(self._has_qa_base(db,workspace,session),'qaDeltaBase','CORRUPT_RECORD')
        legacy_base=db.execute('SELECT payload,content_hash FROM public.btl_qa_state_base_v3 WHERE workspace_id=%s AND session_id=%s',(workspace,session)).fetchone()
        require(legacy_base is not None,'qaDeltaBase','CORRUPT_RECORD')
        base_record=unpack(*legacy_base)
        if upto_revision is None:
            delta_rows=db.execute('SELECT revision,payload,content_hash FROM public.btl_qa_state_delta_v3 WHERE workspace_id=%s AND session_id=%s ORDER BY revision',(workspace,session)).fetchall()
            target_revision=len(delta_rows)
        else:
            revision(upto_revision)
            delta_rows=db.execute('SELECT revision,payload,content_hash FROM public.btl_qa_state_delta_v3 WHERE workspace_id=%s AND session_id=%s AND revision<=%s ORDER BY revision',(workspace,session,upto_revision)).fetchall()
            target_revision=upto_revision
        if require_tip:
            total=db.execute('SELECT count(*) FROM public.btl_qa_state_delta_v3 WHERE workspace_id=%s AND session_id=%s',(workspace,session)).fetchone()[0]
            require(total==target_revision,'qaDeltaRevision','CORRUPT_RECORD')
        require(len(delta_rows)==target_revision,'qaDeltaRevision','CORRUPT_RECORD')
        deltas=[]
        for n,(rev,payload,sha) in enumerate(delta_rows,1):
            item=unpack(payload,sha);require(rev==n and item['body']['revision']==rev,'qaDeltaRevision','CORRUPT_RECORD');deltas.append(item)
        rebuilt=reconstruct_complete(base_record,deltas,target_revision)
        require(rebuilt['revision']==target_revision,'qaDeltaState','CORRUPT_RECORD')
        chain_hash=deltas[-1]['body']['recordHash'] if deltas else base_record['stateHash']
        return rebuilt,chain_hash

    def _read(self,db,workspace,session,*,lock=False,include_format=False):
        row=db.execute('SELECT payload,content_hash,revision,dataset_version,profile_hash FROM btl.tick_sessions WHERE workspace_id=%s AND session_id=%s'+(' FOR UPDATE' if lock else ''),(workspace,session)).fetchone()
        require(row is not None,'session','RESOURCE_UNAVAILABLE')
        wire=unpack(row[0],row[1])
        chain_hash=None
        if wire.get('artifact')==QA3_CHECKPOINT:
            require(self.qa_state_delta_v3,'qaSessionVersion','REFUSED_QA_SESSION_VERSION')
            keys(wire,'schemaVersion formatVersion artifact revision stateHash chainHash controller')
            require(wire['schemaVersion']==1 and wire['formatVersion']==3 and wire['revision']==row[2],'snapshot','CORRUPT_RECORD')
            state,chain_hash=self._qa_reconstruct(db,workspace,session,upto_revision=row[2],require_tip=True)
            require(wire['stateHash']==content_hash(state) and wire['chainHash']==chain_hash,'qaCheckpoint','CORRUPT_RECORD')
            validate_snapshot(state,wire['controller'],order_retention_policy=self.order_retention_policy)
            stored=dict(schemaVersion=1,artifact='BTL-OBSERVED-EXECUTION-CHECKPOINT-1',
                        state=state,controller=wire['controller']);storage_format='qa3'
        else:
            stored=read_snapshot(row[0],row[1],order_retention_policy=self.order_retention_policy);state=stored['state'];storage_format='legacy'
            # CP6A-3 full-state Sessions can retain their v3 delta sidecar; keep
            # verifying that historical path without rewriting their old bytes.
            if self._has_qa_base(db,workspace,session):
                rebuilt,_=self._qa_reconstruct(db,workspace,session,upto_revision=state['revision'],require_tip=True)
                require(canonical_bytes(rebuilt)==canonical_bytes(state),'qaDeltaState','CORRUPT_RECORD')
        s=stored['state']
        require(s['sessionId']==session and (s['revision'],s['datasetVersion'],s['profileHash'])==tuple(row[2:]),'state','CORRUPT_RECORD')
        tip=db.execute('SELECT payload,content_hash FROM btl.tick_checkpoints WHERE workspace_id=%s AND session_id=%s AND revision=%s',(workspace,session,s['revision'])).fetchone()
        require(tip is not None,'immutableTip','CORRUPT_RECORD')
        if storage_format=='qa3':
            tip_wire=unpack(*tip)
            require(tip_wire.get('artifact') in (QA3_CHECKPOINT_BASE,QA3_CHECKPOINT_DELTA)
                    and tip_wire.get('revision')==s['revision'] and tip_wire.get('stateHash')==content_hash(s)
                    and tip_wire.get('chainHash')==chain_hash and tip_wire.get('controller')==stored['controller'],
                    'immutableTip','CORRUPT_RECORD')
        else:
            require(bytes(tip[0])==bytes(row[0]) and tip[1]==row[1],'immutableTip','CORRUPT_RECORD')
        return (stored,storage_format,chain_hash) if include_format else stored

    def _prior(self,db,workspace,session,command):
        row=db.execute('SELECT revision,command_hash,payload,content_hash FROM btl.tick_commands WHERE workspace_id=%s AND session_id=%s AND command_id=%s',(workspace,session,command['commandId'])).fetchone()
        if row is None:return None
        require(row[1]==content_hash(command),'commandId','REFUSED_IDEMPOTENCY_CONFLICT')
        wire=unpack(row[2],row[3])
        if wire.get('artifact')==QA3_RESULT:
            require(self.qa_state_delta_v3,'receiptVersion','REFUSED_QA_RECEIPT_VERSION')
            require(wire.get('schemaVersion')==1 and wire.get('formatVersion')==3,'receiptVersion','CORRUPT_RECORD')
            require(type(wire.get('stateRevision')) is int and wire['stateRevision']==row[0],'receiptState','CORRUPT_RECORD')
            state,chain_hash=self._qa_reconstruct(db,workspace,session,upto_revision=wire['stateRevision'])
            return expand_qa3_receipt(wire,command,state,chain_hash,order_retention_policy=self.order_retention_policy)
        result=checked_result(row[2],row[3],command,order_retention_policy=self.order_retention_policy)
        require(result['state']['revision']==row[0],'receiptState','CORRUPT_RECORD')
        return result

    def _insert(self,db,scope,state,checkpoint):
        workspace,session=scoped(scope,state['sessionId']);require(state['revision']==0,'initialRevision')
        validate_snapshot(state,checkpoint,order_retention_policy=self.order_retention_policy)
        if self.qa_state_delta_v3:
            base_record=encode_base(state)
            base_record.update(artifact=QA3_CHECKPOINT_BASE,chainHash=base_record['stateHash'],controller=deepcopy(checkpoint))
            raw_base,sha_base=pack(base_record)
            raw,sha=pack(compact_qa3_checkpoint(state,checkpoint,base_record['chainHash']))
        else:
            raw,sha=pack(validate_snapshot(state,checkpoint,order_retention_policy=self.order_retention_policy))
        db.execute('INSERT INTO btl.tick_sessions VALUES (%s,%s,%s,%s,%s,%s,%s)',(workspace,session,state['datasetVersion'],state['profileHash'],0,raw,sha))
        if self.qa_state_delta_v3:db.execute('INSERT INTO btl.tick_checkpoints VALUES (%s,%s,%s,%s,%s)',(workspace,session,0,raw_base,sha_base))
        else:db.execute('INSERT INTO btl.tick_checkpoints VALUES (%s,%s,%s,%s,%s)',(workspace,session,0,raw,sha))

    def create(self,scope,state,checkpoint):
        with connect(self.dsn) as db:self._insert(db,scope,state,checkpoint)

    def prepare(self,scope,raw):
        command=command_wire(raw);workspace,session=scoped(scope,command['sessionId'])
        with connect(self.dsn) as db:
            db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY');stored=self._read(db,workspace,session);prior=self._prior(db,workspace,session,command)
            if prior is not None:return stored,prior
            require(stored['state']['revision']==command['expectedRevision'],'revision','REFUSED_STALE_REVISION');return stored,None

    def commit(self,scope,raw,before,after,checkpoint,events,replay=None):
        command=command_wire(raw);workspace,session=scoped(scope,command['sessionId'])
        with connect(self.dsn) as db:
            live,storage_format,prior_chain_hash=self._read(db,workspace,session,lock=True,include_format=True);prior=self._prior(db,workspace,session,command)
            if prior is not None:return prior
            old=live['state'];require(content_hash(live)==content_hash(before) and old['revision']==command['expectedRevision'],'revision','REFUSED_STALE_REVISION')
            require(after['revision']==old['revision']+1 and all(after[k]==old[k] for k in ('sessionId','datasetId','datasetVersion','engineVersion','model','profile','profileHash','policy','startNs','initialBalance','parent')),'immutableContext')
            validate_snapshot(after,checkpoint,order_retention_policy=self.order_retention_policy)
            end,head=check_events(events,after,old['nextEventIndex'],old['eventHash'])
            require(after['nextEventIndex']==end and after['eventHash']==head,'eventHead','CORRUPT_RECORD')
            postings=[e for e in events if e['classification']=='SIMULATED_FILL']
            require(all(e['detail']['commission']=='0' for e in postings) and after['commission']==old['commission']=='0'
                    and Fraction(after['balance'])-Fraction(old['balance'])==sum((Fraction(e['detail']['balanceDelta']) for e in postings),Fraction(0))
                    and Fraction(after['realizedGross'])-Fraction(old['realizedGross'])==sum((Fraction(e['detail']['grossPosted']) for e in postings if e['kind']=='EXIT_FILL'),Fraction(0)),'cashPosting','CORRUPT_RECORD')
            validate_snapshot(after,checkpoint,order_retention_policy=self.order_retention_policy)
            compact_mode=self.qa_state_delta_v3 and storage_format=='qa3'
            legacy_delta_mode=not compact_mode and self._has_qa_base(db,workspace,session)
            delta_record=None;chain_hash=None
            if compact_mode:
                delta_record=encode_delta_v4(old,after,prior_chain_hash)
                chain_hash=delta_record['body']['recordHash']
            elif legacy_delta_mode:
                prior_delta=db.execute('SELECT payload,content_hash FROM public.btl_qa_state_delta_v3 WHERE workspace_id=%s AND session_id=%s ORDER BY revision DESC LIMIT 1',(workspace,session)).fetchone()
                base_row=db.execute('SELECT payload,content_hash FROM public.btl_qa_state_base_v3 WHERE workspace_id=%s AND session_id=%s',(workspace,session)).fetchone()
                previous_hash=unpack(*prior_delta)['body']['recordHash'] if prior_delta else unpack(*base_row)['stateHash']
                delta_record=encode_delta(old,after,previous_hash);chain_hash=delta_record['body']['recordHash']
            if compact_mode:
                require(chain_hash is not None,'qaDeltaBase','CORRUPT_RECORD')
                checkpoint_wire=compact_qa3_checkpoint_delta(after,checkpoint,delta_record)
                session_wire=compact_qa3_checkpoint(after,checkpoint,chain_hash)
            else:
                checkpoint_wire=validate_snapshot(after,checkpoint,order_retention_policy=self.order_retention_policy)
                session_wire=checkpoint_wire
            checkpoint_raw,checkpoint_hash=pack(checkpoint_wire)
            session_raw,session_hash=pack(session_wire)
            page=deepcopy(events[:PAGE_EVENTS]);complete=len(page)==len(events)
            result=dict(schemaVersion=1,artifact='BTL-OBSERVED-EXECUTION-RESULT-1',commandId=command['commandId'],commandHash=content_hash(command),state=after,events=page,eventCount=len(events),eventFromSequence=old['nextEventIndex'],eventsComplete=complete,nextEventSequence=None if complete else old['nextEventIndex']+len(page),replay=replay,durable=True,model=after['model'])
            checked=checked_result(*pack(result),command,order_retention_policy=self.order_retention_policy)
            receipt_wire=compact_qa3_receipt(checked,content_hash(after),chain_hash) if compact_mode else result
            result_raw,result_hash=pack(receipt_wire)
            db.execute('INSERT INTO btl.tick_commands VALUES (%s,%s,%s,%s,%s,%s,%s)',(workspace,session,command['commandId'],after['revision'],content_hash(command),result_raw,result_hash))
            for e in events:
                eraw,esha=pack(e);db.execute('INSERT INTO btl.tick_events VALUES (%s,%s,%s,%s,%s,%s,%s)',(workspace,session,command['commandId'],e['eventId'],e['sequence'],eraw,esha))
            db.execute('INSERT INTO btl.tick_checkpoints VALUES (%s,%s,%s,%s,%s)',(workspace,session,after['revision'],checkpoint_raw,checkpoint_hash))
            db.execute('UPDATE btl.tick_sessions SET revision=%s,payload=%s,content_hash=%s WHERE workspace_id=%s AND session_id=%s',(after['revision'],session_raw,session_hash,workspace,session))
            if legacy_delta_mode:
                delta_raw,delta_hash=pack(delta_record)
                db.execute('INSERT INTO public.btl_qa_state_delta_v3 VALUES (%s,%s,%s,%s,%s,%s)',(workspace,session,after['revision'],command['commandId'],delta_raw,delta_hash))
        return deepcopy(result)

    def inspect(self,scope,session_id,after_sequence=0,maximum=64):
        workspace,session=scoped(scope,session_id);revision(after_sequence);require(type(maximum) is int and 1<=maximum<=PAGE_EVENTS,'maximum')
        with connect(self.dsn) as db:
            db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY');stored=self._read(db,workspace,session);state=stored['state']
            require(after_sequence<=state['nextEventIndex'],'eventOffset')
            if after_sequence==0:
                seed=db.execute('SELECT payload,content_hash FROM btl.tick_checkpoints WHERE workspace_id=%s AND session_id=%s AND revision=0',(workspace,session)).fetchone()
                seed_wire=unpack(*seed)
                if seed_wire.get('artifact')==QA3_CHECKPOINT_BASE:
                    require(self.qa_state_delta_v3,'qaSessionVersion','REFUSED_QA_SESSION_VERSION')
                    initial,_=self._qa_reconstruct(db,workspace,session,upto_revision=0)
                    require(seed_wire['stateHash']==content_hash(initial),'qaCheckpoint','CORRUPT_RECORD')
                    previous=initial['eventHash']
                else:
                    previous=read_snapshot(*seed,order_retention_policy=self.order_retention_policy)['state']['eventHash']
            else:
                prior=db.execute('SELECT payload,content_hash FROM btl.tick_events WHERE workspace_id=%s AND session_id=%s AND sequence=%s',(workspace,session,after_sequence-1)).fetchone();require(prior is not None,'event','CORRUPT_RECORD');previous=unpack(*prior)['eventId']
            rows=db.execute('SELECT payload,content_hash FROM btl.tick_events WHERE workspace_id=%s AND session_id=%s AND sequence>=%s AND sequence<%s ORDER BY sequence LIMIT %s',(workspace,session,after_sequence,state['nextEventIndex'],maximum)).fetchall();events=[unpack(*r) for r in rows]
            end,head=check_events(events,state,after_sequence,previous);require(len(events)==min(maximum,state['nextEventIndex']-after_sequence),'eventCount','CORRUPT_RECORD')
            if end==state['nextEventIndex']:require(head==state['eventHash'],'eventHead','CORRUPT_RECORD')
            return dict(state=state,events=events,nextEventSequence=None if end==state['nextEventIndex'] else end)
