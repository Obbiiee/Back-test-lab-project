"""Stable Method families around the existing immutable financial Method rows."""
from contracts.primitives import require, identifier, revision
from .postgres import unpack, pack
from .research import method_policy, label

MAX_METHODS = 128
MAX_PAGE = 50


def register_first_version(db, workspace_id, method_id):
    db.execute("INSERT INTO btl.product_method_families "
               "(workspace_id,family_id,revision,archived,latest_version,latest_method_id) "
               "VALUES (%s,%s,1,false,1,%s)", (workspace_id, method_id, method_id))
    db.execute("INSERT INTO btl.product_method_versions VALUES (%s,%s,1,%s)",
               (workspace_id, method_id, method_id))


def require_active_method(db, workspace_id, method_id):
    row = db.execute(
        "SELECT f.archived FROM btl.product_method_versions v "
        "JOIN btl.product_method_families f "
        "ON f.workspace_id=v.workspace_id AND f.family_id=v.family_id "
        "WHERE v.workspace_id=%s AND v.method_id=%s",
        (workspace_id, method_id),
    ).fetchone()
    require(row is not None, "methodFamily", "CORRUPT_RECORD")
    archived = row["archived"] if hasattr(row, "keys") else row[0]
    require(not archived, "methodFamily", "REFUSED_ARCHIVED")


def _method(db, workspace_id, method_id):
    row = db.execute(
        "SELECT payload,content_hash FROM btl.tick_methods WHERE workspace_id=%s AND method_id=%s",
        (workspace_id, method_id),
    ).fetchone()
    require(row is not None, "method", "RESOURCE_UNAVAILABLE")
    value = unpack(row["payload"], row["content_hash"])
    policy = method_policy(value)
    require(value["id"] == method_id, "method", "CORRUPT_RECORD")
    return value, policy


def _family(db, workspace_id, family_id, *, lock=False):
    identifier(family_id, "methodFamilyId")
    row = db.execute(
        "SELECT family_id,revision,archived,latest_version,latest_method_id "
        "FROM btl.product_method_families WHERE workspace_id=%s AND family_id=%s" +
        (" FOR UPDATE" if lock else ""), (workspace_id, family_id),
    ).fetchone()
    require(row is not None, "methodFamily", "RESOURCE_UNAVAILABLE")
    current, policy = _method(db, workspace_id, row["latest_method_id"])
    return row, current, policy


def _view(db, workspace_id, family_id):
    family, current, _ = _family(db, workspace_id, family_id)
    rows = db.execute(
        "SELECT v.version,v.method_id,m.payload,m.content_hash "
        "FROM btl.product_method_versions v JOIN btl.tick_methods m "
        "ON m.workspace_id=v.workspace_id AND m.method_id=v.method_id "
        "WHERE v.workspace_id=%s AND v.family_id=%s ORDER BY v.version LIMIT %s",
        (workspace_id, family_id, MAX_METHODS + 1),
    ).fetchall()
    require(0 < len(rows) <= MAX_METHODS, "methodVersions", "REFUSED_METHOD_VERSION_LIMIT")
    versions = []
    for row in rows:
        value = unpack(row["payload"], row["content_hash"])
        method_policy(value)
        require(value["id"] == row["method_id"], "method", "CORRUPT_RECORD")
        versions.append({"version": row["version"], "methodId": row["method_id"], "method": value})
    require(versions[-1]["version"] == family["latest_version"] and
            versions[-1]["methodId"] == family["latest_method_id"] and current == versions[-1]["method"],
            "methodFamily", "CORRUPT_RECORD")
    return {"familyId": family_id, "revision": family["revision"], "archived": family["archived"],
            "latestVersion": family["latest_version"], "latestMethodId": family["latest_method_id"],
            "current": current, "versions": versions}


def page(db, workspace_id, *, limit=25, after=None, include_archived=False):
    require(type(limit) is int and 1 <= limit <= MAX_PAGE, "limit")
    require(after is None or type(after) is str, "after")
    if after is not None:
        identifier(after, "after")
    require(type(include_archived) is bool, "includeArchived")
    rows = db.execute(
        "SELECT family_id FROM btl.product_method_families "
        "WHERE workspace_id=%s AND (%s::text IS NULL OR family_id>%s) "
        "AND (%s OR NOT archived) ORDER BY family_id LIMIT %s",
        (workspace_id, after, after, include_archived, limit + 1),
    ).fetchall()
    items = [_view(db, workspace_id, row["family_id"]) for row in rows[:limit]]
    more = len(rows) > limit
    return {"schemaVersion": 1, "artifact": "BTL-METHOD-FAMILY-PAGE-1", "items": items,
            "nextCursor": items[-1]["familyId"] if more and items else None, "complete": not more}


def detail(db, workspace_id, family_id):
    return {"schemaVersion": 1, "artifact": "BTL-METHOD-FAMILY-1",
            "family": _view(db, workspace_id, family_id)}


def add_version(db, workspace_id, family_id, raw):
    require(type(raw) is dict and set(raw) == {"expectedRevision", "method"}, "methodVersion")
    revision(raw["expectedRevision"], "expectedRevision")
    method = raw["method"]
    require(type(method) is dict, "method")
    method = dict(method)
    method["name"] = label(method.get("name"))
    policy = method_policy(method)
    require(policy.kind != "FREE_STYLE" or not policy.conditions, "freeStyleConditions")
    family, current, _ = _family(db, workspace_id, family_id, lock=True)
    blob, sha = pack(method)

    prior = db.execute(
        "SELECT v.version,m.content_hash FROM btl.product_method_versions v "
        "JOIN btl.tick_methods m ON m.workspace_id=v.workspace_id AND m.method_id=v.method_id "
        "WHERE v.workspace_id=%s AND v.method_id=%s",
        (workspace_id, method["id"]),
    ).fetchone()
    if prior is not None:
        require(prior["content_hash"] == sha, "methodId", "REFUSED_IDEMPOTENCY_CONFLICT")
        require(db.execute("SELECT family_id FROM btl.product_method_versions "
                           "WHERE workspace_id=%s AND method_id=%s", (workspace_id, method["id"])).fetchone()["family_id"] == family_id,
                "methodId", "REFUSED_IDEMPOTENCY_CONFLICT")
        return detail(db, workspace_id, family_id)

    require(family["revision"] == raw["expectedRevision"], "revision", "REFUSED_STALE_REVISION")
    require(not family["archived"], "methodFamily", "REFUSED_ARCHIVED")
    require(method["id"] != family_id and method["id"] != current["id"], "methodId", "REFUSED_IDENTITY_REUSE")
    # The pre-existing 128-row catalog bound counts every immutable Method
    # payload, including successors. Archive is lifecycle metadata and never
    # frees a slot or makes historical version mappings unreadable.
    count = db.execute("SELECT count(*) FROM btl.tick_methods WHERE workspace_id=%s", (workspace_id,)).fetchone()[0]
    require(count < MAX_METHODS, "methods", "REFUSED_CATALOG_LIMIT")
    db.execute("INSERT INTO btl.tick_methods VALUES (%s,%s,%s,%s)",
               (workspace_id, method["id"], blob, sha))
    next_version = family["latest_version"] + 1
    db.execute("INSERT INTO btl.product_method_versions VALUES (%s,%s,%s,%s)",
               (workspace_id, family_id, next_version, method["id"]))
    db.execute("UPDATE btl.product_method_families SET revision=revision+1,latest_version=%s,latest_method_id=%s "
               "WHERE workspace_id=%s AND family_id=%s",
               (next_version, method["id"], workspace_id, family_id))
    return detail(db, workspace_id, family_id)


def set_archived(db, workspace_id, family_id, raw):
    require(type(raw) is dict and set(raw) == {"expectedRevision", "archived"}, "methodLifecycle")
    revision(raw["expectedRevision"], "expectedRevision")
    require(type(raw["archived"]) is bool, "archived")
    family, _current, _policy = _family(db, workspace_id, family_id, lock=True)
    if family["revision"] != raw["expectedRevision"]:
        require(False, "revision", "REFUSED_STALE_REVISION")
    if family["archived"] != raw["archived"]:
        db.execute("UPDATE btl.product_method_families SET revision=revision+1,archived=%s "
                   "WHERE workspace_id=%s AND family_id=%s",
                   (raw["archived"], workspace_id, family_id))
    return detail(db, workspace_id, family_id)
