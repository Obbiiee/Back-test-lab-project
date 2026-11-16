"""Bounded synthetic regression for the local terminal archive API adapter."""
import unittest
from unittest.mock import MagicMock, patch

from application.models import TrustedScope
from execution.postgres import PostgresExecutionStore, pack
from execution.terminal_order_archive import GENESIS, record


class LocalOrderHistoryPageTests(unittest.TestCase):
    def test_page_maps_verified_archive_and_pins_session_revision(self):
        scope=TrustedScope('workspace:page','actor:page')
        order={'id':'order:closed','status':'CLOSED','side':'LONG','quantity':'1'}
        item=record(session_id='session:page',sequence=0,revision=2,order_id=order['id'],
                    order=order,events=[],previous_hash=GENESIS)
        raw,sha=pack(item)
        state={'revision':3}
        db=MagicMock()
        db.execute.side_effect=[None,MagicMock(fetchone=MagicMock(return_value=('payload','hash',3,'v','p'))),
            MagicMock(fetchone=MagicMock(return_value=(1,))),
            MagicMock(fetchall=MagicMock(return_value=[(raw,sha,item['recordHash'],0)]))]
        db.__enter__.return_value=db
        with patch('execution.postgres.connect',return_value=db), \
             patch.object(PostgresExecutionStore,'_load_row',return_value={'state':state}):
            page=PostgresExecutionStore('synthetic:unused').order_history_page(
                scope,'session:page',limit=10)
        self.assertEqual(page['artifact'],'BTL-ORDER-HISTORY-PAGE-1')
        self.assertEqual(page['revision'],3)
        self.assertEqual(page['total'],1)
        self.assertEqual(page['records'][0]['orderId'],'order:closed')
        self.assertTrue(page['complete'])
        self.assertIsNone(page['nextCursor'])

    def test_stale_revision_is_refused_before_archive_read(self):
        scope=TrustedScope('workspace:page','actor:page')
        db=MagicMock()
        db.execute.side_effect=[None,MagicMock(fetchone=MagicMock(return_value=('payload','hash',3,'v','p')))]
        db.__enter__.return_value=db
        with patch('execution.postgres.connect',return_value=db), \
             patch.object(PostgresExecutionStore,'_load_row',return_value={'state':{'revision':3}}):
            with self.assertRaisesRegex(ValueError,'STALE_REVISION'):
                PostgresExecutionStore('synthetic:unused').order_history_page(
                    scope,'session:page',revision_pin=2)
        self.assertEqual(db.execute.call_count,2)


if __name__=='__main__':
    unittest.main()
