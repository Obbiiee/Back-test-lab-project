"""Versioned QA integration adapter; existing 42.17/42.19 interfaces are unchanged."""
import fcntl,hashlib,json,zlib
from contextlib import contextmanager
from pathlib import Path
from contracts.canonical import canonical_bytes,content_hash
from ticks.contracts_v2 import hash_v2
from tests.qa_range_prototype5 import PreparedRanges,commitment
import execution.observed_postgres as storage

FORMAT='RIKSORA-QA-INTEGRATED-SESSION-1'


class Journal(PreparedRanges):
    def __init__(self,path,binding):
        super().__init__(path,binding)
        self.db.execute('CREATE TABLE IF NOT EXISTS intents(id TEXT PRIMARY KEY,hash TEXT NOT NULL,body BLOB NOT NULL) WITHOUT ROWID');self.db.commit()

    def prepare_command(self,command,before,after,positions,previous,candidate):
        raw=canonical_bytes(command);intent_hash=hashlib.sha256(raw).hexdigest();packed=zlib.compress(raw,6)
        old=self.db.execute('SELECT hash,body FROM intents WHERE id=?',(command['commandId'],)).fetchone()
        if old is not None and old!=(intent_hash,packed):raise ValueError('INTENT_CONFLICT')
        self.db.execute('INSERT OR IGNORE INTO intents VALUES(?,?,?)',(command['commandId'],intent_hash,packed))
        digest=None
        if candidate:
            row=dict(schemaVersion=1,format=FORMAT,bindingHash=self.binding_hash,seq=command['expectedRevision']+1,
                     commandId=command['commandId'],commandHash=content_hash(command),kind=command['kind'],
                     targetNs=command['payload'].get('targetNs'),beforeCursorHash=hash_v2(before['cursor']),afterCursorHash=hash_v2(after['cursor']),
                     groupStart=before['cursor']['nextGroupIndex'],groupEnd=after['cursor']['nextGroupIndex'],
                     firstPosition=positions[0]['position'] if positions else None,positionCommitment=commitment(positions),
                     advanceLogHash=after['advanceLogHash'],positionLogHash=after['positionLogHash'],previousHash=previous)
            body=canonical_bytes(row);digest=hashlib.sha256(body).hexdigest()
            self.db.execute('INSERT OR IGNORE INTO prepared VALUES(?,?,?)',(digest,row['seq'],zlib.compress(body,6)))
        self.db.commit()  # Existing SQLite FULL prepare barrier, before authoritative SQL commit.
        return digest


@contextmanager
def session_lock(folder):
    """Single-host QA worker serialization; not a distributed locking contract."""
    path=Path(folder);path.mkdir(mode=0o700,parents=True,exist_ok=True)
    with (path/'worker.lock').open('a+b') as stream:
        fcntl.flock(stream.fileno(),fcntl.LOCK_EX)
        try:yield
        finally:fcntl.flock(stream.fileno(),fcntl.LOCK_UN)


@contextmanager
def baseline_commit_barrier(fault):
    original=storage.connect
    @contextmanager
    def wrapped(dsn):
        with original(dsn) as db:
            yield db
            if fault:fault('before_sql_commit')
    storage.connect=wrapped
    try:yield
    finally:storage.connect=original
