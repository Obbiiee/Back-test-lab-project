"""Authenticated QA MI endpoints over the existing research admission and queue."""
import os
import uuid

from fastapi import Depends, Query, Request

from application.models import TrustedScope
from contracts.primitives import identifier, require
from fractions import Fraction
from execution import mi_checkpoint
from execution.mi_postgres import MultiInstrumentStore
from execution.postgres import unpack
from execution.profile_set import ProfileSet
from execution.research import method_policy
from ticks.contracts import tag, uint

from . import mi_qa
from .entitlements import Entitlements, month_bounds


PRODUCT_SOURCE = "BTL-MI-QA-PRODUCT-SOURCE-1"


def source_info():
    value, sha = mi_qa.manifest()
    require(value["artifact"] == PRODUCT_SOURCE, "miSource", "REFUSED_SOURCE")
    profiles = ProfileSet(value["profiles"])
    require(set(profiles.symbols) == set(value["pins"]) == set(value["ticks"]),
            "miInstruments", "REFUSED_DATASET_MISMATCH")
    start, end = month_bounds(value["startPeriod"])
    return value, sha, profiles, start, end


def run(db, dsn, scope, actor_id, operation, args):
    store = MultiInstrumentStore(dsn)
    catalog, sha, profiles, start, _ = source_info()
    entitlements = Entitlements(dsn)
    if operation == "mi_catalog":
        return dict(schemaVersion=1, artifact="BTL-MI-QA-CATALOG-1", symbols=profiles.symbols,
                    conversionRoutes=profiles.conversion_needs(), startPeriod=catalog["startPeriod"],
                    label="SYNTHETIC / TEST ONLY")
    if operation == "mi_create":
        raw, = args
        tag(raw, "BTL-MI-SESSION-CREATE-1", "id instrumentIds methodIds activeMethodId initialBalance")
        identifier(raw["id"], "sessionId")
        symbols, methods = raw["instrumentIds"], raw["methodIds"]
        require(type(symbols) is list and 2 <= len(symbols) <= 16 and
                all(type(symbol) is str and symbol in profiles.symbols for symbol in symbols) and
                len(set(symbols)) == len(symbols), "instrumentIds")
        require(type(methods) is list and 1 <= len(methods) <= 16 and
                all(type(key) is str for key in methods) and len(set(methods)) == len(methods)
                and raw["activeMethodId"] in methods, "methodIds")
        for method in methods:
            identifier(method, "methodId")
        selected = ProfileSet([profile.wire for profile in profiles.profiles if profile.wire["symbol"] in symbols])
        policies = []
        from execution.product_method_lifecycle import require_active_method
        db.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (scope.workspace_id,))
        for method in methods:
            require_active_method(db, scope.workspace_id, method)
            row = db.execute("SELECT payload,content_hash FROM btl.tick_methods WHERE workspace_id=%s AND method_id=%s",
                             (scope.workspace_id, method)).fetchone()
            require(row is not None, "method", "RESOURCE_UNAVAILABLE")
            policies.append(method_policy(unpack(row["payload"], row["content_hash"])))
        # Validate the entire selection and source before consuming a quota token.
        from execution import mi_kernel
        seed = mi_kernel.seed_state(raw["id"], selected, policies, raw["activeMethodId"], raw["initialBalance"], str(start))
        require(Fraction(raw["initialBalance"]) == Fraction(seed["initialBalance"]), "moneyPrecision")
        sources, _, _ = mi_qa.open_sources(mi_checkpoint.pins_from_state(seed))
        require(all(int(next(open_at(0))["timeNs"]) >= start for open_at in sources.values()),
                "miSourceWindow", "REFUSED_SOURCE")
        exists = db.execute("SELECT 1 FROM btl.tick_sessions WHERE workspace_id=%s AND session_id=%s",
                            (scope.workspace_id, raw["id"])).fetchone()
        claim = None
        if exists:
            require(entitlements.session_window(scope.workspace_id, raw["id"]) is not None,
                    "miWindow", "RESOURCE_UNAVAILABLE")
        else:
            claim = entitlements.reserve(actor_id, scope.workspace_id, dict(raw,
                                         startPeriod=catalog["startPeriod"], sourceKey="mi-qa:" + sha))
        try:
            store.create(scope, selected, policies, raw["activeMethodId"], raw["initialBalance"],
                         str(start), raw["id"], manifest_sha=sha, compact=True)
        except Exception:
            if claim is not None:
                entitlements.release(actor_id, claim)
            raise
        return store.snapshot(scope, raw["id"], required_manifest_sha=sha)

    session, *options = args
    if operation == "mi_review":
        command, = options
        require(type(command) is dict and command.get("sessionId") == session, "sessionId")
        return store.review(scope, command, required_manifest_sha=sha,
                            authorize=window_policy(entitlements, scope.workspace_id, session))
    window = entitlements.session_window(scope.workspace_id, session)
    require(window is not None, "miWindow", "RESOURCE_UNAVAILABLE")
    focus = options[0] if operation == "mi_snapshot" and options else None
    view = store.snapshot(scope, session, required_manifest_sha=sha,
                          focus=focus, open_sources=mi_qa.open_sources)
    restrict_market_view(view, window)
    if operation == "mi_snapshot":
        view["window"] = {key: str(window[key]) for key in ("startNs", "endNs")}
        view["window"]["tier"] = window["tier"]
        return view
    if operation == "mi_command_status":
        raw, = options
        command = mi_qa.request(raw, session)
        return store.command_status(scope, command, jump=raw["jump"], required_manifest_sha=sha,
                                    review_hash=raw.get("reviewHash"))
    if operation == "mi_analytics":
        return store.project(scope, session)
    arguments, = options
    if arguments["revision_pin"] is None:
        arguments = dict(arguments, revision_pin=view["state"]["revision"])
    reader = store.terminal_page if operation == "mi_terminal" else store.event_page
    return reader(scope, session, **arguments)


def restrict_market_view(view, window):
    """Hide restricted quotes while retaining the account and its immutable fills."""
    if window["tier"] != "FREE":
        return
    start, end = int(window["startNs"]), int(window["endNs"])

    def allowed(stamp):
        return start <= int(stamp) < end

    groups = view["state"]["groups"]
    masked = False
    for symbol, group in groups.items():
        if group is not None and not allowed(group["timeNs"]):
            groups[symbol] = None
            masked = True
    if "chart" in view:
        view["chart"] = [bar for bar in view["chart"] if allowed(bar["timeNs"])]
    if masked:
        view["marketViewRestricted"] = True
        if "equity" in view and any(order["status"] == "ACTIVE" for order in view["state"]["orders"].values()):
            view["equity"] = {"complete": False, "reason": "FREE_WINDOW_MARKET_DATA_RESTRICTED"}


def window_policy(entitlements, workspace_id, session_id):
    """Run on the locked checkpoint before new evidence can be consumed."""
    def authorize(db, state, command, jump):
        window = entitlements.session_window_in(db, workspace_id, session_id)
        require(window is not None, "miWindow", "RESOURCE_UNAVAILABLE")
        if window["tier"] == "PRO":
            return None
        kind = command["kind"]
        end = window["endNs"] - 1
        through = int(state["throughNs"])
        if kind == "OPEN":
            require(through < end, "miWindow", "WINDOW_ENDED")
        if kind != "ADVANCE":
            return None  # CANCEL/CLOSE retain order lifecycle, without fetching a quote.
        target = uint(command["payload"]["targetNs"])
        require(target >= window["startNs"], "miWindow", "WINDOW_BOUNDARY")
        orders = state["orders"].values()
        pending = any(order["status"] == "PENDING" for order in orders)
        active = any(order["status"] == "ACTIVE" for order in orders)
        if through >= end:
            if not jump:
                require(False, "miWindow", "WINDOW_ENDED_CONTINUATION_ONLY")
            require(not pending, "miWindow", "PENDING_AT_WINDOW_END")
            require(active, "miWindow", "WINDOW_COMPLETED")
        if jump:
            # A pending fill would create fresh exposure. Active-only
            # continuation may read evidence internally as legacy does.
            return target if active and not pending else min(target, end)
        require(target <= end, "miWindow", "WINDOW_BOUNDARY")
        return target
    return authorize


def guard_worker(dsn, workspace_id, session_id):
    catalog, _ = mi_qa.manifest()
    if catalog["artifact"] != PRODUCT_SOURCE:
        return None
    return window_policy(Entitlements(dsn), workspace_id, session_id)


def install(app, prefix, current, execute, json_body):
    path = prefix + "/mi"

    @app.get(path + "/catalog")
    async def catalog(workspace_id: uuid.UUID, user=Depends(current)):
        return await execute(user, workspace_id, "mi_catalog")

    @app.post(path + "/sessions")
    async def create(workspace_id: uuid.UUID, request: Request, user=Depends(current)):
        return await execute(user, workspace_id, "mi_create", await json_body(request), write=True)

    @app.get(path + "/sessions/{session_id}")
    async def snapshot(workspace_id: uuid.UUID, session_id: str,
                       instrument: str | None = Query(None, max_length=128), user=Depends(current)):
        return await execute(user, workspace_id, "mi_snapshot", session_id, instrument)

    @app.post(path + "/sessions/{session_id}/commands")
    async def command(workspace_id: uuid.UUID, session_id: str, request: Request, user=Depends(current)):
        raw = await json_body(request)
        command = mi_qa.request(raw, session_id)
        require(command["kind"] != "OPEN" or "reviewHash" in raw, "review", "MI_REVIEW_REQUIRED")
        job_id = request.headers.get("x-btl-job")
        try:
            job_id = uuid.UUID(job_id) if job_id is not None else uuid.uuid4()
        except ValueError:
            require(False, "jobId")
        return await execute(user, workspace_id, "replay", session_id, raw, write=True, job_id=job_id)

    @app.post(path + "/sessions/{session_id}/reviews")
    async def review(workspace_id: uuid.UUID, session_id: str,
                     request: Request, user=Depends(current)):
        return await execute(user, workspace_id, "mi_review", session_id, await json_body(request), write=True)

    @app.post(path + "/sessions/{session_id}/command-status")
    async def command_status(workspace_id: uuid.UUID, session_id: str,
                             request: Request, user=Depends(current)):
        return await execute(user, workspace_id, "mi_command_status", session_id, await json_body(request))

    @app.get(path + "/sessions/{session_id}/analytics")
    async def analytics(workspace_id: uuid.UUID, session_id: str, user=Depends(current)):
        return await execute(user, workspace_id, "mi_analytics", session_id)

    @app.get(path + "/sessions/{session_id}/{page}")
    async def history(workspace_id: uuid.UUID, session_id: str, page: str,
                      limit: int = Query(32, ge=1, le=64), after: int | None = None,
                      revision: int | None = None, user=Depends(current)):
        require(page in ("journal", "events"), "miPage", "RESOURCE_UNAVAILABLE")
        operation = "mi_terminal" if page == "journal" else "mi_events"
        return await execute(user, workspace_id, operation, session_id,
                             dict(limit=limit, after_sequence=after, revision_pin=revision))
