"""Authenticated-application composition for the separate observed engine.

Sources are selected only from a trusted, hash-pinned operator catalog. This
class exposes no source paths, qualification proofs or provider handles to a
request. It shares immutable Method definitions but writes an explicitly new
Session artifact and delegates financial truth to the observed controller.
"""
from collections import OrderedDict
from copy import deepcopy
from threading import RLock
from datetime import datetime,timezone
from decimal import Decimal
from fractions import Fraction
import json

from application.models import TrustedScope
from contracts.canonical import canonical_bytes,content_hash
from contracts.models import Command,SessionContext,Observation,validate_command
from contracts.primitives import require,identifier,revision
from ticks.contracts import keys,tag,uint
from infrastructure.database import connect
from .analysis import RESEARCH_VERSION,planned_risk
from .contracts import exact,open_payload,policy_wire,text,risk_quantity
from .journal import validate_note,request as journal_request,MAX_JOURNAL_ORDERS
from .observed_catalog import ObservedCatalog
from .observed_controller import ObservedExecutionController
from .observed_kernel import command_wire, seed_state, PRODUCT_ORDER_RETENTION_V1
from .observed_session_dispatch import dispatch_observed_session
from .observed_postgres import ObservedExecutionStore, PROGRESS_FORMAT
from .observed_profile import ENGINE_VERSION,MODEL,ObservedExecutionProfile
from .observed_analysis import ObservedStatistics
from .postgres import pack,unpack
from .research import method_policy,label
from .bootstrap import bootstrap as descriptive_bootstrap,validate_seed

META='BTL-OBSERVED-RESEARCH-SESSION-1'
VIEW='BTL-OBSERVED-RESEARCH-VIEW-1'
_STATS_LOCK=RLock()
_STATS_BY_DSN=OrderedDict()
REVIEW='BTL-OBSERVED-ORDER-REVIEW-1'
PROGRESS_REVIEW='BTL-OBSERVED-ORDER-REVIEW-PROGRESS-1'
REPLAY_TO_CHUNKS=8


def _stored_observed_state(db,workspace_id,session_id):
    row=db.execute('SELECT payload,content_hash FROM btl.tick_sessions '
                   'WHERE workspace_id=%s AND session_id=%s',(workspace_id,session_id)).fetchone()
    require(row is not None,'state','CORRUPT_RECORD')
    stored=unpack(*row);state=stored.get('state')
    if state is None:
        base=db.execute('SELECT payload,content_hash FROM btl.tick_checkpoints '
                        'WHERE workspace_id=%s AND session_id=%s AND revision=0',
                        (workspace_id,session_id)).fetchone()
        require(base is not None,'genesis','CORRUPT_RECORD')
        state=unpack(*base).get('state')
    require(type(state) is dict and type(state.get('artifact')) is str,
            'sessionFormat','CORRUPT_RECORD')
    return state


class ObservedResearchApplication:
    """One workspace-scoped Method/Session adapter for the observed family."""
    def __init__(self,dsn,scope,catalog,*,state_storage_format='snapshot-v1',
                 product_order_archive_v1=False):
        require(type(scope) is TrustedScope,'scope','SCOPE_REQUIRED');require(type(catalog) is ObservedCatalog,'catalog')
        require(state_storage_format in ('snapshot-v1','compact-v1',PROGRESS_FORMAT),'stateStorageFormat','REFUSED_STATE_VERSION')
        require(type(product_order_archive_v1) is bool,'productOrderArchive')
        if product_order_archive_v1:
            require(state_storage_format in ('compact-v1',PROGRESS_FORMAT),
                    'productOrderArchive','REFUSED_STATE_VERSION')
        retention=PRODUCT_ORDER_RETENTION_V1 if product_order_archive_v1 else None
        self.dsn=dsn;self.scope=scope;self.catalog=catalog
        self.store=ObservedExecutionStore(dsn,order_retention_policy=retention,
            state_storage_format=state_storage_format,product_order_archive_v1=product_order_archive_v1)
        self.controller=ObservedExecutionController(self.store,catalog.resolve,order_retention_policy=retention)
        key=content_hash(dict(schemaVersion=1,artifact='BTL-OBSERVED-STATS-SERVICE-KEY-1',
                              dsnHash=content_hash({'schemaVersion':1,'dsn':dsn}),stateStorageFormat=state_storage_format,
                              productOrderArchiveV1=product_order_archive_v1))
        with _STATS_LOCK:
            self.statistics=_STATS_BY_DSN.get(key)
            if self.statistics is None:self.statistics=ObservedStatistics(self.store);_STATS_BY_DSN[key]=self.statistics
            _STATS_BY_DSN.move_to_end(key)
            while len(_STATS_BY_DSN)>4:_STATS_BY_DSN.popitem(last=False)

    def close(self):pass  # The operator catalog owns handles across admitted requests.

    def close_services(self):
        self.catalog.close()

    @staticmethod
    def _same_projection(projection,state):
        provenance=projection.get('provenance') or {}
        return projection.get('revision',provenance.get('revision'))==state['revision'] and provenance.get('eventHead',state['eventHash'])==state['eventHa