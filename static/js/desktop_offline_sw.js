const CACHE_PREFIX = "nika-desktop-ui-";
const CACHE_NAME = CACHE_PREFIX + "v3";
const CORE_PAGES = [
  "/analytics",
  "/sales",
  "/items",
  "/stock",
  "/stock/income",
  "/stock/writeoff",
  "/stock/movements",
  "/clients",
  "/profile",
  "/tasks",
  "/accounting",
  "/reports",
  "/expenses",
  "/users",
  "/settings"
];

let forcedOffline = false;

self.addEventListener("install", event => {
  self.skipWaiting();
});

self.addEventListener("activate", event => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(
      keys
        .filter(key => key.startsWith(CACHE_PREFIX) && key !== CACHE_NAME)
        .map(key => caches.delete(key))
    );
    await self.clients.claim();
  })());
});

async function cacheStaticFromHtml(html, cache) {
  const matches = html.matchAll(/(?:src|href)=["']([^"']+)["']/gi);
  const urls = new Set();
  for (const match of matches) {
    try {
      const url = new URL(match[1], self.location.origin);
      if (url.origin === self.location.origin && url.pathname.startsWith("/static/")) {
        urls.add(url.href);
      }
    } catch (_) {}
  }

  await Promise.all(Array.from(urls).map(async url => {
    try {
      const response = await fetch(url, { credentials: "include" });
      if (response.ok) await cache.put(url, response.clone());
    } catch (_) {}
  }));
}

async function cachePage(url, cache) {
  try {
    const request = new Request(url, {
      method: "GET",
      credentials: "include",
      headers: { "Accept": "text/html" }
    });
    const response = await fetch(request);
    if (!response.ok) return;

    const finalUrl = new URL(response.url);
    if (finalUrl.origin !== self.location.origin) return;
    if (finalUrl.pathname === "/login" || finalUrl.pathname.startsWith("/subscription")) return;

    const copy = response.clone();
    await cache.put(request, copy);

    const type = response.headers.get("content-type") || "";
    if (type.includes("text/html")) {
      const html = await response.clone().text();
      await cacheStaticFromHtml(html, cache);
    }
  } catch (_) {}
}

function pageVariants(paths) {
  const urls = new Set();
  for (const value of paths || []) {
    try {
      const url = new URL(value, self.location.origin);
      if (url.origin !== self.location.origin) continue;
      if (url.pathname === "/logout" || url.pathname === "/login") continue;
      url.hash = "";
      urls.add(url.pathname + url.search);
      const embedded = new URL(url.href);
      embedded.searchParams.set("nika_embedded", "1");
      urls.add(embedded.pathname + embedded.search);
    } catch (_) {}
  }
  return Array.from(urls);
}

async function prefetchPages(paths) {
  const cache = await caches.open(CACHE_NAME);
  const urls = pageVariants(paths);
  for (let i = 0; i < urls.length; i += 4) {
    await Promise.all(urls.slice(i, i + 4).map(url => cachePage(url, cache)));
  }
}

async function prefetchCore() {
  return prefetchPages(CORE_PAGES);
}

self.addEventListener("message", event => {
  const data = event.data || {};
  if (data.type === "SET_OFFLINE") {
    forcedOffline = data.offline === true;
  }
  if (data.type === "PREFETCH_CORE") {
    event.waitUntil(prefetchCore());
  }
  if (data.type === "PREFETCH_URLS") {
    event.waitUntil(prefetchPages(Array.isArray(data.urls) ? data.urls : []));
  }
  if (data.type === "CLEAR_NIKA_CACHE") {
    event.waitUntil(caches.delete(CACHE_NAME));
  }
});

async function fetchWithTimeout(request, timeoutMs = 1800) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(new Request(request, { signal: controller.signal }));
  } finally {
    clearTimeout(timer);
  }
}

async function matchCachedPage(request, cache) {
  let cached = await cache.match(request);
  if (cached) return cached;
  try {
    const url = new URL(request.url);
    const embedded = url.searchParams.get("nika_embedded") === "1";
    url.search = embedded ? "?nika_embedded=1" : "";
    url.hash = "";
    cached = await cache.match(new Request(url.href, {
      method: "GET",
      credentials: "include",
      headers: { "Accept": "text/html" }
    }));
    return cached || null;
  } catch (_) {
    return null;
  }
}

async function networkFirst(request) {
  const cache = await caches.open(CACHE_NAME);
  const cached = await matchCachedPage(request, cache);

  if (forcedOffline && cached) return cached;
  if (self.navigator && self.navigator.onLine === false && cached) return cached;

  try {
    const response = await fetchWithTimeout(request, 1400);
    if (response && response.ok) {
      const finalUrl = new URL(response.url);
      if (
        finalUrl.origin === self.location.origin &&
        finalUrl.pathname !== "/login" &&
        !finalUrl.pathname.startsWith("/subscription")
      ) {
        await cache.put(request, response.clone());
      }
    }
    return response;
  } catch (_) {
    if (cached) return cached;
    throw _;
  }
}

async function cacheFirst(request) {
  const cache = await caches.open(CACHE_NAME);
  const cached = await cache.match(request);
  if (cached) return cached;

  if (forcedOffline) {
    throw new Error("offline");
  }
  const response = await fetchWithTimeout(request, 1400);
  if (response && response.ok) {
    await cache.put(request, response.clone());
  }
  return response;
}

self.addEventListener("fetch", event => {
  const request = event.request;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/api/")) return;

  if (url.pathname === "/logout") {
    event.respondWith((async () => {
      try {
        const response = await fetch(request);
        await caches.delete(CACHE_NAME);
        return response;
      } catch (error) {
        await caches.delete(CACHE_NAME);
        throw error;
      }
    })());
    return;
  }

  if (url.pathname.startsWith("/static/")) {
    event.respondWith(cacheFirst(request));
    return;
  }

  const acceptsHtml = (request.headers.get("accept") || "").includes("text/html");
  if (request.mode === "navigate" || acceptsHtml) {
    event.respondWith(networkFirst(request));
  }
});
