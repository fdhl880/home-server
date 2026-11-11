import { h, fmtPx, fmtPct, fmtChg, fmtVol, fmtNum, dirCls, LS } from '../util.js';
import { get, tickOk } from '../api.js';
import { quoteTable, COLS } from './quotetable.js';

const PRESETS = {
  CORE: ['#CRYPTO SPOT & PERP', 'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT', 'DOGEUSDT', '#US & GLOBAL INDICES', '^GSPC', '^IXIC', '^DJI', '^N225', '^FTSE', '^JKSE', '#MACRO, FX & COMMODITIES', 'GC=F', 'CL=F', '^TNX', 'EURUSD=X', 'USDJPY=X', 'USDIDR=X'],
  CRYPTO: ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT', 'DOGEUSDT', 'ADAUSDT', 'AVAXUSDT', 'LINKUSDT', 'TONUSDT', 'SUIUSDT', 'PEPEUSDT', 'DOTUSDT', 'NEARUSDT', 'APTUSDT', 'LTCUSDT', 'UNIUSDT', 'ARBUSDT', 'OPUSDT', 'INJUSDT'],
  EQUITIES: ['AAPL', 'MSFT', 'NVDA', 'GOOGL', 'AMZN', 'META', 'TSLA', 'BRK-B', 'TSM', 'AVGO', 'JPM', 'LLY', 'V', 'XOM', 'UNH', 'MA', 'COST', 'HD', 'PG', 'NFLX'],
  INDICES: ['#AMERICAS', '^GSPC', '^DJI', '^IXIC', '^RUT', '^GSPTSE', '^BVSP', '#EMEA', '^FTSE', '^GDAXI', '^FCHI', '^STOXX50E', '#ASIA-PACIFIC', '^N225', '^HSI', '000001.SS', '^JKSE', '^AXJO', '^KS11', '^NSEI'],
  COMMODITIES: ['#ENERGY', 'CL=F', 'BZ=F', 'NG=F', 'RB=F', '#PRECIOUS & BASE METALS', 'GC=F', 'SI=F', 'HG=F', 'PL=F', '#AGRICULTURE', 'ZC=F', 'ZW=F', 'ZS=F', 'KC=F', 'CC=F'],
  BONDS: ['#US TREASURY YIELDS', '^IRX', '^FVX', '^TNX', '^TYX', '#BOND ETFS & PROXIES', 'TLT', 'IEF', 'SHY', 'LQD', 'HYG', 'EMB']
};

export function mountMON(body, ctx, { defaultGroup = 'CORE' } = {}) {
  body.classList.add('fill');
  let grp = defaultGroup;
  const tb = h('div', { class: 'tb' });
  const sc = h('div', { class: 'pb' });
  body.append(tb, sc);

  const qt = quoteTable(ctx, [COLS.sym, COLS.name, COLS.last, COLS.chg, COLS.pct, COLS.bid, COLS.ask, COLS.high, COLS.low, COLS.vol, COLS.mode], {
    onPick: s => ctx.setSymbol(s)
  });
  sc.append(qt.el);

  function renderTabs() {
    tb.textContent = '';
    tb.append(h('span', { class: 'lbl', text: 'MON UNIVERSE:' }));
    for (const k of Object.keys(PRESETS)) {
      tb.append(h('button', { class: k === grp ? 'on' : '', text: k, onclick: () => { grp = k; renderTabs(); qt.setSymbols(PRESETS[grp]); qt.refresh(); } }));
    }
    tb.append(h('button', { text: 'REFRESH', onclick: () => qt.refresh() }));
  }

  renderTabs();
  qt.setSymbols(PRESETS[grp] || PRESETS.CORE);
  qt.refresh();
  const iv = setInterval(() => qt.refresh(), 10000);
  ctx.cleanup(() => clearInterval(iv));
}

export function mountWL(body, ctx) {
  body.classList.add('fill');
  const storeKey = 'bbg_watchlists_v1';
  let lists = LS.get(storeKey, {
    'MAIN DESK': ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'AAPL', 'NVDA', 'TSLA', '^GSPC', 'GC=F', 'USDIDR=X'],
    'CRYPTO ALPHA': ['BTCUSDT.P', 'ETHUSDT.P', 'SOLUSDT.P', 'BNBUSDT.P', 'XRPUSDT.P', 'DOGEUSDT.P', 'SUIUSDT.P'],
    'MACRO & FX': ['^TNX', '^TYX', 'GC=F', 'CL=F', 'EURUSD=X', 'USDJPY=X', 'GBPUSD=X', 'USDIDR=X']
  });
  let active = Object.keys(lists)[0] || 'MAIN DESK';

  const tb = h('div', { class: 'tb' });
  const sc = h('div', { class: 'pb' });
  body.append(tb, sc);

  const qt = quoteTable(ctx, [COLS.sym, COLS.last, COLS.chg, COLS.pct, COLS.bid, COLS.ask, COLS.high, COLS.low, COLS.vol, COLS.mode], {
    onPick: s => ctx.setSymbol(s)
  });
  sc.append(qt.el);

  function save() { LS.set(storeKey, lists); }
  function rebuild() {
    tb.textContent = '';
    tb.append(h('span', { class: 'lbl', text: 'WL:' }));
    for (const name of Object.keys(lists)) {
      tb.append(h('button', { class: name === active ? 'on' : '', text: name, onclick: () => { active = name; rebuild(); } }));
    }
    const inp = h('input', { placeholder: 'TICKER (e.g. BTCUSDT, MSFT)', style: 'width:155px;text-transform:uppercase' });
    const add = () => {
      const s = inp.value.trim().toUpperCase();
      if (!s) return;
      if (!lists[active].includes(s)) { lists[active].push(s); save(); rebuild(); }
    };
    inp.addEventListener('keydown', e => { if (e.key === 'Enter') add(); });
    const delBtn = h('button', { text: '-DEL CURRENT (' + ctx.symbol + ')', onclick: () => {
      lists[active] = (lists[active] || []).filter(x => x !== ctx.symbol);
      save(); rebuild();
    } });
    tb.append(inp, h('button', { text: '+ADD', onclick: add }), delBtn);
    qt.setSymbols(lists[active] || []);
    qt.refresh();
  }

  rebuild();
  const iv = setInterval(() => qt.refresh(), 8000);
  ctx.cleanup(() => clearInterval(iv));
}

export function mountMOST(body, ctx) {
  body.classList.add('fill');
  let asset = 'crypto', dir = 'gainers';
  const tb = h('div', { class: 'tb' });
  const sc = h('div', { class: 'pb' });
  body.append(tb, sc);

  async function load() {
    tb.textContent = '';
    tb.append(h('span', { class: 'lbl', text: 'MOST MARKET:' }));
    for (const [k, lbl] of [['crypto', 'CRYPTO SPOT'], ['crypto-perp', 'CRYPTO PERP (.P)'], ['equity', 'US EQUITIES']]) {
      tb.append(h('button', { class: asset === k ? 'on' : '', text: lbl, onclick: () => { asset = k; load(); } }));
    }
    tb.append(h('span', { class: 'lbl', text: 'RANK:' }));
    for (const [d, lbl] of [['gainers', 'TOP GAINERS'], ['losers', 'TOP LOSERS'], ['active', 'MOST ACTIVE']]) {
      tb.append(h('button', { class: dir === d ? 'on' : '', text: lbl, onclick: () => { dir = d; load(); } }));
    }

    sc.textContent = '';
    const env = await get('movers', { asset, dir, limit: 25 }, 4000);
    ctx.status(env);
    if (!env.ok || !Array.isArray(env.data) || !env.data.length) {
      sc.append(h('div', { class: 'na', text: `N/A (${env.error || 'source down'})` }));
      return;
    }
    sc.append(h('table', { class: 't' },
      h('thead', null, h('tr', null, ['#', 'Security', 'Last', 'Chg', '%Chg', 'High', 'Low', 'Volume', 'Mode'].map(x => h('th', { text: x })))),
      h('tbody', null, env.data.map((t, i) => {
        const cl = dirCls(t.chgPct);
        return h('tr', { class: 'row', onclick: () => ctx.setSymbol(t.symbol) },
          h('td', { class: 'l mu', text: String(i + 1) }),
          h('td', { class: 'l sym am', text: t.symbol }),
          h('td', { class: 'am', text: fmtPx(t.price) }),
          h('td', { class: cl, text: fmtChg(t.chg) }),
          h('td', { class: cl, text: fmtPct(t.chgPct) }),
          h('td', { text: fmtPx(t.high) }),
          h('td', { text: fmtPx(t.low) }),
          h('td', { class: 'mu', text: fmtVol(t.vol) }),
          h('td', { class: t.mode === 'LIVE' ? 'up' : 'am', text: t.mode || 'LIVE' })
        );
      }))
    ));
  }
  load();
  const iv = setInterval(load, 12000);
  ctx.cleanup(() => clearInterval(iv));
}

export function mountFXC(body, ctx) {
  body.classList.add('fill');
  const CCYS = ['USD', 'EUR', 'JPY', 'GBP', 'CHF', 'AUD', 'CAD', 'IDR'];
  const PAIRS = ['EURUSD=X', 'JPY=X', 'GBPUSD=X', 'CHF=X', 'AUDUSD=X', 'CAD=X', 'USDIDR=X'];
  const tb = h('div', { class: 'tb' });
  const sc = h('div', { class: 'pb' });
  body.append(tb, sc);

  let amt = 1000, fromC = 'USD', toC = 'IDR';
  let usdRates = { USD: 1 };

  async function load() {
    const env = await get('quote', { symbols: PAIRS.join(',') }, 4000);
    ctx.status(env);
    sc.textContent = '';
    if (!env.ok || !Array.isArray(env.data)) {
      sc.append(h('div', { class: 'na', text: `N/A (${env.error || 'source down'})` }));
      return;
    }
    const map = {};
    for (const t of env.data) if (tickOk(t)) map[t.symbol] = t;

    // Normalize to 1 USD = X CCY
    usdRates = {
      USD: 1,
      EUR: map['EURUSD=X'] ? 1 / map['EURUSD=X'].price : null,
      JPY: map['JPY=X'] ? map['JPY=X'].price : null,
      GBP: map['GBPUSD=X'] ? 1 / map['GBPUSD=X'].price : null,
      CHF: map['CHF=X'] ? map['CHF=X'].price : null,
      AUD: map['AUDUSD=X'] ? 1 / map['AUDUSD=X'].price : null,
      CAD: map['CAD=X'] ? map['CAD=X'].price : null,
      IDR: map['USDIDR=X'] ? map['USDIDR=X'].price : null,
    };

    // Converter bar
    tb.textContent = '';
    const inp = h('input', { value: String(amt), style: 'width:85px' });
    const selF = h('select', null, CCYS.map(c => h('option', { value: c, selected: c === fromC ? 'selected' : null, text: c })));
    const selT = h('select', null, CCYS.map(c => h('option', { value: c, selected: c === toC ? 'selected' : null, text: c })));
    const resSpan = h('span', { class: 'am sym' });
    const calc = () => {
      amt = parseFloat(inp.value) || 0;
      fromC = selF.value; toC = selT.value;
      const rF = usdRates[fromC], rT = usdRates[toC];
      resSpan.textContent = (rF && rT) ? `= ${fmtNum((amt / rF) * rT, toC === 'IDR' || toC === 'JPY' ? 2 : 4)} ${toC}` : '= N/A';
    };
    inp.oninput = calc; selF.onchange = calc; selT.onchange = calc;
    calc();
    tb.append(h('span', { class: 'lbl', text: 'FXCA CONVERTER:' }), inp, selF, h('span', { class: 'lbl', text: '→' }), selT, resSpan);

    // Cross matrix table
    const tbl = h('table', { class: 't' },
      h('thead', null, h('tr', null, [h('th', { text: 'BASE \\ QUOTE' }), ...CCYS.map(c => h('th', { text: c }))])),
      h('tbody', null, CCYS.map(base => h('tr', { class: 'row' },
        h('td', { class: 'l lb sym', text: base }),
        ...CCYS.map(quote => {
          if (base === quote) return h('td', { class: 'mu', text: '1.0000' });
          const rB = usdRates[base], rQ = usdRates[quote];
          if (!rB || !rQ) return h('td', { class: 'dn', text: 'N/A' });
          const cross = rQ / rB;
          const dp = quote === 'IDR' ? 0 : quote === 'JPY' ? 2 : 4;
          return h('td', { class: 'am', text: fmtNum(cross, dp), onclick: () => ctx.setSymbol(base === 'USD' ? `${quote}=X` : `${base}${quote}=X`) });
        })
      )))
    );

    // Spot performance table below matrix
    const spotTbl = h('table', { class: 't', style: 'margin-top:8px' },
      h('thead', null, h('tr', null, ['Pair', 'Last', 'Chg', '%Chg', 'High', 'Low', 'Mode'].map(x => h('th', { text: x })))),
      h('tbody', null, PAIRS.map(p => {
        const t = map[p] || { symbol: p };
        const cl = dirCls(t.chgPct);
        return h('tr', { class: 'row', onclick: () => ctx.setSymbol(p) },
          h('td', { class: 'l sym am', text: p }),
          h('td', { class: 'am', text: fmtPx(t.price) }),
          h('td', { class: cl, text: fmtChg(t.chg) }),
          h('td', { class: cl, text: fmtPct(t.chgPct) }),
          h('td', { text: fmtPx(t.high) }),
          h('td', { text: fmtPx(t.low) }),
          h('td', { class: 'am', text: t.mode || 'DELAYED' })
        );
      }))
    );

    sc.append(
      h('div', { class: 'tb', style: 'background:#070707' }, h('span', { class: 'lbl', text: 'FXC G10 & EM CROSS-CURRENCY MATRIX (CLICK CELL TO LOAD PAIR)' })),
      tbl,
      h('div', { class: 'tb', style: 'background:#070707;margin-top:6px' }, h('span', { class: 'lbl', text: 'WCR WORLD CURRENCY SPOT PERFORMANCE' })),
      spotTbl
    );
  }

  load();
  const iv = setInterval(load, 15000);
  ctx.cleanup(() => clearInterval(iv));
}

export function mountIMAP(body, ctx) {
  body.classList.add('fill');
  let asset = 'crypto';
  const tb = h('div', { class: 'tb' });
  const heat = h('div', { class: 'heat', style: 'flex:1;position:relative;overflow:hidden;background:#000' });
  body.append(tb, heat);

  function colorForPct(pct) {
    if (pct == null || !isFinite(pct)) return '#222';
    const c = Math.max(-8, Math.min(8, pct));
    if (c >= 0) {
      const g = Math.round(55 + (c / 8) * 145);
      return `rgb(0, ${g}, 45)`;
    } else {
      const r = Math.round(65 + (Math.abs(c) / 8) * 155);
      return `rgb(${r}, 18, 24)`;
    }
  }

  async function load() {
    tb.textContent = '';
    tb.append(
      h('span', { class: 'lbl', text: 'IMAP MARKET TREEMAP:' }),
      h('button', { class: asset === 'crypto' ? 'on' : '', text: 'CRYPTO SPOT', onclick: () => { asset = 'crypto'; load(); } }),
      h('button', { class: asset === 'crypto-perp' ? 'on' : '', text: 'CRYPTO PERP (.P)', onclick: () => { asset = 'crypto-perp'; load(); } }),
      h('button', { class: asset === 'equity' ? 'on' : '', text: 'US EQUITIES', onclick: () => { asset = 'equity'; load(); } })
    );
    heat.textContent = '';
    const env = await get('movers', { asset, dir: 'active', limit: 24 }, 5000);
    ctx.status(env);
    if (!env.ok || !Array.isArray(env.data) || !env.data.length) {
      heat.append(h('div', { class: 'na', text: `N/A (${env.error || 'source down'})` }));
      return;
    }
    const items = env.data.slice(0, 20);
    const cols = 5, rows = Math.ceil(items.length / cols);
    const w = 100 / cols, ht = 100 / rows;
    items.forEach((t, idx) => {
      const c = idx % cols, r = Math.floor(idx / cols);
      const tile = h('div', {
        class: 'tile',
        style: `left:${c * w}%;top:${r * ht}%;width:${w}%;height:${ht}%;background:${colorForPct(t.chgPct)};display:flex;flex-direction:column;justify-content:center;align-items:center;text-align:center`,
        onclick: () => ctx.setSymbol(t.symbol)
      },
        h('b', { style: 'font-size:12px;color:#fff', text: t.symbol.replace(/USDT(\.P)?$/, '') }),
        h('span', { style: 'font-size:11px;color:#eee', text: fmtPx(t.price) }),
        h('span', { style: 'font-size:11px;font-weight:bold;color:#fff', text: fmtPct(t.chgPct) })
      );
      heat.append(tile);
    });
  }
  load();
  const iv = setInterval(load, 12000);
  ctx.cleanup(() => clearInterval(iv));
}

