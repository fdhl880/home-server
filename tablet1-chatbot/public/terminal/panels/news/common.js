// Shared helpers for WP5 panels (news + macro). No external deps, no dummy data.
export const NA = 'N/A (source down)';
export const ENDPOINTS = {
  topNews: '/api/terminal/news?cat=all&limit=120',
  news: '/api/terminal/news',
  calendar: '/api/terminal/calendar',
  fng: '/api/terminal/fng',
  macro: '/api/terminal/macro',   // ?series=CPIAUCSL  | ?curve=1
  quote: '/api/terminal/quote',   // ?symbols=A,B
};

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
  Object.assign(container.style, { background: t.panel, color: t.amber, fontFamily: t.font, fontSize: '12px', lineHeight: '1.35', fontVariantNumeric: 'tabular-nums', overflow: 'auto', height: '100%', boxSizing: 'border-box', padding: '4px' });
  return t;
}

export function header(t, title, extra) {
  const right = h('span', { style: { color: t.label, float: 'right', fontSize: '11px' } }, extra || '');
  return {
    el: h('div', {
      style: {
        background: '#140c00',
        borderBottom: '1px solid ' + t.amber,
        padding: '2px 6px',
        marginBottom: '4px',
        textTransform: 'uppercase',
        fontWeight: 'bold',
        color: t.amber
      }
    }, title, right),
    right
  };
}

export function fmtTime(ts) {
  const d = new Date(typeof ts === 'number' && ts < 1e12 ? ts * 1000 : ts);
  if (isNaN(d)) return '--:--';
  const p = n => String(n).padStart(2, '0');
  const now = new Date();
  const same = d.toDateString() === now.toDateString();
  return (same ? '' : p(d.getUTCMonth() + 1) + '/' + p(d.getUTCDate()) + ' ') + p(d.getUTCHours()) + ':' + p(d.getUTCMinutes());
}

export function num(v, dp = 2) {
  const n = typeof v === 'string' ? parseFloat(v) : v;
  return (n == null || !isFinite(n)) ? '--' : n.toLocaleString('en-US', { minimumFractionDigits: dp, maximumFractionDigits: dp });
}

export function arr(x) {
  if (Array.isArray(x)) return x;
  if (x && typeof x === 'object') for (const k of ['data', 'items', 'results', 'articles', 'events', 'observations']) if (Array.isArray(x[k])) return x[k];
  return [];
}

export function srcLabel(env) {
  if (!env || typeof env !== 'object' || Array.isArray(env)) return '';
  const parts = [env.source, env.mode, env.status === 'PARTIAL' ? 'PARTIAL' : '', env.ts ? fmtTime(env.ts) : ''].filter(Boolean);
  return parts.join(' • ');
}

export function down(container, t, msg) {
  container.append(h('div', { style: { color: t.down, padding: '6px' } }, msg || NA));
}

export function poll(fn, ms) {
  let stopped = false, timer = null;
  const run = async () => { if (stopped) return; try { await fn(); } catch (_) {} if (!stopped) timer = setTimeout(run, ms); };
  run();
  return () => { stopped = true; clearTimeout(timer); };
}

// High-Clarity Bloomberg SVG Area + Grid Chart
export function lineChart(t, points, opts = {}) {
  const W = opts.w || 640, H = opts.h || 115, PL = 8, PR = 54, PT = 10, PB = 16;
  const pts = points.filter(p => isFinite(p.y));
  const ns = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(ns, 'svg');
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  svg.setAttribute('preserveAspectRatio', 'none');
  svg.style.cssText = `width:100%;height:${H}px;display:block;background:#000;border:1px solid ${t.border}`;
  if (pts.length < 2) return svg;

  const xs = pts.map(p => p.x), ys = pts.map(p => p.y);
  const x0 = Math.min(...xs), x1 = Math.max(...xs);
  const minVal = Math.min(...ys), maxVal = Math.max(...ys);
  const padY = (maxVal - minVal) * 0.08 || 0.5;
  const y0 = minVal - padY, y1 = maxVal + padY;

  const plotW = W - PL - PR;
  const plotH = H - PT - PB;
  const sx = v => PL + (x1 === x0 ? 0 : ((v - x0) / (x1 - x0)) * plotW);
  const sy = v => PT + plotH - (y1 === y0 ? 0.5 : ((v - y0) / (y1 - y0)) * plotH);

  // Horizontal & vertical Bloomberg grid lines
  for (let i = 0; i <= 3; i++) {
    const gy = PT + (plotH * i) / 3;
    const gl = document.createElementNS(ns, 'line');
    gl.setAttribute('x1', PL); gl.setAttribute('x2', W - PR);
    gl.setAttribute('y1', gy.toFixed(1)); gl.setAttribute('y2', gy.toFixed(1));
    gl.setAttribute('stroke', '#191919');
    gl.setAttribute('stroke-dasharray', '2,2');
    svg.append(gl);

    const valAtGrid = y1 - ((y1 - y0) * i) / 3;
    const lbl = document.createElementNS(ns, 'text');
    lbl.setAttribute('x', W - 4);
    lbl.setAttribute('y', (gy + 3).toFixed(1));
    lbl.setAttribute('text-anchor', 'end');
    lbl.setAttribute('fill', '#666');
    lbl.setAttribute('font-size', '9.5');
    lbl.textContent = num(valAtGrid, opts.dp ?? 2);
    svg.append(lbl);
  }

  for (let i = 1; i <= 4; i++) {
    const gx = PL + (plotW * i) / 4;
    const vl = document.createElementNS(ns, 'line');
    vl.setAttribute('x1', gx.toFixed(1)); vl.setAttribute('x2', gx.toFixed(1));
    vl.setAttribute('y1', PT); vl.setAttribute('y2', PT + plotH);
    vl.setAttribute('stroke', '#141414');
    svg.append(vl);
  }

  const strokeCol = opts.color || t.amber;
  const coords = pts.map(p => `${sx(p.x).toFixed(1)},${sy(p.y).toFixed(1)}`);

  // Area fill polygon
  const area = document.createElementNS(ns, 'polygon');
  area.setAttribute('points', `${sx(pts[0].x).toFixed(1)},${(PT + plotH).toFixed(1)} ${coords.join(' ')} ${sx(pts[pts.length - 1].x).toFixed(1)},${(PT + plotH).toFixed(1)}`);
  area.setAttribute('fill', strokeCol === t.up ? 'rgba(0,210,106,0.14)' : strokeCol === t.down ? 'rgba(255,59,48,0.14)' : 'rgba(255,176,0,0.14)');
  svg.append(area);

  // Main line
  const path = document.createElementNS(ns, 'polyline');
  path.setAttribute('points', coords.join(' '));
  path.setAttribute('fill', 'none');
  path.setAttribute('stroke', strokeCol);
  path.setAttribute('stroke-width', '1.8');
  svg.append(path);

  // Latest point dot & price callout tag
  const lastPt = pts[pts.length - 1];
  const lx = sx(lastPt.x), ly = sy(lastPt.y);
  const dot = document.createElementNS(ns, 'circle');
  dot.setAttribute('cx', lx.toFixed(1));
  dot.setAttribute('cy', ly.toFixed(1));
  dot.setAttribute('r', '3');
  dot.setAttribute('fill', strokeCol);
  svg.append(dot);

  const tag = document.createElementNS(ns, 'text');
  tag.setAttribute('x', W - 4);
  tag.setAttribute('y', Math.max(PT + 8, Math.min(PT + plotH, ly + 3)).toFixed(1));
  tag.setAttribute('text-anchor', 'end');
  tag.setAttribute('fill', strokeCol);
  tag.setAttribute('font-size', '10');
  tag.setAttribute('font-weight', 'bold');
  tag.textContent = '◀ ' + num(lastPt.y, opts.dp ?? 2);
  svg.append(tag);

  // Min / Max Range Footer inside SVG
  const rangeTxt = document.createElementNS(ns, 'text');
  rangeTxt.setAttribute('x', PL + 2);
  rangeTxt.setAttribute('y', H - 3);
  rangeTxt.setAttribute('fill', t.label);
  rangeTxt.setAttribute('font-size', '9.5');
  rangeTxt.textContent = `HI: ${num(maxVal, opts.dp ?? 2)}   LO: ${num(minVal, opts.dp ?? 2)}   LAST: ${num(lastPt.y, opts.dp ?? 2)}`;
  svg.append(rangeTxt);

  return svg;
}
