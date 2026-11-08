"""Version-aware dispatch for immutable observed Session wire artifacts.

This module deliberately selects a persisted format; it never rewrites an
archive/state or infers the selected family from current application defaults.
"""
from dataclasses import dataclass

from contracts.primitives import require

LEGACY = 'BTL-OBSERVED-EXECUTION-STATE-1'
QA_ARCHIVE = 'BTL-OBSERVED-EXECUTION-STATE-QA-ORDER-ARCHIVE-1'
P0_PRODUCT_ARCHIVE = 'BTL-OBSERVED-EXECUTION-STATE-PRODUCT-ORDER-ARCHIVE-1'
INTEGRATION_PRODUCT_ARCHIVE = 'BTL-OBSERVED-EXECUTION-STATE-ARCHIVE-1'


@dataclass(frozen=True)
class ObservedSessionFormat:
    artifact: str
    family: str
    archive_codec: str
    archive_table: str | None
    lifetime_order_cap: int | None
    active_order_cap: int


_FORMATS = {
    LEGACY: ObservedSessionFormat(LEGACY, 'observed-legacy', 'none', None, 128, 128),
    QA_ARCHIVE: ObservedSessionFormat(QA_ARCHIVE, 'observed-qa', 'qa-v1',
        'public.btl_qa_terminal_order_archive_v1', 512, 128),
    P0_PRODUCT_ARCHIVE: ObservedSessionFormat(P0_PRODUCT_ARCHIVE, 'observed-product', 'p0-v1',
        'btl.tick_terminal_order_archive_v1', None, 128),
    INTEGRATION_PRODUCT_ARCHIVE: ObservedSessionFormat(INTEGRATION_PRODUCT_ARCHIVE,
        'observed-product', 'integration-v1', 'btl.tick_terminal_orders', None, 128),
}


def dispatch_observed_session(state):
    """Select storage, receipt and read-model format from persisted state."""
    require(type(state) is dict and type(state.get('artifact')) is str,
            'sessionFormat', 'CORRUPT_RECORD')
    selected = _FORMATS.get(state['artifact'])
    require(selected is not None, 'sessionFormat', 'REFUSED_SESSION_VERSION')
    require(('orderArchive' in state) is (selected.archive_codec != 'none'),
            'sessionFormat', 'CORRUPT_RECORD')
    return selected


def observed_session_format(artifact):
    """Resolve a persisted artifact string without accepting unknown versions."""
    require(type(artifact) is str, 'sessionFormat', 'CORRUPT_RECORD')
    selected = _FORMATS.get(artifact)
    require(selected is not None, 'sessionFormat', 'REFUSED_SESSION_VERSION')
    return selected
