"""Integrated sixteen-instrument journey using authored provider/data only.

Requires a fresh exclusive PostgreSQL cluster. No SMTP, actual Google consent,
historical coverage, browser rendering or sales acceptance is implied.
"""
import os
import secrets
import unittest
import uuid

import psycopg
from psycopg import sql

from cloud.app import create_app
from contracts.canonical import content_hash
from deploy.vps.ops import migrate_and_grant
from execution.research_fixture_v2 import START_NS, STEP_NS
from market_data.instruments import INSTRUMENTS
from tests import test_google_identity as google_fixture
from tests.test_identity import client, RecordingDelivery, PASSWORD
from tests.test_research_sessions import method
from tests.test_kernel_v2 import opening
from tests.test_execution_v2_postgres import command


class FunctionalJourneyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dsn = os.environ.get('BTL_TEST_DATABASE_URL')
        if not cls.dsn:
            raise RuntimeError('FRESH_EXCLUSIVE_POSTGRESQL_REQUIRED')
        google_fixture.GoogleIdentityTests.setUpClass()
        password = secrets.token_urlsafe(32)
        with psycopg.connect(cls.dsn, autocommit=True) as db:
            db.execute('CREATE ROLE btl_owner NOLOGIN')
            db.execute(sql.SQL('CREATE ROLE btl_app LOGIN NOSUPERUSER NOCREATEDB '
                               'NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD {}')
                       .format(sql.Literal(password)))
        migrate_and_grant(cls.dsn)
        info = psycopg.conninfo.conninfo_to_dict(cls.dsn)
        cls.runtime = psycopg.conninfo.make_conninfo(**{**info, 'user': 'btl_app', 'password': password})

    def test_sixteen_google_accounts_trade_save_stats_and_relogin_with_tenant_isolation(self):
        previous = None
        for symbol in INSTRUMENTS:
            with self.subTest(symbol=symbol):
                qa = google_fixture.GoogleIdentityTests(methodName='runTest')
                qa.factory = lambda dsn: create_app(
                    self.runtime, qa.auth_secret, qa.delivery, rate_limit=1000,
                    sandbox_reset_timezone='UTC', google_client_id=google_fixture.CLIENT,
                    google_client_secret=google_fixture.SECRET,
                    google_redirect_uri=google_fixture.REDIRECT)
                qa.setUp()
                headers = qa.login()
                http = qa.client
                me = http.get('/api/v1/auth/me', headers=headers).json()
                self.assertTrue(me['is_verified'])
                workspace = http.post('/api/v1/workspaces', headers=headers,
                                      json={'name': symbol + ' authored QA'})
                self.assertEqual(workspace.status_code, 201, workspace.text)
                wid = workspace.json()['id']
                root = '/api/v1/workspaces/' + wid + '/research-v2'
                def get(path):
                    response = http.get(root + path, headers=headers)
                    self.assertEqual(response.status_code, 200, response.text)
                    return response.json()
                def post(path, body):
                    response = http.post(root + path, headers=headers, json=body)
                    self.assertEqual(response.status_code, 200, response.text)
                    return response.json()
                catalog = get('/catalog')
                self.assertIn('SYNTHETIC', str(catalog))
                self.assertEqual([item['symbol'] for item in catalog['instruments']], list(INSTRUMENTS))
                self.assertTrue(all(item['model'] == 'AUTHORED_SYNTHETIC_ONLY'
                                    for item in catalog['instruments']))
                m = method()
                post('/methods', m)
                sid = 'session:journey:' + symbol
                path = '/sessions/' + sid
                post('/sessions', dict(id=sid, name=symbol, methodId=m['id'], symbol=symbol,
                                      startPeriod='2020-01', initialBalance='10000'))
                post(path + '/activate', {})
                revision = 0
                def call(kind, payload):
                    nonlocal revision
                    raw = command(sid, 'journey:' + str(revision), revision, kind, payload)
                    receipt = post(path + '/commands', raw)
                    self.assertEqual(post(path + '/commands', raw), receipt)
                    revision = receipt['state']['revision']
                call('ADVANCE', {'targetNs': str(START_NS)})
                review = post(path + '/review', dict(id='order:journey', expectedRevision=revision,
                                                   payload=opening(entry='999')))
                confirm = dict(reviewId=review['id'], reviewHash=content_hash(review))
                receipt = post(path + '/confirm', confirm)
                revision = receipt['state']['revision']
                call('ADVANCE', {'targetNs': str(START_NS + STEP_NS)})
                call('CLOSE', {'orderId': 'order:journey', 'quantity': None})
                call('ADVANCE', {'targetNs': str(START_NS + 2 * STEP_NS)})
                stats = get(path + '/statistics')
                self.assertEqual(stats['metrics']['tradeCount'], 1)
                self.assertIsInstance(stats['account']['balance'], str)
                if symbol == 'EURUSD':
                    self.assertEqual(stats['account']['balance'], '10000.03')
                post(path + '/journal', dict(orderId='order:journey', expectedNoteRevision=0,
                                            text='Authored integrated acceptance', tags=['qa']))
                notes = get(path + '/journal')
                self.assertEqual(len(notes['notes']), 1)
                post(path + '/trash', {})
                post(path + '/restore', {})
                self.assertEqual(post(path + '/confirm', confirm), receipt)
                if previous:
                    self.assertEqual(http.get(previous, headers=headers).status_code, 404)
                self.assertEqual(http.get(root + path + '/statistics').status_code, 401)
                self.assertEqual(http.post('/api/v1/auth/logout', headers=headers).status_code, 204)
                self.assertEqual(http.get(root + path, headers=headers).status_code, 401)
                http.close()
                # New app + cookies: same authored Google subject must recover the account and data.
                qa.app = qa.factory(self.runtime)
                qa.client = client(qa.app)
                qa.app.state.google_verifier.keys.fetch_data = lambda: {'keys': [qa.jwk]}
                import httpx
                qa.app.state.google_client.get_httpx_client = lambda: httpx.AsyncClient(
                    transport=httpx.MockTransport(qa.token_endpoint), follow_redirects=False, timeout=5)
                headers = qa.login()
                http = qa.client
                self.assertEqual(http.get('/api/v1/auth/me', headers=headers).json()['id'], me['id'])
                self.assertEqual(get(path + '/statistics'), stats)
                self.assertEqual(get(path + '/journal'), notes)
                self.assertEqual(get(path)['state']['revision'], revision)
                previous = root + path + '/statistics'
                qa.client.close()

    def test_email_verification_required_before_workspace_and_recovery_revokes_old_session(self):
        delivery = RecordingDelivery()
        http = client(create_app(self.runtime, secrets.token_urlsafe(48), delivery,
                                 rate_limit=1000, sandbox_reset_timezone='UTC'))
        email = uuid.uuid4().hex + '@example.com'
        response = http.post('/api/v1/auth/register', json={'email': email, 'password': PASSWORD})
        self.assertEqual(response.status_code, 201, response.text)
        def login(password=PASSWORD):
            return http.post('/api/v1/auth/login', data={'username': email, 'password': password})
        self.assertEqual(login().status_code, 400)
        verified = http.post('/api/v1/auth/verify', json={'token': delivery.token(email, 'verification')})
        self.assertEqual(verified.status_code, 200, verified.text)
        logged = login()
        self.assertEqual(logged.status_code, 200, logged.text)
        headers = {'Authorization': 'Bearer ' + logged.json()['access_token']}
        self.assertEqual(http.post('/api/v1/workspaces', headers=headers, json={'name': 'Verified email QA'}).status_code, 201)
        response = http.post('/api/v1/auth/forgot-password', json={'email': email})
        self.assertEqual(response.status_code, 202, response.text)
        replacement = 'QA-only-Replacement-Password-942!'
        response = http.post('/api/v1/auth/reset-password', json={
            'token': delivery.token(email, 'recovery'), 'password': replacement})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(http.get('/api/v1/auth/me', headers=headers).status_code, 401)
        self.assertEqual(login().status_code, 400)
        self.assertEqual(login(replacement).status_code, 200)
        http.close()
