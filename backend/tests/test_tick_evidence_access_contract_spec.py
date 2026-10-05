"""42.19 planning oracle only. No V2 runtime, filesystem ingestion or benchmark."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import unittest

from contracts.canonical import _normalize
from ticks.contracts import interval_rows

BLUEPRINT = Path(__file__).resolve().parents[2] / "docs/PRODUCT_SYSTEM_ARCHITECTURE_BLUEPRINT.md"


def fixture():
    text = BLUEPRINT.read_text(encoding="utf-8")
    marker = "<!-- BTL-TICK-EVIDENCE-ACCESS-FIXTURES-2 -->"
    assert text.count(marker) == 1
    return json.loads(re.search(r"```json\s*(.*?)\s*```", text.split(marker)[1], re.S)[1])


def encoded(obj):
    if type(obj.get("schemaVersion")) is not int or obj["schemaVersion"] != 2:
        raise ValueError("SCHEMA_MISMATCH")
    raw = json.dumps(_normalize(obj), sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()
    if len(raw) > 1048576:
        raise ValueError("ARTIFACT_LIMIT")
    return raw


def query_hash(request):
    return hashlib.sha256(encoded(dict(request, cursor=None))).hexdigest()


def projection(start, end, private_metadata=None):
    # Legacy declarations have no causal availability proof; deliberately do
    # not inspect private endpoints, classifications, totals or EOF here.
    return [] if start == end else [dict(startNs=str(start), endNs=str(end), status="UNKNOWN", evidenceHash=None)]


def eligible(record, session, through, fence, codes):
    return (record["code"] in codes and record["timeNs"] is not None
            and session <= int(record["timeNs"]) <= through
            and record["sourceId"] in fence
            and int(record["rawOrdinal"]) <= fence[record["sourceId"]])


def accept_intervals(blocks):
    """Tiny authored all-block example, not disk-bounded production validation."""
    if len(blocks) > 256:
        raise ValueError("EVIDENCE_LIMIT")
    coverage, gaps = [], []
    rights = None
    for i, block in enumerate(blocks):
        if block["blockIndex"] != str(i) or sum(len(block[k]) for k in ("coverage", "gaps", "diagnostics")) > 128:
            raise ValueError("EVIDENCE_LIMIT")
        if rights is not None and rights != block["rights"]:
            raise ValueError("IDENTITY_CONFLICT")
        rights = block["rights"]
        coverage.extend(block["coverage"])
        gaps.extend(block["gaps"])
    bounds = dict(startNs="0", endNs="1000")
    interval_rows(sorted(coverage, key=lambda r: int(r["startNs"])), bounds, "coverage")
    interval_rows(sorted(gaps, key=lambda r: int(r["startNs"])), bounds, "gaps")
    for c in coverage:
        for g in gaps:
            if c["status"] == "DECLARED_COMPLETE" and max(int(c["startNs"]), int(g["startNs"])) < min(int(c["endNs"]), int(g["endNs"])):
                raise ValueError("COVERAGE_CONFLICT")


class EvidenceAccessContractTests(unittest.TestCase):
    def test_single_owner_and_frozen_limits(self):
        f = fixture()
        self.assertEqual(f["limits"], dict(catalogBlocks=256, blockEntries=128, pageRecords=128,
                                         sourceFences=128, coverageWindowNs="86400000000000", bytes=1048576, cacheBytes=67108864))
        for key in ("requestFields", "pageFields"):
            self.assertEqual(len(f[key]), len(set(f[key])))
        encoded(f)

    def test_hidden_gap_end_kind_and_eof_do_not_change_projection(self):
        for case in fixture()["cases"]:
            a, b = int(case["fromNs"]), int(case["throughNs"])
            result = projection(a, b, case)
            changed = dict(case, gapEndNs="999", classification="KNOWN_SESSION_CLOSED", datasetEOF=True, futureGroups=999)
            self.assertEqual(result, projection(a, b, changed))
            self.assertEqual(bool(result), case["expected"] != "EMPTY")
            if result:
                self.assertEqual(result[0]["endNs"], case["throughNs"])
                self.assertEqual(result[0]["status"], "UNKNOWN")
                self.assertIsNone(result[0]["evidenceHash"])

    def test_backdated_future_ordinal_and_nonlocal_diagnostics_withheld(self):
        codes = fixture()["eligibleCodes"]
        record = dict(sourceId="s", rawOrdinal="4", timeNs="150", code="CROSSED_QUOTE")
        self.assertTrue(eligible(record, 100, 200, {"s": 4}, codes))
        for bad in (dict(record, rawOrdinal="5"), dict(record, timeNs="201"),
                    dict(record, timeNs=None), dict(record, timeNs="99"),
                    dict(record, sourceId="foreign"), dict(record, code="SUSPECT_REPEAT"),
                    dict(record, code="ORDER_REVERSAL")):
            self.assertFalse(eligible(bad, 100, 200, {"s": 4}, codes))
        self.assertFalse(eligible(record, 100, 200, {}, codes))

    def test_query_hash_binds_identity_window_fence_and_quota_not_page_cursor(self):
        r = dict(schemaVersion=2, artifact="BTL-TICK-EVIDENCE-REQUEST-2", datasetId="d", datasetVersion="a"*64,
                 manifestHash="a"*64, sessionStartNs="100", fromNs="100", throughNs="200",
                 sourceFence=[dict(sourceId="s", rawOrdinal="4")], maxRecords=128, cursor=None)
        self.assertEqual(set(r), set(fixture()["requestFields"]))
        self.assertEqual(query_hash(r), query_hash(dict(r, cursor={"private": "continuation"})))
        for field, value in (("datasetVersion", "b"*64), ("throughNs", "201"), ("sourceFence", []), ("maxRecords", 1)):
            self.assertNotEqual(query_hash(r), query_hash(dict(r, **{field: value})))

    def test_unused_block_overlap_and_rights_conflicts_reject(self):
        base = dict(blockIndex="0", coverage=[], gaps=[], diagnostics=[], rights={"class": "UNKNOWN", "evidenceHash": None})
        a = deepcopy(base)
        a["coverage"] = [dict(startNs="100", endNs="200", status="DECLARED_COMPLETE", evidenceHash="a"*64)]
        b = deepcopy(base); b["blockIndex"] = "1"
        b["gaps"] = [dict(startNs="150", endNs="160", kind="MISSING_DATA", evidenceHash="b"*64)]
        with self.assertRaisesRegex(ValueError, "COVERAGE_CONFLICT"):accept_intervals([a, b])
        b["gaps"] = []; b["rights"] = {"class": "PUBLIC_GRANTED", "evidenceHash": "b"*64}
        with self.assertRaisesRegex(ValueError, "IDENTITY_CONFLICT"):accept_intervals([a, b])
        accept_intervals([base])
        with self.assertRaises(ValueError):accept_intervals([base]*257)

    def test_canonical_budget_version_and_surrogate_fail_closed(self):
        for obj in (dict(schemaVersion=True), dict(schemaVersion=1),
                    dict(schemaVersion=2, text="x"*65537), dict(schemaVersion=2, text="\ud800")):
            with self.assertRaises(ValueError):encoded(obj)
        obj = dict(schemaVersion=2, fields=["x"*65536]*17)
        with self.assertRaises(ValueError):encoded(obj)


if __name__ == "__main__":
    unittest.main()
