"""Source-family selection for the authenticated research service."""
from contracts.primitives import require, ContractError


def validate_source_selection(raw, catalog):
    """Reject a missing or stale public source selector before queue admission."""
    if catalog is None:
        return
    require(type(raw) is dict and type(raw.get('sourceKey')) is str and
            type(raw.get('period')) is str, 'sourceKey', 'INVALID_INPUT')
    try:
        catalog.selection(raw['sourceKey'], raw['period'])
    except ContractError as error:
        if error.code == 'OBSERVED_PERIOD_UNAVAILABLE':
            raise ContractError('INVALID_INPUT', 'sourceKey') from None
        raise


def observed_route(operation, args, catalog):
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
        return True
    return operation == 'replay_to'
