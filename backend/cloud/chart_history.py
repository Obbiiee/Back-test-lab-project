"""Authenticated, cursor-bound chart history from precomputed OHLC objects on the VPS SSD (artifact BTL-CHART-HISTORY-PAGE-1).

ADDITIVE: the frozen BTL-PAST-CHART-CONTEXT-1 (previous calendar month, 512-bar offset paging) is unchanged and still served by the worker. This route serves the
owner-selected chart contract: first page of already-completed bars for the selected timeframe, older pages by `before`, up to the caller's 5,000-candle window.
The OHLC objects are DERIVED, NON-AUTHORITATIVE display data (never execution authority); the forming bar is rebuilt from ticks revealed at the cursor only.

Security model (every request, server side):
  * identity comes from the product bearer token; workspace membership and session ownership are checked with the same `scoped` primitive the research routes use
    (a foreign or unknown Session answers like an unknown one);
  * the cursor (revealed-through time), dataset pins and revision come from the DURABLE Session summary, never from the request;
  * only bars whose end <= cursor leave the trust boundary; `before` beyond the cursor is refused;
  * a Session whose dataset has no registry rule is refused (no silent fallback to another source).
Registry (JSON, path in BTL_CHART_REGISTRY): {"schemaVersion":1,"store":"<object store root>","basis":"BID","rules":[{"datasetIdPrefix":..,"instrument":..,
"sourceHashes":[16-hex..],"tickRoot":"<dir with YYYY-MM month datasets>"}]}. D1 (and any timeframe) returns what the catalog holds: `historyExhausted` says so
explicitly instead of pretending a 5,000-bar window exists.
"""
import json
import threading
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path

from contracts.primitives import ContractError, require

_PAGE_DEFAULT, _PAGE_MAX, _WINDOW_CAP = 512, 1000, 5000
_TIMEFRAMES = ("M1", "M3", "M5", "M15", "M30", "H1", "H2", "H4", "D1")
_API_TIMEFRAMES = {"1m": "M1", "3m": "M3", "5m": "M5", "15m": "M15", "30m": "M30", "1h": "H1", "2h": "H2", "4h": "H4", "D": "D1"}


def _decimal(value, den):
    """Exact decimal text of value/den where den = 2*10**S (same rule as the frozen display artifact)."""
    digits = len(str(den))
    q, r = divmod(int(value) * 5, 10 ** digits)
    return f"{q}.{r:0{digits}d}"


class ChartHistory:
    def __init__(self, registry, *, authorize, cursor_loader, cache_sessions=1024, cache_objects=64):
        from tools.claude_exp.ohlc.service import ChartService
        from tools.claude_exp.ohlc.store import LocalObjectStore
        require(type(registry) is dict and registry.get("schemaVersion") == 1 and type(registry.get("rules")) is list, "chartRegistry", "INVALID_INPUT")
        self._registry = registry
        self._authorize, self._cursor_loader = authorize, cursor_loader
        self._pins, self._pin_limit, self._lock = OrderedDict(), cache_sessions, threading.Lock()
        self._tick_readers = {}
        self._basis = registry.get("basis", "BID")
        readers = {rule["instrument"]: (lambda ns, _rule=rule: self.tick_reader(_rule, ns)) for rule in registry["rules"]}
        self._service = ChartService(LocalObjectStore(registry["store"]), readers, {}, {}, cache_objects=cache_objects)

    # ---- registry ---------------------------------------------------------------------------------------------------
    def _rule(self, dataset_id):
        for rule in self._registry["rules"]:
            if str(dataset_id).startswith(rule["datasetIdPrefix"]):
                return rule
        raise ContractError("RESOURCE_UNAVAILABLE", "chartSource")

    def tick_reader(self, rule, minute_ns):
        root = rule.get("tickRoot")
        if not root:
            return None
        month = datetime.fromtimestamp(minute_ns // 10**9, timezone.utc).strftime("%Y-%m")
        key = (root, month)
        if key not in self._tick_readers:
            directory = Path(root) / month
            if not ((directory / "compact2.json").exists() or (directory / "compact.json").exists()):
                self._tick_readers[key] = None
            else:
                from tools.claude_exp.compact2 import open_compact
                self._tick_readers[key] = open_compact(directory)
        return self._tick_readers[key]

    # ---- request ----------------------------------------------------------------------------------------------------
    def page(self, actor_id, workspace_id, session_id, *, timeframe, limit=None, before=None, floor_ns=None):
        require(timeframe in _API_TIMEFRAMES, "timeframe", "INVALID_INPUT")
        tf = _API_TIMEFRAMES[timeframe]
        require(limit is None or (type(limit) is int and 1 <= limit <= _PAGE_MAX), "limit", "INVALID_INPUT")
        require(before is None or (type(before) is int and before > 0), "before", "INVALID_INPUT")
        revision = self._authorize(actor_id, workspace_id, session_id)             # identity + membership + ownership, raises like an unknown Session
        key = (str(workspace_id), str(session_id))
        with self._lock:
            pin = self._pins.get(key)
            if pin is not None:
                self._pins.move_to_end(key)
        if pin is None or pin["revision"] != revision:
            summary = self._cursor_loader(actor_id, workspace_id, session_id)      # durable, committed cursor
            pin = dict(revision=int(summary["revision"]), through=int(summary["throughNs"]), datasetId=summary["datasetId"], datasetVersion=summary["datasetVersion"])
            with self._lock:
                self._pins[key] = pin
                while len(self._pins) > self._pin_limit:
                    self._pins.popitem(last=False)
        rule = self._rule(pin["datasetId"])
        from tools.claude_exp.ohlc import service as svc
        session = svc.Session(str(session_id), str(actor_id), rule["instrument"], rule["sourceHashes"][0], self._basis, pin["through"],
                              revision=pin["revision"], source_hashes=rule["sourceHashes"])
        try:
            out = self._service.page_for(session, tf, limit, None if before is None else before * 10**9)
        except svc.ServiceError as error:
            raise ContractError("INVALID_INPUT" if error.status == 400 else "RESOURCE_UNAVAILABLE", "chart") from None
        den = int(out["den"])
        bars = out["bars"]
        candles = [dict(time=int(bars["t"][i]) // 10**9, open=_decimal(bars["o"][i], den), high=_decimal(bars["h"][i], den),
                        low=_decimal(bars["l"][i], den), close=_decimal(bars["c"][i], den)) for i in range(out["count"])]
        forming = None
        if out.get("active"):
            a = out["active"]
            forming = dict(time=int(a["t"]) // 10**9, open=_decimal(a["o"], den), high=_decimal(a["h"], den), low=_decimal(a["l"], den), close=_decimal(a["c"], den))
        next_before = (int(bars["t"][0]) // 10**9) if out["count"] and out["hasMore"] else None
        has_more = bool(out["hasMore"])
        candles, forming, next_before, has_more = clip_to_floor(candles, forming, next_before, has_more, floor_ns)
        return dict(schemaVersion=1, artifact="BTL-CHART-HISTORY-PAGE-1", sessionId=session_id, revision=pin["revision"], timeframe=timeframe,
                    priceBasis=self._basis, evidence="DERIVED_NON_AUTHORITATIVE_DISPLAY_ONLY", executionAuthority=False, volumeAvailable=False,
                    cursorNs=str(pin["through"]), candles=candles, forming=forming,
                    nextBefore=next_before, hasMore=has_more, historyExhausted=not has_more, windowCap=_WINDOW_CAP)


def clip_to_floor(candles, forming, next_before, has_more, floor_ns):
    """Free accounts: drop every candle that starts before the activated month and end paging there (a pure function, unit-tested).
    The clipping happens on the server for every response, so the browser, a cache or a prefetch never receives an older candle."""
    if floor_ns is None:
        return candles, forming, next_before, has_more
    floor = int(floor_ns) // 10**9
    kept = [c for c in candles if c["time"] >= floor]
    if len(kept) != len(candles) or (next_before is not None and next_before <= floor):
        return kept, forming, None, False
    return kept, forming, next_before, has_more


def from_environment(dsn):
    """Build the product ChartHistory from BTL_CHART_REGISTRY, or None when it is not configured (the route then answers like an unknown resource)."""
    import os
    path = os.environ.get("BTL_CHART_REGISTRY")
    if not path:
        return None
    registry = json.loads(Path(path).read_text(encoding="utf-8"))
    from psycopg.rows import dict_row
    from infrastructure.database import connect
    from . import queue as research_queue

    def authorize(actor_id, workspace_id, session_id):
        with connect(dsn) as db:
            db.row_factory = dict_row
            research_queue.scoped(db, actor_id, workspace_id)                       # raises for a non-member exactly like the research routes
            row = db.execute("SELECT revision FROM btl.tick_sessions WHERE workspace_id=%s AND session_id=%s", (str(workspace_id), str(session_id))).fetchone()
            if row is None:
                raise ContractError("RESOURCE_UNAVAILABLE", "session")
            return int(row["revision"])

    def cursor_loader(actor_id, workspace_id, session_id):
        from .research import run
        return run(dsn, actor_id, workspace_id, "summary", (session_id,))

    return ChartHistory(registry, authorize=authorize, cursor_loader=cursor_loader)
