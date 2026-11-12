import { h, fmtPx, fmtPct, fmtChg, fmtVol, fmtNum, dirCls, LS } from '../util.js';
import { get, tickOk } from '../api.js';
import { quoteTable, COLS } from './quotetable.js';
import { MAP_W, MAP_H, mapX, mapY, WORLD_PATH } from './worldmap.js';

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

export function mountBMAP(body, ctx) {
  body.classList.add('fill');
  let filter = 'ALL';
  let selectedId = 'HORMUZ';
  const tb = h('div', { class: 'tb' });
  const sc = h('div', { class: 'pb bmap' });
  body.append(tb, sc);

  const NODES = [
    { id: 'CUSHING', dx: -8, dy: 2, anc: 'end', name: 'Cushing Oil Hub, Oklahoma', cat: 'ENERGY', sym: 'CL=F', lat: 35.98, lon: -96.76, flow: '78.4M bbl storage / WTI delivery', status: 'NORMAL', note: 'Pipeline hub (Keystone / Seaway)' },
    { id: 'BRENT', dx: 8, dy: 2, anc: 'start', name: 'Sullom Voe Brent Terminal, UK', cat: 'ENERGY', sym: 'BZ=F', lat: 60.45, lon: -1.27, flow: '1.8M bbl/d BFOET benchmark', status: 'NORMAL', note: 'Aframax / Suezmax loading' },
    { id: 'SABINE', dx: 8, dy: 8, anc: 'start', name: 'Sabine Pass LNG, Louisiana', cat: 'ENERGY', sym: 'NG=F', lat: 29.73, lon: -93.87, flow: '4.7 Bcf/d LNG feedgas', status: 'FULL', note: 'LNG carriers queued' },
    { id: 'RASTAN', dx: -2, dy: 13, anc: 'end', name: 'Ras Tanura, Saudi Arabia', cat: 'ENERGY', sym: 'BZ=F', lat: 26.64, lon: 50.16, flow: '6.5M bbl/d export terminal', status: 'NORMAL', note: 'Largest offshore oil terminal' },
    { id: 'HORMUZ', dx: 8, dy: 4, anc: 'start', name: 'Strait of Hormuz', cat: 'CHOKEPOINT', sym: 'BZ=F', lat: 26.57, lon: 56.25, flow: '20.9M bbl/d (~21% of world supply)', status: 'RISK', note: 'VLCC transits, Iran / Oman' },
    { id: 'MALACCA', dx: -8, dy: -3, anc: 'end', name: 'Strait of Malacca', cat: 'CHOKEPOINT', sym: 'BZ=F', lat: 2.5, lon: 101.8, flow: '23.7M bbl/d APAC energy lifeline', status: 'BUSY', note: 'Indonesia / Malaysia / Singapore' },
    { id: 'SUEZ', dx: -8, dy: -2, anc: 'end', name: 'Suez Canal / Bab el-Mandeb', cat: 'CHOKEPOINT', sym: 'CL=F', lat: 29.9, lon: 32.55, flow: '8.8M bbl/d, Cape rerouting', status: 'ALERT', note: 'Red Sea diversions +12 days' },
    { id: 'PANAMA', dx: -8, dy: 4, anc: 'end', name: 'Panama Canal', cat: 'CHOKEPOINT', sym: 'NG=F', lat: 9.08, lon: -79.68, flow: '2.6M bbl/d products + US grain', status: 'NORMAL', note: 'Neopanamax slot limits' },
    { id: 'BOSPOR', dx: -8, dy: 5, anc: 'end', name: 'Bosphorus / Turkish Straits', cat: 'CHOKEPOINT', sym: 'ZW=F', lat: 41.12, lon: 29.07, flow: '3.0M bbl/d + Black Sea grain', status: 'WATCH', note: 'Montreux convention transit' },
    { id: 'GRASBERG', dx: 8, dy: 2, anc: 'start', name: 'Grasberg Cu-Au Mine, Papua', cat: 'METALS', sym: 'HG=F', lat: -4.05, lon: 137.11, flow: '1.6B lb Cu + 1.8M oz Au / yr', status: 'NORMAL', note: 'Indonesia' },
    { id: 'ESCONDIDA', dx: -8, dy: 2, anc: 'end', name: 'Escondida Copper, Chile', cat: 'METALS', sym: 'HG=F', lat: -24.26, lon: -69.07, flow: '1.1M t copper / yr', status: 'NORMAL', note: 'World largest Cu mine' },
    { id: 'COMEX', dx: 8, dy: 2, anc: 'start', name: 'COMEX Gold Vaults, New York', cat: 'METALS', sym: 'GC=F', lat: 40.71, lon: -74.0, flow: '18.2M oz registered gold', status: 'NORMAL', note: 'T+1 physical settlement' },
    { id: 'RAND', dx: 8, dy: 2, anc: 'start', name: 'Witwatersrand / Bushveld, South Africa', cat: 'METALS', sym: 'SI=F', lat: -26.2, lon: 28.0, flow: '~72% world platinum', status: 'NORMAL', note: 'PGM + deep-level gold' },
    { id: 'NICKEL', dx: 8, dy: 7, anc: 'start', name: 'Sulawesi Nickel Belt, Indonesia', cat: 'METALS', sym: 'HG=F', lat: -2.6, lon: 121.4, flow: '~50% world nickel supply', status: 'NORMAL', note: 'Morowali / Weda Bay' },
    { id: 'CORN', dx: 8, dy: -5, anc: 'start', name: 'US Corn Belt, Iowa / Illinois', cat: 'AGS', sym: 'ZC=F', lat: 41.8, lon: -93.5, flow: '385M t corn harvest', status: 'PEAK', note: 'Mississippi barge to NOLA' },
    { id: 'MATO', dx: 8, dy: 2, anc: 'start', name: 'Mato Grosso Soy, Brazil', cat: 'AGS', sym: 'ZS=F', lat: -13.0, lon: -55.5, flow: '158M t soybean exports', status: 'PEAK', note: 'Santos / Paranagua ports' },
    { id: 'BLACKSEA', dx: 8, dy: -5, anc: 'start', name: 'Odesa / Black Sea Grain', cat: 'AGS', sym: 'ZW=F', lat: 46.5, lon: 30.7, flow: '48M t wheat + corn', status: 'WATCH', note: 'Panamax bulk carriers' },
    { id: 'PALM', dx: 0, dy: -9, anc: 'middle', name: 'Kalimantan Palm Oil, Indonesia', cat: 'AGS', sym: 'KC=F', lat: -1.5, lon: 113.5, flow: '~55% world palm oil', status: 'NORMAL', note: 'Dumai / Belawan export' }
  ];

  const LANES = [
    [[56.25, 26.57], [62, 21], [73, 10], [90, 5], [101.8, 2.5], [110, 8], [122, 24], [135, 33]],
    [[56.25, 26.57], [50, 14], [43.3, 12.6], [32.55, 29.9], [28, 33], [15, 36], [-5.5, 36]],
    [[-93.87, 29.73], [-85, 24], [-79.68, 9.08], [-100, 10], [-140, 25], [135, 34]],
    [[-93.87, 29.73], [-60, 38], [-30, 48], [-1.27, 55]],
    [[-55.5, -23], [-30, -12], [-5, 5], [10, 38], [30, 36]],
    [[121.4, -3], [118, 8], [122, 24]]
  ];
  const CAT = { ENERGY: '#ffb000', CHOKEPOINT: '#ff3b30', METALS: '#00d26a', AGS: '#4da3ff' };
  const CAT_LBL = { ENERGY: 'OIL / GAS / LNG', CHOKEPOINT: 'CHOKEPOINTS', METALS: 'METALS & MINES', AGS: 'AGRICULTURE' };
  const ns = 'http://www.w3.org/2000/svg';
  const sv = (tag, attrs) => { const e = document.createElementNS(ns, tag); for (const [k, v] of Object.entries(attrs || {})) e.setAttribute(k, v); return e; };

  // viewBox state (zoom / pan)
  let vb = { x: 0, y: 0, w: MAP_W, h: MAP_H };
  const clampVb = () => {
    vb.w = Math.max(120, Math.min(MAP_W, vb.w));
    vb.h = vb.w * (MAP_H / MAP_W);
    vb.x = Math.max(0, Math.min(MAP_W - vb.w, vb.x));
    vb.y = Math.max(0, Math.min(MAP_H - vb.h, vb.y));
  };

  const wrap = h('div', { class: 'bmap-wrap' });
  const side = h('div', { class: 'bmap-side' });
  const mapBox = h('div', { class: 'bmap-box' });
  wrap.append(mapBox, side);
  sc.append(wrap);

  const svg = sv('svg', { viewBox: `0 0 ${MAP_W} ${MAP_H}`, preserveAspectRatio: 'xMidYMid meet', class: 'bmap-svg' });
  const gGrid = sv('g'), gLand = sv('g'), gLanes = sv('g'), gNodes = sv('g');
  svg.append(gGrid, gLand, gLanes, gNodes);
  mapBox.append(svg);

  for (let lon = -150; lon <= 180; lon += 30) gGrid.append(sv('line', { x1: mapX(lon), y1: 0, x2: mapX(lon), y2: MAP_H, stroke: '#101a24', 'stroke-width': 0.6 }));
  for (let lat = -50; lat <= 80; lat += 10) gGrid.append(sv('line', { x1: 0, y1: mapY(lat), x2: MAP_W, y2: mapY(lat), stroke: lat === 0 ? '#1d3347' : '#101a24', 'stroke-width': lat === 0 ? 0.9 : 0.6 }));
  gLand.append(sv('path', { d: WORLD_PATH, fill: '#2b3441', stroke: '#566679', 'stroke-width': 0.5, 'stroke-linejoin': 'round' }));
  for (const pts of LANES) {
    const d = pts.map(([lo, la], i) => (i ? 'L' : 'M') + mapX(lo).toFixed(1) + ',' + mapY(la).toFixed(1)).join(' ');
    gLanes.append(sv('path', { d, fill: 'none', stroke: '#2a78a8', 'stroke-width': 0.9, 'stroke-dasharray': '3 3', opacity: 0.8 }));
  }

  // zoom controls
  const zoomBy = f => { const cx = vb.x + vb.w / 2, cy = vb.y + vb.h / 2; vb.w *= f; clampVb(); vb.x = cx - vb.w / 2; vb.y = cy - vb.h / 2; clampVb(); applyVb(); };
  function applyVb() { svg.setAttribute('viewBox', `${vb.x.toFixed(1)} ${vb.y.toFixed(1)} ${vb.w.toFixed(1)} ${vb.h.toFixed(1)}`); const k = vb.w / MAP_W; gNodes.querySelectorAll('[data-s]').forEach(e => e.setAttribute('transform', `translate(${e.dataset.x},${e.dataset.y}) scale(${k})`)); }
  mapBox.append(
    h('div', { class: 'bmap-hud' },
      h('span', { style: 'color:#ffb000', text: '■ ENERGY' }),
      h('span', { style: 'color:#ff3b30', text: '● CHOKEPOINTS' }),
      h('span', { style: 'color:#00d26a', text: '■ METALS' }),
      h('span', { style: 'color:#4da3ff', text: '■ AGRI' }),
      h('span', { class: 'mu', text: 'SCROLL: ZOOM • DRAG: PAN' })
    ),
    h('div', { class: 'bmap-zoom' },
      h('button', { text: '+', title: 'Zoom in', onclick: () => zoomBy(0.7) }),
      h('button', { text: '-', title: 'Zoom out', onclick: () => zoomBy(1.4) }),
      h('button', { text: '1:1', title: 'Reset', onclick: () => { vb = { x: 0, y: 0, w: MAP_W, h: MAP_H }; applyVb(); } })
    )
  );
  svg.addEventListener('wheel', e => {
    e.preventDefault();
    const r = svg.getBoundingClientRect();
    const fx = (e.clientX - r.left) / r.width, fy = (e.clientY - r.top) / r.height;
    const f = e.deltaY < 0 ? 0.85 : 1.18;
    const nx = vb.x + fx * vb.w, ny = vb.y + fy * vb.h;
    vb.w *= f; clampVb();
    vb.x = nx - fx * vb.w; vb.y = ny - fy * vb.h; clampVb(); applyVb();
  }, { passive: false });
  let drag = null;
  svg.addEventListener('pointerdown', e => { drag = { x: e.clientX, y: e.clientY, vx: vb.x, vy: vb.y }; svg.setPointerCapture(e.pointerId); });
  svg.addEventListener('pointermove', e => {
    if (!drag) return;
    const r = svg.getBoundingClientRect();
    vb.x = drag.vx - ((e.clientX - drag.x) / r.width) * vb.w;
    vb.y = drag.vy - ((e.clientY - drag.y) / r.height) * vb.h;
    clampVb(); applyVb();
  });
  svg.addEventListener('pointerup', () => { drag = null; });

  let qMap = {};
  const U = () => MAP_W / Math.max(280, mapBox.clientWidth || 600);
  function renderNodes() {
    const u = U();
    gNodes.textContent = '';
    const sel = NODES.find(n => n.id === selectedId) || NODES[0];
    for (const n of NODES) {
      if (filter !== 'ALL' && n.cat !== filter) continue;
      const x = mapX(n.lon), y = mapY(n.lat), col = CAT[n.cat];
      const g = sv('g', { 'data-s': '1', 'data-x': x.toFixed(1), 'data-y': y.toFixed(1), transform: `translate(${x.toFixed(1)},${y.toFixed(1)}) scale(${vb.w / MAP_W})`, style: 'cursor:pointer' });
      g.append(sv('circle', { r: (n.id === sel.id ? 14 : 8) * u, fill: col, opacity: n.id === sel.id ? 0.35 : 0.2 }));
      g.append(sv('circle', { r: (n.id === sel.id ? 5.5 : 3.8) * u, fill: col, stroke: '#000', 'stroke-width': 0.8 * u }));
      if (n.cat === 'CHOKEPOINT' || n.id === sel.id) g.append(sv('circle', { r: (n.id === sel.id ? 10 : 8.5) * u, fill: 'none', stroke: n.id === sel.id ? '#fff' : col, 'stroke-width': 1 * u }));
      const t = sv('text', {
        x: (n.dx ?? 8) * u,
        y: (n.dy ?? 3) * u,
        'text-anchor': n.anc || 'start',
        fill: n.id === sel.id ? '#fff' : col,
        'font-size': (n.id === sel.id ? 11.5 : 9) * u,
        'font-weight': 700,
        'paint-order': 'stroke',
        stroke: '#000',
        'stroke-width': 3 * u
      });
      const q = qMap[n.sym];
      t.textContent = n.id + (n.id === sel.id && q && q.price ? ' ' + fmtPx(q.price) : '');
      g.append(t);
      g.addEventListener('click', ev => { ev.stopPropagation(); selectedId = n.id; renderNodes(); renderSide(); });
      gNodes.append(g);
    }
  }

  function renderSide() {
    side.textContent = '';
    const n = NODES.find(x => x.id === selectedId) || NODES[0];
    const q = qMap[n.sym] || {};
    side.append(
      h('div', { class: 'bmap-card' },
        h('div', { class: 'bmap-ttl', style: `color:${CAT[n.cat]}`, text: n.name }),
        h('div', { class: 'mu', text: `${CAT_LBL[n.cat]}  |  ${n.lat.toFixed(2)}, ${n.lon.toFixed(2)}` }),
        h('div', { class: 'kv' },
          h('div', { class: 'k', text: 'Flow' }), h('div', { class: 'v', text: n.flow }),
          h('div', { class: 'k', text: 'Logistics' }), h('div', { class: 'v', text: n.note }),
          h('div', { class: 'k', text: 'Status' }), h('div', { class: 'v sym ' + (n.status === 'ALERT' || n.status === 'RISK' ? 'dn' : n.status === 'WATCH' || n.status === 'BUSY' ? 'am' : 'up'), text: n.status }),
          h('div', { class: 'k', text: n.sym }), h('div', { class: 'v sym ' + dirCls(q.chgPct), text: q.price ? `${fmtPx(q.price)}  ${fmtPct(q.chgPct)}` : 'N/A' })
        ),
        h('button', { class: 'on', text: `${n.sym} GP <GO>`, onclick: () => ctx.run(`${n.sym} GP`) })
      ),
      h('div', { class: 'bmap-list' }, NODES.filter(x => filter === 'ALL' || x.cat === filter).map(x => {
        const qq = qMap[x.sym] || {};
        return h('div', { class: 'bmap-row' + (x.id === selectedId ? ' sel' : ''), onclick: () => { selectedId = x.id; renderNodes(); renderSide(); } },
          h('i', { style: `background:${CAT[x.cat]}` }),
          h('span', { class: 'nm', text: x.id }),
          h('span', { class: 'mu', style: 'font-size:10px', text: qq.price ? fmtPx(qq.price) : x.sym }),
          h('span', { class: 'px ' + dirCls(qq.chgPct), text: qq.price ? fmtPct(qq.chgPct) : '' }));
      }))
    );
  }

  function renderBar() {
    tb.textContent = '';
    tb.append(h('span', { class: 'lbl', text: 'BMAP Commodities Map' }));
    for (const [k, lbl] of [['ALL', 'ALL'], ['ENERGY', 'ENERGY'], ['CHOKEPOINT', 'CHOKEPOINTS'], ['METALS', 'METALS'], ['AGS', 'AGRI']]) {
      tb.append(h('button', { class: filter === k ? 'on' : '', text: lbl, onclick: () => { filter = k; renderBar(); renderNodes(); renderSide(); } }));
    }
  }

  async function load() {
    const syms = [...new Set(NODES.map(n => n.sym))].join(',');
    const env = await get('quote', { symbols: syms }, 6000);
    ctx.status(env);
    qMap = {};
    if (env.ok && Array.isArray(env.data)) env.data.forEach(q => { if (q && q.symbol) qMap[q.symbol] = q; });
    renderNodes(); renderSide();
  }
  renderBar(); renderNodes(); renderSide();
  if (typeof ResizeObserver !== 'undefined') { const ro = new ResizeObserver(() => renderNodes()); ro.observe(mapBox); ctx.cleanup(() => ro.disconnect()); }
  load();
  const iv = setInterval(load, 20000);
  ctx.cleanup(() => clearInterval(iv));
}

export function mountFXFC(body, ctx) {
  body.classList.add('fill');
  const tb = h('div', { class: 'tb' });
  const sc = h('div', { class: 'pb' });
  body.append(tb, sc);

  const RATES = { USD: 4.33, EUR: 2.65, GBP: 4.50, JPY: 0.50, CHF: 0.50, AUD: 4.10, SGD: 2.75, IDR: 5.75, CNH: 2.15 };
  const TENORS = [
    ['O/N', 1 / 365], ['1W', 7 / 365], ['1M', 30 / 365], ['2M', 60 / 365],
    ['3M', 91 / 365], ['6M', 182 / 365], ['9M', 273 / 365], ['1Y', 1], ['2Y', 2]
  ];
  const PAIRS = ['EURUSD=X', 'USDJPY=X', 'GBPUSD=X', 'USDIDR=X', 'AUDUSD=X', 'USDSGD=X', 'USDCHF=X'];

  let activePair = PAIRS.includes(ctx.symbol) ? ctx.symbol : 'USDIDR=X';
  let notional = 1000000;

  async function load() {
    tb.textContent = '';
    const nInp = h('input', { value: String(notional), style: 'width:90px', title: 'Notional Base Amount' });
    tb.append(
      h('span', { class: 'lbl', text: 'FXFC FORWARD CALCULATOR:' }),
      ...PAIRS.map(p => h('button', { class: activePair === p ? 'on' : '', text: p.replace('=X', ''), onclick: () => { activePair = p; load(); } })),
      h('span', { class: 'lbl', text: 'NOTIONAL:' }),
      nInp
    );

    const env = await get('quote', { symbols: PAIRS.join(',') }, 6000);
    ctx.status(env);
    sc.textContent = '';
    const qMap = {};
    if (env.ok && Array.isArray(env.data)) env.data.forEach(q => { if (q && q.symbol) qMap[q.symbol] = q; });
    const q = qMap[activePair] || {};
    const raw = activePair.replace('=X', '');
    const base = raw.slice(0, 3), quote = raw.slice(3, 6);
    const fallbacks = { EURUSD: 1.085, USDJPY: 153.2, GBPUSD: 1.292, USDIDR: 17968, AUDUSD: 0.658, USDSGD: 1.335, USDCHF: 0.878 };
    const spot = q.price || fallbacks[raw] || 1.0;
    const rB = RATES[base] ?? 4.0, rQ = RATES[quote] ?? 3.5;
    const isLarge = quote === 'JPY' || quote === 'IDR';
    const pipMult = quote === 'IDR' ? 1 : quote === 'JPY' ? 100 : 10000;
    const dp = quote === 'IDR' ? 0 : quote === 'JPY' ? 2 : 4;

    const rows = TENORS.map(([tn, yr]) => {
      const fwd = spot * ((1 + (rQ / 100) * yr) / (1 + (rB / 100) * yr));
      const pts = (fwd - spot) * pipMult;
      const annCarry = ((fwd - spot) / spot / yr) * 100;
      return { tn, yr, fwd, pts, annCarry, pnl: (fwd - spot) * (parseFloat(nInp.value) || notional) };
    });

    nInp.oninput = () => { notional = parseFloat(nInp.value) || 0; renderCurveAndTable(); };

    const wrap = h('div');
    sc.append(
      h('div', { class: 'kv', style: 'background:#060606;border-bottom:1px solid var(--border)' },
        h('div', { class: 'k', text: 'CURRENCY PAIR' }), h('div', { class: 'v am sym', text: `${base}/${quote}  •  SPOT: ${fmtNum(spot, dp)} (${q.mode || 'LIVE'})` }),
        h('div', { class: 'k', text: 'INTEREST DIFFERENTIAL' }), h('div', { class: 'v lb', text: `${base} ${rB.toFixed(2)}% vs ${quote} ${rQ.toFixed(2)}%  (Spread: ${(rQ - rB >= 0 ? '+' : '') + (rQ - rB).toFixed(2)}%)` }),
        h('div', { class: 'k', text: 'CIP IMPLIED CURVE' }), h('div', { class: 'v ' + (rQ >= rB ? 'up' : 'dn') + ' sym', text: `${rQ >= rB ? 'FORWARD PREMIUM' : 'FORWARD DISCOUNT'} • 1Y OUTRIGHT: ${fmtNum(rows[7].fwd, dp)}` })
      ),
      wrap
    );

    function renderCurveAndTable() {
      wrap.textContent = '';
      const amt = parseFloat(nInp.value) || 0;
      const W = 520, H = 120, pad = 28;
      const vals = rows.map(r => r.fwd);
      const min = Math.min(...vals, spot), max = Math.max(...vals, spot);
      const span = (max - min) || (spot * 0.001);
      const ptsSvg = rows.map((r, i) => {
        const x = pad + (i / (rows.length - 1)) * (W - 2 * pad);
        const y = H - 20 - ((r.fwd - min) / span) * (H - 36);
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      }).join(' ');

      const ns = 'http://www.w3.org/2000/svg';
      const svg = document.createElementNS(ns, 'svg');
      svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
      svg.style.cssText = 'width:100%;height:125px;background:#040404;border-bottom:1px solid var(--border);display:block';
      const poly = document.createElementNS(ns, 'polyline');
      poly.setAttribute('fill', 'none');
      poly.setAttribute('stroke', '#ffb000');
      poly.setAttribute('stroke-width', '2');
      poly.setAttribute('points', ptsSvg);
      svg.append(poly);
      rows.forEach((r, i) => {
        const x = pad + (i / (rows.length - 1)) * (W - 2 * pad);
        const y = H - 20 - ((r.fwd - min) / span) * (H - 36);
        const c = document.createElementNS(ns, 'circle');
        c.setAttribute('cx', x); c.setAttribute('cy', y); c.setAttribute('r', '3'); c.setAttribute('fill', '#4da3ff');
        const tx = document.createElementNS(ns, 'text');
        tx.setAttribute('x', x); tx.setAttribute('y', H - 5); tx.setAttribute('text-anchor', 'middle');
        tx.setAttribute('fill', '#8a8a8a'); tx.setAttribute('font-size', '9');
        tx.textContent = r.tn;
        svg.append(c, tx);
      });

      wrap.append(
        svg,
        h('table', { class: 't' },
          h('thead', null, h('tr', null, ['Tenor', 'Years', 'Bid Fwd', 'Ask Fwd', 'Fwd Pts', 'Implied Yield', 'Hedging Cost/Benefit'].map(x => h('th', { text: x })))),
          h('tbody', null, rows.map(r => {
            const sprd = isLarge ? (quote === 'IDR' ? 12 : 0.03) : 0.0003;
            const deltaAmt = (r.fwd - spot) * amt;
            return h('tr', { class: 'row' },
              h('td', { class: 'l sym lb', text: r.tn }),
              h('td', { class: 'mu', text: r.yr.toFixed(2) + 'y' }),
              h('td', { class: 'am', text: fmtNum(r.fwd - sprd / 2, dp) }),
              h('td', { class: 'am sym', text: fmtNum(r.fwd + sprd / 2, dp) }),
              h('td', { class: (r.pts >= 0 ? 'up' : 'dn') + ' sym', text: (r.pts >= 0 ? '+' : '') + fmtNum(r.pts, 1) }),
              h('td', { class: r.annCarry >= 0 ? 'up' : 'dn', text: fmtPct(r.annCarry) }),
              h('td', { class: deltaAmt >= 0 ? 'up' : 'dn', text: `${deltaAmt >= 0 ? '+' : '-'}${fmtVol(Math.abs(deltaAmt))} ${quote}` })
            );
          }))
        )
      );
    }
    renderCurveAndTable();
  }
  load();
}

export function mountFUT(body, ctx) {
  body.classList.add('fill');
  const tb = h('div', { class: 'tb' });
  const sc = h('div', { class: 'pb' });
  body.append(tb, sc);

  const CURVES = [
    { sym: 'CL=F', name: 'WTI Crude Oil (NYMEX)', unit: '$/bbl', slope: -0.042, shape: 'BACKWARDATION' },
    { sym: 'BZ=F', name: 'Brent Crude Oil (ICE)', unit: '$/bbl', slope: -0.038, shape: 'BACKWARDATION' },
    { sym: 'GC=F', name: 'COMEX Gold Futures', unit: '$/oz', slope: 0.046, shape: 'CONTANGO' },
    { sym: 'NG=F', name: 'Henry Hub NatGas', unit: '$/MMBtu', slope: 0.145, shape: 'SEASONAL CONTANGO' },
    { sym: 'HG=F', name: 'COMEX Copper', unit: '$/lb', slope: 0.031, shape: 'CONTANGO' },
    { sym: 'BTCUSDT', name: 'CME/Binance BTC Futures', unit: '$', slope: 0.092, shape: 'CONTANGO' }
  ];
  let active = CURVES.find(c => c.sym === ctx.symbol) ? ctx.symbol : 'CL=F';

  async function load() {
    tb.textContent = '';
    tb.append(
      h('span', { class: 'lbl', text: 'FUT TERM STRUCTURE:' }),
      ...CURVES.map(c => h('button', { class: active === c.sym ? 'on' : '', text: c.sym.replace('=F', ''), onclick: () => { active = c.sym; load(); } })),
      h('button', { text: 'BMAP <GO>', onclick: () => ctx.run(`${active} BMAP`) })
    );
    const env = await get('quote', { symbols: CURVES.map(c => c.sym).join(',') }, 6000);
    ctx.status(env);
    sc.textContent = '';
    const qMap = {};
    if (env.ok && Array.isArray(env.data)) env.data.forEach(q => { if (q && q.symbol) qMap[q.symbol] = q; });
    const cfg = CURVES.find(c => c.sym === active) || CURVES[0];
    const q = qMap[active] || {};
    const fallbacks = { 'CL=F': 70.5, 'BZ=F': 74.2, 'GC=F': 2685, 'NG=F': 2.85, 'HG=F': 4.35, BTCUSDT: 89500 };
    const front = q.price || fallbacks[active] || 100;

    const months = ['M1 (FRONT)', 'M2', 'M3', 'M4', 'M5', 'M6', 'M8', 'M10', 'M12 (+1Y)'];
    const tenors = [1, 2, 3, 4, 5, 6, 8, 10, 12];
    const pts = tenors.map((m, i) => {
      const yrs = (m - 1) / 12;
      const wave = active === 'NG=F' ? Math.sin(m * 0.55) * 0.04 : Math.sin(m * 0.25) * 0.002;
      const px = front * (1 + cfg.slope * yrs + wave);
      const spread = px - front;
      const roll = ((px - front) / front) * 100;
      return { lbl: months[i], m, px, spread, roll, oi: Math.round(185000 / Math.pow(m, 0.72)) };
    });

    const W = 520, H = 135, pad = 34;
    const vals = pts.map(p => p.px);
    const min = Math.min(...vals), max = Math.max(...vals), span = (max - min) || 1;
    const ns = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
    svg.style.cssText = 'width:100%;height:135px;background:#040404;border-bottom:1px solid var(--border);display:block';
    const poly = document.createElementNS(ns, 'polyline');
    poly.setAttribute('fill', 'none');
    poly.setAttribute('stroke', cfg.slope < 0 ? '#00d26a' : '#ffb000');
    poly.setAttribute('stroke-width', '2.2');
    poly.setAttribute('points', pts.map((p, i) => {
      const x = pad + (i / (pts.length - 1)) * (W - 2 * pad);
      const y = H - 22 - ((p.px - min) / span) * (H - 42);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(' '));
    svg.append(poly);
    pts.forEach((p, i) => {
      const x = pad + (i / (pts.length - 1)) * (W - 2 * pad);
      const y = H - 22 - ((p.px - min) / span) * (H - 42);
      const dot = document.createElementNS(ns, 'circle');
      dot.setAttribute('cx', x); dot.setAttribute('cy', y); dot.setAttribute('r', '3.2'); dot.setAttribute('fill', '#4da3ff');
      const lbl = document.createElementNS(ns, 'text');
      lbl.setAttribute('x', x); lbl.setAttribute('y', H - 6); lbl.setAttribute('text-anchor', 'middle');
      lbl.setAttribute('fill', '#8a8a8a'); lbl.setAttribute('font-size', '9');
      lbl.textContent = `M${p.m}`;
      svg.append(dot, lbl);
    });

    sc.append(
      h('div', { class: 'kv', style: 'background:#060606;border-bottom:1px solid var(--border)' },
        h('div', { class: 'k', text: 'CONTRACT' }), h('div', { class: 'v am sym', text: `${cfg.name} (${cfg.sym})  •  FRONT: ${fmtPx(front)} ${cfg.unit}` }),
        h('div', { class: 'k', text: 'CURVE REGIME' }), h('div', { class: 'v ' + (cfg.slope < 0 ? 'up' : 'am') + ' sym', text: `${cfg.shape}  (M1-M12 SPREAD: ${fmtChg(pts[pts.length - 1].spread)} / ${fmtPct(pts[pts.length - 1].roll)})` })
      ),
      svg,
      h('table', { class: 't' },
        h('thead', null, h('tr', null, ['Delivery', 'Contract Px', 'Spread vs M1', 'Basis %', 'Est Open Int'].map(x => h('th', { text: x })))),
        h('tbody', null, pts.map(p => h('tr', { class: 'row' },
          h('td', { class: 'l sym lb', text: p.lbl }),
          h('td', { class: 'am sym', text: fmtPx(p.px) }),
          h('td', { class: dirCls(p.spread), text: fmtChg(p.spread) }),
          h('td', { class: dirCls(p.roll), text: fmtPct(p.roll) }),
          h('td', { class: 'mu', text: fmtVol(p.oi) })
        )))
      )
    );
  }
  load();
}

