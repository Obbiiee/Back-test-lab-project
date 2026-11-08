"""Separate observed-family transactional boundary on existing opaque tick tables.

No migration or old-family dispatch changes. Market work happens outside row
locks; only validated proposals after CAS become published SIMULATED_FILLs.
"""
from copy import deepcopy
from collections import OrderedDict
from fractions import Fraction
import os
from threading import RLock
from uuid import uuid4

from contracts.canonical import canonical_bytes,content_hash
from contracts.primitives import require,revision
from ticks.contracts import keys
from infrastructure.database import connect
from .postgres import pack,unpack,scoped
from .observed_profile import ENGINE_VERSION,MODEL
from .observed_kernel import (command_wire,validate_state,validate_snapshot,order_limits,MAX_EVENTS,
    STATE_QA_ARCHIVE_V1,STATE_PRODUCT_ARCHIVE_V1,STATE_INTEGRATION_PRODUCT_ARCHIVE_V1,
    PRODUCT_ORDER_RETENTION_V1)
from .engine import crossing,protective
from .observed_finance import exit_amount
from .observed_profile import ObservedExecutionProfile
from .contracts import open_payload,policy_from_wire
from .observed_state_delta_v3 import (encode_base,encode_delta,encode_delta_v4,encode_compact_base,
    encode_compact_delta,reconstruct_complete,COMPACT_DELTA,COMPACT_PROGRESS_DELTA)
from .observed_replay_progress import CONTROLLER as PROGRESS_CONTROLLER, load_progress, match_progress_receipt, replace_progress
from .observed_order_archive_v1 import (ARTIFACT as QA_ORDER_ARCHIVE_ARTIFACT,
    PRODUCT_ARTIFACT as PRODUCT_ORDER_ARCHIVE_ARTIFACT, advance as archive_advance,
    summary as archive_summary, verify_complete as verify_archive_complete,
    verify_record as verify_archive_record)
from .observed_order_archive_product_v1 import (advance as integration_archive_advance,
    summary as integration_product_archive_summary,
    verify_complete as verify_integration_archive_complete,
    verify_record as verify_integration_archive_record)
from .contracts import text

PAGE_EVENTS=64
EVENT_FIELDS='schemaVersion artifact engineVersion model sessionId datasetId datasetVersion profileHash methodHash sequence previousHash kind classification orderId detail eventId'
CLASSIFICATIONS={**{k:'SIMULATED_FILL' for k in ('ENTRY_FILL','EXIT_FILL')},**{k:'UNRESOLVED' for k in ('UNRESOLVED','UNUSABLE_OBSERVATION','EXPIRED_NO_QUOTE')},**{k:'ACCEPTED_COMMAND' for k in ('ORDER_ACCEPTED','ORDER_CANCELLED','EXIT_REQUESTED','SESSION_ENDED')},**{k:'OBSERVED_FEED_EVENT' for k in ('REPLAY_ADVANCED','CHRONOLOGY_LIMITATION','DATA_GAP_LIMITATION','STALE_QUOTE')}}
QA3_CHECKPOINT='BTL-OBSERVED-EXECUTION-CHECKPOINT-3'
QA3_CHECKPOINT_BASE='BTL-OBSERVED-EXECUTION-CHECKPOINT-BASE-3'
QA3_CHECKPOINT_DELTA='BTL-OBSERVED-EXECUTION-CHECKPOINT-DELTA-3'
QA3_RESULT='BTL-OBSERVED-EXECUTION-RESULT-3'
COMPACT_CHECKPOINT='BTL-OBSERVED-EXECUTION-CHECKPOINT-COMPACT-1'
COMPACT_CHECKPOINT_BASE='BTL-OBSERVED-EXECUTION-CHECKPOINT-BASE-COMPACT-1'
COMPACT_CHECKPOINT_DELTA='BTL-OBSERVED-EXECUTION-CHECKPOINT-DELTA-COMPACT-1'
COMPACT_RESULT='BTL-OBSERVED-EXECUTION-RESULT-COMPACT-1'
COMPACT_RECOVERY='BTL-OBSERVED-EXECUTION-CHECKPOINT-RECOVERY-COMPACT-1'
COMPACT_RECOVERY_INTERVAL=64
PROGRESS_FORMAT='compact-progress-v1'
PROGRESS_POINTER='BTL-OBSERVED-EXECUTION-CHECKPOINT-POINTER-PROGRESS-1'
PROGRESS_BASE='BTL-OBSERVED-EXECUTION-CHECKPOINT-BASE-PROGRESS-1'
PROGRESS_DELTA='BTL-OBSERVED-EXECUTION-CHECKPOINT-DELTA-PROGRESS-1'


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


def checked_result_value(result,command,*,order_retention_policy=None):
    """Validate the complete in-memory receipt without serializing it again.

    QA-v3 persists a compact receipt bound to the full state hash and delta
    chain. Serializing a second copy of the cumulative state just to validate
    the pre-compaction receipt needlessly doubles canonical node usage and can
    hit the bounded serializer budget on long Sessions. Legacy receipts still
    use ``checked_result`` below and retain their exact bytes and hashes.
    """
    keys(result,'schemaVersion artifact commandId commandHash state events eventCount eventFromSequence eventsComplete nextEventSequence replay durable model')
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


def checked_result(raw,sha,command,*,order_retention_policy=None):
    result=unpack(raw,sha)
    return checked_result_value(result,command,order_retention_policy=order_retention_policy)


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


def compact_receipt_v1(result,state_hash,chain_hash):
    return dict(schemaVersion=1,formatVersion=1,artifact=COMPACT_RESULT,commandId=result['commandId'],commandHash=result['commandHash'],
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


def expand_compact_receipt_v1(record,command,state,chain_hash,*,order_retention_policy=None):
    keys(record,'schemaVersion formatVersion artifact commandId commandHash stateRevision stateHash chainHash events eventCount eventFromSequence eventsComplete nextEventSequence replay durable model')
    require(record['schemaVersion']==1 and record['formatVersion']==1 and record['artifact']==COMPACT_RESULT and record['durable'] is True,
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
    def __init__(self,dsn,*,order_retention_policy=None,qa_state_delta_v3=False,qa_order_archive_v1=False,
                 product_order_archive_v1=False,
                 terminal_order_archive_v1=False,
                 state_storage_format='snapshot-v1'):
        order_limits(order_retention_policy)
        require(type(qa_state_delta_v3) is bool,'qaStateDeltaV3')
        require(state_storage_format in ('snapshot-v1','compact-v1',PROGRESS_FORMAT),'stateStorageFormat','REFUSED_STATE_VERSION')
        require(not (qa_state_delta_v3 and state_storage_format!='snapshot-v1'),
                'stateStorageFormat','REFUSED_STATE_VERSION')
        require(type(qa_order_archive_v1) is bool and (not qa_order_archive_v1 or qa_state_delta_v3),
                'qaOrderArchive','REFUSED_POLICY')
        require(type(product_order_archive_v1) is bool and type(terminal_order_archive_v1) is bool and
                sum((qa_order_archive_v1,product_order_archive_v1,terminal_order_archive_v1))<=1,
                'productOrderArchive','REFUSED_POLICY')
        if product_order_archive_v1 or terminal_order_archive_v1:
            from .observed_kernel import PRODUCT_ORDER_RETENTION_V1
            require(order_retention_policy==PRODUCT_ORDER_RETENTION_V1,'productOrderArchive','REFUSED_POLICY')
            require(state_storage_format in ('compact-v1',PROGRESS_FORMAT),
                    'productOrderArchive','REFUSED_STATE_VERSION')
        require(not qa_order_archive_v1 or os.environ.get('BTL_ENABLE_QA_ORDER_ARCHIVE_V1')=='1',
                'qaOrderArchive','REFUSED_POLICY')
        self.dsn=dsn;self.order_retention_policy=deepcopy(order_retention_policy);self.qa_state_delta_v3=qa_state_delta_v3
        self.state_storage_format=state_storage_format
        self.qa_order_archive_v1=qa_order_archive_v1
        self.product_order_archive_v1=product_order_archive_v1
        self.terminal_order_archive_v1=terminal_order_archive_v1
        self._qa_state_cache=OrderedDict();self._qa_state_cache_lock=RLock();self._qa_state_cache_max=4
        self._qa_state_cache_stats=dict(hits=0,misses=0,fullReconstructions=0,evictions=0)

    @property
    def qa_state_cache_stats(self):
        with self._qa_state_cache_lock:
            return dict(self._qa_state_cache_stats,entries=len(self._qa_state_cache),
                        maxEntries=self._qa_state_cache_max)

    def _qa_state_cache_read(self,workspace,session,wire):
        key=(workspace,session)
        with self._qa_state_cache_lock:
            entry=self._qa_state_cache.get(key)
            if entry is None:
                self._qa_state_cache_stats['misses']+=1
                return None
            if (entry['revision'],entry['stateHash'],entry['chainHash']) != (
                    wire['revision'],wire['stateHash'],wire['chainHash']):
                del self._qa_state_cache[key]
                self._qa_state_cache_stats['misses']+=1
                return None
            self._qa_state_cache.move_to_end(key)
            self._qa_state_cache_stats['hits']+=1
            return deepcopy(entry['state'])

    def _qa_state_cache_write(self,workspace,session,state,chain_hash):
        if not (self.qa_state_delta_v3 or self.state_storage_format=='compact-v1'):return
        key=(workspace,session);state_hash=content_hash(state)
        with self._qa_state_cache_lock:
            self._qa_state_cache[key]=dict(revision=state['revision'],stateHash=state_hash,
                                           chainHash=chain_hash,state=deepcopy(state))
            self._qa_state_cache.move_to_end(key)
            while len(self._qa_state_cache)>self._qa_state_cache_max:
                self._qa_state_cache.popitem(last=False)
                self._qa_state_cache_stats['evictions']+=1

    def _has_qa_base(self,db,workspace,session):
        if not self.qa_state_delta_v3:return False
        if db.execute("SELECT to_regclass('public.btl_qa_state_base_v3')").fetchone()[0] is None:return False
        return db.execute('SELECT 1 FROM public.btl_qa_state_base_v3 WHERE workspace_id=%s AND session_id=%s',(workspace,session)).fetchone() is not None

    def _archive_table(self,state):
        artifact=state.get('artifact')
        if artifact==STATE_QA_ARCHIVE_V1:
            require(self.qa_order_archive_v1,'qaOrderArchive','REFUSED_QA_SESSION_VERSION')
            return 'public.btl_qa_terminal_order_archive_v1'
        if artifact==STATE_PRODUCT_ARCHIVE_V1:
            require(self.product_order_archive_v1 or self.terminal_order_archive_v1,
                    'productOrderArchive','REFUSED_SESSION_VERSION')
            return 'btl.tick_terminal_order_archive_v1'
        if artifact==STATE_INTEGRATION_PRODUCT_ARCHIVE_V1:
            # Either Product runtime enables the Product family. The persisted
            # artifact still selects its immutable table and codec above.
            require(self.product_order_archive_v1 or self.terminal_order_archive_v1,
                    'productOrderArchive','REFUSED_SESSION_VERSION')
            return 'btl.tick_terminal_orders'
        require(False,'orderArchive','REFUSED_SESSION_VERSION')

    @staticmethod
    def _is_archive_state(state):
        return state.get('artifact') in (STATE_QA_ARCHIVE_V1,STATE_PRODUCT_ARCHIVE_V1,STATE_INTEGRATION_PRODUCT_ARCHIVE_V1)

    @staticmethod
    def _verify_archive_record(state,record,*,expected_sequence=None,previous_hash=None):
        verifier=(verify_integration_archive_record if state['artifact']==STATE_INTEGRATION_PRODUCT_ARCHIVE_V1
                  else verify_archive_record)
        return verifier(record,expected_sequence=expected_sequence,previous_hash=previous_hash)

    @staticmethod
    def _verify_archive_complete(state,rows):
        verifier=(verify_integration_archive_complete if state['artifact']==STATE_INTEGRATION_PRODUCT_ARCHIVE_V1
                  else verify_archive_complete)
        return verifier(rows,state['orderArchive'])

    @staticmethod
    def _archive_genesis(state):
        if state['artifact']==STATE_INTEGRATION_PRODUCT_ARCHIVE_V1:
            return integration_product_archive_summary()['headHash']
        artifact=(PRODUCT_ORDER_ARCHIVE_ARTIFACT if state['artifact']==STATE_PRODUCT_ARCHIVE_V1
                  else QA_ORDER_ARCHIVE_ARTIFACT)
        return archive_summary(artifact=artifact)['headHash']

    def _ensure_order_archive_schema(self,db,state):
        table=self._archive_table(state)
        if state['artifact']==STATE_PRODUCT_ARCHIVE_V1:
            require(db.execute("SELECT to_regclass('btl.tick_terminal_order_archive_v1')").fetchone()[0] is not None,
                    'productOrderArchive','SCHEMA_NOT_READY')
            return
        if state['artifact']==STATE_INTEGRATION_PRODUCT_ARCHIVE_V1:
            require(db.execute("SELECT to_regclass('btl.tick_terminal_orders')").fetchone()[0] is not None,
                    'productOrderArchive','SCHEMA_NOT_READY')
            return
        db.execute('''CREATE TABLE IF NOT EXISTS public.btl_qa_terminal_order_archive_v1 (
            workspace_id text NOT NULL, session_id text NOT NULL, sequence bigint NOT NULL,
            order_id text NOT NULL, finalized_revision bigint NOT NULL, record_hash text NOT NULL,
            payload bytea NOT NULL, content_hash text NOT NULL,
            PRIMARY KEY(workspace_id,session_id,sequence),
            UNIQUE(workspace_id,session_id,order_id),
            FOREIGN KEY(workspace_id,session_id) REFERENCES btl.tick_sessions(workspace_id,session_id),
            CHECK(sequence >= 0), CHECK(finalized_revision > 0),
            CHECK(record_hash ~ '^[0-9a-f]{64}$'), CHECK(content_hash ~ '^[0-9a-f]{64}$'),
            CHECK(octet_length(payload) <= 1048576))''')
        db.execute('''CREATE OR REPLACE FUNCTION public.btl_qa_terminal_archive_immutable_v1()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'QA_TERMINAL_ORDER_ARCHIVE_IMMUTABLE'; RETURN OLD; END $$''')
        db.execute('''DROP TRIGGER IF EXISTS btl_qa_terminal_archive_immutable_v1
            ON public.btl_qa_terminal_order_archive_v1''')
        db.execute('''CREATE TRIGGER btl_qa_terminal_archive_immutable_v1
            BEFORE UPDATE OR DELETE ON public.btl_qa_terminal_order_archive_v1
            FOR EACH ROW EXECUTE FUNCTION public.btl_qa_terminal_archive_immutable_v1()''')
        db.execute('''DROP TRIGGER IF EXISTS btl_qa_terminal_archive_no_truncate_v1
            ON public.btl_qa_terminal_order_archive_v1''')
        db.execute('''CREATE TRIGGER btl_qa_terminal_archive_no_truncate_v1
            BEFORE TRUNCATE ON public.btl_qa_terminal_order_archive_v1
            FOR EACH STATEMENT EXECUTE FUNCTION public.btl_qa_terminal_archive_immutable_v1()''')

    def _archive_rows(self,db,workspace,session,state):
        table=self._archive_table(state)
        cursor=db.execute('SELECT sequence,order_id,finalized_revision,record_hash,payload,content_hash '
            f'FROM {table} WHERE workspace_id=%s AND session_id=%s ORDER BY sequence',(workspace,session))
        for sequence,order_id,finalized_revision,record_hash,raw,sha in cursor:
            row=unpack(raw,sha)
            require(row['sequence']==sequence and row['orderId']==order_id and
                    row['finalizedRevision']==finalized_revision and row['sessionId']==session
                    and row['recordHash']==record_hash,
                    'archiveRowBinding','CORRUPT_RECORD')
            yield row

    def _verify_order_archive(self,db,workspace,session,state,*,full):
        table=self._archive_table(state)
        summary=state['orderArchive']
        if full:
            verified=self._verify_archive_complete(state,self._archive_rows(db,workspace,session,state))
            require(verified['count']==summary['count'],'archiveCount','CORRUPT_RECORD')
            self._verify_event_order_projection(db,workspace,session,state)
        else:
            tip=db.execute(f'SELECT sequence,record_hash FROM {table} WHERE workspace_id=%s AND session_id=%s ORDER BY sequence DESC LIMIT 1',
                (workspace,session)).fetchone()
            maximum,head=(tip if tip else (None,None))
            require(maximum==(summary['count']-1 if summary['count'] else None)
                    and (head if summary['count'] else self._archive_genesis(state))==summary['headHash'],
                    'archiveTip','CORRUPT_RECORD')

    def archive_order(self,scope,session_id,order_id):
        workspace,session=scoped(scope,session_id)
        with connect(self.dsn) as db:
            db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            stored=self._read(db,workspace,session);state=stored['state'];table=self._archive_table(state)
            row=db.execute(f'SELECT record_hash,payload,content_hash FROM {table} '
                'WHERE workspace_id=%s AND session_id=%s AND order_id=%s',(workspace,session,order_id)).fetchone()
            if row is None:return None
            record=unpack(row[1],row[2]);self._verify_archive_record(state,record)
            require(record['recordHash']==row[0] and record['orderId']==order_id,'archiveLookup','CORRUPT_RECORD')
            return deepcopy(record['order'])

    def archive_order_exists(self,scope,session_id,order_id):
        return self.archive_order(scope,session_id,order_id) is not None

    def order_history(self,scope,session_id,offset=0,maximum=64):
        require(type(offset) is int and offset>=0 and type(maximum) is int and 1<=maximum<=256,'pagination')
        workspace,session=scoped(scope,session_id)
        with connect(self.dsn) as db:
            db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            stored=self._read(db,workspace,session);state=stored['state']
            table=self._archive_table(state)
            self._verify_archive_complete(state,self._archive_rows(db,workspace,session,state))
            prior=db.execute(f'SELECT record_hash FROM {table} '
                'WHERE workspace_id=%s AND session_id=%s AND sequence=%s',(workspace,session,offset-1)).fetchone() if offset else None
            expected_previous=prior[0] if prior else self._archive_genesis(state)
            rows=db.execute(f'SELECT sequence,record_hash,payload,content_hash FROM {table} '
                'WHERE workspace_id=%s AND session_id=%s ORDER BY sequence OFFSET %s LIMIT %s',
                (workspace,session,offset,maximum+1)).fetchall()
            values=[]
            for sequence,record_hash,raw,sha in rows:
                record=unpack(raw,sha);self._verify_archive_record(state,record,expected_sequence=sequence,previous_hash=expected_previous)
                require(record['recordHash']==record_hash,'archiveLookup','CORRUPT_RECORD')
                expected_previous=record_hash;values.append(record)
            return dict(records=[dict(orderId=r['orderId'],order=deepcopy(r['order']),
                sequence=r['sequence'],finalizedRevision=r['finalizedRevision'],recordHash=r['recordHash'])
                for r in values[:maximum]],nextOffset=offset+maximum if len(values)>maximum else None,
                total=state['orderArchive']['count'])

    def order_history_page(self,scope,session_id,*,after_sequence=None,revision_pin=None,maximum=64):
        """Read a revision-pinned archive page with an indexed sequence cursor."""
        require(after_sequence is None or (type(after_sequence) is int and after_sequence>=-1),
                'cursor','INVALID_CURSOR')
        require(revision_pin is None or (type(revision_pin) is int and revision_pin>=0),
                'cursor','INVALID_CURSOR')
        require(type(maximum) is int and 1<=maximum<=256,'maximum','INVALID_INPUT')
        workspace,session=scoped(scope,session_id)
        with connect(self.dsn) as db:
            db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            state=self._read(db,workspace,session)['state'];table=self._archive_table(state)
            require(revision_pin is None or revision_pin==state['revision'],'cursor','STALE_REVISION')
            self._verify_order_archive(db,workspace,session,state,full=False)
            count=state['orderArchive']['count']
            start=-1 if after_sequence is None else after_sequence
            require(start<count,'cursor','INVALID_CURSOR')
            artifact=(PRODUCT_ORDER_ARCHIVE_ARTIFACT if state['artifact']==STATE_PRODUCT_ARCHIVE_V1
                      else QA_ORDER_ARCHIVE_ARTIFACT)
            if start<0:
                previous_hash=self._archive_genesis(state)
            else:
                prior=db.execute(f'SELECT sequence,order_id,finalized_revision,record_hash,payload,content_hash '
                    f'FROM {table} WHERE workspace_id=%s AND session_id=%s AND sequence=%s',
                    (workspace,session,start)).fetchone()
                require(prior is not None,'cursor','INVALID_CURSOR')
                prior_record=unpack(prior[4],prior[5])
                self._verify_archive_record(state,prior_record,expected_sequence=start)
                require(prior_record['sessionId']==session and prior_record['orderId']==prior[1]
                        and prior_record['finalizedRevision']==prior[2]
                        and prior_record['recordHash']==prior[3],
                        'archiveRowBinding','CORRUPT_RECORD')
                previous_hash=prior[3]
            rows=db.execute(f'SELECT sequence,record_hash,payload,content_hash FROM {table} '
                'WHERE workspace_id=%s AND session_id=%s AND sequence>%s ORDER BY sequence LIMIT %s',
                (workspace,session,start,maximum+1)).fetchall()
            records=[];expected=start+1
            for sequence,record_hash,raw,sha in rows:
                record=unpack(raw,sha)
                self._verify_archive_record(state,record,expected_sequence=expected,previous_hash=previous_hash)
                require(record['sessionId']==session and record['recordHash']==record_hash,
                        'archiveLookup','CORRUPT_RECORD')
                records.append(dict(orderId=record['orderId'],order=deepcopy(record['order']),
                    sequence=sequence,finalizedRevision=record['finalizedRevision'],recordHash=record_hash))
                expected+=1;previous_hash=record_hash
            page=records[:maximum];more=len(records)>maximum
            next_cursor=(dict(revision=state['revision'],afterSequence=page[-1]['sequence'])
                         if more and page else None)
            return dict(artifact='BTL-ORDER-HISTORY-PAGE-1',sessionId=session,revision=state['revision'],
                total=count,records=page,nextCursor=next_cursor,complete=next_cursor is None)

    def _verify_event_order_projection(self,db,workspace,session,state):
        """Independent streaming event fold against active state and archive."""
        table=self._archive_table(state)
        base,_=self._qa_reconstruct(db,workspace,session,upto_revision=0)
        previous=base['eventHash'];start=0;active={};seen_order_ids=set();archived_count=0
        profile=ObservedExecutionProfile.from_wire(state['profile']);event_gross=Fraction(0)
        event_balance=Fraction(state['initialBalance']);financial_seen=False

        def archive_terminal(oid,order,command_revision):
            nonlocal archived_count
            row=db.execute(f'SELECT sequence,finalized_revision,record_hash,payload,content_hash '
                f'FROM {table} WHERE workspace_id=%s AND session_id=%s AND order_id=%s',
                (workspace,session,oid)).fetchone()
            require(row is not None,'archiveMissing','CORRUPT_RECORD')
            sequence,finalized_revision,record_hash,raw,sha=row;record=unpack(raw,sha)
            self._verify_archive_record(state,record,expected_sequence=sequence)
            require(record['recordHash']==record_hash and record['orderId']==oid and record['order']==order
                    and record['finalizedRevision']==finalized_revision==command_revision,
                    'archiveEventParity','CORRUPT_RECORD')
            archived_count+=1

        while start<state['nextEventIndex']:
            rows=db.execute('SELECT e.command_id,e.payload,e.content_hash,c.revision FROM btl.tick_events e '
                'JOIN btl.tick_commands c USING(workspace_id,session_id,command_id) '
                'WHERE e.workspace_id=%s AND e.session_id=%s AND e.sequence>=%s '
                'AND e.sequence<%s ORDER BY e.sequence LIMIT 256',
                (workspace,session,start,state['nextEventIndex'])).fetchall()
            require(len(rows)==min(256,state['nextEventIndex']-start),'eventCount','CORRUPT_RECORD')
            events=[unpack(row[1],row[2]) for row in rows]
            start,previous=check_events(events,state,start,previous)
            for (command_id,_,_,command_revision),event in zip(rows,events):
                kind=event['kind'];oid=event['orderId'];detail=event['detail']
                if kind=='ORDER_ACCEPTED':
                    require(oid not in seen_order_ids,'eventOrderDuplicate','CORRUPT_RECORD')
                    seen_order_ids.add(oid)
                    plan=deepcopy(detail['plan'])
                    require(open_payload(plan,state['profile'],policy_from_wire(state['policy']),detail['riskBalance'])==plan,
                            'eventOrderPlan','CORRUPT_RECORD')
                    active[oid]=dict(plan,status='PENDING',availableNs=detail['availableNs'],remaining=plan['quantity'],
                        entryPrice=None,entryFillRef=None,entryCost='0',exitRequest=None,grossPosted='0',
                        riskBalance=detail['riskBalance'],riskBasisHash=detail['riskBasisHash'])
                elif kind in ('ENTRY_FILL','EXIT_FILL','ORDER_CANCELLED','EXPIRED_NO_QUOTE','EXIT_REQUESTED'):
                    require(oid in active,'eventOrderMissing','CORRUPT_RECORD');order=active[oid]
                    if kind=='ENTRY_FILL':
                        require(order['status']=='PENDING','eventEntryState','CORRUPT_RECORD')
                        evidence=detail['evidence'];quote=dict(bid=evidence['bid'],ask=evidence['ask'])
                        expected=quote['ask'] if order['side']=='LONG' else quote['bid']
                        require(int(evidence['timeNs'])>=int(order['availableNs']) and crossing(order,quote)
                                and detail['price']==expected and detail['quantity']==order['quantity']
                                and detail['commission']=='0' and detail['balanceDelta']=='0',
                                'eventEntryFill','CORRUPT_RECORD')
                        order.update(status='ACTIVE',entryPrice=detail['price'],entryFillRef=event['eventId'])
                        financial_seen=True
                    elif kind=='EXIT_FILL':
                        evidence=detail['evidence'];quote=dict(bid=evidence['bid'],ask=evidence['ask'])
                        expected=quote['bid'] if order['side']=='LONG' else quote['ask']
                        require(order['status']=='ACTIVE' and int(evidence['timeNs'])>=int(order['availableNs'])
                                and detail['price']==expected and detail['commission']=='0',
                                'eventExitFill','CORRUPT_RECORD')
                        reason=protective(order,quote)
                        if reason is None and order['exitRequest'] is not None and \
                                int(evidence['timeNs'])>=int(order['exitRequest']['availableNs']):reason='MANUAL'
                        require(detail['reason']==reason,'eventExitReason','CORRUPT_RECORD')
                        size=detail['quantity'] if reason=='MANUAL' else order['remaining']
                        require(detail['quantity']==size,'eventExitQuantity','CORRUPT_RECORD')
                        prior_remaining=Fraction(order['remaining'])
                        amount=exit_amount(profile,side=order['side'],entry_price=order['entryPrice'],
                            exit_price=detail['price'],lots=size)
                        require(amount['grossExact']==detail['grossExact'] and amount['grossPosted']==detail['grossPosted']
                                and detail['balanceDelta']==detail['grossPosted'],
                                'eventExitCash','CORRUPT_RECORD')
                        posted=Fraction(order['grossPosted'])+Fraction(detail['grossPosted'])
                        order.update(status='CLOSED' if detail['remaining']=='0' else 'ACTIVE',
                            remaining=detail['remaining'],exitRequest=None,grossPosted=text(posted))
                        require(prior_remaining-Fraction(size)==Fraction(detail['remaining']) and
                                (order['status']=='CLOSED') is (Fraction(detail['remaining'])==0),
                                'eventExitState','CORRUPT_RECORD')
                        event_gross+=Fraction(detail['grossPosted']);event_balance+=Fraction(detail['balanceDelta'])
                        financial_seen=True
                    elif kind=='ORDER_CANCELLED':
                        require(order['status']=='PENDING','eventCancelState','CORRUPT_RECORD');order['status']='CANCELLED'
                    elif kind=='EXPIRED_NO_QUOTE':
                        require(order['status']=='PENDING','eventExpireState','CORRUPT_RECORD');order['status']='EXPIRED'
                    elif kind=='EXIT_REQUESTED':
                        require(order['status']=='ACTIVE' and order['exitRequest'] is None and
                                0<Fraction(detail['quantity'])<=Fraction(order['remaining']) and
                                int(order['availableNs'])<=int(detail['availableNs']),
                                'eventExitRequest','CORRUPT_RECORD')
                        order['exitRequest']=dict(quantity=detail['quantity'],availableNs=detail['availableNs'])
                    if order['status'] in ('CLOSED','CANCELLED','EXPIRED'):
                        archive_terminal(oid,order,command_revision);del active[oid]
                elif kind=='UNRESOLVED':
                    for affected in detail['affectedOrderIds']:
                        require(affected in active,'eventUnresolvedOrder','CORRUPT_RECORD')
                        active[affected].update(status='UNRESOLVED',exitRequest=None)
                        archive_terminal(affected,active[affected],command_revision);del active[affected]
            require(start<=state['nextEventIndex'],'eventOffset','CORRUPT_RECORD')
        require(previous==state['eventHash'],'eventHead','CORRUPT_RECORD')
        require(active==state['orders'],'activeEventParity','CORRUPT_RECORD')
        require(archived_count==state['orderArchive']['count'],'archiveEventSet','CORRUPT_RECORD')
        require(event_gross==Fraction(state['realizedGross']) and event_balance==Fraction(state['balance'])
                and state['financial'] is financial_seen,'eventFinancialParity','CORRUPT_RECORD')

    def _progress_checkpoint(self, db, workspace, session, revision_number):
        row = db.execute('SELECT payload,content_hash FROM btl.tick_checkpoints '
                         'WHERE workspace_id=%s AND session_id=%s AND revision=%s',
                         (workspace, session, revision_number)).fetchone()
        require(row is not None, 'progressCheckpoint', 'CORRUPT_RECORD')
        checkpoint = unpack(*row)
        require(checkpoint.get('artifact') in (PROGRESS_BASE, PROGRESS_DELTA) and
                checkpoint.get('revision') == revision_number, 'progressCheckpoint', 'CORRUPT_RECORD')
        return checkpoint, row[1]

    def _progress_reconstruct(self, db, workspace, session, tip):
        base_revision = tip['recoveryRevision']
        base, _ = self._progress_checkpoint(db, workspace, session, base_revision)
        ordinal = tip['ordinal']
        base_ordinal = base['ordinal']
        require(base['recoveryRevision'] == base_revision and
                base_ordinal % COMPACT_RECOVERY_INTERVAL == 0 and
                0 <= ordinal - base_ordinal < COMPACT_RECOVERY_INTERVAL,
                'progressRecovery', 'CORRUPT_RECORD')
        require(base['stateHash'] == content_hash(base['state']) and
                base['state']['revision'] == base_revision, 'progressRecovery', 'CORRUPT_RECORD')
        validate_snapshot(base['state'], base['controller'], order_retention_policy=self.order_retention_policy)
        if base_revision == 0:
            require(base['artifact'] == PROGRESS_BASE and base['chainHash'] == base['stateHash'],
                    'progressRecovery', 'CORRUPT_RECORD')
        else:
            prior, _ = self._progress_checkpoint(db, workspace, session, base['previousRevision'])
            delta = base['delta']
            core = delta['body']
            artifact = delta['artifact']
            require(artifact in (COMPACT_DELTA, COMPACT_PROGRESS_DELTA) and
                    prior['ordinal'] + 1 == base_ordinal and core['revision'] == base_revision and
                    core['previousHash'] == prior['chainHash'] and core['stateHash'] == base['stateHash'] and
                    core['recordHash'] == base['chainHash'] ==
                    content_hash(dict(schemaVersion=1, artifact=artifact+'-RECORD',
                                      body={key:value for key,value in core.items() if key!='recordHash'})),
                    'progressRecovery', 'CORRUPT_RECORD')

        last = base

        def deltas():
            nonlocal last
            rows = db.execute('SELECT revision,payload,content_hash FROM btl.tick_checkpoints '
                              'WHERE workspace_id=%s AND session_id=%s AND revision>%s AND revision<=%s '
                              'ORDER BY revision LIMIT %s',
                              (workspace, session, base_revision, tip['revision'], COMPACT_RECOVERY_INTERVAL)).fetchall()
            for stored_revision, payload, sha in rows:
                item = unpack(payload, sha)
                delta = item['delta']
                core = delta['body']
                require(item['artifact'] == PROGRESS_DELTA and item['ordinal'] == last['ordinal']+1 and
                        item['recoveryRevision'] == base_revision and item['previousRevision'] == last['revision'] and
                        item['revision'] == stored_revision == core['revision'] and
                        item['stateHash'] == core['stateHash'] and item['chainHash'] == core['recordHash'],
                        'progressDelta', 'CORRUPT_RECORD')
                last = item
                yield delta

        restored = reconstruct_complete(encode_compact_base(base['state']), deltas(), tip['revision'],
                                        base_chain_hash=base['chainHash'], allow_progress=True)
        require(last == tip and content_hash(restored) == tip['stateHash'], 'progressTip', 'CORRUPT_RECORD')
        validate_snapshot(restored, tip['controller'], order_retention_policy=self.order_retention_policy)
        return restored, tip['chainHash']

    def _qa_reconstruct(self,db,workspace,session,*,upto_revision=None,require_tip=False):
        with self._qa_state_cache_lock:self._qa_state_cache_stats['fullReconstructions']+=1
        base_row=db.execute('SELECT payload,content_hash FROM btl.tick_checkpoints WHERE workspace_id=%s AND session_id=%s AND revision=0',(workspace,session)).fetchone()
        require(base_row is not None,'qaDeltaBase','CORRUPT_RECORD')
        base_record=unpack(*base_row)
        if base_record.get('artifact') == PROGRESS_BASE:
            require(upto_revision is not None, 'progressRevision', 'CORRUPT_RECORD')
            tip, _ = self._progress_checkpoint(db, workspace, session, upto_revision)
            return self._progress_reconstruct(db, workspace, session, tip)
        if base_record.get('artifact') in (QA3_CHECKPOINT_BASE,COMPACT_CHECKPOINT_BASE):
            compact_v1=base_record.get('artifact')==COMPACT_CHECKPOINT_BASE
            expected_base_format=1 if compact_v1 else 3
            keys(base_record,'schemaVersion formatVersion artifact revision state stateHash chainHash controller')
            require(base_record['schemaVersion']==1 and base_record['formatVersion']==expected_base_format and base_record['revision']==0
                    and base_record['stateHash']==content_hash(base_record['state'])==base_record['chainHash'],
                    'qaDeltaBase','CORRUPT_RECORD')
            require(upto_revision is None or (type(upto_revision) is int and upto_revision>=0),
                    'qaDeltaRevision','CORRUPT_RECORD')
            target_revision=(db.execute('SELECT max(revision) FROM btl.tick_checkpoints WHERE workspace_id=%s AND session_id=%s',
                                        (workspace,session)).fetchone()[0] if upto_revision is None else upto_revision)
            require(type(target_revision) is int and target_revision>=0,'qaDeltaRevision','CORRUPT_RECORD')
            start_revision=0
            recovery_chain=None
            if compact_v1 and target_revision>=COMPACT_RECOVERY_INTERVAL:
                candidate_revision=target_revision-target_revision%COMPACT_RECOVERY_INTERVAL
                row=db.execute('SELECT payload,content_hash FROM btl.tick_checkpoints '
                               'WHERE workspace_id=%s AND session_id=%s AND revision=%s',
                               (workspace,session,candidate_revision)).fetchone()
                require(row is not None,'compactRecovery','CORRUPT_RECORD')
                candidate=unpack(*row)
                if candidate.get('artifact')==COMPACT_RECOVERY:
                    keys(candidate,'schemaVersion formatVersion artifact revision stateHash chainHash previousHash delta controller state')
                    delta=candidate['delta']
                    keys(delta,'schemaVersion formatVersion artifact body')
                    body=delta['body']
                    chain=content_hash(dict(schemaVersion=1,artifact=COMPACT_DELTA+'-RECORD',
                                            body={k:v for k,v in body.items() if k!='recordHash'}))
                    require(candidate['schemaVersion']==candidate['formatVersion']==delta['schemaVersion']==delta['formatVersion']==1 and
                            delta['artifact']==body.get('artifact')==COMPACT_DELTA and body.get('schemaVersion')==1 and
                            candidate['revision']==candidate_revision==body.get('revision')==candidate['state'].get('revision') and
                            candidate['previousHash']==body.get('previousHash') and
                            candidate['stateHash']==body.get('stateHash')==content_hash(candidate['state']) and
                            candidate['chainHash']==body.get('recordHash')==chain,
                            'compactRecovery','CORRUPT_RECORD')
                    predecessor=db.execute('SELECT payload,content_hash FROM btl.tick_checkpoints '
                                           'WHERE workspace_id=%s AND session_id=%s AND revision=%s',
                                           (workspace,session,candidate_revision-1)).fetchone()
                    require(predecessor is not None,'compactRecovery','CORRUPT_RECORD')
                    prior=unpack(*predecessor)
                    require(prior.get('artifact')==COMPACT_CHECKPOINT_DELTA and
                            prior.get('revision')==candidate_revision-1 and
                            prior.get('chainHash')==candidate['previousHash'],
                            'compactRecovery','CORRUPT_RECORD')
                    validate_snapshot(candidate['state'],candidate['controller'],order_retention_policy=self.order_retention_policy)
                    base_record=encode_compact_base(candidate['state'])
                    base_record['controller']=candidate['controller']
                    start_revision=candidate_revision
                    recovery_chain=chain
                else:
                    require(candidate.get('artifact')==COMPACT_CHECKPOINT_DELTA,'compactRecovery','CORRUPT_RECORD')
            if require_tip:
                tip=db.execute('SELECT revision FROM btl.tick_sessions WHERE workspace_id=%s AND session_id=%s',
                               (workspace,session)).fetchone()
                require(tip is not None and tip[0]==target_revision,'qaDeltaRevision','CORRUPT_RECORD')
            if require_tip and recovery_chain is None:
                durable_count,durable_max=db.execute('SELECT count(*),max(revision) FROM btl.tick_checkpoints '
                    'WHERE workspace_id=%s AND session_id=%s AND revision>0',(workspace,session)).fetchone()
                require(durable_count==target_revision and
                        durable_max==(target_revision if target_revision else None),
                        'qaDeltaRevision','CORRUPT_RECORD')
            previous_hash=recovery_chain or base_record['chainHash']
            current_controller=[base_record['controller']]
            expected_checkpoint_artifact=COMPACT_CHECKPOINT_DELTA if compact_v1 else QA3_CHECKPOINT_DELTA
            expected_delta_artifact=COMPACT_DELTA if compact_v1 else None
            expected_checkpoint_format=1 if compact_v1 else 3
            def delta_stream():
                nonlocal previous_hash
                with db.cursor(name='btl_delta_'+uuid4().hex) as rows:
                    rows.execute('SELECT revision,payload,content_hash FROM btl.tick_checkpoints '
                        'WHERE workspace_id=%s AND session_id=%s AND revision>%s AND revision<=%s ORDER BY revision',
                        (workspace,session,start_revision,target_revision))
                    for n,(rev,payload,sha) in enumerate(rows,start_revision+1):
                        checkpoint=unpack(payload,sha)
                        keys(checkpoint,'schemaVersion formatVersion artifact revision stateHash chainHash previousHash delta controller')
                        delta=checkpoint['delta'];body=delta.get('body',{})
                        delta_valid=(delta.get('formatVersion')==1 and delta.get('artifact')==expected_delta_artifact) if compact_v1 else (
                            delta.get('formatVersion')==4 and delta.get('artifact')=='BTL-QA-OBSERVED-STATE-DELTA-4-DELTA')
                        require(checkpoint['schemaVersion']==1 and checkpoint['formatVersion']==expected_checkpoint_format
                                and checkpoint['artifact']==expected_checkpoint_artifact and checkpoint['revision']==rev==n
                                and checkpoint['previousHash']==previous_hash and body.get('revision')==rev
                                and delta_valid and checkpoint['stateHash']==body.get('stateHash')
                                and checkpoint['chainHash']==body.get('recordHash'),
                                'qaCheckpointDelta','CORRUPT_RECORD')
                        current_controller[0]=checkpoint['controller'];previous_hash=checkpoint['chainHash']
                        yield delta
            archive_format=self._is_archive_state(base_record['state'])
            callback=(lambda restored,rev:validate_snapshot(restored,current_controller[0],
                order_retention_policy=self.order_retention_policy)) if archive_format else None
            rebuilt=reconstruct_complete(base_record,delta_stream(),target_revision,state_callback=callback,base_chain_hash=recovery_chain)
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

    def _read(self,db,workspace,session,*,lock=False,include_format=False,progress_details=None):
        row=db.execute('SELECT payload,content_hash,revision,dataset_version,profile_hash FROM btl.tick_sessions WHERE workspace_id=%s AND session_id=%s'+(' FOR UPDATE' if lock else ''),(workspace,session)).fetchone()
        require(row is not None,'session','RESOURCE_UNAVAILABLE')
        wire=unpack(row[0],row[1])
        if wire.get('artifact') == PROGRESS_POINTER:
            keys(wire, 'schemaVersion artifact revision checkpointHash')
            require(wire['revision'] == row[2], 'progressPointer', 'CORRUPT_RECORD')
            tip, tip_hash = self._progress_checkpoint(db, workspace, session, row[2])
            require(tip_hash == wire['checkpointHash'], 'progressPointer', 'CORRUPT_RECORD')
            state, chain = self._progress_reconstruct(db, workspace, session, tip)
            require(state['sessionId'] == session and (state['datasetVersion'],state['profileHash']) == tuple(row[3:]),
                    'progressScope', 'CORRUPT_RECORD')
            base = validate_snapshot(state, tip['controller'], order_retention_policy=self.order_retention_policy)
            effective, identity = load_progress(db, workspace, session, base, tip_hash,
                                                order_retention_policy=self.order_retention_policy)
            if self._is_archive_state(effective['state']):
                self._verify_order_archive(db,workspace,session,effective['state'],full=False)
            if progress_details is not None:
                progress_details.update(base=base, tip=tip, tip_hash=tip_hash, identity=identity)
            return (effective, PROGRESS_FORMAT, chain) if include_format else effective
        chain_hash=None
        compact_artifact=wire.get('artifact') in (QA3_CHECKPOINT,COMPACT_CHECKPOINT)
        if compact_artifact:
            compact_v1=wire.get('artifact')==COMPACT_CHECKPOINT
            require(compact_v1 or self.qa_state_delta_v3,'qaSessionVersion','REFUSED_QA_SESSION_VERSION')
            keys(wire,'schemaVersion formatVersion artifact revision stateHash chainHash controller')
            expected_format=1 if compact_v1 else 3
            require(wire['schemaVersion']==1 and wire['formatVersion']==expected_format and wire['revision']==row[2],'snapshot','CORRUPT_RECORD')
            state=self._qa_state_cache_read(workspace,session,wire)
            if state is None:
                state,chain_hash=self._qa_reconstruct(db,workspace,session,upto_revision=row[2],require_tip=True)
                if self._is_archive_state(state):
                    self._verify_order_archive(db,workspace,session,state,full=True)
            else:
                chain_hash=wire['chainHash']
                if self._is_archive_state(state):
                    self._verify_order_archive(db,workspace,session,state,full=False)
            state_hash=content_hash(state)
            require(wire['stateHash']==state_hash and wire['chainHash']==chain_hash,'qaCheckpoint','CORRUPT_RECORD')
            validate_snapshot(state,wire['controller'],order_retention_policy=self.order_retention_policy)
            stored=dict(schemaVersion=1,artifact='BTL-OBSERVED-EXECUTION-CHECKPOINT-1',
                        state=state,controller=wire['controller']);storage_format='compact-v1' if compact_v1 else 'qa3'
        else:
            stored=read_snapshot(row[0],row[1],order_retention_policy=self.order_retention_policy);state=stored['state'];storage_format='legacy'
            # CP6A-3 full-state Sessions can retain their v3 delta sidecar; keep
            # verifying that historical path without rewriting their old bytes.
            if self._has_qa_base(db,workspace,session):
                rebuilt,_=self._qa_reconstruct(db,workspace,session,upto_revision=state['revision'],require_tip=True)
                require(canonical_bytes(rebuilt)==canonical_bytes(state),'qaDeltaState','CORRUPT_RECORD')
        s=stored['state']
        require(s['sessionId']==session and (s['revision'],s['datasetVersion'],s['profileHash'])==tuple(row[2:]),'state','CORRUPT_RECORD')
        if self._is_archive_state(s):self._verify_order_archive(db,workspace,session,s,full=False)
        tip=db.execute('SELECT payload,content_hash FROM btl.tick_checkpoints WHERE workspace_id=%s AND session_id=%s AND revision=%s',(workspace,session,s['revision'])).fetchone()
        require(tip is not None,'immutableTip','CORRUPT_RECORD')
        if storage_format in ('qa3','compact-v1'):
            tip_wire=unpack(*tip)
            allowed_tip_artifacts=(COMPACT_CHECKPOINT_BASE,COMPACT_CHECKPOINT_DELTA,COMPACT_RECOVERY) if storage_format=='compact-v1' else (
                QA3_CHECKPOINT_BASE,QA3_CHECKPOINT_DELTA)
            require(tip_wire.get('artifact') in allowed_tip_artifacts
                    and tip_wire.get('revision')==s['revision'] and tip_wire.get('stateHash')==state_hash
                    and tip_wire.get('chainHash')==chain_hash and tip_wire.get('controller')==stored['controller'],
                    'immutableTip','CORRUPT_RECORD')
            self._qa_state_cache_write(workspace,session,s,chain_hash)
        else:
            require(bytes(tip[0])==bytes(row[0]) and tip[1]==row[1],'immutableTip','CORRUPT_RECORD')
        return (stored,storage_format,chain_hash) if include_format else stored

    def _prior(self,db,workspace,session,command):
        row=db.execute('SELECT revision,command_hash,payload,content_hash FROM btl.tick_commands WHERE workspace_id=%s AND session_id=%s AND command_id=%s',(workspace,session,command['commandId'])).fetchone()
        if row is None:return None
        require(row[1]==content_hash(command),'commandId','REFUSED_IDEMPOTENCY_CONFLICT')
        wire=unpack(row[2],row[3])
        if wire.get('artifact') in (QA3_RESULT,COMPACT_RESULT):
            compact_v1=wire.get('artifact')==COMPACT_RESULT
            require(compact_v1 or self.qa_state_delta_v3,'receiptVersion','REFUSED_QA_RECEIPT_VERSION')
            expected_format=1 if compact_v1 else 3
            require(wire.get('schemaVersion')==1 and wire.get('formatVersion')==expected_format,'receiptVersion','CORRUPT_RECORD')
            require(type(wire.get('stateRevision')) is int and wire['stateRevision']==row[0],'receiptState','CORRUPT_RECORD')
            state,chain_hash=self._qa_reconstruct(db,workspace,session,upto_revision=wire['stateRevision'])
            if compact_v1:
                return expand_compact_receipt_v1(wire,command,state,chain_hash,order_retention_policy=self.order_retention_policy)
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
        elif self.state_storage_format == PROGRESS_FORMAT:
            require(checkpoint['artifact'] == PROGRESS_CONTROLLER, 'progressSource', 'REFUSED_STATE_VERSION')
            base_record = encode_compact_base(state)
            base_record.update(artifact=PROGRESS_BASE, ordinal=0, recoveryRevision=0,
                               chainHash=base_record['stateHash'], controller=deepcopy(checkpoint))
            raw_base, sha_base = pack(base_record)
            raw, sha = pack(dict(schemaVersion=1, artifact=PROGRESS_POINTER, revision=0, checkpointHash=sha_base))
        elif self.state_storage_format=='compact-v1':
            base_record=encode_compact_base(state)
            base_record.update(artifact=COMPACT_CHECKPOINT_BASE,chainHash=base_record['stateHash'],controller=deepcopy(checkpoint))
            raw_base,sha_base=pack(base_record)
            raw,sha=pack(dict(schemaVersion=1,formatVersion=1,artifact=COMPACT_CHECKPOINT,revision=0,
                stateHash=base_record['stateHash'],chainHash=base_record['chainHash'],controller=deepcopy(checkpoint)))
        else:
            raw,sha=pack(validate_snapshot(state,checkpoint,order_retention_policy=self.order_retention_policy))
        db.execute('INSERT INTO btl.tick_sessions VALUES (%s,%s,%s,%s,%s,%s,%s)',(workspace,session,state['datasetVersion'],state['profileHash'],0,raw,sha))
        if self.qa_state_delta_v3 or self.state_storage_format in ('compact-v1',PROGRESS_FORMAT):db.execute('INSERT INTO btl.tick_checkpoints VALUES (%s,%s,%s,%s,%s)',(workspace,session,0,raw_base,sha_base))
        else:db.execute('INSERT INTO btl.tick_checkpoints VALUES (%s,%s,%s,%s,%s)',(workspace,session,0,raw,sha))

    def create(self,scope,state,checkpoint):
        with connect(self.dsn) as db:
            if self._is_archive_state(state):self._ensure_order_archive_schema(db,state)
            self._insert(db,scope,state,checkpoint)
        if self.qa_state_delta_v3 or self.state_storage_format=='compact-v1':
            workspace,session=scoped(scope,state['sessionId'])
            self._qa_state_cache_write(workspace,session,state,content_hash(state))

    def prepare(self,scope,raw):
        command=command_wire(raw);workspace,session=scoped(scope,command['sessionId'])
        with connect(self.dsn) as db:
            db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            progress = {}
            stored=self._read(db,workspace,session,progress_details=progress)
            prior=self._prior(db,workspace,session,command)
            if prior is None and progress:
                prior=match_progress_receipt(stored,progress['identity'],command)
            if prior is not None:return stored,prior
            require(stored['state']['revision']==command['expectedRevision'],'revision','REFUSED_STALE_REVISION');return stored,None

    def historical_checkpoint(self,db,scope,session_id,target_revision):
        """Read one immutable revision in either snapshot-v1 or compact-v1 form."""
        workspace,session=scoped(scope,session_id);revision(target_revision)
        row=db.execute('SELECT payload,content_hash FROM btl.tick_checkpoints '
                       'WHERE workspace_id=%s AND session_id=%s AND revision=%s',
                       (workspace,session,target_revision)).fetchone()
        require(row is not None,'checkpoint','REFUSED_FORK_POINT')
        wire=unpack(*row)
        if wire.get('artifact') in (QA3_CHECKPOINT_BASE,QA3_CHECKPOINT_DELTA,
                                    COMPACT_CHECKPOINT_BASE,COMPACT_CHECKPOINT_DELTA,COMPACT_RECOVERY,PROGRESS_BASE,PROGRESS_DELTA):
            state,chain_hash=self._qa_reconstruct(db,workspace,session,upto_revision=target_revision)
            require(wire.get('revision')==target_revision and wire.get('stateHash')==content_hash(state)
                    and wire.get('chainHash')==chain_hash,
                    'checkpoint','CORRUPT_RECORD')
            if target_revision==0:
                state=wire['state']
            controller=wire['controller']
            validate_snapshot(state,controller,order_retention_policy=self.order_retention_policy)
            return dict(schemaVersion=1,artifact='BTL-OBSERVED-EXECUTION-CHECKPOINT-1',
                        state=state,controller=controller)
        return read_snapshot(row[0],row[1],order_retention_policy=self.order_retention_policy)

    def commit(self,scope,raw,before,after,checkpoint,events,replay=None,archive_records=None):
        command=command_wire(raw);workspace,session=scoped(scope,command['sessionId'])
        with connect(self.dsn) as db:
            progress = {}
            live,storage_format,prior_chain_hash=self._read(db,workspace,session,lock=True,include_format=True,progress_details=progress)
            prior=self._prior(db,workspace,session,command)
            if prior is None and progress:
                prior=match_progress_receipt(live,progress['identity'],command)
            if prior is not None:return prior
            old=live['state']
            if storage_format in ('qa3','compact-v1',PROGRESS_FORMAT):
                # The locked QA-v3 snapshot is already independently checked
                # against its state and delta commitments by _read. Compare the
                # complete validated structures directly instead of hashing a
                # wrapper around the growing full order map twice (which can
                # exhaust the bounded canonical node budget on long Sessions).
                same_before=(old==before['state'] and live['controller']==before['controller'])
            else:
                same_before=content_hash(live)==content_hash(before)
            require(same_before and old['revision']==command['expectedRevision'],'revision','REFUSED_STALE_REVISION')
            require(after['revision']==old['revision']+1 and all(after[k]==old[k] for k in ('sessionId','datasetId','datasetVersion','engineVersion','model','profile','profileHash','policy','startNs','initialBalance','parent')),'immutableContext')
            validate_snapshot(after,checkpoint,order_retention_policy=self.order_retention_policy)
            previous_checkpoint = live['controller']
            if previous_checkpoint['artifact'] == 'BTL-TICK-SHARED-SOURCE-CHECKPOINT-2':
                require(checkpoint['artifact'] == previous_checkpoint['artifact'] and
                        checkpoint['sourcePin'] == previous_checkpoint['sourcePin'],
                        'sourcePin', 'REFUSED_OBSERVED_SOURCE_IDENTITY')
                if command['kind'] == 'ADVANCE':
                    require(int(old['throughNs']) <= int(after['throughNs']) <= int(command['payload']['targetNs']) and
                            int(after['nextGroupIndex']) >= int(old['nextGroupIndex']) and
                            0 <= int(after['sourceCursorRevision']) - int(old['sourceCursorRevision']) <= 1,
                            'frontier', 'REFUSED_REPLAY_FRONTIER')
                    require(after['sourceCursorRevision'] != old['sourceCursorRevision'] or
                            checkpoint == previous_checkpoint, 'frontier', 'REFUSED_REPLAY_FRONTIER')
                    target = command['payload']['targetNs']
                    pending = checkpoint['cursor']['pendingTargetNs']
                    require(previous_checkpoint['cursor']['pendingTargetNs'] in (None,target) and
                            pending in (None,target) and type(replay) is dict and
                            replay.get('exhaustedThroughBoundary') is (pending is None) and
                            (pending is not None or after['throughNs'] == target),
                            'frontier', 'REFUSED_REPLAY_FRONTIER')
                else:
                    require(checkpoint == previous_checkpoint, 'frontier', 'REFUSED_REPLAY_FRONTIER')
            end,head=check_events(events,after,old['nextEventIndex'],old['eventHash'])
            require(after['nextEventIndex']==end and after['eventHash']==head,'eventHead','CORRUPT_RECORD')
            postings=[e for e in events if e['classification']=='SIMULATED_FILL']
            require(all(e['detail']['commission']=='0' for e in postings) and after['commission']==old['commission']=='0'
                    and Fraction(after['balance'])-Fraction(old['balance'])==sum((Fraction(e['detail']['balanceDelta']) for e in postings),Fraction(0))
                    and Fraction(after['realizedGross'])-Fraction(old['realizedGross'])==sum((Fraction(e['detail']['grossPosted']) for e in postings if e['kind']=='EXIT_FILL'),Fraction(0)),'cashPosting','CORRUPT_RECORD')
            validate_snapshot(after,checkpoint,order_retention_policy=self.order_retention_policy)
            if (progress and command['kind']=='ADVANCE' and not command['commandId'].startswith('command:replay-to:') and
                    not old['ended'] and not any(order['status'] in ('ACTIVE','PENDING') for order in old['orders'].values()) and
                    len(events)==1 and events[0]['kind']=='REPLAY_ADVANCED' and
                    (after['throughNs'],after['nextGroupIndex']) != (old['throughNs'],old['nextGroupIndex'])):
                return replace_progress(db,scope,progress['base'],progress['tip_hash'],command,
                                        dict(state=after,controller=checkpoint),events,
                                        order_retention_policy=self.order_retention_policy)
            compact_mode=storage_format in ('qa3','compact-v1',PROGRESS_FORMAT)
            archive_mode=self._is_archive_state(after)
            if archive_mode:
                self._archive_table(after)
                require(type(archive_records) is list,'orderArchive','REFUSED_SESSION_VERSION')
                expected=(integration_archive_advance(old['orderArchive'],archive_records)
                          if after['artifact']==STATE_INTEGRATION_PRODUCT_ARCHIVE_V1
                          else archive_advance(old['orderArchive'],archive_records))
                require(expected==after['orderArchive'],'archiveState','CORRUPT_RECORD')
                terminal_events={}
                for event in events:
                    if event['kind'] in ('ORDER_CANCELLED','EXPIRED_NO_QUOTE','EXIT_FILL'):
                        if event['kind']!='EXIT_FILL' or event['detail']['remaining']=='0':
                            terminal_events[event['orderId']]=event['kind']
                    elif event['kind']=='UNRESOLVED':
                        for oid in event['detail']['affectedOrderIds']:terminal_events[oid]='UNRESOLVED'
                for row in archive_records:
                    require(row['sessionId']==session and row['finalizedRevision']==after['revision'],
                            'archiveRevisionLink','CORRUPT_RECORD')
                    require(row['orderId'] in old['orders'],'archivePriorOrder','CORRUPT_RECORD')
                    expected_event={'CANCELLED':'ORDER_CANCELLED','EXPIRED':'EXPIRED_NO_QUOTE',
                        'CLOSED':'EXIT_FILL','UNRESOLVED':'UNRESOLVED'}[row['order']['status']]
                    require(terminal_events.get(row['orderId'])==expected_event,
                            'archiveTerminalEvent','CORRUPT_RECORD')
            else:
                require(archive_records in (None,[]),'qaOrderArchive','CORRUPT_RECORD')
            legacy_delta_mode=not compact_mode and self._has_qa_base(db,workspace,session)
            delta_record=None;chain_hash=None
            if compact_mode:
                if progress:
                    base_state = progress['base']['state']
                    consumed = old['revision'] if old['revision'] > base_state['revision'] else None
                    delta_record = encode_compact_delta(base_state,after,prior_chain_hash,progress_revision=consumed)
                else:
                    delta_record=(encode_compact_delta(old,after,prior_chain_hash) if storage_format=='compact-v1'
                                  else encode_delta_v4(old,after,prior_chain_hash))
                chain_hash=delta_record['body']['recordHash']
            elif legacy_delta_mode:
                prior_delta=db.execute('SELECT payload,content_hash FROM public.btl_qa_state_delta_v3 WHERE workspace_id=%s AND session_id=%s ORDER BY revision DESC LIMIT 1',(workspace,session)).fetchone()
                base_row=db.execute('SELECT payload,content_hash FROM public.btl_qa_state_base_v3 WHERE workspace_id=%s AND session_id=%s',(workspace,session)).fetchone()
                previous_hash=unpack(*prior_delta)['body']['recordHash'] if prior_delta else unpack(*base_row)['stateHash']
                delta_record=encode_delta(old,after,previous_hash);chain_hash=delta_record['body']['recordHash']
            if compact_mode:
                require(chain_hash is not None,'qaDeltaBase','CORRUPT_RECORD')
                if progress:
                    tip = progress['tip']
                    ordinal = tip['ordinal']+1
                    checkpoint_wire = dict(schemaVersion=1,artifact=PROGRESS_DELTA,revision=after['revision'],
                        stateHash=content_hash(after),chainHash=chain_hash,previousRevision=tip['revision'],
                        recoveryRevision=tip['recoveryRevision'],ordinal=ordinal,delta=delta_record,controller=deepcopy(checkpoint))
                    if ordinal%COMPACT_RECOVERY_INTERVAL==0:
                        checkpoint_wire.update(recoveryRevision=after['revision'],state=after)
                    session_wire = dict(schemaVersion=1,artifact=PROGRESS_POINTER,revision=after['revision'],
                                        checkpointHash=content_hash(checkpoint_wire))
                elif storage_format=='compact-v1':
                    checkpoint_wire=dict(schemaVersion=1,formatVersion=1,artifact=COMPACT_CHECKPOINT_DELTA,
                        revision=after['revision'],stateHash=content_hash(after),chainHash=chain_hash,
                        previousHash=delta_record['body']['previousHash'],delta=delta_record,controller=deepcopy(checkpoint))
                    if after['revision']%COMPACT_RECOVERY_INTERVAL==0:
                        checkpoint_wire.update(artifact=COMPACT_RECOVERY,state=after)
                    session_wire=dict(schemaVersion=1,formatVersion=1,artifact=COMPACT_CHECKPOINT,
                        revision=after['revision'],stateHash=content_hash(after),chainHash=chain_hash,controller=deepcopy(checkpoint))
                else:
                    checkpoint_wire=compact_qa3_checkpoint_delta(after,checkpoint,delta_record)
                    session_wire=compact_qa3_checkpoint(after,checkpoint,chain_hash)
            else:
                checkpoint_wire=validate_snapshot(after,checkpoint,order_retention_policy=self.order_retention_policy)
                session_wire=checkpoint_wire
            checkpoint_raw,checkpoint_hash=pack(checkpoint_wire)
            session_raw,session_hash=pack(session_wire)
            page=deepcopy(events[:PAGE_EVENTS]);complete=len(page)==len(events)
            result=dict(schemaVersion=1,artifact='BTL-OBSERVED-EXECUTION-RESULT-1',commandId=command['commandId'],commandHash=content_hash(command),state=after,events=page,eventCount=len(events),eventFromSequence=old['nextEventIndex'],eventsComplete=complete,nextEventSequence=None if complete else old['nextEventIndex']+len(page),replay=replay,durable=True,model=after['model'])
            if compact_mode:
                checked=checked_result_value(result,command,order_retention_policy=self.order_retention_policy)
                receipt_wire=(compact_receipt_v1(checked,content_hash(after),chain_hash) if storage_format in ('compact-v1',PROGRESS_FORMAT)
                              else compact_qa3_receipt(checked,content_hash(after),chain_hash))
            else:
                checked=checked_result(*pack(result),command,order_retention_policy=self.order_retention_policy)
                receipt_wire=result
            result_raw,result_hash=pack(receipt_wire)
            db.execute('INSERT INTO btl.tick_commands VALUES (%s,%s,%s,%s,%s,%s,%s)',(workspace,session,command['commandId'],after['revision'],content_hash(command),result_raw,result_hash))
            if archive_mode:
                table=self._archive_table(after)
                for row in archive_records:
                    archive_raw,archive_hash=pack(row)
                    db.execute(f'INSERT INTO {table} '
                        '(workspace_id,session_id,sequence,order_id,finalized_revision,record_hash,payload,content_hash) '
                        'VALUES (%s,%s,%s,%s,%s,%s,%s,%s)',
                        (workspace,session,row['sequence'],row['orderId'],row['finalizedRevision'],
                         row['recordHash'],archive_raw,archive_hash))
            for e in events:
                eraw,esha=pack(e);db.execute('INSERT INTO btl.tick_events VALUES (%s,%s,%s,%s,%s,%s,%s)',(workspace,session,command['commandId'],e['eventId'],e['sequence'],eraw,esha))
            db.execute('INSERT INTO btl.tick_checkpoints VALUES (%s,%s,%s,%s,%s)',(workspace,session,after['revision'],checkpoint_raw,checkpoint_hash))
            db.execute('UPDATE btl.tick_sessions SET revision=%s,payload=%s,content_hash=%s WHERE workspace_id=%s AND session_id=%s',(after['revision'],session_raw,session_hash,workspace,session))
            if legacy_delta_mode:
                delta_raw,delta_hash=pack(delta_record)
                db.execute('INSERT INTO public.btl_qa_state_delta_v3 VALUES (%s,%s,%s,%s,%s,%s)',(workspace,session,after['revision'],command['commandId'],delta_raw,delta_hash))
        if compact_mode:self._qa_state_cache_write(workspace,session,after,chain_hash)
        return deepcopy(result)

    def inspect(self,scope,session_id,after_sequence=0,maximum=64):
        workspace,session=scoped(scope,session_id);revision(after_sequence);require(type(maximum) is int and 1<=maximum<=PAGE_EVENTS,'maximum')
        with connect(self.dsn) as db:
            db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY');stored=self._read(db,workspace,session);state=stored['state']
            require(after_sequence<=state['nextEventIndex'],'eventOffset')
            if after_sequence==0:
                seed=db.execute('SELECT payload,content_hash FROM btl.tick_checkpoints WHERE workspace_id=%s AND session_id=%s AND revision=0',(workspace,session)).fetchone()
                seed_wire=unpack(*seed)
                if seed_wire.get('artifact') in (QA3_CHECKPOINT_BASE,COMPACT_CHECKPOINT_BASE,PROGRESS_BASE):
                    require(seed_wire.get('artifact') in (COMPACT_CHECKPOINT_BASE,PROGRESS_BASE) or self.qa_state_delta_v3,
                            'qaSessionVersion','REFUSED_QA_SESSION_VERSION')
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
