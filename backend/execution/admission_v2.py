"""Owner-admitted HistData months as an execution source (free beta).

Owner decision 2026-10-24: HistData months that passed full numeric/order
validation may be traded, labelled as historical replay, not broker fills.
Admission is an explicit, hashed overlay over unchanged accepted monthly
stores: rows keep their provider/feed/instrument/event identity and prices;
only dataset identity and quality are re-labelled under the admission hash.
Nothing is sorted, repaired, deduplicated or substituted. Refused months are
simply never admitted, and replay cannot advance past the admitted range.

Non-USD quotes convert through the admitted route symbol (for example USDJPY
for EURJPY) with the unchanged conversion evidence rules: the latest route
group at or before each primary group, at most maxAgeNs old, one price.
"""
from copy import deepcopy
from datetime import datetime, timezone
import re

from contracts.canonical import canonical_bytes, content_hash
from contracts.primitives import ContractError, digest, identifier, require
from market_data.instruments import instrument
from ticks.contracts import CanonicalTick, keys, tag, uint
from ticks.provider import Cancellation, empty_diagnostics
from ticks.storage_v2 import DiskTickProvider
from ticks.timeline import CURSOR_FIELDS, make_group
from .conversion import convert_usd
from .profile_v2 import ExecutionProfileV2, ADMITTED_MODEL

ADMISSION = "BTL-HISTDATA-ADMISSION-1"
POLICY = "OWNER_2026_10_24_VALIDATED_MONTHS_FREE_BETA"
TIMELINE = "BTL-ADMITTED-TIMELINE-1"
LABEL = "Historical replay (HistData) · not broker fills · coverage and rights unverified"
MAX_GROUPS, PAGE = 64, 256
FX_LOOKBACK_NS = 7 * 24 * 3600 * 10**9
_PERIOD = re.compile(r"[0-9]{4}-(0[1-9]|1[0-2])")


def _next_period(period):
    year, month = int(period[:4]), int(period[5:])
    return f"{year + month // 12:04d}-{month % 12 + 1:02d}"


def _period_ns(period):
    return int(datetime(int(period[:4]), int(period[5:]), 1, tzinfo=timezone.utc).timestamp()) * 10**9


def admission_record(symbol, months):
    """Canonical admission artifact; its hash is the admitted dataset version."""
    instrument(symbol)
    require(type(months) in (list, tuple) and 1 <= len(months) <= 120, "months", "REFUSED_ADMISSION")
    rows = []
    for i, m in enumerate(months):
        keys(m, "period datasetId datasetVersion validationReportHash")
        require(type(m["period"]) is str and _PERIOD.fullmatch(m["period"]) is not None, "period", "REFUSED_ADMISSION")
        require(i == 0 or m["period"] == _next_period(rows[-1]["period"]), "period", "REFUSED_ADMISSION_GAP")
        identifier(m["datasetId"], "datasetId")
        require(":first:" not in m["datasetId"], "selection", "REFUSED_PREFIX_AS_FULL_SOURCE")
        digest(m["datasetVersion"], "datasetVersion")
        digest(m["validationReportHash"], "validationReportHash")
        rows.append(dict(m))
    record = dict(schemaVersion=1, artifact=ADMISSION, symbol=symbol, policy=POLICY, months=rows)
    canonical_bytes(record)
    return record


def admitted_dataset_id(record):
    return f"admitted:histdata:{record['symbol']}:{record['months'][0]['period']}:{record['months'][-1]['period']}"


def admitted_conversion_pin(record, currency, max_age_ns="60000000000"):
    """Profile `conversion` block for an admitted route symbol."""
    pin = admitted_source_pin(record)
    del pin["evidenceClass"]
    return dict(currency=currency, symbol=record["symbol"], **pin, maxAgeNs=max_age_ns)


def admitted_source_pin(record):
    """Profile `primary` block for an admission record."""
    symbol = record["symbol"]
    return dict(datasetId=admitted_dataset_id(record), datasetVersion=content_hash(record), providerId="histdata",
                feedId="local-unverified:" + symbol, feedInstrumentId="histdata:" + symbol,
                evidenceClass="ADMITTED_OBSERVATION")


class AdmittedSource:
    """Controller-private reader over the admitted monthly stores."""

    def __init__(self, record, folders):
        record = admission_record(record["symbol"], record["months"]) if type(record) is dict else None
        require(record is not None and type(folders) in (list, tuple) and len(folders) == len(record["months"]),
                "folders", "REFUSED_ADMISSION")
        self.record, self.pin = record, admitted_source_pin(record)
        self.dataset_id, self.dataset_version = self.pin["datasetId"], self.pin["datasetVersion"]
        self.__months, self.__bounds = [], []
        previous_end = None
        try:
            for month, folder in zip(record["months"], folders):
                provider = DiskTickProvider(folder, month["datasetVersion"])
                self.__months.append(provider)
                root = provider.describe_v2(month["datasetId"], month["datasetVersion"])["root"]
                require(root["datasetId"] == month["datasetId"] and root["providerId"] == "histdata"
                        and root["providerSymbol"] == record["symbol"] and root["feedId"] == self.pin["feedId"]
                        and root["instrumentId"] == self.pin["feedInstrumentId"]
                        and root["evidenceClass"] == "PROVIDER_OBSERVATION", "source", "REFUSED_ADMISSION_SOURCE")
                start, end = int(root["range"]["startNs"]), int(root["range"]["endNs"])
                require(start < end and (previous_end is None or previous_end <= start), "range", "REFUSED_ADMISSION_ORDER")
                require(_period_ns(month["period"]) <= start and end <= _period_ns(_next_period(month["period"])),
                        "range", "REFUSED_ADMISSION_PERIOD")
                previous_end = end
                self.__bounds.append((start, end))
        except BaseException:
            self.close()
            raise
        self.start_ns, self.end_ns = self.__bounds[0][0], self.__bounds[-1][1]
        self.label = LABEL

    def close(self):
        for provider in self.__months:
            provider.close()
        self.__months = []

    def start_for_period(self, period):
        """First observed tick time of an admitted month."""
        require(type(period) is str, "period", "REFUSED_HISTDATA_PERIOD")
        for month, (start, _) in zip(self.record["months"], self.__bounds):
            if month["period"] == period:
                return start
        raise ContractError("REFUSED_HISTDATA_PERIOD", "period")

    def __relabel(self, row):
        # Admission promotes only UNKNOWN freshness/silence; known STALE or
        # MISSING_DATA evidence stays as observed and remains unresolved.
        q = row["quality"]
        tick = dict(row, datasetId=self.dataset_id, datasetVersion=self.dataset_version,
                    quality=dict(q, freshness="CONFIRMED" if q["freshness"] == "UNKNOWN" else q["freshness"],
                                 gapBefore="NONE" if q["gapBefore"] == "UNKNOWN_SILENCE" else q["gapBefore"],
                                 evidenceHash=self.dataset_version))
        return CanonicalTick.from_wire(tick).wire

    def iter_groups(self, after_ns, inclusive, cancel):
        """Complete groups in time order with time > after_ns (>= when inclusive)."""
        target = after_ns if inclusive else after_ns + 1
        current = []
        for i, (provider, (start, end)) in enumerate(zip(self.__months, self.__bounds)):
            if end <= target:
                continue
            month = self.record["months"][i]
            position = provider.locate_v2(month["datasetId"], month["datasetVersion"], str(max(target, start)))["position"]
            while position is not None:
                cancel.check()
                page = provider.read_page_v2(month["datasetId"], month["datasetVersion"], position, PAGE)
                for row in page["events"]:
                    if current and row["timeNs"] != current[0]["timeNs"]:
                        yield make_group(current, self.dataset_version)
                        current = []
                    current.append(self.__relabel(row))
                    require(len(current) <= 1024, "group", "GROUP_LIMIT")
                position = page["nextPosition"]
        # Month ranges never overlap, so a group never spans two stores.
        if current:
            yield make_group(current, self.dataset_version)

    def recent(self, floor_ns, through_ns, maximum, cancel):
        """Last `maximum` groups with floor_ns <= time <= through_ns (bounded backward search)."""
        window = 60 * 10**9
        while True:
            lo = max(floor_ns, through_ns - window)
            found = []
            for group in self.iter_groups(lo, True, cancel):
                if int(group["timeNs"]) > through_ns:
                    break
                found = (found + [group])[-maximum:]
            if len(found) >= maximum or lo == floor_ns:
                return found
            window *= 4

    def groups_after(self, after_ns, inclusive, maximum, cancel, *, until_ns=None):
        groups = []
        for group in self.iter_groups(after_ns, inclusive, cancel):
            if len(groups) == maximum or (until_ns is not None and int(group["timeNs"]) > until_ns):
                break
            groups.append(group)
        return groups


class AdmittedSourceJoin:
    """SourceJoinV2 counterpart for admitted months; same controller interface.

    Checkpoints use the existing V1 cursor shape so kernel validation is
    unchanged. Resume re-locates from the acknowledged clock instead of
    replaying a log: admitted stores are immutable and groups are atomic.
    """

    def __init__(self, profile, primary_provider, *, start_ns, conversion_provider=None):
        require(type(profile) is ExecutionProfileV2 and profile.wire["model"] == ADMITTED_MODEL, "profile", "REFUSED_V2_PROFILE")
        require(type(primary_provider) is AdmittedSource and primary_provider.pin == profile.wire["primary"],
                "source", "REFUSED_V2_SOURCE_PIN")
        fx = profile.wire["conversion"]
        if fx is None:
            require(conversion_provider is None, "conversion", "REFUSED_V2_IDENTITY_SOURCE")
        else:
            require(type(conversion_provider) is AdmittedSource
                    and all(conversion_provider.pin[k] == fx[k] for k in ("datasetId", "datasetVersion", "providerId", "feedId", "feedInstrumentId")),
                    "conversion", "REFUSED_V2_SOURCE_PIN")
        self.__fx = conversion_provider
        start = uint(start_ns)
        require(primary_provider.start_ns <= start < primary_provider.end_ns, "start", "REFUSED_V2_SOURCE_WINDOW")
        self.__profile, self.__source = profile, primary_provider
        initial = content_hash(dict(schemaVersion=1, artifact="BTL-ADMITTED-PREFIX-1", datasetVersion=primary_provider.dataset_version,
                                    sessionStartNs=str(start)))
        self.__cursor = dict(schemaVersion=1, artifact="BTL-TICK-CURSOR-1", datasetId=primary_provider.dataset_id,
                             datasetVersion=primary_provider.dataset_version, timelineVersion=TIMELINE, generation="0",
                             revision="0", sessionStartNs=str(start), throughNs=str(start), pendingTargetNs=None,
                             visiblePrefixHash=initial, nextGroupIndex="0", lastGroupId=None)

    def checkpoint(self):
        return dict(schemaVersion=1, artifact="BTL-V2-SOURCE-CHECKPOINT-1", profileHash=self.__profile.profile_hash,
                    primary=dict(cursor=deepcopy(self.__cursor), advanceTargets=[]), conversion=self.__fx_cursor())

    def __fx_cursor(self):
        # Conversion selection is a stateless lookup at each primary group, so
        # this cursor records only the acknowledged clock in the kernel shape.
        if self.__fx is None:
            return None
        pin, start = self.__profile.wire["conversion"], int(self.__cursor["sessionStartNs"])
        session = str(max(0, start - int(pin["maxAgeNs"])))
        initial = content_hash(dict(schemaVersion=1, artifact="BTL-ADMITTED-PREFIX-1", datasetVersion=pin["datasetVersion"],
                                    sessionStartNs=session))
        cursor = dict(schemaVersion=1, artifact="BTL-TICK-CURSOR-1", datasetId=pin["datasetId"], datasetVersion=pin["datasetVersion"],
                      timelineVersion=TIMELINE, generation="0", revision="0", sessionStartNs=session,
                      throughNs=self.__cursor["throughNs"], pendingTargetNs=None, visiblePrefixHash=initial,
                      nextGroupIndex="0", lastGroupId=None)
        return dict(cursor=cursor, advanceTargets=[])

    def __selection(self, as_of, cancel):
        """Latest admitted route group at or before as_of, with its eligibility."""
        if self.__fx is None:
            return None, "IDENTITY"
        p, at = self.__profile.wire, int(as_of)
        # Look back past maxAgeNs (bounded) so an old quote is reported as STALE, not MISSING.
        floor = max(self.__fx.start_ns, at - FX_LOOKBACK_NS)
        found = self.__fx.recent(floor, at, 1, cancel) if floor <= at else []
        if not found:
            return None, "UNRESOLVED_FX_MISSING"
        group = found[0]
        try:
            # Validate both signed sides; a zero amount alone checks only one.
            for amount in ("1", "-1"):
                convert_usd(amount, p["quoteCurrency"], as_of, pin=p["conversion"], group=group, money_scale=p["moneyScale"])
        except ContractError as error:
            if error.code.startswith("UNRESOLVED_FX_"):
                return group, error.code
            if error.code == "REFUSED_FINANCIAL_LIMIT":
                return group, "UNRESOLVED_FX_PRECISION"
            raise
        # Silence after the group is covered only inside the admitted route range.
        if at >= self.__fx.end_ns:
            return group, "UNRESOLVED_FX_COVERAGE"
        return group, "ELIGIBLE_ADMITTED"

    @classmethod
    def resume(cls, profile, primary_provider, checkpoint, *, conversion_provider=None):
        keys(checkpoint, "schemaVersion artifact profileHash primary conversion")
        require(checkpoint["schemaVersion"] == 1 and checkpoint["artifact"] == "BTL-V2-SOURCE-CHECKPOINT-1"
                and type(profile) is ExecutionProfileV2 and checkpoint["profileHash"] == profile.profile_hash
                and (checkpoint["conversion"] is None or type(checkpoint["conversion"]) is dict), "checkpoint", "REFUSED_V2_CHECKPOINT")
        keys(checkpoint["primary"], "cursor advanceTargets")
        cursor = checkpoint["primary"]["cursor"]
        tag(cursor, "BTL-TICK-CURSOR-1", CURSOR_FIELDS)
        require(checkpoint["primary"]["advanceTargets"] == [] and cursor["timelineVersion"] == TIMELINE,
                "checkpoint", "REFUSED_V2_CHECKPOINT")
        obj = cls(profile, primary_provider, start_ns=cursor["sessionStartNs"], conversion_provider=conversion_provider)
        through = uint(cursor["throughNs"])
        require(int(cursor["sessionStartNs"]) <= through < primary_provider.end_ns, "checkpoint", "REFUSED_V2_CHECKPOINT")
        if cursor["lastGroupId"] is not None:
            last = primary_provider.recent(int(cursor["sessionStartNs"]), through, 1, Cancellation())
            require(bool(last) and last[0]["groupId"] == cursor["lastGroupId"], "checkpoint", "REFUSED_V2_CHECKPOINT")
        else:
            require(cursor["nextGroupIndex"] == "0", "checkpoint", "REFUSED_V2_CHECKPOINT")
        obj.__cursor = deepcopy(cursor)
        require(obj.checkpoint() == checkpoint, "checkpoint", "REFUSED_V2_CHECKPOINT")
        return obj

    def reveal(self, target_ns, expected_checkpoint, *, cancellation=None):
        require(expected_checkpoint == self.checkpoint(), "checkpoint", "REFUSED_V2_STALE_CHECKPOINT")
        cancel = cancellation or Cancellation(); cancel.check()
        target, old = uint(target_ns), int(self.__cursor["throughNs"])
        require(target >= old, "target", "BACKWARD_ADVANCE")
        require(self.__cursor["pendingTargetNs"] in (None, target_ns), "target", "ADVANCE_IN_PROGRESS")
        # The admitted range is the end of available data: refuse, never substitute.
        require(target < self.__source.end_ns, "target", "REFUSED_V2_SOURCE_WINDOW")
        # A group exactly at the session start is due only before any reveal moved the clock.
        fresh = self.__cursor["nextGroupIndex"] == "0" and old == int(self.__cursor["sessionStartNs"])
        due = self.__source.groups_after(old, fresh, MAX_GROUPS + 1, cancel, until_ns=target)
        groups = due[:MAX_GROUPS]
        done = len(due) <= MAX_GROUPS
        through = target if done else int(groups[-1]["timeNs"])
        coverage = [] if through == old else [dict(startNs=str(old), endNs=str(through), status="DECLARED_COMPLETE",
                                                   evidenceHash=self.__source.dataset_version)]
        cursor = dict(self.__cursor)
        if groups or through != old or cursor["pendingTargetNs"] is not None:
            step = dict(schemaVersion=1, artifact="BTL-ADMITTED-PREFIX-STEP-1", previousHash=cursor["visiblePrefixHash"],
                        throughNs=str(through), groupIds=[g["groupId"] for g in groups])
            cursor.update(revision=str(int(cursor["revision"]) + 1), throughNs=str(through),
                          nextGroupIndex=str(int(cursor["nextGroupIndex"]) + len(groups)),
                          lastGroupId=groups[-1]["groupId"] if groups else cursor["lastGroupId"],
                          pendingTargetNs=None if done else target_ns, visiblePrefixHash=content_hash(step))
        pairs, conversions = [], {}
        for g in groups:
            fx, status = self.__selection(g["timeNs"], cancel)
            if fx is not None:
                conversions[fx["groupId"]] = fx
            pairs.append(dict(primaryGroup=g, conversionGroupId=None if fx is None else fx["groupId"], conversionStatus=status))
        cancel.check()
        self.__cursor = cursor
        result = dict(schemaVersion=1, artifact="BTL-V2-SOURCE-REVEAL-1", profileHash=self.__profile.profile_hash,
                      throughNs=str(through), pairs=pairs, conversionGroups=conversions, primaryCoverage=coverage,
                      primaryDiagnostics=empty_diagnostics(), exhaustedThroughBoundary=done, checkpoint=self.checkpoint())
        canonical_bytes(result)
        return deepcopy(result)

    def risk_basis(self, expected_checkpoint, *, cancellation=None):
        require(expected_checkpoint == self.checkpoint(), "checkpoint", "REFUSED_V2_STALE_CHECKPOINT")
        cancel = cancellation or Cancellation(); cancel.check()
        group, status = self.__selection(self.__cursor["throughNs"], cancel)
        return dict(schemaVersion=1, artifact="BTL-V2-SOURCE-RISK-1", profileHash=self.__profile.profile_hash,
                    timeNs=self.__cursor["throughNs"], conversionGroup=deepcopy(group), conversionStatus=status,
                    checkpoint=self.checkpoint())

    def past_primary(self, expected_checkpoint, maximum=64):
        """Last revealed groups for display only; never beyond the acknowledged clock."""
        require(type(maximum) is int and 1 <= maximum <= 64, "maximum")
        require(expected_checkpoint == self.checkpoint(), "checkpoint", "REFUSED_V2_STALE_CHECKPOINT")
        count = int(self.__cursor["nextGroupIndex"])
        if not count:
            return []
        groups = self.__source.recent(int(self.__cursor["sessionStartNs"]), int(self.__cursor["throughNs"]),
                                      min(maximum, count), Cancellation())
        return deepcopy(groups)
