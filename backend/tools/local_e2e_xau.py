# Local QA harness (not part of the product). Run from backend/: XAU_TICK_ZIP=... python tools/local_e2e_xau.py 20000
# The psycopg stub only lets modules import; this script never touches PostgreSQL.
"""End-to-end on REAL XAUUSD ticks (Dukascopy 2024-01 local copy): engine path vs compact path vs old canonical.

Chain: raw CSV -> repo ingestion -> engine dataset -> IndexedTickTimeline session (zlib-1 default, new canonical)
       -> revealed groups -> strategy replay            == compare ==
       raw CSV -> compact parquet -> iter_groups -> same strategy replay
Also: same timeline run with the ORIGINAL canonical walk and with raw log codec; checkpoints must be identical.
"""
import sys, os, io, csv, zipfile, time, tempfile, shutil, sqlite3, datetime as dt, json
from pathlib import Path
from contextlib import closing
from decimal import Decimal
from unittest.mock import MagicMock
for _n in ("psycopg","psycopg.sql","psycopg.rows","psycopg.conninfo","psycopg.errors","psycopg.types","psycopg.types.json","psycopg.pq","psycopg_pool"):
    sys.modules[_n]=MagicMock()
sys.path.insert(0, ".")
sys.path.insert(0, "tests")
from ticks.dukascopy_csv import DukascopyCsvIngestion
from ticks.storage_v2 import DiskTickProvider
from ticks.timeline_v2 import IndexedTickTimeline
from market_data.compact_tick import write_compact, CompactTickReader
import contracts.canonical as C, ticks.contracts_v2 as V
from tests.test_canonical_fastpath import _ref_normalize
from execution.historical import new_session_log_codec

ROWS = int(sys.argv[1])
ZIP = os.environ["XAU_TICK_ZIP"]  # local Dukascopy-format monthly ZIP (ts ms, ask, bid, askVol, bidVol); never committed
tmp = Path(tempfile.mkdtemp(prefix="e2e-"))
out = {}

def stage(name):
    print(f"\n== {name}", flush=True)

# ---------- 1. real raw rows (ts ms, ask, bid) ----------
rows = []
with zipfile.ZipFile(ZIP) as z, z.open(z.namelist()[0]) as raw:
    rd = csv.reader(io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")); next(rd)
    for i, (ts, ask, bid, av, bv) in enumerate(rd):
        if i >= ROWS: break
        rows.append((int(ts), ask, bid, av, bv))
print(f"real ticks read: {len(rows)}; first {rows[0][0]} last {rows[-1][0]}")

# ---------- 2. engine ingestion ----------
stage("engine ingestion (repo DukascopyCsvIngestion)")
src = tmp / "XAUUSD.csv"
with open(src, "w", newline="") as f:
    w = csv.writer(f, lineterminator="\n"); w.writerow(["Gmt time", "Ask", "Bid", "AskVolume", "BidVolume"])
    for ts, ask, bid, av, bv in rows:
        d = dt.datetime.fromtimestamp(ts / 1000, dt.timezone.utc)
        w.writerow([d.strftime("%d.%m.%Y %H:%M:%S.") + f"{ts % 1000:03d}", ask, bid, av, bv])
t0 = time.perf_counter()
imp = DukascopyCsvIngestion(src, tmp / "store", symbol="XAUUSD", month="2024-01")
res = imp.run(); imp.builder.store.close()
t_ing = time.perf_counter() - t0
print(f"ingest {t_ing:.1f}s  accepted {res['acceptedRows']}  ({res['acceptedRows']/t_ing:,.0f} tick/s)")
prov = DiskTickProvider(tmp / "store", res["datasetVersion"])
dsid, dsver = res["datasetId"], res["datasetVersion"]
out["ingest"] = dict(seconds=round(t_ing, 1), accepted=res["acceptedRows"], raw=len(rows))

# ---------- 3. compact path ----------
stage("compact parquet (same raw rows)")
def cevents():
    for i, (ts, ask, bid, av, bv) in enumerate(rows):
        yield dict(timeNs=str(ts * 1_000_000), bid=bid, ask=ask, rawOrdinal=str(i))
t0 = time.perf_counter()
m = write_compact(tmp / "compact", cevents(), parent=dict(datasetId=dsid, datasetVersion=dsver), scale=3)
t_cw = time.perf_counter() - t0
cr = CompactTickReader(tmp / "compact", expected_manifest_hash=m["manifestHash"])
cr.verify_all(deep=True)
csize = sum(x["bytes"] for x in m["files"])
print(f"compact write {t_cw:.2f}s  groups {m['groupCount']}  size {csize/1e6:.2f} MB  crossed {m['quality']['crossedQuotes']}")

# ---------- strategy (shared) ----------
SCALE = 1000
def strategy(tick_iter):
    """tick_iter yields (timeNs:int, bid:int, ask:int) scaled by 1000. Deterministic TP/SL gold replay."""
    trades, pos, n, side = [], None, 0, 1
    TP, SL, EVERY = 1500, 1000, 400
    for t, bid, ask in tick_iter:
        n += 1
        if pos is None:
            if n % EVERY == 0:
                pos = (t, side, ask if side == 1 else bid); side = -side
        else:
            ot, s, e = pos
            if s == 1:
                px = bid; hit = px >= e + TP or px <= e - SL
            else:
                px = ask; hit = px <= e - TP or px >= e + SL
            if hit:
                trades.append((ot, s, e, t, px, (px - e) * s)); pos = None
    return trades

def sc(text):
    return int((Decimal(text) * SCALE).to_integral_value())

# ---------- 4. engine timeline session (new code) ----------
stage("engine session timeline (zlib-1 default + new canonical)")
start_ns = str(int(rows[0][0]) * 1_000_000)
last_ns = str(int(rows[-1][0]) * 1_000_000)

def run_timeline(tag, codec, normalize):
    C._normalize = normalize; V._normalize = normalize
    folder = tmp / ("log-" + tag)
    tl = IndexedTickTimeline(prov, dsid, dsver, start_ns, log_folder=folder, log_codec=codec, max_groups_per_advance=256)
    groups, consumed = [], 0
    t0 = time.perf_counter()
    while True:
        tl.advance_through(last_ns, tl.cursor)
        cp = tl.checkpoint(); cur = cp["cursor"]
        count = int(cur["nextGroupIndex"]) if "nextGroupIndex" in cur else None
        while count is not None and consumed < count:
            take = min(64, count - consumed)
            got = tl.consumer().read_revealed(str(consumed), take)
            groups.extend(got); consumed += len(got)
            if not got: break
        if int(cur["throughNs"]) >= int(last_ns) and cur["pendingTargetNs"] is None: break
    t_adv = time.perf_counter() - t0
    cp = tl.checkpoint(); tl.close()
    t0 = time.perf_counter()
    r = IndexedTickTimeline.resume(prov, cp, log_folder=folder, log_codec=None, max_groups_per_advance=256)
    t_res = time.perf_counter() - t0
    rcp = r.checkpoint(); r.close()
    assert rcp == cp, "resume checkpoint differs"
    with closing(sqlite3.connect(folder / "timeline.sqlite")) as db:
        body = sum(len(x[0]) for x in db.execute("SELECT body FROM blocks"))
    size = sum(f.stat().st_size for f in folder.rglob("*") if f.is_file())
    return dict(tag=tag, adv=t_adv, res=t_res, cp=cp, groups=groups, body=body, size=size)

orig_norm = C._normalize
os.environ.pop("BTL_QA_TIMELINE_LOG_CODEC", None)
codec = new_session_log_codec(tmp / "log-new")
print("codec chosen by product rule for a new session:", codec)
runs = {}
runs["new+zlib"] = run_timeline("new", codec, orig_norm)
runs["old+zlib"] = run_timeline("old", codec, _ref_normalize)
runs["new+raw"] = run_timeline("raw", None, orig_norm)
C._normalize = orig_norm; V._normalize = orig_norm
for k, r in runs.items():
    print(f"{k:9} advance {r['adv']:6.2f}s resume {r['res']:5.2f}s | log blocks {r['body']:>10,} B  files {r['size']:>10,} B | groups revealed {len(r['groups'])}")
same_cp = runs["new+zlib"]["cp"] == runs["old+zlib"]["cp"] == runs["new+raw"]["cp"]
same_hist = runs["new+zlib"]["groups"] == runs["old+zlib"]["groups"] == runs["new+raw"]["groups"]
print("checkpoints identical (new canonical / old canonical / raw codec):", same_cp)
print("revealed history identical:", same_hist)
out["timeline"] = {k: dict(advance_s=round(r["adv"], 2), resume_s=round(r["res"], 2), blockBytes=r["body"], fileBytes=r["size"]) for k, r in runs.items()}
out["timeline"]["sameCheckpoints"] = same_cp; out["timeline"]["sameHistory"] = same_hist

# ---------- 5. strategy parity ----------
stage("strategy replay parity: engine-revealed groups vs compact groups vs raw CSV")
def engine_ticks():
    for g in runs["new+zlib"]["groups"]:
        for e in g["events"]:
            yield int(e["timeNs"]), sc(e["bid"]), sc(e["ask"])
def compact_ticks():
    for ts, g in cr.iter_groups(0, 2**62):
        for b, a in zip(g["bid"], g["ask"]):
            yield ts, int(b), int(a)
def raw_ticks():
    for ts, ask, bid, av, bv in rows:
        yield ts * 1_000_000, sc(bid), sc(ask)
t0 = time.perf_counter(); te = strategy(engine_ticks()); d1 = time.perf_counter() - t0
t0 = time.perf_counter(); tc = strategy(compact_ticks()); d2 = time.perf_counter() - t0
tr = strategy(raw_ticks())
print(f"trades: engine {len(te)}  compact {len(tc)}  raw {len(tr)} | replay time engine-groups {d1:.2f}s compact {d2:.2f}s")
print("engine == raw:", te == tr, "| compact == raw:", tc == tr)
pnl = sum(t[5] for t in tr) / SCALE
print(f"net PnL (price units) {pnl:.2f}; first trade {tr[0] if tr else None}")
out["strategy"] = dict(trades=len(tr), engineEqRaw=te == tr, compactEqRaw=tc == tr, pnl=pnl,
                       engineReplayS=round(d1, 2), compactReplayS=round(d2, 2))

# ---------- 6. same-source tick equality ----------
n_engine = sum(len(g["events"]) for g in runs["new+zlib"]["groups"])
print(f"ticks: raw {len(rows)} | engine accepted {res['acceptedRows']} revealed {n_engine} | compact {m['eventCount']}")
out["counts"] = dict(raw=len(rows), engineAccepted=res["acceptedRows"], engineRevealed=n_engine, compact=m["eventCount"])
print("\nJSON", json.dumps(out))
shutil.rmtree(tmp, ignore_errors=True)
