"""Session CSV export: exact committed values, spreadsheet-injection guard, bounded size, restart on a moving revision, tenant isolation through the real app."""
import csv
import io
import json
import os
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from cloud import export_results as ex
from contracts.primitives import ContractError
import tests.test_cloud_research as cloud_fixture
from application.models import TrustedScope
from execution.research import ResearchApplication
from tests.test_research_sessions import method

TEMPLATE = Path(__file__).resolve().parents[1] / "tools/claude_exp/stack/api_journey_template.json"


def recorded_order():
    """A real committed order exactly as the product's journal page returned it (recorded from the real backend)."""
    for step in json.loads(TEMPLATE.read_text()):
        if "journal/pages" in step["path"] and step["result"].get("orders"):
            return step["result"]["orders"][0]
    raise AssertionError("no recorded journal order")


def parse(text):
    return list(csv.reader(io.StringIO(text)))


class Formatter(unittest.TestCase):
    def test_a_real_committed_order_becomes_one_exact_row(self):
        order = recorded_order()
        prov = dict(sessionId="session:x", datasetId="d", datasetVersion="v" * 64, ledgerRevision=7)
        rows = parse(ex.rows_to_csv([ex.order_row(order, prov)]))
        self.assertEqual(rows[0], list(ex.COLUMNS))
        got = dict(zip(ex.COLUMNS, rows[1]))
        for column, key in (("entryPrice", "entryPrice"), ("exitPrice", "exitPrice"), ("gross", "gross"), ("net", "net"), ("commission", "commission"), ("quantity", "quantity"),
                            ("exitReason", "exitReason"), ("side", "side"), ("orderId", "id"), ("entryTimeNs", "entryTimeNs")):
            self.assertEqual(got[column], str(order[key]), column)                     # the exact committed text, never re-rendered as a float
        want = datetime.fromtimestamp(int(order["entryTimeNs"]) // 10**9, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + f".{int(order['entryTimeNs']) % 10**9:09d}Z"
        self.assertEqual(got["entryTimeUtc"], want)
        self.assertEqual((got["sessionId"], got["ledgerRevision"]), ("session:x", "7"))

    def test_ratio_objects_never_leak_as_python_text(self):
        """Found by the real browser run: a committed ratio {numerator, denominator} was written as a Python dict repr."""
        prov = dict(sessionId="s", datasetId="d", datasetVersion="v", ledgerRevision=1)
        got = dict(zip(ex.COLUMNS, parse(ex.rows_to_csv([ex.order_row(dict(id="o", side="LONG", rMultiple={"numerator": "-19", "denominator": "20"}), prov)]))[1]))
        self.assertEqual((got["rMultiple"], got["rMultipleExact"]), ("-0.95000000", "-19/20"))
        got = dict(zip(ex.COLUMNS, parse(ex.rows_to_csv([ex.order_row(dict(id="o", side="LONG", rMultiple={"numerator": "1", "denominator": "3"}), prov)]))[1]))
        self.assertEqual((got["rMultiple"], got["rMultipleExact"]), ("0.33333333", "1/3"))
        got = dict(zip(ex.COLUMNS, parse(ex.rows_to_csv([ex.order_row(dict(id="o", side="LONG", rMultiple={"numerator": "2", "denominator": "3"}), prov)]))[1]))
        self.assertEqual(got["rMultiple"], "0.66666667")                                  # half away from zero
        self.assertNotIn("numerator", ex.rows_to_csv([ex.order_row(dict(id="o", rMultiple={"numerator": "5", "denominator": "7"}), prov)]))

    def test_nanosecond_time_is_exact(self):
        self.assertEqual(ex.iso_ns("1577836800000000001"), "2020-01-01T00:00:00.000000001Z")
        self.assertEqual(ex.iso_ns(None), "")
        with self.assertRaises(ContractError):
            ex.iso_ns("1.5e18")

    def test_spreadsheet_formula_injection_is_neutralised_but_numbers_are_untouched(self):
        prov = dict(sessionId="s", datasetId="d", datasetVersion="v", ledgerRevision=1)
        rows = parse(ex.rows_to_csv([ex.order_row(dict(id="=HYPERLINK(\"http://x\")", gross="-12.50", net="+1", exitReason="@SUM(A1)", side="LONG"), prov)]))
        got = dict(zip(ex.COLUMNS, rows[1]))
        self.assertTrue(got["orderId"].startswith("'="))
        self.assertEqual(got["gross"], "-12.50")
        self.assertTrue(got["net"].startswith("'+"))
        self.assertTrue(got["exitReason"].startswith("'@"))

    def test_commas_quotes_and_newlines_round_trip(self):
        prov = dict(sessionId="s", datasetId="d", datasetVersion="v", ledgerRevision=1)
        rows = parse(ex.rows_to_csv([ex.order_row(dict(id='a,"b"\nc', side="LONG"), prov)]))
        self.assertEqual(dict(zip(ex.COLUMNS, rows[1]))["orderId"], 'a,"b"\nc')


class Walk(unittest.TestCase):
    def fake(self, pages, summaries):
        calls = dict(summary=0, page=0)

        def run(dsn, actor, workspace, operation, args):
            if operation == "summary":
                value = summaries[min(calls["summary"], len(summaries) - 1)]; calls["summary"] += 1
                return value
            value = pages[min(calls["page"], len(pages) - 1)]; calls["page"] += 1
            return value
        return run, calls

    def page(self, revision, ids, complete, cursor=None):
        return dict(artifact="BTL-TICK-JOURNAL-PAGE-1", financialAuthority="COMMITTED_EVENTS_ONLY", revision=revision,
                    orders=[dict(id=i, side="LONG", net="1") for i in ids], complete=complete, nextCursor=cursor)

    def test_all_pages_are_collected_at_one_revision(self):
        run, _ = self.fake([self.page(5, ["a", "b"], False, "c1"), self.page(5, ["c"], True)], [dict(revision=5, datasetId="d", datasetVersion="v")])
        text, revision, count = ex.export_session_csv("dsn", "u", "w", "s", run=run)
        self.assertEqual((revision, count), (5, 3))
        self.assertEqual([r[4] for r in parse(text)[1:]], ["a", "b", "c"])

    def test_a_moving_revision_restarts_the_walk_and_never_mixes_revisions(self):
        run, calls = self.fake([self.page(5, ["a"], False, "c1"), self.page(6, ["b"], True), self.page(6, ["x", "y"], True)],
                               [dict(revision=5, datasetId="d", datasetVersion="v"), dict(revision=6, datasetId="d", datasetVersion="v")])
        text, revision, count = ex.export_session_csv("dsn", "u", "w", "s", run=run)
        self.assertEqual((revision, count), (6, 2))
        self.assertEqual({r[3] for r in parse(text)[1:]}, {"6"})
        self.assertGreaterEqual(calls["summary"], 2)

    def test_a_revision_that_never_settles_is_refused_after_three_tries(self):
        run, _ = self.fake([self.page(9, ["a"], True)], [dict(revision=r, datasetId="d", datasetVersion="v") for r in (1, 2, 3, 4)])
        with self.assertRaises(ContractError) as refused:
            ex.export_session_csv("dsn", "u", "w", "s", run=run)
        self.assertEqual(refused.exception.code, "STALE_REVISION")

    def test_size_is_bounded(self):
        run, _ = self.fake([self.page(1, ["a", "b", "c", "d"], True)], [dict(revision=1, datasetId="d", datasetVersion="v")])
        with patch.object(ex, "MAX_EXPORT_ORDERS", 3):
            with self.assertRaises(ContractError) as refused:
                ex.export_session_csv("dsn", "u", "w", "s", run=run)
        self.assertEqual(refused.exception.field, "export")


DSN = cloud_fixture.DSN


@unittest.skipUnless(DSN, "Real isolated PostgreSQL required; skip is not PASS")
class Route(unittest.TestCase):
    def setUp(self):
        self.f = cloud_fixture.CloudResearchTests("test_summary_requires_identity_membership_and_hides_foreign_session")
        self.f.setUp(start_workers=False)
        app = ResearchApplication(DSN, TrustedScope(self.f.workspace, self.f.actor))
        m = method(); app.create_method(m)
        self.session = "session:" + uuid.uuid4().hex
        app.create_session(dict(id=self.session, name="Export QA", methodId=m["id"], initialBalance="10000", startPeriod="2020-01"))
        app.close()
        self.path = self.f.root + "/sessions/" + self.session + "/export"

    def tearDown(self):
        self.f.client.close()

    def test_owner_gets_a_csv_and_everyone_else_gets_nothing(self):
        f = self.f
        self.assertEqual(f.client.get(self.path).status_code, 401)
        ok = f.client.get(self.path + "?format=csv", headers=f.headers)
        self.assertEqual(ok.status_code, 200, ok.text)
        self.assertTrue(ok.headers["content-type"].startswith("text/csv"))
        self.assertIn("attachment", ok.headers["content-disposition"])
        self.assertEqual(parse(ok.text)[0], list(ex.COLUMNS), "an empty ledger exports the header only, never invented rows")
        self.assertEqual(f.client.get(self.path + "?format=xlsx", headers=f.headers).status_code in (400, 422), True, "formats that do not exist are refused, not faked")
        _, foreign_headers = f.account()
        self.assertEqual(f.client.get(self.path, headers=foreign_headers).status_code, 404)
        other = f.client.post("/api/v1/workspaces", headers=foreign_headers, json={"name": "Foreign export QA"}).json()["id"]
        self.assertEqual(f.client.get("/api/v1/workspaces/" + other + "/research/sessions/" + self.session + "/export", headers=foreign_headers).status_code, 404)
        self.assertEqual(f.client.get(f.root + "/sessions/session:nope/export", headers=f.headers).status_code, 404)


if __name__ == "__main__":
    unittest.main()
