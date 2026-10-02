import { mkdir, readFile, writeFile, rename } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { unzipSync, strFromU8 } from 'fflate';
import { parseHistDataCSV } from '../src/market/history.js';
import { aggregateCandles, TIMEFRAMES } from '../src/market/candles.js';

const root = new URL('../public/market/decade/', import.meta.url);
const cache = new URL('../.history-downloads/', import.meta.url);
await mkdir(root, {recursive:true}); await mkdir(cache,{recursive:true});
const manifest = {symbol:'XAUUSD',source:'HistData.com',priceType:'bid',timezone:'UTC',sourceTimezone:'EST fixed UTC-5',downloadedAt:new Date().toISOString(),from:'2016-10-01',frames:Object.fromEntries(Object.keys(TIMEFRAMES).map(key=>[key,[]])),archives:[],count:0};
const cutoff = Date.parse('2016-10-01T00:00:00Z')/1000;
const periods = [...Array.from({length:10},(_,i)=>String(2016+i)),...Array.from({length:9},(_,i)=>'2026'+String(i+1).padStart(2,'0'))];
async function download(period) {
  const archive = new URL(period+'.zip',cache);
  try{return new Uint8Array(await readFile(archive));}catch{/* Download missing archives. */}
  const year=period.slice(0,4),month=period.length===6?'/'+Number(period.slice(4)):'';
  const url=`https://www.histdata.com/download-free-forex-historical-data/?/ascii/1-minute-bar-quotes/xauusd/${year}${month}`;
  let failure;
  for(let attempt=0;attempt<3;attempt++) {
    try {
      const page=await fetch(url,{signal:AbortSignal.timeout(30000)});
      if(!page.ok)throw new Error('Page HTTP '+page.status);
      const form=/<form id="file_down"[\s\S]*?<\/form>/.exec(await page.text())?.[0];
      if(!form)throw new Error('Archive unavailable: '+period);
      const body=new URLSearchParams();
      for(const input of form.matchAll(/<input[^>]*name="([^"]+)"[^>]*value="([^"]*)"/g))body.set(input[1],input[2]);
      if(!body.get('tk'))throw new Error('Archive not published: '+period);
      const response=await fetch('https://www.histdata.com/get.php',{method:'POST',headers:{Referer:url},body,signal:AbortSignal.timeout(60000)});
      if(!response.ok)throw new Error('Archive HTTP '+response.status);
      const bytes=new Uint8Array(await response.arrayBuffer());
      if(bytes.length>60000000||bytes[0]!==80||bytes[1]!==75)throw new Error('Invalid ZIP: '+period);
      await writeFile(archive,bytes);return bytes;
    }catch(error){failure=error;}
  }
  throw failure;
}
for(const period of periods) {
  console.log('Downloading '+period);
  const bytes=await download(period), files=unzipSync(bytes);
  const selected=Object.keys(files).filter(name=>name.endsWith('.csv')&&name.includes('XAUUSD')&&name.includes('M1'));
  if(!selected.length)throw new Error('CSV missing: '+period);
  const unique=new Map();
  for(const name of selected) for(const bar of parseHistDataCSV(strFromU8(files[name])))if(bar.time>=cutoff)unique.set(bar.time,bar);
  const candles=[...unique.values()].sort((a,b)=>a.time-b.time);
  manifest.archives.push({period,sha256:createHash('sha256').update(bytes).digest('hex'),count:candles.length});
  // Files are partitioned by UTC month. Boundary rows from neighboring archives
  // are retained and deduplicated before aggregation in the final publishing step.
  const months=new Map();
  for(const bar of candles){const key=new Date(bar.time*1000).toISOString().slice(0,7);if(!months.has(key))months.set(key,[]);months.get(key).push(bar);}
  for(const [month,rows] of months) {
    const path=new URL(month+'.m1.tmp.json',root);
    let previous=[];try{previous=JSON.parse(await readFile(path,'utf8'));}catch{/* New month. */}
    const all=new Map([...previous,...rows].map(bar=>[bar.time,bar]));
    await writeFile(path,JSON.stringify([...all.values()].sort((a,b)=>a.time-b.time)));
  }
  console.log('Ready '+period+': '+candles.length+' M1');
}
const {readdir,unlink}=await import('node:fs/promises');
const monthFiles=(await readdir(root)).filter(name=>name.endsWith('.m1.tmp.json')).sort();
const coarse=[];
for(const name of monthFiles) {
  const bars=JSON.parse(await readFile(new URL(name,root),'utf8'));
  manifest.count+=bars.length;
  if(manifest.first==null)manifest.first=bars[0].time;
  manifest.last=bars.at(-1).time;
  const month=name.slice(0,7);
  for(const timeframe of Object.keys(TIMEFRAMES).filter(key=>!['D','W','M'].includes(key))) {
    const rows=aggregateCandles(bars,timeframe).map(bar=>[bar.time,bar.open,bar.high,bar.low,bar.close]);
    const path=`${month}-${timeframe}.json`;
    await writeFile(new URL(path,root),JSON.stringify(rows));
    manifest.frames[timeframe].push({path,count:rows.length,first:rows[0][0],last:rows.at(-1)[0]});
  }
  coarse.push(...aggregateCandles(bars,'D'));
}
for(const timeframe of ['D','W','M']) {
  const rows=aggregateCandles(coarse,timeframe).map(bar=>[bar.time,bar.open,bar.high,bar.low,bar.close]);
  const path=`all-${timeframe}.json`;
  await writeFile(new URL(path,root),JSON.stringify(rows));
  manifest.frames[timeframe].push({path,count:rows.length,first:rows[0][0],last:rows.at(-1)[0]});
}
await writeFile(new URL('manifest.tmp',root),JSON.stringify(manifest));
await rename(new URL('manifest.tmp',root),new URL('manifest.json',root));
for(const name of monthFiles)await unlink(new URL(name,root));
console.log(JSON.stringify({count:manifest.count,from:new Date(manifest.first*1000).toISOString(),to:new Date(manifest.last*1000).toISOString(),months:monthFiles.length}));
