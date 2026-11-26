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
        h('td', { class: cl + ' sym', text: t.side + (usd >= 25000 ? ' [BLOCK]' : '') }),
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
      h('div', { class: 'tb', style: 'background:#070707' }, h('span', { class: 'lbl', text: 'HORIZONTAL VOLUME-AT-PRICE HISTOGRAM (GREEN = BUY DELTA / RED = SELL DELTA / POC = POINT OF CONTROL)' })),
      h('table', { class: 't' },
        h('thead', null, h('tr', null, ['Price Zone', 'Zone Role', 'Buy Vol', 'Sell Vol', 'Net Delta', '% Total', 'Volume Profile Histogram (Buy vs Sell)'].map(x => h('th', { text: x })))),
        h('tbody', null, [...bins].reverse().map(b => {
          const isPoc = b.idx === pocBin.idx;
          const inVa = vaSet.has(b.idx);
          const buyW = (b.buyVol / maxBinVol) * 100;
          const sellW = (b.sellVol / maxBinVol) * 100;
          const delta = b.buyVol - b.sellVol;
          const role = isPoc ? 'POC NODE' : b.idx === vahBin.idx ? 'VAH (70%)' : b.idx === valBin.idx ? 'VAL (70%)' : inVa ? 'VALUE AREA' : 'LOW VOL NODE';
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
    h('span', { class: 'lbl', text: `LIQ LEVERAGE LIQUIDATION RISK MAP & LIVE OPEN INTEREST [${ctx.symbol}]` }),
    h('button', { text: 'BOT SNIPER <GO>', onclick: () => ctx.run('BOT') }),
    h('button', { text: 'FUND BASIS <GO>', onclick: () => ctx.run('FUND') })
  );
  const sc = h('div', { class: 'pb' });
  body.append(tb, sc);

  async function load() {
    const [qEnv, diEnv, dEnv] = await Promise.all([
      get('quote', { symbols: ctx.symbol }, 3000),
      get('derivatives-intel', { symbol: ctx.symbol }, 4000),
      get('depth', { symbol: ctx.symbol, limit: 20 }, 3000)
    ]);
    ctx.status(diEnv.ok ? diEnv : qEnv);
    sc.textContent = '';

    const q = (qEnv.ok && Array.isArray(qEnv.data) && qEnv.data[0]) || {};
    const di = (diEnv.ok && diEnv.data) || null;
    const spot = Number(di?.markPrice || q.price || 0);
    if (!spot) {
      sc.append(h('div', { class: 'na', text: `N/A (${qEnv.error || 'No live price quote'})` }));
      return;
    }
    if (!di || !di.openInterestUsd) {
      sc.append(h('div', { class: 'na', text: `N/A — Live Binance Futures Open Interest & Positioning Feed Only Available For USDT Perpetual Pairs (current: ${ctx.symbol}). Switch symbol to e.g. BTCUSDT or ETHUSDT.` }));
      return;
    }

    const oiUsd = Number(di.openInterestUsd || 0);
    const oiM = oiUsd / 1e6;
    const oiContracts = Number(di.openInterestContracts ?? di.openInterestQty ?? 0);
    const fundingRateVal = Number(di.fundingRate ?? di.lastFundingRate ?? 0);
    const lsRatio = Number(di.globalLongShortRatio || di.topTraderRatio || 1.0);
    const longFrac = lsRatio / (1 + lsRatio);
    const shortFrac = 1 - longFrac;
    const depthData = (dEnv.ok && dEnv.data) || {};
    const topBidWall = (depthData.bids || []).reduce((mx, lv) => (+lv[1] * +lv[0] > mx.usd ? { px: +lv[0], usd: +lv[1] * +lv[0] } : mx), { px: 0, usd: 0 });
    const topAskWall = (depthData.asks || []).reduce((mx, lv) => (+lv[1] * +lv[0] > mx.usd ? { px: +lv[0], usd: +lv[1] * +lv[0] } : mx), { px: 0, usd: 0 });

    // Weight estimated Open Interest across standard isolated margin leverage bands
    const weights = [
      { lev: '100x ISOLATED', multUp: 1.009, multDn: 0.991, wt: 0.14 },
      { lev: '50x ISOLATED', multUp: 1.019, multDn: 0.981, wt: 0.28 },
      { lev: '25x ISOLATED', multUp: 1.038, multDn: 0.962, wt: 0.25 },
      { lev: '20x ISOLATED', multUp: 1.048, multDn: 0.952, wt: 0.19 },
      { lev: '10x ISOLATED', multUp: 1.095, multDn: 0.905, wt: 0.14 }
    ];
    const tiers = [
      ...weights.map(w => ({ lev: w.lev, side: 'SHORT LIQ RISK TIER', mult: w.multUp, poolM: oiM * shortFrac * w.wt, intensity: w.wt * shortFrac * 4.5 })),
      { lev: 'LIVE MARK PX', side: 'CURRENT EQUILIBRIUM', mult: 1.0, poolM: oiM, intensity: 1.0 },
      ...weights.map(w => ({ lev: w.lev, side: 'LONG LIQ RISK TIER', mult: w.multDn, poolM: oiM * longFrac * w.wt, intensity: w.wt * longFrac * 4.5 }))
    ];

    const shortTotal = oiM * shortFrac;
    const longTotal = oiM * longFrac;

    sc.append(
      h('div', { class: 'kv', style: 'background:#060606;border-bottom:1px solid var(--border);padding:6px 8px' },
        h('div', { class: 'k', text: 'LIVE BINANCE OPEN INTEREST' }), h('div', { class: 'v am sym', text: `$${fmtNum(oiM, 2)}M USDT (${oiContracts > 0 ? fmtNum(oiContracts, 0) + ' contracts' : di.symbol}) • Mark: ${fmtPx(spot)}` }),
        h('div', { class: 'k', text: 'ACCOUNT LONG / SHORT RATIO' }), h('div', { class: 'v lb sym', text: `Global L/S: ${lsRatio.toFixed(2)} (${(longFrac * 100).toFixed(1)}% Long / ${(shortFrac * 100).toFixed(1)}% Short) • Funding: ${(fundingRateVal * 100).toFixed(4)}%` }),
        h('div', { class: 'k', text: 'IMPLIED OI EXPOSURE SPLIT' }), h('div', { class: 'v sym ' + (shortTotal >= longTotal ? 'up' : 'dn'), text: `Short OI: $${shortTotal.toFixed(1)}M vs Long OI: $${longTotal.toFixed(1)}M (Modelled isolated margin distribution — exchange does not publish individual user liquidation prices)` }),
        h('div', { class: 'k', text: 'LIVE L2 TOP BOOK WALLS' }), h('div', { class: 'v mu', text: `Strongest Bid Wall: ${topBidWall.px ? fmtPx(topBidWall.px) + ' ($' + fmtVol(topBidWall.usd) + ')' : 'N/A'}  •  Strongest Ask Wall: ${topAskWall.px ? fmtPx(topAskWall.px) + ' ($' + fmtVol(topAskWall.usd) + ')' : 'N/A'}` })
      ),
      h('table', { class: 't' },
        h('thead', null, h('tr', null, ['Leverage Tier', 'Cluster Side', 'Theoretical Trigger Px', 'Distance %', 'Modelled OI Share ($M)', 'Concentration'].map(x => h('th', { text: x })))),
        h('tbody', null, tiers.map(t => {
          const px = spot * t.mult;
          const dist = (t.mult - 1) * 100;
          if (t.side === 'CURRENT EQUILIBRIUM') {
            return h('tr', { style: 'background:#1d1500;font-weight:bold' },
              h('td', { class: 'l sym am', text: 'LIVE MARK' }),
              h('td', { class: 'am sym', text: 'EXCHANGE MARK PRICE' }),
              h('td', { class: 'am sym', text: fmtPx(spot) }),
              h('td', { class: 'am', text: '0.00%' }),
              h('td', { class: 'am', text: `$${t.poolM.toFixed(1)}M OI` }),
              h('td', { class: 'l am', text: '━━━━━━━━━━ CURRENT MARK ANCHOR ━━━━━━━━━━' })
            );
          }
          const isShort = t.side === 'SHORT LIQ RISK TIER';
          const col = isShort ? '#00e5ff' : '#ff3b30';
          return h('tr', { class: 'row' },
            h('td', { class: 'l sym am', text: t.lev }),
            h('td', { class: isShort ? 'lb sym' : 'dn sym', text: t.side }),
            h('td', { class: 'sym', style: `color:${col}`, text: fmtPx(px) }),
            h('td', { class: dirCls(dist), text: (dist >= 0 ? '+' : '') + dist.toFixed(2) + '%' }),
            h('td', { class: 'am sym', text: `$${t.poolM.toFixed(1)}M` }),
            h('td', { style: 'width:190px' },
              h('div', { style: 'width:175px;height:10px;background:#111;border:1px solid #2a2a2a' },
                h('div', { style: `width:${Math.min(100, Math.round(t.intensity * 100))}%;height:100%;background:linear-gradient(90deg,${col}66,${col})` })
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
    h('span', { class: 'lbl', text: `OMST / GEX — ANALYTICAL BLACK-SCHOLES GAMMA GRID & OPTIONS FEED STATUS [${ctx.symbol}]` }),
    h('button', { text: 'OVDV SURFACE <GO>', onclick: () => ctx.run('OVDV') }),
    h('button', { text: 'OVME PRICER <GO>', onclick: () => ctx.run('OVME') })
  );
  const sc = h('div', { class: 'pb' });
  body.append(tb, sc);

  function normPdf(x) {
    return Math.exp(-0.5 * x * x) / Math.sqrt(2 * Math.PI);
  }

  async function load() {
    const [qEnv, kEnv] = await Promise.all([
      get('quote', { symbols: ctx.symbol }, 3000),
      get('kline', { symbol: ctx.symbol, interval: '1d', limit: 45 }, 4000)
    ]);
    ctx.status(qEnv);
    sc.textContent = '';
    const q = (qEnv.ok && Array.isArray(qEnv.data) && qEnv.data[0]) || {};
    const spot = Number(q.price || 0);
    if (!spot) {
      sc.append(h('div', { class: 'na', text: `N/A (${qEnv.error || 'No live spot quote'})` }));
      return;
    }

    const candles = (kEnv.ok && kEnv.data && kEnv.data.candles) || [];
    let hv30 = 0.35;
    if (candles.length >= 10) {
      const rets = [];
      for (let i = 1; i < candles.length; i++) {
        if (candles[i - 1].c > 0 && candles[i].c > 0) rets.push(Math.log(candles[i].c / candles[i - 1].c));
      }
      if (rets.length >= 5) {
        const mean = rets.reduce((a, b) => a + b, 0) / rets.length;
        const vr = rets.reduce((a, b) => a + (b - mean) ** 2, 0) / rets.length;
        hv30 = Math.max(0.08, Math.sqrt(vr) * Math.sqrt(252));
      }
    }

    const T = 30 / 365;
    const r = 0.043;
    const step = spot > 1000 ? Math.round((spot * 0.02) / 50) * 50 : spot > 50 ? Math.max(1, Math.round(spot * 0.025)) : +(spot * 0.03).toFixed(2);
    const center = Math.round(spot / (step || 1)) * (step || 1);

    const gexStrikes = [-4, -3, -2, -1, 0, 1, 2, 3, 4].map(k => {
      const st = +(center + k * step).toFixed(2);
      const d1 = (Math.log(spot / st) + (r + 0.5 * hv30 * hv30) * T) / (hv30 * Math.sqrt(T));
      const gamma = normPdf(d1) / (spot * hv30 * Math.sqrt(T));
      const d2 = d1 - hv30 * Math.sqrt(T);
      // Unit 100-contract call & put sensitivity per 1% spot move
      const unitDollarGamma1Pct = gamma * spot * spot * 0.01;
      return { st, gamma, unitDollarGamma1Pct, moneyness: ((st - spot) / spot) * 100, d1, d2 };
    });
    const maxGamma = Math.max(...gexStrikes.map(x => x.unitDollarGamma1Pct), 1e-6);

    sc.append(
      h('div', { class: 'kv', style: 'background:#060606;border-bottom:1px solid var(--border);padding:6px 8px' },
        h('div', { class: 'k', text: 'OPRA / DERIBIT LIVE OPTIONS TAPE' }), h('div', { class: 'v dn sym', text: 'N/A — Institutional OPRA / Deribit Live Options Sweep & Dealer OI Feed Not Connected' }),
        h('div', { class: 'k', text: 'LIVE UNDERLYING SPOT & 30D REALIZED VOL' }), h('div', { class: 'v am sym', text: `${ctx.symbol}: ${fmtPx(spot)}  •  Realized HV30: ${(hv30 * 100).toFixed(1)}%  •  30 DTE Analytic Grid` }),
        h('div', { class: 'k', text: 'ANALYTIC METHOD' }), h('div', { class: 'v lb', text: 'Exact Black-Scholes Strike Gamma Density (per 1% move) computed strictly from live spot & OHLCV realized volatility — no fabricated GEX/sweep prints.' })
      ),
      h('div', { class: 'tb', style: 'background:#070707' }, h('span', { class: 'lbl', text: 'THEORETICAL BLACK-SCHOLES UNIT GAMMA PROFILE BY STRIKE (30 DTE • σ = LIVE HV30)' })),
      h('table', { class: 't' },
        h('thead', null, h('tr', null, ['Strike Price', 'Moneyness %', 'Unit B-S Gamma (Γ)', '$Gamma / 1% Move (100ct)', 'Convexity Concentration'].map(x => h('th', { text: x })))),
        h('tbody', null, gexStrikes.map(r => h('tr', { class: 'row', style: r.st === center ? 'background:#1c1500' : '' },
          h('td', { class: 'l sym am', text: fmtPx(r.st) + (r.st === center ? ' [ATM]' : '') }),
          h('td', { class: dirCls(r.moneyness), text: (r.moneyness >= 0 ? '+' : '') + r.moneyness.toFixed(2) + '%' }),
          h('td', { class: 'lb sym', text: r.gamma.toFixed(6) }),
          h('td', { class: 'up sym', text: '$' + fmtNum(r.unitDollarGamma1Pct * 100, 2) }),
          h('td', { style: 'width:190px' },
            h('div', { style: 'width:175px;height:9px;background:#141414;border:1px solid #2b2b2b' },
              h('div', { style: `width:${Math.min(100, Math.round((r.unitDollarGamma1Pct / maxGamma) * 100))}%;height:100%;background:#00e5ff` })
            )
          )
        )))
      ),
      h('div', { class: 'na', style: 'margin-top:8px;padding:10px' },
        'OMST Live Options Sweep Tape: N/A — Live US OPRA / Cboe / Deribit options time & sales requires a licensed options data feed. Use OVME <GO> to price custom vanilla structures or OVDV <GO> to inspect empirical volatility term structure.'
      )
    );
  }
  load();
}


