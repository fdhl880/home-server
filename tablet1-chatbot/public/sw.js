/* Bloomberg Terminal Native PWA Service Worker v20261126a */
const CACHE_NAME = 'bloomberg-terminal-shell-v20261126a';
const APP_SHELL = [
  '/',
  '/widget',
  '/manifest.webmanifest',
  '/icons/icon-192.png',
  '/icons/icon-512.png',
  '/icons/favicon-64.png',
  '/terminal/css/terminal.css?v=20261126a',
  '/terminal/vendor/lightweight-charts.standalone.production.js'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(APP_SHELL).catch(() => {}))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/terminal/ws')) return;

  event.respondWith(
    fetch(req)
      .then((resp) => {
        if (resp && resp.ok && (url.pathname.startsWith('/icons/') || url.pathname.startsWith('/terminal/fonts/') || url.pathname.startsWith('/terminal/vendor/'))) {
          const clone = resp.clone();
          caches.open(CACHE_NAME).then((c) => c.put(req, clone)).catch(() => {});
        }
        return resp;
      })
      .catch(() => caches.match(req).then((hit) => hit || caches.match('/')))
  );
});

// Background Web Push Handler (VAPID encrypted push — fires even when browser is closed)
self.addEventListener('push', (event) => {
  let data = {
    title: 'BLOOMBERG TERMINAL // ALERT',
    body: 'New institutional market or execution notification received.',
    eventType: 'ALERT',
    symbol: 'BTCUSDT',
    url: '/',
    tag: 'bloomberg-alert'
  };
  try {
    if (event.data) {
      const parsed = event.data.json();
      if (parsed && typeof parsed === 'object') data = { ...data, ...parsed };
    }
  } catch {
    try { data.body = event.data.text(); } catch {}
  }

  const options = {
    body: data.body,
    icon: '/icons/icon-192.png',
    badge: '/icons/favicon-64.png',
    tag: data.tag || 'bloomberg-alert',
    renotify: true,
    vibrate: [180, 70, 180],
    requireInteraction: /OPEN|CLOSE|BREAKER|LIMIT|URGENT/i.test(String(data.eventType || '')),
    data: { url: data.url || '/', symbol: data.symbol || 'BTCUSDT', eventType: data.eventType || 'ALERT' },
    actions: [
      { action: 'open_terminal', title: 'Open Terminal' },
      { action: 'dismiss', title: 'Dismiss' }
    ]
  };
  event.waitUntil(self.registration.showNotification(data.title, options));
});

// Instant Foreground / WebSocket OS Notification Bridge
self.addEventListener('message', (event) => {
  const msg = event.data;
  if (!msg || typeof msg !== 'object') return;
  if (msg.type === 'SHOW_NOTIFICATION' && msg.payload) {
    const p = msg.payload;
    self.registration.showNotification(p.title || 'BLOOMBERG TERMINAL', {
      body: p.body || '',
      icon: '/icons/icon-192.png',
      badge: '/icons/favicon-64.png',
      tag: p.tag || ('bloomberg-' + Date.now()),
      renotify: true,
      vibrate: [160, 60, 160],
      data: { url: p.url || '/', symbol: p.symbol || 'BTCUSDT', eventType: p.eventType || 'ALERT' }
    }).catch(() => {});
  } else if (msg.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  if (event.action === 'dismiss') return;
  const targetUrl = (event.notification && event.notification.data && event.notification.data.url) || '/';
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
      for (const client of clientList) {
        if ('focus' in client) {
          client.focus();
          try { client.navigate(targetUrl); } catch {}
          return;
        }
      }
      if (self.clients.openWindow) return self.clients.openWindow(targetUrl);
    })
  );
});
