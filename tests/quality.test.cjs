const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.join(__dirname, '..');
const html = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
function grab(name, next) {
  const start = html.indexOf('      function ' + name + '(');
  assert(start >= 0, name);
  const end = html.indexOf(next, start);
  assert(end > start, next);
  return html.slice(start, end);
}
const stored = new Map();
let failKey = null;
const state = {
  _VIDEO_ID_RE: /^[A-Za-z0-9_-]{11}$/,
  _BOOKMARK_ITEM_PREFIX: 'rescene-bookmark-v2:', _BM_ORDER_KEY: 'sceneflix-bookmark-order-v1',
  _bmOrder: [], BOOKMARKS: new Set(),
  localStorage: {
    get length() { return stored.size; },
    key: i => [...stored.keys()][i],
    getItem: key => stored.get(key) ?? null,
    setItem(key, value) { if (key === failKey) throw Error('Quota'); stored.set(key, value); },
    removeItem: key => stored.delete(key)
  }
};
vm.createContext(state);
vm.runInContext(grab('_readStoredBookmarks', '      const _FEATURE_TEXT'), state);
vm.runInContext(grab('_readBmOrder', '      let _bmOrder'), state);
vm.runInContext(grab('_parseBookmarkBackup', '      function exportBookmarks'), state);
vm.runInContext(grab('_mergeBookmarkBackup', '      document.getElementById("bookmarkBackupFile")'), state);
const a = 'aaaaaaaaaaa', b = 'bbbbbbbbbbb', c = 'ccccccccccc';
function parse(bookmarks, order = bookmarks) { return state._parseBookmarkBackup(JSON.stringify({app:'SCENE-FLIX',version:1,bookmarks,order})); }
assert.throws(() => parse(['<script>']));
assert.throws(() => state._parseBookmarkBackup('{"app":"other"}'));
assert.throws(() => parse(Array(10001).fill(a)));
assert.deepEqual(Array.from(parse([a,a,b],[b,c,b,a]).order),[b,a]);
assert.equal(state._mergeBookmarkBackup(parse([a,b],[b,a])),2);
assert.deepEqual(Array.from(state._bmOrder),[b,a]);
assert.equal(state._mergeBookmarkBackup(parse([a,b,c],[c,a,b])),1);
assert.deepEqual(Array.from(state._bmOrder),[b,a,c]);
assert.equal(state._mergeBookmarkBackup(parse([a,b,c])),0);
stored.clear();stored.set('rescene-bookmarks',JSON.stringify([a]));
failKey='sceneflix-bookmark-order-v1';
const before=[...stored];
assert.throws(() => state._mergeBookmarkBackup(parse([b,c])));
assert.deepEqual([...stored],before);
for(const name of ['performance-v1.js','web-vitals-v6.2.3.min.js'])new vm.Script(fs.readFileSync(path.join(root,'assets/features',name),'utf8'));
console.log('PASS: backup validation, deduplication, merge order, idempotency, storage failure rollback and performance script syntax');
