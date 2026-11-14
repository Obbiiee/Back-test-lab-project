"""Claude architecture prototype: verified compact source -> pinned session cursor -> indexed jump -> REUSED financial code.

Design rules (see docs/CLAUDE_ENGINE_ARCHITECTURE.md):
  * ONE financial source of truth: this module never computes a fill or a money amount itself. Fills/exits go through the
    repo's own `_fills`, `emit`, `_unresolved`, `can_change`, `exit_amount` via observed_kernel. Only the SOURCE and the
    SCAN are new.
  * Skipping is allowed only for a span of groups proven (by exact integer comparison against the pinned immutable arrays)
    to contain no event that the reference loop would act on. Anything not provable is processed by the same per-group
    body the reference uses.
  * Prototype only; not wired to PostgreSQL, not a contract change. Proposed contract changes are listed in the docs.
"""
import hashlib, json
from copy import deepcopy
from decimal import Decimal
from fractions import Fraction
import datetime as dt

import numpy as np

import execution.observed_kernel as K
from execution.observed_order_archive_v1 import ARTIFACT as QA_ARCHIVE_ARTIFACT
from execution.observed_kernel import apply, validate_state
from execution.observed_profile import ObservedExecutionProfile, MODEL_V2
from contracts.canonical import decimal_text, content_hash
from ticks.contracts import event_id
from ticks.timeline import make_group
from market_data.compact_tick import CompactTickReader

BLOCK = 256


def _scaled_text(v, scale=1000):
    return decimal_text(Decimal(int(v)) / scale)


class AdmittedSource:
    """Immutable, hash-pinned compact source + deterministic canonical reconstruction rule (verified at admission)."""

    def __init__(self, root, admission, *, expected_manifest_hash, deep_verify=False):
        self.reader = CompactTickReader(root, expected_manifest_hash=expected_manifest_hash)
        self.reader.verify_all(deep=deep_verify)
        self.adm = admission
        self.scale = int(admission.get("scale", 1000))
        self.kind = admission.get("kind", "dukascopy-csv")
        a = self.reader.read_range(0, 2**62)
        self.ts, self.bid, self.ask = a["ts_ns"], a["bid"], a["ask"]
        self.ordinal, self.crossed = a["ordinal"], a["is_crossed"].astype(bool)
        n = len(self.ts)
        new_group = np.empty(n, dtype=bool)
        new_group[0] = True
        new_group[1:] = self.ts[1:] != self.ts[:-1]
        self.gstart = np.flatnonzero(new_group)
        self.gend = np.r_[self.gstart[1:], n]
        self.gts = self.ts[self.gstart]
        self.gbid, self.gask = self.bid[self.gstart], self.ask[self.gstart]
        gmin_b = np.minimum.reduceat(self.bid, self.gstart); gmax_b = np.maximum.reduceat(self.bid, self.gstart)
        gmin_a = np.minimum.reduceat(self.ask, self.gstart); gmax_a = np.maximum.reduceat(self.ask, self.gstart)
        non_equiv = (gmin_b != gmax_b) | (gmin_a != gmax_a)
        any_crossed = np.logical_or.reduceat(self.crossed, self.gstart)
        # Groups the skip logic may never skip: crossed quotes or equal-time ticks with different quotes.
        self.gexact = non_equiv | any_crossed
        self.exact_idx = np.flatnonzero(self.gexact)
        self.ngroups = len(self.gts)
        nb = (self.ngroups + BLOCK - 1) // BLOCK
        pad = nb * BLOCK - self.ngroups
        def blocks(x, fill, f):
            y = np.concatenate([x, np.full(pad, fill, dtype=x.dtype)]) if pad else x
            return f(y.reshape(nb, BLOCK), axis=1)
        big, small = np.iinfo(np.int64).max, np.iinfo(np.int64).min
        self.bmin_bid, self.bmax_bid = blocks(self.gbid, big, np.min), blocks(self.gbid, small, np.max)
        self.bmin_ask, self.bmax_ask = blocks(self.gask, big, np.min), blocks(self.gask, small, np.max)

    # ---- canonical reconstruction (cold evidence, verified once at admission, used only where a canonical group is needed)
    def canonical_row(self, i):
        a = self.adm
        ts_ms = int(self.ts[i]) // 1_000_000
        if self.kind == "histdata-utc":
            original = str(ts_ms)                      # HistData-UTC keeps the epoch-ms text of the source row
            quote = "CROSSED" if self.crossed[i] else "VALID"
        else:
            original = dt.datetime.fromtimestamp(ts_ms / 1000, dt.timezone.utc).strftime("%d.%m.%Y %H:%M:%S.") + f"{ts_ms % 1000:03d}"
            quote = "VALID"
        ordn = str(int(self.ordinal[i]))
        return {
            "artifact": "BTL-CANONICAL-TICK-1", "ask": _scaled_text(self.ask[i], self.scale), "bid": _scaled_text(self.bid[i], self.scale),
            "datasetId": a["datasetId"],
            "eventId": event_id(a["providerId"], a["feedId"], a["memberHash"], ordn),
            "feedId": a["feedId"], "instrumentId": a["instrumentId"],
            "provenance": {"memberHash": a["memberHash"], "originalTimestamp": original, "sourceId": a["sourceId"]},
            "providerId": a["providerId"],
            "quality": {"duplicateOf": None, "evidenceHash": None, "freshness": "UNKNOWN", "gapBefore": "UNKNOWN_SILENCE", "quote": quote},
            "rawOrdinal": ordn, "resolutionNs": "1000000", "schemaVersion": 1, "timeNs": str(int(self.ts[i])),
            "trustedSequence": None, "datasetVersion": a["datasetVersion"],
        }

    def canonical_group(self, g):
        rows = [self.canonical_row(i) for i in range(int(self.gstart[g]), int(self.gend[g]))]
        return make_group(rows, self.adm["datasetVersion"])

    # ---- exact integer search helpers
    def _first_in_blocks(self, arr, bmin, bmax, lo, hi, op, x):
        """First group index in [lo,hi) with arr[idx] <=/>= x, skipping blocks whose min/max prove no hit."""
        if lo >= hi:
            return hi
        b0, b1 = lo // BLOCK, (hi - 1) // BLOCK + 1
        feasible = (bmin[b0:b1] <= x) if op == "le" else (bmax[b0:b1] >= x)
        for rel in np.flatnonzero(feasible):
            b = b0 + int(rel)
            a, c = max(lo, b * BLOCK), min(hi, (b + 1) * BLOCK)
            seg = arr[a:c]
            hit = np.flatnonzero(seg <= x if op == "le" else seg >= x)
            if len(hit):
                return a + int(hit[0])
        return hi

    def first_order_event(self, state, lo, hi):
        """First group in [lo,hi) at which any live order could change (reference `can_change`), exact integer proofs only.
        Returns lo (i.e. 'cannot prove, scan exactly') for anything not representable as an exact scaled integer."""
        best = hi
        for o in state["orders"].values():
            if o["status"] not in ("PENDING", "ACTIVE"):
                continue
            start = max(lo, int(np.searchsorted(self.gts, int(o["availableNs"]), side="left")))
            if start >= best:
                continue
            side = o["side"]
            d = 1 if side == "LONG" else -1
            def scaled(txt):
                f = Fraction(txt) * self.scale
                return f.numerator if f.denominator == 1 else None
            if o["status"] == "PENDING":
                if o["orderType"] == "MARKET":
                    best = min(best, start); continue
                entry = scaled(o["entry"])
                if entry is None:
                    return lo
                arr, bmin, bmax = (self.gask, self.bmin_ask, self.bmax_ask) if side == "LONG" else (self.gbid, self.bmin_bid, self.bmax_bid)
                limit = o["orderType"] == "LIMIT"
                # diff = d*(value-entry); LIMIT: diff<=0 ; STOP: diff>=0
                op = ("le" if d == 1 else "ge") if limit else ("ge" if d == 1 else "le")
                best = min(best, self._first_in_blocks(arr, bmin, bmax, start, best, op, entry))
            else:  # ACTIVE
                if o["exitRequest"] is not None:
                    best = min(best, start); continue
                arr, bmin, bmax = (self.gbid, self.bmin_bid, self.bmax_bid) if side == "LONG" else (self.gask, self.bmin_ask, self.bmax_ask)
                for key, stop_loss in (("sl", True), ("tp", False)):
                    if o[key] is None:
                        continue
                    x = scaled(o[key])
                    if x is None:
                        return lo
                    # SL: d*(v-sl)<=0 ; TP: d*(v-tp)>=0
                    op = ("le" if d == 1 else "ge") if stop_loss else ("ge" if d == 1 else "le")
                    best = min(best, self._first_in_blocks(arr, bmin, bmax, start, best, op, x))
        return best


class ClaudeSession:
    def __init__(self, source, profile, policy, seed_checkpoint, session_id="session:qa", start_ns=None, archive=False, balance="10000"):
        self.src = source
        self.archive = archive
        self.retention = K.QA_ORDER_RETENTION_V4 if archive else None
        self.opened_ids = set()
        if archive:
            self.state = K.seed_state(session_id, profile, policy, seed_checkpoint, balance, order_retention_policy=self.retention, qa_order_archive_v1=True)
        else:
            self.state = K.seed_state(session_id, profile, policy, seed_checkpoint, balance)
        self.guard = int(self.state["profile"]["maxObservedSilenceNs"])
        self.start_ns = int(self.state["startNs"])
        prev = np.r_[self.start_ns, source.gts[:-1]]
        self.gap_idx = np.flatnonzero(source.gts - prev > self.guard)
        self.tip = hashlib.sha256(("ROOT|" + source.adm["manifestHash"] + "|" + str(self.start_ns)).encode()).hexdigest()
        self.log = []          # durable advance log: tiny records, hash chained
        self.stats = dict(exact_groups=0, skipped_groups=0, jumps=0)
        self._sync_hashes()
        self.serial = 0
        self.full_validate_every_advance = False
        self._fin = None

    def _sync_hashes(self):
        self.state["sourcePrefixHash"] = self.tip
        self.state["sourceCheckpointHash"] = self.tip

    # ---- non-advance commands reuse the repo reducer unchanged
    def command(self, kind, payload, command_id=None):
        self.serial += 1
        raw = dict(schemaVersion=1, artifact="BTL-OBSERVED-EXECUTION-COMMAND-1", sessionId=self.state["sessionId"],
                   commandId=command_id or f"command:{self.serial}", expectedRevision=self.state["revision"], kind=kind, payload=payload)
        if self.archive:
            lookup = lambda oid: dict(status="CLOSED") if oid in self.opened_ids and oid not in self.state["orders"] else None
            self.state, events, _rows = apply(self.state, raw, order_retention_policy=self.retention, qa_order_archive_v1=True, archived_order_lookup=lookup)
        else:
            self.state, events = apply(self.state, raw)
        if kind == "OPEN":
            self.opened_ids.add(raw["commandId"])
        self._commit(dict(t="C", kind=kind, id=raw["commandId"], payload=payload))
        return events

    def _archive_terminal(self, s):
        """Same step `apply` performs after every command: move terminal orders into the hash-chained archive summary."""
        terminal = [(oid, o) for oid, o in sorted(s["orders"].items()) if o["status"] in ("CANCELLED", "CLOSED", "EXPIRED", "UNRESOLVED")]
        summary = s["orderArchive"]
        for oid, order in terminal:
            row = K.archive_append(summary, session_id=s["sessionId"], revision=s["revision"] + 1, order_id=oid, order=order, artifact=QA_ARCHIVE_ARTIFACT)
            summary = K.archive_advance(summary, [row])
            del s["orders"][oid]
        s["orderArchive"] = summary

    def _light_check(self, s):
        """Checks every field a skipped span can change. Orders, balance and flags are untouched on this path."""
        assert int(s["startNs"]) <= int(s["throughNs"])
        last, count = s["lastObservedNs"], int(s["nextGroupIndex"])
        assert (last is None) == (count == 0)
        if last is not None:
            assert int(s["startNs"]) <= int(last) <= int(s["throughNs"])
        if s["quoteBasis"] is not None:
            assert int(s["quoteBasis"]["timeNs"]) <= int(s["throughNs"])
        assert count <= self.src.ngroups

    FIN_FIELDS = ("orders", "balance", "realizedGross", "financial", "unresolved", "ended", "eventHash", "nextEventIndex", "orderArchive")

    def _fin_hash(self):
        """Hash of the financial part of the state only (what a fill/exit/cancel/order can change)."""
        return content_hash(dict(schemaVersion=1, **{k: self.state[k] for k in self.FIN_FIELDS if k in self.state}))

    def _commit(self, rec, dirty=True):
        """Append a durable record. The chain binds: previous tip, the record, the cursor fields it carries and the
        financial-state hash. The financial hash is recomputed only when something financial can have changed; light advances
        carry the cached value, so a saved state cannot be edited without breaking the chain."""
        if dirty or self._fin is None:
            self._fin = self._fin_hash()
        rec = dict(rec, fin=self._fin)
        self.tip = hashlib.sha256((self.tip + "|" + json.dumps(rec, sort_keys=True, separators=(",", ":"))).encode()).hexdigest()
        self.log.append(rec)
        self._sync_hashes()

    def _next_exact(self, i, hi, live):
        s = self.src
        j = hi
        k = int(np.searchsorted(s.exact_idx, i));
        if k < len(s.exact_idx):
            j = min(j, int(s.exact_idx[k]))
        if live:
            if j > i:
                j = min(j, s.first_order_event(self.state, i, j))
            k = int(np.searchsorted(self.gap_idx, i))
            if k < len(self.gap_idx):
                j = min(j, int(self.gap_idx[k]))
        return j

    def _process_exact(self, g, events):
        """Same per-group body as observed_kernel._advance (coverage/diagnostics empty: admission-proved)."""
        s, p = self.state, self.state["profile"]
        group = self.src.canonical_group(g)
        rows, moment = group["events"], int(group["timeNs"])
        live = K._live(s) and not s["unresolved"] and not s["ended"]
        anchor = int(s["lastObservedNs"]) if s["lastObservedNs"] is not None else int(s["startNs"])
        quality_bad = any(r["quality"]["quote"] != "VALID" or r["quality"]["freshness"] not in ("UNKNOWN", "CONFIRMED")
                          or r["quality"]["gapBefore"] not in ("UNKNOWN_SILENCE", "NONE", "KNOWN_SESSION_CLOSED")
                          or r["quality"]["duplicateOf"] is not None for r in rows)
        precision_bad = False
        try:
            for r in rows:
                K.price(r["bid"], p); K.price(r["ask"], p)
        except K.ContractError:
            precision_bad = True
        equivalent = len({(r["bid"], r["ask"]) for r in rows}) == 1
        if live and moment - anchor > self.guard and s["model"] != MODEL_V2:
            K._unresolved(s, events, "UNRESOLVED_OBSERVED_SILENCE", group["groupId"])
        elif live and moment - anchor > self.guard:
            closed = all(r["quality"]["gapBefore"] == "KNOWN_SESSION_CLOSED" for r in rows)
            K.emit(s, events, "DATA_GAP_LIMITATION", groupId=group["groupId"], gapStartNs=str(anchor), gapEndNs=str(moment),
                   elapsedNs=str(moment - anchor), gapKind="MARKET_CLOSED" if closed else "UNKNOWN_COVERAGE_GAP",
                   affectedOrders=[k for k, v in sorted(s["orders"].items()) if v["status"] in ("PENDING", "ACTIVE")],
                   quoteAvailable=True, execution="OBSERVED_QUOTES_ONLY", sourceQuality="UNKNOWN")
        if live and not s["unresolved"] and (quality_bad or precision_bad):
            K._unresolved(s, events, "UNRESOLVED_QUOTE_QUALITY" if quality_bad else "UNRESOLVED_QUOTE_PRECISION", group["groupId"])
        if live and not s["unresolved"]:
            changes = any(K.can_change(s, r) for r in rows)
            if not equivalent and changes:
                K._unresolved(s, events, "UNRESOLVED_EQUAL_TIME_ORDER", group["groupId"])
            elif not equivalent:
                K.emit(s, events, "CHRONOLOGY_LIMITATION", groupId=group["groupId"], timeNs=group["timeNs"], commonOutcome="NO_FINANCIAL_ACTION")
            elif changes:
                K._fills(s, events, group)
        if quality_bad or precision_bad:
            if not live:
                K.emit(s, events, "UNUSABLE_OBSERVATION", classification="UNRESOLVED", groupId=group["groupId"], reason="QUALITY" if quality_bad else "PRECISION")
        s["quoteBasis"] = None if not equivalent or quality_bad or precision_bad else dict(
            timeNs=group["timeNs"], groupId=group["groupId"], bid=rows[0]["bid"], ask=rows[0]["ask"],
            eventIds=[r["eventId"] for r in rows], chronologyLimited=len(rows) > 1 and group["order"] == "UNTRUSTED")
        s["lastObservedNs"] = group["timeNs"]; s["nextGroupIndex"] = str(int(s["nextGroupIndex"]) + 1)
        self.stats["exact_groups"] += 1

    def _skip_span(self, i, j):
        """Groups [i,j) proven event-free: only the last group's quote basis is needed (one canonical group)."""
        s = self.state
        group = self.src.canonical_group(j - 1)
        rows = group["events"]
        s["quoteBasis"] = dict(timeNs=group["timeNs"], groupId=group["groupId"], bid=rows[0]["bid"], ask=rows[0]["ask"],
                               eventIds=[r["eventId"] for r in rows], chronologyLimited=len(rows) > 1 and group["order"] == "UNTRUSTED")
        s["lastObservedNs"] = group["timeNs"]
        s["nextGroupIndex"] = str(int(s["nextGroupIndex"]) + (j - i))
        self.stats["skipped_groups"] += j - i; self.stats["jumps"] += 1

    def next_event_ns(self):
        """Time of the first revealed group at which a live order could change (exact integer proof) or a data gap is crossed.
        None when no order is live or nothing more can happen inside the source. Never looks at an order's outcome, only at
        where it could first be decided, so this is the "jump to next event" target."""
        s, src = self.state, self.src
        if not K._live(s) or s["unresolved"] or s["ended"]:
            return None
        i = int(s["nextGroupIndex"])
        j = src.first_order_event(s, i, src.ngroups)
        k = int(np.searchsorted(self.gap_idx, i))
        if k < len(self.gap_idx):
            j = min(j, int(self.gap_idx[k]))
        return int(src.gts[j]) if j < src.ngroups else None

    def advance_through(self, target):
        s = self.state
        old, target = int(s["throughNs"]), int(target)
        assert not s["ended"] and old <= target
        events, src = [], self.src
        exact_before = self.stats["exact_groups"]
        i = int(s["nextGroupIndex"])
        hi = int(np.searchsorted(src.gts, target, side="right"))
        while i < hi:
            live = K._live(s) and not s["unresolved"] and not s["ended"]
            j = self._next_exact(i, hi, live)
            if j > i:
                self._skip_span(i, j); i = j
            if i < hi and j == i:
                self._process_exact(i, events); i += 1
        guard, through = self.guard, target
        if K._live(s) and not s["unresolved"] and not s["ended"]:
            anchor = int(s["lastObservedNs"]) if s["lastObservedNs"] is not None else int(s["startNs"])
            if through - anchor > guard and s["model"] != MODEL_V2:
                K._unresolved(s, events, "UNRESOLVED_OBSERVED_SILENCE")
            elif through - anchor > guard:
                if s["quoteBasis"] is not None:
                    K.emit(s, events, "STALE_QUOTE", classification="OBSERVED_FEED_EVENT", quoteTimeNs=s["quoteBasis"]["timeNs"],
                           throughNs=str(through), ageNs=str(through - int(s["quoteBasis"]["timeNs"])), gapKind="UNKNOWN_COVERAGE_GAP")
                    s["quoteBasis"] = None
                K.emit(s, events, "DATA_GAP_LIMITATION", gapStartNs=str(anchor), gapEndNs=str(through), elapsedNs=str(through - anchor),
                       gapKind="UNKNOWN_COVERAGE_GAP",
                       affectedOrders=[k for k, v in sorted(s["orders"].items()) if v["status"] in ("PENDING", "ACTIVE")],
                       quoteAvailable=False, execution="OBSERVED_QUOTES_ONLY", sourceQuality="UNKNOWN")
        s["throughNs"] = str(through)
        s["sourceCursorRevision"] = str(int(s["sourceCursorRevision"]) + 1)
        dirty = bool(events) or self.stats["exact_groups"] != exact_before
        # NOTE: the reference emits a REPLAY_ADVANCED progress event when an advance has no other event. It is not a
        # financial event; here progress lives in the advance log instead (proposal, needs owner approval for product use).
        if self.archive and dirty:
            self._archive_terminal(s)
        s["revision"] += 1
        if dirty or self.full_validate_every_advance:
            validate_state(s, order_retention_policy=self.retention)          # financial state may have changed: full reference validation
        else:
            self._light_check(s)       # only cursor fields moved; orders/balance are byte-identical to the validated state
        self._commit(dict(t="A", target=str(target), next=s["nextGroupIndex"]), dirty=dirty)
        return events

    # ---- recovery: rebuild the tip from the durable advance log, compare with the saved state
    def snapshot(self):
        return dict(state=deepcopy(self.state), log=list(self.log), tip=self.tip, serial=self.serial, archive=self.archive)

    @classmethod
    def recover(cls, source, profile, policy, seed_checkpoint, snap):
        """Cheap recovery: verify the hash chain over the durable log, that the saved state is exactly the state the last
        record committed to, and that the cursor is inside the pinned source."""
        self = cls(source, profile, policy, seed_checkpoint, archive=snap.get("archive", False), balance=snap["state"]["initialBalance"], session_id=snap["state"]["sessionId"])
        tip = self.tip
        for rec in snap["log"]:
            tip = hashlib.sha256((tip + "|" + json.dumps(rec, sort_keys=True, separators=(",", ":"))).encode()).hexdigest()
        if tip != snap["tip"] or snap["state"]["sourcePrefixHash"] != tip:
            raise ValueError("RECOVERY_CHAIN_MISMATCH")
        self.state, self.log, self.tip, self.serial = deepcopy(snap["state"]), list(snap["log"]), tip, snap["serial"]
        self.opened_ids = {r["id"] for r in snap["log"] if r["t"] == "C" and r["kind"] == "OPEN"}
        if snap["log"]:
            last = snap["log"][-1]
            if self._fin_hash() != last["fin"]:
                raise ValueError("RECOVERY_STATE_HASH_MISMATCH")
            self._fin = last["fin"]
            a = [r for r in snap["log"] if r["t"] == "A"]
            if a and (a[-1]["next"] != self.state["nextGroupIndex"] or a[-1]["target"] != self.state["throughNs"]):
                raise ValueError("RECOVERY_CURSOR_MISMATCH")
            k = int(self.state["nextGroupIndex"])
            if k and str(int(source.gts[k - 1])) != self.state["lastObservedNs"]:
                raise ValueError("RECOVERY_LAST_OBSERVED_MISMATCH")
            qb = self.state["quoteBasis"]
            if qb is not None and qb["groupId"] != source.canonical_group(k - 1)["groupId"]:
                raise ValueError("RECOVERY_QUOTE_BASIS_MISMATCH")
        if int(self.state["nextGroupIndex"]) > source.ngroups:
            raise ValueError("RECOVERY_CURSOR_BEYOND_SOURCE")
        validate_state(self.state, order_retention_policy=self.retention)
        return self

    @classmethod
    def verify_by_replay(cls, source, profile, policy, seed_checkpoint, snap):
        """Independent recovery proof: deterministically re-execute every logged advance/command from the seed and require
        byte-identical state and chain. Affordable because the jump engine replays millions of ticks per second."""
        self = cls(source, profile, policy, seed_checkpoint, archive=snap.get("archive", False), balance=snap["state"]["initialBalance"], session_id=snap["state"]["sessionId"])
        for rec in snap["log"]:
            if rec["t"] == "A":
                self.advance_through(rec["target"])
            else:
                self.command(rec["kind"], rec["payload"], rec["id"])
        validate_state(self.state, order_retention_policy=self.retention)
        if self.log != snap["log"] or self.tip != snap["tip"] or self.state != snap["state"]:
            raise ValueError("REPLAY_VERIFICATION_MISMATCH")
        return self
