// Service worker: caches only static files (the shell); API always hits the network.
//
// index.html links to app.js/styles.css with a "?v=N" query string (see
// index.html) instead of bare paths. That's deliberate: a versioned URL is a
// guaranteed cache miss for both the browser's HTTP cache and this SW's own
// Cache Storage, so a fresh index.html (served with Cache-Control: no-cache,
// see app/main.py) always pulls the matching fresh JS/CSS on the very next
// load — even from a stuck OLD service worker that hasn't self-updated yet.
// Bump VERSION here AND in index.html together on every frontend change.
const VERSION = 31;
const CACHE = `diet-shell-v${VERSION}`;
const SHELL = ["/", "/index.html", `/styles.css?v=${VERSION}`, `/app.js?v=${VERSION}`, "/manifest.json"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  // API and non-GET requests: don't cache, go straight to the network.
  if (url.pathname.startsWith("/api/") || e.request.method !== "GET") {
    return; // Let the browser handle it by default
  }
  // Static files: cache-first, fall back to the network.
  e.respondWith(
    caches.match(e.request).then((hit) => hit || fetch(e.request))
  );
});
