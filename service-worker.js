const CACHE = 'sceneflix-v6';
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
    e.respondWith(fetch(e.request, { cache: 'no-store' }));
    return;
  }

  if (url.hostname !== self.location.hostname) {
    e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
    return;
  }

  e.respondWith(
    fetch(e.request, { cache: 'no-store' }).then(res => {
      if (res && res.status === 200 && e.request.method === 'GET') {
        const resClone = res.clone();
        caches.open(CACHE).then(cache => cache.put(e.request, resClone));
      }
      return res;
    }).catch(() => caches.match(e.request))
  );
});
