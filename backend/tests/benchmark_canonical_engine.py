"""Bounded canonical Monthly Parquet → execution engine benchmark.

SYNTHETIC / TEST ONLY. This deliberately uses the existing controller,
TickTimeline, Jump scanner and financial reducer. It does not benchmark a
browser, durable queue, PostgreSQL, broker, or historical market data.

Run from backend/ with the repository's pinned test dependencies:
    python -m tests.benchmark_canonical_engine --events 4096 --repeats 3
The product fixture controller caps this mode at 4,096 events. Larger
Parquet-only scans are not engine-throughput evidence.
"""
import argparse
import cProfile
from copy import deepcopy
import io
import json
from pathlib import Path
import resource
import pstats
import statistics
import sys
import tempfile
from time import perf_counter, process_time

from application.models import TrustedScope
from contracts.canonical import canonical_bytes, content_hash
from contracts.models import MethodPolicy
from execution.analysis import project
from execution.controller import ExecutionController
from execution.contracts import command_wire, seed_state
from execution.engine import advance, submit
from execution.fixture_demo import fixture_profile
from execution.jump_next_event import advance_command
from execution.workspace import FixtureTimelineCache
from market_data.monthly_parquet import MonthlyParquetProvider, write_monthly_parquet
from ticks.timeline import TickTimeline
from tests.synthetic_monthly_perf import build_dataset, GENERATOR_VERSION, SEED
from tests.test_tick_execution import MemoryStore


MAX_CONTROLLER_EVENTS = 4096
MAX_ENGINE_DATASET_EVENTS = 65_536
PROFILE = fixture_profile()
PROFILE["tickSize"] = "0.00001"
PROFILE["priceScale"] = "100000"
POLICY = MethodPolicy("fixture:free", "0" * 64, "FREE_STYLE", False, ())


def _io_counters():
    try:
        values = {}
        for line in Path("/proc/self/io").read_text().splitlines():
            name, value = line.split(":", 1)
            values[name] = int(value.strip())
        return values
    except (OSError, ValueError):
        return {}


def _new_run(provider, mode, target_ns=None):
    setup_wall, setup_cpu = perf_counter(), process_time()
    store = MemoryStore()
    scope = TrustedScope("fixture:engine-benchmark", "fixture:synthetic-owner")
    session = "synthetic:engine-benchmark-session"
    cache = FixtureTimelineCache(provider, allow_injected_synthetic=True)
    controller = ExecutionController(store, provider, cache)
    controller.create(scope, session, PROFILE, POLICY)
    first = next(provider.iter_range(int(provider.describe(provider.dataset_id,
        provider.dataset_version)["range"]["startNs"]),
        int(provider.describe(provider.dataset_id, provider.dataset_version)["range"]["endNs"])))
    entry = first["ask"]
    from decimal import Decimal
    entry_value = Decimal(entry)
    command = dict(schemaVersion=1, artifact="BTL-TICK-EXECUTION-COMMAND-1",
        sessionId=session, commandId="synthetic:open", expectedRevision=0, kind="OPEN",
        payload=dict(side="LONG", orderType="MARKET", workflow="QUICK", entry=entry,
            quantity="0.01", sl=format(entry_value - Decimal("0.01"), "f"),
            tp=format(entry_value + Decimal("0.01"), "f"), riskPercent="1", observations=[]))
    controller.apply(scope, command)
    setup = dict(wallSeconds=perf_counter() - setup_wall,
        cpuSeconds=process_time() - setup_cpu)

    all_events = []
    preview_groups = 0
    replay_wall, replay_cpu = perf_counter(), process_time()
    if mode == "jump":
        end_ns = str(int(provider.describe(provider.dataset_id, provider.dataset_version)["range"]["endNs"]) - 1)
        for index in range(32):
            state, checkpoint = store.sessions[(scope.workspace_id, session)]
            request = dict(schemaVersion=1, artifact="BTL-JUMP-NEXT-EVENT-1",
                requestId=f"{index:032x}", sessionId=session,
                expectedRevision=state["revision"], timeframe="1m")
            preview = controller.preview_next_event(scope, state, checkpoint, end_ns)
            preview_groups += preview["previewGroups"]
            command = advance_command({**request, "targetNs": preview["targetNs"]},
                state["revision"], "BTL-TICK-EXECUTION-COMMAND-1")
            receipt = controller.apply(scope, command)
            all_events.extend(receipt["events"])
            if any(event["kind"] in ("EXIT_FILL", "UNRESOLVED") for event in all_events):
                break
        else:
            raise RuntimeError("Jump did not reach a terminal financial boundary within 32 requests")
    elif mode == "normal":
        if target_ns is None:
            raise ValueError("normal replay requires the Jump-discovered event boundary")
        index = 0
        while True:
            state, _checkpoint = store.sessions[(scope.workspace_id, session)]
            command = dict(schemaVersion=1, artifact="BTL-TICK-EXECUTION-COMMAND-1",
                sessionId=session, commandId=f"synthetic:normal-advance:{index}",
                expectedRevision=state["revision"], kind="ADVANCE",
                payload={"targetNs": str(target_ns)})
            receipt = controller.apply(scope, command)
            all_events.extend(receipt["events"])
            replay = receipt["replay"] or {}
            if any(event["kind"] in ("EXIT_FILL", "UNRESOLVED") for event in all_events):
                break
            if replay.get("exhaustedThroughBoundary"):
                break
            index += 1
            if index >= 32:
                raise RuntimeError("Normal replay exceeded 32 bounded advances")
    replay = dict(wallSeconds=perf_counter() - replay_wall,
        cpuSeconds=process_time() - replay_cpu, previewGroups=preview_groups)

    analysis_wall, analysis_cpu = perf_counter(), process_time()
    inspected = controller.inspect(scope, session, maximum=256)
    state = inspected["state"]
    all_committed_events = inspected["events"]
    financial_events = [event for event in all_committed_events
        if event["classification"] == "SIMULATED_FILL"]
    analytics = project(state, all_committed_events, None)
    normalized_state = {key: deepcopy(value) for key, value in state.items()
        if key not in ("revision",)}
    receipt_evidence_hash = content_hash(dict(schemaVersion=1,
        artifact="BTL-SYNTHETIC-FINANCIAL-OUTCOME-1", events=financial_events))
    analytics_evidence = dict(schemaVersion=1, artifact="BTL-SYNTHETIC-ANALYTICS-PARITY-1",
        account=analytics["account"], orders=analytics["orders"], metrics=analytics["metrics"])
    parity = dict(stateHash=content_hash(normalized_state), eventHead=state["eventHash"],
        financialEventsHash=receipt_evidence_hash, analyticsHash=content_hash(analytics_evidence),
        balance=state["balance"], realizedGross=state["realizedGross"],
        closedTrades=analytics["metrics"]["tradeCount"],
        fillCount=len(financial_events))
    analysis = dict(wallSeconds=perf_counter() - analysis_wall,
        cpuSeconds=process_time() - analysis_cpu)
    return dict(state=state, events=all_committed_events, parity=parity,
        stages=dict(setup=setup, replay=replay, committedReadAndAnalytics=analysis),
        throughNs=state["throughNs"], groupIndex=int(state["nextGroupIndex"]))


def _measure(provider, mode, target_ns=None):
    io_before = _io_counters()
    rss_before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    cpu_before, wall_before = process_time(), perf_counter()
    result = _new_run(provider, mode, target_ns)
    wall, cpu = perf_counter() - wall_before, process_time() - cpu_before
    rss_after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    io_after = _io_counters()
    return result, dict(mode=mode, wallSeconds=wall, cpuSeconds=cpu,
        tickGroupsCommitted=result["groupIndex"],
        stages=result["stages"],
        peakRssKiB=max(rss_before, rss_after),
        processIoRcharBytes=(io_after.get("rchar", 0) - io_before.get("rchar", 0)),
        processIoReadBytes=(io_after.get("read_bytes", 0) - io_before.get("read_bytes", 0)))


def _engine_only_full_replay(provider, *, profile=False, progress=False):
    """Stream all Parquet events through canonical Timeline and reducer."""
    start_cpu, start_wall = process_time(), perf_counter()
    manifest = provider.describe(provider.dataset_id, provider.dataset_version)
    start_ns = manifest["range"]["startNs"]
    timeline = TickTimeline(provider, provider.dataset_id, provider.dataset_version, start_ns)
    state = seed_state("synthetic:engine-only-session", provider.dataset_id,
        provider.dataset_version, start_ns, PROFILE, POLICY)
    opening = command_wire(dict(schemaVersion=1, artifact="BTL-TICK-EXECUTION-COMMAND-1",
        sessionId=state["sessionId"], commandId="synthetic:engine-only-open",
        expectedRevision=0, kind="OPEN", payload=dict(side="LONG", orderType="MARKET",
            workflow="QUICK", entry="1.08065", quantity="0.01", sl="1.00000",
            tp="2.00000", riskPercent="1", observations=[])))
    state, events = submit(state, opening)
    setup = dict(wallSeconds=perf_counter() - start_wall,
        cpuSeconds=process_time() - start_cpu)

    io_before = _io_counters()
    rss_before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    replay_cpu, replay_wall = process_time(), perf_counter()
    profiler = cProfile.Profile() if profile else None
    if profiler:
        profiler.enable()
    end_ns = str(int(manifest["range"]["endNs"]) - 1)
    ticks = groups = batches = 0
    while True:
        ack = timeline.advance_through(end_ns, timeline.cursor)
        state, committed = advance(state, ack["groups"], ack["coverage"],
            ack["diagnostics"], ack["throughNs"])
        events.extend(committed)
        count = sum(len(group["events"]) for group in ack["groups"])
        ticks += count
        groups += len(ack["groups"])
        batches += 1
        if progress and batches % 32 == 0:
            elapsed = perf_counter() - replay_wall
            print(json.dumps(dict(label="SYNTHETIC / TEST ONLY", progress=True,
                ticksProcessed=ticks, groupsProcessed=groups, batches=batches,
                elapsedSeconds=round(elapsed, 3), ticksPerSecond=round(ticks / elapsed, 2),
                processRssKiB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),
                sort_keys=True), file=sys.stderr, flush=True)
        if ack["exhaustedThroughBoundary"]:
            break
        if batches > 2048:
            raise RuntimeError("canonical replay exceeded the bounded batch guard")
    if profiler:
        profiler.disable()
    replay_wall_seconds = perf_counter() - replay_wall
    replay_cpu_seconds = process_time() - replay_cpu
    io_after = _io_counters()
    rss_after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    analytics = project(state, events, None)
    profile_output = None
    if profiler:
        output = io.StringIO()
        pstats.Stats(profiler, stream=output).sort_stats("cumtime").print_stats(15)
        profile_output = output.getvalue()
    return dict(label="SYNTHETIC / TEST ONLY", mode="engine-only full chronological replay",
        execution="canonical TickTimeline + existing submit/advance reducer; no controller fixture-size bypass",
        setup=setup, replay=dict(wallSeconds=replay_wall_seconds,
            cpuSeconds=replay_cpu_seconds, ticksProcessed=ticks, groupsProcessed=groups,
            batches=batches, ticksPerSecond=ticks / replay_wall_seconds,
            peakRssKiB=max(rss_before, rss_after),
            processIoRcharBytes=io_after.get("rchar", 0) - io_before.get("rchar", 0),
            processIoReadBytes=io_after.get("read_bytes", 0) - io_before.get("read_bytes", 0)),
        outcome=dict(balance=state["balance"], realizedGross=state["realizedGross"],
            eventHead=state["eventHash"], analyticsHash=content_hash(dict(schemaVersion=1,
                artifact="BTL-SYNTHETIC-ANALYTICS-PARITY-1", account=analytics["account"],
                orders=analytics["orders"], metrics=analytics["metrics"]))),
        cProfileTop=profile_output,
        warning="Engine-only in-memory state; no queue, durable receipts, PostgreSQL, browser, or exclusive CPU reservation.")


def run(events_count=4096, repeats=3, mode="ab", profile=False, progress=False):
    maximum = MAX_CONTROLLER_EVENTS if mode == "ab" else MAX_ENGINE_DATASET_EVENTS
    if type(events_count) is not int or not 512 <= events_count <= maximum:
        raise ValueError(f"{mode} benchmark supports 512..{maximum} events")
    if type(repeats) is not int or not 1 <= repeats <= 3:
        raise ValueError("repeats must be 1..3")
    source_manifest, events = build_dataset(events_count)
    with tempfile.TemporaryDirectory(prefix="riksora-engine-bench-") as temporary:
        root = Path(temporary) / "monthly"
        parquet_manifest = write_monthly_parquet(root, iter(events), source_manifest,
            expected_version=events[0]["datasetVersion"], row_group_size=512)
        provider = MonthlyParquetProvider(root,
            expected_dataset_id=source_manifest["datasetId"],
            expected_dataset_version=events[0]["datasetVersion"],
            expected_manifest_hash=parquet_manifest["manifestHash"])
        file_bytes = sum(item["bytes"] for item in parquet_manifest["files"])
        if mode == "engine-replay":
            result = _engine_only_full_replay(provider, profile=profile, progress=progress)
            result.update(generatorVersion=GENERATOR_VERSION, seed=SEED,
                datasetId=source_manifest["datasetId"], datasetVersion=events[0]["datasetVersion"],
                sourceManifestHash=content_hash(source_manifest),
                parquetManifestHash=parquet_manifest["manifestHash"],
                files=[dict(month=item["month"], bytes=item["bytes"], sha256=item["sha256"],
                    rowGroups=len(item["rowGroups"])) for item in parquet_manifest["files"]],
                eventCount=events_count, parquetBytes=file_bytes)
            print(json.dumps(result, sort_keys=True, indent=2))
            return result
        jump_probe, jump_probe_metrics = _measure(provider, "jump")
        target_ns = jump_probe["throughNs"]
        replay_rows, jump_rows = [], []
        jump_rows.append(jump_probe_metrics)
        parity = jump_probe["parity"]
        if parity["closedTrades"] != 1 or parity["fillCount"] != 2:
            raise AssertionError("synthetic workload did not produce one committed closed trade")
        for iteration in range(repeats):
            normal, normal_metrics = _measure(provider, "normal", target_ns)
            if normal["parity"] != parity:
                raise AssertionError("normal replay and Jump financial parity diverged")
            replay_rows.append(normal_metrics)
            if iteration + 1 < repeats:
                jumped, jump_metrics = _measure(provider, "jump")
                if jumped["parity"] != parity:
                    raise AssertionError("repeated Jump outcome was not deterministic")
                jump_rows.append(jump_metrics)
        def describe(rows, field):
            values = [row[field] for row in rows]
            return dict(median=statistics.median(values), minimum=min(values), maximum=max(values))

        summary = dict(repetitionsPerPath=repeats,
            replayWallSeconds=describe(replay_rows, "wallSeconds"),
            jumpWallSeconds=describe(jump_rows, "wallSeconds"),
            replayCpuSeconds=describe(replay_rows, "cpuSeconds"),
            jumpCpuSeconds=describe(jump_rows, "cpuSeconds"),
            replayStageWallSeconds=describe([row["stages"]["replay"] for row in replay_rows], "wallSeconds"),
            jumpStageWallSeconds=describe([row["stages"]["replay"] for row in jump_rows], "wallSeconds"),
            normalOverJumpWallSpeedup=statistics.median(
                [row["wallSeconds"] for row in replay_rows]) / statistics.median(
                [row["wallSeconds"] for row in jump_rows]))
        result = dict(label="SYNTHETIC / TEST ONLY",
            benchmark="canonical ExecutionController + TickTimeline + financial reducer; in-memory commit adapter",
            generatorVersion=GENERATOR_VERSION, seed=SEED, datasetId=source_manifest["datasetId"],
            datasetVersion=events[0]["datasetVersion"], sourceManifestHash=source_manifest["sourceManifestHash"]
                if "sourceManifestHash" in source_manifest else content_hash(source_manifest),
            parquetManifestHash=parquet_manifest["manifestHash"],
            files=[dict(month=item["month"], bytes=item["bytes"], sha256=item["sha256"],
                rowGroups=len(item["rowGroups"])) for item in parquet_manifest["files"]],
            eventCount=events_count, parquetBytes=file_bytes, targetBoundaryNs=target_ns,
            repetitions=repeats, summary=summary, replay=replay_rows, jump=jump_rows,
            parityHashes=parity, warning=("No PostgreSQL, durable queue, worker, browser, exclusive CPU reservation, "
                "or cold-cache eviction is included. Process I/O counters may reflect filesystem cache behavior."))
        print(json.dumps(result, sort_keys=True, indent=2))
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=int, default=4096)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--mode", choices=("ab", "engine-replay"), default="ab")
    parser.add_argument("--profile", action="store_true",
        help="collect cProfile hot functions; the profiled run is not a throughput measurement")
    parser.add_argument("--progress", action="store_true",
        help="write bounded engine replay progress records to stderr")
    args = parser.parse_args()
    run(args.events, args.repeats, args.mode, args.profile, args.progress)


if __name__ == "__main__":
    main()
