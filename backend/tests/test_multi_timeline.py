"""Stage 1 of multi-pair: the deterministic fan-in timeline (no database, no reducer)."""
import random
import unittest

from contracts.primitives import ContractError
from ticks.multi_timeline import MultiTimeline
from tests.synthetic_multi_instrument import catalogue, source, ticks_for

N = 300


def flat(groups):
    return [(g["timeNs"], g["instrumentIndex"], t["rawOrdinal"]) for g in groups for t in g["events"]]


class Order(unittest.TestCase):
    def setUp(self):
        self.names, self.data, self.sources = catalogue(N)

    def expected(self):
        rows = [(int(t["timeNs"]), i, int(t["rawOrdinal"])) for i, name in enumerate(self.names) for t in self.data[name]]
        return sorted(rows)

    def test_sixteen_instruments_equal_the_independent_total_order(self):
        self.assertEqual(len(self.names), 16)
        out = flat(MultiTimeline(self.names, self.sources).advance(10**20))
        self.assertEqual([(t, i, int(o)) for t, i, o in out], self.expected())
        self.assertEqual(len(out), 16 * N)

    def test_order_does_not_depend_on_how_the_sources_are_supplied(self):
        shuffled = dict(random.Random(5).sample(sorted(self.sources.items()), len(self.sources)))
        a = flat(MultiTimeline(self.names, self.sources).advance(10**20))
        b = flat(MultiTimeline(self.names, shuffled).advance(10**20))
        self.assertEqual(a, b)

    def test_equal_timestamps_follow_the_pinned_instrument_index_not_the_name(self):
        names = ["USDJPY", "AUDUSD", "XAUUSD"]                        # deliberately not alphabetical
        mk = lambda s, t: dict(timeNs=str(t), instrumentId=s, rawOrdinal="0", bid="1", ask="2")
        srcs = {n: source([mk(n, 5)]) for n in names}
        out = MultiTimeline(names, srcs).advance(5)
        self.assertEqual([g["instrument"] for g in out], names)

    def test_a_timestamp_group_is_atomic_and_never_split_by_a_target(self):
        names = ["EURUSD"]
        ticks = [dict(timeNs="10", instrumentId="EURUSD", rawOrdinal=str(k), bid="1", ask="2") for k in range(4)] + [dict(timeNs="11", instrumentId="EURUSD", rawOrdinal="4", bid="1", ask="2")]
        tl = MultiTimeline(names, {"EURUSD": source(ticks)})
        self.assertEqual(tl.advance(9), [])
        first = tl.advance(10)
        self.assertEqual((len(first), len(first[0]["events"])), (1, 4))
        self.assertEqual([e["rawOrdinal"] for e in first[0]["events"]], ["0", "1", "2", "3"])


class NoLookAhead(unittest.TestCase):
    def setUp(self):
        self.names, self.data, self.sources = catalogue(N)

    def test_advance_never_returns_a_group_after_the_target(self):
        tl = MultiTimeline(self.names, self.sources)
        horizon = [int(t["timeNs"]) for t in self.data[self.names[0]]]
        for target in horizon[::37]:
            for g in tl.advance(target):
                self.assertLessEqual(g["timeNs"], target)

    def test_stepwise_advances_concatenate_to_one_big_advance(self):
        whole = flat(MultiTimeline(self.names, self.sources).advance(10**20))
        tl, parts = MultiTimeline(self.names, self.sources), []
        for target in range(1_577_836_800 * 10**9, 1_577_836_800 * 10**9 + 400 * 10**9, 7 * 10**9):
            parts += tl.advance(target)
        parts += tl.advance(10**20)
        self.assertEqual(flat(parts), whole)

    def test_last_quotes_are_the_latest_at_or_before_the_frontier_only(self):
        tl = MultiTimeline(self.names, self.sources)
        target = 1_577_836_800 * 10**9 + 90 * 10**9
        tl.advance(target)
        for name, quote in tl.last_quotes().items():
            upto = [t for t in self.data[name] if int(t["timeNs"]) <= target]
            if not upto:
                self.assertIsNone(quote)
            else:
                last = max(upto, key=lambda t: (int(t["timeNs"]), int(t["rawOrdinal"])))
                self.assertEqual((quote["timeNs"], quote["bid"], quote["ask"]), (last["timeNs"], last["bid"], last["ask"]))
                self.assertLessEqual(int(quote["timeNs"]), target)

    def test_rewind_is_refused(self):
        tl = MultiTimeline(self.names, self.sources)
        tl.advance(1_577_836_800 * 10**9 + 50 * 10**9)
        with self.assertRaises(ContractError):
            tl.advance(1_577_836_800 * 10**9)


class Resume(unittest.TestCase):
    def test_cursor_resume_gives_exactly_the_uninterrupted_remainder(self):
        names, data, sources = catalogue(N)
        full = flat(MultiTimeline(names, sources).advance(10**20))
        rng = random.Random(11)
        for _ in range(12):
            cut = 1_577_836_800 * 10**9 + rng.randrange(0, 380) * 10**9
            a = MultiTimeline(names, sources)
            head = flat(a.advance(cut))
            b = MultiTimeline(names, sources, cursor=a.cursor())               # a "new process" resumes from the durable cursor
            self.assertEqual(b.last_quotes(), a.last_quotes())
            self.assertEqual(head + flat(b.advance(10**20)), full)

    def test_cursor_for_another_instrument_set_is_refused(self):
        names, _d, sources = catalogue(20, ["EURUSD", "GBPUSD"])
        a = MultiTimeline(names, sources)
        a.advance(10**20)
        with self.assertRaises(ContractError):
            MultiTimeline(["GBPUSD", "EURUSD"], sources, cursor=a.cursor())


class Refusals(unittest.TestCase):
    def test_a_source_that_goes_backwards_is_refused(self):
        bad = [dict(timeNs="10", instrumentId="EURUSD", rawOrdinal="0", bid="1", ask="2"), dict(timeNs="5", instrumentId="EURUSD", rawOrdinal="1", bid="1", ask="2")]
        with self.assertRaises(ContractError):
            MultiTimeline(["EURUSD"], {"EURUSD": lambda skip=0: iter(bad)}).advance(100)

    def test_instrument_sets_must_be_valid(self):
        _n, _d, s = catalogue(5, ["EURUSD", "GBPUSD"])
        for names in (["EURUSD", "EURUSD"], [], ["EURUSD"] * 17):
            with self.assertRaises(ContractError):
                MultiTimeline(names, s)
        with self.assertRaises(ContractError):
            MultiTimeline(["EURUSD"], s)                                   # sources do not match the pinned set


if __name__ == "__main__":
    unittest.main()
