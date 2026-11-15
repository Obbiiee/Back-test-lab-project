"""Compact checkpoint V2 (BTL-TICK-COMPACT-CHECKPOINT-1) at the timeline level: equivalence with V1, cold resume without replaying the history, constant size, and refusals.
SYNTHETIC / TEST ONLY. The source is the repository's deterministic Monthly Parquet fixture (optionally with several events per timestamp)."""
import json
import os
import tempfile
import time
import unittest
from unittest.mock import patch

from contracts.canonical import canonical_bytes, content_hash
from contracts.primitives import ContractError
from market_data.monthly_parquet import MonthlyParquetProvider, write_monthly_parquet
from ticks.timeline import TickTimeline, COMPACT_CHECKPOINT
import tests.synthetic_financial_monthly as syn

TICKS = 4096


def build(ticks, *, pair_up=False, row_group_size=256):
    """(provider, tmpdir). With pair_up two consecutive raw events share one timestamp (multi-event atomic groups, also across chunk edges)."""
    tmp = tempfile.TemporaryDirectory(prefix="riksora-cc-")
    original = syn._raw_row

    def paired(index, count, seed):
        row = original(index, count, seed)
        if pair_up:
            row = dict(row, timeNs=str(syn.START_NS + (index // 2) * 60_000_000_000))
        return row
    with patch.object(syn, "_raw_row", paired):
        manifest, _m, _q = syn.build_manifest(ticks)
        version = content_hash(manifest)
        parquet = write_monthly_parquet(os.path.join(tmp.name, "monthly"), syn.iter_events(ticks, manifest), manifest, expected_version=version, row_group_size=row_group_size)
    provider = MonthlyParquetProvider(os.path.join(tmp.name, "monthly"), expected_dataset_id=manifest["datasetId"], expected_dataset_version=version, expected_manifest_hash=parquet["manifestHash"])
    return provider, tmp, manifest


def targets(manifest, step):
    start = int(manifest["range"]["startNs"]); end = int(manifest["range"]["endNs"])
    t, out = start, []
    while t < end + step:
        out.append(str(t)); t += step
    return out


class Equivalence(unittest.TestCase):
    def check(self, pair_up):
        provider, tmp, manifest = build(TICKS, pair_up=pair_up)
        self.addCleanup(tmp.cleanup)
        start = manifest["range"]["startNs"]
        v1 = TickTimeline(provider, provider.dataset_id, provider.dataset_version, start)
        v2 = TickTimeline(provider, provider.dataset_id, provider.dataset_version, start, compact=True)
        plan = targets(manifest, 53 * 60_000_000_000)                       # steps that do not align with chunks or groups
        resumes, steps = 0, 0
        for target in plan:
            while True:
                a = v1.advance_through(target, v1.cursor)
                b = v2.advance_through(target, v2.cursor)
                self.assertEqual(a, b, f"acknowledgement differs at step {steps}")        # identical groups, coverage, diagnostics, cursor and hash chain head
                steps += 1
                if steps % 7 == 3:                                          # a cold process: V2 resumes from the constant-size checkpoint, V1 is the uninterrupted reference
                    cp = v2.checkpoint()
                    self.assertEqual(cp["artifact"], COMPACT_CHECKPOINT)
                    self.assertNotIn("advanceTargets", cp)
                    v2 = TickTimeline.resume(provider, cp)
                    resumes += 1
                    self.assertTrue(v2.is_compact)
                    self.assertEqual(v1.cursor, v2.cursor)
                if a["exhaustedThroughBoundary"]:
                    break
        self.assertGreater(resumes, 3)
        self.assertEqual(v1.cursor["nextGroupIndex"], v2.cursor["nextGroupIndex"])
        self.assertEqual(v1.cursor["visiblePrefixHash"], v2.cursor["visiblePrefixHash"])

    def test_single_event_groups(self):
        self.check(False)

    def test_multi_event_groups_across_chunk_edges(self):
        self.check(True)


class RefusalsSizeAndCost(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.provider, cls.tmp, cls.manifest = build(TICKS)
        cls.start = cls.manifest["range"]["startNs"]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def advanced(self, compact, steps=40):
        tl = TickTimeline(self.provider, self.provider.dataset_id, self.provider.dataset_version, self.start, compact=compact)
        for i in range(steps):
            tl.advance_through(str(int(self.start) + (i + 1) * 60 * 60_000_000_000), tl.cursor)
        return tl

    def test_size_is_constant_for_v2_and_grows_for_v1(self):
        small2, big2 = len(json.dumps(self.advanced(True, 3).checkpoint())), len(json.dumps(self.advanced(True, 60).checkpoint()))
        small1, big1 = len(json.dumps(self.advanced(False, 3).checkpoint())), len(json.dumps(self.advanced(False, 60).checkpoint()))
        self.assertLess(abs(big2 - small2), 40)                       # only digits of counters change
        self.assertGreater(big1 - small1, 500)

    def test_resume_cost_is_bounded_by_the_manifest_not_by_the_history(self):
        early, late = self.advanced(True, 3), self.advanced(True, 70)
        cps = (early.checkpoint(), late.checkpoint())
        v1_late = self.advanced(False, 70).checkpoint()

        def cost(cp):
            t = time.perf_counter(); TickTimeline.resume(self.provider, cp); return time.perf_counter() - t
        c_early, c_late, c_v1 = min(cost(cps[0]) for _ in range(3)), min(cost(cps[1]) for _ in range(3)), min(cost(v1_late) for _ in range(3))
        print(f"\nresume seconds: V2 early {c_early:.4f}, V2 late {c_late:.4f}, V1 late {c_v1:.4f}")
        self.assertLess(c_late, c_v1 / 3, "V2 late resume must not replay the schedule")
        self.assertLess(c_late, c_early * 6 + 0.05, "V2 resume time must not grow with the revealed history")

    def test_wrong_pin_wrong_position_and_swapped_source_are_refused(self):
        cp = self.advanced(True, 30).checkpoint()
        TickTimeline.resume(self.provider, cp)
        def bad(**change):
            out = dict(cp, **change)
            with self.assertRaises(ContractError, msg=str(change)):
                TickTimeline.resume(self.provider, out)
        bad(eventsRevealed=str(int(cp["eventsRevealed"]) + 1))                     # off by one: the last revealed group no longer matches
        bad(eventsRevealed=str(int(cp["eventsRevealed"]) - 1))
        bad(sourcePin=dict(cp["sourcePin"], manifestHash="0" * 64))
        bad(sourcePin=dict(cp["sourcePin"], datasetVersion="f" * 64))
        bad(formatVersion=3)
        bad(cursor=dict(cp["cursor"], lastGroupId="0" * 64))
        other, tmp2, _m = build(TICKS + 256)                                         # a different source (other version) cannot be silently substituted
        self.addCleanup(tmp2.cleanup)
        with self.assertRaises(ContractError):
            TickTimeline.resume(other, cp)

    def test_v1_checkpoints_stay_readable_and_migrate_on_request(self):
        v1 = self.advanced(False, 30)
        cp1 = v1.checkpoint()
        self.assertIn("advanceTargets", cp1)
        resumed = TickTimeline.resume(self.provider, cp1)
        self.assertFalse(resumed.is_compact)
        self.assertEqual(resumed.checkpoint(), cp1)
        resumed.migrate_to_compact()
        cp2 = resumed.checkpoint()
        self.assertEqual(cp2["artifact"], COMPACT_CHECKPOINT)
        self.assertEqual(TickTimeline.resume(self.provider, cp2).cursor, v1.cursor)


if __name__ == "__main__":
    unittest.main()
