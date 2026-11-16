"""Authored synthetic CSVs only; no provider data or download."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from market_data.instruments import INSTRUMENTS, instrument
from ticks.dukascopy_csv import DukascopyCsvIngestion, FIELDS, source_pin, EPOCH
from ticks.provider import Cancellation
from ticks.storage_v2 import DiskTickProvider
from ticks.timeline_v2 import IndexedTickTimeline

HEADER = ",".join(FIELDS) + "\n"
ROW = "01.09.2026 00:00:00.001,1.10020,1.10000,2.5,3\n"


class DukascopyCsvTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source = self.root / "authored.csv"
        self.source.write_text(HEADER + ROW, encoding="utf-8")
        self.resources = []

    def tearDown(self):
        for resource in reversed(self.resources):
            resource.close()
        self.tmp.cleanup()

    def importer(self, folder="store", **kwargs):
        args = dict(symbol="EURUSD", month="2026-09", evidence_class="SYNTHETIC_CONTRACT_ONLY")
        args.update(kwargs)
        imp = DukascopyCsvIngestion(self.source, self.root / folder, **args)
        self.resources.append(imp.builder.store)
        return imp

    def rows(self, imp, result):
        provider = DiskTickProvider(self.root / "store", result["datasetVersion"])
        self.resources.append(provider)
        timeline = IndexedTickTimeline(provider, provider.dataset_id, provider.dataset_version, str(int((imp.start - EPOCH).total_seconds()) * 1000000000), log_folder=self.root / "timeline")
        self.resources.append(timeline)
        groups = []
        while True:
            batch = timeline.advance_through(str(int((imp.start - EPOCH).total_seconds()) * 1000000000 + 10000000), timeline.cursor)
            groups.extend(batch["groups"])
            if batch["exhaustedThroughBoundary"]:
                return groups

    def test_catalogue_all_sixteen_and_no_assumed_execution_parameters(self):
        self.assertEqual(set(INSTRUMENTS), set("AUDUSD EURGBP NZDUSD USDCHF AUDJPY CADJPY EURUSD GBPUSD NZDJPY USDCAD CHFJPY EURJPY EURNZD GBPJPY USDJPY XAUUSD".split()))
        for symbol in INSTRUMENTS:
            with self.subTest(symbol=symbol):
                result = self.importer(symbol, symbol=symbol).run()
                self.assertEqual(result["symbol"], symbol)
                self.assertEqual(result["executionEligibility"], "NOT_GRANTED")
                self.assertEqual(result["evidenceClass"], "SYNTHETIC_CONTRACT_ONLY")
        with self.assertRaises(ValueError): instrument("BTCUSD")
        with self.assertRaises(TypeError): INSTRUMENTS["BTCUSD"] = None
        self.assertFalse(hasattr(instrument("USDJPY"), "spread"))

    def test_exact_prices_unknown_quality_and_atomic_equal_timestamp_group(self):
        self.source.write_text(HEADER + ROW + ROW.replace("1.10020", "1.10021") + ROW.replace(".001,", ".002,"), encoding="utf-8")
        imp = self.importer(packing=(1, 1, 1))
        result = imp.run()
        groups = self.rows(imp, result)
        self.assertEqual([len(g["events"]) for g in groups], [2, 1])
        self.assertEqual(groups[0]["order"], "UNTRUSTED")
        row = groups[0]["events"][0]
        self.assertEqual((row["bid"], row["ask"], row["resolutionNs"]), ("1.1", "1.1002", "1000000"))
        self.assertEqual(row["provenance"]["originalTimestamp"], "01.09.2026 00:00:00.001")
        self.assertEqual(row["provenance"]["memberHash"], source_pin(self.source)["sha256"])
        self.assertIsNone(row["trustedSequence"])
        self.assertEqual(row["quality"]["freshness"], "UNKNOWN")
        self.assertEqual(row["quality"]["gapBefore"], "UNKNOWN_SILENCE")
        self.assertEqual(result["coverage"], "UNVERIFIED")

    def test_crossed_quotes_preserved_as_crossed(self):
        self.source.write_text(HEADER + ROW.replace("1.10000", "1.2"), encoding="utf-8")
        imp = self.importer()
        self.assertEqual(self.rows(imp, imp.run())[0]["events"][0]["quality"]["quote"], "CROSSED")

    def test_invalid_rows_never_publish(self):
        variants = [ROW.replace(".001", ".0001"), ROW.replace("01.09", "31.09"),
            ROW.replace("01.09", "01.10"), ROW.replace("1.10020", "NaN"),
            ROW.replace("1.10020", "0"), ROW.replace("2.5,3", "-1,3"),
            ROW.replace("2.5,3", "Infinity,3"), "\n", '"unterminated\n', "a" * 8193 + "\n",
            ROW + ROW.replace(".001", ".000")]
        for i, bad in enumerate(variants):
            with self.subTest(i=i):
                self.source.write_text(HEADER + bad, encoding="utf-8")
                imp = self.importer(str(i), packing=(1, 1, 1))
                with self.assertRaises(ValueError): imp.run()
                self.assertEqual(imp.builder.store.db.execute("SELECT COUNT(*) FROM publications").fetchone()[0], 0)

    def test_header_month_symbol_and_empty_refused(self):
        for i, header in enumerate([HEADER.replace("Gmt time", "Local time"), HEADER.replace("BidVolume", "Bid"), HEADER.rstrip("\n") + ",extra\n"]):
            self.source.write_text(header + ROW, encoding="utf-8")
            with self.assertRaises(ValueError): self.importer(str(i))
        self.source.write_text(HEADER, encoding="utf-8")
        with self.assertRaises(ValueError): self.importer().run()
        for month in ("2026-13", "2026-9", "0000-01", "9999-12"):
            with self.assertRaises(ValueError): self.importer(month=month)
        with self.assertRaises(ValueError): self.importer(symbol="eurusd")

    def test_resume_deterministic_and_changed_source_refused(self):
        self.source.write_text(HEADER + "".join(ROW.replace(".001", f".{i:03}") for i in range(1, 10)), encoding="utf-8")
        imp = self.importer(packing=(2, 1, 1))
        with self.assertRaises(InterruptedError): imp.run(stop_after=5)
        imp.builder.store.close()
        self.resources.pop()
        resumed = self.importer(resume=True, packing=(2, 1, 1)).run()
        uninterrupted = self.importer("other", packing=(2, 1, 1)).run()
        self.assertEqual(resumed["datasetVersion"], uninterrupted["datasetVersion"])
        self.assertEqual(resumed["acceptedRows"], 9)
        with self.assertRaises(ValueError): self.importer(resume=True, packing=(2, 1, 1))
        imp = self.importer("changed", packing=(1, 1, 1))
        with self.assertRaises(InterruptedError): imp.run(stop_after=2)
        imp.builder.store.close()
        self.resources.pop()
        self.source.write_text(HEADER + ROW, encoding="utf-8")
        with self.assertRaises(ValueError): self.importer("changed", resume=True, packing=(1, 1, 1))

    def test_mutation_during_import_and_cancellation_do_not_publish(self):
        imp = self.importer()
        with patch("ticks.dukascopy_csv.source_pin", return_value=dict(imp.pin, sha256="f" * 64)):
            with self.assertRaises(ValueError): imp.run()
        self.assertEqual(imp.builder.store.db.execute("SELECT COUNT(*) FROM publications").fetchone()[0], 0)
        imp = self.importer("cancelled")
        with self.assertRaisesRegex(ValueError, "CANCELLED"): imp.run(cancellation=Cancellation(True))
        self.assertEqual(imp.builder.store.db.execute("SELECT COUNT(*) FROM publications").fetchone()[0], 0)

    def test_cli_offline_report_is_exclusive_and_only_after_success(self):
        import json
        import subprocess
        import sys
        report = self.root / "report.json"
        command = [sys.executable, "-B", "-m", "ticks.dukascopy_csv", "--source", str(self.source),
            "--store", str(self.root / "cli"), "--symbol", "EURUSD", "--month", "2026-09", "--report", str(report)]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        parsed = json.loads(report.read_text())
        self.assertEqual(parsed["acceptedRows"], 1)
        self.assertEqual(parsed["rights"], "UNVERIFIED")
        original = report.read_bytes()
        self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
        self.assertEqual(report.read_bytes(), original)
        report.unlink()
        self.source.write_text(HEADER + ROW.replace("01.09", "01.10"), encoding="utf-8")
        command[command.index("--store") + 1] = str(self.root / "cli-invalid")
        self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
        self.assertFalse(report.exists())

    def test_calendar_month_boundaries_and_leap_year(self):
        for i, (month, stamp) in enumerate([("2024-02", "29.02.2024 23:59:59.999"), ("2026-12", "31.12.2026 23:59:59.999")]):
            self.source.write_text(HEADER + ROW.replace("01.09.2026 00:00:00.001", stamp), encoding="utf-8")
            self.assertEqual(self.importer(str(i), month=month).run()["acceptedRows"], 1)


if __name__ == "__main__": unittest.main()
