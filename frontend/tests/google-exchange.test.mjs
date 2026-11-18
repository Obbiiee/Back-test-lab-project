// Regression (2026-11-18): the backend's Google exchange returns the standard bearer body ({access_token, token_type}) without schemaVersion.
// The account client must accept it and then load /api/v1/auth/me; a body without a bearer token must still be refused.
import assert from 'node:assert/strict';
import {createAccountClient} from '../src/tickAlpha/accountClient.js';

const USER = {id: 'a0000000-0000-4000-8000-000000000001', is_verified: true, is_active: true};
const json = body => ({ok: true, status: 200, headers: {get: () => null}, json: async () => body, text: async () => JSON.stringify(body)});

function clientWith(exchangeBody) {
  const calls = [];
  const fetcher = async (path) => {
    calls.push(path);
    if (path === '/api/v1/auth/google/exchange') return json(exchangeBody);
    if (path === '/api/v1/auth/me') return json(USER);
    throw new Error('unexpected ' + path);
  };
  return {client: createAccountClient({fetcher, secure: () => true}), calls};
}

const ok = clientWith({access_token: 'opaque-token', token_type: 'bearer'});
const me = await ok.client.completeGoogleLogin();
assert.equal(me.id, USER.id);
assert.ok(ok.calls.includes('/api/v1/auth/me'), 'the session must be confirmed with /api/v1/auth/me');

const bad = clientWith({token_type: 'bearer'});
await assert.rejects(() => bad.client.completeGoogleLogin(), /Unsupported Google sign-in response/);
assert.ok(!bad.calls.includes('/api/v1/auth/me'), 'no identity lookup without a bearer token');

console.log('google exchange tests passed');
