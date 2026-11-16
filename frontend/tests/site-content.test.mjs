// Public-site honesty and consistency checks: claims have evidence in the repo, no profit promises, both languages cover the same sections,
// the Free limits shown equal the backend constants, legal pages carry only known placeholders.
import assert from 'node:assert/strict';
import {existsSync, readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {dirname, resolve} from 'node:path';
import {COPY, CLAIMS, fill, LANGS} from '../src/site/content.js';
import {FREE_LIMITS, RESET, formatIdr, activePromo, currentPrice} from '../src/site/plans.js';
import {SITE} from '../src/site/siteConfig.js';
import {entryRoute} from '../src/entryRoute.js';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');

// 1. every differentiator names evidence that exists in the repository
assert.ok(CLAIMS.length >= 6);
for (const claim of CLAIMS) {
  assert.ok(claim.key && claim.evidence.length >= 1, claim.key);
  for (const path of claim.evidence) assert.ok(existsSync(resolve(root, path)), `${claim.key}: evidence missing: ${path}`);
  for (const lang of LANGS) assert.ok(claim[lang]?.t?.length > 5 && claim[lang]?.d?.length > 20, `${claim.key}/${lang}`);
}

// 2. both languages cover the same marketing sections and list lengths
const shape = value => Array.isArray(value) ? value.map(shape) : value && typeof value === 'object' ? Object.fromEntries(Object.keys(value).sort().map(k => [k, shape(value[k])])) : typeof value;
for (const key of ['nav', 'hero', 'purpose', 'how', 'plans', 'limits', 'faq', 'pricing', 'about', 'contact', 'footer']) {
  assert.deepEqual(shape(COPY.id[key]), shape(COPY.en[key]), `id/en structure differs in ${key}`);
}

// 3. no profit promises, no real-money or broker claims; required disclaimers present
const everything = JSON.stringify([COPY, CLAIMS]).toLowerCase();
for (const banned of ['guaranteed profit', 'guaranteed return', 'risk-free', 'risk free', 'dijamin untung', 'pasti untung', 'pasti profit', 'bebas risiko', 'passive income', 'penghasilan pasif', '100% accurate', '100% akurat', 'beat the market', 'kalahkan pasar', 'get rich quick', 'get-rich-quick', 'cepat kaya', 'kaya cepat', 'easy money', 'uang mudah']) {
  assert.ok(!everything.includes(banned), `banned phrase: ${banned}`);
}
assert.match(COPY.id.hero.caption, /bukan nasihat investasi/i);
assert.match(COPY.en.hero.caption, /not investment advice/i);
assert.match(COPY.id.footer.disclaimer, /bukan nasihat investasi/i);
assert.match(COPY.en.footer.disclaimer, /not investment advice/i);
assert.ok(COPY.id.limits.items.some(item => /simulasi/i.test(item) && /broker/i.test(item)));

// 4. Free/Pro rules equal the backend constants and the reset time is stated correctly
const backend = readFileSync(resolve(root, 'backend/cloud/entitlements.py'), 'utf8');
const match = backend.match(/FREE_LIMITS\s*=\s*\{"SESSION":\s*(\d+),\s*"WINDOW":\s*(\d+)\}/);
assert.ok(match, 'backend FREE_LIMITS not found');
assert.equal(FREE_LIMITS.SESSION, Number(match[1])); assert.equal(FREE_LIMITS.WINDOW, Number(match[2]));
assert.equal(RESET.wibClock, '07.00 WIB');
assert.ok(COPY.id.pricing.free.features[0].includes(String(FREE_LIMITS.SESSION)) && COPY.id.pricing.free.features[1].includes(String(FREE_LIMITS.WINDOW)));
assert.ok(COPY.id.pricing.rules.some(rule => rule.includes('00.00 UTC') && rule.includes('07.00 WIB')));

// 5. currency formatting is Rupiah, integers only
assert.equal(formatIdr(99000), 'Rp 99.000');
assert.equal(formatIdr(0), 'Rp 0');
assert.equal(formatIdr(null), null);
assert.equal(formatIdr(9.5), null);

// 6. legal text uses only known placeholders; unknown {{tokens}} would leak to users
for (const page of ['terms', 'privacy', 'refund']) {
  for (const [heading, paragraphs] of COPY.id[page].sections) {
    assert.ok(heading && paragraphs.length >= 1);
    for (const text of paragraphs) {
      const filled = fill(text, SITE);
      assert.ok(!/\{\{[^}]+\}\}/.test(filled), `unresolved placeholder in ${page}: ${text}`);
    }
  }
}
assert.match(fill('{{brand}} {{legalName}}', {brand: 'B', business: {legalName: 'PT X'}, domain: 'd', refund: {}}), /B PT X/);

// 7. routing: hosted visitors reach the public site; the account page keeps working; local review pages stay local
assert.equal(entryRoute({hostname: 'riksora.example', search: ''}), 'site');
assert.equal(entryRoute({hostname: 'riksora.example', search: '?page=pricing'}), 'site');
assert.equal(entryRoute({hostname: 'riksora.example', search: '?page=account'}), 'account');
assert.equal(entryRoute({hostname: 'riksora.example', search: '?legacy=local'}), 'site');

// 8. the config never contains a made-up price: it is null or a positive integer
for (const period of ['monthly', 'yearly']) {
  assert.ok(Number.isInteger(SITE.pro[period].priceIdr) && SITE.pro[period].priceIdr > 0 && Number.isInteger(SITE.pro[period].periodDays));
}
assert.equal(SITE.pro.yearly.priceIdr, SITE.pro.monthly.priceIdr * 12, 'yearly list price is 12 x monthly');
assert.equal(SITE.pro.monthly.periodDays, 30); assert.equal(SITE.pro.yearly.periodDays, 365);
// promotion: shown only inside its dated window; the list price is shown only when a promotion really lowers the price
const withPromo = (startsOn, endsOn) => ({pro: {...SITE.pro, promo: {monthlyIdr: 87000, yearlyIdr: 400000, startsOn, endsOn}}});
assert.equal(activePromo(withPromo(null, null), '2026-12-01'), null);
assert.equal(activePromo(withPromo('2026-12-01', '2026-12-31'), '2026-11-30'), null);
assert.equal(activePromo(withPromo('2026-12-01', '2026-12-31'), '2027-01-01'), null);
assert.ok(activePromo(withPromo('2026-12-01', '2026-12-31'), '2026-12-15'));
assert.deepEqual(currentPrice(withPromo(null, null), 'monthly', '2026-12-15'), {priceIdr: 137000, listPriceIdr: null, savingPercent: 0, periodDays: 30, endsOn: null});
const promoted = currentPrice(withPromo('2026-12-01', '2026-12-31'), 'monthly', '2026-12-15');
assert.deepEqual([promoted.priceIdr, promoted.listPriceIdr, promoted.savingPercent], [87000, 137000, 36]);
assert.equal(currentPrice(withPromo('2026-12-01', '2026-12-31'), 'yearly', '2026-12-15').priceIdr, 400000);
// a promotion that does not lower the price is ignored, never displayed as a discount
assert.equal(currentPrice({pro: {...SITE.pro, promo: {monthlyIdr: 137000, yearlyIdr: 1644000, startsOn: '2026-12-01', endsOn: '2026-12-31'}}}, 'monthly', '2026-12-15').listPriceIdr, null);
assert.equal(SITE.pro.autoRenew, false);
console.log('site content tests passed');
