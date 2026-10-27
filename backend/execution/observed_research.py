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
from .contracts import exact,open_payload,policy_wire,text
from .journal import validate_note,request as journal_request,MAX_JOURNAL_ORDERS
from .observed_catalog import ObservedCatalog
from .observed_controller import ObservedExecutionController
from .observed_kernel import seed_state
from .observed_postgres import ObservedExecutionStore,read_snapshot
from .observed_profile import ENGINE_VERSION,MODEL,ObservedExecutionProfile
from .observed_analysis import ObservedStatistics
from .postgres import pack,unpack
from .research import method_policy,label
from .bootstrap import bootstrap as descriptive_bootstrap,validate_seed

META='BTL-OBSERVED-RESEARCH-SESSION-1'
VIEW='BTL-OBSERVED-RESEARCH-VIEW-1'
_STATS_LOCK=RLock()
_STATS_BY_DSN=OrderedDict()
REVIEW='BTL-OBSERVED-ORDER-REVIEW-1'


class ObservedResearchApplication:
    """One workspace-scoped Method/Session adapter for the observed family."""
    def __init__(self,dsn,scope,catalog):
        require(type(scope) is TrustedScope,'scope','SCOPE_REQUIRED');require(type(catalog) is ObservedCatalog,'catalog')
        self.dsn=dsn;self.scope=scope;self.catalog=catalog;self.store=ObservedExecutionStore(dsn)
        self.controller=ObservedExecutionController(self.store,catalog.resolve)
        key=content_hash(dict(schemaVersion=1,artifact='BTL-OBSERVED-STATS-SERVICE-KEY-1',dsnHash=content_hash({'schemaVersion':1,'dsn':dsn})))
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
        rows=list(projection['completed'])
        while projection['nextTradeOffset'] is not None:
            next_page=self.statistics.inspect(self.scope,session_id,projection['nextTradeOffset'],64)
            require(self._same_projection(next_page,state) and next_page['status']=='COMPLETE','analysisSnapshot','REFUSED_STALE_REVISION')
            rows.extend(next_page['completed']);projection=next_page
        require(self._same_projection(projection,state),'analysisSnapshot','REFUSED_STALE_REVISION')
        projection['completed']=rows;projection['nextTradeOffset']=None
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
                    self._session(db,meta['id']);sessions.append(meta)
                elif meta.get('artifact')=='BTL-LOCAL-SESSION-1':
                    tag(meta,'BTL-LOCAL-SESSION-1','id name methodId methodHash datasetId datasetVersion profileHash startPeriod initialBalance')
                    require(meta['methodId']==method_id,'session','CORRUPT_RECORD');self._method(db,method_id);sessions.append(meta)
            return dict(schemaVersion=1,artifact='BTL-OBSERVED-RESEARCH-CATALOG-1',methods=methods,sessions=sessions,datasets=self.catalog.public(),model=MODEL)

    def _session(self,db,session_id,*,lock=False):
        identifier(session_id,'sessionId')
        row=db.execute('SELECT payload,content_hash,method_id FROM btl.tick_research_sessions WHERE workspace_id=%s AND session_id=%s',(self.scope.workspace_id,session_id)).fetchone()
        require(row is not None,'session','RESOURCE_UNAVAILABLE');meta=unpack(*row[:2])
        tag(meta,META,'id name methodId methodHash datasetKey period day datasetId datasetVersion profileHash startNs initialBalance model engineVersion creationRequestHash')
        require(meta['id']==session_id and meta['methodId']==row[2] and meta['model']==MODEL and meta['engineVersion']==ENGINE_VERSION,'session','CORRUPT_RECORD')
        method=self._method(db,meta['methodId']);policy=method_policy(method);scoped_row=db.execute('SELECT payload,content_hash,revision,dataset_version,profile_hash FROM btl.tick_sessions WHERE workspace_id=%s AND session_id=%s'+(' FOR UPDATE' if lock else ''),(self.scope.workspace_id,session_id)).fetchone()
        require(scoped_row is not None,'state','CORRUPT_RECORD');saved=read_snapshot(scoped_row[0],scoped_row[1]);state,cp=saved['state'],saved['controller']
        require(state['sessionId']==session_id and state['policy']==policy_wire(policy) and state['revision']==scoped_row[2] and (state['datasetVersion'],state['profileHash'])==tuple(scoped_row[3:]),'state','CORRUPT_RECORD')
        require((meta['methodHash'],meta['datasetId'],meta['datasetVersion'],meta['profileHash'],meta['startNs'],meta['initialBalance'])==(policy.definition_hash,state['datasetId'],state['datasetVersion'],state['profileHash'],state['startNs'],state['initialBalance']),'sessionPins','CORRUPT_RECORD')
        # Full current tip must match its immutable checkpoint even on metadata reads.
        tip=db.execute('SELECT payload,content_hash FROM btl.tick_checkpoints WHERE workspace_id=%s AND session_id=%s AND revision=%s',(self.scope.workspace_id,session_id,state['revision'])).fetchone()
        require(tip is not None and bytes(tip[0])==bytes(scoped_row[0]) and tip[1]==scoped_row[1],'immutableTip','CORRUPT_RECORD')
        return meta,method,state,cp

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
                method=self._method(db,raw['methodId']);policy=method_policy(method)
                start=source.start_for_period(raw['period'],day=raw['day']);timeline=source.cache.new_timeline(self.scope,raw['id'],start);cp=timeline.checkpoint()
                state=seed_state(raw['id'],profile,policy,cp,initial)
                meta=dict(schemaVersion=1,artifact=META,id=raw['id'],name=name,methodId=raw['methodId'],methodHash=policy.definition_hash,datasetKey=raw['sourceKey'],period=raw['period'],day=raw['day'],datasetId=state['datasetId'],datasetVersion=state['datasetVersion'],profileHash=state['profileHash'],startNs=state['startNs'],initialBalance=state['initialBalance'],model=MODEL,engineVersion=ENGINE_VERSION,creationRequestHash=request_hash)
                blob,sha=pack(meta);self.store._insert(db,self.scope,state,cp)
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
        for r in rows:
            completed.append(dict(id=r['id'],side=r['side'],status='CLOSED',quantity=r['quantity'],remaining='0',entry=r['entryPrice'],entryPrice=r['entryPrice'],entryTimeNs=r['entryTimeNs'],entryFillRef=r['entryFillRef'],sl=state['orders'][r['id']]['sl'],tp=state['orders'][r['id']]['tp'],exitPrice=r['exitPrice'],exitFillRef=r['exitFillRef'],exitReason=r['exitReason'],gross=r['grossExact'],commission='0',net=r['netPosted'],durationNs=r['durationNs'],mae=None,mfe=None,excursionReason='OBSERVED_EXCURSIONS_NOT_COMPUTED',rMultiple=r['rMultiple'],rReason=r['rReason']))
        provenance=deepcopy(projection['provenance']);provenance['analysisVersion']=RESEARCH_VERSION
        base.update(status='COMPLETE',provenance=provenance,metrics=metrics,orders=orders,completed=completed,equity=deepcopy(projection['balanceCurve']),analysisProjection=projection)
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

    def workspace(self,session_id,raw):
        keys(raw,'timeframe')
        return self.inspect(session_id,raw['timeframe'])

    def journal(self,session_id):
        # Reuse the immutable committed analysis projection. Notes are held
        # separately and cannot affect financial results.
        from .journal import MAX_JOURNAL_ORDERS
        view=self.inspect(session_id)
        require(view['analysis']['status']=='COMPLETE','journal','REFUSED_ANALYSIS_BUILDING')
        orders=view['analysis']['orders']
        require(len(orders)<=MAX_JOURNAL_ORDERS,'journal','REFUSED_JOURNAL_LIMIT')
        state=view['state'];notes=[]
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
        return dict(schemaVersion=1,artifact='BTL-TICK-JOURNAL-1',provenance=view['analysis']['provenance'],orders=orders,notes=notes,
                    financialAuthority='COMMITTED_EVENTS_ONLY',notesAuthority='MUTABLE_RESEARCH_ANNOTATION')

    def save_note(self,session_id,raw):
        journal_request(raw)
        with connect(self.dsn) as db:
            meta,method,state,cp=self._session(db,session_id,lock=True)
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
            meta,method,state,cp=self._session(db,raw['sessionId'],lock=True);prior=db.execute('SELECT payload,content_hash FROM btl.tick_order_reviews WHERE workspace_id=%s AND session_id=%s AND review_id=%s',(self.scope.workspace_id,raw['sessionId'],raw['requestId'])).fetchone()
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
            basis_row=db.execute('SELECT payload,content_hash FROM btl.tick_checkpoints WHERE workspace_id=%s AND session_id=%s AND revision=%s',(self.scope.workspace_id,raw['sessionId'],state['revision'])).fetchone();require(basis_row is not None,'checkpoint','CORRUPT_RECORD');basis_sha=basis_row[1];basis_hash=content_hash(dict(schemaVersion=1,artifact='BTL-OBSERVED-REVIEW-BASIS-1',snapshotHash=basis_sha,quote=deepcopy(basis)))
            command=dict(schemaVersion=1,artifact='BTL-OBSERVED-EXECUTION-COMMAND-1',sessionId=raw['sessionId'],commandId=raw['requestId'],expectedRevision=state['revision'],kind='OPEN',payload=payload)
            risk=planned_risk(state,command);ctx=SessionContext(self.scope.workspace_id,raw['sessionId'],policy,'XAUUSD',p.wire['primary']['feedId'],state['profileHash'],state['revision'],state['revision'],datetime.fromtimestamp(int(state['throughNs'])//10**9,timezone.utc),Decimal(basis['ask'] if payload['side']=='LONG' else basis['bid']))
            request=Command(self.scope.workspace_id,raw['sessionId'],raw['requestId'],policy.method_id,policy.definition_hash,'XAUUSD',ctx.feed_id,state['profileHash'],state['revision'],state['revision'],payload['workflow'],'BUY' if payload['side']=='LONG' else 'SELL',payload['orderType'],Decimal(payload['entry']),Decimal(payload['quantity']),Decimal(payload['riskPercent']),None if payload['sl'] is None else Decimal(payload['sl']),None if payload['tp'] is None else Decimal(payload['tp']),raw['planId'],raw['planRevision'],tuple(Observation(o['conditionId'],o['outcome']) for o in payload['observations']))
            validate_command(request,ctx)
            reviewed=dict(schemaVersion=1,artifact=REVIEW,requestHash=req_hash,command=command,contractRequest=json.loads(canonical_bytes(request.identity_payload())),methodHash=state['policy']['definitionHash'],profileHash=state['profileHash'],throughNs=state['throughNs'],riskBasis=state['balance'],model=MODEL,basisCheckpointHash=basis_sha,basisHash=basis_hash,researchRisk=risk)
            count=db.execute('SELECT count(*) FROM btl.tick_order_reviews WHERE workspace_id=%s AND session_id=%s',(self.scope.workspace_id,raw['sessionId'])).fetchone()[0];require(count<256,'reviews','REFUSED_REVIEW_LIMIT');blob,sha=pack(reviewed);db.execute('INSERT INTO btl.tick_order_reviews VALUES (%s,%s,%s,%s,%s)',(self.scope.workspace_id,raw['sessionId'],raw['requestId'],blob,sha))
        return dict(review=reviewed,reviewHash=sha)

    def confirm(self,session_id,raw):
        keys(raw,'reviewId reviewHash');identifier(raw['reviewId'],'reviewId');from contracts.primitives import digest;digest(raw['reviewHash'],'reviewHash')
        with connect(self.dsn) as db:
            meta,method,state,cp=self._session(db,session_id);row=db.execute('SELECT payload,content_hash FROM btl.tick_order_reviews WHERE workspace_id=%s AND session_id=%s AND review_id=%s',(self.scope.workspace_id,session_id,raw['reviewId'])).fetchone();require(row is not None,'review','RESOURCE_UNAVAILABLE');reviewed=unpack(*row);command=reviewed.get('command',{});require(row[1]==raw['reviewHash'] and reviewed.get('artifact')==REVIEW and command.get('sessionId')==session_id and command.get('commandId')==raw['reviewId'],'reviewHash','REFUSED_IDEMPOTENCY_CONFLICT')
            require(reviewed['methodHash']==state['policy']['definitionHash'] and reviewed['profileHash']==state['profileHash'],'review','CORRUPT_RECORD')
            basis_row=db.execute('SELECT payload,content_hash FROM btl.tick_checkpoints WHERE workspace_id=%s AND session_id=%s AND revision=%s',(self.scope.workspace_id,session_id,command.get('expectedRevision'))).fetchone();require(basis_row is not None and basis_row[1]==reviewed.get('basisCheckpointHash'),'reviewBasis','CORRUPT_RECORD')
            basis=read_snapshot(*basis_row)['state'];require(basis['sessionId']==session_id and basis['profileHash']==reviewed['profileHash'] and basis['policy']['definitionHash']==reviewed['methodHash'] and basis['throughNs']==reviewed['throughNs'],'reviewBasis','CORRUPT_RECORD')
            quote=basis.get('quoteBasis');require(quote is not None and reviewed.get('basisHash')==content_hash(dict(schemaVersion=1,artifact='BTL-OBSERVED-REVIEW-BASIS-1',snapshotHash=basis_row[1],quote=deepcopy(quote))),'reviewBasis','CORRUPT_RECORD')
            p=ObservedExecutionProfile.from_wire(basis['profile']);payload=open_payload(command['payload'],p.wire,method_policy(method),basis['balance']);require(payload==command['payload'],'reviewPayload','CORRUPT_RECORD')
            if payload['orderType']=='MARKET':require(payload['entry']==quote['ask' if payload['side']=='LONG' else 'bid'],'reviewQuote','CORRUPT_RECORD')
            require(reviewed['researchRisk']==planned_risk(basis,command),'reviewRisk','CORRUPT_RECORD')
        return self.controller.apply(self.scope,reviewed['command'])

    def inspect_statistics(self,session_id,trade_offset=0):return self.statistics.inspect(self.scope,session_id,trade_offset,64)
