/**
 * @fileoverview Progressive Web App (PWA) Service Worker for Genmon.
 * Handles offline static asset caching, background Web Push notifications,
 * and notification click window focus / navigation.
 *
 * Complies with Google JavaScript Style Guide standards.
 */

/** @const {string} Current cache storage name. */
const CACHE_NAME = 'genmon-v12';

/**
 * Core assets kept for offline resilience. Navigation and dynamic API responses
 * are excluded so authentication state is always verified live.
 * @const {!Array<string>}
 */
const SHELL_ASSETS = [
  '/css/genmon.css',
  '/js/genmon.js',
  '/js/addon-icons.js',
  '/favicon.ico',
  '/icons/icon-192x192.png',
  '/icons/icon-512x512.png',
  '/manifest.webmanifest'
];

/**
 * Service Worker install event handler. Pre-caches shell assets.
 */
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return Promise.all(
        SHELL_ASSETS.map((url) =>
          cache.add(url).catch((err) =>
            console.log('SW asset caching skipped:', url, err)
          )
        )
      );
    }).then(() => self.skipWaiting())
  );
});

/**
 * Service Worker activation handler. Evicts stale caches.
 */
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

/**
 * Fetch event listener. Applies network-first strategy for static assets,
 * bypassing documents and dynamic API routes.
 */
self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;

  // Never intercept document navigations to preserve live auth state
  if (req.mode === 'navigate' || req.destination === 'document') return;

  const url = new URL(req.url);
  // API calls and dynamic commands: network only
  if (url.pathname.startsWith('/cmd/') || url.pathname.startsWith('/api/')) return;

  event.respondWith(
    fetch(req)
      .then((response) => {
        if (response && response.ok) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(req, clone)).catch(() => {});
        }
        return response;
      })
      .catch(async () => {
        const cached = await caches.match(req);
        if (cached) return cached;
        return new Response('Network unavailable or service restarting', {
          status: 503,
          statusText: 'Service Unavailable',
          headers: { 'Content-Type': 'text/plain' }
        });
      })
  );
});

/**
 * Push event listener. Receives VAPID-signed Web Push payloads from Genmon daemon.
 */
self.addEventListener('push', (event) => {
  let data = {
    title: '⚡ Genmon Alert',
    body: 'New generator notification received.',
    icon: '/icons/icon-192x192.png'
  };

  if (event.data) {
    try {
      data = event.data.json();
    } catch (e) {
      data.body = event.data.text();
    }
  }

  const options = {
    body: data.body || 'Genmon Status Update',
    icon: data.icon || '/icons/icon-192x192.png',
    badge: '/icons/icon-192x192.png',
    vibrate: [200, 100, 200, 100, 200],
    tag: 'genmon-push-alert',
    renotify: true,
    data: {
      url: data.url || '/'
    }
  };

  event.waitUntil(
    self.registration.showNotification(
      data.title || '⚡ Genmon Notification',
      options
    )
  );
});

/**
 * Notification click listener. Focuses active Genmon browser window or opens root.
 */
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const targetUrl = (event.notification.data && event.notification.data.url)
    ? event.notification.data.url
    : '/';

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((windowClients) => {
      for (let i = 0; i < windowClients.length; i++) {
        const client = windowClients[i];
        if (client.url.includes(location.host) && 'focus' in client) {
          return client.focus();
        }
      }
      if (clients.openWindow) {
        return clients.openWindow(targetUrl);
      }
    })
  );
});
