import asyncio
import io
import unittest
from datetime import datetime, timedelta, timezone

from starlette.datastructures import UploadFile

from api.main import (
    MarketOrderRequest,
    PendingOrderRequest,
    StartRequest,
    import_dataset,
    replay_close_position,
    replay_market_order,
    replay_next,
    replay_pending_order,
    replay_cancel_pending,
    start_replay,
)
from api.main import NextRequest


CSV = "timestamp,open,high,low,close\n" + "\n".join(
    f"{(datetime(2026, 1, 5, tzinfo=timezone.utc) + timedelta(hours=i)):%Y-%m-%d %H:%M:%S},{100+i},{102+i},{99+i},{100.5+i}"
    for i in range(120)
) + "\n"


class ApiTradingRouteTests(unittest.TestCase):
    def test_import_order_close_and_replay_are_connected(self):
        upload = UploadFile(file=io.BytesIO(CSV.encode("utf-8")), filename="prices.csv")
        imported = asyncio.run(import_dataset(upload, "XAUUSD", "1h", "UTC"))
        self.assertTrue(imported["ok"])

        state = start_replay(StartRequest(
            dataset_id=imported["dataset_id"],
            initial_balance=5_000,
            contract_size=100,
            spread=0.4,
            slippage=0.1,
            commission_per_lot=2,
        ))
        self.assertEqual(state["balance"], 5_000)
        self.assertEqual(state["config"]["spread"], 0.4)

        session_id = state["session_id"]
        opened = replay_market_order(session_id, MarketOrderRequest(
            side="BUY", stop_distance=5, take_profit_distance=10, risk_percent=1,
        ))
        self.assertEqual(opened["position"]["side"], "BUY")
        advanced = replay_next(session_id, NextRequest(steps=1))
        self.assertEqual(advanced["cursor"], state["cursor"] + 1)
        closed = replay_close_position(session_id)
        self.assertEqual(closed["trades"][-1]["reason"], "MANUAL")
        self.assertIsNone(closed["position"])

        pending = replay_pending_order(session_id, PendingOrderRequest(
            order_type="BUY_STOP",
            entry_price=advanced["candles"][-1]["close"] + 1,
            stop_distance=5,
            take_profit_distance=10,
            risk_percent=1,
        ))
        self.assertEqual(pending["pending_order"]["order_type"], "BUY_STOP")
        cancelled = replay_cancel_pending(session_id)
        self.assertIsNone(cancelled["pending_order"])


if __name__ == "__main__":
    unittest.main()
