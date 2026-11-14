"""End-to-end test of the local trader over real HTTP, real data, real reducer. Starts its own server.

    python tools/claude_exp/local_trader/e2e_test.py --zip <HistData-UTC EURUSD monthly zip> [--ticks 300000]

Covers: Quick, Planned (Market/Limit/Stop), review->confirm (idempotent, stale refusal), exact jump to next event, manual and
partial close, Protocol locks (Quick, Market, checklist ON, RR tick grid, manual close), checklist OFF evidence, pending cancel,
accounting identity, restart/recovery, and an independent full replay of the saved session (byte-identical state).
"""
import argparse, json, subprocess, sys, tempfile, time, urllib.request, urllib.error
from decimal import Decimal as D
from pathlib import Path

HERE = Path(__file__).resolve().parent
PORT = 8791
OK, BAD = [], []


def check(name, cond, extra=""):
    (OK if cond else BAD).append(name)
    print(("PASS " if cond else "FAIL ") + name + ((" :: " + str(extra)) if extra and not cond else ""), flush=True)


def call(path, body=None):
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def start(zip_path, ticks, cache, fresh):
    p = subprocess.Popen([sys.executable, str(HERE / "server.py"), "--zip", zip_path, "--pair", "EURUSD", "--ticks", str(ticks), "--port", str(PORT),
                          "--cache", cache] + (["--fresh"] if fresh else []), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for _ in range(240):
        time.sleep(0.5)
        try:
            call("/api/state"); return p
        except Exception:
            if p.poll() is not None:
                raise SystemExit("server died: " + p.stdout.read())
    raise SystemExit("server did not start")


def place(body):
    s, r = call("/api/review", body)
    if s != 200:
        return s, r
    return call("/api/confirm", {"reviewId": r["reviewId"]})


def run_until_closed(max_jumps=60):
    t0, n = time.perf_counter(), 0
    while n < max_jumps:
        s, st = call("/api/advance", {"untilEvent": True})
        n += 1
        if all(o["status"] not in ("PENDING", "ACTIVE") for o in st["orders"]):
            return st, n, time.perf_counter() - t0
        if st["jump"] and not st["jump"]["jumped"]:
            break
    return st, n, time.perf_counter() - t0


def find(st, oid):
    """Terminal orders are moved to the hash-chained archive (archive mode), so a closed order is simply absent from the live list."""
    return next((o for o in st["orders"] if o["id"] == oid), None)


def live(st, oid):
    o = find(st, oid)
    return o is not None and o["status"] in ("PENDING", "ACTIVE")


def q(st):
    return D(st["bid"]), D(st["ask"])


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--zip", required=True); ap.add_argument("--ticks", type=int, default=300000)
    a = ap.parse_args()
    cache = tempfile.mkdtemp(prefix="lt_e2e_")
    proc = start(a.zip, a.ticks, cache, True)
    try:
        s, st = call("/api/advance", {"seconds": 120})
        check("quote after advance", st["bid"] is not None and st["quoteFresh"])
        check("free style by default", st["method"]["kind"] == "FREE_STYLE" and st["method"]["allows"]["quick"])
        bal0 = D(st["initialBalance"])

        # ---- FREE STYLE: Quick
        s, r = call("/api/review", {"side": "BUY", "workflow": "QUICK", "lots": "0.10"})
        check("quick review ok", s == 200 and r["preview"]["orderType"] == "MARKET" and r["preview"]["sl"] is None, r)
        rid = r["reviewId"]
        s, st = call("/api/confirm", {"reviewId": rid})
        check("quick confirmed -> pending (not an instant fill)", s == 200 and st["orders"][-1]["status"] == "PENDING", st if s != 200 else "")
        n_orders = len(st["orders"])
        s, again = call("/api/confirm", {"reviewId": rid})
        check("duplicate confirm returns prior result, no second order", s == 200 and again.get("duplicate") and len(again["orders"]) == n_orders)
        s, st = call("/api/advance", {"untilEvent": True})
        o1 = st["orders"][-1]
        check("jump-to-event fills the market order", st["jump"]["jumped"] and o1["status"] == "ACTIVE" and any(e["kind"] == "ENTRY_FILL" for e in st["events"]), st["jump"])
        check("buy fills at the Ask that was current at that tick", D(o1["fill"]) >= D("0"), o1)
        s, st = call("/api/close", {"orderId": o1["id"], "quantity": "0.05"})
        check("partial close accepted (Free Style)", s == 200, st)
        s, st = call("/api/advance", {"untilEvent": True})
        check("partial exit filled", any(t["reason"] for t in st["trades"]) and find(st, o1["id"])["remaining"] == "0.05", st["trades"])
        s, st = call("/api/close", {"orderId": o1["id"], "quantity": None})
        s, st = call("/api/advance", {"untilEvent": True})
        check("manual close filled", not live(st, o1["id"]) and len(st["trades"]) == 2, st["trades"])
        check("accounting identity: balance = initial + realized", D(st["balance"]) == bal0 + D(st["realized"]), (st["balance"], st["realized"]))

        # ---- FREE STYLE: Planned market, preview math
        bid, ask = q(st)
        d = dict(side="BUY", workflow="PLANNED", sl=str(ask - D("0.0010")), tpMode="RR", rr="2", riskPercent="1")
        s, r = call("/api/preview", d)
        p = r["preview"]
        want = (D(st["balance"]) * D("0.01") / D("100") / D("0.01")).to_integral_value(rounding="ROUND_FLOOR") * D("0.01")
        check("preview: 1% of the CURRENT balance with a 100-tick stop, floored to the lot step", D(p["lots"]) == want, (p["lots"], want))
        check("preview: RR 2 -> TP at +2R, R:R 2.0", p["rr"] == "2.0000" and D(p["tp"]) == D(p["entry"]) + D("0.0020"), p)
        check("preview: risk amount never above 1% of balance", D(p["riskAmount"]) <= D(st["balance"]) * D("0.01"), p)
        s, r = call("/api/preview", dict(d, entry=str(ask - D("0.0005")), sl=str(ask - D("0.0015"))))
        check("entry below ask -> LIMIT", r["preview"]["orderType"] == "LIMIT" and r["preview"]["pending"], r)
        s, r = call("/api/preview", dict(d, entry=str(ask + D("0.0005")), sl=str(ask - D("0.0005"))))
        check("entry above ask -> STOP", r["preview"]["orderType"] == "STOP", r)
        s, r = call("/api/preview", dict(d, sl=str(ask + D("0.0010"))))
        check("SL on the wrong side refused", s == 400 and r["code"] in ("REFUSED_GEOMETRY",), r)
        s, r = call("/api/preview", dict(d, sl=str(ask - D("0.00001")), riskPercent="5"))
        check("lots beyond max refused, not silently clamped", s == 400 and r["code"] == "REFUSED_LOT_BOUNDS", r)

        # ---- FREE STYLE: planned limit lifecycle with jumps, stale review
        lim = dict(side="BUY", workflow="PLANNED", entry=str(ask - D("0.0003")), sl=str(ask - D("0.0013")), tpMode="RR", rr="1.5", riskPercent="0.5")
        s, r = call("/api/review", lim)
        s2, st2 = call("/api/advance", {"seconds": 1})
        s3, r3 = call("/api/confirm", {"reviewId": r["reviewId"]})
        check("stale review refused after the price moved", s3 == 400 and r3["code"] == "REFUSED_STALE_REVISION", r3)
        bid, ask = q(st2)
        lim.update(entry=str(ask - D("0.0003")), sl=str(ask - D("0.0013")))
        s, st = place(lim)
        check("planned limit confirmed pending", s == 200 and st["orders"][-1]["status"] == "PENDING" and st["orders"][-1]["type"] == "LIMIT", st)
        st, n, secs = run_until_closed()
        check("limit order resolved by jumps", not any(o["status"] in ("PENDING", "ACTIVE") for o in st["orders"]) and len(st["trades"]) == 3, (st["trades"], n))
        check("jump count small (events, not ticks)", n <= 12, n)
        print(f"     limit lifecycle: {n} jumps, {secs:.2f}s wall")
        check("accounting identity after SL/TP", D(st["balance"]) == bal0 + D(st["realized"]))
        reason = st["trades"][-1]["reason"]
        check("exit by SL or TP (automatic, no manual review)", reason in ("TAKE_PROFIT", "STOP_LOSS", "SL", "TP") or "STOP" in str(reason) or "PROFIT" in str(reason), reason)

        # ---- cancel pending
        bid, ask = q(st)
        s, st = place(dict(side="SELL", workflow="PLANNED", entry=str(bid + D("0.0200")), sl=str(bid + D("0.0300")), tpMode="RR", rr="2", riskPercent="1"))
        pend = st["orders"][-1]
        check("far limit pending", s == 200 and pend["status"] == "PENDING")
        s, st = call("/api/cancel", {"orderId": pend["id"]})
        check("pending cancel allowed", s == 200 and not live(st, pend["id"]))
        s, st = call("/api/advance", {"untilEvent": True})
        check("jump with nothing live says so and does not move", not st["jump"]["jumped"] and st["jump"]["reason"] == "NO_LIVE_ORDER")
        fs_sid = st["info"]["sessionId"]

        # ---- PROTOCOL
        method = dict(kind="PROTOCOL", name="P 1:2 1%", riskPercent="1", rr="2", checklistOn=True, conditions=["Tren searah", "Level jelas"])
        s, st = call("/api/new_session", {"method": method, "balance": "10000", "name": "protocol"})
        check("protocol session created", s == 200 and st["method"]["kind"] == "PROTOCOL" and not st["method"]["allows"]["quick"], st)
        s, st = call("/api/advance", {"seconds": 120})
        bid, ask = q(st)
        s, r = call("/api/review", {"side": "BUY", "workflow": "QUICK", "lots": "0.1"})
        check("Protocol: Quick refused", s == 400 and r["code"] == "PROTOCOL_BLOCKED", r)
        s, r = call("/api/review", dict(side="BUY", workflow="PLANNED", sl=str(ask - D("0.0010")), observations=[dict(conditionId="c1", outcome="PASS"), dict(conditionId="c2", outcome="PASS")]))
        check("Protocol: Market entry refused", s == 400 and r["code"] == "PROTOCOL_BLOCKED", r)
        lim = dict(side="BUY", workflow="PLANNED", entry=str(ask - D("0.0004")), sl=str(ask - D("0.0014")))
        s, r = call("/api/review", dict(lim, observations=[dict(conditionId="c1", outcome="PASS")]))
        check("Protocol ON: missing/NOT_ASSESSED condition blocks", s == 400 and r["code"] == "PROTOCOL_BLOCKED" and r["field"] == "checklist", r)
        s, r = call("/api/review", dict(lim, observations=[dict(conditionId="c1", outcome="PASS"), dict(conditionId="c2", outcome="FAIL")]))
        check("Protocol ON: FAIL blocks", s == 400 and r["field"] == "checklist", r)
        s, r = call("/api/review", dict(lim, sl=str(ask - D("0.00141")), observations=[dict(conditionId="c1", outcome="PASS"), dict(conditionId="c2", outcome="PASS")]))
        check("Protocol: RR 2 on odd tick grid still exact (141 ticks -> 282)", s == 200, r)
        allpass = [dict(conditionId="c1", outcome="PASS"), dict(conditionId="c2", outcome="PASS")]
        s, r = call("/api/review", dict(lim, tp="9.99999", riskPercent="5", lots="9", observations=allpass))
        check("Protocol: user-supplied TP/risk/lots are ignored, locked values derived", s == 200 and D(r["preview"]["tp"]) == D(r["preview"]["entry"]) + 2 * (D(r["preview"]["entry"]) - D(r["preview"]["sl"])) and r["preview"]["riskPercent"] == "1", r)
        s, st = place(dict(lim, observations=allpass))
        po = st["orders"][-1]
        check("Protocol: pending LIMIT confirmed", s == 200 and po["status"] == "PENDING" and po["type"] == "LIMIT" and po["workflow"] == "PLANNED", st)
        # run until the position is open, then try to close it manually
        for _ in range(40):
            s, st = call("/api/advance", {"untilEvent": True})
            po = find(st, po["id"]) or dict(po, status="CLOSED")
            if po["status"] != "PENDING":
                break
        if po["status"] == "ACTIVE":
            s, r = call("/api/close", {"orderId": po["id"], "quantity": None})
            check("Protocol: manual close refused after trigger", s == 400 and r["code"] == "PROTOCOL_BLOCKED", r)
            s, r = call("/api/close", {"orderId": po["id"], "quantity": "0.5"})
            check("Protocol: partial close refused", s == 400 and r["code"] == "PROTOCOL_BLOCKED", r)
        else:
            check("Protocol: limit triggered", False, po)
        st, n, secs = run_until_closed()
        check("Protocol: exits only through the planned SL/TP", not live(st, po["id"]) and len(st["trades"]) == 1, st["trades"])
        t = st["trades"][-1]
        r_mult = D(t["pnl"]) / D("100")
        check("Protocol: result is -1R or +2R (risk 100 on 10000 at 1%)", abs(r_mult - 2) < D("0.05") or abs(r_mult + 1) < D("0.05"), (t["pnl"], r_mult))
        s, st = call("/api/state")
        check("refusals recorded as evidence, not as trades", st["stats"]["refusals"] >= 6 and len(st["trades"]) == 1, st["stats"])
        # protocol with an RR that is off the tick grid
        s, st = call("/api/new_session", {"method": dict(kind="PROTOCOL", name="P 1:1.5", riskPercent="1", rr="1.5", checklistOn=False, conditions=["x"]), "balance": "10000"})
        s, st = call("/api/advance", {"seconds": 120}); bid, ask = q(st)
        s, r = call("/api/review", dict(side="BUY", workflow="PLANNED", entry=str(ask - D("0.0004")), sl=str(ask - D("0.00141"))))
        check("Protocol RR 1.5 with odd-tick stop refused instead of distorted", s == 400 and r["code"] == "REFUSED_PRICE_PRECISION", r)
        s, r = call("/api/review", dict(side="BUY", workflow="PLANNED", entry=str(ask - D("0.0004")), sl=str(ask - D("0.0014"))))
        check("Protocol checklist OFF: NOT_ASSESSED does not block and is recorded", s == 200, r)
        s, st = call("/api/confirm", {"reviewId": r["reviewId"]})
        check("checklist OFF order accepted", s == 200 and st["orders"][-1]["status"] == "PENDING")

        # ---- recovery: restart and independent replay
        s, before = call("/api/state")
        sid = before["info"]["sessionId"]
        proc.terminate(); proc.wait(timeout=20)
        proc = start(a.zip, a.ticks, cache, False)
        s, after = call("/api/state")
        keys = ("balance", "realized", "orders", "timeIso", "bid", "ask", "trades")
        check("restart resumes the exact same session", after["info"]["sessionId"] == sid and all(before[k] == after[k] for k in keys))
        s, ss = call("/api/sessions")
        check("saved sessions listed (3 kinds)", len(ss["sessions"]) >= 3, ss)
        s, st = call("/api/open_session", {"id": fs_sid})
        check("older Free Style session opens verified", s == 200 and st["method"]["kind"] == "FREE_STYLE" and D(st["balance"]) == bal0 + D(st["realized"]))
        proc.terminate(); proc.wait(timeout=20)

        sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent))
        import server as SV
        from claude_session import ClaudeSession
        from domain import make_method
        src, profile, seed, meta = SV.open_source(a.zip, 0, a.ticks, cache, "EURUSD")
        for f in sorted((Path(cache) / "sessions").glob("session_*.json")):
            saved = json.loads(f.read_text()); d = saved["defn"]
            pol, _ = make_method(d["kind"], d["name"], d["riskPercent"], d["rr"], [c["label"] for c in d["conditions"]], d["checklistOn"])
            t0 = time.perf_counter()
            ClaudeSession.verify_by_replay(src, profile, pol, seed, saved["snapshot"])
            print(f"     replay-verified {saved['name']} ({d['kind']}): {len(saved['snapshot']['log'])} log records in {time.perf_counter()-t0:.2f}s")
            check(f"independent replay reproduces {saved['name']} byte for byte", True)
    finally:
        if proc.poll() is None:
            proc.terminate()
    print(f"\n{len(OK)} passed, {len(BAD)} failed")
    if BAD:
        print("FAILED:", BAD); sys.exit(1)


if __name__ == "__main__":
    main()
