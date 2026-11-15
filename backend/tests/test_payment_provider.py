import json
import unittest

from cloud import doku
from cloud.payment_provider import PaymentRefused, PaymentRequest, next_state


class Contract(unittest.TestCase):
    def test_transition_rules(self):
        self.assertEqual(next_state(None, "PENDING"), ("PENDING", "APPLY"))
        self.assertEqual(next_state("PENDING", "PAID"), ("PAID", "APPLY"))
        self.assertEqual(next_state("PAID", "PAID"), ("PAID", "IGNORE"))
        self.assertEqual(next_state("PAID", "PENDING"), ("PAID", "IGNORE"))
        self.assertEqual(next_state("PAID", "REFUNDED"), ("REFUNDED", "APPLY"))
        self.assertEqual(next_state("REFUNDED", "PAID"), ("REFUNDED", "IGNORE"))
        self.assertEqual(next_state("EXPIRED", "PAID"), ("EXPIRED", "HOLD"))
        self.assertEqual(next_state("PAID", "CHARGEBACK"), ("CHARGEBACK", "APPLY"))
        with self.assertRaises(PaymentRefused):
            next_state("PAID", "WHATEVER")


class DokuAdapter(unittest.TestCase):
    """Vectors are computed from the DOCUMENTED algorithm with a fake secret; they are NOT DOKU's own samples."""
    def setUp(self):
        self.d = doku.Doku("MCH-TEST-1", "fake-secret", notification_path="/payments/notifications")
        self.body = json.dumps({"order": {"invoice_number": "btl-sbx-" + "a" * 32, "amount": 99000}, "transaction": {"status": "SUCCESS", "original_request_id": "req-1", "date": "2026-11-15T10:00:00Z"}}).encode()

    def signed(self, body=None, **over):
        h = {"Client-Id": "MCH-TEST-1", "Request-Id": "r-123", "Request-Timestamp": "2026-11-15T10:00:00Z"}
        h.update(over)
        h["Signature"] = over.get("Signature") or doku.signature("fake-secret", h["Client-Id"], h["Request-Id"], h["Request-Timestamp"], "/payments/notifications", body or self.body)
        return h

    def test_string_to_sign_layout_and_prefix(self):
        sig = doku.signature("k", "C", "R", "2026-01-01T00:00:00Z", "/p", b"{}")
        self.assertTrue(sig.startswith("HMACSHA256="))
        self.assertEqual(doku.digest(b"{}"), "RBNvo1WzZ4oRRq0W9+hknpT7T8If536DEMBg9hyq/4o=")        # SHA-256("{}") base64
        self.assertNotEqual(sig, doku.signature("k", "C", "R", "2026-01-01T00:00:00Z", "/p", b"{ }"))
        get = doku.signature("k", "C", "R", "2026-01-01T00:00:00Z", "/orders/v1/status/X", None)   # GET: no Digest line
        self.assertNotEqual(get, sig)

    def test_valid_notification_becomes_a_verified_paid_event(self):
        event = self.d.verify_notification(self.signed(), self.body)
        self.assertEqual((event.kind, event.amount_idr, event.order_id, event.event_key), ("PAID", 99000, "btl-sbx-" + "a" * 32, "DOKU:r-123"))

    def test_tampering_wrong_client_missing_header_and_bad_status_are_refused(self):
        for case, (headers, body) in {
            "body changed": (self.signed(), self.body.replace(b"99000", b"1")),
            "wrong secret": (dict(self.signed(), Signature=doku.signature("other", "MCH-TEST-1", "r-123", "2026-11-15T10:00:00Z", "/payments/notifications", self.body)), self.body),
            "other client": (self.signed(**{"Client-Id": "MCH-OTHER"}), self.body),
            "no signature": ({k: v for k, v in self.signed().items() if k != "Signature"}, self.body),
            "bad timestamp": (self.signed(**{"Request-Timestamp": "yesterday"}), self.body),
        }.items():
            with self.assertRaises(PaymentRefused, msg=case):
                self.d.verify_notification(headers, body)
        bad = json.dumps({"order": {"invoice_number": "x", "amount": 5}, "transaction": {"status": "MAYBE"}}).encode()
        with self.assertRaises(PaymentRefused):
            self.d.verify_notification(self.signed(body=bad), bad)

    def test_checkout_request_is_signed_over_its_own_body(self):
        url, headers, body = self.d.build_checkout(PaymentRequest("btl-sbx-" + "b" * 32, 99000, 2592000, "Pro"), request_id="r-9", timestamp="2026-11-15T10:00:00Z")
        self.assertTrue(url.endswith("/checkout/v1/payment"))
        self.assertEqual(headers["Signature"], doku.signature("fake-secret", "MCH-TEST-1", "r-9", "2026-11-15T10:00:00Z", "/checkout/v1/payment", body))
        self.assertEqual(json.loads(body)["order"]["amount"], 99000)


if __name__ == "__main__":
    unittest.main()
