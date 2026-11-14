"""Synthetic-only regression for the default physical codec of NEW Session timeline logs."""
from contextlib import closing
from pathlib import Path
import os
import sqlite3
import tempfile
import unittest
from unittest import mock

from execution.historical import new_session_log_codec
from ticks.contracts_v2 import ZERO_VERSION
from ticks.provider import SyntheticTickProvider
from ticks.storage_v2 import DatasetBuilder, DiskTickProvider
from ticks.timeline_v2 import IndexedTickTimeline

_BASE = [1_000 + 7 * i for i in range(900)]
TIMES = sorted(_BASE + [t for i, t in enumerate(_BASE) if i % 5 == 0])  # ties every fifth group


class SessionLogCodecTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)
        self.resources = []
        raw = [dict(ordinal=str(i), timeNs=str(t), bid="1.001", ask="1.003", sequence=None) for i, t in enumerate(TIMES)]
        source = SyntheticTickProvider(raw, chunk_size=512)
        manifest = source.describe(source.dataset_id, source.dataset_version)
        meta = {k: manifest[k] for k in ("datasetId", "providerId", "feedId", "instrumentId", "providerSymbol",
                                         "evidenceClass", "adapterVersion", "validatorVersion", "ordering")}
        builder = DatasetBuilder(self.path / "data", meta, manifest["sources"], {"fixture": True}, packing=(64, 8, 8))
        self.resources.append(builder.store)
        token = None
        while True:
            page = source.read_page(source.dataset_id, source.dataset_version, token, 64)
            for row in page["events"]:
                builder.append(dict(row, datasetVersion=ZERO_VERSION))
            if page["endOfDataset"]:
                break
            token = page["nextToken"]
        self.provider = DiskTickProvider(self.path / "data", builder.finish())
        self.resources.append(self.provider)

    def tearDown(self):
        for resource in reversed(self.resources):
            try:
                resource.close()
            except sqlite3.ProgrammingError:
                pass
        self.tmp.cleanup()

    def timeline(self, folder, codec):
        p = self.provider
        t = IndexedTickTimeline(p, p.dataset_id, p.dataset_version, log_folder=self.path / folder,
                                log_codec=codec, max_groups_per_advance=64)
        self.resources.append(t)
        return t

    def drive(self, t):
        for target in (str(TIMES[100]), str(TIMES[400]), str(TIMES[-1])):
            while True:
                t.advance_through(target, t.cursor)
                cursor = t.checkpoint()["cursor"]
                if int(cursor["throughNs"]) >= int(target) and cursor["pendingTargetNs"] is None:
                    break
        return t.checkpoint(), t.consumer().read_revealed("0", 64)

    def layout(self, folder):
        with closing(sqlite3.connect(self.path / folder / "timeline.sqlite")) as db:
            has = db.execute("SELECT 1 FROM sqlite_master WHERE name='log_layout'").fetchone()
            codec = db.execute("SELECT codec FROM log_layout").fetchone()[0] if has else "raw"
            size = sum(len(row[0]) for row in db.execute("SELECT body FROM blocks"))
        return codec, size

    def test_default_rule(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("BTL_QA_TIMELINE_LOG_CODEC", None)
            self.assertEqual(new_session_log_codec(self.path / "never-created"), "zlib-1")
            existing = self.path / "existing"
            existing.mkdir()
            (existing / "timeline.sqlite").write_bytes(b"")
            self.assertIsNone(new_session_log_codec(existing))
        for explicit in ("raw", "zlib-1"):
            with mock.patch.dict(os.environ, {"BTL_QA_TIMELINE_LOG_CODEC": explicit}):
                self.assertEqual(new_session_log_codec(self.path / "never-created"), explicit)
                self.assertEqual(new_session_log_codec(self.path / "existing"), explicit)

    def test_new_default_log_is_smaller_with_identical_logical_history(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("BTL_QA_TIMELINE_LOG_CODEC", None)
            chosen = new_session_log_codec(self.path / "default-log")
        self.assertEqual(chosen, "zlib-1")
        compressed = self.timeline("default-log", chosen)
        plain = self.timeline("raw-log", "raw")
        cp_a, history_a = self.drive(compressed)
        cp_b, history_b = self.drive(plain)
        self.assertEqual(cp_a, cp_b)
        self.assertEqual(history_a, history_b)
        compressed.close()
        plain.close()
        codec_a, bytes_a = self.layout("default-log")
        codec_b, bytes_b = self.layout("raw-log")
        self.assertEqual((codec_a, codec_b), ("zlib-1", "raw"))
        self.assertLess(bytes_a * 3, bytes_b, "zlib-1 should be several times smaller than raw")

    def test_existing_raw_archive_keeps_its_layout_and_resumes(self):
        old = self.timeline("old-session", None)
        checkpoint, history = self.drive(old)
        old.close()
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("BTL_QA_TIMELINE_LOG_CODEC", None)
            codec = new_session_log_codec(self.path / "old-session")
        self.assertIsNone(codec)
        reopened = IndexedTickTimeline.resume(self.provider, checkpoint, log_folder=self.path / "old-session",
                                              log_codec=codec, max_groups_per_advance=64)
        self.resources.append(reopened)
        self.assertEqual(reopened.checkpoint(), checkpoint)
        self.assertEqual(reopened.consumer().read_revealed("0", 64), history)
        reopened.close()
        self.assertEqual(self.layout("old-session")[0], "raw")

    def test_mixed_layout_is_still_refused(self):
        old = self.timeline("mixed", None)
        self.drive(old)
        old.close()
        with self.assertRaises(ValueError):
            self.timeline("mixed", "zlib-1")


if __name__ == "__main__":
    unittest.main()
