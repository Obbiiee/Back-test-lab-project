"""Lapisan layanan: menyimpan dataset dan sesi replay di memori.

Ini batas keamanan terhadap look-ahead: semua respons untuk frontend dibangun
dari ReplayEngine.visible_candles(), sehingga candle masa depan tidak pernah
keluar dari backend. (Penyimpanan permanen di PostgreSQL menyusul di Fase 6.)
"""
import uuid
from datetime import timezone as dt_timezone
from typing import Dict, Optional

from engine.market_data import import_csv, parse_timestamp
from engine.market_data.importer import ImportResult
from engine.replay import ReplayEngine
from engine.trading import TradingConfig, TradingEngine

DEFAULT_START_INDEX = 100  # sisakan riwayat 100 candle sebelum titik mulai (jika data cukup)
DEFAULT_MAX_CANDLES = 5000


class NotFound(Exception):
    pass


class ReplayService:
    def __init__(self):
        self._datasets: Dict[str, ImportResult] = {}
        self._sessions: Dict[str, dict] = {}

    # ---- data ----
    def validate(self, csv_text: str, symbol: str, timeframe: str, timezone: str) -> dict:
        return import_csv(csv_text, symbol, timeframe, timezone).summary()

    def import_dataset(self, csv_text: str, symbol: str, timeframe: str, timezone: str) -> dict:
        result = import_csv(csv_text, symbol, timeframe, timezone)
        report = result.summary()
        if not result.ok:
            return {"ok": False, "report": report}
        dataset_id = uuid.uuid4().hex[:12]
        self._datasets[dataset_id] = result
        return {"ok": True, "dataset_id": dataset_id, "report": report}

    # ---- sesi replay ----
    def start(self, dataset_id: str, start_index: Optional[int] = None,
              start_time: Optional[str] = None, trading_config: Optional[TradingConfig] = None,
              max_candles: int = DEFAULT_MAX_CANDLES) -> dict:
        dataset = self._datasets.get(dataset_id)
        if dataset is None:
            raise NotFound(f"dataset '{dataset_id}' tidak ditemukan")
        if start_time:
            engine = ReplayEngine.from_time(dataset.candles, parse_timestamp(start_time, dt_timezone.utc))
        else:
            if start_index is None:
                start_index = min(DEFAULT_START_INDEX, len(dataset.candles) - 1)
            engine = ReplayEngine(dataset.candles, start_index)
        session_id = uuid.uuid4().hex[:12]
        config = trading_config or TradingConfig()
        self._sessions[session_id] = {
            "engine": engine,
            "trading": TradingEngine(config),
            "trading_config": config,
            "symbol": dataset.symbol,
            "timeframe": dataset.timeframe,
        }
        return self.state(session_id, max_candles)

    def _get(self, session_id: str) -> dict:
        session = self._sessions.get(session_id)
        if session is None:
            raise NotFound(f"sesi replay '{session_id}' tidak ditemukan")
        return session

    def state(self, session_id: str, max_candles: int = DEFAULT_MAX_CANDLES, revealed: int = 0) -> dict:
        session = self._get(session_id)
        engine: ReplayEngine = session["engine"]
        visible = engine.visible_candles()
        shown = visible[-max_candles:] if max_candles > 0 else visible
        result = {
            "session_id": session_id,
            "symbol": session["symbol"],
            "timeframe": session["timeframe"],
            "cursor": engine.cursor,
            "total": engine.total,
            "at_end": engine.at_end,
            "current_time": int(engine.current_time.timestamp()),
            "revealed": revealed,
            "candles": [c.to_dict() for c in shown],
        }
        result.update(session["trading"].state())
        return result

    def next(self, session_id: str, steps: int = 1, max_candles: int = DEFAULT_MAX_CANDLES) -> dict:
        session = self._get(session_id)
        engine: ReplayEngine = session["engine"]
        revealed = 0
        for _ in range(max(1, steps)):
            candle = engine.next()
            if candle is None:
                break
            revealed += 1
            if engine.is_new_progress():
                session["trading"].process_candle(candle)
        return self.state(session_id, max_candles, revealed)

    def previous(self, session_id: str, max_candles: int = DEFAULT_MAX_CANDLES) -> dict:
        self._get(session_id)["engine"].previous()
        return self.state(session_id, max_candles)

    def jump(self, session_id: str, time: str, max_candles: int = DEFAULT_MAX_CANDLES) -> dict:
        engine: ReplayEngine = self._get(session_id)["engine"]
        revealed = engine.jump_to(parse_timestamp(time, dt_timezone.utc))
        session = self._get(session_id)
        for candle in revealed:
            session["trading"].process_candle(candle)
        return self.state(session_id, max_candles, len(revealed))

    def reset(self, session_id: str, max_candles: int = DEFAULT_MAX_CANDLES) -> dict:
        session = self._get(session_id)
        session["engine"].reset()
        session["trading"] = TradingEngine(session["trading_config"])
        return self.state(session_id, max_candles)

    def market_order(
        self,
        session_id: str,
        side: str,
        stop_distance: float,
        take_profit_distance: Optional[float] = None,
        risk_percent: float = 1.0,
    ) -> dict:
        session = self._get(session_id)
        engine: ReplayEngine = session["engine"]
        if engine.cursor < engine.high_water:
            raise ValueError("sedang melihat candle lama; maju kembali ke posisi replay terakhir untuk trading")
        session["trading"].open_market(
            side,
            engine.current_candle,
            stop_distance,
            take_profit_distance,
            risk_percent,
        )
        return self.state(session_id)

    def close_position(self, session_id: str) -> dict:
        session = self._get(session_id)
        engine: ReplayEngine = session["engine"]
        if engine.cursor < engine.high_water:
            raise ValueError("sedang melihat candle lama; maju kembali ke posisi replay terakhir untuk trading")
        session["trading"].close_market(engine.current_candle, "MANUAL")
        return self.state(session_id)

    def pending_order(
        self,
        session_id: str,
        order_type: str,
        entry_price: float,
        stop_distance: float,
        take_profit_distance: Optional[float] = None,
        risk_percent: float = 1.0,
    ) -> dict:
        session = self._get(session_id)
        engine: ReplayEngine = session["engine"]
        if engine.cursor < engine.high_water:
            raise ValueError("sedang melihat candle lama; maju kembali ke posisi replay terakhir untuk trading")
        session["trading"].place_pending(
            order_type,
            engine.current_candle,
            entry_price,
            stop_distance,
            take_profit_distance,
            risk_percent,
        )
        return self.state(session_id)

    def cancel_pending_order(self, session_id: str) -> dict:
        session = self._get(session_id)
        session["trading"].cancel_pending()
        return self.state(session_id)
