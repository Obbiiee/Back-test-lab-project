"""Checkpoint 5 QA ONLY. Not an application persistence format or authority."""
import hashlib
import json
import sqlite3
import zlib
from contextlib import contextmanager
from pathlib import Path

from contracts.canonical import canonical_bytes, content_hash
from ticks.contracts_v2 import canonical_v2_bytes, hash_v2
import execution.observed_postgres as storage

TAG = 'RIKSORA-QA-RANGE-EXPERIMENT-1'


def commitment(records):
    h = hashlib.sha256(b'RIKSORA-QA-POSITIONS-1\0')
    for record in records:
        raw = canonical_v2_bytes(dict(schemaVersion=2,artifact='RIKSORA-QA-POSITION-COMMIT-1',record=record))
        h.update(len(raw).to_bytes(4, 'big')); h.update(raw)
    return h.hexdigest()


class PreparedRanges:
    def __init__(self, path, binding):
        self.path = Path(path)
        self.db = sqlite3.connect(path)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('CREATE TABLE IF NOT EXISTS binding(hash TEXT PRIMARY KEY, body BLOB NOT NULL) WITHOUT ROWID')
        self.db.execute('CREATE TABLE IF NOT EXISTS prepared(hash TEXT PRIMARY KEY, seq INTEGER NOT NULL, body BLOB NOT NULL) WITHOUT ROWID')
        self.db.execute('CREATE TABLE IF NOT EXISTS published(id INTEGER PRIMARY KEY, tip TEXT)')
        self.binding_hash = content_hash(binding)
        old = self.db.execute('SELECT hash,body FROM binding').fetchall()
        if old and old != [(self.binding_hash, canonical_bytes(binding))]: raise ValueError('BINDING_CONFLICT')
        self.db.execute('INSERT OR IGNORE INTO binding VALUES(?,?)', (self.binding_hash, canonical_bytes(binding)))
        self.db.commit()

    def prepare(self, command, before_cp, after_cp, position_records, previous):
        row = dict(schemaVersion=1,format=TAG, bindingHash=self.binding_hash, seq=command['expectedRevision']+1,
                   commandId=command['commandId'], commandHash=content_hash(command), targetNs=command['payload']['targetNs'],
                   beforeCursorHash=hash_v2(before_cp['cursor']), afterCursorHash=hash_v2(after_cp['cursor']),
                   groupStart=before_cp['cursor']['nextGroupIndex'], groupEnd=after_cp['cursor']['nextGroupIndex'],
                   firstPosition=position_records[0]['position'] if position_records else None,
                   positionCommitment=commitment(position_records), previousHash=previous,
                   advanceLogHash=after_cp['advanceLogHash'], positionLogHash=after_cp['positionLogHash'])
        raw = canonical_bytes(row); digest = hashlib.sha256(raw).hexdigest()
        self.db.execute('INSERT OR IGNORE INTO prepared VALUES(?,?,?)', (digest,row['seq'],zlib.compress(raw,6)))
        self.db.commit()  # FULL synchronous: durable prepare precedes authoritative SQL commit.
        return digest

    def publish(self, digest):
        self.db.execute('INSERT OR REPLACE INTO published VALUES(1,?)',(digest,));self.db.commit()

    def rows(self):
        return self.db.execute('SELECT hash,seq,body FROM prepared ORDER BY seq,hash').fetchall()

    def close(self): self.db.close()


def install_commit_table(dsn):
    with storage.connect(dsn) as db:
        db.execute('CREATE TABLE public.qa5_commits(workspace_id TEXT,session_id TEXT,revision BIGINT,command_id TEXT,range_hash TEXT,PRIMARY KEY(workspace_id,session_id,revision),FOREIGN KEY(workspace_id,session_id,command_id) REFERENCES btl.tick_commands)')
        db.execute('CREATE TRIGGER qa5_immutable BEFORE UPDATE OR DELETE OR TRUNCATE ON public.qa5_commits FOR EACH STATEMENT EXECUTE FUNCTION btl.deny_evidence_mutation()')


@contextmanager
def atomic_reference(scope, command, digest, fault=None):
    """QA adapter: existing financial commit plus range reference in ONE SQL transaction."""
    original = storage.connect
    @contextmanager
    def wrapped(dsn):
        with original(dsn) as db:
            yield db
            db.execute('INSERT INTO public.qa5_commits VALUES(%s,%s,%s,%s,%s)',
                       (scope.workspace_id,command['sessionId'],command['expectedRevision']+1,command['commandId'],digest))
            if fault: fault('before_sql_commit')
    storage.connect = wrapped
    try: yield
    finally: storage.connect = original


def refs(dsn, scope, session):
    with storage.connect(dsn) as db:
        return db.execute('SELECT revision,command_id,range_hash FROM public.qa5_commits WHERE workspace_id=%s AND session_id=%s ORDER BY revision',(scope.workspace_id,session)).fetchall()
