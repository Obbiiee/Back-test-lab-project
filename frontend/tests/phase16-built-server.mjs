// Test-only local server: serves the untouched production build plus a disposable
// seed/check page. Never included in dist or the production import graph.
import http from 'node:http';
import { readFileSync, statSync, createReadStream } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const root = fileURLToPath(new URL('../dist/', import.meta.url));
const port = Number(process.argv[2] ?? 5194);
if (!Number.isInteger(port) || port < 1024 || port > 65535) throw Error('Invalid local QA port');
const malformed = '{PHASE16-CORRUPT-PRESERVE';
const legacy = JSON.stringify({initialBalance:100000,balance:100012,orders:[],positions:[],trades:[{id:'legacy-exit',side:'Buy',entry:2000,exit:2001,entryTime:60,exitTime:120,size:.1,pnl:12,notes:'Legacy العربية 日本語'}],lastTime:120});
const incomplete=JSON.parse(legacy);delete incomplete.trades[0].side;delete incomplete.trades[0].entryTime;delete incomplete.trades[0].exitTime;
const page = `<!doctype html><html><head><meta charset="UTF-8"><title>Disposable Phase 16 built-app QA</title></head><body><h1>Isolated local release QA</h1><p>This origin is disposable test data. The app below is served from dist.</p><button id="bad">Seed corrupt account and favorites</button><button id="good">Seed valid legacy account</button><button id="incomplete">Seed incomplete legacy account</button><button id="check">Check retained data</button><a href="/">Open built app</a><pre id="result"></pre><script>
const key='backtest-paper-account-v1';
document.getElementById('bad').onclick=()=>{localStorage.setItem(key,${JSON.stringify(malformed)});localStorage.setItem('backtest-favorites-v1','{}');localStorage.setItem('backtest-workspace-interval-v1','toString');localStorage.setItem('backtest-replay-time-v1','2024-06-03T12:00:00Z');location.href='/';};
document.getElementById('good').onclick=()=>{localStorage.setItem(key,${JSON.stringify(legacy)});localStorage.setItem('backtest-favorites-v1','["Trend Line","Long Position","Short Position"]');localStorage.setItem('backtest-workspace-interval-v1','15m');localStorage.setItem('backtest-replay-time-v1','2024-06-03T12:00:00Z');location.href='/';};
document.getElementById('incomplete').onclick=()=>{localStorage.setItem(key,${JSON.stringify(JSON.stringify(incomplete))});localStorage.setItem('backtest-favorites-v1','[]');localStorage.setItem('backtest-workspace-interval-v1','15m');localStorage.setItem('backtest-replay-time-v1','2024-06-03T12:00:00Z');location.href='/';};
document.getElementById('check').onclick=()=>{const raw=localStorage.getItem(key);let account;try{account=JSON.parse(raw);}catch{}document.getElementById('result').textContent=JSON.stringify({corruptAccountPreserved:raw===${JSON.stringify(malformed)},corruptFavoritesPreserved:localStorage.getItem('backtest-favorites-v1')==='{}',legacyNotes:account?.trades?.[0]?.notes,balance:account?.balance,storedLastTime:account?.lastTime},null,2);};
</script></body></html>`;
const types={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.json':'application/json; charset=utf-8','.svg':'image/svg+xml','.png':'image/png'};
readFileSync(path.join(root,'index.html')); // Require a completed build.
http.createServer((request,response)=>{
 try {
  const uri=decodeURIComponent(new URL(request.url,'http://127.0.0.1').pathname);
  if(uri==='/__qa__'){response.setHeader('Content-Type',types['.html']);response.end(page);return;}
  if(uri.includes('\\')||uri.includes(':')||uri.includes('\0'))throw Error('Invalid path');
  const asset=path.resolve(root,'.'+(uri==='/'?'/index.html':uri));
  if(!asset.startsWith(path.resolve(root)+path.sep))throw Error('Outside build');
  const stat=statSync(asset);if(!stat.isFile())throw Error('Not a file');
  response.setHeader('Content-Type',types[path.extname(asset)]??'application/octet-stream');response.setHeader('Content-Length',stat.size);createReadStream(asset).pipe(response);
 }catch{response.statusCode=404;response.end('Not found');}
}).listen(port,'127.0.0.1',()=>console.log(`Built-app QA http://127.0.0.1:${port}/ · test seed/check /__qa__`));
