"""Streaming nine-timeframe OHLC materialisation from the verified compact tick source (Claude candidate).

  ticks (compact parquet, row-group blocks) -> M1 -> M3,M5,M15,M30,H1,H2,H4,D1  (one pass, bounded memory)

Exactness: prices stay int64. A tick price is bid+ask for MID, 2*bid for BID, 2*ask for ASK, so every basis lives on one exact
grid of scale 2*S (S = source price scale). No float is used anywhere in the aggregation or in the stored columns.
Higher timeframes are rolled up from M1 bars; open/high/low/close are associative, and the oracle (which aggregates ticks directly)
proves the result is identical. Buckets are [start, start+tf) anchored at UTC midnight, so none straddles a month, which makes each
instrument-month an independent immutable publication.
"""
import hashlib
import io
import json
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from market_data.compact_tick import CompactTickReader

TRANSFORM_VERSION = "claude-ohlc-1"
RULES_VERSION = "UTC-MIDNIGHT-HALF-OPEN-1"
TIMEFRAMES = (("M1", 60), ("M3", 180), ("M5", 300), ("M15", 900), ("M30", 1800), ("H1", 3600), ("H2", 7200), ("H4", 14400), ("D1", 86400))
NS = 10**9
COLUMNS = ("t", "o", "h", "l", "c", "n", "first", "last")
SCHEMA = pa.schema([("t", pa.int64()), ("o", pa.int64()), ("h", pa.int64()), ("l", pa.int64()), ("c", pa.int64()),
                    ("n", pa.int32()), ("first", pa.int64()), ("last", pa.int64())])
ROW_GROUP = 4096


class CorruptSource(ValueError):
    pass


def _reduce(t, o, h, l, c, n, first, last, width):
    """Group consecutive rows by bucket start and reduce them. Rows must already be in time order."""
    b = t - (t % width)
    cut = np.flatnonzero(np.concatenate(([True], b[1:] != b[:-1])))
    end = np.append(cut[1:], len(b))
    return dict(t=b[cut], o=o[cut], h=np.maximum.reduceat(h, cut), l=np.minimum.reduceat(l, cut), c=c[end - 1],
                n=np.add.reduceat(n.astype(np.int64), cut), first=first[cut], last=last[end - 1])


class Aggregator:
    """Consumes rows (ticks viewed as one-tick bars, or finer bars) and emits finished bars; keeps one open bar as carry."""

    def __init__(self, tf_seconds):
        self.width = tf_seconds * NS
        self.carry = None
        self.out = []

    def feed(self, rows):
        if len(rows["t"]) == 0:
            return
        bars = _reduce(**rows, width=self.width)
        if self.carry is not None:
            if int(bars["t"][0]) == int(self.carry["t"][0]):          # the open bar continues into this block
                first = {k: v[:1] for k, v in bars.items()}
                merged = dict(t=self.carry["t"], o=self.carry["o"], h=np.maximum(self.carry["h"], first["h"]),
                              l=np.minimum(self.carry["l"], first["l"]), c=first["c"], n=self.carry["n"] + first["n"],
                              first=self.carry["first"], last=first["last"])
                bars = {k: np.concatenate((merged[k], v[1:])) for k, v in bars.items()}
            else:
                self.out.append(self.carry)
        self.carry = {k: v[-1:] for k, v in bars.items()}
        if len(bars["t"]) > 1:
            self.out.append({k: v[:-1] for k, v in bars.items()})

    def finish(self):
        if self.carry is not None:
            self.out.append(self.carry)
            self.carry = None
        if not self.out:
            return {k: np.empty(0, dtype=np.int64) for k in COLUMNS}
        return {k: np.concatenate([part[k] for part in self.out]) for k in COLUMNS}

    def drain(self):
        """Finished bars so far (without the open bar), releasing them from memory."""
        if not self.out:
            return None
        part = {k: np.concatenate([p[k] for p in self.out]) for k in COLUMNS}
        self.out = []
        return part


def tick_rows(block, basis):
    bid, ask = block["bid"].astype(np.int64), block["ask"].astype(np.int64)
    p = {"MID": bid + ask, "BID": bid * 2, "ASK": ask * 2}[basis]
    ts = block["ts_ns"].astype(np.int64)
    return dict(t=ts, o=p, h=p, l=p, c=p, n=np.ones(len(ts), dtype=np.int32), first=ts, last=ts)


def build_month(reader, month, basis="MID"):
    """Convenience: complete column sets for the nine timeframes of one UTC month."""
    y, m = int(month[:4]), int(month[5:])
    start = int(np.datetime64(f"{y:04d}-{m:02d}-01", "ns").astype(np.int64))
    ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
    end = int(np.datetime64(f"{ny:04d}-{nm:02d}-01", "ns").astype(np.int64))
    aggs = {name: Aggregator(sec) for name, sec in TIMEFRAMES}
    m1_parts = []
    previous, ticks, crossed, first_ts = None, 0, 0, None
    for block in reader.iter_blocks(start, end, atomic=False):
        ts = block["ts_ns"]
        if (previous is not None and int(ts[0]) < previous) or bool(np.any(np.diff(ts) < 0)):
            raise CorruptSource("TIMESTAMP_ORDER")
        if first_ts is None:
            first_ts = int(ts[0])
        previous = int(ts[-1])
        ticks += len(ts)
        crossed += int(np.count_nonzero(block["ask"] < block["bid"]))
        if bool(np.any(block["bid"] <= 0)) or bool(np.any(block["ask"] <= 0)):
            raise CorruptSource("NON_POSITIVE_PRICE")
        aggs["M1"].feed(tick_rows(block, basis))
        done = aggs["M1"].drain()
        if done is not None:
            m1_parts.append(done)
            for name, _ in TIMEFRAMES[1:]:
                aggs[name].feed(done)
    tail = aggs["M1"].finish()
    if len(tail["t"]):
        m1_parts.append(tail)
        for name, _ in TIMEFRAMES[1:]:
            aggs[name].feed(tail)
    result = {"M1": {k: np.concatenate([p[k] for p in m1_parts]) for k in COLUMNS} if m1_parts else {k: np.empty(0, dtype=np.int64) for k in COLUMNS}}
    for name, _ in TIMEFRAMES[1:]:
        result[name] = aggs[name].finish()
    return result, dict(ticks=ticks, crossed=crossed, firstTickNs=first_ts, lastTickNs=previous, monthStartNs=start, monthEndNs=end)


def to_parquet_bytes(cols):
    table = pa.table({k: pa.array(cols[k], type=SCHEMA.field(k).type) for k in COLUMNS}, schema=SCHEMA)
    sink = io.BytesIO()
    pq.write_table(table, sink, compression="zstd", compression_level=9, use_dictionary=False, row_group_size=ROW_GROUP,
                   write_statistics=True, version="2.6", data_page_version="2.0", store_schema=False)
    return sink.getvalue()


def from_parquet_bytes(raw):
    table = pq.read_table(io.BytesIO(raw))
    return {k: table.column(k).to_numpy() for k in COLUMNS}


def publish_month(store, reader, instrument, month, *, basis="MID", rights="UNKNOWN", source_label=None):
    """Build and publish one instrument-month (nine objects + manifest) to an object store. Idempotent and immutable:
    the key contains the source manifest hash and transform version, a re-run writes identical bytes or refuses."""
    cols, stats = build_month(reader, month, basis)
    scale = reader.scale
    src = reader.manifest["manifestHash"]
    prefix = f"ohlc/{TRANSFORM_VERSION}/{instrument}/{src[:16]}/{basis}/{month}"
    objects = {}
    for name, sec in TIMEFRAMES:
        c = cols[name]
        raw = to_parquet_bytes(c)
        key = f"{prefix}/{name}.parquet"
        store.put_immutable(key, raw)
        objects[name] = dict(key=key, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(), count=int(len(c["t"])),
                             firstBarNs=int(c["t"][0]) if len(c["t"]) else None, lastBarNs=int(c["t"][-1]) if len(c["t"]) else None,
                             quoteCount=int(c["n"].sum()), tfSeconds=sec)
    manifest = dict(schemaVersion=1, artifact="BTL-CLAUDE-OHLC-MONTH-1", instrument=instrument, month=month, transformVersion=TRANSFORM_VERSION,
                    rulesVersion=RULES_VERSION, priceBasis=basis, priceScaleDenominator=2 * (10 ** scale),
                    priceNote="o/h/l/c are exact integers; price = value / priceScaleDenominator",
                    volume="NONE: quoteCount is a count of quotes, not traded volume",
                    source=dict(manifestHash=src, datasetId=reader.parent["datasetId"], datasetVersion=reader.parent["datasetVersion"], label=source_label),
                    rights=rights, evidence="DERIVED_NON_AUTHORITATIVE",
                    coverage=dict(ticks=stats["ticks"], crossedQuotes=stats["crossed"], firstTickNs=stats["firstTickNs"], lastTickNs=stats["lastTickNs"],
                                  monthStartNs=stats["monthStartNs"], monthEndNs=stats["monthEndNs"]),
                    objects=objects)
    raw = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    store.put_immutable(f"{prefix}/manifest.json", raw)
    return manifest, f"{prefix}/manifest.json"
