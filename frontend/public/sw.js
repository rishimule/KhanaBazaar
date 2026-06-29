// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
// Khana Bazaar — Service Worker
// Provides offline-capable PWA shell caching.

const CACHE_NAME = "khanabazaar-v4";
const SHELL_ASSETS = [
  "/",
  "/manifest.webmanifest",
];

// Install: pre-cache the app shell
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL_ASSETS))
  );
  self.skipWaiting();
});

// Activate: clean up old caches
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => key !== CACHE_NAME)
          .map((key) => caches.delete(key))
      )
    )
  );
  self.clients.claim();
});

// Fetch: network-first for navigations, cache-first for static assets
self.addEventListener("fetch", (event) => {
  const { request } = event;

  // Skip non-GET requests and cross-origin requests
  if (request.method !== "GET" || !request.url.startsWith(self.location.origin)) {
    return;
  }

  // Never intercept API calls. Per-customer data (carts, comparisons,
  // sessions) must never be served from cache to a different visitor on
  // the same device.
  const url = new URL(request.url);
  if (url.pathname.startsWith("/api/")) {
    return;
  }

  // Navigation requests: network-first
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request).catch(() => caches.match("/"))
    );
    return;
  }

  // Static assets: stale-while-revalidate — serve the cached copy instantly,
  // then refresh it in the background so a deploy's new assets are picked up
  // without a manual cache-name bump (avoids serving stale chunks indefinitely).
  event.respondWith(
    caches.open(CACHE_NAME).then((cache) =>
      cache.match(request).then((cached) => {
        const network = fetch(request)
          .then((response) => {
            if (response && response.status === 200 && response.type === "basic") {
              cache.put(request, response.clone());
            }
            return response;
          })
          .catch(() => cached);
        return cached || network;
      })
    )
  );
});

// --- Web Push (order notifications) ---
self.addEventListener("push", (event) => {
  let payload = {};
  try {
    payload = event.data ? event.data.json() : {};
  } catch {
    payload = {};
  }
  const title = payload.title || "Khana Bazaar";
  const body = payload.body || "You have an order update.";
  const url = payload.url || "/account/orders";

  event.waitUntil(
    (async () => {
      await self.registration.showNotification(title, {
        body,
        icon: "/icons/icon-192x192.png",
        badge: "/icons/icon-192x192.png",
        data: { url },
      });
      // Tell any open app tab to refetch the notification feed.
      try {
        const bc = new BroadcastChannel("kb-notifications");
        bc.postMessage({ type: "order-status" });
        bc.close();
      } catch {
        /* BroadcastChannel unsupported — bell refreshes on next focus */
      }
    })()
  );
});

// Focus an existing tab if present, otherwise open the deep link.
self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url =
    (event.notification.data && event.notification.data.url) || "/account/orders";
  event.waitUntil(
    clients
      .matchAll({ type: "window", includeUncontrolled: true })
      .then((windowClients) => {
        for (const client of windowClients) {
          if ("focus" in client) {
            // client.navigate is unsupported on some older browsers — fall
            // back to opening a fresh window if it throws.
            try {
              if ("navigate" in client) client.navigate(url);
            } catch {
              return clients.openWindow(url);
            }
            return client.focus();
          }
        }
        return clients.openWindow(url);
      })
  );
});

// Re-subscribe transparently if the push service rotates the subscription.
self.addEventListener("pushsubscriptionchange", (event) => {
  event.waitUntil(
    (async () => {
      try {
        const bc = new BroadcastChannel("kb-notifications");
        bc.postMessage({ type: "subscription-change" });
        bc.close();
      } catch {
        /* no-op */
      }
    })()
  );
});
