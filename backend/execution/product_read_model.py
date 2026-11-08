"""Bounded, workspace-scoped metadata read models for Product V1.

These endpoints expose only already committed Method and Session metadata. They
do not load tick providers, replay state, calculate financial values, or infer
source eligibility. Session detail remains the authority for current state.
"""
from contracts.primitives import require, identifier
from .postgres import unpack
from .research import method_policy

MAX_PAGE_SIZE = 50


def _page_args(limit, after):
    require(type(limit) is int and 1 <= limit <= MAX_PAGE_SIZE, "limit")
    require(after is None or (type(after) is str and len(after) <= 128), "after")
    if after is not None:
        identifier(after, "after")


def methods(db, workspace_id, *, limit=25, after=None):
    _page_args(limit, after)
    rows = db.execute(
        "SELECT method_id,payload,content_hash FROM btl.tick_methods "
        "WHERE workspace_id=%s AND (%s::text IS NULL OR method_id>%s) "
        "ORDER BY method_id LIMIT %s",
        (workspace_id, after, after, limit + 1),
    ).fetchall()
    page = []
    for row in rows[:limit]:
        method_id = row["method_id"]
        value = unpack(row["payload"], row["content_hash"])
        method_policy(value)
        require(value["id"] == method_id, "method", "CORRUPT_RECORD")
        page.append(value)
    more = len(rows) > limit
    return {
        "schemaVersion": 1,
        "artifact": "BTL-METHOD-PAGE-1",
        "items": page,
        "nextCursor": page[-1]["id"] if more and page else None,
        "complete": not more,
    }


def method(db, workspace_id, method_id):
    identifier(method_id, "methodId")
    row = db.execute(
        "SELECT payload,content_hash FROM btl.tick_methods "
        "WHERE workspace_id=%s AND method_id=%s",
        (workspace_id, method_id),
    ).fetchone()
    require(row is not None, "method", "RESOURCE_UNAVAILABLE")
    value = unpack(row["payload"], row["content_hash"])
    method_policy(value)
    require(value["id"] == method_id, "method", "CORRUPT_RECORD")
    return {"schemaVersion": 1, "artifact": "BTL-METHOD-1", "method": value}


def sessions(db, workspace_id, *, limit=25, after=None, method_id=None):
    _page_args(limit, after)
    if method_id is not None:
        identifier(method_id, "methodId")
    rows = db.execute(
        "SELECT r.session_id,r.method_id,r.payload AS session_payload,r.content_hash AS session_hash,"
        "s.revision,m.payload AS method_payload,m.content_hash AS method_hash "
        "FROM btl.tick_research_sessions r "
        "JOIN btl.tick_sessions s ON s.workspace_id=r.workspace_id AND s.session_id=r.session_id "
        "JOIN btl.tick_methods m ON m.workspace_id=r.workspace_id AND m.method_id=r.method_id "
        "WHERE r.workspace_id=%s AND (%s::text IS NULL OR r.session_id>%s) "
        "AND (%s::text IS NULL OR r.method_id=%s) "
        "ORDER BY r.session_id LIMIT %s",
        (workspace_id, after, after, method_id, method_id, limit + 1),
    ).fetchall()
    page = []
    for row in rows[:limit]:
        session_id = row["session_id"]
        method_id_value = row["method_id"]
        revision = row["revision"]
        meta = unpack(row["session_payload"], row["session_hash"])
        method_value = unpack(row["method_payload"], row["method_hash"])
        policy = method_policy(method_value)
        artifact = meta.get("artifact")
        if artifact == "BTL-LOCAL-SESSION-1":
            from ticks.contracts import tag
            tag(meta, artifact, "id name methodId methodHash datasetId datasetVersion profileHash startPeriod initialBalance" +
                (" sourceKey monthlyManifestHash" if "sourceKey" in meta or "monthlyManifestHash" in meta else ""))
        elif artifact == "BTL-OBSERVED-RESEARCH-SESSION-1":
            from execution.observed_research import META
            from ticks.contracts import tag
            tag(meta, META, "id name methodId methodHash datasetKey period day datasetId datasetVersion profileHash startNs initialBalance model engineVersion creationRequestHash")
        else:
            require(False, "session", "CORRUPT_RECORD")
        require(meta.get("id") == session_id and meta.get("methodId") == method_id_value and
                method_value.get("id") == method_id_value and meta.get("methodHash") == policy.definition_hash,
                "session", "CORRUPT_RECORD")
        public_meta = {
            "id": session_id,
            "name": meta["name"],
            "methodId": method_id_value,
            "methodHash": meta["methodHash"],
            "datasetId": meta["datasetId"],
            "datasetVersion": meta["datasetVersion"],
            "profileHash": meta["profileHash"],
            "startPeriod": meta.get("startPeriod", meta.get("period")),
            "initialBalance": meta["initialBalance"],
        }
        if "day" in meta:
            public_meta["day"] = meta["day"]
        if "sourceKey" in meta:
            public_meta["sourceKey"] = meta["sourceKey"]
        page.append({
            "metadata": public_meta,
            "revision": revision,
            "financialCountsStatus": "NOT_COMPUTED_ON_LIST",
        })
    more = len(rows) > limit
    return {
        "schemaVersion": 1,
        "artifact": "BTL-SESSION-PAGE-1",
        "items": page,
        "nextCursor": page[-1]["metadata"]["id"] if more and page else None,
        "complete": not more,
        "financialAuthority": "SESSION_DETAIL_AND_COMMITTED_EVENTS",
    }
