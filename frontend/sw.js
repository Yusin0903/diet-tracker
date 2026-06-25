// Service worker:只快取靜態檔(殼),API 一律走網路。
const CACHE = "diet-shell-v4";
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
  // API 與非 GET:不快取,直接走網路。
  if (url.pathname.startsWith("/api/") || e.request.method !== "GET") {
    return; // 交給瀏覽器預設處理
  }
  // 靜態檔:cache-first,失敗再打網路。
  e.respondWith(
    caches.match(e.request).then((hit) => hit || fetch(e.request))
  );
});
