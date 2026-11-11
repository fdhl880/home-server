// ECO: economic calendar with actual / forecast / previous and importance.
import { api, h, baseStyle, header, fmtTime, arr, srcLabel, down, poll, ENDPOINTS } from './common.js';

export function normalizeEvent(e) {
  const imp = e.impact ?? e.importance ?? e.priority;
  let lvl = 0;
  if (typeof imp === 'number') lvl = Math.max(1, Math.min(3, imp));
  else if (imp) { const s = String(imp).toLowerCase(); lvl = s.startsWith('h') ? 3 : s.startsWith('m') ? 2 : s.startsWith('l') ? 1 : 0; }
  const v = x => (x === undefined || x === null || x === '') ? null : x;
  return {
    ts: e.ts ?? e.time ?? e.date ?? e.datetime, country: e.country || e.currency || '',
    event: e.title || e.event || e.name || '', actual: v(e.actual), forecast: v(e.forecast ?? e.estimate), previous: v(e.previous ?? e.prev), lvl,
  };
}

export function mount(container, ctx) {
  const t = baseStyle(container, ctx);
  const hd = header(t, 'ECO  Economic Calendar');
  const sel = h('select', { style: { background: t.bg, color: t.amber, border: '1px solid ' + t.border, font: 'inherit' } },
    ...[['0', 'ALL'], ['2', 'MED+'], ['3', 'HIGH']].map(([v, l]) => h('option', { value: v }, l)));
  const body = h('div');
  container.append(hd.el, h('div', { style: { marginBottom: '3px', color: t.label } }, 'IMPORTANCE ', sel), body);
  let events = [];
  const view = () => {
    body.innerHTML = '';
    const min = +sel.value;
    const rows = events.filter(e => e.lvl >= min);
    if (!rows.length) { body.append(h('div', { style: { color: t.label } }, 'NO EVENTS')); return; }
    const tbl = h('table', { style: { width: '100%', borderCollapse: 'collapse' } },
      h('tr', { style: { color: t.label, textAlign: 'right' } }, ...['TIME', 'CTRY', 'EVENT', 'IMP', 'ACT', 'FCST', 'PREV'].map((c, i) => h('th', { style: { textAlign: i < 3 ? 'left' : 'right', fontWeight: 'normal' } }, c))));
    for (const e of rows) {
      const beat = e.actual != null && e.forecast != null && isFinite(parseFloat(e.actual)) && isFinite(parseFloat(e.forecast));
      const ac = !beat ? t.amber : parseFloat(e.actual) > parseFloat(e.forecast) ? t.up : parseFloat(e.actual) < parseFloat(e.forecast) ? t.down : t.amber;
      const td = (x, st) => h('td', { style: Object.assign({ borderBottom: '1px solid ' + t.border, padding: '1px 3px', textAlign: 'right' }, st) }, x == null ? '--' : x);
      tbl.append(h('tr', {},
        td(fmtTime(e.ts), { textAlign: 'left', color: t.label }), td(e.country, { textAlign: 'left' }), td(e.event, { textAlign: 'left' }),
        td('*'.repeat(e.lvl) || '-', { color: e.lvl === 3 ? t.down : t.amber }), td(e.actual, { color: ac }), td(e.forecast), td(e.previous, { color: t.label })));
    }
    body.append(tbl);
  };
  sel.addEventListener('change', view);
  const load = async () => {
    try {
      const { data, env } = await api(ctx, ENDPOINTS.calendar + '?week=this');
      events = arr(data).map(normalizeEvent).sort((a, b) => new Date(a.ts) - new Date(b.ts));
      hd.right.textContent = srcLabel(env) || 'LIVE';
      view();
    } catch (_) { body.innerHTML = ''; hd.right.textContent = ''; down(body, t); }
  };
  const stop = poll(load, 300000);
  return { unmount() { stop(); container.innerHTML = ''; }, setSymbol() {} };
}
