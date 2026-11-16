// Issue #21 F08: register the app-shell service worker only for production builds served
// over HTTPS (installable PWA). Local development and QA never get a worker or cache.
export function registerShellWorker(env = import.meta.env, location = globalThis.location, navigatorRef = globalThis.navigator) {
  if (!env.PROD || location?.protocol !== 'https:' || !navigatorRef?.serviceWorker) return false;
  navigatorRef.serviceWorker.register('/sw.js', { scope: '/' }).catch(() => {});
  return true;
}
export function clearShellCache(navigatorRef = globalThis.navigator) {
  navigatorRef?.serviceWorker?.controller?.postMessage('clear-shell-cache');
}
