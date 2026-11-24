import { h, fmtPx, fmtPct, fmtVol, fmtNum, fmtTime, dirCls, LS } from '../util.js';
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
  const neg = n < 0;
  return (neg ? '-Rp ' : 'Rp ') + Math.abs(n).toLocaleString('id-ID');
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
// SVG VISUAL DIAGRAMS (Radar, Waterfall, FPT Cone, Gauge, Cashflow, ETF)
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
      <text x="${W / 2}" y="${H / 2}" text-anchor="middle" fill="#6c788a" font-size="11" font-family="monospace">Belum ada level Entry / SL / TP untuk koin ini — jalankan scan atau pilih posisi aktif.</text>
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
    const upPts = [];
    const loPts = [];
    const midPts = [];
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
    // Synthesize visual sniper roadmap trajectory cone (Entry -> BE -> TP1 -> TP2)
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

function buildGaugeSvg(score = 50, subtitle = 'SCORE', overrideCol = null) {
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
    <text x="${cx}" y="${cy + 16}" text-anchor="middle" fill="#9aa7b8" font-size="9.5" font-weight="700" font-family="monospace">${esc(subtitle)}</text>
  </svg>`;
}

function buildCashflow14dSvg(days = [], dailyLimit = 100000) {
  const list = Array.isArray(days) ? days : [];
  const W = 580, H = 190, padL = 62, padR = 14, padT = 18, padB = 28;
  const maxVal = Math.max(dailyLimit * 1.25, ...list.map(d => Math.max(d.income || 0, d.expense || 0, d.savings || 0)), 10000);
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
      bars += `<rect x="${(gx + 4 + bw).toFixed(1)}" y="${(padT + plotH - expH).toFixed(1)}" width="${bw.toFixed(1)}" height="${expH.toFixed(1)}" fill="${over ? '#ff2d20' : '#ff8c42'}"><title>${d.date} Expense: ${fmtIdr(d.expense)}${over ? ' (OVER LIMIT!)' : ''}</title></rect>`;
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
    <text x="${padL + 6}" y="${Math.max(padT + 10, limY - 4).toFixed(1)}" fill="#ffb000" font-size="9" font-weight="700" font-family="monospace">BATAS HARIAN ANTI-BOROS: ${esc(fmtIdr(dailyLimit))}</text>
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
// 1. FACT / XRAY / PILLAR — 100% TRANSPARENT BOT GLASS-BOX X-RAY
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
      sc.append(h('div', { class: 'na', text: 'Gagal memuat data Glass-Box Bot: ' + (env.error || 'source down') }));
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
      h('span', { class: 'lbl', text: 'BOT GLASS-BOX X-RAY:' }),
      inp,
      h('button', { class: 'on', text: 'INSPECT <GO>', onclick: () => load(inp.value) }),
      ...['OVERVIEW', 'FUNNEL L1-L6', '24 PILLARS', '532 FACTORS'].map(t => h('button', {
        class: tab === t ? 'on' : '',
        text: t,
        onclick: () => { tab = t; renderToolbar(); renderBody(); }
      })),
      h('button', { style: 'color:#00e5ff;border-color:#00e5ff66', text: '🎙 TRANSKRIP', onclick: () => ctx.run(`${selectedSym} TRAN`) }),
      h('button', { style: 'color:#00d26a;border-color:#00d26a66', text: '📈 CHART GP', onclick: () => ctx.run(`${selectedSym} GP`) }),
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
    const gear = d.gear && d.gear.active_profile ? `GIGI ${d.gear.current_gear} (${d.gear.active_profile.leverage}x)` : 'GIGI 1 (20x)';
    const vaultUsd = Number((d.vault && d.vault.locked_profit_vault_usdt) || 0);

    // 1. Scanned Coin Selector Strip
    const strip = h('div', { style: 'display:flex;gap:4px;flex-wrap:wrap;margin-bottom:8px;align-items:center' },
      h('span', { class: 'lbl', style: 'font-size:10px', text: 'PILIH KOIN SCAN BOT:' })
    );
    if (pos) {
      const psym = String(pos.binance_pair || pos.symbol || '').toUpperCase();
      strip.append(h('button', {
        style: 'background:#072414;color:#00ff88;border-color:#00d26a;font-weight:700;font-size:10px',
        text: `🔴 OPEN LIVE: ${psym} ${pos.direction || ''}`,
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

    // 2. Top Transparent KPI Strip
    const pMath = Number(mp.p_math_pct ?? l5.math_score_pct ?? 0);
    const pAi = Number(mp.p_ai_pct ?? l2.probability_pct ?? 0);
    const sHyb = Number(mp.s_hybrid_pct ?? l5.confidence_score ?? 0);
    const fpt = Number((l3.tp_time_prediction && l3.tp_time_prediction.p_hit_tp1_before_sl_pct) || 0);
    const dir = String(l5.direction || l2.direction || (pos && pos.direction) || mp.preferred_direction || 'NONE').toUpperCase();
    const statusTxt = String(d.scanStatus || l5.status || 'IDLE').toUpperCase();

    sc.append(h('div', { class: 'xgrid4', style: 'margin-bottom:8px' },
      h('div', { class: 'xstat' },
        h('div', { class: 'xl', text: `STATUS (${d.symbol})` }),
        h('div', { class: 'xv', style: `color:${statusTxt.includes('APPROV') || pos ? 'var(--up)' : 'var(--amber)'};font-size:13px`, text: `${statusTxt} • ${dir}` }),
        h('div', { class: 'xs', text: `Regime: ${mp.statistical_regime || 'NORMAL'} • ${d.scanTimestamp ? String(d.scanTimestamp).slice(11, 19) : '-'}` })
      ),
      h('div', { class: 'xstat' },
        h('div', { class: 'xl', text: 'P_MATH / AI / HYBRID' }),
        h('div', { class: 'xv', style: 'color:var(--up);font-size:13px', text: `${pMath.toFixed(1)}% / ${pAi.toFixed(1)}% / ${sHyb.toFixed(1)}%` }),
        h('div', { class: 'xs', text: `Q532=${Number(mp.composite_532_factors || 50).toFixed(1)} | FPT P(TP1<SL)=${fpt.toFixed(1)}%` })
      ),
      h('div', { class: 'xstat' },
        h('div', { class: 'xl', text: 'GEAR & PROFIT VAULT' }),
        h('div', { class: 'xv', style: 'color:var(--amber);font-size:13px', text: `${gear}` }),
        h('div', { class: 'xs', text: `Wallet $${Number(d.walletUsdt || 0).toFixed(2)} | Vault $${vaultUsd.toFixed(2)}` })
      ),
      h('div', { class: 'xstat' },
        h('div', { class: 'xl', text: 'SETUP & CONFLUENCE' }),
        h('div', { class: 'xv', style: 'color:#00e5ff;font-size:12px', text: l2.setup_name || (pos && pos.setup_name) || 'WAIT_SETUP' }),
        h('div', { class: 'xs', text: `L4 Audit: ${l4.total_score || 0}/${l4.max_score || 8} • Open Pos: ${d.openPositionsCount || 0}` })
      )
    ));

    if (tab === 'OVERVIEW') {
      // Active position / trade reasoning card
      const entryPx = Number(l5.entry_price || l3.entry_price || (pos && pos.entry_price) || l1.current_price || 0);
      const slPx = Number(l5.stop_loss || l3.stop_loss || (pos && pos.stop_loss) || 0);
      const tp1Px = Number(l5.take_profit_1 || l3.take_profit_1 || (pos && pos.take_profit_1) || 0);
      const tp2Px = Number(l5.take_profit_2 || l5.take_profit || l3.take_profit_2 || (pos && pos.take_profit_2) || 0);

      sc.append(h('div', { class: 'xcard xcard-hi' },
        h('div', { class: 'xsec-hd' },
          h('span', { text: `TRANSPARENSI KEPUTUSAN BOT — ${d.symbol} (${dir})` }),
          h('span', { class: `xpill ${statusTxt.includes('APPROV') || pos ? 'ok' : 'warn'}`, text: pos ? 'POSISI LIVE AKTIF DI BINANCE' : statusTxt })
        ),
        h('div', { style: 'padding:6px 4px;font-size:11px;line-height:1.45;color:#e6edf3' },
          h('div', { text: `Alasan Keputusan Layer 5: ${l5.final_reason || (pos ? 'Posisi telah lulus seluruh filter Layer 1-6 dan aktif dengan proteksi SL + Maker TP1.' : 'Menunggu seluruh syarat matematis & AI selaras.')}` }),
          h('div', { style: 'margin-top:4px;color:var(--label)', text: `Entry: $${fmtPx(entryPx)}  |  SL: $${fmtPx(slPx)}  |  TP1 (50% Lock): $${fmtPx(tp1Px)}  |  TP2 Runner: $${fmtPx(tp2Px)}  |  ETA: ${(l3.tp_time_prediction && l3.tp_time_prediction.eta_label) || '-'}` })
        )
      ));

      // Visual Diagrams: Radar + Waterfall
      sc.append(h('div', { class: 'xgrid2', style: 'margin-bottom:8px' },
        h('div', { class: 'xcard', style: 'margin-bottom:0' },
          h('div', { class: 'xsec-hd' }, h('span', { text: '8-AXIS BOT DECISION RADAR DIAGRAM' }), h('span', { class: 'am', text: 'LIVE TELEMETRY' })),
          makeSvgBox(buildRadarSvg(d.radarAxes))
        ),
        h('div', { class: 'xcard', style: 'margin-bottom:0' },
          h('div', { class: 'xsec-hd' }, h('span', { text: 'P_MATH CONTRIBUTION WATERFALL CHART' }), h('span', { class: 'up', text: 'FORMULA TRANSPAREN' })),
          makeSvgBox(buildWaterfallSvg(d.waterfall, pMath))
        )
      ));

      // FPT Trajectory Cone + Sniper Ladder
      sc.append(h('div', { class: 'xcard' },
        h('div', { class: 'xsec-hd' },
          h('span', { text: 'FIRST-PASSAGE TIME (FPT) TRAJECTORY CONE & SNIPER LADDER (SL → ENTRY → BE → TP1 → TP2)' }),
          h('span', { class: 'up', text: `P(TP1 < SL) = ${fpt.toFixed(1)}%` })
        ),
        makeSvgBox(buildFptConeSvg(d.trajectoryCone, entryPx, slPx, tp1Px, tp2Px, dir))
      ));

      // 3-Brain Neuro-Symbolic + Compact Funnel
      const ns = d.neuroSymbolic || {};
      sc.append(h('div', { class: 'xgrid3', style: 'margin-bottom:8px' },
        h('div', { class: 'xstat' },
          h('div', { class: 'xl', text: 'BRAIN #1: TABULAR QUANT ML' }),
          h('div', { class: 'xv', style: 'color:#00e5ff', text: `${ns.brain1_tabular_prob_pct ?? pMath.toFixed(1)}%` }),
          h('div', { class: 'xs', text: '532-Factor + Orderbook + Regime' })
        ),
        h('div', { class: 'xstat' },
          h('div', { class: 'xl', text: 'BRAIN #2: EPISODIC k-NN MEMORY' }),
          h('div', { class: 'xv', style: 'color:#ffb000', text: `${ns.brain2_episodic_knn_prob_pct ?? 'N/A'}%` }),
          h('div', { class: 'xs', text: `Closed Memory: ${(d.aiMemorySummary && d.aiMemorySummary.totalClosed) || 0} trades` })
        ),
        h('div', { class: 'xstat' },
          h('div', { class: 'xl', text: 'BRAIN #3: LLM META-JUDGE' }),
          h('div', { class: 'xv', style: 'color:#00d26a', text: `${ns.brain3_llm_prob_pct ?? pAi.toFixed(1)}%` }),
          h('div', { class: 'xs', text: 'Multi-Agent Committee + Risk Audit' })
        )
      ));

      // Compact Pipeline Stages preview
      const fBox = h('div', { class: 'xcard' },
        h('div', { class: 'xsec-hd' },
          h('span', { text: 'PROSES KERJA BOT LAYER 1 → LAYER 6 (RINGKASAN)' }),
          h('button', { style: 'font-size:10px', text: 'LIHAT DETAIL FUNNEL →', onclick: () => { tab = 'FUNNEL L1-L6'; renderToolbar(); renderBody(); } })
        )
      );
      (d.pipelineStages || []).forEach(st => {
        fBox.append(h('div', { style: 'display:flex;justify-content:space-between;align-items:center;gap:8px;padding:5px 6px;border-bottom:1px solid #161a22' },
          h('div', {},
            h('span', { class: `xpill ${st.passed ? 'ok' : 'no'}`, text: st.passed ? 'PASS' : 'HOLD/FAIL' }),
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
              h('span', { class: `xpill ${st.passed ? 'ok' : 'no'}`, text: st.passed ? '✓ PASSED' : '✕ BLOCKED / WAITING' }),
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
            h('span', { text: 'HASIL SIDANG 9-AGENT COMMITTEE TERAKHIR' }),
            h('button', { class: 'on', text: 'BUKA TRANSKRIP LENGKAP (TRAN) →', onclick: () => ctx.run(`${selectedSym} TRAN`) })
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
          h('th', { text: 'PILLAR / SENSOR BOT' }),
          h('th', { text: 'NILAI LIVE AKTUAL' }),
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
          h('td', {}, h('span', { class: `xpill ${p.ok ? 'ok' : 'warn'}`, text: p.ok ? 'OK' : 'ATTN' }))
        ));
      });
      tbl.append(tbdy);
      sc.append(tbl);

    } else if (tab === '532 FACTORS') {
      const cats = Object.entries(d.quantCategories || {});
      const catCard = h('div', { class: 'xcard' },
        h('div', { class: 'xsec-hd' },
          h('span', { text: `BREAKDOWN SKOR KATEGORI 532-FACTOR QUANT ENGINE (${cats.length} KATEGORI)` }),
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
        catCard.append(h('div', { class: 'na', text: 'Kategori 532-factor akan terisi otomatis saat file scan *_latest.json memiliki quant_factors.category_scores.' }));
      }
      sc.append(catCard);

      // Raw sample factors + search
      const flt = h('input', { value: factorFilter, placeholder: 'Cari faktor mentah (contoh: rsi, ema, atr, zscore, vwap)...', style: 'width:100%;margin-bottom:6px' });
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
          h('thead', {}, h('tr', {}, h('th', { text: 'NAMA FAKTOR / INDIKATOR BOT' }), h('th', { text: 'NILAI MENTAH' })))
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
// 2. TRAN / TRSC — 9-AGENT DEBATE TRANSCRIPTS & CORPORATE EARNINGS
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
      sc.append(h('div', { class: 'na', text: 'Transcript feed unavailable: ' + (env.error || 'error') }));
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
    const qInp = h('input', { value: searchQ, placeholder: 'Filter transkrip...', style: 'width:120px' });
    qInp.addEventListener('input', () => { searchQ = qInp.value; renderBody(); });

    tb.append(
      h('span', { class: 'lbl', text: 'TRANSKRIP HUB:' }),
      inp,
      h('button', { class: 'on', text: 'LOAD', onclick: () => load(inp.value) }),
      h('button', { class: tab === 'DEBATE' ? 'on' : '', text: '🎙 9-AGENT DEBATE', onclick: () => { tab = 'DEBATE'; renderToolbar(); renderBody(); } }),
      h('button', { class: tab === 'LAYERS' ? 'on' : '', text: '🧾 5-LAYER & MEMORY', onclick: () => { tab = 'LAYERS'; renderToolbar(); renderBody(); } }),
      h('button', { class: tab === 'CORP' ? 'on' : '', text: '🏢 EARNINGS / CATALYSTS', onclick: () => { tab = 'CORP'; renderToolbar(); renderBody(); } }),
      qInp,
      h('button', { style: 'color:#ffb000;border-color:#ffb00066', text: '🔬 X-RAY', onclick: () => ctx.run(`${sym} FACT`) })
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
          h('div', { class: 'xsec-hd' }, h('span', { text: 'SIDANG 9-AGENT ADVERSARIAL COMMITTEE' }), h('span', { class: 'xpill warn', text: 'MENUNGGU SIDANG' })),
          h('div', { style: 'padding:10px;font-size:11px;line-height:1.5;color:#cfd8e3' },
            'Belum ada rekaman transkrip Sidang 9-Agent untuk simbol ini. Sidang 9-Agent otomatis dipanggil oleh bot tepat setelah koin lolos Layer 5 APPROVED.',
            h('div', { style: 'margin-top:8px;display:flex;gap:6px' },
              h('button', { class: 'on', text: 'LIHAT TRANSKRIP 5-LAYER & MEMORY →', onclick: () => { tab = 'LAYERS'; renderToolbar(); renderBody(); } }),
              h('button', { text: 'LIHAT EARNINGS & CATALYST WIRE →', onclick: () => { tab = 'CORP'; renderToolbar(); renderBody(); } })
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
          text: `#${i + 1} ${s.symbol} · ${s.approved ? 'APPROVED' : 'VETOED'} (${s.direction})`,
          onclick: () => { sessionIdx = i; renderBody(); }
        }));
      });
      sc.append(selBar);

      const cur = sessions[sessionIdx] || sessions[0];
      sc.append(h('div', { class: 'xcard xcard-hi' },
        h('div', { class: 'xsec-hd' },
          h('span', { text: `SESI SIDANG: ${cur.symbol} (${cur.id}) • ${String(cur.timestamp || '').slice(0, 19)}` }),
          h('span', { class: `xpill ${cur.approved ? 'ok' : 'no'}`, text: `${cur.approved ? 'APPROVED' : 'VETOED'} • ${cur.direction} • ${cur.confidencePct}% • ${cur.elapsedSec}s` })
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
          h('span', { text: `AUDIT TRAIL 5-LAYER REASONING BOT (${data.symbol})` }),
          h('span', { class: 'am', text: `${steps.length} LAYER TERCATAT` })
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
        card.append(h('div', { class: 'na', text: 'Belum ada file scan *_latest.json untuk simbol ini.' }));
      }
      sc.append(card);

      // AI Trade Memory Post-Mortems
      const pms = data.postMortems || [];
      const pmCard = h('div', { class: 'xcard' },
        h('div', { class: 'xsec-hd' },
          h('span', { text: 'AI TRADE MEMORY — TRANSKRIP POST-MORTEM & PELAJARAN TRADE' }),
          h('span', { class: 'up', text: `${pms.length} REKAMAN TERBARU` })
        )
      );
      if (pms.length) {
        pms.filter(p => !q || String(p.symbol).toLowerCase().includes(q) || String(p.lesson).toLowerCase().includes(q)).forEach(p => {
          const pnl = Number(p.netPnlUsd || 0);
          pmCard.append(h('div', { class: `xturn ${pnl >= 0 ? 'pro' : 'contra'}`, style: 'margin:6px' },
            h('div', { style: 'display:flex;justify-content:space-between;margin-bottom:3px' },
              h('b', { style: 'color:#fff', text: `${p.symbol} ${p.direction || ''} · ${p.setup || '-'}` }),
              h('span', { class: `xpill ${pnl >= 0 ? 'ok' : 'no'}`, text: `${pnl >= 0 ? '+' : ''}$${pnl.toFixed(4)} (${p.exitReason || 'CLOSED'})` })
            ),
            h('div', { style: 'font-size:11px;color:#cfd8e3', text: p.lesson })
          ));
        });
      } else {
        pmCard.append(h('div', { class: 'na', text: 'Belum ada post-mortem di ai_trade_memory.json.' }));
      }
      sc.append(pmCard);

    } else if (tab === 'CORP') {
      const corp = data.corporateTranscript;
      if (!corp) {
        sc.append(h('div', { class: 'na', text: 'Corporate earnings transcript tidak tersedia.' }));
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
            ...(corp.preparedRemarks || []).map(r => h('div', { style: 'margin-bottom:5px', text: '• ' + r }))
          )
        )
      ));

      const qaCard = h('div', { class: 'xcard' },
        h('div', { class: 'xsec-hd' }, h('span', { text: 'CATALYST WIRE & ANALYST Q&A TRANSCRIPT FEED' }), h('span', { class: 'am', text: `${(corp.qaSnippets || []).length} ITEMS` }))
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
// 3. G / SNAP / PATT — MULTI-CHART STUDIO, PNG GALLERY & PATTERN DIAGRAMS
// =====================================================================
function drawMiniCandles(canvas, candles, sym, iv) {
  const dpr = Math.min(2, window.devicePixelRatio || 1);
  const w = canvas.clientWidth || 340;
  const hPx = 175;
  canvas.width = Math.round(w * dpr);
  canvas.height = Math.round(hPx * dpr);
  const ctx2d = canvas.getContext('2d');
  ctx2d.scale(dpr, dpr);
  ctx2d.fillStyle = '#040608';
  ctx2d.fillRect(0, 0, w, hPx);

  if (!Array.isArray(candles) || candles.length < 5) {
    ctx2d.fillStyle = '#778396';
    ctx2d.font = '11px monospace';
    ctx2d.fillText('No candle data for ' + sym, 12, hPx / 2);
    return { bias: 'N/A', chgPct: 0, lastPx: 0 };
  }

  const list = candles.slice(-60);
  const padL = 8, padR = 56, padT = 22, padB = 22;
  const plotW = w - padL - padR;
  const plotH = hPx - padT - padB;
  let lo = Infinity, hi = -Infinity, maxV = 0;
  list.forEach(c => {
    lo = Math.min(lo, Number(c.l ?? c.low ?? c.c));
    hi = Math.max(hi, Number(c.h ?? c.high ?? c.c));
    maxV = Math.max(maxV, Number(c.v ?? c.volume ?? 0));
  });
  const span = Math.max(1e-8, hi - lo);
  lo -= span * 0.06;
  hi += span * 0.06;
  const yOf = p => padT + ((hi - p) / (hi - lo)) * plotH;
  const step = plotW / list.length;

  // Grid lines
  ctx2d.strokeStyle = '#141923';
  ctx2d.lineWidth = 1;
  for (let i = 0; i <= 3; i++) {
    const gy = padT + (i / 3) * plotH;
    ctx2d.beginPath(); ctx2d.moveTo(padL, gy); ctx2d.lineTo(w - padR, gy); ctx2d.stroke();
    const gp = hi - (i / 3) * (hi - lo);
    ctx2d.fillStyle = '#6c798c';
    ctx2d.font = '9px monospace';
    ctx2d.fillText(fmtPx(gp), w - padR + 4, gy + 3);
  }

  // EMA20
  let ema = Number(list[0].c ?? list[0].close);
  const k = 2 / 21;
  const emaPts = [];

  list.forEach((c, i) => {
    const o = Number(c.o ?? c.open), hV = Number(c.h ?? c.high), lV = Number(c.l ?? c.low), cl = Number(c.c ?? c.close), v = Number(c.v ?? c.volume ?? 0);
    ema = cl * k + ema * (1 - k);
    const x = padL + i * step + step / 2;
    emaPts.push([x, yOf(ema)]);

    // Volume bar
    if (maxV > 0) {
      const vh = (v / maxV) * 24;
      ctx2d.fillStyle = cl >= o ? 'rgba(0,210,106,0.22)' : 'rgba(255,59,48,0.22)';
      ctx2d.fillRect(x - step * 0.35, hPx - padB - vh, Math.max(1.5, step * 0.7), vh);
    }

    const up = cl >= o;
    ctx2d.strokeStyle = up ? '#00d26a' : '#ff453a';
    ctx2d.fillStyle = up ? '#00d26a' : '#ff453a';
    ctx2d.beginPath();
    ctx2d.moveTo(x, yOf(hV));
    ctx2d.lineTo(x, yOf(lV));
    ctx2d.stroke();

    const top = Math.min(yOf(o), yOf(cl));
    const bh = Math.max(1.2, Math.abs(yOf(cl) - yOf(o)));
    ctx2d.fillRect(x - Math.max(1, step * 0.32), top, Math.max(2, step * 0.64), bh);
  });

  // Draw EMA20 overlay
  ctx2d.strokeStyle = '#ffb000';
  ctx2d.lineWidth = 1.4;
  ctx2d.beginPath();
  emaPts.forEach(([x, y], i) => { if (i === 0) ctx2d.moveTo(x, y); else ctx2d.lineTo(x, y); });
  ctx2d.stroke();

  const first = Number(list[0].c ?? list[0].close);
  const last = Number(list[list.length - 1].c ?? list[list.length - 1].close);
  const chgPct = first > 0 ? ((last - first) / first) * 100 : 0;
  const bias = last > ema * 1.001 ? 'BULLISH > EMA20' : last < ema * 0.999 ? 'BEARISH < EMA20' : 'CONSOLIDATION';

  // Watermark Header inside PNG
  ctx2d.fillStyle = '#ffb000';
  ctx2d.font = 'bold 11px monospace';
  ctx2d.fillText(`${sym} [${iv.toUpperCase()}]  $${fmtPx(last)}  (${fmtPct(chgPct)})`, 8, 14);
  ctx2d.fillStyle = bias.startsWith('BULL') ? '#00d26a' : bias.startsWith('BEAR') ? '#ff5a52' : '#9aa7b8';
  ctx2d.font = 'bold 9.5px monospace';
  ctx2d.fillText(bias, 8, hPx - 7);
  ctx2d.fillStyle = '#556173';
  ctx2d.fillText('BLOOMBERG // PYROFUEL', w - 138, hPx - 7);

  return { bias, chgPct, lastPx: last };
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
      h('button', { class: tab === 'WALL' ? 'on' : '', text: '📊 4-CHART WALL', onclick: () => { tab = 'WALL'; renderToolbar(); renderBody(); } }),
      h('button', { class: tab === 'GALLERY' ? 'on' : '', text: '🖼 PNG GALLERY', onclick: () => { tab = 'GALLERY'; renderToolbar(); renderBody(); } }),
      h('button', { class: tab === 'PATTERNS' ? 'on' : '', text: '📐 PATTERN DIAGRAMS', onclick: () => { tab = 'PATTERNS'; renderToolbar(); renderBody(); } }),
      ...['5m', '15m', '1h', '4h'].map(t => h('button', {
        class: iv === t ? 'on' : '',
        text: t.toUpperCase(),
        onclick: () => { iv = t; renderToolbar(); renderBody(); }
      })),
      h('button', { style: 'color:#00d26a;border-color:#00d26a66', text: '📸 SNAP ALL 4', onclick: snapAllFour }),
      h('button', { text: 'OPEN FULL GP', onclick: () => ctx.run(`${ctx.symbol} GP`) })
    );
  }

  function snapCanvas(sym, canvas, downloadFile = true) {
    if (!canvas) return;
    try {
      const dataUrl = canvas.toDataURL('image/png');
      saveSnapshotToGallery({
        id: 'SNAP-' + Date.now() + '-' + sym,
        symbol: sym,
        interval: iv,
        ts: Date.now(),
        dataUrl
      });
      if (downloadFile) {
        const a = document.createElement('a');
        a.href = dataUrl;
        a.download = `BBG_${sym}_${iv}_${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}.png`;
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
        h('span', { class: 'lbl', text: '4 KOIN WALL:' })
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
            h('button', { style: 'font-size:10px', text: '📸 PNG', onclick: () => snapCanvas(sym, canvasMap.get(sym), true) }),
            h('button', { style: 'font-size:10px', text: 'GP', onclick: () => ctx.run(`${sym} GP`) }),
            h('button', { style: 'font-size:10px', text: 'X-RAY', onclick: () => ctx.run(`${sym} FACT`) })
          )
        );
        const cv = h('canvas', { style: 'width:100%;height:175px;display:block;background:#040608' });
        card.append(hd, cv);
        grid.append(card);
        canvasMap.set(sym, cv);

        const env = await get('kline', { symbol: sym, interval: iv, limit: 80 }, 4000);
        if (unmounted) return;
        ctx.status(env);
        const arr = env.ok && Array.isArray(env.data) ? env.data : (env.data && env.data.candles) || [];
        drawMiniCandles(cv, arr, sym, iv);
      }));

    } else if (tab === 'GALLERY') {
      const snaps = LS.get(SNAP_KEY, []);
      const top = h('div', { style: 'display:flex;justify-content:space-between;align-items:center;margin-bottom:8px' },
        h('span', { style: 'color:var(--label);font-size:11px', text: `Galeri Chart PNG Tersimpan (${Array.isArray(snaps) ? snaps.length : 0} gambar). Klik 📸 SNAP PNG di panel GP atau 4-Chart Wall untuk menambah.` }),
        h('button', { style: 'color:#ff5a52;border-color:#ff5a5266', text: 'HAPUS SEMUA', onclick: () => { LS.set(SNAP_KEY, []); renderBody(); } })
      );
      sc.append(top);
      if (!Array.isArray(snaps) || !snaps.length) {
        sc.append(h('div', { class: 'na', text: 'Belum ada snapshot chart PNG tersimpan. Klik tombol "📸 SNAP ALL 4" di atas atau "📸 SNAP PNG" di panel GP.' }));
        return;
      }
      const g = h('div', { class: 'snap-grid' });
      snaps.forEach((s, idx) => {
        const card = h('div', { class: 'snap-card' },
          h('img', { src: s.dataUrl, alt: `${s.symbol} chart snapshot`, onclick: () => openImagePreview(s) }),
          h('div', { style: 'padding:6px;display:flex;justify-content:space-between;align-items:center;gap:6px' },
            h('div', {},
              h('b', { style: 'color:var(--amber)', text: `${s.symbol} [${s.interval || '-'}]` }),
              h('div', { style: 'font-size:9.5px;color:var(--muted)', text: fmtTime(s.ts, true) })
            ),
            h('div', { style: 'display:flex;gap:4px' },
              h('button', { style: 'font-size:10px', text: '⬇ PNG', onclick: () => { const a = document.createElement('a'); a.href = s.dataUrl; a.download = `BBG_${s.symbol}_${s.interval || 'chart'}.png`; a.click(); } }),
              h('button', { style: 'font-size:10px;color:#ff5a52', text: '✕', onclick: () => { snaps.splice(idx, 1); LS.set(SNAP_KEY, snaps); renderBody(); } })
            )
          )
        );
        g.append(card);
      });
      sc.append(g);

    } else if (tab === 'PATTERNS') {
      // Live auto-detected pattern signals from ctx.symbol candles
      const detCard = h('div', { class: 'xcard xcard-hi' },
        h('div', { class: 'xsec-hd' }, h('span', { text: `LIVE AUTO-PATTERN DETECTOR — ${ctx.symbol} (${iv.toUpperCase()})` }), h('span', { class: 'up', text: 'REAL CANDLES' }))
      );
      const detBody = h('div', { style: 'padding:8px;font-size:11px;color:#cfd8e3', text: 'Memindai struktur candle real-time...' });
      detCard.append(detBody);
      sc.append(detCard);

      // 4 crisp institutional SVG pattern diagrams
      const diagGrid = h('div', { class: 'xgrid2' },
        h('div', { class: 'xcard' },
          h('div', { class: 'xsec-hd' }, h('span', { text: '1. PYROFUEL SNIPER TWO-STAGE LADDER' }), h('span', { class: 'up', text: 'TP1 50% + TP2 RUNNER' })),
          makeSvgBox(`<svg viewBox="0 0 360 155" style="width:100%;height:auto;background:#040608;display:block">
            <line x1="20" y1="128" x2="340" y2="128" stroke="#ff5a52" stroke-dasharray="4,3"/>
            <text x="24" y="123" fill="#ff5a52" font-size="9" font-family="monospace">STOP LOSS (-1.0R · LIQ SHIELDED)</text>
            <line x1="20" y1="96" x2="340" y2="96" stroke="#00e5ff" stroke-dasharray="2,2"/>
            <text x="24" y="91" fill="#00e5ff" font-size="9" font-family="monospace">SNIPER ENTRY (0.0R · MAKER GTX)</text>
            <line x1="20" y1="68" x2="340" y2="68" stroke="#ffb000" stroke-dasharray="3,2"/>
            <text x="24" y="63" fill="#ffb000" font-size="9" font-family="monospace">STAGE 0: MOVE SL → BREAKEVEN (+0.65R)</text>
            <line x1="20" y1="48" x2="340" y2="48" stroke="#00d26a"/>
            <text x="24" y="43" fill="#00d26a" font-size="9" font-weight="700" font-family="monospace">STAGE 1: TP1 LOCK 50% PROFIT (+0.90R)</text>
            <line x1="20" y1="22" x2="340" y2="22" stroke="#b388ff"/>
            <text x="24" y="17" fill="#b388ff" font-size="9" font-weight="700" font-family="monospace">STAGE 2: TP2 RUNNER (+2.0R + TRAILING)</text>
            <polyline points="35,108 85,96 150,74 215,48 265,56 325,22" fill="none" stroke="#fff" stroke-width="2"/>
            <circle cx="85" cy="96" r="4" fill="#00e5ff"/><circle cx="215" cy="48" r="4" fill="#00d26a"/><circle cx="325" cy="22" r="4" fill="#b388ff"/>
          </svg>`)
        ),
        h('div', { class: 'xcard' },
          h('div', { class: 'xsec-hd' }, h('span', { text: '2. SMART MONEY BOS / CHoCH & ORDER BLOCK' }), h('span', { class: 'am', text: 'MARKET STRUCTURE' })),
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
          h('div', { class: 'xsec-hd' }, h('span', { text: '3. FAIR VALUE GAP (FVG) & FIBO 0.618' }), h('span', { class: 'am', text: 'GOLDEN POCKET' })),
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
          h('div', { class: 'xsec-hd' }, h('span', { text: '4. LIQUIDATION SWEEP & VPIN TOXIC SHIELD' }), h('span', { class: 'dn', text: 'ANTI-STOP-HUNT' })),
          makeSvgBox(`<svg viewBox="0 0 360 155" style="width:100%;height:auto;background:#040608;display:block">
            <rect x="20" y="98" width="320" height="22" fill="rgba(255,59,48,0.16)" stroke="#ff5a52" stroke-dasharray="3,2"/>
            <text x="26" y="112" fill="#ff5a52" font-size="8.5" font-weight="700" font-family="monospace">RETAIL STOP LIQUIDATION MAGNET POOL (BOT SL SHIELDED BELOW)</text>
            <line x1="20" y1="134" x2="340" y2="134" stroke="#00d26a" stroke-width="1.3"/>
            <text x="26" y="146" fill="#00d26a" font-size="8.5" font-family="monospace">PYROFUEL SHIELDED SL (OUTSIDE LIQUIDATION SWEEP)</text>
            <polyline points="24,62 96,76 146,116 184,72 254,48 332,26" fill="none" stroke="#fff" stroke-width="2"/>
            <circle cx="146" cy="116" r="4" fill="#ff5a52"/>
            <text x="154" y="120" fill="#ffb000" font-size="8.5" font-family="monospace">WICK SWEEP</text>
          </svg>`)
        )
      );
      sc.append(diagGrid);

      // Compute real pattern readouts from live candles
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
        let fvgTxt = 'Tidak ada FVG baru pada 5 candle terakhir';
        for (let i = arr.length - 1; i >= Math.max(2, arr.length - 6); i--) {
          if (lows[i] > highs[i - 2]) { fvgTxt = `BULLISH FVG terdeteksi ($${fmtPx(highs[i - 2])} – $${fmtPx(lows[i])})`; break; }
          if (highs[i] < lows[i - 2]) { fvgTxt = `BEARISH FVG terdeteksi ($${fmtPx(highs[i])} – $${fmtPx(lows[i - 2])})`; break; }
        }
        const struct = lastC > prev20Hi ? 'BULLISH BREAK OF STRUCTURE (BOS UP)' : lastC < prev20Lo ? 'BEARISH BREAK OF STRUCTURE (BOS DOWN)' : 'INSIDE RANGE / ACCUMULATION';
        detBody.textContent = '';
        detBody.append(
          h('div', { style: 'margin-bottom:4px' }, h('b', { style: 'color:var(--amber)', text: 'Struktur Harga: ' }), struct),
          h('div', { style: 'margin-bottom:4px' }, h('b', { style: 'color:#00e5ff', text: 'Swing Range (30 bars): ' }), `Low $${fmtPx(swingLo)}  ↔  High $${fmtPx(swingHi)}  |  Golden Pocket 0.618: $${fmtPx(fib618)}`),
          h('div', {}, h('b', { style: 'color:#00d26a', text: 'Fair Value Gap (FVG): ' }), fvgTxt)
        );
      } else {
        detBody.textContent = 'Data candle belum mencukupi untuk deteksi pola otomatis.';
      }
    }
  }

  function openImagePreview(snap) {
    const ov = h('div', {
      style: 'position:fixed;inset:0;z-index:99995;background:rgba(0,0,0,0.92);display:flex;flex-direction:column;align-items:center;justify-content:center;padding:16px',
      onclick: () => ov.remove()
    },
      h('div', { style: 'color:var(--amber);font-weight:700;margin-bottom:8px', text: `${snap.symbol} [${snap.interval}] • ${fmtTime(snap.ts, true)} (Klik di mana saja untuk tutup)` }),
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
    const html = `<!doctype html><html><head><meta charset="utf-8"><title>Bloomberg Intelligence Report — ${esc(d.symbol)}</title>
    <style>body{font-family:Arial,sans-serif;background:#0a0c10;color:#e6edf3;padding:28px;max-width:900px;margin:0 auto}h1{color:#ffb000;border-bottom:2px solid #ffb000;padding-bottom:8px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}.box{border:1px solid #2b3240;background:#11151d;padding:12px}ul{margin:6px 0;padding-left:18px}.up{color:#00d26a}.dn{color:#ff5a52}</style></head><body>
    <h1>BLOOMBERG INTELLIGENCE DOSSIER // ${esc(d.symbol)} — ${esc(d.name)}</h1>
    <p><b>Asset Class:</b> ${esc(d.assetClass)} &nbsp;|&nbsp; <b>Rating:</b> ${esc(d.rating)} &nbsp;|&nbsp; <b>Price:</b> $${esc(fmtPx(q.price))} (${esc(fmtPct(q.chgPct))}) &nbsp;|&nbsp; <b>Generated:</b> ${new Date().toISOString()}</p>
    <div class="grid">
      <div class="box"><h3 class="up">BULL CASE CONVICTION</h3><ul>${(d.bullPoints || []).map(x => `<li>${esc(x)}</li>`).join('')}</ul></div>
      <div class="box"><h3 class="dn">BEAR CASE & TAIL RISKS</h3><ul>${(d.bearPoints || []).map(x => `<li>${esc(x)}</li>`).join('')}</ul></div>
    </div>
    <div class="box" style="margin-top:14px"><h3>RECENT MARKET CATALYSTS</h3><ul>${(d.catalysts || []).map(c => `<li><b>${esc(c.source || 'WIRE')}:</b> ${esc(c.title)}</li>`).join('')}</ul></div>
    </body></html>`;
    downloadBlob(`BI_Report_${d.symbol}_${new Date().toISOString().slice(0, 10)}.html`, html, 'text/html;charset=utf-8');
  }

  function renderToolbar() {
    tb.textContent = '';
    const inp = h('input', { value: sym, style: 'width:90px;text-transform:uppercase;font-weight:700' });
    inp.addEventListener('keydown', e => { if (e.key === 'Enter') load(inp.value); });
    tb.append(
      h('span', { class: 'lbl', text: 'BLOOMBERG INTELLIGENCE (BI):' }),
      inp,
      h('button', { class: 'on', text: 'RESEARCH <GO>', onclick: () => load(inp.value) }),
      h('button', { style: 'color:#00d26a;border-color:#00d26a66', text: '📄 EXPORT HTML DOSSIER', onclick: exportHtmlReport }),
      h('button', { text: '🔬 BOT X-RAY', onclick: () => ctx.run(`${sym} FACT`) }),
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
          h('div', { style: 'color:var(--label);font-size:10.5px', text: `${d.assetClass}  •  Last: $${fmtPx(q.price)} (${fmtPct(q.chgPct)})  •  Vol: ${fmtVol(q.vol)}` })
        ),
        h('span', { class: `xpill ${rCls}`, style: 'font-size:11px;padding:3px 8px', text: d.rating })
      )
    ));

    sc.append(h('div', { class: 'xgrid4', style: 'margin-bottom:8px' },
      h('div', { class: 'xstat' }, h('div', { class: 'xl', text: 'PYROFUEL P_MATH' }), h('div', { class: 'xv', text: qs.pMath != null ? `${Number(qs.pMath).toFixed(1)}%` : 'N/A' }), h('div', { class: 'xs', text: `Regime: ${qs.regime || '-'}` })),
      h('div', { class: 'xstat' }, h('div', { class: 'xl', text: 'ADX-14 / HURST' }), h('div', { class: 'xv', text: `${qs.adx14 != null ? Number(qs.adx14).toFixed(1) : '-'} / ${qs.hurst != null ? Number(qs.hurst).toFixed(2) : '-'}` }), h('div', { class: 'xs', text: `OBI-20: ${qs.obi20 != null ? Number(qs.obi20).toFixed(3) : '-'}` })),
      h('div', { class: 'xstat' }, h('div', { class: 'xl', text: 'OPTIONS DVOL' }), h('div', { class: 'xv', text: qs.dvol != null ? String(qs.dvol) : 'N/A' }), h('div', { class: 'xs', text: `Hybrid: ${qs.hybridConf != null ? qs.hybridConf + '%' : '-'}` })),
      h('div', { class: 'xstat' }, h('div', { class: 'xl', text: 'AI SETUP BIAS' }), h('div', { class: 'xv', style: 'font-size:12px;color:#00e5ff', text: qs.setup || 'MONITORING' }), h('div', { class: 'xs', text: `Direction: ${qs.direction || 'NEUTRAL'}` }))
    ));

    sc.append(h('div', { class: 'xgrid2', style: 'margin-bottom:8px' },
      h('div', { class: 'xcard', style: 'margin-bottom:0;border-left:3px solid var(--up)' },
        h('div', { class: 'xsec-hd' }, h('span', { style: 'color:var(--up)', text: '▲ BULL CASE / UPSIDE THESIS' })),
        h('div', { style: 'padding:8px;font-size:11px;line-height:1.55' }, ...(d.bullPoints || []).map(p => h('div', { style: 'margin-bottom:5px', text: '• ' + p })))
      ),
      h('div', { class: 'xcard', style: 'margin-bottom:0;border-left:3px solid var(--dn)' },
        h('div', { class: 'xsec-hd' }, h('span', { style: 'color:var(--dn)', text: '▼ BEAR CASE / RISK FACTORS' })),
        h('div', { style: 'padding:8px;font-size:11px;line-height:1.55' }, ...(d.bearPoints || []).map(p => h('div', { style: 'margin-bottom:5px', text: '• ' + p })))
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
// 5. ETF / FLOW / INS / SI — INSTITUTIONAL FLOWS, SQUEEZE & INSIDERS
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

    // 1. ETF Diverging Bar Diagram + Table
    sc.append(h('div', { class: 'xcard' },
      h('div', { class: 'xsec-hd' },
        h('span', { text: 'SPOT CRYPTO & MACRO ETF SIGNED MONEY FLOW PROXY (IBIT, FBTC, GBTC, ETHA, SPY, QQQ, TLT, GLD, EIDO)' }),
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

    // 2. Futures Short Squeeze Pressure Matrix
    sc.append(h('div', { class: 'xsec-hd', style: 'margin-bottom:4px' },
      h('span', { text: 'BINANCE FUTURES SHORT SQUEEZE & CROWDING PRESSURE BOARD' }),
      h('span', { class: 'am', text: `${sq.length} PERPS` })
    ));
    const sqTbl = h('table', { class: 't', style: 'margin-bottom:10px' },
      h('thead', {}, h('tr', {},
        h('th', { text: 'PERP' }),
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

    // 3. SEC Form-4 / Regulatory Insiders
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
      sc.append(h('div', { class: 'na', text: 'Masukkan ticker saham AS (misal NVDA, AAPL, MSFT, TSLA) di toolbar untuk melihat SEC Form-4 Insiders.' }));
    }
  }

  renderToolbar();
  load(insSym);
  ctx.cleanup(() => { unmounted = true; });
}

// =====================================================================
// 6. FIN / BUDGET / CASH — PERSONAL FINANCE & ANTI-BOROS MONEY MANAGER
// =====================================================================
export function mountFIN(body, ctx) {
  body.classList.add('fill');
  const tb = h('div', { class: 'tb' });
  const sc = h('div', { class: 'pb' });
  body.append(tb, sc);

  let tab = 'DASH';
  let finData = null;
  let historyFilter = 'ALL';
  let toastNote = '';
  let unmounted = false;

  async function load() {
    try {
      const r = await apiFetch('/api/finance', { cache: 'no-store' }, 10000);
      if (unmounted) return;
      if (!r.ok) {
        ctx.status({ ok: false, source: 'finance', ts: Date.now(), mode: 'NA' });
        sc.textContent = '';
        sc.append(h('div', { class: 'na', text: `Auth diperlukan atau gagal memuat Keuangan (HTTP ${r.status}).` }));
        return;
      }
      const j = await r.json();
      finData = j.data;
      ctx.status({ ok: true, source: 'personal-finance', ts: Date.now(), mode: 'LIVE' });
      renderToolbar();
      renderBody();
    } catch (e) {
      if (!unmounted) {
        sc.textContent = '';
        sc.append(h('div', { class: 'na', text: 'Error memuat Keuangan: ' + e.message }));
      }
    }
  }

  function exportCsv() {
    if (!finData) return;
    const rows = [['ID', 'Tanggal', 'Tipe', 'Kategori', 'Nominal_IDR', 'Catatan']];
    (finData.transactions || []).forEach(t => {
      rows.push([t.id, t.date, t.type, t.category, t.amountIdr, String(t.note || '').replace(/[\r\n,]+/g, ' ')]);
    });
    downloadBlob(`Keuangan_AntiBoros_${new Date().toISOString().slice(0, 10)}.csv`, rows.map(r => r.join(',')).join('\n'), 'text/csv;charset=utf-8');
  }

  function renderToolbar() {
    tb.textContent = '';
    tb.append(
      h('span', { class: 'lbl', text: 'KEUANGAN & ANTI-BOROS:' }),
      h('button', { class: tab === 'DASH' ? 'on' : '', text: '💰 DASHBOARD & CATAT', onclick: () => { tab = 'DASH'; renderToolbar(); renderBody(); } }),
      h('button', { class: tab === 'BUDGET' ? 'on' : '', text: '🎯 GOALS & LIMIT BUDGET', onclick: () => { tab = 'BUDGET'; renderToolbar(); renderBody(); } }),
      h('button', { class: tab === 'HIST' ? 'on' : '', text: '📋 RIWAYAT & CSV', onclick: () => { tab = 'HIST'; renderToolbar(); renderBody(); } }),
      h('button', { style: 'color:#00d26a;border-color:#00d26a66', text: '⬇ EXPORT CSV', onclick: exportCsv }),
      h('button', { text: 'REFRESH', onclick: load })
    );
  }

  function renderBody() {
    sc.textContent = '';
    if (!finData) return;
    const s = finData.summary || {};

    // Top Anti-Boros Status Banner
    const isBoros = s.borosStatus === 'BOROS_OVER_BUDGET';
    const isWarn = s.borosStatus === 'WASPADA_HAMPIR_LIMIT';
    const bannerCol = isBoros ? '#ff453a' : isWarn ? '#ffb000' : '#00d26a';
    const bannerTxt = isBoros
      ? '🚨 MODE ANTI-BOROS: PENGELUARAN MELEWATI BATAS! REM BELANJA HARI INI!'
      : isWarn
      ? '⚠️ WASPADA: PENGELUARAN SUDAH ≥75% DARI LIMIT — JAGA PENGELUARAN SISA HARI INI!'
      : '✅ KEUANGAN AMAN & TERKONTROL — PERTAHANKAN DISIPLIN ANTI-BOROS!';

    sc.append(h('div', {
      class: 'xcard',
      style: `border-color:${bannerCol};border-left:5px solid ${bannerCol};background:${isBoros ? '#1c0505' : isWarn ? '#1a1203' : '#03190d'}`
    },
      h('div', { style: 'display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:6px' },
        h('b', { style: `color:${bannerCol};font-size:12px`, text: bannerTxt }),
        h('span', { class: `xpill ${isBoros ? 'no' : isWarn ? 'warn' : 'ok'}`, text: `SKOR DISIPLIN: ${s.disciplineScore || 100}/100` })
      ),
      toastNote ? h('div', { style: 'margin-top:4px;color:#00e5ff;font-size:11px', text: toastNote }) : null
    ));

    // Top 4 KPI Cards
    const botSync = s.botSync || {};
    sc.append(h('div', { class: 'xgrid4', style: 'margin-bottom:8px' },
      h('div', { class: 'xstat' },
        h('div', { class: 'xl', text: 'SISA JATAH HARI INI' }),
        h('div', { class: 'xv', style: `color:${(s.remainingTodayIdr || 0) >= 0 ? 'var(--up)' : 'var(--dn)'}`, text: fmtIdr(s.remainingTodayIdr) }),
        h('div', { class: 'xs', text: `Terpakai: ${fmtIdr(s.todayExpense)} / ${fmtIdr(s.dailyLimitIdr)} (${s.dailyUsedPct || 0}%)` })
      ),
      h('div', { class: 'xstat' },
        h('div', { class: 'xl', text: 'JATAH AMAN HARIAN DINAMIS' }),
        h('div', { class: 'xv', style: 'color:#00e5ff', text: fmtIdr(s.dynamicSafeDailyIdr) }),
        h('div', { class: 'xs', text: `Sisa bulan ${fmtIdr(s.remainingMonthIdr)} ÷ ${s.remainingDays || 1} hari` })
      ),
      h('div', { class: 'xstat' },
        h('div', { class: 'xl', text: 'CASHFLOW BULAN INI' }),
        h('div', { class: 'xv', style: 'color:var(--amber)', text: fmtIdr((s.monthIncome || 0) - (s.monthExpense || 0)) }),
        h('div', { class: 'xs', text: `Masuk ${fmtIdr(s.monthIncome)} | Keluar ${fmtIdr(s.monthExpense)} (${s.monthUsedPct || 0}%)` })
      ),
      h('div', { class: 'xstat' },
        h('div', { class: 'xl', text: 'TABUNGAN + BOT BINANCE' }),
        h('div', { class: 'xv', style: 'color:#00d26a', text: fmtIdr((s.totalSavingsIdr || 0) + (botSync.walletIdr || 0)) }),
        h('div', { class: 'xs', text: `Bot Wallet $${Number(botSync.walletUsd || 0).toFixed(2)} | Vault $${Number(botSync.vaultUsd || 0).toFixed(2)}` })
      )
    ));

    if (tab === 'DASH') {
      // Quick-Add Transaction + Discipline Score Gauge side-by-side
      const typeSel = h('select', { style: 'width:100%' },
        h('option', { value: 'EXPENSE', text: '💸 PENGELUARAN (EXPENSE)' }),
        h('option', { value: 'INCOME', text: '💵 PEMASUKAN (INCOME)' }),
        h('option', { value: 'SAVINGS', text: '🏦 TABUNGAN / INVESTASI (SAVINGS)' })
      );
      const expenseCats = Object.keys(finData.categoryLimits || {});
      const catSel = h('select', { style: 'width:100%' });
      const goalSel = h('select', { style: 'width:100%;display:none' },
        h('option', { value: '', text: '-- Tanpa Link Goal --' }),
        ...(finData.goals || []).map(g => h('option', { value: g.id, text: `${g.name} (${fmtIdr(g.savedIdr)} / ${fmtIdr(g.targetIdr)})` }))
      );

      const syncCats = () => {
        catSel.textContent = '';
        const t = typeSel.value;
        goalSel.style.display = t === 'SAVINGS' ? 'block' : 'none';
        const opts = t === 'INCOME'
          ? ['Gaji / Bulanan', 'Profit Trading Bot', 'Freelance / Bonus', 'Pemasukan Lainnya']
          : t === 'SAVINGS'
          ? ['Dana Darurat', 'Modal Bot Gigi 2', 'Investasi Saham/Crypto', 'Tabungan Impian']
          : (expenseCats.length ? expenseCats : ['Makan & Minum', 'Kopi & Jajan', 'Transport & Bensin', 'Tagihan & Kos', 'Belanja & Hobi', 'Kesehatan & Lainnya']);
        opts.forEach(c => catSel.append(h('option', { value: c, text: c })));
      };
      typeSel.addEventListener('change', syncCats);
      syncCats();

      const amtInp = h('input', { type: 'number', min: '500', step: '500', placeholder: 'Nominal Rupiah (contoh: 25000)', style: 'width:100%;font-weight:700;font-size:13px' });
      const noteInp = h('input', { placeholder: 'Catatan singkat (misal: Nasi padang + es teh)', style: 'width:100%' });
      const quickChips = h('div', { style: 'display:flex;gap:4px;flex-wrap:wrap;margin:4px 0' },
        ...[15000, 25000, 50000, 100000, 250000].map(v => h('button', {
          type: 'button',
          style: 'font-size:10px',
          text: `+${v / 1000}rb`,
          onclick: () => { amtInp.value = String((Number(amtInp.value) || 0) + v); }
        }))
      );

      const submitTx = async () => {
        const amountIdr = Math.round(Number(amtInp.value));
        if (!amountIdr || amountIdr <= 0) { toastNote = '⚠️ Masukkan nominal Rupiah yang valid.'; renderBody(); return; }
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
          toastNote = `✅ Tercatat: ${typeSel.value} ${fmtIdr(amountIdr)} (${catSel.value})`;
          renderBody();
        } else {
          toastNote = '❌ Gagal menyimpan: ' + (j.error || 'error');
          renderBody();
        }
      };

      const formCard = h('div', { class: 'xcard', style: 'margin-bottom:0' },
        h('div', { class: 'xsec-hd' }, h('span', { text: 'CATAT TRANSAKSI CEPAT (ANTI-BOROS)' }), h('span', { class: 'am', text: s.todayStr || '' })),
        h('div', { style: 'padding:6px;display:flex;flex-direction:column;gap:6px' },
          typeSel,
          catSel,
          goalSel,
          amtInp,
          quickChips,
          noteInp,
          h('button', { class: 'on', style: 'padding:7px;font-weight:700;background:#00d26a;color:#000;border-color:#00d26a', text: '+ SIMPAN TRANSAKSI', onclick: submitTx })
        )
      );

      const gaugeCard = h('div', { class: 'xcard', style: 'margin-bottom:0' },
        h('div', { class: 'xsec-hd' }, h('span', { text: 'SKOR DISIPLIN KEUANGAN & ATURAN 50/30/20' }), h('span', { class: 'up', text: `SAVING RATE ${s.savingsRatePct || 0}%` })),
        makeSvgBox(buildGaugeSvg(s.disciplineScore || 100, isBoros ? 'BOROS ALERT' : isWarn ? 'WASPADA LIMIT' : 'DISIPLIN MANTAP', bannerCol)),
        h('div', { style: 'padding:4px 8px;font-size:10.5px;line-height:1.5;color:#cfd8e3' },
          h('div', { text: `• Batas Harian Anti-Boros: ${fmtIdr(s.dailyLimitIdr)} (Otomatis kirim Push Notif jika jebol!)` }),
          h('div', { text: `• Budget Bulanan: ${fmtIdr(s.monthlyBudgetIdr)} | Target Income: ${fmtIdr(s.monthlyIncomeTarget)}` }),
          h('div', { text: `• Saldo Bot Binance: $${Number(botSync.walletUsd || 0).toFixed(2)} (~${fmtIdr(botSync.walletIdr)}) | Vault: $${Number(botSync.vaultUsd || 0).toFixed(2)}` })
        )
      );

      sc.append(h('div', { class: 'xgrid2', style: 'margin-bottom:8px' }, formCard, gaugeCard));

      // 14-Day Cashflow Bar Chart
      sc.append(h('div', { class: 'xcard' },
        h('div', { class: 'xsec-hd' },
          h('span', { text: 'DIAGRAM CASHFLOW 14 HARI TERAKHIR (HIJAU = INCOME | ORANYE/MERAH = EXPENSE vs BATAS HARIAN)' }),
          h('span', { class: 'am', text: 'ANTI-BOROS MONITOR' })
        ),
        makeSvgBox(buildCashflow14dSvg(s.dailyTrend14d, s.dailyLimitIdr))
      ));

      // Category Envelopes Visual Bars
      const envCard = h('div', { class: 'xcard' },
        h('div', { class: 'xsec-hd' },
          h('span', { text: 'AMPLOP BUDGET PER KATEGORI BULAN INI' }),
          h('button', { style: 'font-size:10px', text: 'ATUR LIMIT →', onclick: () => { tab = 'BUDGET'; renderToolbar(); renderBody(); } })
        )
      );
      const envGrid = h('div', { class: 'xgrid2', style: 'padding:6px 2px' });
      const allCats = new Set([...Object.keys(s.categoryLimits || {}), ...Object.keys(s.byCategory || {})]);
      allCats.forEach(cat => {
        const spent = Number((s.byCategory && s.byCategory[cat]) || 0);
        const lim = Number((s.categoryLimits && s.categoryLimits[cat]) || 0);
        const pct = lim > 0 ? Math.min(130, (spent / lim) * 100) : (spent > 0 ? 100 : 0);
        const col = pct > 100 ? 'var(--dn)' : pct >= 75 ? 'var(--amber)' : 'var(--up)';
        envGrid.append(h('div', { style: 'padding:5px 7px;border:1px solid #181d26;background:#05070a' },
          h('div', { style: 'display:flex;justify-content:space-between;font-size:10.5px;margin-bottom:3px' },
            h('b', { style: 'color:#e6edf3', text: cat }),
            h('span', { style: `color:${col};font-weight:700`, text: `${fmtIdr(spent)} / ${lim > 0 ? fmtIdr(lim) : 'No Limit'}` })
          ),
          h('div', { class: 'xbar-track' }, h('div', { class: 'xbar-fill', style: `width:${Math.min(100, pct)}%;background:${col}` }))
        ));
      });
      envCard.append(envGrid);
      sc.append(envCard);

    } else if (tab === 'BUDGET') {
      // Budget Limits Editor
      const dLim = h('input', { type: 'number', value: String(finData.dailyLimitIdr || 100000), style: 'width:100%' });
      const mBud = h('input', { type: 'number', value: String(finData.monthlyBudgetIdr || 3000000), style: 'width:100%' });
      const mInc = h('input', { type: 'number', value: String(finData.monthlyIncomeTarget || 5000000), style: 'width:100%' });
      const catInputs = {};

      const budCard = h('div', { class: 'xcard' },
        h('div', { class: 'xsec-hd' }, h('span', { text: 'PENGATURAN BATAS ANTI-BOROS & AMPLOP BULANAN' }), h('span', { class: 'am', text: 'OTOMATIS PUSH ALERT JIKA JEBOL' })),
        h('div', { class: 'xgrid3', style: 'padding:8px 2px' },
          h('div', {}, h('div', { class: 'lbl', style: 'margin-bottom:3px', text: 'Batas Pengeluaran Harian (Rp)' }), dLim),
          h('div', {}, h('div', { class: 'lbl', style: 'margin-bottom:3px', text: 'Total Budget Bulanan (Rp)' }), mBud),
          h('div', {}, h('div', { class: 'lbl', style: 'margin-bottom:3px', text: 'Target Pemasukan Bulanan (Rp)' }), mInc)
        )
      );
      const cGrid = h('div', { class: 'xgrid3', style: 'padding:4px 2px' });
      Object.entries(finData.categoryLimits || {}).forEach(([k, v]) => {
        const el = h('input', { type: 'number', value: String(v), style: 'width:100%' });
        catInputs[k] = el;
        cGrid.append(h('div', {}, h('div', { style: 'font-size:10px;color:var(--label);margin-bottom:2px', text: k }), el));
      });
      budCard.append(cGrid, h('div', { style: 'padding:6px 2px' },
        h('button', {
          class: 'on',
          style: 'background:#ffb000;color:#000;font-weight:700;padding:6px 14px',
          text: '💾 SIMPAN PENGATURAN BUDGET',
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
            if (r.ok && j.ok) { finData = j.data; toastNote = '✅ Pengaturan Budget & Batas Anti-Boros tersimpan!'; renderBody(); }
          }
        })
      ));
      sc.append(budCard);

      // Savings Goals
      const gCard = h('div', { class: 'xcard' },
        h('div', { class: 'xsec-hd' }, h('span', { text: 'TARGET TABUNGAN & DANA DARURAT (SAVINGS GOALS)' }), h('span', { class: 'up', text: `${(finData.goals || []).length} GOALS` }))
      );
      (finData.goals || []).forEach(g => {
        const pct = g.targetIdr > 0 ? Math.min(100, (g.savedIdr / g.targetIdr) * 100) : 0;
        gCard.append(h('div', { style: 'padding:8px;border-bottom:1px solid #181d26' },
          h('div', { style: 'display:flex;justify-content:space-between;align-items:center;margin-bottom:4px' },
            h('div', {}, h('b', { style: 'color:#fff', text: g.name }), h('span', { style: 'color:var(--muted);font-size:10px;margin-left:8px', text: `Target: ${g.deadline || '-'}` })),
            h('div', { style: 'display:flex;gap:6px;align-items:center' },
              h('span', { style: 'color:var(--up);font-weight:700', text: `${fmtIdr(g.savedIdr)} / ${fmtIdr(g.targetIdr)} (${pct.toFixed(1)}%)` }),
              h('button', { style: 'font-size:10px;color:#ff5a52', text: '✕', onclick: async () => {
                const r = await apiFetch(`/api/finance/goal/${encodeURIComponent(g.id)}`, { method: 'DELETE' }, 10000);
                const j = await r.json();
                if (r.ok && j.ok) { finData = j.data; renderBody(); }
              } })
            )
          ),
          h('div', { class: 'xbar-track' }, h('div', { class: 'xbar-fill', style: `width:${pct}%;background:var(--up)` }))
        ));
      });

      const gName = h('input', { placeholder: 'Nama Goal baru (misal: Laptop Baru / DP Rumah)', style: 'width:100%' });
      const gTarget = h('input', { type: 'number', placeholder: 'Target Rp (misal: 5000000)', style: 'width:100%' });
      const gSaved = h('input', { type: 'number', placeholder: 'Sudah terkumpul Rp (0)', style: 'width:100%' });
      gCard.append(h('div', { class: 'xgrid3', style: 'padding:8px 4px' }, gName, gTarget, gSaved),
        h('div', { style: 'padding:0 4px 6px' }, h('button', {
          class: 'on',
          text: '+ TAMBAH SAVINGS GOAL',
          onclick: async () => {
            if (!gName.value.trim() || !Number(gTarget.value)) return;
            const r = await apiFetch('/api/finance/goal', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ name: gName.value.trim(), targetIdr: Number(gTarget.value), savedIdr: Number(gSaved.value || 0) })
            }, 10000);
            const j = await r.json();
            if (r.ok && j.ok) { finData = j.data; toastNote = '✅ Goal baru ditambahkan!'; renderBody(); }
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
        sc.append(h('div', { class: 'na', text: 'Belum ada transaksi tercatat. Mulai catat di tab "💰 DASHBOARD & CATAT".' }));
        return;
      }
      const tbl = h('table', { class: 't' },
        h('thead', {}, h('tr', {},
          h('th', { text: 'TANGGAL' }),
          h('th', { text: 'TIPE' }),
          h('th', { text: 'KATEGORI' }),
          h('th', { text: 'CATATAN' }),
          h('th', { class: 'r', text: 'NOMINAL' }),
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
          h('td', {}, h('button', { style: 'font-size:10px;color:#ff5a52', text: 'HAPUS', onclick: async () => {
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
