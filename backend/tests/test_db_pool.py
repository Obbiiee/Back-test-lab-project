"""BTL_DB_POOL=1 (QA flag, default off): reuse is invisible to callers and never carries state between holders."""
import asyncio
import os
import threading
import unittest
from unittest.mock import patch

import psycopg
from psycopg.rows import dict_row

from contracts.primitives import ContractError
from infrastructure import db_pool
from infrastructure.database import connect
from infrastructure.resources import DATABASE

DSN = os.getenv('BTL_TEST_DATABASE_URL')


@unittest.skipUnless(DSN, 'BTL_TEST_DATABASE_URL required')
class SyncPool(unittest.TestCase):
    def setUp(self):
        db_pool.SYNC.close_all()
        db_pool.SYNC.stats.update(opened=0, reused=0, discarded=0)

    def pid(self):
        with connect(DSN) as db:
            return db.execute('SELECT pg_backend_pid()').fetchone()[0]

    def test_default_off_opens_a_fresh_backend_each_time(self):
        with patch.dict(os.environ, {'BTL_DB_POOL': '0'}):
            self.assertNotEqual(self.pid(), self.pid())
            self.assertEqual(db_pool.SYNC.stats['opened'], 0)

    def test_on_reuses_a_clean_backend(self):
        with patch.dict(os.environ, {'BTL_DB_POOL': '1'}):
            first, second = self.pid(), self.pid()
            self.assertEqual(first, second)
            self.assertEqual(db_pool.SYNC.stats['opened'], 1)
            self.assertGreaterEqual(db_pool.SYNC.stats['reused'], 1)

    def test_client_state_never_leaks_to_the_next_holder(self):
        with patch.dict(os.environ, {'BTL_DB_POOL': '1'}):
            with connect(DSN) as db:
                db.row_factory = dict_row
                self.assertIsInstance(db.execute('SELECT 1 AS one').fetchone(), dict)
            with connect(DSN) as db:
                self.assertIsInstance(db.execute('SELECT 1').fetchone(), tuple)      # row_factory reset
                self.assertFalse(db.autocommit)

    def test_exception_rolls_back_and_nothing_is_committed(self):
        with patch.dict(os.environ, {'BTL_DB_POOL': '1'}):
            with connect(DSN) as db:
                db.execute('CREATE TEMP TABLE IF NOT EXISTS pool_probe(x int)')
                db.execute('TRUNCATE pool_probe')
            with self.assertRaises(RuntimeError):
                with connect(DSN) as db:
                    db.execute('INSERT INTO pool_probe VALUES (1)')
                    raise RuntimeError('boom')
            with connect(DSN) as db:
                # temp tables are per-session: seeing it proves the same backend was reused, and the insert was rolled back
                self.assertEqual(db.execute('SELECT count(*) FROM pool_probe').fetchone()[0], 0)

    def test_commit_on_clean_exit(self):
        with patch.dict(os.environ, {'BTL_DB_POOL': '1'}):
            with connect(DSN) as db:
                db.execute('CREATE TEMP TABLE IF NOT EXISTS pool_probe2(x int)')
                db.execute('TRUNCATE pool_probe2')
                db.execute('INSERT INTO pool_probe2 VALUES (7)')
            with connect(DSN) as db:
                self.assertEqual(db.execute('SELECT x FROM pool_probe2').fetchone()[0], 7)
                self.assertEqual(db.info.transaction_status, psycopg.pq.TransactionStatus.INTRANS)   # a new transaction, not the old one

    def test_a_connection_that_cannot_be_returned_clean_is_closed_not_reused(self):
        with patch.dict(os.environ, {'BTL_DB_POOL': '1'}):
            with connect(DSN) as db:
                broken = db
                pid = db.execute('SELECT pg_backend_pid()').fetchone()[0]
                db.close()                                        # simulates a connection lost inside the request
            self.assertTrue(broken.closed)
            self.assertNotEqual(self.pid(), pid)
            self.assertGreaterEqual(db_pool.SYNC.stats['discarded'], 1)

    def test_active_budget_still_applies(self):
        with patch.dict(os.environ, {'BTL_DB_POOL': '1'}):
            held = []
            original = DATABASE.limit
            try:
                DATABASE.limit = DATABASE.active + 1
                with connect(DSN):
                    with self.assertRaises(ContractError) as caught:
                        with connect(DSN):
                            held.append(1)
                    self.assertEqual(caught.exception.code, 'RESOURCE_CAPACITY')
            finally:
                DATABASE.limit = original
            self.assertEqual(held, [])

    def test_threads_share_a_bounded_set_of_backends(self):
        with patch.dict(os.environ, {'BTL_DB_POOL': '1', 'BTL_DB_POOL_MAX_IDLE': '4'}):
            pids, errors = set(), []

            def work():
                try:
                    for _ in range(30):
                        pids.add(self.pid())
                except Exception as error:      # noqa: BLE001
                    errors.append(error)
            threads = [threading.Thread(target=work) for _ in range(6)]
            [t.start() for t in threads]; [t.join() for t in threads]
            self.assertEqual(errors, [])
            self.assertLessEqual(len(pids), 12)               # far fewer than the 180 requests: connections are reused
            self.assertLessEqual(sum(len(q) for q in db_pool.SYNC.idle.values()), 4)


@unittest.skipUnless(DSN, 'BTL_TEST_DATABASE_URL required')
class AsyncPool(unittest.TestCase):
    def test_identity_connection_reuse_and_reset(self):
        from identity.store import connection

        async def run():
            async with connection(DSN) as db:
                first = (await (await db.execute('SELECT pg_backend_pid() AS p')).fetchone())['p']
                db.row_factory = psycopg.rows.tuple_row
            async with connection(DSN) as db:
                row = await (await db.execute('SELECT pg_backend_pid() AS p')).fetchone()
                self.assertIsInstance(row, dict)                  # row_factory restored for the next holder
                return first, row['p']
        with patch.dict(os.environ, {'BTL_DB_POOL': '1'}):
            db_pool.ASYNC.idle.clear()
            first, second = asyncio.run(run())
            self.assertEqual(first, second)
        with patch.dict(os.environ, {'BTL_DB_POOL': '0'}):
            first, second = asyncio.run(run())
            self.assertNotEqual(first, second)


if __name__ == '__main__':
    unittest.main()
