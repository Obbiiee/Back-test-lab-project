"""Bounded streaming body, shared DB rate protection, no-store and safe errors."""
import hashlib
import json
import logging
import uuid
import anyio
from urllib.parse import parse_qs
from starlette.responses import JSONResponse
from contracts.primitives import ContractError
from .store import connection, audit

log = logging.getLogger(__name__)

# IP-level protection is reserved for requests that can create, verify, recover,
# or exchange credentials. Routine identity reads and sign-out are covered by
# the global API budget instead, so legitimate users behind one NAT do not
# exhaust a shared authentication bucket merely by opening their workspace.
_SENSITIVE_AUTH_REQUESTS = {
    ("POST", "/api/v1/auth/register"),
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/verify"),
    ("POST", "/api/v1/auth/forgot-password"),
    ("POST", "/api/v1/auth/request-verify-token"),
    ("POST", "/api/v1/auth/reset-password"),
    ("GET", "/api/v1/auth/google/start"),
    ("POST", "/api/v1/auth/google/link/start"),
    ("GET", "/api/v1/auth/google/callback"),
    ("POST", "/api/v1/auth/google/exchange"),
}


class IdentityBoundary:
    def __init__(self, app, dsn, limit=30, api_limit=600, max_bytes=16384):
        if type(limit) is not int or not 1 <= limit <= 1200 or type(api_limit) is not int or not 1 <= api_limit <= 1200:
            raise ValueError('BOUNDED_API_RATE_LIMIT_REQUIRED')
        self.app, self.dsn, self.limit, self.api_limit, self.max_bytes = app, dsn, limit, api_limit, max_bytes

    async def _attempt(self, key, limit):
        key = hashlib.sha256(key.encode()).hexdigest()
        async with connection(self.dsn) as db:
            row = await (await db.execute("INSERT INTO btl.auth_rate_limits VALUES (%s,floor(extract(epoch FROM clock_timestamp())/60)::bigint,1) ON CONFLICT(key,bucket) DO UPDATE SET attempts=btl.auth_rate_limits.attempts+1 RETURNING attempts", (key,))).fetchone()
            await db.execute("DELETE FROM btl.auth_rate_limits WHERE (key,bucket) IN (SELECT key,bucket FROM btl.auth_rate_limits WHERE bucket < floor(extract(epoch FROM clock_timestamp())/60)-360 LIMIT 1000)")
            if row["attempts"] == limit + 1:
                await audit(db, "AUTH_RATE_LIMITED")
        return row["attempts"] <= limit

    async def __call__(self, scope, receive, send):
        started = False
        correlation = uuid.uuid4().hex
        async def guard_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                message["headers"] = [*message["headers"], (b"x-request-id", correlation.encode())]
            await send(message)
        try:
            await self._call(scope, receive, guard_send)
        except Exception as error:
            if started or scope["type"] != "http":
                raise
            if isinstance(error, ContractError) and error.code == "RESOURCE_CAPACITY":
                # The identity database budget refused this request before a
                # connection or route handler was entered. Tell clients this
                # is an explicit no-op admission refusal so safe retries remain
                # distinguishable from an ambiguous database failure.
                await JSONResponse({"detail": "SERVICE_BUSY"}, status_code=503,
                                   headers={"Cache-Control": "no-store", "Retry-After": "1",
                                            "X-Request-ID": correlation})(scope, receive, send)
                return
            # Database diagnostic text is retained only for permission errors;
            # it identifies the denied object without request data or DSNs.
            sqlstate = getattr(error, "sqlstate", None)
            object_error = None
            if sqlstate == "42501":
                diagnostic = getattr(error, "diag", None)
                object_error = getattr(diagnostic, "message_primary", None)
            log.error("Identity boundary unavailable requestId=%s type=%s sqlstate=%s objectError=%s",
                      correlation, type(error).__name__, sqlstate, object_error)
            await JSONResponse({"detail": "SERVICE_UNAVAILABLE"}, status_code=503,
                               headers={"Cache-Control": "no-store", "X-Request-ID": correlation})(scope, receive, send)

    async def _call(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        async def protected_send(message):
            if message["type"] == "http.response.start":
                message["headers"] = [*message["headers"], (b"cache-control", b"no-store"), (b"pragma", b"no-cache")]
                if scope.get("scheme") == "https":
                    message["headers"].append((b"strict-transport-security", b"max-age=31536000"))
            await send(message)
        if scope.get("scheme") != "https":
            return await JSONResponse({"detail": "TLS_REQUIRED"}, status_code=426)(scope, receive, protected_send)
        if scope["path"].startswith("/api/v1/"):
            # Never trust X-Forwarded-For. Configure a trusted proxy before deployment.
            ip = (scope.get("client") or ("unknown",))[0]
            if not await self._attempt("api-ip:"+ip, self.api_limit):
                return await JSONResponse({"detail": "RATE_LIMITED"}, status_code=429, headers={"Retry-After": "60"})(scope, receive, protected_send)
            if (scope["method"], scope["path"]) in _SENSITIVE_AUTH_REQUESTS and not await self._attempt('auth-ip:'+ip,self.limit):
                return await JSONResponse({"detail": "RATE_LIMITED"}, status_code=429, headers={"Retry-After": "60"})(scope, receive, protected_send)
        total, messages = 0, []
        with anyio.fail_after(5):
            while True:
                message = await receive()
                if message["type"] != "http.request":
                    return
                total += len(message.get("body", b""))
                if total > self.max_bytes:
                    return await JSONResponse({"detail": "BODY_TOO_LARGE"}, status_code=413)(scope, receive, protected_send)
                messages.append(message)
                if not message.get("more_body"):
                    break
        account = None
        raw = b"".join(message.get("body", b"") for message in messages)
        if scope["method"] == "POST" and scope["path"] == "/api/v1/auth/login":
            try:
                account = parse_qs(raw.decode("utf-8"), max_num_fields=16).get("username", [None])[0]
            except (ValueError, UnicodeDecodeError):
                pass  # Framework refuses malformed input; IP bound still applies.
        elif scope["method"] == "POST" and scope["path"] in {"/api/v1/auth/forgot-password", "/api/v1/auth/request-verify-token"}:
            try:
                data = json.loads(raw)
                account = data.get("email") if type(data) is dict else None
            except (ValueError, UnicodeDecodeError):
                pass
        if type(account) is str and 0 < len(account) <= 320 and not any(0xD800 <= ord(char) <= 0xDFFF for char in account):
            if not await self._attempt("account:"+scope["path"]+":"+account.lower(), 10):
                return await JSONResponse({"detail": "RATE_LIMITED"}, status_code=429, headers={"Retry-After": "60"})(scope, receive, protected_send)
        async def bounded_receive():
            if messages:
                return messages.pop(0)
            return {"type": "http.disconnect"}
        async def response_send(message):
            if message["type"] == "http.response.start":
                if scope["path"].startswith("/api/v1/auth/") and message["status"] in (400, 401, 403):
                    async with connection(self.dsn) as db:
                        await audit(db, "AUTH_REQUEST_REFUSED")
            await protected_send(message)
        await self.app(scope, bounded_receive, response_send)
