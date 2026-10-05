"""Scoped metadata transactions; actor comes only from verified server identity."""
import uuid
from psycopg.rows import dict_row
from contracts.primitives import require
from contracts.models import Passport
from infrastructure.database import connect
from infrastructure.codec import unpack, pack
from .policy import active_verified, owner, writable, expected, name, KINDS


def lock_user(db, actor_id):
    row = db.execute("SELECT is_active,is_verified FROM btl.users WHERE id=%s FOR SHARE", (actor_id,)).fetchone()
    active_verified(row)


def audit(db, actor_id, code, workspace_id=None, resource_id=None):
    db.execute("INSERT INTO btl.security_events(user_id,code,workspace_id,resource_id) VALUES (%s,%s,%s,%s)",
               (actor_id, code, workspace_id, resource_id))


class WorkspaceUnit:
    def __init__(self, db, actor_id, workspace_id):
        self.db, self.actor_id, self.workspace_id = db, actor_id, workspace_id
        lock_user(db, actor_id)
        self.workspace = db.execute("SELECT * FROM btl.workspaces WHERE id=%s FOR SHARE", (workspace_id,)).fetchone()
        member = db.execute("SELECT role FROM btl.memberships WHERE workspace_id=%s AND user_id=%s FOR SHARE",
                            (workspace_id, actor_id)).fetchone()
        require(self.workspace is not None and member is not None, "workspace", "RESOURCE_UNAVAILABLE")
        self.role = member["role"]

    def resource(self, resource_id, write=False):
        lock = "FOR UPDATE" if write else "FOR SHARE"
        row = self.db.execute("SELECT * FROM btl.resources WHERE workspace_id=%s AND id=%s AND NOT archived " + lock,
                              (self.workspace_id, resource_id)).fetchone()
        require(row is not None, "resource", "RESOURCE_UNAVAILABLE")
        if write:
            writable(row, self.actor_id, self.role)
        return row


class WorkspaceStore:
    def __init__(self, dsn):
        self.dsn = dsn

    def run(self, actor_id, workspace_id, operation):
        with connect(self.dsn) as db:
            db.row_factory = dict_row
            return operation(WorkspaceUnit(db, actor_id, workspace_id))

    def create(self, actor_id, display_name):
        display_name = name(display_name)
        workspace_id = uuid.uuid4()
        with connect(self.dsn) as db:
            db.row_factory = dict_row
            lock_user(db, actor_id)
            row = db.execute("INSERT INTO btl.workspaces VALUES (%s,%s,%s) RETURNING *", (workspace_id, actor_id, display_name)).fetchone()
            db.execute("INSERT INTO btl.memberships VALUES (%s,%s,'OWNER')", (workspace_id, actor_id))
            audit(db, actor_id, "WORKSPACE_CREATED", workspace_id)
            return row

    def list(self, actor_id, limit=50, after=None):
        require(type(limit) is int and 1 <= limit <= 50, "limit")
        with connect(self.dsn) as db:
            db.row_factory = dict_row
            lock_user(db, actor_id)
            return db.execute("SELECT w.*,m.role FROM btl.workspaces w JOIN btl.memberships m ON w.id=m.workspace_id WHERE m.user_id=%s AND (%s::uuid IS NULL OR w.id>%s) ORDER BY w.id LIMIT %s",
                (actor_id, after, after, limit)).fetchall()

    def get(self, actor_id, workspace_id):
        return self.run(actor_id, workspace_id, lambda unit: {**unit.workspace, "role": unit.role})

    def add_member(self, actor_id, workspace_id, target_id):
        def operation(unit):
            owner(unit.role)
            require(target_id != unit.workspace["owner_id"], "ownerMembership")
            target = unit.db.execute("SELECT is_active,is_verified FROM btl.users WHERE id=%s FOR SHARE", (target_id,)).fetchone()
            require(target is not None and target["is_active"] and target["is_verified"], "member", "RESOURCE_UNAVAILABLE")
            unit.db.execute("INSERT INTO btl.memberships VALUES (%s,%s,'MEMBER') ON CONFLICT DO NOTHING", (workspace_id, target_id))
            audit(unit.db, actor_id, "MEMBERSHIP_GRANTED", workspace_id)
        self.run(actor_id, workspace_id, operation)

    def remove_member(self, actor_id, workspace_id, target_id):
        def operation(unit):
            owner(unit.role)
            require(target_id != unit.workspace["owner_id"], "ownerMembership")
            unit.db.execute("DELETE FROM btl.memberships WHERE workspace_id=%s AND user_id=%s", (workspace_id, target_id))
            audit(unit.db, actor_id, "MEMBERSHIP_REVOKED", workspace_id)
        self.run(actor_id, workspace_id, operation)

    def create_resource(self, actor_id, workspace_id, kind, display_name):
        require(type(kind) is str and kind in KINDS, "kind")
        display_name = name(display_name)
        def operation(unit):
            row = unit.db.execute("INSERT INTO btl.resources(id,workspace_id,creator_id,kind,name) VALUES (%s,%s,%s,%s,%s) RETURNING *",
                (uuid.uuid4(), workspace_id, actor_id, kind, display_name)).fetchone()
            audit(unit.db, actor_id, "RESOURCE_REGISTERED", workspace_id, row["id"])
            return row
        return self.run(actor_id, workspace_id, operation)

    def resources(self, actor_id, workspace_id, limit=50, after=None):
        require(type(limit) is int and 1 <= limit <= 50, "limit")
        return self.run(actor_id, workspace_id, lambda unit: unit.db.execute("SELECT * FROM btl.resources WHERE workspace_id=%s AND NOT archived AND (%s::uuid IS NULL OR id>%s) ORDER BY id LIMIT %s",
            (workspace_id, after, after, limit)).fetchall())

    def get_resource(self, actor_id, workspace_id, resource_id):
        return self.run(actor_id, workspace_id, lambda unit: unit.resource(resource_id))

    def amend_resource(self, actor_id, workspace_id, resource_id, expected_revision, display_name=None, archive=False):
        if not archive:
            display_name = name(display_name)
        def operation(unit):
            row = unit.resource(resource_id, write=True)
            expected(row, expected_revision)
            result = unit.db.execute("UPDATE btl.resources SET name=%s,archived=%s,revision=revision+1 WHERE workspace_id=%s AND id=%s RETURNING *",
                (row["name"] if archive else display_name, archive, workspace_id, resource_id)).fetchone()
            audit(unit.db, actor_id, "RESOURCE_ARCHIVED" if archive else "RESOURCE_RENAMED", workspace_id, resource_id)
            return result
        return self.run(actor_id, workspace_id, operation)

    def passport(self, actor_id, workspace_id, resource_id, revision):
        from contracts.primitives import revision as check_revision
        check_revision(revision)
        def operation(unit):
            resource = unit.resource(resource_id)
            require(resource["kind"] == "EXPERIMENT", "passport", "RESOURCE_UNAVAILABLE")
            row = unit.db.execute("SELECT payload,content_hash FROM btl.passports WHERE workspace_id=%s AND experiment_id=%s AND revision=%s",
                (str(workspace_id), str(resource_id), revision)).fetchone()
            require(row is not None, "passport", "RESOURCE_UNAVAILABLE")
            result = unpack(row["payload"], row["content_hash"], Passport)
            require(result.workspace_id == str(workspace_id) and result.experiment_id == str(resource_id), "passport", "CORRUPT_RECORD")
            return pack(result)
        return self.run(actor_id, workspace_id, operation)
