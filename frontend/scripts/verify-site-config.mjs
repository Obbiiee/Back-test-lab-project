// Release gate for the public site. `node scripts/verify-site-config.mjs` reports what is missing; with --release it exits 1 until the owner has supplied
// every business fact, the price and period (equal to the server plan when BTL_BILLING_* is in the environment) and approved the three legal texts.
import {SITE} from '../src/site/siteConfig.js';

const release = process.argv.includes('--release');
const problems = [];
const need = (ok, message) => { if (!ok) problems.push(message); };
const text = value => typeof value === 'string' && value.trim().length > 2;

need(text(SITE.domain) && /^[a-z0-9.-]+\.[a-z]{2,}$/i.test(SITE.domain), 'domain (public https domain) is missing or invalid');
need(text(SITE.business.legalName), 'business.legalName is missing');
need(text(SITE.business.legalForm), 'business.legalForm is missing');
need(text(SITE.business.address), 'business.address is missing');
need(text(SITE.business.email) && /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(SITE.business.email), 'business.email is missing or invalid');
need(text(SITE.business.phone), 'business.phone is missing');
need(Number.isInteger(SITE.pro.priceIdr) && SITE.pro.priceIdr > 0, 'pro.priceIdr (integer Rupiah) is missing');
need(Number.isInteger(SITE.pro.periodDays) && SITE.pro.periodDays > 0, 'pro.periodDays is missing');
need(text(SITE.pro.taxNote), 'pro.taxNote (tax inclusive/exclusive statement) is missing');
need(SITE.pro.autoRenew === false, 'pro.autoRenew must stay false: the implementation sells one period per payment');
need(Array.isArray(SITE.payment.methods) && SITE.payment.methods.length > 0, 'payment.methods (the methods actually enabled at Midtrans) is missing');
need(Number.isInteger(SITE.refund.windowDays) && SITE.refund.windowDays >= 0, 'refund.windowDays is missing (owner decision)');
need(text(SITE.refund.conditions), 'refund.conditions is missing (owner decision)');
for (const key of ['terms', 'privacy', 'refund']) need(/^\d{4}-\d{2}-\d{2}$/.test(SITE.legalApproval[key] || ''), `legalApproval.${key} (ISO date of the owner's approval) is missing`);

const env = process.env;
if (env.BTL_BILLING_AMOUNT_IDR) need(String(SITE.pro.priceIdr) === env.BTL_BILLING_AMOUNT_IDR, `price differs from the server plan (BTL_BILLING_AMOUNT_IDR=${env.BTL_BILLING_AMOUNT_IDR})`);
if (env.BTL_BILLING_DURATION_SECONDS) need(String(SITE.pro.periodDays * 86400) === env.BTL_BILLING_DURATION_SECONDS, `period differs from the server plan (BTL_BILLING_DURATION_SECONDS=${env.BTL_BILLING_DURATION_SECONDS})`);

if (problems.length) {
  console.log(`${problems.length} item(s) still needed before a public release:`);
  for (const item of problems) console.log(' - ' + item);
  process.exit(release ? 1 : 0);
}
console.log('site configuration complete');
