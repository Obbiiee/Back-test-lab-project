"""Unmounted Snap sandbox transport. Observations never grant entitlement.

Caller must persist an immutable server order before checkout, and durably
reconcile observations under its account lock. No API/config activation here.
"""
from dataclasses import dataclass, field
import hashlib
import hmac
import json
import re
from urllib.parse import urlsplit

import httpx

MAX_RESPONSE = 65536
ORDER = re.compile(r"btl-sbx-[0-9a-f]{32}")


class PaymentError(ValueError):
    def __init__(self, code, *, uncertain=False):
        self.code, self.uncertain = code, uncertain
        super().__init__(code)


def check(ok, code):
    if not ok:
        raise PaymentError(code)


def text(value, limit=128):
    return type(value) is str and 0 < len(value) <= limit and all(32 <= ord(c) < 127 for c in value)


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            check(key not in result, 'PROVIDER_JSON_INVALID')
            result[key] = value
        return result
    try:
        value = json.loads(raw, object_pairs_hook=pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, UnicodeError, RecursionError):
        raise PaymentError('PROVIDER_JSON_INVALID') from None
    check(type(value) is dict, 'PROVIDER_JSON_INVALID')
    return value


@dataclass(frozen=True)
class SandboxOrder:
    order_id: str
    account_id: str
    plan_version: str
    amount_idr: int
    duration_seconds: int

    def __post_init__(self):
        check(type(self.order_id) is str and ORDER.fullmatch(self.order_id), 'ORDER_INVALID')
        check(text(self.account_id) and text(self.plan_version), 'ORDER_INVALID')
        check(type(self.amount_idr) is int and 1 <= self.amount_idr <= 1_000_000_000, 'ORDER_INVALID')
        check(type(self.duration_seconds) is int and 1 <= self.duration_seconds <= 366*86400, 'ORDER_INVALID')


@dataclass(frozen=True)
class SandboxConfig:
    server_key: str = field(repr=False)
    merchant_id: str

    def __post_init__(self):
        check(type(self.server_key) is str and self.server_key.startswith('SB-Mid-server-')
              and text(self.server_key, 256) and len(self.server_key) >= 24, 'SANDBOX_KEY_REQUIRED')
        check(text(self.merchant_id, 64) and re.fullmatch(r'[A-Za-z0-9_-]+', self.merchant_id), 'MERCHANT_INVALID')


@dataclass(frozen=True)
class Checkout:
    redirect_url: str = field(repr=False)
    # No token exposure, card input, account mutation or paid assertion.
    mode: str = 'SANDBOX'
    funds_collected: bool = False


@dataclass(frozen=True)
class Observation:
    order_id: str
    transaction_id: str
    provider_status: str
    disposition: str
    mode: str = 'SANDBOX'
    funds_collected: bool = False


def amount_matches(value, order):
    # IDR is whole rupiah in this product. Never compare binary floats or exponents.
    return (type(value) is str and len(value) <= 32
            and re.fullmatch(r'(0|[1-9][0-9]*)(?:\.00)?', value)
            and value.split('.')[0] == str(order.amount_idr))


class SnapSandbox:
    """Fixed sandbox endpoints; no production switch, redirects or network retries."""
    def __init__(self, config, *, transport=None):
        check(type(config) is SandboxConfig, 'CONFIG_INVALID')
        self._config = config
        # MockTransport injection is for authored tests, not browser-controlled URLs.
        self._transport = transport

    @property
    def merchant_id(self):
        return self._config.merchant_id

    def _request(self, method, url, payload=None):
        try:
            with httpx.Client(auth=httpx.BasicAuth(self._config.server_key, ''),
                              transport=self._transport, trust_env=False,
                              follow_redirects=False, timeout=httpx.Timeout(10, connect=5)) as client:
                with client.stream(method, url, json=payload,
                                   headers={'Accept': 'application/json'}) as response:
                    if response.status_code != 200 and not (method == 'POST' and response.status_code == 201):
                        raise PaymentError('PROVIDER_REQUEST_UNCERTAIN' if method == 'POST' else 'PROVIDER_UNAVAILABLE', uncertain=method == 'POST')
                    raw = bytearray()
                    for chunk in response.iter_bytes(chunk_size=8192):
                        check(len(raw)+len(chunk) <= MAX_RESPONSE, 'PROVIDER_RESPONSE_TOO_LARGE')
                        raw.extend(chunk)
                    return strict_json(bytes(raw))
        except PaymentError as error:
            if method == 'POST':
                raise PaymentError(error.code, uncertain=True) from None
            raise
        except httpx.HTTPError:
            raise PaymentError('PROVIDER_REQUEST_UNCERTAIN' if method == 'POST' else 'PROVIDER_UNAVAILABLE', uncertain=method == 'POST') from None

    def checkout(self, order):
        check(type(order) is SandboxOrder, 'ORDER_INVALID')
        value = self._request('POST', 'https://app.sandbox.midtrans.com/snap/v1/transactions', {
            'transaction_details': {'order_id': order.order_id, 'gross_amount': order.amount_idr},
            'enabled_payments': ['credit_card'], 'credit_card': {'secure': True},
            'expiry': {'unit': 'minutes', 'duration': 30},
        })
        try:
            redirect = value.get('redirect_url')
            check(text(redirect, 1024), 'CHECKOUT_RESPONSE_INVALID')
            url = urlsplit(redirect)
            check(url.scheme == 'https' and url.netloc == 'app.sandbox.midtrans.com'
                  and re.fullmatch(r'/snap/v[0-9]+/redir/[A-Za-z0-9_-]+', url.path)
                  and not url.query and not url.fragment, 'CHECKOUT_RESPONSE_INVALID')
            check(text(value.get('token'), 256), 'CHECKOUT_RESPONSE_INVALID')
        except ValueError:
            raise PaymentError('CHECKOUT_RESPONSE_INVALID', uncertain=True) from None
        return Checkout(redirect)

    def authenticate_notification(self, raw):
        check(type(raw) is bytes and len(raw) <= MAX_RESPONSE, 'NOTIFICATION_INVALID')
        value = strict_json(raw)
        fields = ('order_id', 'status_code', 'gross_amount', 'signature_key')
        check(all(text(value.get(k), 128) for k in fields), 'NOTIFICATION_INVALID')
        check(ORDER.fullmatch(value['order_id']) and re.fullmatch(r'[0-9]{3}', value['status_code'])
              and re.fullmatch(r'[0-9a-f]{128}', value['signature_key']), 'NOTIFICATION_INVALID')
        message = value['order_id']+value['status_code']+value['gross_amount']+self._config.server_key
        expected = hashlib.sha512(message.encode('utf8')).hexdigest()
        check(hmac.compare_digest(value['signature_key'], expected), 'NOTIFICATION_UNAUTHENTICATED')
        # Only use this as a signal to look up OUR immutable order and GET status.
        # transaction_status/fraud_status/merchant/currency are not signature-covered.
        return value['order_id']

    def status(self, order, *, transaction_id=None):
        check(type(order) is SandboxOrder, 'ORDER_INVALID')
        check(transaction_id is None or text(transaction_id), 'TRANSACTION_INVALID')
        value = self._request('GET', 'https://api.sandbox.midtrans.com/v2/'+order.order_id+'/status')
        check(value.get('order_id') == order.order_id and value.get('merchant_id') == self._config.merchant_id
              and value.get('currency') == 'IDR' and amount_matches(value.get('gross_amount'), order), 'ORDER_EVIDENCE_MISMATCH')
        tx = value.get('transaction_id')
        check(text(tx) and (transaction_id is None or tx == transaction_id), 'TRANSACTION_EVIDENCE_MISMATCH')
        state, fraud, method = value.get('transaction_status'), value.get('fraud_status'), value.get('payment_type')
        check(text(state, 32), 'STATUS_INVALID')
        disposition = 'HOLD'
        # This first adapter supports hosted card checkout only. Unknown methods/status
        # and incomplete fraud evidence remain HOLD; no implicit success/default Free.
        if method == 'credit_card':
            if state in ('refund', 'partial_refund', 'chargeback', 'partial_chargeback'):
                disposition = 'REVERSED'
            elif state in ('capture', 'settlement') and fraud == 'accept' and value.get('status_code') == '200':
                disposition = 'PAID_EVIDENCE'
            elif state == 'pending':
                disposition = 'PENDING'
            elif state in ('deny', 'cancel', 'expire', 'failure'):
                disposition = 'FAILED'
        return Observation(order.order_id, tx, state, disposition)


@dataclass(frozen=True)
class PaymentState:
    """Internal sandbox reducer only, not a persisted order or access grant.

    The future store must CAS this state under the account lock. Only authenticated
    SnapSandbox.status observations may enter observe(); never notification bodies.
    """
    order: SandboxOrder
    phase: str = 'CREATED'
    transaction_id: str | None = None
    paid_at: int | None = None
    expires_at: int | None = None

    def __post_init__(self):
        check(type(self.order) is SandboxOrder, 'ORDER_INVALID')
        check(self.phase in ('CREATED', 'CHECKOUT_STARTED', 'PENDING', 'FAILED', 'PAID', 'REVERSED', 'HOLD'), 'PAYMENT_STATE_INVALID')
        check(self.transaction_id is None or text(self.transaction_id), 'TRANSACTION_INVALID')
        check((self.paid_at is None) == (self.expires_at is None), 'PAYMENT_STATE_INVALID')
        if self.paid_at is not None:
            check(type(self.paid_at) is int and 0 <= self.paid_at <= 253402300799
                  and type(self.expires_at) is int
                  and self.expires_at == self.paid_at + self.order.duration_seconds,
                  'PAYMENT_STATE_INVALID')
            check(self.transaction_id is not None and self.phase in ('PAID', 'REVERSED', 'HOLD'), 'PAYMENT_STATE_INVALID')
        check(self.phase != 'PAID' or self.paid_at is not None, 'PAYMENT_STATE_INVALID')

    def begin_checkout(self):
        # Persist CHECKOUT_STARTED before the outbound POST. A crash/timeout leaves
        # it here; no retry method exists. Reconciliation uses authenticated GET.
        check(self.phase == 'CREATED' and self.transaction_id is None, 'CHECKOUT_ALREADY_STARTED')
        return PaymentState(self.order, 'CHECKOUT_STARTED')

    def observe(self, evidence, observed_at):
        check(type(evidence) is Observation and evidence.mode == 'SANDBOX'
              and evidence.funds_collected is False, 'OBSERVATION_INVALID')
        check(evidence.order_id == self.order.order_id, 'ORDER_EVIDENCE_MISMATCH')
        check(text(evidence.transaction_id) and (self.transaction_id is None
              or evidence.transaction_id == self.transaction_id), 'TRANSACTION_EVIDENCE_MISMATCH')
        check(type(observed_at) is int and 0 <= observed_at <= 253402300799, 'CLOCK_INVALID')
        check(evidence.disposition in ('PAID_EVIDENCE', 'REVERSED', 'PENDING', 'FAILED', 'HOLD'), 'OBSERVATION_INVALID')
        # Reversal is terminal even when a delayed success arrives afterwards.
        if self.phase == 'REVERSED':
            return self
        phase = {'PAID_EVIDENCE': 'PAID', 'REVERSED': 'REVERSED',
                 'PENDING': 'PENDING', 'FAILED': 'FAILED', 'HOLD': 'HOLD'}[evidence.disposition]
        paid_at, expires_at = self.paid_at, self.expires_at
        if phase == 'PAID':
            if paid_at is None:
                paid_at, expires_at = observed_at, observed_at + self.order.duration_seconds
        elif paid_at is not None and phase in ('PENDING', 'FAILED'):
            # Out-of-order non-success cannot extend or silently revoke a grant;
            # inconsistent evidence suspends this order until fresh reconciliation.
            phase = 'HOLD'
        return PaymentState(self.order, phase, evidence.transaction_id, paid_at, expires_at)

    def eligible(self, now):
        check(type(now) is int and 0 <= now <= 253402300799, 'CLOCK_INVALID')
        return self.phase == 'PAID' and self.paid_at <= now < self.expires_at
