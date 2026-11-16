"""Explicit readonly serving projection of a fingerprint-pinned qualified parent.

Copy canonical objects/publications unchanged. Mutable ingestion journals and
identity/deduplication indexes stay in the retained parent, not the serving
copy. This operation grants no new market-data or financial acceptance.
"""
from pathlib import Path
import hashlib
import json
import os
import sqlite3

from contracts.primitives import digest, identifier, require
from .provider import Cancellation
from .storage_v2 import ArtifactStore, DiskTickProvider

LAYOUT = 'BTL-SQLITE-READ-SNAPSHOT-1'


def _sha(path, cancellation=None):
    with path.open('rb') as stream:
        state = hashlib.sha256()
        while block := stream.read(1048576):
            if cancellation is not None:
                cancellation.check()
            state.update(block)
        return state.hexdigest()


def export_read_snapshot(source_folder, destination, *, dataset_id, dataset_version,
                         expected_archive_sha256, cancellation=None):
    """Copy a completed closed parent into a NEW private, protected directory.

    The caller supplies an independently qualified parent fingerprint. Normal
    source qualification is not replaced by copying its completion receipt.
    """
    identifier(dataset_id, 'datasetId')
    digest(dataset_version, 'datasetVersion')
    digest(expected_archive_sha256, 'parentArchiveSha256')
    cancel = cancellation if cancellation is not None else Cancellation()
    require(isinstance(cancel, Cancellation), 'cancellation')
    cancel.check()
    origin, target = Path(source_folder), Path(destination)
    require(not target.exists() and not target.is_symlink(), 'destination', 'SNAPSHOT_DESTINATION_EXISTS')
    require(not target.resolve().is_relative_to(origin.resolve()), 'destination', 'SOURCE_SNAPSHOT_OVERLAP')
    parent_archive = origin/'archive.sqlite'
    source = ArtifactStore(origin, read_only=True)
    reader = output = None
    created = False
    target_inode = None
    try:
        source.db.execute('BEGIN')
        # A source read transaction also prevents normal DELETE-journal writers
        # from committing while its fingerprint and records are being copied.
        names = {row[0] for row in source.db.execute("SELECT name FROM sqlite_master WHERE name IN ('journal','identities') AND type IN ('table','view')")}
        require({'journal', 'identities'} <= names, 'parent', 'QUALIFIED_PARENT_REQUIRED')
        journal_size = source.db.execute("SELECT length(value) FROM journal WHERE key='ingestion'").fetchone()
        require(journal_size is not None and type(journal_size[0]) is int
                and 0 < journal_size[0] <= 8*1048576, 'parent', 'ARTIFACT_LIMIT')
        stage = source.journal()
        require(type(stage) is dict and stage.get('state') == 'COMPLETE', 'parent', 'INCOMPLETE_INGESTION')
        publications = source.db.execute('SELECT version,length(root),length(receipt),length(binding) FROM publications LIMIT 2').fetchall()
        require(len(publications) == 1 and publications[0][0] == dataset_version,
                'parent', 'INCOMPLETE_INGESTION')
        require(all(type(n) is int and 0 < n <= 1048576 for n in publications[0][1:]),
                'parent', 'ARTIFACT_LIMIT')
        reader = DiskTickProvider(origin, dataset_version, read_only=True)
        described = reader.describe_v2(dataset_id, dataset_version)
        require(type(stage.get('count')) is int and stage['count'] == int(described['root']['eventCount']),
                'parent', 'COUNT_CONFLICT')
        require(_sha(parent_archive, cancel) == expected_archive_sha256, 'parent', 'SOURCE_PIN_CHANGED')
        cancel.check()
        target.mkdir(mode=0o700, parents=True, exist_ok=False)
        created = True
        target_inode = target.stat().st_ino
        partial = target/'archive.sqlite.part'
        descriptor = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(descriptor)
        output = sqlite3.connect(partial)
        output.execute('PRAGMA journal_mode=DELETE')
        output.execute('PRAGMA synchronous=FULL')
        output.execute('PRAGMA cache_size=-8192')
        output.execute('PRAGMA temp_store=FILE')
        output.executescript("""
            CREATE TABLE storage_layout(id INTEGER PRIMARY KEY CHECK(id=1),name TEXT NOT NULL);
            INSERT INTO storage_layout VALUES(1,'BTL-SQLITE-READ-SNAPSHOT-1');
            CREATE TABLE objects(hash TEXT PRIMARY KEY,body BLOB NOT NULL,kind TEXT NOT NULL) WITHOUT ROWID;
            CREATE TABLE publications(version TEXT PRIMARY KEY,root BLOB NOT NULL,receipt BLOB NOT NULL,binding BLOB NOT NULL) WITHOUT ROWID;
        """)
        copied = 0
        for hash_, size, kind in source.db.execute('SELECT hash,length(body),kind FROM objects ORDER BY hash'):
            cancel.check()
            # Normal writer zlib delivery is bounded by raw limit plus deflate
            # overhead. Refuse oversized delivery before allocating its BLOB.
            require(type(size) is int and 0 < size <= 1048576+4096, 'compressed', 'ARTIFACT_LIMIT')
            source.raw(hash_)  # Existing bounded decompression/SHA validator.
            body = source.db.execute('SELECT body FROM objects WHERE hash=?', (hash_,)).fetchone()[0]
            output.execute('INSERT INTO objects VALUES(?,?,?)', (hash_, body, kind))
            copied += 1
        cancel.check()
        require(_sha(parent_archive, cancel) == expected_archive_sha256, 'parent', 'SOURCE_PIN_CHANGED')
        publication = source.db.execute('SELECT version,root,receipt,binding FROM publications WHERE version=?',
                                        (dataset_version,)).fetchone()
        # The serving copy has no completion until every copied body is checked.
        output.execute('INSERT INTO publications VALUES(?,?,?,?)', publication)
        output.commit()
        require(output.execute('PRAGMA integrity_check').fetchone()[0] == 'ok', 'snapshot', 'CORRUPT_RECORD')
        output.close()
        output = None
        cancel.check()
        final = target/'archive.sqlite'
        partial.rename(final)
        probe = DiskTickProvider(target, dataset_version, read_only=True)
        try:
            require(probe.describe_v2(dataset_id, dataset_version) == described, 'snapshot', 'IDENTITY_CONFLICT')
        finally:
            probe.close()
        result = dict(format=LAYOUT, status='DERIVED_READONLY_COPY_VERIFIED_NOT_NEW_ADMISSION',
                      datasetId=dataset_id, datasetVersion=dataset_version,
                      parentArchiveSha256=expected_archive_sha256, archiveSha256=_sha(final, cancel),
                      parentBytes=parent_archive.stat().st_size, archiveBytes=final.stat().st_size,
                      objectsCopied=copied, mutableIngestionIndexesCopied=False,
                      parentRetained=True, writerResumeSupported=False, sourceAdmissionChanged=False)
        with (target/'snapshot.json').open('x') as stream:
            json.dump(result, stream, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        final.chmod(0o400)
        (target/'snapshot.json').chmod(0o400)
        target.chmod(0o500)
        return result
    except BaseException:
        if output is not None:
            output.close()
        # Only our newly created directory/known files; never remove or replace
        # an existing destination, source, or unexpected concurrent work.
        if created and not target.is_symlink() and target.is_dir() and target.stat().st_ino == target_inode:
            target.chmod(0o700)
            for name in ('archive.sqlite.part', 'archive.sqlite.part-journal', 'archive.sqlite', 'snapshot.json'):
                file = target/name
                if file.is_file() and not file.is_symlink():
                    file.unlink()
            try:
                target.rmdir()
            except OSError:
                pass
        raise
    finally:
        if reader is not None:
            reader.close()
        source.close()
