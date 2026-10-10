"""Actual disk/runtime 42.19 tests; all prices/records are authored synthetic."""
from copy import deepcopy
import json
import hashlib
import unittest

from ticks.evidence_v2 import WINDOW_NS
from ticks.contracts_v2 import ZERO_VERSION, canonical_v2_bytes
from ticks.provider import SyntheticTickProvider, Cancellation
from ticks.storage_v2 import DatasetBuilder, DiskTickProvider
from ticks.timeline_v2 import IndexedTickTimeline
from tests import test_tick_storage_v2 as fixtures


class EvidenceV2Tests(unittest.TestCase):
    setUp = fixtures.TickStorageV2Tests.setUp
    tearDown = fixtures.TickStorageV2Tests.tearDown
    timeline = fixtures.TickStorageV2Tests.timeline
    def evidence_build(self, blocks=None, *, times=(100, 200, 200, 300), audit=None, folder="evidence"):
        # Ordinal 3 is an authored quarantined backdated source record; later
        # accepted ordinal 4 makes it fence-eligible without inventing a tick.
        raw = [dict(ordinal=str(i if i < 3 else i+1), timeNs=str(t), bid="2", ask="1", sequence=None) for i, t in enumerate(times)]
        original = {row["ordinal"]: row for row in raw}
        if len(raw) >= 4:
            original["3"] = dict(ordinal="3", timeNs="150", bid="2", ask="1", sequence=None)
        raw_hash = lambda row: hashlib.sha256(json.dumps(row, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        diagnostic_input = [] if "3" not in original else [dict(sourceId="authored", memberHash=ZERO_VERSION, rawOrdinal="3", timeNs="150", code="CROSSED_QUOTE", rawRecordHash=raw_hash(original["3"]))]
        p = SyntheticTickProvider(raw, diagnostics=diagnostic_input)
        m = p.describe(p.dataset_id, p.dataset_version)
        meta = {k: m[k] for k in ("datasetId", "providerId", "feedId", "instrumentId", "providerSymbol", "evidenceClass", "adapterVersion", "validatorVersion", "ordering")}
        b = DatasetBuilder(self.path/folder, meta, m["sources"], {"authored": True}, packing=(1, 1, 1))
        self.resources.append(b.store)
        for row in p.read_page(p.dataset_id, p.dataset_version, None, 32)["events"]:
            b.append(dict(row, datasetVersion=ZERO_VERSION))
        source = m["sources"][0]
        def record(ordinal, time, code="CROSSED_QUOTE"):
            return dict(sourceId=source["sourceId"], memberHash=source["memberHash"], rawOrdinal=str(ordinal), timeNs=str(time), code=code, rawRecordHash=raw_hash(original[str(ordinal)]))
        def block(i, coverage=None, gaps=None, diagnostics=None):
            return dict(artifact="BTL-TICK-EVIDENCE-BLOCK-2", blockIndex=str(i), coverage=coverage or [], gaps=gaps or [], diagnostics=diagnostics or [], rights=dict(**{"class": "SYNTHETIC", "evidenceHash": None}))
        bodies = blocks(block, record) if blocks is not None else [block(0, gaps=[dict(startNs="150", endNs="250", kind="MISSING_DATA", evidenceHash="b"*64)], diagnostics=[record(0,100),record(2,200),record(3,150),record(4,300,"SUSPECT_REPEAT")])]
        # Explicit fixture adapter audit: only exact authored original records
        # can pass; altered raw-record hash/ordinal/code fails.
        expected = {(r["sourceId"],r["rawOrdinal"],r["code"]): deepcopy(r) for body in bodies for r in body["diagnostics"]}
        def verify_original(r):
            row = original.get(r["rawOrdinal"])
            return (expected.get((r["sourceId"],r["rawOrdinal"],r["code"])) == r and row is not None
                    and row["timeNs"] == r["timeNs"] and raw_hash(row) == r["rawRecordHash"]
                    and (r["code"] != "CROSSED_QUOTE" or int(row["ask"]) < int(row["bid"])))
        verifier = audit or verify_original
        version = b.finish(evidence_blocks=iter(bodies), audit_record=verifier)
        provider = DiskTickProvider(self.path/folder, version)
        self.resources.append(provider)
        return b, provider, source

    def request(self, p, source, *, low="0", high="200", ordinal="2", quota=128, cursor=None):
        return dict(schemaVersion=2, artifact="BTL-TICK-EVIDENCE-REQUEST-2", datasetId=p.dataset_id, datasetVersion=p.dataset_version,
                    manifestHash=p.dataset_version, sessionStartNs="0", fromNs=low, throughNs=high,
                    sourceFence=[] if ordinal is None else [dict(sourceId=source["sourceId"], rawOrdinal=ordinal)], maxRecords=quota, cursor=cursor)

    def test_nonempty_gap_private_unknown_and_bounded_fenced_pagination(self):
        _, p, source = self.evidence_build()
        req = self.request(p, source, quota=1)
        first = p.read_evidence_v2(req)
        self.assertEqual(first["coverage"], [dict(startNs="0", endNs="200", status="UNKNOWN", evidenceHash=None)])
        self.assertEqual(first["diagnostics"]["records"], [])
        self.assertIsNotNone(first["nextCursor"])
        rows = []
        while first["nextCursor"] is not None:
            req["cursor"] = first["nextCursor"]
            first = p.read_evidence_v2(req)
            self.assertEqual(first["coverage"], [])
            self.assertEqual(first, p.read_evidence_v2(deepcopy(req)))
            rows.extend(first["diagnostics"]["records"])
        self.assertEqual([r["rawOrdinal"] for r in rows], ["0", "2"])
        backdated = p.read_evidence_v2(self.request(p, source, low="200", high="300", ordinal="3"))
        self.assertEqual([r["rawOrdinal"] for r in backdated["diagnostics"]["records"]], ["0", "2", "3"])
        first["diagnostics"]["records"].clear()
        self.assertTrue(p.read_evidence_v2(self.request(p, source))["diagnostics"]["records"])

    def test_no_fence_before_first_after_last_zero_width_and_long_target(self):
        _, p, source = self.evidence_build()
        for low, high in (("0","50"),("300","900"),("200","200")):
            result = p.read_evidence_v2(self.request(p, source, low=low, high=high, ordinal=None))
            self.assertEqual(result["diagnostics"]["records"], [])
            self.assertEqual(len(result["coverage"]), int(low != high))
        t = self.timeline(p, folder="long")
        r = t.advance_through(str(WINDOW_NS*2+100), t.cursor)
        self.assertEqual(r["throughNs"], str(WINDOW_NS*2+100))
        self.assertEqual(r["coverage"][0]["endNs"], r["throughNs"])
        self.assertNotIn("endOfDataset", r)

    def test_exact_tie_fence_backdated_dedup_reset_resume(self):
        _, p, _ = self.evidence_build()
        t = self.timeline(p, folder="atomic")
        first = t.advance_through("200", t.cursor)
        self.assertEqual([len(g["events"]) for g in first["groups"]], [1,2])
        self.assertEqual([r["rawOrdinal"] for r in first["diagnostics"]["records"]], ["0","2"])
        checkpoint = t.checkpoint()
        resumed = IndexedTickTimeline.resume(p, checkpoint, log_folder=self.path/"atomic")
        self.resources.append(resumed)
        a = t.advance_through("300", t.cursor)
        b = resumed.advance_through("300", resumed.cursor)
        self.assertEqual(a, b)
        self.assertEqual([r["rawOrdinal"] for r in a["diagnostics"]["records"]], ["3"])
        self.assertEqual(t.advance_through("300", t.cursor)["diagnostics"]["records"], [])
        view = t.consumer()
        for name in ("provider", "manifest", "read_evidence_v2", "locate_v2", "checkpoint", "endOfDataset"):
            self.assertFalse(hasattr(view, name))
        t.reset()
        with self.assertRaises(ValueError):view.cursor
        self.assertEqual(t.advance_through("200", t.cursor)["diagnostics"], first["diagnostics"])

    def test_cancellation_after_metadata_rolls_back_fence_dedup_and_logs(self):
        _, p, _ = self.evidence_build()
        class Proxy:
            callback = None
            dataset_id = p.dataset_id
            dataset_version = p.dataset_version
            def describe_v2(self,*a):return p.describe_v2(*a)
            def locate_v2(self,*a):return p.locate_v2(*a)
            def read_page_v2(self,*a):return p.read_page_v2(*a)
            def read_evidence_v2(self,r):
                result=p.read_evidence_v2(r)
                if self.callback:self.callback()
                return result
        proxy=Proxy();t=self.timeline(proxy,folder="cancel")
        original=t.checkpoint();proxy.callback=t.cancel
        with self.assertRaisesRegex(ValueError,"CANCELLED"):t.advance_through("200",t.cursor)
        self.assertEqual(t.checkpoint(),original)
        proxy.callback=None
        self.assertEqual(len(t.advance_through("200",t.cursor)["diagnostics"]["records"]),2)

    def test_invalid_request_cursor_schema_query_binding(self):
        _,p,source=self.evidence_build()
        request=self.request(p,source,quota=1)
        token=p.read_evidence_v2(request)["nextCursor"]
        for bad in (dict(request,maxRecords=True),dict(request,maxRecords=129),dict(request,throughNs=str(WINDOW_NS+1)),
                    dict(request,cursor=dict(token,entryOffset="128")),dict(request,cursor=token,throughNs="201"),
                    dict(request,sourceFence=[request["sourceFence"][0]]*2),dict(request,extra=True)):
            with self.assertRaises(ValueError):p.read_evidence_v2(bad)

    def test_unused_cross_block_conflict_and_original_record_audit_reject_publication(self):
        def conflict(block,record):
            return [block(0,coverage=[dict(startNs="100",endNs="220",status="DECLARED_COMPLETE",evidenceHash="a"*64)]),
                    block(1,gaps=[dict(startNs="150",endNs="250",kind="MISSING_DATA",evidenceHash="b"*64)])]
        with self.assertRaisesRegex(ValueError,"COVERAGE_CONFLICT"):self.evidence_build(conflict,folder="conflict")
        with self.assertRaisesRegex(ValueError,"INCOMPLETE_DIAGNOSTICS"):self.evidence_build(audit=lambda _:False,folder="audit")

    def test_missing_corrupted_unused_sidecar_fails_query(self):
        b,p,source=self.evidence_build()
        root=p.describe_v2(p.dataset_id,p.dataset_version)["root"]
        cat=b.store.get(root["evidenceCatalogHash"],p.dataset_version)
        b.store.db.execute("DELETE FROM objects WHERE hash=?",(cat["children"][0]["hash"],));b.store.db.commit()
        with self.assertRaisesRegex(ValueError,"MISSING_CHILD"):p.read_evidence_v2(self.request(p,source,high="50",ordinal=None))

    def test_quarantined_crossed_quote_requires_located_missing_data(self):
        for name, gaps in (("absent", []), ("unknown", [dict(startNs="150", endNs="250", kind="UNKNOWN_SILENCE", evidenceHash=None)]),
                           ("exclusive", [dict(startNs="100", endNs="150", kind="MISSING_DATA", evidenceHash="b"*64)])):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "INCOMPLETE_DIAGNOSTICS"):
                self.evidence_build(lambda block, record: [block(0, gaps=gaps, diagnostics=[record(3,150)])], folder=name)
            failed = self.resources[-1]
            self.assertEqual(failed.db.execute("SELECT COUNT(*) FROM publications").fetchone()[0], 0)
        # The gap may live in another block. It stays private; live coverage
        # remains uniformly UNKNOWN and cannot reveal the quarantined boundary.
        _, p, s = self.evidence_build(lambda block, record: [block(0, diagnostics=[record(3,150)]),
            block(1, gaps=[dict(startNs="150", endNs="151", kind="MISSING_DATA", evidenceHash="b"*64)])], folder="located")
        page = p.read_evidence_v2(self.request(p,s,high="300",ordinal="4"))
        self.assertEqual(page["coverage"], [dict(startNs="0",endNs="300",status="UNKNOWN",evidenceHash=None)])
        self.assertEqual([r["rawOrdinal"] for r in page["diagnostics"]["records"]], ["3"])

    def test_retained_crossed_quotes_do_not_invent_missing_data(self):
        _, p, s = self.evidence_build(lambda block, record: [block(0, diagnostics=[record(0,100),record(2,200)])], folder="retained")
        page = p.read_evidence_v2(self.request(p,s))
        self.assertEqual([r["rawOrdinal"] for r in page["diagnostics"]["records"]], ["0","2"])

    def test_quarantined_noncausal_reversal_requires_private_gap(self):
        with self.assertRaisesRegex(ValueError,"INCOMPLETE_DIAGNOSTICS"):
            self.evidence_build(lambda block,record:[block(0,diagnostics=[record(3,150,"ORDER_REVERSAL")])],folder="reversal-hole")
        _,p,s=self.evidence_build(lambda block,record:[block(0,diagnostics=[record(3,150,"ORDER_REVERSAL")],
            gaps=[dict(startNs="150",endNs="151",kind="MISSING_DATA",evidenceHash="b"*64)])],folder="reversal-gap")
        page=p.read_evidence_v2(self.request(p,s,high="300",ordinal="4"))
        self.assertEqual(page["diagnostics"]["records"],[])
        self.assertEqual(page["coverage"],[dict(startNs="0",endNs="300",status="UNKNOWN",evidenceHash=None)])

    def test_rights_only_empty_multiblock_limits_and_deterministic_identity(self):
        def bodies(block,record):return [block(i) for i in range(256)]
        _,p,s=self.evidence_build(bodies,folder="rights")
        self.assertEqual(p.read_evidence_v2(self.request(p,s))["diagnostics"]["records"],[])
        with self.assertRaisesRegex(ValueError,"EVIDENCE_LIMIT"):
            self.evidence_build(lambda block,record:[block(i) for i in range(257)],folder="overflow")
        _,again,_=self.evidence_build(bodies,folder="repeat")
        self.assertEqual(p.dataset_version,again.dataset_version)

    def test_full_32768_interval_capacity_streams_and_never_projects_endpoints(self):
        def bodies(block,record):
            return [block(i,coverage=[dict(startNs=str(100+i*128+j),endNs=str(101+i*128+j),status="UNKNOWN",evidenceHash=None) for j in range(128)]) for i in range(256)]
        _,p,s=self.evidence_build(bodies,times=(100,70000),folder="capacity")
        page=p.read_evidence_v2(self.request(p,s,ordinal=None,high="200"))
        self.assertEqual(page["coverage"],[dict(startNs="0",endNs="200",status="UNKNOWN",evidenceHash=None)])
        self.assertIsNone(page["nextCursor"])
        self.assertEqual(page["diagnostics"]["records"],[])

    def test_tick_page_duplicates_match_sidecar_without_double_delivery(self):
        _,p,s=self.evidence_build()
        records=p.read_evidence_v2(self.request(p,s,high="300",ordinal="4"))["diagnostics"]["records"]
        class Proxy:
            dataset_id=p.dataset_id
            dataset_version=p.dataset_version
            corrupt=False
            def describe_v2(self,*a):return p.describe_v2(*a)
            def locate_v2(self,*a):return p.locate_v2(*a)
            def read_evidence_v2(self,*a):return p.read_evidence_v2(*a)
            def read_page_v2(self,*a):
                page=p.read_page_v2(*a);copied=deepcopy(records)
                if self.corrupt:copied[0]["rawRecordHash"]="f"*64
                from ticks.provider import diagnostic_counts
                page["diagnostics"]=dict(records=copied,counts=diagnostic_counts(copied),truncated=False)
                return page
        proxy=Proxy();t=self.timeline(proxy,folder="duplicate")
        self.assertEqual(len(t.advance_through("200",t.cursor)["diagnostics"]["records"]),2)
        self.assertEqual(len(t.advance_through("300",t.cursor)["diagnostics"]["records"]),1)
        proxy.corrupt=True;t=self.timeline(proxy,folder="forged")
        before=t.checkpoint()
        with self.assertRaises(ValueError):t.advance_through("200",t.cursor)
        self.assertEqual(t.checkpoint(),before)


if __name__ == "__main__":unittest.main()
