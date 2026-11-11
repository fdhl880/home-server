// Shared helpers for WP5 panels (news + macro). No external deps, no dummy data.
// ctx contract (agreed with shell):
//   ctx.fetchJson(path, {signal}) -> Promise<any>  (rejects on HTTP/network error)
//   ctx.symbol                    -> current security string (may be '')
//   ctx.subscribe(topic, cb)      -> unsubscribe fn (optional; may be undefined)
//   ctx.theme                     -> {bg,panel,amber,label,up,down,border,font}
// mount(container, ctx) returns {unmount(), setSymbol(sym)}.

export const NA = 'N/A (source down)';
export const ENDPOINTS = {
  topNews: '/api/terminal/news?cat=general&limit=30',
  news: '/api/terminal/news',
  calendar: '/api/terminal/calendar',
  fng: '/api/terminal/fng',
  macro: '/api/terminal/macro',   // ?series=CPIAUCSL  | ?curve=1
  quote: '/api/terminal/quote',   // ?symbols=A,B
};

// Fetch an API.md envelope. Throws if ok=false, data null, or status N/A.
// Returns {data, env}; env carries source/mode/ts for the header label.
export async function api(ctx, path) {
  const env = await ctx.fetchJson(path);
  if (!env || env.ok === false || env.data == null || env.status === 'N/A') throw new Error((env && env.error) || 'source down');
  return { data: env.data, env };
}

const DEFAULT_THEME = { bg: '#000000', panel: '#0B0B0B', amber: '#FFB000', label: '#4DA3FF', up: '#00D26A', down: '#FF3B30', border: '#2A2A2A', font: "'JetBrains Mono','IBM Plex Mono',monospace" };

export function theme(ctx) { return Object.assign({}, DEFAULT_THEME, ctx && ctx.theme); }

export function h(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  for (const k in (attrs || {})) {
    if (k === 'style') Object.assign(e.style, attrs[k]);
    else if (k.startsWith('on')) e.addEventListener(k.slice(2), attrs[k]);
    else if (k === 'text') e.textContent = attrs[k];
    else e.setAttribute(k, attrs[k]);
  }
  for (const c of kids.flat()) if (c != null) e.append(c.nodeType ? c : document.createTextNode(String(c)));
  return e;
}

export function baseStyle(container, ctx) {
  const t = theme(ctx);
  container.innerHTML = '';
  Object.assign(container.style, { background: t.panel, color: t.amber, fontFamily: t.font, fontSize: '12px', lineHeight: '1.3', fontVariantNumeric: 'tabular-nums', overflow: 'auto', height: '100%', boxSizing: 'border-box', padding: '4px' });
  return t;
}

export function header(t, title, extra) {
  const right = h('span', { style: { color: t.label, float: 'right' } }, extra || '');
  return { el: h('div', { style: { borderBottom: '1px solid ' + t.border, paddingBottom: '2px', marginBottom: '3px', textTransform: 'uppercase', fontWeight: 'bold' } }, title, right), right };
}

export function fmtTime(ts) {
  const d = new Date(typeof ts === 'number' && ts < 1e12 ? ts * 1000 : ts);
  if (isNaN(d)) return '--:--';
  const p = n => String(n).padStart(2, '0');
  const now = new Date();
  const same = d.toDateString() === now.toDateString();
  return (same ? '' : p(d.getUTCMonth() + 1) + '/' + p(d.getUTCDate()) + ' ') + p(d.getUTCHours()) + ':' + p(d.getUTCMinutes()) + 'Z';
}

export function num(v, dp = 2) {
  const n = typeof v === 'string' ? parseFloat(v) : v;
  return (n == null || !isFinite(n)) ? '--' : n.toLocaleString('en-US', { minimumFractionDigits: dp, maximumFractionDigits: dp });
}

// Accept array or {data|items|results|articles|events|observations: []}
export function arr(x) {
  if (Array.isArray(x)) return x;
  if (x && typeof x === 'object') for (const k of ['data', 'items', 'results', 'articles', 'events', 'observations']) if (Array.isArray(x[k])) return x[k];
  return [];
}

export function srcLabel(env) {
  if (!env || typeof env !== 'object' || Array.isArray(env)) return '';
  const parts = [env.source, env.mode, env.status === 'PARTIAL' ? 'PARTIAL' : '', env.ts ? fmtTime(env.ts) : ''].filter(Boolean);
  return parts.join(' ');
}

export function down(container, t, msg) {
  container.append(h('div', { style: { color: t.down, padding: '6px' } }, msg || NA));
}

// Polling with abort + unmount safety. Returns stop().
export function poll(fn, ms) {
  let stopped = false, timer = null;
  const run = async () => { if (stopped) return; try { await fn(); } catch (_) {} if (!stopped) timer = setTimeout(run, ms); };
  run();
  return () => { stopped = true; clearTimeout(timer); };
}

// Minimal SVG line chart. points: [{x:number(ts/idx), y:number}]
export function lineChart(t, points, opts = {}) {
  const W = opts.w || 320, H = opts.h || 110, P = 4;
  const pts = points.filter(p => isFinite(p.y));
  const ns = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(ns, 'svg');
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`); svg.setAttribute('width', '100%'); svg.setAttribute('height', H);
  svg.style.background = t.bg; svg.style.border = '1px solid ' + t.border;
  if (pts.length < 2) return svg;
  const xs = pts.map(p => p.x), ys = pts.map(p => p.y);
  const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
  const sx = v => P + (x1 === x0 ? 0 : (v - x0) / (x1 - x0)) * (W - 2 * P);
  const sy = v => H - P - (y1 === y0 ? 0.5 : (v - y0) / (y1 - y0)) * (H - 2 * P);
  const path = document.createElementNS(ns, 'polyline');
  path.setAttribute('points', pts.map(p => sx(p.x).toFixed(1) + ',' + sy(p.y).toFixed(1)).join(' '));
  path.setAttribute('fill', 'none'); path.setAttribute('stroke', opts.color || t.amber); path.setAttribute('stroke-width', '1');
  svg.append(path);
  for (const [v, anchor] of [[y1, P + 8], [y0, H - P]]) {
    const tx = document.createElementNS(ns, 'text');
    tx.setAttribute('x', W - P); tx.setAttribute('y', anchor); tx.setAttribute('text-anchor', 'end');
    tx.setAttribute('fill', t.label); tx.setAttribute('font-size', '9'); tx.textContent = num(v, opts.dp ?? 2);
    svg.append(tx);
  }
  return svg;
}
