"""Claude path at scale (compact + jump + reused financial code). The Codex baseline is NOT run here (hours); its cost is
extrapolated elsewhere and labelled as extrapolation. Identity is bound to a small stub canonical store (dataset ids only)."""
import sys, time, json, tempfile, shutil
sys.path.insert(0, ".")
from parity import *
from claude_session import ClaudeSession, AdmittedSource
from market_data.compact_tick import CompactTickReader

n = int(sys.argv[1]); out = dict(n=n)
rows = read_real_rows(n); print("rows", len(rows), flush=True)
work = Path(tempfile.mkdtemp(prefix="b1m-"))
prov, res, _ = ingest_engine(rows[:600], work)               # stub: provides dataset identity + profile + seed checkpoint
profile = make_profile(prov)
tl = IndexedTickTimeline(prov, prov.dataset_id, prov.dataset_version, str(rows[0][0] * 10**6), log_folder=work / "slog"); seed = tl.checkpoint(); tl.close()
first = None
t = IndexedTickTimeline(prov, prov.dataset_id, prov.dataset_version, str(rows[0][0] * 10**6), log_folder=work / "slog2")
fr = t.advance_through(str(rows[3][0] * 10**6), t.cursor); first = fr["groups"][0]["events"][0]; t.close()
adm_parent = dict(datasetId=first["datasetId"], datasetVersion=first["datasetVersion"])
t0, c0 = time.perf_counter(), time.process_time()
m = write_compact(work / "compact", compact_events(rows), parent=adm_parent, scale=3)
print("compact written", flush=True); out["compact_write"] = dict(wall_s=round(time.perf_counter() - t0, 1), cpu_s=round(time.process_time() - c0, 1), bytes=sum(f["bytes"] for f in m["files"]),
                            bytes_per_tick=round(sum(f["bytes"] for f in m["files"]) / n, 2), groups=m["groupCount"], crossed=m["quality"]["crossedQuotes"])
adm = dict(datasetId=first["datasetId"], datasetVersion=first["datasetVersion"], providerId=first["providerId"], feedId=first["feedId"],
           instrumentId=first["instrumentId"], sourceId=first["provenance"]["sourceId"], memberHash=first["provenance"]["memberHash"], manifestHash=m["manifestHash"])
rd = CompactTickReader(work / "compact", expected_manifest_hash=m["manifestHash"])
t0, c0 = time.perf_counter(), time.process_time(); rd.verify_all(deep=True); out["verify_deep"] = dict(wall_s=round(time.perf_counter() - t0, 2), cpu_s=round(time.process_time() - c0, 2))
t0 = time.perf_counter(); a = rd.read_range(0, 2**62); tr = time.perf_counter() - t0; out["pure_read_ticks_per_s"] = round(len(a["ts_ns"]) / tr); del a
t0, c0 = time.perf_counter(), time.process_time(); src = AdmittedSource(work / "compact", adm, expected_manifest_hash=m["manifestHash"])
out["admit_load"] = dict(wall_s=round(time.perf_counter() - t0, 2), cpu_s=round(time.process_time() - c0, 2), groups=src.ngroups, exact_groups_precomputed=int(len(src.exact_idx)))
start, end = rows[0][0] * 10**6, rows[-1][0] * 10**6
CFG = (("swing(step300s,tp1.5,sl1.0)", 300, 1500, 1000), ("scalp(step20s,tp0.15,sl0.10)", 20, 150, 100))
ONLY = os.environ.get("ONLY")
for label, step, tp, sl in [c for c in CFG if not ONLY or c[0].startswith(ONLY)]:
    print("start", label, flush=True)
    cs = ClaudeSession(src, profile, policy(), seed)
    import cProfile, pstats; PR = cProfile.Profile() if len(sys.argv) > 2 else None
    if PR: PR.enable()
    t0, c0 = time.perf_counter(), time.process_time()
    ev = drive(cs.advance_through, lambda k, p, c: cs.command(k, p, c), lambda: cs.state, start, end, step, tp, sl, True)
    wall, cpu = time.perf_counter() - t0, time.process_time() - c0
    if PR:
        PR.disable(); pstats.Stats(PR).sort_stats("tottime").print_stats(16)
    fills = [e for e in ev if e["kind"] in ("ENTRY_FILL", "EXIT_FILL")]
    from contracts.canonical import canonical_bytes
    fb = sum(len(canonical_bytes(e)) for e in fills) / max(len(fills), 1)
    out[label] = dict(wall_s=round(wall, 2), cpu_s=round(cpu, 2), fills=len(fills), unresolved=cs.state["unresolved"], balance=cs.state["balance"], stats=cs.stats,
                      advances=sum(r["t"] == "A" for r in cs.log), session_log_bytes=len(json.dumps(cs.log)), fill_event_canonical_bytes_avg=round(fb),
                      ticks_per_cpu_s=round(n / max(cpu, 1e-9)))
out["peak_rss_mb"] = rss_peak()
print(json.dumps(out, indent=1, default=str)); shutil.rmtree(work, ignore_errors=True)
