"""Independent authored arithmetic vectors, not real provider acceptance."""
from copy import deepcopy
from fractions import Fraction
import unittest

from execution.conversion import convert_usd
from ticks.contracts import event_id
from ticks.timeline import make_group

VERSION = "a" * 64
ROUTES = {"GBP": "GBPUSD", "NZD": "NZDUSD", "JPY": "USDJPY", "CAD": "USDCAD", "CHF": "USDCHF"}


def fixture(currency="JPY", bid="2", ask="4", count=1):
    symbol = ROUTES[currency]
    pin = dict(currency=currency, symbol=symbol, datasetId="authored:fx", datasetVersion=VERSION,
               providerId="synthetic", feedId="authored:fx", feedInstrumentId="synthetic:" + symbol, maxAgeNs="10")
    rows = []
    for i in range(count):
        rows.append(dict(schemaVersion=1, artifact="BTL-CANONICAL-TICK-1", datasetId=pin["datasetId"],
            datasetVersion=VERSION, providerId=pin["providerId"], feedId=pin["feedId"], instrumentId=pin["feedInstrumentId"],
            eventId=event_id(pin["providerId"], pin["feedId"], "b" * 64, str(i)), timeNs="100", resolutionNs="1",
            bid=bid, ask=ask, rawOrdinal=str(i), trustedSequence=None,
            provenance=dict(sourceId="authored:fixture", memberHash="b" * 64, originalTimestamp="authored ns100"),
            quality=dict(evidenceHash="c" * 64, quote="VALID", freshness="CONFIRMED", gapBefore="NONE", duplicateOf=None)))
    return pin, make_group(rows, VERSION)


class ConversionTests(unittest.TestCase):
    def test_signed_direct_and_inverse_routes_independent_vectors(self):
        for currency in ROUTES:
            pin, group = fixture(currency)
            direct = currency in ("GBP", "NZD")
            for amount, expected, side in (("8", "16" if direct else "2", "bid" if direct else "ask"),
                                            ("-8", "-32" if direct else "-4", "ask" if direct else "bid")):
                with self.subTest(currency=currency, amount=amount):
                    result = convert_usd(amount, currency, "100", pin=pin, group=group)
                    self.assertEqual(result["usdRounded"], expected)
                    self.assertEqual(result["evidence"]["side"], side)
                    self.assertEqual(result["evidence"]["pin"]["feedInstrumentId"], "synthetic:" + ROUTES[currency])

    def test_usd_identity_zero_and_half_even_without_binary_float(self):
        for value, expected in (("1.005", "1"), ("1.015", "1.02"), ("-1.005", "-1"), ("-1.015", "-1.02"), ("0", "0")):
            self.assertEqual(convert_usd(value, "USD", "0")["usdRounded"], expected)
        for value in (1.1, True, "NaN", "1e37"):
            with self.assertRaises(ValueError): convert_usd(value, "USD", "100")
        pin, group = fixture()
        with self.assertRaises(ValueError): convert_usd("1", "USD", "100", pin=pin, group=group)

    def test_repeating_rational_retained_and_rounds_only_once(self):
        pin, group = fixture(bid="3", ask="3")
        result = convert_usd("1", "JPY", "100", pin=pin, group=group)
        self.assertEqual(result["usdExact"], dict(numerator="1", denominator="3"))
        self.assertEqual(result["usdRounded"], "0.33")
        result = convert_usd("-1", "JPY", "100", pin=pin, group=group, money_scale=8)
        self.assertEqual(result["usdRounded"], "-0.33333333")
        self.assertEqual(Fraction(int(result["usdExact"]["numerator"]), int(result["usdExact"]["denominator"])), Fraction(-1, 3))

    def test_missing_future_stale_and_age_boundary(self):
        pin, group = fixture()
        for now, code in (("99", "FUTURE"), ("111", "STALE")):
            with self.assertRaisesRegex(ValueError, code): convert_usd("1", "JPY", now, pin=pin, group=group)
        self.assertEqual(convert_usd("1", "JPY", "110", pin=pin, group=group)["usdRounded"], "0.25")
        with self.assertRaisesRegex(ValueError, "MISSING"): convert_usd("1", "JPY", "100")
        for age in ("0", "60000000001", 10, "01"):
            with self.assertRaises(ValueError): convert_usd("1", "JPY", "100", pin=dict(pin, maxAgeNs=age), group=group)

    def test_quality_cannot_be_promoted_by_recent_timestamp(self):
        for field, value in (("freshness", "UNKNOWN"), ("freshness", "STALE"), ("gapBefore", "UNKNOWN_SILENCE"), ("gapBefore", "MISSING_DATA")):
            pin, group = fixture()
            group["events"][0]["quality"][field] = value
            with self.assertRaisesRegex(ValueError, "QUALITY"): convert_usd("1", "JPY", "100", pin=pin, group=group)
        pin, group = fixture(bid="5", ask="4")
        group["events"][0]["quality"]["quote"] = "CROSSED"
        with self.assertRaisesRegex(ValueError, "QUALITY"): convert_usd("1", "JPY", "100", pin=pin, group=group)

    def test_equal_time_distinct_prices_ambiguous_even_with_sequence(self):
        for trusted in (False, True):
            pin, group = fixture(count=2)
            group["events"][1]["bid"] = "3"
            if trusted:
                for i, row in enumerate(group["events"]): row["trustedSequence"] = str(i)
            group = make_group(group["events"], VERSION)
            with self.assertRaisesRegex(ValueError, "AMBIGUOUS"): convert_usd("1", "JPY", "100", pin=pin, group=group)

    def test_equivalent_ties_retain_every_ref_and_do_not_mutate_inputs(self):
        pin, group = fixture(count=2)
        before = deepcopy((pin, group))
        result = convert_usd("1", "JPY", "100", pin=pin, group=group)
        self.assertEqual((pin, group), before)
        self.assertEqual(len(result["evidence"]["events"]), 2)
        self.assertEqual(result["evidence"]["order"], "UNTRUSTED")
        result["evidence"]["pin"]["feedId"] = "mutated"
        result["evidence"]["events"][0]["provenance"]["sourceId"] = "mutated"
        self.assertEqual((pin, group), before)

    def test_identity_group_integrity_and_unsupported_inputs_refused(self):
        pin, group = fixture()
        for field, value in (("datasetVersion", "d" * 64), ("datasetId", "foreign"), ("feedId", "foreign"), ("providerId", "foreign"), ("feedInstrumentId", "foreign")):
            with self.subTest(field=field), self.assertRaises(ValueError):
                convert_usd("1", "JPY", "100", pin=dict(pin, **{field: value}), group=group)
        for change in (dict(groupId="f" * 64), dict(order="TRUSTED_SEQUENCE"), dict(events=[]), dict(timeNs="101")):
            with self.assertRaises(ValueError): convert_usd("1", "JPY", "110", pin=pin, group=dict(group, **change))
        duplicate = make_group(group["events"] * 2, VERSION)
        with self.assertRaisesRegex(ValueError, "GROUP"): convert_usd("1", "JPY", "100", pin=pin, group=duplicate)
        for currency in ("EUR", "jpy", None):
            with self.assertRaises(ValueError): convert_usd("1", currency, "100")
        with self.assertRaises(ValueError): convert_usd("1", "JPY", "100", pin=dict(pin, symbol="GBPUSD"), group=group)
        for scale in (True, -1, 9):
            with self.assertRaises(ValueError): convert_usd("1", "USD", "100", money_scale=scale)


if __name__ == "__main__": unittest.main()
