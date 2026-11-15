"""V1 -> V2 checkpoint migration on a disposable database copy of a Session that already has trades, a partial exit, a pending order and committed receipts.
The migrated Session must end exactly where an all-V1 control Session ends; V1 rows are never rewritten or deleted. SYNTHETIC / TEST ONLY."""
import json
import os
import re
import tempfile
import unittest
import uuid
from unittest.mock import patch

import psycopg
from psycopg import sql

from application.models import TrustedScope
from contracts.canonical import content_hash
from execution import workspace
from execution.postgres import unpack
from execution.research import ResearchApplication
from infrastructure.database import connect, migrate
from market_data.monthly_parquet import MonthlyParquetProvider, write_monthly_parquet
import tests.synthetic_financial_monthly as syn
from tests.test_research_sessions import method

DSN = os.getenv("BTL_TEST_DATABASE_URL")
TICKS = 4096
STEP = 60_000_000_000


def cmd(sid, st, kind, payload):
    return {"schemaVersion": 1, "artifact": "BTL-TICK-EXECUTION-COMMAND-1", "sessionId": sid, "commandId": "c:" + uuid.uuid4().hex, "expectedRevision": st["revision"], "kind": kind, "payload": payload}


@unittest.skipUnless(DSN, "Real isolated PostgreSQL required; skip is not PASS")
class Migration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        name = "btl_mig_" + uuid.uuid4().hex[:10]
        with connect(DSN) as db:
            db.autocommit = True
            db.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        cls.dsn = psycopg.conninfo.make_conninfo(DSN, dbname=name)
        migrate(cls.dsn)
        cls.tmp = tempfile.TemporaryDirectory(prefix="riksora-mig-")
        manifest, _m, _q = syn.build_manifest(TICKS)
        version = content_hash(manifest)
        root = os.path.join(cls.tmp.name, "monthly")
        parquet = write_monthly_parquet(root, syn.iter_events(TICKS, manifest), manifest, expected_version=version, row_group_size=256)
        cls.manifest = manifest
        cls.provider = MonthlyParquetProvider(root, expected_dataset_id=manifest["datasetId"], expected_dataset_version=version, expected_manifest_hash=parquet["manifestHash"])

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def app(self):
        workspace._FIXTURE_ENTRIES.clear()                          # a cold process: no cached timeline
        return ResearchApplication(self.dsn, self.scope, synthetic_provider=self.provider, state_storage_format="compact-v1")

    def setUp(self):
        self.scope = TrustedScope("mig:" + uuid.uuid4().hex, "local:operator")
        self.method = method()
        a = self.app(); a.create_method(self.method); a.close()

    def order(self, app, sid, draft):
        view = app.workspace(sid, {"timeframe": "1m"})
        req = dict(sessionId=sid, requestId="order:" + uuid.uuid4().hex, expectedRevision=view["state"]["revision"], planId=None if draft["workflow"] == "QUICK" else "plan:mig", planRevision=None if draft["workflow"] == "QUICK" else 0,
                   draft=dict(draft, observations=[], riskPercent="1"))
        reviewed = app.review(req)
        app.confirm(sid, dict(reviewId=req["requestId"], reviewHash=reviewed["reviewHash"]))

    def advance(self, app, sid, steps):
        for _ in range(steps):
            st = app.summary(sid)
            app.apply(sid, cmd(sid, st, "ADVANCE", {"targetNs": str(int(st["throughNs"]) + 64 * STEP)}))

    def script(self, flag_after):
        """Same action sequence for control and subject; `flag_after` switches the new-format opt-in on at that point (None = never)."""
        sid = "session:" + uuid.uuid4().hex
        app = self.app()
        app.create_session(dict(id=sid, name="mig", methodId=self.method["id"], initialBalance="10000", startPeriod="2020-01"))
        st0 = app.summary(sid)
        app.apply(sid, cmd(sid, st0, "ADVANCE", {"targetNs": self.manifest["range"]["startNs"]}))     # first quote
        self.order(app, sid, dict(side="LONG", orderType="MARKET", workflow="QUICK", entry="2000", quantity="0.10", sl=None, tp=None))
        self.order(app, sid, dict(side="LONG", orderType="LIMIT", workflow="PLANNED", entry="1998.90", quantity="0.01", sl="1998.00", tp="1999.50"))
        self.advance(app, sid, 3)                                                      # the market order fills
        st = app.summary(sid)
        active = next(oid for oid, o in app.inspect(sid)["state"]["orders"].items() if o["status"] == "ACTIVE")
        app.apply(sid, cmd(sid, st, "CLOSE", {"orderId": active, "quantity": "0.05"}))   # partial exit
        self.advance(app, sid, 2)
        app.close()
        if flag_after is not None:
            os.environ["BTL_TICK_CHECKPOINT_FORMAT"] = "compact-v2"
        try:
            app = self.app()                                                           # cold, possibly in the new format
            for _ in range(80):
                if int(app.summary(sid)["throughNs"]) >= int(self.manifest["range"]["endNs"]) - 1:
                    break
                self.advance(app, sid, 1)
            facts = self.facts(app, sid)
            app.close()
        finally:
            os.environ.pop("BTL_TICK_CHECKPOINT_FORMAT", None)
        return sid, facts

    def facts(self, app, sid):
        st = app.summary(sid)
        journal = app.journal_page(sid, {"limit": 32, "cursor": None})
        return dict(through=st["throughNs"], balance=st["balance"], revision=st["revision"], trades=st["completedTrades"], net=st["netCashChange"],
                    orders=sorted(((o["side"], o["status"], o.get("quantity"), o.get("entryPrice"), o.get("exitPrice"), o.get("net")) for o in journal["orders"]), key=str))

    def normalised(self, sid):
        """Committed events with the per-session random identifiers (session, order and command ids and every hash derived from them) replaced by ordinals."""
        with connect(self.dsn) as db:
            raw = [unpack(p, h) for p, h in db.execute("SELECT payload,content_hash FROM btl.tick_events WHERE session_id=%s ORDER BY sequence", (sid,)).fetchall()]
        text = json.dumps(raw, sort_keys=True)
        seen = {}
        def token(match):
            return seen.setdefault(match.group(0), "ID%d" % len(seen))
        text = re.sub(r"(?:session|order|command|c|jump):[0-9a-f]{32}", token, text)
        return re.sub(r"[0-9a-f]{64}", "H", text)

    def rows(self, sid):
        with connect(self.dsn) as db:
            cps = db.execute("SELECT revision,content_hash FROM btl.tick_checkpoints WHERE session_id=%s ORDER BY revision", (sid,)).fetchall()
            events = db.execute("SELECT sequence,event_id,content_hash FROM btl.tick_events WHERE session_id=%s ORDER BY sequence", (sid,)).fetchall()
            commands = db.execute("SELECT revision,content_hash FROM btl.tick_commands WHERE session_id=%s ORDER BY revision", (sid,)).fetchall()
        return cps, events, commands

    def test_session_with_trades_partial_exit_pending_order_and_receipts_migrates_equal_to_an_all_v1_control(self):
        control_sid, control = self.script(None)
        sid, subject = self.script("compact-v2")
        self.assertEqual(control, subject)
        self.assertGreaterEqual(subject["trades"], 1)
        self.assertTrue(any(o[1] == "CLOSED" for o in subject["orders"]))
        # the old rows are untouched and the chain is mixed: V1 up to the switch, V2 after
        with connect(self.dsn) as db:
            kinds = []
            for (payload, sha) in db.execute("SELECT payload,content_hash FROM btl.tick_checkpoints WHERE session_id=%s ORDER BY revision", (sid,)).fetchall():
                value = unpack(payload, sha)
                controller = value.get("controller", {})
                kinds.append("V2" if controller.get("artifact") == "BTL-TICK-COMPACT-CHECKPOINT-1" else "V1" if "advanceTargets" in controller else "other")
        self.assertEqual(kinds[0], "V1")
        self.assertEqual(kinds[-1], "V2")
        self.assertEqual(kinds, sorted(kinds, key=lambda k: {"V1": 0, "V2": 1, "other": 2}[k]), "V1 rows first, then V2; none rewritten")
        # every event and command hash equals the control's (same sequence, same receipts), in the same order
        c_cps, c_events, c_commands = self.rows(control_sid)
        s_cps, s_events, s_commands = self.rows(sid)
        self.assertEqual(self.normalised(sid), self.normalised(control_sid), "event sequence, kinds, prices, quantities, times and classifications")
        self.assertEqual(len(s_commands), len(c_commands))
        self.assertEqual(len(s_cps), len(c_cps))


    def test_a_rewritten_checkpoint_pointing_at_the_wrong_position_is_refused_and_changes_nothing(self):
        from contracts.primitives import ContractError
        from execution.postgres import pack
        os.environ["BTL_TICK_CHECKPOINT_FORMAT"] = "compact-v2"
        try:
            sid = "session:" + uuid.uuid4().hex
            app = self.app()
            app.create_session(dict(id=sid, name="tamper", methodId=self.method["id"], initialBalance="10000", startPeriod="2020-01"))
            st = app.summary(sid)
            app.apply(sid, cmd(sid, st, "ADVANCE", {"targetNs": self.manifest["range"]["startNs"]}))
            self.advance(app, sid, 3)
            app.close()
            with connect(self.dsn) as db:
                revision, payload, sha = db.execute("SELECT revision,payload,content_hash FROM btl.tick_checkpoints WHERE session_id=%s ORDER BY revision DESC LIMIT 1", (sid,)).fetchone()
            wire = unpack(payload, sha)
            controller = wire["controller"]
            self.assertEqual(controller["artifact"], "BTL-TICK-COMPACT-CHECKPOINT-1")
            before = self.rows(sid)
            for change in (dict(eventsRevealed=str(int(controller["eventsRevealed"]) + 1)), dict(sourcePin=dict(controller["sourcePin"], manifestHash="1" * 64))):
                forged = dict(wire, controller=dict(controller, **change))
                raw, digest = pack(forged)
                with connect(self.dsn) as db:
                    db.execute("ALTER TABLE btl.tick_checkpoints DISABLE TRIGGER USER")
                    db.execute("UPDATE btl.tick_checkpoints SET payload=%s, content_hash=%s WHERE session_id=%s AND revision=%s", (raw, digest, sid, revision))
                    db.execute("ALTER TABLE btl.tick_checkpoints ENABLE TRIGGER USER")
                app = self.app()
                try:
                    with self.assertRaises(ContractError, msg=str(change)):
                        self.advance(app, sid, 1)
                finally:
                    app.close()
                self.assertEqual(self.rows(sid)[1:], before[1:], "no command, event or receipt was written")
                with connect(self.dsn) as db:                                       # restore the genuine row for the next forgery
                    db.execute("ALTER TABLE btl.tick_checkpoints DISABLE TRIGGER USER")
                    db.execute("UPDATE btl.tick_checkpoints SET payload=%s, content_hash=%s WHERE session_id=%s AND revision=%s", (payload, sha, sid, revision))
                    db.execute("ALTER TABLE btl.tick_checkpoints ENABLE TRIGGER USER")
        finally:
            os.environ.pop("BTL_TICK_CHECKPOINT_FORMAT", None)


if __name__ == "__main__":
    unittest.main()
