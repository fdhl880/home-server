// MACRO / ECST: World & US Macroeconomic Indicators (2x2 Chart Matrix)
import { api, h, baseStyle, header, num, arr, srcLabel, poll, lineChart, ENDPOINTS } from '../news/common.js';

export const SERIES = ['CPIAUCSL', 'GDP', 'UNRATE', 'FEDFUNDS'];
const META = {
  CPIAUCSL: { name: 'US CPI Inflation Index / YoY', color: '#ffb000' },
  GDP: { name: 'US Gross Domestic Product (GDP)', color: '#00d26a' },
  UNRATE: { name: 'US Civilian Unemployment Rate (%)', color: '#4da3ff' },
  FEDFUNDS: { name: 'Effective Federal Funds Rate (%)', color: '#e040fb' }
};

function pointsOf(s) {
  return arr(s && s.obs).map(o => ({ x: new Date(o.date).getTime(), y: parseFloat(o.value) })).filter(o => isFinite(o.x) && isFinite(o.y)).sort((a, b) => a.x - b.x);
}

function block(t, id, s, pts) {
  const last = pts[pts.length - 1], prev = pts[pts.length - 2];
  const d = last && prev ? last.y - prev.y : null;
  const m = META[id] || { name: (s && s.title) || id, color: t.amber };
  return h('div', { style: { border: '1px solid ' + t.border, background: '#050505', padding: '5px' } },
    h('div', { style: { display: 'flex', justifyContent: 'space-between', marginBottom: '3px', fontSize: '11px' } },
      h('span', null, h('b', { style: { color: t.label } }, id + ' '), h('span', { style: { color: '#ccc' } }, m.name)),
      h('span', { style: { fontWeight: 'bold', color: t.amber } },
        last ? num(last.y) : '--', ' ',
        h('span', { style: { color: d == null ? t.label : d >= 0 ? t.up : t.down } }, d == null ? '' : `(${d >= 0 ? '+' : ''}${num(d)})`)
      )
    ),
    lineChart(t, pts.slice(-120), { h: 105, color: m.color }),
    h('div', { style: { color: '#777', fontSize: '10px', marginTop: '2px', display: 'flex', justifyContent: 'space-between' } },
      h('span', null, `UNIT: ${(s && s.unit) || 'INDEX / %'} • ${pts.length} OBSERVATIONS`),
      h('span', { style: { color: t.label } }, last ? 'LAST: ' + new Date(last.x).toISOString().slice(0, 10) : '')
    )
  );
}

export function mount(container, ctx) {
  const t = baseStyle(container, ctx);
  const hd = header(t, '90) Actions  91) Countries  92) Series  |  ECST / MACRO - Economic Statistics Workbench');
  const grid = h('div', { style: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px' } });
  container.append(hd.el, grid);
  const load = async () => {
    grid.innerHTML = '';
    let res;
    try { res = await api(ctx, ENDPOINTS.macro + '?series=' + SERIES.join(',')); }
    catch (_) { hd.right.textContent = ''; grid.append(h('div', { style: { color: t.down, padding: '6px' } }, 'N/A (source down)')); return; }
    const all = (res.data && res.data.series) || {};
    for (const id of SERIES) {
      const pts = pointsOf(all[id]);
      grid.append(pts.length ? block(t, id, all[id], pts) : h('div', { style: { color: t.down, marginBottom: '6px' } }, id + ': N/A (source down)'));
    }
    hd.right.textContent = srcLabel(res.env) || 'FRED / WORLD BANK';
  };
  const stop = poll(load, 3600000);
  return { unmount() { stop(); container.innerHTML = ''; }, setSymbol() {} };
}
