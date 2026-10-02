"""Impor dan validasi CSV data historis.

Aturan utama: data yang rusak TIDAK diperbaiki diam-diam. Kalau ada satu saja
error, tidak ada candle yang dikembalikan dan semua masalah dilaporkan lengkap
dengan nomor barisnya. Gap (candle hilang) hanya peringatan, karena akhir pekan
dan hari libur memang wajar tidak punya candle.

Kolom wajib : timestamp, open, high, low, close
Kolom opsional: volume, bid, ask, spread
Zona waktu  : timestamp tanpa offset dianggap berada di zona waktu yang dipilih
              user, lalu dikonversi ke UTC. Timestamp dengan offset (contoh
              2026-01-01T00:00:00Z) dipakai apa adanya. Saran: pakai data UTC
              untuk menghindari kerancuan jam musim panas (DST).
"""
import csv
import io
import math
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone as dt_timezone
from typing import List, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .models import Candle, TIMEFRAME_MINUTES

REQUIRED_COLUMNS = ("timestamp", "open", "high", "low", "close")
OPTIONAL_COLUMNS = ("volume", "bid", "ask", "spread")
MAX_ISSUES_PER_SEVERITY = 100  # daftar masalah dipotong agar laporan tetap ringkas

_TIME_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M",
    "%Y.%m.%d %H:%M:%S",
    "%Y.%m.%d %H:%M",
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d %H:%M",
    "%Y-%m-%d",
    "%Y.%m.%d",
)


@dataclass
class Issue:
    severity: str  # "error" atau "warning"
    code: str
    message: str
    row: Optional[int] = None  # nomor baris di file (baris 1 = header)

    def to_dict(self) -> dict:
        return {"severity": self.severity, "code": self.code, "message": self.message, "row": self.row}


@dataclass
class ImportResult:
    symbol: str
    timeframe: str
    timezone: str
    total_rows: int = 0
    valid_rows: int = 0
    invalid_rows: int = 0
    duplicate_rows: int = 0
    out_of_order_rows: int = 0
    gap_count: int = 0
    first_time: Optional[datetime] = None
    last_time: Optional[datetime] = None
    candles: List[Candle] = field(default_factory=list)
    issues: List[Issue] = field(default_factory=list)

    @property
    def errors(self) -> List[Issue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> List[Issue]:
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0 and len(self.candles) > 0

    def summary(self) -> dict:
        return {
            "ok": self.ok,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "timezone": self.timezone,
            "total_rows": self.total_rows,
            "valid_rows": self.valid_rows,
            "invalid_rows": self.invalid_rows,
            "duplicate_rows": self.duplicate_rows,
            "out_of_order_rows": self.out_of_order_rows,
            "gap_count": self.gap_count,
            "first_time": self.first_time.isoformat() if self.first_time else None,
            "last_time": self.last_time.isoformat() if self.last_time else None,
            "issues": [i.to_dict() for i in self.issues],
        }


def parse_timestamp(raw: str, tz) -> datetime:
    """Ubah teks waktu menjadi datetime UTC. Melempar ValueError jika formatnya tidak dikenal."""
    raw = raw.strip()
    parsed = None
    for fmt in _TIME_FORMATS:
        try:
            parsed = datetime.strptime(raw, fmt)
            break
        except ValueError:
            continue
    if parsed is None:
        try:
            parsed = datetime.fromisoformat(raw)  # menangani offset seperti +07:00 atau Z
        except ValueError:
            raise ValueError(f"format waktu tidak dikenal: '{raw}'")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=tz)
    return parsed.astimezone(dt_timezone.utc)


def _detect_delimiter(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            counts = {d: line.count(d) for d in (",", ";", "\t")}
            best = max(counts, key=counts.get)
            return best if counts[best] > 0 else ","
    return ","


def _to_float(value: str, name: str) -> float:
    try:
        number = float(value.strip())
    except (ValueError, AttributeError):
        raise ValueError(f"kolom '{name}' bukan angka: '{value}'")
    if not math.isfinite(number):
        raise ValueError(f"kolom '{name}' bernilai tidak valid: '{value}'")
    return number


def _parse_row(row: dict, tz) -> Candle:
    """Ubah satu baris CSV menjadi Candle. Melempar ValueError dengan alasan yang jelas."""
    time = parse_timestamp(row.get("timestamp") or "", tz)
    o = _to_float(row.get("open") or "", "open")
    h = _to_float(row.get("high") or "", "high")
    l = _to_float(row.get("low") or "", "low")
    c = _to_float(row.get("close") or "", "close")

    if min(o, h, l, c) <= 0:
        raise ValueError("harga OHLC harus lebih besar dari 0")
    if l > h:
        raise ValueError(f"low ({l}) lebih besar dari high ({h})")
    if h < max(o, c):
        raise ValueError(f"high ({h}) lebih kecil dari open/close")
    if l > min(o, c):
        raise ValueError(f"low ({l}) lebih besar dari open/close")

    def optional(name: str) -> Optional[float]:
        raw = row.get(name)
        if raw is None or raw.strip() == "":
            return None
        return _to_float(raw, name)

    volume = optional("volume")
    if volume is not None and volume < 0:
        raise ValueError("volume tidak boleh negatif")
    bid, ask, spread = optional("bid"), optional("ask"), optional("spread")
    if bid is not None and ask is not None and ask < bid:
        raise ValueError(f"ask ({ask}) lebih kecil dari bid ({bid})")
    if spread is not None and spread < 0:
        raise ValueError("spread tidak boleh negatif")

    return Candle(time, o, h, l, c, volume or 0.0, bid, ask, spread)


def _cap(issues: List[Issue]) -> List[Issue]:
    """Batasi jumlah masalah yang ditampilkan per jenis; jumlah total tetap dicatat di ringkasan."""
    result: List[Issue] = []
    for severity in ("error", "warning"):
        group = [i for i in issues if i.severity == severity]
        result.extend(group[:MAX_ISSUES_PER_SEVERITY])
        extra = len(group) - MAX_ISSUES_PER_SEVERITY
        if extra > 0:
            result.append(Issue(severity, "truncated", f"...dan {extra} masalah {severity} lainnya tidak ditampilkan"))
    return result


def import_csv(text: str, symbol: str, timeframe: str, timezone: str = "UTC") -> ImportResult:
    symbol = (symbol or "").strip().upper()
    timeframe = (timeframe or "").strip().lower()
    result = ImportResult(symbol=symbol, timeframe=timeframe, timezone=timezone)
    issues: List[Issue] = []

    # --- 1. Validasi parameter ---
    if not symbol or not all(ch.isalnum() or ch in "._-/" for ch in symbol):
        issues.append(Issue("error", "bad_symbol", "symbol kosong atau berisi karakter yang tidak diizinkan"))
    if timeframe not in TIMEFRAME_MINUTES:
        issues.append(Issue("error", "bad_timeframe",
                            f"timeframe '{timeframe}' tidak didukung. Pilihan: {', '.join(TIMEFRAME_MINUTES)}"))
    tz = None
    try:
        tz = ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        issues.append(Issue("error", "bad_timezone",
                            f"zona waktu '{timezone}' tidak dikenal (contoh: UTC, Asia/Jakarta, America/New_York)"))
    if not (text or "").strip():
        issues.append(Issue("error", "empty_file", "file kosong"))
    if issues:
        result.issues = issues
        return result

    text = text.lstrip("\ufeff")

    # --- 2. Header ---
    reader = csv.DictReader(io.StringIO(text), delimiter=_detect_delimiter(text))
    reader.fieldnames = [(name or "").strip().lower() for name in (reader.fieldnames or [])]
    missing = [c for c in REQUIRED_COLUMNS if c not in reader.fieldnames]
    if missing:
        result.issues = [Issue("error", "missing_columns",
                               f"kolom wajib tidak ditemukan: {', '.join(missing)}. "
                               f"Kolom yang terbaca: {', '.join(reader.fieldnames)}", row=1)]
        return result

    # --- 3. Baca dan validasi tiap baris ---
    parsed: List[tuple] = []  # (nomor_baris, Candle)
    for row in reader:
        if all((v or "").strip() == "" for v in row.values() if not isinstance(v, list)):
            continue  # baris kosong diabaikan
        result.total_rows += 1
        line = reader.line_num
        try:
            parsed.append((line, _parse_row(row, tz)))
        except ValueError as exc:
            result.invalid_rows += 1
            issues.append(Issue("error", "invalid_row", str(exc), row=line))

    # --- 4. Duplikat dan urutan waktu (tanpa mengubah data) ---
    seen = set()
    running_max = None
    accepted: List[Candle] = []
    for line, candle in parsed:
        if candle.time in seen:
            result.duplicate_rows += 1
            issues.append(Issue("error", "duplicate_timestamp",
                                f"timestamp duplikat: {candle.time.isoformat()}", row=line))
            continue
        seen.add(candle.time)
        if running_max is not None and candle.time < running_max:
            result.out_of_order_rows += 1
            issues.append(Issue("error", "not_chronological",
                                f"urutan waktu mundur: {candle.time.isoformat()} lebih awal dari "
                                f"{running_max.isoformat()}", row=line))
            continue
        running_max = candle.time
        accepted.append(candle)

    result.valid_rows = len(parsed)
    if parsed:
        times = [c.time for _, c in parsed]
        result.first_time, result.last_time = min(times), max(times)

    # --- 5. Gap dan kecocokan timeframe (hanya peringatan) ---
    expected = TIMEFRAME_MINUTES[timeframe] * 60
    deltas = [(b.time - a.time).total_seconds() for a, b in zip(accepted, accepted[1:])]
    if len(deltas) >= 2:
        typical = statistics.median(deltas)
        if typical != expected:
            issues.append(Issue("warning", "timeframe_mismatch",
                                f"jarak antar candle yang umum ({typical / 60:g} menit) tidak sama dengan "
                                f"timeframe {timeframe} ({expected / 60:g} menit). Periksa pilihan timeframe."))
    for a, b, delta in zip(accepted, accepted[1:], deltas):
        if delta > expected:
            result.gap_count += 1
            missing_candles = int(delta // expected) - 1
            issues.append(Issue("warning", "gap",
                                f"celah data: {a.time.isoformat()} -> {b.time.isoformat()} "
                                f"(sekitar {missing_candles} candle hilang)"))

    # --- 6. Hasil akhir: ada error = tidak ada candle yang diterima ---
    result.issues = _cap(issues)
    if not any(i.severity == "error" for i in issues) and not accepted:
        result.issues.append(Issue("error", "no_data", "tidak ada baris data yang valid"))
    if not any(i.severity == "error" for i in result.issues):
        result.candles = accepted
    return result
