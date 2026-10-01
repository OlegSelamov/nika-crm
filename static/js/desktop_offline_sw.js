const CACHE_PREFIX = "nika-desktop-ui-";

self.addEventListener("install", event => {
  self.skipWaiting();
});

self.addEventListener("activate", event => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(
      keys
        .filter(key => key.startsWith(CACHE_PREFIX))
        .map(key => caches.delete(key))
    );

    try {
      await self.registration.unregister();
    } catch (_) {}

    const clients = await self.clients.matchAll({
      type: "window",
      includeUncontrolled: true
    });
    for (const client of clients) {
      try { client.navigate(client.url); } catch (_) {}
    }
  })());
});

self.addEventListener("fetch", () => {
  // Retired: do not intercept requests.
});
