// Account plan panel helpers: redirect allow-list, entitlement summary, Rupiah offer. Pure functions, no browser.
import assert from 'node:assert/strict';
import {isPaymentRedirect, planSummary, planOffer, formatRupiah, periodDays} from '../src/tickAlpha/accountPlan.js';

// the payment redirect is Midtrans over HTTPS or nothing
assert.equal(isPaymentRedirect('https://app.sandbox.midtrans.com/snap/v4/redirection/abc'), true);
assert.equal(isPaymentRedirect('https://app.midtrans.com/snap/v2/vtweb/abc'), true);
for (const bad of ['http://app.midtrans.com/snap/v2/x', 'https://app.midtrans.com.evil.example/snap/v2/x', 'https://evil.example/https://app.midtrans.com/snap/v2/x',
  'javascript:alert(1)', 'https://app.midtrans.com@evil.example/snap/v2/x', '//app.midtrans.com/snap/v2/x', '', null, undefined, 42, 'https://app.midtrans.com/other/x',
  'https://app.midtrans.com/snap/v2/' + 'a'.repeat(3000)]) assert.equal(isPaymentRedirect(bad), false, String(bad));

// entitlement summary: only the documented artifact; unknown shapes are "not known", never guessed
const free = planSummary({schemaVersion: 1, artifact: 'BTL-ENTITLEMENT-STATUS-1', tier: 'FREE', sessions: {limit: 1, used: 1, resetsAt: '2026-12-01T00:00:00+00:00'}, windows: {limit: 1, used: 0, resetsAt: '2026-11-17T00:00:00+00:00'}});
assert.deepEqual([free.known, free.tier, free.pro, free.sessions.used, free.sessions.limit, free.windows.used], [true, 'FREE', false, 1, 1, 0]);
const pro = planSummary({schemaVersion: 1, artifact: 'BTL-ENTITLEMENT-STATUS-1', tier: 'PRO', sessions: {limit: null, used: 3, resetsAt: 'x'}, windows: {limit: null, used: 2, resetsAt: 'y'}});
assert.deepEqual([pro.known, pro.pro, pro.sessions.limit], [true, true, null]);
for (const bad of [null, {}, {schemaVersion: 1, artifact: 'OTHER', tier: 'PRO'}, {schemaVersion: 1, artifact: 'BTL-ENTITLEMENT-STATUS-1', tier: 'GOLD'}, {schemaVersion: 2, artifact: 'BTL-ENTITLEMENT-STATUS-1', tier: 'PRO'}]) assert.deepEqual(planSummary(bad), {known: false});
assert.equal(planSummary({schemaVersion: 1, artifact: 'BTL-ENTITLEMENT-STATUS-1', tier: 'FREE', sessions: {used: -1, limit: 1.5}}).sessions.used, null);

// Rupiah offer: integers only; the period must be whole days; test mode is disclosed
assert.equal(formatRupiah('99000'), 'Rp 99.000'); assert.equal(formatRupiah('9.5'), null); assert.equal(formatRupiah('-1'), null);
assert.equal(periodDays('2592000'), 30); assert.equal(periodDays('100'), null);
assert.deepEqual(planOffer({schemaVersion: 1, mode: 'SANDBOX', fundsCollected: false, amountIdr: '99000', durationSeconds: '2592000'}), {price: 'Rp 99.000', days: 30, testMode: true});
assert.equal(planOffer({schemaVersion: 1, mode: 'LIVE', fundsCollected: true, amountIdr: '99000', durationSeconds: '2592000'}).testMode, false);
assert.equal(planOffer({schemaVersion: 1, amountIdr: 'abc', durationSeconds: '2592000'}), null);
assert.equal(planOffer(null), null);
console.log('account plan tests passed');
