"""Server-private scoped engine2 Session/review/journal service, not HTTP auth."""
from copy import deepcopy
from fractions import Fraction
import psycopg
from psycopg import sql
from application.models import TrustedScope
from contracts.canonical import canonical_bytes, content_hash
from contracts.primitives import require, identifier, digest, revision, ContractError
from contracts.models import Observation
from ticks.contracts import tag, keys, uint
from infrastructure.database import connect
from .contracts import exact, money, text, policy_wire, policy_from_wire
from .kernel_v2 import seed_state, submit, command_wire, ratio as fraction
from .finance_v2 import price, quantity, planned_risk
from .profile_v2 import ENGINE_VERSION
from .sources_v2 import SourceJoinV2
from .controller_v2 import ExecutionControllerV2
from .postgres_v2 import PostgresExecutionStoreV2, read_snapshot
from .postgres import pack, unpack
from .research import label, method_policy
from .research_fixture_v2 import bundle, binding, catalogue, START_NS, STEP_NS, PERIOD
from .workspace import display_candles, TIMEFRAMES
from .journal import request as note_request, note_text, note_tags, MAX_JOURNAL_ORDERS
from .analysis import metrics, ratio

META_FIELDS="id name methodId methodHash symbol engineVersion datasetId datasetVersion profileHash startPeriod initialBalance"
REVIEW_FIELDS="requestHash id sessionId methodHash profileHash revision throughNs basisCheckpointHash command estimate"
FINANCIAL_FIELDS=("entry","quantity","sl","tp","riskPercent")

def checked_review(row,state):
    value=unpack(row[0],row[1]);tag(value,"BTL-ORDER-REVIEW-2",REVIEW_FIELDS)
    revision(value["revision"]);digest(value["requestHash"],"requestHash")
    cmd=command_wire(value["command"]);p=state["profile"];payload=cmd["payload"]
    require(cmd["kind"]=="OPEN" and value["id"]==cmd["commandId"] and value["sessionId"]==cmd["sessionId"]==state["sessionId"]
            and value["revision"]==cmd["expectedRevision"]==row[2] and row[2]<=state["revision"]
            and value["basisCheckpointHash"]==row[3]==row[5] and content_hash(cmd)==row[4]
            and value["methodHash"]==state["policy"]["definitionHash"] and value["profileHash"]==state["profileHash"]
            and uint(value["throughNs"])<=int(state["throughNs"]),"review","CORRUPT_RECORD")
    digest(value["basisCheckpointHash"],"checkpoint")
    estimate=value["estimate"];keys(estimate,"entry quantity sl tp riskPercent risk")
    require(all(estimate[k]==payload[k] for k in FINANCIAL_FIELDS),"estimate","CORRUPT_RECORD")
    for k in FINANCIAL_FIELDS:
        if payload[k] is not None:require(type(payload[k]) is str and text(exact(payload[k],k))==payload[k],k,"CORRUPT_RECORD")
    entry=price(payload["entry"],p);quantity(payload["quantity"],p)
    require(payload["side"] in ("LONG","SHORT") and payload["orderType"] in ("MARKET","LIMIT","STOP")
            and payload["workflow"] in ("QUICK","PLANNED") and (payload["workflow"]!="QUICK" or payload["orderType"]=="MARKET"),"order")
    direction=1 if payload["side"]=="LONG" else -1
    for k in ("sl","tp"):
        if payload[k] is not None:price(payload[k],p)
    require((payload["sl"] is None or direction*(entry-Fraction(payload["sl"]))>0)
            and (payload["tp"] is None or direction*(Fraction(payload["tp"])-entry)>0),"geometry")
    require(payload["workflow"]!="PLANNED" or payload["sl"] is not None and payload["tp"] is not None,"planned")
    require(0<exact(payload["riskPercent"],"risk")<=100,"risk")
    policy=policy_from_wire(state["policy"]);outcomes={}
    require(type(payload["observations"]) is list and len(payload["observations"])<=64,"observations")
    for item in payload["observations"]:
        keys(item,"conditionId outcome");o=Observation(item["conditionId"],item["outcome"])
        require(o.condition_id in policy.conditions and o.condition_id not in outcomes,"observations");outcomes[o.condition_id]=o.outcome
    risk=estimate["risk"]
    require((risk is None)==(payload["sl"] is None),"risk")
    if risk is not None:
        keys(risk,"timeNs recommendedQuantity requestedQuantity plannedRequestedLossUsdExact budgetUsd evidenceHash exceedsBudget")
        amount=fraction(risk["plannedRequestedLossUsdExact"]);budget=exact(risk["budgetUsd"],"budget",True)
        require(amount>0 and risk["timeNs"]==value["throughNs"] and risk["requestedQuantity"]==payload["quantity"]
                and type(risk["exceedsBudget"]) is bool and risk["exceedsBudget"]==(amount>budget),"risk")
        digest(risk["evidenceHash"],"riskHash")
        if risk["recommendedQuantity"] is not None:quantity(risk["recommendedQuantity"],p)
    if policy.kind=="PROTOCOL":
        require(payload["workflow"]=="PLANNED" and payload["orderType"] in ("LIMIT","STOP") and risk is not None
                and payload["quantity"]==risk["recommendedQuantity"] and Fraction(payload["riskPercent"])==Fraction(policy.risk_percent)
                and abs(Fraction(payload["tp"])-entry)==abs(entry-Fraction(payload["sl"]))*Fraction(policy.rr)
                and (not policy.checklist_on or all(outcomes.get(c)=="PASS" for c in policy.conditions)),"protocol")
    return value

def current_quote(groups):
    if not groups:return None
    group=groups[-1];rows=group["events"]
    if len({(r["bid"],r["ask"]) for r in rows})!=1:return None
    if any(r["quality"]["quote"]!="VALID" or r["quality"]["freshness"]!="CONFIRMED"
           or r["quality"]["gapBefore"] not in ("NONE","KNOWN_SESSION_CLOSED") or r["quality"]["duplicateOf"] is not None
           or r["quality"]["evidenceHash"] is None for r in rows):return None
    return deepcopy(rows[0])

class ResearchApplicationV2:
    def __init__(self,dsn,scope):
        require(type(scope) is TrustedScope,"scope","SCOPE_REQUIRED")
        self.dsn,self.scope=dsn,scope;self.store=PostgresExecutionStoreV2(dsn)
    def _catalog_lock(self,db):db.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",(self.scope.workspace_id,))
    def _method(self,db,mid):
        identifier(mid,"methodId")
        row=db.execute("SELECT payload,content_hash FROM btl.tick_methods WHERE workspace_id=%s AND method_id=%s",(self.scope.workspace_id,mid)).fetchone()
        require(row is not None,"method","RESOURCE_UNAVAILABLE")
        value=unpack(*row);method_policy(value);require(value["id"]==mid,"method","CORRUPT_RECORD");return value
    def create_method(self,raw):
        raw=deepcopy(raw);raw["name"]=label(raw.get("name"));policy=method_policy(raw)
        require(policy.kind!="FREE_STYLE" or not policy.conditions,"conditions")
        blob,sha=pack(raw)
        with connect(self.dsn) as db:
            self._catalog_lock(db)
            prior=db.execute("SELECT content_hash FROM btl.tick_methods WHERE workspace_id=%s AND method_id=%s",(self.scope.workspace_id,raw["id"])).fetchone()
            if prior:
                require(prior[0]==sha,"methodId","REFUSED_IDEMPOTENCY_CONFLICT");return self._method(db,raw["id"])
            require(db.execute("SELECT count(*) FROM btl.tick_methods WHERE workspace_id=%s",(self.scope.workspace_id,)).fetchone()[0]<128,"methods","REFUSED_CATALOG_LIMIT")
            db.execute("INSERT INTO btl.tick_methods VALUES (%s,%s,%s,%s)",(self.scope.workspace_id,raw["id"],blob,sha))
        return raw
    def _session(self,db,sid,*,lock=False):
        identifier(sid,"sessionId")
        row=db.execute("SELECT payload,content_hash,method_id FROM btl.tick_v2_research_sessions WHERE workspace_id=%s AND session_id=%s",(self.scope.workspace_id,sid)).fetchone()
        require(row is not None,"session","RESOURCE_UNAVAILABLE")
        meta=unpack(row[0],row[1]);tag(meta,"BTL-RESEARCH-SESSION-2",META_FIELDS)
        require(meta["id"]==sid and meta["methodId"]==row[2],"metadata","CORRUPT_RECORD")
        method=self._method(db,meta["methodId"]);policy=method_policy(method)
        row=db.execute("SELECT payload,content_hash,revision,dataset_version,profile_hash FROM btl.tick_sessions WHERE workspace_id=%s AND session_id=%s"+(" FOR UPDATE" if lock else ""),(self.scope.workspace_id,sid)).fetchone()
        require(row is not None,"state","CORRUPT_RECORD")
        stored=read_snapshot(row[0],row[1]);state=stored["state"]
        require((state["revision"],state["datasetVersion"],state["profileHash"])==tuple(row[2:])
                and all(meta[k]==state[k] for k in ("engineVersion","datasetId","datasetVersion","profileHash","initialBalance"))
                and meta["symbol"]==state["profile"]["symbol"] and meta["methodHash"]==policy.definition_hash
                and state["policy"]==policy_wire(policy) and state["sessionId"]==sid and meta["startPeriod"]==PERIOD,"identity","CORRUPT_RECORD")
        label(meta["name"])
        return meta,method,state,stored["controller"]
    def create_session(self,raw):
        keys(raw,"id name methodId initialBalance startPeriod symbol");identifier(raw["id"],"sessionId")
        normalized={**raw,"name":label(raw["name"])}
        require(raw["startPeriod"]==PERIOD,"period","REFUSED_FIXTURE_PERIOD")
        require(type(raw["initialBalance"]) is str and text(exact(raw["initialBalance"],"balance",True))==raw["initialBalance"]
                and money(Fraction(raw["initialBalance"]),2)==raw["initialBalance"],"initialBalance","REFUSED_MONEY_PRECISION")
        b=bundle(raw["symbol"])
        def prior(db):
            row=db.execute("SELECT 1 FROM btl.tick_v2_research_sessions WHERE workspace_id=%s AND session_id=%s",(self.scope.workspace_id,raw["id"])).fetchone()
            if not row:return None
            meta=self._session(db,raw["id"])[0]
            require(all(meta[k]==normalized[k] for k in normalized),"sessionId","REFUSED_IDEMPOTENCY_CONFLICT")
            return meta
        with connect(self.dsn) as db:
            old=prior(db)
            if old:return old
            policy=method_policy(self._method(db,raw["methodId"]))
        source=SourceJoinV2(b.profile,b.primary,start_ns=str(START_NS),conversion_provider=b.conversion)
        cp=source.checkpoint();state=seed_state(raw["id"],b.profile,policy,cp,raw["initialBalance"])
        meta=dict(schemaVersion=1,artifact="BTL-RESEARCH-SESSION-2",**normalized,engineVersion=ENGINE_VERSION,methodHash=policy.definition_hash,
                  datasetId=state["datasetId"],datasetVersion=state["datasetVersion"],profileHash=state["profileHash"])
        blob,sha=pack(meta)
        try:
            with connect(self.dsn) as db:
                self._catalog_lock(db);old=prior(db)
                if old:return old
                require(method_policy(self._method(db,raw["methodId"])).definition_hash==policy.definition_hash,"method")
                require(db.execute("SELECT count(*) FROM btl.tick_v2_research_sessions WHERE workspace_id=%s",(self.scope.workspace_id,)).fetchone()[0]<128,"sessions","REFUSED_CATALOG_LIMIT")
                self.store._insert(db,self.scope,state,cp)
                db.execute("INSERT INTO btl.tick_v2_research_sessions VALUES (%s,%s,%s,%s,%s)",(self.scope.workspace_id,raw["id"],raw["methodId"],blob,sha))
        except psycopg.errors.UniqueViolation as error:
            raise ContractError("REFUSED_SESSION_IDENTITY_CONFLICT","session") from error
        return meta
    def catalog(self):
        with connect(self.dsn) as db:
            db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            rows=db.execute("SELECT payload,content_hash FROM btl.tick_methods WHERE workspace_id=%s ORDER BY method_id LIMIT 129",(self.scope.workspace_id,)).fetchall()
            require(len(rows)<=128,"methods","REFUSED_CATALOG_LIMIT")
            methods=[unpack(*r) for r in rows]
            for m in methods:method_policy(m)
            rows=db.execute("SELECT session_id FROM btl.tick_v2_research_sessions WHERE workspace_id=%s ORDER BY session_id LIMIT 129",(self.scope.workspace_id,)).fetchall()
            require(len(rows)<=128,"sessions","REFUSED_CATALOG_LIMIT")
            sessions=[self._session(db,r[0])[0] for r in rows]
        return dict(schemaVersion=1,artifact="BTL-RESEARCH-CATALOG-2",methods=methods,sessions=sessions,instruments=catalogue(),label="SHORT SYNTHETIC DEMOS ONLY; NO ACQUIRED HISTORICAL MONTH")
    def _review(self,db,sid,rid,state):
        identifier(rid,"reviewId")
        row=db.execute("SELECT r.payload,r.content_hash,r.basis_revision,r.basis_checkpoint_hash,r.command_hash,p.content_hash FROM btl.tick_v2_order_reviews r JOIN btl.tick_checkpoints p ON p.workspace_id=r.workspace_id AND p.session_id=r.session_id AND p.revision=r.basis_revision WHERE r.workspace_id=%s AND r.session_id=%s AND r.review_id=%s",(self.scope.workspace_id,sid,rid)).fetchone()
        return None if row is None else checked_review(row,state)
    def review(self,sid,raw):
        keys(raw,"id expectedRevision payload")
        cmd=command_wire(dict(schemaVersion=1,artifact="BTL-TICK-EXECUTION-COMMAND-2",sessionId=sid,commandId=raw["id"],expectedRevision=raw["expectedRevision"],kind="OPEN",payload=raw["payload"]))
        request_hash=content_hash(dict(schemaVersion=1,artifact="BTL-ORDER-REVIEW-REQUEST-2",sessionId=sid,request=raw))
        with connect(self.dsn) as db:
            meta,method,state,cp=self._session(db,sid)
            old=self._review(db,sid,raw["id"],state)
            if old:
                require(old["requestHash"]==request_hash,"reviewId","REFUSED_IDEMPOTENCY_CONFLICT");return old
        stored,receipt=self.store.prepare(self.scope,cmd)
        require(receipt is None,"review","REFUSED_REVIEW_AFTER_CONFIRMATION")
        state,cp=stored["state"],stored["controller"];b=binding(state["profile"])
        source=SourceJoinV2.resume(b.profile,b.primary,cp,conversion_provider=b.conversion)
        quote=current_quote(source.past_primary(source.checkpoint()))
        require(quote is not None,"quote","REFUSED_REVIEW_QUOTE")
        basis=source.risk_basis(source.checkpoint());payload=deepcopy(cmd["payload"]);policy=policy_from_wire(state["policy"])
        require(all(v is None or type(v) is str for v in (payload[k] for k in FINANCIAL_FIELDS)),"financialStrings")
        if payload["orderType"]=="MARKET":
            require(payload["side"] in ("LONG","SHORT"),"side")
            payload["entry"]=quote["ask"] if payload["side"]=="LONG" else quote["bid"]
        if policy.kind=="PROTOCOL":
            entry,stop=price(payload["entry"],state["profile"]),price(payload["sl"],state["profile"])
            target=entry+(entry-stop)*Fraction(policy.rr)
            require(payload["tp"] is None or Fraction(payload["tp"])==target,"tp","PROTOCOL_BLOCKED")
            require(payload["riskPercent"] is None or Fraction(payload["riskPercent"])==Fraction(policy.risk_percent),"risk","PROTOCOL_BLOCKED")
            payload.update(tp=text(target),riskPercent=policy.risk_percent)
            require(type(payload["observations"]) is list and len(payload["observations"])<=64,"observations")
            outcomes={}
            for item in payload["observations"]:
                keys(item,"conditionId outcome");o=Observation(item["conditionId"],item["outcome"])
                require(o.condition_id in policy.conditions and o.condition_id not in outcomes,"observations");outcomes[o.condition_id]=o.outcome
            payload["observations"]=[dict(conditionId=c,outcome=outcomes.get(c,"NOT_ASSESSED")) for c in policy.conditions]
        if payload["quantity"] is None:
            p=b.profile.wire;budget=Fraction(state["balance"])*exact(payload["riskPercent"],"risk",True)/100
            payload["quantity"]=planned_risk(b.profile,payload["side"],payload["entry"],payload["sl"],text(budget),state["throughNs"],conversion_group=basis["conversionGroup"])["quantity"]
        for k in FINANCIAL_FIELDS:
            if payload[k] is not None:payload[k]=text(exact(payload[k],k))
        cmd["payload"]=payload
        proposed,_=submit(state,cmd,basis);order=proposed["orders"][cmd["commandId"]]
        value=dict(schemaVersion=1,artifact="BTL-ORDER-REVIEW-2",requestHash=request_hash,id=cmd["commandId"],sessionId=sid,
                   methodHash=state["policy"]["definitionHash"],profileHash=state["profileHash"],revision=state["revision"],throughNs=state["throughNs"],
                   basisCheckpointHash=content_hash(stored),command=cmd,estimate={k:deepcopy(order[k]) for k in (*FINANCIAL_FIELDS,"risk")})
        blob,sha=pack(value);require(len(blob)<=32768,"review","REFUSED_REVIEW_LIMIT")
        with connect(self.dsn) as db:
            live=self._session(db,sid,lock=True)[2];old=self._review(db,sid,raw["id"],live)
            if old:
                require(old["requestHash"]==request_hash,"reviewId","REFUSED_IDEMPOTENCY_CONFLICT");return old
            require(content_hash(live)==content_hash(state),"review","REFUSED_STALE_REVISION")
            require(db.execute("SELECT count(*) FROM btl.tick_v2_order_reviews WHERE workspace_id=%s AND session_id=%s",(self.scope.workspace_id,sid)).fetchone()[0]<128,"reviews","REFUSED_REVIEW_LIMIT")
            db.execute("INSERT INTO btl.tick_v2_order_reviews VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",(self.scope.workspace_id,sid,value["id"],value["revision"],value["basisCheckpointHash"],content_hash(cmd),blob,sha))
        return value
    def _controller(self,state):
        b=binding(state["profile"]);return ExecutionControllerV2(self.store,b.profile,b.primary,conversion_provider=b.conversion)
    def confirm(self,sid,raw):
        keys(raw,"reviewId reviewHash");digest(raw["reviewHash"],"reviewHash")
        with connect(self.dsn) as db:
            state=self._session(db,sid)[2];review=self._review(db,sid,raw["reviewId"],state)
        require(review is not None,"review","RESOURCE_UNAVAILABLE")
        require(content_hash(review)==raw["reviewHash"],"review","REFUSED_REVIEW_HASH")
        def check(proposed):
            require(proposed["orders"][review["id"]]["risk"]==review["estimate"]["risk"],"review","REFUSED_REVIEW_RISK_DRIFT")
        # Dedup precedes even source registry binding; old receipts survive outage.
        _,prior=self.store.prepare(self.scope,review["command"])
        if prior is not None:return prior
        # A retry is the original receipt; fetch inspect separately for current view.
        return self._controller(state).apply(self.scope,review["command"],proposal_check=check)
    def apply(self,sid,raw):
        cmd=command_wire(raw)
        require(cmd["sessionId"]==sid and cmd["kind"] in ("ADVANCE","CANCEL","CLOSE","END"),"command","REFUSED_PRODUCT_COMMAND")
        with connect(self.dsn) as db:state=self._session(db,sid)[2]
        _,prior=self.store.prepare(self.scope,cmd)
        if prior is not None:return prior
        if cmd["kind"]!="ADVANCE":
            from .profile_v2 import ExecutionProfileV2
            return ExecutionControllerV2(self.store,ExecutionProfileV2.from_wire(state["profile"]),None).apply(self.scope,cmd)
        return self._controller(state).apply(self.scope,cmd)
    def _statistics(self,db,sid,state):
        result,actual=self.store._statistics(db,self.scope,sid)
        require(actual==state,"statistics","CORRUPT_RECORD")
        if result["status"]!="COMPLETE":return result
        completed={r["id"]:r for r in result["completed"]}
        if completed:
            rows=db.execute("SELECT r.payload,r.content_hash,r.basis_revision,r.basis_checkpoint_hash,r.command_hash,p.content_hash FROM btl.tick_v2_order_reviews r JOIN btl.tick_checkpoints p ON p.workspace_id=r.workspace_id AND p.session_id=r.session_id AND p.revision=r.basis_revision JOIN btl.tick_commands c ON c.workspace_id=r.workspace_id AND c.session_id=r.session_id AND c.command_id=r.review_id AND c.command_hash=r.command_hash AND c.revision=r.basis_revision+1 WHERE r.workspace_id=%s AND r.session_id=%s AND r.review_id=ANY(%s) AND c.revision<=%s LIMIT 129",(self.scope.workspace_id,sid,list(completed),state["revision"])).fetchall()
            require(len(rows)<=128,"reviews","REFUSED_REVIEW_LIMIT")
            for row in rows:
                review=checked_review(row,state);order=state["orders"][review["id"]];risk=review["estimate"]["risk"]
                require(all(order[k]==v for k,v in review["command"]["payload"].items()) and order["risk"]==risk
                        and order["availableNs"]==review["throughNs"],"confirmedRisk","CORRUPT_RECORD")
                if risk is not None:
                    target=completed[review["id"]];target["rMultiple"]=ratio(Fraction(target["net"])/fraction(risk["plannedRequestedLossUsdExact"]));target["rReason"]=None
            values=[fraction(r["rMultiple"]) for r in result["completed"] if r["rMultiple"] is not None]
            result["metrics"].update(metrics(result["completed"]))
            result["metrics"].update(totalR=ratio(sum(values,Fraction(0))) if values else None,rReason=None if values else "CONFIRMED_R0_NOT_JOINED")
        return result
    def statistics(self,sid):
        with connect(self.dsn) as db:
            db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            state=self._session(db,sid)[2];return self._statistics(db,sid,state)
    def inspect(self,sid,timeframe="1m"):
        require(type(timeframe) is str and timeframe in TIMEFRAMES,"timeframe")
        with connect(self.dsn) as db:
            db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            meta,method,state,cp=self._session(db,sid);start=max(0,state["nextEventIndex"]-64)
            rows=db.execute("SELECT payload,content_hash FROM btl.tick_events WHERE workspace_id=%s AND session_id=%s AND sequence >= %s AND sequence < %s ORDER BY sequence LIMIT 64",(self.scope.workspace_id,sid,start,state["nextEventIndex"])).fetchall()
            view=dict(schemaVersion=1,artifact="BTL-RESEARCH-SESSION-VIEW-2",metadata=meta,method=method,state=state,events=[unpack(*r) for r in rows],eventWindowStart=start,
                      analysis=self._statistics(db,sid,state),quote=None,chart=None,displayStatus="UNAVAILABLE",label="SHORT SYNTHETIC DEMO; NOT HISTORICAL MARKET DATA",replayStepNs=str(STEP_NS))
        try:
            b=binding(state["profile"]);source=SourceJoinV2.resume(b.profile,b.primary,cp,conversion_provider=b.conversion)
            groups=source.past_primary(source.checkpoint());view.update(quote=current_quote(groups),chart=display_candles(groups,state["throughNs"],timeframe,max(0,int(state["nextGroupIndex"])-len(groups))),displayStatus="REVEALED_PREFIX")
        except Exception:
            # Isolate optional display failure from durable financial evidence.
            view["displayStatus"]="SOURCE_DISPLAY_UNAVAILABLE"
        canonical_bytes(view);return view
    def _note(self,value,state,oid):
        tag(value,"BTL-JOURNAL-NOTE-2","sessionId datasetId datasetVersion profileHash orderId noteRevision text tags")
        require(value["orderId"]==oid and oid in state["orders"] and all(value[k]==state[k] for k in ("sessionId","datasetId","datasetVersion","profileHash")),"note","CORRUPT_RECORD")
        revision(value["noteRevision"]);require(value["noteRevision"]>0,"noteRevision");note_text(value["text"]);note_tags(value["tags"]);return value
    def journal(self,sid):
        with connect(self.dsn) as db:
            db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            state=self._session(db,sid)[2]
            rows=db.execute("SELECT order_id,note_revision,payload,content_hash FROM btl.tick_v2_journal_notes WHERE workspace_id=%s AND session_id=%s ORDER BY order_id LIMIT 33",(self.scope.workspace_id,sid)).fetchall()
            require(len(rows)<=MAX_JOURNAL_ORDERS,"notes","REFUSED_JOURNAL_LIMIT");notes=[]
            for row in rows:
                value=self._note(unpack(row[2],row[3]),state,row[0]);require(value["noteRevision"]==row[1],"note","CORRUPT_RECORD");notes.append(value)
        return dict(schemaVersion=1,artifact="BTL-JOURNAL-2",sessionId=sid,revision=state["revision"],notes=notes)
    def edit_note(self,sid,raw):
        request=note_request(raw)
        with connect(self.dsn) as db:
            self._catalog_lock(db);state=self._session(db,sid,lock=True)[2];oid=request["orderId"]
            require(oid in state["orders"],"order","RESOURCE_UNAVAILABLE")
            row=db.execute("SELECT note_revision,payload,content_hash FROM btl.tick_v2_journal_notes WHERE workspace_id=%s AND session_id=%s AND order_id=%s FOR UPDATE",(self.scope.workspace_id,sid,oid)).fetchone()
            if row:
                old=self._note(unpack(row[1],row[2]),state,oid);require(old["noteRevision"]==row[0],"note","CORRUPT_RECORD")
            current=0 if row is None else row[0]
            if row and current==request["expectedNoteRevision"]+1 and old["text"]==request["text"] and old["tags"]==request["tags"]:return old
            require(current==request["expectedNoteRevision"],"noteRevision","REFUSED_STALE_NOTE")
            if row is None:require(db.execute("SELECT count(*) FROM btl.tick_v2_journal_notes WHERE workspace_id=%s AND session_id=%s",(self.scope.workspace_id,sid)).fetchone()[0]<MAX_JOURNAL_ORDERS,"notes","REFUSED_JOURNAL_LIMIT")
            value=dict(schemaVersion=1,artifact="BTL-JOURNAL-NOTE-2",**{k:state[k] for k in ("sessionId","datasetId","datasetVersion","profileHash")},orderId=oid,noteRevision=current+1,text=request["text"],tags=deepcopy(request["tags"]))
            blob,sha=pack(value)
            if row is None:db.execute("INSERT INTO btl.tick_v2_journal_notes VALUES (%s,%s,%s,%s,%s,%s)",(self.scope.workspace_id,sid,oid,current+1,blob,sha))
            else:db.execute("UPDATE btl.tick_v2_journal_notes SET note_revision=%s,payload=%s,content_hash=%s WHERE workspace_id=%s AND session_id=%s AND order_id=%s",(current+1,blob,sha,self.scope.workspace_id,sid,oid))
        return value

def grant_research_v2_runtime(dsn,role):
    from .postgres import grant_execution_runtime
    grant_execution_runtime(dsn,role)
    with connect(dsn) as db:
        db.execute(sql.SQL("GRANT SELECT,INSERT ON btl.tick_methods,btl.tick_v2_research_sessions,btl.tick_v2_order_reviews TO {}").format(sql.Identifier(role)))
        db.execute(sql.SQL("GRANT SELECT,INSERT,UPDATE ON btl.tick_v2_journal_notes TO {}").format(sql.Identifier(role)))
