"""Server-side Free/Pro admission for new research Sessions on the default product path (opt-in: BTL_ENTITLEMENT_ENFORCE=1).

Identity is the verified bearer user; the tier is derived on the server from PAID, unexpired billing orders (never from the request). A Session creation
claims one research window: Free users get one per entitlement day (reset timezone UTC or Asia/Jakarta, visible in the refusal), Pro users are unlimited.
The claim key is a hash of workspace + request body, so an idempotent retry of the same creation does not consume a second window. A creation that fails
after the claim releases it. Open-position boundary rule and viewable-context rules of the spec are NOT implemented here (they need the execution path).
"""
import hashlib
import json
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from contracts.primitives import ContractError, require
from infrastructure.database import connect

TIMEZONES = ("UTC", "Asia/Jakarta")


class Entitlements:
    def __init__(self, dsn, reset_timezone):
        require(reset_timezone in TIMEZONES, "resetTimezone", "ACCESS_UNCONFIGURED")
        self.dsn, self.timezone = dsn, reset_timezone

    def tier(self, db, actor_id):
        now = int(datetime.now(timezone.utc).timestamp())
        paid = db.execute("SELECT 1 FROM btl.sandbox_billing_orders WHERE actor_id=%s AND phase='PAID' AND paid_at<=%s AND expires_at>%s LIMIT 1",
                          (str(actor_id), now, now)).fetchone()
        return "PRO" if paid else "FREE"

    def claim(self, actor_id, workspace_id, body):
        """Returns (claim_key, newly_claimed). Raises ContractError('DAILY_WINDOW_LIMIT') when a Free user already used today's window."""
        key = hashlib.sha256(json.dumps([str(workspace_id), body], sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        with connect(self.dsn) as db:
            day = datetime.now(ZoneInfo(self.timezone)).date()
            tier = self.tier(db, actor_id)
            if db.execute("SELECT 1 FROM btl.entitlement_windows WHERE actor_id=%s AND claim_key=%s", (str(actor_id), key)).fetchone():
                return key, False
            inserted = db.execute("INSERT INTO btl.entitlement_windows(actor_id,entitlement_day,claim_key,tier,workspace_id) VALUES (%s,%s,%s,%s,%s) "
                                  "ON CONFLICT DO NOTHING RETURNING 1", (str(actor_id), day, key, tier, str(workspace_id))).fetchone()
            if inserted is None:
                raise ContractError("DAILY_WINDOW_LIMIT", "window")
            return key, True

    def release(self, actor_id, key):
        with connect(self.dsn) as db:
            db.execute("DELETE FROM btl.entitlement_windows WHERE actor_id=%s AND claim_key=%s", (str(actor_id), key))


def from_environment(dsn):
    if os.environ.get("BTL_ENTITLEMENT_ENFORCE") != "1":
        return None
    zone = os.environ.get("BTL_ENTITLEMENT_RESET_TIMEZONE", "")
    require(zone in TIMEZONES, "resetTimezone", "ACCESS_UNCONFIGURED")      # enforcement without a visible reset rule is a configuration error
    return Entitlements(dsn, zone)
