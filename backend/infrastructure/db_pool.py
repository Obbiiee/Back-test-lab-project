"""Optional per-process PostgreSQL connection reuse (QA flag BTL_DB_POOL=1; default OFF = every connect() opens and closes a connection, as before).

Why: the API opens a fresh PostgreSQL connection (fork, authentication, catalog warm-up) for every research request AND for every identity lookup.
Reuse changes only WHEN a connection is opened, never what a request may read or write:
  * tenancy is enforced by query predicates, not by session state (no SET ROLE / set_config / search_path anywhere), so a reused connection carries no identity;
  * a connection is reused only after the previous holder's transaction ended cleanly (commit, or rollback on error) and it is back in the IDLE state;
  * client-side attributes callers mutate (row_factory, autocommit, cursor_factory) are reset on every checkout;
  * a connection that is closed, broken, in a transaction, too old or used too often is closed instead of reused;
  * the DATABASE budget (BTL_DB_BUDGET, default 12) still bounds ACTIVE holders; idle connections are bounded separately (BTL_DB_POOL_MAX_IDLE, default 8).
The operator must keep (budget + max idle) summed over processes below PostgreSQL max_connections.
"""
import asyncio
import os
import threading
import time
from collections import deque

import psycopg
from psycopg.rows import dict_row, tuple_row

MAX_AGE_SECONDS = 300.0
MAX_USES = 5000
STALE_CHECK_AFTER_SECONDS = 5.0


def enabled():
    return os.environ.get('BTL_DB_POOL') == '1'


def max_idle():
    raw = os.environ.get('BTL_DB_POOL_MAX_IDLE')
    if raw is None or raw == '':
        return 8
    if not (raw.isascii() and raw.isdigit() and 0 <= int(raw) <= 32):
        from contracts.primitives import ContractError
        raise ContractError('INVALID_INPUT', 'BTL_DB_POOL_MAX_IDLE')
    return int(raw)


class _Entry:
    __slots__ = ('conn', 'created', 'last', 'uses')

    def __init__(self, conn):
        self.conn, self.created, self.last, self.uses = conn, time.monotonic(), time.monotonic(), 0


def _healthy(conn, entry):
    if conn.closed or conn.broken:
        return False
    if conn.info.transaction_status != psycopg.pq.TransactionStatus.IDLE:
        return False
    now = time.monotonic()
    return now - entry.created < MAX_AGE_SECONDS and entry.uses < MAX_USES


class SyncPool:
    def __init__(self):
        self.lock = threading.Lock()
        self.idle = {}                      # dsn -> deque[_Entry]
        self.stats = dict(opened=0, reused=0, discarded=0)

    def take(self, dsn):
        while True:
            with self.lock:
                queue = self.idle.get(dsn)
                entry = queue.pop() if queue else None
            if entry is None:
                return None
            if not _healthy(entry.conn, entry):
                self._discard(entry)
                continue
            if time.monotonic() - entry.last > STALE_CHECK_AFTER_SECONDS:
                try:
                    entry.conn.execute('SELECT 1')
                    entry.conn.rollback()
                except psycopg.Error:
                    self._discard(entry)
                    continue
            with self.lock:
                self.stats['reused'] += 1
            return entry

    def _discard(self, entry):
        with self.lock:
            self.stats['discarded'] += 1
        try:
            entry.conn.close()
        except psycopg.Error:
            pass

    def put(self, dsn, entry):
        entry.uses += 1
        entry.last = time.monotonic()
        if not _healthy(entry.conn, entry):
            self._discard(entry)
            return
        with self.lock:
            queue = self.idle.setdefault(dsn, deque())
            if len(queue) < max_idle():
                queue.append(entry)
                return
        self._discard(entry)

    def close_all(self):
        with self.lock:
            entries = [e for q in self.idle.values() for e in q]
            self.idle.clear()
        for entry in entries:
            self._discard(entry)


class AsyncPool:
    """Same rules for psycopg.AsyncConnection; bound to the event loop that created the connections (one per API process)."""
    def __init__(self):
        self.idle = {}
        self.loop = None
        self.stats = dict(opened=0, reused=0, discarded=0)

    def _check_loop(self):
        loop = asyncio.get_running_loop()
        if self.loop is not loop:                       # a different event loop (tests): never reuse connections across loops
            self.idle.clear()
            self.loop = loop

    async def take(self, dsn):
        self._check_loop()
        queue = self.idle.get(dsn)
        while queue:
            entry = queue.pop()
            if not _healthy(entry.conn, entry):
                await self._discard(entry)
                continue
            if time.monotonic() - entry.last > STALE_CHECK_AFTER_SECONDS:
                try:
                    await entry.conn.execute('SELECT 1')
                    await entry.conn.rollback()
                except psycopg.Error:
                    await self._discard(entry)
                    continue
            self.stats['reused'] += 1
            return entry
        return None

    async def _discard(self, entry):
        self.stats['discarded'] += 1
        try:
            await entry.conn.close()
        except psycopg.Error:
            pass

    async def put(self, dsn, entry):
        entry.uses += 1
        entry.last = time.monotonic()
        if not _healthy(entry.conn, entry):
            await self._discard(entry)
            return
        self._check_loop()
        queue = self.idle.setdefault(dsn, deque())
        if len(queue) < max_idle():
            queue.append(entry)
            return
        await self._discard(entry)


SYNC = SyncPool()
ASYNC = AsyncPool()


def reset_sync(conn, cursor_factory):
    conn.row_factory = tuple_row
    conn.autocommit = False
    conn.cursor_factory = cursor_factory


def reset_async(conn):
    conn.row_factory = dict_row                     # identity code never changes autocommit; nothing else client-side is mutated there
