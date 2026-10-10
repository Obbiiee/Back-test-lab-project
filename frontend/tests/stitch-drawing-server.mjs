// Isolated, loopback-only S-1 fixture host. No market-data or API routes.
import {createServer} from 'node:http';
import {readFileSync} from 'node:fs';
import {resolve,sep} from 'node:path';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('..',import.meta.url));
const donorRoot=process.env.BTL_SPIKE_DONOR_ROOT;
const routes=new Map([
  ['/',resolve(root,'tests/browser/stitch-drawing.html')],
  ['/lc.js',resolve(root,'node_modules/lightweight-charts/dist/lightweight-charts.standalone.production.js')],
  ...(donorRoot?[
    ['/openalgo.mjs',resolve(donorRoot,'openalgo-charts-prepared.mjs')],
    ['/opencharts.mjs',resolve(donorRoot,'OpenCharts-prepared.mjs')],
  ]:[]),
]);
createServer((req,res)=>{
  const url=new URL(req.url,'http://127.0.0.1'); let file=routes.get(url.pathname);
  if(url.pathname.startsWith('/src/')){
    const candidate=resolve(root,'.'+decodeURIComponent(url.pathname));
    if(candidate.startsWith(resolve(root,'src')+sep)&&candidate.endsWith('.js'))file=candidate;
  }
  if(req.method!=='GET'||!file){res.writeHead(404);res.end();return;}
  try{res.setHeader('Content-Type',file.endsWith('.html')?'text/html':'text/javascript');res.setHeader('Cache-Control','no-store');res.end(readFileSync(file));}
  catch{res.writeHead(404);res.end();}
}).listen(5204,'127.0.0.1',()=>console.log('S-1 authored drawing fixtures http://127.0.0.1:5204/'));
