"""Free chart restriction (owner decision 2026-11-18): a Free account never receives candles older than the start of its activated month.
 * pure clipping function (no database)
 * route level on the real stack: `chart-history` (previous-month context, frozen artifact) is refused for Free and served for Pro;
   `chart-bars` receives the floor from the server-side entitlement lookup (Free: month start, Pro: none) and the browser never sees older bars."""
import unittest
import uuid

from cloud.chart_history import clip_to_floor
from tests.test_free_pro_months import DSN, NS, MonthBase, utc_ns


def bar(t):
    return dict(time=t, open="1", high="1", low="1", close="1")


class Clip(unittest.TestCase):
    def test_pro_and_missing_floor_pass_through_unchanged(self):
        data = ([bar(100), bar(200)], bar(300), 100, True)
        self.assertEqual(clip_to_floor(*data, None), data)

    def test_free_drops_older_candles_and_ends_paging(self):
        floor = 150
        kept, forming, next_before, more = clip_to_floor([bar(100), bar(150), bar(200)], bar(300), 100, True, floor * NS)
        self.assertEqual([c["time"] for c in kept], [150, 200])               # a candle starting exactly at the floor belongs to the activated month
        self.assertEqual((forming["time"], next_before, more), (300, None, False))

    def test_free_page_wholly_before_the_floor_is_empty_and_final(self):
        kept, _forming, next_before, more = clip_to_floor([bar(10), bar(20)], None, 10, True, 500 * NS)
        self.assertEqual((kept, next_before, more), ([], None, False))

    def test_free_page_inside_the_month_keeps_paging_until_the_floor(self):
        kept, _f, next_before, more = clip_to_floor([bar(300), bar(400)], None, 300, True, 150 * NS)
        self.assertEqual(([c["time"] for c in kept], next_before, more), ([300, 400], 300, True))
        kept, _f, next_before, more = clip_to_floor([bar(200), bar(300)], None, 150, True, 150 * NS)
        self.assertEqual((next_before, more), (None, False))                  # the next page would start at/before the floor: stop here


class Stub:
    def __init__(self):
        self.calls = []

    def page(self, actor, workspace, session, *, timeframe, limit=None, before=None, floor_ns=None):
        self.calls.append(floor_ns)
        return dict(schemaVersion=1, artifact="BTL-CHART-HISTORY-PAGE-1", candles=[], hasMore=False)


@unittest.skipUnless(DSN, "Real isolated PostgreSQL required; skip is not PASS")
class Routes(MonthBase):
    def chart_context(self, sid):
        return self.client.post(self.path + "/sessions/" + sid + "/chart-history", headers={**self.headers, "X-BTL-Job": str(uuid.uuid4())}, json={"timeframe": "1m", "offset": 0})

    def test_previous_month_context_is_refused_for_free_and_not_for_pro(self):
        sid = self.new_session(with_orders=False)
        refused = self.chart_context(sid)
        self.assertEqual((refused.status_code, refused.json()["detail"]), (409, "CHART_CONTEXT_PRO_ONLY"))
        self.assertEqual(refused.json()["windowStartNs"], str(utc_ns(2020, 1)))
        self.grant_pro()
        allowed = self.chart_context(sid)
        self.assertNotEqual(refused.content, allowed.content)
        self.assertNotIn("CHART_CONTEXT_PRO_ONLY", allowed.text)               # served (or refused for an unrelated reason) but never by the plan rule

    def test_chart_bars_gets_the_floor_from_the_server_not_from_the_client(self):
        sid = self.new_session(with_orders=False)
        stub = Stub()
        self.client.app.state.chart_history = stub
        for query in ("timeframe=1m", "timeframe=1m&before=1", "timeframe=1m&before=1&floor_ns=0"):      # a client-supplied floor_ns is ignored
            r = self.client.get(self.path + "/sessions/" + sid + "/chart-bars?" + query, headers=self.headers)
            self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(set(stub.calls), {utc_ns(2020, 1)})
        self.grant_pro()
        self.client.get(self.path + "/sessions/" + sid + "/chart-bars?timeframe=1m", headers=self.headers)
        self.assertIsNone(stub.calls[-1])


if __name__ == "__main__":
    unittest.main()
