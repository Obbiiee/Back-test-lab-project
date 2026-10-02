"""Membuat data contoh XAUUSD 1 jam (SIMULASI, bukan harga asli).
Jalankan: python generate_sample.py
Hasil: sample_XAUUSD_1h.csv (waktu UTC, tanpa candle Sabtu-Minggu)."""
import random
from datetime import datetime, timedelta

rng = random.Random(42)
t = datetime(2026, 1, 1, 0, 0, 0)
close = 3800.0
lines = ["timestamp,open,high,low,close,volume"]
count = 0
while count < 3000:
    if t.weekday() < 5:  # Senin-Jumat saja, supaya ada celah akhir pekan seperti pasar asli
        o = round(close, 2)
        c = round(o + rng.gauss(0, 4), 2)
        h = round(max(o, c) + rng.random() * 5 + 0.5, 2)
        l = round(min(o, c) - rng.random() * 5 - 0.5, 2)
        lines.append(f"{t:%Y-%m-%d %H:%M:%S},{o},{h},{l},{c},{rng.randint(50, 500)}")
        close = c
        count += 1
    t += timedelta(hours=1)

with open("sample_XAUUSD_1h.csv", "w", newline="") as f:
    f.write("\n".join(lines) + "\n")
print("dibuat:", count, "candle")
