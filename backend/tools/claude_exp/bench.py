"""Stage-separated benchmark, identical input for every candidate. Real XAUUSD ticks. Quiet machine assumed."""
import sys, time, json, shutil
sys.path.insert(0, ".")
from parity import *
from claude_session import ClaudeSession, AdmittedSource
from market_data.compact_tick import CompactTickReader
from contracts.canonical import canonical_bytes

n = int(sys.argv[1]); mix = True
r = run(n, "clean", mix=mix)
cs, src, profile, seed, rows, cdir, m, groups = (r.pop(k) for k in ("_cs", "_src", "_profile", "_seed", "_rows", "_cdir", "_manifest", "_groups"))
work = r.pop("_work")
out = dict(n=n, ticks_groups=src.ngroups)
out["stage_ingest_canonical_s"] = r["ingest_engine_s"]
out["stage_compact_write_s"] = r["compact_write_s"]
out["storage_bytes"] = dict(compact=r["compact_bytes"])
# dataset verification
t0 = time.process_time(); CompactTickReader(cdir, expected_manifest_hash=m["manifestHash"]).verify_all(deep=False); out["stage_verify_files_hash_cpu_s"] = round(time.process_time() - t0, 3)
t0 = time.process_time(); CompactTickReader(cdir, expected_manifest_hash=m["manifestHash"]).verify_all(deep=True); out["stage_verify_deep_cpu_s"] = round(time.process_time() - t0, 3)
# pure reader
rd = CompactTickReader(cdir, expected_manifest_hash=m["manifestHash"])
t0 = time.perf_counter(); a = rd.read_range(0, 2**62); tr = time.perf_counter() - t0
out["stage_pure_read_ticks_per_s"] = round(len(a["ts_ns"]) / max(tr, 1e-9))
out["stage_admission_reconstruction_verify_s"] = r["admission_verify_s"]; out["reconstruction_mismatches"] = r["admission_reconstruction_mismatches"]
# full financial execution
out["exec_baseline"] = r["baseline"]; out["exec_claude"] = r["claude"]
out["parity"] = r["parity"]
# canonical engine store size
store = work / "store"
out["storage_bytes"]["canonical_engine_store"] = sum(f.stat().st_size for f in store.rglob("*") if f.is_file())
# baseline timeline log + resume (cold), measured on the same data without the kernel
import tempfile
start, end = rows[0][0] * 10**6, rows[-1][0] * 10**6
prov = DiskTickProvider(store, groups[0]["events"][0]["datasetVersion"])
lf = Path(tempfile.mkdtemp(prefix="blog-"))
tl = IndexedTickTimeline(prov, prov.dataset_id, prov.dataset_version, str(start), log_folder=lf, max_groups_per_advance=256)
cpu0 = time.process_time()
while True:
    tl.advance_through(str(end), tl.cursor); c = tl.checkpoint()["cursor"]
    if int(c["throughNs"]) >= end and c["pendingTargetNs"] is None: break
adv_cpu = time.process_time() - cpu0; cp = tl.checkpoint(); tl.close()
cpu0, t0 = time.process_time(), time.perf_counter()
rr = IndexedTickTimeline.resume(prov, cp, log_folder=lf, max_groups_per_advance=256); res_wall = time.perf_counter() - t0; res_cpu = time.process_time() - cpu0; rr.close()
out["baseline_timeline_only"] = dict(advance_cpu_s=round(adv_cpu, 2), cold_resume_cpu_s=round(res_cpu, 2), cold_resume_wall_s=round(res_wall, 2),
                                    log_bytes=sum(f.stat().st_size for f in lf.rglob("*") if f.is_file()))
# claude recovery (cold)
snap = json.loads(json.dumps(cs.snapshot()))
out["claude_session_log_bytes"] = len(json.dumps(snap["log"]))
cpu0, t0 = time.process_time(), time.perf_counter()
src2 = AdmittedSource(cdir, r_adm := src.adm, expected_manifest_hash=m["manifestHash"])
c2 = ClaudeSession.recover(src2, profile, policy(), seed, snap)
out["claude_cold_recover_chain"] = dict(cpu_s=round(time.process_time() - cpu0, 3), wall_s=round(time.perf_counter() - t0, 3))
cpu0, t0 = time.process_time(), time.perf_counter()
ClaudeSession.verify_by_replay(src2, profile, policy(), seed, snap)
out["claude_cold_recover_full_replay"] = dict(cpu_s=round(time.process_time() - cpu0, 3), wall_s=round(time.perf_counter() - t0, 3))
# per-trade durable bytes (canonical event bytes of the financial events)
evs = [e for e in cs.state.get("_events", [])]
out["note_pg"] = "PostgreSQL not run here; event_bytes is the canonical size of ENTRY/EXIT fill events as a proxy"
shutil.rmtree(work, ignore_errors=True); shutil.rmtree(lf, ignore_errors=True)
out["peak_rss_mb"] = rss_peak()
print(json.dumps(out, indent=1, default=str))
