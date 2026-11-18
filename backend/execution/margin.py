"""Margin arithmetic (pure, exact, INFORMATIONAL). No gate, no stop-out, not wired into any reducer.

The simulator currently has NO margin or leverage model. This module defines the arithmetic and a first set of rules so the owner can approve numbers; it never blocks an
order, closes a position or changes a balance. Rules are explicit parameters; the DEFAULTS below are placeholders chosen by the implementer, not owner decisions.
  required margin (account currency) = lots * contractSize * basePriceInAccountCurrency / leverage
  equity = balance + unrealised;  free margin = equity - used margin;  margin level = equity / used margin * 100  (None when nothing is open)
  status: OK | MARGIN_CALL (level <= marginCallPct) | STOP_OUT (level <= stopOutPct)  -- a label, never an action
"""
from dataclasses import dataclass
from fractions import Fraction

from contracts.primitives import require
from .contracts import exact, text


@dataclass(frozen=True)
class MarginRules:
    leverage: int = 100                     # PLACEHOLDER (owner decision pending)
    margin_call_pct: Fraction = Fraction(100)    # PLACEHOLDER
    stop_out_pct: Fraction = Fraction(50)        # PLACEHOLDER

    def __post_init__(self):
        require(type(self.leverage) is int and 1 <= self.leverage <= 1000, "leverage", "REFUSED_MARGIN_RULES")
        require(0 <= self.stop_out_pct <= self.margin_call_pct, "levels", "REFUSED_MARGIN_RULES")


def required_margin(lots, contract_size, base_price_in_account, rules):
    """Exact Fraction. `base_price_in_account` is the price of ONE unit of the base currency in account currency (for a USD-quoted pair: its own price)."""
    require(rules.leverage >= 1, "leverage", "REFUSED_MARGIN_RULES")
    return exact(lots, "lots", True) * exact(contract_size, "contractSize", True) * exact(base_price_in_account, "price", True) / rules.leverage


def margin_account(balance, unrealised, used_margin, rules):
    """Everything as exact Fractions; text() renders them. `used_margin` is the sum of required margins of the open positions."""
    equity = Fraction(balance) + Fraction(unrealised)
    free = equity - Fraction(used_margin)
    if Fraction(used_margin) == 0:
        level, status = None, "OK"
    else:
        level = equity / Fraction(used_margin) * 100
        status = "STOP_OUT" if level <= rules.stop_out_pct else "MARGIN_CALL" if level <= rules.margin_call_pct else "OK"
    return dict(equity=text(equity), usedMargin=text(Fraction(used_margin)), freeMargin=text(free), marginLevelPct=None if level is None else text(level),
                status=status, leverage=rules.leverage, informational=True)
