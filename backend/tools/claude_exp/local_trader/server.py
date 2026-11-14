"""Local manual-trading app on the Claude engine (QA/prototype, single user, no PostgreSQL).

    py -m tools.claude_exp.local_trader.server --zip <monthly zip> --pair EURUSD --ticks 400000 --offset 0

Everything financial goes through the reference reducer (observed_kernel); this file only serves the UI. The browser never
receives a tick or candle after the session cursor (no look-ahead): candles are built server-side from revealed ticks only.
Trading methods follow docs/TRADING_METHOD_SESSION_SPEC.md: FREE_STYLE (Quick + Planned) and PROTOCOL (Planned pending only,
locked risk and RR, checklist ON/OFF). Rules are enforced by the product's own contracts (see domain.py), not re-implemented.
Execution model: observed quotes only, no slippage/commission.
"""
import argparse, hashlib, json, os, sys, tempfile, threading, time
from decimal import Decimal
from fractions import Fraction
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
from common import *                        # noqa: E402  (stubs psycopg, adds backend to sys.path)
from claude_session import AdmittedSource, ClaudeSession    # noqa: E402
from market_data.compact_tick import write_compact          # noqa: E402
from contracts.primitives import ContractError              # noqa: E402
from domain import build, make_method, method_view          # noqa: E402
import numpy as np                                          # noqa: E402

LOCK = threading.Lock()
S = {}
SESS_DIR = None


def build_histdata(zip_path, pair, offset, ticks, cache):
    import re
    month = re.search(r"_T(\d{6})", Path(zip_path).name).group(1)
    mh = histdata_member_hash(zip_path)
    key = hashlib.sha256(f"{mh}|{pair}|{offset}|{ticks}".encode()).hexdigest()[:16]
    root = Path(cache) / key
    meta_path = root / "meta.json"
    if meta_path.exists():
        return root, json.loads(meta_path.read_text())
    rows = read_histdata_rows(zip_path, ticks, offset)
    print(f"[data] {pair} {len(rows)} HistData-UTC ticks -> compact (one time)", flush=True)
    ds = f"local:histdata-utc:{pair}:{month}:{mh[:24]}"
    dv = hashlib.sha256(f"{ds}|{offset}|{ticks}".encode()).hexdigest()
    root.mkdir(parents=True, exist_ok=True)
    m = write_compact(root / "compact", ({"timeNs": str(ts * 1_000_000), "bid": bid, "ask": ask, "rawOrdinal": str(i)}
                                         for i, (ts, ask, bid) in enumerate(rows)), parent=dict(datasetId=ds, datasetVersion=dv), scale=5)
    adm = dict(datasetId=ds, datasetVersion=dv, providerId="histdata", feedId="local-unverified:" + pair, instrumentId="histdata:" + pair,
               sourceId="histdata:utc:" + mh[:24], memberHash=mh, manifestHash=m["manifestHash"], scale=100000, kind="histdata-utc")
    meta = dict(adm=adm, start_ms=rows[0][0], end_ms=rows[-1][0], ticks=len(rows), seed=genesis_checkpoint(ds, dv, rows[0][0] * 10**6), pair=pair)
    meta_path.write_text(json.dumps(meta))
    return root, meta


def build_dataset(zip_path, offset, ticks, cache):
    key = hashlib.sha256(f"{Path(zip_path).name}|{offset}|{ticks}".encode()).hexdigest()[:16]
    root = Path(cache) / key
    meta_path = root / "meta.json"
    if meta_path.exists():
        return root, json.loads(meta_path.read_text())
    os.environ["XAU_TICK_ZIP"] = str(zip_path)
    rows = read_real_rows(offset + ticks)[offset:]
    print(f"[data] {len(rows)} real ticks -> compact (one time)", flush=True)
    root.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="lt-stub-"))
    prov, res, _ = ingest_engine(rows[:600], work)      # stub canonical store: only provides dataset identity + profile
    tl = IndexedTickTimeline(prov, prov.dataset_id, prov.dataset_version, str(rows[0][0] * 10**6), log_folder=work / "l")
    seed_cp = tl.checkpoint()
    fr = tl.advance_through(str(rows[3][0] * 10**6), tl.cursor)
    first = fr["groups"][0]["events"][0]
    tl.close()
    parent = dict(datasetId=first["datasetId"], datasetVersion=first["datasetVersion"])
    m = write_compact(root / "compact", ({"timeNs": str(ts * 1_000_000), "bid": bid, "ask": ask, "rawOrdinal": str(i)}
                                         for i, (ts, ask, bid) in enumerate(rows)), parent=parent, scale=3)
    meta = dict(adm=dict(datasetId=first["datasetId"], datasetVersion=first["datasetVersion"], providerId=first["providerId"],
                         feedId=first["feedId"], instrumentId=first["instrumentId"], sourceId=first["provenance"]["sourceId"],
                         memberHash=first["provenance"]["memberHash"], manifestHash=m["manifestHash"]),
                start_ms=rows[0][0], end_ms=rows[-1][0], ticks=len(rows), seed=seed_cp)
    meta_path.write_text(json.dumps(meta))
    return root, meta


def open_source(zip_path, offset, ticks, cache, pair="XAUUSD", silence_s=300):
    root, meta = build_dataset(zip_path, offset, ticks, cache) if pair == "XAUUSD" else build_histdata(zip_path, pair, offset, ticks, cache)
    meta.setdefault("pair", "XAUUSD")
    os.environ["XAU_TICK_ZIP"] = str(zip_path)
    adm = meta["adm"]
    src = AdmittedSource(root / "compact", adm, expected_manifest_hash=adm["manifestHash"], deep_verify=True)
    primary = dict(datasetId=adm["datasetId"], datasetVersion=adm["datasetVersion"], providerId=adm["providerId"],
                   feedId=adm["feedId"], feedInstrumentId=adm["instrumentId"], providerSymbol="XAUUSD", evidenceClass="PROVIDER_OBSERVATION")
    if pair == "XAUUSD":
        profile_raw = json.loads(json.dumps(PROFILE)); profile_raw["primary"] = primary
    else:
        import fx_profile
        fx_profile.install()
        profile_raw = fx_profile.fx_profile_wire(PROFILE, pair, primary, silence_s)
    profile = ObservedExecutionProfile.from_wire(profile_raw)
    return src, profile, meta["seed"], meta


def method_json():
    return method_view(S["defn"], S["policy"])


def stats():
    tr = [float(t["pnl"]) for t in S["trades"] if t.get("pnl") is not None]
    wins = [x for x in tr if x > 0]
    return dict(exits=len(tr), wins=len(wins), losses=len([x for x in tr if x < 0]), net=f"{sum(tr):.2f}",
                winRate=None if not tr else f"{len(wins) / len(tr) * 100:.0f}%", refusals=len(S["refusals"]))


def session_json():
    cs, src = S["cs"], S["src"]
    st = cs.state
    k = int(st["nextGroupIndex"])
    bid = ask = None
    sc, dec = src.scale, len(str(src.scale)) - 1
    contract = Fraction(st["profile"]["contractSize"])
    if k:
        bid, ask = int(src.gbid[k - 1]), int(src.gask[k - 1])
    orders = []
    for oid, o in st["orders"].items():
        row = dict(id=oid, side=o["side"], type=o["orderType"], status=o["status"], lots=o["quantity"], entry=o["entry"], sl=o["sl"], tp=o["tp"],
                   fill=o["entryPrice"], pnl=o["grossPosted"], remaining=o["remaining"], workflow=o.get("workflow"),
                   exitRequested=o.get("exitRequest") is not None)
        if o["status"] == "ACTIVE" and bid is not None:
            px = Fraction(bid, sc) if o["side"] == "LONG" else Fraction(ask, sc)
            e = Fraction(o["entryPrice"])
            d = 1 if o["side"] == "LONG" else -1
            row["floating"] = f"{float((px - e) * d * contract * Fraction(o['remaining'])):.2f}"
        orders.append(row)
    thr = int(st["throughNs"])
    nxt = cs.next_event_ns()
    pr = st["profile"]
    return dict(time=thr // 1_000_000, timeIso=time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(thr / 1e9)),
                balance=st["balance"], initialBalance=st["initialBalance"], realized=st["realizedGross"],
                bid=None if bid is None else f"{bid/sc:.{dec}f}",
                ask=None if ask is None else f"{ask/sc:.{dec}f}", spread=None if bid is None else f"{(ask-bid)/sc:.{dec}f}",
                info=dict(symbol=S["meta"]["pair"], dec=dec, tick=pr["tickSize"], contract=pr["contractSize"], lotStep=pr["lotStep"], minLot=pr["minLot"],
                          maxLot=pr["maxLot"], defLot="0.01", silenceSeconds=int(pr["maxObservedSilenceNs"]) // 10**9, sessionName=S["name"], sessionId=S["sid"]),
                method=method_json(), stats=stats(), refusals=S["refusals"][-12:],
                unresolved=st["unresolved"], ended=st["ended"], orders=orders,
                quoteFresh=bool(st["quoteBasis"] is not None and thr - int(st["quoteBasis"]["timeNs"]) <= int(st["profile"]["maxObservedSilenceNs"])),
                progress=dict(group=k, groups=src.ngroups, startMs=S["meta"]["start_ms"], endMs=S["meta"]["end_ms"]),
                nextEvent=None if nxt is None else dict(timeMs=nxt // 1_000_000, inSeconds=max(0, (nxt - thr) // 10**9)),
                atEnd=k >= src.ngroups, events=S["events"][-40:], trades=S["trades"][-40:], model="observed quotes only; no slippage/commission")


def candles(tf, n):
    cs, src = S["cs"], S["src"]
    k = int(cs.state["nextGroupIndex"])
    if k == 0:
        return []
    last_tick = int(src.gend[k - 1])                     # only ticks of groups already revealed
    ts = src.ts[:last_tick]
    lo = max(0, int(np.searchsorted(ts, ts[-1] - n * tf * 10**9)))
    t, bid = ts[lo:], src.bid[lo:last_tick]
    bucket = t // (tf * 10**9)
    first = np.flatnonzero(np.r_[True, bucket[1:] != bucket[:-1]])
    out = []
    for a, b in zip(first, np.r_[first[1:], len(t)]):
        seg = bid[a:b]
        out.append([int(bucket[a]) * tf, float(seg[0]) / src.scale, float(seg.max()) / src.scale, float(seg.min()) / src.scale, float(seg[-1]) / src.scale])
    return out[-n:]


def log_events(evs):
    for e in evs:
        if e["kind"] == "REPLAY_ADVANCED":
            continue
        d = e.get("detail") or {}
        d = d if isinstance(d, dict) else {}
        oid, now = e.get("orderId"), int(S["cs"].state["throughNs"]) // 1_000_000
        S["events"].append(dict(kind=e["kind"], orderId=oid, price=d.get("price"), reason=d.get("reason"), pnl=d.get("grossPosted"), timeMs=now))
        if e["kind"] == "ENTRY_FILL":
            S["meta_orders"].setdefault(oid, {})["entry"] = d.get("price")
        elif e["kind"] == "EXIT_FILL":
            m = S["meta_orders"].get(oid, {})
            S["trades"].append(dict(id=oid, side=m.get("side"), lots=d.get("quantity"), entry=m.get("entry"), exit=d.get("price"),
                                    pnl=d.get("grossPosted"), reason=d.get("reason"), timeMs=now))


def session_file(sid):
    return SESS_DIR / (sid.replace(":", "_") + ".json")


def save():
    session_file(S["sid"]).write_text(json.dumps(dict(
        sid=S["sid"], name=S["name"], dataset=S["meta"]["adm"]["manifestHash"], defn=S["defn"], balance=S["cs"].state["initialBalance"],
        savedMs=int(time.time() * 1000), snapshot=S["cs"].snapshot(), events=S["events"], trades=S["trades"], meta_orders=S["meta_orders"],
        refusals=S["refusals"], serial=S.get("serial", 0))))


def new_session(defn_in, balance, name):
    """A session inherits its method. The method is immutable after this call (its hash is part of the session's identity)."""
    kind = defn_in["kind"]
    policy, defn = make_method(kind, defn_in.get("name") or ("Free Style" if kind == "FREE_STYLE" else "Protocol"),
                               defn_in.get("riskPercent"), defn_in.get("rr"), defn_in.get("conditions") or [], defn_in.get("checklistOn", False))
    bal = f"{Decimal(str(balance)):f}"
    if not (Decimal("100") <= Decimal(bal) <= Decimal("100000000")):
        raise ContractError("INVALID_INPUT", "balance")
    sid = f"session:{int(time.time() * 1000)}"
    cs = ClaudeSession(S["src"], S["profile"], policy, S["meta"]["seed"], session_id=sid, archive=True, balance=bal)
    S.update(cs=cs, sid=sid, policy=policy, defn=defn, name=(name or defn["name"])[:60], events=[], trades=[], meta_orders={}, refusals=[],
             reviews={}, serial=0)
    save()


def load_session(sid):
    saved = json.loads(session_file(sid).read_text())
    d = saved["defn"]
    policy, defn = make_method(d["kind"], d["name"], d["riskPercent"], d["rr"], [c["label"] for c in d["conditions"]], d["checklistOn"])
    if defn != d:
        raise ValueError("METHOD_DEFINITION_CHANGED")
    cs = ClaudeSession.recover(S["src"], S["profile"], policy, S["meta"]["seed"], saved["snapshot"])
    S.update(cs=cs, sid=saved["sid"], policy=policy, defn=defn, name=saved["name"], events=saved["events"], trades=saved["trades"],
             meta_orders=saved["meta_orders"], refusals=saved.get("refusals", []), reviews={}, serial=saved.get("serial", 0))


def saved_sessions():
    out = []
    for f in sorted(SESS_DIR.glob("session_*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            j = json.loads(f.read_text())
        except Exception:
            continue
        if j.get("dataset") == S["meta"]["adm"]["manifestHash"]:
            out.append(dict(id=j["sid"], name=j["name"], kind=j["defn"]["kind"], balance=j["balance"], savedMs=j["savedMs"], current=j["sid"] == S.get("sid")))
    return out


def refuse(action, e):
    S["refusals"].append(dict(timeMs=int(S["cs"].state["throughNs"]) // 1_000_000, action=action, code=e.code, reason=e.field))
    save()


def do_advance(seconds):
    cs, src = S["cs"], S["src"]
    t = min(int(cs.state["throughNs"]) + int(seconds * 1e9), int(src.gts[-1]))
    log_events(cs.advance_through(t))


def jump_next_event():
    """Exact jump: the source proves where a live order can first change; everything before it is skipped, then that group is
    processed by the reference rules. Repeats only when the proof is unavailable (never guesses)."""
    cs = S["cs"]
    start, moves = int(cs.state["throughNs"]), 0
    while True:
        t = cs.next_event_ns()
        if t is None:
            live = any(o["status"] in ("PENDING", "ACTIVE") for o in cs.state["orders"].values())
            return dict(jumped=moves > 0, reason=("NO_EVENT_BEFORE_END_OF_DATA" if live else "NO_LIVE_ORDER") if moves == 0 else "NO_MORE_EVENTS")
        before = len(S["events"])
        log_events(cs.advance_through(t)); moves += 1
        if len(S["events"]) > before or cs.state["unresolved"] or moves > 200000:
            return dict(jumped=True, reason="EVENT", fromMs=start // 10**6, toMs=int(cs.state["throughNs"]) // 10**6, steps=moves)


def review(body, store):
    cs = S["cs"]
    try:
        payload, prev = build(cs.state, body, len(str(S["src"].scale)) - 1)
    except ContractError as e:
        if store:
            refuse("REVIEW_" + str(body.get("workflow")), e)
        raise
    if not store:
        return dict(ok=True, preview=prev)
    S["review_serial"] = S.get("review_serial", 0) + 1
    rid = f"review:{S['review_serial']}"
    S["reviews"][rid] = dict(payload=payload, revision=cs.state["revision"], preview=prev, status="OPEN", orderId=None)
    return dict(ok=True, reviewId=rid, preview=prev, basisRevision=cs.state["revision"])


def confirm(body):
    cs = S["cs"]
    r = S["reviews"].get(body.get("reviewId"))
    if r is None:
        raise ContractError("RESOURCE_UNAVAILABLE", "review")
    if r["status"] == "CONFIRMED":                      # same reviewed snapshot confirmed twice -> the prior result, no second order
        return dict(session_json(), duplicate=True, orderId=r["orderId"])
    if cs.state["revision"] != r["revision"]:
        r["status"] = "STALE"
        e = ContractError("REFUSED_STALE_REVISION", "harga sudah bergerak, review ulang")
        refuse("CONFIRM", e)
        raise e
    S["serial"] = S.get("serial", 0) + 1
    oid = f"order:{S['serial']}"
    S["meta_orders"][oid] = dict(side=r["preview"]["side"])
    try:
        log_events(cs.command("OPEN", r["payload"], oid))
    except ContractError as e:                          # the kernel re-checks everything; a UI bypass still lands here
        refuse("CONFIRM", e)
        raise
    r["status"], r["orderId"] = "CONFIRMED", oid
    save()
    return dict(session_json(), orderId=oid)


def api(path, q, body):
    cs = S["cs"]
    if path == "/api/state":
        return session_json()
    if path == "/api/candles":
        tf = int(q.get("tf", ["60"])[0]); n = min(int(q.get("n", ["300"])[0]), 5000)
        return dict(tf=tf, candles=candles(tf, n))
    if path == "/api/advance":
        res = None
        if body.get("toEnd"):
            do_advance((int(S["src"].gts[-1]) - int(cs.state["throughNs"])) / 1e9)
        elif body.get("untilEvent"):
            res = jump_next_event()
        else:
            do_advance(float(body.get("seconds", 1)))
        save(); return dict(session_json(), jump=res)
    if path == "/api/preview":
        return review(body, False)
    if path == "/api/review":
        return review(body, True)
    if path == "/api/confirm":
        return confirm(body)
    if path in ("/api/close", "/api/cancel"):
        kind = "CLOSE" if path.endswith("close") else "CANCEL"
        pay = dict(orderId=body["orderId"], quantity=body.get("quantity")) if kind == "CLOSE" else dict(orderId=body["orderId"])
        S["serial"] = S.get("serial", 0) + 1
        try:
            log_events(cs.command(kind, pay, f"{kind.lower()}:{body['orderId']}:{S['serial']}"))
        except ContractError as e:
            refuse(kind, e)
            raise
        save(); return session_json()
    if path == "/api/sessions":
        return dict(sessions=saved_sessions())
    if path == "/api/new_session":
        new_session(body["method"], body.get("balance", "10000"), body.get("name"))
        return session_json()
    if path == "/api/open_session":
        load_session(body["id"]); return session_json()
    raise KeyError(path)


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _send(self, code, payload, ctype="application/json"):
        data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path in ("/", "/index.html"):
            return self._send(200, (HERE / "index.html").read_bytes(), "text/html; charset=utf-8")
        self._handle(u, {})

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        self._handle(urlparse(self.path), json.loads(self.rfile.read(n) or b"{}"))

    def _handle(self, u, body):
        with LOCK:
            try:
                self._send(200, api(u.path, parse_qs(u.query), body))
            except ContractError as e:
                self._send(400, dict(error=f"{e.code}: {e.field}", code=e.code, field=e.field))
            except Exception as e:          # surface, never swallow
                self._send(500, dict(error=f"{type(e).__name__}: {e}"))


def main():
    global SESS_DIR
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", required=True); ap.add_argument("--ticks", type=int, default=400000); ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--pair", default="XAUUSD", help="XAUUSD (Dukascopy zip) or EURUSD/GBPUSD/AUDUSD/NZDUSD (HistData-UTC zip)")
    ap.add_argument("--port", type=int, default=8765); ap.add_argument("--cache", default=str(Path(tempfile.gettempdir()) / "riksora_local_trader"))
    ap.add_argument("--silence-seconds", type=int, default=300, help="FX only (QA setting): quote silence longer than this makes live orders UNRESOLVED; XAUUSD keeps the frozen 60 s")
    ap.add_argument("--balance", default="10000"); ap.add_argument("--fresh", action="store_true", help="start a new Free Style session instead of resuming the latest")
    a = ap.parse_args()
    src, profile, seed, meta = open_source(a.zip, a.offset, a.ticks, a.cache, a.pair, a.silence_seconds)
    SESS_DIR = Path(a.cache) / "sessions"; SESS_DIR.mkdir(parents=True, exist_ok=True)
    S.update(src=src, profile=profile, meta=meta, reviews={}, refusals=[], events=[], trades=[], meta_orders={})
    S["meta"]["seed"] = seed
    old = [] if a.fresh else saved_sessions()
    if old:
        load_session(old[0]["id"])
        print(f"[session] resumed '{S['name']}' ({S['defn']['kind']}) from verified snapshot (hash chain + state checked)")
    else:
        new_session(dict(kind="FREE_STYLE", name="Free Style"), a.balance, "Sesi baru")
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), H)
    print(f"[ready] http://127.0.0.1:{a.port}  ({src.ngroups} tick groups)", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
