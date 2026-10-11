"""Process-local admission before allocation; no queue or financial authority.

Operator must budget the sum across processes below PostgreSQL max_connections
with reserved headroom. No DSN, subject or request data enters these counters.
"""
from contextlib import contextmanager
from threading import Lock

from contracts.primitives import require


class Budget:
    def __init__(self, limit):
        require(type(limit) is int and 1 <= limit <= 64, 'resourceLimit')
        self.limit = limit
        self.active = self.peak = self.rejected = 0
        self.lock = Lock()

    @contextmanager
    def claim(self):
        with self.lock:
            if self.active >= self.limit:
                self.rejected += 1
                require(False, 'capacity', 'RESOURCE_CAPACITY')
            self.active += 1
            self.peak = max(self.peak, self.active)
        try:
            yield
        finally:
            with self.lock:
                self.active -= 1

    def snapshot(self):
        with self.lock:
            return dict(limit=self.limit, active=self.active, peak=self.peak, rejected=self.rejected)


DATABASE = Budget(12)


class ApiAdmission:
    """Cheap bounded gate outside auth/rate DB work, including slow body reads."""
    def __init__(self, app, limit=8):
        self.app = app
        self.budget = Budget(limit)

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or not scope.get('path', '').startswith('/api/v1/'):
            return await self.app(scope, receive, send)
        from contracts.primitives import ContractError
        from starlette.responses import JSONResponse
        entered = False
        try:
            with self.budget.claim():
                entered = True
                return await self.app(scope, receive, send)
        except ContractError as error:
            if entered or error.code != 'RESOURCE_CAPACITY':
                raise
            await JSONResponse({'detail': 'SERVICE_BUSY'}, status_code=503,
                               headers={'Cache-Control': 'no-store', 'Retry-After': '1'})(scope, receive, send)
