"""Provider-independent payment contract (design + pure functions; no network, no ledger writes).

A provider adapter turns provider-specific requests/notifications into these neutral types. The entitlement ledger (cloud/billing.py) is updated ONLY from a
VerifiedEvent, idempotently by (provider, eventKey): the same event delivered twice, out of order or after a refund changes nothing twice. Money is integer IDR.
Event kinds: PENDING, PAID, FAILED, EXPIRED, REFUNDED, CHARGEBACK. Terminal precedence: REFUNDED/CHARGEBACK > PAID > EXPIRED/FAILED > PENDING (a late
PAID after EXPIRED is a HOLD for manual reconciliation, never an automatic grant).
"""
from dataclasses import dataclass

KINDS = ("PENDING", "PAID", "FAILED", "EXPIRED", "REFUNDED", "CHARGEBACK")
_RANK = {"PENDING": 0, "FAILED": 1, "EXPIRED": 1, "PAID": 2, "REFUNDED": 3, "CHARGEBACK": 3}


@dataclass(frozen=True)
class PaymentRequest:
    order_id: str          # server-created, immutable, e.g. btl-sbx-<32 hex>
    amount_idr: int
    duration_seconds: int
    description: str


@dataclass(frozen=True)
class VerifiedEvent:
    provider: str
    event_key: str         # unique per provider delivery or per (order, kind, provider transaction): the idempotency key
    order_id: str
    kind: str
    amount_idr: int
    provider_transaction_id: str
    occurred_at: str       # ISO 8601 UTC as given by the provider


class PaymentProvider:
    """Adapter interface. Implementations must verify authenticity BEFORE returning a VerifiedEvent and must never grant entitlement themselves."""
    name = "abstract"

    def create_payment(self, request):        # -> dict(paymentUrl, expiresAt, providerReference)
        raise NotImplementedError

    def verify_notification(self, headers, raw_body, path):    # -> VerifiedEvent; raises PaymentRefused on any doubt
        raise NotImplementedError


class PaymentRefused(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def next_state(current, incoming):
    """Pure transition rule for the ledger: returns (new_state, action) with action in APPLY, IGNORE, HOLD."""
    if incoming not in KINDS or (current is not None and current not in KINDS):
        raise PaymentRefused("EVENT_KIND_INVALID")
    if current is None:
        return incoming, "APPLY"
    if current == incoming:
        return current, "IGNORE"                                    # duplicate delivery
    if current == "EXPIRED" and incoming == "PAID":
        return current, "HOLD"                                      # late payment after expiry: manual reconciliation
    if _RANK[incoming] > _RANK[current]:
        return incoming, "APPLY"
    return current, "IGNORE"                                        # an older/lower-precedence event never overwrites a terminal one
