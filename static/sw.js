const CACHE_NAME = 'hatiapp-v8';

// Static assets to cache during install
const PRECACHE_URLS = [
  '/static/manifest.json',
  '/static/favicon.svg',
  '/static/icon-192.png',
  '/static/icon-512.png',
];

console.log('[SW] Script loaded');

// Install - cache static assets
self.addEventListener('install', (event) => {
  console.log('[SW] Install event');
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      console.log('[SW] Caching static assets');
      return cache.addAll(PRECACHE_URLS);
    }).then(() => {
      console.log('[SW] Install complete');
    }).catch((err) => {
      console.error('[SW] Install failed:', err);
    })
  );
  self.skipWaiting();
});

// Activate - clean OLD caches only (keep current)
self.addEventListener('activate', (event) => {
  console.log('[SW] Activate event');
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames
          .filter((name) => name.startsWith('hatiapp-') && name !== CACHE_NAME)
          .map((name) => {
            console.log('[SW] Deleting old cache:', name);
            return caches.delete(name);
          })
      );
    }).then(() => {
      console.log('[SW] Claiming clients');
      return self.clients.claim();
    }).then(() => {
      console.log('[SW] Activate complete - controlling pages');
      // Log what's in cache
      return caches.open(CACHE_NAME).then(cache => {
        return cache.keys().then(requests => {
          console.log('[SW] Cached URLs:', requests.map(r => r.url));
        });
      });
    })
  );
});

// Offline page fallback
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
    .hint { margin-top: 20px; padding-top: 16px; border-top: 1px solid #e5e7eb; font-size: 12px; color: #9ca3af; }
  </style>
</head>
<body>
  <div class="box">
    <div class="icon">📡</div>
    <h1>Нет связи</h1>
    <p>Вы не в лагере или отсутствует подключение к WiFi.<br>Подключитесь к сети чтобы продолжить.</p>
    <button onclick="location.reload()">🔄 Обновить страницу</button>
    <a href="javascript:history.back()">← Назад</a>
    <div class="hint">Расписание доступно только в лагере.</div>
  </div>
  <script>
    setInterval(() => { if (navigator.onLine) location.reload(); }, 3000);
  </script>
</body>
</html>`;

// Fetch handler
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);
  
  // Skip non-GET and SW itself
  if (request.method !== 'GET') return;
  if (url.pathname === '/sw.js') return;
  
  event.respondWith(
    caches.open(CACHE_NAME).then(async (cache) => {
      const cached = await cache.match(request);
      
      if (cached) {
        return cached;
      }
      
      try {
        const response = await fetch(request);
        
        if (response.ok && response.status === 200) {
          // Cache HTML pages and static assets
          if (request.mode === 'navigate' || 
              url.pathname.startsWith('/static/') ||
              url.pathname === '/') {
            cache.put(request, response.clone());
          }
        }
        
        return response;
      } catch (error) {
        // For navigation requests, return offline page
        if (request.mode === 'navigate') {
          return new Response(OFFLINE_HTML, {
            headers: { 'Content-Type': 'text/html; charset=utf-8' }
          });
        }
        
        return new Response('', { status: 503 });
      }
    })
  );
});

// Listen for skipWaiting
self.addEventListener('message', (event) => {
  console.log('[SW] Message received:', event.data);
  if (event.data === 'skipWaiting') {
    self.skipWaiting();
  }
});
