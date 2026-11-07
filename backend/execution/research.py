"""Local Method/Session application over the ONE durable tick domain."""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from fractions import Fraction
import json

from application.models import TrustedScope
from contracts.canonical import content_hash, canonical_bytes
from contracts.models import MethodPolicy, Command, SessionContext, Observation, validate_command
from contracts.primitives import require, identifier, revision, digest
from ticks.contracts import keys, tag, TickManifest
from ticks.timeline import TickTimeline
from infrastructure.database import connect
from .contracts import seed_state, policy_wire, open_payload, exact, text, price, risk_quantity, MAX_ORDERS
from .controller import ExecutionController
from .postgres import PostgresExecutionStore, pack, unpack, snapshot
from .research_fixture import research_provider, research_profile, START_NS, STEP_NS, WARMUP_NS
from .workspace import FixtureTimelineCache, display_candles, TIMEFRAMES
from .analysis import project, metrics, planned_risk, excursions, ratio, RESEARCH_VERSION, MAX_ANALYSIS_EVENTS
from .journal import (validate_note, request as journal_request, MAX_JOURNAL_ORDERS,
                      MAX_JOURNAL_PAGE_SIZE, MAX_JOURNAL_READ_ORDERS,
                      encode_cursor, decode_cursor)
from .bootstrap import bootstrap as descriptive_bootstrap, validate_seed
from .availability import catalog_availability, eligible_start_month


def label(value):
    require(type(value) is str and 1 <= len(value.strip()) <= 128 and
            not any(ord(c) < 32 for c in value), "label")
    return value.strip()


def method_policy(record):
    tag(record, "BTL-LOCAL-METHOD-1", "id name kind checklistOn conditions riskPercent rr")
    label(record["name"]); identifier(record["id"], "methodId")
    require(type(record["conditions"]) is list and len(record["conditions"]) <= 64, "conditions")
    for c in record["conditions"]:
        keys(c, "id label"); identifier(c["id"], "conditionId"); label(c["label"])
    if record["kind"] == "PROTOCOL":
        exact(record["riskPercent"], "riskPercent", True); exact(record["rr"], "rr", True)
    return MethodPolicy(record["id"], content_hash(record), record["kind"], record["checklistOn"],
                        tuple(c["id"] for c in record["conditions"]), record["riskPercent"], record["rr"])


class ResearchApplication:
    """Single-user local operator; no public identity/tenant composition."""
    def __init__(self, dsn, scope=None, *, historical_source=None, synthetic_provider=None,
                 state_storage_format="snapshot-v1"):
        require(historical_source is None or synthetic_provider is None, 'source', 'IDENTITY_CONFLICT')
        if synthetic_provider is not None:
            manifest = TickManifest.from_wire(
                synthetic_provider.describe(synthetic_provider.dataset_id, synthetic_provider.dataset_version),
                synthetic_provider.dataset_version).wire
            require(manifest['evidenceClass'] == 'SYNTHETIC_CONTRACT_ONLY' and
                    manifest['rights']['class'] == 'SYNTHETIC',
                    'syntheticProvider', 'REFUSED_SOURCE')
        self.dsn = dsn
        self.scope = scope or TrustedScope("local:exness:"+historical_source.version if historical_source else "fixture:local-alpha", "fixture:local-operator")
        self.__historical = historical_source
        self.__provider = historical_source or synthetic_provider or research_provider()
        self.__profile = historical_source.profile if historical_source else research_profile()
        self.__label = historical_source.label if historical_source else "SYNTHETIC / TEST ONLY"
        self.__start = historical_source.start_ns if historical_source else START_NS
        self.__warmup = self.__start + 1800*1000000000 if historical_source else WARMUP_NS
        self.__period = historical_source.start_period if historical_source else "2020-01"
        self.store = PostgresExecutionStore(dsn, state_storage_format=state_storage_format)
        if historical_source:
            from .historical import IndexedTimelineCache
            self.__timeline_cache = IndexedTimelineCache(historical_source)
        else:
            self.__timeline_cache = FixtureTimelineCache(self.__provider,
                allow_injected_synthetic=synthetic_provider is not None)
        self.controller = ExecutionController(self.store, self.__provider, self.__timeline_cache)

    def close(self):
        if self.__historical:
            self.__timeline_cache.close()

    def _catalog_lock(self, db):
        db.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (self.scope.workspace_id,))

    def _method(self, db, method_id):
        identifier(method_id, "methodId")
        row = db.execute("SELECT payload,content_hash FROM btl.tick_methods WHERE workspace_id=%s AND method_id=%s",
                         (self.scope.workspace_id, method_id)).fetchone()
        require(row is not None, "method", "RESOURCE_UNAVAILABLE")
        value = unpack(*row); method_policy(value)
        require(value["id"] == method_id, "method", "CORRUPT_RECORD")
        return value

    def _session(self, db, session_id, lock=False):
        identifier(session_id, "sessionId")
        meta_row = db.execute("SELECT payload,content_hash,method_id FROM btl.tick_research_sessions WHERE workspace_id=%s AND session_id=%s",
                              (self.scope.workspace_id, session_id)).fetchone()
        require(meta_row is not None, "session", "RESOURCE_UNAVAILABLE")
        meta = unpack(*meta_row[:2])
        tag(meta, "BTL-LOCAL-SESSION-1", "id name methodId methodHash datasetId datasetVersion profileHash startPeriod initialBalance")
        require(meta["id"] == session_id and meta["methodId"] == meta_row[2], "session", "CORRUPT_RECORD")
        method = self._method(db, meta["methodId"])
        policy = method_policy(method)
        row = db.execute("SELECT payload,content_hash,revision,dataset_version,profile_hash FROM btl.tick_sessions WHERE workspace_id=%s AND session_id=%s" + (" FOR UPDATE" if lock else ""),
                         (self.scope.workspace_id, session_id)).fetchone()
        require(row is not None, "state", "CORRUPT_RECORD")
        saved = self.store.read_session(db, self.scope, session_id, row)
        state, checkpoint = saved["state"], saved["controller"]
        snapshot(state, checkpoint)
        require(state["sessionId"] == session_id and state["revision"] == row[2] and
                state["policy"] == policy_wire(policy) and meta["methodHash"] == policy.definition_hash and
                (meta["datasetId"],meta["datasetVersion"],meta["profileHash"],meta["initialBalance"]) ==
                (state["datasetId"],state["datasetVersion"],state["profileHash"],state["initialBalance"]), "sessionPins", "CORRUPT_RECORD")
        require(state["datasetId"] == self.__provider.dataset_id and state["datasetVersion"] == self.__provider.dataset_version,
                "dataset", "REFUSED_DATASET_VERSION")
        return meta, method, state, checkpoint

    def catalog(self):
        with connect(self.dsn) as db:
            db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            methods = db.execute("SELECT payload,content_hash FROM btl.tick_methods WHERE workspace_id=%s ORDER BY method_id LIMIT 129", (self.scope.workspace_id,)).fetchall()
            sessions = db.execute("SELECT payload,content_hash FROM btl.tick_research_sessions WHERE workspace_id=%s ORDER BY session_id LIMIT 129", (self.scope.workspace_id,)).fetchall()
            require(len(methods) <= 128 and len(sessions) <= 128, "catalog", "REFUSED_CATALOG_LIMIT")
            parsed = [unpack(*row) for row in methods]
            for value in parsed:
                method_policy(value)
            metas = [unpack(*row) for row in sessions]
            for meta in metas:
                self._session(db, meta["id"])
            return dict(schemaVersion=1, artifact="BTL-LOCAL-CATALOG-1", methods=parsed, sessions=metas,
                        label=self.__label, profile=self.__profile, startPeriod=self.__period,
                        availability=self.availability())

    def availability(self):
        return catalog_availability(instrument_id=self.__profile["instrumentId"],
                                    dataset_id=self.__provider.dataset_id,
                                    dataset_version=self.__provider.dataset_version,
                                    start_period=self.__period,
                                    synthetic=self.__historical is None)

    def assert_start_month_available(self, period):
        require(eligible_start_month(self.availability(), self.__profile["instrumentId"], period),
                "period", "REFUSED_SOURCE_NOT_AVAILABLE")

    def command_result(self, session_id, command_id):
        """Read the durable command receipt or conservatively report uncertainty."""
        identifier(session_id, "sessionId")
        identifier(command_id, "commandId")
        with connect(self.dsn) as db:
            db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            _meta, _method, state, _checkpoint = self._session(db, session_id)
            row = db.execute(
                "SELECT revision,command_hash,payload,content_hash FROM btl.tick_commands "
                "WHERE workspace_id=%s AND session_id=%s AND command_id=%s",
                (self.scope.workspace_id, session_id, command_id)).fetchone()
            if row is not None:
                review_row = db.execute(
                    "SELECT payload,content_hash FROM btl.tick_order_reviews "
                    "WHERE workspace_id=%s AND session_id=%s AND review_id=%s",
                    (self.scope.workspace_id, session_id, command_id)).fetchone()
                require(review_row is not None, "review", "CORRUPT_RECORD")
                reviewed = unpack(*review_row)
                command = reviewed.get("command", {})
                receipt_wire = unpack(row[2], row[3])
                if receipt_wire.get("artifact") == "BTL-TICK-EXECUTION-COMPACT-RESULT-1":
                    receipt = self.store._compact_receipt(command, row, db,
                                                          self.scope.workspace_id, session_id)
                else:
                    receipt = receipt_wire
                require(receipt.get("artifact") == "BTL-TICK-EXECUTION-RESULT-1" and
                        receipt.get("commandId") == command_id and
                        receipt.get("commandHash") == row[1] and receipt.get("durable") is True and
                        receipt.get("state", {}).get("sessionId") == session_id and
                        receipt["state"].get("revision") == row[0], "receipt", "CORRUPT_RECORD")
                expected_revision = command.get("expectedRevision")
                require(command.get("commandId") == command_id and
                        command.get("sessionId") == session_id and type(expected_revision) is int and
                        expected_revision + 1 == receipt["state"]["revision"] and
                        content_hash(command) == row[1], "review", "CORRUPT_RECORD")
                return dict(schemaVersion=1, artifact="BTL-TICK-COMMAND-STATUS-1",
                            sessionId=session_id, commandId=command_id, status="COMMITTED",
                            currentRevision=state["revision"], reviewHash=review_row[1], receipt=receipt)

            review_row = db.execute(
                "SELECT payload,content_hash FROM btl.tick_order_reviews "
                "WHERE workspace_id=%s AND session_id=%s AND review_id=%s",
                (self.scope.workspace_id, session_id, command_id)).fetchone()
            if review_row is None:
                return dict(schemaVersion=1, artifact="BTL-TICK-COMMAND-STATUS-1",
                            sessionId=session_id, commandId=command_id, status="UNKNOWN",
                            reason="REVIEW_OR_COMMAND_NOT_VISIBLE", currentRevision=state["revision"])

            reviewed = unpack(*review_row)
            command = reviewed.get("command", {})
            require(command.get("commandId") == command_id and command.get("sessionId") == session_id,
                    "review", "CORRUPT_RECORD")
            expected_revision = command.get("expectedRevision")
            revision(expected_revision, "expectedRevision")
            require(command_id not in state["orders"], "receipt", "CORRUPT_RECORD")
            common = dict(schemaVersion=1, artifact="BTL-TICK-COMMAND-STATUS-1",
                          sessionId=session_id, commandId=command_id, reviewHash=review_row[1],
                          expectedRevision=expected_revision, currentRevision=state["revision"])
            if state["revision"] > expected_revision:
                return dict(**common, status="NOT_COMMITTED", reason="SESSION_REVISION_ADVANCED")
            return dict(**common, status="UNKNOWN", reason="NO_DURABLE_COMMAND_AT_REVIEW_REVISION")

    def summary(self, session_id):
        """One committed, scoped snapshot; no timeline, quote or event replay."""
        with connect(self.dsn) as db:
            db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            meta, _method, state, _checkpoint = self._session(db, session_id)
            return dict(schemaVersion=1, artifact="BTL-SESSION-SUMMARY-1",
                        sessionId=meta["id"], revision=state["revision"],
                        throughNs=state["throughNs"], datasetId=state["datasetId"],
                        datasetVersion=state["datasetVersion"], profileHash=state["profileHash"],
                        accountCurrency=state["profile"]["accountCurrency"],
                        initialBalance=state["initialBalance"], balance=state["balance"],
                        netCashChange=text(Fraction(state["balance"])-Fraction(state["initialBalance"])),
                        completedTrades=sum(o["status"] == "CLOSED" for o in state["orders"].values()),
                        unresolved=state["unresolved"], ended=state["ended"],
                        model="SIMULATED_QUOTE_BASELINE_NOT_BROKER_EXECUTION")

    def method_analytics(self, method_id):
        """Pool completed committed positions across compatible Sessions only.

        This is a bounded read projection. It never combines account balances,
        runs a replay, or treats incomplete Sessions as zero-return samples.
        """
        from .analysis import MAX_ANALYSIS_EVENTS, metrics
        identifier(method_id, 'methodId')
        with connect(self.dsn) as db:
            db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            method = self._method(db, method_id)
            policy = method_policy(method)
            rows = db.execute(
                'SELECT session_id FROM btl.tick_research_sessions WHERE workspace_id=%s AND method_id=%s '
                'ORDER BY session_id LIMIT 129', (self.scope.workspace_id, method_id)).fetchall()
            require(len(rows) <= 128, 'methodSessions', 'REFUSED_METHOD_ANALYSIS_LIMIT')

            compatible = []
            excluded = []
            event_budget = 0
            units = set()
            for (session_id,) in rows:
                meta, _method, state, _checkpoint = self._session(db, session_id)
                require(meta.get('artifact') == 'BTL-LOCAL-SESSION-1' and
                        meta.get('methodHash') == policy.definition_hash,
                        'methodSession', 'CORRUPT_RECORD')
                current_unit = (state['profileHash'], state['engineVersion'],
                                state['profile']['accountCurrency'])
                units.add(current_unit)
                compatible.append((session_id, state['revision'], current_unit))
                event_budget += state['nextEventIndex']

            common = dict(schemaVersion=1, artifact='BTL-METHOD-ANALYTICS-1', methodId=method_id,
                          methodHash=policy.definition_hash,
                          aggregation='POOLED_COMMITTED_COMPLETED_POSITIONS',
                          balancesCombined=False, financialAuthority='COMMITTED_EVENTS_ONLY')
            if len(units) > 1:
                return dict(**common, status='UNAVAILABLE', reason='INCOMPATIBLE_FINANCIAL_UNITS',
                            includedSessions=[], excludedSessions=[
                                {'sessionId': item[0], 'reason': 'MULTIPLE_FINANCIAL_UNITS'} for item in compatible],
                            metrics=None)
            if event_budget > MAX_ANALYSIS_EVENTS:
                return dict(**common, status='UNAVAILABLE', reason='REFUSED_METHOD_ANALYSIS_LIMIT',
                            eventBudget=MAX_ANALYSIS_EVENTS, observedEventCount=event_budget,
                            includedSessions=[], excludedSessions=excluded + [
                                {'sessionId': item[0], 'reason': 'METHOD_EVENT_BUDGET'} for item in compatible],
                            metrics=None)

            completed = []
            included = []
            for session_id, revision_value, _current_unit in compatible:
                _meta, _method, state, _checkpoint = self._session(db, session_id)
                analysis = self._committed_analysis(db, state)
                if analysis['status'] != 'COMPLETE':
                    excluded.append({'sessionId': session_id, 'reason': analysis.get('reason', 'ANALYSIS_UNAVAILABLE')})
                    continue
                completed.extend(analysis['completed'])
                included.append({'sessionId': session_id, 'revision': revision_value,
                                 'datasetId': state['datasetId'], 'datasetVersion': state['datasetVersion'],
                                 'profileHash': state['profileHash'], 'engineVersion': state['engineVersion'],
                                 'eventHead': state['eventHash'], 'tradeCount': len(analysis['completed'])})

            pooled = metrics(completed)
            # Trade order across separate Sessions has no shared chronology, so
            # cross-Session streaks and balances are intentionally not reported.
            pooled.pop('maxWinStreak', None)
            pooled.pop('maxLossStreak', None)
            unit = next(iter(units), None)
            return dict(**common, status='COMPLETE', accountCurrency=unit[2] if unit else None,
                        completedTradeNet=text(sum((Fraction(row['net']) for row in completed), Fraction())),
                        includedSessions=included, excludedSessions=excluded, metrics=pooled)

    def create_method(self, raw):
        raw = deepcopy(raw)
        raw["name"] = label(raw.get("name"))
        policy = method_policy(raw)
        require(policy.kind != "FREE_STYLE" or not policy.conditions, "freeStyleConditions")
        blob, sha = pack(raw)
        with connect(self.dsn) as db:
            self._catalog_lock(db)
            prior = db.execute("SELECT content_hash FROM btl.tick_methods WHERE workspace_id=%s AND method_id=%s", (self.scope.workspace_id,raw["id"])).fetchone()
            if prior:
                require(prior[0] == sha, "methodId", "REFUSED_IDEMPOTENCY_CONFLICT")
                return self._method(db,raw["id"])
            count = db.execute("SELECT count(*) FROM btl.tick_methods WHERE workspace_id=%s",(self.scope.workspace_id,)).fetchone()[0]
            require(count < 128, "methods", "REFUSED_CATALOG_LIMIT")
            db.execute("INSERT INTO btl.tick_methods VALUES (%s,%s,%s,%s)",(self.scope.workspace_id,raw["id"],blob,sha))
            from .product_method_lifecycle import register_first_version
            register_first_version(db, self.scope.workspace_id, raw["id"])
        return raw

    def create_session(self, raw):
        keys(raw, "id name methodId initialBalance startPeriod")
        identifier(raw["id"], "sessionId"); label(raw["name"])
        if self.__historical:
            start = self.__historical.start_for_period(raw["startPeriod"])
            warmup = start + 1800*1000000000
        else:
            require(raw["startPeriod"] == self.__period, "period", "REFUSED_FIXTURE_PERIOD")
            start, warmup = self.__start, self.__warmup
        timeline = None
        seeded = False
        try:
            with connect(self.dsn) as db:
                self._catalog_lock(db)
                from .product_method_lifecycle import require_active_method
                require_active_method(db, self.scope.workspace_id, raw["methodId"])
                method = self._method(db, raw["methodId"]); policy = method_policy(method)
                state = seed_state(raw["id"], self.__provider.dataset_id, self.__provider.dataset_version,
                                   str(start), self.__profile, policy, raw["initialBalance"])
                require(exact(raw["initialBalance"],"initialBalance",True) == Fraction(state["initialBalance"]), "moneyPrecision")
                meta = dict(schemaVersion=1, artifact="BTL-LOCAL-SESSION-1", id=raw["id"], name=label(raw["name"]), methodId=raw["methodId"],
                            methodHash=policy.definition_hash, datasetId=state["datasetId"], datasetVersion=state["datasetVersion"],
                            profileHash=state["profileHash"], startPeriod=raw["startPeriod"], initialBalance=state["initialBalance"])
                blob, sha = pack(meta)
                prior = db.execute("SELECT content_hash FROM btl.tick_research_sessions WHERE workspace_id=%s AND session_id=%s", (self.scope.workspace_id,raw["id"])).fetchone()
                if prior:
                    # Dedup before constructing a disk timeline: never reset a
                    # previously committed Session's private position lookup.
                    require(prior[0] == sha, "sessionId", "REFUSED_IDEMPOTENCY_CONFLICT")
                    self._session(db,raw["id"])
                else:
                    count = db.execute("SELECT count(*) FROM btl.tick_research_sessions WHERE workspace_id=%s",(self.scope.workspace_id,)).fetchone()[0]
                    require(count < 128, "sessions", "REFUSED_CATALOG_LIMIT")
                    timeline = self.__timeline_cache.new_timeline(self.scope, raw["id"], start) if self.__historical else TickTimeline(self.__provider, self.__provider.dataset_id, self.__provider.dataset_version, str(start))
                    timeline.seek(str(warmup))
                    state.update(throughNs=timeline.cursor["throughNs"], nextGroupIndex=timeline.cursor["nextGroupIndex"])
                    self.store._insert(db,self.scope,state,timeline.checkpoint())
                    db.execute("INSERT INTO btl.tick_research_sessions VALUES (%s,%s,%s,%s,%s)",(self.scope.workspace_id,raw["id"],raw["methodId"],blob,sha))
            if timeline is not None:
                self.__timeline_cache.seed(self.scope, raw['id'], timeline)
                seeded = True
        finally:
            if self.__historical and timeline is not None and not seeded:
                self.__timeline_cache.discard(timeline)
        return self.inspect(raw["id"])

    def _quote(self, state, checkpoint):
        groups = self.__timeline_cache.window(self.scope, state['sessionId'], checkpoint, last_only=True)
        return deepcopy(groups[-1]["events"][-1]) if groups else None

    def chart_history(self, session_id, raw):
        keys(raw, 'timeframe offset')
        require(self.__historical is not None,'history','HISTORY_UNAVAILABLE')
        with connect(self.dsn) as db:
            meta, _, _, _ = self._session(db, session_id)
        return self.__historical.chart_history(meta['startPeriod'],raw['timeframe'],raw['offset'])

    def inspect(self, session_id, timeframe=None):
        with connect(self.dsn) as db:
            db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            meta, method, state, checkpoint = self._session(db,session_id)
            rows = db.execute("SELECT payload,content_hash FROM btl.tick_events WHERE workspace_id=%s AND session_id=%s ORDER BY sequence DESC LIMIT 256",
                              (self.scope.workspace_id,session_id)).fetchall()
            view = dict(schemaVersion=1, artifact="BTL-LOCAL-SESSION-VIEW-1", metadata=meta, method=method, state=state,
                        events=[unpack(*row) for row in reversed(rows)], eventWindowStart=max(0,state["nextEventIndex"]-256),
                        quote=self._quote(state,checkpoint), label=self.__label)
            if self.__historical:
                view['replayStepNs'] = '1000000000'
            if timeframe is not None:
                groups = self.__timeline_cache.window(self.scope, session_id, checkpoint)
                start = max(0,int(state['nextGroupIndex'])-len(groups))
                view['chart'] = display_candles(groups,state['throughNs'],timeframe,start)
                def committed_events():
                    # Small bounded pages from this same repeatable-read snapshot.
                    # Refusal above the projection budget occurs before this generator runs.
                    for offset in range(0, min(state['nextEventIndex'], MAX_ANALYSIS_EVENTS), 256):
                        page = db.execute('SELECT payload,content_hash FROM btl.tick_events WHERE workspace_id=%s AND session_id=%s AND sequence >= %s ORDER BY sequence LIMIT 256',
                            (self.scope.workspace_id,session_id,offset)).fetchall()
                        for row in page:
                            yield unpack(*row)
                view['analysis'] = project(state, committed_events(), view['quote'])
                self._research_risk(db, state, view['analysis'])
                self._research_excursions(state,view['analysis'],groups)
            return view

    def _research_risk(self, db, state, analysis):
        """Join only accepted orders to their immutable confirmed review, never future drafts."""
        if analysis['status'] != 'COMPLETE':
            return
        orders = {row['id']: row for row in analysis['orders']}
        if orders:
            pins = db.execute('SELECT r.review_id,r.payload,r.content_hash,c.command_hash,c.revision '
                'FROM btl.tick_order_reviews r JOIN btl.tick_commands c '
                'ON r.workspace_id=c.workspace_id AND r.session_id=c.session_id AND r.review_id=c.command_id '
                'WHERE r.workspace_id=%s AND r.session_id=%s AND r.review_id=ANY(%s) LIMIT 129',
                (self.scope.workspace_id,state['sessionId'],list(orders))).fetchall()
            require(len(pins)<=128,'riskPins','CORRUPT_RECORD')
            for order_id, payload, sha, command_hash, committed_revision in pins:
                reviewed = unpack(payload,sha)
                command = reviewed['command']; order = orders[order_id]
                require(command['kind']=='OPEN' and command['commandId']==order_id and
                    command['sessionId']==state['sessionId'] and content_hash(command)==command_hash and
                    committed_revision==command['expectedRevision']+1 and committed_revision<=state['revision'] and
                    all(order[k]==v for k,v in command['payload'].items()) and
                    reviewed['profileHash']==state['profileHash'] and
                    reviewed['methodHash']==state['policy']['definitionHash'] and
                    int(reviewed['throughNs'])<=int(state['throughNs']), 'riskReview','CORRUPT_RECORD')
                # Existing pinless reviews remain excluded. No historical retrofit.
                if 'researchRisk' not in reviewed:
                    continue
                basis = dict(state,throughNs=reviewed['throughNs'])
                pin = reviewed['researchRisk']
                require(pin==planned_risk(basis,command),'riskPin','CORRUPT_RECORD')
                require(order['entryTimeNs'] is None or int(reviewed['throughNs'])<=int(order['entryTimeNs']),
                        'preentryRisk','CORRUPT_RECORD')
                order['plannedInitialRisk'] = pin['amount']
                if pin['amount'] is not None and order['status']=='CLOSED':
                    order['rMultiple'] = ratio(Fraction(order['net'])/Fraction(pin['amount']))
                    order['rReason'] = None
                elif pin['amount'] is None:
                    order['rReason'] = pin['reason']
        analysis['metrics'].update(metrics(analysis['completed']))
        analysis['provenance']['researchVersion'] = RESEARCH_VERSION

    def _research_excursions(self, state, analysis, groups):
        if analysis['status']!='COMPLETE':
            return
        for row in analysis['orders']:
            if row['status']!='CLOSED':
                row['excursionReason']='POSITION_NOT_COMPLETED'
        values=excursions(analysis['completed'],groups,state)
        for row in analysis['completed']:
            row.update(values[row['id']])
        analysis['provenance']['excursionVersion']='BTL-CAUSAL-EXCURSIONS-1'

    def workspace(self, session_id, raw):
        keys(raw, 'timeframe')
        require(type(raw['timeframe']) is str and raw['timeframe'] in TIMEFRAMES, 'timeframe', 'REFUSED_TIMEFRAME')
        return self.inspect(session_id, raw['timeframe'])

    def _committed_analysis(self, db, state, quote=None):
        def events():
            for offset in range(0,min(state['nextEventIndex'],MAX_ANALYSIS_EVENTS),256):
                page = db.execute('SELECT payload,content_hash FROM btl.tick_events WHERE workspace_id=%s AND session_id=%s AND sequence >= %s ORDER BY sequence LIMIT 256',
                                  (self.scope.workspace_id,state['sessionId'],offset)).fetchall()
                for row in page:
                    yield unpack(*row)
        analysis = project(state, events(), quote)
        self._research_risk(db,state,analysis)
        return analysis

    def bootstrap(self, session_id, raw):
        keys(raw,'seed')
        validate_seed(raw['seed'])
        with connect(self.dsn) as db:
            db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            _, _, state, _ = self._session(db,session_id)
            analysis=self._committed_analysis(db,state)
            require(analysis['status']=='COMPLETE','bootstrap','REFUSED_ANALYSIS_LIMIT')
        result=descriptive_bootstrap(analysis['completed'],raw['seed'])
        result['provenance']=analysis['provenance']
        return result

    def _journal_projection(self, db, state, checkpoint, max_orders=MAX_JOURNAL_ORDERS):
        require(state['nextEventIndex'] <= MAX_ANALYSIS_EVENTS, 'journal', 'REFUSED_ANALYSIS_LIMIT')
        analysis = self._committed_analysis(db,state,self._quote(state,checkpoint))
        self._research_excursions(state,analysis,self.__timeline_cache.window(self.scope,state['sessionId'],checkpoint) if analysis['completed'] else [])
        require(len(analysis['orders']) <= max_orders,'journal','REFUSED_JOURNAL_LIMIT')
        return analysis

    def journal(self, session_id):
        with connect(self.dsn) as db:
            db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            _, _, state, checkpoint = self._session(db,session_id)
            analysis = self._journal_projection(db,state,checkpoint)
            orders = {row['id']:row for row in analysis['orders']}
            saved = db.execute('SELECT payload,content_hash,note_revision,order_id FROM btl.tick_journal_notes WHERE workspace_id=%s AND session_id=%s ORDER BY order_id LIMIT %s',
                               (self.scope.workspace_id,session_id,MAX_JOURNAL_ORDERS+1)).fetchall()
            require(len(saved) <= MAX_JOURNAL_ORDERS,'journal','REFUSED_JOURNAL_LIMIT')
            notes = []
            for blob,sha,note_revision,order_id in saved:
                value = validate_note(unpack(blob,sha),state,orders)
                require((value['orderId'],value['noteRevision']) == (order_id,note_revision),'journal','CORRUPT_RECORD')
                notes.append(value)
            return dict(schemaVersion=1,artifact='BTL-TICK-JOURNAL-1',provenance=analysis['provenance'],orders=analysis['orders'],notes=notes,
                        financialAuthority='COMMITTED_EVENTS_ONLY',notesAuthority='MUTABLE_RESEARCH_ANNOTATION')

    def journal_page(self, session_id, raw):
        keys(raw, 'limit cursor')
        limit = raw['limit']
        require(type(limit) is int and 1 <= limit <= MAX_JOURNAL_PAGE_SIZE,
                'limit', 'INVALID_INPUT')
        cursor = raw['cursor']
        require(cursor is None or type(cursor) is str, 'cursor', 'INVALID_CURSOR')
        requested_revision, after_order_id = (None, None) if cursor is None else decode_cursor(cursor, session_id)
        with connect(self.dsn) as db:
            db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            _meta, _method, state, checkpoint = self._session(db, session_id)
            if requested_revision is not None:
                require(requested_revision == state['revision'], 'cursor', 'STALE_REVISION')
            analysis = self._journal_projection(db, state, checkpoint, MAX_ORDERS)
            orders = sorted(analysis['orders'], key=lambda row: row['id'])
            require(len(orders) <= MAX_JOURNAL_READ_ORDERS, 'journal', 'REFUSED_JOURNAL_LIMIT')
            if after_order_id is not None:
                orders = [row for row in orders if row['id'] > after_order_id]
            page = orders[:limit]
            more = len(orders) > len(page)
            order_ids = [row['id'] for row in page]
            indexed = {row['id']: row for row in page}
            notes = []
            if order_ids:
                saved = db.execute(
                    'SELECT payload,content_hash,note_revision,order_id FROM btl.tick_journal_notes '
                    'WHERE workspace_id=%s AND session_id=%s AND order_id=ANY(%s) ORDER BY order_id LIMIT %s',
                    (self.scope.workspace_id, session_id, order_ids, limit + 1)).fetchall()
                require(len(saved) <= limit, 'journalNotes', 'CORRUPT_RECORD')
                for blob, sha, note_revision, order_id in saved:
                    value = validate_note(unpack(blob, sha), state, indexed)
                    require((value['orderId'], value['noteRevision']) == (order_id, note_revision),
                            'journalNote', 'CORRUPT_RECORD')
                    notes.append(value)
            next_cursor = encode_cursor(session_id, state['revision'], page[-1]['id']) if more and page else None
            return dict(schemaVersion=1, artifact='BTL-TICK-JOURNAL-PAGE-1', sessionId=session_id,
                        revision=state['revision'], totalOrders=len(analysis['orders']), orders=page,
                        notes=notes, nextCursor=next_cursor, complete=next_cursor is None,
                        provenance=analysis['provenance'], financialAuthority='COMMITTED_EVENTS_ONLY',
                        notesAuthority='MUTABLE_RESEARCH_ANNOTATION')

    def save_note(self, session_id, raw):
        journal_request(raw)
        with connect(self.dsn) as db:
            _, _, state, checkpoint = self._session(db,session_id,lock=True)
            analysis = self._journal_projection(db,state,checkpoint)
            orders = {row['id']:row for row in analysis['orders']}
            require(raw['orderId'] in orders,'order','RESOURCE_UNAVAILABLE')
            prior = db.execute('SELECT payload,content_hash,note_revision FROM btl.tick_journal_notes WHERE workspace_id=%s AND session_id=%s AND order_id=%s FOR UPDATE',
                               (self.scope.workspace_id,session_id,raw['orderId'])).fetchone()
            previous = validate_note(unpack(*prior[:2]),state,orders) if prior else None
            require(previous is None or previous['noteRevision'] == prior[2],'journal','CORRUPT_RECORD')
            current = prior[2] if prior else 0
            # A lost response may be retried exactly, but a competing edit cannot overwrite.
            if previous and current == raw['expectedNoteRevision']+1 and previous['text'] == raw['text'] and previous['tags'] == raw['tags']:
                return previous
            require(raw['expectedNoteRevision'] == current,'noteRevision','REFUSED_STALE_NOTE')
            value = dict(schemaVersion=1,artifact='BTL-TICK-JOURNAL-NOTE-1',sessionId=session_id,
                         datasetId=state['datasetId'],datasetVersion=state['datasetVersion'],orderId=raw['orderId'],
                         noteRevision=current+1,text=raw['text'],tags=raw['tags'])
            validate_note(value,state,orders)
            blob,sha = pack(value)
            db.execute('INSERT INTO btl.tick_journal_notes VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (workspace_id,session_id,order_id) DO UPDATE SET note_revision=EXCLUDED.note_revision,payload=EXCLUDED.payload,content_hash=EXCLUDED.content_hash',
                       (self.scope.workspace_id,session_id,raw['orderId'],value['noteRevision'],blob,sha))
            return value

    def review(self, raw):
        keys(raw,"sessionId requestId expectedRevision planId planRevision draft")
        identifier(raw["requestId"],"requestId"); identifier(raw["sessionId"],"sessionId"); revision(raw["expectedRevision"])
        request_hash = content_hash(dict(schemaVersion=1,artifact="BTL-LOCAL-REVIEW-REQUEST-1",**raw))
        with connect(self.dsn) as db:
            meta, method, state, checkpoint = self._session(db,raw["sessionId"],lock=True)
            prior = db.execute("SELECT payload,content_hash FROM btl.tick_order_reviews WHERE workspace_id=%s AND session_id=%s AND review_id=%s",
                               (self.scope.workspace_id,raw["sessionId"],raw["requestId"])).fetchone()
            if prior:
                reviewed = unpack(*prior)
                require(reviewed["requestHash"] == request_hash,"requestId","REFUSED_IDEMPOTENCY_CONFLICT")
                return dict(review=reviewed,reviewHash=prior[1])
            require(raw["expectedRevision"] == state["revision"],"revision","REFUSED_STALE_REVISION")
            require(not state["ended"] and not state["unresolved"],"session","REFUSED_UNRESOLVED_SESSION")
            draft = deepcopy(raw["draft"])
            keys(draft,"side orderType workflow entry quantity sl tp riskPercent observations")
            require(type(draft["observations"]) is list and len(draft["observations"]) <= 64,"observations")
            for observation in draft["observations"]:
                keys(observation,"conditionId outcome"); Observation(observation["conditionId"],observation["outcome"])
            require(len({o["conditionId"] for o in draft["observations"]}) == len(draft["observations"]),"duplicateObservations")
            policy = method_policy(method)
            quote = self._quote(state,checkpoint)
            require(quote is not None,"quote","UNRESOLVED_NO_QUOTE")
            side = quote["ask"] if draft["side"] == "LONG" else quote["bid"]
            if draft["orderType"] == "MARKET":
                draft["entry"] = side
            if policy.kind == "PROTOCOL":
                entry, stop = price(draft["entry"],state["profile"]), price(draft["sl"],state["profile"])
                tp = text(entry+(entry-stop)*Fraction(policy.rr))
                require(draft["tp"] is None or exact(draft["tp"],"tp") == Fraction(tp),"tp","PROTOCOL_BLOCKED")
                require(draft["riskPercent"] is None or exact(draft["riskPercent"],"riskPercent") == Fraction(policy.risk_percent),"risk","PROTOCOL_BLOCKED")
                draft.update(tp=tp,riskPercent=text(Fraction(policy.risk_percent)))
                supplied = {o["conditionId"]:o["outcome"] for o in draft["observations"]}
                require(set(supplied).issubset(policy.conditions),"conditions")
                # Explicit NOT_ASSESSED for missing conditions; never fabricate PASS.
                draft["observations"] = [dict(conditionId=c,outcome=supplied.get(c,"NOT_ASSESSED")) for c in policy.conditions]
            if draft["quantity"] is None:
                draft["quantity"] = risk_quantity(text(Fraction(state["balance"])*exact(draft["riskPercent"],"risk",True)/100),draft["entry"],draft["sl"],state["profile"])
            payload = open_payload(draft,state["profile"],policy,state["balance"])
            command = dict(schemaVersion=1,artifact="BTL-TICK-EXECUTION-COMMAND-1",sessionId=raw["sessionId"],commandId=raw["requestId"],
                           expectedRevision=raw["expectedRevision"],kind="OPEN",payload=payload)
            context = SessionContext(self.scope.workspace_id,raw["sessionId"],policy,"XAUUSD",state["profile"]["feedId"],state["profileHash"],
                                     state["revision"],state["revision"],datetime.fromtimestamp(int(state["throughNs"])//1000000000,timezone.utc),Decimal(side))
            request = Command(self.scope.workspace_id,raw["sessionId"],raw["requestId"],policy.method_id,policy.definition_hash,"XAUUSD",context.feed_id,
                              context.profile_hash,state["revision"],state["revision"],payload["workflow"],"BUY" if payload["side"]=="LONG" else "SELL",
                              payload["orderType"],payload["entry"],payload["quantity"],payload["riskPercent"],payload["sl"],payload["tp"],
                              raw["planId"],raw["planRevision"],tuple(Observation(o["conditionId"],o["outcome"]) for o in payload["observations"]))
            validate_command(request,context)
            reviewed = dict(schemaVersion=1,artifact="BTL-LOCAL-ORDER-REVIEW-1",requestHash=request_hash,command=command,
                            contractRequest=json.loads(canonical_bytes(request.identity_payload())),methodHash=meta["methodHash"],profileHash=state["profileHash"],
                            throughNs=state["throughNs"],riskBasis=state["balance"],model="SIMULATED_QUOTE_BASELINE_NOT_BROKER_EXECUTION")
            reviewed['researchRisk'] = planned_risk(state,command)
            blob, sha = pack(reviewed)
            count = db.execute("SELECT count(*) FROM btl.tick_order_reviews WHERE workspace_id=%s AND session_id=%s",(self.scope.workspace_id,raw["sessionId"])).fetchone()[0]
            require(count < 256,"reviews","REFUSED_REVIEW_LIMIT")
            db.execute("INSERT INTO btl.tick_order_reviews VALUES (%s,%s,%s,%s,%s)",(self.scope.workspace_id,raw["sessionId"],raw["requestId"],blob,sha))
        return dict(review=reviewed,reviewHash=sha)

    def confirm(self, session_id, raw):
        keys(raw,"reviewId reviewHash"); identifier(raw["reviewId"],"reviewId"); digest(raw["reviewHash"],"reviewHash")
        with connect(self.dsn) as db:
            self._session(db,session_id)
            row = db.execute("SELECT payload,content_hash FROM btl.tick_order_reviews WHERE workspace_id=%s AND session_id=%s AND review_id=%s",
                             (self.scope.workspace_id,session_id,raw["reviewId"])).fetchone()
            require(row is not None,"review","RESOURCE_UNAVAILABLE")
            require(row[1] == raw["reviewHash"],"reviewHash","REFUSED_IDEMPOTENCY_CONFLICT")
            reviewed = unpack(*row)
            require(reviewed["command"]["sessionId"] == session_id and reviewed["command"]["commandId"] == raw["reviewId"],"review","CORRUPT_RECORD")
        return self.controller.apply(self.scope,reviewed["command"])

    def apply(self, session_id, command):
        require(command.get("sessionId") == session_id and command.get("kind") in ("ADVANCE","SEEK","CANCEL","CLOSE"),"command","REFUSED_UNREVIEWED_COMMAND")
        with connect(self.dsn) as db:
            self._session(db,session_id)
        return self.controller.apply(self.scope,command)
