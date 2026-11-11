// RATES: world rates & commodities summary from /api/terminal/quote (Yahoo-style symbols). Values only from API.
import { api, h, baseStyle, header, num, arr, srcLabel, poll, ENDPOINTS } from '../news/common.js';

// Row labels only (no values). Symbols per API.md conventions.
export const GROUPS = {
  'US YIELDS': [['^TNX', 'US 10Y'], ['^FVX', 'US 5Y'], ['^TYX', 'US 30Y']],
  'COMMODITIES': [['GC=F', 'GOLD'], ['SI=F', 'SILVER'], ['CL=F', 'WTI CRUDE'], ['BZ=F', 'BRENT'], ['NG=F', 'NAT GAS'], ['HG=F', 'COPPER']],
  'FOREX': [['EURUSD=X', 'EUR/USD'], ['GBPUSD=X', 'GBP/USD'], ['USDJPY=X', 'USD/JPY'], ['USDIDR=X', 'USD/IDR'], ['DX-Y.NYB', 'USD INDEX']],
};
const ALL = Object.values(GROUPS).flat();

export function mount(container, ctx) {
  const t = baseStyle(container, ctx);
  const hd = header(t, 'RATES  World Rates & Commodities');
  const body = h('div');
  container.append(hd.el, body);
  const load = async () => {
    let res;
    try { res = await api(ctx, ENDPOINTS.quote + '?symbols=' + encodeURIComponent(ALL.map(a => a[0]).join(','))); }
    catch (_) { body.innerHTML = ''; hd.right.textContent = ''; body.append(h('div', { style: { color: t.down, padding: '6px' } }, 'N/A (source down)')); return; }
    const by = {}; for (const q of arr(res.data)) by[q.symbol] = q;
    body.innerHTML = '';
    for (const g in GROUPS) {
      body.append(h('div', { style: { color: t.label, borderBottom: '1px solid ' + t.border, marginTop: '4px' } }, g));
      const tbl = h('table', { style: { width: '100%', borderCollapse: 'collapse' } });
      for (const [sym, name] of GROUPS[g]) {
        const q = by[sym], ok = q && q.price != null;
        const ch = ok ? q.chgPct : null;
        tbl.append(h('tr', {},
          h('td', {}, name),
          h('td', { style: { textAlign: 'right', color: ok ? t.amber : t.down } }, ok ? num(q.price, Math.abs(q.price) < 20 ? 4 : 2) : 'N/A (source down)'),
          h('td', { style: { textAlign: 'right', color: ch == null ? t.label : ch >= 0 ? t.up : t.down } }, ch == null ? '--' : (ch >= 0 ? '+' : '') + num(ch) + '%'),
          h('td', { style: { textAlign: 'right', color: t.label } }, ok ? (q.mode || '') : '')));
      }
      body.append(tbl);
    }
    hd.right.textContent = srcLabel(res.env);
  };
  const stop = poll(load, 30000);
  return { unmount() { stop(); container.innerHTML = ''; }, setSymbol() {} };
}
