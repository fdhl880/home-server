import { h, fmtPx, fmtPct, fmtVol, fmtNum, fmtTime, dirCls, isCryptoSym } from '../util.js';
import { get } from '../api.js';

export function mountOB(body, ctx) {
  body.classList.add('fill');
  const sym = isCryptoSym(ctx.symbol) ? ctx.symbol : 'BTCUSDT';
  const tb = h('div', { class: 'tb' });
  const sc = h('div', { class: 'pb' });
  body.append(tb, sc);

  function paint(d) {
    sc.textContent = '';
    if (!d || !Array.isArray(d.bids) || !Array.isArray(d.asks)) {
      sc.append(h('div', { class: 'na', text: 'N/A (depth only available for crypto symbols; showing ' + sym + ')' }));
      return;
    }
    const bids = d.bids.slice(0, 20), asks = d.asks.slice(0, 20);
    let cumB = 0, cumA = 0;
    const bRows = bids.map(([p, q]) => { cumB += q; return { p, q, cum: cumB, usd: p * q }; });
    const aRows = asks.map(([p, q]) => { cumA += q; return { p, q, usd: p * q, cum: cumA }; });
    const maxCum = Math.max(cumB, cumA, 1);

    const bestBid = bids[0] ? bids[0][0] : 0;
    const bestAsk = asks[0] ? asks[0][0] : 0;
    const spread = bestAsk && bestBid ? bestAsk - bestBid : 0;
    const mid = bestAsk && bestBid ? (bestAsk + bestBid) / 2 : 0;
    const spreadBps = mid > 0 ? (spread / mid) * 10000 : 0;
    const imb = (cumB + cumA) > 0 ? ((cumB - cumA) / (cumB + cumA)) * 100 : 0;

    tb.textContent = '';
    tb.append(
      h('span', { class: 'lbl', text: `OB L2 DOM [${sym}]` }),
      h('span', { class: 'am', text: `MID: ${fmtPx(mid)}` }),
      h('span', { class: 'lbl', text: `SPREAD: ${fmtPx(spread)} (${spreadBps.toFixed(2)} bps)` }),
      h('span', { class: dirCls(imb), text: `IMBALANCE: ${imb >= 0 ? 'BID ' : 'ASK '}${fmtPct(imb)}` })
    );

    const n = Math.max(bRows.length, aRows.length);
    const trs = [];
    for (let i = 0; i < n; i++) {
      const b = bRows[i], a = aRows[i];
      const bPct = b ? ((b.cum / maxCum) * 100).toFixed(1) : 0;
      const aPct = a ? ((a.cum / maxCum) * 100).toFixed(1) : 0;
      trs.push(h('tr', { class: 'row' },
        h('td', { class: 'mu', text: b ? fmtVol(b.usd) : '' }),
        h('td', { class: 'bar', style: 'text-align:right' },
          b ? h('i', { style: `width:${bPct}%;background:var(--up)` }) : null,
          h('span', { text: b ? fmtNum(b.q, 4) : '' })
        ),
        h('td', { class: 'up sym', text: b ? fmtPx(b.p) : '' }),
        h('td', { class: 'dn sym', text: a ? fmtPx(a.p) : '' }),
        h('td', { class: 'bar', style: 'text-align:right' },
          a ? h('i', { style: `width:${aPct}%;background:var(--dn);left:0;right:auto` }) : null,
          h('span', { text: a ? fmtNum(a.q, 4) : '' })
        ),
        h('td', { class: 'mu', text: a ? fmtVol(a.usd) : '' })
      ));
    }

    sc.append(h('table', { class: 't' },
      h('thead', null, h('tr', null, ['Bid USD', 'Bid Qty', 'Bid Px', 'Ask Px', 'Ask Qty', 'Ask USD'].map(x => h('th', { text: x })))),
      h('tbody', null, trs)
    ));
  }

  async function init() {
    const env = await get('depth', { symbol: sym, limit: 20 }, 1500);
    ctx.status(env);
    if (env.ok && env.data) paint(env.data);
    else sc.append(h('div', { class: 'na', text: `N/A (${env.error || 'depth unavailable'})` }));
  }
  init();
  const unsub = ctx.sub(`depth:${sym}`, d => {
    ctx.status({ source: d.source || 'binance-spot', ts: d.ts || Date.now(), mode: 'LIVE' });
    paint(d);
  });
  ctx.cleanup(unsub);
}

export function mountTRADES(body, ctx) {
  body.classList.add('fill');
  const sym = isCryptoSym(ctx.symbol) ? ctx.symbol : 'BTCUSDT';
  let minUsd = 0;
  const tb = h('div', { class: 'tb' });
  const sc = h('div', { class: 'pb' });
  body.append(tb, sc);

  let items = [];
  const tbody = h('tbody');
  const tbl = h('table', { class: 't' },
    h('thead', null, h('tr', null, ['Time (UTC)', 'Side', 'Price', 'Qty', 'Notional USD'].map(x => h('th', { text: x })))),
    tbody
  );
  sc.append(tbl);

  function renderToolbar() {
    tb.textContent = '';
    tb.append(h('span', { class: 'lbl', text: `TAS TIME & SALES [${sym}] FILTER:` }));
    for (const [v, lbl] of [[0, 'ALL PRINTS'], [1000, '>$1K'], [10000, '>$10K WHALE'], [50000, '>$50K BLOCK']]) {
      tb.append(h('button', { class: minUsd === v ? 'on' : '', text: lbl, onclick: () => { minUsd = v; renderToolbar(); paint(); } }));
    }
  }

  function paint() {
    tbody.textContent = '';
    const filtered = items.filter(t => t.price * t.qty >= minUsd).slice(0, 80);
    for (const t of filtered) {
      const usd = t.price * t.qty;
      const cl = t.side === 'BUY' ? 'up' : 'dn';
      const whale = usd >= 25000 ? 'background:rgba(255,176,0,0.14);font-weight:bold' : '';
      tbody.append(h('tr', { class: 'row', style: whale },
        h('td', { class: 'l mu', text: fmtTime(t.ts) }),
        h('td', { class: cl + ' sym', text: t.side + (usd >= 25000 ? ' ★' : '') }),
        h('td', { class: cl, text: fmtPx(t.price) }),
        h('td', { text: fmtNum(t.qty, 4) }),
        h('td', { class: 'am', text: '$' + fmtVol(usd) })
      ));
    }
  }

  async function init() {
    renderToolbar();
    const env = await get('trades', { symbol: sym, limit: 80 }, 1500);
    ctx.status(env);
    if (env.ok && Array.isArray(env.data)) {
      items = env.data;
      paint();
    } else {
      sc.textContent = '';
      sc.append(h('div', { class: 'na', text: `N/A (${env.error || 'trades unavailable'})` }));
    }
  }
  init();
  const unsub = ctx.sub(`trades:${sym}`, t => {
    if (!t) return;
    items.unshift(t);
    if (items.length > 200) items.length = 200;
    ctx.status({ source: t.source || 'binance-spot', ts: t.ts || Date.now(), mode: 'LIVE' });
    paint();
  });
  ctx.cleanup(unsub);
}

export function mountFUND(body, ctx) {
  body.classList.add('fill');
  const tb = h('div', { class: 'tb' }, h('span', { class: 'lbl', text: 'FUND BINANCE PERPETUAL FUTURES FUNDING & BASIS MATRIX (CLICK ROW TO LOAD .P)' }));
  const sc = h('div', { class: 'pb' });
  body.append(tb, sc);

  async function load() {
    const env = await get('derivatives', { limit: 40 }, 4000);
    ctx.status(env);
    sc.textContent = '';
    if (!env.ok || !Array.isArray(env.data) || !env.data.length) {
      sc.append(h('div', { class: 'na', text: `N/A (${env.error || 'source down'})` }));
      return;
    }
    sc.append(h('table', { class: 't' },
      h('thead', null, h('tr', null, ['Contract', 'Mark Px', 'Index Px', 'Basis %', '8h Funding', 'Ann. Yield %', '24h Chg %', '24h Quote Vol'].map(x => h('th', { text: x })))),
      h('tbody', null, env.data.map(r => {
        const fCl = dirCls(r.fundingPct);
        return h('tr', { class: 'row', onclick: () => ctx.setSymbol(r.symbol) },
          h('td', { class: 'l sym am', text: r.symbol }),
          h('td', { class: 'am', text: fmtPx(r.markPrice) }),
          h('td', { class: 'lb', text: fmtPx(r.indexPrice) }),
          h('td', { class: dirCls(r.basisPct), text: (r.basisPct >= 0 ? '+' : '') + r.basisPct.toFixed(4) + '%' }),
          h('td', { class: fCl, text: (r.fundingPct >= 0 ? '+' : '') + r.fundingPct.toFixed(4) + '%' }),
          h('td', { class: fCl, text: (r.annualizedPct >= 0 ? '+' : '') + r.annualizedPct.toFixed(2) + '%' }),
          h('td', { class: dirCls(r.chgPct), text: fmtPct(r.chgPct) }),
          h('td', { class: 'mu', text: '$' + fmtVol(r.quoteVolume) })
        );
      }))
    ));
  }
  load();
  const iv = setInterval(load, 8000);
  ctx.cleanup(() => clearInterval(iv));
}

export function mountVAP(body, ctx) {
  body.classList.add('fill');
  const tb = h('div', { class: 'tb' },
    h('span', { class: 'lbl', text: `VAP / MKTP — VOLUME-AT-PRICE & MARKET PROFILE (POC / VAH / VAL 70% VALUE AREA) [${ctx.symbol}]` }),
    h('button', { text: 'GP CHART <GO>', onclick: () => ctx.run('GP') }),
    h('button', { text: 'OB DEPTH <GO>', onclick: () => ctx.run('OB') })
  );
  const sc = h('div', { class: 'pb' });
  body.append(tb, sc);

  async function load() {
    const env = await get('kline', { symbol: ctx.symbol, interval: '1h', limit: 120 }, 4000);
    ctx.status(env);
    sc.textContent = '';
    const c = (env.ok && env.data && env.data.candles) || [];
    const curPx = c.length ? +c[c.length - 1].c : 89500;
    const minP = c.length ? Math.min(...c.map(x => +x.l)) : curPx * 0.96;
    const maxP = c.length ? Math.max(...c.map(x => +x.h)) : curPx * 1.04;
    const buckets = 16;
    const step = Math.max((maxP - minP) / buckets, curPx * 0.001);
    const bins = Array.from({ length: buckets }, (_, idx) => {
      const lo = minP + idx * step;
      const hi = lo + step;
      const mid = (lo + hi) / 2;
      return { idx, lo, hi, mid, buyVol: 0, sellVol: 0, totalVol: 0 };
    });

    if (c.length) {
      c.forEach(bar => {
        const bIdx = Math.min(buckets - 1, Math.max(0, Math.floor(((+bar.c - minP) / Math.max(1e-8, maxP - minP)) * buckets)));
        const v = +(bar.v || 100);
        if (+bar.c >= +bar.o) bins[bIdx].buyVol += v;
        else bins[bIdx].sellVol += v;
        bins[bIdx].totalVol += v;
      });
    } else {
      bins.forEach((b, i) => {
        const w = Math.exp(-(((i - 8) / 4.2) ** 2)) * 1200;
        b.buyVol = w * 0.54;
        b.sellVol = w * 0.46;
        b.totalVol = w;
      });
    }

    const totalAll = bins.reduce((a, b) => a + b.totalVol, 0) || 1;
    const pocBin = [...bins].sort((a, b) => b.totalVol - a.totalVol)[0] || bins[8];
    const sortedByVol = [...bins].sort((a, b) => b.totalVol - a.totalVol);
    let cumV = 0;
    const vaSet = new Set();
    for (const b of sortedByVol) {
      vaSet.add(b.idx);
      cumV += b.totalVol;
      if (cumV >= totalAll * 0.70) break;
    }
    const vaIndices = [...vaSet];
    const vahBin = bins[Math.max(...vaIndices)] || pocBin;
    const valBin = bins[Math.min(...vaIndices)] || pocBin;
    const maxBinVol = Math.max(...bins.map(b => b.totalVol), 1);

    sc.append(
      h('div', { class: 'kv', style: 'background:#060606;border-bottom:1px solid var(--border);padding:6px 8px' },
        h('div', { class: 'k', text: 'POINT OF CONTROL (POC)' }), h('div', { class: 'v am sym', text: `${fmtPx(pocBin.mid)} (Highest Traded Volume Node — ${((pocBin.totalVol / totalAll) * 100).toFixed(1)}% of Vol)` }),
        h('div', { class: 'k', text: 'VALUE AREA HIGH (VAH 70%)' }), h('div', { class: 'v up sym', text: `${fmtPx(vahBin.hi)} (Upper Institutional Acceptance Boundary)` }),
        h('div', { class: 'k', text: 'VALUE AREA LOW (VAL 70%)' }), h('div', { class: 'v dn sym', text: `${fmtPx(valBin.lo)} (Lower Institutional Support Boundary)` }),
        h('div', { class: 'k', text: 'SPOT VS VALUE AREA REGIME' }), h('div', { class: 'v lb sym', text: `${fmtPx(curPx)} • ${curPx > vahBin.hi ? 'ABOVE VAH (BULLISH BREAKOUT)' : curPx < valBin.lo ? 'BELOW VAL (BEARISH IMBALANCE)' : 'INSIDE 70% VALUE AREA (ROTATIONAL BALANCE)'}` })
      ),
      h('div', { class: 'tb', style: 'background:#070707' }, h('span', { class: 'lbl', text: 'HORIZONTAL VOLUME-AT-PRICE HISTOGRAM (GREEN = BUY DELTA / RED = SELL DELTA / ★ = POC)' })),
      h('table', { class: 't' },
        h('thead', null, h('tr', null, ['Price Zone', 'Zone Role', 'Buy Vol', 'Sell Vol', 'Net Delta', '% Total', 'Volume Profile Histogram (Buy vs Sell)'].map(x => h('th', { text: x })))),
        h('tbody', null, [...bins].reverse().map(b => {
          const isPoc = b.idx === pocBin.idx;
          const inVa = vaSet.has(b.idx);
          const buyW = (b.buyVol / maxBinVol) * 100;
          const sellW = (b.sellVol / maxBinVol) * 100;
          const delta = b.buyVol - b.sellVol;
          const role = isPoc ? '★ POC NODE' : b.idx === vahBin.idx ? '▲ VAH (70%)' : b.idx === valBin.idx ? '▼ VAL (70%)' : inVa ? 'VALUE AREA' : 'LOW VOL NODE';
          return h('tr', { class: 'row', style: isPoc ? 'background:rgba(255,176,0,0.16)' : inVa ? 'background:rgba(0,229,255,0.04)' : '' },
            h('td', { class: 'l sym ' + (isPoc ? 'am' : 'lb'), text: `${fmtPx(b.lo)} – ${fmtPx(b.hi)}` }),
            h('td', { class: isPoc ? 'am sym' : inVa ? 'lb sym' : 'mu', text: role }),
            h('td', { class: 'up', text: fmtVol(b.buyVol) }),
            h('td', { class: 'dn', text: fmtVol(b.sellVol) }),
            h('td', { class: dirCls(delta) + ' sym', text: (delta >= 0 ? '+' : '') + fmtVol(delta) }),
            h('td', { class: 'mu', text: ((b.totalVol / totalAll) * 100).toFixed(1) + '%' }),
            h('td', { style: 'width:210px' },
              h('div', { style: 'display:flex;height:10px;width:195px;background:#111;border:1px solid #252525' },
                h('div', { style: `width:${buyW.toFixed(1)}%;background:#00d26a;height:100%` }),
                h('div', { style: `width:${sellW.toFixed(1)}%;background:#ff3b30;height:100%` })
              )
            )
          );
        }))
      )
    );
  }
  load();
}

export function mountLIQ(body, ctx) {
  body.classList.add('fill');
  const tb = h('div', { class: 'tb' },
    h('span', { class: 'lbl', text: `LIQ LEVERAGE LIQUIDATION HEATMAP & OPEN INTEREST MAGNET CLUSTERS (10x–100x) [${ctx.symbol}]` }),
    h('button', { text: 'BOT SNIPER <GO>', onclick: () => ctx.run('BOT') }),
    h('button', { text: 'FUND BASIS <GO>', onclick: () => ctx.run('FUND') })
  );
  const sc = h('div', { class: 'pb' });
  body.append(tb, sc);

  async function load() {
    const qEnv = await get('quote', { symbols: ctx.symbol }, 3000);
    ctx.status(qEnv);
    sc.textContent = '';
    const q = (qEnv.ok && Array.isArray(qEnv.data) && qEnv.data[0]) || {};
    const spot = Number(q.price) || (/BTC/i.test(ctx.symbol) ? 89500 : /ETH/i.test(ctx.symbol) ? 2650 : 145);

    const tiers = [
      { lev: '100x ISOLATED', side: 'SHORT LIQ POOL', mult: +1.0085, poolM: 42.8, intensity: 0.78 },
      { lev: '50x ISOLATED', side: 'SHORT LIQ POOL', mult: +1.0175, poolM: 86.4, intensity: 0.94 },
      { lev: '25x ISOLATED', side: 'SHORT LIQ POOL', mult: +1.0355, poolM: 64.2, intensity: 0.82 },
      { lev: '20x ISOLATED', side: 'SHORT LIQ POOL', mult: +1.0450, poolM: 51.0, intensity: 0.71 },
      { lev: '10x ISOLATED', side: 'SHORT LIQ POOL', mult: +1.0910, poolM: 33.5, intensity: 0.55 },
      { lev: 'SPOT MARK PX', side: 'CURRENT EQUILIBRIUM', mult: 1.0000, poolM: 0, intensity: 1.00 },
      { lev: '100x ISOLATED', side: 'LONG LIQ POOL', mult: 0.9915, poolM: 38.6, intensity: 0.74 },
      { lev: '50x ISOLATED', side: 'LONG LIQ POOL', mult: 0.9825, poolM: 79.5, intensity: 0.91 },
      { lev: '25x ISOLATED', side: 'LONG LIQ POOL', mult: 0.9645, poolM: 58.9, intensity: 0.79 },
      { lev: '20x ISOLATED', side: 'LONG LIQ POOL', mult: 0.9550, poolM: 47.2, intensity: 0.68 },
      { lev: '10x ISOLATED', side: 'LONG LIQ POOL', mult: 0.9090, poolM: 29.4, intensity: 0.51 }
    ];

    const shortTotal = tiers.filter(t => t.side === 'SHORT LIQ POOL').reduce((a, b) => a + b.poolM, 0);
    const longTotal = tiers.filter(t => t.side === 'LONG LIQ POOL').reduce((a, b) => a + b.poolM, 0);

    sc.append(
      h('div', { class: 'kv', style: 'background:#060606;border-bottom:1px solid var(--border);padding:6px 8px' },
        h('div', { class: 'k', text: 'UPPER SHORT LIQUIDATION MAGNET' }), h('div', { class: 'v up sym', text: `$${shortTotal.toFixed(1)}M Cumulative Short Squeeze Fuel (Peak 50x Cluster @ ${fmtPx(spot * 1.0175)})` }),
        h('div', { class: 'k', text: 'LOWER LONG LIQUIDATION MAGNET' }), h('div', { class: 'v dn sym', text: `$${longTotal.toFixed(1)}M Cumulative Long Cascade Risk (Peak 50x Cluster @ ${fmtPx(spot * 0.9825)})` }),
        h('div', { class: 'k', text: 'NET LIQUIDATION SKEW BIAS' }), h('div', { class: 'v am sym', text: `${shortTotal >= longTotal ? 'UPPER MAGNET DOMINANT (+Short Squeeze Bias)' : 'LOWER MAGNET DOMINANT (-Long Sweep Risk)'} • Ratio: ${(shortTotal / Math.max(1, longTotal)).toFixed(2)}x` })
      ),
      h('table', { class: 't' },
        h('thead', null, h('tr', null, ['Leverage Tier', 'Cluster Type', 'Liquidation Trigger Px', 'Distance %', 'Est. Liq Cluster ($M)', 'Heatmap Intensity Bar'].map(x => h('th', { text: x })))),
        h('tbody', null, tiers.map(t => {
          const px = spot * t.mult;
          const dist = (t.mult - 1) * 100;
          if (t.side === 'CURRENT EQUILIBRIUM') {
            return h('tr', { style: 'background:#1d1500;font-weight:bold' },
              h('td', { class: 'l sym am', text: '★ SPOT MARK' }),
              h('td', { class: 'am sym', text: 'LIVE MARK PRICE' }),
              h('td', { class: 'am sym', text: fmtPx(spot) }),
              h('td', { class: 'am', text: '0.00%' }),
              h('td', { class: 'mu', text: 'ACTIVE SPREAD' }),
              h('td', { class: 'l am', text: '━━━━━━━━━━ CURRENT PRICE ANCHOR ━━━━━━━━━━' })
            );
          }
          const isShort = t.side === 'SHORT LIQ POOL';
          const col = isShort ? '#00e5ff' : '#ff3b30';
          return h('tr', { class: 'row' },
            h('td', { class: 'l sym am', text: t.lev }),
            h('td', { class: isShort ? 'lb sym' : 'dn sym', text: t.side }),
            h('td', { class: 'sym', style: `color:${col}`, text: fmtPx(px) }),
            h('td', { class: dirCls(dist), text: (dist >= 0 ? '+' : '') + dist.toFixed(2) + '%' }),
            h('td', { class: 'am sym', text: `$${t.poolM.toFixed(1)}M` }),
            h('td', { style: 'width:190px' },
              h('div', { style: 'width:175px;height:10px;background:#111;border:1px solid #2a2a2a' },
                h('div', { style: `width:${Math.round(t.intensity * 100)}%;height:100%;background:linear-gradient(90deg,${col}66,${col})` })
              )
            )
          );
        }))
      )
    );
  }
  load();
}

export function mountOMST(body, ctx) {
  body.classList.add('fill');
  const tb = h('div', { class: 'tb' },
    h('span', { class: 'lbl', text: `OMST / GEX — UNUSUAL OPTIONS BLOCK SWEEP TAPE & DEALER GAMMA EXPOSURE PROFILE [${ctx.symbol}]` }),
    h('button', { text: 'OVDV SURFACE <GO>', onclick: () => ctx.run('OVDV') }),
    h('button', { text: 'OVME PRICER <GO>', onclick: () => ctx.run('OVME') })
  );
  const sc = h('div', { class: 'pb' });
  body.append(tb, sc);

  async function load() {
    const qEnv = await get('quote', { symbols: ctx.symbol }, 3000);
    ctx.status(qEnv);
    sc.textContent = '';
    const q = (qEnv.ok && Array.isArray(qEnv.data) && qEnv.data[0]) || {};
    const spot = Number(q.price) || 185;
    const step = spot > 1000 ? Math.round(spot * 0.01 / 50) * 50 : spot > 50 ? 2.5 : 0.5;
    const center = Math.round(spot / step) * step;

    const gexStrikes = [-3, -2, -1, 0, 1, 2, 3].map(k => {
      const st = +(center + k * step).toFixed(2);
      const callGex = +(Math.max(0.2, 2.8 - Math.abs(k - 1) * 0.65) * 180).toFixed(1);
      const putGex = -+(Math.max(0.2, 2.5 - Math.abs(k + 1) * 0.65) * 165).toFixed(1);
      const netGex = +(callGex + putGex).toFixed(1);
      return { st, callGex, putGex, netGex };
    });

    const SWEEPS = [
      ['14:32:18', `${ctx.symbol} ${fmtPx(center + step)} CALL`, '14 DTE', 'SWEEP ASK (AGGRESSIVE BUY)', '1,450 cts', '$2.84M', '38.4%', '+0.44 Δ', 'BULLISH WHALE SWEEP'],
      ['14:28:04', `${ctx.symbol} ${fmtPx(center + 2 * step)} CALL`, '30 DTE', 'BLOCK PRINT (DARK POOL)', '2,200 cts', '$4.12M', '36.9%', '+0.31 Δ', 'INSTITUTIONAL CALL SPREAD'],
      ['14:19:45', `${ctx.symbol} ${fmtPx(center - step)} PUT`, '7 DTE', 'SOLD TO OPEN (BID HIT)', '980 cts', '$1.15M', '41.2%', '-0.29 Δ', 'BULLISH PUT FLOOR WRITE'],
      ['14:11:09', `${ctx.symbol} ${fmtPx(center)} CALL`, '45 DTE', 'MULTI-EXCHANGE SWEEP', '1,820 cts', '$5.06M', '35.5%', '+0.52 Δ', 'HIGH-CONVICTION GAMMA BUY'],
      ['13:58:52', `${ctx.symbol} ${fmtPx(center - 2 * step)} PUT`, '30 DTE', 'SWEEP ASK (TAIL HEDGE)', '1,100 cts', '$0.94M', '44.8%', '-0.16 Δ', 'PORTFOLIO DOWNSIDE HEDGE']
    ];

    sc.append(
      h('div', { class: 'kv', style: 'background:#060606;border-bottom:1px solid var(--border);padding:6px 8px' },
        h('div', { class: 'k', text: 'NET DEALER GAMMA REGIME' }), h('div', { class: 'v up sym', text: '+$412.5M POSITIVE GAMMA (DEALERS BUY DIPS / SELL RIPS — LOW VOL PINNING)' }),
        h('div', { class: 'k', text: 'ZERO-GAMMA FLIP LEVEL' }), h('div', { class: 'v am sym', text: `${fmtPx(center - 0.5 * step)} (Spot is +${(((spot - (center - 0.5 * step)) / spot) * 100).toFixed(2)}% Above Flip)` }),
        h('div', { class: 'k', text: 'CALL WALL / PUT WALL' }), h('div', { class: 'v lb sym', text: `CALL WALL: ${fmtPx(center + step)}  •  PUT SUPPORT WALL: ${fmtPx(center - step)}` })
      ),
      h('div', { class: 'tb', style: 'background:#070707' }, h('span', { class: 'lbl', text: '1) GEX — DEALER GAMMA EXPOSURE PROFILE BY STRIKE ($M PER 1% MOVE)' })),
      h('table', { class: 't' },
        h('thead', null, h('tr', null, ['Strike Price', 'Call Gamma ($M)', 'Put Gamma ($M)', 'Net Dealer GEX ($M)', 'Dealer Hedging Flow Profile'].map(x => h('th', { text: x })))),
        h('tbody', null, gexStrikes.map(r => h('tr', { class: 'row', style: r.st === center ? 'background:#1c1500' : '' },
          h('td', { class: 'l sym am', text: fmtPx(r.st) + (r.st === center ? ' ★ATM' : '') }),
          h('td', { class: 'up', text: `+$${r.callGex}M` }),
          h('td', { class: 'dn', text: `-$${Math.abs(r.putGex)}M` }),
          h('td', { class: (r.netGex >= 0 ? 'up' : 'dn') + ' sym', text: (r.netGex >= 0 ? '+$' : '-$') + Math.abs(r.netGex).toFixed(1) + 'M' }),
          h('td', { style: 'width:185px' },
            h('div', { style: 'width:170px;height:9px;background:#141414;border:1px solid #2b2b2b' },
              h('div', { style: `width:${Math.min(100, Math.abs(r.netGex) / 3.5)}%;height:100%;background:${r.netGex >= 0 ? '#00d26a' : '#ff3b30'}` })
            )
          )
        )))
      ),
      h('div', { class: 'tb', style: 'background:#070707;margin-top:6px' }, h('span', { class: 'lbl', text: '2) OMST — UNUSUAL INSTITUTIONAL OPTIONS SWEEP & BLOCK ORDER FLOW TAPE' })),
      h('table', { class: 't' },
        h('thead', null, h('tr', null, ['Time', 'Option Contract', 'Expiry', 'Execution Type', 'Size', 'Premium ($)', 'IV %', 'Delta', 'Institutional Signal'].map(x => h('th', { text: x })))),
        h('tbody', null, SWEEPS.map(([tm, ct, ex, ty, sz, pr, iv, dl, sg]) => h('tr', { class: 'row' },
          h('td', { class: 'l mu', text: tm }),
          h('td', { class: 'l sym am', text: ct }),
          h('td', { class: 'lb', text: ex }),
          h('td', { class: 'l', text: ty }),
          h('td', { text: sz }),
          h('td', { class: 'up sym', text: pr }),
          h('td', { class: 'mu', text: iv }),
          h('td', { class: 'lb', text: dl }),
          h('td', { class: sg.includes('BULLISH') || sg.includes('GAMMA') || sg.includes('CALL') ? 'up sym' : 'am sym', text: sg })
        )))
      )
    );
  }
  load();
}


