import unittest
from unittest.mock import MagicMock

from contracts.primitives import ContractError
from execution.postgres import pack
from execution.session_storage_metrics import _closed_trade_event_count


class SessionStorageMetricsTests(unittest.TestCase):
    def test_counts_only_terminal_exit_fill_events_and_checks_each_payload_hash(self):
        values = [
            {"schemaVersion": 1, "artifact": "BTL-TICK-EXECUTION-EVENT-1",
             "kind": "ENTRY_FILL", "detail": {"remaining": "1"}},
            {"schemaVersion": 1, "artifact": "BTL-TICK-EXECUTION-EVENT-1",
             "kind": "EXIT_FILL", "detail": {"remaining": "0"}},
            {"schemaVersion": 1, "artifact": "BTL-TICK-EXECUTION-EVENT-1",
             "kind": "EXIT_FILL", "detail": {"remaining": "0.5"}},
        ]
        packed = [pack(value) for value in values]
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.fetchmany.side_effect = [
            [(raw, digest) for raw, digest in packed], [],
        ]
        db = MagicMock()
        db.cursor.return_value = cursor

        count, status = _closed_trade_event_count(
            db, "workspace:qa", "session:qa",
            {"rows": len(packed), "payloadBytes": sum(len(raw) for raw, _ in packed)},
        )

        self.assertEqual(count, 1)
        self.assertEqual(status, "CONTENT_HASHED_EVENT_SCAN_NOT_FINANCIAL_VERIFICATION")
        cursor.execute.assert_called_once()

    def test_event_scan_limits_return_explicit_unknown_without_opening_cursor(self):
        db = MagicMock()
        count, status = _closed_trade_event_count(
            db, "workspace:qa", "session:qa", {"rows": 4097, "payloadBytes": 1},
        )
        self.assertIsNone(count)
        self.assertEqual(status, "NOT_COMPUTED_EVENT_ROW_LIMIT")
        db.cursor.assert_not_called()

        count, status = _closed_trade_event_count(
            db, "workspace:qa", "session:qa", {"rows": 1, "payloadBytes": 16 * 1024 * 1024 + 1},
        )
        self.assertIsNone(count)
        self.assertEqual(status, "NOT_COMPUTED_EVENT_BYTE_LIMIT")
        db.cursor.assert_not_called()

    def test_single_oversized_event_returns_unknown_without_claiming_a_count(self):
        raw, digest = pack({"schemaVersion": 1, "artifact": "BTL-TICK-EXECUTION-EVENT-1",
                            "kind": "EXIT_FILL", "detail": {"remaining": "0",
                                                                  "padding": "x" * (64 * 1024)}})
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.fetchmany.return_value = [(raw, digest)]
        db = MagicMock()
        db.cursor.return_value = cursor
        count, status = _closed_trade_event_count(
            db, "workspace:qa", "session:qa", {"rows": 1, "payloadBytes": len(raw)},
        )
        self.assertIsNone(count)
        self.assertEqual(status, "NOT_COMPUTED_SINGLE_EVENT_BYTE_LIMIT")

    def test_event_payload_hash_mismatch_fails_closed(self):
        raw, _digest = pack({"schemaVersion": 1, "artifact": "BTL-TICK-EXECUTION-EVENT-1",
                             "kind": "EXIT_FILL", "detail": {"remaining": "0"}})
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.fetchmany.side_effect = [[(raw, "0" * 64)]]
        db = MagicMock()
        db.cursor.return_value = cursor
        with self.assertRaises(ContractError):
            _closed_trade_event_count(
                db, "workspace:qa", "session:qa", {"rows": 1, "payloadBytes": len(raw)},
            )


if __name__ == "__main__":
    unittest.main()
