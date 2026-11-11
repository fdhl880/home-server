// N: Live Worldwide & Bloomberg News Wire with desk filters, BN priority badge, sentiment, and in-panel Story Reader
import { api, h, baseStyle, header, fmtTime, arr, srcLabel, down, poll, ENDPOINTS } from './common.js';

const POS = ['surge', 'rally', 'gain', 'beat', 'record', 'rise', 'jump', 'bull', 'upgrade', 'approve', 'soar', 'growth', 'optimism', 'profit', 'Climb', 'higher', 'rebound', 'cut rate', 'stimulus'];
const NEG = ['plunge', 'fall', 'drop', 'miss', 'crash', 'loss', 'bear', 'downgrade', 'hack', 'ban', 'lawsuit', 'slump', 'fear', 'recession', 'retreat', 'sink', 'tariff', 'war', 'default', 'crisis', 'inflation'];

export function normalize(a) {
  const ts = a.ts ?? a.time ?? a.published ?? a.publishedAt ?? a.pubDate ?? a.datetime;
  const pub = a.publisher || a.source || 'BN';
  const isBbg = a.wire === 'BN' || /bloomberg|^BN\b/i.test(pub) || /bloomberg/i.test(a.title || '');
  return {
    id: a.id || '',
    title: String(a.title || a.headline || '').trim(),
    url: a.url || a.link || '',
    source: pub,
    wire: a.wire || (isBbg ? 'BN' : pub.slice(0, 5).toUpperCase()),
    isBbg,
    ts: typeof ts === 'string' && /^\d+$/.test(ts) ? +ts : ts,
    category: a.category || a.type || 'markets',
    desk: a.desk || a.category || 'markets',
    summary: a.summary || a.description || a.title || '',
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
      return uni > 0 && inter / uni >= 0.72;
    });
    if (!dup) { it._t = t; out.push(it); }
  }
  return out.map(o => { delete o._t; return o; });
}

export function sentiment(it) {
  if (it.sentiment) {
    const s = String(it.sentiment).toLowerCase();
    return s.startsWith('pos') || s.startsWith('bull') ? 'POS' : s.startsWith('neg') || s.startsWith('bear') ? 'NEG' : 'NEU';
  }
  const l = (it.title + ' ' + (it.summary || '')).toLowerCase();
  const p = POS.filter(w => l.includes(w)).length, n = NEG.filter(w => l.includes(w)).length;
  return p > n ? 'POS' : n > p ? 'NEG' : 'NEU';
}

export function renderStoryModal(t, it, host, onBack) {
  host.innerHTML = '';
  const s = sentiment(it);
  const sCol = s === 'POS' ? t.up : s === 'NEG' ? t.down : t.label;
  const card = h('div', { style: { border: '1px solid ' + t.amber, background: '#050505', padding: '10px', margin: '4px 0' } },
    h('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid ' + t.border, paddingBottom: '6px', marginBottom: '8px' } },
      h('span', { style: { background: t.amber, color: '#000', fontWeight: 'bold', padding: '1px 6px' } }, `${it.wire || 'BN'} WIRE STORY // ${(it.source || 'BLOOMBERG').toUpperCase()}`),
      h('div', { style: { display: 'flex', gap: '6px' } },
        it.url ? h('a', { href: it.url, target: '_blank', rel: 'noopener noreferrer', style: { background: '#152538', color: t.label, border: '1px solid ' + t.label, padding: '1px 8px', textDecoration: 'none', fontWeight: 'bold' } }, 'OPEN ORIGINAL SOURCE ↗') : null,
        h('button', { onclick: onBack, style: { background: t.down, color: '#fff', border: 'none', padding: '1px 8px', fontWeight: 'bold', cursor: 'pointer' } }, '× BACK TO WIRE <ESC>')
      )
    ),
    h('div', { style: { fontSize: '15px', fontWeight: 'bold', color: '#fff', marginBottom: '6px', lineHeight: '1.4' } }, it.title),
    h('div', { style: { color: t.label, fontSize: '11px', marginBottom: '10px' } },
      `TIMESTAMP: ${fmtTime(it.ts)} UTC   |   DESK: ${(it.desk || it.category || 'GLOBAL').toUpperCase()}   |   SENTIMENT: `,
      h('span', { style: { color: sCol, fontWeight: 'bold' } }, s === 'POS' ? 'BULLISH (+)' : s === 'NEG' ? 'BEARISH (-)' : 'NEUTRAL')
    ),
    h('div', { style: { color: t.amber, fontSize: '12.5px', lineHeight: '1.55', padding: '8px', background: '#0a0a0a', borderLeft: '3px solid ' + t.amber, whiteSpace: 'pre-wrap' } },
      it.summary && it.summary !== it.title
        ? it.summary
        : `${it.title}\n\n[Dispatched via ${it.source || 'Bloomberg Global Wire'} (${it.wire || 'BN'}) — Click "OPEN ORIGINAL SOURCE ↗" above to read the complete web dispatch.]`
    )
  );
  host.append(card);
}

export function renderList(t, items, host) {
  host.innerHTML = '';
  if (!items.length) { host.append(h('div', { style: { color: t.label, padding: '6px' } }, 'NO MATCHING HEADLINES FOR SELECTED DESK')); return; }
  items.forEach((it, idx) => {
    const s = sentiment(it);
    const col = s === 'POS' ? t.up : s === 'NEG' ? t.down : t.label;
    const wireBadge = it.isBbg
      ? h('span', { style: { background: t.amber, color: '#000', fontWeight: 'bold', padding: '0 4px', marginRight: '5px', fontSize: '10.5px' } }, 'BN')
      : h('span', { style: { background: '#1c2836', color: t.label, fontWeight: 'bold', padding: '0 4px', marginRight: '5px', fontSize: '10.5px' } }, (it.wire || 'WIRE').slice(0, 5));

    const row = h('div', {
      style: {
        borderBottom: '1px solid #161616',
        padding: '2.5px 4px',
        whiteSpace: 'nowrap',
        overflow: 'hidden',
        textOverflow: 'ellipsis',
        cursor: 'pointer'
      },
      onclick: () => renderStoryModal(t, it, host, () => renderList(t, items, host))
    },
      h('span', { style: { color: '#777', display: 'inline-block', width: '2.4em' } }, `${idx + 1})`),
      wireBadge,
      h('span', { style: { color: t.label, marginRight: '6px', fontSize: '11px' } }, fmtTime(it.ts)),
      h('span', { style: { color: col, display: 'inline-block', width: '3.0em', fontWeight: 'bold', fontSize: '10.5px' } }, s),
      h('span', { style: { color: '#9a9a9a', display: 'inline-block', width: '11.5em', overflow: 'hidden', textOverflow: 'ellipsis', verticalAlign: 'bottom', marginRight: '6px', fontSize: '11px' } }, it.source || 'BN Bloomberg'),
      h('span', { style: { color: it.isBbg ? '#fff' : t.amber, fontWeight: it.isBbg ? 'bold' : 'normal' } }, it.title)
    );
    row.addEventListener('mouseenter', () => { row.style.background = '#181818'; });
    row.addEventListener('mouseleave', () => { row.style.background = 'transparent'; });
    host.append(row);
  });
}

const DESKS = [
  ['all', 'WORLDWIDE'],
  ['bloomberg', 'BN BLOOMBERG'],
  ['markets', 'MARKETS'],
  ['macro', 'MACRO/FED'],
  ['apac', 'APAC/ASIA'],
  ['indonesia', 'INDONESIA'],
  ['emea', 'EMEA'],
  ['tech', 'TECH/AI'],
  ['commodities', 'CMDTY/OIL'],
  ['crypto', 'CRYPTO']
];

export function mount(container, ctx) {
  const t = baseStyle(container, ctx);
  const hd = header(t, '91) Actions  92) Desks  93) Sources  |  N - Bloomberg Real-Time Worldwide News Wire');
  let activeDesk = 'all';
  const deskBar = h('div', { style: { display: 'flex', gap: '3px', flexWrap: 'wrap', marginBottom: '4px', paddingBottom: '3px', borderBottom: '1px solid ' + t.border } });
  const input = h('input', { placeholder: 'SEARCH KEYWORD / TICKER...', style: { background: t.bg, color: t.amber, border: '1px solid ' + t.border, font: 'inherit', width: '14em', padding: '1px 4px' } });
  const sel = h('select', { style: { background: t.bg, color: t.amber, border: '1px solid ' + t.border, font: 'inherit' } },
    ...['ALL', 'POS', 'NEG', 'NEU'].map(v => h('option', { value: v }, v)));
  const symBtn = h('label', { style: { color: t.label, fontSize: '11px', cursor: 'pointer' } }, h('input', { type: 'checkbox' }), ' FILTER ACTIVE SYM');
  const body = h('div');
  container.append(hd.el, deskBar, h('div', { style: { marginBottom: '4px', display: 'flex', gap: '6px', alignItems: 'center' } }, input, sel, symBtn), body);
  let items = [], symbol = (ctx && ctx.symbol) || '';

  const buildDesks = () => {
    deskBar.innerHTML = '';
    for (const [code, label] of DESKS) {
      const on = activeDesk === code;
      deskBar.append(h('button', {
        style: {
          background: on ? t.amber : '#111',
          color: on ? '#000' : t.label,
          border: '1px solid ' + (on ? t.amber : t.border),
          fontWeight: on ? 'bold' : 'normal',
          padding: '1px 5px',
          fontSize: '10.5px',
          cursor: 'pointer'
        },
        onclick: () => { activeDesk = code; buildDesks(); load(); }
      }, label));
    }
  };

  const view = () => {
    const q = input.value.trim().toLowerCase();
    const useSym = symBtn.firstChild.checked && symbol;
    renderList(t, items.filter(i =>
      (!q || (i.title + ' ' + i.source + ' ' + (i.summary || '')).toLowerCase().includes(q)) &&
      (sel.value === 'ALL' || sentiment(i) === sel.value) &&
      (!useSym || i.title.toLowerCase().includes(symbol.toLowerCase().replace(/(usdt|\.p|-usd|\.jk)$/i, '')))), body);
  };
  input.addEventListener('input', view); sel.addEventListener('change', view); symBtn.addEventListener('change', view);

  const load = async () => {
    try {
      const { data, env } = await api(ctx, `${ENDPOINTS.news}?cat=${activeDesk}&limit=120`);
      items = dedupe(arr(data).map(normalize));
      hd.right.textContent = `${items.length} STORIES • ${srcLabel(env) || 'BN LIVE'}`;
      view();
    } catch (_) { items = []; body.innerHTML = ''; hd.right.textContent = ''; down(body, t); }
  };
  buildDesks();
  const stop = poll(load, 45000);
  const unsub = ctx.subscribe ? ctx.subscribe('news', load) : null;
  return { unmount() { stop(); if (unsub) unsub(); container.innerHTML = ''; }, setSymbol(s) { symbol = s || ''; view(); } };
}
