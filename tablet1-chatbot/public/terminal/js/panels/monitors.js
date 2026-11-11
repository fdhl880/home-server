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

export function mountBMAP(body, ctx) {
  body.classList.add('fill');
  let filter = 'ALL'; // 'ALL' | 'ENERGY' | 'METALS' | 'CHOKEPOINT' | 'AGS'
  let selectedId = 'HORMUZ';
  const tb = h('div', { class: 'tb' });
  const sc = h('div', { class: 'pb' });
  body.append(tb, sc);

  const NODES = [
    { id: 'CUSHING', name: 'Cushing Crude Hub (Oklahoma, US)', cat: 'ENERGY', sym: 'CL=F', lat: 35.98, lon: -96.76, flow: '78.4M bbl Storage / WTI Delivery Point', status: 'OPERATIONAL', tankers: 'Pipeline Hub (Keystone / Seaway)' },
    { id: 'BRENT', name: 'North Sea Brent Terminal (Sullom Voe, UK)', cat: 'ENERGY', sym: 'BZ=F', lat: 59.5, lon: -1.3, flow: '1.8M bbl/d BFOET Benchmark', status: 'OPERATIONAL', tankers: '14 Aframax / Suezmax Active' },
    { id: 'SABINE', name: 'Sabine Pass & Henry Hub LNG (Gulf Coast, US)', cat: 'ENERGY', sym: 'NG=F', lat: 29.7, lon: -93.8, flow: '4.7 Bcf/d LNG Feedgas Export', status: 'FULL CAPACITY', tankers: '21 LNG Carriers Queued' },
    { id: 'HORMUZ', name: 'Strait of Hormuz (Persian Gulf Chokepoint)', cat: 'CHOKEPOINT', sym: 'BZ=F', lat: 26.5, lon: 56.2, flow: '20.9M bbl/d Crude & Condensate (~21% Global)', status: 'ELEVATED RISK', tankers: '42 VLCC Supertankers Transiting' },
    { id: 'MALACCA', name: 'Strait of Malacca (Indonesia / Singapore / Malaysia)', cat: 'CHOKEPOINT', sym: 'BZ=F', lat: 2.5, lon: 101.8, flow: '23.7M bbl/d APAC Energy Lifeline', status: 'HIGH TRAFFIC', tankers: '68 VLCC & LNG Vessels Active' },
    { id: 'SUEZ', name: 'Suez Canal & Bab el-Mandeb (Red Sea Corridor)', cat: 'CHOKEPOINT', sym: 'CL=F', lat: 29.9, lon: 32.5, flow: '8.8M bbl/d (Cape of Good Hope Diverted)', status: 'HIGH ALERT', tankers: '31 Tankers Rerouted (+12 Days)' },
    { id: 'PANAMA', name: 'Panama Canal (Americas — Pacific LNG/Grain Corridor)', cat: 'CHOKEPOINT', sym: 'NG=F', lat: 9.1, lon: -79.7, flow: '2.6M bbl/d Products & US Gulf Grain', status: 'NORMAL', tankers: '34 Neopanamax Daily Slots' },
    { id: 'GRASBERG', name: 'Grasberg Gold & Copper Complex (Papua, Indonesia)', cat: 'METALS', sym: 'GC=F', lat: -4.05, lon: 137.11, flow: '1.6B lbs Cu + 1.8M oz Au Annual Output', status: 'OPERATIONAL', tankers: 'Amamapare Port Concentrate Export' },
    { id: 'COMEX', name: 'COMEX / NYMEX Bullion & Metals Vaults (New York)', cat: 'METALS', sym: 'GC=F', lat: 40.71, lon: -74.0, flow: '18.2M oz Registered Gold / 290M oz Silver', status: 'OPERATIONAL', tankers: 'T+1 Physical Bullion Settlement' },
    { id: 'ESCONDIDA', name: 'Escondida Copper Mine (Atacama Desert, Chile)', cat: 'METALS', sym: 'HG=F', lat: -24.26, lon: -69.07, flow: '1.1M Metric Tons Copper Cathode/Concentrate', status: 'OPERATIONAL', tankers: 'Coloso Port Bulk Ore Terminal' },
    { id: 'RAND', name: 'Witwatersrand & Bushveld PGM/Gold Belt (South Africa)', cat: 'METALS', sym: 'SI=F', lat: -26.2, lon: 28.0, flow: '72% Global Platinum + Deep-Level Gold', status: 'OPERATIONAL', tankers: 'Durban / Richards Bay Export' },
    { id: 'CORNBELT', name: 'US Midwest Grain & CBOT Delivery Hub (Chicago/Iowa)', cat: 'AGS', sym: 'ZC=F', lat: 41.8, lon: -89.5, flow: '385M MT Corn + 115M MT Soybean Harvest', status: 'PEAK FLOW', tankers: 'Mississippi Barge -> New Orleans' },
    { id: 'BLACKSEA', name: 'Black Sea & Bosporus Grain Corridor (Odessa/Istanbul)', cat: 'AGS', sym: 'ZW=F', lat: 43.2, lon: 31.0, flow: '48M MT Wheat & Corn Maritime Export', status: 'MONITORED', tankers: '19 Panamax Bulk Carriers' },
    { id: 'MATO', name: 'Mato Grosso & Santos Ag Export Hub (Brazil)', cat: 'AGS', sym: 'ZS=F', lat: -15.5, lon: -55.0, flow: '158M MT Soybean #1 Global Exporter', status: 'PEAK FLOW', tankers: '44 Panamax Bulk Vessels at Santos' }
  ];

  async function load() {
    const syms = [...new Set(NODES.map(n => n.sym))].join(',');
    const qEnv = await get('quote', { symbols: syms }, 6000);
    ctx.status(qEnv);
    const qMap = {};
    if (qEnv.ok && Array.isArray(qEnv.data)) {
      qEnv.data.forEach(q => { if (q && q.symbol) qMap[q.symbol] = q; });
    }

    tb.textContent = '';
    tb.append(
      h('span', { class: 'lbl', text: '90) Actions  |  BMAP — Global Commodity, Mine, Tanker & Chokepoint Map:' }),
      ...[['ALL', 'ALL GLOBAL NODES (14)'], ['ENERGY', 'OIL & LNG HUBS'], ['CHOKEPOINT', 'MARITIME CHOKEPOINTS'], ['METALS', 'GOLD/COPPER MINES'], ['AGS', 'AGRICULTURE CORRIDORS']].map(([k, lbl]) =>
        h('button', { class: filter === k ? 'on' : '', text: lbl, onclick: () => { filter = k; load(); } })
      )
    );

    sc.textContent = '';
    const visible = NODES.filter(n => filter === 'ALL' || n.cat === filter);
    const selNode = NODES.find(n => n.id === selectedId) || visible[0] || NODES[0];
    const selQ = qMap[selNode.sym] || {};

    // Interactive SVG World Geospatial Map (800 x 235)
    const ns = 'http://www.w3.org/2000/svg';
    const W = 800, H = 235;
    const svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
    svg.setAttribute('preserveAspectRatio', 'none');
    svg.style.cssText = 'width:100%;height:235px;display:block;background:#02060d;border-bottom:1px solid var(--border)';

    const projX = lon => ((lon + 180) / 360) * W;
    const projY = lat => ((90 - lat) / 180) * H;

    // Graticule grid lines
    for (let lon = -150; lon <= 150; lon += 30) {
      const l = document.createElementNS(ns, 'line');
      const x = projX(lon);
      l.setAttribute('x1', x); l.setAttribute('y1', 0); l.setAttribute('x2', x); l.setAttribute('y2', H);
      l.setAttribute('stroke', lon === 0 ? '#16283e' : '#0a1420');
      svg.append(l);
    }
    for (let lat = -60; lat <= 60; lat += 30) {
      const l = document.createElementNS(ns, 'line');
      const y = projY(lat);
      l.setAttribute('x1', 0); l.setAttribute('y1', y); l.setAttribute('x2', W); l.setAttribute('y2', y);
      l.setAttribute('stroke', lat === 0 ? '#16283e' : '#0a1420');
      svg.append(l);
    }

    // Simplified Continental Polygons (Geospatial Silhouette)
    const continents = [
      // North America
      'M 55,28 L 195,25 L 245,65 L 205,102 L 165,112 L 115,92 L 60,55 Z',
      // South America
      'M 215,118 L 285,128 L 298,162 L 265,212 L 238,210 L 222,158 Z',
      // Europe
      'M 365,34 L 465,28 L 485,62 L 435,76 L 372,72 Z',
      // Africa
      'M 362,80 L 455,80 L 485,120 L 455,186 L 415,188 L 385,132 L 358,105 Z',
      // Asia & Middle East
      'M 468,30 L 695,28 L 725,75 L 665,118 L 595,122 L 535,108 L 472,95 Z',
      // Maritime SE Asia / Indonesia Archipelago
      'M 615,118 L 698,122 L 712,138 L 625,136 Z',
      // Australia
      'M 642,152 L 732,150 L 738,195 L 655,195 Z'
    ];
    for (const d of continents) {
      const p = document.createElementNS(ns, 'path');
      p.setAttribute('d', d);
      p.setAttribute('fill', '#0d1b2a');
      p.setAttribute('stroke', '#1f3a52');
      p.setAttribute('stroke-width', '1');
      svg.append(p);
    }

    // Major Maritime Commodity Shipping Corridors
    const lanes = [
      [[56.2, 26.5], [101.8, 2.5], [122.0, 30.0]], // Hormuz -> Malacca -> East Asia
      [[56.2, 26.5], [32.5, 29.9], [5.0, 38.0]],   // Hormuz -> Suez -> Med
      [[-93.8, 29.7], [-79.7, 9.1], [135.0, 34.0]], // US Gulf -> Panama -> Asia
      [[-93.8, 29.7], [-1.3, 59.5]]                 // US Gulf -> North Sea/Europe
    ];
    for (const pts of lanes) {
      const pl = document.createElementNS(ns, 'polyline');
      pl.setAttribute('fill', 'none');
      pl.setAttribute('stroke', '#19527a');
      pl.setAttribute('stroke-width', '1.3');
      pl.setAttribute('stroke-dasharray', '4,3');
      pl.setAttribute('points', pts.map(([lo, la]) => `${projX(lo).toFixed(1)},${projY(la).toFixed(1)}`).join(' '));
      svg.append(pl);
    }

    const catColor = { ENERGY: '#ffb000', CHOKEPOINT: '#ff3b30', METALS: '#00d26a', AGS: '#4da3ff' };

    for (const n of visible) {
      const x = projX(n.lon), y = projY(n.lat);
      const col = catColor[n.cat] || '#ffb000';
      const isSel = n.id === selNode.id;
      const g = document.createElementNS(ns, 'g');
      g.style.cursor = 'pointer';
      g.onclick = () => { selectedId = n.id; load(); };

      if (isSel || n.cat === 'CHOKEPOINT') {
        const ring = document.createElementNS(ns, 'circle');
        ring.setAttribute('cx', x.toFixed(1)); ring.setAttribute('cy', y.toFixed(1));
        ring.setAttribute('r', isSel ? '10' : '7');
        ring.setAttribute('fill', 'none'); ring.setAttribute('stroke', col); ring.setAttribute('stroke-width', isSel ? '1.8' : '1');
        g.append(ring);
      }
      const dot = document.createElementNS(ns, 'circle');
      dot.setAttribute('cx', x.toFixed(1)); dot.setAttribute('cy', y.toFixed(1));
      dot.setAttribute('r', isSel ? '5' : '3.8');
      dot.setAttribute('fill', col);
      g.append(dot);

      const lbl = document.createElementNS(ns, 'text');
      lbl.setAttribute('x', (x + 7).toFixed(1)); lbl.setAttribute('y', (y + 3).toFixed(1));
      lbl.setAttribute('fill', isSel ? '#ffffff' : col);
      lbl.setAttribute('font-size', isSel ? '10' : '8.8');
      lbl.setAttribute('font-weight', 'bold');
      const q = qMap[n.sym];
      lbl.textContent = `${n.id} ${q && q.price ? '(' + fmtPx(q.price) + ')' : ''}`;
      g.append(lbl);
      svg.append(g);
    }

    // Selected Node Telemetry Bar
    const inspector = h('div', { class: 'kv', style: 'background:#070a10;border-bottom:1px solid var(--border);padding:6px 8px' },
      h('div', { class: 'k', text: 'SELECTED BMAP NODE' }),
      h('div', { class: 'v am sym', text: `${selNode.name} [${selNode.cat}] — Coordinates: ${selNode.lat.toFixed(2)}°, ${selNode.lon.toFixed(2)}°` }),
      h('div', { class: 'k', text: 'PHYSICAL FLOW & CAPACITY' }),
      h('div', { class: 'v lb', text: `${selNode.flow}  |  Vessels/Logistics: ${selNode.tankers}` }),
      h('div', { class: 'k', text: `BENCHMARK CONTRACT (${selNode.sym})` }),
      h('div', { class: 'v sym ' + dirCls(selQ.chgPct), style: 'display:flex;gap:10px;align-items:center' },
        h('span', { text: selQ.price ? `${fmtPx(selQ.price)} (${fmtPct(selQ.chgPct)})` : 'LIVE BENCHMARK' }),
        h('button', { class: 'on', text: `OPEN ${selNode.sym} GP <GO>`, onclick: () => ctx.run(`${selNode.sym} GP`) })
      )
    );

    const tbl = h('table', { class: 't' },
      h('thead', null, h('tr', null, ['Node ID', 'Category', 'Global Hub / Chokepoint / Mine', 'Benchmark', 'Live Price', '1D %', 'Physical Throughput / Tankers', 'Status'].map(x => h('th', { text: x })))),
      h('tbody', null, visible.map(n => {
        const q = qMap[n.sym] || {};
        return h('tr', {
          class: 'row',
          style: n.id === selNode.id ? 'background:#1c1400' : '',
          onclick: () => { selectedId = n.id; load(); }
        },
          h('td', { class: 'l sym am', text: n.id }),
          h('td', { class: 'l lb', text: n.cat }),
          h('td', { class: 'l', style: 'color:#fff', text: n.name }),
          h('td', { class: 'l sym lb', text: n.sym }),
          h('td', { class: 'am sym', text: q.price ? fmtPx(q.price) : '-' }),
          h('td', { class: dirCls(q.chgPct) + ' sym', text: q.chgPct != null ? fmtPct(q.chgPct) : '-' }),
          h('td', { class: 'l mu', text: n.flow }),
          h('td', { class: 'l sym ' + (n.status.includes('ALERT') || n.status.includes('RISK') ? 'dn' : 'up'), text: n.status })
        );
      }))
    );

    sc.append(
      h('div', { class: 'tb', style: 'background:#05080f;gap:14px;font-size:10.5px' },
        h('span', { style: 'color:#ffb000;font-weight:bold', text: '● ENERGY & LNG HUBS' }),
        h('span', { style: 'color:#ff3b30;font-weight:bold', text: '◎ MARITIME CHOKEPOINTS (HORMUZ / MALACCA / SUEZ / PANAMA)' }),
        h('span', { style: 'color:#00d26a;font-weight:bold', text: '● GOLD / COPPER MINES (GRASBERG / ESCONDIDA / COMEX)' }),
        h('span', { style: 'color:#4da3ff;font-weight:bold', text: '● AGRICULTURAL EXPORT CORRIDORS' })
      ),
      svg,
      inspector,
      tbl
    );
  }

  load();
}
