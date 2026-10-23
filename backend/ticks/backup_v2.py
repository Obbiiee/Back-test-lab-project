"""Private backup of TRUSTED completed legacy V2 stores, including identities.

No live database, service, migration, source deletion or new financial admission.
A backup is published under archive.sqlite only after its verification succeeds.
"""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time
import zlib

from contracts.primitives import digest, require
from .contracts_v2 import decode_v2, hash_v2, shape, validate_root, validate_container
from .provider import Cancellation
from .serving_v2 import _references


def _completion(db, version):
    tables = {x[0] for x in db.execute("SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
    require(tables == {'objects', 'publications', 'journal', 'identities'},
            'schema', 'VALIDATION_STORE_REQUIRED')
    rows = db.execute('SELECT version,root,receipt,binding FROM publications LIMIT 2').fetchall()
    require(len(rows) == 1 and rows[0][0] == version, 'completion', 'INCOMPLETE_INGESTION')
    root, receipt, binding = map(decode_v2, rows[0][1:])
    validate_root(root); require(hash_v2(root) == version, 'root', 'MANIFEST_HASH_MISMATCH')
    shape(receipt, 'BTL-TICK-COMPLETION-2'); shape(binding, 'BTL-TICK-INDEX-BINDING-2')
    for obj in (receipt, binding):
        require(all(obj[k] == v for k, v in dict(datasetId=root['datasetId'], datasetVersion=version,
                manifestHash=version, indexContentHash=root['indexContentHash']).items()),
                'completion', 'VERSION_MISMATCH')
    require(receipt['sourceCatalogHash'] == root['sourceCatalogHash']
            and receipt['validatorVersion'] == root['validatorVersion'], 'completion', 'INCOMPLETE_INGESTION')
    saved = db.execute("SELECT value FROM journal WHERE key='ingestion'").fetchone()
    require(saved is not None, 'journal', 'INCOMPLETE_INGESTION')
    journal = json.loads(saved[0]); meta = journal.get('pin', {}).get('metadata', {})
    require(journal.get('state') == 'COMPLETE' and str(journal.get('count')) == root['eventCount']
            and all(meta.get(k) == root[k] for k in ('datasetId','providerId','feedId','instrumentId')),
            'journal', 'INCOMPLETE_INGESTION')
    require(str(db.execute('SELECT count(*) FROM identities').fetchone()[0]) == root['eventCount'],
            'identities', 'IDENTITY_CONFLICT')
    return root, rows[0]


def backup_store(source, version, destination, *, trusted_local_completion=False,
                 max_bytes=2147483648, max_objects=65536, timeout_seconds=600, cancellation=None):
    """Native SQLite consistent snapshot; original validation store is retained.

Requires trusted prior full semantic acceptance. Rechecks artifact envelopes,
hashes and referenced-child existence, NOT all source/identity semantics anew.
Pre-publication failure retains private staging, not a reader-visible archive.
Post-publication fsync errors may leave a valid backup: inspect, never overwrite.
"""
    require(trusted_local_completion is True, 'trust', 'BACKUP_TRUST_REQUIRED')
    digest(version, 'version')
    require(type(max_bytes) is int and 1 <= max_bytes <= 8589934592
            and type(max_objects) is int and 1 <= max_objects <= 262144
            and type(timeout_seconds) is int and 1 <= timeout_seconds <= 3600,
            'budget', 'ARTIFACT_LIMIT')
    source, destination = Path(source), Path(destination)
    require(not source.is_symlink() and not (source/'archive.sqlite').is_symlink()
            and (source/'archive.sqlite').is_file(), 'source', 'SOURCE_PATH_REFUSED')
    require(not destination.exists() and not destination.is_symlink()
            and not destination.resolve().is_relative_to(source.resolve()), 'destination', 'SOURCE_PATH_REFUSED')
    cancel = cancellation or Cancellation(); start = time.monotonic()
    def check():
        cancel.check(); require(time.monotonic()-start <= timeout_seconds, 'deadline', 'BACKUP_TIMEOUT')
    check(); src = sqlite3.connect((source/'archive.sqlite').resolve().as_uri()+'?mode=ro', uri=True, timeout=3)
    dst = None
    try:
        src.execute('PRAGMA query_only=ON'); src.execute('PRAGMA cache_size=-8192'); src.execute('BEGIN')
        root, publication = _completion(src, version)
        page_size = src.execute('PRAGMA page_size').fetchone()[0]
        require(src.execute('PRAGMA page_count').fetchone()[0]*page_size <= max_bytes, 'bytes', 'ARTIFACT_LIMIT')
        count, total, largest = src.execute('SELECT count(*),coalesce(sum(length(body)),0),coalesce(max(length(body)),0) FROM objects').fetchone()
        require(0 < count <= max_objects and total <= max_bytes and largest <= 1050000, 'objects', 'ARTIFACT_LIMIT')
        check(); destination.mkdir(mode=0o700); staging = destination/'.staging.sqlite'
        dst = sqlite3.connect(staging)
        def progress(_status, _remaining, pages):
            check(); require(pages*page_size <= max_bytes, 'bytes', 'ARTIFACT_LIMIT')
        src.backup(dst, pages=256, progress=progress, sleep=0.01)
        dst.execute('PRAGMA journal_mode=DELETE'); dst.execute('PRAGMA synchronous=FULL')
        dst.execute('PRAGMA cache_size=-8192'); dst.execute('PRAGMA temp_store=FILE')
        check(); require(dst.execute('PRAGMA quick_check').fetchone()[0] == 'ok', 'database', 'BACKUP_CORRUPT')
        copied_root, copied_publication = _completion(dst, version)
        require(copied_root == root and copied_publication == publication, 'snapshot', 'VERSION_MISMATCH')
        dst.execute('CREATE TEMP TABLE needed(hash TEXT PRIMARY KEY) WITHOUT ROWID')
        dst.executemany('INSERT OR IGNORE INTO needed VALUES(?)', [(h,) for h in _references(root)])
        checked = 0
        for key, compressed, kind in dst.execute('SELECT hash,body,kind FROM objects ORDER BY hash'):
            check(); digest(key, 'object'); decoder = zlib.decompressobj()
            raw = decoder.decompress(compressed, 1048577)
            require(len(raw) <= 1048576 and decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail,
                    'compression', 'ARTIFACT_LIMIT')
            require(hashlib.sha256(raw).hexdigest() == key, 'object', 'CHILD_HASH_MISMATCH')
            obj = decode_v2(raw); require(obj.get('artifact') == kind, 'kind', 'SCHEMA_MISMATCH')
            obj['datasetVersion'] = version
            for event in obj.get('events', []): event['datasetVersion'] = version
            validate_container(obj, root, expected_hash=key)
            dst.executemany('INSERT OR IGNORE INTO needed VALUES(?)', [(h,) for h in _references(obj)])
            checked += 1
            if checked % 128 == 0:
                require(dst.execute('SELECT count(*) FROM needed').fetchone()[0] <= max_objects, 'references', 'ARTIFACT_LIMIT')
        require(checked == count and dst.execute('SELECT count(*) FROM needed').fetchone()[0] <= max_objects,
                'objects', 'ARTIFACT_LIMIT')
        require(dst.execute('SELECT 1 FROM needed n LEFT JOIN objects o ON n.hash=o.hash WHERE o.hash IS NULL LIMIT 1').fetchone() is None,
                'children', 'MISSING_CHILD')
        check(); dst.commit(); dst.close(); dst = None
        require(staging.stat().st_size <= max_bytes, 'bytes', 'ARTIFACT_LIMIT')
        checksum = hashlib.sha256()
        with staging.open('rb') as stream:
            while block := stream.read(1048576): check(); checksum.update(block)
            os.fsync(stream.fileno())
        check(); os.link(staging, destination/'archive.sqlite'); staging.unlink()
        descriptor = os.open(destination, os.O_RDONLY)
        try: os.fsync(descriptor)
        finally: os.close(descriptor)
        return dict(status='VERIFIED_PRIVATE_BACKUP_NOT_NEW_ACCEPTANCE', datasetVersion=version,
                    artifactCount=checked, retainedIdentityRows=int(root['eventCount']),
                    archiveBytes=(destination/'archive.sqlite').stat().st_size, archiveSha256=checksum.hexdigest(),
                    sourceDeleted=False, financialAdmissionChanged=False, sourceValidationRetained=True)
    finally:
        if dst is not None: dst.close()
        src.close()


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ('source','version','destination','report'): parser.add_argument('--'+flag, required=True)
    parser.add_argument('--trusted-local-completion', action='store_true')
    args = parser.parse_args()
    with Path(args.report).open('x') as report:
        try:
            result = backup_store(args.source,args.version,args.destination,
                                  trusted_local_completion=args.trusted_local_completion)
        except (ValueError,OSError,sqlite3.Error,zlib.error) as error:
            result = dict(status='BACKUP_REFUSED_OR_INCOMPLETE',code=getattr(error,'code',type(error).__name__))
            json.dump(result,report,indent=2);print(json.dumps(result));raise SystemExit(1) from None
        json.dump(result,report,indent=2);print(json.dumps(result))


if __name__ == '__main__': main()
