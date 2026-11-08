"""Source-family selection for the authenticated research service."""
from contracts.primitives import require, ContractError


LOCAL_SESSION = 'BTL-LOCAL-SESSION-1'
OBSERVED_SESSION = 'BTL-OBSERVED-RESEARCH-SESSION-1'
MONTHLY_PROVIDER_OPERATIONS = frozenset(('create_session', 'workspace', 'bootstrap', 'replay'))


def monthly_provider_required(operation):
    """Operations that actually read or reveal events from the pinned source."""
    return operation in MONTHLY_PROVIDER_OPERATIONS


def method_analytics_family(sessions):
    """Return the single analytics engine family or fail closed on a mix."""
    families = set()
    for _session_id, artifact in sessions:
        if artifact == LOCAL_SESSION:
            families.add('local')
        elif artifact == OBSERVED_SESSION:
            families.add('observed')
        else:
            raise ContractError('CORRUPT_RECORD', 'methodSession')
    if len(families) > 1:
        return 'mixed'
    return next(iter(families), 'empty')


def validate_source_selection(raw, catalog, monthly_catalog=None):
    """Reject a missing or stale public source selector before queue admission."""
    if catalog is None and monthly_catalog is None:
        return
    require(type(raw) is dict and type(raw.get('sourceKey')) is str and
            type(raw.get('period')) is str, 'sourceKey', 'INVALID_INPUT')
    key, period = raw['sourceKey'], raw['period']
    observed_key = catalog is not None and key in catalog._entries
    monthly_key = monthly_catalog is not None and (key, period) in monthly_catalog._entries
    require(not (observed_key and monthly_key), 'sourceKey', 'REFUSED_OPERATOR_CATALOG')
    if observed_key:
        try:
            catalog.selection(key, period)
        except ContractError as error:
            if error.code == 'OBSERVED_PERIOD_UNAVAILABLE':
                raise ContractError('INVALID_INPUT', 'sourceKey') from None
            raise
        return 'OBSERVED'
    if monthly_key:
        entry = monthly_catalog.selection(key, period)
        require(raw.get('startPeriod') == period, 'startPeriod', 'INVALID_INPUT')
        # Only generated fixtures currently use the V1 synthetic executor.
        # A pinned rights-evidence hash is not an execution eligibility grant.
        require(entry['eligibility'] == 'SYNTHETIC', 'monthlyEligibility', 'REFUSED_SOURCE')
        return 'MONTHLY_SYNTHETIC'
    raise ContractError('INVALID_INPUT', 'sourceKey')


def observed_route(operation, args, catalog, monthly_catalog=None):
    """Select the pinned observed family without a synthetic fallback.

    If an operator catalog is configured, a new Session must explicitly name
    one of its public keys. Existing Sessions are dispatched by their stored
    artifact in the request handler.
    """
    if catalog is None:
        return False
    if operation in ('catalog', 'create_method'):
        return True
    if operation == 'create_session':
        require(args and type(args[0]) is dict and 'sourceKey' in args[0],
                'sourceKey', 'INVALID_INPUT')
        raw = args[0]
        if monthly_catalog is not None and (raw['sourceKey'], raw.get('period')) in monthly_catalog._entries:
            return False
        return True
    return operation == 'replay_to'
