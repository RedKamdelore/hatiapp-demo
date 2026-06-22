window.pageCache = {
  dataKey(page) { return 'hatiapp_cache_' + (page || location.pathname); },
  pageKey(page) { return 'hatiapp_page_' + (page || location.pathname); },

  save(page, data) {
    try {
      localStorage.setItem(this.dataKey(page), JSON.stringify({ ts: Date.now(), data }));
    } catch (e) {}
  },

  load(page) {
    try {
      const raw = localStorage.getItem(this.dataKey(page));
      if (!raw) return null;
      return JSON.parse(raw).data;
    } catch (e) { return null; }
  },

  savePage(page, html) {
    try {
      const key = this.pageKey(page);
      const item = JSON.stringify({ ts: Date.now(), html: html });
      try {
        localStorage.setItem(key, item);
      } catch (quotaErr) {
        this.trimPages(true);
        localStorage.setItem(key, item);
      }
      this.trimPages();
    } catch (e) {}
  },

  loadPage(page) {
    try {
      const raw = localStorage.getItem(this.pageKey(page));
      if (!raw) return null;
      return JSON.parse(raw).html;
    } catch (e) { return null; }
  },

  trimPages(aggressive) {
    try {
      let keys = [];
      for (let i = 0; i < localStorage.length; i++) {
        const k = localStorage.key(i);
        if (k && k.startsWith('hatiapp_page_')) keys.push(k);
      }
      keys.sort((a, b) => {
        const ta = JSON.parse(localStorage.getItem(a) || '{}').ts || 0;
        const tb = JSON.parse(localStorage.getItem(b) || '{}').ts || 0;
        return tb - ta;
      });
      const limit = aggressive ? Math.max(3, Math.floor(keys.length / 2)) : 20;
      while (keys.length > limit) {
        localStorage.removeItem(keys.pop());
      }
    } catch (e) {}
  },

  pageCount() {
    let count = 0;
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i);
      if (k && k.startsWith('hatiapp_page_')) count++;
    }
    return count;
  },

  async clearAll() {
    try {
      const keys = [];
      for (let i = 0; i < localStorage.length; i++) {
        const k = localStorage.key(i);
        if (k && (k.startsWith('hatiapp_page_') || k.startsWith('hatiapp_cache_'))) {
          keys.push(k);
        }
      }
      keys.forEach(k => localStorage.removeItem(k));
    } catch (e) {}
    try {
      if ('caches' in window) {
        const cacheNames = await caches.keys();
        await Promise.all(cacheNames.map(name => caches.delete(name)));
      }
    } catch (e) {}
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
