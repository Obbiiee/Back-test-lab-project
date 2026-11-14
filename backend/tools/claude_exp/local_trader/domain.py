"""Planning / review layer between the local trader UI and the frozen domain contracts.

It owns NO financial state. Every number that matters comes from, and is finally enforced by, the reference code:
  contracts.models.MethodPolicy         Free Style / Protocol definition (locked risk, locked RR, checklist ON/OFF)
  execution.contracts.open_payload      Quick/Planned rules, Protocol blocks (type, RR, risk, quantity, checklist), tick/lot precision
  execution.contracts.risk_quantity     lots from a risk budget (floored to the lot step, never rounded up)
  execution.observed_kernel.apply       re-runs the same checks when the confirmed order is applied (and validate_action for closes)
This module only (a) builds the draft the UI describes, (b) dry-runs it through open_payload and (c) prints the numbers the
spec asks a ticket to show. A request that bypasses the UI still fails in the kernel.
"""
import hashlib
import json
from decimal import Decimal
from fractions import Fraction

from contracts.models import MethodPolicy
from contracts.primitives import ContractError
from execution.contracts import open_payload as OPEN_PAYLOAD, risk_quantity, text, policy_from_wire


def dtxt(value):
    return format(Decimal(str(value)).normalize(), "f")


def make_method(kind, name="Method", risk=None, rr=None, conditions=(), checklist_on=False):
    """Immutable method definition -> (MethodPolicy, definition dict). The hash covers everything a user can lock."""
    if kind not in ("FREE_STYLE", "PROTOCOL"):
        raise ContractError("INVALID_INPUT", "kind")
    labels = [str(c).strip() for c in conditions if str(c).strip()]
    ids = [f"c{i + 1}" for i in range(len(labels))]
    definition = dict(kind=kind, name=str(name)[:60] or "Method", riskPercent=None if risk is None else dtxt(risk),
                      rr=None if rr is None else dtxt(rr), checklistOn=bool(checklist_on),
                      conditions=[dict(id=i, label=l) for i, l in zip(ids, labels)])
    if kind == "FREE_STYLE":
        definition.update(riskPercent=None, rr=None, checklistOn=False, conditions=[])
    digest = hashlib.sha256(json.dumps(definition, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    method_id = "method:" + digest[:12]
    if kind == "FREE_STYLE":
        return MethodPolicy(method_id, digest, "FREE_STYLE", False, ()), definition
    if not ids:
        raise ContractError("INVALID_INPUT", "conditions")
    return MethodPolicy(method_id, digest, "PROTOCOL", definition["checklistOn"], tuple(ids), definition["riskPercent"], definition["rr"]), definition


def method_view(defn, policy):
    protocol = policy.kind == "PROTOCOL"
    return dict(kind=policy.kind, name=defn["name"], id=policy.method_id, hash=policy.definition_hash[:12], riskPercent=defn["riskPercent"],
                rr=defn["rr"], checklistOn=defn["checklistOn"], conditions=defn["conditions"],
                allows=dict(quick=not protocol, market=not protocol, manualClose=not protocol, partialClose=not protocol, amendExits=not protocol,
                            cancelPending=True))


def _fixed(value, decimals):
    return f"{Decimal(str(value)):.{decimals}f}"


def build(state, draft, decimals):
    """Draft from the UI -> (normalized OPEN payload, preview numbers). Raises ContractError with the product's own codes."""
    p = state["profile"]
    policy = policy_from_wire(state["policy"])
    basis = state["quoteBasis"]
    if state["ended"] or state["unresolved"]:
        raise ContractError("SESSION_NOT_TRADABLE", "session")
    if basis is None or int(state["throughNs"]) - int(basis["timeNs"]) > int(p["maxObservedSilenceNs"]):
        raise ContractError("UNRESOLVED_RISK_QUOTE", "quote")
    if draft.get("side") not in ("BUY", "SELL"):
        raise ContractError("INVALID_INPUT", "side")
    side = "LONG" if draft["side"] == "BUY" else "SHORT"
    d = 1 if side == "LONG" else -1
    quote = basis["ask" if side == "LONG" else "bid"]
    workflow = draft.get("workflow")
    if workflow not in ("QUICK", "PLANNED"):
        raise ContractError("INVALID_INPUT", "workflow")
    supplied = {o["conditionId"]: o["outcome"] for o in draft.get("observations") or []}
    if not set(supplied).issubset(policy.conditions):
        raise ContractError("INVALID_INPUT", "conditions")
    observations = [dict(conditionId=c, outcome=supplied.get(c, "NOT_ASSESSED")) for c in policy.conditions]
    balance = Fraction(state["balance"])

    if workflow == "QUICK":
        lots = draft.get("lots")
        if lots in (None, ""):
            raise ContractError("INVALID_INPUT", "lots")
        raw = dict(side=side, orderType="MARKET", workflow="QUICK", entry=quote, quantity=_fixed(lots, 4).rstrip("0").rstrip("."),
                   sl=None, tp=None, riskPercent="1", observations=observations)
    else:
        entry_txt = _fixed(draft["entry"], decimals) if draft.get("entry") not in (None, "") else quote
        if draft.get("sl") in (None, ""):
            raise ContractError("INVALID_INPUT", "sl")
        sl_txt = _fixed(draft["sl"], decimals)
        entry, sl = Fraction(entry_txt), Fraction(sl_txt)
        stop = d * (entry - sl)                              # >0 for a correct stop; open_payload refuses the rest
        tick = Fraction(p["tickSize"])
        if policy.kind == "PROTOCOL":
            tp = entry + d * stop * Fraction(policy.rr)       # exact: a TP that is off the tick grid is refused, never distorted
        elif draft.get("tpMode") == "PRICE" or draft.get("rr") in (None, ""):
            if draft.get("tp") in (None, ""):
                raise ContractError("INVALID_INPUT", "tp")
            tp = Fraction(_fixed(draft["tp"], decimals))
        else:
            raw_tp = entry + d * stop * Fraction(str(draft["rr"]))
            tp = Fraction(round(raw_tp / tick)) * tick        # Free Style preset: nearest tick, the review shows the real R:R
        tp_txt = text(tp)
        if policy.kind == "PROTOCOL":
            risk_txt = text(Fraction(policy.risk_percent))
            qty = risk_quantity(text(balance * Fraction(policy.risk_percent) / 100), entry_txt, sl_txt, p)
        elif draft.get("lots") not in (None, ""):
            risk_txt = _fixed(draft.get("riskPercent") or "1", 4).rstrip("0").rstrip(".")
            qty = _fixed(draft["lots"], 4).rstrip("0").rstrip(".")
        else:
            risk_txt = _fixed(draft.get("riskPercent") or "1", 4).rstrip("0").rstrip(".")
            qty = risk_quantity(text(balance * Fraction(risk_txt) / 100), entry_txt, sl_txt, p)
        if entry_txt == quote:
            order_type = "MARKET"
        else:
            relation = d * (entry - Fraction(quote))
            order_type = "LIMIT" if relation < 0 else "STOP"
        raw = dict(side=side, orderType=order_type, workflow="PLANNED", entry=entry_txt, quantity=qty, sl=sl_txt, tp=tp_txt,
                   riskPercent=risk_txt, observations=observations)

    payload = OPEN_PAYLOAD(raw, p, policy, state["balance"])         # the product's own rules, incl. Protocol blocks
    return payload, preview(payload, p, state, d)


def preview(payload, p, state, d):
    entry, qty, contract = Fraction(payload["entry"]), Fraction(payload["quantity"]), Fraction(p["contractSize"])
    comm = Fraction(p["commissionPerLotSide"])
    tick = Fraction(p["tickSize"])
    out = dict(side="BUY" if d == 1 else "SELL", workflow=payload["workflow"], orderType=payload["orderType"], entry=payload["entry"],
               sl=payload["sl"], tp=payload["tp"], lots=payload["quantity"], riskPercent=payload["riskPercent"],
               pending=payload["orderType"] != "MARKET",
               fills=("pada tick eligible berikutnya di " + ("Ask" if d == 1 else "Bid")) if payload["orderType"] == "MARKET"
               else "saat harga menyentuh entry (pending)",
               stopTicks=None, rewardTicks=None, rr=None, riskAmount=None, riskOfBalance=None, estProfit=None)
    if payload["sl"] is not None:
        stop = d * (entry - Fraction(payload["sl"]))
        risk = qty * stop * contract + 2 * qty * comm
        out.update(stopTicks=str(int(stop / tick)), riskAmount=f"{float(risk):.2f}",
                   riskOfBalance=f"{float(risk / Fraction(state['balance']) * 100):.2f}")
        if payload["tp"] is not None:
            reward = d * (Fraction(payload["tp"]) - entry)
            out.update(rewardTicks=str(int(reward / tick)), rr=f"{float(reward / stop):.4f}",
                       estProfit=f"{float(qty * reward * contract - 2 * qty * comm):.2f}")
    return out
