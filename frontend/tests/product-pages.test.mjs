import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {loadProductCatalog,loadMoreProductCatalog,loadJournalPage,createMethodVersion,setMethodArchived,
  loadMethodFamily,loadMethodFamilyRecord,loadMethodRecord,loadMethodSessionPage,loadMethodVersionPage,loadSessionWithMetadata} from '../src/tickAlpha/client.js';
import {setAccountTransport,clearAccountTransport} from '../src/tickAlpha/accountClient.js';
import {readRoute,routeHref} from '../src/tickAlpha/productRoute.js';

const workspace='00000000-0000-4000-8000-000000000001';
const subject='00000000-0000-4000-8000-000000000002';
const method=id=>({schemaVersion:1,artifact:'BTL-LOCAL-METHOD-1',id,name:id,kind:'FREE_STYLE',
  checklistOn:false,conditions:[],riskPercent:'1',rr:'2'});
const family=id=>({familyId:id,revision:1,archived:false,latestVersion:1,latestMethodId:id,
  current:method(id),versions:[{version:1,methodId:id,method:method(id)}]});
const versionHref=routeHref({screen:'method-new',family:'method:one'},'https://riksora.test/?page=account');
assert.equal(readRoute('https://riksora.test'+versionHref).family,'method:one');
for(const screen of ['session','journal','analytics']){
  const original=`https://riksora.test/?page=account&screen=${screen}&of=session%3Alinked`;
  const rebuilt=routeHref(readRoute(original),'https://riksora.test/?page=account');
  assert.equal(readRoute('https://riksora.test'+rebuilt).analyticsSession,'session:linked');
  assert.equal(readRoute('https://riksora.test'+rebuilt).screen,screen);
}
const sessionWizard=readFileSync(new URL('../src/tickAlpha/AlphaSessionWizard.jsx',import.meta.url),'utf8');
const terminal=readFileSync(new URL('../src/tickAlpha/TickAlpha.jsx',import.meta.url),'utf8');
assert.match(terminal,/<a \{\.\.\.linkTo\(\{screen:'sessions'\}\)\}>All Sessions<\/a>/);
assert.match(terminal,/isAccountPage\(\)\?linkTo\(\{screen:'account'\}\)/);
assert.match(sessionWizard,/onCreate\(\{name:finalName,methodId:method\.id,symbol:instrument,/);
assert.match(terminal,/api\('\/sessions',\{id:creationId\.current,name:fields\.name,methodId:fields\.methodId,\s*initialBalance:fields\.initialBalance,startPeriod:fields\.startPeriod\?\?catalog\.startPeriod\}\)/);
assert.doesNotMatch(terminal,/api\('\/sessions',[^\n]*symbol:/);
const calls=[];
const client={subject:()=>subject,request:async (path,options={})=>{
  calls.push(path);
  if(path.endsWith('/catalog'))return {schemaVersion:1,artifact:'BTL-LOCAL-CATALOG-1',
    methods:[],sessions:[],profile:{instrumentId:'XAUUSD'},availability:{schemaVersion:1}};
  if(path.endsWith('/method-families?includeArchived=true&limit=50'))return {schemaVersion:1,artifact:'BTL-METHOD-FAMILY-PAGE-1',
    items:Array.from({length:50},(_,n)=>family(`method:${String(n).padStart(3,'0')}`)),
    complete:false,nextCursor:'method:049'};
  if(path.endsWith('/method-families?includeArchived=true&limit=50&after=method%3A049'))return {schemaVersion:1,artifact:'BTL-METHOD-FAMILY-PAGE-1',
    items:[family('method:050')],complete:true,nextCursor:null};
  if(path.endsWith('/method-families/method%3A050'))return {schemaVersion:1,artifact:'BTL-METHOD-FAMILY-1',family:{...family('method:050'),revision:4}};
  if(path.endsWith('/methods/method%3Aold'))return {schemaVersion:1,artifact:'BTL-METHOD-1',method:method('method:old')};
  if(path.endsWith('/methods/method%3Amismatch'))return {schemaVersion:1,artifact:'BTL-METHOD-1',method:method('method:old')};
  if(path.endsWith('/method-families/method%3Astale'))return {schemaVersion:1,artifact:'BTL-METHOD-FAMILY-1',family:family('method:stale')};
  if(path.endsWith('/method-families/method%3Astale/versions?limit=25'))return {schemaVersion:1,
    artifact:'BTL-METHOD-VERSION-PAGE-1',familyId:'method:stale',revision:2,versions:[],complete:true,nextCursor:null};
  if(path.endsWith('/method-families/method%3A050/versions?limit=25'))return {schemaVersion:1,
    artifact:'BTL-METHOD-VERSION-PAGE-1',familyId:'method:050',revision:4,
    versions:[{version:1,methodId:'method:050',method:method('method:050')}],complete:false,nextCursor:'cursor-one'};
  if(path.endsWith('/method-families/method%3A050/versions?limit=25&cursor=cursor-one'))return {schemaVersion:1,
    artifact:'BTL-METHOD-VERSION-PAGE-1',familyId:'method:050',revision:4,
    versions:[{version:2,methodId:'method:051',method:method('method:051')}],complete:true,nextCursor:null};
  if(path.endsWith('/sessions?limit=50'))return {schemaVersion:1,artifact:'BTL-SESSION-PAGE-1',
    items:[{metadata:{id:'session:one',name:'Synthetic QA',methodId:'method:000',startPeriod:'2020-01',initialBalance:'10000'},
      revision:4,financialCountsStatus:'NOT_COMPUTED_ON_LIST'}],complete:true,nextCursor:null};
  if(path.endsWith('/sessions?methodId=method%3A050&limit=50'))return {
    schemaVersion:1,artifact:'BTL-SESSION-PAGE-1',items:[{metadata:{id:'session:linked',methodId:'method:050'}}],
    complete:false,nextCursor:'session:linked'};
  if(path.endsWith('/sessions?methodId=method%3A050&limit=50&after=session%3Alinked'))return {
    schemaVersion:1,artifact:'BTL-SESSION-PAGE-1',items:[{metadata:{id:'session:older',methodId:'method:050'}}],
    complete:true,nextCursor:null};
  if(path.endsWith('/sessions?methodId=method%3Amismatch&limit=50'))return {
    schemaVersion:1,artifact:'BTL-SESSION-PAGE-1',items:[{metadata:{id:'session:linked',methodId:'method:050'}}],
    complete:true,nextCursor:null};
  if(path.endsWith('/sessions/session%3Alinked')||path.endsWith('/sessions/session%3Alinked/view')){
    const analytics=path.endsWith('/view');
    assert.equal(options.method,analytics?'POST':'GET');
    assert.deepEqual(options.body,analytics?{timeframe:'1m'}:undefined);
    assert.ok(options.signal instanceof AbortSignal);
    return {schemaVersion:1,metadata:{id:'session:linked',name:'Outside the first page',methodId:'method:050'},
      state:{revision:8},...(analytics?{analysis:{status:'COMPLETE'}}:{})};
  }
  if(path.endsWith('/sessions/session%3Amismatch'))return {
    schemaVersion:1,metadata:{id:'session:linked',name:'Mismatched',methodId:'method:050'},state:{revision:8}};
  if(path.endsWith('/sessions/session%3Aprivate'))throw Object.assign(Error('This workspace or record is unavailable.'),{status:404});
  if(path.endsWith('/sessions/session%3Amismatch/journal/pages?limit=32'))return {
    schemaVersion:1,artifact:'BTL-TICK-JOURNAL-PAGE-1',sessionId:'session:linked',
    totalOrders:0,orders:[],notes:[],nextCursor:null,complete:true};
  if(path.endsWith('/sessions/session%3Aone/journal/pages?limit=32&cursor=order%3A031'))return {
    schemaVersion:1,artifact:'BTL-TICK-JOURNAL-PAGE-1',sessionId:'session:one',revision:8,
    totalOrders:33,orders:[{id:'order:032',side:'LONG',orderType:'MARKET',status:'CLOSED'}],notes:[],
    provenance:{revision:8},nextCursor:null,complete:true};
  if(path.includes('/method-families/method%3A050/versions'))return {schemaVersion:1,artifact:'BTL-METHOD-FAMILY-1'};
  if(path.includes('/method-families/method%3A050/lifecycle'))return {schemaVersion:1,artifact:'BTL-METHOD-FAMILY-1'};
  throw new Error(`Unexpected path ${path}`);
}};

setAccountTransport(client,workspace);
try{
  const catalog=await loadProductCatalog();
  assert.equal(catalog.methods.length,50,'initial load remains one bounded page');
  assert.equal(catalog.methods[49].id,'method:049');
  assert.equal(catalog.methods[49].methodFamilyId,'method:049');
  assert.equal(catalog.methods[49].methodVersion,1);
  assert.equal(catalog.productPagination.methods.complete,false);
  const more=await loadMoreProductCatalog(catalog,'methods');
  assert.equal(more.methods.length,51);
  assert.equal(more.methods[50].id,'method:050');
  assert.ok(!catalog.methods.some(item=>item.id==='method:old'));
  assert.equal((await loadMethodRecord('method:old')).id,'method:old');
  await assert.rejects(loadMethodRecord('method:mismatch'),/invalid Method/);
  assert.equal((await loadMethodFamilyRecord('method:050')).current.id,'method:050');
  await assert.rejects(loadMethodFamily('method:stale'),/Method versions changed/);
  assert.deepEqual(catalog.sessions,[{id:'session:one',name:'Synthetic QA',methodId:'method:000',
    startPeriod:'2020-01',initialBalance:'10000',revision:4,
    financialCountsStatus:'NOT_COMPUTED_ON_LIST'}]);
  assert.ok(calls.some(path=>path.includes('/method-families?includeArchived=true&limit=50&after=')));
  assert.ok(calls.some(path=>path.includes('/sessions?limit=50')));
  assert.ok(!catalog.sessions.some(session=>session.id==='session:linked'));
  const linked=await loadSessionWithMetadata('session:linked');
  assert.equal(linked.metadata.name,'Outside the first page');
  const analytics=await loadSessionWithMetadata('session:linked',{analytics:true});
  assert.equal(analytics.analysis.status,'COMPLETE');
  const methodSessions=await loadMethodSessionPage('method:050');
  assert.equal(methodSessions.items[0].id,'session:linked');
  const following=await loadMethodSessionPage('method:050',methodSessions.nextCursor);
  assert.equal(following.items[0].id,'session:older');
  assert.equal(following.complete,true);
  await assert.rejects(loadMethodSessionPage('method:mismatch'),/invalid Session page/);
  await assert.rejects(loadSessionWithMetadata('session:mismatch'),/invalid Session/);
  await assert.rejects(loadSessionWithMetadata('session:private'),{status:404});
  await assert.rejects(loadJournalPage('session:mismatch'),/Unsupported Journal page/);
  const journal=await loadJournalPage('session:one','order:031');
  assert.equal(journal.totalOrders,33);
  assert.equal(journal.orders[0].id,'order:032');
  assert.ok(calls.includes('/api/v1/workspaces/'+workspace+'/research/sessions/session%3Aone/journal/pages?limit=32&cursor=order%3A031'));
  const nextMethod={...method('method:051')};
  await createMethodVersion({familyId:'method:050',revision:7},nextMethod);
  await setMethodArchived({familyId:'method:050',revision:8},true);
  const detail=await loadMethodFamily('method:050');
  assert.equal(detail.revision,4);
  assert.equal(detail.versions[0].methodId,'method:050');
  const nextVersions=await loadMethodVersionPage('method:050',detail.nextVersionCursor);
  assert.equal(nextVersions.versions[0].version,2);
  assert.equal(nextVersions.complete,true);
  assert.ok(calls.includes('/api/v1/workspaces/'+workspace+'/research/method-families/method%3A050/versions'));
  assert.ok(calls.includes('/api/v1/workspaces/'+workspace+'/research/method-families/method%3A050/lifecycle'));
}finally{clearAccountTransport();}

const nonAdvancingClient={subject:()=>subject,request:async path=>{
  if(path.endsWith('/catalog'))return {schemaVersion:1,artifact:'BTL-LOCAL-CATALOG-1',methods:[],sessions:[],profile:{instrumentId:'XAUUSD'}};
  if(path.includes('/method-families?includeArchived=true&limit=50'))return {schemaVersion:1,artifact:'BTL-METHOD-FAMILY-PAGE-1',items:[],complete:false,nextCursor:'method:stuck'};
  if(path.includes('/sessions?limit=50'))return {schemaVersion:1,artifact:'BTL-SESSION-PAGE-1',items:[],complete:true,nextCursor:null};
  throw new Error(`Unexpected path ${path}`);
}};
setAccountTransport(nonAdvancingClient,workspace);
try{
  const first=await loadProductCatalog();
  await assert.rejects(loadMoreProductCatalog(first,'methods'),/did not advance/);
}
finally{clearAccountTransport();}
console.log('hosted product pagination: ok');
