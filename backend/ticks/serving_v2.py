"""Private serving replicas of TRUSTED completed local V2 acceptance stores.

Original validation/identity tables MUST be retained. No source acquisition,
new semantic acceptance, ingestion resume, rights or financial admission.
"""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import zlib

from contracts.primitives import digest, require
from .contracts_v2 import decode_v2, hash_v2, shape, validate_root, validate_container
from .provider import Cancellation

SCHEMA = '''
CREATE TABLE objects(hash TEXT PRIMARY KEY,body BLOB NOT NULL,kind TEXT NOT NULL) WITHOUT ROWID;
CREATE TABLE journal(key TEXT PRIMARY KEY,value TEXT NOT NULL) WITHOUT ROWID;
CREATE TABLE publications(version TEXT PRIMARY KEY,root BLOB NOT NULL,receipt BLOB NOT NULL,binding BLOB NOT NULL) WITHOUT ROWID;
'''


def _references(obj):
    kind = obj['artifact']
    if kind == 'BTL-TICK-DATASET-2':
        return [x['hash'] for x in obj['directories']] + [obj[k] for k in ('sourceCatalogHash','evidenceCatalogHash','indexContentHash')]
    if 'children' in obj:
        return [x['hash'] for x in obj['children']]
    if kind == 'BTL-TICK-TIME-PARTITION-2':
        return [obj['partitionHash']] + [x['chunkHash'] for x in obj['chunks']]
    return []


def export_serving(source, version, destination, *, trusted_local_completion=False,
                   max_bytes=1073741824, max_objects=65536, cancellation=None):
    """Copy exact accepted artifact bytes; publish receipt LAST in one commit.

Requires trusted local prior semantic acceptance and RETAINED validation store;
not a way to admit an untrusted/self-certified completion receipt. Rechecks
all copied hashes, envelopes, source identities and child existence. Original
identity/index tables remain at source, never dropped/deleted. Pre-commit failures retain an incomplete diagnostic replica. A post-commit
fsync error can leave a valid replica; inspect rather than overwrite/retry.
"""
    require(trusted_local_completion is True, 'trust', 'SERVING_TRUST_REQUIRED')
    digest(version, 'version')
    require(type(max_bytes) is int and 1 <= max_bytes <= 8589934592
            and type(max_objects) is int and 1 <= max_objects <= 262144,
            'budget', 'ARTIFACT_LIMIT')
    source, destination = Path(source), Path(destination)
    require(not source.is_symlink() and not (source/'archive.sqlite').is_symlink()
            and (source/'archive.sqlite').is_file(), 'source', 'SOURCE_PATH_REFUSED')
    require(not destination.exists() and not destination.is_symlink()
            and not destination.resolve().is_relative_to(source.resolve()),
            'destination', 'SOURCE_PATH_REFUSED')
    cancel = cancellation or Cancellation(); cancel.check()
    src = sqlite3.connect((source/'archive.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
    dst = None
    try:
        src.execute('PRAGMA query_only=ON'); src.execute('PRAGMA cache_size=-8192'); src.execute('BEGIN')
        rows = src.execute('SELECT version,root,receipt,binding FROM publications LIMIT 2').fetchall()
        require(len(rows)==1 and rows[0][0]==version, 'completion', 'INCOMPLETE_INGESTION')
        _, root_bytes, receipt_bytes, binding_bytes = rows[0]
        root, receipt, binding = map(decode_v2,(root_bytes,receipt_bytes,binding_bytes))
        validate_root(root); require(hash_v2(root)==version, 'root', 'MANIFEST_HASH_MISMATCH')
        shape(receipt,'BTL-TICK-COMPLETION-2'); shape(binding,'BTL-TICK-INDEX-BINDING-2')
        for obj in (receipt,binding):
            require(obj['datasetId']==root['datasetId'] and obj['datasetVersion']==version
                    and obj['manifestHash']==version and obj['indexContentHash']==root['indexContentHash'],
                    'binding','VERSION_MISMATCH')
        require(receipt['sourceCatalogHash']==root['sourceCatalogHash'] and receipt['validatorVersion']==root['validatorVersion'],
                'completion','INCOMPLETE_INGESTION')
        saved = src.execute("SELECT value FROM journal WHERE key='ingestion'").fetchone()
        require(saved is not None, 'journal', 'INCOMPLETE_INGESTION')
        journal=json.loads(saved[0]); metadata=journal.get('pin',{}).get('metadata',{})
        require(journal.get('state')=='COMPLETE' and str(journal.get('count'))==root['eventCount']
                and all(metadata.get(k)==root[k] for k in ('datasetId','providerId','feedId','instrumentId')),
                'acceptance','INCOMPLETE_INGESTION')
        require(src.execute("SELECT count(*) FROM sqlite_schema WHERE type='table' AND name='identities'").fetchone()[0]==1,
                'acceptance','VALIDATION_STORE_REQUIRED')
        require(str(src.execute('SELECT count(*) FROM identities').fetchone()[0])==root['eventCount'],
                'acceptance','IDENTITY_CONFLICT')
        count, total, largest = src.execute('SELECT count(*),coalesce(sum(length(body)),0),coalesce(max(length(body)),0) FROM objects').fetchone()
        require(0<count<=max_objects and total<=max_bytes and largest<=1050000,
                'objects','ARTIFACT_LIMIT')
        cancel.check(); destination.mkdir(mode=0o700)
        dst=sqlite3.connect(destination/'archive.sqlite')
        dst.execute('PRAGMA synchronous=FULL'); dst.execute('PRAGMA cache_size=-8192'); dst.execute('PRAGMA temp_store=FILE')
        dst.executescript(SCHEMA)
        dst.execute('CREATE TEMP TABLE needed(hash TEXT PRIMARY KEY) WITHOUT ROWID')
        dst.executemany('INSERT OR IGNORE INTO needed VALUES(?)',[(h,) for h in _references(root)])
        copied=0
        for key, compressed, kind in src.execute('SELECT hash,body,kind FROM objects ORDER BY hash'):
            cancel.check(); digest(key,'object')
            decoder=zlib.decompressobj(); raw=decoder.decompress(compressed,1048577)
            require(len(raw)<=1048576 and decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail,
                    'compression','ARTIFACT_LIMIT')
            require(hashlib.sha256(raw).hexdigest()==key,'object','CHILD_HASH_MISMATCH')
            obj=decode_v2(raw); require(obj.get('artifact')==kind,'kind','SCHEMA_MISMATCH')
            obj['datasetVersion']=version
            for event in obj.get('events',[]):event['datasetVersion']=version
            validate_container(obj,root,expected_hash=key)
            dst.execute('INSERT INTO objects VALUES(?,?,?)',(key,compressed,kind))
            dst.executemany('INSERT OR IGNORE INTO needed VALUES(?)',[(h,) for h in _references(obj)])
            copied+=1
            if copied % 128 == 0:
                require(dst.execute("SELECT count(*) FROM needed").fetchone()[0]<=max_objects,
                        "references","ARTIFACT_LIMIT")
        require(copied==count and dst.execute('SELECT count(*) FROM needed').fetchone()[0]<=max_objects,
                'count','ARTIFACT_LIMIT')
        require(dst.execute('SELECT 1 FROM needed n LEFT JOIN objects o ON n.hash=o.hash WHERE o.hash IS NULL LIMIT 1').fetchone() is None,
                'children','MISSING_CHILD')
        cancel.check()
        dst.execute('INSERT INTO journal VALUES(?,?)',('ingestion',saved[0]))
        dst.execute('INSERT INTO publications VALUES(?,?,?,?)',rows[0])
        dst.commit()
        descriptor=os.open(destination,os.O_RDONLY)
        try:os.fsync(descriptor)
        finally:os.close(descriptor)
        return dict(status='SERVING_REPLICA_ONLY_NOT_NEW_ACCEPTANCE',datasetVersion=version,
                    copiedObjects=copied,compressedArtifactBytes=total,
                    sourceValidationMustBeRetained=True,sourceDeleted=False,
                    sourceQualityPromoted=False,financialAdmissionChanged=False)
    finally:
        if dst is not None:dst.close()
        src.close()


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',required=True);parser.add_argument('--version',required=True)
    parser.add_argument('--destination',required=True);parser.add_argument('--report',required=True)
    parser.add_argument('--trusted-local-completion',action='store_true')
    args=parser.parse_args()
    with Path(args.report).open('x') as report:
        try:
            value=export_serving(args.source,args.version,args.destination,
                                 trusted_local_completion=args.trusted_local_completion)
        except (ValueError,OSError,sqlite3.Error,zlib.error) as error:
            value=dict(status='SERVING_EXPORT_REFUSED',code=getattr(error,'code',type(error).__name__))
            json.dump(value,report,indent=2); print(json.dumps(value)); raise SystemExit(1) from None
        json.dump(value,report,indent=2);print(json.dumps(value))


if __name__=='__main__':main()
