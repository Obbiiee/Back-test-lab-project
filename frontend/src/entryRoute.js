import {isLocalReview} from './tickReview/LocalOrigin.js';
import {SITE} from './site/siteConfig.js';

// The local stack (deploy/local/dev_stack.py) serves the full product on https://localhost and builds the frontend with VITE_HOSTED_ENTRY=1, so the
// landing and the account entry behave exactly as on riksora.com instead of opening the legacy private local workspace.
const hostedEverywhere = () => import.meta.env?.VITE_HOSTED_ENTRY === '1';

export function entryRoute({hostname, search, pathname = '/'}) {
  const params = new URLSearchParams(search);
  if (params.get('page') === 'account') return !isLocalReview(hostname) && SITE.launchState === 'preview' ? 'site' : 'account';   // preview: the public app is not open, show the beta notice
  // Protected QA preview on the production origin (Caddy Basic Auth on /preview/): the account entry (Google sign-in, then the workspace with the production API).
  // The public site at / is unchanged. Remove after the production route is verified.
  if ((pathname === '/preview' || pathname.startsWith('/preview/')) && !params.get('page')) return 'account';   // /preview/?page=home etc. still render the public site for design review
  if (!isLocalReview(hostname) || hostedEverywhere()) return 'site';               // hosted: public landing, pricing, about, contact and legal pages
  if (['local', 'exness'].includes(params.get('tick-alpha'))) return 'workspace';
  if (params.get('tick-review') === 'local') return 'review';
  if (params.get('trading-ux') === 'prototype') return 'prototype';
  if (params.get('legacy') === 'local') return 'legacy';
  return 'workspace';
}
