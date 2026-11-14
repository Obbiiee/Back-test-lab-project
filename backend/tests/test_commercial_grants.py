"""The commercial tables must work for the restricted runtime role (the product never runs as the owner); this failed the real browser gate before the grants existed."""
import os
import unittest
import uuid

from infrastructure.database import connect, migrate, grant_identity_runtime, grant_workspace_runtime
from execution.postgres import grant_execution_runtime
import psycopg

DSN = os.getenv("BTL_TEST_DATABASE_URL")


@unittest.skipUnless(DSN, "Real isolated PostgreSQL required; skip is not PASS")
class Grants(unittest.TestCase):
    def test_restricted_role_can_use_the_commercial_tables_and_nothing_more(self):
        migrate(DSN)
        role = "rt_" + uuid.uuid4().hex[:10]
        with connect(DSN) as db:
            db.execute(f"CREATE ROLE {role} LOGIN PASSWORD 'x' NOSUPERUSER NOCREATEDB NOCREATEROLE")
        for grant in (grant_identity_runtime, grant_workspace_runtime, grant_execution_runtime):
            grant(DSN, role)
        base = psycopg.conninfo.conninfo_to_dict(DSN); base.update(user=role, password="x")
        with psycopg.connect(**base) as db:
            db.execute("SELECT 1 FROM btl.session_lifecycle LIMIT 1")
            db.execute("SELECT 1 FROM btl.entitlement_claims LIMIT 1")
            db.execute("SELECT actor_id,phase,paid_at,expires_at FROM btl.sandbox_billing_orders LIMIT 1")      # tier lookup for the Free window
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                db.execute("SELECT transaction_id FROM btl.sandbox_billing_orders LIMIT 1")                   # nothing beyond the four columns
            db.rollback()
            db.execute("INSERT INTO btl.audit_events(actor_id,action,outcome) VALUES (%s,'TEST_GRANT','OK')", (uuid.uuid4(),))
            for statement in ("DELETE FROM btl.audit_events", "UPDATE btl.audit_events SET outcome='REFUSED'", "SELECT 1 FROM btl.audit_events LIMIT 1"):
                with self.assertRaises(psycopg.errors.InsufficientPrivilege, msg=statement):
                    db.execute(statement)
                db.rollback()
        with connect(DSN) as db:
            db.execute(f"DROP OWNED BY {role}"); db.execute(f"DROP ROLE {role}")


if __name__ == "__main__":
    unittest.main()
