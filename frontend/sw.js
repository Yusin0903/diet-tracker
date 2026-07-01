// Service worker: caches only static files (the shell); API always hits the network.
const CACHE = "diet-shell-v25";
const SHELL = ["/", "/index.html", "/styles.css", "/app.js", "/manifest.json"];

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
