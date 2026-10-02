"""Replay engine: memutar candle historis satu per satu tanpa membocorkan masa depan.

Konsep:
- cursor      : indeks candle "sekarang". Hanya candle 0..cursor yang boleh terlihat.
- high_water  : indeks terjauh yang PERNAH dicapai replay. Tombol Previous hanya
                menggeser tampilan mundur; kemajuan "baru" hanya terjadi saat cursor
                melewati high_water. Nanti engine order/posisi hanya boleh memproses
                candle baru (indeks > high_water), supaya SL/TP tidak dieksekusi dua kali.

Satu-satunya cara membaca candle dari luar adalah visible_candles(), current_candle,
dan hasil next()/jump_to(). Tidak ada method yang mengembalikan candle setelah cursor.
"""
from bisect import bisect_right
from datetime import datetime
from typing import List, Optional, Sequence

from ..market_data.models import Candle


class ReplayEngine:
    def __init__(self, candles: Sequence[Candle], start_index: int = 0):
        if not candles:
            raise ValueError("data candle kosong")
        for prev, cur in zip(candles, candles[1:]):
            if cur.time <= prev.time:
                raise ValueError("candle harus berurutan menurut waktu tanpa duplikat")
        if not 0 <= start_index < len(candles):
            raise ValueError(f"start_index di luar rentang (0..{len(candles) - 1})")

        self._candles = tuple(candles)  # privat; jangan diakses dari luar kelas ini
        self._times = [c.time for c in self._candles]
        self._start_index = start_index
        self._cursor = start_index
        self._high_water = start_index
        self._last_step_new = False

    @classmethod
    def from_time(cls, candles: Sequence[Candle], start_time: datetime) -> "ReplayEngine":
        """Mulai dari candle pertama yang waktunya >= start_time."""
        times = [c.time for c in candles]
        index = 0
        while index < len(times) and times[index] < start_time:
            index += 1
        if index >= len(times):
            raise ValueError("start_time berada setelah candle terakhir")
        return cls(candles, index)

    # ---- status ----
    @property
    def cursor(self) -> int:
        return self._cursor

    @property
    def total(self) -> int:
        return len(self._candles)

    @property
    def high_water(self) -> int:
        return self._high_water

    @property
    def at_end(self) -> bool:
        return self._cursor >= len(self._candles) - 1

    @property
    def current_candle(self) -> Candle:
        return self._candles[self._cursor]

    @property
    def current_time(self) -> datetime:
        return self._times[self._cursor]

    # ---- data yang boleh dilihat ----
    def visible_candles(self) -> List[Candle]:
        """Candle 0..cursor. Berupa list baru; mengubahnya tidak memengaruhi engine."""
        return list(self._candles[: self._cursor + 1])

    # ---- kontrol ----
    def next(self) -> Optional[Candle]:
        """Maju satu candle. Mengembalikan candle baru, atau None jika sudah di ujung."""
        if self.at_end:
            return None
        self._cursor += 1
        self._last_step_new = self._cursor > self._high_water
        self._high_water = max(self._high_water, self._cursor)
        return self._candles[self._cursor]

    def previous(self) -> Optional[Candle]:
        """Mundur satu candle (hanya tampilan). Mengembalikan candle sekarang, atau None jika di awal."""
        if self._cursor <= 0:
            return None
        self._cursor -= 1
        self._last_step_new = False
        return self._candles[self._cursor]

    def is_new_progress(self) -> bool:
        """True jika langkah terakhir membawa replay ke candle yang belum pernah dicapai
        (hanya candle seperti ini yang aman diproses untuk eksekusi order)."""
        return self._last_step_new

    def jump_to(self, target: datetime) -> List[Candle]:
        """Pindah ke candle terakhir yang waktunya <= target.

        Lompat maju mengembalikan semua candle yang baru terungkap (berurutan),
        supaya engine eksekusi nanti bisa memprosesnya satu per satu.
        Lompat mundur hanya menggeser tampilan dan mengembalikan list kosong.
        """
        index = bisect_right(self._times, target) - 1
        if index < 0:
            raise ValueError("waktu tujuan lebih awal dari candle pertama")
        if index > self._cursor:
            revealed = list(self._candles[self._cursor + 1: index + 1])
            self._cursor = index
            self._last_step_new = index > self._high_water
            self._high_water = max(self._high_water, index)
            return revealed
        self._cursor = index
        self._last_step_new = False
        return []

    def reset(self) -> None:
        """Kembali ke titik awal replay."""
        self._cursor = self._start_index
        self._high_water = self._start_index
        self._last_step_new = False
