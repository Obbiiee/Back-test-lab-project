"""HTTPS ASGI requests against real PostgreSQL identity; no real email sent."""
import os
import asyncio
import secrets
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient
from cloud.app import create_app
from infrastructure.database import migrate, connect, grant_identity_runtime
from identity.store import TokenStore, UserStore, CredentialChanged
import jwt
import psycopg
from psycopg import sql

DSN = os.getenv("BTL_TEST_DATABASE_URL")
PASSWORD = "Test fixture passphrase 2026 only"


class RecordingDelivery:
    def __init__(self):
        self.messages = []
    async def send(self, email, purpose, token):
        self.messages.append((email, purpose, token))
    def token(self, email, purpose):
        return [token for recipient, kind, token in self.messages if recipient == email and kind == purpose][-1]


def client(app):
    options = {"loop_factory": asyncio.SelectorEventLoop} if os.name == "nt" else {}
    return TestClient(app, base_url="https://testserver", client=(uuid.uuid4().hex, 50000), backend_options=options)


@unittest.skipUnless(DSN, "Identity acceptance requires isolated PostgreSQL; skip is not release PASS")
class IdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        migrate(DSN)

    def setUp(self):
        self.delivery = RecordingDelivery()
        self.secret = secrets.token_urlsafe(48)
        self.app = create_app(DSN, self.secret, self.delivery, rate_limit=100)
        self.client = client(self.app)
        self.email = "u" + uuid.uuid4().hex + "@example.com"

    def register(self, verify=True):
        response = self.client.post("/api/v1/auth/register", json={"email": self.email, "password": PASSWORD})
        self.assertEqual(response.status_code, 201, response.text)
        self.user_id = response.json()["id"]
        if verify:
            verified = self.client.post("/api/v1/auth/verify", json={"token": self.delivery.token(self.email, "verification")})
            self.assertEqual(verified.status_code, 200, verified.text)
        return response

    def login(self, password=PASSWORD):
        return self.client.post("/api/v1/auth/login", data={"username": self.email, "password": password})

    def header(self, token):
        return {"Authorization": "Bearer " + token}

    def test_registration_verification_passwords_and_injection(self):
        registered = self.register(verify=False)
        self.assertFalse(registered.json()["is_superuser"])
        self.assertNotIn("hashed_password", registered.text)
        self.assertEqual(self.login().status_code, 400)
        verification = self.delivery.token(self.email, "verification")
        self.assertEqual(self.client.post("/api/v1/auth/verify", json={"token": "invalid"}).status_code, 400)
        self.assertEqual(self.client.post("/api/v1/auth/verify", json={"token": verification}).status_code, 200)
        self.assertEqual(self.client.post("/api/v1/auth/verify", json={"token": verification}).status_code, 400)
        self.assertEqual(self.login("wrong password").status_code, 400)
        logged = self.login()
        self.assertEqual(logged.status_code, 200, logged.text)
        token = logged.json()["access_token"]
        me = self.client.get("/api/v1/auth/me", headers=self.header(token))
        self.assertEqual(me.status_code, 200); self.assertEqual(me.json()["id"], self.user_id)
        with connect(DSN) as db:
            hashed = db.execute("SELECT hashed_password FROM btl.users WHERE id=%s", (self.user_id,)).fetchone()[0]
            self.assertTrue(hashed.startswith("$argon2")); self.assertNotIn(PASSWORD, hashed)
            self.assertEqual(db.execute("SELECT token_hash FROM btl.auth_sessions WHERE user_id=%s", (self.user_id,)).fetchone()[0], TokenStore.key(token))
        for injection in ({"is_superuser": True}, {"is_verified": True}, {"id": self.user_id}, {"workspaceId": "foreign"}):
            response = self.client.post("/api/v1/auth/register", json={"email": "new"+self.email, "password": PASSWORD, **injection})
            self.assertEqual(response.status_code, 422); self.assertNotIn(PASSWORD, response.text)

    def test_logout_all_expiry_and_disabled_identity(self):
        self.register()
        first, second = self.login().json()["access_token"], self.login().json()["access_token"]
        self.assertEqual(self.client.post("/api/v1/auth/logout", headers=self.header(first)).status_code, 204)
        self.assertEqual(self.client.get("/api/v1/auth/me", headers=self.header(first)).status_code, 401)
        self.assertEqual(self.client.get("/api/v1/auth/me", headers=self.header(second)).status_code, 200)
        self.assertEqual(self.client.post("/api/v1/auth/logout-all", headers=self.header(second)).status_code, 204)
        self.assertEqual(self.client.get("/api/v1/auth/me", headers=self.header(second)).status_code, 401)
        expired = self.login().json()["access_token"]
        with connect(DSN) as db:
            db.execute("UPDATE btl.auth_sessions SET created_at=created_at-interval '2 hours' WHERE token_hash=%s", (TokenStore.key(expired),))
        self.assertEqual(self.client.get("/api/v1/auth/me", headers=self.header(expired)).status_code, 401)
        fresh = self.login().json()["access_token"]
        with connect(DSN) as db: db.execute("UPDATE btl.users SET is_active=false WHERE id=%s", (self.user_id,))
        self.assertEqual(self.client.get("/api/v1/auth/me", headers=self.header(fresh)).status_code, 401)
        self.assertEqual(self.login().status_code, 400)

    def test_recovery_single_use_revokes_sessions_and_no_enumeration(self):
        self.register()
        previous = self.login().json()["access_token"]
        known = self.client.post("/api/v1/auth/forgot-password", json={"email": self.email})
        unknown = self.client.post("/api/v1/auth/forgot-password", json={"email": "absent"+self.email})
        self.assertEqual((known.status_code, known.text), (unknown.status_code, unknown.text))
        self.assertEqual(known.status_code, 202)
        recovery = self.delivery.token(self.email, "recovery")
        new_password = PASSWORD + " changed"
        reset = self.client.post("/api/v1/auth/reset-password", json={"token": recovery, "password": new_password})
        self.assertEqual(reset.status_code, 200, reset.text)
        self.assertEqual(self.client.get("/api/v1/auth/me", headers=self.header(previous)).status_code, 401)
        self.assertEqual(self.login().status_code, 400)
        self.assertEqual(self.login(new_password).status_code, 200)
        self.assertEqual(self.client.post("/api/v1/auth/reset-password", json={"token": recovery, "password": new_password}).status_code, 400)
        invalid = self.client.post("/api/v1/auth/reset-password", json={"token": "invalid", "password": new_password})
        self.assertEqual(invalid.status_code, 400); self.assertNotIn(new_password, invalid.text)

    def test_concurrent_recovery_cas_accepts_one(self):
        self.register()
        self.client.post("/api/v1/auth/forgot-password", json={"email": self.email})
        token = self.delivery.token(self.email, "recovery")
        def reset(index):
            with client(self.app) as caller:
                return caller.post("/api/v1/auth/reset-password", json={"token": token, "password": PASSWORD+str(index)}).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(reset, range(2)))
        self.assertEqual(sorted(statuses), [200, 400])

    def test_expired_wrong_audience_tokens_and_durable_session(self):
        self.register()
        token = self.login().json()["access_token"]
        with client(create_app(DSN, self.secret, self.delivery)) as fresh:
            self.assertEqual(fresh.get("/api/v1/auth/me", headers=self.header(token)).status_code, 200)
        self.client.post("/api/v1/auth/forgot-password", json={"email": self.email})
        recovery = self.delivery.token(self.email, "recovery")
        payload = jwt.decode(recovery, self.secret, algorithms=["HS256"], options={"verify_aud": False})
        expired = jwt.encode({**payload, "exp": 1}, self.secret, algorithm="HS256")
        for invalid in (expired, self.delivery.token(self.email, "verification")):
            response = self.client.post("/api/v1/auth/reset-password", json={"token": invalid, "password": PASSWORD+"new"})
            self.assertEqual(response.status_code, 400); self.assertNotIn(invalid, response.text)

    def test_account_rate_shared_across_client_addresses(self):
        # Production uses fixed PostgreSQL minute buckets. A test crossing a
        # minute must not mistake the intended counter reset for a bypass.
        # Retry a fresh fixture account only when the real DB bucket changed;
        # no mocked rate store/clock or weakened status assertions.
        for _ in range(3):
            email = "u"+uuid.uuid4().hex+"@example.com"
            with connect(DSN) as db:
                before = db.execute("SELECT floor(extract(epoch FROM clock_timestamp())/60)").fetchone()[0]
            statuses = []
            for _index in range(11):
                with client(self.app) as caller:
                    response = caller.post("/api/v1/auth/login", data={"username": email, "password": "bad"})
                    statuses.append(response.status_code)
            with connect(DSN) as db:
                after = db.execute("SELECT floor(extract(epoch FROM clock_timestamp())/60)").fetchone()[0]
            if before == after:
                self.assertEqual(statuses, [400]*10+[429])
                return
        self.fail("No single-minute sample obtained; rate acceptance remains unverified")

    def test_reset_prevents_stale_login_session_publication(self):
        self.register()
        import asyncio
        factory = asyncio.SelectorEventLoop if os.name == "nt" else asyncio.new_event_loop
        old = asyncio.run(UserStore(DSN).get(uuid.UUID(self.user_id)), loop_factory=factory)
        self.client.post("/api/v1/auth/forgot-password", json={"email": self.email})
        token = self.delivery.token(self.email, "recovery")
        self.assertEqual(self.client.post("/api/v1/auth/reset-password", json={"token": token, "password": PASSWORD+" changed"}).status_code, 200)
        with self.assertRaises(CredentialChanged):
            asyncio.run(TokenStore(DSN).create({"token": secrets.token_urlsafe(32), "user_id": old.id, "expected_hash": old.hashed_password}), loop_factory=factory)

    def test_actual_runtime_role_and_safe_database_unavailable(self):
        role, password = "auth_runtime_"+uuid.uuid4().hex, secrets.token_urlsafe(32)
        with connect(DSN) as db:
            db.execute(sql.SQL("CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD {}").format(sql.Identifier(role), sql.Literal(password)))
        grant_identity_runtime(DSN, role)
        info = psycopg.conninfo.conninfo_to_dict(DSN)
        restricted = psycopg.conninfo.make_conninfo(**{**info, "user": role, "password": password})
        delivery = RecordingDelivery()
        with client(create_app(restricted, self.secret, delivery)) as caller:
            registered = caller.post("/api/v1/auth/register", json={"email": self.email, "password": PASSWORD})
            self.assertEqual(registered.status_code, 201, registered.text)
            self.assertEqual(caller.post("/api/v1/auth/verify", json={"token": delivery.token(self.email,"verification")}).status_code, 200)
            logged = caller.post("/api/v1/auth/login", data={"username": self.email, "password": PASSWORD})
            self.assertEqual(logged.status_code, 200)
        with self.assertRaises(psycopg.errors.InsufficientPrivilege):
            with connect(restricted) as db: db.execute("DROP TABLE btl.users")
        unavailable = psycopg.conninfo.make_conninfo(**{**info, "port": "55433"})
        with self.assertLogs("identity.boundary", level="ERROR") as logs, client(create_app(unavailable, self.secret, delivery)) as caller:
            response = caller.get("/api/v1/auth/me")
            self.assertEqual(response.status_code, 503)
            self.assertNotIn(info["password"], response.text + ''.join(logs.output))

    def test_bounded_rate_tls_body_safe_errors_and_fail_closed_config(self):
        app = create_app(DSN, self.secret, self.delivery, rate_limit=3)
        with client(app) as caller:
            for _ in range(3): self.assertEqual(caller.get("/api/v1/auth/me").status_code, 401)
            refused = caller.get("/api/v1/auth/me", headers={"X-Forwarded-For": "different-ip"})
            self.assertEqual(refused.status_code, 429)
            self.assertEqual(refused.headers["cache-control"], "no-store")
            self.assertEqual(len(refused.headers["x-request-id"]), 32)
        with client(self.app) as caller:
            oversized = caller.post("/api/v1/auth/register", content=b"x"*16385)
            self.assertEqual(oversized.status_code, 413)
            plain = caller.get("http://testserver/api/v1/auth/me")
            self.assertEqual(plain.status_code, 426)
            invalid = caller.post("/api/v1/auth/register", json={"email": "invalid", "password": PASSWORD})
            self.assertEqual(invalid.status_code, 422); self.assertNotIn(PASSWORD, invalid.text)
            weak = caller.post("/api/v1/auth/register", json={"email": self.email, "password": "short"})
            self.assertEqual(weak.status_code, 400); self.assertNotIn("short", weak.text)
        with self.assertRaises(ValueError): create_app(DSN, "default", self.delivery)
        with self.assertRaises(ValueError): create_app(DSN, self.secret, None)
        with connect(DSN) as db:
            self.assertGreater(db.execute("SELECT count(*) FROM btl.security_events").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
