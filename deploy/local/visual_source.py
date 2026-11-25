"""Deterministic SYNTHETIC / TEST ONLY demo source whose charts look like candles.

The original fixture (`tests/synthetic_financial_monthly.py`, golden-hash locked) emits ONE tick per minute that oscillates by a few cents, so every
1-minute candle is a single price and the chart is a row of dashes. This source is a separate, opt-in profile: 5 ticks per minute (12 s) following a
bounded random walk with a slowly varying volatility regime, a small mean-reversion pull and an occasional spread widening.

Properties that matter:
  * deterministic: integer arithmetic only (no floats, no libm), so the dataset version is identical on every machine;
  * canonical contracts unchanged: same artifacts, provider/feed/instrument ids, chunk/manifest bounds as the fixture; only the tick values differ;
  * honest label: SYNTHETIC / TEST ONLY. It is not market data and claims no market realism beyond "looks like a candle chart".
"""
import hashlib

from contracts.canonical import canonical_bytes, content_hash
from ticks.contracts import TickManifest, chunk_content, event_id

GENERATOR_VERSION = "riksora-synthetic-visual-v1"
DATASET_ID = "synthetic:visual-v1"
DEFAULT_SEED = 20261125
DEFAULT_TICKS = 655_360                 # 5 ticks/minute: 2020-01-01 to about 2020-04-01 (same months as the fixture)
STEP_NS = 12_000_000_000
CHUNK_SIZE = 512
_SOURCE_ID = "synthetic:visual:source-0"
_MEMBER_NAME = "RIKSORA_SYNTHETIC_VISUAL_JSONL_V1"
_MASK = (1 << 64) - 1


def _start_ns():
    from execution.research_fixture import START_NS
    return START_NS


def _tri(index, period):
    """Integer triangle wave 0..1000."""
    phase, half = index % period, period // 2
    return (phase if phase <= half else period - phase) * 1000 // half


def _text(cents):
    return f"{cents // 100}.{cents % 100:02d}".rstrip("0").rstrip(".")


def _rows(count, seed, start_ns, step_ns):
    state = ((seed * 6364136223846793005 + 1442695040888963407) & _MASK) or 1
    price = 200_000                                         # 2000.00, in cents
    for index in range(count):
        acc = 0
        for _ in range(3):                                  # 12 x 16-bit uniforms (Irwin-Hall) -> approximately normal
            state ^= state >> 12
            state ^= (state << 25) & _MASK
            state ^= state >> 27
            x = (state * 2685821657736338717) & _MASK
            acc += (x & 0xFFFF) + ((x >> 16) & 0xFFFF) + ((x >> 32) & 0xFFFF) + ((x >> 48) & 0xFFFF)
        z = acc - 393_210                                   # mean 12*32767.5, standard deviation 65,536
        regime = 600 + _tri(index, 3600) * 600 // 1000 + _tri(index, 977) * 300 // 1000      # permille, 600..1500
        scaled = 10 * regime * z                            # 10 cents per tick at regime 1000
        move = (abs(scaled) // (1000 * 65536)) * (1 if scaled >= 0 else -1)
        price = min(max(price + move + (200_000 - price) // 5000, 150_000), 250_000)
        spread = 12 + index % 4 + (30 if index and index % 997 == 0 else 0)
        yield {"schemaVersion": 1, "artifact": "BTL-SYNTHETIC-RAW-TICK-1", "ordinal": str(index),
               "timeNs": str(start_ns + index * step_ns), "bid": _text(price), "ask": _text(price + spread)}


def _member_hash(count, seed, start_ns, step_ns):
    digest = hashlib.sha256()
    for row in _rows(count, seed, start_ns, step_ns):
        digest.update(canonical_bytes(row))
        digest.update(b"\n")
    return digest.hexdigest()


def _event(row, member_hash, quality_hash, dataset_id, dataset_version):
    ordinal = row["ordinal"]
    return dict(
        schemaVersion=1, artifact="BTL-CANONICAL-TICK-1", datasetId=dataset_id, datasetVersion=dataset_version,
        providerId="SYNTHETIC", feedId="TEST_ONLY", instrumentId="SYNTHETIC_INSTRUMENT",
        eventId=event_id("SYNTHETIC", "TEST_ONLY", member_hash, ordinal),
        timeNs=row["timeNs"], resolutionNs="1", bid=row["bid"], ask=row["ask"], rawOrdinal=ordinal, trustedSequence=None,
        provenance=dict(sourceId=_SOURCE_ID, memberHash=member_hash, originalTimestamp="SYNTHETIC_NS:" + row["timeNs"]),
        quality=dict(evidenceHash=quality_hash, quote="VALID", freshness="CONFIRMED", gapBefore="NONE", duplicateOf=None))


def _quality_hash(seed, member_hash):
    return content_hash(dict(schemaVersion=1, artifact="BTL-SYNTHETIC-QUALITY-1", label="SYNTHETIC / TEST ONLY", generator=GENERATOR_VERSION,
                             seed=seed, memberHash=member_hash, assertion="AUTHORED_FIXTURE_COMPLETE_FRESH_QUOTES"))


def _check(count, chunk_size):
    if type(count) is not int or not 512 <= count <= 1_048_576:
        raise ValueError("event_count must be between 512 and 1,048,576")
    if count % chunk_size or not 1 <= chunk_size <= 1024 or count // chunk_size > 4096:
        raise ValueError("event_count/chunk_size must satisfy canonical chunk bounds")


def build_manifest(count=DEFAULT_TICKS, seed=DEFAULT_SEED, dataset_id=DATASET_ID, chunk_size=CHUNK_SIZE, start_ns=None, step_ns=STEP_NS):
    """Return (canonical source manifest wire, member hash, quality hash); only one chunk is held in memory."""
    _check(count, chunk_size)
    start_ns = _start_ns() if start_ns is None else start_ns
    member_hash = _member_hash(count, seed, start_ns, step_ns)
    quality_hash = _quality_hash(seed, member_hash)
    chunks, batch, first_ns, last_ns = [], [], None, None
    for row in _rows(count, seed, start_ns, step_ns):
        first_ns = first_ns or row["timeNs"]
        last_ns = row["timeNs"]
        batch.append(_event(row, member_hash, quality_hash, dataset_id, "0" * 64))
        if len(batch) == chunk_size:
            index = len(chunks)
            chunk = dict(schemaVersion=1, artifact="BTL-TICK-CHUNK-1", datasetId=dataset_id, datasetVersion="0" * 64, chunkIndex=str(index), events=batch)
            chunks.append(dict(chunkIndex=str(index), hash=content_hash(chunk_content(chunk)), eventCount=len(batch), firstNs=batch[0]["timeNs"], lastNs=batch[-1]["timeNs"]))
            batch = []
    end_ns = str(int(last_ns) + 1)
    manifest = TickManifest.from_wire(dict(
        schemaVersion=1, artifact="BTL-TICK-MANIFEST-1", datasetId=dataset_id, providerId="SYNTHETIC", feedId="TEST_ONLY", instrumentId="SYNTHETIC_INSTRUMENT",
        providerSymbol="SYNTHETIC_TEST_ONLY", evidenceClass="SYNTHETIC_CONTRACT_ONLY", adapterVersion=GENERATOR_VERSION, validatorVersion="BTL-TICK-VALIDATOR-1",
        sources=[dict(sourceId=_SOURCE_ID, archiveHash=None, memberHash=member_hash, originalName=_MEMBER_NAME, acquiredAtUtc=None, sourceUrl=None,
                      timestampConvention="SYNTHETIC Unix UTC ns; deterministic test-only JSONL; no market evidence", resolutionNs="1", originalScalePolicy="PRESERVE_RAW_TEXT")],
        range=dict(startNs=first_ns, endNs=end_ns, endExclusive=True),
        ordering=dict(timestamps="VERIFIED_NONDECREASING", ties="UNTRUSTED", sequenceScope=None, sequenceEvidenceHash=None),
        coverage=[dict(startNs=first_ns, endNs=end_ns, status="DECLARED_COMPLETE",
                       evidenceHash=content_hash(dict(schemaVersion=1, artifact="BTL-SYNTHETIC-COVERAGE-1", generator=GENERATOR_VERSION, seed=seed,
                                                      eventCount=count, label="SYNTHETIC / TEST ONLY")))],
        gaps=[], rights={"class": "SYNTHETIC", "evidenceHash": None}, diagnostics=[], chunks=chunks))
    return manifest.wire, member_hash, quality_hash


def iter_events(count, source_manifest, seed=DEFAULT_SEED, start_ns=None, step_ns=STEP_NS):
    """Regenerate the verified synthetic ticks one at a time for the Parquet/Compact writers."""
    start_ns = _start_ns() if start_ns is None else start_ns
    manifest = TickManifest.from_wire(source_manifest)
    if len(manifest.wire["sources"]) != 1 or sum(c["eventCount"] for c in manifest.wire["chunks"]) != count:
        raise ValueError("manifest does not match this generator configuration")
    member_hash = manifest.wire["sources"][0]["memberHash"]
    quality_hash = _quality_hash(seed, member_hash)
    for row in _rows(count, seed, start_ns, step_ns):
        yield _event(row, member_hash, quality_hash, manifest.wire["datasetId"], manifest.version)
