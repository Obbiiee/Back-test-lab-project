"""Explicit operator-selected local directory; no path from an HTTP caller."""
import hashlib
import json
import re
from decimal import Decimal
from pathlib import Path

from contracts.canonical import content_hash
from contracts.primitives import require, decimal
from .service import Chunk, Dataset, DataService, PersonalLocalPolicy

MAX_CHUNK = 2097152


def read_bytes(path):
    with path.open("rb") as stream:
        raw = stream.read(MAX_CHUNK+1)
    require(len(raw) <= MAX_CHUNK, "artifact", "ARTIFACT_TOO_LARGE")
    return raw


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate_key")
        result[key] = value
    return result


def decode(raw):
    try:
        return json.loads(raw, parse_float=Decimal,
                          parse_constant=lambda _: require(False, "nonfinite"),
                          object_pairs_hook=unique_object)
    except (ValueError, UnicodeError, RecursionError):
        require(False, "json", "CORRUPT_ARTIFACT")


def valid_rows(raw):
    rows = decode(raw)
    require(type(rows) is list and 1 <= len(rows) <= 40000, "rows", "CORRUPT_ARTIFACT")
    previous = -1
    result = []
    for row in rows:
        require(type(row) is list and len(row) == 5, "row", "CORRUPT_ARTIFACT")
        t = row[0]
        require(type(t) is int and previous < t <= 2**53-1 and t % 60 == 0, "time", "CORRUPT_ARTIFACT")
        prices = tuple(decimal(v, "price", positive=True) for v in row[1:])
        o, h, low, c = prices
        require(low <= min(o,c) <= max(o,c) <= h, "ohlc", "CORRUPT_ARTIFACT")
        result.append((t, *prices))
        previous = t
    return tuple(result)


class LocalStore:
    def __init__(self, root):
        self.root = Path(root).resolve(strict=True)

    def path(self, key):
        require(type(key) is str and re.fullmatch(r"[0-9]{4}-[0-9]{2}-1m\.json", key), "artifactKey")
        path = (self.root/key).resolve(strict=True)
        require(path.parent == self.root and not (self.root/key).is_symlink(), "artifactPath")
        return path

    def rows(self, chunk):
        raw = read_bytes(self.path(chunk.key))
        require(len(raw) == chunk.size and hashlib.sha256(raw).hexdigest() == chunk.sha256,
                "checksum", "CORRUPT_ARTIFACT")
        rows = valid_rows(raw)
        require((len(rows), rows[0][0], rows[-1][0]) == (chunk.count, chunk.first, chunk.last),
                "chunk", "CORRUPT_ARTIFACT")
        return rows


def open_local(root):
    """Hash/validate all M1 chunks before activating the immutable catalog."""
    store = LocalStore(root)
    manifest = decode(read_bytes(store.root/'manifest.json'))
    require(type(manifest) is dict and manifest.get('symbol') == 'XAUUSD' and
            manifest.get('source') == 'HistData.com' and manifest.get('priceType') == 'bid' and
            manifest.get('timezone') == 'UTC' and manifest.get('sourceTimezone') == 'EST fixed UTC-5', 'manifest')
    entries = manifest.get('frames', {}).get('1m')
    require(type(entries) is list and 1 <= len(entries) <= 240, 'chunks')
    chunks = []
    last = -1
    keys = set()
    for entry in entries:
        require(type(entry) is dict and set(entry) == {'path','count','first','last'}, 'chunkDescriptor')
        require(all(type(entry[f]) is int for f in ('count','first','last')), 'chunkFields')
        require(entry['path'] not in keys, 'duplicateChunk')
        keys.add(entry['path'])
        raw = read_bytes(store.path(entry['path']))
        rows = valid_rows(raw)
        require((len(rows), rows[0][0], rows[-1][0]) == (entry['count'], entry['first'], entry['last']) and
                rows[0][0] > last, 'chunkInventory', 'CORRUPT_ARTIFACT')
        last = rows[-1][0]
        chunks.append(Chunk(entry['path'], hashlib.sha256(raw).hexdigest(), len(raw), len(rows), rows[0][0], last))
    identity = {'schemaVersion': 1, 'normalization': 'EXISTING_JSON_M1_V1',
                'source': 'HistData.com', 'instrument': 'XAUUSD', 'side': 'BID',
                'chunks': [{'hash': c.sha256, 'bytes': c.size, 'count': c.count, 'first': c.first, 'last': c.last} for c in chunks]}
    dataset = Dataset('histdata-xauusd-local-m1', content_hash(identity), 'XAUUSD',
                      'HistData.com', tuple(chunks), 'EXISTING_PERSONAL_LOCAL_ONLY_NOT_PUBLIC_GRANT')
    return DataService(dataset, store, PersonalLocalPolicy())
