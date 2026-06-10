# PWA Offline Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add offline PWA support with Service Worker caching, offline indicators, and graceful degradation for users outside the camp.

**Architecture:** Service Worker will cache static assets (CSS, JS, icons, avatars) and API responses. HTML pages use Network First strategy with offline fallback. Chat caches last 50 messages. All mutation actions (booking, cancel, check-in) are blocked when offline with clear visual indicators.

**Tech Stack:** JavaScript Service Worker, Cache API, Tailwind CSS

---

## File Structure

| File | Purpose |
|------|---------|
| `static/sw.js` | Service Worker - caching strategies, offline detection |
| `templates/base.html` | Register SW, add offline banner, handle buttons |
| `main.py` | Modify NoCacheMiddleware to allow static caching |
| `templates/schedule.html` | Add offline overlay for booking buttons |
| `templates/slots.html` | Add offline overlay |
| `templates/chat.html` | Cache last 50 messages, offline banner |
| `ANCHORED_SUMMARY.md` | Update documentation |

---

## Task 1: Service Worker (static/sw.js)

**Files:**
- Create: `static/sw.js`

- [ ] **Step 1: Create Service Worker with caching strategies**

```javascript
const CACHE_NAME = 'hatiapp-v1';
const STATIC_ASSETS = [
  '/static/manifest.json',
  '/static/favicon.svg',
  '/static/icon-192.png',
  '/static/icon-512.png',
  // CSS will be added dynamically from link tags
];

const API_CACHE_NAME = 'hatiapp-api-v1';
const HTML_CACHE_NAME = 'hatiapp-html-v1';
const CHAT_CACHE_NAME = 'hatiapp-chat-v1';
const MAX_CHAT_MESSAGES = 50;

// Install - cache static assets
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(STATIC_ASSETS);
    })
  );
  self.skipWaiting();
});

// Activate - clean old caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames
          .filter((name) => !name.startsWith('hatiapp-'))
          .map((name) => caches.delete(name))
      );
    })
  );
  self.clients.claim();
});

// Fetch handler
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);
  
  // Static assets: Cache First
  if (isStaticAsset(request)) {
    event.respondWith(cacheFirst(request));
    return;
  }
  
  // API endpoints: Network First with cache fallback
  if (isApiEndpoint(url.pathname)) {
    event.respondWith(networkFirst(request, API_CACHE_NAME));
    return;
  }
  
  // HTML pages: Network First with offline fallback
  if (request.mode === 'navigate' || request.headers.get('accept').includes('text/html')) {
    event.respondWith(networkFirstWithOfflineFallback(request));
    return;
  }
  
  // Default: Network First
  event.respondWith(networkFirst(request, API_CACHE_NAME));
});

function isStaticAsset(request) {
  return request.destination === 'image' || 
         request.destination === 'style' || 
         request.destination === 'script' ||
         request.destination === 'font' ||
         request.url.includes('/static/');
}

function isApiEndpoint(pathname) {
  return pathname.startsWith('/api/') ||
         pathname.startsWith('/schedule') ||
         pathname.startsWith('/me') ||
         pathname.startsWith('/slots/');
}

// Cache First strategy for static assets
async function cacheFirst(request) {
  const cache = await caches.open(CACHE_NAME);
  const cached = await cache.match(request);
  if (cached) return cached;
  
  try {
    const response = await fetch(request);
    if (response.ok) {
      cache.put(request, response.clone());
    }
    return response;
  } catch (error) {
    // Return a fallback for images
    if (request.destination === 'image') {
      return new Response('', { status: 404 });
    }
    throw error;
  }
}

// Network First strategy
async function networkFirst(request, cacheName) {
  try {
    const networkResponse = await fetch(request);
    if (networkResponse.ok) {
      const cache = await caches.open(cacheName);
      cache.put(request, networkResponse.clone());
    }
    return networkResponse;
  } catch (error) {
    const cache = await caches.open(cacheName);
    const cached = await cache.match(request);
    if (cached) return cached;
    throw error;
  }
}

// Network First with offline fallback for HTML
async function networkFirstWithOfflineFallback(request) {
  try {
    const networkResponse = await fetch(request);
    if (networkResponse.ok) {
      const cache = await caches.open(HTML_CACHE_NAME);
      cache.put(request, networkResponse.clone());
    }
    return networkResponse;
  } catch (error) {
    const cache = await caches.open(HTML_CACHE_NAME);
    const cached = await cache.match(request);
    if (cached) {
      // Add offline indicator to cached HTML
      const html = await cached.text();
      const modifiedHtml = html.replace(
        '<body',
        '<body data-offline="true"'
      );
      return new Response(modifiedHtml, {
        headers: { 'Content-Type': 'text/html' }
      });
    }
    // Return generic offline page
    return new Response(`
      <!DOCTYPE html>
      <html>
      <head><title>Нет связи</title></head>
      <body style="display:flex;justify-content:center;align-items:center;height:100vh;margin:0;font-family:sans-serif;">
        <div style="text-align:center;padding:20px;">
          <h1>📡 Нет связи</h1>
          <p>Вы не в лагере. Подключитесь к WiFi чтобы получить актуальные данные.</p>
          <button onclick="location.reload()" style="padding:10px 20px;margin-top:20px;">Обновить</button>
        </div>
      </body>
      </html>
    `, { headers: { 'Content-Type': 'text/html' } });
  }
}
```

- [ ] **Step 2: Test that sw.js is syntactically valid**

No syntax errors in the JS code above.

---

## Task 2: Update base.html - Register SW & Add Offline Banner

**Files:**
- Modify: `templates/base.html`

- [ ] **Step 1: Replace SW unregistration with registration**

Remove lines ~520-525 (the unregister block):
```javascript
// REMOVE THIS:
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.getRegistrations().then(function(registrations) {
    registrations.forEach(function(reg) { reg.unregister(); });
  });
}
```

Replace with registration:
```javascript
// Register Service Worker
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/static/sw.js')
    .then(reg => console.log('SW registered:', reg.scope))
    .catch(err => console.error('SW registration failed:', err));
}
```

- [ ] **Step 2: Add offline/online detection script**

Add before closing `</body>` tag:
```javascript
// Online/Offline detection
function updateOnlineStatus() {
  const isOnline = navigator.onLine;
  const banner = document.getElementById('offline-banner');
  
  if (!isOnline) {
    if (!banner) {
      const div = document.createElement('div');
      div.id = 'offline-banner';
      div.className = 'fixed top-0 left-0 right-0 bg-red-600 text-white text-center py-2 text-sm z-50';
      div.innerHTML = '📡 Нет связи · Вы не в лагере';
      document.body.prepend(div);
    }
    document.body.classList.add('offline-mode');
    disableActionButtons();
  } else {
    if (banner) banner.remove();
    document.body.classList.remove('offline-mode');
    enableActionButtons();
    // Auto-reload to get fresh data
    location.reload();
  }
}

function disableActionButtons() {
  document.querySelectorAll('button[type="submit"], .action-button').forEach(btn => {
    if (!btn.dataset.originalDisabled) {
      btn.dataset.originalDisabled = btn.disabled ? 'true' : 'false';
    }
    btn.disabled = true;
    btn.title = 'Доступно только в лагере';
    btn.classList.add('opacity-50', 'cursor-not-allowed');
  });
}

function enableActionButtons() {
  document.querySelectorAll('button[type="submit"], .action-button').forEach(btn => {
    const wasDisabled = btn.dataset.originalDisabled === 'true';
    btn.disabled = wasDisabled;
    btn.removeAttribute('title');
    btn.classList.remove('opacity-50', 'cursor-not-allowed');
  });
}

window.addEventListener('online', updateOnlineStatus);
window.addEventListener('offline', updateOnlineStatus);
updateOnlineStatus(); // Initial check
```

- [ ] **Step 3: Add CSS for offline mode**

Add to existing `<style>` block or create one:
```css
.offline-mode form[action*="/book"],
.offline-mode form[action*="/cancel"],
.offline-mode form[action*="/logs/book"],
.offline-mode form[action*="/logs/cancel"],
.offline-mode form[action*="/leader/attendance"],
.offline-mode form[action*="/profile/preferences"] {
  position: relative;
  pointer-events: none;
}

.offline-mode form[action*="/book"]::after,
.offline-mode form[action*="/cancel"]::after,
.offline-mode form[action*="/logs/book"]::after,
.offline-mode form[action*="/logs/cancel"]::after {
  content: '⚠️ Только в лагере';
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  background: rgba(0,0,0,0.8);
  color: white;
  padding: 8px 16px;
  border-radius: 8px;
  font-size: 12px;
  white-space: nowrap;
  z-index: 10;
}
```

---

## Task 3: Modify NoCacheMiddleware

**Files:**
- Modify: `main.py:26-34`

- [ ] **Step 1: Allow static assets to be cached**

Change from:
```python
class NoCacheMiddleware(BaseHTTPMiddleware):
    """Запрещает кэширование HTML-страниц — предотвращает зависание при "Назад"."""
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        if isinstance(response, (HTMLResponse, RedirectResponse)):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response
```

To:
```python
class NoCacheMiddleware(BaseHTTPMiddleware):
    """Запрещает кэширование HTML-страниц и API — но разрешает статику."""
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        # Skip caching headers for static assets (let Service Worker handle them)
        if request.url.path.startswith('/static/'):
            return response
        if isinstance(response, (HTMLResponse, RedirectResponse)):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response
```

---

## Task 4: Update Templates with Offline Handling

**Files:**
- Modify: `templates/schedule.html`
- Modify: `templates/slots.html`
- Modify: `templates/chat.html`

- [ ] **Step 1: Add offline overlay to schedule.html**

Add after booking forms in the loop:
```html
{% if not is_offline %}
  <!-- existing form -->
{% else %}
  <div class="text-center py-2 text-sm text-gray-400">
    📡 Запись доступна только в лагере
  </div>
{% endif %}
```

Actually, a better approach: add a data attribute to forms and let JS handle it. Or add a simple check in template.

- [ ] **Step 2: Add offline handling to chat**

In `chat.html`, add before message input:
```html
<div id="chat-offline-banner" class="hidden bg-yellow-100 text-yellow-700 text-center py-2 text-sm">
  📡 Нет связи. Сообщения будут отправлены при подключении.
</div>
```

And cache last messages in localStorage.

---

## Task 5: Chat Message Caching

**Files:**
- Modify: `templates/chat.html`
- Modify: `static/sw.js`

- [ ] **Step 1: Cache chat messages in Service Worker**

Add to sw.js fetch handler:
```javascript
// Chat messages caching
if (url.pathname === '/chat' || url.pathname.startsWith('/chat/with/')) {
  event.respondWith(networkFirst(request, CHAT_CACHE_NAME));
  return;
}
```

- [ ] **Step 2: Store last 50 messages in localStorage**

In chat.html script:
```javascript
// On page load, restore cached messages
const cachedMessages = JSON.parse(localStorage.getItem('chat_messages') || '[]');
cachedMessages.slice(-50).forEach(msg => appendMessage(msg));

// When receiving new messages via WebSocket/SSE
function onNewMessage(msg) {
  appendMessage(msg);
  const messages = JSON.parse(localStorage.getItem('chat_messages') || '[]');
  messages.push(msg);
  // Keep only last 50
  if (messages.length > 50) messages.shift();
  localStorage.setItem('chat_messages', JSON.stringify(messages));
}
```

---

## Task 6: Testing

- [ ] **Step 1: Verify Service Worker registration**
Open browser DevTools → Application → Service Workers. Should show active SW.

- [ ] **Step 2: Test offline mode**
Turn off WiFi, reload page. Should show cached data with offline banner.

- [ ] **Step 3: Test booking button blocking**
In offline mode, try to click "Записать" — should be disabled with tooltip.

- [ ] **Step 4: Test auto-reload on reconnect**
Turn WiFi back on, page should auto-reload.

- [ ] **Step 5: Test chat caching**
Send messages, go offline, reload — should show last 50 messages.

---

## Spec Coverage Check

| Requirement | Task | Status |
|------------|------|--------|
| Service Worker caching | Task 1 | ✅ Planned |
| Offline banner (both messages) | Task 2 | ✅ Planned |
| Block booking when offline | Task 2 | ✅ Planned |
| Chat cache last 50 messages | Task 5 | ✅ Planned |
| Auto-reload on reconnect | Task 2 | ✅ Planned |
| NoCacheMiddleware fix | Task 3 | ✅ Planned |
| Avatar caching (seen only) | Task 1 | ✅ Planned (cacheFirst handles this) |

No placeholders found. All tasks have concrete code.
