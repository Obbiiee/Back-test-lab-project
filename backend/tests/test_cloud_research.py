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
from tests.test_identity import RecordingDelivery, client, PASSWORD
from tests.test_research_sessions import method, review_request

DSN = os.getenv('BTL_TEST_DATABASE_URL')


@unittest.skipUnless(DSN, 'Real isolated PostgreSQL required; skip is not PASS')
class CloudResearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        migrate(DSN)

    def setUp(self):
        self.delivery = RecordingDelivery()
        self.app = create_app(DSN, secrets.token_urlsafe(48), self.delivery, rate_limit=200)
        self.client = client(self.app)
        self.actor, self.headers = self.account()
        self.workspace = self.client.post('/api/v1/workspaces', headers=self.headers,
                                          json={'name': 'Isolated research QA'}).json()['id']
        self.root = '/api/v1/workspaces/' + self.workspace + '/research'

    def account(self):
        email = uuid.uuid4().hex + '@example.com'
        registered = self.client.post('/api/v1/auth/register', json={'email': email, 'password': PASSWORD})
        self.assertEqual(registered.status_code, 201, registered.text)
        verified = self.client.post('/api/v1/auth/verify', json={'token': self.delivery.token(email, 'verification')})
        self.assertEqual(verified.status_code, 200, verified.text)
        login = self.client.post('/api/v1/auth/login', data={'username': email, 'password': PASSWORD})
        self.assertEqual(login.status_code, 200, login.text)
        return registered.json()['id'], {'Authorization': 'Bearer ' + login.json()['access_token']}

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
        before = self.client.get(path, headers=self.headers).content
        _, other = self.account()
        for verb, target, body in [('GET', path, None), ('POST', path + '/confirm', pin),
                                   ('GET', self.root + '/catalog', None)]:
            refused = self.client.request(verb, target, headers=other, json=body)
            self.assertEqual(refused.status_code, 404, refused.text)
        self.assertEqual(self.client.get(path, headers=self.headers).content, before)
        self.assertEqual(self.client.get(path).status_code, 401)
        self.assertIn('SYNTHETIC', view['label'])
        self.assertNotIn('sidecar', created.text)

    def test_member_read_only_then_revocation_and_logout(self):
        member, header = self.account()
        target = '/api/v1/workspaces/' + self.workspace + '/members'
        self.assertEqual(self.client.post(target, headers=self.headers, json={'userId': member}).status_code, 204)
        self.assertEqual(self.client.get(self.root + '/catalog', headers=header).status_code, 200)
        self.assertEqual(self.client.post(self.root + '/methods', headers=header, json=method()).status_code, 403)
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
