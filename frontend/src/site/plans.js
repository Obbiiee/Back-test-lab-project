// Free/Pro rules shown to users. Single source for the site; the numbers mirror backend/cloud/entitlements.py (FREE_LIMITS) and a test keeps them equal.
// Rules: Free = one NEW Session per UTC calendar month and one NEWLY ACTIVATED historical month per UTC day. Continuing a Session or re-using an
// already activated month consumes nothing. Pro = no quota on new Sessions or newly activated months (still recorded). Tier comes only from a paid,
// unexpired server-side order. Reset time is UTC: 00:00 UTC = 07:00 WIB.
export const FREE_LIMITS = {SESSION: 1, WINDOW: 1};
export const RESET = {zone: 'UTC', wibClock: '07.00 WIB'};
export const INCLUDED_IN_BOTH = ['replay', 'orders', 'jump', 'journal', 'analytics', 'export'];
export function formatIdr(value) {
  return typeof value === 'number' && Number.isInteger(value) && value >= 0 ? 'Rp ' + value.toLocaleString('id-ID') : null;
}
