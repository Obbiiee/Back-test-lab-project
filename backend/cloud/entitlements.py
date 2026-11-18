"""Server-side Free/Pro admission for new research Sessions with a durable, idempotent reservation ledger.

Quotas (Free; Pro is unlimited but still recorded): one NEW Session per UTC day (owner decision 2026-11-18; was per calendar month), and one NEWLY ACTIVATED historical month per UTC day.
Continuing a Session or re-using an already activated month consumes nothing. Tier comes only from PAID, unexpired server-side billing orders.
Lifecycle of a claim: RESERVED (admitted) -> COMMITTED (the Session exists in the ledger) | RELEASED (failed before commit; token available again).
All transitions run under a per-actor advisory lock, and the database itself refuses a second active Free claim per period (partial unique index).
Reset rule is UTC only. Profiles `commercial` and `staging` (BTL_PRODUCT_PROFILE) refuse to start without enforcement (fail closed).
"""
import hashlib
import json
import os
import re
from datetime import datetime, timedelta, timezone

import psycopg

from contracts.primitives import ContractError, require
from infrastructure.database import connect

RESERVATION_TTL_SECONDS = 150        # > queue TTL 60 s + worker deadline 30 s + margin; a live job is never released by age
FREE_LIMITS = {"SESSION": 1, "WINDOW": 1}
_PERIOD = re.compile(r"^(?:19|20)[0-9]{2}-(?:0[1-9]|1[0-2])$")


class QuotaRefused(ContractError):
    def __init__(self, code, quota, reset_at):
        super().__init__(code, quota)
        self.quota, self.reset_at = quota, reset_at


def month_bounds(period):
    require(type(period) is str and _PERIOD.fullmatch(period) is not None, "startPeriod", "INVALID_INPUT")
    start = datetime(int(period[:4]), int(period[5:7]), 1, tzinfo=timezone.utc)
    end = datetime(start.year + (start.month == 12), start.month % 12 + 1, 1, tzinfo=timezone.utc)
    return int(start.timestamp()) * 10**9, int(end.timestamp()) * 10**9


def next_month(now):
    return datetime(now.year + (now.month == 12), now.month % 12 + 1, 1, tzinfo=timezone.utc)


def next_day(now):
    return datetime(now.year, now.month, now.day, tzinfo=timezone.utc) + timedelta(days=1)


def _key(*parts):
    return hashlib.sha256(json.dumps(parts, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class Entitlements:
    def __init__(self, dsn):
        self.dsn = dsn

    # ---- tier and settlement ------------------------------------------------------------------------------------------
    def tier(self, db, actor_id):
        now = int(datetime.now(timezone.utc).timestamp())
        paid = db.execute("SELECT 1 FROM btl.sandbox_billing_orders WHERE actor_id=%s AND phase='PAID' AND paid_at<=%s AND expires_at>%s LIMIT 1",
                          (str(actor_id), now, now)).fetchone()
        return "PRO" if paid else "FREE"

    def _lock(self, db, actor_id):
        db.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", ("entitle:" + str(actor_id),))

    def _settle(self, db, actor_id):
        """Resolve reservations from durable facts only: the Session exists -> COMMITTED; the job ended unsuccessfully or the reservation is old with
        no live job -> RELEASED. Never touches financial data."""
        rows = db.execute("SELECT kind,claim_key,workspace_id,session_id,job_id,reserved_at < clock_timestamp() - make_interval(secs => %s) "
                          "FROM btl.entitlement_claims WHERE actor_id=%s AND status='RESERVED'", (RESERVATION_TTL_SECONDS, str(actor_id))).fetchall()
        for kind, claim_key, workspace_id, session_id, job_id, old in rows:
            exists = db.execute("SELECT 1 FROM btl.tick_sessions WHERE workspace_id=%s AND session_id=%s", (workspace_id, session_id)).fetchone()
            new_status = None
            if exists:
                new_status = "COMMITTED"
            else:
                if job_id is not None:
                    row = db.execute("SELECT state FROM btl.research_jobs WHERE id=%s", (job_id,)).fetchone()
                    live = row is not None and row[0] in ("QUEUED", "RUNNING")
                    failed = row is not None and row[0] in ("FAILED", "CANCELLED", "EXPIRED", "RECONCILE_REQUIRED")
                else:
                    # the client sent no job id: look at this actor's create_session jobs since the reservation (conservative: a live one keeps it)
                    jobs = db.execute("SELECT state FROM btl.research_jobs WHERE actor_id=%s AND workspace_id=%s AND operation='create_session' "
                                      "AND created_at >= (SELECT reserved_at FROM btl.entitlement_claims WHERE actor_id=%s AND kind=%s AND claim_key=%s)",
                                      (str(actor_id), workspace_id, str(actor_id), kind, claim_key)).fetchall()
                    live = any(j[0] in ("QUEUED", "RUNNING") for j in jobs)
                    failed = bool(jobs) and all(j[0] in ("FAILED", "CANCELLED", "EXPIRED", "RECONCILE_REQUIRED") for j in jobs)
                if not live and (failed or old):
                    new_status = "RELEASED"
            if new_status:
                db.execute("UPDATE btl.entitlement_claims SET status=%s, settled_at=clock_timestamp() WHERE actor_id=%s AND kind=%s AND claim_key=%s",
                           (new_status, str(actor_id), kind, claim_key))

    # ---- reservation --------------------------------------------------------------------------------------------------
    def reserve(self, actor_id, workspace_id, body, job_id=None):
        """Idempotent for the same request body. Returns {'sessionClaim','windowClaim'} keys; raises QuotaRefused with the exact next reset time."""
        require(type(body) is dict and type(body.get("id")) is str, "id", "INVALID_INPUT")
        period = body.get("startPeriod")
        start_ns, end_ns = month_bounds(period)
        session_key = _key("session", str(workspace_id), body)
        window_key = _key("window", str(body.get("sourceKey", "")), period)
        with connect(self.dsn) as db:
            self._lock(db, actor_id)
            self._settle(db, actor_id)
            now = datetime.now(timezone.utc)
            tier = self.tier(db, actor_id)
            self._claim(db, actor_id, "SESSION", session_key, now.strftime("%Y-%m-%d"), tier, workspace_id, body["id"], job_id, start_ns, end_ns,
                        refusal=("SESSION_DAY_LIMIT", next_day(now)))
            self._claim(db, actor_id, "WINDOW", window_key, now.strftime("%Y-%m-%d"), tier, workspace_id, body["id"], job_id, start_ns, end_ns,
                        refusal=("WINDOW_DAY_LIMIT", next_day(now)), reuse_committed=True)
            return {"session": session_key, "window": window_key}

    def _claim(self, db, actor_id, kind, claim_key, period, tier, workspace_id, session_id, job_id, start_ns, end_ns, *, refusal, reuse_committed=False):
        row = db.execute("SELECT status,session_id FROM btl.entitlement_claims WHERE actor_id=%s AND kind=%s AND claim_key=%s FOR UPDATE",
                         (str(actor_id), kind, claim_key)).fetchone()
        code, reset_at = refusal
        if row is not None:
            status, owner_session = row
            if status == "COMMITTED" and (reuse_committed or owner_session == session_id):
                return                                                   # already activated month / already created Session: consumes nothing
            if status == "RESERVED":
                if owner_session == session_id:
                    return                                               # idempotent retry of the same request
                raise QuotaRefused("ACTIVATION_IN_PROGRESS", kind, datetime.now(timezone.utc) + timedelta(seconds=RESERVATION_TTL_SECONDS))
            # RELEASED (or a committed claim of another Session for a Session key): take it again under the same unique rules
            if status == "COMMITTED":
                raise QuotaRefused(code, kind, reset_at)
            statement = ("UPDATE btl.entitlement_claims SET status='RESERVED', period=%s, tier=%s, workspace_id=%s, session_id=%s, job_id=%s, "
                         "window_start_ns=%s, window_end_ns=%s, reserved_at=clock_timestamp(), settled_at=NULL WHERE actor_id=%s AND kind=%s AND claim_key=%s")
            params = (period, tier, str(workspace_id), session_id, job_id, start_ns, end_ns, str(actor_id), kind, claim_key)
        else:
            statement = ("INSERT INTO btl.entitlement_claims(period,tier,workspace_id,session_id,job_id,window_start_ns,window_end_ns,actor_id,kind,claim_key,status) "
                         "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'RESERVED')")
            params = (period, tier, str(workspace_id), session_id, job_id, start_ns, end_ns, str(actor_id), kind, claim_key)
        try:
            with db.transaction():                                       # savepoint: a refused insert must not poison the outer transaction
                db.execute(statement, params)
        except psycopg.errors.UniqueViolation:
            raise QuotaRefused(code, kind, reset_at) from None

    def release(self, actor_id, keys):
        """The creation failed before it started or was refused: give the tokens back (only RESERVED rows whose Session does not exist)."""
        with connect(self.dsn) as db:
            self._lock(db, actor_id)
            for kind, claim_key in (("SESSION", keys["session"]), ("WINDOW", keys["window"])):
                db.execute("UPDATE btl.entitlement_claims c SET status='RELEASED', settled_at=clock_timestamp() "
                           "WHERE actor_id=%s AND kind=%s AND claim_key=%s AND status='RESERVED' AND NOT EXISTS "
                           "(SELECT 1 FROM btl.tick_sessions s WHERE s.workspace_id=c.workspace_id AND s.session_id=c.session_id)",
                           (str(actor_id), kind, claim_key))

    # ---- read model ---------------------------------------------------------------------------------------------------
    def status(self, actor_id):
        with connect(self.dsn) as db:
            self._lock(db, actor_id)
            self._settle(db, actor_id)
            now = datetime.now(timezone.utc)
            tier = self.tier(db, actor_id)
            used = {}
            for kind, period in (("SESSION", now.strftime("%Y-%m-%d")), ("WINDOW", now.strftime("%Y-%m-%d"))):
                used[kind] = db.execute("SELECT count(*) FROM btl.entitlement_claims WHERE actor_id=%s AND kind=%s AND period=%s AND status IN ('RESERVED','COMMITTED')",
                                        (str(actor_id), kind, period)).fetchone()[0]
            limited = tier == "FREE"
            return dict(schemaVersion=1, artifact="BTL-ENTITLEMENT-STATUS-1", tier=tier, resetTimezone="UTC", observedAt=now.isoformat(),
                        sessions=dict(limit=FREE_LIMITS["SESSION"] if limited else None, used=used["SESSION"], period=now.strftime("%Y-%m-%d"), resetsAt=next_day(now).isoformat()),
                        windows=dict(limit=FREE_LIMITS["WINDOW"] if limited else None, used=used["WINDOW"], period=now.strftime("%Y-%m-%d"), resetsAt=next_day(now).isoformat()))

    def session_window(self, workspace_id, session_id):
        """(window_end_ns, tier_now) of a Session, or None when it has no recorded claim (created before enforcement)."""
        with connect(self.dsn) as db:
            row = db.execute("SELECT actor_id,window_start_ns,window_end_ns FROM btl.entitlement_claims WHERE kind='SESSION' AND workspace_id=%s AND session_id=%s "
                             "AND status IN ('RESERVED','COMMITTED') LIMIT 1", (str(workspace_id), session_id)).fetchone()
            if row is None:
                return None
            return dict(startNs=row[1], endNs=row[2], tier=self.tier(db, row[0]))


def from_environment(dsn):
    profile = os.environ.get("BTL_PRODUCT_PROFILE", "development")
    require(profile in ("development", "staging", "commercial"), "productProfile", "ACCESS_UNCONFIGURED")
    enforced = os.environ.get("BTL_ENTITLEMENT_ENFORCE") == "1"
    if profile in ("staging", "commercial"):
        require(enforced, "entitlementEnforce", "ACCESS_UNCONFIGURED")                  # fail closed: a paid-product profile never runs ungated
    if not enforced:
        return None
    zone = os.environ.get("BTL_ENTITLEMENT_RESET_TIMEZONE", "UTC")
    require(zone == "UTC", "resetTimezone", "ACCESS_UNCONFIGURED")                       # the product rule is UTC; any other value is a configuration error
    return Entitlements(dsn)
