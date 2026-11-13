"""Differential test: the optimized canonical walk must equal the original reference exactly.

The reference below is a verbatim copy of the pre-optimization ``_normalize``. For every input
(valid or not) the output, the exception (code and field) and the remaining node budget must match.
"""
import random
import unittest
from collections import OrderedDict
from collections.abc import Mapping
from datetime import datetime, timezone
from decimal import Decimal

from contracts import canonical
from contracts.canonical import _normalize, canonical_bytes, decimal_text, utc_text
from contracts.primitives import ContractError, require


def _ref_text(value):
    require(len(value) <= 65536 and (value.isascii() or not any(0xD800 <= ord(c) <= 0xDFFF for c in value)), "unicode")
    return value


def _ref_normalize(value, depth=0, budget=None):
    if budget is None:
        budget = [canonical.NORMALIZATION_NODE_LIMIT]
    budget[0] -= 1
    require(budget[0] >= 0, "nodeBudget")
    require(depth <= 32, "depth")
    if value is None or type(value) is bool:
        return value
    if type(value) is str:
        return _ref_text(value)
    if type(value) is int:
        require(abs(value) <= 2**53 - 1, "integer")
        return value
    if type(value) is Decimal:
        return decimal_text(value)
    if type(value) is datetime:
        return utc_text(value)
    if isinstance(value, Mapping):
        require(len(value) <= 4096 and all(type(k) is str for k in value), "object")
        return {_ref_text(k): _ref_normalize(v, depth + 1, budget) for k, v in value.items()}
    if type(value) in (list, tuple):
        require(len(value) <= 4096, "array")
        return [_ref_normalize(v, depth + 1, budget) for v in value]
    require(False, "unsupportedType")


class _StrSub(str):
    pass


class _ListSub(list):
    pass


class _IntSub(int):
    pass


def _leaf(rnd):
    return rnd.choice([
        None, True, False, 0, 1, -7, 2**53 - 1, 2**53, -(2**53), "", "abc", "é漢", "x" * 65536, "x" * 65537,
        "\ud800", "a\udfffb", Decimal("1.50"), Decimal("0"), Decimal("1E+3"),
        datetime(2024, 1, 2, 3, 4, 5, 6, tzinfo=timezone.utc), 1.5, b"raw", _StrSub("sub"), _IntSub(3),
        object(), float("nan"), {1, 2},
    ])


def _tree(rnd, depth=0):
    r = rnd.random()
    if depth > 5 or r < 0.35:
        return _leaf(rnd)
    if r < 0.7:
        keys = [rnd.choice(["a", "b", "c", "d", "é", "k" * 5, "\ud800", 5, None, _StrSub("s")]) for _ in range(rnd.randint(0, 6))]
        mapping = {k: _tree(rnd, depth + 1) for k in keys}
        return OrderedDict(mapping) if rnd.random() < 0.1 else mapping
    items = [_tree(rnd, depth + 1) for _ in range(rnd.randint(0, 6))]
    pick = rnd.random()
    return tuple(items) if pick < 0.2 else _ListSub(items) if pick < 0.3 else items


def _run(fn, value, budget_size):
    budget = [budget_size]
    try:
        return ("ok", fn(value, 0, budget), budget[0])
    except ContractError as error:
        return ("err", (error.code, error.field), budget[0])


class CanonicalFastPathTests(unittest.TestCase):
    def test_random_trees_match_reference(self):
        rnd = random.Random(20261113)
        for i in range(6000):
            value = _tree(rnd)
            size = rnd.choice([16384, 40, 12, 5, 1])
            ref, new = _run(_ref_normalize, value, size), _run(_normalize, value, size)
            self.assertEqual(ref, new, f"case {i}: {value!r}")

    def test_depth_and_budget_limits_match_reference(self):
        deep = cur = []
        for _ in range(40):
            nxt = []
            cur.append(nxt)
            cur = nxt
        wide = {"k%d" % i: i for i in range(4096)}
        too_wide = {"k%d" % i: i for i in range(4097)}
        big_list = list(range(4097))
        for value in (deep, wide, too_wide, big_list, [wide] * 5):
            for size in (16384, 100, 3):
                self.assertEqual(_run(_ref_normalize, value, size), _run(_normalize, value, size))

    def test_canonical_bytes_unchanged_for_realistic_tick_group(self):
        group = dict(schemaVersion=1, artifact="BTL-TICK-CHUNK-1", datasetId="d", chunkIndex="0", events=[
            dict(eventId="e%d" % i, timeNs=str(1_000 + i), bid="1.0001", ask="1.0003", rawOrdinal=str(i),
                 trustedSequence=None, provenance=dict(sourceId="s", originalTimestamp="x"),
                 quality=dict(evidenceHash=None, quote="VALID", duplicateOf=None)) for i in range(50)])
        import json
        expected = json.dumps(_ref_normalize(group), sort_keys=True, ensure_ascii=False,
                              separators=(",", ":"), allow_nan=False).encode("utf-8")
        self.assertEqual(canonical_bytes(group), expected)


if __name__ == "__main__":
    unittest.main()
