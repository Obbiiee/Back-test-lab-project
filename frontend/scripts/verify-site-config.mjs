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
// business.phone is optional: contact by email only is accepted (a phone number is still recommended for payment-gateway reviewers)
for (const period of ['monthly', 'yearly']) {
  need(Number.isInteger(SITE.pro[period].priceIdr) && SITE.pro[period].priceIdr > 0, `pro.${period}.priceIdr (integer Rupiah) is missing`);
  need(Number.isInteger(SITE.pro[period].periodDays) && SITE.pro[period].periodDays > 0, `pro.${period}.periodDays is missing`);
}
const promo = SITE.pro.promo;
if (promo && (promo.startsOn || promo.endsOn)) {
  need(/^\d{4}-\d{2}-\d{2}$/.test(promo.startsOn || '') && /^\d{4}-\d{2}-\d{2}$/.test(promo.endsOn || '') && promo.startsOn <= promo.endsOn, 'promo needs a valid startsOn <= endsOn');
  need(promo.monthlyIdr < SITE.pro.monthly.priceIdr && promo.yearlyIdr < SITE.pro.yearly.priceIdr, 'promo prices must be lower than the list prices');
}
const live = SITE.launchState === 'live';     // purchases open: tax statement, payment methods and the server-plan match become mandatory
if (live) need(text(SITE.pro.taxNote), 'pro.taxNote (tax inclusive/exclusive statement) is missing');
need(SITE.pro.autoRenew === false, 'pro.autoRenew must stay false: the implementation sells one period per payment');
if (live) need(Array.isArray(SITE.payment.methods) && SITE.payment.methods.length > 0, 'payment.methods (the methods actually enabled at Midtrans) is missing');
need(Number.isInteger(SITE.refund.windowDays) && SITE.refund.windowDays >= 0, 'refund.windowDays is missing (owner decision)');
need(text(SITE.refund.conditions), 'refund.conditions is missing (owner decision)');
for (const key of ['terms', 'privacy', 'refund']) need(/^\d{4}-\d{2}-\d{2}$/.test(SITE.legalApproval[key] || ''), `legalApproval.${key} (ISO date of the owner's approval) is missing`);

// Server plans: the checkout charges exactly what the server is configured with. The server supports ONE plan today (BTL_BILLING_AMOUNT_IDR + BTL_BILLING_DURATION_SECONDS),
// so a site that sells two periods cannot be released until the server offers both (BTL_BILLING_PLANS, not implemented yet) or the second period is removed.
const env = process.env;
if (!live) {
  // preview: nothing can be bought, so the server plans are not compared yet
} else if (env.BTL_BILLING_PLANS) {
  let plans = [];
  try { plans = JSON.parse(env.BTL_BILLING_PLANS); } catch { need(false, 'BTL_BILLING_PLANS is not valid JSON'); }
  for (const period of ['monthly', 'yearly']) {
    const hit = Array.isArray(plans) && plans.find(plan => Number(plan.durationSeconds) === SITE.pro[period].periodDays * 86400);
    need(hit && Number(hit.amountIdr) === (SITE.pro[period].priceIdr), `server plan for ${period} is missing or its price differs from the site`);
  }
} else if (env.BTL_BILLING_AMOUNT_IDR || env.BTL_BILLING_DURATION_SECONDS) {
  need(false, 'the server is configured with ONE plan; the site sells a monthly and a yearly period. Implement multi-plan billing first or sell one period only');
} else {
  need(false, 'cannot compare with the server plan: BTL_BILLING_PLANS (or the legacy single-plan variables) is not set in this environment');
}

if (problems.length) {
  console.log(`${problems.length} item(s) still needed before a public release:`);
  for (const item of problems) console.log(' - ' + item);
  process.exit(release ? 1 : 0);
}
console.log('site configuration complete');
