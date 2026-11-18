// Free/Pro rules shown to users. Single source for the site; the numbers mirror backend/cloud/entitlements.py (FREE_LIMITS) and a test keeps them equal.
// Rules: Free = one NEW Session per UTC day (each Session uses one month of data; owner decision 2026-11-18, was per calendar month) and one NEWLY ACTIVATED historical month per UTC day. Continuing a Session or re-using an
// already activated month consumes nothing. Pro = no quota on new Sessions or newly activated months (still recorded). Tier comes only from a paid,
// unexpired server-side order. Reset time is UTC: 00:00 UTC = 07:00 WIB.
export const FREE_LIMITS = {SESSION: 1, WINDOW: 1};
export const RESET = {zone: 'UTC', wibClock: '07.00 WIB'};
export const INCLUDED_IN_BOTH = ['replay', 'orders', 'jump', 'journal', 'analytics', 'export'];
export function formatIdr(value) {
  return typeof value === 'number' && Number.isInteger(value) && value >= 0 ? 'Rp ' + value.toLocaleString('id-ID') : null;
}

// Promotion window: the promo price is shown only when both dates are set and today (UTC, ISO date) falls inside [startsOn, endsOn].
export function activePromo(site, todayIso) {
  const promo = site.pro.promo;
  if (!promo || !/^\d{4}-\d{2}-\d{2}$/.test(promo.startsOn || '') || !/^\d{4}-\d{2}-\d{2}$/.test(promo.endsOn || '')) return null;
  if (todayIso < promo.startsOn || todayIso > promo.endsOn) return null;
  return promo;
}
// What a customer pays for one period right now, and the list price when a promotion lowers it.
export function currentPrice(site, period, todayIso) {
  const plan = site.pro[period];
  if (!plan || !Number.isInteger(plan.priceIdr)) return null;
  const promo = activePromo(site, todayIso);
  const promoPrice = promo ? promo[period === 'monthly' ? 'monthlyIdr' : 'yearlyIdr'] : null;
  if (Number.isInteger(promoPrice) && promoPrice < plan.priceIdr) {
    return {priceIdr: promoPrice, listPriceIdr: plan.priceIdr, savingPercent: Math.round(100 * (plan.priceIdr - promoPrice) / plan.priceIdr), periodDays: plan.periodDays, endsOn: promo.endsOn};
  }
  return {priceIdr: plan.priceIdr, listPriceIdr: null, savingPercent: 0, periodDays: plan.periodDays, endsOn: null};
}

// Honest comparison from the prices actually charged: how much cheaper the yearly period is than twelve monthly payments (0 when it is not cheaper).
export function yearlySavingPercent(site) {
  const monthly = site.pro.monthly.priceIdr, yearly = site.pro.yearly.priceIdr;
  if (!Number.isInteger(monthly) || !Number.isInteger(yearly) || monthly <= 0) return 0;
  const twelve = monthly * 12;
  return yearly < twelve ? Math.round(100 * (twelve - yearly) / twelve) : 0;
}
