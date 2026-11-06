import assert from 'node:assert/strict';
import {loadProductCatalog} from '../src/tickAlpha/client.js';
import {setAccountTransport,clearAccountTransport} from '../src/tickAlpha/accountClient.js';

const workspace='00000000-0000-4000-8000-000000000001';
const subject='00000000-0000-4000-8000-000000000002';
const method=id=>({schemaVersion:1,artifact:'BTL-LOCAL-METHOD-1',id,name:id,kind:'FREE_STYLE',
  checklistOn:false,conditions:[],riskPercent:'1',rr:'2'});
const calls=[];
const client={subject:()=>subject,request:async path=>{
  calls.push(path);
  if(path.endsWith('/catalog'))return {schemaVersion:1,artifact:'BTL-LOCAL-CATALOG-1',
    methods:[],sessions:[],profile:{instrumentId:'XAUUSD'},availability:{schemaVersion:1}};
  if(path.endsWith('/methods?limit=50'))return {schemaVersion:1,artifact:'BTL-METHOD-PAGE-1',
    items:Array.from({length:50},(_,n)=>method(`method:${String(n).padStart(3,'0')}`)),
    complete:false,nextCursor:'method:049'};
  if(path.endsWith('/methods?limit=50&after=method%3A049'))return {schemaVersion:1,artifact:'BTL-METHOD-PAGE-1',
    items:[method('method:050')],complete:true,nextCursor:null};
  if(path.endsWith('/sessions?limit=50'))return {schemaVersion:1,artifact:'BTL-SESSION-PAGE-1',
    items:[{metadata:{id:'session:one',name:'Synthetic QA',methodId:'method:000',startPeriod:'2020-01',initialBalance:'10000'},
      revision:4,financialCountsStatus:'NOT_COMPUTED_ON_LIST'}],complete:true,nextCursor:null};
  throw new Error(`Unexpected path ${path}`);
}};

setAccountTransport(client,workspace);
try{
  const catalog=await loadProductCatalog();
  assert.equal(catalog.methods.length,51);
  assert.equal(catalog.methods[50].id,'method:050');
  assert.deepEqual(catalog.sessions,[{id:'session:one',name:'Synthetic QA',methodId:'method:000',
    startPeriod:'2020-01',initialBalance:'10000',revision:4,
    financialCountsStatus:'NOT_COMPUTED_ON_LIST'}]);
  assert.ok(calls.some(path=>path.includes('/methods?limit=50&after=')));
  assert.ok(calls.some(path=>path.includes('/sessions?limit=50')));
}finally{clearAccountTransport();}
console.log('hosted product pagination: ok');
