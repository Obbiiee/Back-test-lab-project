"""Admission saturation before allocation and shared sync/async DB pressure."""
import asyncio
import os
from contextlib import ExitStack
import unittest
from unittest.mock import patch

from contracts.primitives import ContractError
from infrastructure.database import connect
from infrastructure.resources import Budget, DATABASE, ApiAdmission
from identity.store import connection


class ResourceTests(unittest.TestCase):
    def test_budget_rejects_before_entry_and_releases_on_failure(self):
        budget = Budget(2)
        with budget.claim(), budget.claim():
            with self.assertRaises(ContractError):
                with budget.claim():
                    self.fail('Overload may not enter')
            self.assertEqual(budget.snapshot(), dict(limit=2, active=2, peak=2, rejected=1))
        with self.assertRaises(ValueError):
            with budget.claim():
                raise ValueError('authored injected failure')
        self.assertEqual(budget.snapshot()['active'], 0)

    def test_sync_async_share_budget_no_connection_attempt_when_full(self):
        async def attempt():
            with self.assertRaises(ContractError):
                async with connection('authored-not-a-dsn'):
                    self.fail('Must not connect')
        with ExitStack() as stack:
            for _ in range(DATABASE.limit):
                stack.enter_context(DATABASE.claim())
            with patch('infrastructure.database.psycopg.connect') as sync_connect:
                with self.assertRaises(ContractError):
                    with connect('authored-not-a-dsn'):
                        self.fail('Must not connect')
                sync_connect.assert_not_called()
            with patch('identity.store.psycopg.AsyncConnection.connect') as async_connect:
                asyncio.run(attempt())
                async_connect.assert_not_called()
        self.assertEqual(DATABASE.snapshot()['active'], 0)

    def test_driver_failure_releases_reserved_slot(self):
        with patch('infrastructure.database.psycopg.connect', side_effect=ValueError('injected')):
            with self.assertRaises(ValueError):
                with connect('authored-not-a-dsn'):
                    self.fail('Must fail before yield')
        self.assertEqual(DATABASE.snapshot()['active'], 0)

    @unittest.skipUnless(os.getenv('BTL_TEST_DATABASE_URL'), 'Real PostgreSQL required; skip is not acceptance')
    def test_actual_postgres_ceiling_and_post_failure_reuse(self):
        dsn = os.environ['BTL_TEST_DATABASE_URL']
        with ExitStack() as stack:
            connections = [stack.enter_context(connect(dsn)) for _ in range(DATABASE.limit)]
            self.assertEqual(len({db.info.backend_pid for db in connections}), DATABASE.limit)
            self.assertEqual(connections[0].execute('SELECT 1').fetchone(), (1,))
            with self.assertRaises(ContractError):
                with connect(dsn):
                    self.fail('Thirteenth connection must be refused')
        self.assertEqual(DATABASE.snapshot()['active'], 0)
        with connect(dsn) as db:
            self.assertEqual(db.execute('SELECT 1').fetchone(), (1,))

    def test_outer_gate_rejects_without_receive_or_downstream_work(self):
        async def scenario():
            entered = asyncio.Event()
            release = asyncio.Event()
            calls = []
            async def application(scope, receive, send):
                calls.append(scope['path'])
                entered.set()
                await release.wait()
            async def receive():
                self.fail('Overload must not read a body')
            messages = []
            async def send(message):
                messages.append(message)
            boundary = ApiAdmission(application, limit=1)
            scope = dict(type='http', path='/api/v1/auth/login')
            first = asyncio.create_task(boundary(scope, receive, send))
            await entered.wait()
            await boundary(scope, receive, send)
            self.assertEqual(len(calls), 1)
            self.assertEqual(messages[0]['status'], 503)
            self.assertIn((b'retry-after', b'1'), messages[0]['headers'])
            release.set()
            await first
            self.assertEqual(boundary.budget.snapshot()['active'], 0)
        asyncio.run(scenario())
