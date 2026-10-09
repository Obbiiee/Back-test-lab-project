"""Opt-in loopback-only local-alpha transport. No public identity composition."""
import asyncio
from collections import deque
from ipaddress import ip_address
import json
import os
import time

import anyio
from fastapi import FastAPI, Request
from fastapi.responses import Response
from contracts.canonical import canonical_bytes
from contracts.primitives import ContractError, require
from .research import ResearchApplication

ORIGINS = frozenset({"http://127.0.0.1:5173","http://localhost:5173",
                     "http://127.0.0.1:5196","http://localhost:5196"})


def unique_object(pairs):
    result = {}
    for key,value in pairs:
        require(key not in result,"duplicateKey")
        result[key] = value
    return result


async def body(request):
    raw = bytearray()
    with anyio.fail_after(5):
        async for chunk in request.stream():
            raw.extend(chunk)
            require(len(raw) <= 32768,"body","BODY_TOO_LARGE")
    try:
        value = json.loads(raw,object_pairs_hook=unique_object,
                           parse_constant=lambda _:require(False,"nonFinite"))
    except (ValueError, UnicodeError):
        require(False,"body")
    require(type(value) is dict,"body")
    return value


def create_local_app(dsn, *, port=5188):
    app = FastAPI(title="Backtest Lab local tick alpha",docs_url=None,redoc_url=None,openapi_url=None)
    application = ResearchApplication(dsn)
    recent = deque()
    limiter = anyio.CapacityLimiter(2)
    admission = anyio.Semaphore(2)

    def response(value,status=200):
        return Response(canonical_bytes({"schemaVersion":1,**value}),status_code=status,media_type="application/json",
                        headers={"Cache-Control":"no-store","X-Content-Type-Options":"nosniff"})

    @app.middleware("http")
    async def boundary(request: Request, call_next):
        origin = request.headers.get("origin")
        try:
            local = request.client is not None and ip_address(request.client.host).is_loopback
        except ValueError:
            local = False
        if not local or request.headers.get("host") not in {f"localhost:{port}",f"127.0.0.1:{port}"} or origin not in ORIGINS:
            return response({"detail":"LOCAL_ONLY"},403)
        if request.method == "OPTIONS":
            if request.headers.get("access-control-request-method") not in {"GET","POST"}:
                return response({"detail":"METHOD_NOT_ALLOWED"},405)
            result = Response(status_code=204)
            result.headers["Access-Control-Allow-Methods"] = "GET, POST"
            result.headers["Access-Control-Allow-Headers"] = "Content-Type, X-BTL-Local"
        else:
            if request.method not in {"GET","POST"} or request.headers.get("x-btl-local") != "1" or request.headers.get("transfer-encoding") or request.url.query:
                return response({"detail":"LOCAL_REQUEST_REQUIRED"},403)
            if request.method == "POST" and request.headers.get("content-type","").split(";")[0] != "application/json":
                return response({"detail":"JSON_REQUIRED"},415)
            now = time.monotonic()
            while recent and now-recent[0] >= 60:
                recent.popleft()
            if len(recent) >= 240:
                return response({"detail":"RATE_LIMITED"},429)
            recent.append(now)
            try:
                admission.acquire_nowait()
            except anyio.WouldBlock:
                result = response({"detail":"LOCAL_BUSY"},429)
            else:
                try:
                    result = await call_next(request)
                except ContractError as error:
                    result = response({"detail":error.code},413 if error.code=="BODY_TOO_LARGE" else 409)
                except TimeoutError:
                    result = response({"detail":"LOCAL_REQUEST_TIMEOUT"},408)
                except Exception:
                    # No DSN, raw exception, future record or filesystem path in responses.
                    result = response({"detail":"LOCAL_SERVICE_UNAVAILABLE"},503)
                finally:
                    admission.release()
        result.headers["Access-Control-Allow-Origin"] = origin
        result.headers["Vary"] = "Origin"
        result.headers["Cache-Control"] = "no-store"
        result.headers["X-Content-Type-Options"] = "nosniff"
        return result

    async def execute(function,*args):
        return response(await anyio.to_thread.run_sync(function,*args,limiter=limiter))

    @app.get("/api/v1/tick-alpha/catalog")
    async def catalog():
        return await execute(application.catalog)

    @app.post("/api/v1/tick-alpha/methods")
    async def create_method(request: Request):
        return await execute(application.create_method,await body(request))

    @app.post("/api/v1/tick-alpha/sessions")
    async def create_session(request: Request):
        return await execute(application.create_session,await body(request))

    @app.get("/api/v1/tick-alpha/sessions/{session_id}")
    async def session(session_id: str):
        return await execute(application.inspect,session_id)

    @app.post("/api/v1/tick-alpha/reviews")
    async def review(request: Request):
        return await execute(application.review,await body(request))

    @app.post("/api/v1/tick-alpha/sessions/{session_id}/confirm")
    async def confirm(session_id: str,request: Request):
        return await execute(application.confirm,session_id,await body(request))

    @app.post("/api/v1/tick-alpha/sessions/{session_id}/commands")
    async def command(session_id: str,request: Request):
        return await execute(application.apply,session_id,await body(request))

    return app


def main():
    import uvicorn
    config = uvicorn.Config(create_local_app(os.environ["BTL_DATABASE_URL"]),host="127.0.0.1",port=5188,
                            proxy_headers=False,access_log=False)
    factory = asyncio.SelectorEventLoop if os.name=="nt" else asyncio.new_event_loop
    asyncio.run(uvicorn.Server(config).serve(),loop_factory=factory)


if __name__=="__main__":
    main()
