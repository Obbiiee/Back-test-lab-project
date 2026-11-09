"""Real PostgreSQL notes, canonical identity, concurrent edits and unchanged money."""
from copy import deepcopy
import base64
from concurrent.futures import ThreadPoolExecutor
import os
import unittest
import uuid
from unittest.mock import patch

from application.models import TrustedScope
from contracts.canonical import canonical_bytes
from contracts.primitives import ContractError
from infrastructure.database import connect,migrate
from execution.research import ResearchApplication
from execution.journal import (note_text,note_tags,MAX_JOURNAL_ORDERS,encode_cursor,
                               decode_cursor)
from tests import test_research_sessions as sessions

DSN=os.getenv('BTL_TEST_DATABASE_URL')


class JournalInputTests(unittest.TestCase):
    def test_unicode_limits_controls_and_tags(self):
        self.assertEqual(note_text('<img src=x onerror=alert(1)>\n😀'),'<img src=x onerror=alert(1)>\n😀')
        for value in ('x'*4097,'\x00','\ud800',None):
            with self.assertRaises(ContractError):note_text(value)
        for value in (['a','a'],['a']*9,[' x'],['x'*33],['\n'],{}):
            with self.assertRaises(ContractError):note_tags(value)

    def test_journal_cursor_is_canonical_session_and_revision_bound(self):
        token=encode_cursor('session:cursor',7,'order:after')
        self.assertEqual(decode_cursor(token,'session:cursor'),(7,'order:after'))
        bad_json=base64.urlsafe_b64encode(b'{"schemaVersion":1,"artifact":"BTL-TICK-JOURNAL-CURSOR-1","sessionId":"session:cursor","revision":7,"afterOrderId":"order:after","extra":NaN}').decode().rstrip('=')
        for value,session in ((token,'session:other'),(token+'!','session:cursor'),('@@','session:cursor'),(bad_json,'session:cursor')):
            with self.assertRaises(ContractError):decode_cursor(value,session)


@unittest.skipUnless(DSN,'Real isolated PostgreSQL required; skips are not PASS')
class JournalTests(unittest.TestCase):
    create=sessions.ResearchSessionTests.create
    advance=sessions.ResearchSessionTests.advance

    @classmethod
    def setUpClass(cls):migrate(DSN)

    def setUp(self):
        self.scope=TrustedScope('journalqa:'+uuid.uuid4().hex,'fixture:operator')
        self.app=ResearchApplication(DSN,self.scope)
        view,body=self.create();self.session=body['id']
        raw=sessions.review_request(view);review=self.app.review(raw)
        self.app.confirm(self.session,dict(reviewId=raw['requestId'],reviewHash=review['reviewHash']))
        self.order=raw['requestId']
        self.raw=dict(orderId=self.order,expectedNoteRevision=0,text='<script>never execute</script>\nResearch only',tags=['review'])

    def test_cold_roundtrip_export_identity_retry_and_financial_bytes_unchanged(self):
        before=canonical_bytes(self.app.inspect(self.session))
        saved=self.app.save_note(self.session,self.raw)
        self.assertEqual(self.app.save_note(self.session,self.raw),saved)
        fresh=ResearchApplication(DSN,self.scope)
        exported=fresh.journal(self.session)
        self.assertEqual(exported['notes'],[saved])
        self.assertEqual(exported['provenance']['datasetVersion'],saved['datasetVersion'])
        self.assertEqual(exported['orders'][0]['id'],saved['orderId'])
        self.assertEqual(exported['orders'][0]['status'],'PENDING')
        self.assertIsNone(exported['orders'][0]['entryFillRef'])
        self.assertEqual(before,canonical_bytes(fresh.inspect(self.session)))
        self.app.save_note(self.session,dict(self.raw,expectedNoteRevision=1,text='',tags=[]))
        self.assertEqual(fresh.journal(self.session)['notes'][0]['noteRevision'],2)

    def test_revision_pinned_journal_pages_and_note_projection(self):
        view=self.app.inspect(self.session)
        second=sessions.review_request(view)
        reviewed=self.app.review(second)
        self.app.confirm(self.session,dict(reviewId=second['requestId'],reviewHash=reviewed['reviewHash']))
        first_page=self.app.journal_page(self.session,dict(limit=1,cursor=None))
        self.assertEqual(first_page['artifact'],'BTL-TICK-JOURNAL-PAGE-1')
        self.assertEqual(first_page['totalOrders'],2)
        self.assertEqual(len(first_page['orders']),1)
        self.assertIsNotNone(first_page['nextCursor'])
        self.assertEqual(first_page['complete'],False)
        order_id=first_page['orders'][0]['id']
        note=self.app.save_note(self.session,dict(orderId=order_id,expectedNoteRevision=0,
            text='page-bound note',tags=['qa']))
        first_page=self.app.journal_page(self.session,dict(limit=1,cursor=None))
        self.assertEqual(first_page['notes'],[note])
        second_page=self.app.journal_page(self.session,dict(limit=1,cursor=first_page['nextCursor']))
        self.assertEqual(second_page['totalOrders'],2)
        self.assertEqual(len(second_page['orders']),1)
        self.assertEqual(second_page['complete'],True)
        self.assertNotEqual(first_page['orders'][0]['id'],second_page['orders'][0]['id'])
        self.advance(self.app.inspect(self.session))
        with self.assertRaisesRegex(ContractError,'STALE_REVISION'):
            self.app.journal_page(self.session,dict(limit=1,cursor=first_page['nextCursor']))

    def test_scoped_foreign_unknown_extra_and_stale_refusal(self):
        self.app.save_note(self.session,self.raw)
        for raw in (dict(self.raw,text='competing'),dict(self.raw,orderId='order:unknown'),dict(self.raw,balance='999')):
            with self.assertRaises(ContractError):self.app.save_note(self.session,raw)
        foreign=ResearchApplication(DSN,TrustedScope('foreign:'+uuid.uuid4().hex,'fixture:operator'))
        for operation in (lambda:foreign.journal(self.session),lambda:foreign.save_note(self.session,self.raw)):
            with self.assertRaisesRegex(ContractError,'RESOURCE_UNAVAILABLE'):operation()
        _,other=self.create()
        with self.assertRaisesRegex(ContractError,'RESOURCE_UNAVAILABLE'):self.app.save_note(other['id'],self.raw)

    def test_concurrent_changes_have_one_winner_and_preserve_loser(self):
        def edit(text):
            try:return self.app.save_note(self.session,dict(self.raw,text=text))['text']
            except ContractError as error:return error.code
        with ThreadPoolExecutor(max_workers=2) as pool:result=list(pool.map(edit,['first','second']))
        self.assertEqual(result.count('REFUSED_STALE_NOTE'),1)
        self.assertIn(self.app.journal(self.session)['notes'][0]['text'],['first','second'])
        self.assertEqual(self.app.inspect(self.session)['state']['balance'],'10000')

    def test_corrupt_note_does_not_reset_or_export_and_snapshot_has_no_lifetime_cap(self):
        self.app.save_note(self.session,self.raw)
        with connect(DSN) as db:
            db.execute('UPDATE btl.tick_journal_notes SET content_hash=%s WHERE workspace_id=%s AND session_id=%s',('0'*64,self.scope.workspace_id,self.session))
        with self.assertRaisesRegex(ContractError,'CORRUPT_RECORD'):self.app.journal(self.session)
        with self.assertRaisesRegex(ContractError,'CORRUPT_RECORD'):self.app.save_note(self.session,dict(self.raw,expectedNoteRevision=1))
        projection=deepcopy(self.app.workspace(self.session,{'timeframe':'1m'})['analysis'])
        projection['orders']*=MAX_JOURNAL_ORDERS+1
        with patch('execution.research.project',return_value=projection):
            self.assertEqual(len(self.app.journal(self.session)['orders']),MAX_JOURNAL_ORDERS+1)

    def test_revealed_fill_identity_and_atomic_rollback(self):
        view=self.app.inspect(self.session);self.advance(view)
        exported=self.app.journal(self.session)
        order=exported['orders'][0]
        self.assertEqual(order['status'],'ACTIVE')
        self.assertIsNotNone(order['entryFillRef'])
        self.assertLessEqual(int(order['entryTimeNs']),int(self.app.inspect(self.session)['state']['throughNs']))
        native=__import__('execution.research',fromlist=['pack']).pack
        with patch('execution.research.pack',side_effect=RuntimeError('QA before commit')):
            with self.assertRaises(RuntimeError):self.app.save_note(self.session,self.raw)
        self.assertEqual(self.app.journal(self.session)['notes'],[])
        with patch('execution.research.pack',native):self.app.save_note(self.session,self.raw)
