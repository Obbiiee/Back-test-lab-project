"""Integrity / recovery proofs for the Claude architecture (real XAUUSD ticks)."""
import sys, os, json, shutil, copy, hashlib
sys.path.insert(0, ".")
from parity import *
from claude_session import AdmittedSource, ClaudeSession
from market_data.compact_tick import CompactTickReader

n = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
r = run(n, "clean", mix=True)
src, profile, seed, rows, cdir, m, groups = r["_src"], r["_profile"], r["_seed"], r["_rows"], r["_cdir"], r["_manifest"], r["_groups"]
adm = src.adm; mh = m["manifestHash"]
start, end = rows[0][0] * 10**6, rows[-1][0] * 10**6
res = {}

def fresh(source=src):
    return ClaudeSession(source, profile, policy(), seed)

def full(cs, upto=None, step_s=300):
    return drive(cs.advance_through, lambda k, p, c: cs.command(k, p, c), lambda: cs.state, start, upto or end, step_s, 1500, 1000, True)

# ---- 1. uninterrupted reference
ref = fresh(); ref_events = full(ref)
res["reference"] = dict(balance=ref.state["balance"], events=len(ref_events), tip=ref.tip[:16])

# ---- 2. worker restart mid-session: snapshot -> JSON round trip -> NEW process-like reload of the compact source -> recover -> continue
half = start + (end - start) // 2
a = fresh(); ev_a = full(a, upto=half)
snap = json.loads(json.dumps(a.snapshot()))          # persisted form
src2 = AdmittedSource(cdir, adm, expected_manifest_hash=mh, deep_verify=True)   # cold reload, deep hash verification
b = ClaudeSession.recover(src2, profile, policy(), seed, snap)
# continue the SAME trader from the recovered state: drive() restarts its own counters, so replay it identically instead:
cont = drive(b.advance_through, lambda k, p, c: b.command(k, p, c), lambda: b.state, start, end, 300, 1500, 1000, True) if False else None
# simple, exact continuation check: recovered state equals the pre-restart state, then both advance identically
res["recovery_state_equal"] = (b.state == a.state and b.tip == a.tip and b.log == a.log)
t = half + 3600 * 10**9
ea, eb = a.advance_through(t), b.advance_through(t)
res["recovery_continue_equal"] = (ea == eb and a.state == b.state and a.tip == b.tip)

# ---- 3. corruption / tamper cases (each must be REFUSED, never silently accepted)
def expect_refusal(label, fn):
    try:
        fn(); res[label] = "ACCEPTED (BAD)"
    except Exception as e:
        res[label] = "refused: " + type(e).__name__ + ": " + str(e)[:80]

files = sorted((cdir).rglob("*.parquet"))
target = files[0]; raw = bytearray(target.read_bytes())
# (a) flip one byte inside a parquet file
raw[len(raw) // 2] ^= 0x01
bad = cdir.parent / "compact_flip"; shutil.copytree(cdir, bad)
(bad / target.relative_to(cdir)).write_bytes(bytes(raw))
expect_refusal("flip_byte_in_parquet", lambda: AdmittedSource(bad, adm, expected_manifest_hash=mh))
# (b) manifest edited
bad2 = cdir.parent / "compact_manifest"; shutil.copytree(cdir, bad2)
mp = bad2 / "compact.json"; txt = mp.read_text(); mp.write_text(txt.replace('"eventCount"', '"eventCount "', 1) if '"eventCount"' in txt else txt + " ")
expect_refusal("edited_manifest", lambda: AdmittedSource(bad2, adm, expected_manifest_hash=mh))
# (c) pinned to a different manifest hash (wrong dataset version)
expect_refusal("wrong_pinned_manifest_hash", lambda: AdmittedSource(cdir, adm, expected_manifest_hash="0" * 64))
# (d) advance log tampered
s2 = copy.deepcopy(snap); s2["log"][3]["fin"] = "0" * 64
expect_refusal("tampered_advance_log", lambda: ClaudeSession.recover(src2, profile, policy(), seed, s2))
# (e) log truncated but state claims more progress
s3 = copy.deepcopy(snap); s3["log"] = s3["log"][:-2]
expect_refusal("truncated_advance_log", lambda: ClaudeSession.recover(src2, profile, policy(), seed, s3))
# (f) saved state edited (balance) while chain intact -> chain still matches, so this must be caught by state validation/hash
s4 = copy.deepcopy(snap); s4["state"]["balance"] = "99999.00"
expect_refusal("tampered_balance_in_state", lambda: ClaudeSession.recover(src2, profile, policy(), seed, s4))
expect_refusal("tampered_balance_caught_by_replay", lambda: ClaudeSession.verify_by_replay(src2, profile, policy(), seed, s4))
res["replay_verification_of_honest_snapshot"] = bool(ClaudeSession.verify_by_replay(src2, profile, policy(), seed, snap))
s5 = copy.deepcopy(snap); s5["state"]["lastObservedNs"] = str(int(s5["state"]["lastObservedNs"]) - 1)
expect_refusal("tampered_last_observed", lambda: ClaudeSession.recover(src2, profile, policy(), seed, s5))
s6 = copy.deepcopy(snap)
if s6["state"]["quoteBasis"] is not None:
    s6["state"]["quoteBasis"]["groupId"] = "f" * 64
    expect_refusal("tampered_quote_basis", lambda: ClaudeSession.recover(src2, profile, policy(), seed, s6))
# (g) reconstruction rule vs canonical truth: one quote altered in the compact file's source rows -> admission mismatch must be >0
alt = list(rows); ts, ask, bid = alt[5000]; alt[5000] = (ts, f"{float(ask)+1:.3f}", f"{float(bid)+1:.3f}")
from market_data.compact_tick import write_compact
cd2 = cdir.parent / "compact_alt"
m2 = write_compact(cd2, compact_events(alt), parent=dict(datasetId=adm["datasetId"], datasetVersion=adm["datasetVersion"]), scale=3)
adm2 = dict(adm, manifestHash=m2["manifestHash"])
src3 = AdmittedSource(cd2, adm2, expected_manifest_hash=m2["manifestHash"])
mm = sum(1 for g, grp in enumerate(groups) if src3.canonical_group(g) != grp)
res["altered_quote_detected_by_admission_verification"] = mm >= 1; res["altered_groups_found"] = mm

print(json.dumps(res, indent=1))
shutil.rmtree(r["_work"], ignore_errors=True)
