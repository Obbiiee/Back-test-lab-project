// Independent BigInt/profile-byte reference. No production Python imports.
import fs from 'node:fs';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';
const data=JSON.parse(fs.readFileSync(new URL('./fixtures/observed_profile_vectors.json',import.meta.url),'utf8'));
const canon=v=>v===null||typeof v!=='object'?JSON.stringify(v):Array.isArray(v)?'['+v.map(canon).join(',')+']':'{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+canon(v[k])).join(',')+'}';
const decimal=s=>{const neg=s.startsWith('-');if(neg)s=s.slice(1);const [a,b='']=s.split('.');return [BigInt(a+b)*(neg?-1n:1n),10n**BigInt(b.length)];};
const mul=([a,b],[c,d])=>[a*c,b*d];
const sub=([a,b],[c,d])=>[a*d-c*b,b*d];
const div=([a,b],[c,d])=>[a*d,b*c];
const eq=(a,b)=>assert.equal(a[0]*b[1],b[0]*a[1]);
const rounded=([n,d])=>{const neg=n<0n;if(neg)n=-n;n*=100n;let q=n/d;const r=n%d;if(r*2n>d||(r*2n===d&&q%2n===1n))q++;return [q*(neg?-1n:1n),100n];};
for(const v of data.profiles){assert.equal(canon(v.profile),v.canonical);assert.equal(crypto.createHash('sha256').update(v.canonical).digest('hex'),v.sha256);}
for(const v of data.arithmetic){let result=mul(mul(sub(decimal(v.exit),decimal(v.entry)),decimal(v.quantity)),[100n,1n]);if(v.side==='SHORT')result=[-result[0],result[1]];eq(result,decimal(v.expectedGross));eq(rounded(result),decimal(v.expectedPosted));}
const r=data.risk,budget=mul(mul(decimal(r.balance),decimal(r.riskPercent)),[1n,100n]),distance=sub(decimal(r.entry),decimal(r.stop)),perLot=mul(distance,[100n,1n]);
const desired=div(budget,perLot),steps=desired[0]*100n/desired[1],size=[steps,100n];eq(size,decimal(r.expectedQuantity));eq(mul(size,perLot),decimal(r.expectedRisk));
console.log(`PASS independent observed model literals: ${data.profiles.length} profiles, ${data.arithmetic.length} exact/half-even PnL cases, one risk/lot-floor case.`);
