"""Staged benchmark of the Claude OHLC candidate. Each stage is measured separately; nothing is averaged across stages.

  python -m tools.claude_exp.ohlc.bench --src <compact tick dir> [--oracle-upto 1000000] [--repeats 3] [--out result.json]

Stage A  materialisation  G0..G4 (tick prefixes of the pinned month, then the whole month): wall, CPU, peak RSS, ticks/s, output bytes, objects, PUTs
Stage B  equality         engine == independent oracle on the same prefixes (up to --oracle-upto ticks; the oracle is naive and slow)
Stage C  serving          cold and warm cache, HTTP over loopback: payload bytes, p50/p95/p99, store GET/bytes, cache hits/misses
Hardware and versions are printed with the result. Offline materialisation cost is reported; it is not hidden.
"""
import argparse
import json
import os
import platform
import sys
import tempfile
import threading
import time
import urllib.request
from fractions import Fraction
from http.server import ThreadingHTTPServer
from pathlib import Path

import numpy as np
import psutil

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from market_data.compact_tick import CompactTickReader                    # noqa: E402
from tools.claude_exp.ohlc import engine, oracle, service as svc          # noqa: E402
from tools.claude_exp.ohlc.store import LocalObjectStore                   # noqa: E402

GATES = [("G0", 2048), ("G1", 65536), ("G2", 262144), ("G3", 1_000_000), ("G4", None)]


class Prefix:
    """Reader limited to the first N ticks (a pinned prefix of the same source)."""

    def __init__(self, reader, n):
        self.reader, self.n, self.scale = reader, n, reader.scale
        self.manifest, self.parent = reader.manifest, reader.parent

    def iter_blocks(self, start, end, atomic=True):
        left = self.n
        for block in self.reader.iter_blocks(start, end, atomic=atomic):
            if left <= 0:
                return
            if len(block["ts_ns"]) > left:
                block = {k: v[:left] for k, v in block.items()}
            left -= len(block["ts_ns"])
            yield block


def rss_peak(proc, samples):
    while samples["run"]:
        samples["peak"] = max(samples["peak"], proc.memory_info().rss)
        time.sleep(0.01)


def measure(fn):
    proc = psutil.Process()
    samples = dict(run=True, peak=proc.memory_info().rss)
    base = samples["peak"]
    th = threading.Thread(target=rss_peak, args=(proc, samples), daemon=True)
    th.start()
    io0, c0, w0 = proc.io_counters(), time.process_time(), time.perf_counter()
    result = fn()
    wall, cpu, io1 = time.perf_counter() - w0, time.process_time() - c0, proc.io_counters()
    samples["run"] = False
    th.join()
    return result, dict(wall=wall, cpu=cpu, peakRssMB=round(samples["peak"] / 2**20, 1), rssBaseMB=round(base / 2**20, 1),
                        readMB=round((io1.read_bytes - io0.read_bytes) / 2**20, 2), writeMB=round((io1.write_bytes - io0.write_bytes) / 2**20, 2))


def month_of(reader):
    return reader.manifest["files"][0]["month"]


def stage_a(reader, repeats):
    rows = []
    month = month_of(reader)
    total = reader.manifest["eventCount"]
    for gate, n in GATES:
        n = n or total
        n = min(n, total)
        runs = []
        for r in range(repeats):
            store = LocalObjectStore(tempfile.mkdtemp(prefix="bench-store-"))
            src = Prefix(reader, n)
            manifest_holder = {}

            def go():
                manifest_holder["m"], _ = engine.publish_month(store, src, "BENCH", month, rights="UNKNOWN")
            _, m = measure(go)
            m["ticksPerSec"] = round(n / m["wall"])
            m["counters"] = store.counters.snapshot()
            runs.append(m)
            mf = manifest_holder["m"]
        out_bytes = {tf: o["bytes"] for tf, o in mf["objects"].items()}
        counts = {tf: o["count"] for tf, o in mf["objects"].items()}
        med = lambda k: sorted(x[k] for x in runs)[len(runs) // 2]
        rows.append(dict(gate=gate, ticks=n, repeats=repeats, wallMedian=round(med("wall"), 3), wallRange=[round(min(x["wall"] for x in runs), 3), round(max(x["wall"] for x in runs), 3)],
                         cpuMedian=round(med("cpu"), 3), peakRssMB=med("peakRssMB"), rssBaseMB=runs[0]["rssBaseMB"], ticksPerSecMedian=med("ticksPerSec"),
                         readMB=med("readMB"), writeMB=med("writeMB"), objects=len(mf["objects"]) + 1, puts=runs[0]["counters"]["put"],
                         outputBytes=out_bytes, outputBytesTotal=sum(out_bytes.values()), barCounts=counts))
        print(json.dumps(rows[-1]), flush=True)
    return rows


def stage_b(reader, upto):
    out, month = [], month_of(reader)
    for gate, n in GATES:
        n = n or reader.manifest["eventCount"]
        if n > upto:
            out.append(dict(gate=gate, ticks=n, equality="NOT_RUN (oracle is naive; above --oracle-upto)"))
            continue
        src = Prefix(reader, n)
        ticks = []
        den = 10 ** reader.scale
        for block in src.iter_blocks(0, 2**62, atomic=False):
            for t, b, a in zip(block["ts_ns"].tolist(), block["bid"].tolist(), block["ask"].tolist()):
                ticks.append((t, str(Fraction(b, den)), str(Fraction(a, den))))
        t0 = time.perf_counter()
        expect = oracle.all_timeframes([(t, f"{Fraction(b)}", f"{Fraction(a)}") for t, b, a in ticks])
        t_oracle = time.perf_counter() - t0
        cols, _ = engine.build_month(src, month, "MID")
        d2 = 2 * den
        same = True
        for name, _ in engine.TIMEFRAMES:
            c, e = cols[name], expect[name]
            if len(e) != len(c["t"]):
                same = False
                break
            for i, bar in enumerate(e):
                if (bar["t"], bar["n"], bar["first"], bar["last"]) != (int(c["t"][i]), int(c["n"][i]), int(c["first"][i]), int(c["last"][i])) or \
                        any(Fraction(int(c[k][i]), d2) != bar[k] for k in "ohlc"):
                    same = False
                    break
            if not same:
                break
        out.append(dict(gate=gate, ticks=n, equality="IDENTICAL" if same else "MISMATCH", oracleSeconds=round(t_oracle, 2)))
        print(json.dumps(out[-1]), flush=True)
    return out


def stage_c(reader):
    month = month_of(reader)
    store = LocalObjectStore(tempfile.mkdtemp(prefix="bench-serve-"))
    engine.publish_month(store, reader, "BENCH", month, rights="UNKNOWN")
    src = reader.manifest["manifestHash"]
    last = int(reader.manifest["files"][-1]["lastTimeNs"])
    mid = last - (last - int(reader.manifest["files"][0]["firstTimeNs"])) // 3
    out = {}
    for label, cursor in (("late-in-month", last - 1), ("one-third-from-end", mid)):
        sessions = {"s": svc.Session("s", "u", "BENCH", src, "MID", cursor)}
        service = svc.ChartService(store, {"BENCH": reader}, sessions, {"t": "u"})
        metrics = []
        http = ThreadingHTTPServer(("127.0.0.1", 0), svc.make_handler(service, metrics))
        threading.Thread(target=http.serve_forever, daemon=True).start()
        port = http.server_address[1]

        def fetch(q):
            req = urllib.request.Request(f"http://127.0.0.1:{port}/v1/chart/bars?{q}", headers={"Authorization": "Bearer t"})
            t0 = time.perf_counter()
            with urllib.request.urlopen(req) as r:
                body = r.read()
            return time.perf_counter() - t0, len(body)

        def pct(xs, p):
            xs = sorted(xs)
            return round(xs[min(len(xs) - 1, int(len(xs) * p))] * 1000, 2)
        res = {}
        for phase in ("cold", "warm"):
            if phase == "cold":
                service.cache.clear()
                service.catalog.clear()
                store.counters.__init__()
            g0 = dict(store.counters.snapshot())
            lat, size = [], []
            for rep in range(1 if phase == "cold" else 20):
                for tf, _ in engine.TIMEFRAMES:
                    for q in (f"session=s&tf={tf}", f"session=s&tf={tf}&limit=1000"):
                        dt, n = fetch(q)
                        lat.append(dt)
                        size.append(n)
            g1 = store.counters.snapshot()
            res[phase] = dict(requests=len(lat), p50ms=pct(lat, .5), p95ms=pct(lat, .95), p99ms=pct(lat, .99), meanPayloadBytes=round(sum(size) / len(size)),
                              maxPayloadBytes=max(size), storeGets=g1["get"] - g0["get"], storeBytes=g1["bytesGet"] - g0["bytesGet"], storeLists=g1["list"] - g0["list"],
                              cacheHits=service.hits, cacheMisses=service.misses)
        per_tf = {}
        for tf, _ in engine.TIMEFRAMES:
            xs = [fetch(f"session=s&tf={tf}")[0] for _ in range(15)]
            per_tf[tf] = dict(firstPageP50ms=pct(xs, .5), payload=fetch(f"session=s&tf={tf}")[1])
        res["firstPageByTimeframe"] = per_tf
        out[label] = res
        http.shutdown()
        print(label, json.dumps(res)[:600], flush=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True); ap.add_argument("--repeats", type=int, default=3); ap.add_argument("--oracle-upto", type=int, default=1_000_000)
    ap.add_argument("--out"); ap.add_argument("--skip", default="")
    a = ap.parse_args()
    reader = CompactTickReader(a.src)
    env = dict(python=sys.version.split()[0], numpy=np.__version__, platform=platform.platform(), logicalCpus=psutil.cpu_count(), ramGiB=round(psutil.virtual_memory().total / 2**30, 1),
               sourceManifestHash=reader.manifest["manifestHash"], sourceTicks=reader.manifest["eventCount"], scale=reader.scale, targetHostNote="target VPS is 6 vCPU / 16 GiB; this is NOT that host")
    import pyarrow
    env["pyarrow"] = pyarrow.__version__
    print(json.dumps(env), flush=True)
    result = dict(environment=env)
    if "A" not in a.skip:
        result["A_materialisation"] = stage_a(reader, a.repeats)
    if "B" not in a.skip:
        result["B_equality"] = stage_b(reader, a.oracle_upto)
    if "C" not in a.skip:
        result["C_serving"] = stage_c(reader)
    if a.out:
        Path(a.out).write_text(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
