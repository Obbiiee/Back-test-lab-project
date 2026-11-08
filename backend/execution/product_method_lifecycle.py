"""Stable Method families around the existing immutable financial Method rows."""
from contracts.primitives import require, identifier, revision
from .postgres import unpack, pack
from .research import method_policy, label
from .method_version_query import version_rows, latest_version_window
from .method_version_cursor import encode as encode_version_cursor, decode as decode_version_cursor

MAX_METHODS = 128
MAX_PAGE = 50
MAX_VERSION_PAGE = 50


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
    rows, truncated = latest_version_window(
        db, workspace_id, family_id,
        latest_version=family["latest_version"], limit=MAX_METHODS)
    require(bool(rows), "methodVersions", "CORRUPT_RECORD")
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
            "current": current, "versions": versions, "versionsTruncated": truncated}


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


def versions_page(db, workspace_id, family_id, *, limit=25, cursor=None):
    """Read immutable Method versions with a family-revision-pinned keyset."""
    require(type(limit) is int and 1 <= limit <= MAX_VERSION_PAGE, "limit")
    require(cursor is None or type(cursor) is str,"cursor","INVALID_CURSOR")
    family, _current, _policy = _family(db, workspace_id, family_id)
    if cursor is None:
        after=0
    else:
        revision_pin,after=decode_version_cursor(cursor,family_id)
        require(revision_pin==family["revision"],"cursor","STALE_REVISION")
    require(after<=family["latest_version"], "afterVersion", "INVALID_CURSOR")
    rows,more=version_rows(db,workspace_id,family_id,after_version=after,limit=limit)
    page=[]
    for row in rows:
        value=unpack(row["payload"],row["content_hash"])
        method_policy(value)
        require(value["id"]==row["method_id"],
                "methodVersion", "CORRUPT_RECORD")
        page.append({"version":row["version"],"methodId":row["method_id"],"method":value})
    require(bool(page) or after==family["latest_version"],
            "methodVersion", "CORRUPT_RECORD")
    if not more:
        require(after+len(page)==family["latest_version"],
                "methodVersion", "CORRUPT_RECORD")
    return {"schemaVersion":1,"artifact":"BTL-METHOD-VERSION-PAGE-1",
            "familyId":family_id,"revision":family["revision"],"versions":page,
            "nextCursor":encode_version_cursor(family_id,family["revision"],page[-1]["version"])
                if more and page else None,"complete":not more}


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
