// YCRV: US Treasury Sovereign Yield Curve (1M–30Y) + Spread Gauges & Curve Diagram
import { api, h, baseStyle, header, num, arr, srcLabel, down, poll, ENDPOINTS } from '../news/common.js';

const ORDER = ['1M', '3M', '6M', '1Y', '2Y', '3Y', '5Y', '7Y', '10Y', '20Y', '30Y'];

function renderCurveDiagram(t, rows, inverted) {
  const W = 680, H = 175, PL = 36, PR = 24, PT = 22, PB = 26;
  const ns = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(ns, 'svg');
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  svg.setAttribute('preserveAspectRatio', 'none');
  svg.style.cssText = `width:100%;height:${H}px;display:block;background:#000;border:1px solid ${t.border};margin-bottom:6px`;

  const ys = rows.map(r => r.y);
  const minY = Math.min(...ys) - 0.15;
  const maxY = Math.max(...ys) + 0.15;
  const plotW = W - PL - PR, plotH = H - PT - PB;
  const sx = i => PL + (rows.length <= 1 ? 0 : (i / (rows.length - 1)) * plotW);
  const sy = v => PT + plotH - ((v - minY) / (maxY - minY || 1)) * plotH;

  // Horizontal yield gridlines
  for (let i = 0; i <= 4; i++) {
    const val = maxY - ((maxY - minY) * i) / 4;
    const gy = sy(val);
    const gl = document.createElementNS(ns, 'line');
    gl.setAttribute('x1', PL); gl.setAttribute('x2', W - PR);
    gl.setAttribute('y1', gy.toFixed(1)); gl.setAttribute('y2', gy.toFixed(1));
    gl.setAttribute('stroke', '#191919');
    gl.setAttribute('stroke-dasharray', '3,3');
    svg.append(gl);

    const lbl = document.createElementNS(ns, 'text');
    lbl.setAttribute('x', PL - 5); lbl.setAttribute('y', (gy + 3).toFixed(1));
    lbl.setAttribute('text-anchor', 'end'); lbl.setAttribute('fill', '#777'); lbl.setAttribute('font-size', '9.5');
    lbl.textContent = val.toFixed(2) + '%';
    svg.append(lbl);
  }

  const col = inverted ? t.down : t.amber;
  const coords = rows.map((r, i) => `${sx(i).toFixed(1)},${sy(r.y).toFixed(1)}`);

  // Shaded area under curve
  const polyArea = document.createElementNS(ns, 'polygon');
  polyArea.setAttribute('points', `${sx(0).toFixed(1)},${(PT + plotH).toFixed(1)} ${coords.join(' ')} ${sx(rows.length - 1).toFixed(1)},${(PT + plotH).toFixed(1)}`);
  polyArea.setAttribute('fill', inverted ? 'rgba(255,59,48,0.16)' : 'rgba(255,176,0,0.16)');
  svg.append(polyArea);

  // Curve line
  const line = document.createElementNS(ns, 'polyline');
  line.setAttribute('points', coords.join(' '));
  line.setAttribute('fill', 'none');
  line.setAttribute('stroke', col);
  line.setAttribute('stroke-width', '2.2');
  svg.append(line);

  // Tenor nodes, vertical guides, tenor labels & yield values
  rows.forEach((r, i) => {
    const x = sx(i), y = sy(r.y);
    const vl = document.createElementNS(ns, 'line');
    vl.setAttribute('x1', x.toFixed(1)); vl.setAttribute('x2', x.toFixed(1));
    vl.setAttribute('y1', y.toFixed(1)); vl.setAttribute('y2', (PT + plotH).toFixed(1));
    vl.setAttribute('stroke', '#1c1c1c');
    svg.append(vl);

    const dot = document.createElementNS(ns, 'circle');
    dot.setAttribute('cx', x.toFixed(1)); dot.setAttribute('cy', y.toFixed(1));
    dot.setAttribute('r', '3.5'); dot.setAttribute('fill', '#000');
    dot.setAttribute('stroke', col); dot.setAttribute('stroke-width', '2');
    svg.append(dot);

    const vTxt = document.createElementNS(ns, 'text');
    vTxt.setAttribute('x', x.toFixed(1)); vTxt.setAttribute('y', (y - 6).toFixed(1));
    vTxt.setAttribute('text-anchor', 'middle'); vTxt.setAttribute('fill', '#fff'); vTxt.setAttribute('font-size', '9.5');
    vTxt.setAttribute('font-weight', 'bold');
    vTxt.textContent = r.y.toFixed(2);
    svg.append(vTxt);

    const tTxt = document.createElementNS(ns, 'text');
    tTxt.setAttribute('x', x.toFixed(1)); tTxt.setAttribute('y', (H - 8).toFixed(1));
    tTxt.setAttribute('text-anchor', 'middle'); tTxt.setAttribute('fill', t.label); tTxt.setAttribute('font-size', '10');
    tTxt.setAttribute('font-weight', 'bold');
    tTxt.textContent = r.m;
    svg.append(tTxt);
  });

  return svg;
}

export function mount(container, ctx) {
  const t = baseStyle(container, ctx);
  const hd = header(t, '90) Actions  91) Curves  92) Spreads  |  YCRV - US Treasury Sovereign Yield Curve (IYC)');
  const body = h('div');
  container.append(hd.el, body);
  const load = async () => {
    try {
      const { data, env } = await api(ctx, ENDPOINTS.macro + '?curve=1');
      const rows = arr(data.curve).map(r => ({ m: String(r.tenor).toUpperCase(), s: r.series || '', y: parseFloat(r.value), d: r.date }))
        .filter(r => isFinite(r.y)).sort((a, b) => ORDER.indexOf(a.m) - ORDER.indexOf(b.m));
      if (!rows.length) throw new Error('empty');
      body.innerHTML = '';

      const g = m => (rows.find(r => r.m === m) || {}).y;
      const s2s10s = (g('10Y') != null && g('2Y') != null) ? (g('10Y') - g('2Y')) * 100 : 0;
      const s3m10y = (g('10Y') != null && g('3M') != null) ? (g('10Y') - g('3M')) * 100 : 0;
      const s5s30s = (g('30Y') != null && g('5Y') != null) ? (g('30Y') - g('5Y')) * 100 : 0;

      body.append(
        h('div', { style: { display: 'flex', gap: '14px', padding: '3px 6px', background: '#070707', border: '1px solid ' + t.border, marginBottom: '4px', fontSize: '11px' } },
          h('span', { style: { color: s2s10s < 0 ? t.down : t.up, fontWeight: 'bold' } }, `2Y/10Y SPREAD: ${s2s10s >= 0 ? '+' : ''}${num(s2s10s, 1)} bps ${s2s10s < 0 ? '[INVERTED]' : '[NORMAL]'}`),
          h('span', { style: { color: s3m10y < 0 ? t.down : t.up, fontWeight: 'bold' } }, `3M/10Y SPREAD: ${s3m10y >= 0 ? '+' : ''}${num(s3m10y, 1)} bps`),
          h('span', { style: { color: t.amber } }, `5Y/30Y SLOPE: ${s5s30s >= 0 ? '+' : ''}${num(s5s30s, 1)} bps`)
        ),
        renderCurveDiagram(t, rows, s2s10s < 0)
      );

      const tbl = h('table', { class: 't', style: { width: '100%', borderCollapse: 'collapse' } },
        h('thead', null, h('tr', null, ['Tenor', 'Benchmark ID', 'Yield %', 'vs 2Y (bps)', 'vs 10Y (bps)', 'Obs Date'].map((c, i) => h('th', { style: { textAlign: i < 2 ? 'left' : 'right' } }, c)))),
        h('tbody', null, rows.map(r => {
          const vs2 = g('2Y') != null ? (r.y - g('2Y')) * 100 : 0;
          const vs10 = g('10Y') != null ? (r.y - g('10Y')) * 100 : 0;
          return h('tr', { class: 'row' },
            h('td', { style: { textAlign: 'left', color: t.label, fontWeight: 'bold' } }, 'UST ' + r.m),
            h('td', { style: { textAlign: 'left', color: '#888' } }, r.s),
            h('td', { style: { textAlign: 'right', color: t.amber, fontWeight: 'bold' } }, num(r.y, 3) + '%'),
            h('td', { style: { textAlign: 'right', color: vs2 >= 0 ? t.up : t.down } }, (vs2 >= 0 ? '+' : '') + num(vs2, 1)),
            h('td', { style: { textAlign: 'right', color: vs10 >= 0 ? t.up : t.down } }, (vs10 >= 0 ? '+' : '') + num(vs10, 1)),
            h('td', { style: { textAlign: 'right', color: t.label } }, r.d || '')
          );
        }))
      );
      body.append(tbl);
      hd.right.textContent = srcLabel(env) || 'FRED / US TREASURY';
    } catch (_) { body.innerHTML = ''; hd.right.textContent = ''; down(body, t); }
  };
  const stop = poll(load, 1800000);
  return { unmount() { stop(); container.innerHTML = ''; }, setSymbol() {} };
}
