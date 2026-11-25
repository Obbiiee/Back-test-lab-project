#!/usr/bin/env python
"""QA-private real-month measurement (NOT product code, no new engine/format). Rights of the data: UNKNOWN -> private QA only.
Run from anywhere:  RMB_OUT=<scratch dir> [RMB_MODEL=v1|v2] python real_month_bench.py <phase> [--archive] [--n N] [--standalone]
RMB_OUT receives event files that CONTAIN real prices: keep it outside the repository and delete it afterwards; never commit it.

Phases (each is its own process so peak RSS is per phase):
  read      open the REAL Compact V2 month directly (pin + hash verify + decode to arrays)
  ingest    TEMPORARY canonical store from the same ticks (what the baseline needs; the cost direct reading avoids)
  claude    ClaudeSession reading the real Compact V2 directly; reuses observed_kernel.apply (the one financial reducer)
  baseline  canonical IndexedTickTimeline + observed_kernel.apply on the temporary store
  compare   raw/semantic equality of the two runs
Nothing prints tick prices; event files stay in the scratch folder and are deleted by the operator afterwards.
"""
import argparse, hashlib, json, os, resource, shutil, sys, threading, time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND / "tools/claude_exp"))
sys.path.insert(0, str(BACKEND))
import common                                    # noqa: E402  (stubs psycopg; QA harness helpers)
from common import (drive, policy, genesis_checkpoint, strip_source_specific, PROFILE)    # noqa: E402
from compact2 import open_compact                # noqa: E402

REAL = Path(os.environ.get("RMB_REAL", str(Path.home() / "data/incoming/compact2/XAUUSD/2024-02")))      # one real Compact V2 month (private QA, rights UNKNOWN)
OUT = Path(os.environ["RMB_OUT"])
OUT.mkdir(parents=True, exist_ok=True)


# ------------------------------------------------------------------------------------------------ host safety + meters
def meminfo():
    d = {}
    for line in open("/proc/meminfo"):
        k, v = line.split(":", 1)
        d[k] = int(v.split()[0]) * 1024
    return d


def guard():
    """Owner OS guards: MemAvailable >= 1 GiB (kept at 1.5), no swap, free disk >= 30 GB."""
    def loop():
        while True:
            m = meminfo()
            st = os.statvfs("/")
            free_gb = st.f_bavail * st.f_frsize / 1e9
            if m["MemAvailable"] < 1.5 * 2**30 or m["SwapTotal"] - m["SwapFree"] > 0 or free_gb < 30:
                print(f"GUARD STOP: MemAvailable={m['MemAvailable']/2**30:.2f} GiB swapUsed={m['SwapTotal']-m['SwapFree']} diskFree={free_gb:.1f} GB", flush=True)
                os._exit(3)
            time.sleep(3)
    threading.Thread(target=loop, daemon=True).start()


def proc_io():
    d = {}
    for line in open("/proc/self/io"):
        k, v = line.split(":")
        d[k.strip()] = int(v)
    return d


def cg_file(name):
    try:
        rel = open("/proc/self/cgroup").read().strip().split("::")[-1]
        return Path("/sys/fs/cgroup" + rel) / name
    except Exception:
        return None


def cg_read(name):
    p = cg_file(name)
    try:
        return p.read_text()
    except Exception:
        return None


class Meter:
    def __init__(self, label):
        self.label = label
        self.t0, self.c0, self.io0 = time.perf_counter(), time.process_time(), proc_io()
        self.cg0 = cg_read("cpu.stat")

    def stop(self, **extra):
        wall, cpu, io1 = time.perf_counter() - self.t0, time.process_time() - self.c0, proc_io()
        ru = resource.getrusage(resource.RUSAGE_SELF)
        out = dict(phase=self.label, wall_s=round(wall, 2), cpu_s=round(cpu, 2), cpu_util_pct=round(100 * cpu / wall, 1) if wall else None,
                   peak_rss_mb=round(ru.ru_maxrss / 1024, 1),
                   io_read_mb=round((io1["read_bytes"] - self.io0["read_bytes"]) / 1e6, 1),
                   io_write_mb=round((io1["write_bytes"] - self.io0["write_bytes"]) / 1e6, 1),
                   io_rchar_mb=round((io1["rchar"] - self.io0["rchar"]) / 1e6, 1), io_wchar_mb=round((io1["wchar"] - self.io0["wchar"]) / 1e6, 1))
        peak = cg_read("memory.peak")
        if peak and peak.strip().isdigit():
            out["cgroup_memory_peak_mb"] = round(int(peak) / 1e6, 1)
        out.update(extra, model=MODEL, archive=os.environ.get("RMB_ARCHIVE") == "1")
        return out


def emit(name, obj):
    (OUT / f"{name}.json").write_text(json.dumps(obj, indent=1, default=str))
    print(json.dumps(obj, indent=1, default=str), flush=True)


def real_manifest_hash():
    return json.loads((REAL / "DONE.json").read_text())["manifestHash"]


# ------------------------------------------------------------------------------------------------ helpers
def price_txt(v, scale=3):
    v = int(v)
    return f"{v // 10**scale}.{v % 10**scale:0{scale}d}"


def decode_arrays():
    r = open_compact(REAL, expected_manifest_hash=real_manifest_hash())
    return r, r.read_range(0, 2**62)


MODEL = os.environ.get("RMB_MODEL", "v2")        # v1 = CONDITIONAL_OBSERVED_TICK_SIMULATION (old QA profile), v2 = HISTORICAL_TECHNICAL_TICK_SIMULATION_V2


def make_profile_from_identity(ident, model=None):
    from copy import deepcopy
    from execution.observed_profile import ObservedExecutionProfile, historical_technical_profile
    model = model or MODEL
    primary = dict(datasetId=ident["datasetId"], datasetVersion=ident["datasetVersion"], providerId=ident["providerId"], feedId=ident["feedId"],
                   feedInstrumentId=ident["instrumentId"], providerSymbol="XAUUSD", evidenceClass="PROVIDER_OBSERVATION")
    raw = deepcopy(PROFILE)
    raw["primary"] = primary
    if model == "v2":
        # QA placeholder digest: NO qualification receipt exists for this private data and none is claimed.
        raw = historical_technical_profile(raw, hashlib.sha256(b"QA-PRIVATE-NO-QUALIFICATION-CLAIM|" + ident["datasetId"].encode()).hexdigest())
    return ObservedExecutionProfile.from_wire(raw)


def provider_identity(prov):
    desc = prov.describe_v2(prov.dataset_id, prov.dataset_version)["root"]
    return dict(datasetId=prov.dataset_id, datasetVersion=prov.dataset_version, providerId=desc["providerId"], feedId=desc["feedId"], instrumentId=desc["instrumentId"])


# the canonical baseline (baseline.run_baseline) builds its profile through make_profile: give it the same model as the direct path
import baseline as _baseline                      # noqa: E402
_baseline.make_profile = lambda provider, symbol="XAUUSD": make_profile_from_identity(provider_identity(provider))


def semantic_digest(events):
    sem = strip_source_specific([e for e in events if e["kind"] != "REPLAY_ADVANCED"])
    return hashlib.sha256(json.dumps(sem, sort_keys=True, default=str).encode()).hexdigest(), len(sem)


def summarize_events(events):
    kinds = {}
    for e in events:
        key = e["kind"] if e["kind"] != "REFUSED" else f"REFUSED:{e.get('code')}"
        kinds[key] = kinds.get(key, 0) + 1
    return kinds


def unresolved_diagnosis(events, state):
    """Counts only (no prices/timestamps): which codes/kinds produced UNRESOLVED and the orders ending UNRESOLVED."""
    codes = {}
    for e in events:
        txt = json.dumps(e, default=str)
        if "UNRESOLVED" in txt or e["kind"].find("UNRESOLVED") >= 0:
            key = f"{e['kind']}|{e.get('code') or (e.get('detail') or {}).get('code') or (e.get('detail') or {}).get('reason') or e.get('reason')}"
            codes[key] = codes.get(key, 0) + 1
    st = {}
    for o in state["orders"].values():
        st[o["status"]] = st.get(o["status"], 0) + 1
    return dict(eventCodes=codes, ordersByStatus=st, stateUnresolved=state.get("unresolved"))


# ------------------------------------------------------------------------------------------------ phases
def phase_read(a):
    m = Meter("read")
    t = time.perf_counter(); r = open_compact(REAL, expected_manifest_hash=real_manifest_hash()); t_open = time.perf_counter() - t
    t = time.perf_counter(); r.verify_all(deep=False); t_shallow = time.perf_counter() - t
    t = time.perf_counter(); r.verify_all(deep=True); t_deep = time.perf_counter() - t
    t = time.perf_counter(); arr = r.read_range(0, 2**62); t_decode = time.perf_counter() - t
    n = len(arr["ts_ns"])
    emit("read", m.stop(ticks=n, open_s=round(t_open, 3), verify_hash_only_s=round(t_shallow, 2), verify_deep_s=round(t_deep, 2), decode_all_s=round(t_decode, 2),
                        decode_ticks_per_s=round(n / t_decode), compact_v2_bytes=sum(f["bytes"] for f in r.manifest["files"])))


def read_rows(limit=None):
    r, arr = decode_arrays()
    ts, bid, ask = arr["ts_ns"], arr["bid"], arr["ask"]
    n = len(ts) if limit is None else min(limit, len(ts))
    return r, ts[:n], bid[:n], ask[:n]


def phase_ingest(a):
    import time as T
    from ticks.dukascopy_csv import DukascopyCsvIngestion
    from ticks.storage_v2 import DiskTickProvider
    m = Meter("ingest")
    work = OUT / f"store-{a.n or 'full'}"
    shutil.rmtree(work, ignore_errors=True); work.mkdir(parents=True)
    _r, ts, bid, ask = read_rows(a.n)
    csvp = work / "XAUUSD.csv"
    t = T.perf_counter()
    with open(csvp, "w", newline="") as f:
        f.write("Gmt time,Ask,Bid,AskVolume,BidVolume\n")
        for i in range(len(ts)):
            ms = int(ts[i]) // 1_000_000
            g = T.gmtime(ms // 1000)
            f.write(f"{g.tm_mday:02d}.{g.tm_mon:02d}.{g.tm_year} {g.tm_hour:02d}:{g.tm_min:02d}:{g.tm_sec:02d}.{ms % 1000:03d},{price_txt(ask[i])},{price_txt(bid[i])},1,1\n")
    t_csv = T.perf_counter() - t
    t = T.perf_counter()
    imp = DukascopyCsvIngestion(csvp, work / "store", symbol="XAUUSD", month="2024-02")
    res = imp.run()
    imp.builder.store.close()
    t_ing = T.perf_counter() - t
    prov = DiskTickProvider(work / "store", res["datasetVersion"])
    desc = prov.describe_v2(prov.dataset_id, prov.dataset_version)["root"]
    src0 = imp.meta
    ident = dict(datasetId=prov.dataset_id, datasetVersion=prov.dataset_version, providerId=desc["providerId"], feedId=desc["feedId"],
                 instrumentId=desc["instrumentId"], sourceId=imp.source_id, memberHash=imp.pin["sha256"], n=int(len(ts)),
                 startMs=int(ts[0]) // 1_000_000, endMs=int(ts[-1]) // 1_000_000)
    (OUT / f"ident-{a.n or 'full'}.json").write_text(json.dumps(ident))
    size = sum(p.stat().st_size for p in (work / "store").rglob("*") if p.is_file())
    emit(f"ingest-{a.n or 'full'}", m.stop(ticks=len(ts), csv_write_s=round(t_csv, 2), canonical_ingest_s=round(t_ing, 2),
                                          ingest_ticks_per_s=round(len(ts) / t_ing), canonical_store_mb=round(size / 1e6, 1), csv_mb=round(csvp.stat().st_size / 1e6, 1),
                                          accepted=res["acceptedRows"]))


def scenario(a):
    return dict(step_s=a.step_s, tp=a.tp, sl=a.sl, mix=True)


def standalone_ident(src):
    """Identity LABELS borrowed from the 20k smoke ingest + the real arrays' bounds. Used only for Claude-only measurements."""
    ident = json.loads((OUT / "ident-20000.json").read_text())
    ident.update(n=int(src.ts.shape[0]), startMs=int(src.ts[0]) // 1_000_000, endMs=int(src.ts[-1]) // 1_000_000)
    return ident


def phase_claude(a):
    from claude_session import AdmittedSource, ClaudeSession
    tag = a.n or "full"
    m = Meter("claude")
    if a.standalone:
        _r, _arr = decode_arrays(); ident = json.loads((OUT / "ident-20000.json").read_text())
        ident.update(n=int(len(_arr["ts_ns"])), startMs=int(_arr["ts_ns"][0]) // 1_000_000, endMs=int(_arr["ts_ns"][-1]) // 1_000_000); del _arr
        tag = "standalone"
    else:
        ident = json.loads((OUT / f"ident-{tag}.json").read_text())
    adm = dict(datasetId=ident["datasetId"], datasetVersion=ident["datasetVersion"], providerId=ident["providerId"], feedId=ident["feedId"],
               instrumentId=ident["instrumentId"], sourceId=ident["sourceId"], memberHash=ident["memberHash"], manifestHash=real_manifest_hash(),
               scale=1000, kind="dukascopy-csv")
    t = time.perf_counter()
    src = AdmittedSource(REAL, adm, expected_manifest_hash=real_manifest_hash())
    t_admit = time.perf_counter() - t
    profile = make_profile_from_identity(ident)
    start, end = ident["startMs"] * 1_000_000, ident["endMs"] * 1_000_000
    seed = genesis_checkpoint(ident["datasetId"], ident["datasetVersion"], start)
    cs = ClaudeSession(src, profile, policy(), seed, archive=a.archive)
    t = time.perf_counter()
    events = drive(cs.advance_through, lambda k, pl, cid: cs.command(k, pl, cid), lambda: cs.state, start, end, **scenario(a))
    t_run = time.perf_counter() - t
    dig, n_sem = semantic_digest(events)
    (OUT / f"events-claude-{tag}.json").write_text(json.dumps(events, default=str))
    (OUT / f"state-claude-{tag}.json").write_text(json.dumps(cs.state, default=str, sort_keys=True))
    fills = sum(e["kind"] in ("ENTRY_FILL", "EXIT_FILL") for e in events)
    emit(f"claude-{tag}", m.stop(ticks_in_run=ident["n"], month_ticks_loaded=int(src.ts.shape[0]), groups=int(src.ngroups), admit_load_s=round(t_admit, 2), run_s=round(t_run, 2),
                                 ticks_per_s_run_only=round(ident["n"] / t_run), ticks_per_s_incl_admit=round(ident["n"] / (t_admit + t_run)),
                                 events=len(events), eventKinds=summarize_events(events), fills=fills, balance=cs.state["balance"] if a.show_balance else "(hidden)",
                                 stats=cs.stats, advance_log_json_bytes=len(json.dumps(cs.log)), semanticDigest=dig, semanticEvents=n_sem,
                                 unresolved=unresolved_diagnosis(events, cs.state)))


def phase_baseline(a):
    from baseline import run_baseline
    from ticks.storage_v2 import DiskTickProvider
    tag = a.n or "full"
    ident = json.loads((OUT / f"ident-{tag}.json").read_text())
    work = OUT / f"store-{tag}"
    prov = DiskTickProvider(work / "store", ident["datasetVersion"])
    m = Meter("baseline")
    rows = [(ident["startMs"], "0", "0"), (ident["endMs"], "0", "0")]        # run_baseline reads only the first/last timestamp
    r = run_baseline(prov, rows, a.step_s, a.tp, a.sl, collect=None, mix=True, archive=a.archive, symbol="XAUUSD")
    events = r["events"]
    dig, n_sem = semantic_digest(events)
    (OUT / f"events-baseline-{tag}.json").write_text(json.dumps(events, default=str))
    (OUT / f"state-baseline-{tag}.json").write_text(json.dumps(r["state"], default=str, sort_keys=True))
    fills = sum(e["kind"] in ("ENTRY_FILL", "EXIT_FILL") for e in events)
    emit(f"baseline-{tag}", m.stop(ticks=ident["n"], run_wall_s=round(r["wall"], 2), run_cpu_s=round(r["cpu"], 2), ticks_per_s=round(ident["n"] / r["wall"]),
                                   events=len(events), eventKinds=summarize_events(events), fills=fills, semanticDigest=dig, semanticEvents=n_sem,
                                   unresolved=unresolved_diagnosis(events, r["state"])))


def phase_compare(a):
    tag = a.n or "full"
    e1 = json.loads((OUT / f"events-baseline-{tag}.json").read_text())
    e2 = json.loads((OUT / f"events-claude-{tag}.json").read_text())
    s1 = json.loads((OUT / f"state-baseline-{tag}.json").read_text())
    s2 = json.loads((OUT / f"state-claude-{tag}.json").read_text())
    sem = lambda ev: strip_source_specific([x for x in ev if x["kind"] != "REPLAY_ADVANCED"])
    res = dict(rawEventsEqual=e1 == e2, semanticEventsEqual=sem(e1) == sem(e2), eventsBaseline=len(e1), eventsClaude=len(e2),
               balanceEqual=s1["balance"] == s2["balance"], realizedGrossEqual=s1["realizedGross"] == s2["realizedGross"],
               ordersEqual={k: (v["status"], v["entryPrice"], v["grossPosted"], v["remaining"]) for k, v in s1["orders"].items()} ==
                           {k: (v["status"], v["entryPrice"], v["grossPosted"], v["remaining"]) for k, v in s2["orders"].items()},
               lastObservedEqual=s1["lastObservedNs"] == s2["lastObservedNs"], nextGroupEqual=s1["nextGroupIndex"] == s2["nextGroupIndex"],
               quoteBasisEqual=s1["quoteBasis"] == s2["quoteBasis"], unresolvedEqual=s1["unresolved"] == s2["unresolved"])
    if not res["semanticEventsEqual"]:
        for i, (x, y) in enumerate(zip(sem(e1), sem(e2))):
            if x != y:
                res["firstSemanticDiffIndex"] = i; break
    emit(f"compare-{tag}", res)



# ------------------------------------------------------------------------------------------------ Jump / SEEK / checkpoint / resume
def build_claude(a):
    from claude_session import AdmittedSource, ClaudeSession
    _r, arr = decode_arrays()
    ident = json.loads((OUT / "ident-20000.json").read_text())
    ident.update(n=int(len(arr["ts_ns"])), startMs=int(arr["ts_ns"][0]) // 1_000_000, endMs=int(arr["ts_ns"][-1]) // 1_000_000)
    del arr
    adm = dict(datasetId=ident["datasetId"], datasetVersion=ident["datasetVersion"], providerId=ident["providerId"], feedId=ident["feedId"],
               instrumentId=ident["instrumentId"], sourceId=ident["sourceId"], memberHash=ident["memberHash"], manifestHash=real_manifest_hash(),
               scale=1000, kind="dukascopy-csv")
    src = AdmittedSource(REAL, adm, expected_manifest_hash=real_manifest_hash())
    profile = make_profile_from_identity(ident)
    start, end = ident["startMs"] * 1_000_000, ident["endMs"] * 1_000_000
    seed = genesis_checkpoint(ident["datasetId"], ident["datasetVersion"], start)
    return src, profile, seed, start, end, ident


def traced_drive(cs_box, start, end, step_s, tp, sl, jump):
    """The scripted trader of common.drive. jump=True: while an order is live, advance straight to cs.next_event_ns().
    Every advance/command actually executed is recorded in `trace` so the canonical reducer can replay the identical sequence."""
    trace, events = [], []
    def advance(target):
        cs = cs_box["cs"]
        t = int(target)
        if cs.state["ended"]:
            return []
        if jump:
            nxt = cs.next_event_ns()
            if nxt is not None and nxt > t:
                t = nxt
        if t <= int(cs.state["throughNs"]):
            return []
        t = min(t, end)
        ev = cs.advance_through(t)
        events.extend(ev); trace.append(("A", str(t), len(events)))
        return ev
    def command(kind, payload, cid):
        ev = cs_box["cs"].command(kind, payload, cid)
        events.extend(ev); trace.append(("C", kind, payload, cid, len(events)))
        return ev
    drive_events = drive(lambda tg: advance(tg), command, lambda: cs_box["cs"].state, start, end, step_s, tp, sl, True)
    return events, trace


def phase_features(a):
    from claude_session import ClaudeSession
    src, profile, seed, start, end, ident = build_claude(a)
    new = lambda: ClaudeSession(src, profile, policy(), seed, archive=a.archive)
    out = dict(ticks=ident["n"], groups=int(src.ngroups))

    # F1  SEEK: nothing live, one advance across the whole month
    m = Meter("seek")
    cs = new(); t = time.perf_counter(); ev = cs.advance_through(end); dt = time.perf_counter() - t
    out["seek_full_month"] = m.stop(advance_call_s=round(dt, 3), groups_consumed=int(cs.state["nextGroupIndex"]), all_groups_consumed=int(cs.state["nextGroupIndex"]) == src.ngroups,
                                    ticks_per_s=round(ident["n"] / dt), events=len(ev), stats=cs.stats)

    # F2  Jump-driven strategy (market/limit/stop/close/cancel with TP/SL) over the full month, trace recorded for canonical replay
    m = Meter("jump")
    box = dict(cs=new()); t = time.perf_counter()
    ev_j, trace_j = traced_drive(box, start, end, a.step_s, a.tp, a.sl, True)
    dtj = time.perf_counter() - t
    out["jump_strategy_full_month"] = m.stop(run_s=round(dtj, 2), ticks_per_s=round(ident["n"] / dtj), advances=sum(1 for x in trace_j if x[0] == "A"),
                                             commands=sum(1 for x in trace_j if x[0] == "C"), events=len(ev_j), eventKinds=summarize_events(ev_j),
                                             fills=sum(e["kind"] in ("ENTRY_FILL", "EXIT_FILL") for e in ev_j), stats=box["cs"].stats,
                                             unresolved=unresolved_diagnosis(ev_j, box["cs"].state))
    (OUT / "trace-jump.json").write_text(json.dumps(trace_j, default=str))
    (OUT / "events-jump.json").write_text(json.dumps(ev_j, default=str))

    # F3  checkpoint + resume (same strategy, step-driven) with a JSON round trip at the midpoint, then independent replay verification
    m = Meter("checkpoint")
    box = dict(cs=new(), swapped=False)
    mid = start + (end - start) // 2
    real_adv = None
    ref_events, _ = traced_drive(dict(cs=new()), start, end, a.step_s, a.tp, a.sl, False)            # uninterrupted reference (same process)
    t_ref_digest = semantic_digest(ref_events)[0]
    events, tr = [], []
    swap = dict()
    def advance(target):
        cs = box["cs"]
        if (not box["swapped"]) and int(cs.state["throughNs"]) >= mid:
            snap = cs.snapshot(); blob = json.dumps(snap, default=str)
            t0 = time.perf_counter(); snap2 = json.loads(blob)
            box["cs"] = ClaudeSession.recover(src, profile, policy(), seed, snap2); swap["recover_s"] = round(time.perf_counter() - t0, 3)
            swap["snapshot_json_bytes"] = len(blob); swap["log_records"] = len(snap["log"]); box["swapped"] = True
            cs = box["cs"]
        if cs.state["ended"] or int(target) <= int(cs.state["throughNs"]):
            return []
        ev = cs.advance_through(int(target)); events.extend(ev); return ev
    def command(kind, payload, cid):
        ev = box["cs"].command(kind, payload, cid); events.extend(ev); return ev
    t = time.perf_counter()
    drive(advance, command, lambda: box["cs"].state, start, end, a.step_s, a.tp, a.sl, True)
    run_s = time.perf_counter() - t
    t = time.perf_counter(); final_snap = box["cs"].snapshot()
    ClaudeSession.verify_by_replay(src, profile, policy(), seed, final_snap); verify_s = time.perf_counter() - t
    out["checkpoint_resume"] = m.stop(run_with_midpoint_recover_s=round(run_s, 2), swapped=box["swapped"], **swap,
                                      digest_equal_to_uninterrupted=semantic_digest(events)[0] == t_ref_digest, events=len(events),
                                      verify_by_replay_s=round(verify_s, 2), verify_by_replay_ok=True, final_log_records=len(final_snap["log"]),
                                      final_snapshot_json_bytes=len(json.dumps(final_snap, default=str)))
    emit("features", out)


def phase_replay(a):
    """Replay the recorded Jump-driven trace on the CANONICAL timeline+reducer for the first `window` ticks and compare;
    then a SEEK parity check (one advance across the window, nothing live)."""
    from ticks.storage_v2 import DiskTickProvider
    import execution.observed_kernel as K0
    from execution.observed_kernel import apply, seed_state
    from ticks.timeline_v2 import IndexedTickTimeline
    from claude_session import ClaudeSession
    import tempfile
    tag = str(a.window)
    ident = json.loads((OUT / f"ident-{tag}.json").read_text())
    work = OUT / f"store-{tag}"
    prov = DiskTickProvider(work / "store", ident["datasetVersion"])
    profile = make_profile_from_identity(provider_identity(prov))
    start, win_end = ident["startMs"] * 1_000_000, ident["endMs"] * 1_000_000
    trace = json.loads((OUT / "trace-jump.json").read_text())
    ev_claude = json.loads((OUT / "events-jump.json").read_text())
    ret = K0.QA_ORDER_RETENTION_V4 if a.archive else None

    def new_canonical():
        logdir = Path(tempfile.mkdtemp(prefix="rp-", dir=OUT))
        tl = IndexedTickTimeline(prov, prov.dataset_id, prov.dataset_version, str(start), log_folder=logdir / "log", log_codec="zlib-1", max_groups_per_advance=256)
        kw = dict(order_retention_policy=ret, qa_order_archive_v1=True) if a.archive else {}
        box = dict(state=seed_state("session:qa", profile, policy(), tl.checkpoint(), **kw), serial=0, ids=set())
        def run_apply(raw, **extra):
            if a.archive:
                lookup = lambda oid: dict(status="CLOSED") if oid in box["ids"] and oid not in box["state"]["orders"] else None
                st, ev, _rows = apply(box["state"], raw, order_retention_policy=ret, qa_order_archive_v1=True, archived_order_lookup=lookup, **extra)
                return st, ev
            return apply(box["state"], raw, **extra)
        def advance(tgt):
            evs = []
            while True:
                frame = tl.advance_through(str(tgt), tl.cursor); cp = tl.checkpoint()
                box["serial"] += 1
                box["state"], ev = run_apply(common.raw_command(box["state"], box["serial"], "ADVANCE", dict(targetNs=str(tgt))), reveal=frame, checkpoint=cp)
                evs.extend(ev)
                if frame["exhaustedThroughBoundary"]:
                    return evs
        def command(kind, payload, cid):
            box["serial"] += 1
            box["state"], ev = run_apply(common.raw_command(box["state"], box["serial"], kind, payload, command=cid))
            if kind == "OPEN":
                box["ids"].add(cid)
            return ev
        return tl, logdir, box, advance, command

    sem = lambda ev: strip_source_specific([x for x in ev if x["kind"] != "REPLAY_ADVANCED"])
    m = Meter("replay")
    tl, logdir, box, advance, command = new_canonical()
    events, upto = [], 0
    for ent in trace:
        if ent[0] == "A":
            tgt = int(ent[1])
            if tgt > win_end:
                break
            events.extend(advance(tgt)); upto = ent[2]
        else:
            _c, kind, payload, cid, evlen = ent
            events.extend(command(kind, payload, cid)); upto = evlen
    tl.close(); shutil.rmtree(logdir, ignore_errors=True)
    res = m.stop(window_ticks=ident["n"], trace_entries_replayed=sum(1 for e in trace if (e[0] == "A" and int(e[1]) <= win_end) or e[0] == "C"),
                 canonical_events=len(events), claude_events_same_prefix=upto, semanticEventsEqual=sem(events) == sem(ev_claude[:upto]),
                 fillsCanonical=sum(e["kind"] in ("ENTRY_FILL", "EXIT_FILL") for e in events), orderAcceptedCanonical=sum(e["kind"] == "ORDER_ACCEPTED" for e in events))
    emit(f"replay-{tag}", res)

    # SEEK parity: one advance across the window with nothing live, canonical vs direct
    m = Meter("seek-parity")
    tl, logdir, box, advance, command = new_canonical()
    t = time.perf_counter(); ev_c = advance(win_end); t_c = time.perf_counter() - t
    sc = box["state"]; tl.close(); shutil.rmtree(logdir, ignore_errors=True)
    src, cprofile, seed, _s, _e, _i = build_claude(a)
    cs = ClaudeSession(src, cprofile, policy(), seed, archive=a.archive)
    t = time.perf_counter(); ev_d = cs.advance_through(win_end); t_d = time.perf_counter() - t
    sd = cs.state
    qb = lambda st: None if st["quoteBasis"] is None else {k: st["quoteBasis"][k] for k in ("timeNs", "bid", "ask")}
    emit(f"seek-parity-{tag}", m.stop(window_ticks=ident["n"], canonical_advance_s=round(t_c, 2), direct_advance_s=round(t_d, 4),
         nextGroupEqual=sc["nextGroupIndex"] == sd["nextGroupIndex"], lastObservedEqual=sc["lastObservedNs"] == sd["lastObservedNs"],
         throughEqual=sc["throughNs"] == sd["throughNs"], quoteBasisPriceTimeEqual=qb(sc) == qb(sd), balanceEqual=sc["balance"] == sd["balance"],
         ordersEqual=sc["orders"] == sd["orders"], semanticEventsEqual=sem(ev_c) == sem(ev_d), canonicalEventKinds=summarize_events(ev_c), directEventKinds=summarize_events(ev_d)))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("phase", choices=["read", "ingest", "claude", "baseline", "compare", "features", "replay"])
    ap.add_argument("--n", type=int, default=None, help="use only the first n ticks (baseline scaling tiers)")
    ap.add_argument("--step-s", type=int, default=300, dest="step_s")
    ap.add_argument("--tp", type=int, default=1500)
    ap.add_argument("--sl", type=int, default=1000)
    ap.add_argument("--show-balance", action="store_true", dest="show_balance")
    ap.add_argument("--standalone", action="store_true", help="Claude-only run with borrowed identity labels")
    ap.add_argument("--archive", action="store_true", help="order retention V4 + terminal order archive (product rule: no 128 cumulative order cap)")
    ap.add_argument("--window", type=int, default=300000, help="ticks of the canonical replay window for jump/seek parity")
    a = ap.parse_args()
    guard()
    os.environ["RMB_ARCHIVE"] = "1" if getattr(a, "archive", False) else "0"
    dict(read=phase_read, ingest=phase_ingest, claude=phase_claude, baseline=phase_baseline, compare=phase_compare,
         features=phase_features, replay=phase_replay)[a.phase](a)
