"""SYNTHETIC / TEST ONLY; no result here is a market execution/fill."""
from copy import deepcopy
from decimal import Decimal
import unittest

from contracts.canonical import content_hash
from ticks.contracts import CanonicalTick, TickManifest, validate_chunk
from ticks.provider import SyntheticTickProvider, Cancellation, validate_provider
from ticks.timeline import TickTimeline
from tests.test_tick_contract_spec import fixture_matrix


def row(ordinal, time, bid="1", ask="1.1", sequence=None):
    return dict(ordinal=str(ordinal), timeNs=str(time), bid=bid, ask=ask, sequence=None if sequence is None else str(sequence))


def timeline(rows=None, **options):
    p = SyntheticTickProvider(rows or [row(0,100), row(1,200), row(2,300)], **options)
    return p, TickTimeline(p, p.dataset_id, p.dataset_version)


def pump(t, target):
    groups = []
    while True:
        result = t.advance_through(str(target), t.cursor)
        groups += result["groups"]
        if result["exhaustedThroughBoundary"]:
            return groups


class Proxy:
    """Only the public provider port, no Synthetic internals downstream."""
    def __init__(self, provider):
        self.provider, self.mutate, self.callback = provider, None, None
    def describe(self, dataset_id, version):
        return self.provider.describe(dataset_id, version)
    def read_page(self, dataset_id, version, token, maximum):
        if self.callback:
            self.callback()
        page = self.provider.read_page(dataset_id, version, token, min(maximum, 1))
        if self.mutate:
            self.mutate(page)
        return page


class TickTimelineTests(unittest.TestCase):
    def test_exact_decimal_ns_resolution_immutability_and_identity(self):
        rows = [row(0, 1700000000000000123, "1.123456789123456789", "1.12345678912345679")]
        p,t = timeline(rows)
        q = SyntheticTickProvider(rows)
        self.assertEqual(p.dataset_version, q.dataset_version)
        with self.assertRaises(AttributeError):p.dataset_version="0"*64
        initial_token=dict(schemaVersion=1,artifact="BTL-TICK-PAGE-TOKEN-1",datasetVersion=p.dataset_version,sourceIndex="0",afterRawOrdinal=None)
        self.assertEqual(p.read_page(p.dataset_id,p.dataset_version,initial_token,1),p.read_page(p.dataset_id,p.dataset_version,None,1))
        event = t.next_group(t.cursor)["groups"][0]["events"][0]
        tick = CanonicalTick.from_wire(event)
        self.assertEqual(tick.bid, Decimal(rows[0]["bid"]))
        self.assertEqual(tick.time_ns, 1700000000000000123)
        event["bid"] = "9"
        self.assertNotEqual(tick.wire["bid"], "9")
        with self.assertRaises(ValueError):
            timeline(rows, resolution_ns="1000")

    def test_invalid_manifest_and_strict_versions(self):
        p,t = timeline()
        good = p.describe(p.dataset_id, p.dataset_version)
        self.assertEqual(TickManifest.from_wire(good).version, p.dataset_version)
        mutations = [lambda m:m.update(schemaVersion=True), lambda m:m.update(extra=True),
                     lambda m:m["range"].update(endExclusive=False),
                     lambda m:m["sources"][0].update(resolutionNs="0"),
                     lambda m:m["ordering"].update(ties="TRUSTED_SEQUENCE")]
        for mutation in mutations:
            m=deepcopy(good); mutation(m)
            with self.assertRaises(ValueError): TickManifest.from_wire(m)
        with self.assertRaises(ValueError): TickManifest.from_wire(good, "0"*64)

    def test_chunk_checksum_identity_and_source_bounds(self):
        p,t = timeline(chunk_size=3)
        page=p.read_page(p.dataset_id,p.dataset_version,None,3)
        chunk=dict(schemaVersion=1,artifact="BTL-TICK-CHUNK-1",datasetId=p.dataset_id,datasetVersion=p.dataset_version,chunkIndex="0",events=page["events"])
        manifest=TickManifest.from_wire(p.describe(p.dataset_id,p.dataset_version))
        self.assertEqual(len(validate_chunk(chunk,manifest)),3)
        for field,value in (("datasetVersion","0"*64),("chunkIndex","9")):
            bad=deepcopy(chunk);bad[field]=value
            with self.assertRaises(ValueError):validate_chunk(bad,manifest)
        bad=deepcopy(chunk);bad["events"][0]["bid"]="9"
        with self.assertRaises(ValueError):validate_chunk(bad,manifest)

    def test_named_frozen_matrix(self):
        reject = {"duplicate_delivery", "timestamp_reversal"}
        for case in fixture_matrix()["cases"]:
            if "rows" not in case: continue
            with self.subTest(case=case["id"]):
                if case["id"] in reject:
                    with self.assertRaises(ValueError): timeline(case["rows"])
                else:
                    p,t=timeline(case["rows"],trusted=case["id"] in ("trusted_tie","ambiguous_activation"),gaps=[dict(**case["gap"],evidenceHash=None)] if "gap" in case else None)
                    groups=pump(t, max(int(r["timeNs"]) for r in case["rows"]))
                    self.assertEqual(sum(len(g["events"]) for g in groups),len(case["rows"]))
                    self.assertNotIn("fill",str(groups).lower())

    def test_atomic_trusted_and_untrusted_ties_across_pages_chunks(self):
        for trusted in (True,False):
            p = SyntheticTickProvider([row(0,100,sequence=9 if trusted else None),row(1,100,"2","2.1",10 if trusted else None),row(2,200,sequence=11 if trusted else None)],chunk_size=1,trusted=trusted)
            t=TickTimeline(Proxy(p),p.dataset_id,p.dataset_version)
            result=t.advance_through("100",t.cursor)
            self.assertEqual(len(result["groups"]),1)
            self.assertEqual(len(result["groups"][0]["events"]),2)
            self.assertEqual(result["groups"][0]["order"],"TRUSTED_SEQUENCE" if trusted else "UNTRUSTED")
            self.assertEqual(t.cursor["nextGroupIndex"],"1")

    def test_invalid_ordinal_sequence_duplicates_and_conflict(self):
        for rows in ([row(1,100),row(0,200)], [row(0,100,sequence=9),row(1,100,sequence=9)],
                     [row(0,100,sequence=10),row(1,100,sequence=9)], [row(0,100),row(0,200)],
                     [row(0,100,sequence=9),row(1,100,sequence=None)]):
            with self.assertRaises(ValueError):timeline(rows,trusted=True)
        with self.assertRaises(ValueError):timeline([row("01",100)])
        for rows,code in (([row(0,100),row(0,100)],"DUPLICATE_DELIVERY"),([row(0,100),row(0,200)],"IDENTITY_CONFLICT")):
            with self.assertRaises(ValueError) as caught:timeline(rows)
            self.assertEqual(caught.exception.code,code)

    def test_quote_quality_no_repair(self):
        rows=[row(0,100,None,"2"),row(1,200,"2",None),row(2,300,"3","2"),row(3,400,"1","1"),row(4,500,"1","1000000")]
        p,t=timeline(rows)
        events=[g["events"][0] for g in pump(t,500)]
        self.assertEqual([e["quality"]["quote"] for e in events],["MISSING_SIDE","MISSING_SIDE","CROSSED","VALID","VALID"])
        for bad in ("NaN","Infinity","0","-1","1e2",1.1):
            with self.assertRaises(ValueError):timeline([row(0,100,bad,"2")])

    def test_gap_clipping_and_no_future_metadata(self):
        p,t=timeline([row(0,100),row(1,500)],gaps=[dict(startNs="101",endNs="500",kind="UNKNOWN_SILENCE",evidenceHash=None)])
        result=t.advance_through("200",t.cursor)
        self.assertTrue(all(int(c["endNs"])<=200 for c in result["coverage"]))
        self.assertNotIn("endOfDataset",result)
        self.assertNotIn("chunks",result)
        self.assertEqual([g["timeNs"] for g in result["groups"]],["100"])

    def test_no_lookahead_read_capability_and_hostile_indices(self):
        p,t=timeline();v=t.consumer()
        self.assertEqual(v.read_revealed(),[])
        for name in ("advance_through","next_group","describe","read_page","seek","checkpoint"):
            self.assertFalse(hasattr(v,name))
        t.advance_through("100",t.cursor)
        self.assertEqual([g["timeNs"] for g in v.read_revealed()],["100"])
        with self.assertRaises(ValueError):v.read_revealed("2")
        copy=v.read_revealed();copy[0]["events"][0]["bid"]="9"
        self.assertEqual(v.read_revealed()[0]["events"][0]["bid"],"1")

    def test_future_suffix_under_same_pinned_identity(self):
        p,t=timeline();proxy=Proxy(p)
        second=TickTimeline(proxy,p.dataset_id,p.dataset_version)
        # Unrevealed consumer projections cannot inject a hypothetical suffix.
        first=t.advance_through("100",t.cursor)
        other=second.advance_through("100",second.cursor)
        self.assertEqual(first,other)
        private_future=p.read_page(p.dataset_id,p.dataset_version,None,3)["events"][-1]
        private_future["bid"]="999"
        self.assertEqual(second.consumer().read_revealed(),t.consumer().read_revealed())
        proxy.mutate=lambda page:page["events"][0].update(bid="999")
        saved=second.cursor
        # Already hash-validated buffered bytes remain immutable even if an
        # external backing store later corrupts; fresh ingestion must reject it.
        try:
            delta=second.advance_through("300",second.cursor)
            self.assertTrue(all(e["bid"]!="999" for g in delta["groups"] for e in g["events"]))
        except ValueError:
            self.assertEqual(second.cursor,saved)
        with self.assertRaises(ValueError):TickTimeline(proxy,p.dataset_id,p.dataset_version)

    def test_cursor_staleness_silence_noop_end_and_mismatch(self):
        p,t=timeline();initial=t.cursor
        t.advance_through("50",initial)
        self.assertNotEqual(t.cursor,initial)
        with self.assertRaises(ValueError):t.advance_through("60",initial)
        saved=t.cursor;t.advance_through("50",saved);self.assertEqual(t.cursor,saved)
        bad=t.cursor;bad["datasetVersion"]="0"*64
        with self.assertRaises(ValueError):t.advance_through("100",bad)
        pump(t,1000);saved=t.cursor;t.next_group(saved);self.assertEqual(t.cursor,saved)

    def test_seek_before_exact_between_ties_and_after_final(self):
        p,t=timeline([row(0,100),row(1,200),row(2,200),row(3,300)])
        for target,expected in ((50,[]),(100,["100"]),(150,["100"]),(200,["100","200"]),(999,["100","200","300"])):
            t.seek(str(target))
            self.assertEqual([g["timeNs"] for g in t.consumer().read_revealed()],expected)
        with self.assertRaises(ValueError):t.seek("-1")

    def test_reset_and_resume_equal_continuous(self):
        p,t=timeline();pump(t,200);checkpoint=t.checkpoint()
        r=TickTimeline.resume(p,checkpoint)
        self.assertEqual(r.cursor,t.cursor)
        self.assertEqual(pump(r,300),pump(t,300))
        view=t.consumer();before=view.read_revealed();old=t.cursor;t.reset()
        with self.assertRaises(ValueError):view.read_revealed()
        self.assertEqual(t.consumer().read_revealed(),[])
        self.assertNotEqual(t.cursor["generation"],old["generation"])
        pump(t,300);self.assertEqual(t.consumer().read_revealed(),before)
        bad=deepcopy(checkpoint);bad["cursor"]["nextGroupIndex"]="99"
        with self.assertRaises(ValueError):TickTimeline.resume(p,bad)
        p2=SyntheticTickProvider([row(0,100,"9","9.1")])
        with self.assertRaises(ValueError):TickTimeline.resume(p2,checkpoint)

    def test_cancellation_before_and_during_read(self):
        p,t=timeline();cancel=Cancellation(True);saved=t.cursor
        with self.assertRaises(ValueError):t.advance_through("300",saved,cancel)
        self.assertEqual(t.cursor,saved)
        proxy=Proxy(p);t=TickTimeline(proxy,p.dataset_id,p.dataset_version);cancel=Cancellation()
        proxy.callback=lambda:setattr(cancel,"cancelled",True)
        saved=t.cursor
        with self.assertRaises(ValueError):t.advance_through("300",saved,cancel)
        self.assertEqual(t.cursor,saved)
        proxy.callback=None;cancel.cancelled=False
        r=TickTimeline.resume(proxy,t.checkpoint())
        self.assertEqual(pump(r,300),pump(t,300))

    def test_bounded_steps_pending_target_checkpoint(self):
        rows=[row(i,100+i) for i in range(140)]
        p,t=timeline(rows,chunk_size=16)
        result=t.advance_through("1000",t.cursor)
        self.assertFalse(result["exhaustedThroughBoundary"])
        self.assertEqual(len(result["groups"]),64)
        with self.assertRaises(ValueError):t.advance_through("999",t.cursor)
        r=TickTimeline.resume(p,t.checkpoint())
        self.assertEqual(pump(r,1000),pump(t,1000))
        self.assertEqual(len(t.read_revealed("0",1024)),140)

    def test_mutated_provider_and_truncated_or_stalled_pages(self):
        p,t=timeline();proxy=Proxy(p)
        proxy.mutate=lambda page:page.update(datasetVersion="0"*64)
        with self.assertRaises(ValueError):TickTimeline(proxy,p.dataset_id,p.dataset_version)
        proxy.mutate=lambda page:page.update(endOfDataset=True,nextToken=None)
        with self.assertRaises(ValueError):TickTimeline(proxy,p.dataset_id,p.dataset_version)

    def test_located_diagnostics_hash_gap_and_reveal(self):
        diag=dict(sourceId="placeholder",memberHash="0"*64,rawOrdinal="1",timeNs="150",code="MALFORMED_PRICE",rawRecordHash=content_hash(dict(schemaVersion=1,artifact="SYNTHETIC-INVALID-1",bid="NaN")))
        proof=content_hash(dict(schemaVersion=1,artifact="SYNTHETIC-GAP-1",testOnly=True))
        p,t=timeline([row(0,100),row(2,200)],diagnostics=[diag],gaps=[dict(startNs="150",endNs="151",kind="MISSING_DATA",evidenceHash=proof)])
        first=t.advance_through("100",t.cursor)
        self.assertEqual(first["diagnostics"]["records"],[])
        second=t.advance_through("150",t.cursor)
        self.assertEqual(second["diagnostics"]["counts"],{"MALFORMED_PRICE":1})
        self.assertEqual(t.advance_through("200",t.cursor)["diagnostics"]["records"],[])
        self.assertEqual(TickTimeline.resume(p,t.checkpoint()).cursor,t.cursor)
        diag["timeNs"]=None
        with self.assertRaises(ValueError):timeline([row(0,100),row(2,200)],diagnostics=[diag])

    def test_oversized_atomic_group_rejected_without_partial_reveal(self):
        # Existing node budget is stricter than the nominal 1024-count ceiling.
        with self.assertRaises(ValueError):timeline([row(i,100) for i in range(1025)],chunk_size=64)

    def test_direct_construction_and_unlocated_diagnostic_rejection(self):
        with self.assertRaises(ValueError):CanonicalTick(b'{}')
        with self.assertRaises(ValueError):TickManifest(b'{}')
        p,t=timeline();bad=t.cursor;bad["schemaVersion"]=True
        with self.assertRaises(ValueError):t.advance_through("100",bad)
        with self.assertRaises(ValueError):t.next_group(bad)
        with self.assertRaises(ValueError):timeline(trusted="yes")
        proxy=Proxy(p)
        proxy.mutate=lambda page:page["diagnostics"]["counts"].update(MALFORMED_PRICE=True)
        with self.assertRaises(ValueError):TickTimeline(proxy,p.dataset_id,p.dataset_version)

    def test_dataset_replacement_revokes_view_and_old_cursor(self):
        p,t=timeline();v=t.consumer();cursor=t.cursor
        other=SyntheticTickProvider([row(0,100,"9","9.1")])
        replacement=t.replace_dataset(other,other.dataset_id,other.dataset_version)
        with self.assertRaises(ValueError):v.read_revealed()
        with self.assertRaises(ValueError):t.advance_through("100",cursor)
        with self.assertRaises(ValueError):replacement.advance_through("100",cursor)
        self.assertEqual(replacement.consumer().read_revealed(),[])
        self.assertEqual(replacement.next_group(replacement.cursor)["groups"][0]["events"][0]["bid"],"9")

    def test_reset_during_provider_read_rejects_late_callback(self):
        p,t=timeline();proxy=Proxy(p);t=TickTimeline(proxy,p.dataset_id,p.dataset_version)
        old=t.cursor
        def reset_once():
            proxy.callback=None;t.reset()
        proxy.callback=reset_once
        with self.assertRaises(ValueError):t.advance_through("300",old)
        self.assertEqual(t.cursor["nextGroupIndex"],"0")
        self.assertEqual(t.next_group(t.cursor)["groups"][0]["timeNs"],"100")


if __name__=="__main__":unittest.main()
