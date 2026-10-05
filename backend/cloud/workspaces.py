"""Versioned private metadata/intake routes; no engine, migration or cloud sync."""
import json
import uuid
from functools import partial
from datetime import datetime, timezone

import anyio
from fastapi import Depends, Request, Query
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, StrictInt, Field

from identity.store import User
from workspace.store import WorkspaceStore
from workspace.intake import MembershipWorkflow
from application.service import IntakeApplication
from application.models import TrustedScope
from application.transport import handle_review, handle_confirm
from contracts.canonical import canonical_bytes
from contracts.primitives import ContractError


class Named(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=128)


class ResourceCreate(Named):
    kind: str


class ResourceAmend(Named):
    expectedRevision: StrictInt = Field(ge=0, le=9007199254740991)


class MemberCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    userId: uuid.UUID


class Clock:
    def now_utc(self):
        return datetime.now(timezone.utc)


class Ids:
    def next_id(self, kind, scope, session_id, request_id):
        return kind + ":" + str(uuid.uuid4())


def install(app):
    store = WorkspaceStore(app.state.dsn)
    current = app.state.current_user
    prefix = "/api/v1/workspaces"
    async def call(method, *args, **kwargs):
        return await anyio.to_thread.run_sync(partial(method, *args, **kwargs))
    @app.exception_handler(ContractError)
    async def domain_error(request, error):
        statuses = {"RESOURCE_UNAVAILABLE": 404, "UNAUTHORIZED": 401, "OWNER_REQUIRED": 403, "WRITE_FORBIDDEN": 403,
                    "SCOPE_MISMATCH": 403, "STALE_REVISION": 409, "IDEMPOTENCY_CONFLICT": 409, "INVALID_INPUT": 422}
        status = statuses.get(error.code, 503)
        body = {"detail": error.code if status != 503 else "SERVICE_UNAVAILABLE"}
        return Response(canonical_bytes({"schemaVersion": 1, **body}), status_code=status, media_type="application/json")
    @app.post(prefix, status_code=201)
    async def create(body: Named, user: User = Depends(current)):
        return await call(store.create, user.id, body.name)
    @app.get(prefix)
    async def list_workspaces(limit: int = Query(50, ge=1, le=50), after: uuid.UUID | None = None, user: User = Depends(current)):
        return await call(store.list, user.id, limit, after)
    @app.get(prefix+"/{workspace_id}")
    async def get_workspace(workspace_id: uuid.UUID, user: User = Depends(current)):
        return await call(store.get, user.id, workspace_id)
    @app.post(prefix+"/{workspace_id}/members", status_code=204)
    async def member(workspace_id: uuid.UUID, body: MemberCreate, user: User = Depends(current)):
        await call(store.add_member, user.id, workspace_id, body.userId)
    @app.delete(prefix+"/{workspace_id}/members/{target_id}", status_code=204)
    async def remove(workspace_id: uuid.UUID, target_id: uuid.UUID, user: User = Depends(current)):
        await call(store.remove_member, user.id, workspace_id, target_id)
    @app.post(prefix+"/{workspace_id}/resources", status_code=201)
    async def create_resource(workspace_id: uuid.UUID, body: ResourceCreate, user: User = Depends(current)):
        return await call(store.create_resource, user.id, workspace_id, body.kind, body.name)
    @app.get(prefix+"/{workspace_id}/resources")
    async def resources(workspace_id: uuid.UUID, limit: int = Query(50, ge=1, le=50), after: uuid.UUID | None = None, user: User = Depends(current)):
        return await call(store.resources, user.id, workspace_id, limit, after)
    @app.get(prefix+"/{workspace_id}/resources/{resource_id}")
    async def resource(workspace_id: uuid.UUID, resource_id: uuid.UUID, user: User = Depends(current)):
        return await call(store.get_resource, user.id, workspace_id, resource_id)
    @app.patch(prefix+"/{workspace_id}/resources/{resource_id}")
    async def rename(workspace_id: uuid.UUID, resource_id: uuid.UUID, body: ResourceAmend, user: User = Depends(current)):
        return await call(store.amend_resource, user.id, workspace_id, resource_id, body.expectedRevision, body.name)
    @app.delete(prefix+"/{workspace_id}/resources/{resource_id}", status_code=204)
    async def archive(workspace_id: uuid.UUID, resource_id: uuid.UUID, expectedRevision: int = Query(ge=0, le=9007199254740991), user: User = Depends(current)):
        await call(store.amend_resource, user.id, workspace_id, resource_id, expectedRevision, archive=True)
    @app.get(prefix+"/{workspace_id}/resources/{resource_id}/passport")
    async def passport(workspace_id: uuid.UUID, resource_id: uuid.UUID, revision: int = Query(0, ge=0, le=9007199254740991), user: User = Depends(current)):
        raw = await call(store.passport, user.id, workspace_id, resource_id, revision)
        return Response(raw, media_type="application/json")
    async def intake(handler, workspace_id, session_id, request, user):
        workflow = MembershipWorkflow(app.state.dsn, user.id, workspace_id, session_id)
        application = IntakeApplication(workflow, Clock(), Ids())
        raw = await request.body()
        result = await call(handler, raw, TrustedScope(str(workspace_id), str(user.id)), application)
        body = json.loads(result.body_json_bytes)
        if result.status == 200:
            body["durable"], body["persistence"] = True, "POSTGRESQL"
        return Response(canonical_bytes(body), status_code=result.status, media_type="application/json")
    @app.post(prefix+"/{workspace_id}/sessions/{session_id}/reviews")
    async def review(workspace_id: uuid.UUID, session_id: uuid.UUID, request: Request, user: User = Depends(current)):
        return await intake(handle_review, workspace_id, session_id, request, user)
    @app.post(prefix+"/{workspace_id}/sessions/{session_id}/confirmations")
    async def confirm(workspace_id: uuid.UUID, session_id: uuid.UUID, request: Request, user: User = Depends(current)):
        return await intake(handle_confirm, workspace_id, session_id, request, user)
