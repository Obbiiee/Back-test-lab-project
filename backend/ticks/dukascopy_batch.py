"""Sequential offline16-symbol intake. No download, eligibility or month-coverage claim."""
from datetime import datetime
import json,os,re,tempfile
from pathlib import Path
from contracts.primitives import require
from market_data.instruments import INSTRUMENTS
from .dukascopy_csv import DukascopyCsvIngestion,FIELDS,record,source_pin
from .storage_v2 import ArtifactStore,DiskTickProvider


def plan(source_directory,store_directory,month):
    require(type(month) is str and re.fullmatch(r'[0-9]{4}-[0-9]{2}',month),'month')
    try:datetime.strptime(month,'%Y-%m')
    except ValueError:require(False,'month')
    source=Path(source_directory).resolve(strict=True);store=Path(store_directory).resolve()
    require(source.is_dir(),'sourceDirectory')
    # No output may replace or be contained in raw input; preserve source bytes.
    require(not store.is_relative_to(source) and not source.is_relative_to(store),'directories','SOURCE_STORE_OVERLAP')
    items=[];identities=set()
    for symbol in INSTRUMENTS:
        require((store/symbol).resolve()==store/symbol,'store','STORE_PATH_REFUSED')
        path=(source/(symbol+'.csv')).resolve(strict=True)
        require(path.is_file() and path.is_relative_to(source),'source','SOURCE_PATH_REFUSED')
        stat=path.stat();identity=(stat.st_dev,stat.st_ino)
        require(identity not in identities,'source','DUPLICATE_SOURCE_FILE');identities.add(identity)
        with path.open('rb') as stream:require(record(stream.readline(8193))==FIELDS,'UTC header','SCHEMA_MISMATCH')
        items.append((symbol,path,source_pin(path)))
    return store,items


def completed(folder,pin,symbol,month,evidence_class):
    if not (folder/'archive.sqlite').is_file():return None
    archive=ArtifactStore(folder)
    try:
        state=archive.journal()
        if state is None or state['state']!='COMPLETE':return None
        meta=state['pin']['metadata'];dataset='local:dukascopy:'+symbol+':'+month+':'+pin['sha256'][:24]
        require(state['pin']['sourcePin']==pin and meta['datasetId']==dataset and meta['providerSymbol']==symbol
                and meta['evidenceClass']==evidence_class and meta['adapterVersion']=='DUKASCOPY-LOCAL-CSV-1','resume','SOURCE_PIN_CHANGED')
        rows=archive.db.execute('SELECT version FROM publications').fetchall();require(len(rows)==1,'publication')
        version=rows[0][0]
        for (hash_,) in archive.db.execute('SELECT hash FROM objects'):archive.raw(hash_)
    finally:archive.close()
    provider=DiskTickProvider(folder,version)
    try:
        root=provider.describe_v2(dataset,version)['root']
        for key,value in meta.items():require(root[key]==value,'metadata','SOURCE_PIN_CHANGED')
        position=provider.locate_v2(dataset,version,'0')['position'];count=0
        while position is not None:
            page=provider.read_page_v2(dataset,version,position);count+=len(page['events']);position=page['nextPosition']
            require(count<=state['count'],'count')
        require(count==state['count']==int(root['eventCount']),'count')
    finally:provider.close()
    return dict(artifact='BTL-DUKASCOPY-LOCAL-IMPORT-1',status='STRUCTURAL_PUBLICATION_ONLY',datasetId=dataset,datasetVersion=version,
        source=dict(pin),symbol=symbol,requestedMonthUtc=month,acceptedRows=count,evidenceClass=evidence_class,
        symbolIdentity='OPERATOR_LABEL_UNVERIFIED',coverage='UNVERIFIED',freshness='UNKNOWN',rights='UNVERIFIED',
        equalTimestampOrder='UNTRUSTED',executionEligibility='NOT_GRANTED')


def ingest(source_directory,store_directory,month,*,resume=False,evidence_class='PROVIDER_OBSERVATION'):
    store,items=plan(source_directory,store_directory,month)
    results=[]
    for symbol,path,pin in items:
        require(source_pin(path)==pin,'source','SOURCE_PIN_CHANGED')
        prior=completed(store/symbol,pin,symbol,month,evidence_class) if resume else None
        if prior is not None:
            require(source_pin(path)==pin,'source','SOURCE_PIN_CHANGED');results.append(prior);continue
        importer=DukascopyCsvIngestion(path,store/symbol,symbol=symbol,month=month,resume=resume,evidence_class=evidence_class)
        try:
            require(importer.pin==pin,'source','SOURCE_PIN_CHANGED')
            results.append(importer.run())
        finally:importer.builder.store.close()
    for _,path,pin in items:require(source_pin(path)==pin,'source','SOURCE_PIN_CHANGED')
    return dict(schemaVersion=1,artifact='BTL-DUKASCOPY-LOCAL-BATCH-1',status='ALL_STRUCTURAL_IMPORTS_COMPLETED',requestedMonthUtc=month,
        instruments=list(INSTRUMENTS),imports=results,coverage='UNVERIFIED',rights='UNVERIFIED',
        symbolIdentity='OPERATOR_LABEL_UNVERIFIED',executionEligibility='NOT_GRANTED')


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('source-directory','store-directory','month','report'):parser.add_argument('--'+name,required=True)
    parser.add_argument('--resume',action='store_true');args=parser.parse_args()
    report=Path(args.report).resolve();source=Path(args.source_directory).resolve();store=Path(args.store_directory).resolve()
    require(not report.exists(),'report','OUTPUT_ALREADY_EXISTS')
    require(not report.is_relative_to(source) and not report.is_relative_to(store),'report','OUTPUT_PATH_REFUSED')
    result=ingest(source,store,args.month,resume=args.resume)
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=report.parent,delete=False) as stream:
            temporary=Path(stream.name);json.dump(result,stream,indent=2)
        os.link(temporary,report) # Exclusive publication; never overwrite prior evidence.
        print(json.dumps(dict(status=result['status'],instruments=len(result['imports']),coverage=result['coverage'],executionEligibility=result['executionEligibility'])))
    finally:
        if temporary is not None:temporary.unlink(missing_ok=True)

if __name__=='__main__':main()
