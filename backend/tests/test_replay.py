import unittest
from datetime import datetime, timedelta, timezone

from engine.market_data import Candle
from engine.replay import ReplayEngine
from services.replay_service import NotFound, ReplayService

T0 = datetime(2026, 1, 5, 0, 0, tzinfo=timezone.utc)


def make_candles(n):
    return [Candle(T0 + timedelta(hours=i), 100 + i, 101 + i, 99 + i, 100.5 + i) for i in range(n)]


class ReplayEngineTests(unittest.TestCase):
    def test_starts_at_start_index_and_shows_only_history(self):
        e = ReplayEngine(make_candles(50), start_index=10)
        self.assertEqual(e.cursor, 10)
        self.assertEqual(len(e.visible_candles()), 11)

    def test_progression_one_candle_at_a_time(self):
        e = ReplayEngine(make_candles(5), start_index=0)
        seen = [e.next().time for _ in range(4)]
        self.assertEqual(seen, [T0 + timedelta(hours=i) for i in range(1, 5)])
        self.assertTrue(e.at_end)
        self.assertIsNone(e.next())  # di ujung, tidak error

    def test_no_look_ahead_at_every_step(self):
        candles = make_candles(60)
        e = ReplayEngine(candles, start_index=20)
        while True:
            visible = e.visible_candles()
            self.assertEqual(visible[-1].time, e.current_time)
            self.assertTrue(all(c.time <= e.current_time for c in visible))
            self.assertEqual(len(visible), e.cursor + 1)
            if e.next() is None:
                break

    def test_visible_candles_is_a_copy(self):
        e = ReplayEngine(make_candles(10), start_index=3)
        e.visible_candles().clear()
        self.assertEqual(len(e.visible_candles()), 4)

    def test_previous_only_moves_view_and_high_water_remembers_progress(self):
        e = ReplayEngine(make_candles(10), start_index=2)
        e.next(); e.next()
        self.assertEqual((e.cursor, e.high_water), (4, 4))
        e.previous()
        self.assertEqual((e.cursor, e.high_water), (3, 4))
        self.assertFalse(e.is_new_progress())
        e.next()
        self.assertFalse(e.is_new_progress())  # kembali ke candle yang sudah pernah dilihat
        e.next()
        self.assertTrue(e.is_new_progress())   # candle baru
        self.assertEqual(e.high_water, 5)

    def test_previous_at_start_returns_none(self):
        e = ReplayEngine(make_candles(5), start_index=0)
        self.assertIsNone(e.previous())

    def test_jump_forward_returns_all_revealed_candles(self):
        e = ReplayEngine(make_candles(20), start_index=2)
        revealed = e.jump_to(T0 + timedelta(hours=6, minutes=30))  # di antara candle 6 dan 7
        self.assertEqual(e.cursor, 6)
        self.assertEqual([c.time for c in revealed], [T0 + timedelta(hours=i) for i in range(3, 7)])
        self.assertEqual(e.high_water, 6)

    def test_jump_backward_hides_candles_and_reveals_nothing(self):
        e = ReplayEngine(make_candles(20), start_index=10)
        self.assertEqual(e.jump_to(T0 + timedelta(hours=4)), [])
        self.assertEqual(e.cursor, 4)
        self.assertEqual(e.high_water, 10)

    def test_jump_before_first_candle_fails(self):
        e = ReplayEngine(make_candles(5))
        with self.assertRaises(ValueError):
            e.jump_to(T0 - timedelta(hours=1))

    def test_jump_beyond_last_stops_at_last(self):
        e = ReplayEngine(make_candles(5))
        e.jump_to(T0 + timedelta(days=30))
        self.assertTrue(e.at_end)

    def test_from_time(self):
        e = ReplayEngine.from_time(make_candles(20), T0 + timedelta(hours=7, minutes=1))
        self.assertEqual(e.cursor, 8)
        with self.assertRaises(ValueError):
            ReplayEngine.from_time(make_candles(5), T0 + timedelta(days=9))

    def test_reset(self):
        e = ReplayEngine(make_candles(10), start_index=3)
        e.next(); e.next(); e.reset()
        self.assertEqual((e.cursor, e.high_water), (3, 3))

    def test_rejects_bad_input(self):
        with self.assertRaises(ValueError):
            ReplayEngine([])
        with self.assertRaises(ValueError):
            ReplayEngine(make_candles(3), start_index=3)
        c = make_candles(3)
        with self.assertRaises(ValueError):
            ReplayEngine([c[0], c[2], c[1]])


CSV = "timestamp,open,high,low,close,volume\n" + "\n".join(
    f"{(T0 + timedelta(hours=i)).strftime('%Y-%m-%d %H:%M:%S')},{100+i},{102+i},{99+i},{101+i},5" for i in range(300)
) + "\n"


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.svc = ReplayService()
        imported = self.svc.import_dataset(CSV, "XAUUSD", "1h", "UTC")
        self.assertTrue(imported["ok"])
        self.dataset_id = imported["dataset_id"]

    def test_state_never_contains_future_candles(self):
        state = self.svc.start(self.dataset_id, start_index=150)
        self.assertEqual(state["cursor"], 150)
        self.assertEqual(len(state["candles"]), 151)
        for _ in range(30):
            state = self.svc.next(state["session_id"])
            self.assertTrue(all(c["time"] <= state["current_time"] for c in state["candles"]))
            self.assertEqual(state["candles"][-1]["time"], state["current_time"])

    def test_default_start_keeps_history(self):
        state = self.svc.start(self.dataset_id)
        self.assertEqual(state["cursor"], 100)

    def test_start_by_time_and_jump(self):
        state = self.svc.start(self.dataset_id, start_time="2026-01-06T00:00:00")
        self.assertEqual(state["cursor"], 24)
        state = self.svc.jump(state["session_id"], "2026-01-07T12:00:00")
        self.assertEqual(state["cursor"], 60)
        self.assertEqual(state["revealed"], 36)

    def test_max_candles_limits_payload_but_not_cursor(self):
        state = self.svc.start(self.dataset_id, start_index=200, max_candles=50)
        self.assertEqual(len(state["candles"]), 50)
        self.assertEqual(state["cursor"], 200)

    def test_next_with_steps_stops_at_end(self):
        state = self.svc.start(self.dataset_id, start_index=295)
        state = self.svc.next(state["session_id"], steps=50)
        self.assertTrue(state["at_end"])
        self.assertEqual(state["revealed"], 4)

    def test_previous_and_reset(self):
        state = self.svc.start(self.dataset_id, start_index=10)
        sid = state["session_id"]
        self.svc.next(sid, steps=5)
        self.assertEqual(self.svc.previous(sid)["cursor"], 14)
        self.assertEqual(self.svc.reset(sid)["cursor"], 10)

    def test_unknown_ids(self):
        with self.assertRaises(NotFound):
            self.svc.state("nope")
        with self.assertRaises(NotFound):
            self.svc.start("nope")

    def test_bad_import_is_rejected_and_not_stored(self):
        result = self.svc.import_dataset("timestamp,open,high,low,close\n2026-01-05 00:00,1,0.5,2,1\n", "XAUUSD", "1h", "UTC")
        self.assertFalse(result["ok"])
        self.assertNotIn("dataset_id", result)


if __name__ == "__main__":
    unittest.main()
