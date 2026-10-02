"""Model data pasar yang sudah dinormalisasi.

Semua waktu disimpan dalam UTC (timezone-aware). Konversi dari zona waktu
file CSV dilakukan sekali saat impor, di importer.py.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

# Durasi satu candle per timeframe, dalam menit.
TIMEFRAME_MINUTES = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "4h": 240,
    "1d": 1440,
}


@dataclass(frozen=True)
class Candle:
    """Satu candle OHLC. frozen=True: tidak bisa diubah setelah dibuat."""

    time: datetime  # UTC, timezone-aware
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    bid: Optional[float] = None
    ask: Optional[float] = None
    spread: Optional[float] = None

    def to_dict(self) -> dict:
        data = {
            "time": int(self.time.timestamp()),  # detik UTC, format yang dipakai library chart
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
        }
        if self.bid is not None:
            data["bid"] = self.bid
        if self.ask is not None:
            data["ask"] = self.ask
        if self.spread is not None:
            data["spread"] = self.spread
        return data
