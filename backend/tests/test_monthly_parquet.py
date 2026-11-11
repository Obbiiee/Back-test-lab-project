"""Synthetic-only regression for immutable monthly Parquet projection."""
from pathlib import Path
import json
import tempfile
import unittest
import uuid
from unittest.mock import patch

import pyarrow.parquet as pq

from contracts.canonical import canonical_bytes, content_hash
from contracts.primitives import ContractError
from market_data.monthly_parquet import MonthlyParquetProvider, write_monthly_parquet
from application.models import TrustedScope
from execution.workspace import FixtureTimelineCache
from ticks.contracts import TickManifest, chunk_content, event_id
from ticks.provider import SyntheticTickProvider
from ticks.provider import validate_provider
from ticks.timeline import TickTimeline


JAN_LAST = 1_706_745_599_999_999_990
FEB_FIRST = 1_706_745_600_000_000_000


class MonthlyParquetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "ticks"
        self.events = [
            dict(ordinal="0", timeNs=str(JAN_LAST - 2), bid="1.001", ask="1.003", sequence=None),
            dict(ordinal="1", timeNs=str(JAN_LAST), bid="1.002", ask="1.004", sequence=None),
            dict(ordinal="2", timeNs=str(JAN_LAST), bid="1.003", ask="1.005", sequence=None),
            dict(ordinal="3", timeNs=str(FEB_FIRST), bid="1.004", ask="1.006", sequence=None),
        ]
        self.source = SyntheticTickProvider(self.events, chunk_size=2)
        self.manifest = self.source.describe(self.source.dataset_id, self.source.dataset_version)
        self.wire_events = []
        token = None
        while True:
            page = self.source.read_page(self.source.dataset_id, self.source.dataset_version, token, 16)
            self.wire_events.extend(page["events"])
            if page["endOfDataset"]:
                break
            token = page["nextToken"]

    def tearDown(self):
        self.tmp.cleanup()

    def test_round_trip_partial_read_ties_quality_identity_and_manifest(self):
        manifest = write_monthly_parquet(self.root, iter(self.wire_events), self.manifest,
                                         expected_version=self.source.dataset_version, row_group_size=2)
        provider = MonthlyParquetProvider(self.root,
            expected_dataset_id=self.source.dataset_id,
            expected_dataset_version=self.source.dataset_version,
            expected_manifest_hash=manifest["manifestHash"])
        self.assertEqual(provider.verify_all()["eventCount"], len(self.wire_events))
        actual = list(provider.iter_range(JAN_LAST - 3, FEB_FIRST + 1))
        self.assertEqual(actual, self.wire_events)
        groups = list(provider.iter_groups(JAN_LAST, JAN_LAST + 1))
        self.assertEqual(len(groups), 1)
        self.assertEqual(len(groups[0]["events"]), 2)
        self.assertEqual([row["eventId"] for row in actual],
                         [row["eventId"] for row in self.wire_events])
        self.assertEqual([row["bid"] for row in actual], [row["bid"] for row in self.wire_events])
        self.assertEqual([row["ask"] for row in actual], [row["ask"] for row in self.wire_events])
        self.assertEqual(manifest["sourceRights"], self.manifest["rights"])
        self.assertEqual([item["month"] for item in manifest["files"]], ["2024-01", "2024-02"])
        self.assertEqual(manifest["canonicalEventIdentity"], "PRESERVED_EVENT_ID_FIELD")
        for item in manifest["files"]:
            parquet = pq.ParquetFile(self.root / item["path"])
            self.assertTrue(all(parquet.metadata.row_group(0).column(i).compression == "ZSTD"
                                for i in range(parquet.metadata.row_group(0).num_columns)))

    def test_row_group_reads_use_bounded_arrow_batches(self):
        from market_data import monthly_parquet

        manifest = write_monthly_parquet(self.root, iter(self.wire_events), self.manifest,
            expected_version=self.source.dataset_version, row_group_size=len(self.wire_events))
        provider = MonthlyParquetProvider(self.root, expected_manifest_hash=manifest["manifestHash"])
        original = pq.ParquetFile
        batch_calls = []

        class BatchOnlyParquetFile:
            def __init__(self, source):
                self.inner = original(source)

            def __getattr__(self, name):
                return getattr(self.inner, name)

            def iter_batches(self, **kwargs):
                batch_calls.append(kwargs)
                return self.inner.iter_batches(**kwargs)

            def read_row_group(self, *args, **kwargs):
                raise AssertionError("row-group materialization is not allowed")

        with patch("market_data.monthly_parquet.pq.ParquetFile", BatchOnlyParquetFile), \
             patch.object(monthly_parquet, "READ_BATCH_SIZE", 2):
            actual = list(provider.iter_range(JAN_LAST - 3, FEB_FIRST + 1))

        self.assertEqual(actual, self.wire_events)
        self.assertTrue(batch_calls)
        self.assertTrue(all(call["batch_size"] == 2 and call["use_threads"] is False
                            for call in batch_calls))
        self.assertGreaterEqual(len(batch_calls), 2)

    def test_monthly_provider_replays_original_pages_and_timeline(self):
        manifest = write_monthly_parquet(self.root, iter(self.wire_events), self.manifest,
                                         expected_version=self.source.dataset_version, row_group_size=2)
        provider = MonthlyParquetProvider(self.root, expected_dataset_id=self.source.dataset_id,
            expected_dataset_version=self.source.dataset_version,
            expected_manifest_hash=manifest["manifestHash"])
        accepted = validate_provider(provider, provider.dataset_id, provider.dataset_version)
        self.assertEqual(accepted.wire, self.manifest)
        token = None
        pages = []
        while True:
            page = provider.read_page(provider.dataset_id, provider.dataset_version, token, 2)
            pages.extend(page["events"])
            if page["endOfDataset"]:
                break
            token = page["nextToken"]
        self.assertEqual(pages, self.wire_events)
        timeline = TickTimeline(provider, provider.dataset_id, provider.dataset_version)
        prefix = timeline.advance_through(str(FEB_FIRST), timeline.cursor)
        self.assertEqual([group["timeNs"] for group in prefix["groups"]],
                         [str(JAN_LAST - 2), str(JAN_LAST), str(FEB_FIRST)])

    def test_indexed_revealed_window_is_clipped_and_keeps_cross_month_timestamp_groups_atomic(self):
        manifest = write_monthly_parquet(self.root, iter(self.wire_events), self.manifest,
            expected_version=self.source.dataset_version, row_group_size=1)
        provider = MonthlyParquetProvider(self.root, expected_manifest_hash=manifest["manifestHash"])
        self.assertEqual(provider.read_revealed_window(JAN_LAST - 3, 4), [])
        last_january = provider.read_revealed_window(JAN_LAST, 1)
        self.assertEqual(len(last_january), 1)
        self.assertEqual(last_january[0]["timeNs"], str(JAN_LAST))
        self.assertEqual([row["bid"] for row in last_january[0]["events"]], ["1.002", "1.003"])
        through_february = provider.read_revealed_window(FEB_FIRST, 3)
        timeline = TickTimeline(provider, provider.dataset_id, provider.dataset_version)
        expected = timeline.advance_through(str(FEB_FIRST), timeline.cursor)["groups"]
        self.assertEqual(through_february, expected)
        self.assertTrue(all(int(group["timeNs"]) <= FEB_FIRST for group in through_february))
        cache = FixtureTimelineCache(provider, allow_injected_synthetic=True)
        scope = TrustedScope("workspace:monthly-window:"+uuid.uuid4().hex, "fixture:operator")
        with patch("execution.workspace.TickTimeline.resume",
                   side_effect=AssertionError("indexed window must not reconstruct timeline")):
            actual = cache.window(scope, "session:monthly-window", timeline.checkpoint())
            quote = cache.window(scope, "session:monthly-window", timeline.checkpoint(), last_only=True)
        self.assertEqual(actual, expected)
        self.assertEqual(quote, expected[-1:])

    def test_immutable_publish_and_manifest_pin_fail_closed(self):
        manifest = write_monthly_parquet(self.root, iter(self.wire_events), self.manifest,
                                         expected_version=self.source.dataset_version, row_group_size=2)
        with self.assertRaises(ContractError):
            write_monthly_parquet(self.root, iter(self.wire_events), self.manifest,
                                  expected_version=self.source.dataset_version, row_group_size=2)
        with self.assertRaises(ContractError):
            MonthlyParquetProvider(self.root, expected_manifest_hash="0" * 64)
        self.assertTrue((self.root / "manifest.json").is_file())
        self.assertEqual(manifest["eventCount"], len(self.wire_events))

    def test_changed_rowgroup_hash_is_rejected(self):
        write_monthly_parquet(self.root, iter(self.wire_events), self.manifest,
                              expected_version=self.source.dataset_version, row_group_size=2)
        manifest_path = self.root / "manifest.json"
        value = json.loads(manifest_path.read_bytes())
        value["files"][0]["rowGroups"][0]["canonicalEventHash"] = "0" * 64
        value.pop("manifestHash")
        value["manifestHash"] = content_hash(value)
        manifest_path.write_bytes(canonical_bytes(value))
        provider = MonthlyParquetProvider(self.root, expected_manifest_hash=value["manifestHash"])
        with self.assertRaises(ContractError):
            list(provider.iter_range(JAN_LAST - 3, JAN_LAST + 1))

    def test_source_order_and_event_identity_are_not_rewritten(self):
        reversed_events = list(reversed(self.wire_events))
        with self.assertRaises(ContractError):
            write_monthly_parquet(self.root, reversed_events, self.manifest,
                                  expected_version=self.source.dataset_version, row_group_size=2)
        # The failed, unpublished staging directory is retained for diagnosis;
        # no final dataset or manifest is visible.
        self.assertFalse(self.root.exists())
        self.assertTrue(list(Path(self.tmp.name).glob(".ticks.staging-*")))

    def test_valid_but_changed_quote_fails_original_source_chunk_hash(self):
        changed = [dict(row) for row in self.wire_events]
        changed[0] = dict(changed[0], bid="1.0015")
        with self.assertRaises(ContractError):
            write_monthly_parquet(self.root, changed, self.manifest,
                                  expected_version=self.source.dataset_version, row_group_size=2)
        self.assertFalse(self.root.exists())

    def test_unpinned_manifest_is_not_admitted(self):
        write_monthly_parquet(self.root, iter(self.wire_events), self.manifest,
                              expected_version=self.source.dataset_version, row_group_size=2)
        with self.assertRaises(ContractError):
            MonthlyParquetProvider(self.root)

    def test_changed_month_file_hash_is_rejected(self):
        manifest = write_monthly_parquet(self.root, iter(self.wire_events), self.manifest,
                                         expected_version=self.source.dataset_version, row_group_size=2)
        provider = MonthlyParquetProvider(self.root, expected_manifest_hash=manifest["manifestHash"])
        month_file = self.root / manifest["files"][0]["path"]
        with month_file.open("ab") as stream:
            stream.write(b"tamper")
        with self.assertRaises(ContractError):
            provider.verify_file_hash("2024-01")

    def test_source_ordinal_may_restart_only_at_ordered_source_boundary(self):
        sources = []
        events = []
        chunks = []
        for index, original in enumerate(self.wire_events[:2]):
            source_id = f"synthetic:source-{index}"
            member_hash = str(index + 1) * 64
            source = dict(self.manifest["sources"][0], sourceId=source_id,
                          memberHash=member_hash, originalName=f"SYNTHETIC_{index}")
            sources.append(source)
            event = dict(original)
            event["rawOrdinal"] = "0"
            event["datasetVersion"] = "0" * 64
            event["provenance"] = dict(event["provenance"], sourceId=source_id,
                                       memberHash=member_hash)
            event["eventId"] = event_id(event["providerId"], event["feedId"], member_hash, "0")
            events.append(event)
            chunk = dict(schemaVersion=1, artifact="BTL-TICK-CHUNK-1",
                         datasetId=self.source.dataset_id, datasetVersion="0" * 64,
                         chunkIndex=str(index), events=[event])
            chunks.append(dict(chunkIndex=str(index), hash=content_hash(chunk_content(chunk)),
                               eventCount=1, firstNs=event["timeNs"], lastNs=event["timeNs"]))
        source_manifest = dict(self.manifest, sources=sources, chunks=chunks)
        checked = TickManifest.from_wire(source_manifest)
        version = checked.version
        for event in events:
            event["datasetVersion"] = version
        target = Path(self.tmp.name) / "multi-source"
        manifest = write_monthly_parquet(target, events, source_manifest,
                                         expected_version=version, row_group_size=1)
        provider = MonthlyParquetProvider(target, expected_manifest_hash=manifest["manifestHash"])
        readback = list(provider.iter_range(int(events[0]["timeNs"]), int(events[-1]["timeNs"]) + 1))
        self.assertEqual([row["rawOrdinal"] for row in readback], ["0", "0"])
        self.assertEqual([row["provenance"]["sourceId"] for row in readback],
                         ["synthetic:source-0", "synthetic:source-1"])


if __name__ == "__main__":
    unittest.main()
