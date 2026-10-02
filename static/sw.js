/* Promptya service worker — offline shell + smart caching */
const VERSION = "promptya-v5-bilingual-urls";
const STATIC_CACHE = `${VERSION}-static`;
const PAGE_CACHE = `${VERSION}-pages`;
const IMAGE_CACHE = `${VERSION}-images`;

/* Page routes are served at /en/… and /fa/…, and the unprefixed aliases still
   resolve, so this stays on "/" deliberately: the installed app should open the
   reader's own language without a redirect, and every link inside it is built
   from the active language prefix. */
const PRECACHE_URLS = [
  "/static/css/app.css",
  "/static/js/app.js",
  "/static/js/i18n.js",
  "/static/js/theme.js",
  "/static/js/nav.js",
  "/static/js/player.js",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png",
  "/static/icons/apple-touch-icon.png",
  "/static/manifest.webmanifest",
  "/offline/",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(STATIC_CACHE)
      .then((cache) => cache.addAll(PRECACHE_URLS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((key) => !key.startsWith(VERSION))
            .map((key) => caches.delete(key))
        )
      )
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);

  if (request.method !== "GET" || url.origin !== self.location.origin) return;
  /* Never cache admin or API traffic. */
  if (url.pathname.startsWith("/admin/") || url.pathname.startsWith("/api/")) return;
  /* …and never the crawler documents. robots.txt is an instruction, not a page:
     serving a stale copy means a policy change does not reach the crawlers it was
     made for. The sitemap is the same argument, and both are tiny. */
  if (url.pathname === "/robots.txt" || url.pathname.endsWith("/sitemap.xml")) return;

  // Static assets & media: cache-first (stale-while-revalidate)
  if (
    url.pathname.startsWith("/static/") ||
    url.pathname.startsWith("/media/")
  ) {
    const cacheName = url.pathname.startsWith("/media/") ? IMAGE_CACHE : STATIC_CACHE;
    event.respondWith(
      caches.open(cacheName).then(async (cache) => {
        const cached = await cache.match(request);
        const fetchPromise = fetch(request)
          .then((response) => {
            if (response.ok) cache.put(request, response.clone());
            return response;
          })
          .catch(() => cached);
        return cached || fetchPromise;
      })
    );
    return;
  }

  // Pages: network-first, fall back to cache then offline page
  event.respondWith(
    fetch(request)
      .then((response) => {
        const copy = response.clone();
        caches.open(PAGE_CACHE).then((cache) => cache.put(request, copy));
        return response;
      })
      .catch(async () => {
        const cached = await caches.match(request);
        if (cached) return cached;
        const offline = await caches.match("/offline/");
        if (offline) return offline;
        return new Response("You are offline.", {
          status: 503,
          headers: { "Content-Type": "text/plain" },
        });
      })
  );
});
