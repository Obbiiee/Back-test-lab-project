Warning: truncated output (original token count: 21614)
Total output lines: 1143

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
from .journal_projection import journal_projection_changes
from .analytics_projection import advance_projection,ARTIFACT as ANALYTICS_PROJECTION_ARTIFACT
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

    def _insert_archive_record(self,db,workspace,session,state,row):
        """Persist one record using the selected immutable table's column contract."""
        table=self._archive_table(state)
        if state['artifact']==STATE_INTEGRATION_PRODUCT_ARCHIVE_V1:
            db.execute(f'INSERT INTO {table} '
                '(workspace_id,session_id,sequence,order_id,terminal_status,finalized_revision,record_hash,payload,content_hash) '
                'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                (workspace,session,row['sequence'],row['orderId'],row['order']['status'],
                 row['finalizedRevision'],row['recordHash'],*pack(row)))
            return
        db.execute(f'INSERT INTO {table} '
            '(workspace_id,session_id,sequence,order_id,finalized_revision,record_hash,payload,content_hash) '
            'VALUES (%s,%s,%s,%s,%s,%s,%s,%s)',
            (workspace,session,row['sequence'],row['orderId'],row['finalizedRevision'],
             row['recordHash'],*pack(row)))

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
            row=db.execute(f'SELECT record_hash,payload,conten…9614 tokens truncated…te,content_hash(state))

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
            journal_head=db.execute('SELECT format_version,through_sequence,event_hash,order_count,'
                'analytics_format_version,closed_order_count FROM btl.tick_journal_projection_heads '
                'WHERE workspace_id=%s AND session_id=%s FOR UPDATE',(workspace,session)).fetchone()
            if (progress and command['kind']=='ADVANCE' and not command['commandId'].startswith('command:replay-to:') and
                    not old['ended'] and not any(order['status'] in ('ACTIVE','PENDING') for order in old['orders'].values()) and
                    len(events)==1 and events[0]['kind']=='REPLAY_ADVANCED' and
                    (after['throughNs'],after['nextGroupIndex']) != (old['throughNs'],old['nextGroupIndex']) and
                    (journal_head is None or journal_head[0]!=1)):
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
                for row in archive_records:
                    self._insert_archive_record(db,workspace,session,after,row)
            for e in events:
                eraw,esha=pack(e);db.execute('INSERT INTO btl.tick_events VALUES (%s,%s,%s,%s,%s,%s,%s)',(workspace,session,command['commandId'],e['eventId'],e['sequence'],eraw,esha))
            # Maintain the bounded Journal read model only for Sessions that
            # opted into the versioned projection at creation. Legacy Sessions
            # keep their existing verified compatibility path.
            if journal_head is not None:
                format_version,through_sequence,head_hash,order_count,analytics_format_version,closed_order_count=journal_head
                require(format_version==1 and through_sequence==old['nextEventIndex'] and
                        head_hash==old['eventHash'],'journalProjectionHead','CORRUPT_RECORD')
                touched_ids=set()
                for event in events:
                    if event['orderId'] is not None:touched_ids.add(event['orderId'])
                    if event['kind']=='UNRESOLVED':touched_ids.update(event['detail']['affectedOrderIds'])
                prior_history={}
                for order_id in touched_ids:
                    prior_payload=db.execute('SELECT payload,content_hash FROM btl.tick_journal_order_projection '
                        'WHERE workspace_id=%s AND session_id=%s AND order_id=%s FOR UPDATE',
                        (workspace,session,order_id)).fetchone()
                    if prior_payload:
                        prior_wire=unpack(*prior_payload)
                        require(prior_wire.get('artifact')=='BTL-TICK-JOURNAL-ORDER-PROJECTION-1' and
                                prior_wire.get('orderId')==order_id,'journalProjection','CORRUPT_RECORD')
                        require(type(prior_wire.get('history')) is dict,'journalProjection','CORRUPT_RECORD')
                        prior_history[order_id]=prior_wire['history']
                projection_rows=journal_projection_changes(events,after,archive_records,prior_history)
                closed_delta=0
                for row in projection_rows:
                    payload=dict(schemaVersion=1,artifact='BTL-TICK-JOURNAL-ORDER-PROJECTION-1',
                        workspaceId=workspace,sessionId=session,orderId=row['orderId'],
                        status=row['status'],lastSequence=row['sequence'],eventId=row['eventId'],
                        order=row['order'],history=row['history'])
                    projection_raw,projection_hash=pack(payload)
                    prior_projection=db.execute('SELECT order_status FROM btl.tick_journal_order_projection '
                        'WHERE workspace_id=%s AND session_id=%s AND order_id=%s FOR UPDATE',
                        (workspace,session,row['orderId'])).fetchone()
                    prior_status=prior_projection[0] if prior_projection else None
                    closed_delta += int(row['status']=='CLOSED')-int(prior_status=='CLOSED')
                    db.execute('INSERT INTO btl.tick_journal_order_events '
                        '(workspace_id,session_id,order_id,sequence,event_id,event_kind,projection_hash) '
                        'VALUES (%s,%s,%s,%s,%s,%s,%s)',
                        (workspace,session,row['orderId'],row['sequence'],row['eventId'],row['kind'],projection_hash))
                    db.execute('INSERT INTO btl.tick_journal_order_projection '
                        '(workspace_id,session_id,order_id,order_status,last_sequence,event_id,payload,content_hash) '
                        'VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (workspace_id,session_id,order_id) '
                        'DO UPDATE SET order_status=EXCLUDED.order_status,last_sequence=EXCLUDED.last_sequence,'
                        'event_id=EXCLUDED.event_id,payload=EXCLUDED.payload,content_hash=EXCLUDED.content_hash',
                        (workspace,session,row['orderId'],row['status'],row['sequence'],row['eventId'],projection_raw,projection_hash))
                accepted_count=sum(1 for event in events if event['kind']=='ORDER_ACCEPTED')
                db.execute('UPDATE btl.tick_journal_projection_heads SET through_sequence=%s,event_hash=%s,'
                    'order_count=order_count+%s,closed_order_count=closed_order_count+%s '
                    'WHERE workspace_id=%s AND session_id=%s',
                    (after['nextEventIndex'],after['eventHash'],accepted_count,closed_delta,workspace,session))
                if analytics_format_version==1:
                    metric_row=db.execute('SELECT payload,content_hash FROM btl.tick_session_metric_projections '
                        'WHERE workspace_id=%s AND session_id=%s FOR UPDATE',(workspace,session)).fetchone()
                    require(metric_row is not None,'analyticsProjection','CORRUPT_RECORD')
                    metric=unpack(*metric_row)
                    require(metric.get('artifact')==ANALYTICS_PROJECTION_ARTIFACT and
                        metric.get('sessionId')==session and metric.get('revision')==old['revision'] and
                        metric.get('eventHead')==old['eventHash'] and
                        metric.get('tradeCount')==closed_order_count and
                        metric.get('tradeCount')+closed_delta>=0,'analyticsProjectionHead','CORRUPT_RECORD')
                    prior_metric=deepcopy(metric)
                    metric=advance_projection(metric,events,after,projection_rows)
                    metric_blob,metric_hash=pack(metric)
                    db.execute('UPDATE btl.tick_session_metric_projections SET payload=%s,content_hash=%s '
                        'WHERE workspace_id=%s AND session_id=%s',(metric_blob,metric_hash,workspace,session))
                    research_row=db.execute('SELECT method_id FROM btl.tick_research_sessions '
                        'WHERE workspace_id=%s AND session_id=%s',(workspace,session)).fetchone()
                    require(research_row is not None,'methodSession','CORRUPT_RECORD')
                    from .method_analytics_store import replace_session,session_item
                    replace_session(db,workspace,research_row[0],after['policy']['definitionHash'],
                        session_item(old,prior_metric),session_item(after,metric))
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
