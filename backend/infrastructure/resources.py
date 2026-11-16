"""Process-local admission before allocation; no queue or financial authority.

Operator must budget the sum across processes below PostgreSQL max_connections
with reserved headroom. No DSN, subject or request data enters these counters.
"""
from contextlib import contextmanager
from threading import Lock

import anyio
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
    """Bound active API work and a small wait queue before body/DB allocation."""
    def __init__(self, app, limit=8, wait_limit=16, wait_seconds=10):
        require(type(limit) is int and 1 <= limit <= 64, 'apiAdmissionLimit')
        require(type(wait_limit) is int and 0 <= wait_limit <= 64, 'apiAdmissionWaitLimit')
        require(type(wait_seconds) in (int, float) and 0 < wait_seconds <= 30,
                'apiAdmissionWaitSeconds')
        self.app = app
        self.budget = Budget(limit)
        self.wait_limit = wait_limit
        self.wait_seconds = wait_seconds
        self.semaphore = anyio.Semaphore(limit)
        self.pending = 0
        self.pending_lock = Lock()

    def _reserve_waiter(self):
        with self.pending_lock:
            # Requests that can claim an immediately free active slot do not
            # consume the bounded waiting-room quota.
            if self.semaphore.value <= 0 and self.pending >= self.wait_limit:
                return False
            self.pending += 1
            return True

    def _release_waiter(self):
        with self.pending_lock:
            self.pending -= 1

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or not scope.get('path', '').startswith('/api/v1/'):
            return await self.app(scope, receive, send)
        from contracts.primitives import ContractError
        from starlette.responses import JSONResponse
        entered = False
        waiting = False
        acquired = False
        try:
            if not self._reserve_waiter():
                raise ContractError('RESOURCE_CAPACITY', 'capacity')
            waiting = True
            try:
                with anyio.fail_after(self.wait_seconds):
                    await self.semaphore.acquire()
                acquired = True
            except TimeoutError:
                raise ContractError('RESOURCE_CAPACITY', 'capacity') from None
            finally:
                if waiting:
                    self._release_waiter()
                    waiting = False
            with self.budget.claim():
                entered = True
                return await self.app(scope, receive, send)
        except ContractError as error:
            if entered or error.code != 'RESOURCE_CAPACITY':
                raise
            await JSONResponse({'detail': 'SERVICE_BUSY'}, status_code=503,
                               headers={'Cache-Control': 'no-store', 'Retry-After': '1'})(scope, receive, send)
        finally:
            if waiting:
                self._release_waiter()
            if acquired:
                self.semaphore.release()
