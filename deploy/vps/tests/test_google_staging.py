"""Fresh private PostgreSQL + authored Google provider; never live credentials."""
import os
import secrets
import unittest

import psycopg
from psycopg import sql

from deploy.vps.google_staging import create_google_staging_app, grant_workspace_metadata
from infrastructure.database import connect, grant_identity_runtime
from identity.google_store import grant_google_runtime
from tests import test_google_identity as google_fixture
from tests.test_google_identity import CLIENT, SECRET, REDIRECT


class GoogleWorkspaceStagingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dsn = os.environ.get('BTL_TEST_DATABASE_URL')
        if not cls.dsn:
            raise RuntimeError('FRESH_ISOLATED_POSTGRESQL_REQUIRED')
        google_fixture.GoogleIdentityTests.setUpClass()
        password = secrets.token_urlsafe(32)
        with psycopg.connect(cls.dsn, autocommit=True) as db:
            db.execute('CREATE ROLE btl_owner NOLOGIN')
            db.execute(sql.SQL('CREATE ROLE btl_app LOGIN NOSUPERUSER NOCREATEDB '
                               'NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD {}')
                       .format(sql.Literal(password)))
        grant_identity_runtime(cls.dsn, 'btl_app')
        grant_google_runtime(cls.dsn, 'btl_app')
        grant_workspace_metadata(cls.dsn)
        info = psycopg.conninfo.conninfo_to_dict(cls.dsn)
        cls.limited = psycopg.conninfo.make_conninfo(**{**info, 'user': 'btl_app', 'password': password})

    def actor(self, enabled=True, auth_secret=None):
        # Reuse the canonical RSA/state/PKCE fixture without inheriting its suite.
        qa = google_fixture.GoogleIdentityTests(methodName='runTest')
        def factory(dsn):
            return create_google_staging_app(
                self.limited, auth_secret or qa.auth_secret,
                workspace_metadata=enabled, rate_limit=1000,
                google_client_id=CLIENT, google_client_secret=SECRET,
                google_redirect_uri=REDIRECT)
        qa.factory = factory
        qa.setUp()
        return qa

    def test_google_identity_workspace_persistence_isolation_and_logout(self):
        owner, stranger = self.actor(), self.actor()
        headers, other = owner.login(), stranger.login()
        me = owner.client.get('/api/v1/auth/me', headers=headers).json()
        response = owner.client.post('/api/v1/workspaces', headers=headers, json={'name': 'Private saved workspace'})
        self.assertEqual(response.status_code, 201, response.text)
        workspace = response.json()
        path = '/api/v1/workspaces/' + workspace['id']
        self.assertEqual(owner.client.get(path, headers=headers).status_code, 200)
        self.assertEqual(stranger.client.get(path, headers={**other, 'X-Role': 'OWNER', 'X-User-Email': owner.email}).status_code, 404)
        self.assertEqual(stranger.client.get('/api/v1/workspaces', headers=other).json(), [])
        self.assertEqual(owner.client.post('/api/v1/auth/logout', headers=headers).status_code, 204)
        self.assertEqual(owner.client.get(path, headers=headers).status_code, 401)
        # A fresh app and cookie jar, same Google subject and signing secret.
        reopened = self.actor(auth_secret=owner.auth_secret)
        reopened.subject, reopened.email = owner.subject, owner.email
        renewed = reopened.login()
        self.assertEqual(reopened.client.get('/api/v1/auth/me', headers=renewed).json()['id'], me['id'])
        self.assertEqual(reopened.client.get(path, headers=renewed).json(), {**workspace, 'role': 'OWNER'})
        self.assertEqual(len(reopened.client.get('/api/v1/workspaces', headers=renewed).json()), 1)
        self.assertEqual(reopened.client.get(path, headers=headers).status_code, 401)

    def test_routes_default_closed_and_no_privilege_injection(self):
        qa = self.actor()
        headers = qa.login()
        self.assertEqual(qa.client.get('/api/v1/workspaces').status_code, 401)
        for fields in ({'role': 'OWNER'}, {'owner_id': 'forged'}, {'workspaceId': 'forged'}):
            self.assertEqual(qa.client.post('/api/v1/workspaces', headers=headers, json={'name': 'bad', **fields}).status_code, 422)
        for path in ('/api/v1/auth/register', '/api/v1/auth/login', '/api/v1/admin', '/api/v1/billing',
                     '/api/v1/workspaces/00000000-0000-0000-0000-000000000001/members',
                     '/api/v1/workspaces/00000000-0000-0000-0000-000000000001/research-v2/catalog'):
            self.assertEqual(qa.client.get(path, headers=headers).status_code, 404, path)
            self.assertEqual(qa.client.post(path, headers=headers, json={}).status_code, 404, path)
        closed = self.actor(enabled=False)
        self.assertEqual(closed.client.get('/api/v1/workspaces', headers=closed.login()).status_code, 404)
        self.assertEqual(closed.client.get('/api/v1/auth/providers').json(),
                         {'schemaVersion': 1, 'password': False, 'googleConfigured': True, 'billingConfigured': False})
        with self.assertRaises(ValueError):
            create_google_staging_app('unused', 'x'*64, workspace_metadata='true')

    def test_metadata_grants_are_narrow_idempotent_and_operator_only(self):
        grant_workspace_metadata(self.dsn)
        with connect(self.limited) as db:
            for table, privilege in (('memberships', 'DELETE'), ('resources', 'SELECT'),
                                     ('research_jobs', 'INSERT'), ('workspaces', 'DELETE')):
                self.assertFalse(db.execute('SELECT has_table_privilege(current_user,%s,%s)', ('btl.'+table, privilege)).fetchone()[0])
        with self.assertRaises(ValueError):
            grant_workspace_metadata(self.limited)
        with self.assertRaises(ValueError):
            grant_workspace_metadata(self.dsn, 'another_role')
        with connect(self.dsn) as db:
            db.execute('GRANT btl_owner TO btl_app')
        try:
            with self.assertRaises(ValueError):
                grant_workspace_metadata(self.dsn)
        finally:
            with connect(self.dsn) as db:
                db.execute('REVOKE btl_owner FROM btl_app')
