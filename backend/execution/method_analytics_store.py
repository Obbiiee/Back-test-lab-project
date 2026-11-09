"""Transactional storage helpers for verified Method Analytics rollups."""

from contracts.primitives import require
from .method_analytics_projection import MethodAnalyticsAccumulator


MAX_METHOD_ROLLUP_BYTES = 262144


def _codec():
    from .postgres import pack, unpack
    return pack, unpack


def load_rollup(db, workspace_id, method_id, method_hash, *, lock=False):
    suffix = ' FOR UPDATE' if lock else ''
    row = db.execute(
        'SELECT format_version,rollup_state,session_count,payload,content_hash '
        'FROM btl.tick_method_metric_projections '
        'WHERE workspace_id=%s AND method_id=%s' + suffix,
        (workspace_id, method_id),
    ).fetchone()
    require(row is not None and row[0] == 1 and row[1] in
        ('READY', 'REBUILD_REQUIRED') and type(row[2]) is int and row[2] >= 0,
        'methodAnalyticsRollup', 'CORRUPT_RECORD')
    if row[1] == 'REBUILD_REQUIRED':
        require(row[3] is None and row[4] is None,
            'methodAnalyticsRollup', 'CORRUPT_RECORD')
        return dict(state=row[1], sessionCount=row[2], accumulator=None)
    require(row[3] is not None and type(row[4]) is str and len(row[4]) == 64,
        'methodAnalyticsRollup', 'CORRUPT_RECORD')
    _pack, unpack = _codec()
    snapshot = unpack(row[3], row[4])
    accumulator = MethodAnalyticsAccumulator.restore(snapshot,
        method_id=method_id, method_hash=method_hash)
    require(row[2] == accumulator.included_count + accumulator.excluded_count,
        'methodAnalyticsRollup', 'CORRUPT_RECORD')
    return dict(state=row[1], sessionCount=row[2], accumulator=accumulator)


def save_rollup(db, workspace_id, method_id, accumulator, session_count):
    require(type(accumulator) is MethodAnalyticsAccumulator and
        type(session_count) is int and session_count >= 0 and
        session_count == accumulator.included_count + accumulator.excluded_count,
        'methodAnalyticsRollup', 'CORRUPT_RECORD')
    pack, _unpack = _codec()
    payload, content_hash = pack(accumulator.snapshot())
    require(len(payload) <= MAX_METHOD_ROLLUP_BYTES,
        'methodAnalyticsRollup', 'REFUSED_ROLLUP_LIMIT')
    cursor = db.execute(
        'UPDATE btl.tick_method_metric_projections SET rollup_state=%s,'
        'session_count=%s,payload=%s,content_hash=%s '
        'WHERE workspace_id=%s AND method_id=%s AND format_version=1',
        ('READY', session_count, payload, content_hash, workspace_id, method_id),
    )
    require(getattr(cursor, 'rowcount', 1) == 1,
        'methodAnalyticsRollup', 'CORRUPT_RECORD')


def session_item(state, projection):
    require(type(state) is dict and type(projection) is dict and
        type(state.get('profile')) is dict and
        type(state['profile'].get('accountCurrency')) is str,
        'analyticsProjection', 'CORRUPT_RECORD')
    return dict(unit=(state['profileHash'], state['engineVersion'],
                      state['profile']['accountCurrency']),
        projection=projection,
        session=dict(sessionId=state['sessionId'], revision=state['revision'],
            datasetId=state['datasetId'], datasetVersion=state['datasetVersion'],
            profileHash=state['profileHash'], engineVersion=state['engineVersion'],
            eventHead=state['eventHash'], tradeCount=projection['tradeCount']))


def initialize_rollup(db, workspace_id, method_id, method_hash):
    accumulator = MethodAnalyticsAccumulator(method_id, method_hash)
    pack, _unpack = _codec()
    payload, content_hash = pack(accumulator.snapshot())
    db.execute(
        'INSERT INTO btl.tick_method_metric_projections '
        '(workspace_id,method_id,format_version,rollup_state,session_count,payload,content_hash) '
        "VALUES (%s,%s,1,'READY',0,%s,%s)",
        (workspace_id, method_id, payload, content_hash),
    )


def require_rebuild(db, workspace_id, method_id):
    db.execute(
        "UPDATE btl.tick_method_metric_projections SET rollup_state='REBUILD_REQUIRED',"
        'payload=NULL,content_hash=NULL WHERE workspace_id=%s AND method_id=%s',
        (workspace_id, method_id),
    )


def add_session(db, workspace_id, method_id, method_hash, item):
    stored = load_rollup(db, workspace_id, method_id, method_hash, lock=True)
    if stored['state'] != 'READY':
        return False
    stored['accumulator'].include(item)
    save_rollup(db, workspace_id, method_id, stored['accumulator'],
        stored['sessionCount'] + 1)
    return True


def replace_session(db, workspace_id, method_id, method_hash, previous, current):
    stored = load_rollup(db, workspace_id, method_id, method_hash, lock=True)
    if stored['state'] != 'READY':
        return False
    stored['accumulator'].replace_session(previous, current)
    save_rollup(db, workspace_id, method_id, stored['accumulator'],
        stored['sessionCount'])
    return True
