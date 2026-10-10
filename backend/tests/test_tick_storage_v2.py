"""Small disk/runtime fixtures; no real-provider dataset needed in CI."""
from copy import deepcopy
from contextlib import closing
from pathlib import Path
import json
import sqlite3
import tempfile
import unittest
import zlib

from contracts.canonical import content_hash
from ticks.contracts_v2 import (canonical_v2_bytes, content_hash_v2, validate_root, hash_v2, shape, ZERO_VERSION)
from ticks.provider import SyntheticTickProvider, Cancellation
from ticks.storage_v2 import DatasetBuilder, DiskTickProvider, ArtifactStore
from ticks.timeline_v2 import IndexedTickTimeline
from ticks.exness_v2 import ExnessIngestion
from contracts.canonical import _text


def pump(t, target):
    groups = []
    while True:
        r = t.advance_through(str(target), t.cursor)
        groups.extend(r["groups"])
        if r["exhaustedThroughBoundary"]:
            return groups


class TickStorageV2Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)
        self.resources = []

    def tearDown(self):
        for r in reversed(self.resources):
            try:
                r.close()
            except sqlite3.ProgrammingError:
                pass
        self.tmp.cleanup()

    def build(self, times=(100, 200, 200, 200, 300, 400), *, packing=(2, 1, 1), folder="data"):
        raw = [dict(ordinal=str(i), timeNs=str(t), bid="1.001", ask="1.003", sequence=None) for i, t in enumerate(times)]
        p = SyntheticTickProvider(raw)
        m = p.describe(p.dataset_id, p.dataset_version)
        meta = {k: m[k] for k in ("datasetId", "providerId", "feedId", "instrumentId", "providerSymbol", "evidenceClass", "adapterVersion", "validatorVersion", "ordering")}
        b = DatasetBuilder(self.path/folder, meta, m["sources"], {"fixture": True}, packing=packing)
        self.resources.append(b.store)
        token = None
        while True:
            page = p.read_page(p.dataset_id, p.dataset_version, token, 32)
            for row in page["events"]:
                b.append(dict(row, datasetVersion=ZERO_VERSION))
            if page["endOfDataset"]:
                break
            token = page["nextToken"]
        version = b.finish()
        provider = DiskTickProvider(self.path/folder, version)
        self.resources.append(provider)
        return b, provider

    def timeline(self, p, start="0", folder="logs"):
        t = IndexedTickTimeline(p, p.dataset_id, p.dataset_version, start, log_folder=self.path/folder)
        self.resources.append(t)
        return t

    def test_appended_tick_retains_independent_mutable_levels(self):
        p = SyntheticTickProvider([dict(ordinal="0", timeNs="100", bid="1", ask="1.1", sequence=None)])
        m = p.describe(p.dataset_id, p.dataset_version)
        meta = {k: m[k] for k in ("datasetId", "providerId", "feedId", "instrumentId", "providerSymbol", "evidenceClass", "adapterVersion", "validatorVersion", "ordering")}
        b = DatasetBuilder(self.path/"copy-isolation", meta, m["sources"], {}, packing=(256, 256, 1024))
        self.resources.append(b.store)
        row = dict(p.read_page(p.dataset_id, p.dataset_version, None, 1)["events"][0], datasetVersion=ZERO_VERSION)
        expected = deepcopy(row)
        b.append(row)
        row["bid"] = "9"
        row["provenance"]["originalTimestamp"] = "changed"
        row["quality"]["quote"] = "CROSSED"
        self.assertEqual(b.s["group"][0], expected)
        self.assertEqual(b.s["chunk"][0], expected)
        b.s["group"][0]["quality"]["quote"] = "CROSSED"
        b.s["group"][0]["provenance"]["originalTimestamp"] = "internal change"
        self.assertEqual(b.s["chunk"][0], expected)

    def test_hierarchy_cross_directory_atomic_group_and_untrusted(self):
        b, p = self.build()
        root = p.describe_v2(p.dataset_id, p.dataset_version)["root"]
        self.assertEqual(len(root["directories"]), 3)
        self.assertEqual(root["eventCount"], "6")
        t = self.timeline(p, "200")
        r = t.next_group(t.cursor)
        self.assertEqual([e["rawOrdinal"] for e in r["groups"][0]["events"]], ["1", "2", "3"])
        self.assertEqual(r["groups"][0]["order"], "UNTRUSTED")

    def test_chunk_and_partition_ties_atomic(self):
        for packing in ((2, 256, 1024), (2, 1, 1024)):
            _, p = self.build(packing=packing, folder=str(packing))
            t = self.timeline(p, folder="logs"+str(packing))
            groups = pump(t, 400)
            self.assertEqual([len(g["events"]) for g in groups], [1, 3, 1, 1])

    def test_index_before_exact_between_after_early_middle_late(self):
        _, p = self.build()
        for target, expected in ((0,"100"),(100,"100"),(150,"200"),(200,"200"),(201,"300"),(400,"400"),(401,None)):
            located = p.locate_v2(p.dataset_id, p.dataset_version, str(target))
            self.assertEqual(located["groupTimeNs"], expected)
            if expected is not None:
                page = p.read_page_v2(p.dataset_id, p.dataset_version, located["position"], 1)
                self.assertEqual(page["events"][0]["timeNs"], expected)

    def test_bounded_page_tokens_progress_and_determinism(self):
        _, p = self.build()
        position = p.locate_v2(p.dataset_id, p.dataset_version, "0")["position"]
        collected = []
        while position is not None:
            a = p.read_page_v2(p.dataset_id, p.dataset_version, position, 1)
            self.assertEqual(a, p.read_page_v2(p.dataset_id, p.dataset_version, position, 1))
            self.assertLessEqual(len(a["events"]), 1)
            collected.extend(a["events"]); position = a["nextPosition"]
        self.assertEqual(len(collected), 6)
        with self.assertRaises(ValueError):
            p.read_page_v2(p.dataset_id, p.dataset_version, None, 257)

    def test_wrong_dataset_version_and_pointer_fail_closed(self):
        _, p = self.build()
        with self.assertRaisesRegex(ValueError, "DATASET_MISMATCH"):
            p.locate_v2("foreign", p.dataset_version, "0")
        with self.assertRaisesRegex(ValueError, "VERSION_MISMATCH"):
            p.locate_v2(p.dataset_id, "f"*64, "0")
        pointer = p.locate_v2(p.dataset_id, p.dataset_version, "200")["position"]
        for field, value in (("globalOrdinal", "999"), ("eventOffset", "250"), ("manifestHash", "f"*64)):
            with self.assertRaises(ValueError):
                p.read_page_v2(p.dataset_id, p.dataset_version, dict(pointer, **{field:value}), 1)

    def test_disk_identity_duplicate_conflict_and_no_seen_ids_in_ram(self):
        b, _ = self.build()
        self.assertEqual(b.store.db.execute("SELECT COUNT(*) FROM identities").fetchone()[0], 6)
        self.assertNotIn("seen_ids", b.__dict__)
        p = SyntheticTickProvider([dict(ordinal="0", timeNs="100", bid="1", ask="1.1", sequence=None)])
        m = p.describe(p.dataset_id,p.dataset_version)
        meta = {k:m[k] for k in ("datasetId","providerId","feedId","instrumentId","providerSymbol","evidenceClass","adapterVersion","validatorVersion","ordering")}
        builder = DatasetBuilder(self.path/"duplicates",meta,m["sources"],{},packing=(2,1,1))
        self.resources.append(builder.store)
        row = dict(p.read_page(p.dataset_id,p.dataset_version,None,1)["events"][0],datasetVersion=ZERO_VERSION)
        builder.append(row)
        with self.assertRaisesRegex(ValueError,"DUPLICATE_DELIVERY"):
            builder.append(row)
        with self.assertRaisesRegex(ValueError,"IDENTITY_CONFLICT"):
            builder.append(dict(row,bid="1.01"))

    def test_partial_sequence_keeps_last_nonnull_comparator_across_missing_member(self):
        source = SyntheticTickProvider([dict(ordinal=str(i),timeNs="100",bid="1",ask="1.1",sequence=None) for i in range(3)])
        m = source.describe(source.dataset_id,source.dataset_version)
        meta = {k:m[k] for k in ("datasetId","providerId","feedId","instrumentId","providerSymbol","evidenceClass","adapterVersion","validatorVersion","ordering")}
        meta["ordering"] = dict(timestamps="VERIFIED_NONDECREASING",ties="UNTRUSTED",sequenceScope="synthetic:partial",sequenceEvidenceHash="a"*64)
        rows = source.read_page(source.dataset_id,source.dataset_version,None,3)["events"]
        for final in ("4","5","6"):
            with self.subTest(final=final):
                b = DatasetBuilder(self.path/("partial-sequence-"+final),meta,m["sources"],{},packing=(1,1,1))
                self.resources.append(b.store)
                for row, sequence in zip(rows[:2], ("5",None)):
                    b.append(dict(row,datasetVersion=ZERO_VERSION,trustedSequence=sequence))
                last = dict(rows[2],datasetVersion=ZERO_VERSION,trustedSequence=final)
                if final != "6":
                    with self.assertRaisesRegex(ValueError,"INVALID_TRUSTED_SEQUENCE"):b.append(last)
                    self.assertEqual(b.store.db.execute("SELECT COUNT(*) FROM publications").fetchone()[0],0)
                else:
                    b.append(last)
                    version=b.finish()
                    p=DiskTickProvider(self.path/("partial-sequence-"+final),version);self.resources.append(p)
                    t=self.timeline(p,folder="partial-sequence-log")
                    group=t.next_group(t.cursor)["groups"][0]
                    self.assertEqual(group["order"],"UNTRUSTED")
                    self.assertEqual([r["trustedSequence"] for r in group["events"]],["5",None,"6"])

    def test_corruption_and_missing_chunk_refused_on_fresh_open(self):
        b, p = self.build()
        version = p.dataset_version; p.close()
        row = b.store.db.execute("SELECT hash,body FROM objects WHERE kind='BTL-TICK-STORAGE-CHUNK-2' ORDER BY hash LIMIT 1").fetchone()
        for body in (row[1][:-2], zlib.compress(b'{}')):
            b.store.db.execute("UPDATE objects SET body=? WHERE hash=?",(body,row[0]));b.store.db.commit()
            reader = DiskTickProvider(self.path/"data",version);self.resources.append(reader)
            with self.assertRaises(ValueError):
                pump(self.timeline(reader,folder="corrupt"+str(len(body))),400)
        b.store.db.execute("DELETE FROM objects WHERE hash=?",(row[0],));b.store.db.commit()
        reader = DiskTickProvider(self.path/"data",version);self.resources.append(reader)
        with self.assertRaisesRegex(ValueError,"MISSING_CHILD"):
            pump(self.timeline(reader,folder="missing"),400)

    def test_incomplete_publication_rejected(self):
        store = ArtifactStore(self.path/"incomplete",create=True);self.resources.append(store)
        with self.assertRaisesRegex(ValueError,"INCOMPLETE_INGESTION"):
            DiskTickProvider(self.path/"incomplete","0"*64)

    def test_reset_seek_resume_and_checkpoint_tamper(self):
        _,p = self.build();t=self.timeline(p)
        pump(t,200); checkpoint=t.checkpoint()
        restored=IndexedTickTimeline.resume(p,checkpoint,log_folder=self.path/"logs");self.resources.append(restored)
        self.assertEqual(restored.cursor,t.cursor)
        self.assertEqual(pump(restored,400),pump(t,400))
        view=t.consumer();t.reset()
        with self.assertRaisesRegex(ValueError,"STALE_GENERATION"):
            view.read_revealed()
        t.seek("300")
        self.assertEqual([g["timeNs"] for g in t.read_revealed()], ["100","200","300"])
        bad=deepcopy(checkpoint);bad["cursor"]["visiblePrefixHash"]="f"*64
        with self.assertRaises(ValueError):
            IndexedTickTimeline.resume(p,bad,log_folder=self.path/"logs")

    def test_resume_refuses_missing_or_corrupt_original_position_chain(self):
        import json
        _, p = self.build()
        for case in ("missing-tip", "missing-ancestor", "corrupt-body", "absent-tip"):
            with self.subTest(case=case):
                t = self.timeline(p, folder=case)
                t.advance_through("100", t.cursor)
                first = t.checkpoint()["positionLogHash"]
                t.advance_through("200", t.cursor)
                checkpoint = t.checkpoint()
                with closing(sqlite3.connect(self.path/case/"timeline.sqlite")) as db, db:
                    if case.startswith("missing"):
                        removed = first if case == "missing-ancestor" else checkpoint["positionLogHash"]
                        db.execute("DELETE FROM blocks WHERE hash=?", (removed,))
                    elif case == "corrupt-body":
                        raw = db.execute("SELECT body FROM blocks WHERE hash=?", (checkpoint["positionLogHash"],)).fetchone()[0]
                        body = json.loads(raw)
                        body["records"][0]["groupId"] = "f"*64
                        db.execute("UPDATE blocks SET body=? WHERE hash=?", (canonical_v2_bytes(body), checkpoint["positionLogHash"]))
                    else:
                        checkpoint["positionLogHash"] = None
                with self.assertRaisesRegex(ValueError, "INCOMPLETE_INGESTION|IDENTITY_CONFLICT"):
                    IndexedTickTimeline.resume(p, checkpoint, log_folder=self.path/case)
                if case.startswith("missing"):
                    with closing(sqlite3.connect(self.path/case/"timeline.sqlite")) as db:
                        self.assertIsNone(db.execute("SELECT 1 FROM blocks WHERE hash=?", (removed,)).fetchone(),
                                          "Failed resume must not repair the missing acknowledged block")

    def test_cancellation_rolls_back_cursor_and_prefix(self):
        _,p=self.build();t=self.timeline(p)
        before=t.checkpoint();cancel=Cancellation(True)
        with self.assertRaisesRegex(ValueError,"CANCELLED"):
            t.advance_through("400",t.cursor,cancel)
        self.assertEqual(t.checkpoint(),before)
        self.assertEqual(len(pump(t,400)),4)

    def test_no_lookahead_revealed_view_and_dataset_replacement(self):
        _,p=self.build();t=self.timeline(p)
        view=t.consumer();self.assertEqual(view.read_revealed(),[])
        for field in ("provider","locate_v2","checkpoint","next_group","index","eof"):
            self.assertFalse(hasattr(view,field))
        pump(t,100);self.assertEqual([g["timeNs"] for g in view.read_revealed()],["100"])
        with self.assertRaisesRegex(ValueError,"UNREVEALED_INDEX"):
            view.read_revealed("2")
        replacement=t.replace_dataset(p,p.dataset_id,p.dataset_version,"300",log_folder=self.path/"replacement");self.resources.append(replacement)
        with self.assertRaises(ValueError):view.read_revealed()
        self.assertEqual(replacement.next_group(replacement.cursor)["groups"][0]["timeNs"],"300")

    def csv(self, name="sample.csv", rows=None):
        path=self.path/name
        path.write_text('"Exness","Symbol","Timestamp","Bid","Ask"\n'+''.join(rows or [
            '"exness","XAUUSDm","2015-08-10 00:00:00.000Z",1091.741,1092.166\n',
            '"exness","XAUUSDm","2015-08-10 00:00:01.000Z",1091.714,1092.147\n',
            '"exness","XAUUSDm","2015-08-10 00:00:01.000Z",1091.738,1092.168\n',
            '"exness","XAUUSDm","2015-08-10 00:00:03.000Z",1091.812,1092.224\n']),encoding="utf-8")
        return path

    def test_exness_exact_bidask_symbol_resolution_and_changing_spread(self):
        a=ExnessIngestion(self.csv(),self.path/"exness",packing=(2,1,1));self.resources.append(a.builder.store)
        report=a.run();self.assertEqual(report["acceptedRows"],4)
        self.assertEqual(report["maxGroupSize"],2);self.assertEqual(report["sameTimestampGroups"],1)
        p=DiskTickProvider(self.path/"exness",report["datasetVersion"]);self.resources.append(p)
        root=p.describe_v2(p.dataset_id,p.dataset_version)["root"];self.assertEqual(root["providerSymbol"],"XAUUSDm")
        rows=p.read_page_v2(p.dataset_id,p.dataset_version,p.locate_v2(p.dataset_id,p.dataset_version,root["range"]["startNs"])["position"],2)["events"]
        self.assertEqual(rows[0]["bid"],"1091.741");self.assertEqual(rows[0]["resolutionNs"],"1000000000")
        self.assertIsNone(rows[0]["trustedSequence"])
        self.assertNotEqual(report["spreadMin"],report["spreadMax"])

    def test_exness_interruption_restart_deterministic_publication(self):
        source=self.csv()
        first=ExnessIngestion(source,self.path/"resume",packing=(2,1,1))
        with self.assertRaises(InterruptedError):first.run(stop_after=3)
        first.builder.store.close()
        resumed=ExnessIngestion(source,self.path/"resume",resume=True,packing=(2,1,1));self.resources.append(resumed.builder.store)
        result=resumed.run()
        complete=ExnessIngestion(source,self.path/"complete",packing=(2,1,1));self.resources.append(complete.builder.store)
        reference=complete.run()
        self.assertEqual(result["datasetVersion"],reference["datasetVersion"])
        self.assertEqual(result["parsedRows"],reference["parsedRows"])

    def test_exness_malformed_nonfinite_nonpositive_and_subsecond_rejected(self):
        for i,(stamp,bid,ask) in enumerate((("bad","1","2"),("2015-08-10 00:00:00.000Z","NaN","2"),
                                          ("2015-08-10 00:00:00.000Z","0","2"),("2015-08-10 00:00:00.001Z","1","2"))):
            source=self.csv(f"bad{i}.csv",[f'"exness","XAUUSDm","{stamp}",{bid},{ask}\n'])
            a=ExnessIngestion(source,self.path/f"bad{i}");self.resources.append(a.builder.store)
            with self.assertRaises(ValueError):a.run()
            self.assertEqual(a.builder.store.db.execute("SELECT COUNT(*) FROM publications").fetchone()[0],0)

    def test_root_bounds_invalid_range_duplicate_descriptor_budget(self):
        _,p=self.build();root=p.describe_v2(p.dataset_id,p.dataset_version)["root"]
        for mutate in (lambda r:r["directories"].append(deepcopy(r["directories"][0])),
                       lambda r:r["range"].update(endNs="999"),lambda r:r["directories"].__imul__(257)):
            bad=deepcopy(root);mutate(bad)
            with self.assertRaises(ValueError):validate_root(bad)
        with self.assertRaises(ValueError):canonical_v2_bytes(dict(schemaVersion=2,artifact="test",rows=["x"]*4097))

    def test_ascii_fast_path_preserves_unicode_and_size_rejections(self):
        for value in ("", "ASCII", "é", "金", "😀", "x"*65536, "a\x00z"):
            self.assertEqual(_text(value),value)
        for value in ("x"*65537,"\ud800","\udfff","a\udabcx"):
            with self.assertRaises(ValueError):_text(value)

    def test_late_session_does_not_read_dataset_beginning(self):
        _,p=self.build(times=tuple(range(1,101)),packing=(8,4,4))
        class Observe:
            def __init__(self):self.minimum=None
            def describe_v2(self,*a):return p.describe_v2(*a)
            def locate_v2(self,*a):return p.locate_v2(*a)
            def read_evidence_v2(self,*a):return p.read_evidence_v2(*a)
            def read_page_v2(self,d,v,pos,n):
                current=int(pos['globalOrdinal']);self.minimum=current if self.minimum is None else min(self.minimum,current)
                return p.read_page_v2(d,v,pos,n)
        observed=Observe();t=IndexedTickTimeline(observed,p.dataset_id,p.dataset_version,"90",log_folder=self.path/"late");self.resources.append(t)
        groups=pump(t,95)
        self.assertEqual([g["timeNs"] for g in groups],[str(i) for i in range(90,96)])
        self.assertEqual(observed.minimum,89)

    def test_stale_corrupt_index_binding_and_missing_index(self):
        b,p=self.build();version=p.dataset_version;p.close()
        row=b.store.db.execute("SELECT binding FROM publications WHERE version=?",(version,)).fetchone()
        import json
        original=json.loads(row[0]);bad=dict(original,datasetVersion="f"*64)
        b.store.db.execute("UPDATE publications SET binding=? WHERE version=?",(canonical_v2_bytes(bad),version));b.store.db.commit()
        with self.assertRaisesRegex(ValueError,"VERSION_MISMATCH"):DiskTickProvider(self.path/"data",version)
        b.store.db.execute("UPDATE publications SET binding=? WHERE version=?",(row[0],version));b.store.db.commit()
        index_hash=json.loads(b.store.db.execute("SELECT root FROM publications WHERE version=?",(version,)).fetchone()[0])["indexContentHash"]
        b.store.db.execute("DELETE FROM objects WHERE hash=?",(index_hash,));b.store.db.commit()
        reader=DiskTickProvider(self.path/"data",version);self.resources.append(reader)
        with self.assertRaisesRegex(ValueError,"MISSING_CHILD"):reader.locate_v2(reader.dataset_id,version,"100")

    def test_corrupt_boundary_anchor_rejected_at_finalization(self):
        p=SyntheticTickProvider([dict(ordinal=str(i),timeNs=str(t),bid="1",ask="1.1",sequence=None) for i,t in enumerate((100,200,200))])
        m=p.describe(p.dataset_id,p.dataset_version);meta={k:m[k] for k in ("datasetId","providerId","feedId","instrumentId","providerSymbol","evidenceClass","adapterVersion","validatorVersion","ordering")}
        b=DatasetBuilder(self.path/"bad-anchor",meta,m["sources"],{},packing=(1,256,1024));self.resources.append(b.store)
        for row in p.read_page(p.dataset_id,p.dataset_version,None,4)["events"]:b.append(dict(row,datasetVersion=ZERO_VERSION))
        b.s["indexChunks"][2]["firstGroupStart"]["globalOrdinal"]="2"
        with self.assertRaisesRegex(ValueError,"CORRUPT_INDEX_POINTER"):b.finish()
        self.assertEqual(b.store.db.execute("SELECT COUNT(*) FROM publications").fetchone()[0],0)

    def test_callback_cancellation_and_reset_cannot_commit_old_generation(self):
        _,p=self.build()
        class Callback:
            def read_evidence_v2(self,*a):return p.read_evidence_v2(*a)
            callback=None
            def describe_v2(self,*a):return p.describe_v2(*a)
            def locate_v2(self,*a):return p.locate_v2(*a)
            def read_page_v2(self,*a):
                if self.callback:
                    callback,self.callback=self.callback,None;callback()
                return p.read_page_v2(*a)
        proxy=Callback();t=IndexedTickTimeline(proxy,p.dataset_id,p.dataset_version,log_folder=self.path/"race")
        self.resources.append(t);original=t.checkpoint();proxy.callback=t.cancel
        with self.assertRaisesRegex(ValueError,"CANCELLED"):t.advance_through("400",t.cursor)
        self.assertEqual(t.checkpoint(),original)
        proxy.callback=lambda:t.reset("300")
        with self.assertRaises(ValueError):t.advance_through("400",t.cursor)
        self.assertEqual(t.cursor["sessionStartNs"],"300")
        self.assertEqual([g["timeNs"] for g in pump(t,400)],["300","400"])

    def test_exness_global_quote_repeat_preserved_and_crossed_unknown(self):
        first='"exness","XAUUSDm","2015-08-10 00:00:00.000Z",2.001,1.999\n'
        source=self.csv("repeat.csv",[first,first])
        a=ExnessIngestion(source,self.path/"repeat",packing=(1,1,1));self.resources.append(a.builder.store)
        report=a.run();self.assertEqual(report["acceptedRows"],2);self.assertEqual(report["exactDuplicateSourceRecords"],1)
        self.assertEqual(report["crossedQuotes"],2)
        p=DiskTickProvider(self.path/"repeat",report["datasetVersion"]);self.resources.append(p)
        t=self.timeline(p,"1439164800000000000",folder="repeatlogs")
        group=t.next_group(t.cursor)["groups"][0];self.assertEqual(len(group["events"]),2)
        self.assertEqual(group["order"],"UNTRUSTED");self.assertEqual(group["events"][0]["quality"]["freshness"],"UNKNOWN")

    def test_nested_index_bounds_and_root_descriptor_lies_rejected(self):
        b,p=self.build()
        root=p.describe_v2(p.dataset_id,p.dataset_version)["root"]
        for field,value in (("eventCount","7"),("directories",root["directories"]+[root["directories"][0]])):
            with self.assertRaises(ValueError):validate_root(dict(root,**{field:value}))
        malformed=deepcopy(root);malformed["directories"][0]["lastNs"]="99"
        with self.assertRaises(ValueError):validate_root(malformed)
        ix=b.store.get(root["indexContentHash"],p.dataset_version)
        for rows in ([],ix["children"]*257):
            with self.assertRaises(ValueError):shape(dict(ix,children=rows))
        malformed=deepcopy(ix);malformed["children"][0]["lastNs"]="99"
        with self.assertRaises(ValueError):shape(malformed)
        with self.assertRaises(ValueError):canonical_v2_bytes(dict(schemaVersion=2,artifact="test",text="x"*1048576))

    def test_benchmark_resume_does_not_count_old_rows_as_new_throughput(self):
        from contextlib import redirect_stdout
        from io import StringIO
        from ticks.benchmark_v2 import benchmark
        source = self.csv(rows=[f'"exness","XAUUSDm","2015-01-01 00:00:{i//100:02}.000Z",1200.123,1200.234\n' for i in range(4200)])
        folder = self.path/"bench-resume"
        first = ExnessIngestion(source,folder/"dataset")
        try:
            with self.assertRaises(InterruptedError):first.run(stop_after=4100)
            self.assertEqual(first.builder.store.journal()["count"],4096)
        finally:
            first.builder.store.close()
        with redirect_stdout(StringIO()):
            result = benchmark(source,folder,self.path/"private-report.json",resume=True)
        self.assertEqual(result["status"],"COMPLETE")
        info=result["ingestion"]
        self.assertEqual((info["acceptedRows"],info["startingAcceptedRows"],info["processedRowsThisAttempt"]),(4200,4096,104))
        self.assertEqual(result["referenceScan"]["sourceRows"],4200)
        self.assertAlmostEqual(info["rowsPerSecond"]*info["thisAttemptSecondsIncludingSourceHash"],104)
        self.assertTrue(info["totalSecondsIncludingSourceHash"].startswith("NOT MEASURABLE"))

    def test_existing_benchmark_requires_matching_original_source_hash(self):
        from ticks.benchmark_v2 import benchmark
        source=self.csv()
        ingestion=ExnessIngestion(source,self.path/"bench-pin"/"dataset")
        try:result=ingestion.run()
        finally:ingestion.builder.store.close()
        source.write_bytes(source.read_bytes().replace(b'1091.741',b'1091.742'))
        with self.assertRaisesRegex(ValueError,"SOURCE_CHANGED"):
            benchmark(source,self.path/"bench-pin",self.path/"private-pin-report.json",existing_version=result["datasetVersion"])

    def test_finalization_cancellation_leaves_only_resumable_staging(self):
        p=SyntheticTickProvider([dict(ordinal="0",timeNs="100",bid="1",ask="1.1",sequence=None)])
        m=p.describe(p.dataset_id,p.dataset_version)
        meta={k:m[k] for k in ("datasetId","providerId","feedId","instrumentId","providerSymbol","evidenceClass","adapterVersion","validatorVersion","ordering")}
        b=DatasetBuilder(self.path/"cancel-final",meta,m["sources"],{});self.resources.append(b.store)
        b.append(dict(p.read_page(p.dataset_id,p.dataset_version,None,1)["events"][0],datasetVersion=ZERO_VERSION))
        class CancelDuringValidation:
            calls=0
            def check(self):
                self.calls+=1
                if self.calls==2:raise ValueError("CANCELLED")
        with self.assertRaisesRegex(ValueError,"CANCELLED"):b.finish(cancellation=CancelDuringValidation())
        self.assertEqual(b.store.db.execute("SELECT COUNT(*) FROM publications").fetchone()[0],0)
        b.store.close()
        resumed=DatasetBuilder(self.path/"cancel-final",meta,m["sources"],{},resume=True);self.resources.append(resumed.store)
        version=resumed.finish();reader=DiskTickProvider(self.path/"cancel-final",version);self.resources.append(reader)
        self.assertEqual(reader.describe_v2(reader.dataset_id,version)["root"]["eventCount"],"1")



class IncrementalCanonicalBudgetTests(unittest.TestCase):
    def test_exact_original_envelope_limits_and_failed_append_recovery(self):
        from ticks.contracts_v2 import CanonicalGroupBudget, canonical_v2_bytes
        cases = [
            [{'timeNs': str(i), 'events': [{'bid': '1100.001', 'quality': {'freshness': 'UNKNOWN'}}]*3} for i in range(100)],
            [{'text': 'a'*65000} for _ in range(18)],
            [{'nodes': [None]*1024} for _ in range(20)],
            [{'text': chr(0x1f600)*30000} for _ in range(12)],
            [{'text': chr(0xd800)}],
            [{'nested': [[[[[None]]]]]}],
            [{'bad': 1.25}],
        ]
        for artifact in ('BTL-TICK-STEP-CHECK-2', 'BTL-TICK-VIEW-CHECK-2'):
            for candidates in cases:
                packed = CanonicalGroupBudget(artifact)
                reference = []
                for candidate in candidates:
                    try:
                        expected = canonical_v2_bytes(dict(schemaVersion=2, artifact=artifact, groups=reference+[candidate]))
                    except ValueError:
                        with self.assertRaises(ValueError): packed.append(candidate)
                        self.assertEqual(packed.groups, reference)
                        # A refusal must not consume the remaining node budget.
                        small = {'timeNs': '0'}
                        try: canonical_v2_bytes(dict(schemaVersion=2, artifact=artifact, groups=reference+[small]))
                        except ValueError:
                            with self.assertRaises(ValueError): packed.append(small)
                        else:
                            packed.append(small);reference.append(small)
                    else:
                        packed.append(candidate);reference.append(candidate)
                        self.assertEqual(canonical_v2_bytes(dict(schemaVersion=2, artifact=artifact, groups=packed.groups)), expected)

    def test_envelope_depth_remains_part_of_the_limit(self):
        from ticks.contracts_v2 import CanonicalGroupBudget, canonical_v2_bytes
        value = None
        for _ in range(32): value = [value]
        envelope = dict(schemaVersion=2, artifact='BTL-TICK-STEP-CHECK-2', groups=[value])
        with self.assertRaises(ValueError): canonical_v2_bytes(envelope)
        packed = CanonicalGroupBudget(envelope['artifact'])
        with self.assertRaises(ValueError): packed.append(value)


class BenchmarkEvidenceTests(unittest.TestCase):
    def test_external_accepted_store_is_not_copied_and_failure_revokes_old_complete_report(self):
        from contextlib import redirect_stdout
        from io import StringIO
        from ticks.benchmark_v2 import benchmark
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            source = path/'source.csv'
            source.write_text('Exness,Symbol,Timestamp,Bid,Ask\n'+''.join(
                f'exness,XAUUSDm,2015-01-01 00:00:{i:02}.000Z,1200.123,1200.234\n' for i in range(3)), encoding='utf-8')
            store = path/'accepted'
            importer = ExnessIngestion(source, store)
            try: result = importer.run()
            finally: importer.builder.store.close()
            with redirect_stdout(StringIO()):
                measured = benchmark(source, path/'measurements', path/'report.json',
                                     existing_version=result['datasetVersion'], dataset_folder=store)
            self.assertEqual(measured['status'], 'COMPLETE')
            self.assertEqual(measured['referenceScan']['sourceRows'], 3)
            self.assertFalse((path/'measurements'/'dataset').exists())
            self.assertGreaterEqual(measured['totalOutputFootprintBytes'], measured['datasetFootprintBytes'])
            source.write_bytes(source.read_bytes()+b'exness,XAUUSDm,2015-01-01 00:00:03.000Z,1200.123,1200.234\n')
            with self.assertRaisesRegex(ValueError, 'SOURCE_CHANGED'):
                benchmark(source, path/'measurements', path/'report.json',
                          existing_version=result['datasetVersion'], dataset_folder=store)
            self.assertEqual(json.loads((path/'report.json').read_text(encoding='utf-8'))['status'], 'FAILED')


if __name__ == "__main__":unittest.main()
