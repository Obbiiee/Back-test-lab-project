"""Streaming financial-active Monthly Parquet fixture (SYNTHETIC / TEST ONLY).

The raw source member is deterministic canonical JSONL. It is hashed in a
bounded first pass, then the canonical tick manifest is hashed, and ticks are
re-generated in bounded chunks for publication. No tick history is retained in
memory and no market-source or price-realism claim is made.
"""
from datetime import datetime, timezone
import hashlib

from contracts.canonical import canonical_bytes, content_hash
from ticks.contracts import TickManifest, chunk_content, event_id


GENERATOR_VERSION = "riksora-synthetic-financial-monthly-v1"
DEFAULT_SEED = 20261112
DEFAULT_DATASET_ID = "synthetic:financial-active-v1"
CHUNK_SIZE = 256
START_NS = int(datetime(2020, 1, 30, tzinfo=timezone.utc).timestamp()) * 1_000_000_000
_SOURCE_ID = "synthetic:financial-active:source-0"
_MEMBER_NAME = "RIKSORA_SYNTHETIC_FINANCIAL_ACTIVE_JSONL_V1"


def _raw_row(index: int, count: int, seed: int):
    # A deterministic, bounded oscillation, occasional explicit gap/spread
    # changes, followed by an authored limit-entry and TP sequence. This is a
    # software workload, not a market model.
    phase = ((index * 1_103_515_245 + seed) & 0x7fffffff) % 41 - 20
    bid_units = 200_000 + phase
    spread_units = 10 + index % 4
    if index and index % 4093 == 0:
        bid_units += 80  # explicit synthetic price gap
    if index and index % 997 == 0:
        spread_units += 35  # explicit synthetic spread widening
    if index == count - 2:
        bid_units, spread_units = 199_880, 10
    elif index == count - 1:
        bid_units, spread_units = 199_960, 10
    # Preserve the long no-trigger interval; the authored entry is 1998.90.
    return {
        "schemaVersion": 1, "artifact": "BTL-SYNTHETIC-RAW-TICK-1",
        "ordinal": str(index),
        # One authored observation per synthetic minute creates sparse
        # multi-day spans and monthly partition crossings at modest row count.
        "timeNs": str(START_NS + index * 60_000_000_000),
        "bid": f"{bid_units // 100}.{bid_units % 100:02d}".rstrip("0").rstrip("."),
        "ask": f"{(bid_units + spread_units) // 100}.{(bid_units + spread_units) % 100:02d}".rstrip("0").rstrip("."),
    }


def _member_hash(event_count, seed):
    digest = hashlib.sha256()
    for index in range(event_count):
        digest.update(canonical_bytes(_raw_row(index, event_count, seed)))
        digest.update(b"\n")
    return digest.hexdigest()


def _event(row, member_hash, quality_hash, dataset_id, dataset_version):
    ordinal = row["ordinal"]
    return dict(
        schemaVersion=1, artifact="BTL-CANONICAL-TICK-1", datasetId=dataset_id,
        datasetVersion=dataset_version, providerId="SYNTHETIC", feedId="TEST_ONLY",
        instrumentId="SYNTHETIC_INSTRUMENT",
        eventId=event_id("SYNTHETIC", "TEST_ONLY", member_hash, ordinal),
        timeNs=row["timeNs"], resolutionNs="1", bid=row["bid"], ask=row["ask"],
        rawOrdinal=ordinal, trustedSequence=None,
        provenance=dict(sourceId=_SOURCE_ID, memberHash=member_hash,
                        originalTimestamp="SYNTHETIC_NS:" + row["timeNs"]),
        quality=dict(evidenceHash=quality_hash, quote="VALID", freshness="CONFIRMED",
                     gapBefore="NONE", duplicateOf=None),
    )


def build_manifest(event_count, seed=DEFAULT_SEED, dataset_id=DEFAULT_DATASET_ID,
                   chunk_size=CHUNK_SIZE):
    """Return a canonical source manifest while retaining only one chunk."""
    if type(event_count) is not int or not 512 <= event_count <= 1_048_576:
        raise ValueError("event_count must be between 512 and 1,048,576")
    if event_count % chunk_size or not 1 <= chunk_size <= 1024 or event_count // chunk_size > 4096:
        raise ValueError("event_count/chunk_size must satisfy canonical chunk bounds")
    if type(seed) is not int or seed < 0:
        raise ValueError("seed must be a nonnegative integer")
    member_hash = _member_hash(event_count, seed)
    quality_hash = content_hash(dict(schemaVersion=1, artifact="BTL-SYNTHETIC-QUALITY-1",
        label="SYNTHETIC / TEST ONLY", generator=GENERATOR_VERSION, seed=seed,
        memberHash=member_hash, assertion="AUTHORED_FIXTURE_COMPLETE_FRESH_QUOTES"))
    chunks = []
    first_ns = last_ns = None
    batch = []
    for index in range(event_count):
        row = _raw_row(index, event_count, seed)
        event = _event(row, member_hash, quality_hash, dataset_id, "0" * 64)
        if first_ns is None:
            first_ns = row["timeNs"]
        last_ns = row["timeNs"]
        batch.append(event)
        if len(batch) == chunk_size:
            chunk_index = len(chunks)
            chunk = dict(schemaVersion=1, artifact="BTL-TICK-CHUNK-1", datasetId=dataset_id,
                         datasetVersion="0" * 64, chunkIndex=str(chunk_index), events=batch)
            chunks.append(dict(chunkIndex=str(chunk_index), hash=content_hash(chunk_content(chunk)),
                eventCount=len(batch), firstNs=batch[0]["timeNs"], lastNs=batch[-1]["timeNs"]))
            batch = []
    end_ns = str(int(last_ns) + 1)
    source_manifest = TickManifest.from_wire(dict(
        schemaVersion=1, artifact="BTL-TICK-MANIFEST-1", datasetId=dataset_id,
        providerId="SYNTHETIC", feedId="TEST_ONLY", instrumentId="SYNTHETIC_INSTRUMENT",
        providerSymbol="SYNTHETIC_TEST_ONLY", evidenceClass="SYNTHETIC_CONTRACT_ONLY",
        adapterVersion=GENERATOR_VERSION, validatorVersion="BTL-TICK-VALIDATOR-1",
        sources=[dict(sourceId=_SOURCE_ID, archiveHash=None, memberHash=member_hash,
            originalName=_MEMBER_NAME, acquiredAtUtc=None, sourceUrl=None,
            timestampConvention="SYNTHETIC Unix UTC ns; deterministic test-only JSONL; no market evidence",
            resolutionNs="1", originalScalePolicy="PRESERVE_RAW_TEXT")],
        range=dict(startNs=first_ns, endNs=end_ns, endExclusive=True),
        ordering=dict(timestamps="VERIFIED_NONDECREASING", ties="UNTRUSTED",
                      sequenceScope=None, sequenceEvidenceHash=None),
        coverage=[dict(startNs=first_ns, endNs=end_ns, status="DECLARED_COMPLETE",
            evidenceHash=content_hash(dict(schemaVersion=1, artifact="BTL-SYNTHETIC-COVERAGE-1",
                generator=GENERATOR_VERSION, seed=seed, eventCount=event_count,
                label="SYNTHETIC / TEST ONLY")))],
        gaps=[], rights={"class": "SYNTHETIC", "evidenceHash": None}, diagnostics=[], chunks=chunks))
    return source_manifest.wire, member_hash, quality_hash


def iter_events(event_count, source_manifest, seed=DEFAULT_SEED):
    """Regenerate verified synthetic ticks one at a time for Parquet writer."""
    manifest = TickManifest.from_wire(source_manifest)
    if len(manifest.wire["sources"]) != 1 or sum(c["eventCount"] for c in manifest.wire["chunks"]) != event_count:
        raise ValueError("manifest does not match this generator configuration")
    member_hash = manifest.wire["sources"][0]["memberHash"]
    quality_hash = content_hash(dict(schemaVersion=1, artifact="BTL-SYNTHETIC-QUALITY-1",
        label="SYNTHETIC / TEST ONLY", generator=GENERATOR_VERSION, seed=seed,
        memberHash=member_hash, assertion="AUTHORED_FIXTURE_COMPLETE_FRESH_QUOTES"))
    for index in range(event_count):
        yield _event(_raw_row(index, event_count, seed), member_hash, quality_hash,
                     manifest.wire["datasetId"], manifest.version)


def fixture_identity(event_count, source_manifest):
    manifest = TickManifest.from_wire(source_manifest)
    return dict(label="SYNTHETIC / TEST ONLY", generatorVersion=GENERATOR_VERSION,
        seed=DEFAULT_SEED, eventCount=event_count, datasetId=manifest.wire["datasetId"],
        datasetVersion=manifest.version,
        sourceMemberSha256=manifest.wire["sources"][0]["memberHash"],
        firstNs=manifest.wire["range"]["startNs"], lastNs=manifest.wire["range"]["endNs"])
