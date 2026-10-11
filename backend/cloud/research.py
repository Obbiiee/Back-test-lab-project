"""Verified workspace composition; private loopback datasets are never mounted."""
from functools import partial
import uuid

import anyio
from fastapi import Depends, Request
from fastapi.responses import Response
from psycopg.rows import dict_row

from application.models import TrustedScope
from contracts.canonical import canonical_bytes
from contracts.primitives import require
from execution.local_api import body
from execution.research import ResearchApplication
from identity.store import User
from infrastructure.database import connect
from workspace.policy import owner
from workspace.store import WorkspaceUnit


def run(dsn, actor_id, workspace_id, operation, args=(), *, write=False):
    # Keep verified-user/membership locks through the INNER service commit.
    # A preflight check alone would allow revocation between check and write.
    with connect(dsn) as db:
        db.row_factory = dict_row
        unit = WorkspaceUnit(db, actor_id, workspace_id)
        if write:
            owner(unit.role)
        research = ResearchApplication(dsn, TrustedScope(str(workspace_id), str(actor_id)))
        try:
            return getattr(research, operation)(*args)
        finally:
            research.close()


def install(app):
    prefix = '/api/v1/workspaces/{workspace_id}/research'
    current = app.state.current_user
    admission = anyio.Semaphore(2)
    limiter = anyio.CapacityLimiter(2)

    async def json_body(request):
        require(request.headers.get('content-type', '').split(';')[0] == 'application/json', 'contentType')
        require(not request.url.query and not request.headers.get('x-btl-source'), 'source')
        return await body(request)

    async def execute(user, workspace_id, operation, *args, write=False):
        try:
            admission.acquire_nowait()
        except anyio.WouldBlock:
            return Response(canonical_bytes({'schemaVersion': 1, 'detail': 'RESEARCH_BUSY'}),
                            status_code=429, media_type='application/json')
        try:
            value = await anyio.to_thread.run_sync(
                partial(run, app.state.dsn, user.id, workspace_id, operation, args, write=write),
                limiter=limiter)
            raw = canonical_bytes({'schemaVersion': 1, **value})
            require(len(raw) <= 8388608, 'response', 'REFUSED_RESPONSE_LIMIT')
            return Response(raw, media_type='application/json', headers={'X-Content-Type-Options': 'nosniff'})
        finally:
            admission.release()

    @app.get(prefix + '/catalog')
    async def catalog(workspace_id: uuid.UUID, user: User = Depends(current)):
        return await execute(user, workspace_id, 'catalog')

    @app.post(prefix + '/methods')
    async def method(workspace_id: uuid.UUID, request: Request, user: User = Depends(current)):
        return await execute(user, workspace_id, 'create_method', await json_body(request), write=True)

    @app.post(prefix + '/sessions')
    async def create_session(workspace_id: uuid.UUID, request: Request, user: User = Depends(current)):
        return await execute(user, workspace_id, 'create_session', await json_body(request), write=True)

    @app.post(prefix + '/reviews')
    async def review(workspace_id: uuid.UUID, request: Request, user: User = Depends(current)):
        return await execute(user, workspace_id, 'review', await json_body(request), write=True)

    @app.get(prefix + '/sessions/{session_id}')
    async def inspect(workspace_id: uuid.UUID, session_id: str, user: User = Depends(current)):
        return await execute(user, workspace_id, 'inspect', session_id)

    @app.get(prefix + '/sessions/{session_id}/journal')
    async def journal(workspace_id: uuid.UUID, session_id: str, user: User = Depends(current)):
        return await execute(user, workspace_id, 'journal', session_id)

    @app.post(prefix + '/sessions/{session_id}/{operation}')
    async def session_operation(workspace_id: uuid.UUID, session_id: str, operation: str,
                                request: Request, user: User = Depends(current)):
        operations = {'view': ('workspace', False), 'bootstrap': ('bootstrap', False),
                      'journal': ('save_note', True), 'confirm': ('confirm', True), 'commands': ('apply', True)}
        require(operation in operations, 'operation', 'RESOURCE_UNAVAILABLE')
        name, write = operations[operation]
        return await execute(user, workspace_id, name, session_id, await json_body(request), write=write)
