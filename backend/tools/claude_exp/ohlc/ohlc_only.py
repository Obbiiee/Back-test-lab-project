"""OHLC-only prehistory (no ticks): M1 bars -> the same nine-timeframe immutable objects as the tick path. DISPLAY AND INDICATOR CONTEXT ONLY.

Never execution authority: no quote count, no tick ordinals, evidence class OHLC_ONLY_DISPLAY_NOT_EXECUTION, price basis taken from the source (e.g. BID) and
never mixed silently with another basis. Exact integer arithmetic on the same 2*10^S grid as the tick path (value = decimal price * 2 * 10^S).
Higher timeframes are rolled up from M1 (open=first, high=max, low=min, close=last), UTC-midnight half-open buckets, like the tick engine.
Strict: ascending unique M1 timestamps, positive prices, high >= max(open, close), low <= min(open, close); anything else is refused, never repaired.
Formats: `histdata-ascii` (`YYYYMMDD HHMMSS;open;high;low;close;volume`, local time with a fixed offset, HistData default EST = -300 minutes) and
`csv` (header with time,open,high,low,close; time = epoch seconds, epoch milliseconds or ISO-8601 UTC).
  python -m tools.claude_exp.ohlc.ohlc_only --file X --format histdata-ascii --tz-offset-min -300 --instrument EURUSD --basis BID --scale 6 --store DIR [--source-label S]
"""
import argparse, csv, hashlib, io, json, sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.claude_exp.ohlc import engine                             # noqa: E402
from tools.claude_exp.ohlc.store import LocalObjectStore             # noqa: E402

NS = 10**9
EVIDENCE = "OHLC_ONLY_DISPLAY_NOT_EXECUTION"


class OhlcOnlyError(ValueError):
    pass


def _grid(text, scale):
    d = Decimal(text) * (2 * 10**scale)
    if d != d.to_integral_value():
        raise OhlcOnlyError(f"PRECISION_LOSS {text} at scale {scale}")
    v = int(d)
    if v <= 0:
        raise OhlcOnlyError("NON_POSITIVE_PRICE")
    return v


def read_m1(raw_text, fmt, scale, tz_offset_min=0):
    """-> dict of int64 arrays t (ns UTC), o, h, l, c on the 2*10^scale grid."""
    t, o, h, l, c = [], [], [], [], []
    if fmt == "histdata-ascii":
        for line in io.StringIO(raw_text):
            line = line.strip()
            if not line:
                continue
            stamp, op, hi, lo, cl = line.split(";")[:5]
            local = datetime.strptime(stamp, "%Y%m%d %H%M%S").replace(tzinfo=timezone.utc)
            t.append((int(local.timestamp()) - tz_offset_min * 60) * NS)
            o.append(_grid(op, scale)); h.append(_grid(hi, scale)); l.append(_grid(lo, scale)); c.append(_grid(cl, scale))
    elif fmt == "csv":
        for row in csv.DictReader(io.StringIO(raw_text)):
            raw_t = row["time"].strip()
            if raw_t.isdigit():
                n = int(raw_t); secs = n // 1000 if n > 10**11 else n
            else:
                secs = int(datetime.fromisoformat(raw_t.replace("Z", "+00:00")).astimezone(timezone.utc).timestamp())
            t.append((secs - tz_offset_min * 60) * NS)
            o.append(_grid(row["open"], scale)); h.append(_grid(row["high"], scale)); l.append(_grid(row["low"], scale)); c.append(_grid(row["close"], scale))
    else:
        raise OhlcOnlyError(f"UNKNOWN_FORMAT {fmt}")
    cols = {k: np.array(v, dtype=np.int64) for k, v in (("t", t), ("o", o), ("h", h), ("l", l), ("c", c))}
    if len(cols["t"]) == 0:
        raise OhlcOnlyError("EMPTY")
    if bool(np.any(cols["t"] % (60 * NS))):
        raise OhlcOnlyError("M1_TIMESTAMP_NOT_ON_MINUTE")
    if bool(np.any(np.diff(cols["t"]) <= 0)):
        raise OhlcOnlyError("TIMESTAMP_ORDER_OR_DUPLICATE")
    if bool(np.any(cols["h"] < np.maximum(cols["o"], cols["c"])) or np.any(cols["l"] > np.minimum(cols["o"], cols["c"]))):
        raise OhlcOnlyError("INCONSISTENT_OHLC")
    return cols


def roll_up(m1, tf_seconds):
    if tf_seconds == 60:
        return {k: m1[k].copy() for k in "tohlc"}
    width = tf_seconds * NS
    bucket = m1["t"] - (m1["t"] % width)
    starts = np.flatnonzero(np.r_[True, bucket[1:] != bucket[:-1]])
    ends = np.r_[starts[1:], len(bucket)]
    return dict(t=bucket[starts], o=m1["o"][starts], h=np.maximum.reduceat(m1["h"], starts), l=np.minimum.reduceat(m1["l"], starts), c=m1["c"][ends - 1])


def split_months(m1):
    months = np.array([np.datetime64(int(x), "ns").astype("datetime64[M]").astype(str) for x in m1["t"][::1]]) if len(m1["t"]) < 50_000 else None
    out = {}
    ym = (m1["t"].astype("datetime64[ns]").astype("datetime64[M]")).astype(str)
    for month in sorted(set(ym.tolist())):
        sel = ym == month
        out[month] = {k: m1[k][sel] for k in "tohlc"}
    return out


def publish_month(store, instrument, month, basis, m1_month, *, scale, source_sha256, source_label=None, rights="UNKNOWN"):
    prefix = f"ohlc/{engine.TRANSFORM_VERSION}/{instrument}/{source_sha256[:16]}/{basis}/{month}"
    objects = {}
    for name, sec in engine.TIMEFRAMES:
        r = roll_up(m1_month, sec)
        cols = dict(t=r["t"], o=r["o"], h=r["h"], l=r["l"], c=r["c"], n=np.zeros(len(r["t"]), dtype=np.int32),
                    first=np.zeros(len(r["t"]), dtype=np.int64), last=np.zeros(len(r["t"]), dtype=np.int64))
        raw = engine.to_parquet_bytes(cols)
        key = f"{prefix}/{name}.parquet"
        store.put_immutable(key, raw)
        objects[name] = dict(key=key, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(), count=int(len(r["t"])),
                             firstBarNs=int(r["t"][0]), lastBarNs=int(r["t"][-1]), quoteCount=0, tfSeconds=sec)
    manifest = dict(schemaVersion=1, artifact="BTL-CLAUDE-OHLC-MONTH-1", instrument=instrument, month=month, transformVersion=engine.TRANSFORM_VERSION,
                    rulesVersion=engine.RULES_VERSION, priceBasis=basis, priceScaleDenominator=2 * (10**scale),
                    priceNote="o/h/l/c are exact integers; price = value / priceScaleDenominator",
                    volume="NONE: OHLC-only source; no quote count, no tick ordinals",
                    source=dict(manifestHash=source_sha256, datasetId=f"ohlc-only:{instrument}:{basis}:{source_sha256[:16]}", datasetVersion=source_sha256, label=source_label),
                    rights=rights, evidence=EVIDENCE,
                    coverage=dict(m1Bars=int(len(m1_month["t"])), firstBarNs=int(m1_month["t"][0]), lastBarNs=int(m1_month["t"][-1])), objects=objects)
    store.put_immutable(f"{prefix}/manifest.json", json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode())
    return manifest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True); ap.add_argument("--format", required=True, choices=("histdata-ascii", "csv"))
    ap.add_argument("--tz-offset-min", type=int, default=0); ap.add_argument("--instrument", required=True); ap.add_argument("--basis", required=True, choices=("BID", "ASK", "MID"))
    ap.add_argument("--scale", type=int, required=True); ap.add_argument("--store", required=True); ap.add_argument("--source-label")
    a = ap.parse_args()
    raw = Path(a.file).read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    m1 = read_m1(raw.decode("utf-8-sig"), a.format, a.scale, a.tz_offset_min)
    store = LocalObjectStore(a.store)
    months = split_months(m1)
    for month, cols in months.items():
        publish_month(store, a.instrument, month, a.basis, cols, scale=a.scale, source_sha256=sha, source_label=a.source_label)
    print(json.dumps(dict(file=a.file, sha256=sha, m1Bars=int(len(m1["t"])), months=len(months), first=min(months), last=max(months), basis=a.basis, evidence=EVIDENCE)))


if __name__ == "__main__":
    main()
