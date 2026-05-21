const CACHE_PREFIX = 'sceneflix-';
const SHELL = [
  './image/favicon.png',
  './image/icon-192.png',
  './image/icon-512.png',
  'https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500&display=swap',
];

async function getVersion() {
  try {
    const res = await fetch('./index.html', { method: 'HEAD', cache: 'no-store' });
    return res.headers.get('etag') || res.headers.get('last-modified') || Date.now().toString();
  } catch {
    return Date.now().toString();
  }
}

self.addEventListener('install', e => {
  e.waitUntil(
    getVersion().then(v =>
      caches.open(CACHE_PREFIX + v).then(c => c.addAll(SHELL)).then(() => self.skipWaiting())
    )
  );
});

self.addEventListener('activate', e => {
  e.waitUntil(
    getVersion().then(v => {
      const current = CACHE_PREFIX + v;
      return caches.keys().then(keys =>
        Promise.all(keys.filter(k => k !== current).map(k => caches.delete(k)))
      ).then(() => self.clients.claim());
    })
  );
});

self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);

  if (url.hostname.includes('youtube.com') || url.hostname.includes('ytimg.com') || url.hostname.includes('googleapis.com')) {
    e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
    return;
  }

  if (url.pathname.endsWith('/') || url.pathname.endsWith('index.html')) {
    e.respondWith(
      fetch(e.request).then(res => {
        const clone = res.clone();
        getVersion().then(v => caches.open(CACHE_PREFIX + v).then(c => c.put(e.request, clone)));
        return res;
      }).catch(() => caches.match(e.request))
    );
    return;
  }

  e.respondWith(
    caches.match(e.request).then(cached => {
      if (cached) return cached;
      return fetch(e.request).then(res => {
        if (res && res.status === 200 && e.request.method === 'GET') {
          const clone = res.clone();
          getVersion().then(v => caches.open(CACHE_PREFIX + v).then(c => c.put(e.request, clone)));
        }
        return res;
      });
    })
  );
});
