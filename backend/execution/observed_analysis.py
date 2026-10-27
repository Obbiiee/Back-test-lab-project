"""Read-only bounded-memory observed ledger fold; no source/quote/settlement access."""
from collections import deque
from copy import deepcopy
from fractions import Fraction
from contracts.canonical import content_hash
from contracts.primitives import require
from ticks.contracts import uint
from execution.contracts import open_payload,policy_from_wire,text
from execution.engine import protective
from execution.observed_profile import ObservedExecutionProfile,MODEL
from execution.observed_finance import exit_amount
from execution.observed_kernel import validate_state
from execution.analysis import metrics as committed_metrics
from execution.observed_postgres import check_events
from collections import OrderedDict
from threading import RLock
from infrastructure.database import connect
from execution.postgres import scoped,unpack
from execution.observed_postgres import read_snapshot


def ratio(v):return dict(numerator=str(v.numerator),denominator=str(v.denominator))


class LedgerFold:
    """At most128orders and256cash curve points, regardless of replay history."""
    def __init__(self,genesis):
        validate_state(genesis);require(genesis['revision']==0 and genesis['nextEventIndex']==0 and genesis['orders']=={} and genesis['balance']==genesis['initialBalance'] and not genesis['unresolved'] and not genesis['ended'],'genesis','CORRUPT_RECORD')
        seed=dict(schemaVersion=1,artifact='BTL-OBSERVED-EXECUTION-SEED-1',sessionId=genesis['sessionId'],profileHash=genesis['profileHash'],policy=genesis['policy'],startNs=genesis['startNs'],initialBalance=genesis['initialBalance'])
        require(content_hash(seed)==genesis['eventHash'],'genesisHash','CORRUPT_RECORD')
        self.genesis=deepcopy(genesis);self.profile=ObservedExecutionProfile.from_wire(genesis['profile']);self.next=0;self.head=genesis['eventHash'];self.orders={};self.entry_times={};self.exit_times={};self.exact_gross={};self.exit_counts={};self.exit_sequences={}
        self.balance=self.peak=Fraction(genesis['initialBalance']);self.gross=self.max_dd=self.max_dd_rate=Fraction(0);self.curve=deque(maxlen=256);self.financial_count=0;self.unresolved=False;self.ended=False;self.last_fill=int(genesis['startNs'])

    def consume(self,e):
        next_,head=check_events([e],self.genesis,self.next,self.head);kind=e['kind'];oid=e['orderId'];d=e['detail'];p=self.profile.wire
        if kind in ('ENTRY_FILL','EXIT_FILL','ORDER_CANCELLED','EXPIRED_NO_QUOTE','EXIT_REQUESTED'):require(oid in self.orders,'order','CORRUPT_RECORD')
        if kind=='ORDER_ACCEPTED':
            require(oid not in self.orders,'order','CORRUPT_RECORD');plan=deepcopy(d['plan']);require(open_payload(plan,p,policy_from_wire(self.genesis['policy']),d['riskBalance'])==plan,'plan','CORRUPT_RECORD')
            self.orders[oid]=dict(plan,status='PENDING',availableNs=d['availableNs'],remaining=plan['quantity'],entryPrice=None,entryFillRef=None,entryCost='0',exitRequest=None,grossPosted='0',riskBalance=d['riskBalance'],riskBasisHash=d['riskBasisHash'])
        elif kind in ('ORDER_CANCELLED','EXPIRED_NO_QUOTE'):
            o=self.orders[oid];require(o['status']=='PENDING','order','CORRUPT_RECORD');o['status']='CANCELLED' if kind=='ORDER_CANCELLED' else 'EXPIRED'
        elif kind=='EXIT_REQUESTED':
            o=self.orders[oid];require(o['status']=='ACTIVE' and o['exitRequest'] is None,'exit','CORRUPT_RECORD');o['exitRequest']=dict(quantity=d['quantity'],availableNs=d['availableNs'])
        elif kind=='UNRESOLVED':
            for key in d['affectedOrderIds']:
                require(key in self.orders,'order','CORRUPT_RECORD');o=self.orders[key];require(o['status'] in ('PENDING','ACTIVE'),'unresolved','CORRUPT_RECORD');o.update(status='UNRESOLVED',exitRequest=None);self.unresolved=True
        elif kind=='SESSION_ENDED':self.ended=True
        if kind in ('ENTRY_FILL','EXIT_FILL'):
            o=self.orders[oid];evidence=d['evidence'];moment=uint(evidence['timeNs']);require(self.last_fill<=moment and int(o['availableNs'])<=moment and d['commission']=='0','fill','CORRUPT_RECORD');self.last_fill=moment
            expected_side='ask' if (o['side']=='LONG')==(kind=='ENTRY_FILL') else 'bid';require(d['price']==evidence[expected_side],'side','CORRUPT_RECORD')
            if kind=='ENTRY_FILL':
                require(o['status']=='PENDING' and d['quantity']==o['quantity'] and d['balanceDelta']=='0','entry','CORRUPT_RECORD');o.update(status='ACTIVE',entryPrice=d['price'],entryFillRef=e['eventId']);self.entry_times[oid]=moment
            else:
                size=Fraction(d['quantity']);remaining=Fraction(o['remaining'])-size
                require(o['status']=='ACTIVE' and 0<size<=Fraction(o['remaining']) and remaining==Fraction(d['remaining']) and d['entryFillRef']==o['entryFillRef'],'exit','CORRUPT_RECORD')
                amount=exit_amount(self.profile,side=o['side'],entry_price=o['entryPrice'],exit_price=d['price'],lots=d['quantity'])
                require(amount['grossExact']==d['grossExact'] and amount['grossPosted']==d['grossPosted']==d['balanceDelta'],'cash','CORRUPT_RECORD')
                if d['reason']=='MANUAL':
                    request=o['exitRequest'];require(protective(o,dict(bid=evidence['bid'],ask=evidence['ask'])) is None and request is not None and request['quantity']==d['quantity'] and int(request['availableNs'])<=moment,'exitRequest','CORRUPT_RECORD')
                else:require(d['reason']==protective(o,dict(bid=evidence['bid'],ask=evidence['ask'])) and size==Fraction(o['remaining']),'protection','CORRUPT_RECORD')
                posted=Fraction(d['grossPosted']);self.balance+=posted;self.gross+=posted;self.exact_gross[oid]=self.exact_gross.get(oid,Fraction(0))+Fraction(d['grossExact']);self.exit_counts[oid]=self.exit_counts.get(oid,0)+1
                o.update(remaining=d['remaining'],status='CLOSED' if remaining==0 else 'ACTIVE',exitRequest=None,grossPosted=text(Fraction(o['grossPosted'])+posted));self.exit_times[oid]=moment;self.exit_sequences[oid]=e['sequence']
            self.financial_count+=1;self.peak=max(self.peak,self.balance);dd=self.peak-self.balance;self.max_dd=max(self.max_dd,dd);self.max_dd_rate=max(self.max_dd_rate,dd/self.peak)
            self.curve.append(dict(sequence=e['sequence'],eventId=e['eventId'],orderId=oid,timeNs=str(moment),balance=text(self.balance),drawdown=text(dd)))
        self.next,self.head=next_,head

    def project(self,state,offset=0,maximum=64):
        validate_state(state);require(all(state[k]==self.genesis[k] for k in ('sessionId','datasetId','datasetVersion','profileHash','profile','policy','initialBalance','startNs','parent')),'context','CORRUPT_RECORD')
        require(self.next==state['nextEventIndex'] and self.head==state['eventHash'] and self.orders==state['orders'] and self.balance==Fraction(state['balance']) and self.gross==Fraction(state['realizedGross']) and self.unresolved==state['unresolved'] and self.ended==state['ended'] and state['financial'] is (self.financial_count>0) and self.last_fill<=int(state['throughNs']),'ledgerHead','CORRUPT_RECORD')
        rows=[]
        for oid,o in sorted(self.orders.items(),key=lambda pair:self.exit_sequences.get(pair[0],-1)):
            if o['status']!='CLOSED':continue
            # Frozen research owner requires immutable PRE-ENTRY confirmation
            # R0; actual-entry geometry is not a retrospective substitute.
            r=None;reason='PREENTRY_REVIEW_RISK_NOT_JOINED'
            rows.append(dict(id=oid,side=o['side'],entryTimeNs=str(self.entry_times[oid]),exitTimeNs=str(self.exit_times[oid]),entryPrice=o['entryPrice'],quantity=o['quantity'],exitFills=self.exit_counts[oid],netPosted=o['grossPosted'],grossExact=text(self.exact_gross[oid]),rMultiple=None if r is None else ratio(r),rReason=reason,durationNs=str(self.exit_times[oid]-self.entry_times[oid])))
        require(type(offset) is int and 0<=offset<=len(rows) and type(maximum) is int and 1<=maximum<=64,'pagination')
        total=len(rows);page=rows[offset:offset+maximum]
        # Reuse the frozen pure calculator, including signed average loss,
        # BE streak reset, duration and null-denominator semantics.
        metrics=committed_metrics([dict(row,net=row['netPosted']) for row in rows])
        metrics.update(closed=total,profitFactorReason='NO_REALIZED_LOSSES' if metrics['profitFactor'] is None else None,realizedNetCompleted=text(sum((Fraction(r['netPosted']) for r in rows),Fraction(0))),unresolved=sum(o['status']=='UNRESOLVED' for o in self.orders.values()),expired=sum(o['status']=='EXPIRED' for o in self.orders.values()),cancelled=sum(o['status']=='CANCELLED' for o in self.orders.values()),totalR=None,rAvailable=0,rReason='INCOMPLETE_R_COVERAGE',rBasis='IMMUTABLE_PREENTRY_CONFIRMED_RISK_REQUIRED',maxDrawdown=text(self.max_dd),maxDrawdownRate=ratio(self.max_dd_rate),unrealizedExcluded=True)
        return dict(schemaVersion=1,artifact='BTL-OBSERVED-COMMITTED-STATISTICS-1',status='COMPLETE',provenance=dict(sessionId=state['sessionId'],revision=state['revision'],engineVersion=state['engineVersion'],model=MODEL,datasetId=state['datasetId'],datasetVersion=state['datasetVersion'],profileHash=state['profileHash'],methodHash=state['policy']['definitionHash'],eventHead=state['eventHash']),metrics=metrics,completed=page,nextTradeOffset=offset+len(page) if offset+len(page)<total else None,account=dict(currency='USD',initialBalance=state['initialBalance'],balance=state['balance'],realizedGross=state['realizedGross'],commission='0'),balanceCurve=list(self.curve),curveWindowStart=max(0,self.financial_count-256),markToMarketAvailable=False)


class ObservedStatistics:
    """Source-free, bounded incremental projection of immutable SQL evidence.

    One call consumes at most 1024 events; BUILDING has no partial financial
    metrics. A 64-session LRU bounds memory without imposing a lifetime event
    ceiling. Eviction merely rebuilds from SQL. Lock precedes opening the read
    snapshot, so a cached fold cannot come from a newer concurrent snapshot.
    This first implementation serializes projection calls, not trading writes.
    """
    def __init__(self,store):
        self.store=store;self._folds=OrderedDict();self._lock=RLock()

    def inspect(self,scope,session_id,offset=0,maximum=64):
        workspace,session=scoped(scope,session_id)
        require(type(offset) is int and 0<=offset<=128 and type(maximum) is int and 1<=maximum<=64,'pagination')
        with self._lock,connect(self.store.dsn) as db:
            db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            state=self.store._read(db,workspace,session)['state']
            seed=db.execute('SELECT payload,content_hash FROM btl.tick_checkpoints WHERE workspace_id=%s AND session_id=%s AND revision=0',(workspace,session)).fetchone()
            require(seed is not None,'genesis','CORRUPT_RECORD');genesis=read_snapshot(*seed)['state']
            key=(workspace,session,content_hash(genesis));prior=self._folds.get(key)
            fold=deepcopy(prior) if prior is not None else LedgerFold(genesis)
            require(fold.next<=state['nextEventIndex'],'eventRegression','CORRUPT_RECORD')
            for _ in range(16):
                if fold.next==state['nextEventIndex']:break
                rows=db.execute('SELECT payload,content_hash FROM btl.tick_events WHERE workspace_id=%s AND session_id=%s AND sequence>=%s AND sequence<%s ORDER BY sequence LIMIT 64',(workspace,session,fold.next,state['nextEventIndex'])).fetchall()
                require(len(rows)==min(64,state['nextEventIndex']-fold.next),'eventCount','CORRUPT_RECORD')
                for row in rows:fold.consume(unpack(*row))
            if fold.next==state['nextEventIndex']:
                result=fold.project(state,offset,maximum)
            else:
                result=dict(schemaVersion=1,artifact='BTL-OBSERVED-COMMITTED-STATISTICS-1',status='BUILDING',sessionId=session,revision=state['revision'],processedEvents=fold.next,totalEvents=state['nextEventIndex'],metrics=None,completed=[],nextTradeOffset=None)
            # Failed validation never replaces an accepted cached prefix.
            self._folds[key]=fold;self._folds.move_to_end(key)
            while len(self._folds)>64:self._folds.popitem(last=False)
            return result
