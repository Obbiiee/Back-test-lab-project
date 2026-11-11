import {pathToFileURL} from 'node:url';
import {resolve,join} from 'node:path';

const root=resolve(new URL('../../',import.meta.url).pathname);
const tools=resolve(process.env.RIKSORA_BROWSER_TOOLS||join(root,'frontend/tests/browser-tools'));
const {chromium}=await import(pathToFileURL(join(tools,'node_modules/playwright/index.mjs')));
const server=await chromium.launchServer({headless:true,host:'127.0.0.1'});
process.stdout.write(JSON.stringify({wsEndpoint:server.wsEndpoint()})+'\n');
let closing=false;
const close=async()=>{
  if(closing)return;
  closing=true;
  await server.close();
  process.exit(0);
};
process.on('SIGTERM',close);
process.on('SIGINT',close);
