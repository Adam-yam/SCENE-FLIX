import Fuse from 'fuse.js';
import { getChoseong } from 'es-hangul';
const normalize = value => String(value ?? '').normalize('NFC').toLowerCase().trim();
const compact = value => value.replace(/[\s\p{P}\p{S}]+/gu, '');
const cache = new WeakMap();
function record(item, text) {
  const previous = item && typeof item === 'object' ? cache.get(item) : null;
  if (previous?.source === text) return previous;
  const value = normalize(text);
  const result = {source: text, text: value, compact: compact(value), initials: compact(getChoseong(value))};
  if (item && typeof item === 'object') cache.set(item, result);
  return result;
}
function rank(items, query, getText, ordered = true) {
  const q = normalize(query);
  if (!q) return items.slice();
  const tokens = q.split(/\s+/u);
  const rows = items.map((item, index) => ({item, index, ...record(item, getText(item)), tier: 0, score: 0}));
  let candidates = rows;
  for (const token of tokens) {
    const key = compact(token);
    const initials = /^[ㄱ-ㅎ]+$/u.test(key);
    const direct = new Map();
    for (const row of candidates) {
      if (row.text.includes(token) || (key && row.compact.includes(key))) direct.set(row, 0);
      else if (initials && row.initials.includes(key)) direct.set(row, 1);
    }
    const fuzzy = new Map();
    if (!initials && key.length >= 3 && key.length <= 32 && !/\d/u.test(key)) {
      const pending = candidates.filter(row => !direct.has(row));
      if (pending.length) {
        const engine = new Fuse(pending, {keys: ['text', 'compact'], threshold: 0.34, ignoreLocation: true, ignoreFieldNorm: true, includeScore: true});
        for (const result of engine.search(key)) fuzzy.set(result.item, result.score ?? 1);
      }
    }
    candidates = candidates.filter(row => {
      if (direct.has(row)) { row.tier = Math.max(row.tier, direct.get(row)); return true; }
      if (fuzzy.has(row)) { row.tier = 2; row.score += fuzzy.get(row); return true; }
      return false;
    });
    if (!candidates.length) break;
  }
  if (ordered) candidates.sort((a,b) => a.tier - b.tier || a.score - b.score || a.index - b.index);
  return candidates.map(row => row.item);
}
window.SceneSearch = Object.freeze({rank});
