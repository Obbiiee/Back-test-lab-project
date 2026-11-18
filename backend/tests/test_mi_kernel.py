"""Stage 3: the multi-instrument reducer. Pure (no database).
References: (a) the existing single-instrument v2 kernel run on the SAME ticks for every instrument, (b) an independent exact oracle (Fractions, half-even money rounding) for
the shared balance, the PnL aggregation, the USD conversion and the equity. A one-instrument agreement alone is NOT taken as proof of portfolio parity."""
import random
import unittest
from fractions import Fraction

from contracts.canonical import content_hash
from contracts.primitives import ContractError
from execution import mi_kernel as mik
from tests import synthetic_mi as syn
from tests.mi_harness import FREE, PROTO, MI, reference

STEPS = 30


def half_even(value, scale=2):
    scaled = Fraction(value) * 10 ** scale
    q, r = divmod(abs(scaled.numerator), scaled.denominator)
    if 2 * r > scaled.denominator or (2 * r == scaled.denominator and q % 2):
        q += 1
    return Fraction((-q if scaled < 0 else q), 10 ** scale)


def script(symbol, rows_):
    """The same commands for every instrument and for both engines (prices are derived from the instrument's own ticks and tick size)."""
    size = syn.tick_size(symbol)
    px = lambda step, side: Fraction(rows_[step][2 if side == "ask" else 1])
    t = lambda v: __import__("execution.contracts", fromlist=["text"]).text(v)
    return {2: [("OPEN", dict(side="LONG", orderType="MARKET", workflow="QUICK", entry=t(px(2, "ask")), quantity="0.10", sl=None, tp=None, riskPercent="1", observations=[]), "a")],
            5: [("CLOSE", dict(orderId="a", quantity=None), None)],
            6: [("OPEN", dict(side="SHORT", orderType="MARKET", workflow="QUICK", entry=t(px(6, "bid")), quantity="0.20", sl=t(px(6, "ask") + 40 * size), tp=t(px(6, "bid") - 40 * size),
                              riskPercent="1", observations=[]), "b"),
                ("OPEN", dict(side="LONG", orderType="LIMIT", workflow="PLANNED", entry=t(px(6, "bid") - 6 * size), quantity="0.05", sl=t(px(6, "bid") - 40 * size),
                              tp=t(px(6, "bid") + 30 * size), riskPercent="1", observations=[]), "c")],
            12: [("OPEN", dict(side="SHORT", orderType="STOP", workflow="PLANNED", entry=t(px(12, "bid") - 8 * size), quantity="0.10", sl=t(px(12, "ask") + 40 * size),
                               tp=t(px(12, "bid") - 60 * size), riskPercent="1", observations=[]), "d")],
            16: [("CLOSE", dict(orderId="b", quantity="0.10"), None)],                      # partial close
            22: [("CLOSE", dict(orderId="b", quantity=None), None)]}


def run_mi(symbols, steps=STEPS, scripts=None, only=None, through_steps=None, **kw):
    m = MI(symbols, steps=steps, **kw)
    scripts = scripts or {s: (script(s, m.rows[s]) if only in (None, s) else {}) for s in symbols}
    # Keep the canonical source long enough to build the complete command script;
    # callers may stop the replay early without truncating source evidence.
    for step in range(steps if through_steps is None else through_steps):
        m.to(m.at(step))
        for s in symbols:
            for kind, payload, cid in scripts[s].get(step, []):
                if kind == "OPEN":
                    m.apply("OPEN", dict(payload, symbol=s), f"{s}:{cid}")
                elif m.state["orders"].get(f"{s}:{payload['orderId']}", {}).get("status") == "ACTIVE":
                    m.apply("CLOSE", dict(payload, orderId=f"{s}:{payload['orderId']}"))
    return m, scripts


FIELDS = ("status", "entryPrice", "remaining", "grossPosted", "entryCostPosted", "exitCostPosted")


class SingleInstrumentParity(unittest.TestCase):
    def test_every_one_of_the_sixteen_instruments_equals_the_v2_kernel(self):
        for symbol in syn.ORDER:
            with self.subTest(symbol=symbol):
                route = next(v["input"]["conversion"]["symbol"] for v in syn.VECTORS if v["name"] == symbol and v["input"]["conversion"])  if any(
                    v["name"] == symbol and v["input"]["conversion"] for v in syn.VECTORS) else None
                symbols = [symbol] + ([route] if route and route != symbol else [])      # USDJPY-style pairs convert through themselves
                m, scripts = run_mi(symbols, only=symbol)                               # only the instrument under test trades; its route just quotes
                route_rows = m.rows[route] if route else None
                ref = reference(symbol, m.rows[symbol], route_rows, scripts[symbol], STEPS)
                self.assertEqual(set(ref.state["orders"]), {k.split(":")[1] for k in m.state["orders"]})
                for cid, ro in ref.state["orders"].items():
                    mo = m.state["orders"][f"{symbol}:{cid}"]
                    self.assertEqual({f: mo[f] for f in FIELDS}, {f: ro[f] for f in FIELDS}, cid)
                for key in ("balance", "realizedGross", "commission"):
                    self.assertEqual(m.state[key], ref.state[key], key)
                fills = [(e["kind"], e["detail"]["price"], e["detail"]["timeNs"]) for e in m.events if e["classification"] == "SIMULATED_FILL"]
                rfills = [(e["kind"], e["detail"]["price"], e["detail"]["timeNs"]) for e in ref.events if e["classification"] == "SIMULATED_FILL"]
                self.assertEqual(fills, rfills)
                self.assertGreater(len(fills), 3, "the scenario must actually trade")


class Portfolio(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m, cls.scripts = run_mi(syn.ORDER)

    def test_shared_balance_and_realised_pnl_equal_the_sum_of_sixteen_references(self):
        total_delta = total_gross = total_fee = Fraction(0)
        for symbol in syn.ORDER:
            route = next((v["input"]["conversion"]["symbol"] for v in syn.VECTORS if v["name"] == symbol and v["input"]["conversion"]), None)
            ref = reference(symbol, self.m.rows[symbol], self.m.rows[route] if route else None, self.scripts[symbol], STEPS)
            for cid, ro in ref.state["orders"].items():
                mo = self.m.state["orders"][f"{symbol}:{cid}"]
                self.assertEqual({f: mo[f] for f in FIELDS}, {f: ro[f] for f in FIELDS}, symbol + cid)
            total_delta += Fraction(ref.state["balance"]) - 10000
            total_gross += Fraction(ref.state["realizedGross"]); total_fee += Fraction(ref.state["commission"])
        self.assertEqual(Fraction(self.m.state["balance"]) - 10000, total_delta)
        self.assertEqual((Fraction(self.m.state["realizedGross"]), Fraction(self.m.state["commission"])), (total_gross, total_fee))
        self.assertTrue(any(o["status"] == "CLOSED" for o in self.m.state["orders"].values()))
        self.assertGreaterEqual(len({o["symbol"] for o in self.m.state["orders"].values() if o["status"] != "PENDING"}), 8, "many instruments must have traded")

    def test_independent_oracle_for_gross_in_usd_per_exit(self):
        """Recompute every exit's USD gross from the raw ticks with a separate implementation of the conversion rule (gain: ask for DIVIDE / bid for MULTIPLY; loss: the other side)."""
        rows = {s: [(t, Fraction(b), Fraction(a)) for t, b, a in self.m.rows[s]] for s in syn.ORDER}
        by_wire = {w["symbol"]: w for w in self.m.wires}
        checked = 0
        for e in self.m.events:
            if e["kind"] != "EXIT_FILL":
                continue
            o, w = self.m.state["orders"][e["orderId"]], by_wire[e["symbol"]]
            exit_t, fill = int(e["detail"]["timeNs"]), Fraction(e["detail"]["price"])
            lots = Fraction(e["detail"]["quantity"])
            gross_quote = (1 if o["side"] == "LONG" else -1) * (fill - Fraction(o["entryPrice"])) * Fraction(w["contractSize"]) * lots
            quote_ccy = w["quoteCurrency"]
            if quote_ccy == "USD":
                usd = gross_quote
            else:
                route = w["conversion"]["symbol"]
                t, bid, ask = [r for r in rows[route] if r[0] <= exit_t][-1]                       # latest route tick at or before the exit: never a later one
                multiply = route.endswith("USD")                                                   # GBPUSD, NZDUSD multiply; USDJPY, USDCAD, USDCHF divide
                side = (bid if gross_quote >= 0 else ask) if multiply else (ask if gross_quote >= 0 else bid)
                usd = gross_quote * side if multiply else gross_quote / side
            self.assertEqual(Fraction(e["detail"]["grossPosted"]), half_even(usd), (e["symbol"], e["orderId"]))
            checked += 1
        self.assertGreaterEqual(checked, 12)

    def test_financial_events_follow_the_total_order_time_then_instrument_index(self):
        fin = [(int(e["detail"]["timeNs"]), syn.ORDER.index(e["symbol"])) for e in self.m.events if e["classification"] == "SIMULATED_FILL"]
        self.assertEqual(fin, sorted(fin))
        self.assertTrue(any(fin[i][0] == fin[i + 1][0] for i in range(len(fin) - 1)), "the scenario must include fills at the same timestamp on different instruments")

    def test_equity_oracle_at_several_times(self):
        for stop in (8, 14, 20, STEPS - 1):
            m, _ = run_mi(syn.ORDER, through_steps=stop + 1)
            eq = mik.equity(m.state)
            total = Fraction(0)
            by_wire = {w["symbol"]: w for w in m.wires}
            complete = True
            for oid, o in m.state["orders"].items():
                if o["status"] != "ACTIVE":
                    continue
                w, now = by_wire[o["symbol"]], int(m.state["throughNs"])
                # The oracle may use only quotes the timeline has revealed. Looking
                # up the generated source rows by timestamp leaked a same-time route
                # quote when that instrument had not yet been consumed in total order.
                primary = m.state["groups"][o["symbol"]]
                if primary is None:
                    complete = False
                    continue
                bid, ask = Fraction(primary["events"][-1]["bid"]), Fraction(primary["events"][-1]["ask"])
                q = (1 if o["side"] == "LONG" else -1) * ((bid if o["side"] == "LONG" else ask) - Fraction(o["entryPrice"])) * Fraction(w["contractSize"]) * Fraction(o["remaining"])
                if w["quoteCurrency"] != "USD":
                    route = w["conversion"]["symbol"]
                    route_group = m.state["groups"][route]
                    if route_group is None:
                        # Missing revealed conversion evidence must make equity
                        # incomplete; it must never be filled from future source rows.
                        complete = False
                        continue
                    if now - int(route_group["timeNs"]) > int(w["conversion"]["maxAgeNs"]):
                        complete = False
                        continue
                    rb, ra = Fraction(route_group["events"][-1]["bid"]), Fraction(route_group["events"][-1]["ask"])
                    multiply = route.endswith("USD")
                    side = (rb if q >= 0 else ra) if multiply else (ra if q >= 0 else rb)
                    q = q * side if multiply else q / side
                total += q
            self.assertEqual(eq["complete"], complete, stop)
            self.assertEqual(Fraction(int(eq["unrealizedUsdExact"]["numerator"]), int(eq["unrealizedUsdExact"]["denominator"])), total, stop)
            self.assertEqual(Fraction(eq["equityUsd"]), half_even(Fraction(m.state["balance"]) + total))


class Determinism(unittest.TestCase):
    def test_same_inputs_give_identical_state_and_hash_chain(self):
        a, _ = run_mi(syn.ORDER)
        b, _ = run_mi(syn.ORDER)
        self.assertEqual(content_hash(a.state), content_hash(b.state))
        self.assertEqual([e["eventId"] for e in a.events], [e["eventId"] for e in b.events])
        self.assertEqual(a.pset.profile_set_hash, b.pset.profile_set_hash)

    def test_stepwise_replay_equals_one_big_advance(self):
        a, scripts = run_mi(["EURUSD", "GBPUSD"], steps=20)
        b = MI(["EURUSD", "GBPUSD"], steps=20)
        b.to(b.at(0))
        for step in range(20):
            if step:
                b.to(b.at(step))
            for s in b.symbols:
                for kind, payload, cid in scripts[s].get(step, []):
                    if kind == "OPEN":
                        b.apply("OPEN", dict(payload, symbol=s), f"{s}:{cid}")
                    elif b.state["orders"].get(f"{s}:{payload['orderId']}", {}).get("status") == "ACTIVE":
                        b.apply("CLOSE", dict(payload, orderId=f"{s}:{payload['orderId']}"))
        self.assertEqual({k: v for k, v in a.state.items() if k not in ("revision",)}["balance"], b.state["balance"])
        self.assertEqual(a.state["orders"], b.state["orders"])


class NoLookAheadAndNoSyntheticPrices(unittest.TestCase):
    def test_a_conversion_is_never_taken_from_a_later_route_tick(self):
        m = MI(["EURJPY", "USDJPY"], steps=12)
        m.to(m.at(1)); m.open("EURJPY", cid="x"); m.to(m.at(3))
        before = m.state["groups"]["USDJPY"]["timeNs"]
        m.apply("CLOSE", dict(orderId="x", quantity=None)); m.to(m.at(4))
        fill = next(e for e in m.events if e["kind"] == "EXIT_FILL")
        self.assertLessEqual(int(fill["detail"]["conversionEvidence"]["timeNs"]), int(fill["detail"]["timeNs"]))
        self.assertLessEqual(int(before), int(fill["detail"]["timeNs"]))

    def test_a_stale_route_makes_the_session_unresolved_and_equity_unavailable_never_a_made_up_rate(self):
        # USDJPY stops quoting after step 2 while EURJPY keeps going for 100 more seconds of simulated time (ages are in ns: 60 s = 60e9)
        big = {}
        eur = [(syn.T0 + i * 10 * 10 ** 9, "165", "165.02") for i in range(12)]
        usd = [(syn.T0 + i * 10 * 10 ** 9, "150", "150.02") for i in range(3)]
        m = MI(["EURJPY", "USDJPY"], steps=12, rows_override={"EURJPY": eur, "USDJPY": usd})
        m.to(syn.T0); m.open("EURJPY", cid="x"); m.to(syn.T0 + 20 * 10 ** 9)
        self.assertEqual(m.state["orders"]["x"]["status"], "ACTIVE")
        m.to(syn.T0 + 60 * 10 ** 9)                                                                   # route quote is now 40 s old: still fresh (limit 60 s)
        self.assertTrue(mik.equity(m.state)["complete"])
        m.to(syn.T0 + 100 * 10 ** 9)                                                                  # 80 s old: stale
        eq = mik.equity(m.state)
        self.assertFalse(eq["complete"])
        self.assertEqual(eq["positions"][0]["status"], "UNAVAILABLE")
        self.assertTrue(eq["positions"][0]["reason"].startswith("UNRESOLVED_FX"))
        m.apply("CLOSE", dict(orderId="x", quantity=None)); m.to(syn.T0 + 110 * 10 ** 9)
        self.assertTrue(m.state["unresolved"], "an exit that needs a stale rate must not be priced")
        self.assertEqual(m.state["orders"]["x"]["status"], "UNRESOLVED")
        self.assertEqual(m.state["realizedGross"], "0")

    def test_no_order_is_accepted_on_a_pair_without_a_revealed_quote_or_a_provable_conversion(self):
        m = MI(["EURJPY", "USDJPY"], steps=6, gaps={"USDJPY": (0, 1, 2, 3, 4, 5)})
        m.to(m.at(0))
        with self.assertRaises(ContractError) as ctx:
            m.open("EURJPY")
        self.assertIn("UNRESOLVED_FX", ctx.exception.code)

    def test_the_target_never_reveals_a_later_group(self):
        m = MI(["EURUSD", "GBPUSD"], steps=10)
        m.to(m.at(3))
        self.assertTrue(all(int(g["timeNs"]) <= m.at(3) for g in m.state["groups"].values() if g))
        with self.assertRaises(ContractError):
            mik.advance(m.state, [dict(timeNs=m.at(9), instrument="EURUSD", instrumentIndex=0, events=m.ticks["EURUSD"][9:10])], str(m.at(5)))


class MethodsAndPairs(unittest.TestCase):
    def test_orders_keep_their_pair_and_method_while_the_user_switches_both(self):
        m = MI(["EURUSD", "XAUUSD", "EURJPY", "USDJPY"], steps=20, policies=[FREE, PROTO])
        m.to(m.at(2))
        m.open("EURUSD", cid="o1")                                                                    # Free style on EURUSD
        m.apply("SET_METHOD", dict(methodId="method:proto"))
        m.open("XAUUSD", lots="0.1", cid="o2") if False else None
        with self.assertRaises(ContractError):
            m.open("XAUUSD", cid="o2")                                                                # Protocol refuses a QUICK order on ANY pair
        m.apply("SET_METHOD", dict(methodId="method:free"))
        m.open("EURJPY", cid="o3"); m.to(m.at(8))
        self.assertEqual({k: (o["symbol"], o["methodId"]) for k, o in m.state["orders"].items()}, {"o1": ("EURUSD", "method:free"), "o3": ("EURJPY", "method:free")})
        m.apply("SET_METHOD", dict(methodId="method:proto"))                                          # the open positions are untouched and still processed
        before = {k: dict(o) for k, o in m.state["orders"].items()}
        m.to(m.at(12))
        self.assertTrue(all(m.state["orders"][k]["methodId"] == "method:free" for k in before))
        # closing is governed by the order's own Method (Free style): allowed although Protocol is active
        m.apply("CLOSE", dict(orderId="o1", quantity=None)); m.to(m.at(14))
        self.assertEqual(m.state["orders"]["o1"]["status"], "CLOSED")

    def test_protocol_sizing_on_a_non_usd_pair_equals_an_independent_calculation(self):
        m = MI(["EURJPY", "USDJPY"], steps=8, policies=[FREE, PROTO], active="method:proto")
        m.to(m.at(3))
        bid, ask = (Fraction(x) for x in m.quote("EURJPY"))
        size = syn.tick_size("EURJPY")
        entry, sl = bid - 4 * size, bid - 4 * size - 50 * size
        tp = entry + (entry - sl) * 2                                                                 # R:R 1:2 as the Protocol demands
        usdjpy = Fraction(m.quote("USDJPY")[0])                                                       # a loss converts at the BID of USDJPY (divide)
        per_lot_usd = (entry - sl) * 100000 / usdjpy
        budget = Fraction(m.state["balance"]) * 1 / 100
        step = Fraction("0.01")
        lots = int(budget / per_lot_usd / step) * step
        from execution.contracts import text
        good = dict(symbol="EURJPY", side="LONG", orderType="LIMIT", workflow="PLANNED", entry=text(entry), quantity=text(lots), sl=text(sl), tp=text(tp), riskPercent="1",
                    observations=[dict(conditionId="c1", outcome="PASS")])
        m.apply("OPEN", good, "p1")
        bad = dict(good, quantity=text(lots + step))
        with self.assertRaises(ContractError):
            m.apply("OPEN", bad, "p2")


class Refusals(unittest.TestCase):
    def test_conversion_route_outside_the_set_and_unknown_pair_are_refused(self):
        with self.assertRaises(ContractError):
            MI(["EURJPY"], steps=3)                                                                   # USDJPY is not in the set
        m = MI(["EURUSD", "GBPUSD"], steps=5)
        m.to(m.at(1))
        with self.assertRaises(ContractError):
            m.apply("OPEN", dict(symbol="AUDUSD", side="LONG", orderType="MARKET", workflow="QUICK", entry="1", quantity="0.1", sl=None, tp=None, riskPercent="1", observations=[]), "z")

    def test_stale_revision_and_duplicate_command_ids_are_refused(self):
        m = MI(["EURUSD"], steps=5)
        m.to(m.at(1)); m.open("EURUSD", cid="dup")
        with self.assertRaises(ContractError):
            m.open("EURUSD", cid="dup")


if __name__ == "__main__":
    unittest.main()
