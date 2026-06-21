const CACHE = 'sceneflix-v5';
const SHELL = [
  './image/favicon.png',
  './image/icon-192.png',
  './image/icon-512.png',
  'https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500&display=swap',
];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('message', e => {
  if (e.data === 'SKIP_WAITING') self.skipWaiting();
});

self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);

  if (url.pathname.endsWith('/') || url.pathname.endsWith('.html')) {
    e.respondWith(fetch(e.request));
    return;
  }

  if (url.hostname !== self.location.hostname) {
    e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
    return;
  }

  e.respondWith(
    caches.open(CACHE).then(cache =>
      cache.match(e.request).then(cached => {
        const fetchAndUpdate = fetch(e.request).then(res => {
          if (res && res.status === 200 && e.request.method === 'GET') {
            cache.put(e.request, res.clone());
          }
          return res;
        });
        return cached || fetchAndUpdate;
      })
    )
  );
});
