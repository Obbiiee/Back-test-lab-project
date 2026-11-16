"""Opt-in normalized identity writer; no existing archive migration or new wire format.

Canonical payloads, hashes, source strings and uniqueness semantics remain the
original ones. Only identity source strings are interned in SQLite. A logical
view and insertion trigger keep the existing validated builder unchanged.
"""
from pathlib import Path

from contracts.primitives import require
from .storage_v2 import ArtifactStore, DatasetBuilder
from .exness_v2 import ExnessMillisecondIngestion

LAYOUT = "BTL-SQLITE-COMPACT-1"


class CompactArtifactStore(ArtifactStore):
    LAYOUT = LAYOUT

    def __init__(self, folder, **kwargs):
        path = Path(folder)
        require(not path.is_symlink() and not (path / 'archive.sqlite').is_symlink(),
                'store', 'SOURCE_PATH_REFUSED')
        super().__init__(folder, **kwargs)
        try:
            self.db.execute('PRAGMA foreign_keys=ON')
            require(self.db.execute('PRAGMA foreign_keys').fetchone()[0] == 1,
                    'storageLayout', 'STORAGE_LAYOUT_MISMATCH')
        except BaseException:
            self.db.close()
            raise

    def _initialize_schema(self):
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS storage_layout(
                id INTEGER PRIMARY KEY CHECK(id=1),
                name TEXT NOT NULL CHECK(name='BTL-SQLITE-COMPACT-1'));
            INSERT OR IGNORE INTO storage_layout VALUES(1,'BTL-SQLITE-COMPACT-1');
            CREATE TABLE IF NOT EXISTS objects(hash TEXT PRIMARY KEY, body BLOB NOT NULL, kind TEXT NOT NULL) WITHOUT ROWID;
            CREATE TABLE IF NOT EXISTS publications(version TEXT PRIMARY KEY, root BLOB NOT NULL, receipt BLOB NOT NULL, binding BLOB NOT NULL) WITHOUT ROWID;
            CREATE TABLE IF NOT EXISTS journal(key TEXT PRIMARY KEY, value TEXT NOT NULL) WITHOUT ROWID;
            CREATE TABLE IF NOT EXISTS identity_sources(id INTEGER PRIMARY KEY, source TEXT NOT NULL UNIQUE);
            CREATE TABLE IF NOT EXISTS identity_rows(
                event BLOB PRIMARY KEY CHECK(length(event)=32),
                digest BLOB NOT NULL CHECK(length(digest)=32),
                source INTEGER NOT NULL REFERENCES identity_sources(id),
                ordinal TEXT NOT NULL, UNIQUE(source,ordinal)) WITHOUT ROWID;
            CREATE VIEW IF NOT EXISTS identities AS
                SELECT i.event,i.digest,s.source,i.ordinal
                FROM identity_rows i JOIN identity_sources s ON s.id=i.source;
            CREATE TRIGGER IF NOT EXISTS identities_insert INSTEAD OF INSERT ON identities
            BEGIN
                INSERT OR IGNORE INTO identity_sources(source) VALUES(NEW.source);
                INSERT INTO identity_rows(event,digest,source,ordinal)
                VALUES(NEW.event,NEW.digest,
                    (SELECT id FROM identity_sources WHERE source=NEW.source),NEW.ordinal);
            END;
        """)


class CompactDatasetBuilder(DatasetBuilder):
    STORE_CLASS = CompactArtifactStore


class CompactExnessMillisecondIngestion(ExnessMillisecondIngestion):
    """Explicit new-store option; retains the native-ms logical adapter pin."""
    BUILDER_CLASS = CompactDatasetBuilder
