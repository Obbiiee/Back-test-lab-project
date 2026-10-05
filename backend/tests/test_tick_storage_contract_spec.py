"""42.17 DESIGN ORACLE ONLY: tiny fixtures, not production V2 storage/index.

No filesystem ingestion, provider port, execution, or runtime mounting. The
blueprint owns the specification; these tests check authored contract examples.
"""
from copy import deepcopy
import json
import hashlib
from pathlib import Path
import re
import unittest

from contracts.canonical import canonical_bytes, content_hash, _normalize
from contracts.primitives import require
from ticks.contracts import CanonicalTick, TickManifest, chunk_content
from ticks.provider import SyntheticTickProvider, validate_provider
from ticks.timeline import TickTimeline


BLUEPRINT = Path(__file__).resolve().parents[2] / "docs/PRODUCT_SYSTEM_ARCHITECTURE_BLUEPRINT.md"


def fixture():
    text = BLUEPRINT.read_text(encoding="utf-8")
    marker = "<!-- BTL-TICK-STORAGE-CONTRACT-FIXTURES-2 -->"
    require(text.count(marker) == 1, "fixture_owner")
    match = re.search(r"```json\s*(.*?)\s*```", text.split(marker)[1], re.S)
    def reject(value):
        raise ValueError(value)
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "duplicate_key")
            result[key] = value
        return result
    return json.loads(match[1], parse_float=reject, parse_constant=reject, object_pairs_hook=unique)


def design_bytes(obj):
    """Test-only V2 encoder oracle; V1 public encoder still rejects version 2."""
    require(type(obj.get("schemaVersion")) is int and obj["schemaVersion"] == 2, "version", "SCHEMA_MISMATCH")
    encoded = json.dumps(_normalize(obj), sort_keys=True, ensure_ascii=False,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
    require(len(encoded) <= 1048576, "bytes", "ARTIFACT_LIMIT")
    return encoded


def design_hash(obj):
    return hashlib.sha256(design_bytes(obj)).hexdigest()


def v2_hash(obj):
    payload = {k: v for k, v in obj.items() if k != "datasetVersion"}
    if obj["artifact"] == "BTL-TICK-STORAGE-CHUNK-2":
        payload["events"] = [{k: v for k, v in row.items() if k != "datasetVersion"}
                             for row in obj["events"]]
    return design_hash(payload)


def descriptor(index, child):
    if "events" in child:
        first = int(child["firstOrdinal"])
        count = len(child["events"])
        low, high = child["events"][0]["timeNs"], child["events"][-1]["timeNs"]
    else:
        first = int(child["children"][0]["firstOrdinal"])
        count = sum(int(d["eventCount"]) for d in child["children"])
        low, high = child["children"][0]["firstNs"], child["children"][-1]["lastNs"]
    return dict(index=str(index), hash=v2_hash(child), eventCount=str(count), firstNs=low,
                lastNs=high, firstOrdinal=str(first), lastOrdinal=str(first+count-1))


class LayoutOracle:
    """In-memory authored example ONLY; never a scalability implementation."""
    def __init__(self, layout):
        self.objects, self.index_objects, self.events, self.positions = {}, {}, [], []
        header = dict(schemaVersion=2, datasetId="synthetic:storage-v2", datasetVersion="0"*64,
                      providerId="SYNTHETIC", feedId="TEST_ONLY", instrumentId="SYNTHETIC_INSTRUMENT")
        raw = [dict(ordinal=str(i), timeNs=t, bid="1", ask="1.1", sequence=None)
               for i, t in enumerate(t for d in layout for p in d for c in p for t in c)]
        # Reuse validated V1 canonical events; replace only pinned datasetVersion.
        small = SyntheticTickProvider(raw, dataset_id=header["datasetId"])
        token = None
        while True:
            page = small.read_page(small.dataset_id, small.dataset_version, token, 32)
            self.events.extend(page["events"])
            if page["endOfDataset"]:
                break
            token = page["nextToken"]
        for event in self.events:
            event["datasetVersion"] = header["datasetVersion"]
        directory_descriptors, ordinal = [], 0
        index_directories = []
        for di, directory in enumerate(layout):
            partitions, index_partitions = [], []
            for pi, partition in enumerate(directory):
                chunks, entries = [], []
                for ci, values in enumerate(partition):
                    chunk = dict(header, artifact="BTL-TICK-STORAGE-CHUNK-2", directoryIndex=str(di),
                                 partitionIndex=str(pi), chunkIndex=str(ci), firstOrdinal=str(ordinal),
                                 events=deepcopy(self.events[ordinal:ordinal+len(values)]))
                    self.objects[di, pi, ci] = chunk
                    meta = descriptor(ci, chunk)
                    chunks.append(meta)
                    for offset in range(len(values)):
                        self.positions.append(dict(directoryIndex=str(di), partitionIndex=str(pi),
                                                   chunkIndex=str(ci), eventOffset=str(offset),
                                                   globalOrdinal=str(ordinal+offset), timeNs=values[offset]))
                    start = ordinal
                    while start and self.events[start-1]["timeNs"] == values[0]:
                        start -= 1
                    entries.append(dict(chunkIndex=str(ci), chunkHash=meta["hash"],
                                        firstNs=meta["firstNs"], lastNs=meta["lastNs"],
                                        firstOrdinal=meta["firstOrdinal"], lastOrdinal=meta["lastOrdinal"],
                                        firstGroupStart=deepcopy(self.positions[start])))
                    ordinal += len(values)
                part = dict(header, artifact="BTL-TICK-PARTITION-2", directoryIndex=str(di),
                            partitionIndex=str(pi), range=self.range_for(chunks),
                            eventCount=str(sum(int(c["eventCount"]) for c in chunks)), children=chunks)
                self.objects[di, pi] = part
                meta = descriptor(pi, part)
                partitions.append(meta)
                leaf = dict(header, artifact="BTL-TICK-TIME-PARTITION-2", directoryIndex=str(di),
                            partitionIndex=str(pi), partitionHash=meta["hash"], chunks=entries)
                self.index_objects[di, pi] = leaf
                index_partitions.append(self.index_descriptor(pi, leaf, meta))
            obj = dict(header, artifact="BTL-TICK-DIRECTORY-2", directoryIndex=str(di),
                       range=self.range_for(partitions),
                       eventCount=str(sum(int(p["eventCount"]) for p in partitions)), children=partitions)
            self.objects[di,] = obj
            meta = descriptor(di, obj)
            directory_descriptors.append(meta)
            index_dir = dict(header, artifact="BTL-TICK-TIME-DIRECTORY-2", directoryIndex=str(di), children=index_partitions)
            self.index_objects[di] = index_dir
            index_directories.append(self.index_descriptor(di, index_dir, meta))
        self.index_root = dict(header, artifact="BTL-TICK-TIME-ROOT-2", children=index_directories)
        self.source = dict(header, artifact="BTL-TICK-SOURCE-CATALOG-2", sources=small.describe(small.dataset_id, small.dataset_version)["sources"])
        self.evidence = dict(header, artifact="BTL-TICK-EVIDENCE-CATALOG-2", children=[])
        self.root = {k: v for k, v in header.items() if k != "datasetVersion"}
        self.root.update(artifact="BTL-TICK-DATASET-2", providerSymbol="SYNTHETIC_TEST_ONLY",
                         evidenceClass="SYNTHETIC_CONTRACT_ONLY", adapterVersion="SYNTHETIC-2",
                         validatorVersion="BTL-TICK-VALIDATOR-2", range=self.range_for(directory_descriptors),
                         ordering=dict(timestamps="VERIFIED_NONDECREASING", ties="UNTRUSTED", sequenceScope=None, sequenceEvidenceHash=None),
                         eventCount=str(len(raw)), directories=directory_descriptors,
                         sourceCatalogHash=v2_hash(self.source), evidenceCatalogHash=v2_hash(self.evidence),
                         indexContentHash=v2_hash(self.index_root))
        self.version = design_hash(self.root)
        for obj in [*self.objects.values(), *self.index_objects.values(), self.index_root, self.source, self.evidence]:
            obj["datasetVersion"] = self.version
            for row in obj.get("events", []):
                row["datasetVersion"] = self.version
        self.binding = dict(schemaVersion=2, artifact="BTL-TICK-INDEX-BINDING-2", datasetId=header["datasetId"],
                            datasetVersion=self.version, manifestHash=self.version, indexContentHash=self.root["indexContentHash"])
        self.receipt = dict(schemaVersion=2, artifact="BTL-TICK-COMPLETION-2", datasetId=header["datasetId"],
                            datasetVersion=self.version, manifestHash=self.version, validatorVersion=self.root["validatorVersion"],
                            indexContentHash=self.root["indexContentHash"], sourceCatalogHash=self.root["sourceCatalogHash"])

    @staticmethod
    def range_for(descriptors):
        return dict(startNs=descriptors[0]["firstNs"], endNs=str(int(descriptors[-1]["lastNs"])+1), endExclusive=True)

    @staticmethod
    def index_descriptor(index, obj, meta):
        return dict(index=str(index), hash=v2_hash(obj), firstNs=meta["firstNs"], lastNs=meta["lastNs"])

    def child(self, key):
        require(key in self.objects, "child", "MISSING_CHILD")
        return self.objects[key]

    def validate(self):
        require(self.version == design_hash(self.root), "root", "MANIFEST_HASH_MISMATCH")
        require(self.receipt is not None, "publication", "INCOMPLETE_INGESTION")
        expected = dict(schemaVersion=2, artifact="BTL-TICK-COMPLETION-2", datasetId=self.root["datasetId"],
                        datasetVersion=self.version, manifestHash=self.version, validatorVersion=self.root["validatorVersion"],
                        indexContentHash=self.root["indexContentHash"], sourceCatalogHash=self.root["sourceCatalogHash"])
        require(self.receipt == expected, "receipt", "INCOMPLETE_INGESTION")
        for key, obj in self.objects.items():
            require(obj["schemaVersion"] == 2 and type(obj["schemaVersion"]) is int, "version", "SCHEMA_MISMATCH")
            require(obj["datasetVersion"] == self.version, "version", "VERSION_MISMATCH")
            for field in ("datasetId", "providerId", "feedId", "instrumentId"):
                require(obj[field] == self.root[field], field, "IDENTITY_CONFLICT")
            design_bytes(obj)
            if "events" in obj:
                require(1 <= len(obj["events"]) <= 256, "events", "ARTIFACT_LIMIT")
                for row in obj["events"]:
                    CanonicalTick.from_wire(row)
                    for field in ("datasetId", "datasetVersion", "providerId", "feedId", "instrumentId"):
                        require(row[field] == obj[field], field, "IDENTITY_CONFLICT")
            else:
                self.validate_descriptors(obj["children"], key)
                require(obj["range"] == self.range_for(obj["children"]), "range", "RANGE_CONFLICT")
                require(int(obj["eventCount"]) == sum(int(x["eventCount"]) for x in obj["children"]), "count", "COUNT_CONFLICT")
        self.validate_descriptors(self.root["directories"], ())
        require(self.root["range"] == self.range_for(self.root["directories"]), "range", "RANGE_CONFLICT")
        require(int(self.root["eventCount"]) == sum(int(d["eventCount"]) for d in self.root["directories"]), "count", "COUNT_CONFLICT")
        require(v2_hash(self.index_root) == self.root["indexContentHash"], "index", "INDEX_HASH_MISMATCH")
        require(self.binding["datasetId"] == self.root["datasetId"], "dataset", "DATASET_MISMATCH")
        require(self.binding["datasetVersion"] == self.version, "index", "STALE_INDEX")
        require(self.binding["manifestHash"] == self.version and self.binding["indexContentHash"] == self.root["indexContentHash"], "binding", "INDEX_HASH_MISMATCH")
        # Exhaustive tiny example checks each immutable navigation edge against storage.
        for di, meta in enumerate(self.index_root["children"]):
            directory = self.index_objects[di]
            require(meta == self.index_descriptor(di, directory, self.root["directories"][di]), "index", "INDEX_HASH_MISMATCH")
            for pi, link in enumerate(directory["children"]):
                leaf = self.index_objects[di, pi]
                part = self.child((di, pi))
                require(link == self.index_descriptor(pi, leaf, descriptor(pi, part)), "index", "INDEX_HASH_MISMATCH")
                require(leaf["partitionHash"] == v2_hash(part), "partition", "PARTITION_HASH_MISMATCH")
                require(len(leaf["chunks"]) == len(part["children"]), "index", "MISSING_CHILD")
                for ci, entry in enumerate(leaf["chunks"]):
                    d = part["children"][ci]
                    require(entry["chunkHash"] == d["hash"] and entry["chunkIndex"] == str(ci), "index", "CORRUPT_INDEX_POINTER")
                    require(all(entry[k] == d[k] for k in ("firstNs", "lastNs", "firstOrdinal", "lastOrdinal")), "index", "RANGE_CONFLICT")
                    self.check_anchor(entry["firstGroupStart"], entry["firstNs"])
        return self

    def validate_descriptors(self, values, parent):
        limit = 1024 if len(parent) == 1 else 256
        require(1 <= len(values) <= limit, "fanout", "ARTIFACT_LIMIT")
        last_time, last_ordinal = -1, None
        for i, d in enumerate(values):
            require(d["index"] == str(i), "index", "DUPLICATE_PARTITION")
            key = (*parent, i)
            actual = descriptor(i, self.child(key))
            require(d["hash"] == actual["hash"], "hash", "CHILD_HASH_MISMATCH")
            require(d == actual, "descriptor", "RANGE_CONFLICT")
            require(int(d["firstNs"]) >= last_time, "seam", "ORDER_REVERSAL")
            require(last_ordinal is None or int(d["firstOrdinal"]) == last_ordinal+1, "ordinal", "INVALID_SOURCE_ORDINAL")
            last_time, last_ordinal = int(d["lastNs"]), int(d["lastOrdinal"])

    def check_anchor(self, pointer, time):
        key = tuple(int(pointer[k]) for k in ("directoryIndex", "partitionIndex", "chunkIndex"))
        chunk = self.child(key)
        offset = int(pointer["eventOffset"])
        require(0 <= offset < len(chunk["events"]), "offset", "CORRUPT_INDEX_POINTER")
        ordinal = int(chunk["firstOrdinal"])+offset
        require(pointer["globalOrdinal"] == str(ordinal) and pointer["timeNs"] == time and
                chunk["events"][offset]["timeNs"] == time, "anchor", "CORRUPT_INDEX_POINTER")
        require(ordinal == 0 or int(self.events[ordinal-1]["timeNs"]) < int(time), "predecessor", "INCOMPLETE_ATOMIC_BOUNDARY")
        return ordinal

    def locate_group(self, target):
        self.validate()
        # Private lower-bound semantics, not a consumer API.
        choose = lambda xs: next((x for x in xs if int(x["lastNs"]) >= int(target)), None)
        d = choose(self.index_root["children"])
        if d is None:
            return []
        di = int(d["index"])
        p = choose(self.index_objects[di]["children"])
        pi = int(p["index"])
        entry = choose(self.index_objects[di, pi]["chunks"])
        ci = int(entry["chunkIndex"])
        chunk = self.child((di, pi, ci))
        offset = next(i for i, row in enumerate(chunk["events"]) if int(row["timeNs"]) >= int(target))
        time = chunk["events"][offset]["timeNs"]
        if time == entry["firstNs"]:
            start = self.check_anchor(entry["firstGroupStart"], time)
        else:
            while offset and chunk["events"][offset-1]["timeNs"] == time:
                offset -= 1
            start = int(chunk["firstOrdinal"])+offset
        rows = []
        while start < len(self.events) and self.events[start]["timeNs"] == time:
            # Resolve through actual storage, so missing boundary chunks cannot hide.
            pointer = self.positions[start]
            obj = self.child(tuple(int(pointer[k]) for k in ("directoryIndex", "partitionIndex", "chunkIndex")))
            rows.append(deepcopy(obj["events"][int(pointer["eventOffset"])]))
            start += 1
        return rows


class ScalableTickStorageContractTests(unittest.TestCase):
    def setUp(self):
        self.spec = fixture()
        self.o = LayoutOracle(self.spec["layout"])

    def test_capacity_explicit_limits_and_canonical_maximum_descriptors(self):
        limits = self.spec["limits"]
        self.assertEqual(limits["directories"]*limits["partitionsPerDirectory"]*
                         limits["chunksPerPartition"]*limits["eventsPerChunk"], int(limits["capacity"]))
        self.assertEqual(int(limits["capacity"]), 17179869184)
        d = descriptor(0, self.o.child((0, 0, 0)))
        for count in (256, 1024):
            obj = dict(self.o.child((0,)), children=[dict(d, index=str(i)) for i in range(count)])
            self.assertLess(len(design_bytes(obj)), 1048576)
        obj["children"] = [dict(d, index=str(i)) for i in range(4096)]
        with self.assertRaises(ValueError):
            design_bytes(obj)  # node limit tighter than generic array ceiling
        for key in ((0,), (0, 0)):
            self.o.objects[key]["children"] *= 1025
            with self.assertRaises(ValueError):
                self.o.validate()

    def test_v1_manifest_events_chunks_and_timeline_remain_valid(self):
        p = SyntheticTickProvider([dict(ordinal="0", timeNs="100", bid="1.001", ask="1.002", sequence=None)])
        m = validate_provider(p, p.dataset_id, p.dataset_version)
        self.assertEqual(TickManifest.from_wire(m.wire).version, p.dataset_version)
        timeline = TickTimeline(p, p.dataset_id, p.dataset_version)
        self.assertEqual(timeline.next_group(timeline.cursor)["groups"][0]["events"][0]["bid"], "1.001")

    def test_v2_encoder_version_is_hashed_and_v1_encoder_is_unchanged(self):
        obj = dict(schemaVersion=2, artifact="BTL-TICK-DATASET-2", value="1.001")
        self.assertEqual(design_bytes(obj), b'{"artifact":"BTL-TICK-DATASET-2","schemaVersion":2,"value":"1.001"}')
        self.assertNotEqual(design_hash(obj), content_hash(dict(obj, schemaVersion=1)))
        with self.assertRaises(ValueError):
            canonical_bytes(obj)
        for bad in (True, 1, 3, "2"):
            with self.assertRaises(ValueError):
                design_bytes(dict(obj, schemaVersion=bad))
        with self.assertRaises(ValueError):
            design_bytes(dict(obj, value=1.1))

    def test_full_chunk_count_and_metadata_node_budgets(self):
        from ticks.contracts import event_id
        obj = deepcopy(self.o.child((0, 0, 0)))
        template = obj["events"][0]
        obj["events"] = []
        for i in range(256):
            row = dict(deepcopy(template), rawOrdinal=str(i))
            row["eventId"] = event_id(row["providerId"], row["feedId"], row["provenance"]["memberHash"], str(i))
            CanonicalTick.from_wire(row)
            obj["events"].append(row)
        self.assertLess(len(design_bytes(obj)), 1048576)
        self.o.objects[0, 0, 0] = dict(obj, events=obj["events"]+[template])
        with self.assertRaisesRegex(ValueError, "ARTIFACT_LIMIT"):
            self.o.validate()

    def test_time_reversal_and_source_identity_conflicts_rejected(self):
        with self.assertRaisesRegex(ValueError, "ORDER_REVERSAL"):
            LayoutOracle([[[["100", "200", "150", "300"]]]])
        raw = dict(deepcopy(self.o.events[0]), rawOrdinal="999")
        with self.assertRaisesRegex(ValueError, "IDENTITY_CONFLICT"):
            CanonicalTick.from_wire(raw)

    def test_index_pointer_cannot_leak_extra_events_at_boundary(self):
        early = self.o.locate_group("100")
        self.assertEqual([r["timeNs"] for r in early], ["100"])
        self.assertEqual(self.o.locate_group("401"), [])  # private navigation only
        self.assertNotIn("nextPosition", early[0])
        self.assertNotIn("globalOrdinal", early[0])

    def test_same_time_boundary_layout_does_not_change_event_identity(self):
        other = LayoutOracle([[[["100", "200", "200", "200", "300", "400"]]]])
        self.assertNotEqual(self.o.version, other.version)  # layout identity is pinned
        self.assertEqual([r["eventId"] for r in self.o.locate_group("200")],
                         [r["eventId"] for r in other.locate_group("200")])

    def test_hierarchy_hash_identity_acyclic_and_multiple_partitions(self):
        self.o.validate()
        self.assertEqual(len(self.o.root["directories"]), 2)
        self.assertEqual(len(self.o.child((0,))["children"]), 2)
        chunk = self.o.child((0, 0, 0))
        digest = v2_hash(chunk)
        chunk["datasetVersion"] = "a"*64
        for row in chunk["events"]:
            row["datasetVersion"] = "a"*64
        self.assertEqual(v2_hash(chunk), digest)
        with self.assertRaisesRegex(ValueError, "VERSION_MISMATCH"):
            self.o.validate()
        v1_envelope = dict(schemaVersion=1, artifact="BTL-TICK-CHUNK-1", datasetId=chunk["datasetId"],
                           datasetVersion=chunk["datasetVersion"], chunkIndex="0", events=chunk["events"])
        self.assertNotEqual(digest, content_hash(chunk_content(v1_envelope)))

    def test_lookup_before_exact_between_and_after(self):
        for case in self.spec["lookups"]:
            with self.subTest(target=case["targetNs"]):
                rows = self.o.locate_group(case["targetNs"])
                self.assertEqual([r["rawOrdinal"] for r in rows], case["expectedOrdinals"])

    def test_atomic_untrusted_group_crosses_chunks_partitions_directories(self):
        from ticks.timeline import make_group
        rows = self.o.locate_group("200")
        self.assertEqual([r["rawOrdinal"] for r in rows], ["1", "2", "3"])
        self.assertEqual(make_group(rows, self.o.version)["order"], "UNTRUSTED")
        self.assertTrue(all(row["trustedSequence"] is None for row in rows))
        at = self.o.positions[1:4]
        self.assertNotEqual(at[0]["partitionIndex"], at[1]["partitionIndex"])
        self.assertNotEqual(at[1]["directoryIndex"], at[2]["directoryIndex"])

    def test_missing_child_and_hash_mismatch(self):
        for key in ((0,), (0, 0), (0, 0, 0)):
            o = deepcopy(self.o)
            del o.objects[key]
            with self.assertRaisesRegex(ValueError, "MISSING_CHILD"):
                o.validate()
        self.o.child((0, 0, 0))["events"][0]["bid"] = "1.01"
        with self.assertRaisesRegex(ValueError, "CHILD_HASH_MISMATCH"):
            self.o.validate()

    def test_partition_range_count_and_duplicate_reject(self):
        p = self.o.child((0, 0))
        for mutate, code in ((lambda x: x["range"].update(endNs="202"), "RANGE_CONFLICT"),
                             (lambda x: x.update(eventCount="999"), "COUNT_CONFLICT"),
                             (lambda x: x["children"].append(deepcopy(x["children"][0])), "DUPLICATE_PARTITION")):
            original = deepcopy(p)
            mutate(p)
            with self.assertRaisesRegex(ValueError, code):
                self.o.validate()
            p.clear(); p.update(original)

    def test_index_dataset_stale_binding_and_content_hash(self):
        for field, value, code in (("datasetId", "other", "DATASET_MISMATCH"),
                                   ("datasetVersion", "f"*64, "STALE_INDEX"),
                                   ("manifestHash", "f"*64, "INDEX_HASH_MISMATCH")):
            o = deepcopy(self.o); o.binding[field] = value
            with self.assertRaisesRegex(ValueError, code):
                o.validate()
        self.o.index_root["children"][0]["lastNs"] = "999"
        with self.assertRaisesRegex(ValueError, "INDEX_HASH_MISMATCH"):
            self.o.validate()

    def test_corrupt_pointer_and_incomplete_atomic_predecessor(self):
        pointer = deepcopy(self.o.positions[1])
        self.assertEqual(self.o.check_anchor(pointer, "200"), 1)
        for field, value in (("eventOffset", "99"), ("globalOrdinal", "999"), ("timeNs", "201")):
            bad = dict(pointer, **{field: value})
            with self.assertRaisesRegex(ValueError, "CORRUPT_INDEX_POINTER"):
                self.o.check_anchor(bad, "200")
        with self.assertRaisesRegex(ValueError, "INCOMPLETE_ATOMIC_BOUNDARY"):
            self.o.check_anchor(self.o.positions[2], "200")

    def test_incomplete_publication_and_wrong_version_fail_closed(self):
        self.o.receipt = None
        with self.assertRaisesRegex(ValueError, "INCOMPLETE_INGESTION"):
            self.o.validate()
        self.o = LayoutOracle(self.spec["layout"])
        self.o.child((0, 0, 0))["schemaVersion"] = 1
        with self.assertRaisesRegex(ValueError, "SCHEMA_MISMATCH"):
            self.o.validate()

    def test_instrument_identity_cannot_mix(self):
        self.o.child((0, 0, 0))["instrumentId"] = "EURUSD"
        with self.assertRaisesRegex(ValueError, "IDENTITY_CONFLICT"):
            self.o.validate()

    def test_one_authority_and_protected_runtime_contracts_not_renamed(self):
        text = BLUEPRINT.read_text(encoding="utf-8").split("## 42.17 ", 1)[1]
        self.assertEqual(self.spec["evidenceClass"], "SYNTHETIC_CONTRACT_ONLY")
        for fragment in ("17,179,869,184", "TickDataProvider V1", "INCOMPLETE_ATOMIC_BOUNDARY",
                         "INDEX-BINDING-2", "sessionStartNs", "no-look-ahead", "STOP"):
            self.assertIn(fragment.lower(), text.lower())


if __name__ == "__main__":
    unittest.main()
