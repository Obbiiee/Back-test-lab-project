import {isLocalReview} from './tickReview/LocalOrigin.js';

export function entryRoute({hostname, search}) {
  const params = new URLSearchParams(search);
  if (params.get('page') === 'account') return 'account';
  if (!isLocalReview(hostname)) return 'hosted-home';
  if (['local', 'exness'].includes(params.get('tick-alpha'))) return 'workspace';
  if (params.get('tick-review') === 'local') return 'review';
  if (params.get('trading-ux') === 'prototype') return 'prototype';
  if (params.get('legacy') === 'local') return 'legacy';
  return 'workspace';
}
