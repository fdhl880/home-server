// FNG: Fear & Greed index.
import { api, h, baseStyle, header, num, arr, srcLabel, down, poll, lineChart, fmtTime, ENDPOINTS } from './common.js';

export function classify(v) {
  return v < 25 ? 'EXTREME FEAR' : v < 45 ? 'FEAR' : v <= 55 ? 'NEUTRAL' : v < 75 ? 'GREED' : 'EXTREME GREED';
}

export function mount(container, ctx) {
  const t = baseStyle(container, ctx);
  const hd = header(t, 'FNG  Fear & Greed');
  const body = h('div');
  container.append(hd.el, body);
  const load = async () => {
    try {
      const { data: p, env } = await api(ctx, ENDPOINTS.fng);
      const hist = arr(p.history);
      const cur = p.value;
      const v = parseFloat(cur);
      if (!isFinite(v)) throw new Error('no value');
      body.innerHTML = '';
      const col = v < 45 ? t.down : v > 55 ? t.up : t.amber;
      body.append(
        h('div', { style: { fontSize: '28px', color: col } }, num(v, 0)),
        h('div', { style: { color: col, marginBottom: '4px' } }, (p.classification || p.label || classify(v)).toUpperCase()),
        h('div', { style: { color: t.label } }, p.ts ? 'AS OF ' + fmtTime(p.ts) : ''));
      const pts = hist.map((r, i) => ({ x: r.ts ?? r.timestamp ?? i, y: parseFloat(r.value) })).filter(r => isFinite(r.y)).sort((a, b) => a.x - b.x);
      if (pts.length > 1) body.append(h('div', { style: { color: t.label, marginTop: '4px' } }, 'HISTORY'), lineChart(t, pts, { dp: 0 }));
      hd.right.textContent = srcLabel(env) || 'DAILY';
    } catch (_) { body.innerHTML = ''; hd.right.textContent = ''; down(body, t); }
  };
  const stop = poll(load, 600000);
  return { unmount() { stop(); container.innerHTML = ''; }, setSymbol() {} };
}
