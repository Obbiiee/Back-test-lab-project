"""Storage boundary for versioned observed replay progress.

The caller supplies a verified immutable base snapshot and owns the transaction.
The hosted execution store does not select this format until financial commits
and command reconciliation can consume the same logical frontier.
"""
from copy import deepcopy

from contracts.primitives import digest, require, revision
from ticks.contracts import keys
from .observed_kernel import emit, validate_snapshot
from .postgres import pack, scoped, unpack

ARTIFACT = 'BTL-OBSERVED-REPLAY-PROGRESS-1'
CONTROLLER = 'BTL-TICK-SHARED-SOURCE-CHECKPOINT-2'
REPLAY_FIELDS = ('revision', 'throughNs', 'nextGroupIndex', 'sourceCheckpointHash',
                 'sourcePrefixHash', 'sourceCursorRevision', 'lastObservedNs', 'quoteBasis')


def read_progress(db, scope, base, base_hash):
    """Return the effective snapshot, checking the row against its immutable base."""
    workspace, session = scoped(scope, base['state']['sessionId'])
    row = db.execute(
        'SELECT base_revision,base_hash,revision,through_ns,next_group_index,payload,content_hash '
        'FROM btl.observed_replay_progress WHERE workspace_id=%s AND session_id=%s',
        (workspace, session),
    ).fetchone()
    if row is None:
        return base

    base_state = base['state']
    base_revision, stored_base_hash, stored_revision, through, next_group, raw, sha = row
    require((base_revision, stored_base_hash) == (base_state['revision'], base_hash),
            'replayProgressBase', 'CORRUPT_RECORD')
    wire = unpack(raw, sha)
    keys(wire, 'schemaVersion artifact replay controller')
    require(wire['schemaVersion'] == 1 and wire['artifact'] == ARTIFACT,
            'replayProgressFormat', 'CORRUPT_RECORD')
    keys(wire['replay'], ' '.join(REPLAY_FIELDS))
    state = {**deepcopy(base_state), **wire['replay']}
    restored = validate_snapshot(state, wire['controller'])
    require(state['revision'] == stored_revision and stored_revision > base_revision and
            int(state['throughNs']) == through and int(state['nextGroupIndex']) == next_group,
            'replayProgressPointer', 'CORRUPT_RECORD')
    _check_transition(base, state, wire['controller'])
    return restored


def _check_transition(before, state, controller):
    old = before['state']
    previous_controller = before['controller']
    require(not old['ended'] and
            not any(order['status'] in ('PENDING', 'ACTIVE') for order in old['orders'].values()),
            'replayProgressFinancialState', 'REFUSED_FINANCIAL_PROGRESS')
    require(previous_controller.get('artifact') == controller.get('artifact') == CONTROLLER and
            previous_controller['sourcePin'] == controller['sourcePin'],
            'replayProgressSource', 'REFUSED_OBSERVED_SOURCE_IDENTITY')
    require(int(state['throughNs']) >= int(old['throughNs']) and
            int(state['nextGroupIndex']) >= int(old['nextGroupIndex']) and
            int(state['sourceCursorRevision']) > int(old['sourceCursorRevision']) and
            (int(state['throughNs']) > int(old['throughNs']) or
             int(state['nextGroupIndex']) > int(old['nextGroupIndex'])),
            'replayProgressFrontier', 'REFUSED_REPLAY_FRONTIER')


def replace_progress(db, scope, base, base_hash, expected_revision, proposed, events):
    """Replace a progress-only snapshot after locking the scoped Session row."""
    old_base = base['state']
    workspace, session = scoped(scope, old_base['sessionId'])
    digest(base_hash, 'replayProgressBaseHash')
    revision(expected_revision)
    row = db.execute(
        'SELECT revision FROM btl.tick_sessions WHERE workspace_id=%s AND session_id=%s FOR UPDATE',
        (workspace, session),
    ).fetchone()
    require(row is not None and row[0] == old_base['revision'],
            'replayProgressBase', 'REFUSED_STALE_REVISION')
    current = read_progress(db, scope, base, base_hash)
    require(current['state']['revision'] == expected_revision, 'revision', 'REFUSED_STALE_REVISION')

    state, controller = deepcopy(proposed['state']), proposed['controller']
    validate_snapshot(state, controller)
    # Only the reducer's single bookkeeping event can be omitted. Any
    # limitation, unresolved evidence or financial event stays immutable.
    prior_state = current['state']
    event_state = dict(prior_state)
    expected_events = []
    emit(event_state, expected_events, 'REPLAY_ADVANCED', throughNs=state['throughNs'])
    require(events == expected_events and
            (state['nextEventIndex'], state['eventHash']) == (event_state['nextEventIndex'], event_state['eventHash']),
            'replayProgressEvents', 'REFUSED_FINANCIAL_PROGRESS')
    state.update(nextEventIndex=prior_state['nextEventIndex'], eventHash=prior_state['eventHash'])
    require(state['revision'] == expected_revision + 1 and
            int(state['sourceCursorRevision']) == int(current['state']['sourceCursorRevision']) + 1,
            'replayProgressRevision', 'REFUSED_STALE_REVISION')
    require(all(state[key] == old_base[key] for key in old_base if key not in REPLAY_FIELDS),
            'replayProgressFinancialState', 'REFUSED_FINANCIAL_PROGRESS')
    _check_transition(current, state, controller)
    raw, sha = pack(dict(schemaVersion=1, artifact=ARTIFACT,
                         replay={key: state[key] for key in REPLAY_FIELDS}, controller=controller))
    db.execute(
        'INSERT INTO btl.observed_replay_progress '
        '(workspace_id,session_id,base_revision,base_hash,revision,through_ns,next_group_index,payload,content_hash) '
        'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (workspace_id,session_id) DO UPDATE SET '
        'revision=EXCLUDED.revision,through_ns=EXCLUDED.through_ns,next_group_index=EXCLUDED.next_group_index,'
        'payload=EXCLUDED.payload,content_hash=EXCLUDED.content_hash',
        (workspace,session,old_base['revision'],base_hash,state['revision'],
         int(state['throughNs']),int(state['nextGroupIndex']),raw,sha),
    )
