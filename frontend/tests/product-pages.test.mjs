import assert from 'node:assert/strict';
import {loadProductCatalog,createMethodVersion,setMethodArchived} from '../src/tickAlpha/client.js';
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
  if(path.endsWith('/sessions?limit=50'))return {schemaVersion:1,artifact:'BTL-SESSION-PAGE-1',
    items:[{metadata:{id:'session:one',name:'Synthetic QA',methodId:'method:000',startPeriod:'2020-01',initialBalance:'10000'},
      revision:4,financialCountsStatus:'NOT_COMPUTED_ON_LIST'}],complete:true,nextCursor:null};
  if(path.includes('/method-families/method%3A050/versions'))return {schemaVersion:1,artifact:'BTL-METHOD-FAMILY-1'};
  if(path.includes('/method-families/method%3A050/lifecycle'))return {schemaVersion:1,artifact:'BTL-METHOD-FAMILY-1'};
  throw new Error(`Unexpected path ${path}`);
}};

setAccountTransport(client,workspace);
try{
  const catalog=await loadProductCatalog();
  assert.equal(catalog.methods.length,51);
  assert.equal(catalog.methods[50].id,'method:050');
  assert.equal(catalog.methods[50].methodFamilyId,'method:050');
  assert.equal(catalog.methods[50].methodVersion,1);
  assert.deepEqual(catalog.sessions,[{id:'session:one',name:'Synthetic QA',methodId:'method:000',
    startPeriod:'2020-01',initialBalance:'10000',revision:4,
    financialCountsStatus:'NOT_COMPUTED_ON_LIST'}]);
  assert.ok(calls.some(path=>path.includes('/method-families?includeArchived=true&limit=50&after=')));
  assert.ok(calls.some(path=>path.includes('/sessions?limit=50')));
  const nextMethod={...method('method:051')};
  await createMethodVersion({familyId:'method:050',revision:7},nextMethod);
  await setMethodArchived({familyId:'method:050',revision:8},true);
  assert.ok(calls.includes('/api/v1/workspaces/'+workspace+'/research/method-families/method%3A050/versions'));
  assert.ok(calls.includes('/api/v1/workspaces/'+workspace+'/research/method-families/method%3A050/lifecycle'));
}finally{clearAccountTransport();}

let methodPage=0;
const nonAdvancingClient={subject:()=>subject,request:async path=>{
  if(path.endsWith('/catalog'))return {schemaVersion:1,artifact:'BTL-LOCAL-CATALOG-1',methods:[],sessions:[],profile:{instrumentId:'XAUUSD'}};
  if(path.includes('/method-families?includeArchived=true&limit=50'))return {schemaVersion:1,artifact:'BTL-METHOD-FAMILY-PAGE-1',items:[],complete:false,nextCursor:`method:${++methodPage}`};
  if(path.includes('/sessions?limit=50'))return {schemaVersion:1,artifact:'BTL-SESSION-PAGE-1',items:[],complete:true,nextCursor:null};
  throw new Error(`Unexpected path ${path}`);
}};
setAccountTransport(nonAdvancingClient,workspace);
try{await assert.rejects(loadProductCatalog(),/page bound/);}
finally{clearAccountTransport();}
console.log('hosted product pagination: ok');
