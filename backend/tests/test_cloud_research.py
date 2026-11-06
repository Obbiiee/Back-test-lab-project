"""Real verified identity + tenant + canonical tick service composition."""
import os
import secrets
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import time
from unittest.mock import patch

from cloud.app import create_app
from infrastructure.database import migrate, connect
from execution.research import ResearchApplication
from application.models import TrustedScope
from tests.test_identity import RecordingDelivery, client, PASSWORD
from tests.test_research_sessions import method, review_request
from tests.virtual_traders import COHORT_SIZES, build_stages

DSN = os.getenv('BTL_TEST_DATABASE_URL')


@unittest.skipUnless(DSN, 'Real isolated PostgreSQL required; skip is not PASS')
class CloudResearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        migrate(DSN)

    def setUp(self):
        self.delivery = RecordingDelivery()
        requested_users = int(os.environ.get('BTL_QA_VIRTUAL_TRADER_USERS', '5'))
        self.app = create_app(DSN, secrets.token_urlsafe(48), self.delivery,
                              rate_limit=max(200, requested_users * 20))
        self.client = client(self.app)
        self.actor, self.headers = self.account()
        self.workspace = self.client.post('/api/v1/workspaces', headers=self.headers,
                                          json={'name': 'Isolated research QA'}).json()['id']
        self.root = '/api/v1/workspaces/' + self.workspace + '/research'

    def account(self, email=None):
        email = email or (uuid.uuid4().hex + '@example.com')
        registered = self.client.post('/api/v1/auth/register', json={'email': email, 'password': PASSWORD})
        self.assertEqual(registered.status_code, 201, registered.text)
        verified = self.client.post('/api/v1/auth/verify', json={'token': self.delivery.token(email, 'verification')})
        self.assertEqual(verified.status_code, 200, verified.text)
        login = self.client.post('/api/v1/auth/login', data={'username': email, 'password': PASSWORD})
        self.assertEqual(login.status_code, 200, login.text)
        return registered.json()['id'], {'Authorization': 'Bearer ' + login.json()['access_token']}

    def test_summary_requires_identity_membership_and_hides_foreign_session(self):
        app = ResearchApplication(DSN, TrustedScope(self.workspace,self.actor))
        m=method();app.create_method(m)
        session='session:'+uuid.uuid4().hex
        app.create_session(dict(id=session,name='Summary QA',methodId=m['id'],initialBalance='10000',startPeriod='2020-01'))
        path=self.root+'/sessions/'+session+'/summary'
        response=self.client.get(path,headers=self.headers)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json(),app.summary(session))
        self.assertEqual(response.headers['cache-control'],'no-store')
        self.assertNotIn('controller',response.json())
        self.assertNotIn('quote',response.json())
        self.assertEqual(self.client.get(path).status_code,401)
        foreign_actor,foreign_headers=self.account()
        self.assertNotEqual(foreign_actor,self.actor)
        self.assertEqual(self.client.get(path,headers=foreign_headers).status_code,404)
        other=self.client.post('/api/v1/workspaces',headers=foreign_headers,json={'name':'Foreign summary QA'}).json()['id']
        foreign_path='/api/v1/workspaces/'+other+'/research/sessions/'+session+'/summary'
        self.assertEqual(self.client.get(foreign_path,headers=foreign_headers).status_code,404)
        app.close()

    def test_product_method_and_session_pages_are_authenticated_bounded_metadata(self):
        app = ResearchApplication(DSN, TrustedScope(self.workspace, self.actor))
        methods = [method() for _ in range(2)]
        methods.sort(key=lambda item: item['id'])
        for record in methods:
            app.create_method(record)
        session_ids = []
        for index, record in enumerate(methods):
            session_id = 'session:product-page-' + uuid.uuid4().hex
            session_ids.append(session_id)
            app.create_session({'id': session_id, 'name': f'Product page {index}',
                                'methodId': record['id'], 'initialBalance': '10000',
                                'startPeriod': '2020-01'})

        method_page = self.client.get(self.root + '/methods?limit=1', headers=self.headers)
        self.assertEqual(method_page.status_code, 200, method_page.text)
        first = method_page.json()
        self.assertEqual(first['artifact'], 'BTL-METHOD-PAGE-1')
        self.assertEqual(len(first['items']), 1)
        self.assertFalse(first['complete'])
        detail = self.client.get(self.root + '/methods/' + first['items'][0]['id'], headers=self.headers)
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertEqual(detail.json()['method'], first['items'][0])
        second = self.client.get(self.root + '/methods?limit=1&after=' + first['nextCursor'], headers=self.headers)
        self.assertEqual(second.status_code, 200, second.text)
        self.assertTrue(second.json()['complete'])
        self.assertNotEqual(first['items'][0]['id'], second.json()['items'][0]['id'])

        sessions = self.client.get(self.root + '/sessions?limit=1&methodId=' + methods[0]['id'],
                                   headers=self.headers)
        self.assertEqual(sessions.status_code, 200, sessions.text)
        page = sessions.json()
        self.assertEqual(page['artifact'], 'BTL-SESSION-PAGE-1')
        self.assertEqual(len(page['items']), 1)
        item = page['items'][0]
        self.assertEqual(item['metadata']['id'], session_ids[0])
        self.assertEqual(item['metadata']['methodId'], methods[0]['id'])
        self.assertEqual(item['metadata']['startPeriod'], '2020-01')
        self.assertEqual(item['revision'], 0)
        self.assertEqual(item['financialCountsStatus'], 'NOT_COMPUTED_ON_LIST')
        self.assertNotIn('orders', item)
        analytics = self.client.get(self.root + '/methods/' + methods[0]['id'] + '/analytics',
                                    headers=self.headers)
        self.assertEqual(analytics.status_code, 200, analytics.text)
        aggregate = analytics.json()
        self.assertEqual(aggregate['artifact'], 'BTL-METHOD-ANALYTICS-1')
        self.assertEqual(aggregate['status'], 'COMPLETE')
        self.assertEqual(aggregate['aggregation'], 'POOLED_COMMITTED_COMPLETED_POSITIONS')
        self.assertEqual(aggregate['includedSessions'][0]['sessionId'], session_ids[0])
        self.assertEqual(aggregate['metrics']['tradeCount'], 0)
        self.assertFalse(aggregate['balancesCombined'])
        self.assertNotIn('balance', aggregate)
        self.assertEqual(self.client.get(self.root + '/sessions').status_code, 401)
        self.assertEqual(self.client.get(self.root + '/methods/' + methods[0]['id'] + '/analytics').status_code, 401)

        _foreign_actor, foreign_headers = self.account()
        self.assertEqual(self.client.get(self.root + '/methods', headers=foreign_headers).status_code, 404)
        self.assertEqual(self.client.get(self.root + '/methods/' + methods[0]['id'],
                                         headers=foreign_headers).status_code, 404)
        self.assertEqual(self.client.get(self.root + '/methods/' + methods[0]['id'] + '/analytics',
                                         headers=foreign_headers).status_code, 404)
        self.assertEqual(self.client.get(self.root + '/sessions?limit=51', headers=self.headers).status_code, 422)
        app.close()

    def test_paginated_journal_route_keeps_workspace_authority_and_financial_projection(self):
        app=ResearchApplication(DSN,TrustedScope(self.workspace,self.actor))
        record=method();app.create_method(record)
        session='session:'+uuid.uuid4().hex
        created=app.create_session(dict(id=session,name='Paged Journal QA',methodId=record['id'],
                                         initialBalance='10000',startPeriod='2020-01'))
        review=review_request(created);approved=app.review(review)
        app.confirm(session,dict(reviewId=review['requestId'],reviewHash=approved['reviewHash']))
        path=self.root+'/sessions/'+session+'/journal/pages?limit=1'
        response=self.client.get(path,headers=self.headers)
        self.assertEqual(response.status_code,200,response.text)
        page=response.json()
        self.assertEqual(page['artifact'],'BTL-TICK-JOURNAL-PAGE-1')
        self.assertEqual(page['totalOrders'],1)
        self.assertEqual([order['id'] for order in page['orders']],[review['requestId']])
        self.assertTrue(page['complete']);self.assertIsNone(page['nextCursor'])
        self.assertEqual(page['financialAuthority'],'COMMITTED_EVENTS_ONLY')
        self.assertEqual(self.client.get(path).status_code,401)
        _foreign_actor,foreign_headers=self.account()
        self.assertEqual(self.client.get(path,headers=foreign_headers).status_code,404)
        app.close()

    def test_verified_scope_canonical_session_and_hostile_tenant(self):
        m = method()
        created = self.client.post(self.root + '/methods', headers=self.headers, json=m)
        self.assertEqual(created.status_code, 200, created.text)
        payload = {'id': 'session:' + uuid.uuid4().hex, 'name': 'Scoped fixture', 'methodId': m['id'],
                   'initialBalance': '10000', 'startPeriod': '2020-01'}
        created = self.client.post(self.root + '/sessions', headers=self.headers, json=payload)
        self.assertEqual(created.status_code, 200, created.text)
        view = created.json()
        path = self.root + '/sessions/' + payload['id']
        review_body = review_request(view)
        reviewed = self.client.post(self.root + '/reviews', headers=self.headers, json=review_body)
        self.assertEqual(reviewed.status_code, 200, reviewed.text)
        pin = {'reviewId': review_body['requestId'], 'reviewHash': reviewed.json()['reviewHash']}
        result = self.client.post(path + '/confirm', headers=self.headers, json=pin)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertTrue(result.json()['durable'])
        status = self.client.get(path + '/commands/' + review_body['requestId'], headers=self.headers)
        self.assertEqual(status.status_code, 200, status.text)
        self.assertEqual(status.json()['status'], 'COMMITTED')
        self.assertTrue(status.json()['receipt']['durable'])
        before = self.client.get(path, headers=self.headers).content
        _, other = self.account()
        for verb, target, body in [('GET', path, None),
                                   ('GET', path + '/commands/' + review_body['requestId'], None),
                                   ('POST', path + '/confirm', pin),
                                   ('GET', self.root + '/catalog', None)]:
            refused = self.client.request(verb, target, headers=other, json=body)
            self.assertEqual(refused.status_code, 404, refused.text)
        self.assertEqual(self.client.get(path, headers=self.headers).content, before)
        self.assertEqual(self.client.get(path).status_code, 401)
        self.assertIn('SYNTHETIC', view['label'])
        self.assertNotIn('sidecar', created.text)

    def test_concurrent_identical_confirm_returns_one_durable_receipt(self):
        """A lost/racing response must not create a second financial command."""
        from threading import Barrier

        record = method()
        self.assertEqual(self.client.post(self.root + '/methods', headers=self.headers,
                                          json=record).status_code, 200)
        session_id = 'session:' + uuid.uuid4().hex
        created = self.client.post(self.root + '/sessions', headers=self.headers, json={
            'id': session_id, 'name': 'Concurrent confirm QA', 'methodId': record['id'],
            'initialBalance': '10000', 'startPeriod': '2020-01'})
        self.assertEqual(created.status_code, 200, created.text)
        review = review_request(created.json())
        reviewed = self.client.post(self.root + '/reviews', headers=self.headers, json=review)
        self.assertEqual(reviewed.status_code, 200, reviewed.text)
        pin = {'reviewId': review['requestId'], 'reviewHash': reviewed.json()['reviewHash']}
        path = self.root + '/sessions/' + session_id + '/confirm'

        barrier = Barrier(3)

        def confirm():
            barrier.wait(timeout=5)
            return self.client.post(path, headers=self.headers, json=pin)

        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(confirm)
            second = pool.submit(confirm)
            barrier.wait(timeout=5)
            responses = (first.result(timeout=20), second.result(timeout=20))

        self.assertEqual([response.status_code for response in responses], [200, 200])
        self.assertEqual(responses[0].content, responses[1].content)
        self.assertTrue(responses[0].json()['durable'])
        status = self.client.get(self.root + '/sessions/' + session_id +
                                 '/commands/' + review['requestId'], headers=self.headers)
        self.assertEqual(status.status_code, 200, status.text)
        self.assertEqual(status.json()['status'], 'COMMITTED')
        self.assertTrue(status.json()['receipt']['durable'])
        journal = self.client.get(self.root + '/sessions/' + session_id + '/journal',
                                  headers=self.headers)
        self.assertEqual(journal.status_code, 200, journal.text)
        self.assertEqual([order['id'] for order in journal.json()['orders']], [review['requestId']])
        self.assertEqual(len(journal.json()['orders']), 1)

    def test_virtual_traders_complete_isolated_authenticated_journey(self):
        """A bounded synthetic cohort journey; never a capacity certification."""
        requested_users = int(os.environ.get('BTL_QA_VIRTUAL_TRADER_USERS', '5'))
        self.assertIn(requested_users, COHORT_SIZES)
        base_run_id = uuid.UUID(os.environ['BTL_QA_VIRTUAL_TRADER_RUN_ID']) \
            if os.environ.get('BTL_QA_VIRTUAL_TRADER_RUN_ID') else uuid.uuid4()
        cohort = next(stage for stage in build_stages(base_run_id)
                      if stage.requested_users == requested_users)
        traders = []
        for trader in cohort.traders:
            actor, headers = self.account(email=trader.email)
            created_workspace = self.client.post('/api/v1/workspaces', headers=headers,
                                                 json={'name': f'Virtual trader {trader.ordinal}'})
            self.assertEqual(created_workspace.status_code, 201, created_workspace.text)
            workspace = created_workspace.json()['id']
            root = f'/api/v1/workspaces/{workspace}/research'

            record = method()
            record['id'] = trader.method_id
            created_method = self.client.post(root + '/methods', headers=headers, json=record)
            self.assertEqual(created_method.status_code, 200, created_method.text)
            request = {'id': trader.session_id, 'name': f'Virtual trader {trader.ordinal} QA',
                       'methodId': trader.method_id, 'initialBalance': '10000', 'startPeriod': '2020-01'}
            created_session = self.client.post(root + '/sessions', headers=headers, json=request)
            self.assertEqual(created_session.status_code, 200, created_session.text)

            review = review_request(created_session.json())
            review['requestId'] = trader.command_id
            reviewed = self.client.post(root + '/reviews', headers=headers, json=review)
            self.assertEqual(reviewed.status_code, 200, reviewed.text)
            confirmed = self.client.post(
                root + '/sessions/' + trader.session_id + '/confirm', headers=headers,
                json={'reviewId': review['requestId'], 'reviewHash': reviewed.json()['reviewHash']})
            self.assertEqual(confirmed.status_code, 200, confirmed.text)
            duplicate = self.client.post(
                root + '/sessions/' + trader.session_id + '/confirm', headers=headers,
                json={'reviewId': review['requestId'], 'reviewHash': reviewed.json()['reviewHash']})
            self.assertEqual(duplicate.content, confirmed.content)
            status = self.client.get(root + '/sessions/' + trader.session_id + '/commands/' + trader.command_id,
                                     headers=headers)
            self.assertEqual(status.status_code, 200, status.text)
            self.assertEqual(status.json()['status'], 'COMMITTED')
            self.assertTrue(status.json()['receipt']['durable'])
            journal = self.client.get(root + '/sessions/' + trader.session_id + '/journal', headers=headers)
            self.assertEqual(journal.status_code, 200, journal.text)
            self.assertEqual([order['id'] for order in journal.json()['orders']], [trader.command_id])
            storage = self.client.get(root + '/sessions/' + trader.session_id + '/metering/storage', headers=headers)
            self.assertEqual(storage.status_code, 200, storage.text)
            self.assertEqual(storage.json()['artifact'], 'BTL-SESSION-STORAGE-METRICS-1')
            self.assertEqual(storage.json()['tables']['sessionState']['rows'], 1)
            self.assertEqual(storage.json()['tables']['commandsAndReceipts']['rows'], 1)
            self.assertEqual(storage.json()['integrityStatus'], 'NOT_CHECKED_BY_STORAGE_METER')
            self.assertEqual(storage.json()['totals']['rows'],
                             sum(table['rows'] for table in storage.json()['tables'].values()))
            self.assertIsNone(storage.json()['tradeCount'])
            self.assertEqual(storage.json()['tradeCountStatus'], 'NOT_COMPUTED_FROM_STORAGE_COUNTERS')
            self.assertEqual(storage.json()['closedTradeEventCount'], 0)
            self.assertEqual(storage.json()['closedTradeEventCountStatus'],
                             'CONTENT_HASHED_EVENT_SCAN_NOT_FINANCIAL_VERIFICATION')
            self.assertIsNone(storage.json()['perSessionWalBytes'])
            self.assertIsNone(storage.json()['sharedCanonicalDatasetBytes'])
            traders.append((actor, headers, root, trader.session_id))

        for index, (_actor, headers, root, session_id) in enumerate(traders):
            self.assertEqual(self.client.get(root + '/sessions/' + session_id, headers=headers).status_code, 200)
            if len(traders) <= 5:
                foreign_sessions = [item[3] for other_index, item in enumerate(traders)
                                    if other_index != index]
            else:
                # Linear-cost ring sampling keeps the 100-user functional
                # cohort bounded while exercising every tenant boundary.
                foreign_sessions = [traders[(index + 1) % len(traders)][3]] if len(traders) > 1 else []
            for other_session in foreign_sessions:
                foreign = self.client.get(root + '/sessions/' + other_session, headers=headers)
                self.assertEqual(foreign.status_code, 404, foreign.text)
                foreign_metrics = self.client.get(root + '/sessions/' + other_session + '/metering/storage',
                                                  headers=headers)
                self.assertEqual(foreign_metrics.status_code, 404, foreign_metrics.text)

    def test_session_creation_honors_durable_job_header(self):
        method_id = 'method:' + uuid.uuid4().hex
        request = {'id': 'session:' + uuid.uuid4().hex, 'name': 'Queued session',
                   'methodId': method_id, 'initialBalance': '10000', 'startPeriod': '2020-01'}
        job_id = str(uuid.uuid4())
        queued = {'schemaVersion': 1, 'jobId': job_id, 'state': 'QUEUED', 'result': None}
        with patch('cloud.research.queue.submit', return_value=queued) as submit:
            response = self.client.post(self.root + '/sessions', headers={**self.headers, 'X-BTL-Job': job_id}, json=request)
        self.assertEqual(response.status_code, 202, response.text)
        self.assertEqual(response.json(), queued)
        args = submit.call_args.args
        self.assertEqual(args[4], 'create_session')
        self.assertEqual(args[5], (request,))
        self.assertEqual(str(args[3]), job_id)
        invalid = self.client.post(self.root + '/sessions', headers={**self.headers, 'X-BTL-Job': 'not-a-uuid'}, json=request)
        self.assertEqual(invalid.status_code, 422, invalid.text)

    def test_observed_replay_to_honors_durable_job_header(self):
        session='session:'+uuid.uuid4().hex
        request={'schemaVersion':1,'artifact':'BTL-OBSERVED-REPLAY-TO-1','requestId':uuid.uuid4().hex,
                 'sessionId':session,'expectedRevision':0,'targetNs':'1700000000000000000','timeframe':'1m'}
        job_id=str(uuid.uuid4());queued={'schemaVersion':1,'jobId':job_id,'state':'QUEUED','result':None}
        with patch('cloud.research.queue.submit',return_value=queued) as submit:
            response=self.client.post(self.root+'/sessions/'+session+'/replay-to',
                                      headers={**self.headers,'X-BTL-Job':job_id},json=request)
        self.assertEqual(response.status_code,202,response.text);self.assertEqual(response.json(),queued)
        args=submit.call_args.args
        self.assertEqual(args[3:5],(uuid.UUID(job_id),'replay_to'));self.assertEqual(args[5],(session,request))

    def test_member_read_only_then_revocation_and_logout(self):
        member, header = self.account()
        record = method()
        self.assertEqual(self.client.post(self.root + '/methods', headers=self.headers, json=record).status_code, 200)
        session_id = 'session:' + uuid.uuid4().hex
        session = {'id': session_id, 'name': 'Owner metering scope', 'methodId': record['id'],
                   'initialBalance': '10000', 'startPeriod': '2020-01'}
        self.assertEqual(self.client.post(self.root + '/sessions', headers=self.headers, json=session).status_code, 200)
        target = '/api/v1/workspaces/' + self.workspace + '/members'
        self.assertEqual(self.client.post(target, headers=self.headers, json={'userId': member}).status_code, 204)
        self.assertEqual(self.client.get(self.root + '/catalog', headers=header).status_code, 200)
        self.assertEqual(self.client.post(self.root + '/methods', headers=header, json=method()).status_code, 403)
        self.assertEqual(self.client.get(self.root + '/sessions/' + session_id + '/metering/storage',
                                         headers=header).status_code, 403)
        self.assertEqual(self.client.delete(target + '/' + member, headers=self.headers).status_code, 204)
        self.assertEqual(self.client.get(self.root + '/catalog', headers=header).status_code, 404)
        self.assertEqual(self.client.post('/api/v1/auth/logout-all', headers=self.headers).status_code, 204)
        self.assertEqual(self.client.get(self.root + '/catalog', headers=self.headers).status_code, 401)

    def test_tls_duplicate_fields_and_unknown_operations_refused(self):
        response = self.client.get('http://testserver' + self.root + '/catalog', headers=self.headers)
        self.assertEqual(response.status_code, 426)
        response = self.client.post(self.root + '/methods', headers={**self.headers, 'Content-Type': 'application/json'},
                                    content='{"id":"one","id":"two"}')
        self.assertNotEqual(response.status_code, 200)
        response = self.client.post(self.root + '/sessions/session:qa/provider', headers=self.headers, json={})
        self.assertEqual(response.status_code, 404)
        response = self.client.post(self.root + '/methods', headers={**self.headers, 'X-BTL-Source': 'historical'}, json=method())
        self.assertEqual(response.status_code, 422)

    def test_verified_user_lock_covers_inner_commit_not_only_preflight(self):
        entered, release = Event(), Event()
        original = ResearchApplication.create_method
        record = method()
        marker = 'qa-revoke-' + uuid.uuid4().hex

        def held(application, raw):
            entered.set()
            self.assertTrue(release.wait(8))
            return original(application, raw)

        def revoke():
            with connect(DSN) as db:
                db.execute('SELECT set_config(\'application_name\',%s,true)', (marker,))
                db.execute('UPDATE btl.users SET is_active=false WHERE id=%s', (self.actor,))

        with patch('cloud.research.ResearchApplication.create_method', held), ThreadPoolExecutor(max_workers=2) as pool:
            writing = pool.submit(self.client.post, self.root + '/methods', headers=self.headers, json=record)
            try:
                self.assertTrue(entered.wait(5))
                revoking = pool.submit(revoke)
                deadline = time.monotonic() + 4
                blocked = False
                while time.monotonic() < deadline:
                    with connect(DSN) as db:
                        blocked = db.execute("SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE application_name=%s AND wait_event_type='Lock')", (marker,)).fetchone()[0]
                    if blocked:
                        break
                    time.sleep(.01)
                self.assertTrue(blocked, 'Revocation must wait for the enclosing authorization transaction')
            finally:
                release.set()
            self.assertEqual(writing.result(timeout=10).status_code, 200)
            revoking.result(timeout=10)
        self.assertEqual(self.client.get(self.root + '/catalog', headers=self.headers).status_code, 401)
        with connect(DSN) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM btl.tick_methods WHERE workspace_id=%s AND method_id=%s',
                                       (self.workspace, record['id'])).fetchone()[0], 1)
