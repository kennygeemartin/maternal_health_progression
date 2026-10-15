// Cache only the application shell. Health records and API responses never enter the cache.
const CACHE = 'bloom-shell-v8';
const SHELL = ['/', '/styles.css', '/app.js', '/icon.svg', '/manifest.webmanifest', '/assets/maternal-header-v2.jpg', '/assets/fonts/manrope-latin.woff2', '/assets/fonts/manrope-latin-ext.woff2', '/assets/fonts/source-sans-3-latin.woff2', '/assets/fonts/source-sans-3-latin-ext.woff2'];
self.addEventListener('install', e => { e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL))); self.skipWaiting(); });
self.addEventListener('activate', e => { e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim())); });
self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET' || url.origin !== self.location.origin || !SHELL.includes(url.pathname)) return;
  e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
});
