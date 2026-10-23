// Server rendering is a composition check, not desktop/phone browser acceptance.
import assert from 'node:assert/strict';
import {mkdtemp,rm} from 'node:fs/promises';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {build} from 'vite';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
const directory=await mkdtemp(resolve('node_modules/.riksora-render-'));
const before=globalThis.location;
try {
  await build({logLevel:'silent',build:{ssr:true,rollupOptions:{input:['src/beta/BetaAccount.jsx','src/tickAlpha/AlphaHome.jsx']},outDir:directory,emptyOutDir:true}});
  globalThis.location={protocol:'https:',search:'',hostname:'riksora.com'};
  const {default:Account}=await import(pathToFileURL(resolve(directory,'BetaAccount.js')).href);
  const google=renderToStaticMarkup(React.createElement(Account,{googleOnly:true,entryPath:'/login/'}));
  assert.match(google,/Sign in to RIKSORA/);
  assert.match(google,/16 synthetic demo pairs/);
  assert.match(google,/Email registration and payments are unavailable/);
  assert.doesNotMatch(google,/name="password"|name="email"|Forgot password|Create account/);
  globalThis.location={protocol:'http:',search:'',hostname:'localhost'};
  const insecure=renderToStaticMarkup(React.createElement(Account,{googleOnly:true}));
  assert.match(insecure,/Open the secure Beta address/);
  assert.doesNotMatch(insecure,/name="password"|Create workspace/);
  globalThis.location={protocol:'https:',search:'',hostname:'riksora.com'};
  const {default:Home}=await import(pathToFileURL(resolve(directory,'AlphaHome.js')).href);
  const home=renderToStaticMarkup(React.createElement(Home,{hostedPreview:true}));
  assert.match(home,/16 short synthetic demo pairs/);
  assert.match(home,/16-pair Beta sandbox/);
  assert.match(home,/href="\/login\/"/);
  assert.doesNotMatch(home,/Explore all features|view=features/);
  assert.doesNotMatch(home,/Replay real bid\/ask ticks|Local Alpha|href="http:\/\/127/);
  console.log('PASS repository landing rendering and canonical account links; no invented feature-directory step.');
  console.log('PASS Google-only SSR composition: existing account owner, synthetic disclosure, no password/register form, HTTP denied. Not browser acceptance.');
} finally {
  globalThis.location=before;
  await rm(directory,{recursive:true,force:true});
}
