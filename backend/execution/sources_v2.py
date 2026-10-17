"""Private authored-source join. No financial commits or consumer capability.

Uses unchanged V1 accepted synthetic timelines only. It does not upgrade frozen
V2 UNKNOWN sidecars or accept real-provider datasets.
"""
from copy import deepcopy
from contracts.canonical import canonical_bytes
from contracts.primitives import ContractError, require
from ticks.contracts import TickManifest, keys, uint, tag
from ticks.provider import Cancellation
from ticks.timeline import TickTimeline, CURSOR_FIELDS
from .conversion import convert_usd
from .profile_v2 import ExecutionProfileV2

MAX_SOURCE_STEPS = 256


def _manifest(provider, source):
    require(callable(getattr(provider, "describe", None)) and callable(getattr(provider, "read_page", None)),
            "provider", "REFUSED_V2_SOURCE_INTERFACE")
    manifest = TickManifest.from_wire(provider.describe(source["datasetId"], source["datasetVersion"]))
    raw = manifest.wire
    require(manifest.version == source["datasetVersion"] and raw["evidenceClass"] == "SYNTHETIC_CONTRACT_ONLY"
            and raw["rights"]["class"] == "SYNTHETIC" and all(raw[k] == source[k] for k in ("datasetId", "providerId", "feedId"))
            and raw["instrumentId"] == source["feedInstrumentId"], "source", "REFUSED_V2_SOURCE_PIN")
    return raw


def _complete_between(manifest, start, end):
    # Authored V1 metadata only, private and clipped at current decision time.
    if start == end:
        return True
    points = {start, end}
    for row in manifest["coverage"] + manifest["gaps"]:
        points.update(max(start, min(end, int(row[k]))) for k in ("startNs", "endNs"))
    boundaries = sorted(points)
    for lo, hi in zip(boundaries, boundaries[1:]):
        complete = any(int(c["startNs"]) <= lo < hi <= int(c["endNs"])
                       and c["status"] == "DECLARED_COMPLETE" and c["evidenceHash"] is not None
                       for c in manifest["coverage"])
        gap = any(max(lo, int(g["startNs"])) < min(hi, int(g["endNs"])) for g in manifest["gaps"])
        if not complete or gap:
            return False
    return True


class SourceJoinV2:
    """Controller-private capability; never return this object to a consumer."""
    def __init__(self, profile, primary_provider, *, start_ns, conversion_provider=None):
        require(type(profile) is ExecutionProfileV2, "profile", "REFUSED_V2_PROFILE")
        p = profile.wire
        start = uint(start_ns)
        self.__profile, self.__p = profile, p
        self.__primary_provider, self.__fx_provider = primary_provider, conversion_provider
        primary_manifest = _manifest(primary_provider, p["primary"])
        require(int(primary_manifest["range"]["startNs"]) <= start < int(primary_manifest["range"]["endNs"]),
                "start", "REFUSED_V2_SOURCE_WINDOW")
        self.__primary = TickTimeline(primary_provider, p["primary"]["datasetId"], p["primary"]["datasetVersion"], start_ns)
        self.__fx, self.__fx_manifest = None, None
        if p["conversion"] is None:
            require(conversion_provider is None, "conversion", "REFUSED_V2_IDENTITY_SOURCE")
        else:
            require(conversion_provider is not None, "conversion", "REFUSED_V2_SOURCE_MISSING")
            source = p["conversion"]
            self.__fx_manifest = _manifest(conversion_provider, source)
            fx_start = str(max(0, start - int(source["maxAgeNs"])))
            self.__fx = TickTimeline(conversion_provider, source["datasetId"], source["datasetVersion"], fx_start)
        self.__broken = False

    def checkpoint(self):
        require(not self.__broken, "controller", "REFUSED_V2_RECOVERY_FAILED")
        return dict(schemaVersion=1, artifact="BTL-V2-SOURCE-CHECKPOINT-1", profileHash=self.__profile.profile_hash,
                    primary=self.__primary.checkpoint(), conversion=None if self.__fx is None else self.__fx.checkpoint())

    def __restore(self, checkpoint):
        self.__primary = TickTimeline.resume(self.__primary_provider, checkpoint["primary"])
        if self.__fx is not None:
            self.__fx = TickTimeline.resume(self.__fx_provider, checkpoint["conversion"])

    @classmethod
    def resume(cls, profile, primary_provider, checkpoint, *, conversion_provider=None):
        keys(checkpoint, "schemaVersion artifact profileHash primary conversion")
        require(type(checkpoint["schemaVersion"]) is int and checkpoint["schemaVersion"] == 1
                and checkpoint["artifact"] == "BTL-V2-SOURCE-CHECKPOINT-1"
                and type(profile) is ExecutionProfileV2 and checkpoint["profileHash"] == profile.profile_hash,
                "checkpoint", "REFUSED_V2_CHECKPOINT")
        require(type(checkpoint["primary"]) is dict and (checkpoint["conversion"] is None or type(checkpoint["conversion"]) is dict),
                "checkpoint", "REFUSED_V2_CHECKPOINT")
        canonical_bytes(checkpoint)
        for value in (checkpoint["primary"], checkpoint["conversion"]):
            if value is not None:
                keys(value, "cursor advanceTargets")
                tag(value["cursor"], "BTL-TICK-CURSOR-1", CURSOR_FIELDS)
                uint(value["cursor"]["sessionStartNs"])
                uint(value["cursor"]["throughNs"])
                require(type(value["advanceTargets"]) is list and len(value["advanceTargets"]) <= MAX_SOURCE_STEPS,
                        "checkpoint", "REFUSED_V2_RECOVERY_LIMIT")
        obj = cls(profile, primary_provider, start_ns=checkpoint["primary"]["cursor"]["sessionStartNs"],
                  conversion_provider=conversion_provider)
        require((checkpoint["conversion"] is None) == (obj.__fx is None), "conversion", "REFUSED_V2_CHECKPOINT")
        for key, source in (("primary", profile.wire["primary"]), ("conversion", profile.wire["conversion"])):
            if source is not None:
                cursor = checkpoint[key]["cursor"]
                require(cursor["datasetId"] == source["datasetId"] and cursor["datasetVersion"] == source["datasetVersion"],
                        "source", "REFUSED_V2_CHECKPOINT")
        if obj.__fx is not None:
            cursor = checkpoint["conversion"]["cursor"]
            require(cursor["sessionStartNs"] == obj.__fx.cursor["sessionStartNs"] and cursor["pendingTargetNs"] is None
                    and int(cursor["throughNs"]) <= int(checkpoint["primary"]["cursor"]["throughNs"]),
                    "conversion", "REFUSED_V2_CHECKPOINT")
        obj.__restore(checkpoint)
        require(obj.checkpoint() == checkpoint, "checkpoint", "REFUSED_V2_CHECKPOINT")
        return obj

    def __step(self, timeline, target, cancel):
        require(len(timeline.checkpoint()["advanceTargets"]) < MAX_SOURCE_STEPS,
                "checkpoint", "REFUSED_V2_RECOVERY_LIMIT")
        return timeline.advance_through(target, timeline.cursor, cancel)

    def __selection(self, as_of, cancel):
        if self.__fx is None:
            return None, "IDENTITY"
        for _ in range(MAX_SOURCE_STEPS):
            ack = self.__step(self.__fx, as_of, cancel)
            if ack["exhaustedThroughBoundary"]:
                break
        else:
            raise ContractError("REFUSED_V2_JOIN_BUDGET", "conversion")
        count = int(self.__fx.cursor["nextGroupIndex"])
        if count == 0:
            return None, "UNRESOLVED_FX_MISSING"
        group = self.__fx.read_revealed(str(count - 1), 1)[0]
        try:
            # Validate both signed sides; a zero amount alone checks only one.
            for amount in ("1", "-1"):
                convert_usd(amount, self.__p["quoteCurrency"], as_of, pin=self.__p["conversion"], group=group,
                            money_scale=self.__p["moneyScale"])
        except ContractError as error:
            if error.code.startswith("UNRESOLVED_FX_"):
                return group, error.code
            if error.code == "REFUSED_FINANCIAL_LIMIT":
                return group, "UNRESOLVED_FX_PRECISION"
            raise
        if not _complete_between(self.__fx_manifest, int(group["timeNs"]), int(as_of)):
            return group, "UNRESOLVED_FX_COVERAGE"
        return group, "ELIGIBLE_SYNTHETIC"

    def reveal(self, target_ns, expected_checkpoint, *, cancellation=None):
        before = self.checkpoint()
        require(expected_checkpoint == before, "checkpoint", "REFUSED_V2_STALE_CHECKPOINT")
        cancel = cancellation or Cancellation()
        cancel.check()
        try:
            primary = self.__step(self.__primary, target_ns, cancel)
            pairs, conversions = [], {}
            for group in primary["groups"]:
                cancel.check()
                fx, status = self.__selection(group["timeNs"], cancel)
                ref = None if fx is None else fx["groupId"]
                if fx is not None:
                    conversions[ref] = fx
                pairs.append(dict(primaryGroup=group, conversionGroupId=ref, conversionStatus=status))
                canonical_bytes(dict(schemaVersion=1, pairs=pairs, conversionGroups=conversions))
            result = dict(schemaVersion=1, artifact="BTL-V2-SOURCE-REVEAL-1", profileHash=self.__profile.profile_hash,
                          throughNs=primary["throughNs"], pairs=pairs, conversionGroups=conversions,
                          primaryCoverage=primary["coverage"], primaryDiagnostics=primary["diagnostics"],
                          exhaustedThroughBoundary=primary["exhaustedThroughBoundary"], checkpoint=self.checkpoint())
            canonical_bytes(result)
            cancel.check()
            return deepcopy(result)
        except BaseException:
            try:
                self.__restore(before)
            except BaseException as error:
                self.__broken = True
                raise ContractError("REFUSED_V2_RECOVERY_FAILED", "controller") from error
            raise

    def risk_basis(self, expected_checkpoint, *, cancellation=None):
        """Private FX proof at already acknowledged primary clock; no future read."""
        before = self.checkpoint()
        require(expected_checkpoint == before, "checkpoint", "REFUSED_V2_STALE_CHECKPOINT")
        cancel = cancellation or Cancellation()
        cancel.check()
        try:
            as_of = self.__primary.cursor["throughNs"]
            group, status = self.__selection(as_of, cancel)
            result = dict(schemaVersion=1, artifact="BTL-V2-SOURCE-RISK-1", profileHash=self.__profile.profile_hash,
                          timeNs=as_of, conversionGroup=group, conversionStatus=status, checkpoint=self.checkpoint())
            canonical_bytes(result)
            cancel.check()
            return deepcopy(result)
        except BaseException:
            try:
                self.__restore(before)
            except BaseException as error:
                self.__broken = True
                raise ContractError("REFUSED_V2_RECOVERY_FAILED", "controller") from error
            raise
