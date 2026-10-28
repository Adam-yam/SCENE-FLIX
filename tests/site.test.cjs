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

{
  const grab = (name, next) => html.slice(html.indexOf('      function ' + name + '('), html.indexOf(next, html.indexOf('      function ' + name + '(')));
  const vids = ['aaaaaaaaaaa', 'bbbbbbbbbbb', 'ccccccccccc', 'ddddddddddd'];
  const items = vids.map((vid, i) => ({vid, meta:{date:String(i)}}));
  const state = {BOOKMARKS:new Set(vids), curBmSort:'manual', _bmOrder:[vids[2], vids[0]], buildUnifiedVideoList:()=>[...items, items[0]], _videoDate:()=>'', _dateStrToSortKey:Number};
  vm.createContext(state);
  vm.runInContext(grab('_getBookmarkedItems', '      const BOOKMARK_PLAYLIST_LIMIT'), state);
  assert.deepEqual(Array.from(state._getBookmarkedItems('manual'), i=>i.vid), [vids[2],vids[0],vids[1],vids[3]]);
  assert.deepEqual(Array.from(state._getBookmarkedItems('added'), i=>i.vid), vids);
  assert.deepEqual(Array.from(state._getBookmarkedItems('newest'), i=>i.vid), [...vids].reverse());
  state.BOOKMARKS.delete(vids[2]);
  assert.deepEqual(Array.from(state._getBookmarkedItems('manual'), i=>i.vid), [vids[0],vids[1],vids[3]]);
  const urlSource = html.slice(html.indexOf('      function _seriesPlaylistUrl('), html.indexOf('      async function openSeriesQr('));
  vm.runInContext(urlSource,state);
  assert.equal(state._seriesPlaylistUrl({ids:vids}), 'https://www.youtube.com/watch_videos?video_ids='+vids.join(','));
  for (const name of ['sortable','qrcode']) new vm.Script(fs.readFileSync(path.join(root,'assets/features',name+'-v1.min.js'),'utf8'));
  console.log('PASS: bookmark manual order, new and removed entries, existing sort modes, QR playlist address, bundled script syntax');
}

(async () => {
  const scripts=[], timers=new Map();let clock=0;
  const state={window:{},document:{createElement:()=>({remove(){this.removed=true}}),head:{append:s=>scripts.push(s)}},setTimeout:fn=>{timers.set(++clock,fn);return clock},clearTimeout:id=>timers.delete(id)};
  vm.createContext(state);
  const begin=html.indexOf('      const _featureScripts');
  vm.runInContext(html.slice(begin,html.indexOf('      function _featureToast',begin)),state);
  const first=state._featureLoad('sortable');
  assert.equal(first,state._featureLoad('sortable'));
  const rejected=assert.rejects(first);
  scripts[0].onerror();await rejected;
  assert(scripts[0].removed);
  const retry=state._featureLoad('sortable');state.window.Sortable=function(){};scripts[1].onload();await retry;
  assert.equal(timers.size,0);
  const timeout=state._featureLoad('qrcode');const expired=assert.rejects(timeout);[...timers.values()][0]();await expired;
  await assert.rejects(state._featureLoad('../unknown'));
  let release,enabled=0;
  const edit={_bmEditing:false,_bmLoading:false,_bmEditRequest:0,_bmSortable:null,_elGrid:null,curSection:'bookmark',curSearchQuery:'',_featureLoad:()=>new Promise(resolve=>release=resolve),_featureToast:()=>{},_ft:()=>({}),document:{getElementById:()=>null},setSort:()=>enabled++};
  vm.createContext(edit);
  const end=html.indexOf('      function _endBmEdit');
  vm.runInContext(html.slice(end,html.indexOf('      function _saveBmOrder',end)),edit);
  const toggle=html.indexOf('      async function toggleBookmarkReorder');
  vm.runInContext(html.slice(toggle,html.indexOf('      document.addEventListener',toggle)),edit);
  const loading=edit.toggleBookmarkReorder();
  edit.curSection='series';edit._endBmEdit();edit.curSection='bookmark';release();await loading;
  assert.equal(enabled,0);assert.equal(edit._bmEditing,false);assert.equal(edit._bmLoading,false);
  console.log('PASS: feature load deduplication, retry, timeout, allowlist and stale reorder cancellation');
})().catch(error=>{console.error(error);process.exitCode=1});
