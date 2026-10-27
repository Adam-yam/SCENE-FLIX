const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const root = path.join(__dirname, '..');
const html = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
for (const match of html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/gi)) {
  if (match[1].trim()) new vm.Script(match[1]);
}
const manifest = JSON.parse(fs.readFileSync(path.join(root, 'data/schedule/manifest.json')));
for (const name of manifest.files) {
  assert.match(name, /^schedule_\d{4}_h[12]\.json$/);
  assert(Array.isArray(JSON.parse(fs.readFileSync(path.join(root, 'data/schedule', name))).events));
}
const handlers = {}, saved = new Map();
const keyOf = key => typeof key === 'string' ? key : key.url;
const caches = {
  async open(name) {
    if (!saved.has(name)) saved.set(name, new Map());
    const map = saved.get(name);
    return {
      async put(key, value) { map.set(keyOf(key), value.clone()); },
      async match(key) { return map.get(keyOf(key))?.clone(); },
      async keys() { return [...map.keys()]; },
      async delete(key) { return map.delete(keyOf(key)); }
    };
  },
  async keys() { return [...saved.keys()]; },
  async delete(name) { return saved.delete(name); }
};
let offline = false, content = 'initial';
const context = {
  URL, Response, Promise, Set,
  caches,
  fetch: async () => { if (offline) throw Error('offline'); return new Response(content); },
  self: {
    registration: {scope: 'https://example.com/SCENE-FLIX/'},
    location: {origin: 'https://example.com'},
    clients: {claim: async () => {}},
    skipWaiting: async () => {},
    addEventListener(type, handler) { handlers[type] = handler; }
  }
};
vm.createContext(context);
vm.runInContext(fs.readFileSync(path.join(root, 'service-worker.js'), 'utf8'), context);
async function lifecycle(type) {
  const waits=[]; handlers[type]({waitUntil(p){waits.push(p)}}); await Promise.all(waits);
}
async function request(url, mode='cors', destination='') {
  const waits=[]; let result;
  handlers.fetch({request:{url,method:'GET',mode,destination},waitUntil(p){waits.push(p)},respondWith(p){result=p}});
  if (!result) return null;
  const response=await result; await Promise.all(waits); return response;
}
(async () => {
  await caches.open('other-project-cache');
  await caches.open('sceneflix-v8');
  await lifecycle('install');await lifecycle('activate');
  assert(saved.has('other-project-cache'));
  assert(!saved.has('sceneflix-v8'));
  content='updated HTML';
  await request('https://example.com/SCENE-FLIX/?tab=chart','navigate');
  offline=true;
  assert.equal(await (await request('https://example.com/SCENE-FLIX/?tab=schedule','navigate')).text(),'updated HTML');
  offline=false;content='chart data';
  await request('https://example.com/SCENE-FLIX/data/charts/chart.json?_=1');
  offline=true;
  assert.equal(await (await request('https://example.com/SCENE-FLIX/data/charts/chart.json?_=2')).text(),'chart data');
  offline=false;
  for(let i=0;i<130;i++)await request('https://images.example.com/'+i,'cors','image');
  const external=[...saved.entries()].find(([k])=>k.endsWith('external-v9'))[1];
  assert.equal(external.size,60);
  assert.equal(await request('https://www.youtube.com/oembed?url=test'),null);
  assert.equal(await request('https://example.com/other-project/data.json'),null);
  console.log('PASS: script syntax, schedule manifest, latest offline HTML, stable data cache keys, cache limits, other project protection');
})().catch(error=>{console.error(error);process.exitCode=1});

require('./schedule.test.cjs');
