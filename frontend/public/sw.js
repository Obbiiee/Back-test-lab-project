/* RIKSORA PWA service worker (Issue #21 F08): app-shell only.
   Caches the HTML shell and hashed build assets so the app opens and can show an
   offline notice. It never caches API, auth, market or ledger responses: anything
   that is not a same-origin GET for the shell or /assets/ goes straight to the network. */
const CACHE = 'riksora-shell-v1';
const SHELL = ['/', '/manifest.webmanifest', '/icons/riksora-192.png', '/icons/riksora-512.png'];
self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key !== CACHE).map(key => caches.delete(key)))).then(() => self.clients.claim()));
});
const isShellAsset = url => url.pathname.startsWith('/assets/') || url.pathname.startsWith('/icons/') || url.pathname === '/manifest.webmanifest';
self.addEventListener('fetch', event => {
  const request = event.request;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return; // API/auth hosts are never intercepted
  if (request.mode === 'navigate') {
    // Network first so a signed-in page is always fresh; the cached shell is only an offline fallback.
    event.respondWith(fetch(request).catch(() => caches.match('/')));
    return;
  }
  if (!isShellAsset(url)) return;
  event.respondWith(caches.match(request).then(hit => hit || fetch(request).then(response => {
    if (response.ok && response.type === 'basic') { const copy = response.clone(); caches.open(CACHE).then(cache => cache.put(request, copy)); }
    return response;
  })));
});
self.addEventListener('message', event => {
  if (event.data === 'clear-shell-cache') event.waitUntil(caches.delete(CACHE)); // used on sign-out
});
