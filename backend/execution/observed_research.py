"""Authenticated-application composition for the separate observed engine.

Sources are selected only from a trusted, hash-pinned operator catalog. This
class exposes no source paths, qualification proofs or provider handles to a
request. It shares immutable Method definitions but writes an explicitly new
Session artifact and delegates financial truth to the observed controller.
"""
from collections import OrderedDict
from copy import deepcopy
from threading import RLock
from datetime import datetime,timezone
from decimal import Decimal
from fractions import Fraction
import json

from application.models import TrustedScope
from contracts.canonical import canonical_bytes,content_hash
from contracts.models import Command,SessionContext,Observation,validate_command
from contracts.primitives import require,identifier,revision
from ticks.contracts import keys,tag,uint
from infrastructure.database import connect
from .analysis import RESEARCH_VERSION,planned_risk
from .contracts import exact,open_payload,policy_wire,text,risk_quantity
from .journal import validate_note,request as journal_request,MAX_JOURNAL_ORDERS
from .journal_projection import journal_order_summary
from .observed_catalog import ObservedCatalog
from .observed_controller import ObservedExecutionController
from .observed_kernel import command_wire, seed_state, PRODUCT_ORDER_RETENTION_V1
from .observed_session_dispatch import dispatch_observed_session
from .observed_postgres import ObservedExecutionStore, PROGRESS_FORMAT
from .observed_profile import ENGINE_VERSION,MODEL,ObservedExecutionProfile
from .observed_analysis import ObservedStatistics
from .analytics_projection import (initial_projection,analytics_view,completed_trade_row,
    encode_trade_cursor,decode_trade_cursor,ARTIFACT as ANALYTICS_PROJECTION_ARTIFACT)
from .postgres import pack,unpack
from .research import method_policy,label
from .bootstrap import bootstrap as descriptive_bootstrap,validate_seed

META='BTL-OBSERVED-RESEARCH-SESSION-1'
VIEW='BTL-OBSERVED-RESEARCH-VIEW-1'
_STATS_LOCK=RLock()
_STATS_BY_DSN=OrderedDict()
REVIEW='BTL-OBSERVED-ORDER-REVIEW-1'
PROGRESS_REVIEW='BTL-OBSERVED-ORDER-REVIEW-PROGRESS-1'
REPLAY_TO_CHUNKS=8


def _stored_observed_state(db,workspace_id,session_id):
    row=db.execute('SELECT payload,content_hash FROM btl.tick_sessions '
                   'WHERE workspace_id=%s AND session_id=%s',(workspace_id,session_id)).fetchone()
    require(row is not None,'state','CORRUPT_RECORD')
    stored=unpack(*row);state=stored.get('state')
    if state is None:
        base=db.execute('SELECT payload,content_hash FROM btl.tick_checkpoints '
                        'WHERE workspace_id=%s AND session_id=%s AND revision=0',
                        (workspace_id,session_id)).fetchone()
        require(base is not None,'genesis','CORRUPT_RECORD')
        state=unpack(*base).get('state')
    require(type(state) is dict and type(state.get('artifact')) is str,
            'sessionFormat','CORRUPT_RECORD')
    return state


class ObservedResearchApplication:
    """One workspace-scoped Method/Session adapter for the observed family."""
    def __init__(self,dsn,scope,catalog,*,state_storage_format='snapshot-v1',
                 product_order_archive_v1=False):
        require(type(scope) is TrustedScope,'scope','SCOPE_REQUIRED');require(type(catalog) is ObservedCatalog,'catalog')
        require(state_storage_format in ('snapshot-v1','compact-v1',PROGRESS_FORMAT),'stateStorageFormat','REFUSED_STATE_VERSION')
        require(type(product_order_archive_v1) is bool,'productOrderArchive')
        if product_order_archive_v1:
            require(state_storage_format in ('compact-v1',PROGRESS_FORMAT),
                    'productOrderArchive','REFUSED_STATE_VERSION')
        retention=PRODUCT_ORDER_RETENTION_V1 if product_order_archive_v1 else None
        self.dsn=dsn;self.scope=scope;self.catalog=catalog
        self.store=ObservedExecutionStore(dsn,order_retention_policy=retention,
            state_storage_format=state_storage_format,product_order_archive_v1=product_order_archive_v1)
        self.controller=ObservedExecutionController(self.store,catalog.resolve,order_retention_policy=retention)
        key=content_hash(dict(schemaVersion=1,artifact='BTL-OBSERVED-STATS-SERVICE-KEY-1',
                              dsnHash=content_hash({'schemaVersion':1,'dsn':dsn}),stateStorageFormat=state_storage_format,
                              productOrderArchiveV1=product_order_archive_v1))
        with _STATS_LOCK:
            self.statistics=_STATS_BY_DSN.get(key)
            if self.statistics is None:self.statistics=ObservedStatistics(self.store);_STATS_BY_DSN[key]=self.statistics
            _STATS_BY_DSN.move_to_end(key)
            while len(_STATS_BY_DSN)>4:_STATS_BY_DSN.popitem(last=False)

    def close(self):pass  # The operator catalog owns handles across admitted requests.

    def close_services(self):
        self.catalog.close()

    @staticmethod
    def _same_projection(projection,state):
        provenance=projection.get('provenance') or {}
        return projection.get('revision',provenance.get('revision'))==state['revision'] and provenance.get('eventHead',state['eventHash'])==state['eventHash']

    def _complete_statistics(self,session_id,state):
        projection=self.statistics.inspect(self.scope,session_id,0,64)
        if projection['status']!='COMPLETE':return projection
        require(self._same_projection(projection,state),'analysisSnapshot','REFUSED_STALE_REVISION')
        rows=list(projection['completed'])
        details=dict(projection.get('orderDetails',{}))
        while projection['nextTradeOffset'] is not None:
            next_page=self.statistics.inspect(self.scope,session_id,projection['nextTradeOffset'],64)
            require(self._same_projection(next_page,state) and next_page['status']=='COMPLETE','analysisSnapshot','REFUSED_STALE_REVISION')
            details.update(next_page.get('orderDetails',{}))
            rows.extend(next_page['completed']);projection=next_page
        require(self._same_projection(projection,state),'analysisSnapshot','REFUSED_STALE_REVISION')
        projection['completed']=rows;projection['nextTradeOffset']=None
        if 'orderDetails' in projection:projection['orderDetails']=details
        return projection

    def _catalog_lock(self,db):db.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',(self.scope.workspace_id,))

    def _method(self,db,method_id):
        identifier(method_id,'methodId');row=db.execute('SELECT payload,content_hash FROM btl.tick_methods WHERE workspace_id=%s AND method_id=%s',(self.scope.workspace_id,method_id)).fetchone()
        require(row is not None,'method','RESOURCE_UNAVAILABLE');value=unpack(*row);method_policy(value);require(value['id']==method_id,'method','CORRUPT_RECORD');return value

    def create_method(self,raw):
        from .research import ResearchApplication
        shell=object.__new__(ResearchApplication);shell.dsn=self.dsn;shell.scope=self.scope
        shell._catalog_lock=self._catalog_lock;shell._method=self._method
        return ResearchApplication.create_method(shell,raw)

    def catalog_view(self):
        with connect(self.dsn) as db:
            db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            methods=[unpack(*row) for row in db.execute('SELECT payload,content_hash FROM btl.tick_methods WHERE workspace_id=%s ORDER BY method_id LIMIT 129',(self.scope.workspace_id,)).fetchall()]
            require(len(methods)<=128,'catalog','REFUSED_CATALOG_LIMIT')
            for method in methods:method_policy(method)
            rows=db.execute('SELECT payload,content_hash,method_id FROM btl.tick_research_sessions WHERE workspace_id=%s ORDER BY session_id LIMIT 129',(self.scope.workspace_id,)).fetchall()
            require(len(rows)<=128,'catalog','REFUSED_CATALOG_LIMIT');sessions=[]
            for raw,sha,method_id in rows:
                meta=unpack(raw,sha)
                if meta.get('artifact')==META:
                    stored_state=_stored_observed_state(db,self.scope.workspace_id,meta['id'])
                    selected_format=dispatch_observed_session(stored_state)
                    if selected_format.family=='observed-product':
                        session_store=ObservedExecutionStore(self.dsn,
                            order_retention_policy=PRODUCT_ORDER_RETENTION_V1,
                            product_order_archive_v1=selected_format.archive_codec=='p0-v1',
                            terminal_order_archive_v1=selected_format.archive_codec=='integration-v1',
                            state_storage_format='compact-v1')
                    else:
                        session_store=ObservedExecutionStore(self.dsn,state_storage_format='snapshot-v1')
                    self._session(db,meta['id'],store=session_store);sessions.append(meta)
                elif meta.get('artifact')=='BTL-LOCAL-SESSION-1':
                    tag(meta,'BTL-LOCAL-SESSION-1','id name methodId methodHash datasetId datasetVersion profileHash startPeriod initialBalance')
                    require(meta['methodId']==method_id,'session','CORRUPT_RECORD');self._method(db,method_id);sessions.append(meta)
            return dict(schemaVersion=1,artifact='BTL-OBSERVED-RESEARCH-CATALOG-1',methods=methods,sessions=sessions,datasets=self.catalog.public(),model=MODEL)

    def _session(self,db,session_id,*,lock=False,include_format=False,store=None):
        identifier(session_id,'sessionId')
        row=db.execute('SELECT payload,content_hash,method_id FROM btl.tick_research_sessions WHERE workspace_id=%s AND session_id=%s',(self.scope.workspace_id,session_id)).fetchone()
        require(row is not None,'session','RESOURCE_UNAVAILABLE');meta=unpack(*row[:2])
        tag(meta,META,'id name methodId methodHash datasetKey period day datasetId datasetVersion profileHash startNs initialBalance model engineVersion creationRequestHash')
        require(meta['id']==session_id and meta['methodId']==row[2] and meta['model']==MODEL and meta['engineVersion']==ENGINE_VERSION,'session','CORRUPT_RECORD')
        method=self._method(db,meta['methodId']);policy=method_policy(method);scoped_row=db.execute('SELECT payload,content_hash,revision,dataset_version,profile_hash FROM btl.tick_sessions WHERE workspace_id=%s AND session_id=%s'+(' FOR UPDATE' if lock else ''),(self.scope.workspace_id,session_id)).fetchone()
        require(scoped_row is not None,'state','CORRUPT_RECORD')
        selected_store=store or self.store
        saved, storage_format, _ = selected_store._read(db,self.scope.workspace_id,session_id,lock=lock,include_format=True)
        state,cp=saved['state'],saved['controller']
        persisted_format=dispatch_observed_session(state)
        if persisted_format.archive_codec!='none':
            # This checks that the selected runtime is capable of reaching the
            # artifact's immutable table without rewriting or migrating it.
            selected_store._archive_table(state)
        same_revision = state['revision'] >= scoped_row[2] if storage_format==PROGRESS_FORMAT else state['revision']==scoped_row[2]
        require(state['sessionId']==session_id and state['policy']==policy_wire(policy) and same_revision and (state['datasetVersion'],state['profileHash'])==tuple(scoped_row[3:]),'state','CORRUPT_RECORD')
        require((meta['methodHash'],meta['datasetId'],meta['datasetVersion'],meta['profileHash'],meta['startNs'],meta['initialBalance'])==(policy.definition_hash,state['datasetId'],state['datasetVersion'],state['profileHash'],state['startNs'],state['initialBalance']),'sessionPins','CORRUPT_RECORD')
        # The storage adapter verifies the full snapshot or compact hash-chain
        # tip against the immutable checkpoint for both new and legacy Sessions.
        return (meta,method,state,cp,storage_format) if include_format else (meta,method,state,cp)

    def create_session(self,raw):
        keys(raw,'id name methodId initialBalance sourceKey period day')
        identifier(raw['id'],'sessionId');name=label(raw['name']);profile=self.catalog.selection(raw['sourceKey'],raw['period'])
        require(raw['day'] is None or (type(raw['day']) is str and len(raw['day'])==10 and raw['day'][:7]==raw['period']),'day')
        initial=text(exact(raw['initialBalance'],'initialBalance',True));require(Fraction(initial)>0,'initialBalance')
        request_hash=content_hash(dict(schemaVersion=1,artifact='BTL-OBSERVED-SESSION-CREATE-REQUEST-1',id=raw['id'],name=name,methodId=raw['methodId'],initialBalance=initial,sourceKey=raw['sourceKey'],period=raw['period'],day=raw['day'],profileHash=profile.profile_hash))
        # An exact retry returns before source admission or timeline construction.
        existing=self._existing(raw['id'],request_hash)
        if existing is not None:return self.inspect(raw['id'])
        source=self.catalog.resolve(profile.profile_hash);timeline=None
        try:
            with connect(self.dsn) as db:
                self._catalog_lock(db)
                previous=db.execute('SELECT payload,content_hash FROM btl.tick_research_sessions WHERE workspace_id=%s AND session_id=%s',(self.scope.workspace_id,raw['id'])).fetchone()
                if previous:
                    old=unpack(*previous);require(old.get('artifact')==META and old.get('creationRequestHash')==request_hash,'sessionId','REFUSED_IDEMPOTENCY_CONFLICT')
                    self._session(db,raw['id'])
                    return self.inspect(raw['id'])
                from .product_method_lifecycle import require_active_method
                require_active_method(db,self.scope.workspace_id,raw['methodId'])
                method=self._method(db,raw['methodId']);policy=method_policy(method)
                start=source.start_for_period(raw['period'],day=raw['day']);timeline=source.cache.new_timeline(self.scope,raw['id'],start);cp=timeline.checkpoint()
                state=seed_state(raw['id'],profile,policy,cp,initial,
                    order_retention_policy=self.store.order_retention_policy,
                    product_order_archive_v1=self.store.product_order_archive_v1)
                meta=dict(schemaVersion=1,artifact=META,id=raw['id'],name=name,methodId=raw['methodId'],methodHash=policy.definition_hash,datasetKey=raw['sourceKey'],period=raw['period'],day=raw['day'],datasetId=state['datasetId'],datasetVersion=state['datasetVersion'],profileHash=state['profileHash'],startNs=state['startNs'],initialBalance=state['initialBalance'],model=MODEL,engineVersion=ENGINE_VERSION,creationRequestHash=request_hash)
                blob,sha=pack(meta);self.store._insert(db,self.scope,state,cp)
                # New Sessions start with an explicit empty keyset projection.
                # Older Sessions without this marker retain their compatibility path.
                db.execute('INSERT INTO btl.tick_journal_projection_heads '
                    '(workspace_id,session_id,format_version,through_sequence,event_hash,order_count,analytics_format_version) '
                    'VALUES (%s,%s,1,0,%s,0,1)',
                    (self.scope.workspace_id,raw['id'],state['eventHash']))
                analytics_blob,analytics_hash=pack(initial_projection(state))
                db.execute('INSERT INTO btl.tick_session_metric_projections '
                    '(workspace_id,session_id,payload,content_hash) VALUES (%s,%s,%s,%s)',
                    (self.scope.workspace_id,raw['id'],analytics_blob,analytics_hash))
                db.execute('INSERT INTO btl.tick_research_sessions VALUES (%s,%s,%s,%s,%s)',(self.scope.workspace_id,raw['id'],raw['methodId'],blob,sha))
            source.cache.seed(self.scope,raw['id'],timeline);timeline=None
            return self.inspect(raw['id'])
        finally:
            if timeline is not None:source.cache.discard(timeline)

    def _existing(self,session_id,request_hash):
        with connect(self.dsn) as db:
            db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            row=db.execute('SELECT payload,content_hash FROM btl.tick_research_sessions WHERE workspace_id=%s AND session_id=%s',(self.scope.workspace_id,session_id)).fetchone()
            if row is None:return None
            meta=unpack(*row);require(meta.get('artifact')==META and meta.get('creationRequestHash')==request_hash,'sessionId','REFUSED_IDEMPOTENCY_CONFLICT')
            self._session(db,session_id);return meta

    def summary(self,session_id):
        with connect(self.dsn) as db:
            db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY');meta,method,state,cp=self._session(db,session_id)
            return dict(schemaVersion=1,artifact='BTL-OBSERVED-SESSION-SUMMARY-1',sessionId=meta['id'],revision=state['revision'],throughNs=state['throughNs'],datasetId=state['datasetId'],datasetVersion=state['datasetVersion'],profileHash=state['profileHash'],accountCurrency='USD',initialBalance=state['initialBalance'],balance=state['balance'],netCashChange=text(Fraction(state['balance'])-Fraction(state['initialBalance'])),completedTrades=sum(o['status']=='CLOSED' for o in state['orders'].values()),unresolved=state['unresolved'],ended=state['ended'],model=MODEL)

    def inspect(self,session_id,timeframe='1m',*,trade_offset=0):
        # Workspace/chart is a controller operation; only prior observed groups
        # at this accepted checkpoint are projected. No candle settles a trade.
        from .workspace import display_candles,TIMEFRAMES
        require(type(timeframe) is str and timeframe in TIMEFRAMES,'timeframe','REFUSED_TIMEFRAME')
        with connect(self.dsn) as db:
            db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY');meta,method,state,cp=self._session(db,session_id)
            rows=db.execute('SELECT payload,content_hash FROM btl.tick_events WHERE workspace_id=%s AND session_id=%s ORDER BY sequence DESC LIMIT 64',(self.scope.workspace_id,session_id)).fetchall();events=[unpack(*row) for row in reversed(rows)]
            view=dict(schemaVersion=1,artifact=VIEW,metadata=meta,method=method,state=state,events=events,eventWindowStart=max(0,state['nextEventIndex']-64),quote=deepcopy(state['quoteBasis']),label=f"{self.catalog.selection(meta['datasetKey'],meta['period']).wire['primary']['providerId']} · {MODEL}",replayStepNs='1000000000')
            # This is the user's previously requested target, not source availability.
            view['pendingReplayTargetNs']=cp['cursor']['pendingTargetNs']
            # The display helper sees only groups already clipped to this cursor.
            source=self.catalog.resolve(state['profileHash']);groups=source.cache.window(self.scope,session_id,cp)
            start=max(0,int(state['nextGroupIndex'])-len(groups));view['chart']=display_candles(groups,state['throughNs'],timeframe,start)
        projection=self._complete_statistics(session_id,state)
        require(self._same_projection(projection,state),'analysisSnapshot','REFUSED_STALE_REVISION')
        view['analysis']=self._view_analysis(state,projection)
        return view

    @staticmethod
    def _view_analysis(state,projection):
        base=dict(account=dict(currency='USD',initialBalance=state['initialBalance'],balance=state['balance'],netCashChange=text(Fraction(state['balance'])-Fraction(state['initialBalance'])),realizedGross=state['realizedGross'],commission='0',unrealizedIndicative=None,equityIndicative=None),
                  orders=[],completed=[],equity=[],model=MODEL)
        if projection['status']!='COMPLETE':
            return dict(status='BUILDING',reason='LEDGER_PROJECTION_BUILDING',progress=dict(processedEvents=projection['processedEvents'],totalEvents=projection['totalEvents']),**base)
        metrics=deepcopy(projection['metrics']);metrics['equityWindowStart']=projection['curveWindowStart'];rows=deepcopy(projection['completed'])
        orders=[]
        for oid,o in sorted(state['orders'].items()):
            row=next((item for item in rows if item['id']==oid),None)
            orders.append(dict(id=oid,side=o['side'],status=o['status'],quantity=o['quantity'],remaining=o['remaining'],entry=o['entry'],entryPrice=o['entryPrice'],entryTimeNs=None if row is None else row['entryTimeNs'],entryFillRef=None if row is None else row['entryFillRef'],sl=o['sl'],tp=o['tp'],exitRequested=o['exitRequest'] is not None,exitPrice=None if row is None else row['exitPrice'],exitFillRef=None if row is None else row['exitFillRef'],exitReason=None if row is None else row['exitReason'],gross=o['grossPosted'],commission='0',net=o['grossPosted'],netCashChange=o['grossPosted'],unrealizedIndicative=None,mae=None,mfe=None,excursionReason='OBSERVED_EXCURSIONS_NOT_COMPUTED'))
        completed=[]
        order_details=projection.get('orderDetails',state['orders'])
        for r in rows:
            detail=order_details.get(r['id'])
            require(detail is not None,'analysisOrder','CORRUPT_RECORD')
            completed.append(dict(id=r['id'],side=r['side'],status='CLOSED',quantity=r['quantity'],remaining='0',entry=r['entryPrice'],entryPrice=r['entryPrice'],entryTimeNs=r['entryTimeNs'],exitTimeNs=r['exitTimeNs'],entryFillRef=r['entryFillRef'],sl=detail['sl'],tp=detail['tp'],exitPrice=r['exitPrice'],exitFillRef=r['exitFillRef'],exitReason=r['exitReason'],gross=r['grossExact'],commission='0',net=r['netPosted'],durationNs=r['durationNs'],mae=None,mfe=None,excursionReason='OBSERVED_EXCURSIONS_NOT_COMPUTED',rMultiple=r['rMultiple'],rReason=r['rReason']))
        provenance=deepcopy(projection['provenance']);provenance['analysisVersion']=RESEARCH_VERSION
        base.update(status='COMPLETE',provenance=provenance,metrics=metrics,orders=orders,completed=completed,equity=deepcopy(projection['balanceCurve']),annotations=deepcopy(projection['annotations']),annotationWindowStart=projection['annotationWindowStart'],analysisProjection=projection)
        return base

    def bootstrap(self,session_id,raw):
        keys(raw,'seed');validate_seed(raw['seed'])
        with connect(self.dsn) as db:
            db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY');meta,method,state,cp=self._session(db,session_id)
        projection=self._complete_statistics(session_id,state)
        require(projection['status']=='COMPLETE','bootstrap','REFUSED_ANALYSIS_BUILDING')
        require(self._same_projection(projection,state),'bootstrap','REFUSED_STALE_REVISION')
        result=descriptive_bootstrap([dict(row,net=row['netPosted']) for row in projection['completed']],raw['seed'])
        result['provenance']=dict(sessionId=state['sessionId'],revision=state['revision'],datasetId=state['datasetId'],datasetVersion=state['datasetVersion'],profileHash=state['profileHash'],engineVersion=state['engineVersion'],methodHash=state['policy']['definitionHash'],eventHead=state['eventHash'],researchVersion=RESEARCH_VERSION)
        return result

    def apply(self,session_id,raw):
        require(raw.get('sessionId')==session_id and raw.get('kind') in ('ADVANCE','CANCEL','CLOSE','END'),'command','REFUSED_COMMAND')
        with connect(self.dsn) as db:self._session(db,session_id)
        return self.controller.apply(self.scope,raw)

    def replay_to(self,session_id,raw):
        """Advance to a UTC target in bounded, individually durable 64-group commands."""
        keys(raw,'schemaVersion artifact requestId sessionId expectedRevision targetNs timeframe')
        require(type(raw['schemaVersion']) is int and raw['schemaVersion']==1
                and raw['artifact']=='BTL-OBSERVED-REPLAY-TO-1' and raw['sessionId']==session_id,'replayTo')
        require(type(raw['requestId']) is str and len(raw['requestId'])==32
                and all(c in '0123456789abcdef' for c in raw['requestId']),'requestId')
        revision(raw['expectedRevision']);target=uint(raw['targetNs'],'targetNs')
        from .workspace import TIMEFRAMES
        require(type(raw['timeframe']) is str and raw['timeframe'] in TIMEFRAMES,'timeframe','REFUSED_TIMEFRAME')
        prefix=f"command:replay-to:{raw['requestId']}:r"
        def advance_command(expected_revision):
            return dict(schemaVersion=1,artifact='BTL-OBSERVED-EXECUTION-COMMAND-1',sessionId=session_id,
                        commandId=f"{prefix}{expected_revision}",expectedRevision=expected_revision,
                        kind='ADVANCE',payload={'targetNs':str(target)})

        with connect(self.dsn) as db:
            db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            meta,method,state,checkpoint=self._session(db,session_id)
            prior_revision=db.execute('SELECT max(revision) FROM btl.tick_commands WHERE workspace_id=%s AND session_id=%s AND command_id LIKE %s',(self.scope.workspace_id,session_id,prefix+'%')).fetchone()[0]
            if prior_revision is not None:
                initial=advance_command(raw['expectedRevision'])
                original=db.execute('SELECT revision,command_hash FROM btl.tick_commands '
                    'WHERE workspace_id=%s AND session_id=%s AND command_id=%s',
                    (self.scope.workspace_id,session_id,initial['commandId'])).fetchone()
                require(original is not None and original[0]==raw['expectedRevision']+1 and
                        original[1]==content_hash(initial),'requestId','REFUSED_IDEMPOTENCY_CONFLICT')
        if prior_revision is None:
            require(state['revision']==raw['expectedRevision'],'revision','REFUSED_STALE_REVISION')
        else:
            require(state['revision']==prior_revision,'revision','REFUSED_STALE_REVISION')
        require(target>=int(state['throughNs']),'advance','REFUSED_BACKWARD_ADVANCE')
        advances=0
        while advances<REPLAY_TO_CHUNKS and int(state['throughNs'])<target:
            previous_index=int(state['nextGroupIndex']);previous_through=int(state['throughNs'])
            command=advance_command(state['revision'])
            saved=self.controller.apply(self.scope,command);state=saved['state'];advances+=1
            if int(state['nextGroupIndex'])==previous_index and int(state['throughNs'])==previous_through:break
        view=self.inspect(session_id,raw['timeframe'])
        require(view['state']['revision']==state['revision'] and view['state']['throughNs']==state['throughNs'],'replayTo','REFUSED_STALE_REVISION')
        return dict(schemaVersion=1,artifact='BTL-OBSERVED-REPLAY-TO-RESULT-1',requestId=raw['requestId'],
                    sessionId=session_id,targetNs=str(target),throughNs=state['throughNs'],advances=advances,
                    targetReached=int(state['throughNs'])>=target,view=view)

    def workspace(self,session_id,raw):
        keys(raw,'timeframe')
        return self.inspect(session_id,raw['timeframe'])

    def chart_history(self,session_id,raw):
        from datetime import datetime,timezone
        from market_data.context_warmup import FrameWarmup,MAX_BARS
        from .workspace import TIMEFRAMES
        keys(raw,'timeframe offset');timeframe=raw['timeframe'];offset=raw['offset']
        require(type(timeframe) is str and timeframe in TIMEFRAMES,'timeframe','REFUSED_TIMEFRAME')
        require(type(offset) is int and 0<=offset<=50000,'offset','INVALID_INPUT')
        archive,source_info=self.catalog.reference_context()
        with connect(self.dsn) as db:
            db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY');meta,method,state,cp=self._session(db,session_id)
        start=int(state['startNs']);stamp=datetime.fromtimestamp(start//10**9,timezone.utc)
        prior_year,prior_month=(stamp.year-1,12) if stamp.month==1 else (stamp.year,stamp.month-1)
        month=f'{prior_year:04d}-{prior_month:02d}';end=datetime(stamp.year,stamp.month,1,tzinfo=timezone.utc)
        begin=datetime(prior_year,prior_month,1,tzinfo=timezone.utc);start_s=int(begin.timestamp());end_s=int(end.timestamp())
        duration=TIMEFRAMES[timeframe]
        suffix={60:'1m',180:'3m',300:'5m',900:'15m',1800:'30m',3600:'1h',7200:'2h',14400:'4h',86400:'D'}[duration]
        pin=self.catalog.reference_pin(f'{month}-{suffix}.json') if archive is not None else None
        reference=None if source_info is None or pin is None else {**source_info,'fileName':pin['name'],'fileSha256':pin['sha256']}
        result=dict(schemaVersion=1,artifact='BTL-OBSERVED-REFERENCE-OHLC-1',datasetId=state['datasetId'],datasetVersion=state['datasetVersion'],
                    reference=reference,timeframe=timeframe,period=month,startTime=start_s,endTime=end_s,trustedStartNs=str(start),
                    priceBasis='HISTDATA_BID_REFERENCE_ONLY',volumeAvailable=False,coverage='UNKNOWN',executionAuthority=False,
                    status='UNAVAILABLE' if archive is None else 'WARMUP_INCOMPLETE',candles=[],nextOffset=None)
        if archive is None:return result
        required=MAX_BARS
        selection=archive.select(FrameWarmup(duration,required,1e-6),trusted_start_ns=start,month=month)
        candles=[]
        for bar in selection.candles:
            t=bar.open_ns//10**9
            if t>=start_s and bar.close_ns<=start and t+duration<=end_s:
                candles.append(dict(time=t,open=bar.open,high=bar.high,low=bar.low,close=bar.close))
        # One calendar month is the reference window. Gaps/rights remain unknown.
        page=candles[offset:offset+512]
        result.update(status='READY' if candles else 'WARMUP_INCOMPLETE',candles=page,
                      nextOffset=offset+len(page) if offset+len(page)<len(candles) else None)
        return result

    def journal(self,session_id):
        # Reuse the immutable committed analysis projection. Notes are held
        # separately and cannot affect financial results.
        from .journal import MAX_JOURNAL_ORDERS
        with connect(self.dsn) as db:
            db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            state=self._session(db,session_id)[2]
            indexed=db.execute('SELECT format_version FROM btl.tick_journal_projection_heads '
                'WHERE workspace_id=%s AND session_id=%s',(self.scope.workspace_id,session_id)).fetchone()
        if indexed is not None and indexed[0]==1:
            page=self.journal_page(session_id,dict(limit=MAX_JOURNAL_ORDERS,cursor=None))
            require(page['totalOrders']<=MAX_JOURNAL_ORDERS,'journal','REFUSED_JOURNAL_LIMIT')
            return dict(schemaVersion=1,artifact='BTL-TICK-JOURNAL-1',
                provenance=page['provenance'],orders=page['orders'],notes=page['notes'],
                financialAuthority='COMMITTED_EVENTS_ONLY',
                notesAuthority='MUTABLE_RESEARCH_ANNOTATION')
        projection=self._complete_statistics(session_id,state)
        require(self._same_projection(projection,state),'journal','REFUSED_STALE_REVISION')
        analysis=self._view_analysis(state,projection)
        require(analysis['status']=='COMPLETE','journal','REFUSED_ANALYSIS_BUILDING')
        orders=analysis['orders']
        require(len(orders)<=MAX_JOURNAL_ORDERS,'journal','REFUSED_JOURNAL_LIMIT')
        notes=[]
        with connect(self.dsn) as db:
            db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            live=self._session(db,session_id)[2]
            require(live['revision']==state['revision'] and live['eventHash']==state['eventHash'],'journal','REFUSED_STALE_REVISION')
            saved=db.execute('SELECT payload,content_hash,note_revision,order_id FROM btl.tick_journal_notes WHERE workspace_id=%s AND session_id=%s ORDER BY order_id LIMIT %s',(self.scope.workspace_id,session_id,MAX_JOURNAL_ORDERS+1)).fetchall()
            require(len(saved)<=MAX_JOURNAL_ORDERS,'journal','REFUSED_JOURNAL_LIMIT')
            indexed={order['id']:order for order in orders}
            for blob,sha,note_revision,order_id in saved:
                value=validate_note(unpack(blob,sha),state,indexed)
                require((value['orderId'],value['noteRevision'])==(order_id,note_revision),'journal','CORRUPT_RECORD');notes.append(value)
        return dict(schemaVersion=1,artifact='BTL-TICK-JOURNAL-1',provenance=analysis['provenance'],orders=orders,notes=notes,
                    financialAuthority='COMMITTED_EVENTS_ONLY',notesAuthority='MUTABLE_RESEARCH_ANNOTATION')

    def journal_page(self, session_id, raw):
        from .journal import (MAX_JOURNAL_PAGE_SIZE, MAX_JOURNAL_READ_ORDERS,
                              encode_cursor, decode_cursor, validate_note)
        keys(raw, 'limit cursor')
        limit=raw['limit']
        require(type(limit) is int and 1<=limit<=MAX_JOURNAL_PAGE_SIZE,'limit','INVALID_INPUT')
        cursor=raw['cursor']
        require(cursor is None or type(cursor) is str,'cursor','INVALID_CURSOR')
        requested_revision,after_order_id=(None,None) if cursor is None else decode_cursor(cursor,session_id)
        with connect(self.dsn) as db:
            db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            state=self._session(db,session_id)[2]
        if requested_revision is not None:
            require(requested_revision==state['revision'],'cursor','STALE_REVISION')
        indexed=self._journal_projection_page(session_id,state,limit,after_order_id)
        if indexed is not None:
            page,more,total,notes=self._journal_projection_notes(session_id,state,indexed)
            next_cursor=encode_cursor(session_id,state['revision'],page[-1]['id']) if more and page else None
            return dict(schemaVersion=1,artifact='BTL-TICK-JOURNAL-PAGE-1',sessionId=session_id,
                revision=state['revision'],totalOrders=total,orders=page,notes=notes,
                nextCursor=next_cursor,complete=next_cursor is None,
                provenance=dict(sessionId=state['sessionId'],revision=state['revision'],
                    datasetId=state['datasetId'],datasetVersion=state['datasetVersion'],
                    profileHash=state['profileHash'],engineVersion=state['engineVersion'],model=MODEL,
                    methodHash=state['policy']['definitionHash'],analysisVersion=RESEARCH_VERSION),
                financialAuthority='COMMITTED_EVENTS_ONLY',notesAuthority='MUTABLE_RESEARCH_ANNOTATION')
        projection=self._complete_statistics(session_id,state)
        require(self._same_projection(projection,state),'journal','REFUSED_STALE_REVISION')
        analysis=self._view_analysis(state,projection)
        require(analysis['status']=='COMPLETE','journal','REFUSED_ANALYSIS_BUILDING')
        by_id={row['id']:row for row in analysis['orders']}
        for row in analysis['completed']:
            by_id[row['id']]=row
        all_orders=sorted(by_id.values(),key=lambda row:row['id'])
        require(len(all_orders)<=MAX_JOURNAL_READ_ORDERS,'journal','REFUSED_JOURNAL_LIMIT')
        orders=[row for row in all_orders if after_order_id is None or row['id']>after_order_id]
        page=orders[:limit];more=len(orders)>len(page);indexed={row['id']:row for row in page};notes=[]
        with connect(self.dsn) as db:
            db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            live=self._session(db,session_id)[2]
            require(live['revision']==state['revision'] and live['eventHash']==state['eventHash'],
                    'journal','REFUSED_STALE_REVISION')
            if page:
                ids=[row['id'] for row in page]
                saved=db.execute('SELECT payload,content_hash,note_revision,order_id FROM btl.tick_journal_notes WHERE workspace_id=%s AND session_id=%s AND order_id=ANY(%s) ORDER BY order_id LIMIT %s',(self.scope.workspace_id,session_id,ids,limit+1)).fetchall()
                require(len(saved)<=limit,'journalNotes','CORRUPT_RECORD')
                for blob,sha,note_revision,order_id in saved:
                    value=validate_note(unpack(blob,sha),state,indexed)
                    require((value['orderId'],value['noteRevision'])==(order_id,note_revision),'journalNote','CORRUPT_RECORD')
                    notes.append(value)
        next_cursor=encode_cursor(session_id,state['revision'],page[-1]['id']) if more and page else None
        return dict(schemaVersion=1,artifact='BTL-TICK-JOURNAL-PAGE-1',sessionId=session_id,
                    revision=state['revision'],totalOrders=len(all_orders),orders=page,notes=notes,
                    nextCursor=next_cursor,complete=next_cursor is None,provenance=analysis['provenance'],
                    financialAuthority='COMMITTED_EVENTS_ONLY',notesAuthority='MUTABLE_RESEARCH_ANNOTATION')

    def _journal_projection_page(self,session_id,state,limit,after_order_id):
        """Read one indexed page, returning None for pre-index compatibility Sessions."""
        with connect(self.dsn) as db:
            db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            live=self._session(db,session_id)[2]
            require(live['revision']==state['revision'] and live['eventHash']==state['eventHash'],
                    'journal','REFUSED_STALE_REVISION')
            head=db.execute('SELECT format_version,through_sequence,event_hash,order_count '
                'FROM btl.tick_journal_projection_heads WHERE workspace_id=%s AND session_id=%s',
                (self.scope.workspace_id,session_id)).fetchone()
            if head is None:return None
            format_version,through_sequence,event_hash,total=head
            require(format_version==1 and through_sequence==state['nextEventIndex'] and
                    event_hash==state['eventHash'],'journalProjectionHead','CORRUPT_RECORD')
            if after_order_id is None:
                rows=db.execute('SELECT order_id,order_status,last_sequence,event_id,payload,content_hash '
                    'FROM btl.tick_journal_order_projection WHERE workspace_id=%s AND session_id=%s '
                    'ORDER BY order_id COLLATE "C" LIMIT %s',
                    (self.scope.workspace_id,session_id,limit+1)).fetchall()
            else:
                rows=db.execute('SELECT order_id,order_status,last_sequence,event_id,payload,content_hash '
                    'FROM btl.tick_journal_order_projection WHERE workspace_id=%s AND session_id=%s '
                    'AND order_id COLLATE "C">%s COLLATE "C" ORDER BY order_id COLLATE "C" LIMIT %s',
                    (self.scope.workspace_id,session_id,after_order_id,limit+1)).fetchall()
            more=len(rows)>limit;rows=rows[:limit];orders=[]
            for order_id,status,sequence,event_id,blob,sha in rows:
                wire=unpack(blob,sha)
                require(wire.get('artifact')=='BTL-TICK-JOURNAL-ORDER-PROJECTION-1' and
                    (wire.get('sessionId'),wire.get('orderId'),wire.get('status'),
                     wire.get('lastSequence'),wire.get('eventId'))==
                    (session_id,order_id,status,sequence,event_id),'journalProjection','CORRUPT_RECORD')
                order=wire.get('order');history=wire.get('history')
                require(type(order) is dict and type(history) is dict,'journalProjection','CORRUPT_RECORD')
                orders.append(journal_order_summary(order_id,status,order,history))
            return orders,more,total

    def _journal_projection_notes(self,session_id,state,projection_page):
        orders,more,total=projection_page
        indexed={row['id']:row for row in orders}
        notes=[]
        if orders:
            ids=[row['id'] for row in orders]
            with connect(self.dsn) as db:
                db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
                live=self._session(db,session_id)[2]
                require(live['revision']==state['revision'] and live['eventHash']==state['eventHash'],
                        'journal','REFUSED_STALE_REVISION')
                saved=db.execute('SELECT payload,content_hash,note_revision,order_id '
                    'FROM btl.tick_journal_notes WHERE workspace_id=%s AND session_id=%s '
                    'AND order_id=ANY(%s) ORDER BY order_id LIMIT %s',
                    (self.scope.workspace_id,session_id,ids,len(ids)+1)).fetchall()
                require(len(saved)<=len(ids),'journalNotes','CORRUPT_RECORD')
                for blob,sha,note_revision,order_id in saved:
                    value=validate_note(unpack(blob,sha),state,indexed)
                    require((value['orderId'],value['noteRevision'])==(order_id,note_revision),
                            'journalNote','CORRUPT_RECORD')
                    notes.append(value)
        # Keep the same summary-order shape exposed by the legacy Journal path;
        # completed trade rows remain available through Analytics pagination.
        return orders,more,total,notes

    def order_history_page(self,session_id,raw):
        keys(raw,'limit afterSequence revision')
        limit=raw['limit'];after=raw['afterSequence'];revision_pin=raw['revision']
        require(type(limit) is int and 1<=limit<=256,'limit','INVALID_INPUT')
        require(after is None or (type(after) is int and after>=-1),'afterSequence','INVALID_CURSOR')
        require(revision_pin is None or (type(revision_pin) is int and revision_pin>=0),
                'revision','INVALID_CURSOR')
        return self.controller.order_history_page(self.scope,session_id,after_sequence=after,
            revision_pin=revision_pin,maximum=limit)

    def analytics_page(self,session_id,raw):
        """Return one bounded completed-trade page with revision-pinned metrics."""
        required={'limit','offset','revision'}
        require(type(raw) is dict and required.issubset(raw) and
            set(raw).issubset(required|{'cursor'}),'analyticsPage','SCHEMA_MISMATCH')
        limit=raw['limit'];offset=raw['offset'];revision_pin=raw['revision']
        require(type(limit) is int and 1<=limit<=64,'limit','INVALID_INPUT')
        require(type(offset) is int and offset>=0,'offset','INVALID_CURSOR')
        require(revision_pin is None or (type(revision_pin) is int and revision_pin>=0),
                'revision','INVALID_CURSOR')
        cursor_token=raw.get('cursor')
        require(cursor_token is None or type(cursor_token) is str,'cursor','INVALID_CURSOR')
        require(cursor_token is None or offset==0,'cursor','INVALID_CURSOR')
        with connect(self.dsn) as db:
            db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            state=self._session(db,session_id)[2]
        cursor=None
        if cursor_token is not None:
            cursor_revision,after_sequence,after_order_id=decode_trade_cursor(cursor_token,session_id)
            require(cursor_revision==state['revision'] and
                (revision_pin is None or revision_pin==cursor_revision),'revision','STALE_REVISION')
            revision_pin=cursor_revision;cursor=(after_sequence,after_order_id)
        require(revision_pin is None or revision_pin==state['revision'],'revision','STALE_REVISION')
        durable=self._durable_analytics_page(session_id,state,offset,limit,cursor=cursor)
        if durable is not None:return durable
        require(cursor is None,'cursor','ANALYTICS_CURSOR_UNAVAILABLE')
        projection=self.statistics.inspect(self.scope,session_id,offset,limit)
        require(self._same_projection(projection,state),'analysisSnapshot','REFUSED_STALE_REVISION')
        if projection['status']=='BUILDING':
            return dict(schemaVersion=1,artifact='BTL-OBSERVED-ANALYTICS-PAGE-1',sessionId=session_id,
                revision=state['revision'],status='BUILDING',processedEvents=projection['processedEvents'],
                totalEvents=projection['totalEvents'],completed=[],nextTradeOffset=None)
        analysis=self._view_analysis(state,projection)
        require(analysis['status']=='COMPLETE','analysis','CORRUPT_RECORD')
        return dict(schemaVersion=1,artifact='BTL-OBSERVED-ANALYTICS-PAGE-1',sessionId=session_id,
            revision=state['revision'],status='COMPLETE',metrics=analysis['metrics'],
            completed=analysis['completed'],nextTradeOffset=projection['nextTradeOffset'],
            account=analysis['account'],equity=analysis['equity'],
            equityWindowStart=analysis['metrics']['equityWindowStart'],
            annotations=analysis['annotations'],annotationWindowStart=analysis['annotationWindowStart'],
            provenance=analysis['provenance'])

    def _durable_analytics_page(self,session_id,state,offset,limit,*,cursor=None):
        """Serve a bounded page from the transactionally maintained aggregate."""
        with connect(self.dsn) as db:
            db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            live=self._session(db,session_id)[2]
            require(live['revision']==state['revision'] and live['eventHash']==state['eventHash'],
                    'analysisSnapshot','REFUSED_STALE_REVISION')
            head=db.execute('SELECT analytics_format_version,closed_order_count FROM '
                'btl.tick_journal_projection_heads WHERE workspace_id=%s AND session_id=%s',
                (self.scope.workspace_id,session_id)).fetchone()
            if head is None or head[0]!=1:return None
            aggregate_row=db.execute('SELECT payload,content_hash FROM btl.tick_session_metric_projections '
                'WHERE workspace_id=%s AND session_id=%s',
                (self.scope.workspace_id,session_id)).fetchone()
            require(aggregate_row is not None,'analyticsProjection','CORRUPT_RECORD')
            aggregate=unpack(*aggregate_row)
            require(aggregate.get('artifact')==ANALYTICS_PROJECTION_ARTIFACT and
                aggregate.get('sessionId')==session_id and aggregate.get('revision')==state['revision'] and
                aggregate.get('eventHead')==state['eventHash'] and
                aggregate.get('tradeCount')==head[1],'analyticsProjectionHead','CORRUPT_RECORD')
            total=head[1]
            if cursor is None:
                require(offset<=total,'offset','INVALID_CURSOR')
                rows=db.execute('SELECT last_sequence,order_id,payload,content_hash FROM btl.tick_journal_order_projection '
                    'WHERE workspace_id=%s AND session_id=%s AND order_status=\'CLOSED\' '
                    'ORDER BY last_sequence,order_id COLLATE "C" OFFSET %s LIMIT %s',
                    (self.scope.workspace_id,session_id,offset,limit+1)).fetchall()
            else:
                after_sequence,after_order_id=cursor
                require(type(after_sequence) is int and 0<=after_sequence<state['nextEventIndex'],
                    'cursor','INVALID_CURSOR')
                prior=db.execute('SELECT order_id FROM btl.tick_journal_order_projection '
                    'WHERE workspace_id=%s AND session_id=%s AND order_status=\'CLOSED\' '
                    'AND last_sequence=%s AND order_id=%s COLLATE "C"',
                    (self.scope.workspace_id,session_id,after_sequence,after_order_id)).fetchone()
                require(prior is not None,'cursor','INVALID_CURSOR')
                rows=db.execute('SELECT last_sequence,order_id,payload,content_hash FROM btl.tick_journal_order_projection '
                    'WHERE workspace_id=%s AND session_id=%s AND order_status=\'CLOSED\' '
                    'AND (last_sequence,order_id COLLATE "C")>(%s,%s::text COLLATE "C") '
                    'ORDER BY last_sequence,order_id COLLATE "C" LIMIT %s',
                    (self.scope.workspace_id,session_id,after_sequence,after_order_id,limit+1)).fetchall()
            more=len(rows)>limit;rows=rows[:limit]
            if cursor is None:
                require(len(rows)==min(limit,total-offset),'analyticsOrderProjection','CORRUPT_RECORD')
            else:
                require(len(rows)<=limit and total>=len(rows),'analyticsOrderProjection','CORRUPT_RECORD')
            completed=[]
            for _last_sequence,order_id,blob,sha in rows:
                wire=unpack(blob,sha)
                require(wire.get('artifact')=='BTL-TICK-JOURNAL-ORDER-PROJECTION-1' and
                    wire.get('sessionId')==session_id and wire.get('orderId')==order_id and
                    wire.get('status')=='CLOSED' and type(wire.get('history')) is dict,
                    'analyticsOrderProjection','CORRUPT_RECORD')
                completed.append(completed_trade_row(order_id,wire['order'],wire['history']))
            view=analytics_view(aggregate,state)
            next_cursor=None
            if more and rows:
                next_cursor=encode_trade_cursor(session_id,state['revision'],rows[-1][0],rows[-1][1])
            return dict(schemaVersion=1,artifact='BTL-OBSERVED-ANALYTICS-PAGE-1',sessionId=session_id,
                revision=state['revision'],status='COMPLETE',metrics=view['metrics'],completed=completed,
                nextTradeOffset=(offset+len(completed) if cursor is None and offset+len(completed)<total else None),
                nextCursor=next_cursor,
                account=view['account'],equity=view['equity'],equityWindowStart=view['equityWindowStart'],
                annotations=view['annotations'],annotationWindowStart=view['annotationWindowStart'],
                provenance=view['provenance'])

    def save_note(self,session_id,raw):
        journal_request(raw)
        with connect(self.dsn) as db:
            meta,method,state,cp=self._session(db,session_id,lock=True)
            head=db.execute('SELECT format_version,through_sequence,event_hash FROM btl.tick_journal_projection_heads '
                'WHERE workspace_id=%s AND session_id=%s',(self.scope.workspace_id,session_id)).fetchone()
            if head is not None and head[0]==1:
                require(head[1:]==(state['nextEventIndex'],state['eventHash']),
                        'journalProjectionHead','CORRUPT_RECORD')
                indexed=db.execute('SELECT order_status,payload,content_hash FROM '
                    'btl.tick_journal_order_projection WHERE workspace_id=%s AND session_id=%s AND order_id=%s',
                    (self.scope.workspace_id,session_id,raw['orderId'])).fetchone()
                require(indexed is not None,'order','RESOURCE_UNAVAILABLE')
                status,blob,sha=indexed;wire=unpack(blob,sha)
                require(wire.get('artifact')=='BTL-TICK-JOURNAL-ORDER-PROJECTION-1' and
                    (wire.get('sessionId'),wire.get('orderId'),wire.get('status'))==
                    (session_id,raw['orderId'],status),'journalProjection','CORRUPT_RECORD')
                orders={raw['orderId']:wire['order']}
            else:
                projection=self._complete_statistics(session_id,state)
                require(self._same_projection(projection,state),'journal','REFUSED_STALE_REVISION')
                require(projection['status']=='COMPLETE','journal','REFUSED_ANALYSIS_BUILDING')
                orders={r['id']:r for r in projection['completed']}
                require(raw['orderId'] in orders,'order','RESOURCE_UNAVAILABLE')
            prior=db.execute('SELECT payload,content_hash,note_revision FROM btl.tick_journal_notes WHERE workspace_id=%s AND session_id=%s AND order_id=%s FOR UPDATE',(self.scope.workspace_id,session_id,raw['orderId'])).fetchone()
            previous=validate_note(unpack(*prior[:2]),state,orders) if prior else None
            current=prior[2] if prior else 0
            if previous and current==raw['expectedNoteRevision']+1 and previous['text']==raw['text'] and previous['tags']==raw['tags']:return previous
            require(raw['expectedNoteRevision']==current,'noteRevision','REFUSED_STALE_NOTE')
            value=dict(schemaVersion=1,artifact='BTL-TICK-JOURNAL-NOTE-1',sessionId=session_id,datasetId=state['datasetId'],datasetVersion=state['datasetVersion'],orderId=raw['orderId'],noteRevision=current+1,text=raw['text'],tags=raw['tags'])
            validate_note(value,state,orders);blob,sha=pack(value)
            db.execute('INSERT INTO btl.tick_journal_notes VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (workspace_id,session_id,order_id) DO UPDATE SET note_revision=EXCLUDED.note_revision,payload=EXCLUDED.payload,content_hash=EXCLUDED.content_hash',(self.scope.workspace_id,session_id,raw['orderId'],value['noteRevision'],blob,sha))
            return value

    def review(self,raw):
        keys(raw,'sessionId requestId expectedRevision planId planRevision draft');identifier(raw['requestId'],'requestId');identifier(raw['sessionId'],'sessionId');revision(raw['expectedRevision'])
        require(raw['planId'] is None or type(raw['planId']) is str,'planId');require(raw['planRevision'] is None or type(raw['planRevision']) is int,'planRevision')
        req_hash=content_hash(dict(schemaVersion=1,artifact='BTL-OBSERVED-REVIEW-REQUEST-1',**raw));
        with connect(self.dsn) as db:
            meta,method,state,cp,storage_format=self._session(db,raw['sessionId'],lock=True,include_format=True);prior=db.execute('SELECT payload,content_hash FROM btl.tick_order_reviews WHERE workspace_id=%s AND session_id=%s AND review_id=%s',(self.scope.workspace_id,raw['sessionId'],raw['requestId'])).fetchone()
            if prior:
                saved=unpack(*prior);require(saved['requestHash']==req_hash,'requestId','REFUSED_IDEMPOTENCY_CONFLICT');return dict(review=saved,reviewHash=prior[1])
            require(raw['expectedRevision']==state['revision'] and not state['ended'] and not state['unresolved'],'revision','REFUSED_STALE_REVISION')
            draft=deepcopy(raw['draft']);keys(draft,'side orderType workflow entry quantity sl tp riskPercent observations');require(type(draft['observations']) is list and len(draft['observations'])<=64,'observations')
            for observation in draft['observations']:keys(observation,'conditionId outcome');Observation(observation['conditionId'],observation['outcome'])
            require(len({o['conditionId'] for o in draft['observations']})==len(draft['observations']),'observations')
            p=ObservedExecutionProfile.from_wire(state['profile']);policy=method_policy(method);basis=state['quoteBasis']
            require(basis is not None and int(state['throughNs'])-int(basis['timeNs'])<=int(p.wire['maxObservedSilenceNs']),'quote','UNRESOLVED_RISK_QUOTE')
            side_quote=basis['ask'] if draft['side']=='LONG' else basis['bid']
            if draft['orderType']=='MARKET':draft['entry']=side_quote
            if policy.kind=='PROTOCOL':
                require(draft['workflow']=='PLANNED' and draft['orderType'] in ('LIMIT','STOP'),'protocolType','PROTOCOL_BLOCKED')
                entry=exact(draft['entry'],'entry');stop=exact(draft['sl'],'sl');tp=text(entry+(entry-stop)*Fraction(policy.rr))
                require(draft['tp'] is None or exact(draft['tp'],'tp')==Fraction(tp),'tp','PROTOCOL_BLOCKED')
                require(draft['riskPercent'] is None or exact(draft['riskPercent'],'riskPercent')==Fraction(policy.risk_percent),'risk','PROTOCOL_BLOCKED')
                draft.update(tp=tp,riskPercent=text(Fraction(policy.risk_percent)))
                supplied={o['conditionId']:o['outcome'] for o in draft['observations']}
                require(set(supplied).issubset(policy.conditions),'conditions');draft['observations']=[dict(conditionId=c,outcome=supplied.get(c,'NOT_ASSESSED')) for c in policy.conditions]
                if draft['quantity'] is None:draft['quantity']=risk_quantity(text(Fraction(state['balance'])*Fraction(policy.risk_percent)/100),draft['entry'],draft['sl'],p.wire)
            elif draft['quantity'] is None:
                require(draft['sl'] is not None,'quantity','REFUSED_QUANTITY_WITHOUT_STOP')
                draft['quantity']=risk_quantity(text(Fraction(state['balance'])*exact(draft['riskPercent'],'riskPercent',True)/100),draft['entry'],draft['sl'],p.wire)
            payload=open_payload(draft,p.wire,policy,state['balance'])
            review_artifact = PROGRESS_REVIEW if storage_format == PROGRESS_FORMAT else REVIEW
            if review_artifact == PROGRESS_REVIEW:
                basis_sha = content_hash(state)
            else:
                basis_row=db.execute('SELECT content_hash FROM btl.tick_checkpoints WHERE workspace_id=%s AND session_id=%s AND revision=%s',(self.scope.workspace_id,raw['sessionId'],state['revision'])).fetchone()
                require(basis_row is not None,'checkpoint','CORRUPT_RECORD')
                basis_sha=basis_row[0]
            basis_hash=content_hash(dict(schemaVersion=1,artifact='BTL-OBSERVED-REVIEW-BASIS-1',snapshotHash=basis_sha,quote=deepcopy(basis)))
            command=dict(schemaVersion=1,artifact='BTL-OBSERVED-EXECUTION-COMMAND-1',sessionId=raw['sessionId'],commandId=raw['requestId'],expectedRevision=state['revision'],kind='OPEN',payload=payload)
            risk=planned_risk(state,command);ctx=SessionContext(self.scope.workspace_id,raw['sessionId'],policy,'XAUUSD',p.wire['primary']['feedId'],state['profileHash'],state['revision'],state['revision'],datetime.fromtimestamp(int(state['throughNs'])//10**9,timezone.utc),Decimal(basis['ask'] if payload['side']=='LONG' else basis['bid']))
            request=Command(self.scope.workspace_id,raw['sessionId'],raw['requestId'],policy.method_id,policy.definition_hash,'XAUUSD',ctx.feed_id,state['profileHash'],state['revision'],state['revision'],payload['workflow'],'BUY' if payload['side']=='LONG' else 'SELL',payload['orderType'],Decimal(payload['entry']),Decimal(payload['quantity']),Decimal(payload['riskPercent']),None if payload['sl'] is None else Decimal(payload['sl']),None if payload['tp'] is None else Decimal(payload['tp']),raw['planId'],raw['planRevision'],tuple(Observation(o['conditionId'],o['outcome']) for o in payload['observations']))
            validate_command(request,ctx)
            reviewed=dict(schemaVersion=1,artifact=review_artifact,requestHash=req_hash,command=command,contractRequest=json.loads(canonical_bytes(request.identity_payload())),methodHash=state['policy']['definitionHash'],profileHash=state['profileHash'],throughNs=state['throughNs'],riskBasis=state['balance'],model=MODEL,basisCheckpointHash=basis_sha,basisHash=basis_hash,researchRisk=risk)
            count=db.execute('SELECT count(*) FROM btl.tick_order_reviews WHERE workspace_id=%s AND session_id=%s',(self.scope.workspace_id,raw['sessionId'])).fetchone()[0];require(count<256,'reviews','REFUSED_REVIEW_LIMIT');blob,sha=pack(reviewed);db.execute('INSERT INTO btl.tick_order_reviews VALUES (%s,%s,%s,%s,%s)',(self.scope.workspace_id,raw['sessionId'],raw['requestId'],blob,sha))
        return dict(review=reviewed,reviewHash=sha)

    def confirm(self,session_id,raw):
        keys(raw,'reviewId reviewHash');identifier(raw['reviewId'],'reviewId');from contracts.primitives import digest;digest(raw['reviewHash'],'reviewHash')
        with connect(self.dsn) as db:
            meta,method,state,cp=self._session(db,session_id);row=db.execute('SELECT payload,content_hash FROM btl.tick_order_reviews WHERE workspace_id=%s AND session_id=%s AND review_id=%s',(self.scope.workspace_id,session_id,raw['reviewId'])).fetchone();require(row is not None,'review','RESOURCE_UNAVAILABLE');reviewed=unpack(*row);command=reviewed.get('command',{});require(row[1]==raw['reviewHash'] and reviewed.get('artifact') in (REVIEW,PROGRESS_REVIEW) and command.get('sessionId')==session_id and command.get('commandId')==raw['reviewId'],'reviewHash','REFUSED_IDEMPOTENCY_CONFLICT')
            require(reviewed['methodHash']==state['policy']['definitionHash'] and reviewed['profileHash']==state['profileHash'],'review','CORRUPT_RECORD')
            if reviewed['artifact']==PROGRESS_REVIEW:
                prior=self.store._prior(db,self.scope.workspace_id,session_id,command_wire(command))
                if prior is not None:return prior
                require(state['revision']==command['expectedRevision'],'reviewBasis','REFUSED_STALE_REVISION')
                basis=state
                basis_sha=content_hash(basis)
            else:
                basis_row=db.execute('SELECT content_hash FROM btl.tick_checkpoints WHERE workspace_id=%s AND session_id=%s AND revision=%s',(self.scope.workspace_id,session_id,command.get('expectedRevision'))).fetchone()
                require(basis_row is not None,'reviewBasis','CORRUPT_RECORD')
                basis_sha=basis_row[0]
                basis=self.store.historical_checkpoint(db,self.scope,session_id,command.get('expectedRevision'))['state']
            require(basis_sha==reviewed.get('basisCheckpointHash') and basis['sessionId']==session_id and
                    basis['profileHash']==reviewed['profileHash'] and basis['policy']['definitionHash']==reviewed['methodHash'] and
                    basis['throughNs']==reviewed['throughNs'],'reviewBasis','CORRUPT_RECORD')
            quote=basis.get('quoteBasis');require(quote is not None and reviewed.get('basisHash')==content_hash(dict(schemaVersion=1,artifact='BTL-OBSERVED-REVIEW-BASIS-1',snapshotHash=basis_sha,quote=deepcopy(quote))),'reviewBasis','CORRUPT_RECORD')
            p=ObservedExecutionProfile.from_wire(basis['profile']);payload=open_payload(command['payload'],p.wire,method_policy(method),basis['balance']);require(payload==command['payload'],'reviewPayload','CORRUPT_RECORD')
            if payload['orderType']=='MARKET':require(payload['entry']==quote['ask' if payload['side']=='LONG' else 'bid'],'reviewQuote','CORRUPT_RECORD')
            require(reviewed['researchRisk']==planned_risk(basis,command),'reviewRisk','CORRUPT_RECORD')
        return self.controller.apply(self.scope,reviewed['command'])

    def command_result(self,session_id,command_id):
        identifier(command_id,'commandId')
        with connect(self.dsn) as db:
            db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            _,_,state,_=self._session(db,session_id)
            result=dict(schemaVersion=1,artifact='BTL-TICK-COMMAND-STATUS-1',sessionId=session_id,
                        commandId=command_id,currentRevision=state['revision'],status='UNKNOWN',
                        reason='REVIEW_OR_COMMAND_NOT_VISIBLE')
            row=db.execute('SELECT payload,content_hash FROM btl.tick_order_reviews '
                           'WHERE workspace_id=%s AND session_id=%s AND review_id=%s',
                           (self.scope.workspace_id,session_id,command_id)).fetchone()
            if row is None:return result
            reviewed=unpack(*row)
            command=command_wire(reviewed['command'])
            require(reviewed['artifact'] in (REVIEW,PROGRESS_REVIEW) and command['kind']=='OPEN' and
                    command['sessionId']==session_id and command['commandId']==command_id,
                    'review','CORRUPT_RECORD')
            result.update(reviewHash=row[1],expectedRevision=command['expectedRevision'])
            receipt=self.store._prior(db,self.scope.workspace_id,session_id,command)
            if receipt is not None:
                require(receipt['state']['revision']==command['expectedRevision']+1<=state['revision'],
                        'receipt','CORRUPT_RECORD')
                result.pop('reason')
                return dict(result,status='COMMITTED',receipt=receipt)
            require(command_id not in state['orders'],'receipt','CORRUPT_RECORD')
            if state['revision']>command['expectedRevision']:
                return dict(result,status='NOT_COMMITTED',reason='SESSION_REVISION_ADVANCED')
            return dict(result,reason='NO_DURABLE_COMMAND_AT_REVIEW_REVISION')

    def inspect_statistics(self,session_id,trade_offset=0):return self.statistics.inspect(self.scope,session_id,trade_offset,64)
