const PREFIX = 'sceneflix-' + new URL(self.registration.scope).pathname + '-';
const SHELL = PREFIX + 'shell-v9';
const ASSETS = PREFIX + 'assets-v9';
const EXTERNAL = PREFIX + 'external-v9';
const HOME = new URL('./', self.registration.scope).href;
const CURRENT = new Set([SHELL, ASSETS, EXTERNAL]);
let writes = Promise.resolve();
function store(name, key, response, limit) {
  writes = writes.catch(() => {}).then(async () => {
    const cache = await caches.open(name);
    await cache.put(key, response);
    const keys = await cache.keys();
    for (const old of keys.slice(0, Math.max(0, keys.length - limit))) await cache.delete(old);
  }).catch(() => {});
  return writes;
}
self.addEventListener('install', event => {
  event.waitUntil((async () => {
    const cache = await caches.open(SHELL);
    const response = await fetch(HOME, {cache: 'no-store'});
    if (!response.ok) throw new Error('Unable to cache page');
    await cache.put(HOME, response);
    await Promise.allSettled(['image/favicon.png', 'image/icon-192.png', 'image/icon-512.png'].map(async path => {
      const url = new URL(path, HOME).href;
      const response = await fetch(url);
      if (response.ok) await store(ASSETS, url, response, 100);
    }));
  })());
});
self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.filter(key => (key.startsWith(PREFIX) || /^sceneflix-v\d+$/.test(key)) && !CURRENT.has(key)).map(key => caches.delete(key)));
    await self.clients.claim();
  })());
});
self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET') return;
  const url = new URL(event.request.url);
  const local = url.origin === self.location.origin;
  if (local && !url.href.startsWith(self.registration.scope)) return;
  if (event.request.mode === 'navigate' && local) {
    event.respondWith((async () => {
      try {
        const response = await fetch(event.request, {cache: 'no-store'});
        if (response.ok) event.waitUntil(store(SHELL, HOME, response.clone(), 1));
        return response;
      } catch {
        return await (await caches.open(SHELL)).match(HOME) || Response.error();
      }
    })());
    return;
  }
  const isExternalAsset = !local && ['image', 'font', 'style'].includes(event.request.destination);
  if (!local && !isExternalAsset) return;
  const name = local ? ASSETS : EXTERNAL;
  if (local) url.searchParams.delete('_');
  const key = url.href;
  event.respondWith((async () => {
    try {
      const response = await fetch(event.request);
      if (response.ok && response.type !== 'opaque') event.waitUntil(store(name, key, response.clone(), local ? 100 : 60));
      return response;
    } catch {
      return await (await caches.open(name)).match(key) || Response.error();
    }
  })());
});
