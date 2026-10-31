"""Pure conditional observed transitions. Only a durable controller publishes them.

No filesystem/provider/clock access and no candle inputs. Frozen strict engines
remain unchanged. Raw quote quality is inspected, never rewritten as confirmed.
"""
from copy import deepcopy
from fractions import Fraction

from contracts.canonical import canonical_bytes, content_hash
from contracts.models import validate_action
from contracts.primitives import ContractError, digest, identifier, require, revision
from ticks.contracts import CanonicalTick, event_id, keys, uint
from ticks.contracts_v2 import canonical_v2_bytes, hash_v2
from ticks.evidence_v2 import CODES
from ticks.provider import diagnostic_counts
from ticks.timeline import CURSOR_FIELDS, make_group
from ticks.timeline_v2 import VERSION as TIMELINE_VERSION
from .contracts import exact, money, open_payload, policy_from_wire, policy_wire, price, quantity, text
from .engine import crossing, protective, can_change
from .observed_profile import ENGINE_VERSION, MODEL, MODEL_V2, ObservedExecutionProfile
from .observed_finance import exit_amount
from .observed_order_archive_v1 import append as archive_append, advance as archive_advance, summary as archive_summary

MAX_EVENTS, MAX_ORDERS = 256, 128
MAX_ACTIVE_ORDERS = 128
QA_ORDER_RETENTION_V2 = dict(schemaVersion=1,artifact='BTL-QA-ORDER-RETENTION-2',scope='ISOLATED_QA_ONLY',
                            maxCumulativeOrders=512,maxActiveOrders=MAX_ACTIVE_ORDERS)
QA_ORDER_RETENTION_V3 = dict(schemaVersion=1,artifact='BTL-QA-ORDER-RETENTION-3',scope='ISOLATED_QA_ONLY',
                            maxCumulativeOrders=1024,maxActiveOrders=MAX_ACTIVE_ORDERS)
STATE_FIELDS = ('sessionId datasetId datasetVersion engineVersion model profile profileHash policy revision '
                'initialBalance balance realizedGross commission startNs throughNs nextGroupIndex nextEventIndex '
                'eventHash sourceCheckpointHash sourcePrefixHash sourceCursorRevision lastObservedNs quoteBasis orders unresolved ended financial parent')
STATE_FIELDS_QA_ARCHIVE_V1 = STATE_FIELDS+' orderArchive'
STATE_QA_ARCHIVE_V1 = 'BTL-OBSERVED-EXECUTION-STATE-QA-ORDER-ARCHIVE-1'
PLAN_FIELDS = 'side orderType workflow entry quantity sl tp riskPercent observations'
ORDER_FIELDS = PLAN_FIELDS+' status availableNs remaining entryPrice entryFillRef entryCost exitRequest grossPosted riskBalance riskBasisHash'


def _tag(raw, artifact, fields):
    keys(raw, 'schemaVersion artifact '+fields)
    require(type(raw['schemaVersion']) is int and raw['schemaVersion']==1 and raw['artifact']==artifact, 'artifact')


def order_limits(policy=None):
    if policy is None:return MAX_ORDERS,MAX_ORDERS
    keys(policy,'schemaVersion artifact scope maxCumulativeOrders maxActiveOrders')
    require(policy in (QA_ORDER_RETENTION_V2,QA_ORDER_RETENTION_V3) and policy['scope']=='ISOLATED_QA_ONLY',
            'orderRetention','REFUSED_POLICY')
    canonical_bytes(policy)
    return policy['maxCumulativeOrders'],policy['maxActiveOrders']


def _checkpoint(cp, profile):
    keys(cp, 'schemaVersion artifact cursor advanceLogHash positionLogHash')
    require(type(cp['schemaVersion']) is int and cp['schemaVersion']==2 and cp['artifact']=='BTL-TICK-CHECKPOINT-2', 'checkpoint')
    cursor=cp['cursor'];keys(cursor, 'schemaVersion artifact '+CURSOR_FIELDS)
    require(type(cursor['schemaVersion']) is int and cursor['schemaVersion']==2 and cursor['artifact']=='BTL-TICK-CURSOR-2'
            and cursor['timelineVersion']==TIMELINE_VERSION and cursor['generation']=='0', 'cursor')
    p=profile.wire['primary']
    require(cursor['datasetId']==p['datasetId'] and cursor['datasetVersion']==p['datasetVersion'], 'source', 'REFUSED_OBSERVED_SOURCE_IDENTITY')
    for f in ('generation','revision','sessionStartNs','throughNs','nextGroupIndex'):uint(cursor[f])
    require(int(cursor['sessionStartNs'])<=int(cursor['throughNs']), 'time')
    if cursor['pendingTargetNs'] is not None:require(uint(cursor['pendingTargetNs'])>=int(cursor['throughNs']), 'target')
    for h in (cursor['visiblePrefixHash'],):digest(h, 'digest')
    for h in (cursor['lastGroupId'],cp['advanceLogHash'],cp['positionLogHash']):
        if h is not None:digest(h, 'digest')
    canonical_v2_bytes(cp)
    return cursor


def validate_state(state,*,order_retention_policy=None):
    archive_v1=type(state) is dict and state.get('artifact')==STATE_QA_ARCHIVE_V1
    _tag(state,STATE_QA_ARCHIVE_V1 if archive_v1 else 'BTL-OBSERVED-EXECUTION-STATE-1',
         STATE_FIELDS_QA_ARCHIVE_V1 if archive_v1 else STATE_FIELDS)
    require(state['engineVersion']==ENGINE_VERSION and state['model']==ObservedExecutionProfile.from_wire(state['profile']).wire['model'],'model')
    profile=ObservedExecutionProfile.from_wire(state['profile']);p=profile.wire
    require(state['profileHash']==profile.profile_hash and all(state[k]==p['primary'][k] for k in ('datasetId','datasetVersion')),'profile','CORRUPT_RECORD')
    identifier(state['sessionId'], 'identifier');revision(state['revision']);revision(state['nextEventIndex'])
    for f in ('startNs','throughNs','nextGroupIndex','sourceCursorRevision'):uint(state[f])
    require(int(state['startNs'])<=int(state['throughNs']),'time')
    for f in ('eventHash','sourceCheckpointHash','sourcePrefixHash'):digest(state[f], 'digest')
    require(all(type(state[f]) is bool for f in ('unresolved','ended','financial')) and state['parent'] is None,'flags')
    policy=policy_from_wire(state['policy'])
    for f in ('initialBalance','balance','realizedGross','commission'):
        v=exact(state[f],f);require(type(state[f]) is str and text(v)==state[f] and (v*100).denominator==1,f,'CORRUPT_RECORD')
    require(exact(state['initialBalance'],'initial',True)>0 and state['commission']=='0','account')
    require(Fraction(state['balance'])==Fraction(state['initialBalance'])+Fraction(state['realizedGross']),'account','CORRUPT_RECORD')
    count=int(state['nextGroupIndex']);last=state['lastObservedNs'];basis=state['quoteBasis']
    require((last is None)==(count==0),'groupCount')
    if last is not None:require(int(state['startNs'])<=uint(last)<=int(state['throughNs']),'lastObserved')
    if basis is not None:
        keys(basis,'timeNs groupId bid ask eventIds chronologyLimited')
        require(last==basis['timeNs'] and type(basis['chronologyLimited']) is bool,'basis')
        digest(basis['groupId'], 'digest');require(type(basis['eventIds']) is list and 1<=len(basis['eventIds'])<=1024 and len(set(basis['eventIds']))==len(basis['eventIds']),'basis')
        for eid in basis['eventIds']:digest(eid, 'digest')
        require(price(basis['bid'],p)<=price(basis['ask'],p),'basis')
    max_cumulative,max_active=order_limits(order_retention_policy)
    require(archive_v1 or order_retention_policy!=QA_ORDER_RETENTION_V3,
            'orderRetention','REFUSED_POLICY')
    require(type(state['orders']) is dict,'orders','CORRUPT_RECORD')
    if archive_v1:
        keys(state['orderArchive'],'schemaVersion artifact count grossPosted headHash')
        require(order_retention_policy is not None and state['orderArchive']['artifact']=='BTL-QA-TERMINAL-ORDER-ARCHIVE-1-SUMMARY',
                'orderArchive','REFUSED_POLICY')
        require(state['orderArchive']['schemaVersion']==1 and type(state['orderArchive']['count']) is int
                and state['orderArchive']['count']>=0 and state['orderArchive']['count']+len(state['orders'])<=max_cumulative,
                'orderArchive','CORRUPT_RECORD')
        digest(state['orderArchive']['headHash'],'digest')
        archived_gross=exact(state['orderArchive']['grossPosted'],'archiveGrossPosted')
        require(text(archived_gross)==state['orderArchive']['grossPosted'],'orderArchive','CORRUPT_RECORD')
        require(len(state['orders'])<=max_active,'orders','REFUSED_ACTIVE_ORDER_LIMIT')
    else:
        require(len(state['orders'])<=max_cumulative,'orders','REFUSED_STATE_LIMIT')
    require(sum(type(o) is dict and o.get('status') in ('PENDING','ACTIVE') for o in state['orders'].values())<=max_active,
            'orders','REFUSED_ACTIVE_ORDER_LIMIT')
    total=Fraction(0)
    for oid,o in state['orders'].items():
        identifier(oid, 'identifier');keys(o,ORDER_FIELDS)
        original={f:o[f] for f in PLAN_FIELDS.split()}
        require(open_payload(original,p,policy,o['riskBalance'])==original,'order','CORRUPT_RECORD')
        exact(o['riskBalance'],'riskBalance',True);digest(o['riskBasisHash'], 'digest')
        require(int(state['startNs'])<=uint(o['availableNs'])<=int(state['throughNs']),'available')
        size=quantity(o['quantity'],p);remaining=exact(o['remaining'],'remaining')
        require(0<=remaining<=size and (remaining/exact(p['lotStep'],'step')).denominator==1,'remaining')
        require(o['status'] in ('PENDING','ACTIVE','CLOSED','CANCELLED','EXPIRED','UNRESOLVED') and o['entryCost']=='0','order')
        if archive_v1:require(o['status'] in ('PENDING','ACTIVE'),'hotOrder','CORRUPT_RECORD')
        if o['entryPrice'] is None:
            require(o['entryFillRef'] is None and remaining==size and o['grossPosted']=='0' and o['status']!='ACTIVE' and o['status']!='CLOSED','entry')
        else:
            price(o['entryPrice'],p);digest(o['entryFillRef'], 'digest');require(o['status'] in ('ACTIVE','CLOSED','UNRESOLVED'),'entry')
        require(o['status']!='CLOSED' or remaining==0,'closed')
        require(o['status']!='ACTIVE' or remaining>0,'active')
        posted=exact(o['grossPosted'],'grossPosted');require(text(posted)==o['grossPosted'] and (posted*100).denominator==1,'posted');total+=posted
        if o['exitRequest'] is not None:
            keys(o['exitRequest'],'quantity availableNs');require(o['status']=='ACTIVE' and 0<quantity(o['exitRequest']['quantity'],p)<=remaining,'exitRequest')
            require(int(o['availableNs'])<=uint(o['exitRequest']['availableNs'])<=int(state['throughNs']),'exitRequest')
    if archive_v1:total+=archived_gross
    require(total==Fraction(state['realizedGross']),'account','CORRUPT_RECORD')
    require(not state['unresolved'] or not _live(state),'unresolved')
    canonical_bytes(state)
    return state


def validate_snapshot(state,checkpoint,*,order_retention_policy=None):
    validate_state(state,order_retention_policy=order_retention_policy);c=_checkpoint(checkpoint,ObservedExecutionProfile.from_wire(state['profile']))
    require(hash_v2(checkpoint)==state['sourceCheckpointHash'] and c['visiblePrefixHash']==state['sourcePrefixHash'] and all(c[a]==state[b] for a,b in
            (('sessionStartNs','startNs'),('throughNs','throughNs'),('nextGroupIndex','nextGroupIndex'),('revision','sourceCursorRevision'))),'checkpoint','CORRUPT_RECORD')
    return dict(schemaVersion=1,artifact='BTL-OBSERVED-EXECUTION-CHECKPOINT-1',state=state,controller=checkpoint)


def seed_state(session_id,profile,policy,checkpoint,balance='10000',*,order_retention_policy=None,qa_order_archive_v1=False):
    require(type(profile) is ObservedExecutionProfile,'profile');identifier(session_id, 'identifier')
    c=_checkpoint(checkpoint,profile);require(c['nextGroupIndex']=='0' and c['revision']=='0' and c['throughNs']==c['sessionStartNs'],'initialCursor')
    initial=money(exact(balance,'balance',True),2);require(exact(initial,'initial',True)>0,'balance');p=profile.wire;policy=policy_wire(policy)
    genesis=dict(schemaVersion=1,artifact='BTL-OBSERVED-EXECUTION-SEED-1',sessionId=session_id,profileHash=profile.profile_hash,policy=policy,startNs=c['sessionStartNs'],initialBalance=initial)
    require(type(qa_order_archive_v1) is bool,'qaOrderArchive')
    state=dict(schemaVersion=1,artifact=STATE_QA_ARCHIVE_V1 if qa_order_archive_v1 else 'BTL-OBSERVED-EXECUTION-STATE-1',sessionId=session_id,datasetId=p['primary']['datasetId'],datasetVersion=p['primary']['datasetVersion'],engineVersion=ENGINE_VERSION,model=p['model'],profile=p,profileHash=profile.profile_hash,policy=policy,revision=0,initialBalance=initial,balance=initial,realizedGross='0',commission='0',startNs=c['sessionStartNs'],throughNs=c['throughNs'],nextGroupIndex='0',nextEventIndex=0,eventHash=content_hash(genesis),sourceCheckpointHash=hash_v2(checkpoint),sourcePrefixHash=c['visiblePrefixHash'],sourceCursorRevision='0',lastObservedNs=None,quoteBasis=None,orders={},unresolved=False,ended=False,financial=False,parent=None)
    if qa_order_archive_v1:state['orderArchive']=archive_summary()
    validate_snapshot(state,checkpoint,order_retention_policy=order_retention_policy);return state


def command_wire(raw):
    _tag(raw,'BTL-OBSERVED-EXECUTION-COMMAND-1','sessionId commandId expectedRevision kind payload')
    identifier(raw['sessionId'], 'identifier');identifier(raw['commandId'], 'identifier');revision(raw['expectedRevision'])
    fields={'OPEN':PLAN_FIELDS,'CANCEL':'orderId','CLOSE':'orderId quantity','ADVANCE':'targetNs','END':''}
    require(type(raw['kind']) is str and raw['kind'] in fields,'command','REFUSED_COMMAND');keys(raw['payload'],fields[raw['kind']])
    if raw['kind']=='ADVANCE':uint(raw['payload']['targetNs'])
    if raw['kind'] in ('CANCEL','CLOSE'):identifier(raw['payload']['orderId'], 'identifier')
    canonical_bytes(raw);return deepcopy(raw)


def emit(state,events,kind,*,order_id=None,classification='OBSERVED_FEED_EVENT',**detail):
    require(len(events)<MAX_EVENTS,'events','REFUSED_EVENT_LIMIT')
    e=dict(schemaVersion=1,artifact='BTL-OBSERVED-EXECUTION-EVENT-1',engineVersion=ENGINE_VERSION,model=state['model'],sessionId=state['sessionId'],datasetId=state['datasetId'],datasetVersion=state['datasetVersion'],profileHash=state['profileHash'],methodHash=state['policy']['definitionHash'],sequence=state['nextEventIndex'],previousHash=state['eventHash'],kind=kind,classification=classification,orderId=order_id,detail=detail)
    e['eventId']=content_hash(e);state['eventHash']=e['eventId'];state['nextEventIndex']+=1;events.append(e);return e['eventId']


def _live(s):return any(o['status'] in ('PENDING','ACTIVE') for o in s['orders'].values())


def _unresolved(s,events,reason,group_id=None):
    if s['unresolved']:return
    affected=[]
    for oid in sorted(s['orders']):
        o=s['orders'][oid]
        if o['status'] in ('PENDING','ACTIVE'):o.update(status='UNRESOLVED',exitRequest=None);affected.append(oid)
    if affected:s['unresolved']=True
    emit(s,events,'UNRESOLVED',classification='UNRESOLVED',reason=reason,affectedOrderIds=affected,groupId=group_id)


def _fills(s,events,group):
    row=group['events'][0];p=s['profile'];profile=ObservedExecutionProfile.from_wire(p)
    qualities={canonical_bytes(dict(schemaVersion=1,artifact='BTL-RAW-QUOTE-QUALITY-1',quality=r['quality'])):r['quality'] for r in group['events']}
    evidence=dict(groupId=group['groupId'],timeNs=group['timeNs'],order=group['order'],eventIds=[r['eventId'] for r in group['events']],bid=row['bid'],ask=row['ask'],rawQualities=[deepcopy(qualities[k]) for k in sorted(qualities)],chronologyLimited=len(group['events'])>1 and group['order']=='UNTRUSTED')
    for oid in sorted(s['orders']):
        o=s['orders'][oid]
        if o['status'] not in ('PENDING','ACTIVE') or int(row['timeNs'])<int(o['availableNs']):continue
        if o['status']=='PENDING' and crossing(o,row):
            fill=row['ask'] if o['side']=='LONG' else row['bid'];o.update(status='ACTIVE',entryPrice=fill)
            o['entryFillRef']=emit(s,events,'ENTRY_FILL',order_id=oid,classification='SIMULATED_FILL',price=fill,quantity=o['quantity'],commission='0',balanceDelta='0',evidence=evidence);s['financial']=True
        if o['status']!='ACTIVE':continue
        reason=protective(o,row);request=o['exitRequest']
        if reason is None and request is not None and int(row['timeNs'])>=int(request['availableNs']):reason='MANUAL'
        if reason is None:continue
        size=request['quantity'] if reason=='MANUAL' else o['remaining'];fill=row['bid'] if o['side']=='LONG' else row['ask']
        proposal=exit_amount(profile,side=o['side'],entry_price=o['entryPrice'],exit_price=fill,lots=size)
        remaining=exact(o['remaining'],'remaining')-exact(size,'quantity');posted=Fraction(proposal['grossPosted'])
        o.update(status='CLOSED' if remaining==0 else 'ACTIVE',remaining=text(remaining),exitRequest=None,grossPosted=text(Fraction(o['grossPosted'])+posted))
        s['realizedGross']=text(Fraction(s['realizedGross'])+posted);s['balance']=text(Fraction(s['balance'])+posted);s['financial']=True
        emit(s,events,'EXIT_FILL',order_id=oid,classification='SIMULATED_FILL',price=fill,quantity=size,grossExact=proposal['grossExact'],grossPosted=proposal['grossPosted'],commission='0',balanceDelta=proposal['grossPosted'],remaining=o['remaining'],reason=reason,entryFillRef=o['entryFillRef'],evidence=evidence)


def _incomplete(coverage,lo,hi):
    return any(c['status']=='INCOMPLETE' and max(lo,int(c['startNs']))<min(hi,int(c['endNs'])) for c in coverage)


def _advance(s,events,raw,frame,checkpoint):
    require(type(frame) is dict and type(checkpoint) is dict,'controllerFrame')
    keys(frame,'schemaVersion artifact datasetId datasetVersion timelineVersion generation sessionStartNs targetNs throughNs groups coverage diagnostics visiblePrefixHash cursor exhaustedThroughBoundary')
    require(type(frame['schemaVersion']) is int and frame['schemaVersion']==2 and frame['artifact']=='BTL-TICK-REVEAL-2','frame')
    p=s['profile'];c=_checkpoint(checkpoint,ObservedExecutionProfile.from_wire(p));old=int(s['throughNs']);through=uint(frame['throughNs']);target=uint(raw['payload']['targetNs'])
    require(old<=through<=target and frame['targetNs']==raw['payload']['targetNs'] and type(frame['exhaustedThroughBoundary']) is bool
            and (not frame['exhaustedThroughBoundary'] or through==target),'time','REFUSED_FUTURE_EVIDENCE')
    require(frame['cursor']==c and frame['datasetId']==s['datasetId'] and frame['datasetVersion']==s['datasetVersion'] and frame['timelineVersion']==TIMELINE_VERSION and frame['generation']=='0' and frame['sessionStartNs']==s['startNs'] and c['throughNs']==frame['throughNs'] and c['visiblePrefixHash']==frame['visiblePrefixHash'],'source','REFUSED_OBSERVED_SOURCE_IDENTITY')
    require(c['pendingTargetNs']==(None if frame['exhaustedThroughBoundary'] else raw['payload']['targetNs']),'target')
    # Manual/product sources remain at their 64-group default. The bounded
    # historical QA fast-forward may pass up to 256 groups; the timeline keeps
    # the complete timestamp groups and splits durable position-log blocks at
    # their unchanged 128-record limit. Every group still reaches _fills.
    groups=frame['groups'];require(type(groups) is list and len(groups)<=256,'groups')
    require(int(c['nextGroupIndex'])==int(s['nextGroupIndex'])+len(groups) and 0<=int(c['revision'])-int(s['sourceCursorRevision'])<=1,'cursor')
    if groups:require(c['lastGroupId']==groups[-1]['groupId'] and int(c['revision'])==int(s['sourceCursorRevision'])+1,'cursor')
    coverage=frame['coverage'];require(type(coverage) is list and len(coverage)<=2048,'coverage')
    for v in coverage:
        keys(v,'startNs endNs status evidenceHash');require(old<=uint(v['startNs'])<uint(v['endNs'])<=through and v['status'] in ('DECLARED_COMPLETE','UNKNOWN','INCOMPLETE'),'coverage','REFUSED_FUTURE_EVIDENCE')
        if v['evidenceHash'] is not None:digest(v['evidenceHash'], 'digest')
    diag=frame['diagnostics'];keys(diag,'records counts truncated');require(type(diag['records']) is list and len(diag['records'])<=128 and diag['truncated'] is False,'diagnostics')
    for d in diag['records']:
        keys(d,'sourceId memberHash rawOrdinal timeNs code rawRecordHash');identifier(d['sourceId'], 'identifier');digest(d['memberHash'], 'digest');digest(d['rawRecordHash'], 'digest');uint(d['rawOrdinal'])
        require(old<=uint(d['timeNs'])<=through and d['code'] in CODES,'diagnostics','REFUSED_FUTURE_EVIDENCE')
    require(diag['counts']==diagnostic_counts(diag['records']),'diagnostics');canonical_v2_bytes(frame)
    if int(c['revision'])==int(s['sourceCursorRevision']):
        require(not groups and through==old and not coverage and not diag['records'] and frame['visiblePrefixHash']==s['sourcePrefixHash'] and hash_v2(checkpoint)==s['sourceCheckpointHash'],'prefix','CORRUPT_RECORD')
    else:
        expected=hash_v2(dict(schemaVersion=2,artifact='BTL-TICK-PREFIX-STEP-2',previousHash=s['sourcePrefixHash'],throughNs=frame['throughNs'],groups=groups,coverage=coverage,diagnostics=diag))
        require(frame['visiblePrefixHash']==expected,'prefix','CORRUPT_RECORD')
    previous=old;guard=int(p['maxObservedSilenceNs'])
    for group in groups:
        keys(group,'groupId timeNs order events');moment=uint(group['timeNs']);rows=group['events']
        require(previous<=moment<=through and (s['lastObservedNs'] is None or moment>int(s['lastObservedNs'])),'group','REFUSED_FUTURE_EVIDENCE')
        require(type(rows) is list and 1<=len(rows)<=1024 and len({r['eventId'] for r in rows})==len(rows),'group')
        for r in rows:
            CanonicalTick._validate(r)
            require(r['datasetId']==s['datasetId'] and r['datasetVersion']==s['datasetVersion'] and r['timeNs']==group['timeNs'] and all(r[a]==p['primary'][b] for a,b in (('providerId','providerId'),('feedId','feedId'),('instrumentId','feedInstrumentId'))),'identity','REFUSED_OBSERVED_SOURCE_IDENTITY')
            require(r['eventId']==event_id(r['providerId'],r['feedId'],r['provenance']['memberHash'],r['rawOrdinal']),'eventId')
        require(make_group(rows,s['datasetVersion'])==group,'group')
        live=_live(s) and not s['unresolved'] and not s['ended'];anchor=int(s['lastObservedNs']) if s['lastObservedNs'] is not None else int(s['startNs'])
        quality_bad=any(r['quality']['quote']!='VALID' or r['quality']['freshness'] not in ('UNKNOWN','CONFIRMED') or r['quality']['gapBefore'] not in ('UNKNOWN_SILENCE','NONE','KNOWN_SESSION_CLOSED') or r['quality']['duplicateOf'] is not None for r in rows)
        precision_bad=False
        try:
            for r in rows:price(r['bid'],p);price(r['ask'],p)
        except ContractError:precision_bad=True
        equivalent=len({(r['bid'],r['ask']) for r in rows})==1
        if live and moment-anchor>guard and s['model']!=MODEL_V2:_unresolved(s,events,'UNRESOLVED_OBSERVED_SILENCE',group['groupId'])
        elif live and moment-anchor>guard:
            closed=all(r['quality']['gapBefore']=='KNOWN_SESSION_CLOSED' for r in rows)
            emit(s,events,'DATA_GAP_LIMITATION',groupId=group['groupId'],gapStartNs=str(anchor),gapEndNs=str(moment),elapsedNs=str(moment-anchor),gapKind='MARKET_CLOSED' if closed else 'UNKNOWN_COVERAGE_GAP',affectedOrders=[k for k,v in sorted(s['orders'].items()) if v['status'] in ('PENDING','ACTIVE')],quoteAvailable=True,execution='OBSERVED_QUOTES_ONLY',sourceQuality='UNKNOWN')
        if live and not s['unresolved'] and any(previous<=int(d['timeNs'])<=moment for d in diag['records']):_unresolved(s,events,'UNRESOLVED_DIAGNOSTIC',group['groupId'])
        elif live and not s['unresolved'] and _incomplete(coverage,previous,moment):_unresolved(s,events,'UNRESOLVED_KNOWN_COVERAGE',group['groupId'])
        elif live and not s['unresolved'] and (quality_bad or precision_bad):_unresolved(s,events,'UNRESOLVED_QUOTE_QUALITY' if quality_bad else 'UNRESOLVED_QUOTE_PRECISION',group['groupId'])
        if live and not s['unresolved']:
            changes=any(can_change(s,r) for r in rows)
            if not equivalent and changes:_unresolved(s,events,'UNRESOLVED_EQUAL_TIME_ORDER',group['groupId'])
            elif not equivalent:emit(s,events,'CHRONOLOGY_LIMITATION',groupId=group['groupId'],timeNs=group['timeNs'],commonOutcome='NO_FINANCIAL_ACTION')
            elif changes:_fills(s,events,group)
        if quality_bad or precision_bad:
            if not live:emit(s,events,'UNUSABLE_OBSERVATION',classification='UNRESOLVED',groupId=group['groupId'],reason='QUALITY' if quality_bad else 'PRECISION')
        s['quoteBasis']=None if not equivalent or quality_bad or precision_bad else dict(timeNs=group['timeNs'],groupId=group['groupId'],bid=rows[0]['bid'],ask=rows[0]['ask'],eventIds=[r['eventId'] for r in rows],chronologyLimited=len(rows)>1 and group['order']=='UNTRUSTED')
        s['lastObservedNs']=group['timeNs'];s['nextGroupIndex']=str(int(s['nextGroupIndex'])+1);previous=moment
    if _live(s) and not s['unresolved'] and not s['ended']:
        anchor=int(s['lastObservedNs']) if s['lastObservedNs'] is not None else int(s['startNs'])
        if through-anchor>guard and s['model']!=MODEL_V2:_unresolved(s,events,'UNRESOLVED_OBSERVED_SILENCE')
        elif through-anchor>guard:
            if s['quoteBasis'] is not None:
                emit(s,events,'STALE_QUOTE',classification='OBSERVED_FEED_EVENT',quoteTimeNs=s['quoteBasis']['timeNs'],throughNs=str(through),ageNs=str(through-int(s['quoteBasis']['timeNs'])),gapKind='UNKNOWN_COVERAGE_GAP')
                s['quoteBasis']=None
            emit(s,events,'DATA_GAP_LIMITATION',gapStartNs=str(anchor),gapEndNs=str(through),elapsedNs=str(through-anchor),gapKind='UNKNOWN_COVERAGE_GAP',affectedOrders=[k for k,v in sorted(s['orders'].items()) if v['status'] in ('PENDING','ACTIVE')],quoteAvailable=False,execution='OBSERVED_QUOTES_ONLY',sourceQuality='UNKNOWN')
        elif any(previous<=int(d['timeNs'])<=through for d in diag['records']):_unresolved(s,events,'UNRESOLVED_DIAGNOSTIC')
        elif _incomplete(coverage,previous,through):_unresolved(s,events,'UNRESOLVED_KNOWN_COVERAGE')
    if s['quoteBasis'] is not None and (any(int(d['timeNs'])>=int(s['quoteBasis']['timeNs']) for d in diag['records']) or _incomplete(coverage,int(s['quoteBasis']['timeNs']),through)):
        s['quoteBasis']=None
        if not s['unresolved']:emit(s,events,'UNUSABLE_OBSERVATION',classification='UNRESOLVED',reason='KNOWN_EVIDENCE',throughNs=frame['throughNs'])
    s['throughNs']=frame['throughNs'];s['sourceCheckpointHash']=hash_v2(checkpoint);s['sourcePrefixHash']=frame['visiblePrefixHash'];s['sourceCursorRevision']=c['revision']
    if not events:emit(s,events,'REPLAY_ADVANCED',throughNs=s['throughNs'])


def apply(state,raw,*,reveal=None,checkpoint=None,order_retention_policy=None,
          qa_order_archive_v1=False,archived_order_lookup=None):
    validate_state(state,order_retention_policy=order_retention_policy);raw=command_wire(raw)
    archive_mode=state.get('artifact')==STATE_QA_ARCHIVE_V1
    require(archive_mode is qa_order_archive_v1,'qaOrderArchive','REFUSED_STATE_VERSION')
    require(not archive_mode or callable(archived_order_lookup),'archiveLookup','REFUSED_STATE_VERSION')
    max_cumulative,max_active=order_limits(order_retention_policy)
    require(raw['sessionId']==state['sessionId'] and raw['expectedRevision']==state['revision'],'revision','REFUSED_STALE_REVISION')
    kind=raw['kind'];require(not state['ended'] or kind=='ADVANCE','ended','REFUSED_SESSION_ENDED')
    require(not state['unresolved'] or kind in ('ADVANCE','END'),'unresolved','REFUSED_UNRESOLVED_SESSION')
    s=deepcopy(state);events=[];archive_rows=[];p=s['profile'];payload=raw['payload'];policy=policy_from_wire(s['policy'])
    if kind=='ADVANCE':_advance(s,events,raw,reveal,checkpoint)
    else:
        require(reveal is None and checkpoint is None,'unexpectedControllerFrame')
        if kind=='OPEN':
            cumulative=len(s['orders'])+(s['orderArchive']['count'] if archive_mode else 0)
            require(cumulative<max_cumulative,'orders','REFUSED_STATE_LIMIT')
            require(sum(o['status'] in ('PENDING','ACTIVE') for o in s['orders'].values())<max_active,
                    'orders','REFUSED_ACTIVE_ORDER_LIMIT')
            oid=raw['commandId'];require(oid not in s['orders'],'order')
            if archive_mode:
                require(archived_order_lookup(oid) is None,'order','REFUSED_DUPLICATE_ORDER_ID')
            basis=s['quoteBasis'];require(basis is not None and int(s['throughNs'])-int(basis['timeNs'])<=int(p['maxObservedSilenceNs']),'quote','UNRESOLVED_RISK_QUOTE')
            require(exact(s['balance'],'balance',True)>0,'balance');plan=open_payload(payload,p,policy,s['balance'])
            if plan['orderType']=='MARKET':require(plan['entry']==basis['ask' if plan['side']=='LONG' else 'bid'],'quote','REFUSED_STALE_QUOTE')
            bh=content_hash(dict(schemaVersion=1,artifact='BTL-OBSERVED-RISK-BASIS-1',profileHash=s['profileHash'],quote=deepcopy(basis)))
            s['orders'][oid]=dict(plan,status='PENDING',availableNs=s['throughNs'],remaining=plan['quantity'],entryPrice=None,entryFillRef=None,entryCost='0',exitRequest=None,grossPosted='0',riskBalance=s['balance'],riskBasisHash=bh)
            emit(s,events,'ORDER_ACCEPTED',order_id=oid,classification='ACCEPTED_COMMAND',plan=plan,availableNs=s['throughNs'],riskBalance=s['balance'],riskBasisHash=bh)
        elif kind in ('CANCEL','CLOSE'):
            oid=payload['orderId'];o=s['orders'].get(oid)
            if o is None and archive_mode:o=archived_order_lookup(oid)
            require(o is not None,'order','RESOURCE_UNAVAILABLE')
            if kind=='CANCEL':
                require(o['status']=='PENDING','order','REFUSED_NOT_PENDING');validate_action(policy,'CANCEL_PENDING');o['status']='CANCELLED';emit(s,events,'ORDER_CANCELLED',order_id=oid,classification='ACCEPTED_COMMAND')
            else:
                validate_action(policy,'MANUAL_CLOSE' if payload['quantity'] is None else 'PARTIAL_CLOSE');require(o['status']=='ACTIVE' and o['exitRequest'] is None,'order','REFUSED_NOT_ACTIVE')
                size=o['remaining'] if payload['quantity'] is None else text(quantity(payload['quantity'],p))
                require(0<exact(size,'size')<=exact(o['remaining'],'remaining') and (payload['quantity'] is None or exact(size,'size')<exact(o['remaining'],'remaining')),'quantity','REFUSED_PARTIAL_QUANTITY')
                o['exitRequest']=dict(quantity=size,availableNs=s['throughNs']);emit(s,events,'EXIT_REQUESTED',order_id=oid,classification='ACCEPTED_COMMAND',quantity=size,availableNs=s['throughNs'])
        elif kind=='END':
            for oid in sorted(s['orders']):
                o=s['orders'][oid]
                if o['status']=='PENDING':o['status']='EXPIRED';emit(s,events,'EXPIRED_NO_QUOTE',order_id=oid,classification='UNRESOLVED')
            if _live(s):_unresolved(s,events,'UNRESOLVED_SESSION_END_ACTIVE')
            s['ended']=True;emit(s,events,'SESSION_ENDED',classification='ACCEPTED_COMMAND')
    if archive_mode:
        terminal=[(oid,o) for oid,o in sorted(s['orders'].items()) if o['status'] in ('CANCELLED','CLOSED','EXPIRED','UNRESOLVED')]
        summary=s['orderArchive']
        for oid,order in terminal:
            row=archive_append(summary,session_id=s['sessionId'],revision=s['revision']+1,order_id=oid,order=order)
            archive_rows.append(row);summary=archive_advance(summary,[row]);del s['orders'][oid]
        s['orderArchive']=summary
    s['revision']+=1;validate_state(s,order_retention_policy=order_retention_policy)
    if kind=='ADVANCE':validate_snapshot(s,checkpoint,order_retention_policy=order_retention_policy)
    return (s,events,archive_rows) if archive_mode else (s,events)
