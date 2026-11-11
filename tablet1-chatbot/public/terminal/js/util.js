export const $ = (s, r = document) => r.querySelector(s);
export function h(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  if (attrs) for (const [k, v] of Object.entries(attrs)) {
    if (k === 'class') e.className = v;
    else if (k === 'text') e.textContent = v;
    else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else if (v !== false && v != null) e.setAttribute(k, v);
  }
  for (const c of kids.flat()) if (c != null) e.append(c.nodeType ? c : document.createTextNode(c));
  return e;
}
export const NA = 'N/A';
export function fmtPx(v) {
  if (v == null || !isFinite(v)) return NA;
  const a = Math.abs(v);
  const d = a >= 100 ? 2 : a >= 1 ? 4 : a >= 0.01 ? 5 : 8;
  return v.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
}
export function fmtNum(v, d = 2) {
  if (v == null || !isFinite(v)) return NA;
  return v.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
}
export function fmtVol(v) {
  if (v == null || !isFinite(v)) return NA;
  const a = Math.abs(v);
  if (a >= 1e12) return (v / 1e12).toFixed(2) + 'T';
  if (a >= 1e9) return (v / 1e9).toFixed(2) + 'B';
  if (a >= 1e6) return (v / 1e6).toFixed(2) + 'M';
  if (a >= 1e3) return (v / 1e3).toFixed(1) + 'K';
  return v.toFixed(2);
}
export function fmtPct(v) {
  if (v == null || !isFinite(v)) return NA;
  return (v > 0 ? '+' : '') + v.toFixed(2) + '%';
}
export function fmtChg(v) {
  if (v == null || !isFinite(v)) return NA;
  return (v > 0 ? '+' : '') + fmtPx(v);
}
export const dirCls = v => (v == null || !isFinite(v) || v === 0) ? '' : v > 0 ? 'up' : 'dn';
export function fmtTime(ts, withDate) {
  if (!ts) return NA;
  const d = new Date(ts);
  const p = n => String(n).padStart(2, '0');
  const t = `${p(d.getUTCHours())}:${p(d.getUTCMinutes())}:${p(d.getUTCSeconds())}Z`;
  return withDate ? `${d.getUTCFullYear()}-${p(d.getUTCMonth() + 1)}-${p(d.getUTCDate())} ${t}` : t;
}
export function fmtDate(ts) {
  const d = new Date(ts), p = n => String(n).padStart(2, '0');
  return `${d.getUTCFullYear()}-${p(d.getUTCMonth() + 1)}-${p(d.getUTCDate())}`;
}
export function flash(el, dir) {
  if (!el || !dir) return;
  const c = dir > 0 ? 'fl-up' : 'fl-dn';
  el.classList.remove('fl-up', 'fl-dn');
  clearTimeout(el._fl);
  el.classList.add(c);
  el._fl = setTimeout(() => el.classList.remove(c), 350);
}
export function setText(el, text, cls) {
  if (el.textContent !== text) el.textContent = text;
  if (cls !== undefined && el._cls !== cls) {
    if (el._cls) el.classList.remove(el._cls);
    if (cls) el.classList.add(cls);
    el._cls = cls;
  }
}
export function throttle(fn, ms) {
  let last = 0, t = null;
  return (...a) => {
    const now = Date.now();
    if (now - last >= ms) { last = now; fn(...a); }
    else if (!t) t = setTimeout(() => { t = null; last = Date.now(); fn(...a); }, ms - (now - last));
  };
}
export const isCryptoSym = s => /^[A-Z0-9]{2,}(USDT|USDC|BUSD|FDUSD|BTC|ETH|BNB)(\.P)?$/.test(s);
export const stripP = s => s.replace(/\.P$/, '');
const LS = {
  get(k, d) { try { const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* quota */ } }
};
export { LS };
