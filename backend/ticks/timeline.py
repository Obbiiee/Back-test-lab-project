"""Controller-owned replay; consumers hold only the revealed-view capability.

No candles, fills, accounts, PnL, filesystem or network. Provider is private to
controller; each forward step streams pages, never copies the entire dataset.
"""
from copy import deepcopy
from itertools import groupby, islice, chain
import json

from contracts.canonical import canonical_bytes, content_hash
from contracts.primitives import require
from .contracts import uint, keys, tag, validate_chunk, CanonicalTick
from .provider import Cancellation, validate_provider, empty_diagnostics, diagnostic_counts


TIMELINE_VERSION = "BTL-TICK-TIMELINE-1"
CURSOR_FIELDS="datasetId datasetVersion timelineVersion generation revision sessionStartNs throughNs pendingTargetNs visiblePrefixHash nextGroupIndex lastGroupId"


def make_group(rows, version):
    require(0 < len(rows) <= 1024, "group", "GROUP_LIMIT")
    trusted = all(row["trustedSequence"] is not None for row in rows)
    group = dict(groupId=content_hash(dict(schemaVersion=1, artifact="BTL-TICK-GROUP-ID-1",
                                         datasetVersion=version, timeNs=rows[0]["timeNs"],
                                         eventIds=[r["eventId"] for r in rows])),
                 timeNs=rows[0]["timeNs"], order="TRUSTED_SEQUENCE" if trusted else "UNTRUSTED",
                 events=rows)
    try:
        canonical_bytes({"schemaVersion": 1, "artifact": "BTL-TICK-GROUP-CHECK-1", "group": group})
    except ValueError:
        require(False, "group", "GROUP_LIMIT")
    return group


class RevealedView:
    """Read-only capability. No advance/seek/provider/manifest/EOF access."""
    __slots__ = ("__read", "__cursor")

    def __init__(self, read, cursor):
        self.__read, self.__cursor = read, cursor

    def read_revealed(self, from_group_index="0", max_groups=64):
        return self.__read(from_group_index, max_groups)

    @property
    def cursor(self):
        return self.__cursor()


class TickTimeline:
    """Replay controller. Offline factory accepts validated provider identity.

    Private iterator holds one page plus one atomic group. Prefix reading and
    seek/resume stream from source; checkpoints store advance acknowledgements,
    not hidden quotes. No caller can advance through the consumer view.
    """
    def __init__(self, provider, dataset_id, dataset_version, session_start_ns="0"):
        self.__provider = provider
        diagnostics=[]
        self.__manifest = validate_provider(provider, dataset_id, dataset_version,
                                            diagnostic_sink=lambda r:diagnostics.append(canonical_bytes(dict(schemaVersion=1,artifact="BTL-TICK-DIAGNOSTIC-CACHE-1",record=r))))
        self.__diagnostic_records=tuple(diagnostics)
        self.__id, self.__version = dataset_id, dataset_version
        self.__generation = 0
        self.__active = True
        self.__start = uint(session_start_ns)
        self.__schedule = []
        self.__cancel_epoch = 0
        self.__initialize()

    def __initialize(self):
        self.__iterator = self.__groups()
        self.__pending = None
        self.__has_pending = False
        initial = dict(schemaVersion=1, artifact="BTL-TICK-PREFIX-1", datasetId=self.__id,
                       datasetVersion=self.__version, timelineVersion=TIMELINE_VERSION,
                       generation=str(self.__generation), sessionStartNs=str(self.__start),
                       throughNs=str(self.__start), groups=[], coverage=[], diagnostics=empty_diagnostics())
        self.__cursor = dict(schemaVersion=1, artifact="BTL-TICK-CURSOR-1", datasetId=self.__id,
                             datasetVersion=self.__version, timelineVersion=TIMELINE_VERSION,
                             generation=str(self.__generation), revision="0", sessionStartNs=str(self.__start),
                             throughNs=str(self.__start), pendingTargetNs=None, visiblePrefixHash=content_hash(initial),
                             nextGroupIndex="0", lastGroupId=None)
        self.__revealed_diagnostics = set()

    @property
    def cursor(self):
        return deepcopy(self.__cursor)

    def consumer(self):
        generation=self.__generation
        def read(index, maximum):
            require(self.__active and self.__generation==generation,"view","STALE_GENERATION")
            return self.read_revealed(index,maximum)
        def cursor():
            require(self.__active and self.__generation==generation,"view","STALE_GENERATION")
            return self.cursor
        return RevealedView(read,cursor)

    def __rows(self):
        token, chunk_index, buffer = None, 0, []
        metadata = self.__manifest.wire["chunks"]
        while True:
            page = self.__provider.read_page(self.__id, self.__version, token, 64)
            tag(page, "BTL-TICK-PAGE-1", "datasetId datasetVersion events diagnostics nextToken endOfDataset")
            require(type(page["events"]) is list and len(page["events"])<=64 and type(page["endOfDataset"]) is bool,"page_bounds")
            # Recheck identity/content on each page against immutable ingress.
            require(page["datasetId"] == self.__id and page["datasetVersion"] == self.__version, "page", "VERSION_MISMATCH")
            for row in page["events"]:
                buffer.append(row)
                require(chunk_index < len(metadata), "chunk", "EXTRA_EVENT")
                if len(buffer) == metadata[chunk_index]["eventCount"]:
                    chunk = dict(schemaVersion=1, artifact="BTL-TICK-CHUNK-1", datasetId=self.__id,
                                 datasetVersion=self.__version, chunkIndex=str(chunk_index), events=buffer)
                    ticks = validate_chunk(chunk, self.__manifest)
                    for tick in ticks:
                        yield tick.wire
                    chunk_index += 1; buffer = []
            if page["endOfDataset"]:
                require(page["nextToken"] is None,"eof_token")
                require(not buffer and chunk_index == len(metadata), "chunks", "TRUNCATED_DATASET")
                break
            require(page["nextToken"] is not None and page["nextToken"] != token, "token", "NO_PROGRESS")
            token = page["nextToken"]

    def __groups(self):
        for time, rows in groupby(self.__rows(), lambda r: r["timeNs"]):
            collected = []
            for row in rows:
                collected.append(row)
                require(len(collected) <= 1024, "group", "GROUP_LIMIT")
            group = make_group(collected, self.__version)
            if int(time) >= self.__start:
                yield group

    def __peek(self):
        if not self.__has_pending:
            self.__pending = next(self.__iterator, None)
            self.__has_pending = True
        return self.__pending

    def __coverage(self, old, through):
        result = []
        m = self.__manifest.wire
        # Explicit UNKNOWN fills only metadata intervals, never quote prices.
        points = {old, through}
        for row in m["coverage"] + m["gaps"]:
            for key in ("startNs", "endNs"):
                points.add(max(old, min(through, int(row[key]))))
        ordered = sorted(points)
        for start, end in zip(ordered, ordered[1:]):
            if start == end:
                continue
            status, evidence = "UNKNOWN", None
            for c in m["coverage"]:
                if int(c["startNs"]) <= start and end <= int(c["endNs"]):
                    status, evidence = c["status"], c["evidenceHash"]
            for gap in m["gaps"]:
                if int(gap["startNs"]) <= start and end <= int(gap["endNs"]):
                    status = "INCOMPLETE" if gap["kind"] == "MISSING_DATA" else "UNKNOWN"
                    evidence = gap["evidenceHash"] if status == "INCOMPLETE" else None
            result.append(dict(startNs=str(start), endNs=str(end), status=status, evidenceHash=evidence))
        return result

    def __diagnostics(self, through):
        # Offline integrity checks already accepted bounded diagnostic blocks.
        records = [r for r in (json.loads(raw)["record"] for raw in self.__diagnostic_records)
                   if self.__start <= int(r["timeNs"]) <= through
                   and (r["sourceId"], r["rawOrdinal"], r["code"]) not in self.__revealed_diagnostics]
        require(len(records)<=128,"diagnostic_window","REVEAL_LIMIT")
        return dict(records=records, counts=diagnostic_counts(records), truncated=False)

    def advance_through(self, target_ns, expected_cursor, cancellation=None):
        require(self.__active,"timeline","REPLACED_TIMELINE")
        tag(expected_cursor,"BTL-TICK-CURSOR-1",CURSOR_FIELDS)
        target = uint(target_ns)
        require(expected_cursor == self.__cursor, "cursor", "STALE_CURSOR")
        require(target >= int(self.__cursor["throughNs"]), "target", "BACKWARD_ADVANCE")
        require(self.__cursor["pendingTargetNs"] in (None, target_ns), "target", "ADVANCE_IN_PROGRESS")
        cancel = cancellation or Cancellation()
        cancel.check()
        epoch = self.__cancel_epoch
        old = int(self.__cursor["throughNs"])
        groups = []
        # Speculative consumed groups can be reconstructed after cancellation.
        try:
            while (group := self.__peek()) is not None and int(group["timeNs"]) <= target:
                cancel.check(); require(epoch == self.__cancel_epoch, "cancel", "CANCELLED")
                candidate = groups + [group]
                try:
                    canonical_bytes(dict(schemaVersion=1, artifact="BTL-TICK-STEP-CHECK-1", groups=candidate))
                except ValueError:
                    require(bool(groups), "group", "GROUP_LIMIT")
                    break
                if len(groups) == 64:
                    break
                groups.append(group)
                self.__has_pending = False
            pending = self.__peek()
            done = pending is None or int(pending["timeNs"]) > target
            through = target if done else int(groups[-1]["timeNs"]) if groups else old
            coverage = self.__coverage(old, through)
            diagnostics = self.__diagnostics(through)
            updated = self.cursor
            noop = not groups and through == old and updated["pendingTargetNs"] is None
            if not noop:
                step = dict(schemaVersion=1, artifact="BTL-TICK-PREFIX-STEP-1", previousHash=updated["visiblePrefixHash"],
                            throughNs=str(through), groups=groups, coverage=coverage, diagnostics=diagnostics)
                updated.update(revision=str(int(updated["revision"])+1), throughNs=str(through),
                               nextGroupIndex=str(int(updated["nextGroupIndex"])+len(groups)),
                               lastGroupId=groups[-1]["groupId"] if groups else updated["lastGroupId"],
                               pendingTargetNs=None if done else target_ns, visiblePrefixHash=content_hash(step))
            result = dict(schemaVersion=1, artifact="BTL-TICK-REVEAL-1", datasetId=self.__id, datasetVersion=self.__version,
                          timelineVersion=TIMELINE_VERSION, generation=updated["generation"], sessionStartNs=str(self.__start),
                          targetNs=target_ns, throughNs=str(through), groups=groups, coverage=coverage, diagnostics=diagnostics,
                          visiblePrefixHash=updated["visiblePrefixHash"], cursor=updated, exhaustedThroughBoundary=done)
            canonical_bytes(result)
            cancel.check(); require(epoch == self.__cancel_epoch, "cancel", "CANCELLED")
        except BaseException:
            if cancel.cancelled or epoch!=self.__cancel_epoch:
                if self.__active and expected_cursor["generation"]!=self.__cursor["generation"]:
                    self.__restore_iterator()
                elif self.__active:
                    rest=[] if not self.__has_pending or self.__pending is None else [self.__pending]
                    self.__iterator=chain(groups,rest,self.__iterator)
                    self.__pending,self.__has_pending=None,False
            else:
                self.__restore_iterator()
            raise
        self.__cursor = updated
        for record in diagnostics["records"]:
            self.__revealed_diagnostics.add((record["sourceId"], record["rawOrdinal"], record["code"]))
        if not noop:
            self.__schedule.append(target_ns)
        return deepcopy(result)

    def __restore_iterator(self):
        self.__iterator = self.__groups()
        for _ in range(int(self.__cursor["nextGroupIndex"])):
            require(next(self.__iterator, None) is not None, "cursor", "TRUNCATED_DATASET")
        self.__pending, self.__has_pending = None, False

    def next_group(self, expected_cursor, cancellation=None):
        require(self.__active,"timeline","REPLACED_TIMELINE")
        tag(expected_cursor,"BTL-TICK-CURSOR-1",CURSOR_FIELDS)
        require(expected_cursor == self.__cursor, "cursor", "STALE_CURSOR")
        require(self.__cursor["pendingTargetNs"] is None, "target", "ADVANCE_IN_PROGRESS")
        (cancellation or Cancellation()).check()
        group = self.__peek()
        # No future EOF property is handed to consumer: at end, empty no-op.
        target = self.__cursor["throughNs"] if group is None else group["timeNs"]
        return self.advance_through(target, expected_cursor, cancellation)

    def read_revealed(self, from_group_index="0", max_groups=64):
        require(self.__active,"timeline","REPLACED_TIMELINE")
        start = uint(from_group_index)
        require(type(max_groups) is int and 1 <= max_groups <= 1024, "max_groups")
        end = int(self.__cursor["nextGroupIndex"])
        require(start <= end, "index", "UNREVEALED_INDEX")
        groups = []
        for group in islice(self.__groups(), start, min(end, start+max_groups)):
            candidate = groups + [group]
            try:
                canonical_bytes(dict(schemaVersion=1, artifact="BTL-TICK-VIEW-CHECK-1", groups=candidate))
            except ValueError:
                require(bool(groups), "group", "GROUP_LIMIT")
                break
            groups.append(group)
        return deepcopy(groups)

    def cancel(self):
        self.__cancel_epoch += 1

    def reset(self, session_start_ns=None):
        require(self.__active,"timeline","REPLACED_TIMELINE")
        if session_start_ns is not None:
            self.__start = uint(session_start_ns)
        self.cancel()
        self.__generation += 1
        self.__schedule = []
        self.__initialize()
        return self.cursor

    def replace_dataset(self, provider, dataset_id, dataset_version, session_start_ns="0"):
        require(self.__active,"timeline","REPLACED_TIMELINE")
        replacement=TickTimeline(provider,dataset_id,dataset_version,session_start_ns)
        replacement.__generation=self.__generation+1
        replacement.__initialize()
        self.cancel()
        self.__active=False
        return replacement

    def seek(self, target_ns, cancellation=None):
        uint(target_ns)
        require(int(target_ns) >= self.__start, "seek", "BEFORE_SESSION_START")
        self.reset()
        result = self.advance_through(target_ns, self.cursor, cancellation)
        while not result["exhaustedThroughBoundary"]:
            result = self.advance_through(target_ns, self.cursor, cancellation)
        return result

    def checkpoint(self):
        require(self.__active,"timeline","REPLACED_TIMELINE")
        # Controller-private acknowledgements are not market-consumer data.
        return {"cursor": self.cursor, "advanceTargets": list(self.__schedule)}

    @classmethod
    def resume(cls, provider, checkpoint):
        keys(checkpoint, "cursor advanceTargets")
        cursor = checkpoint["cursor"]
        tag(cursor,"BTL-TICK-CURSOR-1",CURSOR_FIELDS)
        require(cursor["artifact"] == "BTL-TICK-CURSOR-1" and cursor["schemaVersion"] == 1 and cursor["timelineVersion"] == TIMELINE_VERSION, "cursor", "SCHEMA_MISMATCH")
        require(type(checkpoint["advanceTargets"]) is list, "checkpoint")
        result = cls(provider, cursor["datasetId"], cursor["datasetVersion"], cursor["sessionStartNs"])
        result.__generation = uint(cursor["generation"])
        result.__initialize()
        for target in checkpoint["advanceTargets"]:
            result.advance_through(target, result.cursor)
        require(result.cursor == cursor, "resume", "INVALID_CHECKPOINT")
        return result
