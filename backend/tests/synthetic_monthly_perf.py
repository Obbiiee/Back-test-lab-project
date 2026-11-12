"""Deterministic, synthetic-only monthly Parquet workload generator.

This is a performance fixture, not market history and not a price model. It
keeps canonical source segments bounded so it can build legal V1 manifests.
"""
from datetime import datetime, timezone

from contracts.canonical import content_hash
from ticks.contracts import CanonicalTick, TickManifest, chunk_content, event_id


GENERATOR_VERSION = "riksora-synthetic-parquet-perf-v1"
MAX_EVENTS = 65_536  # 128 source segments x 512 source records (manifest limit).
SOURCE_SEGMENT_SIZE = 512
CHUNK_SIZE = 64
SEED = 20261111
DATASET_ID = "synthetic:perf-monthly-65k-v1"


def _price(value):
    return f"{value // 100_000}.{value % 100_000:05d}".rstrip("0").rstrip(".")


def build_dataset(event_count=MAX_EVENTS, seed=SEED):
    """Return (canonical source manifest, canonical events) for Parquet tests.

    Timestamps are deterministic and cross the January/February 2020 partition
    boundary. Most rows advance one second; periodic 60s/300s pauses provide
    sparse intervals. Spread changes deterministically. No market claim is made.
    """
    if (type(event_count) is not int or event_count < SOURCE_SEGMENT_SIZE or
            event_count > MAX_EVENTS or event_count % SOURCE_SEGMENT_SIZE or
            (event_count // SOURCE_SEGMENT_SIZE) % 2):
        raise ValueError("event_count must be an even multiple of 512 up to 65,536")
    if type(seed) is not int or seed < 0:
        raise ValueError("seed must be a nonnegative integer")

    segment_count = event_count // SOURCE_SEGMENT_SIZE
    jan_ns = int(datetime(2020, 1, 1, tzinfo=timezone.utc).timestamp() * 1_000_000_000)
    feb_ns = int(datetime(2020, 2, 1, tzinfo=timezone.utc).timestamp() * 1_000_000_000)
    rows = []
    timestamp = jan_ns
    for index in range(event_count):
        half = index // (event_count // 2)
        local = index % (event_count // 2)
        if local == 0:
            timestamp = jan_ns if half == 0 else feb_ns
        elif index % 4096 == 0:
            timestamp += 300_000_000_000
        elif index % 1024 == 0:
            timestamp += 60_000_000_000
        else:
            timestamp += 1_000_000_000
        phase = ((index * 1103515245 + seed) & 0x7FFFFFFF) % 4001 - 2000
        base = 110_000 + phase
        spread = 3 + index % 5 + (15 if index % 97 == 0 else 0)
        rows.append(dict(ordinal=str(index % SOURCE_SEGMENT_SIZE), timeNs=str(timestamp),
                         bid=_price(base), ask=_price(base + spread), sequence=None))

    sources = []
    member_hashes = []
    for segment in range(segment_count):
        raw_rows = rows[segment * SOURCE_SEGMENT_SIZE:(segment + 1) * SOURCE_SEGMENT_SIZE]
        member_hash = content_hash(dict(schemaVersion=1, artifact="BTL-SYNTHETIC-RAW-1",
                                        rows=raw_rows, diagnostics=[]))
        member_hashes.append(member_hash)
        sources.append(dict(sourceId=f"synthetic:perf:{segment:03d}", archiveHash=None,
            memberHash=member_hash,
            originalName=f"SYNTHETIC_PERF_SEED_{seed}_SEGMENT_{segment:03d}",
            acquiredAtUtc=None, sourceUrl=None,
            timestampConvention="SYNTHETIC Unix UTC ns; deterministic performance fixture; no market evidence",
            resolutionNs="1", originalScalePolicy="PRESERVE_RAW_TEXT"))

    events = []
    for segment, member_hash in enumerate(member_hashes):
        quality_hash = content_hash(dict(schemaVersion=1, artifact="BTL-SYNTHETIC-QUALITY-1",
            label="SYNTHETIC / TEST ONLY", memberHash=member_hash,
            assertion="AUTHORED_FIXTURE_COMPLETE_FRESH_QUOTES"))
        source_id = f"synthetic:perf:{segment:03d}"
        for index in range(segment * SOURCE_SEGMENT_SIZE, (segment + 1) * SOURCE_SEGMENT_SIZE):
            row = rows[index]
            event = dict(schemaVersion=1, artifact="BTL-CANONICAL-TICK-1",
                datasetId=DATASET_ID, datasetVersion="0" * 64,
                providerId="SYNTHETIC", feedId="TEST_ONLY", instrumentId="SYNTHETIC_INSTRUMENT",
                eventId=event_id("SYNTHETIC", "TEST_ONLY", member_hash, row["ordinal"]),
                timeNs=row["timeNs"], resolutionNs="1", bid=row["bid"], ask=row["ask"],
                rawOrdinal=row["ordinal"], trustedSequence=None,
                provenance=dict(sourceId=source_id, memberHash=member_hash,
                                originalTimestamp="SYNTHETIC_NS:" + row["timeNs"]),
                quality=dict(evidenceHash=quality_hash, quote="VALID", freshness="CONFIRMED",
                             gapBefore="NONE", duplicateOf=None))
            events.append(CanonicalTick.from_wire(event).wire)

    chunk_index = []
    for offset in range(0, event_count, CHUNK_SIZE):
        batch = events[offset:offset + CHUNK_SIZE]
        chunk = dict(schemaVersion=1, artifact="BTL-TICK-CHUNK-1", datasetId=DATASET_ID,
                     chunkIndex=str(len(chunk_index)), events=batch)
        chunk_index.append(dict(chunkIndex=str(len(chunk_index)),
            hash=content_hash(chunk_content(chunk)), eventCount=len(batch),
            firstNs=batch[0]["timeNs"], lastNs=batch[-1]["timeNs"]))

    source_manifest = TickManifest.from_wire(dict(
        schemaVersion=1, artifact="BTL-TICK-MANIFEST-1", datasetId=DATASET_ID,
        providerId="SYNTHETIC", feedId="TEST_ONLY", instrumentId="SYNTHETIC_INSTRUMENT",
        providerSymbol="SYNTHETIC_TEST_ONLY", evidenceClass="SYNTHETIC_CONTRACT_ONLY",
        adapterVersion="SYNTHETIC-PERF-1", validatorVersion="BTL-TICK-VALIDATOR-1",
        sources=sources, range=dict(startNs=events[0]["timeNs"],
            endNs=str(int(events[-1]["timeNs"]) + 1), endExclusive=True),
        ordering=dict(timestamps="VERIFIED_NONDECREASING", ties="UNTRUSTED",
                      sequenceScope=None, sequenceEvidenceHash=None),
        # Completeness here means the authored synthetic fixture is fully
        # enumerated, including intentional quiet intervals. It is not market
        # coverage evidence and must never be presented as historical data.
        coverage=[
            dict(startNs=events[0]["timeNs"], endNs=str(feb_ns), status="DECLARED_COMPLETE",
                 evidenceHash=content_hash(dict(schemaVersion=1, artifact="BTL-SYNTHETIC-COVERAGE-1",
                     generator=GENERATOR_VERSION, seed=seed, month="2020-01", label="SYNTHETIC / TEST ONLY"))),
            dict(startNs=str(feb_ns), endNs=str(int(events[-1]["timeNs"]) + 1),
                 status="DECLARED_COMPLETE",
                 evidenceHash=content_hash(dict(schemaVersion=1, artifact="BTL-SYNTHETIC-COVERAGE-1",
                     generator=GENERATOR_VERSION, seed=seed, month="2020-02", label="SYNTHETIC / TEST ONLY"))),
        ], gaps=[], rights={"class": "SYNTHETIC", "evidenceHash": None},
        diagnostics=[], chunks=chunk_index))
    version = source_manifest.version
    for event in events:
        event["datasetVersion"] = version
    return source_manifest.wire, events
