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
    window = entitlements.session_window(scope.workspace_id, session)
    require(window is not None, "miWindow", "RESOURCE_UNAVAILABLE")
    focus = options[0] if operation == "mi_snapshot" and options else None
    view = store.snapshot(scope, session, required_manifest_sha=sha,
                          focus=focus, open_sources=mi_qa.open_sources)
    require(window["tier"] == "PRO" or int(view["state"]["throughNs"]) < window["endNs"],
            "miWindow", "REFUSED_SOURCE")
    if operation == "mi_snapshot":
        return view
    if operation == "mi_command_status":
        raw, = options
        command = mi_qa.request(raw, session)
        return store.command_status(scope, command, jump=raw["jump"], required_manifest_sha=sha)
    if operation == "mi_analytics":
        return store.project(scope, session)
    arguments, = options
    if arguments["revision_pin"] is None:
        arguments = dict(arguments, revision_pin=view["state"]["revision"])
    reader = store.terminal_page if operation == "mi_terminal" else store.event_page
    return reader(scope, session, **arguments)


def guard_worker(dsn, workspace_id, session_id, command):
    """Product manifest jobs recheck the durable historical entitlement at execution."""
    catalog, sha = mi_qa.manifest()
    if catalog["artifact"] != PRODUCT_SOURCE:
        return
    window = Entitlements(dsn).session_window(workspace_id, session_id)
    require(window is not None, "miWindow", "RESOURCE_UNAVAILABLE")
    if window["tier"] != "PRO":
        view = MultiInstrumentStore(dsn).snapshot(
            TrustedScope(workspace_id, "internal:mi"), session_id, required_manifest_sha=sha)
        require(int(view["state"]["throughNs"]) < window["endNs"], "miWindow", "REFUSED_SOURCE")
    if command["kind"] == "ADVANCE":
        target = uint(command["payload"]["targetNs"])
        require(target >= window["startNs"] and
                (window["tier"] == "PRO" or target < window["endNs"]),
                "miWindow", "REFUSED_SOURCE")


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
        mi_qa.request(raw, session_id)
        job_id = request.headers.get("x-btl-job")
        try:
            job_id = uuid.UUID(job_id) if job_id is not None else uuid.uuid4()
        except ValueError:
            require(False, "jobId")
        return await execute(user, workspace_id, "replay", session_id, raw, write=True, job_id=job_id)

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
