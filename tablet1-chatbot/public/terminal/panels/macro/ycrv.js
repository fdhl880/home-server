// YCRV: US Treasury yield curve via /api/terminal/macro?curve=1 -> data.curve[{tenor,series,value,date}]
import { api, h, baseStyle, header, num, arr, srcLabel, down, poll, lineChart, ENDPOINTS } from '../news/common.js';

const ORDER = ['1M', '3M', '6M', '1Y', '2Y', '3Y', '5Y', '7Y', '10Y', '20Y', '30Y'];

export function mount(container, ctx) {
  const t = baseStyle(container, ctx);
  const hd = header(t, 'YCRV  US Yield Curve');
  const body = h('div');
  container.append(hd.el, body);
  const load = async () => {
    try {
      const { data, env } = await api(ctx, ENDPOINTS.macro + '?curve=1');
      const rows = arr(data.curve).map(r => ({ m: String(r.tenor).toUpperCase(), y: parseFloat(r.value), d: r.date }))
        .filter(r => isFinite(r.y)).sort((a, b) => ORDER.indexOf(a.m) - ORDER.indexOf(b.m));
      if (!rows.length) throw new Error('empty');
      body.innerHTML = '';
      body.append(lineChart(t, rows.map((r, i) => ({ x: i, y: r.y })), { h: 120 }));
      const tbl = h('table', { style: { width: '100%', borderCollapse: 'collapse', marginTop: '4px' } });
      for (const r of rows) tbl.append(h('tr', {}, h('td', { style: { color: t.label } }, r.m), h('td', { style: { textAlign: 'right' } }, num(r.y) + '%'), h('td', { style: { textAlign: 'right', color: t.label } }, r.d || '')));
      body.append(tbl);
      const g = m => (rows.find(r => r.m === m) || {}).y;
      if (g('10Y') != null && g('2Y') != null) {
        const s = g('10Y') - g('2Y');
        body.append(h('div', { style: { marginTop: '4px', color: s < 0 ? t.down : t.up } }, '10Y-2Y SPREAD ' + num(s * 100, 0) + ' bp' + (s < 0 ? ' INVERTED' : '')));
      }
      hd.right.textContent = srcLabel(env) || 'FRED';
    } catch (_) { body.innerHTML = ''; hd.right.textContent = ''; down(body, t); }
  };
  const stop = poll(load, 1800000);
  return { unmount() { stop(); container.innerHTML = ''; }, setSymbol() {} };
}
