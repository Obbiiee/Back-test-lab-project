"""Codex baseline: real ticks -> canonical store -> IndexedTickTimeline -> REAL observed_kernel.apply (financial reducer)."""
import sys, time, json, tempfile, shutil
from pathlib import Path
from common import *

def run_baseline(provider, rows, step_s=300, tp=1500, sl=1000, log_codec="zlib-1", collect=None, mix=False, archive=False, symbol="XAUUSD"):
    work = Path(tempfile.mkdtemp(prefix="bl-"))
    profile = make_profile(provider, symbol)
    start = rows[0][0] * 1_000_000; end = rows[-1][0] * 1_000_000
    tl = IndexedTickTimeline(provider, provider.dataset_id, provider.dataset_version, str(start), log_folder=work / "log",
                             log_codec=log_codec, max_groups_per_advance=256)
    import execution.observed_kernel as K0
    ret = K0.QA_ORDER_RETENTION_V4 if archive else None
    box = dict(state=seed_state("session:qa", profile, policy(), tl.checkpoint(), **(dict(order_retention_policy=ret, qa_order_archive_v1=True) if archive else {})), serial=0, ids=set())
    def run_apply(raw, **kw):
        if archive:
            lookup = lambda oid: dict(status="CLOSED") if oid in box["ids"] and oid not in box["state"]["orders"] else None
            st, ev, _rows = apply(box["state"], raw, order_retention_policy=ret, qa_order_archive_v1=True, archived_order_lookup=lookup, **kw)
            return st, ev
        return apply(box["state"], raw, **kw)
    def advance(target):
        evs = []
        while True:
            frame = tl.advance_through(str(target), tl.cursor); cp = tl.checkpoint()
            if collect is not None: collect.extend(frame["groups"])
            box["serial"] += 1
            box["state"], ev = run_apply(raw_command(box["state"], box["serial"], "ADVANCE", dict(targetNs=str(target))), reveal=frame, checkpoint=cp)
            evs.extend(ev)
            if frame["exhaustedThroughBoundary"]: return evs
    def command(kind, payload, cid):
        box["serial"] += 1
        box["state"], ev = run_apply(raw_command(box["state"], box["serial"], kind, payload, command=cid))
        if kind == "OPEN": box["ids"].add(cid)
        return ev
    cpu0, t0 = time.process_time(), time.perf_counter()
    events_all = drive(advance, command, lambda: box["state"], start, end, step_s, tp, sl, mix)
    cpu, wall = time.process_time() - cpu0, time.perf_counter() - t0
    tl.close(); shutil.rmtree(work, ignore_errors=True)
    return dict(state=box["state"], events=events_all, cpu=cpu, wall=wall)

if __name__ == "__main__":
    n = int(sys.argv[1]); rows = read_real_rows(n)
    work = tempfile.mkdtemp(prefix="blsrc-")
    provider, res, t_ing = ingest_engine(rows, work)
    print(f"ingest {t_ing:.1f}s accepted {res['acceptedRows']}")
    r = run_baseline(provider, rows)
    fills = [e for e in r["events"] if e["kind"] in ("ENTRY_FILL", "EXIT_FILL")]
    print(f"baseline cpu {r['cpu']:.1f}s wall {r['wall']:.1f}s events {len(r['events'])} fills {len(fills)} balance {r['state']['balance']} unresolved {r['state']['unresolved']}")
    print(json.dumps(fills[0], default=str)[:700])
    print(json.dumps(strip_source_specific(fills[:2]), default=str))
    shutil.rmtree(work, ignore_errors=True)
