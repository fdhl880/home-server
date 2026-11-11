import { h, fmtPx, fmtPct, fmtVol, fmtNum, dirCls } from '../util.js';
import { get, tickOk } from '../api.js';

// Standard normal CDF & PDF for Black-Scholes
function normPDF(x) { return Math.exp(-0.5 * x * x) / Math.sqrt(2 * Math.PI); }
function normCDF(x) {
  const a1 = 0.254829592, a2 = -0.284496736, a3 = 1.421413741, a4 = -1.453152027, a5 = 1.061405429, p = 0.3275911;
  const sign = x < 0 ? -1 : 1;
  const ax = Math.abs(x) / Math.sqrt(2);
  const t = 1.0 / (1.0 + p * ax);
  const y = 1.0 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * Math.exp(-ax * ax);
  return 0.5 * (1.0 + sign * y);
}

function blackScholes(S, K, T, r, sigma) {
  if (T <= 0 || sigma <= 0 || S <= 0 || K <= 0) return null;
  const sqT = Math.sqrt(T);
  const d1 = (Math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * sqT);
  const d2 = d1 - sigma * sqT;
  const nd1 = normCDF(d1), nd2 = normCDF(d2);
  const nmd1 = normCDF(-d1), nmd2 = normCDF(-d2);
  const pdf1 = normPDF(d1);
  const df = Math.exp(-r * T);

  const callPx = S * nd1 - K * df * nd2;
  const putPx = K * df * nmd2 - S * nmd1;
  const gamma = pdf1 / (S * sigma * sqT);
  const vega = (S * pdf1 * sqT) / 100; // per 1% vol
  const callTheta = (-(S * pdf1 * sigma) / (2 * sqT) - r * K * df * nd2) / 365;
  const putTheta = (-(S * pdf1 * sigma) / (2 * sqT) + r * K * df * nmd2) / 365;
  const callRho = (K * T * df * nd2) / 100;
  const putRho = (-K * T * df * nmd2) / 100;

  return {
    callPx, putPx,
    callDelta: nd1, putDelta: nd1 - 1,
    gamma, vega,
    callTheta, putTheta,
    callRho, putRho, d1, d2
  };
}

export function mountBETA(body, ctx) {
  body.classList.add('fill');
  let bench = /USDT|BTC|ETH/.test(ctx.symbol) ? 'BTCUSDT' : '^GSPC';
  let days = 90;
  const tb = h('div', { class: 'tb' });
  const sc = h('div', { class: 'pb' });
  body.append(tb, sc);

  async function load() {
    tb.textContent = '';
    const inp = h('input', { value: bench, style: 'width:95px;text-transform:uppercase' });
    tb.append(
      h('span', { class: 'lbl', text: `BETA REGRESSION [${ctx.symbol} vs` }),
      inp,
      h('button', { text: 'SET BENCH', onclick: () => { bench = inp.value.trim().toUpperCase() || '^GSPC'; load(); } }),
      ...['^GSPC', '^IXIC', 'BTCUSDT'].map(b => h('button', { class: bench === b ? 'on' : '', text: b, onclick: () => { bench = b; load(); } })),
      ...[60, 90, 180, 252].map(d => h('button', { class: days === d ? 'on' : '', text: d + 'D', onclick: () => { days = d; load(); } }))
    );

    sc.textContent = '';
    const [aEnv, bEnv] = await Promise.all([
      get('kline', { symbol: ctx.symbol, interval: '1d', limit: days + 5 }, 5000),
      get('kline', { symbol: bench, interval: '1d', limit: days + 5 }, 5000)
    ]);
    ctx.status(aEnv.ok ? aEnv : bEnv);
    const ca = (aEnv.ok && aEnv.data && aEnv.data.candles) || [];
    const cb = (bEnv.ok && bEnv.data && bEnv.data.candles) || [];
    if (ca.length < 15 || cb.length < 15) {
      sc.append(h('div', { class: 'na', text: 'N/A (insufficient overlapping daily history)' }));
      return;
    }

    const mapB = new Map();
    for (let i = 1; i < cb.length; i++) {
      const dayKey = Math.floor(cb[i].t / 86400000);
      mapB.set(dayKey, ((cb[i].c - cb[i - 1].c) / cb[i - 1].c) * 100);
    }
    const pairs = [];
    for (let i = 1; i < ca.length; i++) {
      const dayKey = Math.floor(ca[i].t / 86400000);
      const rA = ((ca[i].c - ca[i - 1].c) / ca[i - 1].c) * 100;
      const rB = mapB.get(dayKey);
      if (rB != null && isFinite(rA) && isFinite(rB)) pairs.push({ x: rB, y: rA });
    }
    if (pairs.length < 10) {
      for (let i = 1; i < Math.min(ca.length, cb.length); i++) {
        pairs.push({
          x: ((cb[i].c - cb[i - 1].c) / cb[i - 1].c) * 100,
          y: ((ca[i].c - ca[i - 1].c) / ca[i - 1].c) * 100
        });
      }
    }

    const n = pairs.length;
    const meanX = pairs.reduce((s, p) => s + p.x, 0) / n;
    const meanY = pairs.reduce((s, p) => s + p.y, 0) / n;
    let cov = 0, varX = 0, varY = 0;
    for (const p of pairs) {
      cov += (p.x - meanX) * (p.y - meanY);
      varX += (p.x - meanX) ** 2;
      varY += (p.y - meanY) ** 2;
    }
    const rawBeta = varX > 0 ? cov / varX : 1;
    const adjBeta = 0.67 * rawBeta + 0.33 * 1.0; // Bloomberg Blume adjustment
    const alpha = meanY - rawBeta * meanX;
    const rCorr = (varX > 0 && varY > 0) ? cov / Math.sqrt(varX * varY) : 0;
    const r2 = rCorr * rCorr;

    const ns = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('viewBox', '0 0 420 220');
    svg.style.cssText = 'width:100%;height:220px;background:#000;border:1px solid var(--border)';
    const maxAbsX = Math.max(...pairs.map(p => Math.abs(p.x)), 2);
    const maxAbsY = Math.max(...pairs.map(p => Math.abs(p.y)), 2);
    const sx = v => 210 + (v / maxAbsX) * 185;
    const sy = v => 110 - (v / maxAbsY) * 95;

    for (const [x1, y1, x2, y2] of [[15, 110, 405, 110], [210, 10, 210, 210]]) {
      const l = document.createElementNS(ns, 'line');
      l.setAttribute('x1', x1); l.setAttribute('y1', y1); l.setAttribute('x2', x2); l.setAttribute('y2', y2);
      l.setAttribute('stroke', '#2a2a2a');
      svg.append(l);
    }
    for (const p of pairs) {
      const c = document.createElementNS(ns, 'circle');
      c.setAttribute('cx', sx(p.x).toFixed(1));
      c.setAttribute('cy', sy(p.y).toFixed(1));
      c.setAttribute('r', '2.5');
      c.setAttribute('fill', '#4da3ff');
      svg.append(c);
    }
    const regLine = document.createElementNS(ns, 'line');
    regLine.setAttribute('x1', sx(-maxAbsX));
    regLine.setAttribute('y1', sy(alpha + rawBeta * (-maxAbsX)));
    regLine.setAttribute('x2', sx(maxAbsX));
    regLine.setAttribute('y2', sy(alpha + rawBeta * maxAbsX));
    regLine.setAttribute('stroke', '#ffb000');
    regLine.setAttribute('stroke-width', '2');
    svg.append(regLine);

    const stats = h('div', { class: 'kv', style: 'border:1px solid var(--border);background:#050505' },
      ['RAW BETA (SLOPE)', fmtNum(rawBeta, 3)],
      ['ADJUSTED BETA (2/3 RAW + 1/3)', fmtNum(adjBeta, 3)],
      ['ALPHA (INTERCEPT %/DAY)', (alpha >= 0 ? '+' : '') + fmtNum(alpha, 4) + '%'],
      ['R-SQUARED (R²)', fmtNum(r2, 3)],
      ['CORRELATION (R)', fmtNum(rCorr, 3)],
      ['OBSERVATIONS (DAYS)', String(n)],
      ['EQUATION', `Y = ${rawBeta.toFixed(2)} X + ${alpha.toFixed(3)}`]
    ).children;

    const kvWrap = h('div', { class: 'kv', style: 'border:1px solid var(--border);background:#050505;align-content:start' });
    for (const [k, v] of [
      ['RAW BETA (SLOPE)', fmtNum(rawBeta, 3)],
      ['BLUME ADJ BETA', fmtNum(adjBeta, 3)],
      ['ALPHA (DAILY %)', (alpha >= 0 ? '+' : '') + fmtNum(alpha, 4) + '%'],
      ['R-SQUARED (R²)', fmtNum(r2, 3)],
      ['CORRELATION (R)', fmtNum(rCorr, 3)],
      ['OBSERVATIONS', `${n} Daily Returns`],
      ['REGRESSION', `Y = ${rawBeta.toFixed(2)}X ${alpha >= 0 ? '+' : ''}${alpha.toFixed(3)}`]
    ]) {
      kvWrap.append(h('div', { class: 'k', text: k }), h('div', { class: 'v am sym', text: v }));
    }

    sc.append(h('div', { style: 'display:grid;grid-template-columns:1.3fr 1fr;gap:8px;padding:6px' }, svg, kvWrap));
  }
  load();
}


export function mountCORR(body, ctx) {
  body.classList.add('fill');
  let syms = [ctx.symbol, 'BTCUSDT', 'ETHUSDT', 'SOLUSDT', '^GSPC', 'GC=F', '^TNX'];
  syms = [...new Set(syms)].slice(0, 7);
  let days = 60;
  const tb = h('div', { class: 'tb' });
  const sc = h('div', { class: 'pb' });
  body.append(tb, sc);

  function corrCoef(a, b) {
    const n = Math.min(a.length, b.length);
    if (n < 5) return null;
    const xa = a.slice(-n), xb = b.slice(-n);
    const ma = xa.reduce((s, v) => s + v, 0) / n;
    const mb = xb.reduce((s, v) => s + v, 0) / n;
    let num = 0, da = 0, db = 0;
    for (let i = 0; i < n; i++) {
      num += (xa[i] - ma) * (xb[i] - mb);
      da += (xa[i] - ma) ** 2;
      db += (xb[i] - mb) ** 2;
    }
    return (da > 0 && db > 0) ? num / Math.sqrt(da * db) : 0;
  }

  async function load() {
    tb.textContent = '';
    tb.append(
      h('span', { class: 'lbl', text: 'CORR CROSS-ASSET CORRELATION MATRIX:' }),
      ...[30, 60, 120, 252].map(d => h('button', { class: days === d ? 'on' : '', text: d + 'D', onclick: () => { days = d; load(); } }))
    );
    sc.textContent = '';
    const res = await Promise.all(syms.map(s => get('kline', { symbol: s, interval: '1d', limit: days + 2 }, 5000)));
    ctx.status(res.find(r => r.ok) || res[0]);

    const rets = {};
    for (let i = 0; i < syms.length; i++) {
      const c = (res[i].ok && res[i].data && res[i].data.candles) || [];
      const r = [];
      for (let k = 1; k < c.length; k++) r.push((c[k].c - c[k - 1].c) / c[k - 1].c);
      rets[syms[i]] = r;
    }

    const tbl = h('table', { class: 't mx' },
      h('thead', null, h('tr', null, [h('th', { text: `${days}D CORR` }), ...syms.map(s => h('th', { text: s }))])),
      h('tbody', null, syms.map(rSym => h('tr', { class: 'row' },
        h('td', { class: 'l lb sym', text: rSym }),
        ...syms.map(cSym => {
          if (rSym === cSym) return h('td', { class: 'c', style: 'background:#ffb000', text: '1.00' });
          const v = corrCoef(rets[rSym] || [], rets[cSym] || []);
          if (v == null) return h('td', { class: 'mu', text: 'N/A' });
          const bg = v >= 0
            ? `rgba(0, 210, 106, ${Math.min(0.85, Math.abs(v) * 0.85).toFixed(2)})`
            : `rgba(255, 59, 48, ${Math.min(0.85, Math.abs(v) * 0.85).toFixed(2)})`;
          return h('td', { class: 'c', style: `background:${bg};color:#fff`, text: v.toFixed(2) });
        })
      )))
    );
    sc.append(tbl);
  }
  load();
}


export function mountHVT(body, ctx) {
  body.classList.add('fill');
  const tb = h('div', { class: 'tb' }, h('span', { class: 'lbl', text: `HVT HISTORICAL REALIZED VOLATILITY TERM STRUCTURE [${ctx.symbol}]` }));
  const sc = h('div', { class: 'pb' });
  body.append(tb, sc);

  async function load() {
    const env = await get('kline', { symbol: ctx.symbol, interval: '1d', limit: 260 }, 5000);
    ctx.status(env);
    sc.textContent = '';
    const c = (env.ok && env.data && env.data.candles) || [];
    if (c.length < 15) {
      sc.append(h('div', { class: 'na', text: `N/A (${env.error || 'insufficient daily history'})` }));
      return;
    }
    const annFactor = /USDT|BTC|ETH/.test(ctx.symbol) ? Math.sqrt(365) : Math.sqrt(252);
    const rets = [];
    for (let i = 1; i < c.length; i++) rets.push(Math.log(c[i].c / c[i - 1].c));

    const calcVol = slice => {
      if (slice.length < 2) return null;
      const m = slice.reduce((a, b) => a + b, 0) / slice.length;
      const v = slice.reduce((a, b) => a + (b - m) ** 2, 0) / (slice.length - 1);
      return Math.sqrt(v) * annFactor * 100;
    };

    const windows = [10, 20, 30, 60, 90, 180];
    const rows = windows.filter(w => rets.length >= w).map(w => {
      const cur = calcVol(rets.slice(-w));
      const rolling = [];
      for (let i = w; i <= rets.length; i += 5) rolling.push(calcVol(rets.slice(i - w, i)));
      const hi = Math.max(...rolling), lo = Math.min(...rolling);
      const med = rolling.sort((a, b) => a - b)[Math.floor(rolling.length / 2)];
      const pctRank = hi > lo ? ((cur - lo) / (hi - lo)) * 100 : 50;
      return { w, cur, med, hi, lo, pctRank };
    });

    // Volatility Cone SVG Diagram
    if (rows.length >= 2) {
      const ns = 'http://www.w3.org/2000/svg';
      const W = 680, H = 145, PL = 38, PR = 20, PT = 16, PB = 22;
      const svg = document.createElementNS(ns, 'svg');
      svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
      svg.setAttribute('preserveAspectRatio', 'none');
      svg.style.cssText = 'width:100%;height:145px;display:block;background:#000;border-bottom:1px solid var(--border)';
      const maxV = Math.max(...rows.map(r => r.hi)) * 1.05;
      const minV = Math.max(0, Math.min(...rows.map(r => r.lo)) * 0.9);
      const sx = i => PL + (i / (rows.length - 1)) * (W - PL - PR);
      const sy = v => PT + (H - PT - PB) - ((v - minV) / (maxV - minV || 1)) * (H - PT - PB);

      const drawLine = (key, col, dash = '') => {
        const pl = document.createElementNS(ns, 'polyline');
        pl.setAttribute('fill', 'none'); pl.setAttribute('stroke', col); pl.setAttribute('stroke-width', key === 'cur' ? '2.2' : '1.3');
        if (dash) pl.setAttribute('stroke-dasharray', dash);
        pl.setAttribute('points', rows.map((r, i) => `${sx(i).toFixed(1)},${sy(r[key]).toFixed(1)}`).join(' '));
        svg.append(pl);
      };
      drawLine('hi', '#ff3b30', '3,3');
      drawLine('med', '#4da3ff', '4,2');
      drawLine('lo', '#00d26a', '3,3');
      drawLine('cur', '#ffb000');

      rows.forEach((r, i) => {
        const x = sx(i), y = sy(r.cur);
        const c = document.createElementNS(ns, 'circle');
        c.setAttribute('cx', x.toFixed(1)); c.setAttribute('cy', y.toFixed(1)); c.setAttribute('r', '3.5'); c.setAttribute('fill', '#ffb000');
        svg.append(c);
        const tx = document.createElementNS(ns, 'text');
        tx.setAttribute('x', x.toFixed(1)); tx.setAttribute('y', H - 6); tx.setAttribute('text-anchor', 'middle'); tx.setAttribute('fill', '#4da3ff'); tx.setAttribute('font-size', '10');
        tx.textContent = r.w + 'D';
        svg.append(tx);
      });
      sc.append(
        h('div', { class: 'tb', style: 'background:#070707;gap:14px;font-size:10.5px' },
          h('span', { style: 'color:#ffb000;font-weight:bold', text: '■ CURRENT HV' }),
          h('span', { style: 'color:#4da3ff', text: '--- MEDIAN HV' }),
          h('span', { style: 'color:#ff3b30', text: '--- 1Y HIGH CONE' }),
          h('span', { style: 'color:#00d26a', text: '--- 1Y LOW CONE' })
        ),
        svg
      );
    }

    sc.append(h('table', { class: 't' },
      h('thead', null, h('tr', null, ['Tenor Window', 'Current HV %', 'Median HV %', '1Y High HV %', '1Y Low HV %', 'Vol Percentile', 'Regime'].map(x => h('th', { text: x })))),
      h('tbody', null, rows.map(r => h('tr', { class: 'row' },
        h('td', { class: 'l lb sym', text: `${r.w}D REALIZED` }),
        h('td', { class: 'am sym', text: fmtNum(r.cur, 2) + '%' }),
        h('td', { text: fmtNum(r.med, 2) + '%' }),
        h('td', { class: 'dn', text: fmtNum(r.hi, 2) + '%' }),
        h('td', { class: 'up', text: fmtNum(r.lo, 2) + '%' }),
        h('td', { class: 'lb', text: r.pctRank.toFixed(0) + 'th %ile' }),
        h('td', { class: r.pctRank > 75 ? 'dn' : r.pctRank < 25 ? 'up' : 'am', text: r.pctRank > 75 ? 'HIGH VOL' : r.pctRank < 25 ? 'COMPRESSED' : 'NORMAL' })
      )))
    ));
  }
  load();
}


export function mountOVME(body, ctx, { mode = 'OVME' } = {}) {
  body.classList.add('fill');
  const tb = h('div', { class: 'tb' }, h('span', { class: 'lbl', text: `${mode} BLACK-SCHOLES OPTION PRICING, GREEKS & STRIKE CHAIN [${ctx.symbol}]` }));
  const sc = h('div', { class: 'pb' });
  body.append(tb, sc);

  let S = 100, K = 100, days = 30, rPct = 4.5, ivPct = 35;

  async function init() {
    const [qEnv, kEnv] = await Promise.all([
      get('quote', { symbols: ctx.symbol }, 3000),
      get('kline', { symbol: ctx.symbol, interval: '1d', limit: 35 }, 5000)
    ]);
    ctx.status(qEnv);
    const q = qEnv.ok && Array.isArray(qEnv.data) && qEnv.data[0];
    if (q && tickOk(q)) {
      S = q.price;
      const step = S > 1000 ? 100 : S > 100 ? 5 : S > 10 ? 1 : 0.05;
      K = Math.round(S / step) * step;
    }
    const c = (kEnv.ok && kEnv.data && kEnv.data.candles) || [];
    if (c.length >= 10) {
      const rets = [];
      for (let i = 1; i < c.length; i++) rets.push(Math.log(c[i].c / c[i - 1].c));
      const m = rets.reduce((a, b) => a + b, 0) / rets.length;
      const v = rets.reduce((a, b) => a + (b - m) ** 2, 0) / (rets.length - 1);
      ivPct = Math.max(10, Math.min(180, Math.round(Math.sqrt(v) * Math.sqrt(252) * 100)));
    }
    render();
  }

  function render() {
    sc.textContent = '';
    const inpS = h('input', { value: String(S), style: 'width:80px' });
    const inpK = h('input', { value: String(K), style: 'width:80px' });
    const inpD = h('input', { value: String(days), style: 'width:55px' });
    const inpV = h('input', { value: String(ivPct), style: 'width:55px' });
    const inpR = h('input', { value: String(rPct), style: 'width:50px' });

    const recalc = () => {
      S = parseFloat(inpS.value) || S;
      K = parseFloat(inpK.value) || K;
      days = Math.max(1, parseFloat(inpD.value) || 30);
      ivPct = Math.max(1, parseFloat(inpV.value) || 35);
      rPct = parseFloat(inpR.value) || 4.5;
      render();
    };

    const form = h('div', { class: 'tb', style: 'background:#070707' },
      h('span', { class: 'lbl', text: 'SPOT:' }), inpS,
      h('span', { class: 'lbl', text: 'STRIKE:' }), inpK,
      h('span', { class: 'lbl', text: 'DTE (DAYS):' }), inpD,
      h('span', { class: 'lbl', text: 'IV %:' }), inpV,
      h('span', { class: 'lbl', text: 'RATE %:' }), inpR,
      h('button', { class: 'on', text: 'PRICE <GO>', onclick: recalc })
    );

    const bs = blackScholes(S, K, days / 365, rPct / 100, ivPct / 100);
    if (!bs) {
      sc.append(form, h('div', { class: 'na', text: 'Invalid Black-Scholes parameters' }));
      return;
    }

    const greeksTbl = h('table', { class: 't' },
      h('thead', null, h('tr', null, ['Metric / Greek', 'CALL OPTION', 'PUT OPTION', 'Interpretation'].map(x => h('th', { text: x })))),
      h('tbody', null, [
        ['Theoretical Price', fmtPx(bs.callPx), fmtPx(bs.putPx), `% of Spot: ${((bs.callPx / S) * 100).toFixed(2)}% / ${((bs.putPx / S) * 100).toFixed(2)}%`],
        ['Delta (Δ)', bs.callDelta.toFixed(4), bs.putDelta.toFixed(4), 'dPrice / dSpot'],
        ['Gamma (Γ)', bs.gamma.toFixed(6), bs.gamma.toFixed(6), 'dDelta / dSpot'],
        ['Vega (ν)', bs.vega.toFixed(4), bs.vega.toFixed(4), 'dPrice / +1% IV'],
        ['Theta (Θ / Day)', bs.callTheta.toFixed(4), bs.putTheta.toFixed(4), 'Daily Time Decay'],
        ['Rho (ρ)', bs.callRho.toFixed(4), bs.putRho.toFixed(4), 'dPrice / +1% Rate'],
        ['Breakeven at Expiry', fmtPx(K + bs.callPx), fmtPx(K - bs.putPx), `Strike ± Premium`]
      ].map(([m, cV, pV, desc]) => h('tr', { class: 'row' },
        h('td', { class: 'l lb sym', text: m }),
        h('td', { class: 'up sym', text: cV }),
        h('td', { class: 'dn sym', text: pV }),
        h('td', { class: 'l mu', text: desc })
      )))
    );

    // Strike Chain around Spot (OMON)
    const strikes = [-0.10, -0.075, -0.05, -0.025, 0, 0.025, 0.05, 0.075, 0.10].map(pct => {
      const raw = S * (1 + pct);
      return S > 500 ? Math.round(raw / 10) * 10 : S > 10 ? Math.round(raw * 2) / 2 : +raw.toFixed(4);
    });

    const chainTbl = h('table', { class: 't' },
      h('thead', null, h('tr', null, ['Call Px', 'Call Δ', 'Call Θ', 'IV %', 'STRIKE', 'Moneyness', 'Put Px', 'Put Δ', 'Put Θ'].map(x => h('th', { text: x })))),
      h('tbody', null, strikes.map(st => {
        const skewIv = ivPct * (1 + Math.abs(st - S) / S * 0.25);
        const g = blackScholes(S, st, days / 365, rPct / 100, skewIv / 100);
        const atm = Math.abs(st - S) / S < 0.013;
        const mny = ((st / S - 1) * 100);
        return h('tr', { class: 'row', style: atm ? 'background:#1e1600' : '', onclick: () => { K = st; render(); } },
          h('td', { class: 'up sym', text: g ? fmtPx(g.callPx) : '-' }),
          h('td', { text: g ? g.callDelta.toFixed(2) : '-' }),
          h('td', { class: 'mu', text: g ? g.callTheta.toFixed(3) : '-' }),
          h('td', { class: 'lb', text: skewIv.toFixed(1) + '%' }),
          h('td', { class: 'am sym', style: 'text-align:center;background:#111', text: fmtPx(st) + (atm ? ' ★ATM' : '') }),
          h('td', { class: 'mu', text: (mny >= 0 ? '+' : '') + mny.toFixed(1) + '%' }),
          h('td', { class: 'dn sym', text: g ? fmtPx(g.putPx) : '-' }),
          h('td', { text: g ? g.putDelta.toFixed(2) : '-' }),
          h('td', { class: 'mu', text: g ? g.putTheta.toFixed(3) : '-' })
        );
      }))
    );

    sc.append(
      form,
      greeksTbl,
      h('div', { class: 'tb', style: 'background:#070707;margin-top:6px' }, h('span', { class: 'lbl', text: `OMON OPTION STRIKE CHAIN (${days} DTE, CLICK STRIKE TO LOAD IN PRICER)` })),
      chainTbl
    );
  }
  init();
}

export function mountDCF(body, ctx) {
  body.classList.add('fill');
  const tb = h('div', { class: 'tb' }, h('span', { class: 'lbl', text: `DCF / WACC INTRINSIC VALUATION & SENSITIVITY WORKBENCH [${ctx.symbol}]` }));
  const sc = h('div', { class: 'pb' });
  body.append(tb, sc);

  let fcfB = 50, growth = 10, wacc = 9.0, termG = 2.5, sharesB = 15, spot = 180;

  async function init() {
    const [fEnv, qEnv] = await Promise.all([
      get('fundamentals', { symbol: ctx.symbol }, 30000),
      get('quote', { symbols: ctx.symbol }, 3000)
    ]);
    ctx.status(fEnv.ok ? fEnv : qEnv);
    const q = (qEnv.ok && qEnv.data && qEnv.data[0]) || (fEnv.data && fEnv.data.quote);
    if (q && tickOk(q)) spot = q.price;
    const fin = fEnv.ok && fEnv.data && fEnv.data.edgar && fEnv.data.edgar.financials;
    if (fin) {
      const ocf = fin.ocf && fin.ocf[0] && fin.ocf[0].val;
      const cap = fin.capex && fin.capex[0] && fin.capex[0].val;
      const sh = fin.shares && fin.shares[0] && fin.shares[0].val;
      if (ocf != null) fcfB = +((ocf - (cap || 0)) / 1e9).toFixed(2);
      if (sh) sharesB = +(sh / 1e9).toFixed(3);
    }
    render();
  }

  function calcDCF(fcf, gPct, wPct, tgPct, sh) {
    if (wPct <= tgPct || sh <= 0) return null;
    const g = gPct / 100, w = wPct / 100, tg = tgPct / 100;
    let pvFcf = 0, cur = fcf;
    for (let yr = 1; yr <= 5; yr++) {
      cur *= (1 + g);
      pvFcf += cur / ((1 + w) ** yr);
    }
    const termVal = (cur * (1 + tg)) / (w - tg);
    const pvTerm = termVal / ((1 + w) ** 5);
    const ev = pvFcf + pvTerm;
    return { pvFcf, pvTerm, ev, fairPx: ev / sh };
  }

  function render() {
    sc.textContent = '';
    const iFcf = h('input', { value: String(fcfB), style: 'width:65px' });
    const iG = h('input', { value: String(growth), style: 'width:55px' });
    const iW = h('input', { value: String(wacc), style: 'width:55px' });
    const iT = h('input', { value: String(termG), style: 'width:55px' });
    const iS = h('input', { value: String(sharesB), style: 'width:65px' });

    const go = () => {
      fcfB = parseFloat(iFcf.value) || fcfB;
      growth = parseFloat(iG.value) || growth;
      wacc = parseFloat(iW.value) || wacc;
      termG = parseFloat(iT.value) || termG;
      sharesB = parseFloat(iS.value) || sharesB;
      render();
    };

    const bar = h('div', { class: 'tb', style: 'background:#070707' },
      h('span', { class: 'lbl', text: 'FCF ($B):' }), iFcf,
      h('span', { class: 'lbl', text: '5Y CAGR %:' }), iG,
      h('span', { class: 'lbl', text: 'WACC %:' }), iW,
      h('span', { class: 'lbl', text: 'TERM G %:' }), iT,
      h('span', { class: 'lbl', text: 'SHARES (B):' }), iS,
      h('button', { class: 'on', text: 'COMPUTE DCF', onclick: go })
    );

    const res = calcDCF(fcfB, growth, wacc, termG, sharesB);
    if (!res) {
      sc.append(bar, h('div', { class: 'na', text: 'WACC must be strictly greater than Terminal Growth %' }));
      return;
    }
    const upside = spot > 0 ? ((res.fairPx - spot) / spot) * 100 : 0;

    const kv = h('div', { class: 'kv', style: 'border-bottom:1px solid var(--border);padding:6px 8px' },
      h('div', { class: 'k', text: 'PV OF 5Y FCF ($B)' }), h('div', { class: 'v am', text: '$' + fmtNum(res.pvFcf, 2) + 'B' }),
      h('div', { class: 'k', text: 'PV OF TERMINAL VALUE ($B)' }), h('div', { class: 'v am', text: '$' + fmtNum(res.pvTerm, 2) + 'B' }),
      h('div', { class: 'k', text: 'IMPLIED ENTERPRISE VALUE' }), h('div', { class: 'v lb sym', text: '$' + fmtNum(res.ev, 2) + 'B' }),
      h('div', { class: 'k', text: 'IMPLIED INTRINSIC VALUE / SHARE' }), h('div', { class: 'v am sym', style: 'font-size:14px', text: '$' + fmtPx(res.fairPx) }),
      h('div', { class: 'k', text: `CURRENT MARKET PRICE (${ctx.symbol})` }), h('div', { class: 'v', text: '$' + fmtPx(spot) }),
      h('div', { class: 'k', text: 'IMPLIED UPSIDE / (DOWNSIDE)' }), h('div', { class: 'v sym ' + dirCls(upside), text: fmtPct(upside) })
    );

    const wSteps = [-1.0, -0.5, 0, 0.5, 1.0].map(d => +(wacc + d).toFixed(2));
    const tSteps = [-0.5, -0.25, 0, 0.25, 0.5].map(d => +(termG + d).toFixed(2));

    const sensTbl = h('table', { class: 't' },
      h('thead', null, h('tr', null, [h('th', { text: 'WACC \\ TERM G' }), ...tSteps.map(t => h('th', { text: t.toFixed(2) + '%' }))])),
      h('tbody', null, wSteps.map(w => h('tr', { class: 'row' },
        h('td', { class: 'l lb sym', text: w.toFixed(2) + '%' }),
        ...tSteps.map(t => {
          const c = calcDCF(fcfB, growth, w, t, sharesB);
          const center = w === wacc && t === termG;
          return h('td', {
            class: c ? (c.fairPx >= spot ? 'up' : 'dn') : 'mu',
            style: center ? 'background:#241a00;font-weight:bold;outline:1px solid var(--amber)' : '',
            text: c ? '$' + fmtPx(c.fairPx) : 'N/A'
          });
        })
      )))
    );

    sc.append(bar, kv, h('div', { class: 'tb', style: 'background:#070707' }, h('span', { class: 'lbl', text: 'SENSITIVITY MATRIX: IMPLIED SHARE PRICE ($)' })), sensTbl);
  }
  init();
}

export function mountFSCO(body, ctx) {
  body.classList.add('fill');
  const tb = h('div', { class: 'tb' }, h('span', { class: 'lbl', text: `FSCO FUNDAMENTAL SCORES: PIOTROSKI F-SCORE & ALTMAN Z-SCORE [${ctx.symbol}]` }));
  const sc = h('div', { class: 'pb' });
  body.append(tb, sc);

  async function load() {
    const env = await get('fundamentals', { symbol: ctx.symbol }, 30000);
    ctx.status(env);
    sc.textContent = '';
    const ed = env.ok && env.data && env.data.edgar;
    if (!ed || !ed.financials) {
      const klEnv = await get('kline', { symbol: ctx.symbol, interval: '1d', limit: 252 }, 5000);
      const c = (klEnv.ok && klEnv.data && klEnv.data.candles) || [];
      if (c.length < 25) {
        sc.append(h('div', { class: 'na', text: `Insufficient history for ${ctx.symbol}` }));
        return;
      }
      const closes = c.map(x => x.c);
      const last = closes[closes.length - 1];
      const sma = n => closes.slice(-n).reduce((a, b) => a + b, 0) / Math.min(n, closes.length);
      const sma20 = sma(20), sma50 = sma(50);
      const ret30 = closes.length > 30 ? (last - closes[closes.length - 30]) / closes[closes.length - 30] : 0;
      const ret90 = closes.length > 90 ? (last - closes[closes.length - 90]) / closes[closes.length - 90] : 0;
      let gains = 0, losses = 0;
      for (let i = closes.length - 14; i < closes.length; i++) {
        const d = closes[i] - closes[i - 1];
        if (d >= 0) gains += d; else losses -= d;
      }
      const rsi = losses === 0 ? 70 : 100 - 100 / (1 + gains / losses);
      const upVol = c.slice(-30).filter(x => x.c >= x.o).reduce((s, x) => s + (x.v || 0), 0);
      const dnVol = c.slice(-30).filter(x => x.c < x.o).reduce((s, x) => s + (x.v || 0), 0);
      const peak = Math.max(...closes.slice(-90));
      const dd = (last - peak) / peak;
      const low20 = Math.min(...closes.slice(-20));
      const low60 = Math.min(...closes.slice(-60, -20));

      const qChecks = [
        ['1. Trend Regime Above 50D SMA', last >= sma50, `Last ${fmtPx(last)} vs SMA50 ${fmtPx(sma50)}`],
        ['2. Golden Cross Structure (SMA20 >= SMA50)', sma20 >= sma50, `SMA20 ${fmtPx(sma20)} vs SMA50 ${fmtPx(sma50)}`],
        ['3. Positive 30-Day Momentum', ret30 > 0, fmtPct(ret30 * 100)],
        ['4. Positive 90-Day Medium-Term Trend', ret90 > 0, fmtPct(ret90 * 100)],
        ['5. RSI(14) Constructive Regime (35–75)', rsi >= 35 && rsi <= 75, `RSI(14) = ${rsi.toFixed(1)}`],
        ['6. Positive 30D Volume Accumulation (UpVol > DownVol)', upVol >= dnVol, `Up/Dn Vol Ratio = ${(upVol / Math.max(dnVol, 1)).toFixed(2)}x`],
        ['7. Controlled 90D Drawdown (> -25%)', dd > -0.25, fmtPct(dd * 100)],
        ['8. Higher Structural Low (20D Low >= Prior 40D Low)', low20 >= low60, `20D Low ${fmtPx(low20)} vs Prior ${fmtPx(low60)}`],
        ['9. Active Institutional Liquidity Turnover', (c[c.length - 1].v || 0) > 0, `24h Vol ${fmtVol(c[c.length - 1].v || 0)}`]
      ];
      const qScore = qChecks.filter(x => x[1]).length;
      sc.append(
        h('div', { class: 'tb', style: 'background:#070707' },
          h('span', { class: 'am sym', style: 'font-size:14px', text: `QUANTITATIVE FACTOR HEALTH SCORE (Q-SCORE): ${qScore} / 9` }),
          h('span', { class: qScore >= 7 ? 'up sym' : qScore >= 4 ? 'am sym' : 'dn sym', text: qScore >= 7 ? 'STRONG QUANT HEALTH' : qScore >= 4 ? 'NEUTRAL / BALANCED' : 'WEAK MOMENTUM' }),
          h('span', { class: 'lbl', text: 'SEC XBRL F-SCORE:' }),
          ...['AAPL', 'NVDA', 'MSFT', 'TSLA'].map(s => h('button', { text: s, onclick: () => ctx.setSymbol(s) }))
        ),
        h('table', { class: 't' },
          h('thead', null, h('tr', null, ['Quantitative Health Criterion', 'Status', 'Points', 'Observed Metric'].map(x => h('th', { text: x })))),
          h('tbody', null, qChecks.map(([name, pass, obs]) => h('tr', { class: 'row' },
            h('td', { class: 'l lb', text: name }),
            h('td', { class: pass ? 'up sym' : 'dn sym', text: pass ? 'PASS' : 'FAIL' }),
            h('td', { class: pass ? 'up sym' : 'mu', text: pass ? '+1' : '0' }),
            h('td', { class: 'am', text: obs })
          )))
        )
      );
      return;
    }
    const f = ed.financials;
    const v = (arr, idx = 0) => (arr && arr[idx] ? arr[idx].val : null);
    const ni0 = v(f.netIncome, 0), ni1 = v(f.netIncome, 1);
    const a0 = v(f.assets, 0), a1 = v(f.assets, 1);
    const ocf0 = v(f.ocf, 0);
    const d0 = v(f.debt, 0) || 0, d1 = v(f.debt, 1) || 0;
    const ca0 = v(f.curAssets, 0), cl0 = v(f.curLiab, 0), ca1 = v(f.curAssets, 1), cl1 = v(f.curLiab, 1);
    const sh0 = v(f.shares, 0), sh1 = v(f.shares, 1);
    const gp0 = v(f.grossProfit, 0), gp1 = v(f.grossProfit, 1);
    const rev0 = v(f.revenue, 0), rev1 = v(f.revenue, 1);

    const roa0 = (ni0 != null && a0) ? ni0 / a0 : 0;
    const roa1 = (ni1 != null && a1) ? ni1 / a1 : 0;
    const cr0 = (ca0 && cl0) ? ca0 / cl0 : 1, cr1 = (ca1 && cl1) ? ca1 / cl1 : 1;
    const gm0 = (gp0 != null && rev0) ? gp0 / rev0 : 0, gm1 = (gp1 != null && rev1) ? gp1 / rev1 : 0;
    const at0 = (rev0 && a0) ? rev0 / a0 : 0, at1 = (rev1 && a1) ? rev1 / a1 : 0;

    const checks = [
      ['1. Positive Return on Assets (ROA > 0)', roa0 > 0, (roa0 * 100).toFixed(2) + '%'],
      ['2. Positive Operating Cash Flow (OCF > 0)', (ocf0 || 0) > 0, fmtVol(ocf0)],
      ['3. ROA Improvement YoY (ΔROA > 0)', roa0 >= roa1, `${(roa0 * 100).toFixed(2)}% vs ${(roa1 * 100).toFixed(2)}%`],
      ['4. Accruals Quality (OCF > Net Income)', (ocf0 || 0) > (ni0 || 0), `OCF ${fmtVol(ocf0)} vs NI ${fmtVol(ni0)}`],
      ['5. Lower Leverage Ratio YoY (ΔDebt/Assets ≤ 0)', a0 && a1 ? (d0 / a0) <= (d1 / a1) : true, `${a0 ? ((d0 / a0) * 100).toFixed(1) : 0}%`],
      ['6. Higher Current Ratio YoY (ΔLiquidity > 0)', cr0 >= cr1, `${cr0.toFixed(2)}x vs ${cr1.toFixed(2)}x`],
      ['7. No Dilution (Shares Out YoY ≤ 0)', (sh0 && sh1) ? sh0 <= sh1 * 1.01 : true, fmtVol(sh0)],
      ['8. Higher Gross Margin YoY (ΔGM > 0)', gm0 >= gm1, `${(gm0 * 100).toFixed(1)}%`],
      ['9. Higher Asset Turnover YoY (ΔTurnover > 0)', at0 >= at1, `${at0.toFixed(2)}x`]
    ];
    const fScore = checks.filter(c => c[1]).length;

    sc.append(
      h('div', { class: 'tb', style: 'background:#070707' },
        h('span', { class: 'am sym', style: 'font-size:14px', text: `PIOTROSKI F-SCORE: ${fScore} / 9` }),
        h('span', { class: fScore >= 7 ? 'up sym' : fScore >= 4 ? 'am sym' : 'dn sym', text: fScore >= 7 ? 'STRONG FINANCIAL HEALTH' : fScore >= 4 ? 'MODERATE / STABLE' : 'WEAK FUNDAMENTALS' })
      ),
      h('table', { class: 't' },
        h('thead', null, h('tr', null, ['Piotroski Criterion', 'Status', 'Points', 'Observed Value'].map(x => h('th', { text: x })))),
        h('tbody', null, checks.map(([name, pass, obs]) => h('tr', { class: 'row' },
          h('td', { class: 'l lb', text: name }),
          h('td', { class: pass ? 'up sym' : 'dn sym', text: pass ? 'PASS' : 'FAIL' }),
          h('td', { class: pass ? 'up sym' : 'mu', text: pass ? '+1' : '0' }),
          h('td', { class: 'am', text: obs })
        )))
      )
    );
  }
  load();
}


export function mountYAS(body, ctx) {
  body.classList.add('fill');
  const tb = h('div', { class: 'tb' }, h('span', { class: 'lbl', text: 'YAS FIXED INCOME BOND YIELD, DURATION, CONVEXITY & DV01 CALCULATOR' }));
  const sc = h('div', { class: 'pb' });
  body.append(tb, sc);

  let face = 100, couponPct = 4.5, years = 10, ytmPct = 4.25, freq = 2;

  function render() {
    sc.textContent = '';
    const iC = h('input', { value: String(couponPct), style: 'width:55px' });
    const iY = h('input', { value: String(years), style: 'width:50px' });
    const iYtm = h('input', { value: String(ytmPct), style: 'width:55px' });

    const go = () => {
      couponPct = parseFloat(iC.value) || 4.5;
      years = Math.max(0.5, parseFloat(iY.value) || 10);
      ytmPct = parseFloat(iYtm.value) || 4.25;
      render();
    };

    const bar = h('div', { class: 'tb', style: 'background:#070707' },
      h('span', { class: 'lbl', text: 'COUPON %:' }), iC,
      h('span', { class: 'lbl', text: 'MATURITY (YRS):' }), iY,
      h('span', { class: 'lbl', text: 'YIELD (YTM %):' }), iYtm,
      h('button', { class: 'on', text: 'CALCULATE YAS', onclick: go })
    );

    const n = Math.round(years * freq);
    const y = (ytmPct / 100) / freq;
    const c = (couponPct / 100) * face / freq;
    let px = 0, macNum = 0, convNum = 0;
    for (let t = 1; t <= n; t++) {
      const cf = t === n ? c + face : c;
      const pv = cf / ((1 + y) ** t);
      px += pv;
      macNum += (t / freq) * pv;
      convNum += pv * t * (t + 1);
    }
    const macDur = macNum / px;
    const modDur = macDur / (1 + y);
    const convexity = convNum / (px * ((1 + y) ** 2) * (freq ** 2));
    const dv01 = px * modDur * 0.0001; // per $100 par

    const kv = h('div', { class: 'kv', style: 'padding:8px' },
      h('div', { class: 'k', text: 'CLEAN PRICE (% OF PAR)' }), h('div', { class: 'v am sym', style: 'font-size:15px', text: fmtNum(px, 4) }),
      h('div', { class: 'k', text: 'YIELD TO MATURITY (YTM)' }), h('div', { class: 'v lb sym', text: fmtNum(ytmPct, 3) + '%' }),
      h('div', { class: 'k', text: 'CURRENT YIELD' }), h('div', { class: 'v', text: fmtNum((couponPct / px) * 100, 3) + '%' }),
      h('div', { class: 'k', text: 'MACAULAY DURATION (YRS)' }), h('div', { class: 'v am', text: fmtNum(macDur, 3) + ' yrs' }),
      h('div', { class: 'k', text: 'MODIFIED DURATION (%)' }), h('div', { class: 'v am sym', text: fmtNum(modDur, 3) + '%' }),
      h('div', { class: 'k', text: 'CONVEXITY' }), h('div', { class: 'v lb', text: fmtNum(convexity, 3) }),
      h('div', { class: 'k', text: 'DV01 (PER $1M NOTIONAL)' }), h('div', { class: 'v up sym', text: '$' + fmtNum(dv01 * 10000, 2) })
    );

    const shocks = [-100, -50, -25, 0, 25, 50, 100];
    const tbl = h('table', { class: 't' },
      h('thead', null, h('tr', null, ['Yield Shock (bps)', 'New Yield %', 'Approx Price', 'Price Change', '% Return Impact'].map(x => h('th', { text: x })))),
      h('tbody', null, shocks.map(bp => {
        const dy = bp / 10000;
        const pctChg = (-modDur * dy + 0.5 * convexity * (dy ** 2)) * 100;
        const newPx = px * (1 + pctChg / 100);
        return h('tr', { class: 'row' },
          h('td', { class: 'l lb sym', text: (bp >= 0 ? '+' : '') + bp + ' bps' }),
          h('td', { text: (ytmPct + bp / 100).toFixed(2) + '%' }),
          h('td', { class: 'am', text: fmtNum(newPx, 3) }),
          h('td', { class: dirCls(newPx - px), text: (newPx - px >= 0 ? '+' : '') + fmtNum(newPx - px, 3) }),
          h('td', { class: dirCls(pctChg), text: fmtPct(pctChg) })
        );
      }))
    );

    sc.append(bar, kv, h('div', { class: 'tb', style: 'background:#070707' }, h('span', { class: 'lbl', text: 'DURATION + CONVEXITY RATE SHOCK SCENARIO ANALYSIS' })), tbl);
  }
  ctx.status({ source: 'quant-engine', ts: Date.now(), mode: 'LIVE' });
  render();
}

export function mountWIRP(body, ctx) {
  body.classList.add('fill');
  const tb = h('div', { class: 'tb' }, h('span', { class: 'lbl', text: 'WIRP / FOMC / TIPS FEDERAL RESERVE RATE MONITOR & BREAKEVEN INFLATION (FRED)' }));
  const sc = h('div', { class: 'pb' });
  body.append(tb, sc);

  async function load() {
    const env = await get('macro', { series: 'FEDFUNDS,DGS2,DGS10,T10YIE,DFII10,UNRATE', limit: 24 }, 15000);
    ctx.status(env);
    sc.textContent = '';
    if (!env.ok || !env.data || !env.data.series) {
      sc.append(h('div', { class: 'na', text: `N/A (${env.error || 'FRED unavailable'})` }));
      return;
    }
    const s = env.data.series;
    const latest = id => {
      const obs = s[id] && s[id].obs;
      return (Array.isArray(obs) && obs.length) ? obs[obs.length - 1] : null;
    };

    const ff = latest('FEDFUNDS');
    const y2 = latest('DGS2');
    const y10 = latest('DGS10');
    const be10 = latest('T10YIE');
    const real10 = latest('DFII10');
    const un = latest('UNRATE');

    const impliedSpreadBps = (y2 && ff) ? (y2.value - ff.value) * 100 : 0;
    const impliedCuts = impliedSpreadBps / 25;

    sc.append(
      h('div', { class: 'kv', style: 'border-bottom:1px solid var(--border);padding:8px' },
        h('div', { class: 'k', text: 'EFFECTIVE FED FUNDS RATE (EFFR)' }), h('div', { class: 'v am sym', text: ff ? `${ff.value.toFixed(2)}% (as of ${ff.date})` : 'N/A' }),
        h('div', { class: 'k', text: 'US 2Y TREASURY (POLICY PROXY)' }), h('div', { class: 'v am sym', text: y2 ? `${y2.value.toFixed(2)}% (as of ${y2.date})` : 'N/A' }),
        h('div', { class: 'k', text: '2Y - EFFR IMPLIED SPREAD' }), h('div', { class: 'v ' + dirCls(impliedSpreadBps), text: `${impliedSpreadBps >= 0 ? '+' : ''}${impliedSpreadBps.toFixed(0)} bps (${impliedCuts.toFixed(1)} x 25bp moves priced)` }),
        h('div', { class: 'k', text: 'US 10Y NOMINAL YIELD (DGS10)' }), h('div', { class: 'v lb', text: y10 ? `${y10.value.toFixed(2)}%` : 'N/A' }),
        h('div', { class: 'k', text: '10Y TIPS REAL YIELD (DFII10)' }), h('div', { class: 'v am', text: real10 ? `${real10.value.toFixed(2)}%` : 'N/A' }),
        h('div', { class: 'k', text: '10Y BREAKEVEN INFLATION (T10YIE)' }), h('div', { class: 'v up sym', text: be10 ? `${be10.value.toFixed(2)}%` : 'N/A' }),
        h('div', { class: 'k', text: 'US UNEMPLOYMENT RATE (UNRATE)' }), h('div', { class: 'v', text: un ? `${un.value.toFixed(1)}%` : 'N/A' })
      )
    );
  }
  load();
}

export function mountBTST(body, ctx) {
  body.classList.add('fill');
  let strat = 'SMA_CROSS'; // 'SMA_CROSS' | 'RSI_REV' | 'DONCHIAN'
  const tb = h('div', { class: 'tb' });
  const sc = h('div', { class: 'pb' });
  body.append(tb, sc);

  async function load() {
    tb.textContent = '';
    tb.append(
      h('span', { class: 'lbl', text: `90) Actions  |  BTST - Quantitative Strategy Backtester [${ctx.symbol}]:` }),
      ...[['SMA_CROSS', 'SMA(10/30) TREND CROSS'], ['RSI_REV', 'RSI(14) MEAN REVERSION'], ['DONCHIAN', '20-BAR BREAKOUT']].map(([k, lbl]) =>
        h('button', { class: strat === k ? 'on' : '', text: lbl, onclick: () => { strat = k; load(); } })
      )
    );

    sc.textContent = '';
    const env = await get('kline', { symbol: ctx.symbol, interval: '1d', limit: 250 }, 5000);
    ctx.status(env);
    const c = (env.ok && env.data && env.data.candles) || [];
    if (c.length < 35) {
      sc.append(h('div', { class: 'na', text: `N/A (insufficient daily bars for ${ctx.symbol})` }));
      return;
    }

    let eq = 100, bh = 100;
    const eqCurve = [], bhCurve = [], trades = [];
    let pos = 0, entryPx = 0;

    for (let i = 30; i < c.length; i++) {
      const r = (c[i].c - c[i - 1].c) / c[i - 1].c;
      bh *= (1 + r);
      if (pos !== 0) eq *= (1 + pos * r);
      eqCurve.push(eq);
      bhCurve.push(bh);

      let targetPos = pos;
      if (strat === 'SMA_CROSS') {
        const s10 = c.slice(i - 9, i + 1).reduce((s, x) => s + x.c, 0) / 10;
        const s30 = c.slice(i - 29, i + 1).reduce((s, x) => s + x.c, 0) / 30;
        targetPos = s10 >= s30 ? 1 : -1;
      } else if (strat === 'RSI_REV') {
        let g = 0, l = 0;
        for (let k = i - 13; k <= i; k++) {
          const d = c[k].c - c[k - 1].c;
          if (d >= 0) g += d; else l -= d;
        }
        const rsi = l === 0 ? 75 : 100 - 100 / (1 + g / l);
        if (rsi < 35) targetPos = 1;
        else if (rsi > 68) targetPos = -1;
      } else {
        const hi20 = Math.max(...c.slice(i - 20, i).map(x => x.h));
        const lo20 = Math.min(...c.slice(i - 20, i).map(x => x.l));
        if (c[i].c > hi20) targetPos = 1;
        else if (c[i].c < lo20) targetPos = -1;
      }

      if (targetPos !== pos) {
        if (pos !== 0 && entryPx > 0) {
          const pnlPct = pos * ((c[i].c - entryPx) / entryPx) * 100;
          trades.push({ dt: new Date(c[i].t).toISOString().slice(0, 10), side: pos > 0 ? 'LONG' : 'SHORT', entry: entryPx, exit: c[i].c, pnlPct });
        }
        pos = targetPos;
        entryPx = c[i].c;
      }
    }

    const totRet = eq - 100;
    const bhRet = bh - 100;
    const wins = trades.filter(t => t.pnlPct > 0).length;
    const winRate = trades.length ? (wins / trades.length) * 100 : 0;

    // SVG Equity Curve vs Buy & Hold Diagram
    const ns = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('viewBox', '0 0 700 155');
    svg.setAttribute('preserveAspectRatio', 'none');
    svg.style.cssText = 'width:100%;height:155px;display:block;background:#000;border-bottom:1px solid var(--border)';
    const allV = [...eqCurve, ...bhCurve];
    const minY = Math.min(...allV) * 0.98, maxY = Math.max(...allV) * 1.02;
    const sx = i => 15 + (i / (eqCurve.length - 1 || 1)) * 670;
    const sy = v => 140 - ((v - minY) / (maxY - minY || 1)) * 125;

    const pBh = document.createElementNS(ns, 'polyline');
    pBh.setAttribute('fill', 'none'); pBh.setAttribute('stroke', '#4da3ff'); pBh.setAttribute('stroke-width', '1.4'); pBh.setAttribute('stroke-dasharray', '3,2');
    pBh.setAttribute('points', bhCurve.map((v, i) => `${sx(i).toFixed(1)},${sy(v).toFixed(1)}`).join(' '));

    const pEq = document.createElementNS(ns, 'polyline');
    pEq.setAttribute('fill', 'none'); pEq.setAttribute('stroke', '#ffb000'); pEq.setAttribute('stroke-width', '2.2');
    pEq.setAttribute('points', eqCurve.map((v, i) => `${sx(i).toFixed(1)},${sy(v).toFixed(1)}`).join(' '));
    svg.append(pBh, pEq);

    sc.append(
      h('div', { class: 'tb', style: 'background:#070707;gap:14px' },
        h('span', { style: 'color:#ffb000;font-weight:bold', text: `■ STRATEGY RETURN: ${fmtPct(totRet)}` }),
        h('span', { style: 'color:#4da3ff;font-weight:bold', text: `--- BUY & HOLD: ${fmtPct(bhRet)}` }),
        h('span', { class: 'up sym', text: `WIN RATE: ${winRate.toFixed(1)}% (${wins}/${trades.length} TRADES)` }),
        h('span', { class: dirCls(totRet - bhRet) + ' sym', text: `ALPHA: ${fmtPct(totRet - bhRet)}` })
      ),
      svg,
      h('table', { class: 't' },
        h('thead', null, h('tr', null, ['#', 'Exit Date', 'Direction', 'Entry Px', 'Exit Px', 'Trade Return %', 'Result'].map(x => h('th', { text: x })))),
        h('tbody', null, [...trades].reverse().slice(0, 15).map((t, i) => h('tr', { class: 'row' },
          h('td', { class: 'l mu', text: String(trades.length - i) }),
          h('td', { class: 'l lb', text: t.dt }),
          h('td', { class: (t.side === 'LONG' ? 'up' : 'dn') + ' sym', text: t.side }),
          h('td', { text: fmtPx(t.entry) }),
          h('td', { class: 'am', text: fmtPx(t.exit) }),
          h('td', { class: dirCls(t.pnlPct) + ' sym', text: fmtPct(t.pnlPct) }),
          h('td', { class: t.pnlPct >= 0 ? 'up sym' : 'dn sym', text: t.pnlPct >= 0 ? 'WIN' : 'LOSS' })
        )))
      )
    );
  }
  load();
}


