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

    QA-v3 pers