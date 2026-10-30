"""Independent QA reader: never imports the range writer or its indexes/caches."""
import hashlib
import json
import zlib
from copy import deepcopy

from contracts.canonical import canonical_bytes, content_hash
from ticks.contracts_v2 import canonical_v2_bytes, hash_v2
from ticks.timeline import make_group, RevealedView
from ticks.timeline_v2 import IndexedTickTimeline
from execution.observed_kernel import apply


def source_groups(provider, start):
    position=provider.locate_v2(provider.dataset_id,provider.dataset_version,start)['position']
    rows=[];timestamp=None;anchor=None
    while position is not None:
        page=provider.read_page_v2(provider.dataset_id,provider.dataset_version,position,256)
        for offset,event in enumerate(page['events']):
            if timestamp is not None and event['timeNs']!=timestamp:
                yield anchor,make_group(rows,provider.dataset_version)
                rows=[];anchor=None
            if anchor is None:
                anchor=dict(position,eventOffset=str(int(position['eventOffset'])+offset),globalOrdinal=str(int(position['globalOrdinal'])+offset))
            timestamp=event['timeNs'];rows.append(event)
        position=page['nextPosition']
    if rows:yield anchor,make_group(rows,provider.dataset_version)


def validate_envelopes(binding, physical_rows, committed, commands):
    by_hash={}
    for digest,seq,packed in physical_rows:
        if digest in by_hash:raise ValueError('DUPLICATED_PREPARED')
        decoder=zlib.decompressobj();raw=decoder.decompress(bytes(packed),1048577)
        if len(raw)>1048576 or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:raise ValueError('CORRUPT_ENCODING')
        obj=json.loads(raw)
        if canonical_bytes(obj)!=raw or hashlib.sha256(raw).hexdigest()!=digest or obj['seq']!=seq:raise ValueError('CORRUPT_RANGE')
        by_hash[digest]=obj
    previous=None;group_end='0';result=[]
    if len(committed)!=len(commands):raise ValueError('MISSING_COMMIT')
    for i,((revision,cid,digest),command) in enumerate(zip(committed,commands),1):
        if revision!=i or cid!=command['commandId']:raise ValueError('REORDERED_COMMIT')
        if digest not in by_hash:raise ValueError('MISSING_PREPARED')
        obj=by_hash[digest]
        if obj['format']!='RIKSORA-QA-RANGE-EXPERIMENT-1' or obj['bindingHash']!=content_hash(binding):raise ValueError('SUBSTITUTED_BINDING')
        if obj['seq']!=i or obj['previousHash']!=previous or obj['commandId']!=cid or obj['commandHash']!=content_hash(command) or obj['targetNs']!=command['payload']['targetNs']:raise ValueError('CHAIN_OR_COMMAND')
        if obj['groupStart']!=group_end or int(obj['groupEnd'])<int(group_end):raise ValueError('GROUP_CONTINUITY')
        previous=digest;group_end=obj['groupEnd'];result.append(obj)
    return result


def verify(binding, physical_rows, committed, commands, seed, receipts, provider, scratch):
    ranges=validate_envelopes(binding,physical_rows,committed,commands)
    engine=IndexedTickTimeline(provider,provider.dataset_id,provider.dataset_version,seed['controller']['cursor']['sessionStartNs'],log_folder=scratch,log_codec='zlib-1')
    observed=source_groups(provider,seed['controller']['cursor']['sessionStartNs']);state=deepcopy(seed['state']);prior_cp=seed['controller']
    all_events=[];group_count=0;stream=hashlib.sha256()
    try:
        for obj,command,receipt in zip(ranges,commands,receipts):
            frame=engine.advance_through(command['payload']['targetNs'],engine.cursor);cp=engine.checkpoint()
            state,events=apply(state,command,reveal=frame,checkpoint=cp)
            if state!=receipt['state'] or events!=receipt['events'] or receipt['commandHash']!=content_hash(command):raise ValueError('FINANCIAL_OR_RECEIPT_PARITY')
            if hash_v2(prior_cp['cursor'])!=obj['beforeCursorHash'] or hash_v2(cp['cursor'])!=obj['afterCursorHash'] or cp['advanceLogHash']!=obj['advanceLogHash'] or cp['positionLogHash']!=obj['positionLogHash']:raise ValueError('CURSOR_CHAIN')
            n=int(obj['groupEnd'])-int(obj['groupStart']);h=hashlib.sha256(b'RIKSORA-QA-POSITIONS-1\0');first=None
            for index in range(int(obj['groupStart']),int(obj['groupEnd'])):
                pos,group=next(observed)
                if first is None:first=pos
                if int(group['timeNs'])>int(cp['cursor']['throughNs']):raise ValueError('FUTURE_GROUP')
                record=dict(groupIndex=str(index),position=pos,groupId=group['groupId'],successorCursorHash=hash_v2(cp['cursor']))
                raw=canonical_v2_bytes(dict(schemaVersion=2,artifact='RIKSORA-QA-POSITION-COMMIT-1',record=record));h.update(len(raw).to_bytes(4,'big'));h.update(raw)
                stream.update(json.dumps(group,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode());group_count+=1
            if first!=obj['firstPosition'] or h.hexdigest()!=obj['positionCommitment'] or n!=len(frame['groups']):raise ValueError('SOURCE_RANGE_PROOF')
            all_events.extend(events);prior_cp=cp
        return dict(groups=group_count,revealHash=stream.hexdigest(),checkpoint=prior_cp,state=state,events=all_events,zeroReveal=sum(r['groupStart']==r['groupEnd'] for r in ranges))
    finally:engine.close()


def consumer(provider, start, checkpoint):
    end=int(checkpoint['cursor']['nextGroupIndex'])
    def read(index='0',maximum=64):
        index=int(index)
        if index<0 or index>end or not 1<=maximum<=64:raise ValueError('UNREVEALED_INDEX')
        if index==end:return []
        result=[]
        for ordinal,(_,group) in enumerate(source_groups(provider,start)):
            if ordinal>=end or len(result)>=maximum:break
            if ordinal>=index:result.append(group)
        return result
    return RevealedView(read,lambda:deepcopy(checkpoint['cursor']))
