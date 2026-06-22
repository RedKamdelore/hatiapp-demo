# Restore SPA navigation with fresh offline cache

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring back lightweight SPA navigation so page transitions feel instant, but ensure every page (especially `/announcements`) re-initialises its per-page JavaScript and keeps an offline snapshot of its data.

**Architecture:** `base.html` intercepts internal link clicks, fetches the next page, swaps `#main-content` and `#global-modals`, then executes only the *new* page scripts (those not already loaded by the shell). Per-page scripts live in `{% block extra_scripts %}` and run inside an IIFE so they bind fresh listeners every time the page is entered. The Service Worker continues to serve HTML/pages stale-while-revalidate and API calls bypass the SW cache.

**Tech Stack:** Jinja2, vanilla JS, Service Worker, localStorage, pytest.

---

### Task 1: Mark shell scripts in base.html

**Files:**
- Modify: `templates/base.html`

- [ ] **Step 1: Add `data-shell="1"` to base-level `<script>` tags**

Mark every `<script>` tag that is part of the persistent shell so SPA transitions can skip them. Tags to mark:
- theme toggle script
- toast helpers script
- notification permission script
- SSE script
- reminders script
- SSE manager script
- `{% block extra_scripts %}` block must NOT have the marker

Example:
```html
<script data-shell="1">
  // existing shell code
</script>
```

- [ ] **Step 2: Add an `id="spa-scripts"` marker around `extra_scripts` block**

This makes extraction reliable:
```html
<div id="spa-scripts" style="display:none;">
  {% block extra_scripts %}{% endblock %}
</div>
```
Wrap the block in a hidden div. The content is still valid HTML and scripts inside execute normally on full page loads.

- [ ] **Step 3: Verify tests still pass**

Run: `.\venv\Scripts\python -m pytest -q`
Expected: 83 passed, 1 skipped.

---

### Task 2: Restore SPA navigation in base.html

**Files:**
- Modify: `templates/base.html` (append after SSE manager script)

- [ ] **Step 1: Re-add the SPA helper block**

Insert before `</body>`:
```html
<script data-shell="1">
(function() {
  function updateActiveNav(pathname) {
    document.querySelectorAll('.nav-item').forEach(item => {
      item.classList.remove('active');
      const href = item.getAttribute('href');
      if (href && pathname.startsWith(href)) {
        item.classList.add('active');
      }
    });
  }

  var _navigating = false;
  async function navigateTo(pathname, pushState) {
    if (_navigating) return;
    _navigating = true;

    if (pathname === '/logout' || pathname.startsWith('http')) {
      window.location.href = pathname;
      return;
    }

    if (typeof closeAllSSE === 'function') closeAllSSE();

    const mainContent = document.getElementById('main-content');
    if (mainContent) mainContent.style.opacity = '0.6';

    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 10000);
      const response = await fetch(pathname, {
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
        signal: controller.signal,
      });
      clearTimeout(timeoutId);

      if (response.ok) {
        const html = await response.text();
        const parser = new DOMParser();
        const doc = parser.parseFromString(html, 'text/html');
        const newTitle = doc.title;
        const newContent = doc.getElementById('main-content');
        const newModals = doc.getElementById('global-modals');
        const newSpaScripts = doc.getElementById('spa-scripts');

        if (mainContent && newContent) {
          mainContent.innerHTML = newContent.innerHTML;
          document.title = newTitle;
          if (mainContent) mainContent.style.opacity = '1';

          if (newModals) {
            const currentModals = document.getElementById('global-modals');
            if (currentModals) {
              currentModals.innerHTML = newModals.innerHTML;
            }
          }

          if (newSpaScripts) {
            executeNewScripts(newSpaScripts);
          }

          if (pushState) {
            history.pushState({ pathname: pathname }, '', pathname);
          }

          attachLinkHandlers();
          updateActiveNav(pathname);
          _navigating = false;
          return;
        }
      }
      window.location.href = pathname;
    } catch (e) {
      window.location.href = pathname;
    }
  }

  function executeNewScripts(container) {
    const existing = new Set();
    document.querySelectorAll('script[data-shell="1"]').forEach(s => {
      if (s.src) existing.add(s.src);
      else existing.add(s.textContent.trim());
    });

    container.querySelectorAll('script').forEach(script => {
      if (script.src && existing.has(script.src)) return;
      const text = script.textContent.trim();
      if (!text) return;
      if (existing.has(text)) return;

      const newScript = document.createElement('script');
      if (script.src) newScript.src = script.src;
      else newScript.textContent = text;
      document.head.appendChild(newScript);
      document.head.removeChild(newScript);
    });
  }

  function attachLinkHandlers() {
    document.querySelectorAll('a[href]').forEach(link => {
      const href = link.getAttribute('href');
      if (!href || href.startsWith('http') || href.startsWith('#') ||
          href.startsWith('javascript:') || href.startsWith('mailto:') ||
          href === '/logout' || link.target === '_blank' || link.hasAttribute('download')) {
        return;
      }
      if (link.dataset.spaHandled) return;
      link.dataset.spaHandled = 'true';
      link.addEventListener('click', function(e) {
        if (e.ctrlKey || e.metaKey || e.shiftKey || e.button !== 0) return;
        e.preventDefault();
        navigateTo(href, true);
      });
    });
  }

  window.addEventListener('popstate', function(e) {
    const expected = e.state && e.state.pathname;
    if (expected) {
      navigateTo(expected, false);
    }
  });

  document.addEventListener('DOMContentLoaded', function() {
    attachLinkHandlers();
    updateActiveNav(location.pathname);
  });
})();
</script>
```

- [ ] **Step 2: Run tests**

Run: `.\venv\Scripts\python -m pytest -q`
Expected: 83 passed, 1 skipped.

---

### Task 3: Restore SPA print-schedule test

**Files:**
- Modify: `tests/test_print_schedule.py`

- [ ] **Step 1: Re-add `test_spa_handler_skips_target_blank_links`**

Replace the current file content with:
```python
import re
from pathlib import Path

import pytest

from config import COOKIE_NAME
from services.auth import sign_cookie


class TestPrintSchedule:
    @pytest.fixture
    def admin_client(self, client, admin_user):
        """Клиент с авторизованной админской сессией, без использования /login."""
        client.cookies.set(COOKIE_NAME, sign_cookie(admin_user.id))
        return client

    def test_admin_print_returns_full_html_page(self, admin_client, admin_user):
        """/admin/print должен возвращать полную самостоятельную HTML-страницу."""
        response = admin_client.get("/admin/print")
        assert response.status_code == 200
        text = response.text
        assert "<!DOCTYPE html>" in text
        assert "<html" in text
        assert "Расписание смен" in text
        assert "id=\"main-content\"" not in text

    def test_spa_handler_skips_target_blank_links(self):
        """SPA-обработчик не должен перехватывать ссылки
        с target=\"_blank\" (например, кнопку печати расписания)."""
        base_html = Path("templates/base.html").read_text(encoding="utf-8")

        # Находим SPA-блок по уникальному маркеру
        spa_block_start = base_html.find("function attachLinkHandlers()")
        assert spa_block_start != -1, "SPA navigation block not found"
        spa_block = base_html[spa_block_start:]

        # Извлекаем функцию attachLinkHandlers
        match = re.search(
            r"function\s+attachLinkHandlers\(\)\s*\{(.*?)^  \}",
            spa_block,
            re.DOTALL | re.MULTILINE,
        )
        assert match, "attachLinkHandlers not found in SPA block"
        handler_body = match.group(1)

        # Должен быть guard, который пропускает target="_blank"
        assert "link.target === '_blank'" in handler_body, (
            "SPA handler does not skip target='_blank' links"
        )

    def test_admin_page_has_print_link_with_target_blank(self, admin_client, admin_user):
        """На странице /admin кнопка печати должна открываться в новой вкладке."""
        response = admin_client.get("/admin")
        assert response.status_code == 200
        text = response.text
        assert 'id="print-btn"' in text
        assert '/admin/print' in text
        assert 'target="_blank"' in text
```

- [ ] **Step 2: Run tests**

Run: `.\venv\Scripts\python -m pytest tests/test_print_schedule.py -v`
Expected: 3 passed.

---

### Task 4: Add a page offline cache helper

**Files:**
- Create: `static/page-cache.js`
- Modify: `templates/base.html` to load it as shell script

- [ ] **Step 1: Create helper**

```javascript
window.pageCache = {
  key(page) { return 'hatiapp_cache_' + (page || location.pathname); },
  save(page, data) {
    try {
      localStorage.setItem(this.key(page), JSON.stringify({ ts: Date.now(), data }));
    } catch (e) {}
  },
  load(page) {
    try {
      const raw = localStorage.getItem(this.key(page));
      if (!raw) return null;
      return JSON.parse(raw).data;
    } catch (e) { return null; }
  },
  isOnline() { return navigator.onLine !== false; },
  banner(text, containerId) {
    const container = document.getElementById(containerId || 'main-content');
    if (!container) return;
    let banner = document.getElementById('page-offline-banner');
    if (!banner) {
      banner = document.createElement('div');
      banner.id = 'page-offline-banner';
      banner.className = 'text-sm text-amber-700 dark:text-amber-300 bg-amber-100 dark:bg-amber-900/40 px-3 py-2 rounded-lg mb-3';
      container.insertBefore(banner, container.firstChild);
    }
    banner.textContent = text;
  },
  hideBanner() {
    const banner = document.getElementById('page-offline-banner');
    if (banner) banner.remove();
  }
};
```

- [ ] **Step 2: Include it in base.html**

Add before `{% block extra_scripts %}`:
```html
<script data-shell="1" src="/static/page-cache.js"></script>
```

- [ ] **Step 3: Run tests**

Run: `.\venv\Scripts\python -m pytest -q`
Expected: 83 passed, 1 skipped.

---

### Task 5: Refactor announcements feed to use page cache helper

**Files:**
- Modify: `templates/announcements.html`

- [ ] **Step 1: Replace inline cache helpers with pageCache**

Remove the local `FEED_CACHE_KEY`, `saveFeedCache`, `loadFeedCache`, `showOfflineBanner`, and `hideOfflineBanner` functions. Use the global helper instead.

Inside `loadFeed`:
- On successful first fetch call `window.pageCache.save('/announcements', data)` and `window.pageCache.hideBanner()`.
- On error when offline and `offset === 0`, load cached data, render it, and show banner:
```javascript
const cached = window.pageCache.load('/announcements');
if (cached) {
  renderPosts(cached.pinned, 'pinned-list', true);
  renderPosts(cached.posts, 'posts-list', false);
  window.pageCache.banner('Нет соединения — показаны ранее загруженные объявления', 'feed');
}
```

- [ ] **Step 2: Run tests**

Run: `.\venv\Scripts\python -m pytest tests/test_announcements.py tests/test_wall_navigation.py -v`
Expected: all pass.

---

### Task 6: Bump Service Worker version

**Files:**
- Modify: `static/sw.js`

- [ ] **Step 1: Update cache name**

```javascript
const CACHE_NAME = 'hatiapp-v13';
```

- [ ] **Step 2: Run tests**

Run: `.\venv\Scripts\python -m pytest -q`
Expected: 83 passed, 1 skipped.

---

### Task 7: Manual verification

- [ ] **Step 1: Start local server**

Run: `.\venv\Scripts\python main.py` or `start-http.bat`

- [ ] **Step 2: Open browser DevTools**

- Confirm Service Worker registered with `hatiapp-v13`
- Go to `/announcements`, create a post
- Navigate to another tab via bottom nav, then back to "Стена"
- Confirm posts load without full reload
- Enable "Offline" in Network tab, navigate to "Стена"
- Confirm cached posts appear with offline banner

---

## Self-review checklist

- [ ] Shell scripts are marked with `data-shell="1"`
- [ ] SPA navigation re-runs per-page scripts on every transition
- [ ] `target="_blank"` links still bypass SPA handler
- [ ] Offline banner appears when network fails and cache exists
- [ ] Service Worker cache version bumped
