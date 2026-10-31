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
from .observed_state_delta_v3 import encode_base,encode_delta,reconstruct

PAGE_EVENTS=64
EVENT_FIELDS='schemaVersion artifact engineVersion model sessionId datasetId datasetVersion profileHash methodHash sequence previousHash kind classification orderId detail eventId'
CLASSIFICATIONS={**{k:'SIMULATED_FILL' for k in ('ENTRY_FILL','EXIT_FILL')},**{k:'UNRESOLVED' for k in ('UNRESOLVED','UNUSABLE_OBSERVATION','EXPIRED_NO_QUOTE')},**{k:'ACCEPTED_COMMAND' for k in ('ORDER_ACCEPTED','ORDER_CANCELLED','EXIT_REQUESTED','SESSION_ENDED')},**{k:'OBSERVED_FEED_EVENT' for k in ('REPLAY_ADVANCED','CHRONOLOGY_LIMITATION','DATA_GAP_LIMITATION','STALE_QUOTE')}}


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


class ObservedExecutionStore:
    def __init__(self,dsn,*,order_retention_policy=None,qa_state_delta_v3=False):
        order_limits(order_retention_policy)
        require(type(qa_state_delta_v3) is bool,'qaStateDeltaV3')
        self.dsn=dsn;self.order_retention_policy=deepcopy(order_retention_policy);self.qa_state_delta_v3=qa_state_delta_v3

    @staticmethod
    def _ensure_qa_delta_tables(db):
        db.execute('''CREATE TABLE IF NOT EXISTS public.btl_qa_state_base_v3 (
            workspace_id text NOT NULL, session_id text NOT NULL, revision bigint NOT NULL,
            payload bytea NOT NULL, content_hash text NOT NULL,
            PRIMARY KEY(workspace_id,session_id))''')
        db.execute('''CREATE TABLE IF NOT EXISTS public.btl_qa_state_delta_v3 (
            workspace_id text NOT NULL, session_id text NOT NULL, revision bigint NOT NULL,
            command_id text NOT NULL, payload bytea NOT NULL, content_hash text NOT NULL,
            PRIMARY KEY(workspace_id,session_id,revision),
            UNIQUE(workspace_id,session_id,command_id),
            FOREIGN KEY(workspace_id,session_id,command_id)
                REFERENCES btl.tick_commands(workspace_id,session_id,command_id))''')

    def _verify_qa_delta(self,db,workspace,session,state):
        if not self.qa_state_delta_v3:return
        base=db.execute('SELECT payload,content_hash FROM public.btl_qa_state_base_v3 WHERE workspace_id=%s AND session_id=%s',(workspace,session)).fetchone()
        require(base is not None,'qaDeltaBase','CORRUPT_RECORD')
        base_record=unpack(*base)
        delta_rows=db.execute('SELECT revision,payload,content_hash FROM public.btl_qa_state_delta_v3 WHERE workspace_id=%s AND session_id=%s ORDER BY revision',(workspace,session)).fetchall()
        deltas=[]
        for n,(rev,payload,sha) in enumerate(delta_rows,1):
            item=unpack(payload,sha);require(rev==n and item['body']['revision']==rev,'qaDeltaRevision','CORRUPT_RECORD');deltas.append(item)
        rebuilt=reconstruct(base_record,deltas)
        require(canonical_bytes(rebuilt)==canonical_bytes(state) and len(deltas)==state['revision'],'qaDeltaState','CORRUPT_RECORD')

    def _read(self,db,workspace,session,*,lock=False):
        row=db.execute('SELECT payload,content_hash,revision,dataset_version,profile_hash FROM btl.tick_sessions WHERE workspace_id=%s AND session_id=%s'+(' FOR UPDATE' if lock else ''),(workspace,session)).fetchone()
        require(row is not None,'session','RESOURCE_UNAVAILABLE')
        stored=read_snapshot(row[0],row[1],order_retention_policy=self.order_retention_policy);s=stored['state']
        require(s['sessionId']==session and (s['revision'],s['datasetVersion'],s['profileHash'])==tuple(row[2:]),'state','CORRUPT_RECORD')
        tip=db.execute('SELECT payload,content_hash FROM btl.tick_checkpoints WHERE workspace_id=%s AND session_id=%s AND revision=%s',(workspace,session,s['revision'])).fetchone()
        require(tip is not None and bytes(tip[0])==bytes(row[0]) and tip[1]==row[1],'immutableTip','CORRUPT_RECORD')
        self._verify_qa_delta(db,workspace,session,s)
        return stored

    def _prior(self,db,workspace,session,command):
        row=db.execute('SELECT command_hash,payload,content_hash FROM btl.tick_commands WHERE workspace_id=%s AND session_id=%s AND command_id=%s',(workspace,session,command['commandId'])).fetchone()
        if row is None:return None
        require(row[0]==content_hash(command),'commandId','REFUSED_IDEMPOTENCY_CONFLICT')
        return checked_result(row[1],row[2],command,order_retention_policy=self.order_retention_policy)

    def _insert(self,db,scope,state,checkpoint):
        workspace,session=scoped(scope,state['sessionId']);require(state['revision']==0,'initialRevision')
        if self.qa_state_delta_v3:
            self._ensure_qa_delta_tables(db);raw_base,sha_base=pack(encode_base(state))
        raw,sha=pack(validate_snapshot(state,checkpoint,order_retention_policy=self.order_retention_policy))
        db.execute('INSERT INTO btl.tick_sessions VALUES (%s,%s,%s,%s,%s,%s,%s)',(workspace,session,state['datasetVersion'],state['profileHash'],0,raw,sha))
        db.execute('INSERT INTO btl.tick_checkpoints VALUES (%s,%s,%s,%s,%s)',(workspace,session,0,raw,sha))
        if self.qa_state_delta_v3:db.execute('INSERT INTO public.btl_qa_state_base_v3 VALUES (%s,%s,0,%s,%s)',(workspace,session,raw_base,sha_base))

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
            live=self._read(db,workspace,session,lock=True);prior=self._prior(db,workspace,session,command)
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
            state_raw,state_hash=pack(validate_snapshot(after,checkpoint,order_retention_policy=self.order_retention_policy))
            delta_raw=delta_hash=None
            if self.qa_state_delta_v3:
                prior_delta=db.execute('SELECT payload,content_hash FROM public.btl_qa_state_delta_v3 WHERE workspace_id=%s AND session_id=%s ORDER BY revision DESC LIMIT 1',(workspace,session)).fetchone()
                base_row=db.execute('SELECT payload,content_hash FROM public.btl_qa_state_base_v3 WHERE workspace_id=%s AND session_id=%s',(workspace,session)).fetchone()
                previous_hash=unpack(*prior_delta)['body']['recordHash'] if prior_delta else unpack(*base_row)['stateHash']
                delta_raw,delta_hash=pack(encode_delta(old,after,previous_hash))
            page=deepcopy(events[:PAGE_EVENTS]);complete=len(page)==len(events)
            result=dict(schemaVersion=1,artifact='BTL-OBSERVED-EXECUTION-RESULT-1',commandId=command['commandId'],commandHash=content_hash(command),state=after,events=page,eventCount=len(events),eventFromSequence=old['nextEventIndex'],eventsComplete=complete,nextEventSequence=None if complete else old['nextEventIndex']+len(page),replay=replay,durable=True,model=after['model'])
            result_raw,result_hash=pack(result)
            checked_result(result_raw,result_hash,command,order_retention_policy=self.order_retention_policy)
            db.execute('INSERT INTO btl.tick_commands VALUES (%s,%s,%s,%s,%s,%s,%s)',(workspace,session,command['commandId'],after['revision'],content_hash(command),result_raw,result_hash))
            for e in events:
                eraw,esha=pack(e);db.execute('INSERT INTO btl.tick_events VALUES (%s,%s,%s,%s,%s,%s,%s)',(workspace,session,command['commandId'],e['eventId'],e['sequence'],eraw,esha))
            db.execute('INSERT INTO btl.tick_checkpoints VALUES (%s,%s,%s,%s,%s)',(workspace,session,after['revision'],state_raw,state_hash))
            db.execute('UPDATE btl.tick_sessions SET revision=%s,payload=%s,content_hash=%s WHERE workspace_id=%s AND session_id=%s',(after['revision'],state_raw,state_hash,workspace,session))
            if self.qa_state_delta_v3:
                db.execute('INSERT INTO public.btl_qa_state_delta_v3 VALUES (%s,%s,%s,%s,%s,%s)',(workspace,session,after['revision'],command['commandId'],delta_raw,delta_hash))
        return deepcopy(result)

    def inspect(self,scope,session_id,after_sequence=0,maximum=64):
        workspace,session=scoped(scope,session_id);revision(after_sequence);require(type(maximum) is int and 1<=maximum<=PAGE_EVENTS,'maximum')
        with connect(self.dsn) as db:
            db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY');stored=self._read(db,workspace,session);state=stored['state']
            require(after_sequence<=state['nextEventIndex'],'eventOffset')
            if after_sequence==0:
                seed=db.execute('SELECT payload,content_hash FROM btl.tick_checkpoints WHERE workspace_id=%s AND session_id=%s AND revision=0',(workspace,session)).fetchone()
                previous=read_snapshot(*seed,order_retention_policy=self.order_retention_policy)['state']['eventHash']
            else:
                prior=db.execute('SELECT payload,content_hash FROM btl.tick_events WHERE workspace_id=%s AND session_id=%s AND sequence=%s',(workspace,session,after_sequence-1)).fetchone();require(prior is not None,'event','CORRUPT_RECORD');previous=unpack(*prior)['eventId']
            rows=db.execute('SELECT payload,content_hash FROM btl.tick_events WHERE workspace_id=%s AND session_id=%s AND sequence>=%s AND sequence<%s ORDER BY sequence LIMIT %s',(workspace,session,after_sequence,state['nextEventIndex'],maximum)).fetchall();events=[unpack(*r) for r in rows]
            end,head=check_events(events,state,after_sequence,previous);require(len(events)==min(maximum,state['nextEventIndex']-after_sequence),'eventCount','CORRUPT_RECORD')
            if end==state['nextEventIndex']:require(head==state['eventHash'],'eventHead','CORRUPT_RECORD')
            return dict(state=state,events=events,nextEventSequence=None if end==state['nextEventIndex'] else end)
