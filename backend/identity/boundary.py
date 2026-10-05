"""Bounded streaming body, shared DB rate protection, no-store and safe errors."""
import hashlib
import json
import logging
import uuid
from urllib.parse import parse_qs
from starlette.responses import JSONResponse
from .store import connection, audit

log = logging.getLogger(__name__)


class IdentityBoundary:
    def __init__(self, app, dsn, limit=30, max_bytes=16384):
        self.app, self.dsn, self.limit, self.max_bytes = app, dsn, limit, max_bytes

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
            log.error("Identity boundary unavailable requestId=%s type=%s", correlation, type(error).__name__)
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
            if not await self._attempt("ip:"+ip, self.limit):
                return await JSONResponse({"detail": "RATE_LIMITED"}, status_code=429, headers={"Retry-After": "60"})(scope, receive, protected_send)
        total, messages = 0, []
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
