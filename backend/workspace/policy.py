"""Pure minimum ownership policy, distinct from future configurable RBAC."""
from contracts.primitives import require, revision

KINDS = {"BACKTEST", "STRATEGY", "DRAWING", "INDICATOR", "PREFERENCE", "EXPERIMENT", "REPORT", "RESEARCH_JOB"}


def name(value):
    require(type(value) is str and 0 < len(value.strip()) <= 128 and
            not any(ord(char) < 32 or 0xD800 <= ord(char) <= 0xDFFF for char in value), "name")
    return value.strip()


def active_verified(user):
    require(user is not None and user["is_active"] and user["is_verified"], "identity", "UNAUTHORIZED")


def owner(role):
    require(role == "OWNER", "membership", "OWNER_REQUIRED")


def writable(resource, actor_id, role):
    require(role == "OWNER" or resource["creator_id"] == actor_id, "resource", "WRITE_FORBIDDEN")


def expected(resource, value):
    revision(value)
    require(resource["revision"] == value, "resourceRevision", "STALE_REVISION")
