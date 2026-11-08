"""Pure conditional observed transitions. Only a durable controller publishes them.

No filesystem/provider/clock access and no candle inputs. Frozen strict engines
remain unchanged. Raw quote quality is inspected, never rewritten as confirmed.
"""
from copy import deepcopy
from fractions import Fraction

from contracts.canonical import canonical_bytes, content_hash
from contracts.models import validate_action
from contracts.primitives import ContractError, digest, identifier, require, revision
from ticks.contracts import CanonicalTick, event_id, keys, uint
from ticks.contracts_v2 import canonical_v2_bytes, hash_v2
from ticks.evidence_v2 import CODES
from ticks.provider import diagnostic_counts
from ticks.timeline import CURSOR_FIELDS, make_group
from ticks.timeline_v2 import VERSION as TIMELINE_VERSION
from .contracts import exact, money, open_payload, policy_from_wire, policy_wire, price, quantity, text
from .engine import crossing, protective, can_change
from .observed_profile import ENGINE_VERSION, MODEL, MODEL_V2, ObservedExecutionProfile
from .observed_finance import exit_amount
from .observed_order_archive_v1 import (ARTIFACT as QA_ORDER_ARCHIVE_ARTIFACT,
    PRODUCT_ARTIFACT as PRODUCT_ORDER_ARCHIVE_ARTIFACT,
    PRODUCT_STATE_ARTIFACT as STATE_PRODUCT_ARCHIVE_V1, append as archive_append,
    advance as archive_advance, summary as archive_summary)
from .observed_order_archive_product_v1 import (ARTIFACT as INTEGRATION_PRODUCT_ORDER_ARCHIVE_ARTIFACT,
    summary as integration_product_archive_summary, append as integration_product_archive_append,
    advance as integration_product_archive_advance)

MAX_EVENTS, MAX_ORDERS = 256, 128
MAX_ACTIVE_ORDERS = 128
QA_ORDER_RETENTION_V2 = dict(schemaVersion=1,artifact='BTL-QA-ORDER-RETENTION-2',scope='ISOLATED_QA_ONLY',
                            maxCumulativeOrders=512,maxActiveOrders=MAX_ACTIVE_ORDERS)
QA_ORDER_RETENTION_V3 = dict(schemaVersion=1,artifact='BTL-QA-ORDER-RETENTION-3',scope='ISOLATED_QA_ONLY',
                            maxCumulativeOrders=1024,maxActiveOrders=MAX_ACTIVE_ORDERS)
QA_ORDER_RETENTION_V4 = dict(schemaVersion=1,artifact='BTL-QA-ORDER-RETENTION-4',scope='ISOLATED_QA_ONLY',
                            maxCumulativeOrders=4096,maxActiveOrders=MAX_ACTIVE_ORDERS)
PRODUCT_ORDER_RETENTION_V1 = dict(schemaVersion=1,artifact='BTL-PRODUCT-ORDER-RETENTION-1',
    scope='PRODUCT_V1',maxCumulativeOrders=None,maxActiveOrders=MAX_ACTIVE_ORDERS)
STATE_FIELDS = ('sessionId datasetId datasetVersion engineVersion model profile profileHash policy revision '
                'initialBalance balance realizedGross commission startNs throughNs nextGroupIndex nextEventIndex '
                'eventHash sourceCheckpointHash sourcePrefixHash sourceCursorRevision lastObservedNs quoteBasis orders unresolved ended financial parent')
STATE_FIELDS_QA_ARCHIVE_V1 = STATE_FIELDS+' orderArchive'
STATE_QA_ARCHIVE_V1 = 'BTL-OBSERVED-EXECUTION-STATE-QA-ORDER-ARCHIVE-1'
STATE_INTEGRATION_PRODUCT_ARCHIVE_V1 = 'BTL-OBSERVED-EXECUTION-STATE-ARCHIVE-1'
PLAN_FIELDS = 'side orderType workflow entry quantity sl tp riskPercent observations'
ORDER_FIELDS = PLAN_FIELDS+' status availableNs remaining entryPrice entryFillRef entryCost exitRequest grossPosted riskBalance riskBasisHash'


def _tag(raw, artifact, fields):
    keys(raw, 'schemaVersion artifact '+fields)
    require(type(raw['schemaVersion']) is int and raw['schemaVersion']==1 and raw['artifact']==artifact, 'artifact')


def order_limits(policy=None):
    if policy is None:return MAX_ORDERS,MAX_ORDERS
    if policy==PRODUCT_ORDER_RETENTION_V1:
        canonical_bytes(policy)
        return None,MAX_ACTIVE_ORDERS
    keys(policy,'schemaVersion artifact scope maxCumulativeOrders maxActiveOrders')
    require(policy in (QA_ORDER_RETENTION_V2,QA_ORDER_RETENTION_V3,QA_ORDER_RETENTION_V4)
            and policy['scope']=='ISOLATED_QA_ONLY',
            'orderRetention','REFUSED_POLICY')
    canonical_bytes(policy)
    return policy['maxCumulativeOrders'],policy['maxActiveOrders']


def _checkpoint(cp, profile):
    artifact=cp.get('artifact') if type(cp) is dict else None
    shared=artifact in ('BTL-TICK-SHARED-SOURCE-CHECKPOINT-1','BTL-TICK-SHARED-SOURCE-CHECKPOINT-2')
    shared_v2=artifact=='BTL-TICK-SHARED-SOURCE-CHECKPOINT-2'
    if shared_v2:
        keys(cp,'schemaVersion artifact sourcePin cursor nextPosition')
    elif shared:
        keys(cp,'schemaVersion artifact sourcePin cursor advanceLogHash')
    else:
        keys(cp, 'schemaVersion artifact cursor advanceLogHash positionLogHash')
        require(type(cp['schemaVersion']) is int and cp['schemaVersion']==2 and cp['artifact']=='BTL-TICK-CHECKPOINT-2', 'checkpoint')
    if shared:
        pin=cp['sourcePin']
        keys(pin,'schemaVersion artifact datasetId datasetVersion manifestHash rootHash indexContentHash archiveSha256 qualificationReceiptSha256')
        require(pin['schemaVersion']==1 and pin['artifact']=='BTL-QA-SHARED-SOURCE-PIN-1',
                's