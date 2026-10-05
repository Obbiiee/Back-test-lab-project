"""Local-only HTTP adapter. Public transport must supply real auth/rights later."""
import argparse
import time
from collections import deque
from ipaddress import ip_address

import anyio
from fastapi import FastAPI, Query, Request
from fastapi.responses import Response
from contracts.canonical import canonical_bytes
from contracts.primitives import ContractError
from .local import open_local


def create_local_app(service, *, port=5199, rate_limit=30):
    app = FastAPI(title='Backtest Lab local market data', docs_url=None, redoc_url=None, openapi_url=None)
    recent = deque()
    reads = anyio.CapacityLimiter(2)
    def response(data, status=200):
        return Response(canonical_bytes({'schemaVersion':1, **data}), status_code=status, media_type='application/json',
                        headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})
    @app.middleware('http')
    async def boundary(request: Request, call_next):
        # A loopback bind alone does not prevent DNS rebinding or browser-origin access.
        try:
            local = request.client is not None and ip_address(request.client.host).is_loopback
        except ValueError:
            local = False
        if not local or request.headers.get('host') not in {f'127.0.0.1:{port}',f'localhost:{port}'} or request.headers.get('origin') or request.headers.get('sec-fetch-site') == 'cross-site':
            return response({'detail':'LOCAL_ONLY'},403)
        if request.method != 'GET' or request.headers.get('transfer-encoding') or request.headers.get('content-length','0') != '0':
            return response({'detail':'READ_ONLY'},405)
        if len(request.scope.get('query_string',b'')) > 2048:
            return response({'detail':'QUERY_TOO_LARGE'},413)
        permitted = {'version','start','end','limit','after','revealedBefore'} if request.url.path.endswith('/candles') else set()
        keys = [key for key, _ in request.query_params.multi_items()]
        if len(keys) != len(set(keys)) or not set(keys).issubset(permitted):
            return response({'detail':'INVALID_QUERY'},422)
        now = time.monotonic()
        while recent and now-recent[0] >= 60:
            recent.popleft()
        if len(recent) >= rate_limit:
            return response({'detail':'RATE_LIMITED'},429)
        recent.append(now)
        try:
            return await call_next(request)
        except ContractError as error:
            status = 409 if error.code == 'VERSION_MISMATCH' else 403 if error.code == 'ACCESS_DENIED' else 503 if error.code in {'CORRUPT_ARTIFACT','ARTIFACT_TOO_LARGE'} else 422
            return response({'detail':error.code},status)
        except Exception:
            return response({'detail':'SERVICE_UNAVAILABLE'},503)
    @app.get('/api/v1/local-market/dataset')
    async def descriptor():
        return response(service.descriptor())
    @app.get('/api/v1/local-market/candles')
    async def candles(version: str, start: int, end: int, limit: int = Query(1000,ge=1,le=10000), after: int | None = None, revealedBefore: int | None = None):
        from functools import partial
        data = await anyio.to_thread.run_sync(partial(service.read, version,start,end,limit,after,revealedBefore),limiter=reads)
        return response(data)
    return app


def main():
    import uvicorn
    parser = argparse.ArgumentParser(description='Read-only personal local M1 delivery; never a public server')
    parser.add_argument('--root',required=True)
    parser.add_argument('--port',type=int,default=5199)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('Port must be 1024–65535')
    service = open_local(args.root)
    uvicorn.run(create_local_app(service,port=args.port),host='127.0.0.1',port=args.port,proxy_headers=False,access_log=False)


if __name__ == '__main__':
    main()
