"""Source registry for research Sessions: authored demos plus owner-admitted months.

Without a registry file only the authored synthetic demos exist (unchanged).
`BTL_ADMISSION_REGISTRY` may name a private JSON file listing admission
records (see `admission_v2`) and the accepted monthly store folders behind
them. Store folders and handles stay controller-side; the catalog shows
symbols, periods and labels only.

Build a registry from full-file HistData intake reports with
`python -B -m execution.registry_v2 --out registry.json --entry SYMBOL STORE REPORT [STORE REPORT ...]`,
or run intake and build in one step with
`python -B -m execution.registry_v2 --out registry.json --source-dir CONVERTED --work-dir PRIVATE --window 2024-11 2025-09 --skip 2024-10 2025-10`.
A non-USD quote symbol needs its conversion route symbol (GBPUSD, NZDUSD,
USDJPY, USDCAD or USDCHF) in the same registry for all of its months.
"""
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path

from contracts.primitives import ContractError, require
from market_data.instruments import INSTRUMENTS, instrument
from ticks.contracts import keys, tag
from ticks.storage_v2 import DiskTickProvider
from .admission_v2 import AdmittedSource, AdmittedSourceJoin, admission_record, admitted_conversion_pin, admitted_source_pin, LABEL
from .conversion import conversion_route
from .profile_v2 import ExecutionProfileV2, ADMITTED_MODEL, SYNTHETIC_MODEL
from .research_fixture_v2 import bundle as fixture_bundle, START_NS, PERIOD
from .sources_v2 import SourceJoinV2

REGISTRY = "BTL-ADMISSION-REGISTRY-1"
INTAKE_STATUS = "STRUCTURAL_PUBLICATION_ONLY_NOT_EXECUTION_ACCEPTANCE"
SYNTHETIC_LABEL = "SHORT SYNTHETIC DEMO; NOT HISTORICAL MONTH"


@dataclass(frozen=True)
class SourceBundle:
    profile: ExecutionProfileV2
    primary: object
    conversion: object
    join: type
    start_ns: int


def route_symbol(symbol):
    quote = instrument(symbol).quote
    return None if quote == "USD" else conversion_route(quote)[0]


def admitted_profile(record, records):
    """Synthetic demo profile terms (tick size, contract, lots) with admission pins.

    A non-USD quote needs its route symbol admitted for every primary month."""
    symbol, conversion = record["symbol"], None
    route = route_symbol(symbol)
    if route is not None:
        fx = records.get(route)
        require(fx is not None and {m["period"] for m in record["months"]} <= {m["period"] for m in fx["months"]},
                "conversion", "REFUSED_ADMISSION_ROUTE")
        conversion = admitted_conversion_pin(fx, instrument(symbol).quote)
    raw = dict(fixture_bundle(symbol).profile.wire, model=ADMITTED_MODEL, primary=admitted_source_pin(record), conversion=conversion)
    return ExecutionProfileV2.from_wire(raw)


class Registry:
    def __init__(self, path=None):
        self.__entries, self.__open = {}, {}
        if path is None:
            return
        path = Path(path)
        raw = json.loads(path.read_text())
        tag(raw, REGISTRY, "entries")
        require(type(raw["entries"]) is list and len(raw["entries"]) <= len(INSTRUMENTS), "entries", "REFUSED_ADMISSION")
        for entry in raw["entries"]:
            keys(entry, "record folders")
            record = admission_record(entry["record"]["symbol"], entry["record"]["months"])
            require(record == entry["record"] and record["symbol"] not in self.__entries, "record", "REFUSED_ADMISSION")
            require(type(entry["folders"]) is list and all(type(f) is str for f in entry["folders"]), "folders", "REFUSED_ADMISSION")
            self.__entries[record["symbol"]] = (record, [path.parent / f for f in entry["folders"]], None)
        records = {s: e[0] for s, e in self.__entries.items()}
        for s, (record, folders, _) in list(self.__entries.items()):
            self.__entries[s] = (record, folders, admitted_profile(record, records))

    def close(self):
        for source in self.__open.values():
            source.close()
        self.__open = {}

    def __source(self, symbol):
        if symbol not in self.__open:
            record, folders, _ = self.__entries[symbol]
            self.__open[symbol] = AdmittedSource(record, folders)
        return self.__open[symbol]

    def catalogue(self):
        rows = []
        for s, v in INSTRUMENTS.items():
            if s in self.__entries:
                periods = [m["period"] for m in self.__entries[s][0]["months"]]
                rows.append(dict(symbol=s, baseCurrency=v.base, quoteCurrency=v.quote, model=ADMITTED_MODEL, label=LABEL,
                                 dataLabel="Historical · beta", startPeriod=periods[0], periods=periods))
            else:
                rows.append(dict(symbol=s, baseCurrency=v.base, quoteCurrency=v.quote, model=SYNTHETIC_MODEL,
                                 label=SYNTHETIC_LABEL, startPeriod=PERIOD))
        return rows

    def session_bundle(self, symbol, period):
        """Source for a new Session; admitted symbols start at the chosen admitted month."""
        instrument(symbol)
        if symbol not in self.__entries:
            require(period == PERIOD, "period", "REFUSED_FIXTURE_PERIOD")
            b = fixture_bundle(symbol)
            return SourceBundle(b.profile, b.primary, b.conversion, SourceJoinV2, START_NS)
        source = self.__source(symbol)
        try:
            start = source.start_for_period(period)
        except ContractError:
            raise ContractError("REFUSED_HISTDATA_PERIOD", "period") from None
        return SourceBundle(self.__entries[symbol][2], source, self.__conversion(symbol), AdmittedSourceJoin, start)

    def binding(self, profile):
        """Source for a stored Session; the profile hash must match what is registered now."""
        parsed = ExecutionProfileV2.from_wire(profile)
        symbol = parsed.wire["symbol"]
        if parsed.wire["model"] == SYNTHETIC_MODEL:
            b = fixture_bundle(symbol)
            require(b.profile.profile_hash == parsed.profile_hash, "source", "SOURCE_VERSION_UNAVAILABLE")
            return SourceBundle(b.profile, b.primary, b.conversion, SourceJoinV2, START_NS)
        entry = self.__entries.get(symbol)
        require(entry is not None and entry[2].profile_hash == parsed.profile_hash, "source", "SOURCE_VERSION_UNAVAILABLE")
        source = self.__source(symbol)
        return SourceBundle(entry[2], source, self.__conversion(symbol), AdmittedSourceJoin, source.start_ns)

    def __conversion(self, symbol):
        route = route_symbol(symbol)
        return None if route is None else self.__source(route)

    def period_allowed(self, profile, period):
        """Stored Session metadata check, from the Session's own pinned source.

        Independent of what is registered now, so withdrawing a registry never
        turns stored Sessions into corrupt records."""
        if profile["model"] == SYNTHETIC_MODEL:
            return period == PERIOD
        first, last = profile["primary"]["datasetId"].split(":")[-2:]
        return type(period) is str and len(period) == 7 and first <= period <= last


_DEFAULT = None


def default_registry():
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = Registry(os.environ.get("BTL_ADMISSION_REGISTRY") or None)
    return _DEFAULT


def month_from_intake(store, report_path):
    """Admission month from a full-file HistData intake report and its store."""
    blob = Path(report_path).read_bytes(); report = json.loads(blob)
    require(type(report) is dict and report.get("status") == INTAKE_STATUS
            and report.get("sourceSelection", {}).get("kind") == "FULL_FILE", "report", "REFUSED_ADMISSION_REPORT")
    first, last = report["firstTimestamp"], report["lastTimestamp"]
    require(type(first) is str and type(last) is str and first[:7] == last[:7], "report", "REFUSED_ADMISSION_REPORT")
    provider = DiskTickProvider(store, report["datasetVersion"])
    try:
        provider.describe_v2(report["datasetId"], report["datasetVersion"])
    finally:
        provider.close()
    return dict(period=first[:7], datasetId=report["datasetId"], datasetVersion=report["datasetVersion"],
                validationReportHash=hashlib.sha256(blob).hexdigest())


def _periods(first, last):
    out = [first]
    while out[-1] != last:
        y, m = int(out[-1][:4]), int(out[-1][5:])
        out.append(f"{y + m // 12:04d}-{m % 12 + 1:02d}")
        require(len(out) <= 120, "window", "REFUSED_ADMISSION")
    return out


def intake_window(source_dir, work_dir, symbols, first, last, *, skip=()):
    """Full-file intake of SYMBOL_YYYY-MM.csv.gz for each month, reusing finished reports.

    Returns {symbol: [(store, report), ...]} for the longest consecutive run of
    accepted months, plus a per-month outcome log. Refused months stay refused."""
    from ticks.histdata_v2 import HistDataIngestion
    source_dir, work_dir = Path(source_dir), Path(work_dir)
    accepted, log = {}, {}
    for symbol in symbols:
        instrument(symbol); ok = []
        for period in _periods(first, last):
            store, report = work_dir / "stores" / f"{symbol}-{period}", work_dir / "reports" / f"{symbol}-{period}.json"
            source = source_dir / f"{symbol}_{period}.csv.gz"
            if period in skip:
                log[f"{symbol} {period}"] = "SKIPPED_BY_OWNER"; ok.append(None); continue
            if not report.exists():
                if not source.exists():
                    log[f"{symbol} {period}"] = "NO_SOURCE_FILE"; ok.append(None); continue
                report.parent.mkdir(parents=True, exist_ok=True)
                try:
                    with HistDataIngestion(source, store, symbol, first_rows=None) as job:
                        result = job.run()
                except (ContractError, ValueError, EOFError, OSError) as error:
                    result = dict(status="REFUSED_NOT_PUBLISHED", code=getattr(error, "code", type(error).__name__))
                report.write_text(json.dumps(result, indent=2))
            result = json.loads(report.read_text())
            if result.get("status") != INTAKE_STATUS:
                log[f"{symbol} {period}"] = "REFUSED " + str(result.get("code")); ok.append(None); continue
            log[f"{symbol} {period}"] = "ACCEPTED"; ok.append((str(store), str(report)))
        best, run = [], []
        for item in ok + [None]:
            if item is None:
                best, run = (run if len(run) > len(best) else best), []
            else:
                run.append(item)
        if best:
            accepted[symbol] = best
    return accepted, log


def build(out, groups, *, strict=False):
    """Write a registry for {symbol: [(store, report), ...]}; crosses without a full route are left out."""
    out = Path(out).resolve(); entries = {}
    for symbol, pairs in groups.items():
        stores = [Path(s).resolve() for s, _ in pairs]
        months = [month_from_intake(s, r) for s, (_, r) in zip(stores, pairs)]
        record = admission_record(symbol, months)
        source = AdmittedSource(record, stores); source.close()
        entries[symbol] = dict(record=record, folders=[os.path.relpath(s, out.parent) for s in stores])
    records = {s: e["record"] for s, e in entries.items()}
    left_out = {}
    for symbol in list(entries):
        try:
            admitted_profile(records[symbol], records)
        except ContractError as error:
            left_out[symbol] = error.code
    if strict and left_out:
        raise ContractError(next(iter(left_out.values())), "conversion")
    kept = [e for s, e in entries.items() if s not in left_out]
    require(kept, "entries", "REFUSED_ADMISSION")
    with out.open("x") as handle:
        json.dump(dict(schemaVersion=1, artifact=REGISTRY, entries=kept), handle, indent=2)
    return {e["record"]["symbol"]: [m["period"] for m in e["record"]["months"]] for e in kept}, left_out


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description="Build a private admission registry from full-file intake reports.")
    parser.add_argument("--out", required=True)
    parser.add_argument("--entry", nargs="+", action="append", metavar="SYMBOL STORE REPORT")
    parser.add_argument("--source-dir", help="folder of converted SYMBOL_YYYY-MM.csv.gz files; runs intake first")
    parser.add_argument("--work-dir", help="private folder for stores/ and reports/ (with --source-dir)")
    parser.add_argument("--window", nargs=2, metavar=("FIRST", "LAST"))
    parser.add_argument("--symbols", nargs="+", default=sorted(INSTRUMENTS))
    parser.add_argument("--skip", nargs="*", default=[], metavar="YYYY-MM")
    args = parser.parse_args(argv)
    if args.source_dir:
        require(args.work_dir and args.window and not args.entry, "arguments", "REFUSED_ADMISSION")
        groups, log = intake_window(args.source_dir, args.work_dir, args.symbols, *args.window, skip=set(args.skip))
    else:
        require(bool(args.entry), "entry", "REFUSED_ADMISSION")
        groups, log = {}, {}
        for symbol, *pairs in args.entry:
            require(pairs and len(pairs) % 2 == 0 and symbol not in groups, "entry", "REFUSED_ADMISSION")
            groups[symbol] = list(zip(pairs[0::2], pairs[1::2]))
    admitted, left_out = build(args.out, groups, strict=not args.source_dir)
    print(json.dumps(dict(months=log, admitted=admitted, leftOut=left_out), indent=2) if args.source_dir else json.dumps(admitted))


if __name__ == "__main__":
    main()
