"""Exact conditional-model arithmetic proposals, never a quote admission or fill."""
from contracts.primitives import require
from .contracts import exact, money, price, quantity, text
from .observed_profile import ENGINE_VERSION, MODEL, ObservedExecutionProfile


def _profile(profile):
    require(type(profile) is ObservedExecutionProfile, 'profile', 'REFUSED_OBSERVED_PROFILE')
    return profile.wire


def _strings(**values):
    for name, value in values.items():
        require(type(value) is str, name)


def _proposal(profile, artifact, **values):
    return dict(schemaVersion=1, artifact=artifact, engineVersion=ENGINE_VERSION,
                model=MODEL, profileHash=profile.profile_hash, committed=False, **values)


def exit_amount(profile, *, side, entry_price, exit_price, lots):
    """Caller must establish the recorded liquidation side/causal eligibility.

    This helper only calculates given exact prices; it cannot select events,
    infer a path, post a balance, or admit UNKNOWN evidence to another model.
    """
    p = _profile(profile)
    require(type(side) is str and side in ('LONG', 'SHORT'), 'side')
    _strings(entry=entry_price, exit=exit_price, quantity=lots)
    entry, exit_ = price(entry_price, p), price(exit_price, p)
    size = quantity(lots, p)
    gross = (exit_-entry)*(1 if side == 'LONG' else -1)*exact(p['contractSize'], 'contract', True)*size
    return _proposal(profile, 'BTL-OBSERVED-EXIT-PROPOSAL-1', quantity=text(size),
                     entryPrice=text(entry), exitPrice=text(exit_), grossExact=text(gross),
                     grossPosted=money(gross, p['moneyScale']), commissionExact='0', commissionPosted='0')


def risk_size(profile, *, balance, risk_percent, entry_price, stop_price):
    """Exact zero-cost sizing; order geometry/Method policy belong to the reducer."""
    p = _profile(profile)
    _strings(balance=balance, riskPercent=risk_percent, entry=entry_price, stop=stop_price)
    capital, percent = exact(balance, 'balance', True), exact(risk_percent, 'riskPercent', True)
    require(percent <= 100, 'riskPercent')
    entry, stop = price(entry_price, p), price(stop_price, p)
    distance = abs(entry-stop)
    require(distance > 0, 'stopDistance', 'REFUSED_STOP_DISTANCE')
    budget = capital*percent/100
    per_lot = distance*exact(p['contractSize'], 'contract', True)
    step = exact(p['lotStep'], 'step', True)
    wanted_steps = budget/per_lot/step
    size = (wanted_steps.numerator//wanted_steps.denominator)*step
    quantity(text(size), p)  # Refuse below/above bounds; never round up or cap silently.
    return _proposal(profile, 'BTL-OBSERVED-RISK-PROPOSAL-1', quantity=text(size),
                     riskBudgetExact=text(budget), riskUsedExact=text(size*per_lot),
                     unusedRiskExact=text(budget-size*per_lot), costBudgetPerLotExact='0')
