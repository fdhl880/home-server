import { $, h, fmtTime, LS } from './util.js';
import { get, net, startHub } from './api.js';
import { dev } from './dev-adapter.js';

import { mountGP, mountHP, mountCOMP } from './panels/charts.js';
import { mountMON, mountWL, mountMOST, mountFXC, mountIMAP } from './panels/monitors.js';
import { mountOB, mountTRADES, mountFUND } from './panels/micro.js';
import { mountDES, mountFA, mountCF, mountDVD, mountRV, mountEQS, mountMEMB, mountCN } from './panels/equities.js';
import { mountBETA, mountCORR, mountHVT, mountOVME, mountDCF, mountFSCO, mountYAS, mountWIRP } from './panels/quant.js';
import { mountBOT, mountPORT, mountMARS, mountALRT, mountIB, mountSECF, mountFLDS, mountHELP } from './panels/ops.js';

import { panels as newsPanels } from '../panels/news/index.js';
import { panels as macroPanels } from '../panels/macro/index.js';

// Enable dev adapter ONLY if explicitly requested via ?dev=1
const urlParams = new URLSearchParams(location.search);
if (urlParams.get('dev') === '1') {
  net.adapter = dev;
  const db = $('#devbanner');
  if (db) db.style.display = 'block';
}

const hub = startHub();

function wrapWP5(fn) {
  return (body, ctx) => {
    const inst = fn(body, ctx);
    if (inst && typeof inst.unmount === 'function') ctx.cleanup(() => inst.unmount());
    ctx.status({ source: 'live-api', ts: Date.now(), mode: 'LIVE' });
  };
}

export const CATALOG = [
  // Charts
  { code: 'GP', cat: 'CHART', title: 'Price Graph', desc: 'Candlestick/Line/Area Chart + SMA/EMA/BB/VWAP + RSI14', mount: (b, c) => mountGP(b, c, { intraday: false }) },
  { code: 'GIP', cat: 'CHART', title: 'Intraday Graph', desc: 'Intraday 1m/5m/15m Real-Time Chart & VWAP', mount: (b, c) => mountGP(b, c, { intraday: true }) },
  { code: 'HP', cat: 'CHART', title: 'Historical Price Table', desc: 'Tabular OHLCV History + High/Low/Avg Summary & CSV Export', mount: mountHP },
  { code: 'COMP', cat: 'CHART', title: 'Comparative Returns', desc: 'Multi-Asset Normalized Total Return Chart & Sharpe Ratio', mount: mountCOMP },
  { code: 'GPO', cat: 'CHART', title: 'Graph Overlay', desc: 'Multi-Security Price & Return Overlay', mount: mountCOMP },

  // Monitors & Asset Sectors
  { code: 'MON', cat: 'MONITOR', title: 'Quote Monitor', desc: 'Real-Time Multi-Asset Streaming Quote Grid', mount: (b, c) => mountMON(b, c, { defaultGroup: 'CORE' }) },
  { code: 'QR', cat: 'MONITOR', title: 'Quote Recap', desc: 'Real-Time Bid/Ask & Intraday Quote Recap', mount: (b, c) => mountMON(b, c, { defaultGroup: 'CORE' }) },
  { code: 'BQ', cat: 'MONITOR', title: 'Bloomberg Quote', desc: 'Composite Security Quote & Multi-Asset Monitor', mount: (b, c) => mountMON(b, c, { defaultGroup: 'CORE' }) },
  { code: 'WL', cat: 'MONITOR', title: 'Watchlist Manager', desc: 'Custom Saved Watchlists with Real-Time WebSocket Ticks', mount: mountWL },
  { code: 'MOST', cat: 'MONITOR', title: 'Most Active / Movers', desc: 'Top Gainers, Losers & Volume Leaders (Crypto, Perp, Equities)', mount: mountMOST },
  { code: 'MOV', cat: 'MONITOR', title: 'Market Movers', desc: 'Top Gainers & Losers Leaderboard', mount: mountMOST },
  { code: 'WEI', cat: 'INDEX', title: 'World Equity Indices', desc: 'Global Equity Benchmarks: Americas, EMEA, APAC & IDX/IHSG', mount: (b, c) => mountMON(b, c, { defaultGroup: 'INDICES' }) },
  { code: 'CRYP', cat: 'CRYPTO', title: 'Crypto Monitor', desc: 'Top 20 Institutional Crypto Spot & Perpetuals Monitor', mount: (b, c) => mountMON(b, c, { defaultGroup: 'CRYPTO' }) },
  { code: 'COIN', cat: 'CRYPTO', title: 'Crypto Universe', desc: 'Digital Asset Real-Time Quote Matrix', mount: (b, c) => mountMON(b, c, { defaultGroup: 'CRYPTO' }) },
  { code: 'FXC', cat: 'FX', title: 'Currency Rate Matrix', desc: '8x8 G10 & EM Cross-Currency Matrix + FX Converter', mount: mountFXC },
  { code: 'WCR', cat: 'FX', title: 'World Currency Rankings', desc: 'Global Spot FX Performance & Cross Matrix', mount: mountFXC },
  { code: 'FXCA', cat: 'FX', title: 'FX Conversion Calculator', desc: 'Live Cross-Currency Converter & Matrix', mount: mountFXC },
  { code: 'WFX', cat: 'FX', title: 'World FX Monitor', desc: 'Global Foreign Exchange Monitor', mount: mountFXC },
  { code: 'CMDTY', cat: 'CMDTY', title: 'Global Commodities', desc: 'Energy (WTI, Brent, NatGas), Metals (Gold, Silver, Copper) & Ags', mount: (b, c) => mountMON(b, c, { defaultGroup: 'COMMODITIES' }) },
  { code: 'GLCO', cat: 'CMDTY', title: 'Global Commodity Prices', desc: 'Benchmark Commodity Futures & Spot Monitor', mount: (b, c) => mountMON(b, c, { defaultGroup: 'COMMODITIES' }) },
  { code: 'WB', cat: 'FIXED INC', title: 'World Bond Markets', desc: 'US Treasury Yields & Global Fixed Income Benchmarks', mount: (b, c) => mountMON(b, c, { defaultGroup: 'BONDS' }) },
  { code: 'BTMM', cat: 'FIXED INC', title: 'Treasury & Money Markets', desc: 'US Treasury Bills/Notes/Bonds & Money Market Rates', mount: (b, c) => mountMON(b, c, { defaultGroup: 'BONDS' }) },
  { code: 'RATES', cat: 'FIXED INC', title: 'Rates, Commodities & FX', desc: 'Cross-Asset Yields, Commodities & Major FX Rates', mount: wrapWP5(macroPanels.RATES) },
  { code: 'IMAP', cat: 'MONITOR', title: 'Intraday Market Map', desc: 'Interactive Market Treemap Heatmap by Volume & % Change', mount: mountIMAP },
  { code: 'MMAP', cat: 'MONITOR', title: 'Market Heatmap', desc: 'Sector & Asset Class Visual Heatmap', mount: mountIMAP },

  // Microstructure & Derivatives
  { code: 'OB', cat: 'MICRO', title: 'Order Book Depth (L2 DOM)', desc: 'Live 20-Level Bid/Ask Depth of Market, Spread bps & Imbalance', mount: mountOB },
  { code: 'DOM', cat: 'MICRO', title: 'Depth of Market', desc: 'Real-Time L2 Order Book Ladder', mount: mountOB },
  { code: 'TRADES', cat: 'MICRO', title: 'Time & Sales Tape', desc: 'Live Aggregated Trade Stream with Whale Print Filter', mount: mountTRADES },
  { code: 'TAS', cat: 'MICRO', title: 'Time & Sales', desc: 'Real-Time Tick-by-Tick Trade Recap', mount: mountTRADES },
  { code: 'FUND', cat: 'CRYPTO', title: 'Perpetual Funding & Basis', desc: 'Binance Futures Mark vs Index Price, Basis % & Annualized Funding', mount: mountFUND },

  // Equities & Fundamentals
  { code: 'DES', cat: 'EQUITY', title: 'Security Description', desc: 'Institutional Asset Profile, Snapshot Stats, 52W Range & Filings', mount: mountDES },
  { code: 'FA', cat: 'EQUITY', title: 'Financial Analysis', desc: 'SEC EDGAR XBRL Standardized Income Stmt, Balance Sheet, Cash Flow & Ratios', mount: mountFA },
  { code: 'CF', cat: 'EQUITY', title: 'Company Filings (EDGAR)', desc: 'Official SEC EDGAR 10-K, 10-Q, 8-K, Form 4 & Proxy Filings', mount: mountCF },
  { code: 'FLNG', cat: 'EQUITY', title: 'SEC Filings Archive', desc: 'Direct Links to Official SEC EDGAR Regulatory Filings', mount: mountCF },
  { code: 'DVD', cat: 'EQUITY', title: 'Dividend & Split History', desc: '5-Year Cash Dividend Schedule, TTM Yield & Stock Splits', mount: mountDVD },
  { code: 'SPLT', cat: 'EQUITY', title: 'Stock Splits', desc: 'Historical Corporate Split Ratio Schedule', mount: mountDVD },
  { code: 'RV', cat: 'EQUITY', title: 'Relative Value Peers', desc: 'Sector Peer Group Comparison vs Group Mean', mount: mountRV },
  { code: 'EQS', cat: 'EQUITY', title: 'Equity & Crypto Screener', desc: 'Multi-Factor Market Screener with Momentum & Volume Sorting', mount: mountEQS },
  { code: 'MEMB', cat: 'INDEX', title: 'Index Members & Weights', desc: 'Constituent Weights & Point Impact for S&P 500, Dow 30 & Crypto', mount: mountMEMB },
  { code: 'CN', cat: 'NEWS', title: 'Company / Security News', desc: 'Security-Filtered Real-Time Financial News Wire', mount: (b, c) => mountCN(b, c, { mode: 'CN' }) },
  { code: 'NH', cat: 'NEWS', title: 'News Headlines', desc: 'Chronological Security & Market Headlines', mount: (b, c) => mountCN(b, c, { mode: 'CN' }) },
  { code: 'NSE', cat: 'NEWS', title: 'News Search Engine', desc: 'Keyword Search Across Global Financial News Wires', mount: (b, c) => mountCN(b, c, { mode: 'NSE' }) },
  { code: 'READ', cat: 'NEWS', title: 'Most Read Headlines', desc: 'High-Impact Financial Headlines Wire', mount: (b, c) => mountCN(b, c, { mode: 'READ' }) },

  // News & Macro (WP5)
  { code: 'TOP', cat: 'NEWS', title: 'Top Financial News', desc: 'Curated Breaking Market & Macro Headlines (Deduped)', mount: wrapWP5(newsPanels.TOP) },
  { code: 'N', cat: 'NEWS', title: 'Live News Wire', desc: 'Real-Time Scrolling News Feed with Sentiment Tags (POS/NEG/NEU)', mount: wrapWP5(newsPanels.N) },
  { code: 'ECO', cat: 'MACRO', title: 'Economic Calendar', desc: 'Global Macroeconomic Releases: Actual vs Forecast vs Previous', mount: wrapWP5(newsPanels.ECO) },
  { code: 'WECO', cat: 'MACRO', title: 'World Economic Calendar', desc: 'Global Economic Release Schedule & Impact Ratings', mount: wrapWP5(newsPanels.ECO) },
  { code: 'FNG', cat: 'CRYPTO', title: 'Fear & Greed Index', desc: 'Live Crypto Fear & Greed Index Gauge + 30-Day Sentiment Curve', mount: wrapWP5(newsPanels.FNG) },
  { code: 'MACRO', cat: 'MACRO', title: 'Macroeconomic Indicators', desc: 'FRED Economic Time-Series: CPI Inflation, GDP, Unemployment, Fed Funds', mount: wrapWP5(macroPanels.MACRO) },
  { code: 'ECST', cat: 'MACRO', title: 'Economic Statistics', desc: 'Federal Reserve (FRED) Macroeconomic Series Charts', mount: wrapWP5(macroPanels.MACRO) },
  { code: 'GDP', cat: 'MACRO', title: 'GDP & Macro Monitor', desc: 'US & Global GDP, CPI, Unemployment & Policy Rates', mount: wrapWP5(macroPanels.MACRO) },
  { code: 'YCRV', cat: 'FIXED INC', title: 'Yield Curve Analysis', desc: 'US Treasury Yield Curve (1M–30Y) & 10Y-2Y Inversion Spread', mount: wrapWP5(macroPanels.YCRV) },
  { code: 'GC', cat: 'FIXED INC', title: 'Graph Curve', desc: 'Sovereign Yield Curve Structure & Tenor Spreads', mount: wrapWP5(macroPanels.YCRV) },

  // Quant, Valuation & Fixed Income Calculators
  { code: 'BETA', cat: 'QUANT', title: 'Beta & Linear Regression', desc: 'Security vs Benchmark Scatter Plot, Raw/Blume Beta, Alpha & R²', mount: mountBETA },
  { code: 'CORR', cat: 'QUANT', title: 'Correlation Matrix', desc: 'Cross-Asset Pearson Correlation Heatmap Matrix (30D–252D)', mount: mountCORR },
  { code: 'HVT', cat: 'QUANT', title: 'Historical Volatility', desc: 'Realized Volatility Term Structure (10D–180D) & Percentile Regime', mount: mountHVT },
  { code: 'VOL', cat: 'QUANT', title: 'Volatility Analysis', desc: 'Multi-Window Historical Volatility Workbench', mount: mountHVT },
  { code: 'OMON', cat: 'DERIV', title: 'Option Monitor', desc: 'Option Strike Chain (Calls/Puts) with Implied Vol & Greeks', mount: (b, c) => mountOVME(b, c, { mode: 'OMON' }) },
  { code: 'OVME', cat: 'DERIV', title: 'Option Valuation (Black-Scholes)', desc: 'Black-Scholes-Merton Option Pricer, Greeks (Δ, Γ, ν, Θ, ρ) & Chain', mount: (b, c) => mountOVME(b, c, { mode: 'OVME' }) },
  { code: 'OSA', cat: 'DERIV', title: 'Option Scenario Analysis', desc: 'Option Pricing & Strike Moneyness Workbench', mount: (b, c) => mountOVME(b, c, { mode: 'OSA' }) },
  { code: 'DCF', cat: 'VALUATION', title: 'Discounted Cash Flow', desc: 'Interactive 5Y DCF & WACC Intrinsic Valuation + Sensitivity Matrix', mount: mountDCF },
  { code: 'WACC', cat: 'VALUATION', title: 'Cost of Capital & DCF', desc: 'WACC & Terminal Growth Intrinsic Fair Value Model', mount: mountDCF },
  { code: 'DDM', cat: 'VALUATION', title: 'Dividend & Cash Flow Model', desc: 'Intrinsic Valuation Workbench', mount: mountDCF },
  { code: 'FSCO', cat: 'VALUATION', title: 'Fundamental Scores', desc: '9-Point Piotroski F-Score Financial Health Breakdown (SEC XBRL)', mount: mountFSCO },
  { code: 'YAS', cat: 'FIXED INC', title: 'Yield & Spread Calculator', desc: 'Bond Price, YTM, Macaulay/Modified Duration, Convexity & DV01', mount: mountYAS },
  { code: 'WIRP', cat: 'FIXED INC', title: 'World Interest Rate Prob', desc: 'Implied Fed Rate Path, 2Y-EFFR Spread & 10Y TIPS Breakevens', mount: mountWIRP },
  { code: 'FOMC', cat: 'FIXED INC', title: 'FOMC Policy Monitor', desc: 'Federal Reserve Policy Rate, Real Yields & Inflation Breakevens', mount: mountWIRP },
  { code: 'TIPS', cat: 'FIXED INC', title: 'TIPS & Breakeven Inflation', desc: '10Y TIPS Real Yields vs Breakeven Inflation Expectations', mount: mountWIRP },

  // Operations, Portfolio, Risk, AI & System
  { code: 'BOT', cat: 'AI ENGINE', title: 'Pyrofuel 28-Pillar AI Bot', desc: 'Live Binance Futures Auto-Trader Telemetry, Active Positions & 5-Layer Signals', mount: mountBOT },
  { code: 'PORT', cat: 'PORTFOLIO', title: 'Portfolio & P&L Analytics', desc: 'Multi-Asset Holdings Valuation, Weight Attribution & Intraday P&L', mount: mountPORT },
  { code: 'PRTU', cat: 'PORTFOLIO', title: 'Portfolio Administration', desc: 'Manage Portfolio Lots, Cost Basis & Live Valuation', mount: mountPORT },
  { code: 'MARS', cat: 'RISK', title: 'Multi-Asset Risk System', desc: 'Parametric & Historical VaR (95%/99%), CVaR, Max DD & Stress Tests', mount: mountMARS },
  { code: 'VAR', cat: 'RISK', title: 'Value at Risk', desc: 'Daily Value-at-Risk, Expected Shortfall & Leverage Shock Scenarios', mount: mountMARS },
  { code: 'RISK', cat: 'RISK', title: 'Risk Analytics', desc: 'Portfolio & Single-Security Tail Risk Workbench', mount: mountMARS },
  { code: 'ALRT', cat: 'SYSTEM', title: 'Price Alert Manager', desc: 'Real-Time WebSocket Price Alerts with Audio & Visual Trigger', mount: mountALRT },
  { code: 'IB', cat: 'SYSTEM', title: 'Instant Bloomberg & AI', desc: 'Desk Chat + Ask Bloomberg (ASKB) AI Quant Analyst', mount: mountIB },
  { code: 'MSG', cat: 'SYSTEM', title: 'Terminal Messaging', desc: 'Desk Notes & AI Quant Communication Log', mount: mountIB },
  { code: 'ASKB', cat: 'AI ENGINE', title: 'Ask Bloomberg Quant AI', desc: 'Natural Language Quantitative Market Query Engine', mount: mountIB },
  { code: 'SECF', cat: 'SYSTEM', title: 'Security Finder', desc: 'Global Ticker Search Across Crypto, Equities, Indices, FX, Commodities', mount: mountSECF },
  { code: 'FLDS', cat: 'SYSTEM', title: 'Field Mnemonic Finder', desc: 'Bloomberg Data Field Dictionary with Live Security Values', mount: mountFLDS },
  { code: 'HELP', cat: 'SYSTEM', title: 'Terminal Manual & Help', desc: 'Complete Directory of All Function Codes, Sector Keys & Shortcuts', mount: (b, c) => mountHELP(b, c, { catalog: CATALOG }) }
];

const FN_MAP = new Map(CATALOG.map(x => [x.code, x]));

const WORKSPACES = {
  'DEFAULT DESK': [
    { symbol: 'BTCUSDT', fn: 'GP' },
    { symbol: 'BTCUSDT', fn: 'MON' },
    { symbol: 'BTCUSDT', fn: 'TOP' },
    { symbol: 'BTCUSDT', fn: 'BOT' }
  ],
  'CRYPTO QUANT': [
    { symbol: 'BTCUSDT', fn: 'GP' },
    { symbol: 'BTCUSDT', fn: 'OB' },
    { symbol: 'BTCUSDT.P', fn: 'FUND' },
    { symbol: 'BTCUSDT', fn: 'IMAP' }
  ],
  'EQUITY & EDGAR': [
    { symbol: 'AAPL', fn: 'DES' },
    { symbol: 'AAPL', fn: 'FA' },
    { symbol: 'AAPL', fn: 'DCF' },
    { symbol: 'AAPL', fn: 'CF' }
  ],
  'MACRO & RATES': [
    { symbol: '^TNX', fn: 'YCRV' },
    { symbol: '^TNX', fn: 'MACRO' },
    { symbol: 'EURUSD=X', fn: 'FXC' },
    { symbol: '^GSPC', fn: 'ECO' }
  ],
  'DERIVATIVES & RISK': [
    { symbol: 'BTCUSDT', fn: 'OVME' },
    { symbol: 'BTCUSDT', fn: 'MARS' },
    { symbol: 'BTCUSDT', fn: 'CORR' },
    { symbol: 'BTCUSDT', fn: 'HVT' }
  ],
  'PYROFUEL AI BOT': [
    { symbol: 'ETHUSDT.P', fn: 'BOT' },
    { symbol: 'ETHUSDT', fn: 'GIP' },
    { symbol: 'ETHUSDT', fn: 'TRADES' },
    { symbol: 'ETHUSDT', fn: 'FNG' }
  ]
};

const slots = [...document.querySelectorAll('.slot')];
let activeSlot = 0;
let panes = LS.get('bbg_active_panes_v2', WORKSPACES['DEFAULT DESK']);
if (!Array.isArray(panes) || panes.length !== 4) panes = JSON.parse(JSON.stringify(WORKSPACES['DEFAULT DESK']));

const cleanups = [null, null, null, null];

function savePanes() { LS.set('bbg_active_panes_v2', panes); }

function setActiveSlot(idx) {
  activeSlot = idx;
  slots.forEach((s, i) => s.classList.toggle('active', i === idx));
  const p = panes[activeSlot];
  $('#cmdctx').textContent = `[P${activeSlot + 1}: ${p.symbol} ${p.fn}]`;
}

function mountSlot(idx) {
  if (cleanups[idx]) {
    try { cleanups[idx](); } catch {}
    cleanups[idx] = null;
  }
  const slot = slots[idx];
  slot.textContent = '';
  const state = panes[idx];
  const fnDef = FN_MAP.get(state.fn) || FN_MAP.get('GP');

  const metaEl = h('span', { class: 'meta', text: '...' });
  const badgeEl = h('span', { class: 'badge LIVE', text: 'INIT' });

  const secInput = h('input', {
    value: state.symbol,
    title: 'Change panel security',
    style: 'width:92px;background:#000;color:var(--amber);border:1px solid #333;padding:0 4px;font-weight:bold;text-transform:uppercase',
    onclick: ev => ev.stopPropagation(),
    onkeydown: ev => {
      if (ev.key === 'Enter') {
        const s = secInput.value.trim().toUpperCase();
        if (s) { state.symbol = s; savePanes(); mountSlot(idx); setActiveSlot(idx); }
      }
    }
  });

  const fnSelect = h('select', {
    title: 'Switch panel function',
    style: 'background:#000;color:var(--label);border:1px solid #333;font-size:11px',
    onclick: ev => ev.stopPropagation(),
    onchange: () => {
      state.fn = fnSelect.value;
      savePanes();
      mountSlot(idx);
      setActiveSlot(idx);
    }
  }, CATALOG.map(c => h('option', { value: c.code, selected: c.code === fnDef.code ? 'selected' : null, text: `${c.code} - ${c.title}` })));

  const maxBtn = h('button', {
    class: 'x',
    title: 'Maximize / Restore Panel',
    text: '□',
    onclick: ev => {
      ev.stopPropagation();
      const isMax = slot.style.position === 'fixed';
      if (isMax) {
        slot.style.cssText = '';
      } else {
        slot.style.cssText = 'position:fixed;inset:28px 0 38px 0;z-index:40';
      }
      window.dispatchEvent(new Event('resize'));
    }
  });

  const hdr = h('div', {
    class: 'ph',
    draggable: 'true',
    onclick: () => setActiveSlot(idx)
  },
    h('span', { class: 'fn', text: `P${idx + 1}:${fnDef.code}` }),
    secInput,
    fnSelect,
    h('span', { class: 'ttl', text: fnDef.title }),
    h('span', { class: 'sp' }),
    metaEl,
    badgeEl,
    maxBtn
  );

  // Drag to swap panels
  hdr.addEventListener('dragstart', e => { e.dataTransfer.setData('text/plain', String(idx)); });
  slot.addEventListener('dragover', e => { e.preventDefault(); slot.classList.add('dropt'); });
  slot.addEventListener('dragleave', () => slot.classList.remove('dropt'));
  slot.addEventListener('drop', e => {
    e.preventDefault();
    slot.classList.remove('dropt');
    const from = +e.dataTransfer.getData('text/plain');
    if (isFinite(from) && from !== idx && panes[from]) {
      const tmp = panes[from]; panes[from] = panes[idx]; panes[idx] = tmp;
      savePanes();
      mountSlot(from);
      mountSlot(idx);
      setActiveSlot(idx);
    }
  });

  const body = h('div', { class: 'pb', onclick: () => setActiveSlot(idx) });
  const panelEl = h('div', { class: 'panel' }, hdr, body);
  slot.append(panelEl);

  const cbs = [];
  cleanups[idx] = () => cbs.forEach(fn => { try { fn(); } catch {} });

  const ctx = {
    get symbol() { return state.symbol; },
    fn: fnDef.code,
    cleanup(fn) { if (typeof fn === 'function') cbs.push(fn); },
    sub(ch, cb) {
      const u = hub.sub(ch, cb);
      cbs.push(u);
      return u;
    },
    subscribe(topic, cb) {
      if (topic === 'news') {
        const iv = setInterval(async () => {
          const r = await get('news', { limit: 20 }, 15000);
          if (r.ok && r.data) cb(r.data);
        }, 30000);
        cbs.push(() => clearInterval(iv));
        return () => clearInterval(iv);
      }
      return () => {};
    },
    async fetchJson(path) {
      const r = await fetch(path, { cache: 'no-store' });
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    },
    status(env) {
      if (!env) return;
      const mode = env.mode || (env.ok === false ? 'NA' : 'LIVE');
      badgeEl.className = 'badge ' + (mode === 'N/A' ? 'NA' : mode);
      badgeEl.textContent = mode;
      metaEl.textContent = `${env.source || '-'} • ${fmtTime(env.ts || Date.now())}`;
    },
    setSymbol(sym) {
      if (!sym) return;
      state.symbol = String(sym).trim().toUpperCase();
      savePanes();
      mountSlot(idx);
      setActiveSlot(idx);
    },
    run(cmdStr) {
      setActiveSlot(idx);
      executeCommand(cmdStr);
    }
  };

  try {
    fnDef.mount(body, ctx);
  } catch (err) {
    body.append(h('div', { class: 'na', text: 'Panel error: ' + err.message }));
  }
}

// Command Parser: supports `[FUNCTION]`, `[SECURITY]`, `[SECURITY] [FUNCTION]`, `[SECURITY] [SECTOR] [FUNCTION] <GO>`
const SECTORS = new Set(['EQUITY', 'CORP', 'GOVT', 'CMDTY', 'INDEX', 'CURNCY', 'CRYP', 'CRYPTO', 'MTGE', 'MUNI', 'PFD', 'GO']);

export function executeCommand(raw) {
  const cleaned = String(raw || '').trim().toUpperCase().replace(/<GO>$/i, '').trim();
  if (!cleaned) return;
  const tokens = cleaned.split(/\s+/).filter(t => !SECTORS.has(t));
  if (!tokens.length) return;

  const cur = panes[activeSlot];
  if (tokens.length === 1) {
    const t0 = tokens[0];
    if (FN_MAP.has(t0)) {
      cur.fn = t0;
    } else {
      cur.symbol = normalizeTickerInput(t0);
    }
  } else {
    const last = tokens[tokens.length - 1];
    if (FN_MAP.has(last)) {
      cur.symbol = normalizeTickerInput(tokens[0]);
      cur.fn = last;
    } else if (FN_MAP.has(tokens[0])) {
      cur.fn = tokens[0];
      cur.symbol = normalizeTickerInput(tokens[1]);
    } else {
      cur.symbol = normalizeTickerInput(tokens[0]);
    }
  }

  savePanes();
  mountSlot(activeSlot);
  setActiveSlot(activeSlot);
  $('#msg').textContent = `OK: ${cur.symbol} ${cur.fn} <GO>`;
}

function normalizeTickerInput(s) {
  const map = {
    BTC: 'BTCUSDT', ETH: 'ETHUSDT', SOL: 'SOLUSDT', BNB: 'BNBUSDT', XRP: 'XRPUSDT', DOGE: 'DOGEUSDT',
    SPX: '^GSPC', SP500: '^GSPC', NDX: '^IXIC', DJI: '^DJI', INDU: '^DJI', NKY: '^N225', IHSG: '^JKSE', JKSE: '^JKSE',
    GOLD: 'GC=F', XAUUSD: 'GC=F', WTI: 'CL=F', OIL: 'CL=F', US10Y: '^TNX', UST10Y: '^TNX',
    EURUSD: 'EURUSD=X', USDJPY: 'USDJPY=X', GBPUSD: 'GBPUSD=X', USDIDR: 'USDIDR=X'
  };
  return map[s] || s;
}

// Command bar & Autocomplete
const cmdInput = $('#cmd');
const acBox = $('#ac');
let acItems = [], acIndex = 0;

function renderAC(items) {
  acItems = items;
  acIndex = 0;
  if (!items.length) { acBox.style.display = 'none'; return; }
  acBox.textContent = '';
  acBox.style.display = 'block';
  items.forEach((it, idx) => {
    acBox.append(h('div', {
      class: 'it' + (idx === acIndex ? ' sel' : ''),
      onmousedown: ev => {
        ev.preventDefault();
        cmdInput.value = '';
        acBox.style.display = 'none';
        executeCommand(it.cmd);
      }
    },
      h('span', { class: 'code', text: it.code }),
      h('span', { class: 'desc', text: it.desc })
    ));
  });
}

let searchTimer = null;
cmdInput.addEventListener('input', () => {
  const q = cmdInput.value.trim().toUpperCase();
  if (!q) { acBox.style.display = 'none'; return; }
  const parts = q.split(/\s+/);
  const last = parts[parts.length - 1];
  const fnMatches = CATALOG
    .filter(c => c.code.startsWith(last) || c.title.toUpperCase().includes(last) || c.desc.toUpperCase().includes(last))
    .slice(0, 8)
    .map(c => ({
      code: parts.length > 1 ? `${parts[0]} ${c.code}` : c.code,
      desc: `[${c.cat}] ${c.title} — ${c.desc}`,
      cmd: parts.length > 1 ? `${parts[0]} ${c.code}` : c.code
    }));
  renderAC(fnMatches);

  clearTimeout(searchTimer);
  if (parts.length === 1 && q.length >= 2) {
    searchTimer = setTimeout(async () => {
      const env = await get('search', { q }, 15000);
      if (env.ok && Array.isArray(env.data)) {
        const secMatches = env.data.slice(0, 6).map(s => ({
          code: `${s.symbol} <${(s.asset || 'ASSET').toUpperCase()}>`,
          desc: `${s.name || s.symbol} (${s.exchange || s.source})`,
          cmd: s.symbol
        }));
        renderAC([...fnMatches, ...secMatches]);
      }
    }, 220);
  }
});

cmdInput.addEventListener('keydown', e => {
  if (e.key === 'ArrowDown' && acItems.length) {
    e.preventDefault();
    acIndex = (acIndex + 1) % acItems.length;
    [...acBox.children].forEach((el, i) => el.classList.toggle('sel', i === acIndex));
  } else if (e.key === 'ArrowUp' && acItems.length) {
    e.preventDefault();
    acIndex = (acIndex - 1 + acItems.length) % acItems.length;
    [...acBox.children].forEach((el, i) => el.classList.toggle('sel', i === acIndex));
  } else if (e.key === 'Enter') {
    e.preventDefault();
    const val = cmdInput.value.trim();
    const picked = (acBox.style.display !== 'none' && acItems[acIndex] && !val.includes(' ')) ? null : null;
    acBox.style.display = 'none';
    cmdInput.value = '';
    if (val) executeCommand(val);
    else if (picked) executeCommand(picked.cmd);
  } else if (e.key === 'Escape') {
    acBox.style.display = 'none';
    cmdInput.value = '';
    cmdInput.blur();
  }
});
cmdInput.addEventListener('blur', () => setTimeout(() => { acBox.style.display = 'none'; }, 180));
$('#go').addEventListener('click', () => {
  const val = cmdInput.value.trim();
  acBox.style.display = 'none';
  cmdInput.value = '';
  executeCommand(val);
});

// Yellow Market Sector & Function F-Keys Bar
const FKEYS = [
  ['F1', 'HELP', 'HELP'],
  ['F2', 'GOVT', '^TNX YCRV'],
  ['F3', 'MACRO', 'MACRO'],
  ['F4', 'ECO', 'ECO'],
  ['F5', 'NEWS', 'TOP'],
  ['F6', 'CRYP', 'BTCUSDT CRYP'],
  ['F7', 'FUND', 'BTCUSDT.P FUND'],
  ['F8', 'EQUITY', 'AAPL DES'],
  ['F9', 'CMDTY', 'GC=F CMDTY'],
  ['F10', 'INDEX', '^GSPC WEI'],
  ['F11', 'CURNCY', 'EURUSD=X FXC'],
  ['F12', 'AI BOT', 'BOT']
];
const fkBar = $('#fkeys');
for (const [fk, lbl, cmd] of FKEYS) {
  fkBar.append(h('button', {
    title: `${fk}: ${cmd}`,
    onclick: () => executeCommand(cmd)
  }, h('b', { text: fk + ' ' }), lbl));
}

// Global keyboard shortcuts
window.addEventListener('keydown', e => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
    e.preventDefault();
    cmdInput.focus();
    cmdInput.select();
  } else if (e.key === 'F1') {
    e.preventDefault();
    executeCommand('HELP');
  }
});

// Resizable 4-quadrant splitters
function bindSplitter(el, isVert) {
  el.addEventListener('pointerdown', e => {
    e.preventDefault();
    el.setPointerCapture(e.pointerId);
    el.classList.add('drag');
    const grid = $('#grid');
    const move = ev => {
      const r = grid.getBoundingClientRect();
      const pct = isVert
        ? ((ev.clientX - r.left) / r.width) * 100
        : ((ev.clientY - r.top) / r.height) * 100;
      const clamped = Math.max(20, Math.min(80, pct));
      document.documentElement.style.setProperty(isVert ? '--c' : '--r', clamped.toFixed(1));
      window.dispatchEvent(new Event('resize'));
    };
    const up = () => {
      el.classList.remove('drag');
      el.removeEventListener('pointermove', move);
      el.removeEventListener('pointerup', up);
    };
    el.addEventListener('pointermove', move);
    el.addEventListener('pointerup', up);
  });
}
bindSplitter($('#vs'), true);
bindSplitter($('#hs'), false);

// Workspace selector
const wsel = $('#wsel');
wsel.append(h('option', { value: '', text: 'LAUNCHPAD WORKSPACES (BLP)...' }));
for (const k of Object.keys(WORKSPACES)) {
  wsel.append(h('option', { value: k, text: 'WORKSPACE: ' + k }));
}
wsel.addEventListener('change', () => {
  const k = wsel.value;
  if (WORKSPACES[k]) {
    panes = JSON.parse(JSON.stringify(WORKSPACES[k]));
    savePanes();
    for (let i = 0; i < 4; i++) mountSlot(i);
    setActiveSlot(0);
    $('#msg').textContent = `WORKSPACE: ${k}`;
  }
  wsel.value = '';
});

// Status bar: WebSocket state, Provider Health & 4 World Clocks
hub.listeners.add(st => {
  const el = $('#wsstate');
  if (el) {
    el.className = 'badge ' + (st === 'OPEN' ? 'LIVE' : st === 'DEV' ? 'DEV' : 'DELAYED');
    el.textContent = 'WS:' + st;
  }
});

async function pollHealth() {
  const env = await get('health', {}, 10000);
  const provEl = $('#prov');
  if (!provEl || !env.ok || !env.data || !env.data.providers) return;
  provEl.textContent = '';
  for (const [name, p] of Object.entries(env.data.providers)) {
    if (p.status === 'DISABLED') continue;
    provEl.append(h('span', { title: `${name}: ${p.status} (${p.latencyMs ?? '-'}ms)` },
      h('i', { class: 'dot ' + (p.status || 'UNKNOWN') }),
      name.replace('binance-', 'bn-')
    ));
  }
}
pollHealth();
setInterval(pollHealth, 20000);

function updateClocks() {
  const now = new Date();
  const fmt = tz => now.toLocaleTimeString('en-GB', { timeZone: tz, hour12: false });
  const el = $('#clocks');
  if (el) {
    el.innerHTML = `<b>WIB</b> ${fmt('Asia/Jakarta')} <b>UTC</b> ${fmt('UTC')} <b>NY</b> ${fmt('America/New_York')} <b>LDN</b> ${fmt('Europe/London')}`;
  }
}
updateClocks();
setInterval(updateClocks, 1000);

// Mount all 4 quadrants
for (let i = 0; i < 4; i++) mountSlot(i);
setActiveSlot(0);
$('#msg').textContent = `READY (${CATALOG.length} FUNCTIONS LOADED)`;

