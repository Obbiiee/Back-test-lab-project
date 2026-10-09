// Read-only isolated fixture routes, no API, provider or disk-access capabilities.
import {createServer} from 'node:http';
import {readFileSync} from 'node:fs';
const routes=new Map([['/',new URL('./browser/stitch-indicators.html',import.meta.url)],['/host.mjs',new URL('./artifacts/stitch-indicator-host.mjs',import.meta.url)],['/lc.js',new URL('../node_modules/lightweight-charts/dist/lightweight-charts.standalone.production.js',import.meta.url)]]);
createServer((req,res)=>{const file=routes.get(new URL(req.url,'http://127.0.0.1').pathname);if(req.method!=='GET'||!file){res.writeHead(404);res.end();return;}try{res.setHeader('Content-Type',String(file).endsWith('.html')?'text/html':'text/javascript');res.setHeader('Cache-Control','no-store');res.end(readFileSync(file));}catch{res.writeHead(404);res.end();}}).listen(5205,'127.0.0.1',()=>console.log('S-3 http://127.0.0.1:5205/'));
