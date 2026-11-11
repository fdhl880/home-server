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

