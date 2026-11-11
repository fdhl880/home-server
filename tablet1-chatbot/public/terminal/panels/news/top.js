// TOP: Bloomberg Top Worldwide News (BN First Word + Global Regional Desks)
import { api, h, baseStyle, header, arr, srcLabel, down, poll, ENDPOINTS } from './common.js';
import { normalize, dedupe, renderList } from './news.js';

const TOP_DESKS = [
  ['all', '1) TOP WORLDWIDE'],
  ['bloomberg', '2) BN BLOOMBERG FIRST'],
  ['markets', '3) GLOBAL MARKETS'],
  ['macro', '4) CENTRAL BANKS & MACRO'],
  ['apac', '5) APAC / NIKKEI'],
  ['indonesia', '6) INDONESIA / IDX'],
  ['emea', '7) EMEA / LONDON'],
  ['tech', '8) TECH & AI'],
  ['commodities', '9) OIL & GOLD'],
  ['crypto', '10) DIGITAL ASSETS']
];

export function mount(container, ctx) {
  const t = baseStyle(container, ctx);
  const hd = header(t, '90) Actions  91) Sources  92) Languages  |  TOP - Bloomberg Top Worldwide News');
  let cat = 'all';
  const deskBar = h('div', { style: { display: 'flex', gap: '3px', flexWrap: 'wrap', marginBottom: '4px', paddingBottom: '3px', borderBottom: '1px solid ' + t.border } });
  const body = h('div');
  container.append(hd.el, deskBar, body);

  const renderDesks = () => {
    deskBar.innerHTML = '';
    for (const [code, lbl] of TOP_DESKS) {
      const on = cat === code;
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
        onclick: () => { cat = code; renderDesks(); load(); }
      }, lbl));
    }
  };

  const load = async () => {
    try {
      const { data, env } = await api(ctx, `${ENDPOINTS.news}?cat=${cat}&limit=80`);
      const items = dedupe(arr(data).map(normalize)).slice(0, 60);
      hd.right.textContent = `${items.length} HEADLINES • ${srcLabel(env) || 'BN WIRE LIVE'}`;
      renderList(t, items, body);
    } catch (_) { body.innerHTML = ''; hd.right.textContent = ''; down(body, t); }
  };
  renderDesks();
  const stop = poll(load, 45000);
  return { unmount() { stop(); container.innerHTML = ''; }, setSymbol() {} };
}
