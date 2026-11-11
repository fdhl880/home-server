// MACRO: FRED charts (CPI, GDP, UNRATE, FEDFUNDS) via /api/terminal/macro?series=...
import { api, h, baseStyle, header, num, arr, srcLabel, poll, lineChart, ENDPOINTS } from '../news/common.js';

export const SERIES = ['CPIAUCSL', 'GDP', 'UNRATE', 'FEDFUNDS'];

function pointsOf(s) {
  return arr(s && s.obs).map(o => ({ x: new Date(o.date).getTime(), y: parseFloat(o.value) })).filter(o => isFinite(o.x) && isFinite(o.y)).sort((a, b) => a.x - b.x);
}

function block(t, id, s, pts) {
  const last = pts[pts.length - 1], prev = pts[pts.length - 2];
  const d = last && prev ? last.y - prev.y : null;
  return h('div', { style: { marginBottom: '6px' } },
    h('div', {}, h('span', { style: { color: t.label } }, id + ' '), (s && s.title) || '',
      h('span', { style: { float: 'right' } }, last ? num(last.y) : '--', ' ',
        h('span', { style: { color: d == null ? t.label : d >= 0 ? t.up : t.down } }, d == null ? '' : (d >= 0 ? '+' : '') + num(d)))),
    lineChart(t, pts.slice(-120), { h: 90 }),
    h('div', { style: { color: t.label, fontSize: '10px' } }, ((s && s.unit) || '') + (last ? ' LAST OBS ' + new Date(last.x).toISOString().slice(0, 10) : '')));
}

export function mount(container, ctx) {
  const t = baseStyle(container, ctx);
  const hd = header(t, 'MACRO  FRED Series');
  const body = h('div');
  container.append(hd.el, body);
  const load = async () => {
    body.innerHTML = '';
    let res;
    try { res = await api(ctx, ENDPOINTS.macro + '?series=' + SERIES.join(',')); }
    catch (_) { hd.right.textContent = ''; body.append(h('div', { style: { color: t.down, padding: '6px' } }, 'N/A (source down)')); return; }
    const all = (res.data && res.data.series) || {};
    for (const id of SERIES) {
      const pts = pointsOf(all[id]);
      body.append(pts.length ? block(t, id, all[id], pts) : h('div', { style: { color: t.down, marginBottom: '6px' } }, id + ': N/A (source down)'));
    }
    hd.right.textContent = srcLabel(res.env) || 'FRED';
  };
  const stop = poll(load, 3600000);
  return { unmount() { stop(); container.innerHTML = ''; }, setSymbol() {} };
}
