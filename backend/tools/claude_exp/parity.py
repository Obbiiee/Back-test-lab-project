"""Financial parity: Codex baseline (canonical source + real timeline + real kernel) vs Claude path (verified compact + jump + same kernel code)."""
import sys, os, time, json, tempfile, shutil, hashlib
from pathlib import Path
from common import *
from baseline import run_baseline
from claude_session import AdmittedSource, ClaudeSession
from market_data.compact_tick import write_compact
try:
    import psutil; PS = psutil.Process()
except Exception:
    PS = None

def rss_peak():
    if PS is None: return None
    mi = PS.memory_info(); return getattr(mi, "peak_wset", mi.rss) / 1e6

def inject(rows, mode):
    rows = list(rows)
    if mode == "tie":      # equal timestamp, different quote (UNTRUSTED order), every 997th tick
        out = []
        for i, (ts, ask, bid) in enumerate(rows):
            out.append((ts, ask, bid))
            if i % 997 == 996:
                out.append((ts, f"{float(ask)+0.4:.3f}", f"{float(bid)+0.4:.3f}"))
        return out
    if mode == "gap":      # a >60 s silence after tick 3000 and 9000 (shift the rest of the series)
        out = []; shift = 0
        for i, (ts, ask, bid) in enumerate(rows):
            if i in (3000, 9000): shift += 150_000
            out.append((ts + shift, ask, bid))
        return out
    return rows

def compact_events(rows):
    for i, (ts, ask, bid) in enumerate(rows):
        yield dict(timeNs=str(ts * 1_000_000), bid=bid, ask=ask, rawOrdinal=str(i))

def _orders_view(orders, drop_terminal):
    keep = lambda v: not (drop_terminal and v["status"] in ("CANCELLED", "CLOSED", "EXPIRED", "UNRESOLVED"))
    return {k: {x: v[x] for x in ("status", "entryPrice", "grossPosted", "remaining")} for k, v in orders.items() if keep(v)}

def semantic(events):
    return [e for e in strip_source_specific([x for x in events if x["kind"] != "REPLAY_ADVANCED"])]

def run(n, mode="clean", step_s=300, tp=1500, sl=1000, tmp=None, mix=False, seed=0, rows_override=None, offset=0, archive=False):
    out = dict(n=n, mode=mode)
    rows = rows_override if rows_override is not None else inject(read_real_rows(n + offset)[offset:], mode)
    work = Path(tempfile.mkdtemp(prefix="par-", dir=tmp))
    provider, res, t_ing = ingest_engine(rows, work)
    out["ingest_engine_s"] = round(t_ing, 1); out["accepted"] = res["acceptedRows"]
    # baseline
    groups = []
    b = run_baseline(provider, rows, step_s, tp, sl, collect=groups, mix=mix, archive=archive)
    out["baseline"] = dict(cpu=round(b["cpu"], 2), wall=round(b["wall"], 2), balance=b["state"]["balance"],
                           fills=sum(e["kind"] in ("ENTRY_FILL", "EXIT_FILL") for e in b["events"]),
                           unresolved=b["state"]["unresolved"])
    # compact + admission
    t0 = time.perf_counter()
    first = groups[0]["events"][0]
    cdir = work / "compact"
    m = write_compact(cdir, compact_events([(r[0], r[1], r[2]) for r in rows]), parent=dict(datasetId=first["datasetId"], datasetVersion=first["datasetVersion"]), scale=3)
    out["compact_write_s"] = round(time.perf_counter() - t0, 2); out["compact_bytes"] = sum(f["bytes"] for f in m["files"])
    adm = dict(datasetId=first["datasetId"], datasetVersion=first["datasetVersion"], providerId=first["providerId"], feedId=first["feedId"],
               instrumentId=first["instrumentId"], sourceId=first["provenance"]["sourceId"], memberHash=first["provenance"]["memberHash"],
               manifestHash=m["manifestHash"])
    t0 = time.perf_counter()
    src = AdmittedSource(cdir, adm, expected_manifest_hash=m["manifestHash"])
    out["admit_load_s"] = round(time.perf_counter() - t0, 2)
    t0 = time.perf_counter()
    mismatch = 0
    assert len(groups) == src.ngroups, (len(groups), src.ngroups)
    for g, grp in enumerate(groups):
        if src.canonical_group(g) != grp: mismatch += 1
    out["admission_reconstruction_mismatches"] = mismatch; out["admission_verify_s"] = round(time.perf_counter() - t0, 2)
    # claude run (identical strategy)
    profile = make_profile(provider)
    work2 = tempfile.mkdtemp(prefix="seed-")
    tl = IndexedTickTimeline(provider, provider.dataset_id, provider.dataset_version, str(rows[0][0] * 1_000_000), log_folder=work2)
    seed_cp = tl.checkpoint(); tl.close()
    start, end = rows[0][0] * 1_000_000, rows[-1][0] * 1_000_000
    cs = ClaudeSession(src, profile, policy(), seed_cp, archive=archive)
    cpu0, t0 = time.process_time(), time.perf_counter()
    events_all = drive(cs.advance_through, lambda k, pl, cid: cs.command(k, pl, cid), lambda: cs.state, start, end, step_s, tp, sl, mix)
    cpu, wall = time.process_time() - cpu0, time.perf_counter() - t0
    out["claude"] = dict(cpu=round(cpu, 2), wall=round(wall, 2), balance=cs.state["balance"], stats=cs.stats,
                         fills=sum(e["kind"] in ("ENTRY_FILL", "EXIT_FILL") for e in events_all), unresolved=cs.state["unresolved"],
                         advanceLogBytes=len(json.dumps(cs.log)))
    sb, sc_ = semantic(b["events"]), semantic(events_all)
    out["parity"] = dict(eventsEqual=sb == sc_, eventsBaseline=len(sb), eventsClaude=len(sc_),
                         balanceEqual=b["state"]["balance"] == cs.state["balance"],
                         ordersEqual=_orders_view(b["state"]["orders"], False) == _orders_view(cs.state["orders"], False),
                         lastObservedEqual=b["state"]["lastObservedNs"] == cs.state["lastObservedNs"],
                         nextGroupEqual=b["state"]["nextGroupIndex"] == cs.state["nextGroupIndex"],
                         quoteBasisEqual=b["state"]["quoteBasis"] == cs.state["quoteBasis"],
                         realizedEqual=b["state"]["realizedGross"] == cs.state["realizedGross"])
    if not out["parity"]["eventsEqual"]:
        for x, y in zip(sb, sc_):
            if x != y: out["firstDiff"] = (x, y); break
    out["peak_rss_mb"] = rss_peak()
    out["_rows"] = rows; out["_cdir"] = cdir; out["_manifest"] = m; out["_groups"] = groups; out["_cs"] = cs; out["_src"] = src; out["_profile"] = profile; out["_seed"] = seed_cp; out["_work"] = work
    return out

if __name__ == "__main__":
    n = int(sys.argv[1]); mode = sys.argv[2] if len(sys.argv) > 2 else "clean"
    r = run(n, mode)
    work = r.pop("_work"); [r.pop(k) for k in ("_cs", "_src", "_profile", "_seed", "_rows", "_cdir", "_manifest", "_groups")]
    print(json.dumps(r, indent=1, default=str)); shutil.rmtree(work, ignore_errors=True)
