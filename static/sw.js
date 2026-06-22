const CACHE_NAME = 'hatiapp-v15';

// Static assets to precache on install
const PRECACHE_URLS = [
  '/static/manifest.json',
  '/static/favicon.svg',
  '/static/icon-192.png',
  '/static/icon-512.png',
  '/static/tailwind.min.js',
];

// HTML pages that should be available offline
const OFFLINE_PAGES = [
  '/',
  '/schedule',
  '/me',
  '/leader',
  '/announcements',
  '/profile',
  '/chat',
  '/logs',
  '/admin',
  '/slots',
];

function isOfflinePage(url) {
  if (url.pathname === '/') return true;
  if (OFFLINE_PAGES.includes(url.pathname)) return true;
  if (url.pathname.startsWith('/leader/')) return true;
  if (url.pathname.startsWith('/a/')) return true;
  return false;
}

function isStatic(url) {
  return url.pathname.startsWith('/static/') || url.pathname === '/api/theme.css';
}

function isApi(url) {
  return url.pathname.startsWith('/api/') || url.pathname.startsWith('/sse/');
}

// Install - precache static shell
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(PRECACHE_URLS))
      .then(() => self.skipWaiting())
  );
});

// Activate - clean old caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) =>
      Promise.all(
        cacheNames
          .filter((name) => name.startsWith('hatiapp-') && name !== CACHE_NAME)
          .map((name) => caches.delete(name))
      )
    ).then(() => self.clients.claim())
  );
});

// Offline fallback HTML
const OFFLINE_HTML = `<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Нет связи · Hatiapp</title>
  <style>
    * { box-sizing: border-box; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f3f4f6; margin: 0; min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 16px; }
    .box { background: white; border-radius: 16px; padding: 32px 24px; max-width: 400px; width: 100%; text-align: center; box-shadow: 0 10px 15px -3px rgba(0,0,0,0.1); }
    .icon { font-size: 56px; margin-bottom: 16px; }
    h1 { margin: 0 0 8px 0; font-size: 22px; color: #111827; }
    p { color: #6b7280; margin-bottom: 24px; line-height: 1.5; font-size: 15px; }
    button { width: 100%; background: #4f46e5; color: white; border: none; padding: 12px; border-radius: 8px; font-size: 16px; cursor: pointer; margin-bottom: 10px; font-family: inherit; }
    button:hover { background: #4338ca; }
    a { display: block; width: 100%; background: #f3f4f6; color: #374151; text-decoration: none; padding: 12px; border-radius: 8px; font-size: 16px; }
    a:hover { background: #e5e7eb; }
  </style>
</head>
<body>
  <div class="box">
    <div class="icon">📡</div>
    <h1>Нет связи</h1>
    <p>Страница не была сохранена для офлайн-режима.</p>
    <button onclick="location.reload()">🔄 Обновить страницу</button>
    <a href="javascript:history.back()">← Назад</a>
  </div>
</body>
</html>`;

async function cacheStatic(request, cache) {
  const cached = await cache.match(request);
  try {
    const networkResponse = await fetch(request);
    if (networkResponse.ok) {
      cache.put(request, networkResponse.clone());
    }
    return networkResponse;
  } catch (error) {
    if (cached) return cached;
    return new Response('', { status: 503 });
  }
}

async function staleWhileRevalidate(request, cache) {
  const cached = await cache.match(request);
  const fetchPromise = fetch(request).then((networkResponse) => {
    if (networkResponse.ok) {
      cache.put(request, networkResponse.clone());
    }
    return networkResponse;
  }).catch(() => cached);

  if (cached) {
    fetchPromise.catch(() => {});
    return cached;
  }

  try {
    return await fetchPromise;
  } catch (error) {
    return new Response(OFFLINE_HTML, {
      headers: { 'Content-Type': 'text/html; charset=utf-8' }
    });
  }
}

// Fetch handler
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  if (request.method !== 'GET') return;
  if (url.pathname === '/sw.js') return;
  if (isApi(url)) return;

  event.respondWith(
    caches.open(CACHE_NAME).then((cache) => {
      if (isStatic(url)) {
        return cacheStatic(request, cache);
      }
      if (isOfflinePage(url)) {
        return staleWhileRevalidate(request, cache);
      }
      return fetch(request).catch(() => cache.match(request).then(cached => cached || new Response('', { status: 503 })));
    })
  );
});

// Push notifications
self.addEventListener('push', (event) => {
  if (!event.data) return;
  let data = {};
  try { data = event.data.json(); } catch (e) {}

  const title = data.type === 'announcement'
    ? 'HatiApp — объявление'
    : data.title || 'HatiApp';
  const body = data.type === 'announcement'
    ? (data.title || 'Новое объявление')
    : (data.body || '');
  const url = data.type === 'announcement'
    ? (data.post_id ? '/a/' + data.post_id : '/announcements')
    : (data.url || '/');

  event.waitUntil(
    self.registration.showNotification(title, {
      body: body,
      icon: '/static/icon-192.png',
      badge: '/static/icon-192.png',
      data: { url: url },
    })
  );
});

// Background sync
self.addEventListener('sync', (event) => {
  if (event.tag === 'check-reminders') {
    event.waitUntil(
      fetch('/api/my-upcoming-shifts', { credentials: 'include' })
        .then(r => r.json())
        .then(shifts => {
          const now = new Date();
          const notifications = [];
          shifts.forEach(s => {
            const slotTime = new Date(s.datetime_iso);
            const diffMin = (slotTime - now) / (1000 * 60);
            if (diffMin > 0 && diffMin <= 2 * 60) {
              notifications.push(
                self.registration.showNotification('HatiApp — напоминание', {
                  body: `${s.direction}: смена через 2 часа в ${s.time}`,
                  icon: '/static/icon-192.png',
                })
              );
            }
          });
          return Promise.all(notifications);
        })
        .catch(() => {})
    );
  }
});

// Notification click
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const url = event.notification.data && event.notification.data.url ? event.notification.data.url : '/';
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true })
      .then(clientList => {
        if (clientList.length > 0) {
          clientList[0].navigate(url);
          return clientList[0].focus();
        }
        return self.clients.openWindow(url);
      })
  );
});
