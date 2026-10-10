"""Explicit private local real CSV ingestion/access/replay benchmark CLI."""
import argparse
import ctypes
import json
import os
from pathlib import Path
import time

from .exness_v2 import ExnessIngestion, parse_record, EPOCH, source_pin
from .storage_v2 import DiskTickProvider, ArtifactStore
from .timeline_v2 import IndexedTickTimeline


def memory():
    if os.name == "nt":
        class Counters(ctypes.Structure):
            _fields_ = [("cb",ctypes.c_ulong),("PageFaultCount",ctypes.c_ulong),
                        *[(k,ctypes.c_size_t) for k in ("PeakWorkingSetSize","WorkingSetSize","QuotaPeakPagedPoolUsage",
                        "QuotaPagedPoolUsage","QuotaPeakNonPagedPoolUsage","QuotaNonPagedPoolUsage","PagefileUsage","PeakPagefileUsage")]]
        psapi = ctypes.WinDLL("psapi",use_last_error=True)
        kernel = ctypes.WinDLL("kernel32",use_last_error=True)
        kernel.GetCurrentProcess.restype=ctypes.c_void_p
        psapi.GetProcessMemoryInfo.argtypes=[ctypes.c_void_p,ctypes.POINTER(Counters),ctypes.c_ulong]
        values=Counters(); values.cb=ctypes.sizeof(values)
        if psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(),ctypes.byref(values),values.cb):
            return dict(method="Windows GetProcessMemoryInfo cumulative peak working set", currentBytes=values.WorkingSetSize, peakBytes=values.PeakWorkingSetSize)
    return dict(method="unavailable",currentBytes=None,peakBytes=None)


def disk_size(folder):
    return sum(p.stat().st_size for p in Path(folder).rglob("*") if p.is_file())


def _benchmark(source, folder, report_path, *, resume=False, existing_version=None, dataset_folder=None):
    source, folder, report_path=Path(source),Path(folder),Path(report_path)
    folder.mkdir(parents=True,exist_ok=True)
    dataset = Path(dataset_folder) if dataset_folder is not None else folder/"dataset"
    report={"status":"RUNNING","sourceFilename":source.name,"rawUpload":False,"execution":False,"memoryMethod":memory()["method"]}
    def save():
        report_path.parent.mkdir(parents=True,exist_ok=True)
        report_path.write_text(json.dumps(report,indent=2),encoding="utf-8")
    save()  # A prior COMPLETE report must never survive a new failed attempt.
    start=time.perf_counter()
    if existing_version is None:
        ingestion=ExnessIngestion(source,dataset,resume=resume)
        starting_rows=ingestion.builder.s["count"]
        measurements=[]
        def progress(value):
            observation=dict(value,memory=memory(),diskBytes=disk_size(dataset))
            # At most 128 sampled observations. Never keep one record per tick.
            if len(measurements)<128:measurements.append(observation)
            print(json.dumps(dict(stage="INGESTING",**observation)),flush=True)
        try:
            result=ingestion.run(progress=progress)
            report["ingestion"]=result
            elapsed=time.perf_counter()-start
            report["ingestion"].update(startingAcceptedRows=starting_rows,
                processedRowsThisAttempt=result["acceptedRows"]-starting_rows,
                thisAttemptSecondsIncludingSourceHash=elapsed,
                totalSecondsIncludingSourceHash=elapsed if starting_rows == 0 else "NOT MEASURABLE: earlier attempt durations not recorded",
                throughputScope="new rows in this invocation; includes source hashing and full finalization",
                rowsPerSecond=(result["acceptedRows"]-starting_rows)/elapsed)
            report["ingestion"]["memory"]=memory()
            report["ingestion"]["scalingSamples"]=measurements
            report["ingestion"]["temporaryPeakDiskSampledBytes"]=max((s["diskBytes"] for s in measurements),default=0)
            version=result["datasetVersion"]
            report["storage"]=dict(finalBytes=disk_size(dataset),ratioToRaw=disk_size(dataset)/result["source"]["bytes"],
                                   physical="SQLite content-addressed zlib level-1 canonical payloads + disk UNIQUE indexes/journal; version materialized on read")
            db=ingestion.builder.store.db
            report["storage"]["artifacts"]={kind:count for kind,count in db.execute("SELECT kind,COUNT(*) FROM objects GROUP BY kind")}
            report["storage"]["compressedIndexPayloadBytes"]=db.execute("SELECT SUM(length(body)) FROM objects WHERE kind LIKE 'BTL-TICK-TIME-%'").fetchone()[0]
            report["storage"]["compressedTickPayloadBytes"]=db.execute("SELECT SUM(length(body)) FROM objects WHERE kind='BTL-TICK-STORAGE-CHUNK-2'").fetchone()[0]
            report["storage"]["compressedEvidencePayloadBytes"]=db.execute("SELECT COALESCE(SUM(length(body)),0) FROM objects WHERE kind LIKE 'BTL-TICK-EVIDENCE-%'").fetchone()[0]
            report["storage"]["compressedSourcePayloadBytes"]=db.execute("SELECT COALESCE(SUM(length(body)),0) FROM objects WHERE kind='BTL-TICK-SOURCE-CATALOG-2'").fetchone()[0]
            report["storage"]["identityRecords"]=db.execute("SELECT COUNT(*) FROM identities").fetchone()[0]
        except BaseException as exc:
            report.update(status="FAILED",error=repr(exc),partialAudit=ingestion.stats,committedRows=ingestion.builder.store.journal()["count"],memory=memory())
            save();raise
        finally:
            ingestion.builder.store.close()
        save()
    else:
        version=existing_version
        report["ingestion"]={"status":"NOT_RERUN","datasetVersion":version}
    p=DiskTickProvider(dataset,version)
    root=p.describe_v2(p.dataset_id,p.dataset_version)["root"]
    # An existing publication does not authorize comparing against a different
    # CSV, or claiming full counts from only representative seek matches.
    pin=source_pin(source)
    try:
        store=ArtifactStore(dataset)
        try:
            sources=store.get(root["sourceCatalogHash"],version)["sources"]
            if len(sources) != 1 or sources[0]["memberHash"] != pin["sha256"]:
                raise ValueError("SOURCE_CHANGED")
        finally:
            store.close()
    except BaseException:
        p.close();raise
    low,high=int(root["range"]["startNs"]),int(root["range"]["endNs"])-1
    report["access"]=[]
    targets = (("before-first",max(0,low-1)),("exact-first",low),("between-early",low+1),
               ("early",low+(high-low)//10),("middle",(low+high)//2),
               ("late",low+9*(high-low)//10),("near-end",max(low,high-1)),("exact-last",high),("after-last",high+1))
    # Independent streaming raw-source lower bound, not storage/index metadata.
    from datetime import datetime
    expected = {}
    ordered = sorted(targets, key=lambda pair:pair[1])
    next_target, ordinal, cached_stamp, cached_time = 0, 0, None, None
    scan_started = time.perf_counter()
    with source.open("rb") as stream:
        stream.readline(8193)
        for raw in stream:
            row = parse_record(raw)
            if row["Timestamp"] != cached_stamp:
                dt = datetime.fromisoformat(row["Timestamp"].replace("Z", "+00:00"))-EPOCH
                cached_stamp, cached_time = row["Timestamp"], (dt.days*86400+dt.seconds)*1000000000
            while next_target < len(ordered) and ordered[next_target][1] <= cached_time:
                expected[ordered[next_target][0]] = (str(cached_time), str(ordinal))
                next_target += 1
            ordinal += 1
    for name,_ in ordered[next_target:]:expected[name]=(None,None)
    report["referenceScan"] = dict(sourceRows=ordinal,elapsedSeconds=time.perf_counter()-scan_started,
                                   method="independent full source-order CSV scan; first ordinal >= each target")
    if ordinal != int(root["eventCount"]):
        p.close();raise ValueError("SOURCE_COUNT_CONFLICT")
    for name,target in targets:
        reader=DiskTickProvider(dataset,version)
        opened=time.perf_counter()
        located=reader.locate_v2(reader.dataset_id,version,str(target));seek=time.perf_counter()-opened
        if (located["groupTimeNs"],None if located["position"] is None else located["position"]["globalOrdinal"]) != expected[name]:
            raise ValueError("REFERENCE_SCAN_MISMATCH")
        if located != reader.locate_v2(reader.dataset_id,version,str(target)):raise ValueError("NONDETERMINISTIC_POSITION")
        opened=time.perf_counter();page=reader.read_page_v2(reader.dataset_id,version,located["position"],256);read=time.perf_counter()-opened
        opened=time.perf_counter()
        for _ in range(10):reader.locate_v2(reader.dataset_id,version,str(target))
        warm=(time.perf_counter()-opened)/10
        opened=time.perf_counter();position=located["position"];events=0
        for _ in range(100):
            if position is None:break
            r=reader.read_page_v2(reader.dataset_id,version,position,256);events+=len(r["events"]);position=r["nextPosition"]
        sequential=time.perf_counter()-opened
        timeline=IndexedTickTimeline(reader,reader.dataset_id,version,str(target),log_folder=folder/("first-group-"+name))
        opened=time.perf_counter();first=timeline.next_group(timeline.cursor);group_latency=time.perf_counter()-opened
        timeline.close();reader.close()
        observation=dict(position=name,targetNs=str(target),firstUseLookupSeconds=seek,warmLookupMeanSeconds=warm,
                         boundedPageSeconds=read,pageEvents=len(page["events"]),firstAtomicGroupSeconds=group_latency,
                         firstAtomicGroupEvents=sum(len(g["events"]) for g in first["groups"]),sequentialEvents=events,
                         sequentialSeconds=sequential,sequentialEventsPerSecond=events/sequential,memory=memory(),
                         referenceScanMatches=True,repeatPositionMatches=True,
                         cacheNote="fresh provider cache; OS cache not flushed, not a claimed cold-disk test")
        report["access"].append(observation);print(json.dumps(dict(stage="ACCESS",**observation)),flush=True);save()
    report["replay"]=[]
    # Start at the first observed timestamp; durations are not calendar certification.
    for name,seconds in (("minute",60),("hour",3600),("day",86400)):
        t=IndexedTickTimeline(p,p.dataset_id,version,str(low),log_folder=folder/("replay-"+name))
        opened=time.perf_counter();events=groups=steps=0;last_update=opened
        target=str(low+seconds*1000000000)
        while True:
            r=t.advance_through(target,t.cursor);steps+=1;groups+=len(r["groups"]);events+=sum(len(g["events"]) for g in r["groups"])
            if time.perf_counter()-last_update>20:
                print(json.dumps(dict(stage="REPLAY_PROGRESS",window=name,events=events,groups=groups,elapsed=time.perf_counter()-opened)),flush=True);last_update=time.perf_counter()
            if r["exhaustedThroughBoundary"]:break
        elapsed=time.perf_counter()-opened
        observation=dict(window=name,seconds=seconds,events=events,atomicGroups=groups,steps=steps,elapsedSeconds=elapsed,
                         eventsPerSecond=events/elapsed,memory=memory(),gapPolicy="observed quotes only; no completeness/session-closure claim")
        report["replay"].append(observation);t.close();print(json.dumps(dict(stage="REPLAY",**observation)),flush=True);save()
    p.close()
    if source_pin(source) != pin:raise ValueError("SOURCE_CHANGED")
    report["status"]="COMPLETE";report["memory"]=memory()
    report["totalBenchmarkSeconds"]=time.perf_counter()-start
    report["datasetFootprintBytes"]=disk_size(dataset)
    report["totalOutputFootprintBytes"]=disk_size(folder)+(disk_size(dataset) if not dataset.resolve().is_relative_to(folder.resolve()) else 0)
    save()
    return report


def benchmark(source, folder, report_path, *, resume=False, existing_version=None, dataset_folder=None):
    try:
        return _benchmark(source, folder, report_path, resume=resume, existing_version=existing_version,
                          dataset_folder=dataset_folder)
    except BaseException as exc:
        path = Path(report_path)
        report = json.loads(path.read_text(encoding="utf-8")) if path.exists() and path.stat().st_size <= 4194304 else {}
        report.update(status="INTERRUPTED" if isinstance(exc, KeyboardInterrupt) else "FAILED", error=repr(exc))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        raise


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--source",required=True);parser.add_argument("--store",required=True);parser.add_argument("--report",required=True)
    parser.add_argument("--resume",action="store_true");parser.add_argument("--existing-version")
    parser.add_argument("--dataset-folder",help="Existing private accepted store; no copy or re-ingestion")
    args=parser.parse_args();benchmark(args.source,args.store,args.report,resume=args.resume,existing_version=args.existing_version,dataset_folder=args.dataset_folder)
