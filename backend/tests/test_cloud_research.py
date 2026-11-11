"""Real verified identity + tenant + canonical tick service composition."""
import os
import secrets
import unittest
import uuid
import asyncio
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock
import time
from unittest.mock import patch

from cloud.app import create_app
from infrastructure.database import migrate, connect
from execution.research import ResearchApplication
from application.models import TrustedScope
from tests.test_identity import RecordingDelivery, client, PASSWORD
from tests.test_research_sessions import method, review_request, STEP_NS
from tests.virtual_traders import COHORT_SIZES, build_stages

DSN = os.getenv('BTL_TEST_DATABASE_URL')


@unittest.skipUnless(DSN, 'Real isolated PostgreSQL required; skip is not PASS')
class CloudResearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        migrate(DSN)

    def setUp(self, start_workers=True):
        self.delivery = RecordingDelivery()
        requested_users = int(os.environ.get('BTL_QA_VIRTUAL_TRADER_USERS', '5'))
        self.app = create_app(DSN, secrets.token_urlsafe(48), self.delivery,
                              rate_limit=max(200, requested_users * 20))
        self.client = client(self.app)
        # TestClient only runs FastAPI lifespan hooks when entered as a context
        # manager. The product's queued 202 contract relies on those durable
        # workers, so integration tests must exercise the real lifecycle too.
        self._client_lifespan = self.client if start_workers else None
        if self._client_lifespan is not None:
            self._client_lifespan.__enter__()
        self.actor, self.headers = self.account()
        self.workspace = self.client.post('/api/v1/workspaces', headers=self.headers,
                                          json={'name': 'Isolated research QA'}).json()['id']
        self.root = '/api/v1/workspaces/' + self.workspace + '/research'

    def tearDown(self):
        if self._client_lifespan is not None:
            self._client_lifespan.__exit__(None, None, None)

    def account(self, email=None):
        email = email or (uuid.uuid4().hex + '@example.com')
        registered = self.client.post('/api/v1/auth/register', json={'email': email, 'password': PASSWORD})
        self.assertEqual(registered.status_code, 201, registered.text)
        verified = self.client.post('/api/v1/auth/verify', json={'token': self.delivery.token(email, 'verification')})
        self.assertEqual(verified.status_code, 200, verified.text)
        login = self.client.post('/api/v1/auth/login', data={'username': email, 'password': PASSWORD})
        self.assertEqual(login.status_code, 200, login.text)
        return registered.json()['id'], {'Authorization': 'Bearer ' + login.json()['access_token']}

    def completed_job_result(self, response, root=None, headers=None):
        """Resolve the API's documented immediate-or-durable-job response."""
        self.assertIn(response.status_code, (200, 202), response.text)
        if response.status_code == 200:
            return response.json()
        body = response.json()
        self.assertIn(body.get('state'), ('QUEUED', 'RUNNING'), body)
        job_id = body.get('jobId')
        self.assertIsInstance(job_id, str)
        root = root or self.root
        headers = headers or self.headers
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            current = self.client.get(root + '/jobs/' + job_id, headers=headers)
            self.assertEqual(current.status_code, 200, current.text)
            value = current.json()
            if value['state'] == 'SUCCEEDED':
                self.assertIsInstance(value.get('result'), dict)
                return value['result']
            self.assertIn(value['state'], ('QUEUED', 'RUNNING'), value)
            time.sleep(.01)
        self.fail('Durable research job did not complete before its bounded test deadline')

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
        capabilities = self.client.get('/api/v1/workspaces/' + self.workspace + '/capabilities',
                                       headers=self.headers)
        self.assertEqual(capabilities.status_code, 200, capabilities.text)
        capability = capabilities.json()
        self.assertEqual(capability['artifact'], 'BTL-WORKSPACE-CAPABILITIES-1')
        self.assertEqual(capability['role'], 'OWNER')
        self.assertTrue(capability['capabilities']['createSession'])
        self.assertEqual(capability['entitlement']['status'], 'NOT_CONFIGURED')
        self.assertFalse(capability['entitlement']['productionEntitlement'])
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

    def test_job_status_poll_has_reserved_thread_capacity_during_direct_reads(self):
        from cloud import queue

        session_ids = ['session:poll-isolation-' + uuid.uuid4().hex for _ in range(2)]
        job = queue.submit(DSN, uuid.UUID(self.actor), uuid.UUID(self.workspace), uuid.uuid4(),
                           'workspace', (session_ids[0], {'timeframe': '1m'}))
        readers_started = Event()
        both_reads_running = __import__('threading').Barrier(2, action=readers_started.set)
        release_reads = Event()

        def blocked_read(*_args, **_kwargs):
            both_reads_running.wait(timeout=5)
            if not release_reads.wait(timeout=5):
                raise TimeoutError('QA_DIRECT_READ_RELEASE_TIMEOUT')
            return {'artifact': 'QA-DIRECT-READ-1'}

        paths = [self.root + '/catalog' for _session_id in session_ids]
        try:
            with patch('cloud.research.run', side_effect=blocked_read):
                with ThreadPoolExecutor(max_workers=2) as pool:
                    reads = [pool.submit(self.client.get, path, headers=self.headers) for path in paths]
                    started = readers_started.wait(5)
                    if not started:
                        release_reads.set()
                        outcomes = [future.result(timeout=10) for future in reads]
                        self.fail(f'direct-read fixtures did not occupy both bounded slots: {outcomes!r}')
                    self.app.state.qa_timing = True
                    try:
                        poll = self.client.get(self.root + '/jobs/' + str(job['jobId']), headers=self.headers)
                    finally:
                        self.app.state.qa_timing = False
                    self.assertEqual(poll.status_code, 200, poll.text)
                    self.assertEqual(poll.json()['state'], 'QUEUED')
                    self.assertRegex(poll.headers.get('server-timing', ''),
                                     r'^queue-thread-wait;dur=[0-9.]+, queue-query;dur=[0-9.]+$')
                    release_reads.set()
                    responses = [future.result(timeout=10) for future in reads]
                    self.assertEqual([response.status_code for response in responses], [200, 200])
            self.app.state.qa_timing = True
            try:
                timed = self.client.get(self.root + '/catalog', headers=self.headers)
            finally:
                self.app.state.qa_timing = False
            self.assertEqual(timed.status_code, 200, timed.text)
            self.assertRegex(timed.headers.get('server-timing', ''),
                             r'^research-admission;dur=[0-9.]+, research-thread-wait;dur=[0-9.]+, research-operation;dur=[0-9.]+$')
        finally:
            release_reads.set()

    def test_committed_analysis_projection_is_reused_across_research_instances(self):
        from execution.research import ResearchApplication
        from execution.analysis_cache import COMMITTED_ANALYSIS_CACHE

        app = ResearchApplication(DSN, TrustedScope(self.workspace, self.actor))
        record = method()
        app.create_method(record)
        session_id = 'session:analysis-cache-' + uuid.uuid4().hex
        app.create_session({'id': session_id, 'name': 'Analysis cache QA',
                            'methodId': record['id'], 'initialBalance': '10000',
                            'startPeriod': '2020-01'})
        try:
            first = app.workspace(session_id, {'timeframe': '1m'})
            self.assertEqual(first['analysis']['status'], 'COMPLETE')
            key = COMMITTED_ANALYSIS_CACHE.key(dsn=DSN, workspace_id=self.workspace,
                session_id=session_id, revision=first['state']['revision'],
                event_head=first['state']['eventHash'], quote=first['quote'])
            entry = COMMITTED_ANALYSIS_CACHE.get(key)
            self.assertEqual(entry['artifact'], 'BTL-COMMITTED-ANALYSIS-CACHE-1')
        finally:
            app.close()

        resumed = ResearchApplication(DSN, TrustedScope(self.workspace, self.actor))
        try:
            with patch('execution.research.project', side_effect=AssertionError('projection cache miss')):
                page = resumed.journal_page(session_id, {'limit': 32, 'cursor': None})
            self.assertEqual(page['artifact'], 'BTL-TICK-JOURNAL-PAGE-1')
            self.assertEqual(page['financialAuthority'], 'COMMITTED_EVENTS_ONLY')
            self.assertEqual(page['totalOrders'], 0)
        finally:
            resumed.close()

    def test_method_analytics_pools_positive_committed_synthetic_trades_only(self):
        from fractions import Fraction
        from execution.contracts import text

        app = ResearchApplication(DSN, TrustedScope(self.workspace, self.actor))
        record = method()
        saved_method = self.client.post(self.root + '/methods', headers=self.headers, json=record)
        self.assertEqual(saved_method.status_code, 200, saved_method.text)

        def advance(session_id, steps):
            target = int(app.inspect(session_id)['state']['throughNs']) + steps * STEP_NS
            for _ in range(512):
                view = app.inspect(session_id)
                state = view['state']
                if int(state['throughNs']) >= target or state['ended']:
                    return view
                command = {'schemaVersion': 1, 'artifact': 'BTL-TICK-EXECUTION-COMMAND-1',
                           'sessionId': session_id, 'commandId': 'analytics-advance:' + uuid.uuid4().hex,
                           'expectedRevision': state['revision'], 'kind': 'ADVANCE',
                           'payload': {'targetNs': str(target)}}
                app.apply(session_id, command)
            self.fail('Synthetic analytics advance did not reach its requested tick target')

        def completed_trade(label, *, pre_advance, post_fill_advance, side='LONG'):
            session_id = 'session:analytics-' + label + '-' + uuid.uuid4().hex
            session_payload = {'id': session_id, 'name': 'Analytics ' + label,
                               'methodId': record['id'], 'initialBalance': '10000',
                               'startPeriod': '2020-01'}
            created = self.client.post(self.root + '/sessions', headers=self.headers,
                                       json=session_payload)
            view = self.completed_job_result(created)
            if pre_advance:
                view = advance(session_id, pre_advance)
            request = review_request(view)
            request['draft']['side'] = side
            review_response = self.client.post(self.root + '/reviews', headers=self.headers, json=request)
            self.assertEqual(review_response.status_code, 200, review_response.text)
            reviewed = review_response.json()
            confirmed = self.client.post(self.root + '/sessions/' + session_id + '/confirm',
                headers=self.headers,
                json={'reviewId': request['requestId'], 'reviewHash': reviewed['reviewHash']})
            self.assertEqual(confirmed.status_code, 200, confirmed.text)
            self.assertTrue(confirmed.json()['durable'])
            receipt = self.client.get(self.root + '/sessions/' + session_id + '/commands/' + request['requestId'],
                                      headers=self.headers)
            self.assertEqual(receipt.status_code, 200, receipt.text)
            self.assertEqual(receipt.json()['status'], 'COMMITTED')
            self.assertTrue(receipt.json()['receipt']['durable'])
            journal_after_confirm = self.client.get(self.root + '/sessions/' + session_id + '/journal',
                                                     headers=self.headers)
            self.assertEqual(journal_after_confirm.status_code, 200, journal_after_confirm.text)
            self.assertEqual([order['id'] for order in journal_after_confirm.json()['orders']],
                             [request['requestId']])
            advance(session_id, 1)  # the pending market order is filled from the next authored quote
            if post_fill_advance:
                advance(session_id, post_fill_advance)
            state = app.inspect(session_id)['state']
            order_id = next(iter(state['orders']))
            close = {'schemaVersion': 1, 'artifact': 'BTL-TICK-EXECUTION-COMMAND-1',
                     'sessionId': session_id, 'commandId': 'analytics-close:' + uuid.uuid4().hex,
                     'expectedRevision': state['revision'], 'kind': 'CLOSE',
                     'payload': {'orderId': order_id, 'quantity': None}}
            app.apply(session_id, close)
            advance(session_id, 1)  # close at a later committed quote
            journal = self.client.get(self.root + '/sessions/' + session_id + '/journal',
                                      headers=self.headers)
            self.assertEqual(journal.status_code, 200, journal.text)
            self.assertEqual(journal.json()['financialAuthority'], 'COMMITTED_EVENTS_ONLY')
            self.assertEqual([order['id'] for order in journal.json()['orders']], [order_id])
            self.assertEqual(journal.json()['orders'][0]['status'], 'CLOSED')
            analysis = app.workspace(session_id, {'timeframe': '1m'})['analysis']
            self.assertEqual(analysis['status'], 'COMPLETE')
            self.assertEqual(len(analysis['completed']), 1)
            return session_id, Fraction(analysis['completed'][0]['net'])

        # The fixture rises from its low at phase zero and falls from its high
        # at phase 120. Timed close requests produce authored positive, negative,
        # and exactly flat committed outcomes without injecting ledger rows.
        positions = [
            completed_trade('win', pre_advance=120, post_fill_advance=3),
            completed_trade('loss', pre_advance=0, post_fill_advance=0),
            completed_trade('breakeven', pre_advance=120, post_fill_advance=1),
        ]
        observed_nets = [net for _session, net in positions]
        self.assertGreater(observed_nets[0], 0)
        self.assertLess(observed_nets[1], 0)
        self.assertEqual(observed_nets[2], 0)

        analytics = self.client.get(self.root + '/methods/' + record['id'] + '/analytics',
                                    headers=self.headers)
        self.assertEqual(analytics.status_code, 200, analytics.text)
        result = analytics.json()
        self.assertEqual(result['status'], 'COMPLETE')
        self.assertEqual((result['metrics']['tradeCount'], result['metrics']['wins'],
                          result['metrics']['losses'], result['metrics']['breakeven']), (3, 1, 1, 1))
        self.assertEqual(result['completedTradeNet'], text(sum(observed_nets, Fraction())))
        self.assertEqual({item['sessionId'] for item in result['includedSessions']},
                         {session for session, _net in positions})
        self.assertFalse(result['balancesCombined'])
        self.assertNotIn('maxWinStreak', result['metrics'])
        self.assertNotIn('maxLossStreak', result['metrics'])
        app.close()

    def test_method_family_versions_are_immutable_session_pinned_and_cas_archived(self):
        import copy

        original = method()
        created = self.client.post(self.root + '/methods', headers=self.headers, json=original)
        self.assertEqual(created.status_code, 200, created.text)
        family_id = original['id']
        # The registered migration runner must be safe to invoke again: its
        # version/checksum record makes this a no-op, not a duplicate backfill.
        migrate(DSN)
        rerun = self.client.get(self.root + '/method-families/' + family_id, headers=self.headers)
        self.assertEqual(rerun.status_code, 200, rerun.text)
        self.assertEqual(len(rerun.json()['family']['versions']), 1)
        session_id = 'session:method-version-' + uuid.uuid4().hex
        app = ResearchApplication(DSN, TrustedScope(self.workspace, self.actor))
        saved = app.create_session({'id': session_id, 'name': 'Pinned old version',
                                     'methodId': original['id'], 'initialBalance': '10000',
                                     'startPeriod': '2020-01'})
        old_hash = saved['metadata']['methodHash']

        detail_path = self.root + '/method-families/' + family_id
        initial = self.client.get(detail_path, headers=self.headers)
        self.assertEqual(initial.status_code, 200, initial.text)
        family = initial.json()['family']
        self.assertEqual((family['familyId'], family['revision'], family['latestVersion']),
                         (family_id, 1, 1))
        self.assertEqual(family['versions'][0]['methodId'], original['id'])

        successor = copy.deepcopy(original)
        successor['id'] = 'method-version:' + uuid.uuid4().hex
        successor['name'] += ' revised'
        changed = self.client.post(self.root + '/method-families/' + family_id + '/versions',
                                   headers=self.headers,
                                   json={'expectedRevision': 1, 'method': successor})
        self.assertEqual(changed.status_code, 200, changed.text)
        current = changed.json()['family']
        self.assertEqual((current['revision'], current['latestVersion'], current['latestMethodId']),
                         (2, 2, successor['id']))
        self.assertEqual([item['version'] for item in current['versions']], [1, 2])
        self.assertEqual(current['versions'][0]['method']['id'], original['id'])
        self.assertEqual(current['versions'][1]['method']['id'], successor['id'])
        retried = self.client.post(self.root + '/method-families/' + family_id + '/versions',
                                   headers=self.headers,
                                   json={'expectedRevision': 1, 'method': successor})
        self.assertEqual(retried.status_code, 200, retried.text)
        self.assertEqual(retried.json()['family']['latestMethodId'], successor['id'])
        self.assertEqual(len(retried.json()['family']['versions']), 2,
                         'exact successor retry must not create another immutable version')

        concurrent = []
        for suffix in ('left', 'right'):
            candidate = copy.deepcopy(original)
            candidate['id'] = 'method-version:' + uuid.uuid4().hex
            candidate['name'] += ' ' + suffix
            concurrent.append(candidate)
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(lambda candidate: self.client.post(
                self.root + '/method-families/' + family_id + '/versions', headers=self.headers,
                json={'expectedRevision': 2, 'method': candidate}), concurrent))
        self.assertEqual(sorted(response.status_code for response in outcomes), [200, 409])
        current = self.client.get(detail_path, headers=self.headers).json()['family']
        self.assertEqual((current['revision'], current['latestVersion']), (3, 3))
        self.assertEqual(len(current['versions']), 3, 'stale concurrent successor must leave no partial version')

        stale = self.client.post(self.root + '/method-families/' + family_id + '/versions',
                                 headers=self.headers,
                                 json={'expectedRevision': 1, 'method': {
                                     **successor, 'id': 'method-version:' + uuid.uuid4().hex}})
        self.assertEqual(stale.status_code, 409, stale.text)
        pinned = self.client.get(self.root + '/sessions/' + session_id, headers=self.headers)
        self.assertEqual(pinned.status_code, 200, pinned.text)
        self.assertEqual(pinned.json()['metadata']['methodId'], original['id'])
        self.assertEqual(pinned.json()['metadata']['methodHash'], old_hash)

        archived = self.client.post(self.root + '/method-families/' + family_id + '/lifecycle',
                                    headers=self.headers,
                                    json={'expectedRevision': 3, 'archived': True})
        self.assertEqual(archived.status_code, 200, archived.text)
        self.assertTrue(archived.json()['family']['archived'])
        self.assertEqual(archived.json()['family']['revision'], 4)
        from contracts.primitives import ContractError
        with self.assertRaises(ContractError) as refused:
            app.create_session({'id': 'session:archived-method-' + uuid.uuid4().hex,
                                'name': 'Cannot start from archived Method',
                                'methodId': successor['id'], 'initialBalance': '10000',
                                'startPeriod': '2020-01'})
        self.assertEqual(refused.exception.code, 'REFUSED_ARCHIVED')
        hidden = self.client.get(self.root + '/method-families', headers=self.headers)
        self.assertNotIn(family_id, [item['familyId'] for item in hidden.json()['items']])
        included = self.client.get(self.root + '/method-families?includeArchived=true', headers=self.headers)
        self.assertIn(family_id, [item['familyId'] for item in included.json()['items']])
        old_detail = self.client.get(self.root + '/sessions/' + session_id, headers=self.headers)
        self.assertEqual(old_detail.status_code, 200, old_detail.text)
        self.assertEqual(old_detail.json()['metadata']['methodHash'], old_hash)
        stale_unarchive = self.client.post(self.root + '/method-families/' + family_id + '/lifecycle',
                                           headers=self.headers,
                                           json={'expectedRevision': 3, 'archived': False})
        self.assertEqual(stale_unarchive.status_code, 409, stale_unarchive.text)
        unarchive = self.client.post(self.root + '/method-families/' + family_id + '/lifecycle',
                                     headers=self.headers,
                                     json={'expectedRevision': 4, 'archived': False})
        self.assertEqual(unarchive.status_code, 200, unarchive.text)
        self.assertEqual(unarchive.json()['family']['revision'], 5)
        self.assertFalse(unarchive.json()['family']['archived'])

        page = self.client.get(self.root + '/method-families', headers=self.headers)
        self.assertEqual(page.status_code, 200, page.text)
        self.assertIn(family_id, [item['familyId'] for item in page.json()['items']])
        other_actor, other_headers = self.account()
        self.assertNotEqual(other_actor, self.actor)
        self.assertEqual(self.client.get(detail_path, headers=other_headers).status_code, 404)
        self.assertEqual(self.client.post(self.root + '/method-families/' + family_id + '/lifecycle',
                                          headers=other_headers,
                                          json={'expectedRevision': 4, 'archived': True}).status_code, 404)
        app.close()

    def test_method_family_version_history_exceeds_128_and_is_keyset_paginated(self):
        from psycopg.rows import dict_row
        from execution.product_method_lifecycle import add_version
        from infrastructure.database import connect
        original=method()
        created=self.client.post(self.root+'/methods',headers=self.headers,json=original)
        self.assertEqual(created.status_code,200,created.text)
        expected=[original['id']]
        revision=1
        with connect(DSN) as db:
            db.row_factory=dict_row
            for index in range(128):
                successor=dict(original,id='method-version:'+uuid.uuid4().hex,name=f'Version {index+2}')
                add_version(db,self.workspace,original['id'],{'expectedRevision':revision,'method':successor})
                expected.append(successor['id']);revision+=1
        version_path=self.root+'/method-families/'+original['id']+'/versions'
        first=self.client.get(version_path,params={'limit':50},headers=self.headers)
        self.assertEqual(first.status_code,200,first.text)
        first_page=first.json()
        self.assertEqual([row['version'] for row in first_page['versions']],list(range(1,51)))
        self.assertIsNotNone(first_page['nextCursor'])
        second=self.client.get(version_path,params={'limit':50,'cursor':first_page['nextCursor']},headers=self.headers)
        self.assertEqual(second.status_code,200,second.text)
        second_page=second.json()
        self.assertEqual([row['version'] for row in second_page['versions']],list(range(51,101)))
        self.assertIsNotNone(second_page['nextCursor'])
        final=self.client.get(version_path,params={'limit':50,'cursor':second_page['nextCursor']},headers=self.headers)
        self.assertEqual(final.status_code,200,final.text)
        final_page=final.json()
        self.assertEqual([row['methodId'] for row in final_page['versions']],expected[100:])
        self.assertIsNone(final_page['nextCursor'])
        self.assertTrue(final_page['complete'])
        detail=self.client.get(self.root+'/method-families/'+original['id'],headers=self.headers)
        self.assertEqual(detail.status_code,200,detail.text)
        detail_family=detail.json()['family']
        self.assertTrue(detail_family['versionsTruncated'])
        self.assertEqual([row['version'] for row in detail_family['versions']],list(range(2,130)))

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
        view = self.completed_job_result(created)
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
        review = review_request(self.completed_job_result(created))
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
            created_session_result = self.completed_job_result(created_session, root, headers)

            review = review_request(created_session_result)
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
        import copy

        member, header = self.account()
        record = method()
        self.assertEqual(self.client.post(self.root + '/methods', headers=self.headers, json=record).status_code, 200)
        session_id = 'session:' + uuid.uuid4().hex
        session = {'id': session_id, 'name': 'Owner metering scope', 'methodId': record['id'],
                   'initialBalance': '10000', 'startPeriod': '2020-01'}
        self.completed_job_result(self.client.post(self.root + '/sessions', headers=self.headers, json=session))
        target = '/api/v1/workspaces/' + self.workspace + '/members'
        self.assertEqual(self.client.post(target, headers=self.headers, json={'userId': member}).status_code, 204)
        self.assertEqual(self.client.get(self.root + '/catalog', headers=header).status_code, 200)
        member_capability = self.client.get('/api/v1/workspaces/' + self.workspace + '/capabilities', headers=header)
        self.assertEqual(member_capability.status_code, 200, member_capability.text)
        self.assertEqual(member_capability.json()['role'], 'MEMBER')
        self.assertFalse(member_capability.json()['capabilities']['createSession'])
        self.assertEqual(self.client.post(self.root + '/methods', headers=header, json=method()).status_code, 403)
        successor = copy.deepcopy(record)
        successor['id'] = 'method-version:' + uuid.uuid4().hex
        self.assertEqual(self.client.post(self.root + '/method-families/' + record['id'] + '/versions',
                                          headers=header,
                                          json={'expectedRevision': 1, 'method': successor}).status_code, 403)
        self.assertEqual(self.client.post(self.root + '/method-families/' + record['id'] + '/lifecycle',
                                          headers=header,
                                          json={'expectedRevision': 1, 'archived': True}).status_code, 403)
        self.assertEqual(self.client.get(self.root + '/sessions/' + session_id + '/metering/storage',
                                         headers=header).status_code, 403)
        self.assertEqual(self.client.delete(target + '/' + member, headers=self.headers).status_code, 204)
        self.assertEqual(self.client.get(self.root + '/catalog', headers=header).status_code, 404)
        self.assertEqual(self.client.post(self.root + '/method-families/' + record['id'] + '/versions',
                                          headers=header,
                                          json={'expectedRevision': 1, 'method': successor}).status_code, 404)
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

    def test_bounded_research_admission_waits_for_active_reads(self):
        from cloud import research
        import httpx
        self.assertEqual(research.DIRECT_READ_WAIT_SECONDS, 20)
        self.assertEqual(research.DIRECT_MUTATION_WAIT_SECONDS, 20)
        self.assertEqual(research.DIRECT_OPERATION_CONCURRENCY, 3)
        first_three_entered, fourth_entered, release = Event(), Event(), Event()
        calls = 0
        calls_lock = Lock()

        def held(*_args, **_kwargs):
            nonlocal calls
            with calls_lock:
                calls += 1
                current = calls
            if current == 3:
                first_three_entered.set()
            if current == 4:
                fourth_entered.set()
            self.assertTrue(release.wait(8))
            return {'artifact': 'BTL-METHOD-FAMILY-PAGE-1', 'items': [], 'complete': True,
                    'nextCursor': None}

        path = self.root + '/method-families'
        async def exercise():
            transport=httpx.ASGITransport(app=self.app)
            async with httpx.AsyncClient(transport=transport,base_url='https://testserver') as client:
                async def get():
                    return await client.get(path,headers=self.headers)
                with patch('cloud.research.run', held):
                    requests=[asyncio.create_task(get()) for _ in range(3)]
                    try:
                        self.assertTrue(await asyncio.to_thread(first_three_entered.wait,5),
                                        'three bounded research slots should be used')
                        fourth=asyncio.create_task(get())
                        await asyncio.sleep(.1)
                        self.assertFalse(fourth_entered.is_set(),
                                         'fourth read must wait instead of bypassing the cap')
                        release.set()
                        requests.append(fourth)
                        return await asyncio.wait_for(asyncio.gather(*requests),24)
                    finally:
                        release.set()
        responses=asyncio.run(exercise())
        self.assertEqual([response.status_code for response in responses], [200, 200, 200, 200])
        self.assertEqual(calls, 4)

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
