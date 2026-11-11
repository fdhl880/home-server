// N: live news feed with filters, dedupe, source+time, sentiment tag.
import { api, h, baseStyle, header, fmtTime, arr, srcLabel, down, poll, ENDPOINTS } from './common.js';

const POS = ['surge', 'rally', 'gain', 'beat', 'record', 'rise', 'jump', 'bull', 'upgrade', 'approve', 'soar', 'growth'];
const NEG = ['plunge', 'fall', 'drop', 'miss', 'crash', 'loss', 'bear', 'downgrade', 'hack', 'ban', 'lawsuit', 'slump', 'fear', 'recession'];

// Normalise whatever the API returns into a stable shape.
export function normalize(a) {
  const ts = a.ts ?? a.time ?? a.published ?? a.publishedAt ?? a.pubDate ?? a.datetime;
  return {
    title: String(a.title || a.headline || '').trim(),
    url: a.url || a.link || '',
    source: a.publisher || a.source || '',
    ts: typeof ts === 'string' && /^\d+$/.test(ts) ? +ts : ts,
    category: a.category || a.type || '',
    sentiment: a.sentiment || null,
  };
}

const tok = s => new Set(s.toLowerCase().replace(/[^a-z0-9 ]/g, ' ').split(/\s+/).filter(w => w.length > 2));
export function dedupe(items) {
  const out = [];
  for (const it of items) {
    if (!it.title) continue;
    const t = tok(it.title);
    const dup = out.some(o => {
      if (o.url && o.url === it.url) return true;
      let inter = 0; for (const w of t) if (o._t.has(w)) inter++;
      const uni = t.size + o._t.size - inter;
      return uni > 0 && inter / uni >= 0.7;
    });
    if (!dup) { it._t = t; out.push(it); }
  }
  return out.map(o => { delete o._t; return o; });
}

// Keyword tag used only when the API supplies no sentiment; marked "kw".
export function sentiment(it) {
  if (it.sentiment) {
    const s = String(it.sentiment).toLowerCase();
    return s.startsWith('pos') || s.startsWith('bull') ? 'POS' : s.startsWith('neg') || s.startsWith('bear') ? 'NEG' : 'NEU';
  }
  const l = it.title.toLowerCase();
  const p = POS.filter(w => l.includes(w)).length, n = NEG.filter(w => l.includes(w)).length;
  return p > n ? 'POS' : n > p ? 'NEG' : 'NEU';
}

export function renderList(t, items, host) {
  host.innerHTML = '';
  if (!items.length) { host.append(h('div', { style: { color: t.label } }, 'NO MATCHING HEADLINES')); return; }
  for (const it of items) {
    const s = sentiment(it);
    const col = s === 'POS' ? t.up : s === 'NEG' ? t.down : t.label;
    host.append(h('div', { style: { borderBottom: '1px solid ' + t.border, padding: '2px 0', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' } },
      h('span', { style: { color: t.label } }, fmtTime(it.ts) + ' '),
      h('span', { style: { color: col, display: 'inline-block', width: '3.2em' } }, s),
      h('span', { style: { color: t.label } }, (it.source || '?').slice(0, 14).padEnd(14, '\u00a0') + ' '),
      it.url ? h('a', { href: it.url, target: '_blank', rel: 'noopener noreferrer', style: { color: t.amber, textDecoration: 'none' } }, it.title) : it.title));
  }
}

export function mount(container, ctx) {
  const t = baseStyle(container, ctx);
  const hd = header(t, 'N  News');
  const input = h('input', { placeholder: 'FILTER', style: { background: t.bg, color: t.amber, border: '1px solid ' + t.border, font: 'inherit', width: '10em', padding: '1px 3px' } });
  const sel = h('select', { style: { background: t.bg, color: t.amber, border: '1px solid ' + t.border, font: 'inherit' } },
    ...['ALL', 'POS', 'NEG', 'NEU'].map(v => h('option', { value: v }, v)));
  const symBtn = h('label', { style: { color: t.label } }, h('input', { type: 'checkbox' }), ' SYM');
  const body = h('div');
  container.append(hd.el, h('div', { style: { marginBottom: '3px' } }, input, ' ', sel, ' ', symBtn), body);
  let items = [], symbol = (ctx && ctx.symbol) || '';

  const view = () => {
    const q = input.value.trim().toLowerCase();
    const useSym = symBtn.firstChild.checked && symbol;
    renderList(t, items.filter(i =>
      (!q || (i.title + ' ' + i.source).toLowerCase().includes(q)) &&
      (sel.value === 'ALL' || sentiment(i) === sel.value) &&
      (!useSym || i.title.toLowerCase().includes(symbol.toLowerCase().replace(/(usdt|usd)$/, '')))), body);
  };
  input.addEventListener('input', view); sel.addEventListener('change', view); symBtn.addEventListener('change', view);

  const load = async () => {
    try {
      const { data, env } = await api(ctx, ENDPOINTS.news + '?limit=100');
      items = dedupe(arr(data).map(normalize)).sort((a, b) => new Date(b.ts) - new Date(a.ts));
      hd.right.textContent = srcLabel(env) || 'LIVE';
      view();
    } catch (_) { items = []; body.innerHTML = ''; hd.right.textContent = ''; down(body, t); }
  };
  const stop = poll(load, 60000);
  const unsub = ctx.subscribe ? ctx.subscribe('news', load) : null;
  return { unmount() { stop(); if (unsub) unsub(); container.innerHTML = ''; }, setSymbol(s) { symbol = s || ''; view(); } };
}
