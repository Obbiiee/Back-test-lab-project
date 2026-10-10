// Loopback-only authored fixture; no data/controller/backend routes.
import {createServer} from 'node:http';
import {readFileSync} from 'node:fs';
const routes = new Map([
  ['/', new URL('./browser/alpha-drawing-spike.html',import.meta.url)],
  ['/donor.js', new URL('./artifacts/alpha-drawing-051.mjs',import.meta.url)],
  ['/lc.js', new URL('../node_modules/lightweight-charts/dist/lightweight-charts.standalone.production.js',import.meta.url)],
  ['/coords.js',new URL('../src/drawings/timeCoordinates.js',import.meta.url)],
]);
createServer((req,res)=>{
  const file=routes.get(new URL(req.url,'http://127.0.0.1').pathname);
  if(req.method!=='GET'||!file){res.writeHead(404);res.end();return;}
  try{res.setHeader('Content-Type',file.pathname.endsWith('.html')?'text/html':'text/javascript');res.end(readFileSync(file));}
  catch{res.writeHead(404);res.end();}
}).listen(5206,'127.0.0.1',()=>console.log('Supplemental authored fixture http://127.0.0.1:5206/'));
