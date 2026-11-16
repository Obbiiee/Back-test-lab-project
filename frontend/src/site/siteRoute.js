// Route helpers for the public site (kept out of the component file so fast refresh keeps working).
export const PAGES = ['home', 'pricing', 'about', 'contact', 'terms', 'privacy', 'refund', 'account'];

export function siteLang(search) {
  const value = new URLSearchParams(search).get('lang');
  return value === 'en' ? 'en' : 'id';
}
export function sitePage(search) {
  const value = new URLSearchParams(search).get('page');
  return PAGES.includes(value) ? value : 'home';
}
