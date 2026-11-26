import { $, h, fmtPx, fmtPct, fmtTime, dirCls, LS } from './util.js';
import { get, net, startHub, apiFetch, setDashToken, setAuthRequiredHandler } from './api.js';
import { dev } from './dev-adapter.js';

import { mountGP, mountHP, mountCOMP } from './panels/charts.js?v=20261126d';
import { mountMON, mountWL, mountMOST, mountFXC, mountFXFC, mountFUT, mountIMAP, mountBMAP } from './panels/monitors.js?v=20261126d';
import { mountOB, mountTRADES, mountFUND, mountVAP, mountLIQ, mountOMST } from './panels/micro.js?v=20261126d';
import { mountDES, mountFA, mountCF, mountDVD, mountRV, mountEQS, mountMEMB, mountCN, mountANR, mountERN, mountSPLC, mountHDS, mountMGMT, mountMA, mountIPO, mountESG } from './panels/equities.js?v=20261126d';
import { mountBETA, mountCORR, mountHVT, mountOVME, mountDCF, mountFSCO, mountYAS, mountWIRP, mountBTST, mountECFC, mountWCDS, mountOVDV, mountRRG, mountSEAG, mountDOTS, mountFSTA, mountCRPR, mountBTCA } from './panels/quant.js?v=20261126d';
import { mountBOT, mountPORT, mountEMSX, mountMARS, mountALRT, mountIB, mountMSG, mountSECF, mountFLDS, mountHELP, mountBLP } from './panels/ops.js?v=20261126d';
import { mountFACT, mountTRAN, mountSTUDIO, mountBI, mountETF, mountFIN, mountWDGT, mountROE, mountTECH, mountBRDT } from './panels/intelligence.js?v=20261126d';

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
  { code: 'FXFC', cat: 'FX', title: 'FX Forward Calculator', desc: 'Covered Interest Rate Parity Forward Points (O/N–2Y) & Forward Curve Diagram', mount: mountFXFC },
  { code: 'WFX', cat: 'FX', title: 'World FX Monitor', desc: 'Global Foreign Exchange Monitor', mount: mountFXC },
  { code: 'CMDTY', cat: 'CMDTY', title: 'Global Commodities', desc: 'Energy (WTI, Brent, NatGas), Metals (Gold, Silver, Copper) & Ags', mount: (b, c) => mountMON(b, c, { defaultGroup: 'COMMODITIES' }) },
  { code: 'GLCO', cat: 'CMDTY', title: 'Global Commodity Prices', desc: 'Benchmark Commodity Futures & Spot Monitor', mount: (b, c) => mountMON(b, c, { defaultGroup: 'COMMODITIES' }) },
  { code: 'FUT', cat: 'CMDTY', title: 'Futures Term Structure Curve', desc: 'Contango / Backwardation Forward Curve (M1–M12) & Basis Spreads', mount: mountFUT },
  { code: 'BMAP', cat: 'CMDTY', title: 'Bloomberg Commodity & Maritime Map', desc: 'Interactive World Map of Oil Hubs, LNG Tankers, Gold/Copper Mines & Chokepoints (Hormuz, Malacca, Suez)', mount: mountBMAP },
  { code: 'CMAP', cat: 'CMDTY', title: 'Commodity Geospatial Map', desc: 'Global Energy, Metals, Agriculture & Chokepoint Geospatial Map', mount: mountBMAP },
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
  { code: 'VAP', cat: 'MICRO', title: 'Volume-at-Price Profile', desc: 'Horizontal Volume Profile with Point of Control (POC), VAH & VAL 70% Value Area', mount: mountVAP },
  { code: 'MKTP', cat: 'MICRO', title: 'Market Profile (TPO)', desc: 'Institutional Market Profile Value Area & Buy/Sell Delta Nodes', mount: mountVAP },
  { code: 'LIQ', cat: 'CRYPTO', title: 'Liquidation Heatmap & OI Magnet', desc: '10x/20x/50x/100x Leverage Liquidation Clusters & Short Squeeze / Long Cascade Pools', mount: mountLIQ },
  { code: 'OMST', cat: 'DERIV', title: 'Options Most Active & Sweeps', desc: 'Unusual Institutional Options Block & Multi-Exchange Sweep Flow Tape', mount: mountOMST },
  { code: 'GEX', cat: 'DERIV', title: 'Dealer Gamma Exposure (GEX)', desc: 'Dealer Gamma Exposure by Strike, Call/Put Walls & Zero-Gamma Flip Level', mount: mountOMST },

  // Equities & Fundamentals
  { code: 'DES', cat: 'EQUITY', title: 'Security Description', desc: 'Institutional Asset Profile, Snapshot Stats, 52W Range & Filings', mount: mountDES },
  { code: 'FA', cat: 'EQUITY', title: 'Financial Analysis', desc: 'SEC EDGAR XBRL Standardized Income Stmt, Balance Sheet, Cash Flow & Ratios', mount: mountFA },
  { code: 'ANR', cat: 'EQUITY', title: 'Analyst Recommendations', desc: 'Bloomberg Consensus Rating (1-5), 12M Target Price & Institutional Broker Matrix', mount: mountANR },
  { code: 'ERN', cat: 'EQUITY', title: 'Earnings & Estimates', desc: 'Quarterly Consensus EPS Estimates vs Actual Reported Beat/Miss Diagram', mount: mountERN },
  { code: 'EE', cat: 'EQUITY', title: 'Earnings Estimates Workbench', desc: 'Consensus Earnings & Surprise History', mount: mountERN },
  { code: 'SPLC', cat: 'EQUITY', title: 'Supply Chain Analysis', desc: 'Interactive Upstream Suppliers, Downstream Customers & Peer Revenue Flow Diagram', mount: mountSPLC },
  { code: 'HDS', cat: 'EQUITY', title: 'Institutional Holders (13F)', desc: 'Top Institutional Shareholders, 13F Ownership Breakdown & QoQ Flows', mount: mountHDS },
  { code: 'MGMT', cat: 'EQUITY', title: 'Company Management & Board', desc: 'Key Executives, Board Directors, Compensation, Tenure & Governance Score', mount: mountMGMT },
  { code: 'OWN', cat: 'EQUITY', title: 'Equity Ownership Structure', desc: 'Institutional, Sovereign, Insider & Public Float Ownership Diagram', mount: mountHDS },
  { code: 'CF', cat: 'EQUITY', title: 'Company Filings (EDGAR)', desc: 'Official SEC EDGAR 10-K, 10-Q, 8-K, Form 4 & Proxy Filings', mount: mountCF },
  { code: 'FLNG', cat: 'EQUITY', title: 'SEC Filings Archive', desc: 'Direct Links to Official SEC EDGAR Regulatory Filings', mount: mountCF },
  { code: 'DVD', cat: 'EQUITY', title: 'Dividend & Split History', desc: '5-Year Cash Dividend Schedule, TTM Yield & Stock Splits', mount: mountDVD },
  { code: 'SPLT', cat: 'EQUITY', title: 'Stock Splits', desc: 'Historical Corporate Split Ratio Schedule', mount: mountDVD },
  { code: 'RV', cat: 'EQUITY', title: 'Relative Value Peers', desc: 'Sector Peer Group Comparison vs Group Mean', mount: mountRV },
  { code: 'EQS', cat: 'EQUITY', title: 'Equity & Crypto Screener', desc: 'Multi-Factor Market Screener with Momentum & Volume Sorting', mount: mountEQS },
  { code: 'MEMB', cat: 'INDEX', title: 'Index Members & Weights', desc: 'Constituent Weights & Point Impact for S&P 500, Dow 30 & Crypto', mount: mountMEMB },
  { code: 'MA', cat: 'EQUITY', title: 'Mergers & Acquisitions (M&A)', desc: 'Global M&A Deal Monitor, EV/EBITDA Multiples & Merger Arbitrage IRR Spreads', mount: mountMA },
  { code: 'IPO', cat: 'EQUITY', title: 'Equity Offerings & IPO Pipeline', desc: 'Global IPO Syndicate Pipeline, Pre-IPO Unicorns & Secondary Offerings', mount: mountIPO },
  { code: 'EVTS', cat: 'EQUITY', title: 'Corporate Events Calendar', desc: 'Earnings Calls, Investor Days & Corporate Catalyst Schedule', mount: mountIPO },
  { code: 'CACS', cat: 'EQUITY', title: 'Corporate Actions Schedule', desc: 'Dividends, Share Buybacks, Splits & Governance Actions', mount: mountIPO },
  { code: 'ESG', cat: 'EQUITY', title: 'ESG Sustainability Scorecard', desc: 'Environmental, Social & Governance Pillar Scores & Carbon Intensity', mount: mountESG },
  { code: 'GUID', cat: 'EQUITY', title: 'Management Guidance vs Street', desc: 'Corporate Management Guidance Range vs Wall Street Consensus', mount: mountESG },
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
  { code: 'ECFC', cat: 'MACRO', title: 'Economic Forecasts & Recession Prob', desc: 'US & Global 12-Month Recession Probability Model (NY Fed Probit + Sahm Rule) & Consensus Forecasts', mount: mountECFC },
  { code: 'RPROB', cat: 'MACRO', title: 'Recession Probability Monitor', desc: 'Federal Reserve Yield Curve Probit 12M Recession Probability Curve & Country Matrix', mount: mountECFC },
  { code: 'REC', cat: 'MACRO', title: 'US & Global Recession Tracker', desc: '12-Month Recession Probability & Macroeconomic Cycle Regime', mount: mountECFC },
  { code: 'WCDS', cat: 'FIXED INC', title: 'World Sovereign CDS Monitor', desc: '5Y Sovereign Credit Default Swaps Spreads & Implied Default Probability Matrix', mount: mountWCDS },
  { code: 'CDS', cat: 'FIXED INC', title: 'Credit Default Swaps & Default Prob', desc: 'Sovereign 5Y CDS Spreads & Cumulative Default Probabilities', mount: mountWCDS },
  { code: 'BTST', cat: 'QUANT', title: 'Strategy Backtester', desc: 'Quantitative Strategy Backtester (SMA Cross, RSI Reversion, Breakout) & Equity Curve Diagram', mount: mountBTST },
  { code: 'OVDV', cat: 'DERIV', title: 'Volatility Surface & 25Δ Skew', desc: '3D Implied Volatility Surface (10Δ–90Δ × 1W–1Y) & 25Δ Risk Reversal / Butterfly Smile', mount: mountOVDV },
  { code: 'RRG', cat: 'QUANT', title: 'Relative Rotation Graph (RRG)', desc: '4-Quadrant JdK RS-Ratio vs RS-Momentum Sector Rotation Trails (Leading/Weakening/Lagging/Improving)', mount: mountRRG },
  { code: 'SEAG', cat: 'QUANT', title: 'Seasonality Heatmap Matrix', desc: 'Historical Monthly Return Heatmap (Jan–Dec) & Multi-Year Hit Rate', mount: mountSEAG },
  { code: 'DOTS', cat: 'FIXED INC', title: 'FOMC Dot Plot & Central Banks', desc: 'FOMC SEP Participant Dot Plot Distribution & Global Central Bank Policy Matrix', mount: mountDOTS },
  { code: 'FED', cat: 'FIXED INC', title: 'Federal Reserve Policy Desk', desc: 'FOMC Dot Plot, Implied OIS Path & Central Bank Rate Matrix', mount: mountDOTS },
  { code: 'FSTA', cat: 'QUANT', title: 'Factor Style Attribution', desc: 'Barra / Fama-French 6-Factor Style Loadings & Return Attribution', mount: mountFSTA },
  { code: 'TCA', cat: 'EXECUTION', title: 'Transaction Cost Analysis', desc: 'Institutional Implementation Shortfall, VWAP/TWAP Slippage & Fill Quality Audit', mount: mountFSTA },
  { code: 'CRPR', cat: 'FIXED INC', title: 'Credit Rating Profile', desc: 'S&P, Moody\'s, Fitch Credit Ratings, Altman Z-Score & Merton Distance-to-Default', mount: mountCRPR },
  { code: 'RATD', cat: 'FIXED INC', title: 'Credit Rating Scales & Agency', desc: 'Multi-Agency Rating Matrix & Structural Default Probability', mount: mountCRPR },
  { code: 'FIW', cat: 'FIXED INC', title: 'Fixed Income Worksheet', desc: 'Senior Corporate Bond Curve, G-Spread OAS & Modified Duration Worksheet', mount: mountCRPR },

  // Operations, Portfolio, Risk, AI & System
  { code: 'BOT', cat: 'EXECUTION', title: 'Autonomous Futures Execution Desk', desc: 'Live Binance Futures Auto-Trader Telemetry, Active Positions & 5-Layer Signals', mount: mountBOT },
  { code: 'FACT', cat: 'ANALYTICS', title: 'Quantitative Execution X-Ray', desc: 'Full Factor Transparency: 8-Axis Radar, P_Math Waterfall, Layer 1-6 Funnel, 24 Pillars, 532 Factors & FPT Cone', mount: mountFACT },
  { code: 'XRAY', cat: 'ANALYTICS', title: 'Execution Decision X-Ray', desc: 'Transparent Inspection of Quantitative Signals, Microstructure & Risk Gates', mount: mountFACT },
  { code: 'PILLAR', cat: 'ANALYTICS', title: '24/28-Pillar Telemetry Matrix', desc: 'Live Microstructure, Regime, Derivatives, Options & Risk Pillar Matrix', mount: mountFACT },
  { code: 'TRAN', cat: 'RESEARCH', title: 'Committee & Earnings Transcripts', desc: '9-Agent Adversarial Debate Transcripts, 5-Layer Audit Trail, Trade Memory & Corporate Earnings Tone', mount: mountTRAN },
  { code: 'TRSC', cat: 'RESEARCH', title: 'Transcripts Archive', desc: 'Committee Debate Logs & SEC/News Catalyst Transcripts', mount: mountTRAN },
  { code: 'G', cat: 'CHART', title: 'Multi-Chart Studio & PNG Archive', desc: '4-Asset Live Multi-Study Candlestick Wall (EMA20/50 + BB + VPVR), Saved PNG Archive & Pattern Schematics', mount: mountSTUDIO },
  { code: 'SNAP', cat: 'CHART', title: 'Chart PNG Snapshot Archive', desc: 'Archived Institutional Chart & ROE PNG Exports & 4-Chart Wall', mount: mountSTUDIO },
  { code: 'PATT', cat: 'CHART', title: 'Technical Pattern Schematics', desc: 'Live Structure Detector (BOS/FVG/Golden Pocket) & Execution Architecture Diagrams', mount: mountSTUDIO },
  { code: 'TECH', cat: 'CHART', title: 'Multi-Timeframe Technical Matrix', desc: '5-Timeframe (5m/15m/1h/4h/1d) x 6-Indicator Confluence Matrix, Consensus Gauge & Daily Floor Pivots', mount: mountTECH },
  { code: 'MTF', cat: 'CHART', title: 'Multi-Timeframe Signal Scanner', desc: 'Simultaneous 5m–1d RSI, MACD, EMA20/50, SuperTrend, Bollinger & BOS Confluence Rating', mount: mountTECH },
  { code: 'ROE', cat: 'EXECUTION', title: 'Shareable ROE Card Studio', desc: 'HiDPI Institutional ROE & PnL Card Generator (16:9 Desk & 9:16 Story) with Live Sparkline & Native Share', mount: mountROE },
  { code: 'PNL', cat: 'EXECUTION', title: 'Execution ROE & P&L Card Generator', desc: 'Generate & Share Verified Futures ROE Cards from Open Positions or Audited Trade History', mount: mountROE },
  { code: 'BRDT', cat: 'MONITOR', title: 'Market Breadth & Dominance', desc: 'Advancers/Decliners Internals, Dollar-Volume Dominance Share & Cross-Asset Risk-On/Risk-Off Regime', mount: mountBRDT },
  { code: 'DOMI', cat: 'CRYPTO', title: 'Crypto Volume Dominance & Rotation', desc: 'BTC/ETH/Majors/Altcoin Liquidity Share & Cross-Asset Macro Pulse', mount: mountBRDT },
  { code: 'BI', cat: 'RESEARCH', title: 'Bloomberg Intelligence Dossier', desc: 'Institutional Bull/Bear Thesis, Quantitative Snapshot, Catalysts & HTML Research Export', mount: mountBI },
  { code: 'RES', cat: 'RESEARCH', title: 'Institutional Research Hub', desc: 'Bloomberg Intelligence Research Dossier & Printable Report Export', mount: mountBI },
  { code: 'ETF', cat: 'FLOWS', title: 'Spot Crypto & Macro ETF Flows', desc: 'IBIT/FBTC/GBTC/ETHA/SPY/QQQ/TLT/GLD/EIDO Signed Flows, Futures Crowding & SEC Form-4 Insiders', mount: mountETF },
  { code: 'FLOW', cat: 'FLOWS', title: 'Institutional Capital Flows', desc: 'Cross-Asset Spot ETF Flows & Perpetual Short Squeeze Pressure Matrix', mount: mountETF },
  { code: 'INS', cat: 'EQUITY', title: 'SEC Form-4 Insiders & Flows', desc: 'Corporate Insider Filings (Form 4 / 8-K) & Institutional Flow Monitor', mount: mountETF },
  { code: 'SI', cat: 'DERIV', title: 'Short Squeeze Pressure Monitor', desc: 'Perpetual Funding Crowding & Short Squeeze Pressure Matrix', mount: mountETF },
  { code: 'FIN', cat: 'CAPITAL', title: 'Personal Capital Manager (Warren Buffett)', desc: 'Warren Buffett Pay-Yourself-First Automatic Allocation (40/60), Daily Ceiling, 14D Cashflow & Compounding Forecast', mount: mountFIN },
  { code: 'BUFFETT', cat: 'CAPITAL', title: 'Warren Buffett Auto-Allocation Engine', desc: 'Automatic Fixed Monthly Income Split (25% Invest, 15% Reserve, 45% Food, 15% Transport) & Compounding Projection', mount: mountFIN },
  { code: 'BUDGET', cat: 'CAPITAL', title: 'Operating Budget & Envelopes', desc: 'Daily Operating Ceiling, Monthly Envelopes & Capital Reserves', mount: mountFIN },
  { code: 'CASH', cat: 'CAPITAL', title: 'Personal Cashflow Ledger', desc: 'Daily Cashflow Discipline Monitor, Ledger & CSV Export', mount: mountFIN },
  { code: 'WDGT', cat: 'SYSTEM', title: 'Bloomberg Live Widget Studio', desc: 'Interactive Live Widgets, Always-on-Top Floating Mini-Terminal & Android Home Screen Widget Setup', mount: mountWDGT },
  { code: 'WIDGET', cat: 'SYSTEM', title: 'Floating Mini-Terminal Widgets', desc: 'Live Market, Execution & Capital Widgets for Desktop and Android Home Screen', mount: mountWDGT },
  { code: 'BTCA', cat: 'EXECUTION', title: 'Execution TCA & Quant Health', desc: 'Maker GTX Fill Share, Arrival Slippage, +1m/+5m Markouts, Risk Breaker & ADWIN Drift', mount: mountBTCA },
  { code: 'TCA', cat: 'EXECUTION', title: 'Transaction Cost Analysis (TCA)', desc: 'Execution Quality, VWAP Impact, Fee Drag & Strategy Bandit Audit', mount: mountBTCA },
  { code: 'PORT', cat: 'PORTFOLIO', title: 'Portfolio & Risk Analytics', desc: 'Institutional Multi-Asset Holdings Valuation, Weight Attribution & DMA Execution', mount: mountPORT },
  { code: 'EMSX', cat: 'EXECUTION', title: 'Execution Management System (EMSX)', desc: 'Direct Market Access (DMA) Multi-Asset Order Routing & Execution Blotter', mount: mountEMSX },
  { code: 'BLOT', cat: 'EXECUTION', title: 'Execution Trade Blotter', desc: 'Audited Multi-Asset Order & Trade History Blotter', mount: mountEMSX },
  { code: 'ORD', cat: 'EXECUTION', title: 'Order Entry Ticket', desc: 'Institutional Buy/Sell Order Entry & Settlement', mount: mountEMSX },
  { code: 'MARS', cat: 'RISK', title: 'Multi-Asset Risk System', desc: 'Parametric & Historical VaR (95%/99%), CVaR, Max DD & Stress Tests', mount: mountMARS },
  { code: 'VAR', cat: 'RISK', title: 'Value at Risk', desc: 'Daily Value-at-Risk, Expected Shortfall & Leverage Shock Scenarios', mount: mountMARS },
  { code: 'RISK', cat: 'RISK', title: 'Risk Analytics', desc: 'Portfolio & Single-Security Tail Risk Workbench', mount: mountMARS },
  { code: 'ALRT', cat: 'SYSTEM', title: 'Price Alert Manager', desc: 'Real-Time WebSocket Price Alerts with Audio & Visual Trigger', mount: mountALRT },
  { code: 'MSG', cat: 'B-MAIL', title: 'Bloomberg Mail (@bloomberg.net)', desc: 'Institutional Terminal Email Inbox, Compose (MSG1), Sent & Auto-Email to fadhilsyafiq90@gmail.com', mount: (b, c) => mountMSG(b, c, { initialTab: 'INBOX' }) },
  { code: 'BMAIL', cat: 'B-MAIL', title: 'Bloomberg Mail Client', desc: 'Institutional @bloomberg.net Email Gateway & Auto-Relay to fadhilsyafiq90@gmail.com', mount: (b, c) => mountMSG(b, c, { initialTab: 'INBOX' }) },
  { code: 'GMAIL', cat: 'B-MAIL', title: 'Auto-Email Alerts (fadhilsyafiq90@gmail.com)', desc: 'Automatic Email Dispatcher to fadhilsyafiq90@gmail.com on Hot News & Futures Open/Close', mount: (b, c) => mountMSG(b, c, { initialTab: 'ALERTS' }) },
  { code: 'MSG1', cat: 'B-MAIL', title: 'Compose Bloomberg Mail', desc: 'Compose & Dispatch Institutional @bloomberg.net Email with Terminal Attachments', mount: (b, c) => mountMSG(b, c, { initialTab: 'COMPOSE' }) },
  { code: 'SPDL', cat: 'B-MAIL', title: 'Bloomberg Speed Dial Directory', desc: 'Institutional Counterparty Directory (Goldman, JPM, MS, BlackRock, EMSX)', mount: (b, c) => mountMSG(b, c, { initialTab: 'SPDL' }) },
  { code: 'PEOP', cat: 'B-MAIL', title: 'People & Desk Directory', desc: 'Global Institutional Counterparty & Analyst Directory', mount: (b, c) => mountMSG(b, c, { initialTab: 'SPDL' }) },
  { code: 'IB', cat: 'SYSTEM', title: 'Instant Bloomberg & AI', desc: 'Desk Chat + Ask Bloomberg (ASKB) AI Quant Analyst', mount: mountIB },
  { code: 'ASKB', cat: 'AI ENGINE', title: 'Ask Bloomberg Quant AI', desc: 'Natural Language Quantitative Market Query Engine', mount: mountIB },
  { code: 'SECF', cat: 'SYSTEM', title: 'Security Finder', desc: 'Global Ticker Search Across Crypto, Equities, Indices, FX, Commodities', mount: mountSECF },
  { code: 'FLDS', cat: 'SYSTEM', title: 'Field Mnemonic Finder', desc: 'Bloomberg Data Field Dictionary with Live Security Values', mount: mountFLDS },
  { code: 'BLP', cat: 'SYSTEM', title: 'Launchpad Workspace Manager', desc: 'Preset Multi-Panel Bloomberg Workspaces & Custom Layout Saver', mount: (b, c) => mountBLP(b, c, { workspaces: WORKSPACES, onLaunch: (k, list) => { panes = JSON.parse(JSON.stringify(list)); savePanes(); for (let i = 0; i < 4; i++) mountSlot(i); setActiveSlot(0); $('#msg').textContent = `WORKSPACE: ${k}`; } }) },
  { code: 'HELP', cat: 'SYSTEM', title: 'Terminal Manual & Help', desc: 'Complete Directory of All Function Codes, Sector Keys & Shortcuts', mount: (b, c) => mountHELP(b, c, { catalog: CATALOG }) }
];

const FN_MAP = new Map(CATALOG.map(x => [x.code, x]));

const WORKSPACES = {
  'DEFAULT DESK': [
    { symbol: 'BTCUSDT', fn: 'GP' },
    { symbol: 'BTCUSDT', fn: 'TOP' },
    { symbol: 'SPCX', fn: 'PORT' },
    { symbol: 'SPCX', fn: 'EMSX' }
  ],
  'GLOBAL NEWS & MACRO': [
    { symbol: 'BTCUSDT', fn: 'TOP' },
    { symbol: 'BTCUSDT', fn: 'N' },
    { symbol: '^TNX', fn: 'YCRV' },
    { symbol: '^GSPC', fn: 'WEI' }
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
  'AUTONOMOUS FUTURES DESK': [
    { symbol: 'ETHUSDT.P', fn: 'BOT' },
    { symbol: 'ETHUSDT', fn: 'GIP' },
    { symbol: 'ETHUSDT', fn: 'TRADES' },
    { symbol: 'ETHUSDT', fn: 'FNG' }
  ],
  'EXECUTION X-RAY & TRANSCRIPTS': [
    { symbol: 'BTCUSDT', fn: 'FACT' },
    { symbol: 'BTCUSDT', fn: 'TRAN' },
    { symbol: 'BTCUSDT', fn: 'GP' },
    { symbol: 'BTCUSDT.P', fn: 'BOT' }
  ],
  'BLOOMBERG INTELLIGENCE': [
    { symbol: 'BTCUSDT', fn: 'BI' },
    { symbol: 'BTCUSDT', fn: 'ETF' },
    { symbol: 'BTCUSDT', fn: 'G' },
    { symbol: 'BTCUSDT', fn: 'TOP' }
  ],
  'QUANT CHARTING & ROE': [
    { symbol: 'BTCUSDT', fn: 'GP' },
    { symbol: 'BTCUSDT', fn: 'TECH' },
    { symbol: 'BTCUSDT', fn: 'ROE' },
    { symbol: 'BTCUSDT', fn: 'BRDT' }
  ],
  'CAPITAL MANAGEMENT (BUFFETT)': [
    { symbol: 'BTCUSDT', fn: 'FIN' },
    { symbol: 'BTCUSDT.P', fn: 'BOT' },
    { symbol: 'BTCUSDT', fn: 'WDGT' },
    { symbol: 'BTCUSDT', fn: 'TOP' }
  ],
  'COMMODITIES & GEOPOLITICAL': [
    { symbol: 'CL=F', fn: 'BMAP' },
    { symbol: 'CL=F', fn: 'FUT' },
    { symbol: 'USDIDR=X', fn: 'FXFC' },
    { symbol: 'GC=F', fn: 'GP' }
  ]
};

const slots = [...document.querySelectorAll('.slot')];
let activeSlot = 0;
let panes = LS.get('bbg_active_panes_v4', WORKSPACES['DEFAULT DESK']);
if (!Array.isArray(panes) || panes.length !== 4) panes = JSON.parse(JSON.stringify(WORKSPACES['DEFAULT DESK']));
// Deep-link layout: /?w=CL=F:BMAP,BTCUSDT:TOP,SPCX:PORT,NVDA:SPLC  (also ?win=1|2|4)
{
  const w = urlParams.get('w');
  if (w) {
    const parts = w.split(',').map(x => x.trim()).filter(Boolean).slice(0, 4);
    parts.forEach((x, i) => {
      const k = x.lastIndexOf(':');
      const sym = (k > 0 ? x.slice(0, k) : 'BTCUSDT').toUpperCase();
      const fn = (k > 0 ? x.slice(k + 1) : x).toUpperCase();
      if (FN_MAP.has(fn)) panes[i] = { symbol: sym, fn };
    });
  }
}

const cleanups = [null, null, null, null];

function savePanes() { LS.set('bbg_active_panes_v4', panes); }

function setActiveSlot(idx) {
  activeSlot = idx;
  slots.forEach((s, i) => s.classList.toggle('active', i === idx));
  const p = panes[activeSlot];
  $('#cmdctx').textContent = `[${activeSlot + 1}-BLOOMBERG: ${p.symbol} ${p.fn}]`;
  renderMobNav();
}

function renderMobNav() {
  const nav = $('#mobnav');
  if (!nav) return;
  const grid = $('#grid');
  const isSingle = grid.classList.contains('mode-1');
  nav.textContent = '';
  panes.forEach((p, i) => {
    nav.append(h('button', {
      class: isSingle && i === activeSlot ? 'on' : '',
      text: `${i + 1}:${p.fn}`,
      title: `Switch to ${i + 1}-BLOOMBERG (${p.symbol} ${p.fn})`,
      onclick: () => {
        setActiveSlot(i);
        if (window.innerWidth <= 900) {
          setWinMode(1);
          window.scrollTo({ top: 0, behavior: 'auto' });
        }
      }
    }));
  });
  nav.append(h('button', {
    class: !isSingle ? 'on' : '',
    text: window.innerWidth <= 900 ? 'STACK ALL' : '4-QUAD',
    onclick: () => setWinMode(4)
  }));
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
      slot.classList.toggle('maxed');
      window.dispatchEvent(new Event('resize'));
    }
  });

  const hdr = h('div', {
    class: 'ph',
    draggable: 'true',
    onclick: () => setActiveSlot(idx)
  },
    h('span', { class: 'fn', text: `${idx + 1}-BLOOMBERG:${fnDef.code}` }),
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
  const actBar = h('div', { class: 'psub-act' },
    h('span', { class: 'am sym', text: `${state.symbol}:` }),
    ...['GP', 'TECH', 'ROE', 'DES', 'FACT', 'BRDT', 'BOT'].map(code => h('button', {
      style: 'font-size:10px;padding:0 5px',
      text: code,
      onclick: ev => { ev.stopPropagation(); actBar.classList.remove('open'); setActiveSlot(idx); executeCommand(`${state.symbol} ${code}`); }
    })),
    h('button', {
      style: 'font-size:10px;padding:0 5px;color:var(--amber)',
      text: 'MAXIMIZE',
      onclick: ev => { ev.stopPropagation(); actBar.classList.remove('open'); slot.classList.toggle('maxed'); window.dispatchEvent(new Event('resize')); }
    })
  );

  const exportPanelData = () => {
    const tbl = body.querySelector('table');
    if (tbl) {
      const csvRows = [...tbl.querySelectorAll('tr')].map(tr =>
        [...tr.querySelectorAll('th,td')].map(td => `"${String(td.textContent || '').replace(/"/g, '""').trim()}"`).join(',')
      );
      if (csvRows.length) {
        const blob = new Blob([csvRows.join('\n')], { type: 'text/csv;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `Bloomberg_${state.symbol.replace(/[^A-Z0-9_-]/gi, '_')}_${fnDef.code}.csv`;
        a.click();
        setTimeout(() => URL.revokeObjectURL(url), 250);
        $('#msg').textContent = `EXPORTED CSV: ${state.symbol} ${fnDef.code}`;
        return;
      }
    }
    const cv = body.querySelector('canvas');
    if (cv && cv.width > 0 && cv.height > 0) {
      try {
        const a = document.createElement('a');
        a.href = cv.toDataURL('image/png');
        a.download = `Bloomberg_${state.symbol.replace(/[^A-Z0-9_-]/gi, '_')}_${fnDef.code}.png`;
        a.click();
        $('#msg').textContent = `EXPORTED PNG: ${state.symbol} ${fnDef.code}`;
        return;
      } catch {}
    }
    window.print();
  };

  const subHdr = h('div', { class: 'psub' },
    h('span', { class: 'psub-menu' },
      h('button', { class: 'pm', text: '90) Actions', title: 'Quick Bloomberg Function Actions', onclick: ev => { ev.stopPropagation(); actBar.classList.toggle('open'); } }),
      h('button', { class: 'pm', text: '91) Edit', title: 'Focus & Edit Security Ticker', onclick: ev => { ev.stopPropagation(); secInput.focus(); secInput.select(); } }),
      h('button', { class: 'pm', text: '92) Export', title: 'Export Table CSV / Chart PNG', onclick: ev => { ev.stopPropagation(); exportPanelData(); } }),
      h('button', { class: 'pm', text: '99) Help', title: 'Open Terminal Manual (HELP <GO>)', onclick: ev => { ev.stopPropagation(); setActiveSlot(idx); executeCommand('HELP'); } }),
      h('span', { style: 'opacity:.85;margin-left:4px', text: `|   ${state.symbol} <${fnDef.cat}> ${fnDef.code}` })
    ),
    h('span', { class: 'pr', text: `BLOOMBERG PROFESSIONAL • PAGE 1/1` })
  );

  const panelEl = h('div', { class: 'panel' }, hdr, subHdr, actBar, body);
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
        let busy = false;
        const iv = setInterval(async () => {
          if ((typeof document !== 'undefined' && document.hidden) || busy) return;
          busy = true;
          try {
            const r = await get('news', { limit: 20 }, 15000);
            if (r.ok && r.data) cb(r.data);
          } finally {
            busy = false;
          }
        }, 30000);
        cbs.push(() => clearInterval(iv));
        return () => clearInterval(iv);
      }
      return () => {};
    },
    async fetchJson(path) {
      const r = await apiFetch(path, { cache: 'no-store' }, 12000);
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
    BTC: 'BTCUSDT', 'BTC-USD': 'BTCUSDT', ETH: 'ETHUSDT', 'ETH-USD': 'ETHUSDT',
    SOL: 'SOLUSDT', 'SOL-USD': 'SOLUSDT', BNB: 'BNBUSDT', XRP: 'XRPUSDT', DOGE: 'DOGEUSDT',
    SPACEX: 'SPACEX', SPCX: 'SPCX', OPENAI: 'OPENAI', ANTHROPIC: 'ANTHROPIC', STRIPE: 'STRIPE',
    BBCA: 'BBCA.JK', BBRI: 'BBRI.JK', BMRI: 'BMRI.JK', BBNI: 'BBNI.JK', TLKM: 'TLKM.JK',
    ASII: 'ASII.JK', GOTO: 'GOTO.JK', BREN: 'BREN.JK', AMMN: 'AMMN.JK', ADRO: 'ADRO.JK', ANTM: 'ANTM.JK', UNVR: 'UNVR.JK',
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
    acBox.style.display = 'none';
    cmdInput.value = '';
    if (val) executeCommand(val);
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

// Authentic Bloomberg Yellow Market Sector Keys + Function F-Keys Bar
const FKEYS = [
  ['F2', 'GOVT', '^TNX YCRV', true],
  ['F3', 'CORP', '^TNX CRPR', true],
  ['F4', 'CMDTY', 'CL=F BMAP', true],
  ['F8', 'EQUITY', 'AAPL DES', true],
  ['F10', 'CURNCY', 'USDIDR=X FXC', true],
  ['F11', 'CRYP', 'BTCUSDT CRYP', true],
  ['F1', 'HELP', 'HELP', false],
  ['TOP', 'NEWS', 'TOP', false],
  ['BOT', 'EXEC', 'BTCUSDT.P BOT', false],
  ['ROE', 'PNL', 'BTCUSDT ROE', false],
  ['TECH', 'MTF', 'BTCUSDT TECH', false],
  ['BRDT', 'BREADTH', 'BTCUSDT BRDT', false],
  ['FACT', 'X-RAY', 'BTCUSDT FACT', false],
  ['G', 'STUDIO', 'BTCUSDT G', false],
  ['BI', 'RESEARCH', 'BTCUSDT BI', false],
  ['FIN', 'CAPITAL', 'BTCUSDT FIN', false],
  ['MSG', 'B-MAIL', 'MSG', false]
];
const fkBar = $('#fkeys');
for (const [fk, lbl, cmd, isYellow] of FKEYS) {
  fkBar.append(h('button', {
    class: isYellow ? 'ykey' : 'fkey',
    title: `${fk}: ${cmd}`,
    onclick: () => executeCommand(cmd)
  }, h('b', { text: fk + ' ' }), lbl));
}

// Global Bloomberg Hardware Keyboard Shortcuts (F1-F11 Yellow Keys, Ctrl+K, ESC Modals)
const HW_FKEY_MAP = {
  F1: 'HELP',
  F2: '^TNX YCRV',
  F3: '^TNX CRPR',
  F4: 'CL=F BMAP',
  F8: 'AAPL DES',
  F10: 'USDIDR=X FXC',
  F11: 'BTCUSDT CRYP'
};
window.addEventListener('keydown', e => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
    e.preventDefault();
    cmdInput.focus();
    cmdInput.select();
  } else if (e.key === 'Escape') {
    for (const id of ['bbgRoeModal', 'pushCenterModal', 'installGuideModal']) {
      const m = document.getElementById(id);
      if (m) m.remove();
    }
  } else if (HW_FKEY_MAP[e.key] && !e.ctrlKey && !e.altKey && !e.metaKey) {
    e.preventDefault();
    executeCommand(HW_FKEY_MAP[e.key]);
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

// Workspace selector & Window Layout Modes (4-WIN, 2-WIN, 1-WIN)
const gridEl = $('#grid');
const modeBtns = [...document.querySelectorAll('#winmodes button[data-mode]')];
function setWinMode(m) {
  gridEl.classList.remove('mode-1', 'mode-2', 'mode-4');
  gridEl.classList.add('mode-' + m);
  modeBtns.forEach(b => b.classList.toggle('on', b.dataset.mode === String(m)));
  renderMobNav();
  window.dispatchEvent(new Event('resize'));
  $('#msg').textContent = `DISPLAY MODE: ${m}-WINDOW BLOOMBERG PROFESSIONAL`;
}
modeBtns.forEach(b => b.addEventListener('click', () => setWinMode(b.dataset.mode)));
const btnCancel = $('#btnCancel');
if (btnCancel) {
  btnCancel.addEventListener('click', () => {
    cmdInput.value = '';
    acBox.style.display = 'none';
    $('#msg').textContent = 'CANCELLED — READY FOR COMMAND';
  });
}

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

let healthInFlight = false;
async function pollHealth(force = false) {
  if (!force && typeof document !== 'undefined' && document.hidden) return;
  if (healthInFlight) return;
  healthInFlight = true;
  try {
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
  } finally {
    healthInFlight = false;
  }
}
pollHealth(true);
setInterval(() => pollHealth(false), 20000);

function updateClocks(force = false) {
  if (!force && typeof document !== 'undefined' && document.hidden) return;
  const now = new Date();
  const fmt = tz => now.toLocaleTimeString('en-GB', { timeZone: tz, hour12: false });
  const el = $('#clocks');
  if (el) {
    el.innerHTML = `<b>WIB</b> ${fmt('Asia/Jakarta')} <b>UTC</b> ${fmt('UTC')} <b>NY</b> ${fmt('America/New_York')} <b>LDN</b> ${fmt('Europe/London')}`;
  }
}
updateClocks(true);
setInterval(() => updateClocks(false), 1000);

// Global Live Market Ticker Strip (#mktstrip) — Persistent Launchpad Benchmark Tape
(function initGlobalMarketStrip() {
  const strip = $('#mktstrip');
  if (!strip) return;
  const BENCHMARKS = [
    { sym: 'BTCUSDT', lbl: 'BTC', ws: true },
    { sym: 'ETHUSDT', lbl: 'ETH', ws: true },
    { sym: 'SOLUSDT', lbl: 'SOL', ws: true },
    { sym: '^GSPC', lbl: 'SPX', ws: false },
    { sym: '^IXIC', lbl: 'NDX', ws: false },
    { sym: 'GC=F', lbl: 'GOLD', ws: false },
    { sym: 'CL=F', lbl: 'WTI', ws: false },
    { sym: '^TNX', lbl: 'US10Y', ws: false },
    { sym: 'USDIDR=X', lbl: 'USD/IDR', ws: false }
  ];

  const cells = new Map();
  strip.textContent = '';
  for (const b of BENCHMARKS) {
    const pxEl = h('span', { class: 'ms-px', text: '—' });
    const chgEl = h('span', { class: 'ms-chg mu', text: '' });
    const item = h('div', {
      class: 'ms-item',
      title: `Open ${b.sym} GP <GO>`,
      onclick: () => executeCommand(`${b.sym} GP`)
    },
      h('span', { class: 'ms-sym', text: b.lbl }),
      pxEl,
      chgEl
    );
    strip.append(item);
    cells.set(b.sym, { item, pxEl, chgEl, lastPx: 0 });
  }

  const paintCell = (sym, price, chgPct) => {
    const c = cells.get(sym);
    const p = Number(price);
    if (!c || !Number.isFinite(p) || p <= 0) return;
    if (c.lastPx > 0 && p !== c.lastPx) {
      const fl = p > c.lastPx ? 'fl-up' : 'fl-dn';
      c.item.classList.remove('fl-up', 'fl-dn');
      c.item.classList.add(fl);
      setTimeout(() => c.item.classList.remove(fl), 360);
    }
    c.lastPx = p;
    c.pxEl.textContent = sym === 'USDIDR=X' ? Math.round(p).toLocaleString('id-ID') : fmtPx(p);
    if (Number.isFinite(Number(chgPct))) {
      const pct = Number(chgPct);
      c.chgEl.className = 'ms-chg ' + dirCls(pct);
      c.chgEl.textContent = fmtPct(pct);
    }
  };

  let stripBusy = false;
  const pollStrip = async (force = false) => {
    if (!force && typeof document !== 'undefined' && document.hidden) return;
    if (stripBusy) return;
    stripBusy = true;
    try {
      const env = await get('quote', { symbols: BENCHMARKS.map(b => b.sym).join(',') }, 8000);
      if (env && env.ok && Array.isArray(env.data)) {
        for (const q of env.data) {
          if (q && q.symbol && q.price) paintCell(q.symbol, q.price, q.chgPct);
        }
      }
    } finally {
      stripBusy = false;
    }
  };

  for (const b of BENCHMARKS) {
    if (b.ws) {
      hub.sub(`ticker:${b.sym}`, tk => {
        if (tk && tk.price) paintCell(b.sym, tk.price, tk.chgPct);
      });
    }
  }
  pollStrip(true);
  setInterval(() => pollStrip(false), 30000);
})();

if (typeof document !== 'undefined') {
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) {
      updateClocks(true);
      pollHealth(true);
    }
  });
}

// Token Login Modal (Decision 3.B fail-closed remote access)
const authModal = $('#authModal');
const authForm = $('#authModalForm');
const authInput = $('#authTokenInput');
const authErr = $('#authModalErr');
const authSubmit = $('#authSubmitBtn');
let authVerifiedOnce = false;

function showAuthModal(reason) {
  if (!authModal) return;
  if (authModal.style.display === 'flex') return;
  authModal.style.display = 'flex';
  if (authErr) authErr.textContent = reason && reason !== 'HTTP 401' ? String(reason) : 'Authentication required for protected feeds and actions.';
  if (authInput) setTimeout(() => authInput.focus(), 20);
}

function hideAuthModal() {
  if (!authModal) return;
  authModal.style.display = 'none';
  if (authErr) authErr.textContent = '';
}

setAuthRequiredHandler(reason => {
  if (net.adapter) return;
  showAuthModal(reason);
});

if (authForm) {
  authForm.addEventListener('submit', async ev => {
    ev.preventDefault();
    const tok = (authInput ? authInput.value : '').trim();
    if (!tok) {
      if (authErr) authErr.textContent = 'Please enter DASH_TOKEN.';
      return;
    }
    if (authSubmit) authSubmit.disabled = true;
    if (authErr) authErr.textContent = 'Verifying token...';
    try {
      const res = await fetch('/api/auth/verify', {
        method: 'POST',
        cache: 'no-store',
        headers: { 'Content-Type': 'application/json', 'X-Dash-Token': tok },
        body: JSON.stringify({ token: tok }),
      });
      if (!res.ok) {
        if (authErr) authErr.textContent = res.status === 429 ? 'Rate limited. Wait a moment and retry.' : 'Invalid token (HTTP ' + res.status + ').';
        return;
      }
      setDashToken(tok);
      if (authInput) authInput.value = '';
      hideAuthModal();
      authVerifiedOnce = true;
      hub.reconnect();
      pollHealth(true);
      for (let i = 0; i < 4; i++) mountSlot(i);
      const msgEl = $('#msg');
      if (msgEl) msgEl.textContent = 'AUTHENTICATED';
    } catch {
      if (authErr) authErr.textContent = 'Network error verifying token.';
    } finally {
      if (authSubmit) authSubmit.disabled = false;
    }
  });
}

// Mount all 4 quadrants
for (let i = 0; i < 4; i++) mountSlot(i);
setActiveSlot(0);
const winParam = urlParams.get('win');
if (winParam === '1' || winParam === '2' || winParam === '4') setWinMode(winParam);
$('#msg').textContent = `READY (${CATALOG.length} FUNCTIONS LOADED)`;
if (!net.adapter && hub.state === 'AUTH_REQUIRED' && !authVerifiedOnce) {
  showAuthModal('Enter DASH_TOKEN to unlock terminal feeds.');
}

// =====================================================================
// BLOOMBERG TERMINAL PWA INSTALLER, WIDGET LAUNCHER & MULTI-CHANNEL PUSH
// =====================================================================
let swRegistration = null;
let deferredInstallPrompt = window.__bbgDeferredInstall || null;

function urlBase64ToUint8Array(base64String) {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
  const rawData = atob(base64);
  const out = new Uint8Array(rawData.length);
  for (let i = 0; i < rawData.length; ++i) out[i] = rawData.charCodeAt(i);
  return out;
}

function playAlertChime() {
  try {
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtx) return;
    const ctxA = new AudioCtx();
    const osc = ctxA.createOscillator();
    const gain = ctxA.createGain();
    osc.type = 'sine';
    osc.frequency.setValueAtTime(880, ctxA.currentTime);
    osc.frequency.exponentialRampToValueAtTime(1174.66, ctxA.currentTime + 0.12);
    gain.gain.setValueAtTime(0.06, ctxA.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctxA.currentTime + 0.28);
    osc.connect(gain);
    gain.connect(ctxA.destination);
    osc.start();
    osc.stop(ctxA.currentTime + 0.29);
    setTimeout(() => { try { ctxA.close(); } catch {} }, 400);
  } catch {}
}

function showBloombergToast(payload = {}) {
  const rack = $('#toastRack');
  if (!rack) return;
  const evType = String(payload.eventType || 'ALERT').toUpperCase();
  const cls = /LIMIT|BOROS|ERR|BREAKER|SL|VETO/i.test(evType) ? 'err' : /WARN|NEWS/i.test(evType) ? 'warn' : '';
  const toast = h('div', {
    class: 'bbg-toast ' + cls,
    onclick: () => {
      toast.remove();
      if (payload.url && typeof payload.url === 'string') {
        try {
          const u = new URL(payload.url, location.origin);
          const w = u.searchParams.get('w');
          if (w) {
            const first = w.split(',')[0] || '';
            const k = first.lastIndexOf(':');
            if (k > 0) executeCommand(`${first.slice(0, k)} ${first.slice(k + 1)}`);
            return;
          }
        } catch {}
      }
      if (payload.symbol === 'FIN') executeCommand('BTCUSDT FIN');
      else if (payload.symbol) executeCommand(`${payload.symbol} BOT`);
    }
  },
    h('div', { class: 't-hd' },
      h('span', { text: payload.title || 'BLOOMBERG TERMINAL // ALERT' }),
      h('span', { text: fmtTime(payload.ts || Date.now()) })
    ),
    h('div', { class: 't-bd', text: payload.body || '' })
  );
  rack.append(toast);
  while (rack.children.length > 4) rack.firstElementChild.remove();
  setTimeout(() => { try { toast.remove(); } catch {} }, 10000);
}

async function triggerOsNotification(payload = {}) {
  if (typeof Notification === 'undefined' || Notification.permission !== 'granted') return false;
  try {
    const reg = swRegistration || (navigator.serviceWorker && await navigator.serviceWorker.ready.catch(() => null));
    if (reg && reg.active) {
      reg.active.postMessage({ type: 'SHOW_NOTIFICATION', payload });
      return true;
    }
    if (reg && typeof reg.showNotification === 'function') {
      await reg.showNotification(payload.title || 'BLOOMBERG TERMINAL', {
        body: payload.body || '',
        icon: '/icons/icon-192.png',
        badge: '/icons/favicon-64.png',
        tag: payload.tag || ('bloomberg-' + Date.now())
      });
      return true;
    }
    new Notification(payload.title || 'BLOOMBERG TERMINAL', {
      body: payload.body || '',
      icon: '/icons/icon-192.png'
    });
    return true;
  } catch {
    return false;
  }
}

hub.onPushAlert = (payload) => {
  if (!payload || typeof payload !== 'object') return;
  playAlertChime();
  showBloombergToast(payload);
  triggerOsNotification(payload);
};

// Immediate Service Worker sync (picks up early <head> registration so Chrome never misses install criteria)
if ('serviceWorker' in navigator) {
  Promise.resolve(window.__bbgSwPromise || navigator.serviceWorker.register('/sw.js', { scope: '/' }))
    .then(reg => { if (reg) swRegistration = reg; })
    .catch(() => {});
}

// Header Widget Button (#btnWidget)
const btnWidget = $('#btnWidget');
if (btnWidget) {
  btnWidget.addEventListener('click', (ev) => {
    if (ev.shiftKey) {
      window.open('/widget?mode=all', 'BloombergTerminalWidget', 'width=430,height=520,menubar=no,toolbar=no,location=no,status=no');
    } else {
      executeCommand('BTCUSDT WDGT');
    }
  });
}

// Native Install App Button (#btnInstallApp)
const btnInstall = $('#btnInstallApp');
const isStandalone = () => (window.matchMedia && window.matchMedia('(display-mode: standalone)').matches) || window.navigator.standalone === true;

function syncInstallBtn() {
  if (!btnInstall) return;
  if (isStandalone()) {
    btnInstall.textContent = 'APP ACTIVE';
    btnInstall.style.background = '#102418';
    btnInstall.style.color = '#00d26a';
    btnInstall.style.borderColor = '#00d26a';
    btnInstall.title = 'Bloomberg Terminal running in Native Standalone Mode';
  } else if (deferredInstallPrompt) {
    btnInstall.textContent = 'INSTALL APP';
    btnInstall.style.background = '#00d26a';
    btnInstall.style.color = '#000';
    btnInstall.style.borderColor = '#00d26a';
    btnInstall.title = 'Native Android/Desktop Install Ready — Click to Install Bloomberg Terminal';
  }
}
syncInstallBtn();

window.addEventListener('bbg-install-ready', () => {
  deferredInstallPrompt = window.__bbgDeferredInstall || deferredInstallPrompt;
  syncInstallBtn();
});
window.addEventListener('beforeinstallprompt', (e) => {
  e.preventDefault();
  deferredInstallPrompt = e;
  window.__bbgDeferredInstall = e;
  syncInstallBtn();
});

window.addEventListener('appinstalled', () => {
  deferredInstallPrompt = null;
  window.__bbgDeferredInstall = null;
  syncInstallBtn();
  showBloombergToast({
    title: 'BLOOMBERG TERMINAL // APPLICATION INSTALLED',
    body: 'Bloomberg Terminal has been added to your device and is ready for standalone fullscreen launch.',
    eventType: 'PWA_INSTALLED'
  });
});

async function showInstallGuideModal() {
  const existing = $('#pwaInstallModal');
  if (existing) existing.remove();
  const isSecure = window.isSecureContext || location.protocol === 'https:' || location.hostname === 'localhost' || location.hostname === '127.0.0.1';
  const ua = navigator.userAgent || '';
  const isInAppBrowser = /Telegram|WhatsApp|FBAN|FBAV|Instagram|Line\/|wv\)/i.test(ua);
  const swReady = Boolean(swRegistration && (swRegistration.active || swRegistration.installing || swRegistration.waiting)) || Boolean(navigator.serviceWorker && navigator.serviceWorker.controller);
  let manifestOk = false;
  try {
    const mr = await fetch('/manifest.webmanifest', { cache: 'no-store' });
    manifestOk = mr.ok;
  } catch {}

  const ov = h('div', {
    id: 'pwaInstallModal',
    style: 'position:fixed;inset:0;z-index:99998;background:rgba(0,0,0,0.88);display:flex;align-items:center;justify-content:center;padding:16px',
    onclick: ev => { if (ev.target === ov) ov.remove(); }
  },
    h('div', { style: 'width:510px;max-width:95vw;background:#0a0d12;border:1px solid #ff6600;padding:16px 18px;color:#e6edf3;line-height:1.55' },
      h('div', { style: 'color:#ff6600;font-weight:700;font-size:12.5px;border-bottom:1px solid #262b33;padding-bottom:8px;margin-bottom:10px;letter-spacing:0.6px', text: 'BLOOMBERG TERMINAL // ANDROID & DESKTOP INSTALLATION DIAGNOSTICS' }),
      h('div', { class: 'xgrid2', style: 'margin-bottom:10px' },
        h('div', { class: 'xstat' }, h('div', { class: 'xl', text: 'HTTPS / SECURE CONTEXT' }), h('div', { class: 'xv', style: `font-size:11.5px;color:${isSecure ? '#00d26a' : '#ff453a'}`, text: isSecure ? 'PASS (HTTPS)' : 'FAIL (HTTP)' })),
        h('div', { class: 'xstat' }, h('div', { class: 'xl', text: 'SERVICE WORKER' }), h('div', { class: 'xv', style: `font-size:11.5px;color:${swReady ? '#00d26a' : '#ffb000'}`, text: swReady ? 'ACTIVE' : 'INITIALIZING (RELOAD)' })),
        h('div', { class: 'xstat' }, h('div', { class: 'xl', text: 'MANIFEST.WEBMANIFEST' }), h('div', { class: 'xv', style: `font-size:11.5px;color:${manifestOk ? '#00d26a' : '#ff453a'}`, text: manifestOk ? 'VALID' : 'UNREACHABLE' })),
        h('div', { class: 'xstat' }, h('div', { class: 'xl', text: 'BROWSER ENVIRONMENT' }), h('div', { class: 'xv', style: `font-size:11.5px;color:${isInAppBrowser ? '#ff453a' : '#00d26a'}`, text: isInAppBrowser ? 'IN-APP WEBVIEW (OPEN IN CHROME)' : 'STANDARD BROWSER' }))
      ),
      h('div', { style: 'font-size:11px;margin-bottom:10px' },
        isInAppBrowser ? h('div', { style: 'margin-bottom:7px;padding:7px;background:#240c0a;border:1px solid #ff453a;color:#ffd2cf', text: 'DETECTED IN-APP BROWSER (Telegram/WhatsApp/WebView): Browser bawaan aplikasi chat TIDAK bisa install PWA. Tap menu kanan atas -> pilih "Open in Chrome".' }) : null,
        h('div', { style: 'margin-bottom:6px' }, h('b', { style: 'color:#00d26a', text: '1. Android Chrome (Cara Install Resmi): ' }), 'Pastikan buka di ', h('b', { text: 'Google Chrome mode normal (BUKAN Incognito)' }), ' -> tap menu titik tiga (⋮) kanan atas -> pilih ', h('b', { text: '"Add to Home screen" -> "Install"' }), ' (pada Chrome Android versi baru, tombol Install ada di dalam menu "Add to Home screen").'),
        h('div', { style: 'margin-bottom:6px' }, h('b', { style: 'color:#ffb000', text: '2. Jika Hanya Muncul "Create Shortcut" (Bukan Install): ' }), 'Pastikan sudah reload 1x setelah Service Worker ACTIVE, tidak dalam mode Incognito, dan tidak ada versi aplikasi lama yang masih terinstall di HP.'),
        h('div', { style: 'margin-bottom:6px' }, h('b', { style: 'color:#4da3ff', text: '3. iOS Safari: ' }), 'Tap tombol ', h('b', { text: 'Share' }), ' -> pilih ', h('b', { text: '"Add to Home Screen"' }), '.'),
        !isSecure ? h('div', { style: 'margin-top:6px;padding:7px;background:#1a1203;border:1px solid #ffb00066;color:#ffd580', text: `Origin ${location.origin} bukan HTTPS. Buka melalui link HTTPS cloudflared Anda agar opsi Install Native muncul.` }) : null
      ),
      h('div', { style: 'display:flex;justify-content:flex-end;gap:8px' },
        h('button', { style: 'border-color:#00d26a;color:#00d26a', text: 'RELOAD PAGE', onclick: () => location.reload() }),
        h('button', { class: 'on', text: 'CLOSE', onclick: () => ov.remove() })
      )
    )
  );
  document.body.appendChild(ov);
}

if (btnInstall) {
  btnInstall.addEventListener('click', async () => {
    const promptEv = deferredInstallPrompt || window.__bbgDeferredInstall;
    if (promptEv) {
      promptEv.prompt();
      try { await promptEv.userChoice; } catch {}
      deferredInstallPrompt = null;
      window.__bbgDeferredInstall = null;
      syncInstallBtn();
    } else {
      showInstallGuideModal();
    }
  });
}

// Multi-Channel Push Notification Control Center (#btnPush)
const btnPush = $('#btnPush');
function syncPushBtn(enabled) {
  if (!btnPush) return;
  btnPush.classList.toggle('bbg-push-on', Boolean(enabled));
  btnPush.textContent = enabled ? 'ALERTS: ON' : 'ALERTS';
}
if (typeof Notification !== 'undefined' && Notification.permission === 'granted') {
  syncPushBtn(true);
}

async function attemptBrowserPushSubscription() {
  if (!window.isSecureContext) {
    return {
      ok: false,
      mode: 'INSECURE_HTTP',
      detail: `Origin ${location.origin} is not a Secure Context. Browser Web Push requires http://localhost:${location.port || '4000'} or HTTPS. Use Mobile ntfy or Android Termux Native below for non-HTTPS LAN/4G push.`
    };
  }
  if (typeof Notification === 'undefined') {
    return { ok: false, mode: 'UNSUPPORTED', detail: 'Browser Notification API unavailable on this client. WebSocket Toast, Termux Native, and ntfy Mobile Push remain available.' };
  }
  const perm = await Notification.requestPermission();
  if (perm !== 'granted') {
    syncPushBtn(false);
    return { ok: false, mode: 'DENIED', detail: 'Browser notification permission is blocked. Enable Notifications in Chrome Site Settings for this domain.' };
  }

  let vapidOk = false;
  let subErr = '';
  try {
    if (!swRegistration && 'serviceWorker' in navigator) {
      swRegistration = await navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(() => null);
    }
    const reg = swRegistration || (navigator.serviceWorker && await Promise.race([
      navigator.serviceWorker.ready,
      new Promise(res => setTimeout(() => res(null), 6000))
    ]).catch(() => null));
    if (reg && reg.pushManager) {
      const kRes = await fetch('/api/push/vapid-public-key', { cache: 'no-store' });
      const kJson = kRes.ok ? await kRes.json() : null;
      const pubKey = kJson && kJson.publicKey;
      if (pubKey) {
        let sub = await reg.pushManager.getSubscription();
        if (!sub) {
          sub = await reg.pushManager.subscribe({
            userVisibleOnly: true,
            applicationServerKey: urlBase64ToUint8Array(pubKey)
          });
        }
        if (sub) {
          const sRes = await apiFetch('/api/push/subscribe', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ subscription: sub.toJSON(), deviceLabel: navigator.userAgent.slice(0, 60) })
          }, 10000);
          vapidOk = sRes.ok;
          if (!sRes.ok) subErr = `HTTP ${sRes.status}`;
        }
      }
    }
  } catch (e) {
    subErr = e && e.message ? e.message : 'PushManager subscription error';
  }

  syncPushBtn(true);
  return {
    ok: true,
    mode: vapidOk ? 'VAPID_BACKGROUND' : 'OS_FOREGROUND',
    detail: vapidOk
      ? 'Background VAPID Web Push + Foreground OS Notification active.'
      : `Foreground OS Notification active (Background VAPID skipped: ${subErr || 'Service Worker PushManager unavailable'}).`
  };
}

async function openPushControlCenter() {
  const existing = $('#pushCenterModal');
  if (existing) existing.remove();

  let serverCfg = { ntfyTopic: '', enableTermux: true, enableWebPush: true, webPushAvailable: false, termuxAvailable: false, subscriptionsCount: 0 };
  try {
    const r = await apiFetch('/api/push/config', { cache: 'no-store' }, 8000);
    if (r.ok) {
      const j = await r.json();
      if (j && j.config) serverCfg = { ...serverCfg, ...j.config };
    }
  } catch {}

  const statusLog = h('div', { style: 'padding:6px 8px;background:#05070a;border:1px solid #1e2430;font-size:10.5px;color:#00e5ff;min-height:28px;margin-bottom:10px;line-height:1.45', text: 'Ready. Enable Browser Push or configure Mobile ntfy Topic below, then click SEND LIVE TEST.' });
  const ntfyInput = h('input', {
    value: serverCfg.ntfyTopic || '',
    placeholder: 'Private ntfy topic (e.g. bloomberg-fadhil-2026)',
    style: 'flex:1;min-width:190px;background:#05070a;color:#fff;border:1px solid #333b48;padding:5px 8px;font:inherit;font-size:11px'
  });

  const browserState = !window.isSecureContext
    ? `BLOCKED (HTTP LAN ${location.origin})`
    : (typeof Notification === 'undefined' ? 'UNSUPPORTED' : Notification.permission.toUpperCase());
  const browserCol = browserState === 'GRANTED' ? '#00d26a' : '#ffb000';

  const ov = h('div', {
    id: 'pushCenterModal',
    style: 'position:fixed;inset:0;z-index:99998;background:rgba(0,0,0,0.88);display:flex;align-items:center;justify-content:center;padding:16px',
    onclick: ev => { if (ev.target === ov) ov.remove(); }
  },
    h('div', { style: 'width:540px;max-width:95vw;background:#0a0d12;border:1px solid #ff6600;padding:16px 18px;color:#e6edf3;line-height:1.5' },
      h('div', { style: 'display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #262b33;padding-bottom:8px;margin-bottom:10px' },
        h('span', { style: 'color:#ff6600;font-weight:700;font-size:12.5px;letter-spacing:0.6px', text: 'BLOOMBERG TERMINAL // PUSH NOTIFICATION CONTROL CENTER' }),
        h('button', { text: 'CLOSE', onclick: () => ov.remove() })
      ),
      h('div', { class: 'xgrid2', style: 'margin-bottom:10px' },
        h('div', { class: 'xstat' },
          h('div', { class: 'xl', text: '1. BROWSER / PWA PUSH' }),
          h('div', { class: 'xv', style: `font-size:11.5px;color:${browserCol}`, text: browserState }),
          h('div', { class: 'xs', text: `VAPID Engine: ${serverCfg.webPushAvailable ? 'READY' : 'INSTALL web-push'} | Subs: ${serverCfg.subscriptionsCount}` })
        ),
        h('div', { class: 'xstat' },
          h('div', { class: 'xl', text: '2. WEBSOCKET LIVE STREAM' }),
          h('div', { class: 'xv', style: `font-size:11.5px;color:${hub.state === 'OPEN' ? '#00d26a' : '#ffb000'}`, text: hub.state }),
          h('div', { class: 'xs', text: 'Instant Terminal Toast + Audio Chime' })
        ),
        h('div', { class: 'xstat' },
          h('div', { class: 'xl', text: '3. ANDROID TERMUX NATIVE' }),
          h('div', { class: 'xv', style: `font-size:11.5px;color:${serverCfg.termuxAvailable ? '#00d26a' : '#9aa7b8'}`, text: serverCfg.termuxAvailable ? 'DETECTED (READY)' : 'NOT INSTALLED' }),
          h('div', { class: 'xs', text: 'Android OS bar via pkg install termux-api' })
        ),
        h('div', { class: 'xstat' },
          h('div', { class: 'xl', text: '4. MOBILE PUSH (NTFY.SH)' }),
          h('div', { class: 'xv', style: `font-size:11.5px;color:${serverCfg.ntfyTopic ? '#00d26a' : '#ffb000'}`, text: serverCfg.ntfyTopic ? 'ACTIVE' : 'NOT SET' }),
          h('div', { class: 'xs', text: 'Works on Android/iOS 4G/5G without HTTPS' })
        )
      ),
      h('div', { style: 'padding:8px;background:#070a10;border:1px solid #222936;margin-bottom:10px;font-size:11px' },
        h('div', { style: 'color:var(--amber);font-weight:700;margin-bottom:4px', text: 'RECOMMENDED FOR ANDROID / iOS (WORKS ON ANY NETWORK WITHOUT HTTPS):' }),
        h('div', { style: 'color:#cfd8e3;margin-bottom:6px', text: 'Install free "ntfy" app from Play Store / App Store -> Subscribe to a private topic name -> Enter the same topic below and click SAVE.' }),
        h('div', { style: 'display:flex;gap:6px;flex-wrap:wrap' },
          ntfyInput,
          h('button', {
            class: 'on',
            text: 'SAVE NTFY TOPIC',
            onclick: async () => {
              const r = await apiFetch('/api/push/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ntfyTopic: ntfyInput.value.trim(), enableTermux: true, enableWebPush: true })
              }, 10000);
              const j = await r.json();
              statusLog.textContent = r.ok ? `Saved ntfy topic: "${j.config.ntfyTopic || '(disabled)'}". Click SEND LIVE TEST to verify phone delivery.` : `Save error: ${j.error || 'failed'}`;
              if (r.ok && j.config.ntfyTopic) syncPushBtn(true);
            }
          })
        )
      ),
      statusLog,
      h('div', { style: 'display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end' },
        h('button', {
          style: 'border-color:#00d26a;color:#00d26a;font-weight:700',
          text: 'ENABLE BROWSER PUSH',
          onclick: async () => {
            statusLog.textContent = 'Requesting browser notification permission and VAPID subscription...';
            const res = await attemptBrowserPushSubscription();
            statusLog.textContent = `[${res.mode}] ${res.detail}`;
            if (res.ok) {
              triggerOsNotification({
                title: 'BLOOMBERG TERMINAL // BROWSER PUSH ENABLED',
                body: res.detail,
                eventType: 'PUSH_ENABLED'
              });
            }
          }
        }),
        h('button', {
          style: 'background:#ff6600;color:#000;border-color:#ff6600;font-weight:700',
          text: 'SEND LIVE TEST ALERT',
          onclick: async () => {
            statusLog.textContent = 'Dispatching test alert across all active channels...';
            try {
              const r = await apiFetch('/api/push/test', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) }, 12000);
              const j = await r.json();
              if (r.ok && j.ok) {
                statusLog.textContent = `DELIVERED — WebSocket: ${j.wsSent || 0} | WebPush: ${j.webPushDelivered || 0}/${j.totalSubs || 0} | Android Termux: ${j.termuxDelivered ? 'SENT' : 'OFF'} | Mobile ntfy: ${j.ntfyDelivered ? 'SENT' : 'OFF'}`;
                if (!j.wsSent) {
                  playAlertChime();
                  showBloombergToast(j.payload);
                  triggerOsNotification(j.payload);
                }
              } else {
                statusLog.textContent = `Test failed: ${j.error || ('HTTP ' + r.status)}`;
              }
            } catch (e) {
              statusLog.textContent = 'Test error: ' + e.message;
            }
          }
        })
      )
    )
  );
  document.body.appendChild(ov);
}

if (btnPush) {
  btnPush.addEventListener('click', openPushControlCenter);
}



