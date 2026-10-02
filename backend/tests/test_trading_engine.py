import unittest
from datetime import datetime, timedelta, timezone

from engine.market_data import Candle
from engine.trading import TradingConfig, TradingEngine
from services.replay_service import ReplayService

T0 = datetime(2026, 1, 5, tzinfo=timezone.utc)


def candle(index=0, open_=100, high=101, low=99, close=100):
    return Candle(T0 + timedelta(hours=index), open_, high, low, close)


class TradingEngineTests(unittest.TestCase):
    def test_buy_position_size_and_stop_loss_include_execution_costs(self):
        engine = TradingEngine(TradingConfig(
            initial_balance=10_000,
            contract_size=100,
            spread=2,
            slippage=0.5,
            commission_per_lot=3,
        ))
        position = engine.open_market("BUY", candle(), stop_distance=10, risk_percent=1)

        self.assertEqual(position.entry_price, 101.5)
        self.assertEqual(position.stop_loss, 91.5)
        self.assertEqual(position.lots, 0.086)
        self.assertLessEqual(position.risk_amount, 100)

        trade = engine.process_candle(candle(1, open_=100, high=102, low=91, close=95))
        self.assertEqual(trade.reason, "SL")
        self.assertAlmostEqual(trade.pnl, -position.risk_amount)
        self.assertAlmostEqual(engine.balance, 10_000 - position.risk_amount)

    def test_sell_target_closes_with_expected_r_multiple(self):
        engine = TradingEngine()
        position = engine.open_market("SELL", candle(), 10, 20, 1)
        trade = engine.process_candle(candle(1, open_=100, high=101, low=79, close=85))

        self.assertEqual(position.take_profit, position.entry_price - 20)
        self.assertEqual(trade.reason, "TP")
        self.assertAlmostEqual(trade.r_multiple, 2)

    def test_stop_wins_if_stop_and_target_are_hit_in_same_candle(self):
        engine = TradingEngine()
        engine.open_market("BUY", candle(), 5, 5, 1)
        trade = engine.process_candle(candle(1, open_=100, high=110, low=90, close=101))

        self.assertEqual(trade.reason, "SL")

    def test_gap_through_stop_fills_at_worse_open(self):
        engine = TradingEngine()
        engine.open_market("BUY", candle(), 5, 20, 1)
        trade = engine.process_candle(candle(1, open_=90, high=95, low=88, close=92))

        self.assertEqual(trade.reason, "SL")
        self.assertEqual(trade.exit_price, 90)
        self.assertLess(trade.pnl, -trade.risk_amount)

    def test_pending_orders_wait_for_a_later_candle_then_fill(self):
        cases = (
            ("BUY_LIMIT", 95, candle(1, open_=96, high=98, low=94, close=95)),
            ("SELL_LIMIT", 105, candle(1, open_=104, high=106, low=102, close=105)),
            ("BUY_STOP", 105, candle(1, open_=106, high=110, low=104, close=108)),
            ("SELL_STOP", 95, candle(1, open_=94, high=96, low=90, close=92)),
        )
        for order_type, trigger, next_bar in cases:
            with self.subTest(order_type=order_type):
                engine = TradingEngine()
                engine.place_pending(order_type, candle(), trigger, 5, 10, 1)
                self.assertIsNone(engine.position)
                self.assertIsNotNone(engine.state()["pending_order"])
                engine.process_candle(next_bar)
                self.assertIsNone(engine.state()["pending_order"])
                self.assertIsNotNone(engine.position)
                if order_type == "BUY_STOP":
                    self.assertEqual(engine.position.entry_price, 106)
                if order_type == "SELL_STOP":
                    self.assertEqual(engine.position.entry_price, 94)

    def test_pending_entry_and_sl_tp_in_one_bar_use_conservative_stop_first(self):
        engine = TradingEngine()
        engine.place_pending("BUY_LIMIT", candle(), 95, 2, 2, 1)
        trade = engine.process_candle(candle(1, open_=100, high=99, low=90, close=95))

        self.assertIsNone(engine.pending_order)
        self.assertEqual(trade.reason, "SL")

    def test_cancel_pending_and_reject_wrong_side_of_market(self):
        engine = TradingEngine()
        with self.assertRaises(ValueError):
            engine.place_pending("BUY_LIMIT", candle(), 101, 2, 4, 1)
        engine.place_pending("SELL_STOP", candle(), 99, 2, 4, 1)
        engine.cancel_pending()
        self.assertIsNone(engine.pending_order)

    def test_manual_close_and_no_duplicate_processing(self):
        engine = TradingEngine()
        engine.open_market("BUY", candle(), 10, 20, 1)
        self.assertIsNone(engine.process_candle(candle(1, low=99, high=102, close=101)))
        self.assertIsNone(engine.process_candle(candle(1, low=99, high=102, close=101)))
        trade = engine.close_market(candle(1, low=99, high=102, close=101))

        self.assertEqual(trade.reason, "MANUAL")
        self.assertEqual(len(engine.trades), 1)
        self.assertIsNone(engine.position)

    def test_rejects_invalid_orders_and_config(self):
        with self.assertRaises(ValueError):
            TradingEngine(TradingConfig(spread=-1))
        engine = TradingEngine()
        for side, distance, risk in (("HOLD", 1, 1), ("BUY", 0, 1), ("BUY", 1, 101)):
            with self.assertRaises(ValueError):
                engine.open_market(side, candle(), distance, risk_percent=risk)


CSV = "timestamp,open,high,low,close\n" + "\n".join(
    f"{(T0 + timedelta(hours=i)).strftime('%Y-%m-%d %H:%M:%S')},{100+i},{102+i},{99+i},{100.5+i}"
    for i in range(120)
) + "\n"


class TradingServiceTests(unittest.TestCase):
    def setUp(self):
        self.service = ReplayService()
        imported = self.service.import_dataset(CSV, "XAUUSD", "1h", "UTC")
        self.session = self.service.start(imported["dataset_id"])
        self.session_id = self.session["session_id"]

    def test_market_order_and_replay_process_stop_or_target(self):
        state = self.service.market_order(self.session_id, "BUY", 10, 1, 1)
        self.assertIsNotNone(state["position"])
        state = self.service.next(self.session_id)

        self.assertIsNone(state["position"])
        self.assertEqual(state["trades"][-1]["reason"], "TP")
        self.assertGreater(state["balance"], 10_000)

    def test_replay_history_does_not_process_a_candle_twice(self):
        self.service.market_order(self.session_id, "BUY", 1_000, 2_000, 1)
        state = self.service.next(self.session_id, steps=3)
        self.assertIsNotNone(state["position"])
        state = self.service.previous(self.session_id)
        state = self.service.next(self.session_id, steps=2)

        self.assertIsNotNone(state["position"])
        self.assertEqual(state["trades"], [])

    def test_cannot_trade_while_reviewing_older_candles(self):
        self.service.next(self.session_id)
        self.service.previous(self.session_id)
        with self.assertRaises(ValueError):
            self.service.market_order(self.session_id, "BUY", 10, 20, 1)

    def test_reset_clears_positions_and_restores_balance(self):
        self.service.market_order(self.session_id, "BUY", 1_000, 2_000, 1)
        state = self.service.reset(self.session_id)

        self.assertEqual(state["balance"], 10_000)
        self.assertIsNone(state["position"])
        self.assertEqual(state["trades"], [])

    def test_pending_order_only_activates_on_replay_progress(self):
        state = self.service.pending_order(self.session_id, "BUY_STOP", 201, 5, 10, 1)
        self.assertIsNone(state["position"])
        self.assertEqual(state["pending_order"]["order_type"], "BUY_STOP")
        state = self.service.next(self.session_id)

        self.assertIsNone(state["pending_order"])
        self.assertIsNotNone(state["position"])

    def test_cancel_pending_order(self):
        self.service.pending_order(self.session_id, "BUY_STOP", 201, 5, 10, 1)
        state = self.service.cancel_pending_order(self.session_id)
        self.assertIsNone(state["pending_order"])


if __name__ == "__main__":
    unittest.main()
