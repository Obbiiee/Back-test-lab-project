"""Shared fixtures for the Claude architecture experiments (QA only, never product code).

Real ticks come from a local Dukascopy-format ZIP named by XAU_TICK_ZIP; nothing from it is committed.
The psycopg stub only lets modules import; no experiment here touches PostgreSQL.
"""
import csv, datetime as dt, io, json, os, sys, tempfile, time, zipfile
from pathlib import Path
from unittest.mock import MagicMock

for _n in ("psycopg", "psycopg.sql", "psycopg.rows", "psycopg.conninfo", "psycopg.errors", "psycopg.types",
           "psycopg.types.json", "psycopg.pq", "psycopg_pool"):
    sys.modules.setdefault(_n, MagicMock())

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from contracts.models import MethodPolicy
from execution.observed_profile import ObservedExecutionProfile
from execution.observed_kernel import apply, seed_state
from ticks.dukascopy_csv import DukascopyCsvIngestion
from ticks.storage_v2 import DiskTickProvider
from ticks.timeline_v2 import IndexedTickTimeline

FMT = dict(dec=3, scale=1000, pending="0.4")      # instrument price format used by the scripted trader


def set_instrument(dec, pending):
    FMT.update(dec=dec, scale=10**dec, pending=pending)


PROFILE = json.loads((BACKEND / "tests/fixtures/observed_profile_vectors.json").read_text())["profiles"][0]["profile"]


def read_real_rows(limit):
    """[(ts_ms, ask, bid)] of the first `limit` real XAUUSD ticks."""
    rows = []
    with zipfile.ZipFile(os.environ["XAU_TICK_ZIP"]) as z, z.open(z.namelist()[0]) as raw:
        rd = csv.reader(io.TextIOWrapper(raw, encoding="utf-8-sig", newline=""))
        next(rd)
        for i, (ts, ask, bid, _av, _bv) in enumerate(rd):
            if i >= limit:
                break
            rows.append((int(ts), ask, bid))
    return rows


def ingest_engine(rows, work):
    """Repo ingestion -> canonical engine store (the Codex baseline source). Returns (provider, res, seconds)."""
    src = Path(work) / "XAUUSD.csv"
    with open(src, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["Gmt time", "Ask", "Bid", "AskVolume", "BidVolume"])
        for ts, ask, bid in rows:
            d = dt.datetime.fromtimestamp(ts / 1000, dt.timezone.utc)
            w.writerow([d.strftime("%d.%m.%Y %H:%M:%S.") + f"{ts % 1000:03d}", ask, bid, "1", "1"])
    t0 = time.perf_counter()
    imp = DukascopyCsvIngestion(src, Path(work) / "store", symbol="XAUUSD", month="2024-01")
    res = imp.run()
    imp.builder.store.close()
    seconds = time.perf_counter() - t0
    return DiskTickProvider(Path(work) / "store", res["datasetVersion"]), res, seconds


def make_profile(provider, symbol="XAUUSD"):
    desc = provider.describe_v2(provider.dataset_id, provider.dataset_version)["root"]
    primary = dict(datasetId=provider.dataset_id, datasetVersion=provider.dataset_version, providerId=desc["providerId"], feedId=desc["feedId"],
                   feedInstrumentId=desc["instrumentId"], providerSymbol="XAUUSD", evidenceClass=desc["evidenceClass"])
    if symbol == "XAUUSD":
        raw = json.loads(json.dumps(PROFILE)); raw["primary"] = primary
    else:
        import fx_profile
        fx_profile.install()
        raw = fx_profile.fx_profile_wire(PROFILE, symbol, primary)
    return ObservedExecutionProfile.from_wire(raw)


def policy():
    return MethodPolicy("method:qa", "a" * 64, "FREE_STYLE", False, ())


def raw_command(state, serial, kind, payload, command=None):
    return dict(schemaVersion=1, artifact="BTL-OBSERVED-EXECUTION-COMMAND-1", sessionId=state["sessionId"],
                commandId=command or f"command:{serial}", expectedRevision=state["revision"], kind=kind, payload=payload)


def open_payload(state, side, tp_points, sl_points):
    """Market order at the current basis with fixed TP/SL (price units = scale 1000)."""
    basis = state["quoteBasis"]
    entry = basis["ask" if side == "LONG" else "bid"]
    from decimal import Decimal
    e = Decimal(entry)
    sgn = 1 if side == "LONG" else -1
    tp = e + sgn * Decimal(tp_points) / FMT["scale"]
    sl = e - sgn * Decimal(sl_points) / FMT["scale"]
    dec = FMT["dec"]
    return dict(side=side, orderType="MARKET", workflow="QUICK", entry=entry, quantity="0.01", sl=f"{sl:.{dec}f}",
                tp=f"{tp:.{dec}f}", riskPercent="1", observations=[])


def strip_source_specific(events):
    """Semantic view of financial events: drop representation-specific hashes (group ids, evidence blobs)."""
    keep = ("kind", "code", "field", "orderId", "price", "quantity", "grossPosted", "balanceDelta", "reason", "remaining", "commission",
            "gapKind", "elapsedNs", "throughNs")
    out = []
    for e in events:
        flat = {}
        for k in keep:
            if k in e:
                flat[k] = e[k]
            elif isinstance(e.get("detail"), dict) and k in e["detail"]:
                flat[k] = e["detail"][k]
        evid = (e.get("detail") or {}).get("evidence") if isinstance(e.get("detail"), dict) else None
        if isinstance(evid, dict):
            flat["fillTimeNs"] = evid.get("timeNs")
            flat["fillBid"], flat["fillAsk"] = evid.get("bid"), evid.get("ask")
        out.append(flat)
    return out


def _safe(command):
    from contracts.primitives import ContractError
    def run(kind, payload, cid):
        try:
            return command(kind, payload, cid)
        except ContractError as e:      # a refusal is part of the observable behaviour; both engines must refuse identically
            return [dict(kind="REFUSED", code=e.code, field=e.field)]
    return run


def drive(advance, command, get_state, start, end, step_s=300, tp=1500, sl=1000, mix=False):
    """Identical scripted trader for both engines. advance(target)->events ; command(kind,payload,id)->events.

    mix=False: alternating MARKET long/short with TP/SL (one live order at a time).
    mix=True : cycles market / limit / stop / manual-close / cancel-pending so pending-order, exit-request and
               cancel paths are exercised too.
    """
    from decimal import Decimal
    command = _safe(command)
    events, side, cycle, target, opened = [], 1, 0, start, 0
    while True:
        target = min(target + step_s * 10**9, end)
        events.extend(advance(target))
        st = get_state()
        orders = st["orders"]
        live = [(k, o) for k, o in orders.items() if o["status"] in ("PENDING", "ACTIVE")]
        if mix:
            for k, o in live:
                if o["status"] == "PENDING" and int(st["throughNs"]) - int(o["availableNs"]) > 2 * step_s * 10**9:
                    events.extend(command("CANCEL", dict(orderId=k), f"cancel:{k}:{target}"))
                elif o["status"] == "ACTIVE" and o["exitRequest"] is None and cycle % 4 == 3 and int(st["throughNs"]) - int(o["availableNs"]) > step_s * 10**9:
                    events.extend(command("CLOSE", dict(orderId=k, quantity=None), f"close:{k}:{target}"))
            st = get_state(); live = [(k, o) for k, o in st["orders"].items() if o["status"] in ("PENDING", "ACTIVE")]
        if not live and st["quoteBasis"] is not None and not st["unresolved"] and target < end and int(st["throughNs"]) - int(st["quoteBasis"]["timeNs"]) <= 60 * 10**9:
            b = st["quoteBasis"]; sd = "LONG" if side == 1 else "SHORT"; side = -side
            kind = (cycle % 4) if mix else 0
            d = 1 if sd == "LONG" else -1
            if kind in (1, 2):    # pending LIMIT (better price) or STOP (worse price), 0.40 away
                px = Decimal(b["ask" if sd == "LONG" else "bid"])
                entry = px - d * Decimal(FMT["pending"]) if kind == 1 else px + d * Decimal(FMT["pending"])
                dec = FMT["dec"]
                pay = dict(side=sd, orderType="LIMIT" if kind == 1 else "STOP", workflow="PLANNED", entry=f"{entry:.{dec}f}", quantity="0.01",
                           sl=f"{entry - d*Decimal(sl)/FMT['scale']:.{dec}f}", tp=f"{entry + d*Decimal(tp)/FMT['scale']:.{dec}f}", riskPercent="1", observations=[])
            else:
                pay = open_payload(st, sd, tp, sl)
            opened += 1; cycle += 1
            events.extend(command("OPEN", pay, f"order:{opened}"))
        if target >= end:
            return events


def read_histdata_rows(zip_path, limit, offset=0):
    """HistData-UTC monthly zip (header timestamp,bid,ask; epoch ms UTC) -> [(ts_ms, ask, bid)] (same shape as read_real_rows)."""
    rows = []
    with zipfile.ZipFile(zip_path) as z, z.open(z.namelist()[0]) as raw:
        rd = csv.reader(io.TextIOWrapper(raw, encoding="utf-8-sig", newline=""))
        assert next(rd) == ["timestamp", "bid", "ask"]
        for i, (ts, bid, ask) in enumerate(rd):
            if i < offset:
                continue
            if len(rows) >= limit:
                break
            rows.append((int(ts), ask, bid))
    return rows


def histdata_member_hash(zip_path):
    import hashlib
    sha = hashlib.sha256()
    with zipfile.ZipFile(zip_path) as z, z.open(z.namelist()[0]) as f:
        while b := f.read(1 << 20):
            sha.update(b)
    return sha.hexdigest()


def genesis_checkpoint(dataset_id, dataset_version, start_ns):
    """Revision-0 timeline checkpoint (same bytes IndexedTickTimeline produces) without needing a canonical store."""
    from ticks.contracts_v2 import hash_v2
    from ticks.timeline_v2 import VERSION
    from ticks.provider import empty_diagnostics
    initial = dict(schemaVersion=2, artifact="BTL-TICK-PREFIX-2", datasetId=dataset_id, datasetVersion=dataset_version, timelineVersion=VERSION,
                   generation="0", sessionStartNs=str(start_ns), throughNs=str(start_ns), groups=[], coverage=[], diagnostics=empty_diagnostics())
    cursor = dict(schemaVersion=2, artifact="BTL-TICK-CURSOR-2", datasetId=dataset_id, datasetVersion=dataset_version, timelineVersion=VERSION,
                  generation="0", revision="0", sessionStartNs=str(start_ns), throughNs=str(start_ns), pendingTargetNs=None,
                  visiblePrefixHash=hash_v2(initial), nextGroupIndex="0", lastGroupId=None)
    return dict(schemaVersion=2, artifact="BTL-TICK-CHECKPOINT-2", cursor=cursor, advanceLogHash=None, positionLogHash=None)


def ingest_histdata(rows, work, pair, member_hash, month):
    """Canonical engine store for HistData-UTC rows (Codex baseline source). Event layout follows the repo-validated
    histutc conversion: provider histdata, feed local-unverified:PAIR, provenance.originalTimestamp = epoch-ms text."""
    import hashlib
    from contracts.canonical import decimal_text
    from contracts.primitives import decimal
    from ticks.contracts import event_id
    from ticks.contracts_v2 import ZERO_VERSION
    from ticks.storage_v2 import DatasetBuilder
    ds = f"local:histdata-utc:{pair}:{month}:{member_hash[:24]}"
    src_id = "histdata:utc:" + member_hash[:24]
    feed, inst = "local-unverified:" + pair, "histdata:" + pair
    meta = dict(datasetId=ds, providerId="histdata", feedId=feed, instrumentId=inst, providerSymbol=pair, evidenceClass="PROVIDER_OBSERVATION",
                adapterVersion="HISTDATA-UTC-LOCAL-CSV-1", validatorVersion="BTL-TICK-VALIDATOR-2",
                ordering=dict(timestamps="VERIFIED_NONDECREASING", ties="UNTRUSTED", sequenceScope=None, sequenceEvidenceHash=None))
    sources = [dict(sourceId=src_id, archiveHash=None, memberHash=member_hash, originalName="histdata.csv", acquiredAtUtc=None, sourceUrl=None,
                    timestampConvention="HistData-UTC local copy; ordering/provenance UNVERIFIED", resolutionNs="1000000", originalScalePolicy="PRESERVE_RAW_TEXT")]
    b = DatasetBuilder(Path(work) / "store", meta, sources, {"local": True}, packing=(256, 256, 1024))
    for i, (ts, ask, bid) in enumerate(rows):
        bt, at = decimal_text(decimal(bid, "bid", positive=True)), decimal_text(decimal(ask, "ask", positive=True))
        b.append(dict(schemaVersion=1, artifact="BTL-CANONICAL-TICK-1", datasetId=ds, datasetVersion=ZERO_VERSION, providerId="histdata", feedId=feed,
                      instrumentId=inst, eventId=event_id("histdata", feed, member_hash, str(i)), timeNs=str(ts * 1_000_000), resolutionNs="1000000",
                      bid=bt, ask=at, rawOrdinal=str(i), trustedSequence=None,
                      provenance=dict(sourceId=src_id, memberHash=member_hash, originalTimestamp=str(ts)),
                      quality=dict(evidenceHash=None, quote="CROSSED" if float(bt) > float(at) else "VALID", freshness="UNKNOWN", gapBefore="UNKNOWN_SILENCE", duplicateOf=None)))
    version = b.finish()
    return DiskTickProvider(Path(work) / "store", version)
