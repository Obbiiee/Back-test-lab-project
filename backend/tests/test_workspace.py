"""Private HTTP + real DB ownership gates; no mock membership or engine execution."""
import os
import secrets
import tempfile
import threading
import unittest
import uuid
from pathlib import Path
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor

import psycopg
from psycopg import sql
from cloud.app import create_app
from infrastructure.database import (migrate, connect, backup, restore, grant_runtime,
                                     grant_identity_runtime, grant_workspace_runtime)
from infrastructure.postgres import PostgresWorkflow, ProvenanceStore
from application.models import TrustedScope
from contracts.models import Passport
from contracts.primitives import ContractError
from workspace.store import WorkspaceStore
from workspace.policy import KINDS
from tests.test_identity import client, RecordingDelivery, PASSWORD
from tests.application_fakes import sample, H, NOW
from tests.test_application_transport import wire, confirmation

DSN = os.getenv("BTL_TEST_DATABASE_URL")


@unittest.skipUnless(DSN, "Workspace release gate requires real isolated PostgreSQL; skip is not PASS")
class WorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        migrate(DSN)

    def setUp(self):
        self.secret, self.delivery = secrets.token_urlsafe(48), RecordingDelivery()
        self.app = create_app(DSN, self.secret, self.delivery, rate_limit=1000)
        self.c = client(self.app)
        self.users = []
        for _ in range(3):
            email = "w" + uuid.uuid4().hex + "@example.com"
            registered = self.c.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
            self.assertEqual(registered.status_code, 201, registered.text)
            self.assertEqual(self.c.post("/api/v1/auth/verify", json={"token": self.delivery.token(email, "verification")}).status_code, 200)
            token = self.c.post("/api/v1/auth/login", data={"username": email, "password": PASSWORD}).json()["access_token"]
            self.users.append((uuid.UUID(registered.json()["id"]), token))
        self.w = self.request("post", "/api/v1/workspaces", json={"name": "private"}).json()["id"]
        self.base = "/api/v1/workspaces/" + self.w

    def request(self, method, path, actor=0, **kwargs):
        return getattr(self.c, method)(path, headers={"Authorization": "Bearer " + self.users[actor][1]}, **kwargs)

    def resource(self, kind="BACKTEST", actor=0):
        response = self.request("post", self.base+"/resources", actor, json={"kind": kind, "name": "original"})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["id"]

    def member(self):
        self.assertEqual(self.request("post", self.base+"/members", json={"userId": str(self.users[1][0])}).status_code, 204)

    def test_cross_workspace_all_resource_kinds_and_unauthenticated(self):
        self.assertEqual(self.c.get(self.base).status_code, 401)
        for kind in sorted(KINDS):
            rid = self.resource(kind)
            path = self.base+"/resources/"+rid
            self.assertEqual(self.request("get", path, 2).status_code, 404)
            self.assertEqual(self.request("patch", path, 2, json={"name": "stolen", "expectedRevision": 0}).status_code, 404)
            self.assertEqual(self.request("delete", path+"?expectedRevision=0", 2).status_code, 404)
            self.assertEqual(self.request("get", path).json()["name"], "original")
        self.assertEqual(self.request("get", "/api/v1/workspaces", 2).json(), [])

    def test_owner_member_creator_and_revocation(self):
        self.member()
        owned = self.resource()
        self.assertEqual(self.request("get", self.base+"/resources/"+owned, 1).status_code, 200)
        self.assertEqual(self.request("patch", self.base+"/resources/"+owned, 1, json={"name": "no", "expectedRevision": 0}).status_code, 403)
        self.assertEqual(self.request("post", self.base+"/members", 1, json={"userId": str(self.users[2][0])}).status_code, 403)
        created = self.resource("DRAWING", 1)
        path = self.base+"/resources/"+created
        self.assertEqual(self.request("patch", path, 1, json={"name": "mine", "expectedRevision": 0}).status_code, 200)
        self.assertEqual(self.request("patch", path, json={"name": "owner", "expectedRevision": 1}).status_code, 200)
        self.assertEqual(self.request("delete", self.base+"/members/"+str(self.users[0][0])).status_code, 422)
        self.assertEqual(self.request("delete", self.base+"/members/"+str(self.users[1][0])).status_code, 204)
        self.assertEqual(self.request("get", path, 1).status_code, 404)
        self.assertEqual(self.request("post", self.base+"/resources", 1, json={"kind": "DRAWING", "name": "no"}).status_code, 404)

    def test_forged_fields_cas_archive_pagination_and_immutable_identity(self):
        for injected in ({"owner_id": str(self.users[2][0])}, {"role": "OWNER"}, {"workspaceId": self.w}):
            self.assertEqual(self.request("post", "/api/v1/workspaces", json={"name": "bad", **injected}).status_code, 422)
        self.assertEqual(self.request("post", self.base+"/resources", json={"name": "bad", "kind": "DRAWING", "creator_id": str(self.users[2][0])}).status_code, 422)
        rid = self.resource()
        path = self.base+"/resources/"+rid
        self.assertEqual(self.request("patch", path, json={"name": "x", "expectedRevision": True}).status_code, 422)
        self.assertEqual(self.request("patch", path, json={"name": "x", "expectedRevision": 1}).status_code, 409)
        self.assertEqual(self.request("get", self.base+"/resources?limit=51").status_code, 422)
        self.resource("DRAWING")
        first = self.request("get", self.base+"/resources?limit=1").json()
        second = self.request("get", self.base+"/resources?limit=1&after="+first[0]["id"]).json()
        self.assertEqual(len(first), 1); self.assertEqual(len(second), 1)
        self.assertNotEqual(first[0]["id"], second[0]["id"])
        with self.assertRaises(psycopg.IntegrityError):
            with connect(DSN) as db: db.execute("UPDATE btl.resources SET creator_id=%s WHERE id=%s", (self.users[2][0], rid))
        with self.assertRaises(psycopg.IntegrityError):
            with connect(DSN) as db: db.execute("DELETE FROM btl.memberships WHERE workspace_id=%s AND user_id=%s", (self.w, self.users[0][0]))
        self.assertEqual(self.request("delete", path+"?expectedRevision=0").status_code, 204)
        self.assertEqual(self.request("get", path).status_code, 404)
        with connect(DSN) as db:
            self.assertEqual(db.execute("SELECT archived,revision FROM btl.resources WHERE id=%s", (rid,)).fetchone(), (True, 1))

    def provision(self, kind="FREE_STYLE", on=False):
        rid = self.resource()
        context, command = sample(kind, on)
        context = replace(context, workspace_id=self.w, session_id=rid)
        command = replace(command, workspace_id=self.w, session_id=rid)
        scope = TrustedScope(self.w, str(self.users[0][0]))
        PostgresWorkflow(DSN).create_context(scope, context)
        return rid, context, command, scope

    def test_private_intake_durable_retry_concurrency_and_protocol(self):
        rid, context, command, scope = self.provision()
        path = self.base+"/sessions/"+rid
        reviewed = self.request("post", path+"/reviews", json=wire(command))
        self.assertEqual(reviewed.status_code, 200, reviewed.text)
        assertions = {**confirmation(reviewed.json()), "sessionId": rid}
        def confirm(_):
            with client(self.app) as caller:
                response = caller.post(path+"/confirmations", headers={"Authorization": "Bearer "+self.users[0][1]}, json=assertions)
                self.assertEqual(response.status_code, 200, response.text)
                return response.json()
        with ThreadPoolExecutor(max_workers=4) as pool: outcomes = list(pool.map(confirm, range(8)))
        self.assertEqual(sum(not x["duplicate"] for x in outcomes), 1)
        self.assertTrue(all(x["durable"] and not x["executionPerformed"] for x in outcomes))
        self.assertTrue(all(x["receipt"] == outcomes[0]["receipt"] and x["event"] == outcomes[0]["event"] for x in outcomes))
        PostgresWorkflow(DSN).advance_context(scope, replace(context, quote_revision=8), 4, 7)
        self.assertTrue(confirm(0)["duplicate"])
        self.assertEqual(self.request("post", path+"/reviews", json=wire(replace(command, request_id="stale"))).status_code, 409)
        self.member()
        self.assertEqual(self.request("post", path+"/confirmations", 1, json=assertions).status_code, 404)
        self.assertEqual(self.request("post", path+"/confirmations", 2, json=assertions).status_code, 404)
        for on in (False, True):
            pid, _, protocol, _ = self.provision("PROTOCOL", on)
            payload = {**wire(protocol), "observations": [{"conditionId": "setup", "outcome": "FAIL"}]}
            response = self.request("post", self.base+"/sessions/"+pid+"/reviews", json=payload)
            self.assertEqual(response.status_code, 422 if on else 200, response.text)

    def test_legacy_unbound_context_cannot_be_adopted(self):
        context, command = sample()
        rid = str(uuid.uuid4())
        context, command = replace(context, workspace_id=self.w, session_id=rid), replace(command, workspace_id=self.w, session_id=rid)
        PostgresWorkflow(DSN).create_context(TrustedScope(self.w, "old-actor"), context)
        response = self.request("post", self.base+"/sessions/"+rid+"/reviews", json=wire(command))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.request("post", self.base+"/sessions/"+rid+"/reviews", json={**wire(command), "actorRef": "old-actor"}).status_code, 400)

    def test_passport_scoped_exact_hash_and_missing(self):
        rid = self.resource("EXPERIMENT")
        passport = Passport(rid, self.w, "dataset", "v1", H, H, H, H, "engine1", "calc1", "XAUUSD", "feed", NOW, NOW, 4, "trial")
        ProvenanceStore(DSN).append_passport(TrustedScope(self.w, str(self.users[0][0])), passport)
        path = self.base+"/resources/"+rid+"/passport"
        self.member()
        self.assertEqual(self.request("get", path).status_code, 200)
        self.assertEqual(self.request("get", path).content, self.request("get", path, 1).content)
        self.assertEqual(self.request("get", path, 2).status_code, 404)
        self.assertEqual(self.request("get", path+"?revision=1").status_code, 404)

    def test_revocation_serializes_with_inflight_membership_transaction(self):
        self.member()
        store = WorkspaceStore(DSN)
        entered, release, removing = threading.Event(), threading.Event(), threading.Event()
        def operation(unit):
            entered.set()
            self.assertTrue(release.wait(5))
            return unit.role
        def revoke():
            removing.set()
            store.remove_member(self.users[0][0], uuid.UUID(self.w), self.users[1][0])
        with ThreadPoolExecutor(max_workers=2) as pool:
            running = pool.submit(store.run, self.users[1][0], uuid.UUID(self.w), operation)
            self.assertTrue(entered.wait(5))
            removed = pool.submit(revoke)
            self.assertTrue(removing.wait(5))
            self.assertFalse(removed.done())
            release.set()
            self.assertEqual(running.result(5), "MEMBER")
            removed.result(5)
        with self.assertRaisesRegex(ContractError, "RESOURCE_UNAVAILABLE"):
            store.get(self.users[1][0], uuid.UUID(self.w))

    def test_real_runtime_permissions_and_native_restore_preserve_private_access(self):
        rid = self.resource("DRAWING")
        session_id, _, command, _ = self.provision()
        self.member()
        role, password = "workspace_runtime_"+uuid.uuid4().hex, secrets.token_urlsafe(32)
        with connect(DSN) as db:
            db.execute(sql.SQL("CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD {}").format(sql.Identifier(role), sql.Literal(password)))
        for grant in (grant_runtime, grant_identity_runtime, grant_workspace_runtime): grant(DSN, role)
        info = psycopg.conninfo.conninfo_to_dict(DSN)
        restricted = psycopg.conninfo.make_conninfo(**{**info, "user": role, "password": password})
        with client(create_app(restricted, self.secret, self.delivery, rate_limit=1000)) as caller:
            response = caller.get(self.base+"/resources/"+rid, headers={"Authorization": "Bearer "+self.users[1][1]})
            self.assertEqual(response.status_code, 200, response.text)
            created = caller.post("/api/v1/workspaces", headers={"Authorization": "Bearer "+self.users[1][1]}, json={"name": "restricted"})
            self.assertEqual(created.status_code, 201, created.text)
            intake_path = self.base+"/sessions/"+session_id
            header = {"Authorization": "Bearer "+self.users[0][1]}
            reviewed = caller.post(intake_path+"/reviews", headers=header, json=wire(command))
            self.assertEqual(reviewed.status_code, 200, reviewed.text)
            confirmed = caller.post(intake_path+"/confirmations", headers=header,
                                    json={**confirmation(reviewed.json()), "sessionId": session_id})
            self.assertEqual(confirmed.status_code, 200, confirmed.text)
            self.assertTrue(confirmed.json()["durable"])
            self.assertFalse(confirmed.json()["executionPerformed"])
        for statement in ("DROP TABLE btl.resources", "DELETE FROM btl.resources", "UPDATE btl.workspaces SET name='illegal'"):
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                with connect(restricted) as db: db.execute(statement)
        with self.assertRaises(psycopg.IntegrityError):
            with connect(restricted) as db:
                db.execute("UPDATE btl.memberships SET user_id=%s WHERE workspace_id=%s AND user_id=%s", (self.users[2][0], self.w, self.users[1][0]))
        restored_name = "workspace_restore_"+uuid.uuid4().hex
        with psycopg.connect(DSN, autocommit=True) as db:
            db.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(sql.Identifier(restored_name)))
        restored_dsn = psycopg.conninfo.make_conninfo(**{**info, "dbname": restored_name})
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)/"private.dump"
            digest = backup(DSN, target, os.environ["BTL_PG_BIN"])
            restore(restored_dsn, target, digest, os.environ["BTL_PG_BIN"])
        with connect(DSN) as original, connect(restored_dsn) as copy:
            for table in ("users", "auth_sessions", "workspaces", "memberships", "resources", "security_events"):
                query = sql.SQL("SELECT to_jsonb(t)::text FROM btl.{} t ORDER BY to_jsonb(t)::text").format(sql.Identifier(table))
                self.assertEqual(original.execute(query).fetchall(), copy.execute(query).fetchall())
        with client(create_app(restored_dsn, self.secret, self.delivery, rate_limit=1000)) as restored:
            response = restored.get(self.base+"/resources/"+rid, headers={"Authorization": "Bearer "+self.users[1][1]})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["id"], rid)
            self.assertEqual(restored.get(self.base, headers={"Authorization": "Bearer "+self.users[2][1]}).status_code, 404)


if __name__ == "__main__": unittest.main()
