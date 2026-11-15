"""DOKU (Non-SNAP) adapter: signature, Checkout request builder and notification verification, written from DOKU's public developer documentation
(developers.doku.com, read 2026-11-15). NOT integrated and NOT tested against DOKU: no sandbox credentials exist. Open points the documentation leaves unstated are listed in
docs/acceptance/RIKSORA-PAYMENT-PROVIDER-20261115.md and must be confirmed in the DOKU sandbox before any real use.

Signature (documented): components in order Client-Id, Request-Id, Request-Timestamp, Request-Target, Digest, each as 'Name:value' joined by '\\n' with no trailing
newline; Digest = base64(SHA-256(body)) and exists only for POST; Signature header = 'HMACSHA256=' + base64(HMAC-SHA256(secret, string)).
"""
import base64
import hashlib
import hmac
import json
import re

from .payment_provider import PaymentProvider, PaymentRefused, VerifiedEvent

SANDBOX_BASE = "https://api-sandbox.doku.com"
CHECKOUT_PATH = "/checkout/v1/payment"          # path rule from the documentation; the Checkout path itself is inferred, confirm in the sandbox
_TS = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
_STATUS = {"SUCCESS": "PAID", "FAILED": "FAILED", "EXPIRED": "EXPIRED", "REFUNDED": "REFUNDED", "VOIDED": "REFUNDED", "PENDING": "PENDING"}


def digest(body: bytes) -> str:
    return base64.b64encode(hashlib.sha256(body).digest()).decode()


def signature(secret: str, client_id: str, request_id: str, timestamp: str, target: str, body: bytes | None) -> str:
    parts = [f"Client-Id:{client_id}", f"Request-Id:{request_id}", f"Request-Timestamp:{timestamp}", f"Request-Target:{target}"]
    if body is not None:
        parts.append(f"Digest:{digest(body)}")
    mac = hmac.new(secret.encode(), "\n".join(parts).encode(), hashlib.sha256).digest()
    return "HMACSHA256=" + base64.b64encode(mac).decode()


class Doku(PaymentProvider):
    name = "DOKU"

    def __init__(self, client_id, secret_key, *, notification_path, base_url=SANDBOX_BASE):
        if not (client_id and secret_key and notification_path.startswith("/")):
            raise PaymentRefused("CONFIG_INVALID")
        self.client_id, self._secret, self.notification_path, self.base_url = client_id, secret_key, notification_path, base_url
        self._seen = set()                       # request ids already accepted (duplicate/replay guard; the ledger's event key is the durable one)

    def build_checkout(self, request, *, request_id, timestamp):
        """(url, headers, body bytes) for POST /checkout/v1/payment. Not sent by this module."""
        if not _TS.fullmatch(timestamp):
            raise PaymentRefused("TIMESTAMP_INVALID")
        body = json.dumps({"order": {"amount": request.amount_idr, "invoice_number": request.order_id, "auto_redirect": False},
                           "payment": {"payment_due_date": max(1, request.duration_seconds // 60)}}, separators=(",", ":")).encode()
        headers = {"Client-Id": self.client_id, "Request-Id": request_id, "Request-Timestamp": timestamp,
                   "Signature": signature(self._secret, self.client_id, request_id, timestamp, CHECKOUT_PATH, body), "Content-Type": "application/json"}
        return self.base_url + CHECKOUT_PATH, headers, body

    def verify_notification(self, headers, raw_body, path=None):
        h = {k.lower(): v for k, v in headers.items()}
        for name in ("client-id", "request-id", "request-timestamp", "signature"):
            if name not in h:
                raise PaymentRefused("NOTIFICATION_HEADER_MISSING")
        if h["client-id"] != self.client_id or not _TS.fullmatch(h["request-timestamp"]):
            raise PaymentRefused("NOTIFICATION_UNAUTHENTICATED")
        expected = signature(self._secret, self.client_id, h["request-id"], h["request-timestamp"], path or self.notification_path, raw_body)
        if not hmac.compare_digest(expected, h["signature"]):
            raise PaymentRefused("NOTIFICATION_UNAUTHENTICATED")
        try:
            body = json.loads(raw_body)
            order, transaction = body["order"], body["transaction"]
            invoice, amount, status = order["invoice_number"], int(order["amount"]), transaction["status"]
        except (ValueError, KeyError, TypeError):
            raise PaymentRefused("NOTIFICATION_INVALID") from None
        if status not in _STATUS or amount <= 0 or not isinstance(invoice, str):
            raise PaymentRefused("NOTIFICATION_INVALID")
        # DOKU retries until it sees 2xx and tells merchants to deduplicate by Request-Id; FAILED is not terminal for a Checkout (the payer may retry another method).
        return VerifiedEvent(provider=self.name, event_key=f"{self.name}:{h['request-id']}", order_id=invoice, kind=_STATUS[status], amount_idr=amount,
                             provider_transaction_id=str(transaction.get("original_request_id", "")), occurred_at=str(transaction.get("date", h["request-timestamp"])))
