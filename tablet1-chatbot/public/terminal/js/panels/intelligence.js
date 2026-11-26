import { h, fmtPx, fmtPct, fmtVol, fmtTime, dirCls, LS } from '../util.js';
import { get, apiFetch } from '../api.js';

const SNAP_KEY = 'bbg_chart_snapshots_v1';

function esc(v) {
  return String(v == null ? '' : v)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function fmtIdr(v) {
  const n = Math.round(Number(v) || 0);
  return (n < 0 ? '-Rp ' : 'Rp ') + Math.abs(n).toLocaleString('id-ID');
}

function fmtUsdShort(v) {
  const n = Number(v) || 0;
  const sign = n > 0 ? '+' : n < 0 ? '-' : '';
  const a = Math.abs(n);
  if (a >= 1e9) return `${sign}$${(a / 1e9).toFixed(2)}B`;
  if (a >= 1e6) return `${sign}$${(a / 1e6).toFixed(2)}M`;
  if (a >= 1e3) return `${sign}$${(a / 1e3).toFixed(1)}K`;
  return `${sign}$${a.toFixed(0)}`;
}

function makeSvgBox(markup) {
  const d = h('div', { style: 'width:100%;overflow:hidden' });
  d.innerHTML = markup;
  return d;
}

function downloadBlob(filename, content, mime = 'text/plain;charset=utf-8') {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => {
    try { a.remove(); URL.revokeObjectURL(url); } catch {}
  }, 200);
}

function saveSnapshotToGallery(snap) {
  try {
    const arr = LS.get(SNAP_KEY, []);
    const list = Array.isArray(arr) ? arr : [];
    list.unshift(snap);
    LS.set(SNAP_KEY, list.slice(0, 12));
  } catch {}
}

// =====================================================================
// INSTITUTIONAL SVG VISUALIZATIONS
// =====================================================================
function buildRadarSvg(axes = []) {
  const list = Array.isArray(axes) && axes.length ? axes : [
    { axis: '532-QUANT', score: 50, raw: '50' },
    { axis: 'TREND/ADX', score: 50, raw: '-' },
    { axis: 'ORDERFLOW', score: 50, raw: '-' },
    { axis: 'CLEAN FLOW', score: 50, raw: '-' },
    { axis: 'AI SETUP', score: 50, raw: '-' },
    { axis: 'FPT PROB', score: 50, raw: '-' },
    { axis: 'RISK AUDIT', score: 50, raw: '-' },
    { axis: 'MACRO/NEWS', score: 50, raw: '-' }
  ];
  const W = 360, H = 266, cx = 180, cy = 136, R = 88;
  const n = list.length;
  const pt = (idx, pct) => {
    const a = -Math.PI / 2 + (idx * 2 * Math.PI) / n;
    const r = (Math.max(0, Math.min(100, Number(pct) || 0)) / 100) * R;
    return [cx + r * Math.cos(a), cy + r * Math.sin(a)];
  };

  let rings = '';
  for (const lv of [25, 50, 75, 100]) {
    const pts = list.map((_, i) => pt(i, lv).map(v => v.toFixed(1)).join(',')).join(' ');
    rings += `<polygon points="${pts}" fill="none" stroke="${lv === 50 ? '#3a4252' : '#1f2530'}" stroke-width="${lv === 100 ? 1.2 : 0.8}" stroke-dasharray="${lv === 50 ? '3,2' : ''}"/>`;
    rings += `<text x="${cx + 3}" y="${(cy - (lv / 100) * R + 3).toFixed(1)}" fill="#5f6b7d" font-size="8" font-family="monospace">${lv}</text>`;
  }

  let spokes = '';
  let labels = '';
  const dataPts = [];
  list.forEach((item, i) => {
    const [ox, oy] = pt(i, 100);
    const [dx, dy] = pt(i, item.score);
    const [lx, ly] = pt(i, 122);
    dataPts.push([dx, dy, item]);
    spokes += `<line x1="${cx}" y1="${cy}" x2="${ox.toFixed(1)}" y2="${oy.toFixed(1)}" stroke="#222834" stroke-width="0.9"/>`;
    const anchor = lx < cx - 12 ? 'end' : lx > cx + 12 ? 'start' : 'middle';
    const sc = Math.round(Number(item.score) || 0);
    const col = sc >= 70 ? '#00d26a' : sc >= 45 ? '#ffb000' : '#ff5a52';
    labels += `<text x="${lx.toFixed(1)}" y="${(ly - 1).toFixed(1)}" text-anchor="${anchor}" fill="#cfd8e3" font-size="9" font-weight="700" font-family="monospace">${esc(item.axis)}</text>`;
    labels += `<text x="${lx.toFixed(1)}" y="${(ly + 9).toFixed(1)}" text-anchor="${anchor}" fill="${col}" font-size="8.5" font-weight="700" font-family="monospace">${sc}%</text>`;
  });

  const polyStr = dataPts.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
  const dots = dataPts.map(([x, y, item]) => {
    const sc = Number(item.score) || 0;
    const col = sc >= 70 ? '#00d26a' : sc >= 45 ? '#ffb000' : '#ff5a52';
    return `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="3.5" fill="${col}" stroke="#000" stroke-width="1"><title>${esc(item.axis)}: ${sc.toFixed(1)}% (${esc(item.raw)})</title></circle>`;
  }).join('');

  return `<svg viewBox="0 0 ${W} ${H}" style="width:100%;height:auto;max-height:260px;display:block;background:#040608">
    ${rings}${spokes}
    <polygon points="${polyStr}" fill="rgba(0,210,106,0.20)" stroke="#00d26a" stroke-width="1.8"/>
    ${dots}${labels}
  </svg>`;
}

function buildWaterfallSvg(items = [], finalMath = 50) {
  const list = Array.isArray(items) && items.length ? items : [{ label: 'Base Prior', pts: 54, note: '' }];
  const W = 420, rowH = 27, padTop = 18, padBot = 30;
  const H = padTop + list.length * rowH + padBot;
  const maxAbs = Math.max(25, ...list.slice(1).map(x => Math.abs(Number(x.pts) || 0)), 60);
  const barLeft = 148, barW = 195;

  let rows = '';
  list.forEach((it, idx) => {
    const y = padTop + idx * rowH;
    const pts = Number(it.pts) || 0;
    const isBase = idx === 0;
    const pct = Math.min(1, Math.abs(pts) / (isBase ? 100 : Math.max(25, maxAbs * 0.55)));
    const w = Math.max(2, pct * barW);
    const col = isBase ? '#4da3ff' : pts > 0 ? '#00d26a' : pts < 0 ? '#ff5a52' : '#556070';
    const signTxt = isBase ? pts.toFixed(1) : `${pts >= 0 ? '+' : ''}${pts.toFixed(2)}`;
    rows += `
      <text x="6" y="${y + 13}" fill="#cfd8e3" font-size="10" font-family="monospace">${esc(it.label)}</text>
      <rect x="${barLeft}" y="${y + 3}" width="${barW}" height="14" fill="#11151d" stroke="#1e2430" stroke-width="0.6"/>
      <rect x="${barLeft}" y="${y + 3}" width="${w.toFixed(1)}" height="14" fill="${col}" opacity="0.88"><title>${esc(it.label)}: ${signTxt} (${esc(it.note || '')})</title></rect>
      <text x="${barLeft + barW + 6}" y="${y + 14}" fill="${col}" font-size="10" font-weight="700" font-family="monospace">${signTxt}</text>
    `;
  });

  const fy = padTop + list.length * rowH + 6;
  const fCol = finalMath >= 68 ? '#00d26a' : finalMath >= 58 ? '#ffb000' : '#ff5a52';
  rows += `
    <line x1="6" y1="${fy - 4}" x2="${W - 6}" y2="${fy - 4}" stroke="#2d3544" stroke-dasharray="3,2"/>
    <text x="6" y="${fy + 13}" fill="#ffb000" font-size="11" font-weight="700" font-family="monospace">FINAL DETERMINISTIC P_MATH</text>
    <text x="${W - 10}" y="${fy + 13}" text-anchor="end" fill="${fCol}" font-size="13" font-weight="700" font-family="monospace">${Number(finalMath || 0).toFixed(2)}%</text>
  `;

  return `<svg viewBox="0 0 ${W} ${H}" style="width:100%;height:auto;display:block;background:#040608">${rows}</svg>`;
}

function buildFptConeSvg(cone, entryPx, slPx, tp1Px, tp2Px, dir = 'LONG') {
  const W = 560, H = 190, padL = 62, padR = 68, padT = 18, padB = 24;
  const e = Number(entryPx) || 0;
  const sl = Number(slPx) || 0;
  const tp1 = Number(tp1Px) || 0;
  const tp2 = Number(tp2Px) || 0;

  const hasCone = Array.isArray(cone) && cone.length >= 2;
  const prices = [e, sl, tp1, tp2].filter(v => v > 0);
  if (hasCone) {
    cone.forEach(c => {
      for (const k of ['expected_price', 'upper_1sigma', 'lower_1sigma', 'p_mid', 'p_high', 'p_low', 'price']) {
        const v = Number(c[k]);
        if (v > 0) prices.push(v);
      }
    });
  }
  if (!prices.length) {
    return `<svg viewBox="0 0 ${W} ${H}" style="width:100%;height:auto;display:block;background:#040608">
      <text x="${W / 2}" y="${H / 2}" text-anchor="middle" fill="#6c788a" font-size="11" font-family="monospace">No active Entry/SL/TP projection for this symbol. Select a scanned asset or live position.</text>
    </svg>`;
  }

  let pMin = Math.min(...prices);
  let pMax = Math.max(...prices);
  const span = Math.max(1e-8, pMax - pMin);
  pMin -= span * 0.12;
  pMax += span * 0.12;
  const yOf = p => padT + ((pMax - p) / Math.max(1e-8, pMax - pMin)) * (H - padT - padB);
  const plotW = W - padL - padR;

  let lines = '';
  const drawLevel = (px, label, col, dash = '') => {
    if (!(px > 0)) return;
    const y = yOf(px);
    lines += `<line x1="${padL}" y1="${y.toFixed(1)}" x2="${W - padR}" y2="${y.toFixed(1)}" stroke="${col}" stroke-width="1.2" ${dash ? `stroke-dasharray="${dash}"` : ''}/>`;
    lines += `<text x="${W - padR + 4}" y="${(y + 3).toFixed(1)}" fill="${col}" font-size="9" font-weight="700" font-family="monospace">${esc(label)}</text>`;
    lines += `<text x="${padL - 5}" y="${(y + 3).toFixed(1)}" text-anchor="end" fill="${col}" font-size="9" font-family="monospace">${esc(fmtPx(px))}</text>`;
  };

  let coneMarkup = '';
  if (hasCone) {
    const upPts = [], loPts = [], midPts = [];
    cone.forEach((pt, i) => {
      const x = padL + (i / (cone.length - 1)) * plotW;
      const mid = Number(pt.expected_price || pt.p_mid || pt.price || e);
      const hi = Number(pt.upper_1sigma || pt.p_high || mid);
      const lo = Number(pt.lower_1sigma || pt.p_low || mid);
      upPts.push(`${x.toFixed(1)},${yOf(hi).toFixed(1)}`);
      loPts.unshift(`${x.toFixed(1)},${yOf(lo).toFixed(1)}`);
      midPts.push(`${x.toFixed(1)},${yOf(mid).toFixed(1)}`);
    });
    coneMarkup = `
      <polygon points="${upPts.concat(loPts).join(' ')}" fill="rgba(77,163,255,0.16)" stroke="rgba(77,163,255,0.45)" stroke-width="0.9"/>
      <polyline points="${midPts.join(' ')}" fill="none" stroke="#00e5ff" stroke-width="2"/>
    `;
  } else if (e > 0) {
    const sign = String(dir).toUpperCase() === 'SHORT' ? -1 : 1;
    const risk = sl > 0 ? Math.abs(e - sl) : e * 0.012;
    const be = e + sign * risk * 0.65;
    const t1 = tp1 > 0 ? tp1 : e + sign * risk * 0.9;
    const t2 = tp2 > 0 ? tp2 : e + sign * risk * 2.0;
    const pts = [
      [padL, e, 'T0 ENTRY'],
      [padL + plotW * 0.32, be, 'BE +0.65R'],
      [padL + plotW * 0.60, t1, 'TP1 50%'],
      [padL + plotW, t2, 'TP2 RUNNER']
    ];
    const upper = pts.map(([x, p], i) => `${x.toFixed(1)},${yOf(p + risk * 0.28 * (i + 0.3)).toFixed(1)}`);
    const lower = [...pts].reverse().map(([x, p], i) => `${x.toFixed(1)},${yOf(p - risk * 0.28 * (pts.length - i)).toFixed(1)}`);
    const mid = pts.map(([x, p]) => `${x.toFixed(1)},${yOf(p).toFixed(1)}`).join(' ');
    coneMarkup = `
      <polygon points="${upper.concat(lower).join(' ')}" fill="rgba(0,210,106,0.10)" stroke="rgba(0,210,106,0.35)" stroke-width="0.8"/>
      <polyline points="${mid}" fill="none" stroke="#00e5ff" stroke-width="2"/>
      ${pts.map(([x, p, lbl]) => `<circle cx="${x.toFixed(1)}" cy="${yOf(p).toFixed(1)}" r="3.5" fill="#ffb000" stroke="#000"/><text x="${x.toFixed(1)}" y="${H - 7}" text-anchor="middle" fill="#8b97a8" font-size="8.5" font-family="monospace">${lbl}</text>`).join('')}
    `;
  }

  drawLevel(sl, 'STOP LOSS', '#ff5a52', '4,3');
  drawLevel(e, 'ENTRY', '#00e5ff', '2,2');
  drawLevel(tp1, 'TP1 (50%)', '#00d26a', '');
  drawLevel(tp2, 'TP2 RUN', '#ffb000', '');

  return `<svg viewBox="0 0 ${W} ${H}" style="width:100%;height:auto;display:block;background:#040608">
    <rect x="${padL}" y="${padT}" width="${plotW}" height="${H - padT - padB}" fill="#06090e" stroke="#1b212c"/>
    ${coneMarkup}${lines}
  </svg>`;
}

function buildGaugeSvg(score = 50, subtitle = 'INDEX', overrideCol = null) {
  const s = Math.max(0, Math.min(100, Number(score) || 0));
  const col = overrideCol || (s >= 75 ? '#00d26a' : s >= 50 ? '#ffb000' : '#ff5a52');
  const cx = 110, cy = 102, r = 74;
  const rad = Math.PI - (s / 100) * Math.PI;
  const nx = cx + (r - 8) * Math.cos(rad);
  const ny = cy - (r - 8) * Math.sin(rad);
  const arcLen = Math.PI * r;
  const fillLen = (s / 100) * arcLen;

  return `<svg viewBox="0 0 220 124" style="width:100%;max-width:230px;height:auto;display:block;margin:0 auto">
    <path d="M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}" fill="none" stroke="#1d232e" stroke-width="14" stroke-linecap="round"/>
    <path d="M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}" fill="none" stroke="${col}" stroke-width="14" stroke-linecap="round" stroke-dasharray="${fillLen.toFixed(1)} ${arcLen.toFixed(1)}"/>
    <line x1="${cx}" y1="${cy}" x2="${nx.toFixed(1)}" y2="${ny.toFixed(1)}" stroke="#fff" stroke-width="2.2" stroke-linecap="round"/>
    <circle cx="${cx}" cy="${cy}" r="5" fill="${col}" stroke="#000" stroke-width="1.5"/>
    <text x="${cx}" y="${cy - 18}" text-anchor="middle" fill="${col}" font-size="22" font-weight="700" font-family="monospace">${Math.round(s)}</text>
    <text x="${cx}" y="${cy + 16}" text-anchor="middle" fill="#9aa7b8" font-size="9" font-weight="700" font-family="monospace">${esc(subtitle)}</text>
  </svg>`;
}

function buildCashflow14dSvg(days = [], dailyLimit = 20000) {
  const list = Array.isArray(days) ? days : [];
  const W = 580, H = 190, padL = 62, padR = 14, padT = 18, padB = 28;
  const maxVal = Math.max(dailyLimit * 1.4, ...list.map(d => Math.max(d.income || 0, d.expense || 0, d.savings || 0)), 10000);
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;
  const yOf = v => padT + plotH - (Math.max(0, v) / maxVal) * plotH;
  const step = plotW / Math.max(1, list.length);

  let bars = '';
  list.forEach((d, i) => {
    const gx = padL + i * step;
    const bw = Math.max(4, step * 0.32);
    const incH = Math.max(0, (d.income / maxVal) * plotH);
    const expH = Math.max(0, (d.expense / maxVal) * plotH);
    const over = d.expense > dailyLimit;
    if (d.income > 0) {
      bars += `<rect x="${(gx + 3).toFixed(1)}" y="${(padT + plotH - incH).toFixed(1)}" width="${bw.toFixed(1)}" height="${incH.toFixed(1)}" fill="#00d26a"><title>${d.date} Income: ${fmtIdr(d.income)}</title></rect>`;
    }
    if (d.expense > 0) {
      bars += `<rect x="${(gx + 4 + bw).toFixed(1)}" y="${(padT + plotH - expH).toFixed(1)}" width="${bw.toFixed(1)}" height="${expH.toFixed(1)}" fill="${over ? '#ff3b30' : '#ff8c42'}"><title>${d.date} Expense: ${fmtIdr(d.expense)}${over ? ' (EXCEEDS DAILY CEILING)' : ''}</title></rect>`;
    }
    if (i % 2 === 0 || i === list.length - 1) {
      bars += `<text x="${(gx + step / 2).toFixed(1)}" y="${H - 9}" text-anchor="middle" fill="#818fa3" font-size="8.5" font-family="monospace">${esc(String(d.date || '').slice(5))}</text>`;
    }
  });

  const limY = yOf(dailyLimit);
  return `<svg viewBox="0 0 ${W} ${H}" style="width:100%;height:auto;display:block;background:#040608">
    <rect x="${padL}" y="${padT}" width="${plotW}" height="${plotH}" fill="#06090e" stroke="#1c222d"/>
    <text x="${padL - 5}" y="${padT + 8}" text-anchor="end" fill="#7c8799" font-size="8.5" font-family="monospace">${esc((maxVal / 1000).toFixed(0))}k</text>
    <text x="${padL - 5}" y="${padT + plotH}" text-anchor="end" fill="#7c8799" font-size="8.5" font-family="monospace">0</text>
    ${bars}
    <line x1="${padL}" y1="${limY.toFixed(1)}" x2="${W - padR}" y2="${limY.toFixed(1)}" stroke="#ffb000" stroke-width="1.3" stroke-dasharray="4,3"/>
    <text x="${padL + 6}" y="${Math.max(padT + 10, limY - 4).toFixed(1)}" fill="#ffb000" font-size="9" font-weight="700" font-family="monospace">DAILY OPERATING CEILING: ${esc(fmtIdr(dailyLimit))}</text>
  </svg>`;
}

function buildCompoundingSvg(projections = []) {
  const list = Array.isArray(projections) && projections.length ? projections : [];
  if (!list.length) return '';
  const W = 540, H = 160, padL = 66, padR = 16, padT = 18, padB = 26;
  const maxVal = Math.max(1000000, ...list.map(p => p.benchmarkIdr || 0));
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;
  const step = plotW / list.length;

  let bars = '';
  list.forEach((p, i) => {
    const gx = padL + i * step + step * 0.14;
    const bw = Math.max(14, step * 0.22);
    const hPrin = (p.principalIdr / maxVal) * plotH;
    const hCons = (p.conservativeIdr / maxVal) * plotH;
    const hBmk = (p.benchmarkIdr / maxVal) * plotH;
    bars += `
      <rect x="${gx.toFixed(1)}" y="${(padT + plotH - hPrin).toFixed(1)}" width="${bw.toFixed(1)}" height="${hPrin.toFixed(1)}" fill="#4da3ff"><title>${p.years}Y Principal: ${fmtIdr(p.principalIdr)}</title></rect>
      <rect x="${(gx + bw + 3).toFixed(1)}" y="${(padT + plotH - hCons).toFixed(1)}" width="${bw.toFixed(1)}" height="${hCons.toFixed(1)}" fill="#ffb000"><title>${p.years}Y Conservative (8%): ${fmtIdr(p.conservativeIdr)}</title></rect>
      <rect x="${(gx + (bw + 3) * 2).toFixed(1)}" y="${(padT + plotH - hBmk).toFixed(1)}" width="${bw.toFixed(1)}" height="${hBmk.toFixed(1)}" fill="#00d26a"><title>${p.years}Y Benchmark (12%): ${fmtIdr(p.benchmarkIdr)}</title></rect>
      <text x="${(gx + bw * 1.5).toFixed(1)}" y="${H - 8}" text-anchor="middle" fill="#cfd8e3" font-size="9.5" font-weight="700" font-family="monospace">${p.years}Y</text>
      <text x="${(gx + (bw + 3) * 2 + bw / 2).toFixed(1)}" y="${Math.max(padT + 9, padT + plotH - hBmk - 4).toFixed(1)}" text-anchor="middle" fill="#00d26a" font-size="8.5" font-weight="700" font-family="monospace">${(p.benchmarkIdr / 1e6).toFixed(1)}M</text>
    `;
  });

  return `<svg viewBox="0 0 ${W} ${H}" style="width:100%;height:auto;display:block;background:#040608">
    <rect x="${padL}" y="${padT}" width="${plotW}" height="${plotH}" fill="#06090e" stroke="#1c222d"/>
    <text x="${padL - 5}" y="${padT + 9}" text-anchor="end" fill="#7c8799" font-size="8.5" font-family="monospace">${(maxVal / 1e6).toFixed(1)}M</text>
    <text x="${padL - 5}" y="${padT + plotH}" text-anchor="end" fill="#7c8799" font-size="8.5" font-family="monospace">0</text>
    ${bars}
  </svg>`;
}

function buildEtfFlowSvg(etfs = []) {
  const list = Array.isArray(etfs) ? etfs : [];
  const W = 540, rowH = 24, padT = 16, padB = 12;
  const H = padT + Math.max(1, list.length) * rowH + padB;
  const maxAbs = Math.max(1e6, ...list.map(e => Math.abs(Number(e.signedFlowEstUsd) || 0)));
  const zeroX = 290, halfW = 165;

  let rows = `<line x1="${zeroX}" y1="${padT - 6}" x2="${zeroX}" y2="${H - 6}" stroke="#394354" stroke-width="1"/>`;
  list.forEach((e, idx) => {
    const y = padT + idx * rowH;
    const val = Number(e.signedFlowEstUsd) || 0;
    const w = Math.min(halfW, (Math.abs(val) / maxAbs) * halfW);
    const x = val >= 0 ? zeroX : zeroX - w;
    const col = val >= 0 ? '#00d26a' : '#ff5a52';
    rows += `
      <text x="6" y="${y + 14}" fill="#ffb000" font-size="10" font-weight="700" font-family="monospace">${esc(e.symbol)}</text>
      <text x="58" y="${y + 14}" fill="#8b97a8" font-size="9" font-family="monospace">${esc(String(e.group || '').slice(0, 14))}</text>
      <rect x="${x.toFixed(1)}" y="${y + 4}" width="${Math.max(2, w).toFixed(1)}" height="13" fill="${col}" opacity="0.88"/>
      <text x="${W - 6}" y="${y + 14}" text-anchor="end" fill="${col}" font-size="9.5" font-weight="700" font-family="monospace">${esc(fmtUsdShort(val))}</text>
    `;
  });
  return `<svg viewBox="0 0 ${W} ${H}" style="width:100%;height:auto;display:block;background:#040608">${rows}</svg>`;
}

// =====================================================================
// 1. FACT / XRAY / PILLAR — QUANTITATIVE EXECUTION X-RAY
// =====================================================================
export function mountFACT(body, ctx) {
  body.classList.add('fill');
  const tb = h('div', { class: 'tb' });
  const sc = h('div', { class: 'pb' });
  body.append(tb, sc);

  let selectedSym = ctx.symbol || 'BTCUSDT';
  let tab = 'OVERVIEW';
  let pillarGroup = 'ALL';
  let factorFilter = '';
  let payload = null;
  let unmounted = false;

  async function load(sym = selectedSym) {
    selectedSym = String(sym || 'BTCUSDT').trim().toUpperCase();
    const env = await get('factors', { symbol: selectedSym }, 2500);
    if (unmounted) return;
    ctx.status(env);
    if (!env.ok || !env.data) {
      sc.textContent = '';
      sc.append(h('div', { class: 'na', text: 'Execution X-Ray feed unavailable: ' + (env.error || 'source down') }));
      return;
    }
    payload = env.data;
    renderToolbar();
    renderBody();
  }

  function renderToolbar() {
    tb.textContent = '';
    const inp = h('input', { value: selectedSym, style: 'width:92px;text-transform:uppercase;font-weight:700', placeholder: 'BTCUSDT' });
    inp.addEventListener('keydown', e => { if (e.key === 'Enter') load(inp.value); });
    tb.append(
      h('span', { class: 'lbl', text: 'EXECUTION X-RAY:' }),
      inp,
      h('button', { class: 'on', text: 'INSPECT <GO>', onclick: () => load(inp.value) }),
      ...['OVERVIEW', 'FUNNEL L1-L6', '24 PILLARS', '532 FACTORS'].map(t => h('button', {
        class: tab === t ? 'on' : '',
        text: t,
        onclick: () => { tab = t; renderToolbar(); renderBody(); }
      })),
      h('button', { style: 'color:#00e5ff;border-color:#00e5ff66', text: 'TRANSCRIPTS', onclick: () => ctx.run(`${selectedSym} TRAN`) }),
      h('button', { style: 'color:#00d26a;border-color:#00d26a66', text: 'CHART GP', onclick: () => ctx.run(`${selectedSym} GP`) }),
      h('button', { text: 'REFRESH', onclick: () => load(selectedSym) })
    );
  }

  function renderBody() {
    sc.textContent = '';
    if (!payload) return;
    const d = payload;
    const mp = d.mathProof || {};
    const l1 = d.layer1 || {};
    const l2 = d.layer2 || {};
    const l3 = d.layer3 || {};
    const l4 = d.layer4 || {};
    const l5 = d.layer5 || {};
    const pos = d.activePosition;
    const gear = d.gear && d.gear.active_profile ? `TIER ${d.gear.current_gear} (${d.gear.active_profile.leverage}x)` : 'TIER 1 (20x)';
    const vaultUsd = Number((d.vault && d.vault.locked_profit_vault_usdt) || 0);

    const strip = h('div', { style: 'display:flex;gap:4px;flex-wrap:wrap;margin-bottom:8px;align-items:center' },
      h('span', { class: 'lbl', style: 'font-size:10px', text: 'SCANNED INSTRUMENTS:' })
    );
    if (pos) {
      const psym = String(pos.binance_pair || pos.symbol || '').toUpperCase();
      strip.append(h('button', {
        style: 'background:#072414;color:#00ff88;border-color:#00d26a;font-weight:700;font-size:10px',
        text: `LIVE POSITION: ${psym} ${pos.direction || ''}`,
        onclick: () => load(psym)
      }));
    }
    (d.scannedCoins || []).slice(0, 14).forEach(c => {
      const active = String(c.symbol).toUpperCase().replace('-USD', 'USDT') === selectedSym.replace('-USD', 'USDT').replace(/\.P$/, '');
      const stCol = String(c.status).startsWith('APPROVED') ? '#00d26a' : '#ffb000';
      strip.append(h('button', {
        class: active ? 'on' : '',
        style: `font-size:10px;${active ? '' : `border-color:${stCol}55`}`,
        title: `${c.symbol} | ${c.status} | P_Math ${c.p_math.toFixed(1)}% | ${c.reason}`,
        text: `${c.symbol.replace('-USD', '')} ${c.p_math ? c.p_math.toFixed(0) + '%' : ''}`,
        onclick: () => load(c.symbol.replace('-USD', 'USDT'))
      }));
    });
    sc.append(strip);

    const pMath = Number(mp.p_math_pct ?? l5.math_score_pct ?? 0);
    const pAi = Number(mp.p_ai_pct ?? l2.probability_pct ?? 0);
    const sHyb = Number(mp.s_hybrid_pct ?? l5.confidence_score ?? 0);
    const fpt = Number((l3.tp_time_prediction && l3.tp_time_prediction.p_hit_tp1_before_sl_pct) || 0);
    const dir = String(l5.direction || l2.direction || (pos && pos.direction) || mp.preferred_direction || 'NONE').toUpperCase();
    const statusTxt = String(d.scanStatus || l5.status || 'IDLE').toUpperCase();

    sc.append(h('div', { class: 'xgrid4', style: 'margin-bottom:8px' },
      h('div', { class: 'xstat' },
        h('div', { class: 'xl', text: `DECISION STATUS (${d.symbol})` }),
        h('div', { class: 'xv', style: `color:${statusTxt.includes('APPROV') || pos ? 'var(--up)' : 'var(--amber)'};font-size:13px`, text: `${statusTxt} | ${dir}` }),
        h('div', { class: 'xs', text: `Regime: ${mp.statistical_regime || 'NORMAL'} | ${d.scanTimestamp ? String(d.scanTimestamp).slice(11, 19) : '-'}` })
      ),
      h('div', { class: 'xstat' },
        h('div', { class: 'xl', text: 'P_MATH / AI / HYBRID' }),
        h('div', { class: 'xv', style: 'color:var(--up);font-size:13px', text: `${pMath.toFixed(1)}% / ${pAi.toFixed(1)}% / ${sHyb.toFixed(1)}%` }),
        h('div', { class: 'xs', text: `Q532=${Number(mp.composite_532_factors || 50).toFixed(1)} | FPT P(TP1<SL)=${fpt.toFixed(1)}%` })
      ),
      h('div', { class: 'xstat' },
        h('div', { class: 'xl', text: 'RISK TIER & PROFIT VAULT' }),
        h('div', { class: 'xv', style: 'color:var(--amber);font-size:13px', text: gear }),
        h('div', { class: 'xs', text: `Wallet $${Number(d.walletUsdt || 0).toFixed(2)} | Vault $${vaultUsd.toFixed(2)}` })
      ),
      h('div', { class: 'xstat' },
        h('div', { class: 'xl', text: 'STRATEGY SETUP & AUDIT' }),
        h('div', { class: 'xv', style: 'color:#00e5ff;font-size:12px', text: l2.setup_name || (pos && pos.setup_name) || 'MONITORING' }),
        h('div', { class: 'xs', text: `L4 Audit: ${l4.total_score || 0}/${l4.max_score || 8} | Open Positions: ${d.openPositionsCount || 0}` })
      )
    ));

    if (tab === 'OVERVIEW') {
      const entryPx = Number(l5.entry_price || l3.entry_price || (pos && pos.entry_price) || l1.current_price || 0);
      const slPx = Number(l5.stop_loss || l3.stop_loss || (pos && pos.stop_loss) || 0);
      const tp1Px = Number(l5.take_profit_1 || l3.take_profit_1 || (pos && pos.take_profit_1) || 0);
      const tp2Px = Number(l5.take_profit_2 || l5.take_profit || l3.take_profit_2 || (pos && pos.take_profit_2) || 0);

      sc.append(h('div', { class: 'xcard xcard-hi' },
        h('div', { class: 'xsec-hd' },
          h('span', { text: `EXECUTION DECISION TRANSPARENCY — ${d.symbol} (${dir})` }),
          h('span', { class: `xpill ${statusTxt.includes('APPROV') || pos ? 'ok' : 'warn'}`, text: pos ? 'ACTIVE BINANCE FUTURES POSITION' : statusTxt })
        ),
        h('div', { style: 'padding:6px 4px;font-size:11px;line-height:1.45;color:#e6edf3' },
          h('div', { text: `Layer 5 Rationale: ${l5.final_reason || (pos ? 'Position satisfied Layer 1-6 quantitative and risk gates with active SL and Maker TP1.' : 'Awaiting full alignment across deterministic and AI risk gates.')}` }),
          h('div', { style: 'margin-top:4px;color:var(--label)', text: `Entry: $${fmtPx(entryPx)}  |  Stop Loss: $${fmtPx(slPx)}  |  TP1 (50%): $${fmtPx(tp1Px)}  |  TP2 Runner: $${fmtPx(tp2Px)}  |  ETA: ${(l3.tp_time_prediction && l3.tp_time_prediction.eta_label) || '-'}` })
        )
      ));

      sc.append(h('div', { class: 'xgrid2', style: 'margin-bottom:8px' },
        h('div', { class: 'xcard', style: 'margin-bottom:0' },
          h('div', { class: 'xsec-hd' }, h('span', { text: '8-AXIS QUANTITATIVE DECISION RADAR' }), h('span', { class: 'am', text: 'LIVE TELEMETRY' })),
          makeSvgBox(buildRadarSvg(d.radarAxes))
        ),
        h('div', { class: 'xcard', style: 'margin-bottom:0' },
          h('div', { class: 'xsec-hd' }, h('span', { text: 'P_MATH CONTRIBUTION WATERFALL' }), h('span', { class: 'up', text: 'FACTOR ATTRIBUTION' })),
          makeSvgBox(buildWaterfallSvg(d.waterfall, pMath))
        )
      ));

      sc.append(h('div', { class: 'xcard' },
        h('div', { class: 'xsec-hd' },
          h('span', { text: 'FIRST-PASSAGE TIME (FPT) TRAJECTORY CONE & EXECUTION LADDER' }),
          h('span', { class: 'up', text: `P(TP1 < SL) = ${fpt.toFixed(1)}%` })
        ),
        makeSvgBox(buildFptConeSvg(d.trajectoryCone, entryPx, slPx, tp1Px, tp2Px, dir))
      ));

      const ns = d.neuroSymbolic || {};
      sc.append(h('div', { class: 'xgrid3', style: 'margin-bottom:8px' },
        h('div', { class: 'xstat' },
          h('div', { class: 'xl', text: 'MODEL 1: TABULAR QUANT ML' }),
          h('div', { class: 'xv', style: 'color:#00e5ff', text: `${ns.brain1_tabular_prob_pct ?? pMath.toFixed(1)}%` }),
          h('div', { class: 'xs', text: '532-Factor + Orderbook + Regime' })
        ),
        h('div', { class: 'xstat' },
          h('div', { class: 'xl', text: 'MODEL 2: EPISODIC k-NN MEMORY' }),
          h('div', { class: 'xv', style: 'color:#ffb000', text: `${ns.brain2_episodic_knn_prob_pct ?? 'N/A'}%` }),
          h('div', { class: 'xs', text: `Historical Samples: ${(d.aiMemorySummary && d.aiMemorySummary.totalClosed) || 0} trades` })
        ),
        h('div', { class: 'xstat' },
          h('div', { class: 'xl', text: 'MODEL 3: LLM META-JUDGE' }),
          h('div', { class: 'xv', style: 'color:#00d26a', text: `${ns.brain3_llm_prob_pct ?? pAi.toFixed(1)}%` }),
          h('div', { class: 'xs', text: 'Multi-Agent Committee + Risk Audit' })
        )
      ));

      const fBox = h('div', { class: 'xcard' },
        h('div', { class: 'xsec-hd' },
          h('span', { text: 'EXECUTION DECISION PIPELINE (LAYER 1 TO LAYER 6)' }),
          h('button', { style: 'font-size:10px', text: 'FULL PIPELINE DETAILS ->', onclick: () => { tab = 'FUNNEL L1-L6'; renderToolbar(); renderBody(); } })
        )
      );
      (d.pipelineStages || []).forEach(st => {
        fBox.append(h('div', { style: 'display:flex;justify-content:space-between;align-items:center;gap:8px;padding:5px 6px;border-bottom:1px solid #161a22' },
          h('div', {},
            h('span', { class: `xpill ${st.passed ? 'ok' : 'no'}`, text: st.passed ? 'PASS' : 'HOLD' }),
            ' ',
            h('b', { style: 'color:var(--amber)', text: st.stage + ' ' }),
            h('span', { style: 'color:#fff', text: st.name })
          ),
          h('span', { style: 'color:var(--label);font-size:10px;text-align:right', text: st.metric })
        ));
      });
      sc.append(fBox);

    } else if (tab === 'FUNNEL L1-L6') {
      (d.pipelineStages || []).forEach(st => {
        sc.append(h('div', { class: `xturn ${st.passed ? 'pro' : 'contra'}` },
          h('div', { style: 'display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:4px' },
            h('div', {},
              h('span', { class: `xpill ${st.passed ? 'ok' : 'no'}`, text: st.passed ? 'PASSED' : 'BLOCKED / HOLD' }),
              ' ',
              h('b', { style: 'color:var(--amber)', text: `${st.stage} — ${st.name}` })
            ),
            h('span', { style: 'color:#00e5ff;font-weight:700;font-size:11px', text: st.metric })
          ),
          h('div', { style: 'color:#dce4ee;font-size:11px;line-height:1.45', text: st.detail })
        ));
      });
      if (d.committee) {
        sc.append(h('div', { class: 'xcard' },
          h('div', { class: 'xsec-hd' },
            h('span', { text: 'LATEST 9-AGENT COMMITTEE VERDICT' }),
            h('button', { class: 'on', text: 'OPEN FULL TRANSCRIPT (TRAN) ->', onclick: () => ctx.run(`${selectedSym} TRAN`) })
          ),
          h('div', { style: 'padding:6px;font-size:11px', text: `Verdict: ${d.committee.approved ? 'APPROVED' : 'VETOED'} | Direction: ${d.committee.direction || '-'} | Decision: ${(d.committee.portfolio_manager && d.committee.portfolio_manager.decision) || '-'}` })
        ));
      }

    } else if (tab === '24 PILLARS') {
      const groups = ['ALL', ...new Set((d.pillars || []).map(p => p.group))];
      const fBar = h('div', { style: 'display:flex;gap:4px;flex-wrap:wrap;margin-bottom:8px' });
      groups.forEach(g => fBar.append(h('button', {
        class: pillarGroup === g ? 'on' : '',
        style: 'font-size:10px',
        text: g,
        onclick: () => { pillarGroup = g; renderBody(); }
      })));
      sc.append(fBar);

      const tbl = h('table', { class: 't' },
        h('thead', {}, h('tr', {},
          h('th', { text: 'ID' }),
          h('th', { text: 'GROUP' }),
          h('th', { text: 'TELEMETRY PILLAR' }),
          h('th', { text: 'CURRENT READING' }),
          h('th', { text: 'STATUS' })
        ))
      );
      const tbdy = h('tbody');
      (d.pillars || []).filter(p => pillarGroup === 'ALL' || p.group === pillarGroup).forEach(p => {
        tbdy.append(h('tr', {},
          h('td', { class: 'am', text: p.id }),
          h('td', { style: 'color:var(--label)', text: p.group }),
          h('td', { style: 'color:#fff;font-weight:600', text: p.name }),
          h('td', { text: p.val }),
          h('td', {}, h('span', { class: `xpill ${p.ok ? 'ok' : 'warn'}`, text: p.ok ? 'OK' : 'REVIEW' }))
        ));
      });
      tbl.append(tbdy);
      sc.append(tbl);

    } else if (tab === '532 FACTORS') {
      const cats = Object.entries(d.quantCategories || {});
      const catCard = h('div', { class: 'xcard' },
        h('div', { class: 'xsec-hd' },
          h('span', { text: `532-FACTOR QUANTITATIVE CATEGORY ATTRIBUTION (${cats.length} GROUPS)` }),
          h('span', { class: 'am', text: `COMPOSITE: ${Number(mp.composite_532_factors || 50).toFixed(2)}/100` })
        )
      );
      if (cats.length) {
        const grid = h('div', { class: 'xgrid2', style: 'padding:6px 2px' });
        cats.forEach(([k, v]) => {
          const val = Number(typeof v === 'object' ? (v.score ?? v.value ?? 50) : v) || 50;
          const col = val >= 60 ? 'var(--up)' : val <= 40 ? 'var(--dn)' : 'var(--amber)';
          grid.append(h('div', { style: 'padding:4px 6px;border:1px solid #181c24;background:#05070a' },
            h('div', { style: 'display:flex;justify-content:space-between;font-size:10px;margin-bottom:3px' },
              h('span', { style: 'color:#cfd8e3;font-weight:700', text: k.toUpperCase() }),
              h('span', { style: `color:${col};font-weight:700`, text: `${val.toFixed(1)}/100` })
            ),
            h('div', { class: 'xbar-track' }, h('div', { class: 'xbar-fill', style: `width:${Math.max(2, Math.min(100, val))}%;background:${col}` }))
          ));
        });
        catCard.append(grid);
      } else {
        catCard.append(h('div', { class: 'na', text: 'Category attribution populates automatically upon completed scan output.' }));
      }
      sc.append(catCard);

      const flt = h('input', { value: factorFilter, placeholder: 'Filter raw quantitative factors (rsi, ema, atr, zscore, vwap)...', style: 'width:100%;margin-bottom:6px' });
      flt.addEventListener('input', () => { factorFilter = flt.value; renderFactorTable(); });
      const fWrap = h('div');
      sc.append(flt, fWrap);

      const allRaw = { ...(d.sampleFactors || {}), ...mp };
      const renderFactorTable = () => {
        fWrap.textContent = '';
        const q = factorFilter.trim().toLowerCase();
        const rows = Object.entries(allRaw).filter(([k, v]) => {
          if (v != null && typeof v === 'object') return false;
          if (!q) return true;
          return k.toLowerCase().includes(q) || String(v).toLowerCase().includes(q);
        });
        const t = h('table', { class: 't' },
          h('thead', {}, h('tr', {}, h('th', { text: 'FACTOR IDENTIFIER' }), h('th', { text: 'COMPUTED VALUE' })))
        );
        const tb2 = h('tbody');
        rows.slice(0, 140).forEach(([k, v]) => {
          tb2.append(h('tr', {},
            h('td', { style: 'color:var(--label)', text: k }),
            h('td', { style: 'color:#fff', text: typeof v === 'number' ? (Number.isInteger(v) ? String(v) : v.toFixed(4)) : String(v) })
          ));
        });
        t.append(tb2);
        fWrap.append(t);
      };
      renderFactorTable();
    }
  }

  renderToolbar();
  load(selectedSym);
  const iv = setInterval(() => { if (!document.hidden && !unmounted) load(selectedSym); }, 15000);
  ctx.cleanup(() => { unmounted = true; clearInterval(iv); });
}

// =====================================================================
// 2. TRAN / TRSC — COMMITTEE DEBATE & EARNINGS TRANSCRIPTS
// =====================================================================
export function mountTRAN(body, ctx) {
  body.classList.add('fill');
  const tb = h('div', { class: 'tb' });
  const sc = h('div', { class: 'pb' });
  body.append(tb, sc);

  let sym = ctx.symbol || 'BTCUSDT';
  let tab = 'DEBATE';
  let sessionIdx = 0;
  let searchQ = '';
  let data = null;
  let unmounted = false;

  async function load(target = sym) {
    sym = String(target || 'BTCUSDT').trim().toUpperCase();
    const env = await get('transcripts', { symbol: sym }, 4000);
    if (unmounted) return;
    ctx.status(env);
    if (!env.ok || !env.data) {
      sc.textContent = '';
      sc.append(h('div', { class: 'na', text: 'Transcript service unavailable: ' + (env.error || 'error') }));
      return;
    }
    data = env.data;
    sessionIdx = 0;
    renderToolbar();
    renderBody();
  }

  function renderToolbar() {
    tb.textContent = '';
    const inp = h('input', { value: sym, style: 'width:88px;text-transform:uppercase;font-weight:700' });
    inp.addEventListener('keydown', e => { if (e.key === 'Enter') load(inp.value); });
    const qInp = h('input', { value: searchQ, placeholder: 'Search transcript...', style: 'width:125px' });
    qInp.addEventListener('input', () => { searchQ = qInp.value; renderBody(); });

    tb.append(
      h('span', { class: 'lbl', text: 'TRANSCRIPTS:' }),
      inp,
      h('button', { class: 'on', text: 'LOAD', onclick: () => load(inp.value) }),
      h('button', { class: tab === 'DEBATE' ? 'on' : '', text: '9-AGENT DEBATE', onclick: () => { tab = 'DEBATE'; renderToolbar(); renderBody(); } }),
      h('button', { class: tab === 'LAYERS' ? 'on' : '', text: '5-LAYER & MEMORY', onclick: () => { tab = 'LAYERS'; renderToolbar(); renderBody(); } }),
      h('button', { class: tab === 'CORP' ? 'on' : '', text: 'EARNINGS & CATALYSTS', onclick: () => { tab = 'CORP'; renderToolbar(); renderBody(); } }),
      qInp,
      h('button', { style: 'color:#ffb000;border-color:#ffb00066', text: 'X-RAY', onclick: () => ctx.run(`${sym} FACT`) })
    );
  }

  function renderBody() {
    sc.textContent = '';
    if (!data) return;
    const q = searchQ.trim().toLowerCase();

    if (tab === 'DEBATE') {
      const sessions = data.debateSessions || [];
      if (!sessions.length) {
        sc.append(h('div', { class: 'xcard' },
          h('div', { class: 'xsec-hd' }, h('span', { text: '9-AGENT ADVERSARIAL COMMITTEE TRANSCRIPT' }), h('span', { class: 'xpill warn', text: 'STANDBY' })),
          h('div', { style: 'padding:10px;font-size:11px;line-height:1.5;color:#cfd8e3' },
            'No committee debate session recorded yet for this symbol. The 9-Agent Adversarial Committee convenes automatically once an instrument passes Layer 5 approval.',
            h('div', { style: 'margin-top:8px;display:flex;gap:6px' },
              h('button', { class: 'on', text: 'VIEW 5-LAYER AUDIT TRAIL ->', onclick: () => { tab = 'LAYERS'; renderToolbar(); renderBody(); } }),
              h('button', { text: 'VIEW EARNINGS & CATALYSTS ->', onclick: () => { tab = 'CORP'; renderToolbar(); renderBody(); } })
            )
          )
        ));
        return;
      }

      const selBar = h('div', { style: 'display:flex;gap:4px;flex-wrap:wrap;margin-bottom:8px' });
      sessions.forEach((s, i) => {
        selBar.append(h('button', {
          class: i === sessionIdx ? 'on' : '',
          style: 'font-size:10px',
          text: `#${i + 1} ${s.symbol} | ${s.approved ? 'APPROVED' : 'VETOED'} (${s.direction})`,
          onclick: () => { sessionIdx = i; renderBody(); }
        }));
      });
      sc.append(selBar);

      const cur = sessions[sessionIdx] || sessions[0];
      sc.append(h('div', { class: 'xcard xcard-hi' },
        h('div', { class: 'xsec-hd' },
          h('span', { text: `SESSION: ${cur.symbol} (${cur.id}) | ${String(cur.timestamp || '').slice(0, 19)}` }),
          h('span', { class: `xpill ${cur.approved ? 'ok' : 'no'}`, text: `${cur.approved ? 'APPROVED' : 'VETOED'} | ${cur.direction} | ${cur.confidencePct}% | ${cur.elapsedSec}s` })
        )
      ));

      (cur.turns || []).filter(t => !q || t.speaker.toLowerCase().includes(q) || String(t.text).toLowerCase().includes(q)).forEach(t => {
        const cls = t.role === 'PRO' || t.role === 'REBUTTAL' ? 'pro' : t.role === 'CONTRA' ? 'contra' : t.role === 'JUDGE' ? 'judge' : t.role === 'RISK' ? 'risk' : '';
        const pCls = t.stance === 'APPROVED' || t.stance === 'APPROVE' ? 'ok' : t.stance === 'VETOED' || t.stance === 'VETO' || t.stance === 'CHALLENGE' ? 'no' : 'info';
        sc.append(h('div', { class: `xturn ${cls}` },
          h('div', { style: 'display:flex;justify-content:space-between;align-items:center;margin-bottom:4px' },
            h('b', { style: 'color:#fff;font-size:11px', text: t.speaker }),
            h('span', { class: `xpill ${pCls}`, text: t.stance })
          ),
          h('div', { style: 'font-size:11px;line-height:1.5;color:#dce4ee;white-space:pre-wrap', text: t.text })
        ));
      });

    } else if (tab === 'LAYERS') {
      const steps = data.pipelineTranscript || [];
      const card = h('div', { class: 'xcard' },
        h('div', { class: 'xsec-hd' },
          h('span', { text: `5-LAYER EXECUTION AUDIT TRAIL (${data.symbol})` }),
          h('span', { class: 'am', text: `${steps.length} STAGES LOGGED` })
        )
      );
      if (steps.length) {
        steps.filter(s => !q || s.step.toLowerCase().includes(q) || s.text.toLowerCase().includes(q)).forEach(s => {
          card.append(h('div', { class: 'xturn', style: 'margin:6px' },
            h('div', { style: 'display:flex;justify-content:space-between;margin-bottom:3px' },
              h('b', { style: 'color:var(--amber)', text: s.step }),
              h('span', { style: 'color:var(--label);font-size:10px', text: s.speaker })
            ),
            h('div', { style: 'font-size:11px;line-height:1.48;color:#e6edf3', text: s.text })
          ));
        });
      } else {
        card.append(h('div', { class: 'na', text: 'No scan audit file found for this instrument yet.' }));
      }
      sc.append(card);

      const pms = data.postMortems || [];
      const pmCard = h('div', { class: 'xcard' },
        h('div', { class: 'xsec-hd' },
          h('span', { text: 'TRADE MEMORY — POST-MORTEM ARCHIVE' }),
          h('span', { class: 'up', text: `${pms.length} RECORDS` })
        )
      );
      if (pms.length) {
        pms.filter(p => !q || String(p.symbol).toLowerCase().includes(q) || String(p.lesson).toLowerCase().includes(q)).forEach(p => {
          const pnl = Number(p.netPnlUsd || 0);
          pmCard.append(h('div', { class: `xturn ${pnl >= 0 ? 'pro' : 'contra'}`, style: 'margin:6px' },
            h('div', { style: 'display:flex;justify-content:space-between;margin-bottom:3px' },
              h('b', { style: 'color:#fff', text: `${p.symbol} ${p.direction || ''} | ${p.setup || '-'}` }),
              h('span', { class: `xpill ${pnl >= 0 ? 'ok' : 'no'}`, text: `${pnl >= 0 ? '+' : ''}$${pnl.toFixed(4)} (${p.exitReason || 'CLOSED'})` })
            ),
            h('div', { style: 'font-size:11px;color:#cfd8e3', text: p.lesson })
          ));
        });
      } else {
        pmCard.append(h('div', { class: 'na', text: 'No closed-trade post-mortems archived yet.' }));
      }
      sc.append(pmCard);

    } else if (tab === 'CORP') {
      const corp = data.corporateTranscript;
      if (!corp) {
        sc.append(h('div', { class: 'na', text: 'Corporate earnings transcript unavailable.' }));
        return;
      }
      sc.append(h('div', { class: 'xgrid2', style: 'margin-bottom:8px' },
        h('div', { class: 'xcard', style: 'margin-bottom:0' },
          h('div', { class: 'xsec-hd' }, h('span', { text: `${corp.entityName} (${corp.exchange})` }), h('span', { class: 'am', text: 'NLP TONE GAUGE' })),
          makeSvgBox(buildGaugeSvg(corp.toneScore, corp.toneLabel))
        ),
        h('div', { class: 'xcard', style: 'margin-bottom:0' },
          h('div', { class: 'xsec-hd' }, h('span', { text: 'PREPARED REMARKS & SEC XBRL HIGHLIGHTS' }), h('span', { class: 'up', text: 'VERIFIED' })),
          h('div', { style: 'padding:8px;font-size:11px;line-height:1.6;color:#e6edf3' },
            ...(corp.preparedRemarks || []).map(r => h('div', { style: 'margin-bottom:5px', text: '- ' + r }))
          )
        )
      ));

      const qaCard = h('div', { class: 'xcard' },
        h('div', { class: 'xsec-hd' }, h('span', { text: 'CATALYST WIRE & ANALYST Q&A FEED' }), h('span', { class: 'am', text: `${(corp.qaSnippets || []).length} ITEMS` }))
      );
      (corp.qaSnippets || []).filter(it => !q || String(it.text).toLowerCase().includes(q)).forEach(it => {
        const cls = it.sentiment === 'POSITIVE' ? 'pro' : it.sentiment === 'NEGATIVE' ? 'contra' : '';
        const pCls = it.sentiment === 'POSITIVE' ? 'ok' : it.sentiment === 'NEGATIVE' ? 'no' : 'info';
        qaCard.append(h('div', { class: `xturn ${cls}`, style: 'margin:6px' },
          h('div', { style: 'display:flex;justify-content:space-between;margin-bottom:3px' },
            h('b', { style: 'color:var(--label)', text: `#${it.idx} ${it.speaker}` }),
            h('span', { class: `xpill ${pCls}`, text: it.sentiment })
          ),
          h('div', { style: 'font-size:11px;color:#fff' },
            it.link ? h('a', { href: it.link, target: '_blank', rel: 'noopener', style: 'color:#e6edf3;text-decoration:none', text: it.text }) : it.text
          )
        ));
      });
      sc.append(qaCard);

      if (corp.recentFilings && corp.recentFilings.length) {
        const fTbl = h('table', { class: 't' },
          h('thead', {}, h('tr', {}, h('th', { text: 'FORM' }), h('th', { text: 'DATE' }), h('th', { text: 'SEC EDGAR FILING' })))
        );
        const fb = h('tbody');
        corp.recentFilings.forEach(f => fb.append(h('tr', {},
          h('td', { class: 'am', text: f.form || '-' }),
          h('td', { text: f.date || '-' }),
          h('td', {}, f.url ? h('a', { href: f.url, target: '_blank', rel: 'noopener', style: 'color:var(--label)', text: f.desc || f.accession || 'Open SEC Filing' }) : (f.desc || '-'))
        )));
        fTbl.append(fb);
        sc.append(fTbl);
      }
    }
  }

  renderToolbar();
  load(sym);
  ctx.cleanup(() => { unmounted = true; });
}

// =====================================================================
// 3. G / SNAP / PATT — MULTI-CHART STUDIO & SNAPSHOT ARCHIVE
// =====================================================================
function calcMiniRsi14(closes) {
  if (!Array.isArray(closes) || closes.length < 15) return 50;
  let avgG = 0, avgL = 0;
  for (let i = 1; i <= 14; i++) {
    const d = closes[i] - closes[i - 1];
    if (d > 0) avgG += d; else avgL -= d;
  }
  avgG /= 14; avgL /= 14;
  for (let i = 15; i < closes.length; i++) {
    const d = closes[i] - closes[i - 1];
    avgG = (avgG * 13 + (d > 0 ? d : 0)) / 14;
    avgL = (avgL * 13 + (d < 0 ? -d : 0)) / 14;
  }
  if (avgL <= 1e-12) return 100;
  return 100 - 100 / (1 + avgG / avgL);
}

function drawMiniCandles(canvas, candles, sym, iv) {
  const dpr = 2; // Force 2x Retina supersampling for razor-sharp display & PNG export
  const w = canvas.clientWidth || 380;
  const hPx = 230;
  canvas.width = Math.round(w * dpr);
  canvas.height = Math.round(hPx * dpr);
  const ctx2d = canvas.getContext('2d');
  ctx2d.scale(dpr, dpr);
  ctx2d.fillStyle = '#040609';
  ctx2d.fillRect(0, 0, w, hPx);

  if (!Array.isArray(candles) || candles.length < 5) {
    ctx2d.fillStyle = '#778396';
    ctx2d.font = '11px monospace';
    ctx2d.fillText('No market data for ' + sym, 12, hPx / 2);
    return { bias: 'N/A', chgPct: 0, lastPx: 0 };
  }

  const allCloses = candles.map(c => Number(c.c ?? c.close ?? 0)).filter(v => v > 0);
  const rsiVal = calcMiniRsi14(allCloses);

  const list = candles.slice(-64);
  const padL = 8, padR = 64, padT = 26, padB = 24;
  const plotW = w - padL - padR;
  const plotH = hPx - padT - padB;
  let lo = Infinity, hi = -Infinity, maxV = 0;
  let hiIdx = 0, loIdx = 0;

  // Precompute EMA20, EMA50, and Bollinger(20, 2) across full candle array so tail slice is warm
  let e20 = Number(candles[0].c ?? candles[0].close ?? 0);
  let e50 = e20;
  const k20 = 2 / 21, k50 = 2 / 51;
  const fullMeta = candles.map((c, idx) => {
    const cl = Number(c.c ?? c.close ?? 0);
    e20 = idx === 0 ? cl : cl * k20 + e20 * (1 - k20);
    e50 = idx === 0 ? cl : cl * k50 + e50 * (1 - k50);
    let bbUp = null, bbLo = null;
    if (idx >= 19) {
      let sum = 0;
      for (let j = idx - 19; j <= idx; j++) sum += Number(candles[j].c ?? candles[j].close ?? 0);
      const mean = sum / 20;
      let sq = 0;
      for (let j = idx - 19; j <= idx; j++) {
        const d = Number(candles[j].c ?? candles[j].close ?? 0) - mean;
        sq += d * d;
      }
      const sd = Math.sqrt(sq / 20);
      bbUp = mean + 2 * sd;
      bbLo = mean - 2 * sd;
    }
    return { e20, e50, bbUp, bbLo };
  });
  const metaSlice = fullMeta.slice(-list.length);

  list.forEach((c, i) => {
    const cLo = Number(c.l ?? c.low ?? c.c);
    const cHi = Number(c.h ?? c.high ?? c.c);
    if (cLo < lo) { lo = cLo; loIdx = i; }
    if (cHi > hi) { hi = cHi; hiIdx = i; }
    if (metaSlice[i].bbLo != null) lo = Math.min(lo, metaSlice[i].bbLo);
    if (metaSlice[i].bbUp != null) hi = Math.max(hi, metaSlice[i].bbUp);
    maxV = Math.max(maxV, Number(c.v ?? c.volume ?? 0));
  });

  const rawLo = Number(list[loIdx].l ?? list[loIdx].low ?? lo);
  const rawHi = Number(list[hiIdx].h ?? list[hiIdx].high ?? hi);
  const span = Math.max(1e-8, hi - lo);
  lo -= span * 0.07;
  hi += span * 0.08;
  const yOf = p => padT + ((hi - p) / (hi - lo)) * plotH;
  const step = plotW / list.length;

  // Grid & Right Price Scale
  ctx2d.strokeStyle = '#121822';
  ctx2d.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const gy = padT + (i / 4) * plotH;
    ctx2d.beginPath(); ctx2d.moveTo(padL, gy); ctx2d.lineTo(w - padR, gy); ctx2d.stroke();
    const gp = hi - (i / 4) * (hi - lo);
    ctx2d.fillStyle = '#6c798c';
    ctx2d.font = '9px monospace';
    ctx2d.fillText(fmtPx(gp), w - padR + 4, gy + 3);
  }

  // Horizontal Volume-at-Price Profile (14 Bins) + POC Line
  const BINS = 14;
  const binVol = new Array(BINS).fill(0);
  list.forEach(c => {
    const typ = (Number(c.h ?? c.high ?? c.c) + Number(c.l ?? c.low ?? c.c) + Number(c.c ?? c.close)) / 3;
    const v = Math.max(0, Number(c.v ?? c.volume ?? 0));
    const bIdx = Math.max(0, Math.min(BINS - 1, Math.floor(((typ - lo) / (hi - lo)) * BINS)));
    binVol[bIdx] += v;
  });
  const maxBinV = Math.max(...binVol, 0);
  let pocIdx = 0;
  if (maxBinV > 0) {
    const binH = plotH / BINS;
    binVol.forEach((bv, bIdx) => {
      if (bv > binVol[pocIdx]) pocIdx = bIdx;
      const bw = (bv / maxBinV) * (plotW * 0.24);
      const by = padT + plotH - (bIdx + 1) * binH;
      ctx2d.fillStyle = bIdx === pocIdx ? 'rgba(255, 176, 0, 0.24)' : 'rgba(77, 163, 255, 0.12)';
      ctx2d.fillRect(w - padR - bw, by + 0.5, bw, Math.max(1.5, binH - 1));
    });
    const pocPx = lo + ((pocIdx + 0.5) / BINS) * (hi - lo);
    const pocY = yOf(pocPx);
    ctx2d.save();
    ctx2d.strokeStyle = 'rgba(255, 176, 0, 0.55)';
    ctx2d.setLineDash([3, 3]);
    ctx2d.lineWidth = 1;
    ctx2d.beginPath(); ctx2d.moveTo(padL, pocY); ctx2d.lineTo(w - padR, pocY); ctx2d.stroke();
    ctx2d.restore();
  }

  // Bollinger(20, 2) Shaded Envelope
  const bbPts = [];
  list.forEach((_, i) => {
    if (metaSlice[i].bbUp != null && metaSlice[i].bbLo != null) {
      bbPts.push({ x: padL + i * step + step / 2, u: yOf(metaSlice[i].bbUp), l: yOf(metaSlice[i].bbLo) });
    }
  });
  if (bbPts.length >= 2) {
    ctx2d.beginPath();
    bbPts.forEach((p, idx) => { if (idx === 0) ctx2d.moveTo(p.x, p.u); else ctx2d.lineTo(p.x, p.u); });
    for (let idx = bbPts.length - 1; idx >= 0; idx--) ctx2d.lineTo(bbPts[idx].x, bbPts[idx].l);
    ctx2d.closePath();
    ctx2d.fillStyle = 'rgba(77, 163, 255, 0.07)';
    ctx2d.fill();

    ctx2d.save();
    ctx2d.strokeStyle = 'rgba(77, 163, 255, 0.36)';
    ctx2d.lineWidth = 0.9;
    ctx2d.setLineDash([2, 2]);
    ctx2d.beginPath();
    bbPts.forEach((p, idx) => { if (idx === 0) ctx2d.moveTo(p.x, p.u); else ctx2d.lineTo(p.x, p.u); });
    ctx2d.stroke();
    ctx2d.beginPath();
    bbPts.forEach((p, idx) => { if (idx === 0) ctx2d.moveTo(p.x, p.l); else ctx2d.lineTo(p.x, p.l); });
    ctx2d.stroke();
    ctx2d.restore();
  }

  // Candlesticks + Bottom Volume Histogram + EMA20/EMA50 Coordinates
  const ema20Pts = [], ema50Pts = [];
  list.forEach((c, i) => {
    const o = Number(c.o ?? c.open), hV = Number(c.h ?? c.high), lV = Number(c.l ?? c.low), cl = Number(c.c ?? c.close), v = Number(c.v ?? c.volume ?? 0);
    const x = padL + i * step + step / 2;
    ema20Pts.push([x, yOf(metaSlice[i].e20)]);
    ema50Pts.push([x, yOf(metaSlice[i].e50)]);

    if (maxV > 0) {
      const vh = (v / maxV) * 26;
      ctx2d.fillStyle = cl >= o ? 'rgba(0,210,106,0.22)' : 'rgba(255,59,48,0.22)';
      ctx2d.fillRect(x - step * 0.35, hPx - padB - vh, Math.max(1.5, step * 0.7), vh);
    }

    const up = cl >= o;
    ctx2d.strokeStyle = up ? '#00d26a' : '#ff453a';
    ctx2d.fillStyle = up ? '#00d26a' : '#ff453a';
    ctx2d.lineWidth = 1.1;
    ctx2d.beginPath();
    ctx2d.moveTo(x, yOf(hV));
    ctx2d.lineTo(x, yOf(lV));
    ctx2d.stroke();

    const top = Math.min(yOf(o), yOf(cl));
    const bh = Math.max(1.3, Math.abs(yOf(cl) - yOf(o)));
    ctx2d.fillRect(x - Math.max(1, step * 0.33), top, Math.max(2, step * 0.66), bh);
  });

  // EMA50 (#00e5ff) & EMA20 (#ffb000)
  ctx2d.strokeStyle = '#00e5ff';
  ctx2d.lineWidth = 1.15;
  ctx2d.beginPath();
  ema50Pts.forEach(([x, y], i) => { if (i === 0) ctx2d.moveTo(x, y); else ctx2d.lineTo(x, y); });
  ctx2d.stroke();

  ctx2d.strokeStyle = '#ffb000';
  ctx2d.lineWidth = 1.45;
  ctx2d.beginPath();
  ema20Pts.forEach(([x, y], i) => { if (i === 0) ctx2d.moveTo(x, y); else ctx2d.lineTo(x, y); });
  ctx2d.stroke();

  // Swing High & Swing Low Price Callouts
  const xHi = Math.min(w - padR - 58, Math.max(padL + 2, padL + hiIdx * step - 8));
  const xLo = Math.min(w - padR - 58, Math.max(padL + 2, padL + loIdx * step - 8));
  ctx2d.font = 'bold 8.5px monospace';
  ctx2d.fillStyle = '#00d26a';
  ctx2d.fillText(`HI ${fmtPx(rawHi)}`, xHi, Math.max(padT + 8, yOf(rawHi) - 4));
  ctx2d.fillStyle = '#ff5a52';
  ctx2d.fillText(`LO ${fmtPx(rawLo)}`, xLo, Math.min(hPx - padB - 3, yOf(rawLo) + 10));

  const first = Number(list[0].c ?? list[0].close);
  const last = Number(list[list.length - 1].c ?? list[list.length - 1].close);
  const lastE20 = metaSlice[metaSlice.length - 1].e20;
  const lastE50 = metaSlice[metaSlice.length - 1].e50;
  const chgPct = first > 0 ? ((last - first) / first) * 100 : 0;
  const bias = (last > lastE20 && lastE20 >= lastE50)
    ? 'BULL TREND (PX > EMA20 > EMA50)'
    : (last < lastE20 && lastE20 <= lastE50)
    ? 'BEAR TREND (PX < EMA20 < EMA50)'
    : 'MEAN REVERSION / CONSOLIDATION';

  // Live Last Price Pill on Right Scale
  const lastY = Math.max(padT + 6, Math.min(hPx - padB - 6, yOf(last)));
  ctx2d.fillStyle = chgPct >= 0 ? '#00d26a' : '#ff453a';
  ctx2d.fillRect(w - padR + 1, lastY - 6, padR - 2, 12);
  ctx2d.fillStyle = '#000000';
  ctx2d.font = 'bold 8.5px monospace';
  ctx2d.fillText(fmtPx(last), w - padR + 4, lastY + 3);

  // Top & Bottom Institutional HUD Bars
  ctx2d.fillStyle = '#0a0e14';
  ctx2d.fillRect(0, 0, w, 20);
  ctx2d.fillStyle = '#ff6600';
  ctx2d.font = 'bold 10.5px monospace';
  ctx2d.fillText(`${sym} [${iv.toUpperCase()}]  $${fmtPx(last)} (${fmtPct(chgPct)})`, 8, 13.5);
  ctx2d.fillStyle = rsiVal >= 65 ? '#00d26a' : rsiVal <= 35 ? '#ff5a52' : '#ffb000';
  ctx2d.font = 'bold 9.5px monospace';
  ctx2d.textAlign = 'right';
  ctx2d.fillText(`RSI14: ${rsiVal.toFixed(1)} | EMA20/50 + BB + VPVR`, w - 8, 13.5);
  ctx2d.textAlign = 'left';

  ctx2d.fillStyle = '#070a0f';
  ctx2d.fillRect(0, hPx - 18, w, 18);
  ctx2d.fillStyle = bias.startsWith('BULL') ? '#00d26a' : bias.startsWith('BEAR') ? '#ff5a52' : '#9aa7b8';
  ctx2d.font = 'bold 9px monospace';
  ctx2d.fillText(bias, 8, hPx - 6);
  ctx2d.fillStyle = '#6c798c';
  ctx2d.textAlign = 'right';
  ctx2d.fillText('BLOOMBERG TERMINAL // HD', w - 8, hPx - 6);
  ctx2d.textAlign = 'left';

  return { bias, chgPct, lastPx: last, rsi: rsiVal };
}

export function mountSTUDIO(body, ctx) {
  body.classList.add('fill');
  const tb = h('div', { class: 'tb' });
  const sc = h('div', { class: 'pb' });
  body.append(tb, sc);

  let tab = 'WALL';
  let iv = '15m';
  let wallSyms = LS.get('bbg_studio_wall_v1', ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT']);
  if (!Array.isArray(wallSyms) || wallSyms.length !== 4) wallSyms = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT'];
  const canvasMap = new Map();
  let unmounted = false;

  function renderToolbar() {
    tb.textContent = '';
    tb.append(
      h('span', { class: 'lbl', text: 'MULTI-CHART STUDIO:' }),
      h('button', { class: tab === 'WALL' ? 'on' : '', text: '4-CHART WALL', onclick: () => { tab = 'WALL'; renderToolbar(); renderBody(); } }),
      h('button', { class: tab === 'GALLERY' ? 'on' : '', text: 'PNG ARCHIVE', onclick: () => { tab = 'GALLERY'; renderToolbar(); renderBody(); } }),
      h('button', { class: tab === 'PATTERNS' ? 'on' : '', text: 'PATTERN SCHEMATICS', onclick: () => { tab = 'PATTERNS'; renderToolbar(); renderBody(); } }),
      ...['5m', '15m', '1h', '4h'].map(t => h('button', {
        class: iv === t ? 'on' : '',
        text: t.toUpperCase(),
        onclick: () => { iv = t; renderToolbar(); renderBody(); }
      })),
      h('button', { style: 'color:#00d26a;border-color:#00d26a66', text: 'SNAP ALL 4', onclick: snapAllFour }),
      h('button', { text: 'OPEN GP', onclick: () => ctx.run(`${ctx.symbol} GP`) })
    );
  }

  function snapCanvas(sym, canvas, downloadFile = true) {
    if (!canvas) return;
    try {
      const dataUrl = canvas.toDataURL('image/png');
      saveSnapshotToGallery({
        id: 'SNAP-' + Date.now() + '-' + sym,
        symbol: sym,
        interval: iv.toUpperCase(),
        ts: Date.now(),
        dataUrl
      });
      if (downloadFile) {
        const a = document.createElement('a');
        a.href = dataUrl;
        a.download = `Bloomberg_Terminal_${sym}_${iv}_${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}.png`;
        document.body.appendChild(a);
        a.click();
        setTimeout(() => a.remove(), 150);
      }
    } catch {}
  }

  function snapAllFour() {
    if (tab !== 'WALL') { tab = 'WALL'; renderToolbar(); renderBody(); return; }
    let count = 0;
    for (const [sym, c] of canvasMap.entries()) {
      snapCanvas(sym, c, false);
      count++;
    }
    if (count > 0) {
      tab = 'GALLERY';
      renderToolbar();
      renderBody();
    }
  }

  async function renderBody() {
    sc.textContent = '';
    canvasMap.clear();
    if (tab === 'WALL') {
      const editBar = h('div', { style: 'display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin-bottom:8px' },
        h('span', { class: 'lbl', text: 'WATCHLIST QUAD:' })
      );
      const inputs = wallSyms.map((s, idx) => h('input', { value: s, style: 'width:84px;text-transform:uppercase;font-weight:700', title: `Slot ${idx + 1}` }));
      editBar.append(...inputs, h('button', {
        class: 'on',
        text: 'APPLY 4 CHARTS',
        onclick: () => {
          wallSyms = inputs.map((el, i) => (el.value.trim().toUpperCase() || ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT'][i]));
          LS.set('bbg_studio_wall_v1', wallSyms);
          renderBody();
        }
      }));
      sc.append(editBar);

      const grid = h('div', { class: 'xgrid2' });
      sc.append(grid);

      await Promise.all(wallSyms.map(async sym => {
        const card = h('div', { class: 'xcard', style: 'margin-bottom:0;padding:6px' });
        const hd = h('div', { class: 'xsec-hd' },
          h('span', { style: 'color:var(--amber)', text: `${sym} (${iv.toUpperCase()})` }),
          h('div', { style: 'display:flex;gap:4px' },
            h('button', { style: 'font-size:10px', text: 'SNAP PNG', onclick: () => snapCanvas(sym, canvasMap.get(sym), true) }),
            h('button', { style: 'font-size:10px', text: 'TECH', onclick: () => ctx.run(`${sym} TECH`) }),
            h('button', { style: 'font-size:10px', text: 'GP', onclick: () => ctx.run(`${sym} GP`) }),
            h('button', { style: 'font-size:10px', text: 'X-RAY', onclick: () => ctx.run(`${sym} FACT`) })
          )
        );
        const cv = h('canvas', { style: 'width:100%;height:230px;display:block;background:#040609' });
        card.append(hd, cv);
        grid.append(card);
        canvasMap.set(sym, cv);

        const env = await get('kline', { symbol: sym, interval: iv, limit: 110 }, 4000);
        if (unmounted) return;
        ctx.status(env);
        const arr = env.ok && Array.isArray(env.data) ? env.data : (env.data && env.data.candles) || [];
        drawMiniCandles(cv, arr, sym, iv);
      }));

    } else if (tab === 'GALLERY') {
      const snaps = LS.get(SNAP_KEY, []);
      const top = h('div', { style: 'display:flex;justify-content:space-between;align-items:center;margin-bottom:8px' },
        h('span', { style: 'color:var(--label);font-size:11px', text: `Archived Chart PNG Snapshots (${Array.isArray(snaps) ? snaps.length : 0} files). Capture from GP <GO> or 4-Chart Wall.` }),
        h('button', { style: 'color:#ff5a52;border-color:#ff5a5266', text: 'CLEAR ARCHIVE', onclick: () => { LS.set(SNAP_KEY, []); renderBody(); } })
      );
      sc.append(top);
      if (!Array.isArray(snaps) || !snaps.length) {
        sc.append(h('div', { class: 'na', text: 'No archived chart PNGs yet. Click SNAP ALL 4 above or SNAP PNG inside GP <GO>.' }));
        return;
      }
      const g = h('div', { class: 'snap-grid' });
      snaps.forEach((s, idx) => {
        const srcUrl = s.dataUrl || s.img || '';
        if (!srcUrl) return;
        const card = h('div', { class: 'snap-card' },
          h('img', { src: srcUrl, alt: `${s.symbol} chart snapshot`, onclick: () => openImagePreview({ ...s, dataUrl: srcUrl }) }),
          h('div', { style: 'padding:6px;display:flex;justify-content:space-between;align-items:center;gap:6px' },
            h('div', {},
              h('b', { style: 'color:var(--amber)', text: `${s.symbol} [${s.interval || '-'}]` }),
              h('div', { style: 'font-size:9.5px;color:var(--muted)', text: fmtTime(s.ts, true) })
            ),
            h('div', { style: 'display:flex;gap:4px' },
              h('button', { style: 'font-size:10px', text: 'DOWNLOAD PNG', onclick: () => { const a = document.createElement('a'); a.href = srcUrl; a.download = `Bloomberg_Terminal_${s.symbol}_${s.interval || 'chart'}.png`; a.click(); } }),
              h('button', { style: 'font-size:10px;color:#ff5a52', text: 'DEL', onclick: () => { snaps.splice(idx, 1); LS.set(SNAP_KEY, snaps); renderBody(); } })
            )
          )
        );
        g.append(card);
      });
      sc.append(g);

    } else if (tab === 'PATTERNS') {
      const detCard = h('div', { class: 'xcard xcard-hi' },
        h('div', { class: 'xsec-hd' }, h('span', { text: `REAL-TIME STRUCTURE & PATTERN SCANNER — ${ctx.symbol} (${iv.toUpperCase()})` }), h('span', { class: 'up', text: 'LIVE OHLCV' }))
      );
      const detBody = h('div', { style: 'padding:8px;font-size:11px;color:#cfd8e3', text: 'Scanning live candle structure...' });
      detCard.append(detBody);
      sc.append(detCard);

      const diagGrid = h('div', { class: 'xgrid2' },
        h('div', { class: 'xcard' },
          h('div', { class: 'xsec-hd' }, h('span', { text: '1. TWO-STAGE EXECUTION LADDER' }), h('span', { class: 'up', text: 'TP1 50% + TP2 RUNNER' })),
          makeSvgBox(`<svg viewBox="0 0 360 155" style="width:100%;height:auto;background:#040608;display:block">
            <line x1="20" y1="128" x2="340" y2="128" stroke="#ff5a52" stroke-dasharray="4,3"/>
            <text x="24" y="123" fill="#ff5a52" font-size="9" font-family="monospace">STOP LOSS (-1.0R | LIQ SHIELDED)</text>
            <line x1="20" y1="96" x2="340" y2="96" stroke="#00e5ff" stroke-dasharray="2,2"/>
            <text x="24" y="91" fill="#00e5ff" font-size="9" font-family="monospace">EXECUTION ENTRY (0.0R | MAKER GTX)</text>
            <line x1="20" y1="68" x2="340" y2="68" stroke="#ffb000" stroke-dasharray="3,2"/>
            <text x="24" y="63" fill="#ffb000" font-size="9" font-family="monospace">STAGE 0: MOVE SL TO BREAKEVEN (+0.65R)</text>
            <line x1="20" y1="48" x2="340" y2="48" stroke="#00d26a"/>
            <text x="24" y="43" fill="#00d26a" font-size="9" font-weight="700" font-family="monospace">STAGE 1: TP1 LOCK 50% (+0.90R)</text>
            <line x1="20" y1="22" x2="340" y2="22" stroke="#b388ff"/>
            <text x="24" y="17" fill="#b388ff" font-size="9" font-weight="700" font-family="monospace">STAGE 2: TP2 RUNNER (+2.0R + TRAILING)</text>
            <polyline points="35,108 85,96 150,74 215,48 265,56 325,22" fill="none" stroke="#fff" stroke-width="2"/>
            <circle cx="85" cy="96" r="4" fill="#00e5ff"/><circle cx="215" cy="48" r="4" fill="#00d26a"/><circle cx="325" cy="22" r="4" fill="#b388ff"/>
          </svg>`)
        ),
        h('div', { class: 'xcard' },
          h('div', { class: 'xsec-hd' }, h('span', { text: '2. MARKET STRUCTURE (BOS / ORDER BLOCK)' }), h('span', { class: 'am', text: 'PRICE ACTION' })),
          makeSvgBox(`<svg viewBox="0 0 360 155" style="width:100%;height:auto;background:#040608;display:block">
            <rect x="64" y="96" width="88" height="24" fill="rgba(0,210,106,0.18)" stroke="#00d26a" stroke-dasharray="3,2"/>
            <text x="68" y="112" fill="#00d26a" font-size="8.5" font-family="monospace">DEMAND ORDER BLOCK</text>
            <line x1="95" y1="54" x2="290" y2="54" stroke="#ffb000" stroke-dasharray="4,2"/>
            <text x="195" y="49" fill="#ffb000" font-size="9" font-weight="700" font-family="monospace">BOS (BREAK OF STRUCTURE)</text>
            <polyline points="20,120 65,98 98,54 136,104 205,34 252,70 328,20" fill="none" stroke="#00e5ff" stroke-width="2"/>
            <circle cx="136" cy="104" r="4" fill="#00d26a"/>
            <text x="142" y="110" fill="#fff" font-size="8.5" font-family="monospace">RETEST ENTRY</text>
          </svg>`)
        ),
        h('div', { class: 'xcard' },
          h('div', { class: 'xsec-hd' }, h('span', { text: '3. FAIR VALUE GAP (FVG) & FIBO 0.618' }), h('span', { class: 'am', text: 'IMBALANCE' })),
          makeSvgBox(`<svg viewBox="0 0 360 155" style="width:100%;height:auto;background:#040608;display:block">
            <rect x="112" y="64" width="160" height="28" fill="rgba(255,176,0,0.16)" stroke="#ffb000"/>
            <text x="120" y="81" fill="#ffb000" font-size="9" font-weight="700" font-family="monospace">FVG IMBALANCE / GOLDEN POCKET 0.618</text>
            <rect x="52" y="96" width="14" height="30" fill="#00d26a"/>
            <rect x="82" y="48" width="16" height="62" fill="#00d26a"/>
            <rect x="112" y="28" width="14" height="36" fill="#00d26a"/>
            <polyline points="126,35 178,76 238,52 320,18" fill="none" stroke="#00e5ff" stroke-width="2"/>
            <circle cx="178" cy="76" r="4" fill="#ffb000"/>
          </svg>`)
        ),
        h('div', { class: 'xcard' },
          h('div', { class: 'xsec-hd' }, h('span', { text: '4. LIQUIDATION SWEEP & VPIN SHIELD' }), h('span', { class: 'dn', text: 'MICROSTRUCTURE' })),
          makeSvgBox(`<svg viewBox="0 0 360 155" style="width:100%;height:auto;background:#040608;display:block">
            <rect x="20" y="98" width="320" height="22" fill="rgba(255,59,48,0.16)" stroke="#ff5a52" stroke-dasharray="3,2"/>
            <text x="26" y="112" fill="#ff5a52" font-size="8.5" font-weight="700" font-family="monospace">STOP-LOSS LIQUIDATION POOL (SHIELDED BELOW)</text>
            <line x1="20" y1="134" x2="340" y2="134" stroke="#00d26a" stroke-width="1.3"/>
            <text x="26" y="146" fill="#00d26a" font-size="8.5" font-family="monospace">PROTECTED STOP-LOSS LEVEL</text>
            <polyline points="24,62 96,76 146,116 184,72 254,48 332,26" fill="none" stroke="#fff" stroke-width="2"/>
            <circle cx="146" cy="116" r="4" fill="#ff5a52"/>
            <text x="154" y="120" fill="#ffb000" font-size="8.5" font-family="monospace">LIQUIDITY SWEEP</text>
          </svg>`)
        )
      );
      sc.append(diagGrid);

      const env = await get('kline', { symbol: ctx.symbol, interval: iv, limit: 80 }, 4000);
      if (unmounted) return;
      ctx.status(env);
      const arr = env.ok && Array.isArray(env.data) ? env.data : (env.data && env.data.candles) || [];
      if (arr.length >= 20) {
        const highs = arr.map(c => Number(c.h ?? c.high));
        const lows = arr.map(c => Number(c.l ?? c.low));
        const closes = arr.map(c => Number(c.c ?? c.close));
        const swingHi = Math.max(...highs.slice(-30));
        const swingLo = Math.min(...lows.slice(-30));
        const lastC = closes[closes.length - 1];
        const prev20Hi = Math.max(...highs.slice(-22, -2));
        const prev20Lo = Math.min(...lows.slice(-22, -2));
        const fib618 = swingHi - (swingHi - swingLo) * 0.618;
        let fvgTxt = 'No fresh FVG imbalance within last 5 bars';
        for (let i = arr.length - 1; i >= Math.max(2, arr.length - 6); i--) {
          if (lows[i] > highs[i - 2]) { fvgTxt = `BULLISH FVG ($${fmtPx(highs[i - 2])} - $${fmtPx(lows[i])})`; break; }
          if (highs[i] < lows[i - 2]) { fvgTxt = `BEARISH FVG ($${fmtPx(highs[i])} - $${fmtPx(lows[i - 2])})`; break; }
        }
        const struct = lastC > prev20Hi ? 'BULLISH BREAK OF STRUCTURE (BOS UP)' : lastC < prev20Lo ? 'BEARISH BREAK OF STRUCTURE (BOS DOWN)' : 'RANGE CONSOLIDATION';
        detBody.textContent = '';
        detBody.append(
          h('div', { style: 'margin-bottom:4px' }, h('b', { style: 'color:var(--amber)', text: 'Price Structure: ' }), struct),
          h('div', { style: 'margin-bottom:4px' }, h('b', { style: 'color:#00e5ff', text: '30-Bar Range: ' }), `Low $${fmtPx(swingLo)}  -  High $${fmtPx(swingHi)}  |  Golden Pocket 0.618: $${fmtPx(fib618)}`),
          h('div', {}, h('b', { style: 'color:#00d26a', text: 'Fair Value Gap (FVG): ' }), fvgTxt)
        );
      } else {
        detBody.textContent = 'Insufficient OHLCV history for automated pattern scan.';
      }
    }
  }

  function openImagePreview(snap) {
    const ov = h('div', {
      style: 'position:fixed;inset:0;z-index:99995;background:rgba(0,0,0,0.92);display:flex;flex-direction:column;align-items:center;justify-content:center;padding:16px',
      onclick: () => ov.remove()
    },
      h('div', { style: 'color:var(--amber);font-weight:700;margin-bottom:8px', text: `${snap.symbol} [${snap.interval}] | ${fmtTime(snap.ts, true)} (Click anywhere to close)` }),
      h('img', { src: snap.dataUrl, style: 'max-width:95vw;max-height:84vh;border:1px solid var(--amber)' })
    );
    document.body.appendChild(ov);
  }

  renderToolbar();
  renderBody();
  ctx.cleanup(() => { unmounted = true; });
}

// =====================================================================
// 4. BI / RES — BLOOMBERG INTELLIGENCE RESEARCH DOSSIER
// =====================================================================
export function mountBI(body, ctx) {
  body.classList.add('fill');
  const tb = h('div', { class: 'tb' });
  const sc = h('div', { class: 'pb' });
  body.append(tb, sc);

  let sym = ctx.symbol || 'BTCUSDT';
  let dossier = null;
  let unmounted = false;

  async function load(target = sym) {
    sym = String(target || 'BTCUSDT').trim().toUpperCase();
    const env = await get('intelligence', { symbol: sym }, 5000);
    if (unmounted) return;
    ctx.status(env);
    if (!env.ok || !env.data) {
      sc.textContent = '';
      sc.append(h('div', { class: 'na', text: 'Bloomberg Intelligence unavailable: ' + (env.error || 'error') }));
      return;
    }
    dossier = env.data;
    renderToolbar();
    renderBody();
  }

  function exportHtmlReport() {
    if (!dossier) return;
    const d = dossier;
    const q = d.quote || {};
    const html = `<!doctype html><html><head><meta charset="utf-8"><title>Bloomberg Terminal Intelligence — ${esc(d.symbol)}</title>
    <style>body{font-family:Arial,sans-serif;background:#0a0c10;color:#e6edf3;padding:28px;max-width:900px;margin:0 auto}h1{color:#ff6600;border-bottom:2px solid #ff6600;padding-bottom:8px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}.box{border:1px solid #2b3240;background:#11151d;padding:12px}ul{margin:6px 0;padding-left:18px}.up{color:#00d26a}.dn{color:#ff5a52}</style></head><body>
    <h1>BLOOMBERG TERMINAL INTELLIGENCE // ${esc(d.symbol)} — ${esc(d.name)}</h1>
    <p><b>Asset Class:</b> ${esc(d.assetClass)} &nbsp;|&nbsp; <b>Rating:</b> ${esc(d.rating)} &nbsp;|&nbsp; <b>Price:</b> $${esc(fmtPx(q.price))} (${esc(fmtPct(q.chgPct))}) &nbsp;|&nbsp; <b>Generated:</b> ${new Date().toISOString()}</p>
    <div class="grid">
      <div class="box"><h3 class="up">BULL CASE CONVICTION</h3><ul>${(d.bullPoints || []).map(x => `<li>${esc(x)}</li>`).join('')}</ul></div>
      <div class="box"><h3 class="dn">BEAR CASE &amp; TAIL RISKS</h3><ul>${(d.bearPoints || []).map(x => `<li>${esc(x)}</li>`).join('')}</ul></div>
    </div>
    <div class="box" style="margin-top:14px"><h3>RECENT MARKET CATALYSTS</h3><ul>${(d.catalysts || []).map(c => `<li><b>${esc(c.source || 'WIRE')}:</b> ${esc(c.title)}</li>`).join('')}</ul></div>
    </body></html>`;
    downloadBlob(`Bloomberg_Terminal_BI_${d.symbol}_${new Date().toISOString().slice(0, 10)}.html`, html, 'text/html;charset=utf-8');
  }

  function renderToolbar() {
    tb.textContent = '';
    const inp = h('input', { value: sym, style: 'width:90px;text-transform:uppercase;font-weight:700' });
    inp.addEventListener('keydown', e => { if (e.key === 'Enter') load(inp.value); });
    tb.append(
      h('span', { class: 'lbl', text: 'BLOOMBERG INTELLIGENCE (BI):' }),
      inp,
      h('button', { class: 'on', text: 'RESEARCH <GO>', onclick: () => load(inp.value) }),
      h('button', { style: 'color:#00d26a;border-color:#00d26a66', text: 'EXPORT REPORT (HTML)', onclick: exportHtmlReport }),
      h('button', { text: 'X-RAY', onclick: () => ctx.run(`${sym} FACT`) }),
      h('button', { text: 'REFRESH', onclick: () => load(sym) })
    );
  }

  function renderBody() {
    sc.textContent = '';
    if (!dossier) return;
    const d = dossier;
    const q = d.quote || {};
    const qs = d.quantSnapshot || {};
    const rCls = /OUTPERFORM|CONSTRUCTIVE/i.test(d.rating) ? 'ok' : /UNDERPERFORM|CAUTIOUS/i.test(d.rating) ? 'no' : 'warn';

    sc.append(h('div', { class: 'xcard xcard-hi' },
      h('div', { style: 'display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px' },
        h('div', {},
          h('div', { style: 'color:var(--amber);font-size:14px;font-weight:700', text: `${d.symbol} — ${d.name}` }),
          h('div', { style: 'color:var(--label);font-size:10.5px', text: `${d.assetClass}  |  Last: $${fmtPx(q.price)} (${fmtPct(q.chgPct)})  |  Vol: ${fmtVol(q.vol)}` })
        ),
        h('span', { class: `xpill ${rCls}`, style: 'font-size:11px;padding:3px 8px', text: d.rating })
      )
    ));

    sc.append(h('div', { class: 'xgrid4', style: 'margin-bottom:8px' },
      h('div', { class: 'xstat' }, h('div', { class: 'xl', text: 'QUANT P_MATH' }), h('div', { class: 'xv', text: qs.pMath != null ? `${Number(qs.pMath).toFixed(1)}%` : 'N/A' }), h('div', { class: 'xs', text: `Regime: ${qs.regime || '-'}` })),
      h('div', { class: 'xstat' }, h('div', { class: 'xl', text: 'ADX-14 / HURST' }), h('div', { class: 'xv', text: `${qs.adx14 != null ? Number(qs.adx14).toFixed(1) : '-'} / ${qs.hurst != null ? Number(qs.hurst).toFixed(2) : '-'}` }), h('div', { class: 'xs', text: `OBI-20: ${qs.obi20 != null ? Number(qs.obi20).toFixed(3) : '-'}` })),
      h('div', { class: 'xstat' }, h('div', { class: 'xl', text: 'OPTIONS DVOL' }), h('div', { class: 'xv', text: qs.dvol != null ? String(qs.dvol) : 'N/A' }), h('div', { class: 'xs', text: `Hybrid: ${qs.hybridConf != null ? qs.hybridConf + '%' : '-'}` })),
      h('div', { class: 'xstat' }, h('div', { class: 'xl', text: 'SIGNAL BIAS' }), h('div', { class: 'xv', style: 'font-size:12px;color:#00e5ff', text: qs.setup || 'MONITORING' }), h('div', { class: 'xs', text: `Direction: ${qs.direction || 'NEUTRAL'}` }))
    ));

    sc.append(h('div', { class: 'xgrid2', style: 'margin-bottom:8px' },
      h('div', { class: 'xcard', style: 'margin-bottom:0;border-left:3px solid var(--up)' },
        h('div', { class: 'xsec-hd' }, h('span', { style: 'color:var(--up)', text: 'BULL CASE / UPSIDE THESIS' })),
        h('div', { style: 'padding:8px;font-size:11px;line-height:1.55' }, ...(d.bullPoints || []).map(p => h('div', { style: 'margin-bottom:5px', text: '- ' + p })))
      ),
      h('div', { class: 'xcard', style: 'margin-bottom:0;border-left:3px solid var(--dn)' },
        h('div', { class: 'xsec-hd' }, h('span', { style: 'color:var(--dn)', text: 'BEAR CASE / RISK FACTORS' })),
        h('div', { style: 'padding:8px;font-size:11px;line-height:1.55' }, ...(d.bearPoints || []).map(p => h('div', { style: 'margin-bottom:5px', text: '- ' + p })))
      )
    ));

    const catCard = h('div', { class: 'xcard' },
      h('div', { class: 'xsec-hd' }, h('span', { text: 'KEY CATALYSTS & NEWS WIRE' }), h('span', { class: 'am', text: `${(d.catalysts || []).length} DISPATCHES` }))
    );
    (d.catalysts || []).forEach(c => {
      catCard.append(h('div', { style: 'padding:5px 7px;border-bottom:1px solid #161b24;font-size:11px' },
        h('span', { class: 'am', text: `[${c.source || 'WIRE'}] ` }),
        c.link ? h('a', { href: c.link, target: '_blank', rel: 'noopener', style: 'color:#e6edf3;text-decoration:none', text: c.title }) : c.title
      ));
    });
    sc.append(catCard);
  }

  renderToolbar();
  load(sym);
  ctx.cleanup(() => { unmounted = true; });
}

// =====================================================================
// 5. ETF / FLOW / INS / SI — INSTITUTIONAL FLOWS & INSIDERS
// =====================================================================
export function mountETF(body, ctx) {
  body.classList.add('fill');
  const tb = h('div', { class: 'tb' });
  const sc = h('div', { class: 'pb' });
  body.append(tb, sc);

  let insSym = (ctx.symbol && !/USDT|\.P/i.test(ctx.symbol)) ? ctx.symbol : 'NVDA';
  let payload = null;
  let unmounted = false;

  async function load(target = insSym) {
    insSym = String(target || 'NVDA').trim().toUpperCase();
    const env = await get('flows', { symbol: insSym }, 6000);
    if (unmounted) return;
    ctx.status(env);
    if (!env.ok || !env.data) {
      sc.textContent = '';
      sc.append(h('div', { class: 'na', text: 'Institutional flows unavailable: ' + (env.error || 'error') }));
      return;
    }
    payload = env.data;
    renderToolbar();
    renderBody();
  }

  function renderToolbar() {
    tb.textContent = '';
    const inp = h('input', { value: insSym, style: 'width:80px;text-transform:uppercase', placeholder: 'NVDA' });
    inp.addEventListener('keydown', e => { if (e.key === 'Enter') load(inp.value); });
    tb.append(
      h('span', { class: 'lbl', text: 'INSTITUTIONAL ETF FLOWS & SQUEEZE BOARD:' }),
      h('span', { class: 'lbl', text: 'SEC INSIDER:' }),
      inp,
      h('button', { class: 'on', text: 'LOAD <GO>', onclick: () => load(inp.value) }),
      h('button', { text: 'REFRESH', onclick: () => load(insSym) })
    );
  }

  function renderBody() {
    sc.textContent = '';
    if (!payload) return;
    const etfs = payload.etfs || [];
    const sq = payload.squeezeBoard || [];
    const ins = payload.insiderFilings || [];

    sc.append(h('div', { class: 'xcard' },
      h('div', { class: 'xsec-hd' },
        h('span', { text: 'SPOT CRYPTO & MACRO ETF SIGNED FLOW PROXY (IBIT, FBTC, GBTC, ETHA, SPY, QQQ, TLT, GLD, EIDO)' }),
        h('span', { class: 'up', text: 'LIVE QUOTES' })
      ),
      makeSvgBox(buildEtfFlowSvg(etfs))
    ));

    const etfTbl = h('table', { class: 't', style: 'margin-bottom:10px' },
      h('thead', {}, h('tr', {},
        h('th', { text: 'ETF' }),
        h('th', { text: 'FUND NAME' }),
        h('th', { text: 'GROUP' }),
        h('th', { class: 'r', text: 'PRICE' }),
        h('th', { class: 'r', text: 'CHG %' }),
        h('th', { class: 'r', text: '$ VOL' }),
        h('th', { class: 'r', text: 'EST FLOW' })
      ))
    );
    const etfB = h('tbody');
    etfs.forEach(e => {
      etfB.append(h('tr', { style: 'cursor:pointer', onclick: () => ctx.run(`${e.symbol} GP`) },
        h('td', { class: 'am', style: 'font-weight:700', text: e.symbol }),
        h('td', { style: 'color:#e6edf3', text: e.name }),
        h('td', { style: 'color:var(--label)', text: e.group }),
        h('td', { class: 'r', text: '$' + fmtPx(e.price) }),
        h('td', { class: 'r ' + dirCls(e.chgPct), text: fmtPct(e.chgPct) }),
        h('td', { class: 'r', text: fmtUsdShort(e.dollarVol) }),
        h('td', { class: 'r ' + dirCls(e.signedFlowEstUsd), style: 'font-weight:700', text: fmtUsdShort(e.signedFlowEstUsd) })
      ));
    });
    etfTbl.append(etfB);
    sc.append(etfTbl);

    sc.append(h('div', { class: 'xsec-hd', style: 'margin-bottom:4px' },
      h('span', { text: 'BINANCE FUTURES SHORT SQUEEZE & CROWDING PRESSURE BOARD' }),
      h('span', { class: 'am', text: `${sq.length} PERPS` })
    ));
    const sqTbl = h('table', { class: 't', style: 'margin-bottom:10px' },
      h('thead', {}, h('tr', {},
        h('th', { text: 'CONTRACT' }),
        h('th', { class: 'r', text: 'MARK' }),
        h('th', { class: 'r', text: 'FUNDING %' }),
        h('th', { class: 'r', text: 'ANN %' }),
        h('th', { text: 'PRESSURE' }),
        h('th', { text: 'CROWDING BIAS' })
      ))
    );
    const sqB = h('tbody');
    sq.forEach(r => {
      const col = r.pressureScore >= 65 ? 'var(--dn)' : r.pressureScore >= 35 ? 'var(--amber)' : 'var(--up)';
      sqB.append(h('tr', { style: 'cursor:pointer', onclick: () => ctx.run(`${r.symbol} FACT`) },
        h('td', { class: 'am', style: 'font-weight:700', text: r.symbol }),
        h('td', { class: 'r', text: '$' + fmtPx(r.markPrice) }),
        h('td', { class: 'r ' + dirCls(-r.fundingPct), text: `${r.fundingPct >= 0 ? '+' : ''}${r.fundingPct}%` }),
        h('td', { class: 'r', text: `${r.annualizedPct}%` }),
        h('td', { style: 'min-width:90px' }, h('div', { class: 'xbar-track' }, h('div', { class: 'xbar-fill', style: `width:${r.pressureScore}%;background:${col}` }))),
        h('td', { style: 'font-size:10px', text: r.squeezeBias })
      ));
    });
    sqTbl.append(sqB);
    sc.append(sqTbl);

    sc.append(h('div', { class: 'xsec-hd', style: 'margin-bottom:4px' },
      h('span', { text: `SEC FORM-4 & REGULATORY INSIDER FILINGS (${payload.insiderSymbol})` }),
      h('span', { class: 'am', text: `${ins.length} FILINGS` })
    ));
    if (ins.length) {
      const iTbl = h('table', { class: 't' },
        h('thead', {}, h('tr', {}, h('th', { text: 'FORM' }), h('th', { text: 'FILED DATE' }), h('th', { text: 'DOCUMENT / ACCESS' })))
      );
      const ib = h('tbody');
      ins.forEach(f => ib.append(h('tr', {},
        h('td', { class: 'am', text: f.form || '-' }),
        h('td', { text: f.date || '-' }),
        h('td', {}, f.url ? h('a', { href: f.url, target: '_blank', rel: 'noopener', style: 'color:var(--label)', text: f.desc || f.accession || 'View EDGAR Filing' }) : (f.desc || '-'))
      )));
      iTbl.append(ib);
      sc.append(iTbl);
    } else {
      sc.append(h('div', { class: 'na', text: 'Enter a US equity ticker (e.g. NVDA, AAPL, MSFT) in the toolbar to inspect SEC Form-4 filings.' }));
    }
  }

  renderToolbar();
  load(insSym);
  ctx.cleanup(() => { unmounted = true; });
}

// =====================================================================
// 6. FIN / BUDGET / CASH / BUFFETT — PERSONAL CAPITAL MANAGER (WARREN BUFFETT)
// =====================================================================
export function mountFIN(body, ctx) {
  body.classList.add('fill');
  const tb = h('div', { class: 'tb' });
  const sc = h('div', { class: 'pb' });
  body.append(tb, sc);

  let tab = 'DASH';
  let finData = null;
  let historyFilter = 'ALL';
  let statusNote = '';
  let unmounted = false;

  async function load() {
    try {
      const r = await apiFetch('/api/finance', { cache: 'no-store' }, 10000);
      if (unmounted) return;
      if (!r.ok) {
        ctx.status({ ok: false, source: 'capital-desk', ts: Date.now(), mode: 'NA' });
        sc.textContent = '';
        sc.append(h('div', { class: 'na', text: `Authentication required to access Personal Capital Desk (HTTP ${r.status}).` }));
        return;
      }
      const j = await r.json();
      finData = j.data;
      ctx.status({ ok: true, source: 'capital-desk', ts: Date.now(), mode: 'LIVE' });
      renderToolbar();
      renderBody();
    } catch (e) {
      if (!unmounted) {
        sc.textContent = '';
        sc.append(h('div', { class: 'na', text: 'Capital Desk error: ' + e.message }));
      }
    }
  }

  function exportCsv() {
    if (!finData) return;
    const rows = [['ID', 'Date', 'Type', 'Category', 'Amount_IDR', 'Note']];
    (finData.transactions || []).forEach(t => {
      rows.push([t.id, t.date, t.type, t.category, t.amountIdr, String(t.note || '').replace(/[\r\n,]+/g, ' ')]);
    });
    downloadBlob(`Bloomberg_Terminal_Capital_${new Date().toISOString().slice(0, 10)}.csv`, rows.map(r => r.join(',')).join('\n'), 'text/csv;charset=utf-8');
  }

  async function applyBuffett(monthlyIncomeIdr, recordMonthlyCycle = false) {
    const r = await apiFetch('/api/finance/buffett-apply', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ monthlyIncomeIdr: Number(monthlyIncomeIdr || 1000000), recordMonthlyCycle })
    }, 10000);
    const j = await r.json();
    if (r.ok && j.ok) {
      finData = j.data;
      statusNote = recordMonthlyCycle
        ? `WARREN BUFFETT CYCLE BOOKED: Income ${fmtIdr(j.plan.monthlyIncomeIdr)} recorded & ${fmtIdr(j.plan.payYourselfFirstIdr)} (40%) locked first. Daily ceiling: ${fmtIdr(j.plan.dailyLimitIdr)}/day.`
        : `WARREN BUFFETT ALLOCATION APPLIED (${fmtIdr(j.plan.monthlyIncomeIdr)}/month): 40% Pay-Yourself-First (${fmtIdr(j.plan.payYourselfFirstIdr)}) | 60% Operating (${fmtIdr(j.plan.spendableMonthlyIdr)}, ${fmtIdr(j.plan.dailyLimitIdr)}/day).`;
      renderBody();
    } else {
      statusNote = 'Allocation error: ' + (j.error || 'failed');
      renderBody();
    }
  }

  function renderToolbar() {
    tb.textContent = '';
    tb.append(
      h('span', { class: 'lbl', text: 'PERSONAL CAPITAL (WARREN BUFFETT):' }),
      h('button', { class: tab === 'DASH' ? 'on' : '', text: 'DASHBOARD & ENTRY', onclick: () => { tab = 'DASH'; renderToolbar(); renderBody(); } }),
      h('button', { class: tab === 'BUFFETT' ? 'on' : '', text: 'WARREN BUFFETT AUTO-PLAN', onclick: () => { tab = 'BUFFETT'; renderToolbar(); renderBody(); } }),
      h('button', { class: tab === 'BUDGET' ? 'on' : '', text: 'GOALS & LIMITS', onclick: () => { tab = 'BUDGET'; renderToolbar(); renderBody(); } }),
      h('button', { class: tab === 'HIST' ? 'on' : '', text: 'LEDGER & CSV', onclick: () => { tab = 'HIST'; renderToolbar(); renderBody(); } }),
      h('button', { style: 'color:#00d26a;border-color:#00d26a66', text: 'EXPORT CSV', onclick: exportCsv }),
      h('button', { text: 'REFRESH', onclick: load })
    );
  }

  function renderBody() {
    sc.textContent = '';
    if (!finData) return;
    const s = finData.summary || {};
    const wb = s.buffettPlan || {};
    const botSync = s.botSync || {};

    const isOver = s.borosStatus === 'BOROS_OVER_BUDGET';
    const isWarn = s.borosStatus === 'WASPADA_HAMPIR_LIMIT';
    const bannerCol = isOver ? '#ff453a' : isWarn ? '#ffb000' : '#00d26a';
    const bannerTxt = isOver
      ? 'CAPITAL DISCIPLINE ALERT: DAILY OR MONTHLY OPERATING CEILING EXCEEDED'
      : isWarn
      ? 'CAPITAL CAUTION: OPERATING UTILIZATION ABOVE 75% — MONITOR REMAINING ALLOWANCE'
      : 'CAPITAL DISCIPLINE: ON TRACK UNDER WARREN BUFFETT PAY-YOURSELF-FIRST FRAMEWORK';

    sc.append(h('div', {
      class: 'xcard',
      style: `border-color:${bannerCol};border-left:5px solid ${bannerCol};background:${isOver ? '#1c0505' : isWarn ? '#1a1203' : '#03190d'}`
    },
      h('div', { style: 'display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:6px' },
        h('b', { style: `color:${bannerCol};font-size:11.5px`, text: bannerTxt }),
        h('span', { class: `xpill ${isOver ? 'no' : isWarn ? 'warn' : 'ok'}`, text: `DISCIPLINE INDEX: ${s.disciplineScore || 100}/100` })
      ),
      statusNote ? h('div', { style: 'margin-top:4px;color:#00e5ff;font-size:11px', text: statusNote }) : null
    ));

    sc.append(h('div', { class: 'xgrid4', style: 'margin-bottom:8px' },
      h('div', { class: 'xstat' },
        h('div', { class: 'xl', text: 'DAILY ALLOWANCE REMAINING' }),
        h('div', { class: 'xv', style: `color:${(s.remainingTodayIdr || 0) >= 0 ? 'var(--up)' : 'var(--dn)'}`, text: fmtIdr(s.remainingTodayIdr) }),
        h('div', { class: 'xs', text: `Spent: ${fmtIdr(s.todayExpense)} / ${fmtIdr(s.dailyLimitIdr)} (${s.dailyUsedPct || 0}%)` })
      ),
      h('div', { class: 'xstat' },
        h('div', { class: 'xl', text: 'DYNAMIC SAFE DAILY SPEND' }),
        h('div', { class: 'xv', style: 'color:#00e5ff', text: fmtIdr(s.dynamicSafeDailyIdr) }),
        h('div', { class: 'xs', text: `Remaining Pool ${fmtIdr(s.remainingMonthIdr)} / ${s.remainingDays || 1} days` })
      ),
      h('div', { class: 'xstat' },
        h('div', { class: 'xl', text: 'MONTHLY OPERATING BUDGET (60%)' }),
        h('div', { class: 'xv', style: 'color:var(--amber)', text: `${fmtIdr(s.monthExpense)} / ${fmtIdr(s.monthlyBudgetIdr)}` }),
        h('div', { class: 'xs', text: `Fixed Income: ${fmtIdr(s.monthlyIncomeTarget)} | Saved: ${fmtIdr(s.monthSavings)}` })
      ),
      h('div', { class: 'xstat' },
        h('div', { class: 'xl', text: 'TOTAL INTEGRATED NET WORTH' }),
        h('div', { class: 'xv', style: 'color:#00d26a', text: fmtIdr(s.totalIntegratedWealthIdr ?? ((s.bankTotalIdr || 0) + (botSync.walletIdr || 0))) }),
        h('div', { class: 'xs', text: `Bank ${fmtIdr(s.bankTotalIdr || 0)} + Futures $${Number(botSync.walletUsd || 0).toFixed(2)} (FX ${fmtIdr(botSync.fxRateIdr || 18218)})` })
      )
    ));

    // Integrated Wealth Milestones Roadmap (Rp 10M -> Rp 100M -> Rp 1B)
    const milestones = s.milestones || [];
    if (milestones.length && (tab === 'DASH' || tab === 'BUDGET')) {
      const mCard = h('div', { class: 'xcard', style: 'border-color:#ff6600' },
        h('div', { class: 'xsec-hd' },
          h('span', { style: 'color:#ff6600', text: 'INTEGRATED WEALTH MILESTONES (BANK + RESERVES + LIVE BINANCE FUTURES)' }),
          h('span', { class: 'up', text: `NET WORTH: ${fmtIdr(s.totalIntegratedWealthIdr || 0)}` })
        )
      );
      const mGrid = h('div', { class: 'xgrid3', style: 'padding:6px 2px' });
      milestones.forEach(ms => {
        mGrid.append(h('div', { style: `padding:7px 8px;border:1px solid #1e2530;border-left:3px solid ${ms.color};background:#05070a` },
          h('div', { style: 'display:flex;justify-content:space-between;align-items:center;margin-bottom:3px' },
            h('span', { style: `color:${ms.color};font-size:10px;font-weight:700`, text: `${ms.tier} | ${ms.shortLabel.toUpperCase()}` }),
            h('span', { class: `xpill ${ms.achieved ? 'ok' : 'info'}`, text: ms.achieved ? 'ACHIEVED' : `${ms.progressPct}%` })
          ),
          h('div', { style: 'font-size:12px;font-weight:700;color:#fff;margin-bottom:4px', text: `${fmtIdr(ms.currentIdr)} / ${fmtIdr(ms.targetIdr)}` }),
          h('div', { class: 'xbar-track', style: 'margin-bottom:4px' },
            h('div', { class: 'xbar-fill', style: `width:${Math.max(1, Math.min(100, ms.progressPct))}%;background:${ms.color}` })
          ),
          h('div', { style: 'display:flex;justify-content:space-between;font-size:9.5px;color:var(--muted)' },
            h('span', { text: `Rem: ${fmtIdr(ms.remainingIdr)}` }),
            h('span', { text: `Est (12% p.a.): ${ms.etaLabel}` })
          )
        ));
      });
      mCard.append(mGrid);
      sc.append(mCard);
    }

    if (tab === 'DASH') {
      // Compact Warren Buffett Auto-Allocation Bar
      const buckets = wb.buckets || [];
      if (buckets.length) {
        const segBar = h('div', { style: 'display:flex;height:14px;width:100%;overflow:hidden;border:1px solid #262e3d;margin:6px 0' });
        buckets.forEach(b => {
          segBar.append(h('div', {
            style: `width:${b.pct}%;background:${b.color};height:100%`,
            title: `${b.name}: ${b.pct}% (${fmtIdr(b.amountIdr)})`
          }));
        });
        const leg = h('div', { style: 'display:flex;gap:10px;flex-wrap:wrap;font-size:10px;color:#cfd8e3' });
        buckets.forEach(b => {
          leg.append(h('span', {},
            h('span', { style: `display:inline-block;width:8px;height:8px;background:${b.color};margin-right:4px` }),
            `${b.name}: `,
            h('b', { style: 'color:#fff', text: `${b.pct}% (${fmtIdr(b.amountIdr)})` })
          ));
        });
        sc.append(h('div', { class: 'xcard xcard-hi' },
          h('div', { class: 'xsec-hd' },
            h('span', { text: `WARREN BUFFETT AUTO-ALLOCATION — FIXED MONTHLY INCOME ${fmtIdr(wb.monthlyIncomeIdr)}` }),
            h('div', { style: 'display:flex;gap:5px' },
              h('button', { class: 'on', style: 'font-size:10px', text: 'BOOK MONTHLY INCOME + LOCK 40%', onclick: () => applyBuffett(wb.monthlyIncomeIdr, true) }),
              h('button', { style: 'font-size:10px', text: 'FULL BUFFETT PLAN ->', onclick: () => { tab = 'BUFFETT'; renderToolbar(); renderBody(); } })
            )
          ),
          h('div', { style: 'padding:4px 4px 2px' }, segBar, leg)
        ));
      }

      // Quick Transaction Form + Discipline Gauge
      const typeSel = h('select', { style: 'width:100%' },
        h('option', { value: 'EXPENSE', text: 'EXPENSE (OPERATING OUTFLOW)' }),
        h('option', { value: 'INCOME', text: 'INCOME (ALLOWANCE / INFLOW)' }),
        h('option', { value: 'SAVINGS', text: 'SAVINGS / INVESTMENT LOCK' })
      );
      const expenseCats = Object.keys(finData.categoryLimits || {});
      const catSel = h('select', { style: 'width:100%' });
      const goalSel = h('select', { style: 'width:100%;display:none' },
        h('option', { value: '', text: '-- Optional Goal Attribution --' }),
        ...(finData.goals || []).map(g => h('option', { value: g.id, text: `${g.name} (${fmtIdr(g.savedIdr)} / ${fmtIdr(g.targetIdr)})` }))
      );

      const syncCats = () => {
        catSel.textContent = '';
        const t = typeSel.value;
        goalSel.style.display = t === 'SAVINGS' ? 'block' : 'none';
        const opts = t === 'INCOME'
          ? ['Monthly Fixed Allowance', 'Trading Realized Profit', 'Additional Income']
          : t === 'SAVINGS'
          ? ['Productive Investment Capital', 'Emergency Margin of Safety']
          : (expenseCats.length ? expenseCats : ['Food & Refreshments', 'Transportation']);
        opts.forEach(c => catSel.append(h('option', { value: c, text: c })));
      };
      typeSel.addEventListener('change', syncCats);
      syncCats();

      const amtInp = h('input', { type: 'number', min: '500', step: '500', placeholder: 'Amount in IDR (e.g. 15000)', style: 'width:100%;font-weight:700;font-size:13px' });
      const noteInp = h('input', { placeholder: 'Description (e.g. Lunch, Fuel, Commute)', style: 'width:100%' });
      const quickChips = h('div', { style: 'display:flex;gap:4px;flex-wrap:wrap;margin:4px 0' },
        ...[5000, 10000, 15000, 20000, 50000].map(v => h('button', {
          type: 'button',
          style: 'font-size:10px',
          text: `+${v / 1000}k`,
          onclick: () => { amtInp.value = String((Number(amtInp.value) || 0) + v); }
        }))
      );

      const submitTx = async () => {
        const amountIdr = Math.round(Number(amtInp.value));
        if (!amountIdr || amountIdr <= 0) { statusNote = 'Enter a valid IDR amount.'; renderBody(); return; }
        const r = await apiFetch('/api/finance/tx', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            type: typeSel.value,
            category: catSel.value,
            amountIdr,
            note: noteInp.value.trim(),
            goalId: typeSel.value === 'SAVINGS' ? goalSel.value : ''
          })
        }, 10000);
        const j = await r.json();
        if (r.ok && j.ok) {
          finData = j.data;
          statusNote = `RECORDED: ${typeSel.value} ${fmtIdr(amountIdr)} (${catSel.value})`;
          renderBody();
        } else {
          statusNote = 'Transaction failed: ' + (j.error || 'error');
          renderBody();
        }
      };

      const formCard = h('div', { class: 'xcard', style: 'margin-bottom:0' },
        h('div', { class: 'xsec-hd' }, h('span', { text: 'RECORD TRANSACTION' }), h('span', { class: 'am', text: s.todayStr || '' })),
        h('div', { style: 'padding:6px;display:flex;flex-direction:column;gap:6px' },
          typeSel,
          catSel,
          goalSel,
          amtInp,
          quickChips,
          noteInp,
          h('button', { class: 'on', style: 'padding:7px;font-weight:700;background:#ff6600;color:#000;border-color:#ff6600', text: 'POST TRANSACTION <GO>', onclick: submitTx })
        )
      );

      const gaugeCard = h('div', { class: 'xcard', style: 'margin-bottom:0' },
        h('div', { class: 'xsec-hd' }, h('span', { text: 'CAPITAL DISCIPLINE INDEX' }), h('span', { class: 'up', text: `SAVING RATE ${s.savingsRatePct || 0}%` })),
        makeSvgBox(buildGaugeSvg(s.disciplineScore || 100, s.statusLabel || 'DISCIPLINED', bannerCol)),
        h('div', { style: 'padding:4px 8px;font-size:10.5px;line-height:1.5;color:#cfd8e3' },
          h('div', { text: `- Daily Operating Ceiling: ${fmtIdr(s.dailyLimitIdr)} (Food ~${fmtIdr(wb.foodDailyIdr || 15000)} + Transport ~${fmtIdr(wb.transportDailyIdr || 5000)})` }),
          h('div', { text: `- Pay-Yourself-First Target: ${fmtIdr(wb.payYourselfFirstIdr || 400000)}/month (40% locked first)` }),
          h('div', { text: `- Synced Futures Desk: Wallet $${Number(botSync.walletUsd || 0).toFixed(2)} | Vault $${Number(botSync.vaultUsd || 0).toFixed(2)}` })
        )
      );

      sc.append(h('div', { class: 'xgrid2', style: 'margin-bottom:8px' }, formCard, gaugeCard));

      sc.append(h('div', { class: 'xcard' },
        h('div', { class: 'xsec-hd' },
          h('span', { text: '14-DAY CASHFLOW MONITOR (GREEN = INFLOW | ORANGE/RED = EXPENSE VS DAILY CEILING)' }),
          h('span', { class: 'am', text: 'DAILY TRACKER' })
        ),
        makeSvgBox(buildCashflow14dSvg(s.dailyTrend14d, s.dailyLimitIdr))
      ));

      const envCard = h('div', { class: 'xcard' },
        h('div', { class: 'xsec-hd' },
          h('span', { text: 'MONTHLY OPERATING ENVELOPES (FOOD & TRANSPORTATION)' }),
          h('button', { style: 'font-size:10px', text: 'CONFIGURE LIMITS ->', onclick: () => { tab = 'BUDGET'; renderToolbar(); renderBody(); } })
        )
      );
      const envGrid = h('div', { class: 'xgrid2', style: 'padding:6px 2px' });
      const allCats = new Set([...Object.keys(s.categoryLimits || {}), ...Object.keys(s.byCategory || {})]);
      allCats.forEach(cat => {
        const spent = Number((s.byCategory && s.byCategory[cat]) || 0);
        const lim = Number((s.categoryLimits && s.categoryLimits[cat]) || 0);
        const pct = lim > 0 ? Math.min(130, (spent / lim) * 100) : (spent > 0 ? 100 : 0);
        const col = pct > 100 ? 'var(--dn)' : pct >= 75 ? 'var(--amber)' : 'var(--up)';
        envGrid.append(h('div', { style: 'padding:6px 8px;border:1px solid #181d26;background:#05070a' },
          h('div', { style: 'display:flex;justify-content:space-between;font-size:10.5px;margin-bottom:3px' },
            h('b', { style: 'color:#e6edf3', text: cat }),
            h('span', { style: `color:${col};font-weight:700`, text: `${fmtIdr(spent)} / ${lim > 0 ? fmtIdr(lim) : 'Unallocated'}` })
          ),
          h('div', { class: 'xbar-track' }, h('div', { class: 'xbar-fill', style: `width:${Math.min(100, pct)}%;background:${col}` }))
        ));
      });
      envCard.append(envGrid);
      sc.append(envCard);

    } else if (tab === 'BUFFETT') {
      const incInp = h('input', { type: 'number', value: String(wb.monthlyIncomeIdr || 1000000), min: '100000', step: '50000', style: 'width:170px;font-weight:700;font-size:13px' });
      sc.append(h('div', { class: 'xcard xcard-hi' },
        h('div', { class: 'xsec-hd' },
          h('span', { text: 'WARREN BUFFETT AUTOMATIC CAPITAL ALLOCATION ENGINE' }),
          h('span', { class: 'up', text: 'PAY YOURSELF FIRST (40% / 60%)' })
        ),
        h('div', { style: 'padding:8px;font-size:11px;line-height:1.55;color:#dce4ee' },
          h('div', { style: 'color:var(--amber);font-style:italic;margin-bottom:6px', text: '"Do not save what is left after spending, but spend what is left after saving." — Warren Buffett' }),
          h('div', { style: 'margin-bottom:8px', text: wb.principle || 'Allocate 40% to productive investment & emergency reserves on Day 1; operate strictly within 60% for Food & Transportation.' }),
          h('div', { style: 'display:flex;gap:8px;align-items:center;flex-wrap:wrap' },
            h('span', { class: 'lbl', text: 'FIXED MONTHLY INCOME (IDR):' }),
            incInp,
            h('button', { class: 'on', style: 'background:#ff6600;color:#000;border-color:#ff6600;font-weight:700', text: 'APPLY AUTOMATIC SPLIT', onclick: () => applyBuffett(incInp.value, false) }),
            h('button', { style: 'background:#00d26a;color:#000;border-color:#00d26a;font-weight:700', text: 'BOOK INCOME + AUTO-LOCK 40% SAVINGS', onclick: () => applyBuffett(incInp.value, true) })
          )
        )
      ));

      const tbl = h('table', { class: 't', style: 'margin-bottom:8px' },
        h('thead', {}, h('tr', {},
          h('th', { text: 'PRIORITY TIER' }),
          h('th', { text: 'ALLOCATION BUCKET' }),
          h('th', { class: 'r', text: 'SHARE' }),
          h('th', { class: 'r', text: 'MONTHLY (IDR)' }),
          h('th', { class: 'r', text: 'DAILY EQUIV' }),
          h('th', { text: 'PURPOSE' })
        ))
      );
      const tbdy = h('tbody');
      (wb.buckets || []).forEach(b => {
        tbdy.append(h('tr', {},
          h('td', { style: `color:${b.color};font-weight:700`, text: b.tier }),
          h('td', { style: 'color:#fff;font-weight:700', text: b.name }),
          h('td', { class: 'r am', text: `${b.pct}%` }),
          h('td', { class: 'r up', style: 'font-weight:700', text: fmtIdr(b.amountIdr) }),
          h('td', { class: 'r', text: fmtIdr(Math.floor(b.amountIdr / 30)) }),
          h('td', { style: 'color:var(--muted)', text: b.desc })
        ));
      });
      tbl.append(tbdy);
      sc.append(tbl);

      sc.append(h('div', { class: 'xcard' },
        h('div', { class: 'xsec-hd' },
          h('span', { text: `LONG-TERM COMPOUNDING PROJECTION (${fmtIdr(wb.payYourselfFirstIdr || 400000)}/MONTH LOCKED)` }),
          h('span', { class: 'up', text: 'BLUE=PRINCIPAL | AMBER=8% P.A. | GREEN=12% P.A.' })
        ),
        makeSvgBox(buildCompoundingSvg(wb.projections || []))
      ));

      const pTbl = h('table', { class: 't' },
        h('thead', {}, h('tr', {},
          h('th', { text: 'HORIZON' }),
          h('th', { class: 'r', text: 'TOTAL PRINCIPAL' }),
          h('th', { class: 'r', text: 'CONSERVATIVE (8% P.A.)' }),
          h('th', { class: 'r', text: 'EQUITY BENCHMARK (12% P.A.)' })
        ))
      );
      const pBody = h('tbody');
      (wb.projections || []).forEach(p => {
        pBody.append(h('tr', {},
          h('td', { class: 'am', style: 'font-weight:700', text: `${p.years} Year${p.years > 1 ? 's' : ''}` }),
          h('td', { class: 'r', text: fmtIdr(p.principalIdr) }),
          h('td', { class: 'r am', text: fmtIdr(p.conservativeIdr) }),
          h('td', { class: 'r up', style: 'font-weight:700', text: fmtIdr(p.benchmarkIdr) })
        ));
      });
      pTbl.append(pBody);
      sc.append(pTbl);

    } else if (tab === 'BUDGET') {
      const dLim = h('input', { type: 'number', value: String(finData.dailyLimitIdr || 20000), style: 'width:100%' });
      const mBud = h('input', { type: 'number', value: String(finData.monthlyBudgetIdr || 600000), style: 'width:100%' });
      const mInc = h('input', { type: 'number', value: String(finData.monthlyIncomeTarget || 1000000), style: 'width:100%' });
      const catInputs = {};

      const budCard = h('div', { class: 'xcard' },
        h('div', { class: 'xsec-hd' }, h('span', { text: 'OPERATING LIMITS & ENVELOPE CONFIGURATION' }), h('span', { class: 'am', text: 'AUTO PUSH ALERT ON BREACH' })),
        h('div', { class: 'xgrid3', style: 'padding:8px 2px' },
          h('div', {}, h('div', { class: 'lbl', style: 'margin-bottom:3px', text: 'Daily Operating Ceiling (IDR)' }), dLim),
          h('div', {}, h('div', { class: 'lbl', style: 'margin-bottom:3px', text: 'Monthly Operating Budget (IDR)' }), mBud),
          h('div', {}, h('div', { class: 'lbl', style: 'margin-bottom:3px', text: 'Fixed Monthly Income (IDR)' }), mInc)
        )
      );
      const cGrid = h('div', { class: 'xgrid2', style: 'padding:4px 2px' });
      Object.entries(finData.categoryLimits || {}).forEach(([k, v]) => {
        const el = h('input', { type: 'number', value: String(v), style: 'width:100%' });
        catInputs[k] = el;
        cGrid.append(h('div', {}, h('div', { style: 'font-size:10px;color:var(--label);margin-bottom:2px', text: k }), el));
      });
      budCard.append(cGrid, h('div', { style: 'padding:6px 2px;display:flex;gap:8px;flex-wrap:wrap' },
        h('button', {
          class: 'on',
          style: 'background:#ff6600;color:#000;border-color:#ff6600;font-weight:700;padding:6px 14px',
          text: 'SAVE BUDGET LIMITS',
          onclick: async () => {
            const categoryLimits = {};
            for (const [k, el] of Object.entries(catInputs)) categoryLimits[k] = Number(el.value) || 0;
            const r = await apiFetch('/api/finance/budget', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                dailyLimitIdr: Number(dLim.value),
                monthlyBudgetIdr: Number(mBud.value),
                monthlyIncomeTarget: Number(mInc.value),
                categoryLimits
              })
            }, 10000);
            const j = await r.json();
            if (r.ok && j.ok) { finData = j.data; statusNote = 'Budget limits saved successfully.'; renderBody(); }
          }
        }),
        h('button', {
          style: 'color:#00d26a;border-color:#00d26a',
          text: 'RESET TO WARREN BUFFETT AUTO-SPLIT',
          onclick: () => applyBuffett(Number(mInc.value || 1000000), false)
        })
      ));
      sc.append(budCard);

      const gCard = h('div', { class: 'xcard' },
        h('div', { class: 'xsec-hd' }, h('span', { text: 'CAPITAL RESERVES & SAVINGS GOALS' }), h('span', { class: 'up', text: `${(finData.goals || []).length} GOALS` }))
      );
      (finData.goals || []).forEach(g => {
        const pct = g.targetIdr > 0 ? Math.min(100, (g.savedIdr / g.targetIdr) * 100) : 0;
        gCard.append(h('div', { style: 'padding:8px;border-bottom:1px solid #181d26' },
          h('div', { style: 'display:flex;justify-content:space-between;align-items:center;margin-bottom:4px' },
            h('div', {}, h('b', { style: 'color:#fff', text: g.name }), h('span', { style: 'color:var(--muted);font-size:10px;margin-left:8px', text: `Target Date: ${g.deadline || '-'}` })),
            h('div', { style: 'display:flex;gap:6px;align-items:center' },
              h('span', { style: 'color:var(--up);font-weight:700', text: `${fmtIdr(g.savedIdr)} / ${fmtIdr(g.targetIdr)} (${pct.toFixed(1)}%)` }),
              h('button', { style: 'font-size:10px;color:#ff5a52', text: 'DEL', onclick: async () => {
                const r = await apiFetch(`/api/finance/goal/${encodeURIComponent(g.id)}`, { method: 'DELETE' }, 10000);
                const j = await r.json();
                if (r.ok && j.ok) { finData = j.data; renderBody(); }
              } })
            )
          ),
          h('div', { class: 'xbar-track' }, h('div', { class: 'xbar-fill', style: `width:${pct}%;background:var(--up)` }))
        ));
      });

      const gName = h('input', { placeholder: 'Goal title (e.g. Emergency Reserve / Equipment)', style: 'width:100%' });
      const gTarget = h('input', { type: 'number', placeholder: 'Target amount (IDR)', style: 'width:100%' });
      const gSaved = h('input', { type: 'number', placeholder: 'Current saved (IDR)', style: 'width:100%' });
      gCard.append(h('div', { class: 'xgrid3', style: 'padding:8px 4px' }, gName, gTarget, gSaved),
        h('div', { style: 'padding:0 4px 6px' }, h('button', {
          class: 'on',
          text: 'ADD CAPITAL GOAL',
          onclick: async () => {
            if (!gName.value.trim() || !Number(gTarget.value)) return;
            const r = await apiFetch('/api/finance/goal', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ name: gName.value.trim(), targetIdr: Number(gTarget.value), savedIdr: Number(gSaved.value || 0) })
            }, 10000);
            const j = await r.json();
            if (r.ok && j.ok) { finData = j.data; statusNote = 'Capital goal added.'; renderBody(); }
          }
        }))
      );
      sc.append(gCard);

    } else if (tab === 'HIST') {
      const fBar = h('div', { style: 'display:flex;gap:4px;margin-bottom:8px' },
        ...['ALL', 'EXPENSE', 'INCOME', 'SAVINGS'].map(f => h('button', {
          class: historyFilter === f ? 'on' : '',
          text: f,
          onclick: () => { historyFilter = f; renderBody(); }
        }))
      );
      sc.append(fBar);

      const list = (finData.transactions || []).filter(t => historyFilter === 'ALL' || t.type === historyFilter);
      if (!list.length) {
        sc.append(h('div', { class: 'na', text: 'No ledger entries recorded yet.' }));
        return;
      }
      const tbl = h('table', { class: 't' },
        h('thead', {}, h('tr', {},
          h('th', { text: 'DATE' }),
          h('th', { text: 'TYPE' }),
          h('th', { text: 'CATEGORY' }),
          h('th', { text: 'DESCRIPTION' }),
          h('th', { class: 'r', text: 'AMOUNT' }),
          h('th', { text: '' })
        ))
      );
      const tbdy = h('tbody');
      list.slice(0, 150).forEach(t => {
        const cls = t.type === 'INCOME' ? 'up' : t.type === 'SAVINGS' ? 'am' : 'dn';
        tbdy.append(h('tr', {},
          h('td', { text: t.date || '-' }),
          h('td', {}, h('span', { class: `xpill ${t.type === 'INCOME' ? 'ok' : t.type === 'SAVINGS' ? 'warn' : 'no'}`, text: t.type })),
          h('td', { style: 'color:#e6edf3', text: t.category }),
          h('td', { style: 'color:var(--muted)', text: t.note || '-' }),
          h('td', { class: `r ${cls}`, style: 'font-weight:700', text: (t.type === 'EXPENSE' ? '-' : '+') + fmtIdr(t.amountIdr) }),
          h('td', {}, h('button', { style: 'font-size:10px;color:#ff5a52', text: 'DELETE', onclick: async () => {
            const r = await apiFetch(`/api/finance/tx/${encodeURIComponent(t.id)}`, { method: 'DELETE' }, 10000);
            const j = await r.json();
            if (r.ok && j.ok) { finData = j.data; renderBody(); }
          } }))
        ));
      });
      tbl.append(tbdy);
      sc.append(tbl);
    }
  }

  renderToolbar();
  load();
  ctx.cleanup(() => { unmounted = true; });
}

// =====================================================================
// 7. WDGT / WIDGET — BLOOMBERG TERMINAL WIDGET STUDIO & FLOATING DESK
// =====================================================================
export function mountWDGT(body, ctx) {
  body.classList.add('fill');
  const tb = h('div', { class: 'tb' });
  const sc = h('div', { class: 'pb' });
  body.append(tb, sc);

  let mode = 'all';

  async function launchFloatingWidget() {
    const widgetUrl = `${location.origin}/widget?mode=${mode}`;
    try {
      if (window.documentPictureInPicture && typeof window.documentPictureInPicture.requestWindow === 'function') {
        const pipWin = await window.documentPictureInPicture.requestWindow({ width: 420, height: 500 });
        pipWin.document.body.style.margin = '0';
        pipWin.document.body.style.background = '#000';
        const ifr = pipWin.document.createElement('iframe');
        ifr.src = widgetUrl;
        ifr.style.cssText = 'width:100vw;height:100vh;border:0;display:block';
        pipWin.document.body.appendChild(ifr);
        return;
      }
    } catch {}
    window.open(widgetUrl, 'BloombergTerminalWidget', 'width=430,height=520,menubar=no,toolbar=no,location=no,status=no');
  }

  function renderToolbar() {
    tb.textContent = '';
    tb.append(
      h('span', { class: 'lbl', text: 'BLOOMBERG WIDGET STUDIO:' }),
      ...[['all', 'UNIFIED DESK'], ['market', 'MARKET QUOTES'], ['bot', 'EXECUTION'], ['finance', 'CAPITAL']].map(([m, lbl]) => h('button', {
        class: mode === m ? 'on' : '',
        text: lbl,
        onclick: () => { mode = m; renderToolbar(); renderBody(); }
      })),
      h('button', { style: 'background:#ff6600;color:#000;border-color:#ff6600;font-weight:700', text: 'LAUNCH FLOATING WIDGET', onclick: launchFloatingWidget })
    );
  }

  function renderBody() {
    sc.textContent = '';
    const widgetUrl = `${location.origin}/widget?mode=${mode}`;
    const termuxCmd = 'mkdir -p ~/.shortcuts && cp ~/home-server/tablet1-chatbot/scripts/termux-widget-bloomberg.sh ~/.shortcuts/"Bloomberg Terminal.sh" && chmod +x ~/.shortcuts/"Bloomberg Terminal.sh"';

    sc.append(h('div', { class: 'xgrid2', style: 'margin-bottom:8px' },
      h('div', { class: 'xcard', style: 'margin-bottom:0' },
        h('div', { class: 'xsec-hd' }, h('span', { text: 'LIVE WIDGET PREVIEW' }), h('span', { class: 'up', text: mode.toUpperCase() })),
        h('iframe', { src: `/widget?mode=${mode}`, style: 'width:100%;height:340px;border:0;background:#000;display:block' })
      ),
      h('div', { class: 'xcard', style: 'margin-bottom:0' },
        h('div', { class: 'xsec-hd' }, h('span', { text: 'DEPLOYMENT & HOME SCREEN SETUP' }), h('span', { class: 'am', text: 'ANDROID / WINDOWS / PWA' })),
        h('div', { style: 'padding:8px;font-size:11px;line-height:1.55;color:#dce4ee' },
          h('div', { style: 'margin-bottom:8px' },
            h('b', { style: 'color:var(--amber)', text: '1. Floating Always-on-Top Widget (Desktop / Tablet):' }),
            h('div', { text: 'Click "LAUNCH FLOATING WIDGET" above to pop out a compact live mini-terminal window.' })
          ),
          h('div', { style: 'margin-bottom:8px' },
            h('b', { style: 'color:#00d26a', text: '2. Android Home Screen Live Web Widget:' }),
            h('div', { text: 'Use Android Web Widget / Hermit / KWGT and point it to this live widget endpoint:' }),
            h('input', { value: widgetUrl, readonly: 'readonly', style: 'width:100%;margin-top:4px;color:#00e5ff' })
          ),
          h('div', { style: 'margin-bottom:8px' },
            h('b', { style: 'color:#4da3ff', text: '3. Android Termux:Widget Home Screen Shortcut:' }),
            h('div', { text: 'Run once in Termux, then add "Termux:Widget" to your Android Home Screen:' }),
            h('input', { value: termuxCmd, readonly: 'readonly', style: 'width:100%;margin-top:4px;color:#ffb000;font-size:10px' })
          ),
          h('div', {},
            h('b', { style: 'color:#b388ff', text: '4. Windows / Edge PWA Widgets Manifest:' }),
            h('div', { text: 'Declared in /manifest.webmanifest via /widgets/terminal-widget.json & /api/widget/summary (60s auto-refresh).' })
          )
        )
      )
    ));
    ctx.status({ ok: true, source: 'widget-studio', ts: Date.now(), mode: 'LIVE' });
  }

  renderToolbar();
  renderBody();
}

// =====================================================================
// 8. ROE / PNL — INSTITUTIONAL SHAREABLE ROE CARD STUDIO & MODAL
// =====================================================================
const _roeKlineCache = new Map();

async function fetchRoeSparkCandles(sym) {
  const clean = String(sym || 'BTCUSDT').toUpperCase().replace('-USD', 'USDT').replace(/\.P$/, '');
  const hit = _roeKlineCache.get(clean);
  if (hit && Date.now() - hit.ts < 30000) return hit.candles;
  try {
    const env = await get('kline', { symbol: clean, interval: '15m', limit: 48 }, 8000);
    const arr = env && env.ok
      ? (Array.isArray(env.data) ? env.data : (env.data && Array.isArray(env.data.candles) ? env.data.candles : []))
      : [];
    if (arr.length >= 5) {
      _roeKlineCache.set(clean, { ts: Date.now(), candles: arr });
      return arr;
    }
  } catch {}
  return [];
}

function renderRoeCardCanvas(canvas, cfg = {}, candles = []) {
  const isStory = cfg.aspect === '9:16';
  const W = isStory ? 1080 : 1200;
  const H = isStory ? 1920 : 675;
  canvas.width = W;
  canvas.height = H;

  const ctx = canvas.getContext('2d');
  const sym = String(cfg.symbol || 'BTCUSDT').toUpperCase().replace('-USD', 'USDT').replace(/\.P$/, '');
  const dir = String(cfg.direction || 'LONG').toUpperCase() === 'SHORT' ? 'SHORT' : 'LONG';
  const lev = Math.max(1, Number(cfg.leverage) || 20);
  const marginMode = String(cfg.marginMode || 'ISOLATED').toUpperCase();
  const entry = Math.max(0, Number(cfg.entryPrice) || 0);
  const mark = Math.max(0, Number(cfg.markPrice) || entry);
  const sign = dir === 'SHORT' ? -1 : 1;
  const unleveredPct = entry > 0 && mark > 0 ? sign * ((mark - entry) / entry) * 100 : 0;
  const roePct = Number.isFinite(Number(cfg.roePct))
    ? Number(cfg.roePct)
    : +(unleveredPct * lev).toFixed(2);
  const isGain = roePct >= 0;
  const fxRate = Number(cfg.fxRateIdr) > 10000 ? Number(cfg.fxRateIdr) : 18218;
  const pnlUsd = Number(cfg.pnlUsd) || 0;
  const pnlIdr = Number(cfg.pnlIdr) || Math.round(pnlUsd * fxRate);
  const setup = String(cfg.setup || 'QUANT_EXECUTION').toUpperCase();
  const statusTag = String(cfg.status || 'OPEN').toUpperCase().startsWith('OPEN') ? 'LIVE OPEN POSITION' : 'REALIZED EXECUTION';
  const confScore = Number(cfg.hybridConf || cfg.pMath || 0);

  const themes = {
    CLASSIC: {
      bg0: '#030508', bg1: '#080d16', accent: '#ff6600', accentText: '#000000',
      border: '#253042', subText: '#8e9cb2', cardBg: '#090e17', grid: 'rgba(255,255,255,0.032)'
    },
    GOLD: {
      bg0: '#070603', bg1: '#120e05', accent: '#ffb000', accentText: '#000000',
      border: '#59410d', subText: '#cbb682', cardBg: '#0e0b05', grid: 'rgba(255,176,0,0.04)'
    },
    MATRIX: {
      bg0: '#02080d', bg1: '#051521', accent: '#00e5ff', accentText: '#000000',
      border: '#114a5c', subText: '#7ec8d9', cardBg: '#06121c', grid: 'rgba(0,229,255,0.04)'
    }
  };
  const th = themes[cfg.theme] || themes.CLASSIC;
  const gainCol = isGain ? '#00d26a' : '#ff453a';

  // Background gradient
  const bgGrad = ctx.createLinearGradient(0, 0, W, H);
  bgGrad.addColorStop(0, th.bg0);
  bgGrad.addColorStop(1, th.bg1);
  ctx.fillStyle = bgGrad;
  ctx.fillRect(0, 0, W, H);

  // Ambient radial glow behind ROE readout
  const radGlow = ctx.createRadialGradient(
    isStory ? W * 0.5 : W * 0.34,
    isStory ? H * 0.30 : H * 0.44,
    20,
    isStory ? W * 0.5 : W * 0.34,
    isStory ? H * 0.30 : H * 0.44,
    isStory ? 520 : 390
  );
  radGlow.addColorStop(0, isGain ? 'rgba(0, 210, 106, 0.16)' : 'rgba(255, 69, 58, 0.16)');
  radGlow.addColorStop(1, 'rgba(0, 0, 0, 0)');
  ctx.fillStyle = radGlow;
  ctx.fillRect(0, 0, W, H);

  // Precision institutional grid
  ctx.strokeStyle = th.grid;
  ctx.lineWidth = 1;
  const gStep = isStory ? 60 : 48;
  for (let gx = gStep; gx < W; gx += gStep) {
    ctx.beginPath(); ctx.moveTo(gx, 0); ctx.lineTo(gx, H); ctx.stroke();
  }
  for (let gy = gStep; gy < H; gy += gStep) {
    ctx.beginPath(); ctx.moveTo(0, gy); ctx.lineTo(W, gy); ctx.stroke();
  }

  // Outer institutional frame
  ctx.strokeStyle = th.border;
  ctx.lineWidth = 2;
  ctx.strokeRect(16, 16, W - 32, H - 32);
  ctx.strokeStyle = th.accent;
  ctx.lineWidth = 2;
  // Corner brackets
  const cb = 28;
  [
    [16, 16 + cb, 16, 16, 16 + cb, 16],
    [W - 16 - cb, 16, W - 16, 16, W - 16, 16 + cb],
    [16, H - 16 - cb, 16, H - 16, 16 + cb, H - 16],
    [W - 16 - cb, H - 16, W - 16, H - 16, W - 16, H - 16 - cb]
  ].forEach(([x1, y1, x2, y2, x3, y3]) => {
    ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.lineTo(x3, y3); ctx.stroke();
  });

  const padX = isStory ? 64 : 52;
  const topY = isStory ? 68 : 44;

  // Top Header: [B] Monogram + BLOOMBERG TERMINAL
  ctx.fillStyle = th.accent;
  ctx.fillRect(padX, topY, isStory ? 48 : 38, isStory ? 48 : 38);
  ctx.fillStyle = th.accentText;
  ctx.font = `900 ${isStory ? 30 : 24}px Consolas, "JetBrains Mono", monospace`;
  ctx.fillText('B', padX + (isStory ? 14 : 11), topY + (isStory ? 35 : 28));

  ctx.fillStyle = '#ffffff';
  ctx.font = `bold ${isStory ? 28 : 21}px Consolas, "JetBrains Mono", monospace`;
  ctx.fillText('BLOOMBERG TERMINAL', padX + (isStory ? 64 : 50), topY + (isStory ? 24 : 18));
  ctx.fillStyle = th.accent;
  ctx.font = `bold ${isStory ? 16 : 12.5}px Consolas, "JetBrains Mono", monospace`;
  ctx.fillText('QUANTITATIVE FUTURES EXECUTION DESK // VERIFIED ROE RECORD', padX + (isStory ? 64 : 50), topY + (isStory ? 46 : 35));

  const utcStr = new Date().toISOString().replace('T', ' ').slice(0, 19) + ' UTC';
  const refHash = 'REF #BBG-' + Math.abs(
    `${sym}${dir}${entry}${mark}`.split('').reduce((a, ch) => ((a << 5) - a + ch.charCodeAt(0)) | 0, 0)
  ).toString(16).toUpperCase().padStart(6, '0').slice(0, 6);
  ctx.textAlign = 'right';
  ctx.fillStyle = th.subText;
  ctx.font = `bold ${isStory ? 16 : 12.5}px Consolas, "JetBrains Mono", monospace`;
  ctx.fillText(utcStr, W - padX, topY + (isStory ? 22 : 17));
  ctx.fillStyle = th.accent;
  ctx.fillText(refHash, W - padX, topY + (isStory ? 45 : 35));
  ctx.textAlign = 'left';

  // Divider line
  const divY = topY + (isStory ? 68 : 52);
  ctx.strokeStyle = th.border;
  ctx.lineWidth = 1.5;
  ctx.beginPath(); ctx.moveTo(padX, divY); ctx.lineTo(W - padX, divY); ctx.stroke();

  // Helper to draw embedded sparkline chart inside a rect
  const drawEmbeddedChart = (cx, cy, cw, ch) => {
    ctx.fillStyle = th.cardBg;
    ctx.fillRect(cx, cy, cw, ch);
    ctx.strokeStyle = th.border;
    ctx.lineWidth = 1.5;
    ctx.strokeRect(cx, cy, cw, ch);

    ctx.fillStyle = th.subText;
    ctx.font = `bold ${isStory ? 16 : 12}px Consolas, "JetBrains Mono", monospace`;
    ctx.fillText(`${sym} PRICE TRAJECTORY (15M FEED • ENTRY TO MARK)`, cx + 16, cy + (isStory ? 28 : 22));

    let series = Array.isArray(candles) ? candles.slice(-36).map(c => ({
      o: Number(c.o ?? c.open ?? c.c ?? c.close),
      h: Number(c.h ?? c.high ?? c.c ?? c.close),
      l: Number(c.l ?? c.low ?? c.c ?? c.close),
      c: Number(c.c ?? c.close ?? 0)
    })).filter(c => c.c > 0) : [];

    // Ensure chart reflects live mark & entry if klines unavailable
    if (series.length < 4 && entry > 0) {
      series = [];
      const steps = 28;
      for (let i = 0; i < steps; i++) {
        const t = i / (steps - 1);
        const wave = Math.sin(i * 0.65) * Math.abs(mark - entry || entry * 0.004) * 0.18 * (1 - t * 0.5);
        const cl = entry + (mark - entry) * Math.pow(t, 0.88) + wave;
        const op = i === 0 ? entry : series[i - 1].c;
        const sp = Math.max(Math.abs(cl - op) * 0.6, entry * 0.0012);
        series.push({ o: op, c: cl, h: Math.max(op, cl) + sp, l: Math.min(op, cl) - sp });
      }
    } else if (series.length >= 4 && mark > 0) {
      series[series.length - 1] = {
        ...series[series.length - 1],
        c: mark,
        h: Math.max(series[series.length - 1].h, mark),
        l: Math.min(series[series.length - 1].l, mark)
      };
    }

    if (series.length < 2) return;
    const pL = cx + 16, pR = cx + cw - (isStory ? 116 : 96), pT = cy + (isStory ? 46 : 36), pB = cy + ch - 18;
    const pW = pR - pL, pH = pB - pT;
    let lo = Infinity, hi = -Infinity;
    series.forEach(b => { lo = Math.min(lo, b.l); hi = Math.max(hi, b.h); });
    if (entry > 0) { lo = Math.min(lo, entry); hi = Math.max(hi, entry); }
    if (mark > 0) { lo = Math.min(lo, mark); hi = Math.max(hi, mark); }
    const span = Math.max(1e-8, hi - lo);
    lo -= span * 0.12;
    hi += span * 0.12;
    const yOf = px => pT + ((hi - px) / (hi - lo)) * pH;

    // Shaded zone between Entry and Mark
    if (entry > 0 && mark > 0) {
      const yE = yOf(entry), yM = yOf(mark);
      ctx.fillStyle = isGain ? 'rgba(0, 210, 106, 0.09)' : 'rgba(255, 69, 58, 0.09)';
      ctx.fillRect(pL, Math.min(yE, yM), pW, Math.max(2, Math.abs(yM - yE)));
    }

    // Mini candles
    const step = pW / series.length;
    series.forEach((b, idx) => {
      const x = pL + idx * step + step * 0.5;
      const up = b.c >= b.o;
      ctx.strokeStyle = up ? '#00d26a' : '#ff453a';
      ctx.fillStyle = up ? '#00d26a' : '#ff453a';
      ctx.lineWidth = 1.4;
      ctx.beginPath(); ctx.moveTo(x, yOf(b.h)); ctx.lineTo(x, yOf(b.l)); ctx.stroke();
      const bt = Math.min(yOf(b.o), yOf(b.c));
      const bh = Math.max(2, Math.abs(yOf(b.c) - yOf(b.o)));
      ctx.fillRect(x - Math.max(1.5, step * 0.3), bt, Math.max(3, step * 0.6), bh);
    });

    // Entry dashed line
    if (entry > 0) {
      const yE = yOf(entry);
      ctx.save();
      ctx.strokeStyle = '#ffb000';
      ctx.lineWidth = 1.6;
      ctx.setLineDash([6, 4]);
      ctx.beginPath(); ctx.moveTo(pL, yE); ctx.lineTo(pR, yE); ctx.stroke();
      ctx.restore();
      ctx.fillStyle = '#ffb000';
      ctx.font = `bold ${isStory ? 14 : 11}px Consolas, monospace`;
      ctx.fillText('ENT ' + fmtPx(entry), pR + 6, yE + 4);
    }

    // Mark dashed line & live beacon
    if (mark > 0) {
      const yM = yOf(mark);
      ctx.save();
      ctx.strokeStyle = gainCol;
      ctx.lineWidth = 1.8;
      ctx.setLineDash([3, 3]);
      ctx.beginPath(); ctx.moveTo(pL, yM); ctx.lineTo(pR, yM); ctx.stroke();
      ctx.restore();

      const lastX = pL + (series.length - 0.5) * step;
      ctx.beginPath();
      ctx.arc(lastX, yM, isStory ? 6 : 5, 0, Math.PI * 2);
      ctx.fillStyle = gainCol;
      ctx.fill();

      ctx.fillStyle = gainCol;
      ctx.font = `bold ${isStory ? 14 : 11}px Consolas, monospace`;
      ctx.fillText('MRK ' + fmtPx(mark), pR + 6, yM + (entry > 0 && Math.abs(yM - yOf(entry)) < 14 ? -6 : 4));
    }
  };

  const roeSign = roePct >= 0 ? '+' : '';
  const roeText = `${roeSign}${roePct.toFixed(2)}%`;
  const pnlText = cfg.showPnlAmount
    ? `${pnlUsd >= 0 ? '+$' : '-$'}${Math.abs(pnlUsd).toFixed(2)} USDT   |   ${pnlIdr >= 0 ? '+Rp ' : '-Rp '}${Math.abs(pnlIdr).toLocaleString('id-ID')} IDR`
    : 'NOMINAL SIZE PROTECTED  •  VERIFIED PERCENTAGE RETURN ON MARGIN';

  const metrics = [
    ['ENTRY PRICE', entry > 0 ? '$' + fmtPx(entry) : 'N/A', '#ffb000'],
    [statusTag.startsWith('LIVE') ? 'LIVE MARK PRICE' : 'EXIT PRICE', mark > 0 ? '$' + fmtPx(mark) : 'N/A', '#ffffff'],
    ['UNLEVERED MOVE', `${unleveredPct >= 0 ? '+' : ''}${unleveredPct.toFixed(2)}% (${lev}x)`, gainCol],
    ['QUANT TELEMETRY', confScore > 0 ? `CONF ${confScore.toFixed(1)}% • ${setup.slice(0, 12)}` : setup.slice(0, 18), th.accent]
  ];

  if (!isStory) {
    // ================= 16:9 DESK CARD LAYOUT (1200 x 675) =================
    const bodyTop = divY + 26;
    // Left Half: Contract Badge, Giant ROE %, PnL Sub-banner
    ctx.fillStyle = '#ffffff';
    ctx.font = '900 36px Consolas, "JetBrains Mono", monospace';
    ctx.fillText(`${sym} PERP`, padX, bodyTop + 32);

    // Direction + Leverage Pill
    const badgeTxt = `${dir} ${lev}X ${marginMode}`;
    ctx.font = 'bold 15px Consolas, "JetBrains Mono", monospace';
    const bw = ctx.measureText(badgeTxt).width + 24;
    ctx.fillStyle = dir === 'LONG' ? 'rgba(0,210,106,0.18)' : 'rgba(255,69,58,0.18)';
    ctx.strokeStyle = dir === 'LONG' ? '#00d26a' : '#ff453a';
    ctx.lineWidth = 1.5;
    ctx.fillRect(padX, bodyTop + 48, bw, 28);
    ctx.strokeRect(padX, bodyTop + 48, bw, 28);
    ctx.fillStyle = dir === 'LONG' ? '#00d26a' : '#ff453a';
    ctx.fillText(badgeTxt, padX + 12, bodyTop + 67);

    // Status Pill
    ctx.font = 'bold 13px Consolas, "JetBrains Mono", monospace';
    const sw = ctx.measureText(statusTag).width + 20;
    ctx.fillStyle = 'rgba(255,176,0,0.12)';
    ctx.strokeStyle = th.accent;
    ctx.fillRect(padX + bw + 10, bodyTop + 48, sw, 28);
    ctx.strokeRect(padX + bw + 10, bodyTop + 48, sw, 28);
    ctx.fillStyle = th.accent;
    ctx.fillText(statusTag, padX + bw + 20, bodyTop + 67);

    // ROE Label & Giant Readout
    ctx.fillStyle = th.subText;
    ctx.font = 'bold 14px Consolas, "JetBrains Mono", monospace';
    ctx.fillText('RETURN ON EQUITY (ROE %)', padX, bodyTop + 114);

    ctx.save();
    ctx.shadowColor = isGain ? 'rgba(0,210,106,0.35)' : 'rgba(255,69,58,0.35)';
    ctx.shadowBlur = 22;
    ctx.fillStyle = gainCol;
    ctx.font = `900 ${roeText.length > 8 ? 76 : 88}px Consolas, "JetBrains Mono", monospace`;
    ctx.fillText(roeText, padX, bodyTop + 198);
    ctx.restore();

    // Nominal PnL or Privacy Strip
    ctx.fillStyle = cfg.showPnlAmount ? '#e6edf3' : th.subText;
    ctx.font = 'bold 15px Consolas, "JetBrains Mono", monospace';
    ctx.fillText(pnlText, padX, bodyTop + 236);

    // Right Half: Embedded Sparkline Chart
    drawEmbeddedChart(610, bodyTop + 4, W - 610 - padX, 258);

    // Bottom 4-Column Telemetry Grid
    const gridY = 428;
    const boxW = (W - padX * 2 - 36) / 4;
    metrics.forEach(([k, val, col], idx) => {
      const bx = padX + idx * (boxW + 12);
      ctx.fillStyle = th.cardBg;
      ctx.strokeStyle = th.border;
      ctx.lineWidth = 1.5;
      ctx.fillRect(bx, gridY, boxW, 128);
      ctx.strokeRect(bx, gridY, boxW, 128);
      ctx.fillStyle = th.accent;
      ctx.fillRect(bx, gridY, 4, 128);

      ctx.fillStyle = th.subText;
      ctx.font = 'bold 13px Consolas, "JetBrains Mono", monospace';
      ctx.fillText(k, bx + 16, gridY + 34);
      ctx.fillStyle = col;
      ctx.font = '900 22px Consolas, "JetBrains Mono", monospace';
      ctx.fillText(val, bx + 16, gridY + 84);
    });
  } else {
    // ================= 9:16 STORY / STATUS LAYOUT (1080 x 1920) =================
    const sTop = divY + 54;
    ctx.fillStyle = '#ffffff';
    ctx.font = '900 62px Consolas, "JetBrains Mono", monospace';
    ctx.fillText(`${sym} PERPETUAL`, padX, sTop + 52);

    const badgeTxt = `${dir} ${lev}X ${marginMode}`;
    ctx.font = 'bold 26px Consolas, "JetBrains Mono", monospace';
    const bw = ctx.measureText(badgeTxt).width + 38;
    ctx.fillStyle = dir === 'LONG' ? 'rgba(0,210,106,0.18)' : 'rgba(255,69,58,0.18)';
    ctx.strokeStyle = dir === 'LONG' ? '#00d26a' : '#ff453a';
    ctx.lineWidth = 2;
    ctx.fillRect(padX, sTop + 82, bw, 48);
    ctx.strokeRect(padX, sTop + 82, bw, 48);
    ctx.fillStyle = dir === 'LONG' ? '#00d26a' : '#ff453a';
    ctx.fillText(badgeTxt, padX + 19, sTop + 115);

    ctx.font = 'bold 24px Consolas, "JetBrains Mono", monospace';
    const sw = ctx.measureText(statusTag).width + 34;
    ctx.fillStyle = 'rgba(255,176,0,0.12)';
    ctx.strokeStyle = th.accent;
    ctx.fillRect(padX + bw + 16, sTop + 82, sw, 48);
    ctx.strokeRect(padX + bw + 16, sTop + 82, sw, 48);
    ctx.fillStyle = th.accent;
    ctx.fillText(statusTag, padX + bw + 33, sTop + 115);

    ctx.fillStyle = th.subText;
    ctx.font = 'bold 26px Consolas, "JetBrains Mono", monospace';
    ctx.fillText('RETURN ON EQUITY (ROE %)', padX, sTop + 216);

    ctx.save();
    ctx.shadowColor = isGain ? 'rgba(0,210,106,0.4)' : 'rgba(255,69,58,0.4)';
    ctx.shadowBlur = 32;
    ctx.fillStyle = gainCol;
    ctx.font = `900 ${roeText.length > 8 ? 128 : 148}px Consolas, "JetBrains Mono", monospace`;
    ctx.fillText(roeText, padX, sTop + 362);
    ctx.restore();

    ctx.fillStyle = cfg.showPnlAmount ? '#ffffff' : th.subText;
    ctx.font = 'bold 24px Consolas, "JetBrains Mono", monospace';
    ctx.fillText(pnlText, padX, sTop + 422);

    // Embedded Chart (Full Width)
    drawEmbeddedChart(padX, sTop + 474, W - padX * 2, 540);

    // 2x2 Telemetry Grid
    const gTop = sTop + 1060;
    const cellW = (W - padX * 2 - 28) / 2;
    const cellH = 190;
    metrics.forEach(([k, val, col], idx) => {
      const colIdx = idx % 2;
      const rowIdx = Math.floor(idx / 2);
      const bx = padX + colIdx * (cellW + 28);
      const by = gTop + rowIdx * (cellH + 26);
      ctx.fillStyle = th.cardBg;
      ctx.strokeStyle = th.border;
      ctx.lineWidth = 2;
      ctx.fillRect(bx, by, cellW, cellH);
      ctx.strokeRect(bx, by, cellW, cellH);
      ctx.fillStyle = th.accent;
      ctx.fillRect(bx, by, 6, cellH);

      ctx.fillStyle = th.subText;
      ctx.font = 'bold 22px Consolas, "JetBrains Mono", monospace';
      ctx.fillText(k, bx + 26, by + 56);
      ctx.fillStyle = col;
      ctx.font = '900 36px Consolas, "JetBrains Mono", monospace';
      ctx.fillText(val, bx + 26, by + 132);
    });
  }

  // Footer Watermark Strip
  const footY = H - (isStory ? 64 : 38);
  ctx.strokeStyle = th.border;
  ctx.lineWidth = 1.2;
  ctx.beginPath(); ctx.moveTo(padX, footY - (isStory ? 34 : 22)); ctx.lineTo(W - padX, footY - (isStory ? 34 : 22)); ctx.stroke();

  ctx.fillStyle = th.subText;
  ctx.font = `bold ${isStory ? 18 : 12.5}px Consolas, "JetBrains Mono", monospace`;
  ctx.fillText('BLOOMBERG TERMINAL // 5-LAYER QUANT + AI EXECUTION ENGINE • ISOLATED RISK GUARD', padX, footY);
  ctx.textAlign = 'right';
  ctx.fillStyle = th.accent;
  ctx.fillText(`USD/IDR FX: Rp ${Math.round(fxRate).toLocaleString('id-ID')}`, W - padX, footY);
  ctx.textAlign = 'left';
}

function canvasToPngBlob(canvas) {
  return new Promise(resolve => canvas.toBlob(b => resolve(b), 'image/png'));
}

function makeRoeFilename(cfg) {
  const sym = String(cfg.symbol || 'BTCUSDT').toUpperCase().replace(/[^A-Z0-9]/g, '');
  const tag = cfg.aspect === '9:16' ? 'STORY' : 'DESK';
  const ts = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-');
  return `Bloomberg_Terminal_ROE_${sym}_${tag}_${ts}.png`;
}

async function archiveAndDownloadRoe(canvas, cfg, onMsg) {
  const dataUrl = canvas.toDataURL('image/png');
  const sym = String(cfg.symbol || 'BTCUSDT').toUpperCase();
  saveSnapshotToGallery({
    id: 'ROE-' + Date.now() + '-' + sym,
    symbol: sym,
    interval: `ROE ${cfg.roePct >= 0 ? '+' : ''}${Number(cfg.roePct || 0).toFixed(1)}%`,
    ts: Date.now(),
    dataUrl
  });
  const a = document.createElement('a');
  a.href = dataUrl;
  a.download = makeRoeFilename(cfg);
  document.body.appendChild(a);
  a.click();
  setTimeout(() => a.remove(), 180);
  if (onMsg) onMsg('HD PNG downloaded & archived to G <GO>.');
}

async function copyRoeImage(canvas, onMsg) {
  const blob = await canvasToPngBlob(canvas);
  if (!blob) return false;
  if (navigator.clipboard && typeof window.ClipboardItem === 'function') {
    try {
      await navigator.clipboard.write([new window.ClipboardItem({ 'image/png': blob })]);
      if (onMsg) onMsg('ROE card copied to clipboard (ready to paste in Telegram / WhatsApp / Discord / X).');
      return true;
    } catch {}
  }
  if (onMsg) onMsg('Clipboard image write unsupported in this browser; downloading PNG instead.');
  return false;
}

async function shareRoeNative(canvas, cfg, onMsg) {
  const blob = await canvasToPngBlob(canvas);
  if (!blob) return;
  const filename = makeRoeFilename(cfg);
  const file = new File([blob], filename, { type: 'image/png' });
  const sym = String(cfg.symbol || 'BTCUSDT').toUpperCase();
  const roeStr = `${Number(cfg.roePct || 0) >= 0 ? '+' : ''}${Number(cfg.roePct || 0).toFixed(2)}%`;
  const caption = `Bloomberg Terminal // ${sym} ${cfg.direction || 'LONG'} ${cfg.leverage || 20}x ROE: ${roeStr}`;

  if (navigator.share && (!navigator.canShare || navigator.canShare({ files: [file] }))) {
    try {
      await navigator.share({ files: [file], title: 'Bloomberg Terminal ROE', text: caption });
      if (onMsg) onMsg('Shared via system share sheet.');
      return;
    } catch (e) {
      if (e && e.name === 'AbortError') return;
    }
  }
  const copied = await copyRoeImage(canvas, null);
  await archiveAndDownloadRoe(canvas, cfg, null);
  if (onMsg) onMsg(copied ? 'PNG downloaded & copied to clipboard for instant sharing.' : 'HD PNG downloaded & saved to G <GO> archive.');
}

export async function openRoeShareModal(initialTrade = {}) {
  const existing = document.getElementById('bbgRoeModal');
  if (existing) existing.remove();

  const cfg = {
    symbol: String(initialTrade.symbol || 'BTCUSDT').toUpperCase().replace('-USD', 'USDT').replace(/\.P$/, ''),
    direction: String(initialTrade.direction || 'LONG').toUpperCase(),
    leverage: Number(initialTrade.leverage || 20),
    marginMode: String(initialTrade.marginMode || 'ISOLATED').toUpperCase(),
    entryPrice: Number(initialTrade.entryPrice || 0),
    markPrice: Number(initialTrade.markPrice || initialTrade.entryPrice || 0),
    roePct: Number(initialTrade.roePct || 0),
    pnlUsd: Number(initialTrade.pnlUsd || 0),
    pnlIdr: Number(initialTrade.pnlIdr || 0),
    fxRateIdr: Number(initialTrade.fxRateIdr || 18218),
    setup: initialTrade.setup || 'QUANT_EXECUTION',
    status: initialTrade.status || 'OPEN',
    hybridConf: Number(initialTrade.hybridConf || initialTrade.pMath || 0),
    aspect: '16:9',
    theme: 'CLASSIC',
    showPnlAmount: false
  };

  const cv = h('canvas', { style: 'max-width:100%;max-height:56vh;width:auto;height:auto;display:block;margin:0 auto;border:1px solid #263142;background:#040609' });
  const msgEl = h('div', { style: 'font-size:11px;color:#00d26a;min-height:16px;margin-top:6px' });
  const ctrlBar = h('div', { class: 'tb', style: 'background:#0a0f17;border:1px solid #1f2937;margin-bottom:8px;gap:5px;flex-wrap:wrap' });

  let candles = [];
  const redraw = () => {
    ctrlBar.textContent = '';
    ctrlBar.append(
      h('span', { class: 'lbl', text: 'FORMAT:' }),
      ...[['16:9', '16:9 DESK'], ['9:16', '9:16 STORY']].map(([k, lbl]) => h('button', {
        class: cfg.aspect === k ? 'on' : '', text: lbl, onclick: () => { cfg.aspect = k; redraw(); }
      })),
      h('span', { class: 'lbl', text: 'THEME:' }),
      ...['CLASSIC', 'GOLD', 'MATRIX'].map(t => h('button', {
        class: cfg.theme === t ? 'on' : '', text: t, onclick: () => { cfg.theme = t; redraw(); }
      })),
      h('button', {
        class: cfg.showPnlAmount ? 'on' : '',
        text: cfg.showPnlAmount ? 'PNL: USD + IDR SHOWN' : 'PRIVACY: ROE % ONLY',
        onclick: () => { cfg.showPnlAmount = !cfg.showPnlAmount; redraw(); }
      })
    );
    renderRoeCardCanvas(cv, cfg, candles);
  };

  const overlay = h('div', {
    id: 'bbgRoeModal',
    style: 'position:fixed;inset:0;z-index:99995;background:rgba(0,0,0,0.88);display:flex;align-items:center;justify-content:center;padding:12px;font-family:var(--font,monospace)',
    onclick: ev => { if (ev.target === overlay) overlay.remove(); }
  },
    h('div', { style: 'width:760px;max-width:96vw;max-height:94vh;overflow:auto;background:#070a10;border:1px solid #ff6600;padding:12px;box-shadow:0 12px 44px rgba(0,0,0,0.85)' },
      h('div', { style: 'display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #222b38;padding-bottom:8px;margin-bottom:8px' },
        h('span', { style: 'color:#ff6600;font-weight:700;font-size:12px;letter-spacing:0.6px', text: `BLOOMBERG TERMINAL // SHAREABLE ROE CARD [${cfg.symbol}]` }),
        h('button', { style: 'background:#240808;color:#ff5a52;border:1px solid #ff453a88;padding:2px 8px;cursor:pointer;font-weight:700', text: 'CLOSE [ESC]', onclick: () => overlay.remove() })
      ),
      ctrlBar,
      h('div', { style: 'background:#020407;padding:8px;border:1px solid #18202c;text-align:center' }, cv),
      msgEl,
      h('div', { style: 'display:flex;gap:6px;justify-content:flex-end;flex-wrap:wrap;margin-top:8px' },
        h('button', { style: 'background:#ff6600;color:#000;border:1px solid #ff6600;padding:6px 12px;font-weight:800;cursor:pointer', text: 'SHARE TO APP (WA / IG / TG / X)', onclick: () => shareRoeNative(cv, cfg, m => { msgEl.textContent = m; }) }),
        h('button', { style: 'background:#0b1929;color:#00e5ff;border:1px solid #00e5ff88;padding:6px 12px;font-weight:700;cursor:pointer', text: 'COPY PNG', onclick: () => copyRoeImage(cv, m => { msgEl.textContent = m; }) }),
        h('button', { style: 'background:#061c10;color:#00d26a;border:1px solid #00d26a88;padding:6px 12px;font-weight:700;cursor:pointer', text: 'DOWNLOAD HD PNG', onclick: () => archiveAndDownloadRoe(cv, cfg, m => { msgEl.textContent = m; }) })
      )
    )
  );

  document.body.appendChild(overlay);
  redraw();
  candles = await fetchRoeSparkCandles(cfg.symbol);
  if (overlay.isConnected) redraw();
}

export function mountROE(body, ctx) {
  body.classList.add('fill');
  const tb = h('div', { class: 'tb' });
  const sc = h('div', { class: 'pb' });
  body.append(tb, sc);

  let unmounted = false;
  let feed = { fxRateIdr: 18218, openPositions: [], closedTrades: [], stats: {} };
  let candles = [];
  let msgTxt = '';

  const cleanInitSym = String(ctx.symbol || 'BTCUSDT').toUpperCase().replace('-USD', 'USDT').replace(/\.P$/, '');
  const state = {
    symbol: /USDT$/.test(cleanInitSym) ? cleanInitSym : 'BTCUSDT',
    direction: 'LONG',
    leverage: 20,
    marginMode: 'ISOLATED',
    entryPrice: 0,
    markPrice: 0,
    marginUsd: 25,
    roePct: 0,
    pnlUsd: 0,
    pnlIdr: 0,
    setup: 'QUANT_EXECUTION',
    status: 'OPEN',
    hybridConf: 78.5,
    aspect: '16:9',
    theme: 'CLASSIC',
    showPnlAmount: false
  };

  const previewCv = h('canvas', { style: 'width:100%;height:auto;max-height:420px;object-fit:contain;display:block;background:#030508;border:1px solid #1d2633' });
  const statusEl = h('div', { style: 'font-size:11px;color:#00d26a;min-height:16px;margin-top:5px' });

  function recalcFromPrices() {
    const e = Number(state.entryPrice) || 0;
    const m = Number(state.markPrice) || 0;
    const lev = Math.max(1, Number(state.leverage) || 20);
    const mUsd = Math.max(0, Number(state.marginUsd) || 0);
    if (e > 0 && m > 0) {
      const sgn = state.direction === 'SHORT' ? -1 : 1;
      state.roePct = +(sgn * ((m - e) / e) * lev * 100).toFixed(2);
      state.pnlUsd = +(mUsd * (state.roePct / 100)).toFixed(2);
      state.pnlIdr = Math.round(state.pnlUsd * (feed.fxRateIdr || 18218));
    }
  }

  async function applyTradeRecord(tr) {
    if (!tr) return;
    state.symbol = String(tr.symbol || 'BTCUSDT').toUpperCase();
    state.direction = String(tr.direction || 'LONG').toUpperCase() === 'SHORT' ? 'SHORT' : 'LONG';
    state.leverage = Number(tr.leverage || 20);
    state.marginMode = String(tr.marginMode || 'ISOLATED').toUpperCase();
    state.entryPrice = Number(tr.entryPrice || 0);
    state.markPrice = Number(tr.markPrice || tr.entryPrice || 0);
    state.marginUsd = Number(tr.marginUsd || state.marginUsd || 25);
    state.roePct = Number(tr.roePct || 0);
    state.pnlUsd = Number(tr.pnlUsd || 0);
    state.pnlIdr = Number(tr.pnlIdr || Math.round(state.pnlUsd * (feed.fxRateIdr || 18218)));
    state.setup = tr.setup || 'QUANT_EXECUTION';
    state.status = tr.status || 'OPEN';
    state.hybridConf = Number(tr.hybridConf || tr.pMath || 0);
    candles = await fetchRoeSparkCandles(state.symbol);
    if (!unmounted) renderBody();
  }

  function redrawCanvasOnly() {
    renderRoeCardCanvas(previewCv, { ...state, fxRateIdr: feed.fxRateIdr || 18218 }, candles);
  }

  function renderToolbar() {
    tb.textContent = '';
    tb.append(
      h('span', { class: 'lbl', text: 'ROE CARD STUDIO:' }),
      ...[['16:9', '16:9 DESK (1200x675)'], ['9:16', '9:16 STORY (1080x1920)']].map(([k, lbl]) => h('button', {
        class: state.aspect === k ? 'on' : '',
        text: lbl,
        onclick: () => { state.aspect = k; renderToolbar(); redrawCanvasOnly(); }
      })),
      ...['CLASSIC', 'GOLD', 'MATRIX'].map(t => h('button', {
        class: state.theme === t ? 'on' : '',
        text: t,
        onclick: () => { state.theme = t; renderToolbar(); redrawCanvasOnly(); }
      })),
      h('button', {
        class: state.showPnlAmount ? 'on' : '',
        text: state.showPnlAmount ? 'SHOWING USD/IDR PNL' : 'PRIVACY: ROE % ONLY',
        onclick: () => { state.showPnlAmount = !state.showPnlAmount; renderToolbar(); redrawCanvasOnly(); }
      }),
      h('button', { style: 'background:#ff6600;color:#000;border-color:#ff6600;font-weight:700', text: 'SHARE ROE', onclick: () => shareRoeNative(previewCv, { ...state, fxRateIdr: feed.fxRateIdr }, m => { msgTxt = m; statusEl.textContent = m; }) }),
      h('button', { style: 'color:#00d26a;border-color:#00d26a66', text: 'DOWNLOAD PNG', onclick: () => archiveAndDownloadRoe(previewCv, { ...state, fxRateIdr: feed.fxRateIdr }, m => { msgTxt = m; statusEl.textContent = m; }) }),
      h('button', { text: 'REFRESH', onclick: load })
    );
  }

  function renderBody() {
    sc.textContent = '';
    const st = feed.stats || {};
    const openList = Array.isArray(feed.openPositions) ? feed.openPositions : [];
    const closedList = Array.isArray(feed.closedTrades) ? feed.closedTrades : [];

    // Summary Strip
    sc.append(h('div', { class: 'xgrid4', style: 'margin-bottom:8px' },
      h('div', { class: 'xcard', style: 'margin-bottom:0;padding:6px 8px' },
        h('div', { class: 'mu', style: 'font-size:10px', text: 'LIVE OPEN POSITIONS' }),
        h('div', { class: 'am sym', style: 'font-size:15px;font-weight:700', text: `${openList.length} ACTIVE` })
      ),
      h('div', { class: 'xcard', style: 'margin-bottom:0;padding:6px 8px' },
        h('div', { class: 'mu', style: 'font-size:10px', text: 'AUDITED WIN RATE' }),
        h('div', { class: (Number(st.winRatePct) >= 50 ? 'up' : 'am') + ' sym', style: 'font-size:15px;font-weight:700', text: `${Number(st.winRatePct || 0).toFixed(1)}% (${st.totalClosed || 0} TRADES)` })
      ),
      h('div', { class: 'xcard', style: 'margin-bottom:0;padding:6px 8px' },
        h('div', { class: 'mu', style: 'font-size:10px', text: 'REALIZED NET P&L' }),
        h('div', { class: (Number(st.realizedPnlUsd) >= 0 ? 'up' : 'dn') + ' sym', style: 'font-size:15px;font-weight:700', text: `${Number(st.realizedPnlUsd || 0) >= 0 ? '+$' : '-$'}${Math.abs(Number(st.realizedPnlUsd || 0)).toFixed(2)} USD` })
      ),
      h('div', { class: 'xcard', style: 'margin-bottom:0;padding:6px 8px' },
        h('div', { class: 'mu', style: 'font-size:10px', text: 'LIVE USD / IDR FX' }),
        h('div', { class: 'lb sym', style: 'font-size:15px;font-weight:700', text: fmtIdr(feed.fxRateIdr || 18218) })
      )
    ));

    // Custom Parameter Inputs
    const symInp = h('input', { value: state.symbol, style: 'width:100%;text-transform:uppercase;font-weight:700' });
    const dirSel = h('select', { style: 'width:100%' },
      h('option', { value: 'LONG', selected: state.direction === 'LONG' ? 'selected' : null, text: 'LONG' }),
      h('option', { value: 'SHORT', selected: state.direction === 'SHORT' ? 'selected' : null, text: 'SHORT' })
    );
    const levInp = h('input', { type: 'number', value: String(state.leverage), style: 'width:100%' });
    const entInp = h('input', { type: 'number', step: 'any', value: String(state.entryPrice || ''), style: 'width:100%' });
    const mrkInp = h('input', { type: 'number', step: 'any', value: String(state.markPrice || ''), style: 'width:100%' });
    const mgnInp = h('input', { type: 'number', step: 'any', value: String(state.marginUsd || 25), style: 'width:100%' });
    const setInp = h('input', { value: state.setup, style: 'width:100%;text-transform:uppercase' });
    const cnfInp = h('input', { type: 'number', step: '0.1', value: String(state.hybridConf || 0), style: 'width:100%' });

    const syncEditor = async () => {
      const nextSym = (symInp.value || 'BTCUSDT').trim().toUpperCase().replace('-USD', 'USDT').replace(/\.P$/, '');
      const symChanged = nextSym !== state.symbol;
      state.symbol = nextSym;
      state.direction = dirSel.value;
      state.leverage = Math.max(1, Number(levInp.value) || 20);
      state.entryPrice = Number(entInp.value) || 0;
      state.markPrice = Number(mrkInp.value) || 0;
      state.marginUsd = Math.max(0, Number(mgnInp.value) || 0);
      state.setup = (setInp.value || 'QUANT_EXECUTION').trim().toUpperCase();
      state.hybridConf = Number(cnfInp.value) || 0;
      recalcFromPrices();
      if (symChanged) candles = await fetchRoeSparkCandles(state.symbol);
      redrawCanvasOnly();
    };

    const leftCol = h('div', { class: 'xcard', style: 'margin-bottom:0' },
      h('div', { class: 'xsec-hd' },
        h('span', { text: `HIGH-RESOLUTION ROE CARD PREVIEW (${state.aspect === '9:16' ? '1080x1920 STORY' : '1200x675 DESK'})` }),
        h('span', { class: state.roePct >= 0 ? 'up' : 'dn', text: `${state.roePct >= 0 ? '+' : ''}${Number(state.roePct).toFixed(2)}% ROE` })
      ),
      h('div', { style: 'padding:8px;background:#020408' }, previewCv),
      h('div', { style: 'padding:8px;display:flex;gap:6px;flex-wrap:wrap;border-top:1px solid var(--border)' },
        h('button', { style: 'background:#ff6600;color:#000;border-color:#ff6600;font-weight:700;padding:5px 10px', text: 'SHARE TO APP (WA / IG / TG / X)', onclick: () => shareRoeNative(previewCv, { ...state, fxRateIdr: feed.fxRateIdr }, m => { statusEl.textContent = m; }) }),
        h('button', { style: 'color:#00e5ff;border-color:#00e5ff77;padding:5px 10px', text: 'COPY IMAGE TO CLIPBOARD', onclick: () => copyRoeImage(previewCv, m => { statusEl.textContent = m; }) }),
        h('button', { style: 'color:#00d26a;border-color:#00d26a77;padding:5px 10px', text: 'DOWNLOAD HD PNG & ARCHIVE', onclick: () => archiveAndDownloadRoe(previewCv, { ...state, fxRateIdr: feed.fxRateIdr }, m => { statusEl.textContent = m; }) }),
        h('button', { style: 'padding:5px 10px', text: 'VIEW PNG ARCHIVE (G)', onclick: () => ctx.run(`${state.symbol} G`) })
      ),
      h('div', { style: 'padding:0 8px 6px' }, statusEl)
    );
    statusEl.textContent = msgTxt;

    const rightCol = h('div', { style: 'display:flex;flex-direction:column;gap:8px' });

    // Live Open Positions Selector
    const openCard = h('div', { class: 'xcard', style: 'margin-bottom:0' },
      h('div', { class: 'xsec-hd' }, h('span', { text: '1. LIVE BINANCE FUTURES POSITIONS (1-CLICK LOAD)' }), h('span', { class: 'am', text: `${openList.length} OPEN` }))
    );
    if (openList.length) {
      const tbl = h('table', { class: 't' },
        h('thead', {}, h('tr', {}, h('th', { text: 'CONTRACT' }), h('th', { text: 'SIDE' }), h('th', { text: 'ENTRY / MARK' }), h('th', { text: 'LIVE ROE' }), h('th', { text: 'CARD' })))
      );
      const tbod = h('tbody');
      openList.forEach(p => {
        tbod.append(h('tr', { class: 'row', onclick: () => applyTradeRecord(p) },
          h('td', { class: 'am sym', text: p.symbol }),
          h('td', { class: p.direction === 'LONG' ? 'up' : 'dn', text: `${p.direction} ${p.leverage}x` }),
          h('td', { text: `${fmtPx(p.entryPrice)} / ${fmtPx(p.markPrice)}` }),
          h('td', { class: dirCls(p.roePct) + ' sym', text: `${p.roePct >= 0 ? '+' : ''}${p.roePct.toFixed(2)}%` }),
          h('td', {}, h('button', { class: 'on', style: 'font-size:10px', text: 'LOAD ROE', onclick: ev => { ev.stopPropagation(); applyTradeRecord(p); } }))
        ));
      });
      tbl.append(tbod);
      openCard.append(tbl);
    } else {
      openCard.append(h('div', { style: 'padding:8px;font-size:11px;color:var(--muted)', text: 'No live open positions right now. Select a closed trade below or customize parameters.' }));
    }
    rightCol.append(openCard);

    // Closed Trades Selector
    const closedCard = h('div', { class: 'xcard', style: 'margin-bottom:0' },
      h('div', { class: 'xsec-hd' }, h('span', { text: '2. CLOSED EXECUTION HISTORY (AUDITED LEDGER)' }), h('span', { class: 'lb', text: `${closedList.length} RECORDS` }))
    );
    if (closedList.length) {
      const cWrap = h('div', { style: 'max-height:170px;overflow:auto' });
      const tbl = h('table', { class: 't' },
        h('thead', {}, h('tr', {}, h('th', { text: 'SYMBOL' }), h('th', { text: 'SIDE' }), h('th', { text: 'ENTRY / EXIT' }), h('th', { text: 'REALIZED ROE' }), h('th', { text: 'LOAD' })))
      );
      const tbod = h('tbody');
      closedList.slice(0, 20).forEach(t => {
        tbod.append(h('tr', { class: 'row', onclick: () => applyTradeRecord(t) },
          h('td', { class: 'am sym', text: t.symbol }),
          h('td', { class: t.direction === 'LONG' ? 'up' : 'dn', text: `${t.direction} ${t.leverage}x` }),
          h('td', { text: `${fmtPx(t.entryPrice)} / ${fmtPx(t.markPrice)}` }),
          h('td', { class: dirCls(t.roePct) + ' sym', text: `${t.roePct >= 0 ? '+' : ''}${t.roePct.toFixed(2)}%` }),
          h('td', {}, h('button', { style: 'font-size:10px', text: 'SELECT', onclick: ev => { ev.stopPropagation(); applyTradeRecord(t); } }))
        ));
      });
      tbl.append(tbod);
      cWrap.append(tbl);
      closedCard.append(cWrap);
    } else {
      closedCard.append(h('div', { style: 'padding:8px;font-size:11px;color:var(--muted)', text: 'No closed trades recorded in ledger yet.' }));
    }
    rightCol.append(closedCard);

    // Custom Card Precision Editor
    const editCard = h('div', { class: 'xcard', style: 'margin-bottom:0' },
      h('div', { class: 'xsec-hd' }, h('span', { text: '3. PRECISION CARD EDITOR / SIMULATION' }), h('span', { class: 'am', text: 'AUTO-ROE CALC' })),
      h('div', { style: 'padding:8px;display:grid;grid-template-columns:repeat(2,1fr);gap:6px;font-size:10.5px' },
        h('div', {}, h('div', { class: 'mu', text: 'CONTRACT SYMBOL' }), symInp),
        h('div', {}, h('div', { class: 'mu', text: 'DIRECTION' }), dirSel),
        h('div', {}, h('div', { class: 'mu', text: 'LEVERAGE (X)' }), levInp),
        h('div', {}, h('div', { class: 'mu', text: 'MARGIN SIZE (USDT)' }), mgnInp),
        h('div', {}, h('div', { class: 'mu', text: 'ENTRY PRICE ($)' }), entInp),
        h('div', {}, h('div', { class: 'mu', text: 'MARK / EXIT PRICE ($)' }), mrkInp),
        h('div', {}, h('div', { class: 'mu', text: 'STRATEGY / SETUP TAG' }), setInp),
        h('div', {}, h('div', { class: 'mu', text: 'QUANT CONFIDENCE (%)' }), cnfInp)
      ),
      h('div', { style: 'padding:0 8px 8px;display:flex;justify-content:flex-end' },
        h('button', { class: 'on', text: 'UPDATE ROE CARD PREVIEW', onclick: syncEditor })
      )
    );
    rightCol.append(editCard);

    sc.append(h('div', { class: 'xgrid2' }, leftCol, rightCol));
    redrawCanvasOnly();
  }

  async function load() {
    renderToolbar();
    try {
      const r = await apiFetch('/api/terminal/roe-feed', { skipAuthModal: false }, 10000);
      if (r.ok) {
        const j = await r.json();
        if (j && j.ok && j.data) feed = j.data;
      }
    } catch {}
    if (unmounted) return;

    if (feed.openPositions && feed.openPositions.length) {
      const match = feed.openPositions.find(p => p.symbol === state.symbol) || feed.openPositions[0];
      await applyTradeRecord(match);
    } else if (feed.closedTrades && feed.closedTrades.length && state.entryPrice <= 0) {
      await applyTradeRecord(feed.closedTrades[0]);
    } else {
      candles = await fetchRoeSparkCandles(state.symbol);
      if (candles.length >= 2 && state.entryPrice <= 0) {
        const firstPx = Number(candles[Math.max(0, candles.length - 18)].c ?? candles[0].close ?? 0);
        const lastPx = Number(candles[candles.length - 1].c ?? candles[candles.length - 1].close ?? 0);
        if (firstPx > 0 && lastPx > 0) {
          state.direction = lastPx >= firstPx ? 'LONG' : 'SHORT';
          state.entryPrice = firstPx;
          state.markPrice = lastPx;
          state.status = 'SIMULATED';
          recalcFromPrices();
        }
      }
      if (!unmounted) renderBody();
    }
    ctx.status({ ok: true, source: 'execution-roe-desk', ts: Date.now(), mode: 'LIVE' });
  }

  load();
  ctx.cleanup(() => { unmounted = true; });
}

// =====================================================================
// 9. TECH / MTF — MULTI-TIMEFRAME TECHNICAL CONSENSUS MATRIX & PIVOTS
// =====================================================================
function analyzeTfCandles(raw) {
  const list = Array.isArray(raw) ? raw.map(c => ({
    o: Number(c.o ?? c.open ?? 0),
    h: Number(c.h ?? c.high ?? 0),
    l: Number(c.l ?? c.low ?? 0),
    c: Number(c.c ?? c.close ?? 0),
    v: Number(c.v ?? c.volume ?? 0)
  })).filter(c => c.c > 0) : [];

  if (list.length < 25) return null;
  const closes = list.map(c => c.c);
  const last = closes[closes.length - 1];

  // 1. RSI(14)
  const rsi = calcMiniRsi14(closes);
  const rsiSig = rsi <= 30 ? ['OVERSOLD BUY', 1] : rsi >= 70 ? ['OVERBOUGHT SELL', -1] : rsi >= 54 ? ['BULLISH', 1] : rsi <= 46 ? ['BEARISH', -1] : ['NEUTRAL', 0];

  // 2. EMA 20 / 50
  const emaOf = (p) => {
    const k = 2 / (p + 1);
    let e = closes[0];
    for (let i = 1; i < closes.length; i++) e = closes[i] * k + e * (1 - k);
    return e;
  };
  const ema20 = emaOf(20), ema50 = emaOf(50);
  const emaSig = (last > ema20 && ema20 > ema50) ? ['GOLDEN BULL', 1]
    : (last < ema20 && ema20 < ema50) ? ['DEATH BEAR', -1]
    : (last > ema20 ? ['ABOVE EMA20', 0.5] : ['BELOW EMA20', -0.5]);

  // 3. MACD (12, 26, 9)
  const k12 = 2 / 13, k26 = 2 / 27, k9 = 2 / 10;
  let e12 = closes[0], e26 = closes[0], macdLine = 0, sigLine = 0;
  for (let i = 1; i < closes.length; i++) {
    e12 = closes[i] * k12 + e12 * (1 - k12);
    e26 = closes[i] * k26 + e26 * (1 - k26);
    macdLine = e12 - e26;
    sigLine = i === 1 ? macdLine : macdLine * k9 + sigLine * (1 - k9);
  }
  const hist = macdLine - sigLine;
  const macdSig = (hist > 0 && macdLine > 0) ? ['BULL +HIST', 1]
    : (hist > 0) ? ['BULL RECOV', 0.5]
    : (hist < 0 && macdLine < 0) ? ['BEAR -HIST', -1]
    : ['BEAR FADE', -0.5];

  // 4. SuperTrend (10, 3.0)
  const period = 10, mult = 3.0;
  let atr = list[0].h - list[0].l;
  let upBand = 0, dnBand = 0, stDir = 1, stVal = last;
  for (let i = 1; i < list.length; i++) {
    const tr = Math.max(list[i].h - list[i].l, Math.abs(list[i].h - list[i - 1].c), Math.abs(list[i].l - list[i - 1].c));
    atr = (atr * (period - 1) + tr) / period;
    const hl2 = (list[i].h + list[i].l) / 2;
    const bUp = hl2 + mult * atr;
    const bLo = hl2 - mult * atr;
    upBand = (i === 1 || bUp < upBand || list[i - 1].c > upBand) ? bUp : upBand;
    dnBand = (i === 1 || bLo > dnBand || list[i - 1].c < dnBand) ? bLo : dnBand;
    if (stDir === 1 && list[i].c < dnBand) stDir = -1;
    else if (stDir === -1 && list[i].c > upBand) stDir = 1;
    stVal = stDir === 1 ? dnBand : upBand;
  }
  const stSig = stDir === 1 ? [`BUY > ${fmtPx(stVal)}`, 1] : [`SELL < ${fmtPx(stVal)}`, -1];

  // 5. Bollinger (20, 2) %B & Bandwidth
  const tail20 = closes.slice(-20);
  const mean20 = tail20.reduce((s, v) => s + v, 0) / 20;
  const sd20 = Math.sqrt(tail20.reduce((s, v) => s + (v - mean20) ** 2, 0) / 20);
  const bbUp = mean20 + 2 * sd20, bbLo = mean20 - 2 * sd20;
  const pctB = bbUp > bbLo ? ((last - bbLo) / (bbUp - bbLo)) * 100 : 50;
  const bwPct = mean20 > 0 ? ((bbUp - bbLo) / mean20) * 100 : 0;
  const sqz = bwPct < 2.2 ? ' [SQZ]' : '';
  const bbSig = pctB >= 85 ? [`UPPER BREAK${sqz}`, 1]
    : pctB >= 55 ? [`BULL ZONE (${pctB.toFixed(0)}%)${sqz}`, 0.5]
    : pctB <= 15 ? [`LOWER STRETCH${sqz}`, -1]
    : pctB <= 45 ? [`BEAR ZONE (${pctB.toFixed(0)}%)${sqz}`, -0.5]
    : [`MID BAND${sqz}`, 0];

  // 6. 20-Bar Market Structure (BOS)
  const prior = list.slice(-21, -1);
  const hi20 = Math.max(...prior.map(x => x.h));
  const lo20 = Math.min(...prior.map(x => x.l));
  const mid20 = (hi20 + lo20) / 2;
  const bosSig = last > hi20 ? ['BOS HIGH BREAK', 1]
    : last < lo20 ? ['BOS LOW BREAK', -1]
    : last >= mid20 ? ['UPPER STRUCT', 0.5]
    : ['LOWER STRUCT', -0.5];

  const rawScore = ((rsiSig[1] + emaSig[1] + macdSig[1] + stSig[1] + bbSig[1] + bosSig[1]) / 6) * 100;
  const rating = rawScore >= 55 ? 'STRONG BUY' : rawScore >= 20 ? 'BUY' : rawScore <= -55 ? 'STRONG SELL' : rawScore <= -20 ? 'SELL' : 'NEUTRAL';

  return {
    last,
    rsi, rsiSig,
    ema20, ema50, emaSig,
    hist, macdSig,
    stVal, stSig,
    pctB, bwPct, bbSig,
    hi20, lo20, bosSig,
    score: +rawScore.toFixed(1),
    rating,
    prevBar: list[list.length - 2] || list[list.length - 1]
  };
}

function buildTechGaugeSvg(score, label, subtitle) {
  const clamped = Math.max(-100, Math.min(100, Number(score) || 0));
  const norm = (clamped + 100) / 200; // 0..1
  const ang = Math.PI + norm * Math.PI; // PI..2PI
  const cx = 170, cy = 122, r = 86;
  const nx = cx + (r - 12) * Math.cos(ang);
  const ny = cy + (r - 12) * Math.sin(ang);
  const col = clamped >= 55 ? '#00d26a' : clamped >= 20 ? '#4cd964' : clamped <= -55 ? '#ff453a' : clamped <= -20 ? '#ff7b72' : '#ffb000';

  const arcSeg = (a0, a1, stroke) => {
    const x0 = cx + r * Math.cos(a0), y0 = cy + r * Math.sin(a0);
    const x1 = cx + r * Math.cos(a1), y1 = cy + r * Math.sin(a1);
    return `<path d="M ${x0.toFixed(1)} ${y0.toFixed(1)} A ${r} ${r} 0 0 1 ${x1.toFixed(1)} ${y1.toFixed(1)}" fill="none" stroke="${stroke}" stroke-width="14"/>`;
  };

  return `<svg viewBox="0 0 340 165" style="width:100%;height:auto;display:block;background:#05080d">
    ${arcSeg(Math.PI, Math.PI * 1.2, '#ff453a')}
    ${arcSeg(Math.PI * 1.21, Math.PI * 1.4, '#ff8c42')}
    ${arcSeg(Math.PI * 1.41, Math.PI * 1.59, '#ffb000')}
    ${arcSeg(Math.PI * 1.60, Math.PI * 1.79, '#32d74b')}
    ${arcSeg(Math.PI * 1.80, Math.PI * 2.0, '#00d26a')}
    <line x1="${cx}" y1="${cy}" x2="${nx.toFixed(1)}" y2="${ny.toFixed(1)}" stroke="#ffffff" stroke-width="2.6"/>
    <circle cx="${cx}" cy="${cy}" r="5" fill="${col}" stroke="#fff" stroke-width="1.5"/>
    <text x="24" y="132" fill="#ff5a52" font-size="9" font-family="monospace" font-weight="bold">STRONG SELL</text>
    <text x="316" y="132" fill="#00d26a" font-size="9" font-family="monospace" font-weight="bold" text-anchor="end">STRONG BUY</text>
    <text x="${cx}" y="94" fill="${col}" font-size="16" font-family="monospace" font-weight="900" text-anchor="middle">${esc(label)}</text>
    <text x="${cx}" y="146" fill="#e6edf3" font-size="11" font-family="monospace" font-weight="bold" text-anchor="middle">COMPOSITE SCORE: ${clamped >= 0 ? '+' : ''}${clamped.toFixed(1)} / 100</text>
    <text x="${cx}" y="160" fill="#7d8b9e" font-size="9" font-family="monospace" text-anchor="middle">${esc(subtitle || '')}</text>
  </svg>`;
}

export function mountTECH(body, ctx) {
  body.classList.add('fill');
  const tb = h('div', { class: 'tb' });
  const sc = h('div', { class: 'pb' });
  body.append(tb, sc);

  let sym = ctx.symbol || 'BTCUSDT';
  let unmounted = false;
  const TFS = [
    { iv: '5m', label: '5 MIN (SCALP)', weight: 0.12 },
    { iv: '15m', label: '15 MIN (INTRADAY)', weight: 0.18 },
    { iv: '1h', label: '1 HOUR (SWING)', weight: 0.25 },
    { iv: '4h', label: '4 HOUR (REGIME)', weight: 0.25 },
    { iv: '1d', label: '1 DAY (MACRO)', weight: 0.20 }
  ];

  function renderToolbar() {
    tb.textContent = '';
    const inp = h('input', { value: sym, style: 'width:105px;text-transform:uppercase;font-weight:700' });
    tb.append(
      h('span', { class: 'lbl', text: 'MULTI-TF TECHNICAL MATRIX:' }),
      inp,
      h('button', { class: 'on', text: 'SCAN MTF', onclick: () => { sym = inp.value.trim().toUpperCase() || sym; ctx.setSymbol(sym); load(); } }),
      ...['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'NVDA', 'GC=F'].map(s => h('button', {
        class: sym === s ? 'on' : '', text: s, onclick: () => { sym = s; ctx.setSymbol(s); renderToolbar(); load(); }
      })),
      h('button', { style: 'color:#ffb000;border-color:#ffb00066', text: 'OPEN GP CHART', onclick: () => ctx.run(`${sym} GP`) }),
      h('button', { style: 'color:#00d26a;border-color:#00d26a66', text: 'SHARE ROE', onclick: () => ctx.run(`${sym} ROE`) })
    );
  }

  async function load() {
    renderToolbar();
    sc.textContent = '';
    sc.append(h('div', { class: 'na', text: `Computing 5-Timeframe x 6-Indicator Technical Matrix for ${sym}...` }));

    const cleanSym = sym.replace(/\.P$/, '');
    const results = await Promise.all(TFS.map(async t => {
      const env = await get('kline', { symbol: cleanSym, interval: t.iv, limit: 100 }, 4000);
      const arr = env && env.ok ? (Array.isArray(env.data) ? env.data : (env.data && env.data.candles) || []) : [];
      return { ...t, env, analysis: analyzeTfCandles(arr) };
    }));
    if (unmounted) return;
    sc.textContent = '';

    const valid = results.filter(r => r.analysis);
    if (!valid.length) {
      sc.append(h('div', { class: 'na', text: `Insufficient OHLCV history to compute Multi-Timeframe Matrix for ${sym}.` }));
      ctx.status({ ok: false, source: 'mtf-tech', ts: Date.now(), mode: 'N/A' });
      return;
    }

    const totalW = valid.reduce((s, r) => s + r.weight, 0) || 1;
    const weightedScore = valid.reduce((s, r) => s + r.analysis.score * r.weight, 0) / totalW;
    const masterRating = weightedScore >= 50 ? 'STRONG BUY' : weightedScore >= 18 ? 'BUY' : weightedScore <= -50 ? 'STRONG SELL' : weightedScore <= -18 ? 'SELL' : 'NEUTRAL';
    const buyTfs = valid.filter(r => r.analysis.score >= 18).length;
    const sellTfs = valid.filter(r => r.analysis.score <= -18).length;
    const lastPx = valid[0].analysis.last;

    // Classic & Fibonacci Pivots from 1D prior candle (or highest TF available)
    const dailyRec = results.find(r => r.iv === '1d' && r.analysis) || valid[valid.length - 1];
    const pb = dailyRec.analysis.prevBar;
    const P = (pb.h + pb.l + pb.c) / 3;
    const rng = Math.max(1e-8, pb.h - pb.l);
    const pivots = {
      classic: { r3: pb.h + 2 * (P - pb.l), r2: P + rng, r1: 2 * P - pb.l, p: P, s1: 2 * P - pb.h, s2: P - rng, s3: pb.l - 2 * (pb.h - P) },
      fib: { r3: P + 1.0 * rng, r2: P + 0.618 * rng, r1: P + 0.382 * rng, p: P, s1: P - 0.382 * rng, s2: P - 0.618 * rng, s3: P - 1.0 * rng }
    };

    // Top Row: Semicircular Gauge + Daily Pivot Ladder
    const pivotTbl = h('table', { class: 't' },
      h('thead', {}, h('tr', {}, h('th', { text: 'LEVEL' }), h('th', { text: 'CLASSIC FLOOR' }), h('th', { text: 'FIBONACCI' }), h('th', { text: 'DIST VS SPOT' })))
    );
    const pBody = h('tbody');
    [['R3', 'r3', 'dn'], ['R2', 'r2', 'dn'], ['R1', 'r1', 'am'], ['PIVOT (P)', 'p', 'lb'], ['S1', 's1', 'am'], ['S2', 's2', 'up'], ['S3', 's3', 'up']].forEach(([lbl, k, cls]) => {
      const cp = pivots.classic[k];
      const fp = pivots.fib[k];
      const distPct = lastPx > 0 ? ((cp - lastPx) / lastPx) * 100 : 0;
      pBody.append(h('tr', {},
        h('td', { class: cls + ' sym', text: lbl }),
        h('td', { text: fmtPx(cp) }),
        h('td', { text: fmtPx(fp) }),
        h('td', { class: dirCls(distPct), text: fmtPct(distPct) })
      ));
    });
    pivotTbl.append(pBody);

    sc.append(h('div', { class: 'xgrid2', style: 'margin-bottom:8px' },
      h('div', { class: 'xcard', style: 'margin-bottom:0' },
        h('div', { class: 'xsec-hd' },
          h('span', { text: `MULTI-TIMEFRAME CONSENSUS [${sym}]` }),
          h('span', { class: 'am sym', text: `SPOT $${fmtPx(lastPx)}` })
        ),
        makeSvgBox(buildTechGaugeSvg(weightedScore, masterRating, `${buyTfs} BULLISH TFs  •  ${valid.length - buyTfs - sellTfs} NEUTRAL  •  ${sellTfs} BEARISH TFs`))
      ),
      h('div', { class: 'xcard', style: 'margin-bottom:0' },
        h('div', { class: 'xsec-hd' },
          h('span', { text: 'INSTITUTIONAL PIVOT LEVELS (PRIOR DAILY BAR)' }),
          h('span', { class: lastPx >= P ? 'up' : 'dn', text: lastPx >= P ? 'ABOVE DAILY PIVOT' : 'BELOW DAILY PIVOT' })
        ),
        pivotTbl
      )
    ));

    // Full 5x6 Multi-Timeframe Signal Heatmap Table
    const cellCls = v => v > 0 ? 'background:rgba(0,210,106,0.13);color:#00d26a;font-weight:700' : v < 0 ? 'background:rgba(255,69,58,0.13);color:#ff5a52;font-weight:700' : 'color:#9aa7b8';
    const mTbl = h('table', { class: 't' },
      h('thead', {}, h('tr', {},
        h('th', { text: 'TIMEFRAME' }),
        h('th', { text: 'RSI (14)' }),
        h('th', { text: 'EMA 20 / 50' }),
        h('th', { text: 'MACD (12,26,9)' }),
        h('th', { text: 'SUPERTREND (10,3)' }),
        h('th', { text: 'BOLLINGER (20,2)' }),
        h('th', { text: '20-BAR STRUCTURE' }),
        h('th', { text: 'TF VERDICT' })
      ))
    );
    const mBody = h('tbody');
    results.forEach(r => {
      const a = r.analysis;
      if (!a) {
        mBody.append(h('tr', {}, h('td', { class: 'am', text: r.label }), h('td', { colspan: '7', class: 'mu', text: 'N/A' })));
        return;
      }
      const rCls = a.score >= 20 ? 'up' : a.score <= -20 ? 'dn' : 'am';
      mBody.append(h('tr', {},
        h('td', { class: 'am sym', text: r.label }),
        h('td', { style: cellCls(a.rsiSig[1]), text: `${a.rsi.toFixed(1)} • ${a.rsiSig[0]}` }),
        h('td', { style: cellCls(a.emaSig[1]), text: a.emaSig[0] }),
        h('td', { style: cellCls(a.macdSig[1]), text: a.macdSig[0] }),
        h('td', { style: cellCls(a.stSig[1]), text: a.stSig[0] }),
        h('td', { style: cellCls(a.bbSig[1]), text: a.bbSig[0] }),
        h('td', { style: cellCls(a.bosSig[1]), text: a.bosSig[0] }),
        h('td', { class: rCls + ' sym', text: `${a.rating} (${a.score >= 0 ? '+' : ''}${a.score})` })
      ));
    });
    mTbl.append(mBody);

    sc.append(h('div', { class: 'xcard' },
      h('div', { class: 'xsec-hd' },
        h('span', { text: '5-TIMEFRAME X 6-STUDY SIGNAL CONFLUENCE MATRIX' }),
        h('span', { class: 'lb', text: 'WEIGHTED: 1H (25%) + 4H (25%) + 1D (20%) + 15M (18%) + 5M (12%)' })
      ),
      mTbl
    ));
    ctx.status({ ok: true, source: 'mtf-technical-engine', ts: Date.now(), mode: 'LIVE' });
  }

  load();
  ctx.cleanup(() => { unmounted = true; });
}

// =====================================================================
// 10. BRDT / DOMI — MARKET BREADTH, VOLUME DOMINANCE & MACRO REGIME
// =====================================================================
export function mountBRDT(body, ctx) {
  body.classList.add('fill');
  const tb = h('div', { class: 'tb' });
  const sc = h('div', { class: 'pb' });
  body.append(tb, sc);

  let unmounted = false;

  function renderToolbar() {
    tb.textContent = '';
    tb.append(
      h('span', { class: 'lbl', text: 'MARKET INTERNALS, BREADTH & DOMINANCE:' }),
      h('button', { class: 'on', text: 'REFRESH INTERNALS', onclick: load }),
      h('button', { text: 'HEATMAP (IMAP)', onclick: () => ctx.run('BTCUSDT IMAP') }),
      h('button', { text: 'SECTOR RRG', onclick: () => ctx.run('BTCUSDT RRG') }),
      h('button', { text: 'ETF FLOWS', onclick: () => ctx.run('BTCUSDT ETF') }),
      h('button', { text: 'MTF TECH', onclick: () => ctx.run(`${ctx.symbol} TECH`) })
    );
  }

  async function load() {
    renderToolbar();
    const env = await get('breadth', {}, 5000);
    if (unmounted) return;
    ctx.status(env);
    sc.textContent = '';

    if (!env.ok || !env.data) {
      sc.append(h('div', { class: 'na', text: 'Market breadth feed temporarily unavailable.' }));
      return;
    }

    const d = env.data;
    const br = d.breadth || {};
    const dom = Array.isArray(d.dominance) ? d.dominance : [];
    const macro = Array.isArray(d.macroPulse) ? d.macroPulse : [];
    const members = Array.isArray(d.constituents) ? d.constituents : [];
    const riskScore = (Number(d.riskAppetite || 50) - 50) * 2; // Map 0..100 -> -100..+100 for gauge

    const totalU = Math.max(1, Number(br.universeCount || 16));
    const advW = ((br.advancers || 0) / totalU) * 100;
    const uncW = ((br.unchanged || 0) / totalU) * 100;
    const decW = ((br.decliners || 0) / totalU) * 100;

    // Top Row: Risk Appetite Gauge + Breadth & Dominance Stacked Bars
    const internalsBox = h('div', { class: 'xcard', style: 'margin-bottom:0;padding:8px' },
      h('div', { class: 'xsec-hd', style: 'margin:-8px -8px 8px -8px' },
        h('span', { text: 'ADVANCERS / DECLINERS & VOLUME DOMINANCE' }),
        h('span', { class: 'am sym', text: `A/D RATIO: ${br.advDeclRatio ?? 1.0}` })
      ),
      h('div', { style: 'font-size:11px;display:flex;justify-content:space-between;margin-bottom:4px' },
        h('span', { class: 'up sym', text: `ADVANCERS: ${br.advancers || 0} (${br.breadthPct || 0}%)` }),
        h('span', { class: 'mu', text: `UNCHANGED: ${br.unchanged || 0}` }),
        h('span', { class: 'dn sym', text: `DECLINERS: ${br.decliners || 0}` })
      ),
      h('div', { style: 'display:flex;height:16px;width:100%;background:#11161f;border:1px solid #232d3d;margin-bottom:10px;overflow:hidden' },
        h('div', { style: `width:${advW}%;background:#00d26a` }),
        h('div', { style: `width:${uncW}%;background:#5c687a` }),
        h('div', { style: `width:${decW}%;background:#ff453a` })
      ),
      h('div', { style: 'font-size:10.5px;color:#9aa7b8;margin-bottom:10px;display:flex;justify-content:space-between' },
        h('span', { text: `STRONG BREAKOUTS (>+2.5%): ${br.strongUp || 0}` }),
        h('span', { text: `ABOVE INTRADAY MID: ${br.upperRangePct || 0}%` }),
        h('span', { text: `DEEP SELLOFFS (<-2.5%): ${br.strongDn || 0}` })
      ),
      h('div', { class: 'mu', style: 'font-size:10px;margin-bottom:4px;font-weight:700', text: 'INSTITUTIONAL DOLLAR-VOLUME DOMINANCE SHARE:' }),
      h('div', { style: 'display:flex;height:18px;width:100%;border:1px solid #232d3d;margin-bottom:8px;overflow:hidden' },
        ...dom.map(seg => h('div', { style: `width:${seg.pct}%;background:${seg.color}`, title: `${seg.label}: ${seg.pct}%` }))
      ),
      h('div', { style: 'display:grid;grid-template-columns:repeat(2,1fr);gap:4px;font-size:10.5px' },
        ...dom.map(seg => h('div', { style: 'display:flex;justify-content:space-between;background:#06090f;padding:3px 6px;border-left:3px solid ' + seg.color },
          h('span', { text: seg.label }),
          h('b', { style: `color:${seg.color}`, text: `${seg.pct}% (${fmtUsdShort(seg.dollarVol).replace(/^\+/, '')})` })
        ))
      )
    );

    sc.append(h('div', { class: 'xgrid2', style: 'margin-bottom:8px' },
      h('div', { class: 'xcard', style: 'margin-bottom:0' },
        h('div', { class: 'xsec-hd' },
          h('span', { text: 'CROSS-ASSET RISK-ON / RISK-OFF REGIME' }),
          h('span', { class: d.riskAppetite >= 55 ? 'up' : d.riskAppetite <= 45 ? 'dn' : 'am', text: `INDEX ${d.riskAppetite}/100` })
        ),
        makeSvgBox(buildTechGaugeSvg(riskScore, d.regimeLabel || 'BALANCED REGIME', 'COMPOSITE OF CRYPTO BREADTH + S&P 500 + GOLD + US10Y'))
      ),
      internalsBox
    ));

    // Cross-Asset Macro Pulse Strip
    if (macro.length) {
      sc.append(
        h('div', { class: 'xcard', style: 'margin-bottom:8px' },
          h('div', { class: 'xsec-hd' }, h('span', { text: 'CROSS-ASSET MACRO BENCHMARK PULSE' }), h('span', { class: 'lb', text: 'EQUITIES • GOLD • OIL • TREASURIES • FX' })),
          h('div', { style: 'display:grid;grid-template-columns:repeat(6,1fr);gap:6px;padding:6px' },
            ...macro.map(m => h('div', {
              style: 'background:#06090f;border:1px solid #1b2432;padding:6px;cursor:pointer',
              onclick: () => ctx.run(`${m.symbol} GP`)
            },
              h('div', { class: 'mu', style: 'font-size:9.5px', text: m.role }),
              h('div', { class: 'am sym', style: 'font-size:11px;font-weight:700', text: m.name }),
              h('div', { style: 'font-size:12.5px;font-weight:700;color:#fff;margin-top:2px', text: fmtPx(m.price) }),
              h('div', { class: dirCls(m.chgPct) + ' sym', style: 'font-size:11px', text: fmtPct(m.chgPct) })
            ))
          )
        )
      );
    }

    // 16-Asset Breadth Constituents Table
    const mTbl = h('table', { class: 't' },
      h('thead', {}, h('tr', {},
        h('th', { text: 'RANK' }),
        h('th', { text: 'CONTRACT' }),
        h('th', { text: 'LAST PRICE' }),
        h('th', { text: '24H CHANGE' }),
        h('th', { text: '24H DOLLAR VOL' }),
        h('th', { text: 'INTRADAY RANGE POS' }),
        h('th', { text: 'DRILLDOWN' })
      ))
    );
    const mBody = h('tbody');
    members.forEach((c, idx) => {
      mBody.append(h('tr', { class: 'row', onclick: () => ctx.run(`${c.symbol} GP`) },
        h('td', { class: 'mu', text: String(idx + 1) }),
        h('td', { class: 'am sym', text: c.symbol }),
        h('td', { text: '$' + fmtPx(c.price) }),
        h('td', { class: dirCls(c.chgPct) + ' sym', text: fmtPct(c.chgPct) }),
        h('td', { class: 'lb', text: fmtUsdShort(c.dollarVol).replace(/^\+/, '') }),
        h('td', {},
          h('div', { style: 'display:flex;align-items:center;gap:6px' },
            h('div', { style: 'width:70px;height:7px;background:#141b26;border:1px solid #273244' },
              h('div', { style: `width:${Math.max(2, Math.min(100, c.rangePos))}%;height:100%;background:${c.rangePos >= 55 ? '#00d26a' : '#ff5a52'}` })
            ),
            h('span', { style: 'font-size:10px', text: `${c.rangePos}%` })
          )
        ),
        h('td', {},
          h('button', { style: 'font-size:9.5px;margin-right:3px', text: 'GP', onclick: ev => { ev.stopPropagation(); ctx.run(`${c.symbol} GP`); } }),
          h('button', { style: 'font-size:9.5px', text: 'TECH', onclick: ev => { ev.stopPropagation(); ctx.run(`${c.symbol} TECH`); } })
        )
      ));
    });
    mTbl.append(mBody);

    sc.append(h('div', { class: 'xcard' },
      h('div', { class: 'xsec-hd' }, h('span', { text: 'INSTITUTIONAL CRYPTO UNIVERSE BREADTH LEADERBOARD' }), h('span', { class: 'am', text: `${members.length} LIQUID MAJORS` })),
      mTbl
    ));
  }

  load();
  ctx.cleanup(() => { unmounted = true; });
}
