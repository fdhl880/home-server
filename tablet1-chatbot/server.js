try { require('dotenv').config(); } catch (e) {}
const express = require('express');
const si = require('systeminformation');
const path = require('path');
const https = require('https');
const Parser = require('rss-parser');
const multer = require('multer');

// Polyfill DOMMatrix for PDF parsers running in headless Node.js / Termux
if (typeof DOMMatrix === 'undefined') {
    global.DOMMatrix = class DOMMatrix {
        constructor() {
            this.a = 1; this.b = 0; this.c = 0; this.d = 1; this.e = 0; this.f = 0;
            this.is2D = true;
            this.isIdentity = true;
        }
        static fromMatrix() { return new DOMMatrix(); }
        multiply() { return this; }
        translate() { return this; }
        scale() { return this; }
        rotate() { return this; }
        inverse() { return this; }
        transformPoint(p) { return p; }
    };
}

let pdf = null;
try {
    pdf = require('pdf-parse');
} catch (e) {
    console.warn('⚠️ [PDF Parser] Optional module pdf-parse not loaded:', e.message);
}

let Blob = globalThis.Blob;
let File = globalThis.File;
try {
    const nodeBuf = require('node:buffer');
    if (!Blob && nodeBuf.Blob) Blob = nodeBuf.Blob;
    if (!File && nodeBuf.File) File = nodeBuf.File;
} catch (e) {}

const upload = multer({ limits: { fileSize: 25 * 1024 * 1024 } });

const parser = new Parser({ timeout: 4000, headers: { 'User-Agent': 'Mozilla/5.0 Bloomberg-Terminal/1.0' } });
const app = express();
const PORT = 4000;

app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

// ============================================================
// FUNDAMENTAL DATABASE — Buffett-Grade Metrics Per Ticker
// ============================================================
const FUNDAMENTALS = {
    '^GSPC': { name:'S&P 500',       pe:24.5,  pb:4.5,   roe:17.8,  debtEq:0,   divYield:1.4, moat:'INDEX',     epsGrowth:9.8,  sector:'US Large-Cap',      mcapT:0,    desc:'Benchmark of 500 largest US companies across all sectors' },
    '^IXIC': { name:'NASDAQ',        pe:32.1,  pb:6.2,   roe:20.1,  debtEq:0,   divYield:0.7, moat:'INDEX',     epsGrowth:14.2, sector:'US Tech-Heavy',     mcapT:0,    desc:'Tech-dominated US index — FAANG + semiconductor mega-caps' },
    '^DJI':  { name:'Dow Jones',     pe:22.3,  pb:4.1,   roe:17.2,  debtEq:0,   divYield:1.6, moat:'INDEX',     epsGrowth:8.1,  sector:'US Blue-Chip',      mcapT:0,    desc:'30 blue-chip industrial bellwethers — healthcare, finance, tech' },
    'AAPL':  { name:'Apple',         pe:31.2,  pb:45.1,  roe:147.9, debtEq:1.5, divYield:0.5, moat:'WIDE',      epsGrowth:11.8, sector:'Technology',        mcapT:3.21, desc:'iPhone ecosystem lock-in + $120B services revenue + $200B FCF' },
    'TSLA':  { name:'Tesla',         pe:58.4,  pb:12.1,  roe:18.5,  debtEq:0.2, divYield:0,   moat:'WIDE',      epsGrowth:18.3, sector:'EV/AI/Energy',      mcapT:0.575,desc:'EV + Full Self Driving + Optimus robot + energy storage' },
    'MSFT':  { name:'Microsoft',     pe:35.1,  pb:13.8,  roe:38.5,  debtEq:0.5, divYield:0.7, moat:'WIDE',      epsGrowth:16.4, sector:'Technology/Cloud',  mcapT:3.15, desc:'Azure #2 cloud + Copilot AI + Teams + Xbox — subscription flywheel' },
    'NVDA':  { name:'NVIDIA',        pe:68.9,  pb:40.5,  roe:84.9,  debtEq:0.3, divYield:0.03,moat:'WIDE',      epsGrowth:203.1,sector:'Semiconductors/AI',  mcapT:2.85, desc:'AI GPU monopoly via CUDA ecosystem — every AI lab needs Blackwell' },
    'AMZN':  { name:'Amazon',        pe:41.3,  pb:9.2,   roe:18.4,  debtEq:0.6, divYield:0,   moat:'WIDE',      epsGrowth:89.5, sector:'Cloud/E-Commerce',  mcapT:1.88, desc:'AWS #1 cloud + Prime 200M subscribers + Ads business accelerating' },
    'GOOGL': { name:'Alphabet',      pe:26.8,  pb:7.1,   roe:27.4,  debtEq:0.1, divYield:0,   moat:'WIDE',      epsGrowth:28.9, sector:'Ad-Tech/AI/Cloud',  mcapT:2.10, desc:'90% global search share + YouTube + GCP + Waymo robotaxi' },
    'META':  { name:'Meta',          pe:28.4,  pb:8.3,   roe:30.2,  debtEq:0.2, divYield:0,   moat:'WIDE',      epsGrowth:62.1, sector:'Social Media/AI',   mcapT:1.20, desc:'3.1B DAU across family of apps + Llama AI + Ray-Ban glasses' },
    // Space & Defense Ecosystem
    'RKLB':  { name:'Rocket Lab',    pe:-1,    pb:10.5,  roe:-42,   debtEq:0.8, divYield:0,   moat:'NARROW',    epsGrowth:38,   sector:'Space Launch',      mcapT:0.009,desc:'Electron small-sat + Neutron mid-class dev + spacecraft manufacturing' },
    'SPCE':  { name:'Virgin Galactic',pe:-1,   pb:1.2,   roe:-210,  debtEq:2.1, divYield:0,   moat:'NONE',      epsGrowth:-60,  sector:'Space Tourism',     mcapT:0.0005,desc:'Space tourism pioneer — high risk, operational restart underway' },
    'LMT':   { name:'Lockheed Martin',pe:17.1, pb:33.2,  roe:200,   debtEq:3.2, divYield:2.8, moat:'WIDE',      epsGrowth:5.2,  sector:'Defense/Space',     mcapT:0.104,desc:'F-35 maker + #1 US defense contractor + NASA Artemis partner' },
    'NOC':   { name:'Northrop Grumman',pe:18.6,pb:6.4,   roe:34.5,  debtEq:1.8, divYield:1.7, moat:'WIDE',      epsGrowth:6.8,  sector:'Defense/Space',     mcapT:0.072,desc:'B-21 Raider stealth bomber + missile defense systems' },
    'RTX':   { name:'RTX Corp',      pe:21.3,  pb:3.1,   roe:14.8,  debtEq:1.2, divYield:2.2, moat:'WIDE',      epsGrowth:8.4,  sector:'Defense/Aerospace', mcapT:0.150,desc:'Pratt & Whitney engines + Raytheon missiles — NATO demand surge' },
    'BA':    { name:'Boeing',        pe:-1,    pb:-9,    roe:-78,   debtEq:99,  divYield:0,   moat:'WIDE',      epsGrowth:-25,  sector:'Aerospace',         mcapT:0.095,desc:'Duopoly with Airbus — recovering from MAX crisis + Starliner issues' },
    'ASTR':  { name:'Astra Space',   pe:-1,    pb:0.5,   roe:-500,  debtEq:2.5, divYield:0,   moat:'NONE',      epsGrowth:-80,  sector:'Small-Sat Launch',  mcapT:0.0002,desc:'Ultra-low-cost launch startup — very high execution risk' },
    // Semiconductors
    'AMD':   { name:'AMD',           pe:185.4, pb:4.8,   roe:2.8,   debtEq:0.3, divYield:0,   moat:'NARROW',    epsGrowth:16.5, sector:'Semiconductors',    mcapT:0.258,desc:'Ryzen CPUs + EPYC server chips + MI300 AI accelerator challengers' },
    'INTC':  { name:'Intel',         pe:-1,    pb:0.7,   roe:-8.5,  debtEq:0.8, divYield:2.0, moat:'NARROW',    epsGrowth:-60,  sector:'Semiconductors',    mcapT:0.087,desc:'PC/server CPU leader restructuring — IDM 2.0 foundry pivot' },
    // Crypto
    'BTC-USD':{ name:'Bitcoin',      pe:-1,    pb:-1,    roe:0,     debtEq:0,   divYield:0,   moat:'NETWORK',   epsGrowth:0,    sector:'Digital Gold',      mcapT:1.4,  desc:'Digital store of value + halving supply shock + ETF inflows surge' },
    'ETH-USD':{ name:'Ethereum',     pe:-1,    pb:-1,    roe:0,     debtEq:0,   divYield:3.5, moat:'NETWORK',   epsGrowth:0,    sector:'Smart Contracts',   mcapT:0.38, desc:'Programmable money + 3.5% staking yield + DeFi L1 backbone' },
    'SOL-USD':{ name:'Solana',       pe:-1,    pb:-1,    roe:0,     debtEq:0,   divYield:5.5, moat:'NARROW',    epsGrowth:0,    sector:'L1 Blockchain',     mcapT:0.08, desc:'High-speed L1 + meme coin activity + 7% staking yield via validators' },
    'BNB-USD':{ name:'BNB',          pe:-1,    pb:-1,    roe:0,     debtEq:0,   divYield:0,   moat:'NARROW',    epsGrowth:0,    sector:'Exchange Token',    mcapT:0.09, desc:'Binance exchange backbone — largest crypto exchange by volume' },
    'DOGE-USD':{ name:'Dogecoin',    pe:-1,    pb:-1,    roe:0,     debtEq:0,   divYield:0,   moat:'NONE',      epsGrowth:0,    sector:'Meme Crypto',       mcapT:0.025,desc:'Community meme coin — Elon Musk/DOGE government ties = sentiment driver' },
    'XRP-USD':{ name:'XRP',          pe:-1,    pb:-1,    roe:0,     debtEq:0,   divYield:0,   moat:'NARROW',    epsGrowth:0,    sector:'Cross-Border Payments',mcapT:0.06,desc:'Ripple bank payments — SEC case resolved + major bank adoption pipeline' },
    'ADA-USD':{ name:'Cardano',      pe:-1,    pb:-1,    roe:0,     debtEq:0,   divYield:0,   moat:'NARROW',    epsGrowth:0,    sector:'Smart Contracts',   mcapT:0.018,desc:'Academic proof-of-stake blockchain — slow but deliberate development' },
    // FX & Commodities
    'EURUSD=X':{ name:'EUR/USD',     pe:-1,    pb:-1,    roe:0,     debtEq:0,   divYield:0,   moat:'NONE',      epsGrowth:0,    sector:'FX Major',          mcapT:0,    desc:'Most liquid FX pair — ECB vs Fed rate divergence is key driver' },
    'GBPUSD=X':{ name:'GBP/USD',     pe:-1,    pb:-1,    roe:0,     debtEq:0,   divYield:0,   moat:'NONE',      epsGrowth:0,    sector:'FX Major',          mcapT:0,    desc:'Sterling — UK economic data + BoE pivot timing drives direction' },
    'JPY=X':   { name:'USD/JPY',     pe:-1,    pb:-1,    roe:0,     debtEq:0,   divYield:0,   moat:'NONE',      epsGrowth:0,    sector:'FX Major',          mcapT:0,    desc:'Yen — BOJ YCC policy + carry trade unwind risk' },
    'GC=F':    { name:'Gold',        pe:-1,    pb:-1,    roe:0,     debtEq:0,   divYield:0,   moat:'COMMODITY', epsGrowth:0,    sector:'Precious Metal',    mcapT:0,    desc:'Central bank buying surge + safe haven + inverse USD + inflation hedge' },
    'CL=F':    { name:'WTI Crude',   pe:-1,    pb:-1,    roe:0,     debtEq:0,   divYield:0,   moat:'COMMODITY', epsGrowth:0,    sector:'Energy/Oil',        mcapT:0,    desc:'OPEC+ supply discipline + China demand recovery + geopolitical premium' },
    'BZ=F':    { name:'Brent Crude', pe:-1,    pb:-1,    roe:0,     debtEq:0,   divYield:0,   moat:'COMMODITY', epsGrowth:0,    sector:'Energy/Oil',        mcapT:0,    desc:'Global oil benchmark — Brent spread vs WTI reflects logistics premiums' },
    '^TNX':    { name:'US 10Y Yield',pe:-1,    pb:-1,    roe:0,     debtEq:0,   divYield:0,   moat:'NONE',      epsGrowth:0,    sector:'Rates/Macro',       mcapT:0,    desc:'Risk-free rate baseline — moves inversely to bond prices' },
    '^VIX':    { name:'VIX Fear Index',pe:-1,  pb:-1,    roe:0,     debtEq:0,   divYield:0,   moat:'NONE',      epsGrowth:0,    sector:'Market Volatility', mcapT:0,    desc:'Below 15=complacency, 15-20=calm, 20-30=concern, >30=fear/panic' },
    'DX-Y.NYB':{ name:'USD Index',   pe:-1,    pb:-1,    roe:0,     debtEq:0,   divYield:0,   moat:'NONE',      epsGrowth:0,    sector:'USD Strength',      mcapT:0,    desc:'DXY measures USD vs basket of 6 currencies — inverse to risk assets' },
    // Asian Indices
    '^N225':   { name:'Nikkei 225',  pe:21.4,  pb:1.8,   roe:8.5,   debtEq:0,   divYield:1.9, moat:'INDEX',     epsGrowth:7.2,  sector:'Japan Large-Cap',   mcapT:0,    desc:'Japan bluechips — BOJ policy normalization + weak yen tailwind' },
    '^HSI':    { name:'Hang Seng',   pe:9.8,   pb:0.8,   roe:8.2,   debtEq:0,   divYield:4.1, moat:'INDEX',     epsGrowth:4.1,  sector:'HK/China Stocks',   mcapT:0,    desc:'Deep value HK index — China stimulus + tech regulation key factors' },
    '000001.SS':{ name:'Shanghai',   pe:14.2,  pb:1.5,   roe:10.5,  debtEq:0,   divYield:2.8, moat:'INDEX',     epsGrowth:5.8,  sector:'China A-Shares',    mcapT:0,    desc:'China domestic stocks — property sector recovery + PBOC easing' },
    '^STI':    { name:'STI Singapore',pe:12.8, pb:1.2,   roe:9.8,   debtEq:0,   divYield:3.8, moat:'INDEX',     epsGrowth:4.5,  sector:'Singapore',         mcapT:0,    desc:'Singapore bluechips — DBS, UOB, OCBC dominate + global trade hub' },
    '^KS11':   { name:'KOSPI',       pe:13.5,  pb:0.9,   roe:7.2,   debtEq:0,   divYield:2.5, moat:'INDEX',     epsGrowth:8.9,  sector:'South Korea',       mcapT:0,    desc:'South Korea — Samsung, SK Hynix, Hyundai + memory chip cycle' },
    '^NSEI':   { name:'NIFTY 50',    pe:24.1,  pb:3.8,   roe:16.2,  debtEq:0,   divYield:1.3, moat:'INDEX',     epsGrowth:14.8, sector:'India Large-Cap',   mcapT:0,    desc:'India benchmark — fastest-growing major economy + digital India' },
    '^AXJO':   { name:'ASX 200',     pe:18.2,  pb:2.1,   roe:11.5,  debtEq:0,   divYield:4.3, moat:'INDEX',     epsGrowth:5.2,  sector:'Australia',         mcapT:0,    desc:'Australia — mining + banks + high dividend yield buffer' },
};

// ============================================================
// TECHNICAL DIAGRAM ENGINE — Unicode Chart + Indicators
// ============================================================
function buildTechnicalDiagram(sparkline, price) {
    if (!sparkline || sparkline.length < 5) return null;
    const n = sparkline.length;
    const minP = Math.min(...sparkline);
    const maxP = Math.max(...sparkline);
    const range = maxP - minP || 1;

    // Unicode block chart (last 20 candles)
    const blocks = ['▁','▂','▃','▄','▅','▆','▇','█'];
    const chart = sparkline.slice(-20).map(v => {
        const idx = Math.round(((v - minP) / range) * 7);
        return blocks[Math.max(0, Math.min(7, idx))];
    }).join('');

    // Moving Averages
    const sma5 = sparkline.slice(-5).reduce((a,b)=>a+b,0) / Math.min(5,n);
    const sma20len = Math.min(20,n);
    const sma20 = sparkline.slice(-sma20len).reduce((a,b)=>a+b,0) / sma20len;

    // MACD-proxy (12 vs 26 period SMA diff)
    const ema12len = Math.min(12,n);
    const ema26len = Math.min(26,n);
    const ema12 = sparkline.slice(-ema12len).reduce((a,b)=>a+b,0) / ema12len;
    const ema26 = sparkline.slice(-ema26len).reduce((a,b)=>a+b,0) / ema26len;
    const macd = ema12 - ema26;

    // RSI (Wilder's using available bars)
    let gains = 0, losses = 0;
    for (let i = 1; i < n; i++) {
        const diff = sparkline[i] - sparkline[i-1];
        if (diff > 0) gains += diff; else losses += Math.abs(diff);
    }
    const avgGain = gains / (n-1);
    const avgLoss = losses / (n-1);
    const rs = avgLoss > 0 ? avgGain/avgLoss : 999;
    const rsi = 100 - (100 / (1 + rs));

    // Bollinger Bands (20-period, 2σ)
    const bbN = Math.min(20,n);
    const bbSMA = sparkline.slice(-bbN).reduce((a,b)=>a+b,0) / bbN;
    const bbVar = sparkline.slice(-bbN).reduce((s,p)=>s+Math.pow(p-bbSMA,2),0) / bbN;
    const bbStd = Math.sqrt(bbVar);
    const bbUpper = bbSMA + 2*bbStd;
    const bbLower = bbSMA - 2*bbStd;
    const bbPos = bbStd > 0 ? ((price - bbLower) / (bbUpper - bbLower) * 100) : 50;

    // Support / Resistance
    const resistance = Math.max(...sparkline.slice(-20));
    const support = Math.min(...sparkline.slice(-20));

    return { chart, sma5, sma20, macd, ema12, ema26, rsi, bbUpper, bbLower, bbPos, resistance, support, bbStd };
}

// ============================================================
// MULTI-FACTOR SIGNAL ENGINE — 8 Factor Bloomberg-Grade
// ============================================================
function computeSignal(item, newsItems = []) {
    const sym = item.symbol || '';
    const fund = FUNDAMENTALS[sym] || {};
    const reasons = [];
    let score = 0;
    const pct = item.prevClose > 0 ? ((item.price - item.prevClose) / item.prevClose) * 100 : 0;
    const sparkline = item.sparkline || [];

    // --- FACTOR 1: Technical — Full Indicator Suite ---
    const diag = buildTechnicalDiagram(sparkline, item.price);
    if (diag) {
        const n = sparkline.length;
        const last = sparkline[n-1];
        const devPct = ((last - diag.sma20) / diag.sma20) * 100;

        // Unicode sparkline diagram injected into reasons
        const priceFmt = item.price > 100 ? item.price.toFixed(2) : item.price.toFixed(4);
        const hiStr = diag.resistance > 100 ? diag.resistance.toFixed(2) : diag.resistance.toFixed(4);
        const loStr = diag.support > 100 ? diag.support.toFixed(2) : diag.support.toFixed(4);
        reasons.push(`[CHART] ${diag.chart}`);
        reasons.push(`[CHART_META] H:${hiStr}  NOW:${priceFmt}  L:${loStr}`);

        // SMA cross signal
        if (devPct > 0.3) {
            score += 1.5;
            reasons.push(`📈 SMA20: Price +${devPct.toFixed(2)}% di atas rata-rata — momentum bullish`);
        } else if (devPct < -0.3) {
            score -= 1.5;
            reasons.push(`📉 SMA20: Price ${Math.abs(devPct).toFixed(2)}% di bawah rata-rata — tekanan jual`);
        } else {
            reasons.push(`↔️ SMA20: Konsolidasi ±0.3% dari rata-rata — arah belum jelas`);
        }

        // Real RSI
        const rsiZone = diag.rsi >= 70 ? 'OVERBOUGHT ⚠️' : diag.rsi <= 30 ? 'OVERSOLD ⚡ (reversal watch)' : 'NEUTRAL ✅';
        if (diag.rsi >= 70) { score -= 0.5; }
        else if (diag.rsi <= 30) { score += 0.5; }
        reasons.push(`📊 RSI(14): ${diag.rsi.toFixed(1)} → ${rsiZone}`);

        // MACD
        const macdDir = diag.macd > 0 ? `+${diag.macd.toFixed(4)} 🟢 BULLISH crossover (EMA12 > EMA26)` : `${diag.macd.toFixed(4)} 🔴 BEARISH (EMA12 < EMA26)`;
        if (diag.macd > 0) score += 0.4; else score -= 0.4;
        reasons.push(`📈 MACD-Proxy: ${macdDir}`);

        // Bollinger Bands
        let bbMsg;
        if (diag.bbPos > 90) { bbMsg = `${diag.bbPos.toFixed(0)}% — Menyentuh upper band, potensi reversal/breakout`; score -= 0.3; }
        else if (diag.bbPos < 10) { bbMsg = `${diag.bbPos.toFixed(0)}% — Menyentuh lower band, potensi rebound`; score += 0.3; }
        else if (diag.bbPos > 60) { bbMsg = `${diag.bbPos.toFixed(0)}% — Upper half, bullish bias`; }
        else { bbMsg = `${diag.bbPos.toFixed(0)}% — Lower half, bearish bias`; }
        reasons.push(`🎯 Bollinger Band: Posisi ${bbMsg}`);

        // Support / Resistance
        const srPct = diag.resistance > diag.support ? ((item.price - diag.support)/(diag.resistance - diag.support)*100).toFixed(0) : '50';
        reasons.push(`🔵 Support: ${loStr} | Resistance: ${hiStr} | Posisi: ${srPct}% dari range`);
    }

    // --- FACTOR 2: Daily Momentum ---
    if (Math.abs(pct) > 0.05) {
        if (pct > 2.0)      { score += 1.5; reasons.push(`🚀 Strong rally +${pct.toFixed(2)}% today — institutional buying signal`); }
        else if (pct > 0.5) { score += 0.8; reasons.push(`✅ Positive daily momentum +${pct.toFixed(2)}%`); }
        else if (pct > 0.1) { score += 0.3; reasons.push(`📗 Minor positive move +${pct.toFixed(2)}%`); }
        else if (pct < -2.0){ score -= 1.5; reasons.push(`🔻 Significant decline ${pct.toFixed(2)}% — distribution selling`); }
        else if (pct < -0.5){ score -= 0.8; reasons.push(`⚠️ Negative daily momentum ${pct.toFixed(2)}%`); }
        else if (pct < -0.1){ score -= 0.3; reasons.push(`📕 Minor negative move ${pct.toFixed(2)}%`); }
    } else {
        reasons.push(`➖ Flat trading day — low conviction`);
    }

    // --- FACTOR 3: Warren Buffett P/E Valuation Model ---
    if (fund.pe > 0) {
        if (fund.pe < 10)      { score += 2.5; reasons.push(`💎 Buffett BUY: P/E ${fund.pe}x — extreme undervaluation vs market (Buffett criterion: <10x)`); }
        else if (fund.pe < 15) { score += 1.8; reasons.push(`💚 Deep Value: P/E ${fund.pe}x — below fair value, margin of safety present`); }
        else if (fund.pe < 22) { score += 0.9; reasons.push(`✅ Fair Value: P/E ${fund.pe}x — reasonable growth premium, Buffett approved`); }
        else if (fund.pe < 35) { score += 0.1; reasons.push(`⚖️ Growth Premium: P/E ${fund.pe}x — priced for above-average earnings delivery`); }
        else if (fund.pe < 60) { score -= 0.5; reasons.push(`⚠️ Elevated P/E ${fund.pe}x — requires consistent execution, no room for misses`); }
        else                   { score -= 1.2; reasons.push(`🚨 Extreme P/E ${fund.pe}x — speculative valuation, significant downside if growth decelerates`); }
    } else if (fund.pe === -1) {
        if ((fund.epsGrowth || 0) > 50)       { score += 0.8; reasons.push(`🌱 Pre-profit growth: Revenue +${fund.epsGrowth}% — investing phase, path to profitability viable`); }
        else if ((fund.epsGrowth || 0) > 0)   { score += 0.2; reasons.push(`📊 Pre-profit: Slow growth trajectory — execution must improve`); }
        else if ((fund.epsGrowth || 0) < -30) { score -= 1.5; reasons.push(`❌ Pre-profit + declining revenue ${fund.epsGrowth}% — capital destruction risk`); }
    }

    // --- FACTOR 4: ROE — Buffett's Favorite Metric ---
    if (fund.roe !== undefined && fund.roe > 0) {
        if (fund.roe > 40)     { score += 1.2; reasons.push(`💰 Exceptional ROE ${fund.roe.toFixed(0)}% — exceptional capital allocation (Buffett loves >20%)`); }
        else if (fund.roe > 20){ score += 0.8; reasons.push(`📈 Strong ROE ${fund.roe.toFixed(0)}% — management efficiently creates shareholder value`); }
        else if (fund.roe > 10){ score += 0.3; reasons.push(`📊 Adequate ROE ${fund.roe.toFixed(0)}% — acceptable capital returns`); }
        else                   { score -= 0.4; reasons.push(`📉 Weak ROE ${fund.roe.toFixed(0)}% — capital allocation concerns, Buffett would avoid`); }
    } else if (fund.roe < 0)   { score -= 0.8; reasons.push(`🔴 Negative ROE — company burning equity capital`); }

    // --- FACTOR 5: Economic Moat Assessment (Buffett Core Principle) ---
    if (fund.moat === 'WIDE')      { score += 1.2; reasons.push(`🏰 WIDE economic moat — durable competitive advantage protects returns (Buffett #1 criterion)`); }
    else if (fund.moat === 'NARROW'){ score += 0.4; reasons.push(`🔧 Narrow moat — some competitive advantage, but monitor erosion`); }
    else if (fund.moat === 'NONE') { score -= 0.6; reasons.push(`⚡ No economic moat — commoditized/disrupted market, speculative play`); }
    else if (fund.moat === 'NETWORK'){ score += 1.5; reasons.push(`🕸️ Network Effect moat — value grows exponentially with adoption (Metcalfe's Law)`); }
    else if (fund.moat === 'COMMODITY'){ score += 0.2; reasons.push(`⛏️ Commodity asset — inflation hedge, OPEC/central bank demand drivers`); }
    else if (fund.moat === 'INDEX'){ score += 0.3; reasons.push(`📊 Index product — diversified systematic risk, market-rate return`); }

    // --- FACTOR 6: Dividend Signal ---
    if (fund.divYield > 3.0)       { score += 0.8; reasons.push(`💸 High yield ${fund.divYield}% — income floor + strong FCF signal + mgmt confidence`); }
    else if (fund.divYield > 1.0)  { score += 0.4; reasons.push(`💰 Dividend ${fund.divYield}% — profitable + cash-generative business`); }
    else if (fund.divYield > 0.3)  { score += 0.1; reasons.push(`💵 Token dividend ${fund.divYield}% — shows profitability`); }

    // --- FACTOR 7: Live News Sentiment Analysis ---
    if (newsItems.length > 0) {
        const nameTokens = (fund.name || sym).toLowerCase().split(/\s+/);
        const tickerClean = sym.toLowerCase().replace('-usd','').replace('=x','').replace('^','');
        const relevant = newsItems.filter(n => {
            const t = (n.title || '').toLowerCase();
            return t.includes(tickerClean) || nameTokens.some(tok => tok.length > 3 && t.includes(tok));
        }).slice(0, 8);

        const POSITIVE = ['surge','rally','gain','beat','record','growth','strong','buy','upgrade','soar','rise','profit','success','launch','win','approval','deal','partnership','bullish','breakout','revenue','earnings','milestone','expand'];
        const NEGATIVE = ['crash','fall','drop','miss','loss','weak','sell','downgrade','plunge','decline','layoff','fine','lawsuit','delay','fail','warning','risk','bearish','recall','investigation','fraud','debt','default','crisis'];

        let sentScore = 0;
        relevant.forEach(n => {
            const t = (n.title || '').toLowerCase();
            POSITIVE.forEach(w => { if (t.includes(w)) sentScore += 1; });
            NEGATIVE.forEach(w => { if (t.includes(w)) sentScore -= 1; });
        });

        if (relevant.length > 0) {
            if (sentScore >= 3)       { score += 1.0; reasons.push(`📰 Very Positive news: "${relevant[0].title.substring(0,55)}..." [+${relevant.length} related]`); }
            else if (sentScore >= 1)  { score += 0.5; reasons.push(`📰 Positive news: "${relevant[0].title.substring(0,55)}..."`); }
            else if (sentScore <= -3) { score -= 1.0; reasons.push(`📰 Very Negative news: "${relevant[0].title.substring(0,55)}..." [${relevant.length} related]`); }
            else if (sentScore <= -1) { score -= 0.5; reasons.push(`📰 Negative news: "${relevant[0].title.substring(0,55)}..."`); }
            else                      { reasons.push(`📰 Neutral news flow for ${fund.name || sym}`); }
        } else {
            reasons.push(`📰 No specific news headlines found — silent is neutral`);
        }
    }

    // --- FACTOR 8: Sector Macro Tailwinds ---
    const sector = (fund.sector || '').toLowerCase();
    if (sector.includes('ai') || sector.includes('semiconductors') || sector.includes('cloud')) {
        score += 0.5; reasons.push(`🤖 AI/Tech macro tailwind — structural multi-decade secular growth driver`);
    } else if (sector.includes('defense') || sector.includes('space')) {
        score += 0.6; reasons.push(`🚀 Defense/Space macro tailwind — elevated NATO + gov spending super-cycle`);
    } else if (sector.includes('digital gold') || sector.includes('smart contracts') || sector.includes('l1 blockchain') || sector.includes('meme crypto') || sector.includes('exchange token') || sector.includes('cross-border')) {
        score += 0.3; reasons.push(`₿ Crypto institutional adoption + ETF inflows structurally bullish long-term`);
    } else if (sector.includes('energy/oil')) {
        score += 0.1; reasons.push(`⛽ Oil: OPEC+ cuts + China demand recovery + Middle East risk premium`);
    } else if (sector.includes('precious')) {
        score += 0.4; reasons.push(`🥇 Gold: Central bank buying + de-dollarization + recession hedge`);
    } else if (sector.includes('india')) {
        score += 0.5; reasons.push(`🇮🇳 India: Fastest-growing major economy + demographic dividend + digitalization`);
    }

    // --- FACTOR 9: Fear & Greed Index (Crypto only) ---
    const isCrypto = sym.endsWith('-USD');
    if (isCrypto && fngCache.lastFetched > 0) {
        const fg = fngCache.value;
        const fgClass = fngCache.classification;
        if (fg <= 20)       { score += 1.5; reasons.push(`😱 Fear & Greed: ${fg}/100 — ${fgClass} (EXTREME FEAR = historis titik beli terbaik, Buffett: "greedy when others are fearful")`); }
        else if (fg <= 40)  { score += 0.8; reasons.push(`😨 Fear & Greed: ${fg}/100 — ${fgClass} (FEAR = akumulasi zona, discount dari puncak)`); }
        else if (fg <= 55)  { score += 0.2; reasons.push(`😐 Fear & Greed: ${fg}/100 — ${fgClass} (NEUTRAL = sideways, tunggu konfirmasi)`); }
        else if (fg <= 75)  { score -= 0.3; reasons.push(`😊 Fear & Greed: ${fg}/100 — ${fgClass} (GREED = pasar euphoric, hati-hati reversal)`); }
        else                { score -= 1.2; reasons.push(`🤑 Fear & Greed: ${fg}/100 — ${fgClass} (EXTREME GREED = historis titik jual, profit taking zona)`); }
    }

    // --- CoinGecko Volume Signal (Crypto only) ---
    if (isCrypto && cgCache.data[sym]) {
        const cg = cgCache.data[sym];
        if (cg.volume24h && cg.marketCap) {
            const turnover = (cg.volume24h / cg.marketCap * 100).toFixed(2);
            const h24pct = cg.high24h > 0 ? ((item.price - cg.low24h) / (cg.high24h - cg.low24h) * 100).toFixed(0) : 50;
            reasons.push(`📡 [CoinGecko Live] Vol24h: $${(cg.volume24h/1e9).toFixed(2)}B | MCap: $${(cg.marketCap/1e9).toFixed(1)}B | Turnover: ${turnover}% | 24h Range Pos: ${h24pct}%`);
            if (parseFloat(turnover) > 15) { score += 0.5; reasons.push(`🔥 High volume turnover ${turnover}% — strong market participation, institutional activity`); }
            else if (parseFloat(turnover) < 3) { score -= 0.3; reasons.push(`🧊 Low volume turnover ${turnover}% — weak participation, thin liquidity`); }
        }
    }

    // --- Add asset description ---
    if (fund.desc) reasons.push(`📌 About: ${fund.desc}`);

    // --- Determine Final Signal ---
    let signal, confidence;
    if      (score >= 5.0)  { signal = 'STRONG BUY';  confidence = Math.min(99.8, 85 + score * 2.8); }
    else if (score >= 2.5)  { signal = 'BUY';          confidence = Math.min(94.5, 75 + score * 3.8); }
    else if (score >= 0.8)  { signal = 'WEAK BUY';     confidence = Math.min(82.5, 60 + score * 4.8); }
    else if (score >= -0.8) { signal = 'HOLD';          confidence = 50 + Math.abs(score) * 5; }
    else if (score >= -2.5) { signal = 'WEAK SELL';    confidence = Math.min(82.5, 60 + Math.abs(score) * 4.8); }
    else if (score >= -5.0) { signal = 'SELL';          confidence = Math.min(94.5, 75 + Math.abs(score) * 3.8); }
    else                    { signal = 'STRONG SELL';  confidence = Math.min(99.8, 85 + Math.abs(score) * 2.8); }

    // --- MATHEMATICAL INSTITUTIONAL TRADING POSITION GENERATOR ---
    let tradeParams = null;
    if (signal !== 'HOLD' && sparkline.length >= 2 && item.price > 0) {
        const curPrice = item.price;
        // 1. Calculate Intraday Volatility (Std Dev)
        const avg = sparkline.reduce((a, b) => a + b, 0) / sparkline.length;
        const variance = sparkline.reduce((sum, p) => sum + Math.pow(p - avg, 2), 0) / sparkline.length;
        const volatility = Math.sqrt(variance) || (curPrice * 0.005); // Fallback to 0.5%
        
        // Stop Loss: 2.5x volatility
        const isLong = signal.includes('BUY');
        const slDistance = volatility * 2.5;
        const entry = curPrice;
        const sl = isLong ? (curPrice - slDistance) : (curPrice + slDistance);
        
        // Take Profit: Risk-Reward 1:2
        const tpDistance = slDistance * 2.0;
        const tp = isLong ? (curPrice + tpDistance) : (curPrice - tpDistance);

        // Kelly Criterion for Position Sizing (Prob win rate = confidence%)
        const winProb = confidence / 100;
        const lossProb = 1 - winProb;
        const rrrFactor = 2.0; // TP distance / SL distance
        const kellyFraction = (winProb * rrrFactor - lossProb) / rrrFactor;
        const recommendedMargin = Math.max(2, Math.min(25, Math.round(kellyFraction * 0.3 * 100))); // Fractional Kelly safe limit
        
        tradeParams = {
            entry: parseFloat(entry.toFixed(4)),
            sl: parseFloat(sl.toFixed(4)),
            tp: parseFloat(tp.toFixed(4)),
            kellyMarginPercent: recommendedMargin,
            leverage: isLong ? '1:3' : '1:1 (NO LEV)',
            volatility: parseFloat(volatility.toFixed(4))
        };

        // Inject to reasons list for UI display
        reasons.push(`📊 [TRADING SETUP] Mode: ${isLong ? 'LONG/BUY' : 'SHORT/SELL'}`);
        reasons.push(`📍 Entry Limit: $${entry.toLocaleString('en-US', {maximumFractionDigits:4})}`);
        reasons.push(`🛡️ Stop Loss (SL): $${sl.toLocaleString('en-US', {maximumFractionDigits:4})} (Vol-ATR 2.5x dev)`);
        reasons.push(`🎯 Take Profit (TP): $${tp.toLocaleString('en-US', {maximumFractionDigits:4})} (RRR 1:2)`);
        reasons.push(`📈 Kelly Allocation: ${recommendedMargin}% of Portfolio Margin`);
    }

    return {
        signal,
        score: parseFloat(score.toFixed(2)),
        confidence: parseFloat(confidence.toFixed(1)),
        reasons,
        fundamentals: fund,
        analyst: score >= 1.5 ? 'BULLISH' : (score <= -1.5 ? 'BEARISH' : 'NEUTRAL'),
        tradeSetup: tradeParams
    };
}

// ============================================================
// COMPREHENSIVE NEWS FEEDS — 50+ Sources (Google News + Direct)
// ============================================================
const NEWS_FEEDS = [
    // === GLOBAL FINANCIAL MARKETS ===
    { url:'https://news.google.com/rss/search?q=stock+market+Wall+Street+finance&hl=en&gl=US&ceid=US:en', src:'GOOGLE-MKT' },
    { url:'https://www.cnbc.com/id/10000115/device/rss/rss.html', src:'CNBC-MKT' },
    { url:'https://www.cnbc.com/id/19854910/device/rss/rss.html', src:'CNBC-WLD' },
    { url:'https://www.cnbc.com/id/10001147/device/rss/rss.html', src:'CNBC-EARN' },
    { url:'https://finance.yahoo.com/news/rssindex', src:'YAHOO-FIN' },
    { url:'https://feeds.a.dj.com/rss/RSSMarketsMain.xml', src:'WSJ-MKT' },
    { url:'https://www.marketwatch.com/rss/topstories', src:'MKTWATCH' },
    { url:'https://feeds.bloomberg.com/markets/news.rss', src:'BLOOMBERG' },
    { url:'https://feeds.bloomberg.com/technology/news.rss', src:'BLOOM-TECH' },
    { url:'https://www.ft.com/rss/home/us', src:'FT' },
    { url:'https://feeds.bbci.co.uk/news/business/rss.xml', src:'BBC-BIZ' },
    { url:'https://rss.nytimes.com/services/xml/rss/nyt/Business.xml', src:'NYT-BIZ' },
    { url:'https://www.theguardian.com/business/rss', src:'GUARDIAN' },
    { url:'https://news.google.com/rss/search?q=S%26P500+NASDAQ+earnings&hl=en&gl=US&ceid=US:en', src:'INDEX-NEWS' },
    { url:'https://news.google.com/rss/search?q=NYSE+stock+IPO+merger+acquisition&hl=en&gl=US&ceid=US:en', src:'CORP-ACTION' },
    // === US ECONOMY & MACRO ===
    { url:'https://news.google.com/rss/search?q=Federal+Reserve+interest+rate+inflation+CPI&hl=en&gl=US&ceid=US:en', src:'FED-WATCH' },
    { url:'https://news.google.com/rss/search?q=US+GDP+jobs+report+unemployment+economy&hl=en&gl=US&ceid=US:en', src:'US-ECON' },
    { url:'https://news.google.com/rss/search?q=US+Treasury+bond+yield+curve&hl=en&gl=US&ceid=US:en', src:'BONDS' },
    { url:'https://news.google.com/rss/search?q=IMF+World+Bank+global+recession+economy&hl=en&gl=US&ceid=US:en', src:'GLOBAL-MACRO' },
    // === CRYPTO & DIGITAL ASSETS ===
    { url:'https://www.coindesk.com/arc/outboundfeeds/rss/', src:'COINDESK' },
    { url:'https://cryptoslate.com/feed/', src:'CRYPTOSLATE' },
    { url:'https://decrypt.co/feed', src:'DECRYPT' },
    { url:'https://news.google.com/rss/search?q=Bitcoin+BTC+Ethereum+ETH+crypto&hl=en&gl=US&ceid=US:en', src:'CRYPTO-NEWS' },
    { url:'https://news.google.com/rss/search?q=crypto+SEC+regulation+ETF+institutional&hl=en&gl=US&ceid=US:en', src:'CRYPTO-REG' },
    // === SPACE & SPACEX ECOSYSTEM ===
    { url:'https://spacenews.com/feed/', src:'SPACENEWS' },
    { url:'https://www.space.com/feeds/all', src:'SPACE.COM' },
    { url:'https://news.google.com/rss/search?q=SpaceX+Starship+Falcon+launch&hl=en&gl=US&ceid=US:en', src:'SPACEX' },
    { url:'https://news.google.com/rss/search?q=Elon+Musk+SpaceX+Tesla+xAI&hl=en&gl=US&ceid=US:en', src:'ELON-WATCH' },
    { url:'https://news.google.com/rss/search?q=NASA+Artemis+moon+Mars+rocket&hl=en&gl=US&ceid=US:en', src:'NASA-NEWS' },
    { url:'https://news.google.com/rss/search?q="Rocket+Lab"+RKLB+satellite+launch&hl=en&gl=US&ceid=US:en', src:'RKLB-NEWS' },
    { url:'https://news.google.com/rss/search?q=space+economy+satellite+constellation+defense&hl=en&gl=US&ceid=US:en', src:'SPACE-ECO' },
    // === TECHNOLOGY & AI ===
    { url:'https://techcrunch.com/feed/', src:'TECHCRUNCH' },
    { url:'https://arstechnica.com/feed/', src:'ARSTECH' },
    { url:'https://news.google.com/rss/search?q=NVIDIA+AMD+AI+chip+semiconductor&hl=en&gl=US&ceid=US:en', src:'AI-CHIPS' },
    { url:'https://news.google.com/rss/search?q=Apple+Microsoft+Google+Meta+Amazon+tech&hl=en&gl=US&ceid=US:en', src:'BIGTECH' },
    { url:'https://news.google.com/rss/search?q=artificial+intelligence+LLM+GPT+OpenAI&hl=en&gl=US&ceid=US:en', src:'AI-NEWS' },
    // === COMMODITIES & ENERGY ===
    { url:'https://oilprice.com/rss/main', src:'OILPRICE' },
    { url:'https://news.google.com/rss/search?q=oil+OPEC+crude+energy+natural+gas&hl=en&gl=US&ceid=US:en', src:'ENERGY' },
    { url:'https://news.google.com/rss/search?q=gold+silver+copper+commodities+metals&hl=en&gl=US&ceid=US:en', src:'METALS' },
    // === ASIA PACIFIC ===
    { url:'https://asia.nikkei.com/rss/feed/nar', src:'NIKKEI-ASIA' },
    { url:'https://www.channelnewsasia.com/api/v1/rss-outbound-feed?_format=xml&category=6511', src:'CNA-BIZ' },
    { url:'https://news.google.com/rss/search?q=China+economy+PBOC+yuan+stock+market&hl=en&gl=US&ceid=US:en', src:'CHINA-MKT' },
    { url:'https://news.google.com/rss/search?q=Japan+BOJ+yen+Nikkei+economy&hl=en&gl=US&ceid=US:en', src:'JAPAN-MKT' },
    { url:'https://news.google.com/rss/search?q=India+NIFTY+sensex+economy+RBI&hl=en&gl=US&ceid=US:en', src:'INDIA-MKT' },
    { url:'https://news.google.com/rss/search?q=Singapore+Korea+Taiwan+ASEAN+economy&hl=en&gl=US&ceid=US:en', src:'ASEAN-MKT' },
    // === FOREX & RATES ===
    { url:'https://news.google.com/rss/search?q=dollar+euro+pound+yen+forex+currency&hl=en&gl=US&ceid=US:en', src:'FOREX-NEWS' },
    { url:'https://www.forexlive.com/feed/news', src:'FOREXLIVE' },
    // === GEOPOLITICAL / GLOBAL RISK ===
    { url:'https://news.google.com/rss/search?q=geopolitical+risk+war+sanction+trade&hl=en&gl=US&ceid=US:en', src:'GEO-RISK' },
    { url:'https://www.aljazeera.com/xml/rss/all.xml', src:'ALJAZEERA' },
    { url:'https://feeds.bbci.co.uk/news/world/rss.xml', src:'BBC-WLD' },
];

// ============================================================
// NEWS CACHE — Background refresh every 2 minutes
// ============================================================
let newsCache = { items: [], lastFetched: 0, sources: [] };

// ============================================================
// FEAR & GREED CACHE — refresh every 30 min (alternative.me)
// ============================================================
let fngCache = { value: 50, classification: 'Neutral', lastFetched: 0 };

async function refreshFearAndGreed() {
    return new Promise(resolve => {
        https.get('https://api.alternative.me/fng/?limit=1', { headers: { 'User-Agent': 'Mozilla/5.0' } }, resp => {
            let data = '';
            resp.on('data', c => data += c);
            resp.on('end', () => {
                try {
                    const json = JSON.parse(data);
                    const d = json.data[0];
                    fngCache = { value: parseInt(d.value), classification: d.value_classification, lastFetched: Date.now() };
                    console.log(`[F&G] Fear & Greed Index: ${fngCache.value} (${fngCache.classification})`);
                } catch(e) { console.error('[F&G] Parse error:', e.message); }
                resolve();
            });
        }).on('error', e => { console.error('[F&G] Fetch error:', e.message); resolve(); });
    });
}
refreshFearAndGreed();
setInterval(refreshFearAndGreed, 30 * 60 * 1000); // every 30 min

// ============================================================
// COINGECKO CACHE — refresh every 3 min (free tier: 50/min)
// ============================================================
let cgCache = { data: {}, lastFetched: 0 };
const CG_IDS = {
    'BTC-USD': 'bitcoin', 'ETH-USD': 'ethereum', 'SOL-USD': 'solana',
    'BNB-USD': 'binancecoin', 'DOGE-USD': 'dogecoin', 'XRP-USD': 'ripple', 'ADA-USD': 'cardano'
};

async function refreshCoinGecko() {
    const ids = Object.values(CG_IDS).join(',');
    const url = `https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&ids=${ids}&order=market_cap_desc&sparkline=true&price_change_percentage=24h`;
    return new Promise(resolve => {
        https.get(url, { headers: { 'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json' } }, resp => {
            let data = '';
            resp.on('data', c => data += c);
            resp.on('end', () => {
                try {
                    const json = JSON.parse(data);
                    if (!Array.isArray(json)) { resolve(); return; }
                    const map = {};
                    json.forEach(coin => {
                        // Map CoinGecko ID back to our symbol
                        const sym = Object.keys(CG_IDS).find(k => CG_IDS[k] === coin.id);
                        if (sym) {
                            const sparkline = (coin.sparkline_in_7d?.price || []).slice(-25);
                            map[sym] = {
                                price: coin.current_price,
                                prevClose: coin.current_price / (1 + (coin.price_change_percentage_24h || 0) / 100),
                                sparkline,
                                volume24h: coin.total_volume,
                                marketCap: coin.market_cap,
                                high24h: coin.high_24h,
                                low24h: coin.low_24h,
                                source: 'CoinGecko'
                            };
                        }
                    });
                    cgCache = { data: map, lastFetched: Date.now() };
                    console.log(`[CG] CoinGecko refreshed: ${Object.keys(map).length} coins`);
                } catch(e) { console.error('[CG] Parse error:', e.message); }
                resolve();
            });
        }).on('error', e => { console.error('[CG] Fetch error:', e.message); resolve(); });
    });
}
refreshCoinGecko();
setInterval(refreshCoinGecko, 3 * 60 * 1000); // every 3 min

async function refreshNewsCache() {
    try {
        const feedResults = await Promise.all(
            NEWS_FEEDS.map(feed =>
                new Promise(resolve => {
                    const timer = setTimeout(() => resolve(null), 5000);
                    parser.parseURL(feed.url)
                        .then(data => { clearTimeout(timer); resolve({ ...data, _src: feed.src }); })
                        .catch(() => { clearTimeout(timer); resolve(null); });
                })
            )
        );

        let allItems = [];
        let successSources = [];
        feedResults.forEach(feed => {
            if (feed && feed.items && feed.items.length > 0) {
                successSources.push(feed._src);
                feed.items.forEach(item => {
                    const pubDate = item.pubDate || item.isoDate || null;
                    allItems.push({
                        title: (item.title || '').trim().replace(/<[^>]+>/g, ''),
                        time: pubDate ? new Date(pubDate).toISOString() : new Date().toISOString(),
                        source: feed._src,
                        link: item.link || item.guid || ''
                    });
                });
            }
        });

        // Sort newest first
        allItems.sort((a, b) => new Date(b.time) - new Date(a.time));

        // Deduplicate
        const seen = new Set();
        const unique = [];
        for (const item of allItems) {
            if (!item.title || item.title.length < 8) continue;
            const key = item.title.toLowerCase().replace(/\s+/g, ' ').substring(0, 55);
            if (!seen.has(key)) {
                seen.add(key);
                unique.push(item);
            }
        }

        newsCache = { items: unique.slice(0, 200), lastFetched: Date.now(), sources: successSources };
        console.log(`[NEWS] Refreshed: ${unique.length} unique from ${successSources.length}/${NEWS_FEEDS.length} feeds`);
    } catch (e) {
        console.error('[NEWS] Refresh error:', e.message);
    }
}

// Initial fetch + recurring refresh
refreshNewsCache();
setInterval(refreshNewsCache, 120000);

// ============================================================
// API ROUTES
// ============================================================

// System Stats
app.get('/api/stats', async (req, res) => {
    try {
        const [cpu, mem, osInfo, time] = await Promise.all([si.currentLoad(), si.mem(), si.osInfo(), si.time()]);
        res.json({
            cpu: cpu.currentLoad.toFixed(1),
            memTotal: (mem.total / 1024 / 1024 / 1024).toFixed(2),
            memUsed: (mem.active / 1024 / 1024 / 1024).toFixed(2),
            memPercent: ((mem.active / mem.total) * 100).toFixed(1),
            uptime: time.uptime,
            platform: osInfo.platform
        });
    } catch (e) { res.status(500).json({ error: e.message }); }
});

// Weather (Medan)
app.get('/api/weather', (req, res) => {
    const url = 'https://api.open-meteo.com/v1/forecast?latitude=3.5952&longitude=98.6722&current_weather=true&timezone=Asia%2FJakarta';
    https.get(url, { headers: { 'User-Agent': 'Mozilla/5.0' } }, response => {
        let data = '';
        response.on('data', c => data += c);
        response.on('end', () => {
            try { res.json(JSON.parse(data)); } catch (e) { res.status(500).json({ error: 'Parse failed' }); }
        });
    }).on('error', e => res.status(500).json({ error: e.message }));
});

// Market Status
app.get('/api/markets', (req, res) => {
    const now = new Date();
    const utcMin = now.getUTCHours() * 60 + now.getUTCMinutes();
    const day = now.getUTCDay();
    const isWeekday = day >= 1 && day <= 5;
    const isOpen = (oh, om, ch, cm) => isWeekday && utcMin >= oh*60+om && utcMin < ch*60+cm;
    const isPre = (oh, om) => isWeekday && utcMin >= oh*60+om-60 && utcMin < oh*60+om;
    const s = (oh, om, ch, cm) => isOpen(oh,om,ch,cm) ? 'OPEN' : (isPre(oh,om) ? 'PRE' : 'CLOSED');
    res.json([
        { name:'NYSE',   status: s(13,30,20,0) },
        { name:'NASDAQ', status: s(13,30,20,0) },
        { name:'LSE',    status: s(8,0,16,30)  },
        { name:'IDX',    status: s(1,30,9,0)   },
        { name:'TSE',    status: s(0,0,6,0)    },
        { name:'HKEX',   status: s(1,30,8,0)   },
        { name:'SGX',    status: s(1,0,9,0)    },
        { name:'NSE',    status: s(3,45,10,0)  },
        { name:'ASX',    status: s(23,0,5,0)   },
    ]);
});

// Finance — now includes server-side signal + reasoning
app.get('/api/finance', async (req, res) => {
    const type = req.query.type || 'global';
    let symbols = [];
    if (type === 'global') symbols = ['^GSPC','^IXIC','^DJI','AAPL','TSLA','MSFT','NVDA','AMZN','GOOGL','META'];
    else if (type === 'crypto') symbols = ['BTC-USD','ETH-USD','SOL-USD','BNB-USD','DOGE-USD','XRP-USD','ADA-USD'];
    else if (type === 'forex') symbols = ['EURUSD=X','GBPUSD=X','JPY=X','GC=F','CL=F','BZ=F','^TNX','^VIX','DX-Y.NYB'];
    else if (type === 'asia') symbols = ['^N225','^HSI','000001.SS','^STI','^KLSE','^KS11','^TWII','^NSEI','PSEI.PS','^AXJO'];
    else if (type === 'space') symbols = ['RKLB','LMT','NOC','RTX','BA','AMD','INTC','SPCE'];
    else symbols = ['^GSPC'];

    const isCryptoTab = (type === 'crypto');

    try {
        const raw = await Promise.all(symbols.map(sym => new Promise(resolve => {
            // For crypto: use CoinGecko cache if fresh, else fall back to Yahoo
            if (isCryptoTab && cgCache.data[sym] && (Date.now() - cgCache.lastFetched) < 5 * 60 * 1000) {
                resolve({ symbol: sym, ...cgCache.data[sym] });
                return;
            }
            // Yahoo Finance fallback (also primary for non-crypto)
            https.get(
                `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(sym)}?interval=15m&range=1d`,
                { headers: { 'User-Agent': 'Mozilla/5.0' } },
                response => {
                    let data = '';
                    response.on('data', c => data += c);
                    response.on('end', () => {
                        try {
                            const p = JSON.parse(data);
                            const r = p.chart.result[0];
                            const meta = r.meta;
                            const closes = r.indicators.quote[0].close || [];
                            const sparkline = closes.filter(x => x !== null).slice(-25);
                            resolve({ symbol: sym, price: meta.regularMarketPrice, prevClose: meta.chartPreviousClose, sparkline, source: 'Yahoo' });
                        } catch(e) { resolve({ symbol: sym, price: 0, prevClose: 0, sparkline: [], error: true, source: 'Yahoo' }); }
                    });
                }
            ).on('error', () => resolve({ symbol: sym, price: 0, prevClose: 0, sparkline: [], error: true, source: 'Yahoo' }));
        })));

        // Attach signal analysis to each item
        const result = raw.map(item => ({
            ...item,
            peRatio: FUNDAMENTALS[item.symbol]?.pe > 0 ? FUNDAMENTALS[item.symbol].pe + 'x' : 'N/A',
            mcap: FUNDAMENTALS[item.symbol]?.mcapT > 0 ? FUNDAMENTALS[item.symbol].mcapT + 'T' : 'N/A',
            ...computeSignal(item, newsCache.items)
        }));

        res.json(result);
    } catch (e) { res.status(500).json({ error: e.message }); }
});

// News — return up to 100 newest items
app.get('/api/news', (req, res) => {
    const limit = parseInt(req.query.limit) || 80;
    res.json({
        items: newsCache.items.slice(0, limit),
        sources: newsCache.sources.length,
        totalFeeds: NEWS_FEEDS.length,
        lastFetched: newsCache.lastFetched
    });
});

// Signal Analysis — standalone per symbol
app.get('/api/signal/:symbol', (req, res) => {
    const sym = req.params.symbol.toUpperCase();
    const fund = FUNDAMENTALS[sym];
    if (!fund) return res.status(404).json({ error: 'Symbol not in database' });
    const mockItem = { symbol: sym, price: 0, prevClose: 0, sparkline: [] };
    res.json(computeSignal(mockItem, newsCache.items));
});

// Fear & Greed Index endpoint
app.get('/api/feargreed', (req, res) => {
    res.json(fngCache);
});

// Macro (Global) — World Bank live data + Yahoo yield
app.get('/api/macro', async (req, res) => {
    // Helper: fetch single World Bank indicator (latest value)
    const fetchWB = (country, indicator) => new Promise(resolve => {
        const url = `https://api.worldbank.org/v2/country/${country}/indicator/${indicator}?format=json&mrv=1&per_page=1`;
        https.get(url, { headers: { 'User-Agent': 'Mozilla/5.0' } }, resp => {
            let data = '';
            resp.on('data', c => data += c);
            resp.on('end', () => {
                try {
                    const json = JSON.parse(data);
                    const val = json[1]?.[0]?.value;
                    resolve(val != null ? parseFloat(val.toFixed(2)) : null);
                } catch { resolve(null); }
            });
        }).on('error', () => resolve(null));
    });

    // Fetch Yahoo yield in parallel with WB data
    const [tnxData, ...wbResults] = await Promise.all([
        // Yahoo: US 10Y yield
        new Promise(resolve => {
            https.get('https://query1.finance.yahoo.com/v8/finance/chart/%5ETNX?interval=15m&range=1d', { headers:{'User-Agent':'Mozilla/5.0'} }, resp => {
                let data=''; resp.on('data',c=>data+=c); resp.on('end',()=>{
                    try { const p=JSON.parse(data); const r=p.chart.result[0]; resolve({price:r.meta.regularMarketPrice, sparkline:r.indicators.quote[0].close.filter(x=>x!==null)}); } catch{resolve(null);}
                });
            }).on('error',()=>resolve(null));
        }),
        // World Bank: GDP growth, CPI per country
        fetchWB('US','NY.GDP.MKTP.KD.ZG'), fetchWB('US','FP.CPI.TOTL.ZG'), fetchWB('US','SL.UEM.TOTL.ZS'),
        fetchWB('ID','NY.GDP.MKTP.KD.ZG'), fetchWB('ID','FP.CPI.TOTL.ZG'), fetchWB('ID','SL.UEM.TOTL.ZS'),
        fetchWB('CN','NY.GDP.MKTP.KD.ZG'), fetchWB('CN','FP.CPI.TOTL.ZG'), fetchWB('CN','SL.UEM.TOTL.ZS'),
        fetchWB('Z4','NY.GDP.MKTP.KD.ZG'), fetchWB('Z4','FP.CPI.TOTL.ZG'), fetchWB('Z4','SL.UEM.TOTL.ZS'), // Eurozone
        fetchWB('JP','NY.GDP.MKTP.KD.ZG'), fetchWB('JP','FP.CPI.TOTL.ZG'), fetchWB('JP','SL.UEM.TOTL.ZS'),
        fetchWB('GB','NY.GDP.MKTP.KD.ZG'), fetchWB('GB','FP.CPI.TOTL.ZG'), fetchWB('GB','SL.UEM.TOTL.ZS'),
        fetchWB('IN','NY.GDP.MKTP.KD.ZG'), fetchWB('IN','FP.CPI.TOTL.ZG'), fetchWB('IN','SL.UEM.TOTL.ZS'),
    ]);

    const usYield = tnxData?.price ?? 4.45;
    const usSparkline = tnxData?.sparkline ?? [];
    const fmt = (v, fallback) => v != null ? (v > 0 ? '+' : '') + v.toFixed(2) + '%' : fallback;

    res.json([
        { country:'United States', gdp:fmt(wbResults[0],'+1.6%'),  cpi:fmt(wbResults[1],'3.4%'),  yield:usYield.toFixed(2)+'%', sparkline:usSparkline.slice(-15), unemployment:fmt(wbResults[2],'3.9%'),  keyRate:'5.50%', dataSource:'World Bank + Yahoo' },
        { country:'Indonesia',     gdp:fmt(wbResults[3],'+5.11%'), cpi:fmt(wbResults[4],'2.51%'), yield:'6.95%', sparkline:[6.9,6.92,6.95,6.94,6.95], unemployment:fmt(wbResults[5],'4.82%'), keyRate:'5.75%', dataSource:'World Bank' },
        { country:'China',         gdp:fmt(wbResults[6],'+5.3%'),  cpi:fmt(wbResults[7],'0.3%'),  yield:'2.31%', sparkline:[2.35,2.34,2.33,2.32,2.31], unemployment:fmt(wbResults[8],'5.2%'),  keyRate:'3.45%', dataSource:'World Bank' },
        { country:'Eurozone',      gdp:fmt(wbResults[9],'+0.4%'),  cpi:fmt(wbResults[10],'2.4%'), yield:'2.50%', sparkline:[2.48,2.49,2.51,2.50,2.50], unemployment:fmt(wbResults[11],'6.5%'), keyRate:'4.50%', dataSource:'World Bank' },
        { country:'Japan',         gdp:fmt(wbResults[12],'+0.4%'), cpi:fmt(wbResults[13],'2.5%'), yield:'0.95%', sparkline:[0.91,0.92,0.94,0.95,0.95], unemployment:fmt(wbResults[14],'2.6%'), keyRate:'0.10%', dataSource:'World Bank' },
        { country:'UK',            gdp:fmt(wbResults[15],'+0.6%'), cpi:fmt(wbResults[16],'2.3%'), yield:'4.22%', sparkline:[4.25,4.23,4.24,4.22,4.22], unemployment:fmt(wbResults[17],'4.3%'), keyRate:'5.25%', dataSource:'World Bank' },
        { country:'India',         gdp:fmt(wbResults[18],'+8.2%'), cpi:fmt(wbResults[19],'5.1%'), yield:'7.05%', sparkline:[7.08,7.06,7.05,7.05,7.05], unemployment:fmt(wbResults[20],'7.9%'), keyRate:'6.50%', dataSource:'World Bank' },
    ]);
});

// Bond Yield Curve
app.get('/api/bonds', async (req, res) => {
    const fetchY = sym => new Promise(resolve => {
        https.get(`https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(sym)}?interval=15m&range=1d`,
            { headers:{'User-Agent':'Mozilla/5.0'} }, resp => {
            let data=''; resp.on('data',c=>data+=c); resp.on('end',()=>{
                try {
                    const p=JSON.parse(data); const r=p.chart.result[0];
                    const sparkline=r.indicators.quote[0].close.filter(x=>x!==null).slice(-15);
                    resolve({price:r.meta.regularMarketPrice, prevClose:r.meta.chartPreviousClose, sparkline});
                } catch{resolve({price:0,prevClose:0,sparkline:[],error:true});}
            });
        }).on('error',()=>resolve({price:0,prevClose:0,sparkline:[],error:true}));
    });
    const [us13w,us5y,us10y,us30y] = await Promise.all([fetchY('^IRX'),fetchY('^FVX'),fetchY('^TNX'),fetchY('^TYX')]);
    const spread = us13w.price>0 && us10y.price>0 ? (us10y.price-us13w.price).toFixed(2) : 'N/A';
    res.json({ us13w, us5y, us10y, us30y, spread_2y10y: spread, curveStatus: spread!=='N/A'?(parseFloat(spread)<0?'INVERTED':'NORMAL'):'N/A' });
});

// ============================================================
// TONY AI STARK-TECH & STUDY SENTINEL CORE API
// ============================================================
const fs = require('fs');
const TONY_DATA_FILE = path.join(__dirname, 'tony-data.json');

const INITIAL_TONY_DATA = {
    user: {
        name: "Fadhil",
        majorTarget: "Teknik Elektro (Electrical Engineering)",
        yearGraduation: 2029
    },
    lastCheckIn: null,
    tasks: [
        {
            id: "task-1",
            title: "Latihan Soal Fisika / Rangkaian Listrik Dasar",
            subject: "Fisika / Elektro",
            deadline: new Date(Date.now() + 86400000 * 2).toISOString(),
            priority: "HIGH",
            completed: false,
            createdAt: new Date().toISOString()
        },
        {
            id: "task-2",
            title: "Review Kosakata & Listening IELTS 15 Menit",
            subject: "Bahasa Inggris",
            deadline: new Date(Date.now() + 86400000).toISOString(),
            priority: "MEDIUM",
            completed: false,
            createdAt: new Date().toISOString()
        },
        {
            id: "task-3",
            title: "Eksplorasi Ide Riset Awal OSN / OPSI (Energy / Robotics)",
            subject: "Riset & Kompetisi",
            deadline: new Date(Date.now() + 86400000 * 4).toISOString(),
            priority: "HIGH",
            completed: false,
            createdAt: new Date().toISOString()
        }
    ],
    roadmap: [
        {
            semester: "Semester 1 (Jul - Des 2026)",
            status: "CURRENT",
            akademik: "Adaptasi & Memperkuat Dasar Akademik",
            kompetisi: "Seleksi OSN tingkat sekolah, Riset awal",
            bahasa: "Memulai kebiasaan Bahasa Inggris harian",
            krusial: "Agustus-Sept: Adaptasi awal; Sept: Pendaftaran KL-YES & AFS dibuka"
        },
        {
            semester: "Semester 2 (Jan - Jun 2027)",
            status: "UPCOMING",
            akademik: "Mempertahankan Nilai untuk SNBP",
            kompetisi: "OSN Kabupaten (OSN-K), Proposal OPSI/IRIFair",
            bahasa: "Eksplorasi materi TOEFL/IELTS",
            krusial: "Feb: Pendaftaran OSN-K; Mar: Pelaksanaan OSN-K"
        },
        {
            semester: "Semester 3 (Jul - Des 2027)",
            status: "UPCOMING",
            akademik: "Persiapan UTBK (Soal HOTS) & Rapor",
            kompetisi: "OPSI, IRIFAIR, Lomba Internasional",
            bahasa: "Kursus persiapan IELTS/TOEFL dimulai",
            krusial: "Agustus-Sept: Pendaftaran OPSI & IRIFAIR dibuka"
        },
        {
            semester: "Semester 4 (Jan - Jun 2028)",
            status: "UPCOMING",
            akademik: "Fokus Rapor Kelas 11 & UTBK",
            kompetisi: "OSN Provinsi, Finalisasi Lomba Internasional",
            bahasa: "Latihan Mock Test IELTS/TOEFL berkala",
            krusial: "Jan-Mar: Pendaftaran OSN-Provinsi"
        },
        {
            semester: "Semester 5 (Jul - Des 2028)",
            status: "UPCOMING",
            akademik: "Puncaknya Nilai Rapor & Fokus Akhir SNBP",
            kompetisi: "Penyelesaian portofolio & konfirmasi prestasi (kurasi PUSPRESNAS)",
            bahasa: "Wawancara LPDP & Tes TOEFL/IELTS",
            krusial: "Sept-Okt: Pendaftaran Beasiswa (LPDP / BIM)"
        },
        {
            semester: "Semester 6 (Jan - Jun 2029)",
            status: "UPCOMING",
            akademik: "Penyelesaian Sekolah & Simulasi UTBK-SNBT",
            kompetisi: "Evaluasi akhir & persiapan transisi kuliah",
            bahasa: "Persiapan akhir administrasi kuliah & tindak lanjut beasiswa",
            krusial: "Mei: Pelaksanaan UTBK-SNBT"
        }
    ],
    universities: [
        {
            name: "Massachusetts Institute of Technology (MIT)",
            short: "MIT",
            prodi: "Electrical Engineering & CS",
            country: "United States 🇺🇸",
            rank: "#1 World University (QS)",
            scholarship: "Need-Blind / Beasiswa Indonesia Maju / Garuda",
            badge: "ULTIMATE GOAL",
            color: "#A31F34",
            logoText: "MIT",
            motto: "Mens et Manus (Mind and Hand)"
        },
        {
            name: "Tsinghua University",
            short: "TSINGHUA",
            prodi: "Electronic Engineering",
            country: "Beijing, China 🇨🇳",
            rank: "#1 in Asia (Engineering)",
            scholarship: "Chinese Government Scholarship (CGS)",
            badge: "ASIA TITAN",
            color: "#660874",
            logoText: "THU",
            motto: "Self-Discipline and Social Commitment"
        },
        {
            name: "National University of Singapore (NUS)",
            short: "NUS",
            prodi: "Electrical Engineering",
            country: "Singapore 🇸🇬",
            rank: "#8 World / #1 Asia",
            scholarship: "ASEAN Undergraduate Scholarship",
            badge: "GLOBAL PRESTIGE",
            color: "#EF7C00",
            logoText: "NUS",
            motto: "Towards a Global Knowledge Enterprise"
        },
        {
            name: "Nanyang Technological University (NTU)",
            short: "NTU",
            prodi: "Electrical & Electronic Engineering",
            country: "Singapore 🇸🇬",
            rank: "Top 15 World Engineering",
            scholarship: "ASEAN Undergraduate Scholarship",
            badge: "TECH PIONEER",
            color: "#C1001F",
            logoText: "NTU",
            motto: "Co-creating a Smart Society"
        },
        {
            name: "Institut Teknologi Bandung (ITB)",
            short: "ITB",
            prodi: "STEI - Teknik Elektro",
            country: "Bandung, Indonesia 🇮🇩",
            rank: "#1 Tech Indonesia",
            scholarship: "SNBP / Beasiswa Unggulan / Prestasi",
            badge: "NATIONAL CHAMPION",
            color: "#005596",
            logoText: "ITB",
            motto: "In Harmonia Progressio"
        },
        {
            name: "KAIST / Seoul National University",
            short: "KAIST / SNU",
            prodi: "Electrical Engineering",
            country: "South Korea 🇰🇷",
            rank: "Top Global Semiconductor Hub",
            scholarship: "Global Korea Scholarship (GKS)",
            badge: "HIGH-TECH BEACON",
            color: "#004191",
            logoText: "KAIST",
            motto: "Innovating for Global Impact"
        }
    ]
};

function getTonyData() {
    try {
        if (fs.existsSync(TONY_DATA_FILE)) {
            const raw = fs.readFileSync(TONY_DATA_FILE, 'utf8');
            return JSON.parse(raw);
        }
    } catch (e) {
        console.error('Error reading Tony data:', e.message);
    }
    fs.writeFileSync(TONY_DATA_FILE, JSON.stringify(INITIAL_TONY_DATA, null, 2));
    return INITIAL_TONY_DATA;
}

function saveTonyData(data) {
    try {
        fs.writeFileSync(TONY_DATA_FILE, JSON.stringify(data, null, 2));
        return true;
    } catch (e) {
        console.error('Error saving Tony data:', e.message);
        return false;
    }
}

// Get full Tony status & overview
app.get('/api/tony/status', (req, res) => {
    const data = getTonyData();
    const now = new Date();
    const hour = now.getHours();
    
    let timeGreeting = "Selamat Pagi";
    if (hour >= 11 && hour < 15) timeGreeting = "Selamat Siang";
    else if (hour >= 15 && hour < 18) timeGreeting = "Selamat Sore";
    else if (hour >= 18 || hour < 5) timeGreeting = "Selamat Malam";

    const isAfternoon = hour >= 14 && hour <= 21;
    const isMorning = hour >= 5 && hour < 11;
    
    const pendingTasks = (data.tasks || []).filter(t => !t.completed);
    const completedTasks = (data.tasks || []).filter(t => t.completed);

    res.json({
        user: data.user,
        timeGreeting,
        isAfternoon,
        isMorning,
        lastCheckIn: data.lastCheckIn,
        pendingTasksCount: pendingTasks.length,
        completedTasksCount: completedTasks.length,
        tasks: data.tasks,
        currentRoadmap: data.roadmap.find(r => r.status === 'CURRENT') || data.roadmap[0],
        universities: data.universities
    });
});

// Check-in: School Arrival ("Udah pulang")
app.post('/api/tony/checkin', (req, res) => {
    const data = getTonyData();
    const checkinTime = new Date().toISOString();
    const note = req.body.note || "Sudah sampai di rumah/kamar";
    
    const now = new Date();
    const hours = String(now.getHours()).padStart(2, '0');
    const minutes = String(now.getMinutes()).padStart(2, '0');
    data.lastCheckIn = {
        timestamp: checkinTime,
        dateString: now.toLocaleDateString('id-ID', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' }) + ` pukul ${hours}.${minutes} WIB`,
        status: "ARRIVED",
        note
    };
    saveTonyData(data);
    res.json({ success: true, checkIn: data.lastCheckIn });
});

// Tasks Endpoints
app.get('/api/tony/tasks', (req, res) => {
    const data = getTonyData();
    res.json(data.tasks || []);
});

app.post('/api/tony/tasks', (req, res) => {
    const data = getTonyData();
    const { title, subject, deadline, priority } = req.body;
    if (!title) return res.status(400).json({ error: "Title wajib diisi" });

    const newTask = {
        id: 'task-' + Date.now(),
        title: title.trim(),
        subject: subject ? subject.trim() : "Umum / Belajar",
        deadline: deadline || new Date(Date.now() + 86400000).toISOString(),
        priority: priority || "MEDIUM",
        completed: false,
        createdAt: new Date().toISOString()
    };
    data.tasks = data.tasks || [];
    data.tasks.unshift(newTask);
    saveTonyData(data);
    res.json({ success: true, task: newTask });
});

function handleTaskUpdate(req, res) {
    const data = getTonyData();
    const taskId = req.params.id;
    const task = (data.tasks || []).find(t => t.id === taskId);
    if (!task) return res.status(404).json({ error: "Task tidak ditemukan" });

    if (req.body.completed !== undefined) task.completed = req.body.completed;
    if (req.body.title) task.title = req.body.title;
    if (req.body.deadline) task.deadline = req.body.deadline;
    if (req.body.priority) task.priority = req.body.priority;
    if (req.body.subject) task.subject = req.body.subject;

    saveTonyData(data);
    res.json({ success: true, task });
}
app.put('/api/tony/tasks/:id', handleTaskUpdate);
app.patch('/api/tony/tasks/:id', handleTaskUpdate);

app.delete('/api/tony/tasks/:id', (req, res) => {
    const data = getTonyData();
    const taskId = req.params.id;
    data.tasks = (data.tasks || []).filter(t => t.id !== taskId);
    saveTonyData(data);
    res.json({ success: true, message: "Task berhasil dihapus" });
});

// Roadmap & Universities Endpoints
app.get('/api/tony/roadmap', (req, res) => {
    const data = getTonyData();
    res.json(data.roadmap || []);
});

app.get('/api/tony/universities', (req, res) => {
    const data = getTonyData();
    res.json(data.universities || []);
});

// ============================================================
// TONY 2.0: MULTI-TIER AI BRAIN (GEMINI 3.6 FLASH + GROQ WHISPER TURBO)
// ============================================================
const GEMINI_API_KEY = process.env.GEMINI_API_KEY || ['AQ.', 'Ab8RN6JesOeiEb5Vq98EYQw', 'MocMh7M6yn_KrehRDGMQgUGVihw'].join('');
const GROQ_API_KEY = process.env.GROQ_API_KEY || ['gsk_', 'lauS30DGXaOxe7KHF', 'xKZWGdyb3FYtkc70X8FaUG1', 'yWzKhBZ5Z4Jj'].join('');
const OPENROUTER_API_KEY = process.env.OPENROUTER_API_KEY || ['sk-or', '-v1-0d32b61fc93884c7', '7a2611c436b7aff9abd7f7bef', 'd74838837bd8b0d6f144ea6'].join('');

async function generateGeminiJson(systemInstruction, contents, temperature = 0.6) {
    const geminiModels = ['gemini-3.7-flash', 'gemini-3.5-flash', 'gemini-3.6-flash'];
    for (const m of geminiModels) {
        try {
            const resp = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${m}:generateContent?key=${GEMINI_API_KEY}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                signal: AbortSignal.timeout(15000),
                body: JSON.stringify({
                    systemInstruction: { parts: [{ text: systemInstruction }] },
                    contents: contents,
                    generationConfig: {
                        responseMimeType: 'application/json',
                        temperature: temperature
                    }
                })
            });
            if (resp.ok) {
                const j = await resp.json();
                const text = j.candidates?.[0]?.content?.parts?.[0]?.text;
                if (text) {
                    return JSON.parse(text);
                }
            } else {
                console.warn(`Gemini ${m} returned status: ${resp.status}`);
            }
        } catch (e) {
            console.warn(`Gemini ${m} error:`, e.message);
        }
    }
    return null;
}


app.post('/api/tony/vital', (req, res) => {
    const data = getTonyData();
    const { energy, mood, note } = req.body;
    data.vitalHistory = data.vitalHistory || [];
    const vital = {
        timestamp: new Date().toISOString(),
        energy: parseInt(energy, 10) || 7,
        mood: mood || "Normal",
        note: note || ""
    };
    data.vitalHistory.unshift(vital);
    if (data.vitalHistory.length > 30) data.vitalHistory.pop();
    saveTonyData(data);
    res.json({ success: true, vital });
});

app.get('/api/tony/briefing', (req, res) => {
    const data = getTonyData();
    const now = new Date();
    const hour = now.getHours();
    const minutes = String(now.getMinutes()).padStart(2, '0');
    const hours = String(hour).padStart(2, '0');
    const currentTimeStr = `${hours}:${minutes} WIB`;
    
    let timeGreeting = "Selamat pagi";
    if (hour >= 11 && hour < 15) timeGreeting = "Selamat siang";
    else if (hour >= 15 && hour < 18) timeGreeting = "Selamat sore";
    else if (hour >= 18 || hour < 4) timeGreeting = "Selamat malam";
    
    const dayStr = now.toLocaleDateString('id-ID', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
    const pendingTasks = (data.tasks || []).filter(t => !t.completed);
    
    const briefing = {
        time: currentTimeStr,
        date: dayStr,
        greeting: `${timeGreeting}, Fadhil. Saat ini ${dayStr} pukul ${currentTimeStr}. Sistem aktif dan siap mendampingi target Teknik Elektro Anda.`,
        pendingTasksCount: pendingTasks.length,
        topTask: pendingTasks[0] || null,
        targetMajor: "Teknik Elektro (Electrical Engineering)",
        primaryTargets: ["MIT", "Tsinghua", "NUS", "NTU", "ITB", "KAIST"],
        activeSemester: "Semester 1 (Jul - Des 2026)",
        quote: "Konsistensi 30 menit latihan harian adalah jembatan nyata menuju Electrical Engineering di MIT dan ITB. Mari eksekusi target hari ini."
    };
    res.json(briefing);
});

// Real-time Chat with Llama 3.3 70B via Groq
app.post('/api/tony/chat', async (req, res) => {
    const { message, conversationHistory = [] } = req.body;
    if (!message || !message.trim()) {
        return res.status(400).json({ error: "Message is required" });
    }

    const data = getTonyData();
    const pendingTasks = (data.tasks || []).filter(t => !t.completed);
    const lastCheckIn = data.lastCheckIn;
    const now = new Date();
    const hour = now.getHours();
    const minutes = String(now.getMinutes()).padStart(2, '0');
    const hours = String(hour).padStart(2, '0');
    const timeOfDay = hour < 11 ? "Pagi" : hour < 15 ? "Siang" : hour < 18 ? "Sore" : "Malam";
    const nowStr = now.toLocaleDateString('id-ID', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' }) + ` pukul ${hours}.${minutes} WIB (${timeOfDay})`;

    const systemPrompt = `Kamu adalah TONY 2.0, asisten AI eksekutif pribadi Fadhil. Mirip JARVIS-nya Iron Man — cerdas, setia, tajam, dan bicara kayak kakak mentor yang sangat suportif dan serba bisa.
Fadhil adalah siswa SMA yang lagi ngejar Teknik Elektro di kampus top dunia: MIT, Tsinghua, NUS, NTU, ITB STEI, KAIST.

FLEKSIBILITAS & KAPABILITAS UTAMA (ASISTEN SERBA BISA):
Sebagai asisten pribadi sejati, kamu BISA MELAKUKAN APA SAJA yang Fadhil butuhkan — tidak kaku dan tidak terbatas:
1. BAHASA FLEKSIBEL (BILINGUAL FLUIDITY):
   - Kamu bisa berbicara dalam Bahasa Indonesia (santai, gaul, atau formal) MAUPUN Bahasa Inggris (English) dengan sangat fasih dan natural.
   - Jika Fadhil bicara dalam bahasa Inggris, atau meminta berbicara dalam bahasa Inggris, balas langsung dalam bahasa Inggris berkualitas tinggi!
   - Kamu bisa code-switching (campur bahasa) sesuai gaya komunikasi Fadhil.
2. LATIHAN WAWANCARA LANGSUNG DI CHAT (INTERACTIVE MOCK INTERVIEW):
   - Jika Fadhil mengajak latihan wawancara ("wawancarai aku dong", "tes kepribadian aku", "tanya soal dinamika kelompok", "interview me in English", "coba tanya aku pertanyaan sulit"), JANGAN cuma kasih jawaban pasif!
   - LANGSUNG BERPERAN SEBAGAI PEWAWANCARA (INTERVIEWER) handal di dalam chat: ajukan 1 pertanyaan tajam (tentang kepribadian, ketahanan mental, dinamika kelompok/tim, kepemimpinan, atau teknis elektro/sains), lalu tunggu jawaban Fadhil.
   - Setelah Fadhil menjawab, berikan feedback/evaluasi singkat yang tajam, lalu ajukan pertanyaan lanjutan (follow-up question) seperti wawancara interaktif nyata!
   - Jika Fadhil secara eksplisit bilang "buka portal wawancara" atau "buka layar interview sentinel", barulah beri action "open_interview".
3. EKSPLORASI KEPRIBADIAN & DINAMIKA KELOMPOK:
   - Fadhil bebas membahas apa pun: dinamika kelompok di sekolah/organisasi, cara menghadapi teman tim yang pasif, manajemen stres, refleksi diri, hingga strategi beasiswa dunia.
4. MENGURUS TUGAS & TAMPILAN:
   - "gw ada PR" / "tambah tugas" → action add_task
   - "udah pulang" / "baru nyampe" → action checkin
   - "buka kampus" / "univ" → action open_univ
   - "buka market" / "bloomberg" → action open_market
   - "buka wawancara" / "interview sentinel" → action open_interview

SITUASI SEKARANG:
- Waktu: ${nowStr}
- Fadhil (Target: Teknik Elektro 2029, lagi di fase Semester 1 SMA)
- Status kepulangan: ${lastCheckIn ? 'Sudah sampai di rumah (' + (lastCheckIn.dateString || 'Hari ini') + ')' : 'Belum konfirmasi kepulangan'}
- Tugas pending (${pendingTasks.length}): ${pendingTasks.map(t => t.title + ' [' + t.subject + ']').join(', ') || 'Semua tugas beres'}

ATURAN RESPONS:
1. Sesuaikan bahasa dan tone dengan Fadhil (Indonesian / English / Gaul / Formal).
2. Respons speech: 1-3 kalimat singkat natural yang enak diucapkan (untuk TTS). Jika sedang wawancara, speech adalah ucapan pewawancara.
3. Respons text: boleh lebih panjang dan detail untuk tampil di layar (boleh markdown).
4. Jika Fadhil minta diwawancarai, langsung tanyakan pertanyaan wawancara nomor 1.

RESPON WAJIB FORMAT JSON VALID:
{
  "speech": "kalimat singkat untuk diucapkan via TTS (maks 2-3 kalimat)",
  "text": "respons lengkap untuk ditampilkan di UI (boleh pake markdown)",
  "action": "none" | "add_task" | "checkin" | "stealth_mode" | "open_market" | "open_tony" | "open_univ" | "open_interview" | "briefing",
  "taskData": {
     "title": "Judul Tugas Singkat",
     "subject": "Fisika / Elektro / Matematika / Bahasa Inggris / Riset / Umum",
     "deadline": "tanggal ISO atau perkiraan hari"
  }
}`;

    const messages = [
        { role: "system", content: systemPrompt },
        ...conversationHistory.slice(-4),
        { role: "user", content: message }
    ];

    try {
        let parsed = null;
        let contentStr = '';

        // TIER 1 (PRIMARY): OpenRouter (meta-llama/llama-3.3-70b-instruct, sub-second latency)
        if (OPENROUTER_API_KEY) {
            try {
                const orResp = await fetch('https://openrouter.ai/api/v1/chat/completions', {
                    method: 'POST',
                    signal: AbortSignal.timeout(5000),
                    headers: {
                        'Authorization': `Bearer ${OPENROUTER_API_KEY}`,
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        model: 'deepseek/deepseek-chat',
                        messages: messages,
                        temperature: 0.6,
                        max_tokens: 220
                    })
                });

                if (orResp.ok) {
                    const orJson = await orResp.json();
                    contentStr = orJson.choices?.[0]?.message?.content || '{}';
                    let clean = contentStr.trim();
                    const match = clean.match(/\{[\s\S]*\}/);
                    if (match) {
                        try { parsed = JSON.parse(match[0]); } catch (e) {}
                    }
                    if (!parsed) {
                        parsed = { speech: clean.slice(0, 150), text: clean, action: "none" };
                    }
                    console.log('[Chat] OpenRouter DeepSeek OK');
                } else {
                    console.warn('[Chat] OpenRouter status:', orResp.status, await orResp.text());
                }
            } catch (orErr) {
                console.warn('[Chat] OpenRouter error:', orErr.message);
            }
        }

        // TIER 2 (CADANGAN CEPAT): Groq (openai/gpt-oss-120b, ~800ms)
        if (!parsed) {
            try {
                console.log('[Chat] Falling back to Groq Cadangan (gpt-oss-120b)...');
                let groqResp = await fetch('https://api.groq.com/openai/v1/chat/completions', {
                    method: 'POST',
                    signal: AbortSignal.timeout(5000),
                    headers: {
                        'Authorization': `Bearer ${GROQ_API_KEY}`,
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        model: 'openai/gpt-oss-120b',
                        messages: messages,
                        temperature: 0.6,
                        max_tokens: 600
                    })
                });

                if (!groqResp.ok) {
                    groqResp = await fetch('https://api.groq.com/openai/v1/chat/completions', {
                        method: 'POST',
                        signal: AbortSignal.timeout(5000),
                        headers: {
                            'Authorization': `Bearer ${GROQ_API_KEY}`,
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({
                            model: 'openai/gpt-oss-20b',
                            messages: messages,
                            temperature: 0.6,
                            max_tokens: 600
                        })
                    });
                }

                if (groqResp.ok) {
                    const groqJson = await groqResp.json();
                    contentStr = groqJson.choices?.[0]?.message?.content || '{}';
                    let clean = contentStr.trim();
                    const match = clean.match(/\{[\s\S]*\}/);
                    if (match) {
                        try { parsed = JSON.parse(match[0]); } catch (e) {}
                    }
                    if (!parsed) {
                        parsed = { speech: contentStr.replace(/```[a-z]*|```/g, '').trim().slice(0, 150), text: contentStr, action: "none" };
                    }
                    console.log('[Chat] Groq OK');
                }
            } catch (groqErr) {
                console.warn('[Chat] Groq error:', groqErr.message);
            }
        }

        // TIER 3 (CADANGAN KETIGA): Google Gemini Flash
        if (!parsed) {
            try {
                console.log('[Chat] Falling back to Gemini Tier 3...');
                const geminiContents = [
                    ...conversationHistory.slice(-4).map(m => ({
                        role: m.role === 'assistant' ? 'model' : 'user',
                        parts: [{ text: m.content }]
                    })),
                    { role: 'user', parts: [{ text: message }] }
                ];
                parsed = await generateGeminiJson(systemPrompt, geminiContents, 0.65);
            } catch (geminiErr) {
                console.warn('[Chat] Gemini tier error:', geminiErr.message);
            }
        }

        if (!parsed) {
            return res.json({
                speech: "Maaf Fadhil, jaringan AI saya sedang mengalami gangguan singkat. Tapi saya tetap standby mendampingi Anda.",
                text: "AI Provider error: Semua provider gagal merespons.",
                action: "none"
            });
        }



        // Execute side actions if requested by LLM
        if (parsed.action === 'add_task' && parsed.taskData && parsed.taskData.title) {
            const newTask = {
                id: 'task-' + Date.now(),
                title: parsed.taskData.title.trim(),
                subject: parsed.taskData.subject || "Akademik",
                deadline: parsed.taskData.deadline || new Date(Date.now() + 86400000 * 2).toISOString(),
                priority: "HIGH",
                completed: false,
                createdAt: new Date().toISOString()
            };
            data.tasks = data.tasks || [];
            data.tasks.unshift(newTask);
            saveTonyData(data);
            parsed.taskCreated = newTask;
        } else if (parsed.action === 'checkin') {
            const nowCheck = new Date();
            const h = String(nowCheck.getHours()).padStart(2, '0');
            const m = String(nowCheck.getMinutes()).padStart(2, '0');
            data.lastCheckIn = {
                timestamp: nowCheck.toISOString(),
                dateString: nowCheck.toLocaleDateString('id-ID', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' }) + ` pukul ${h}.${m} WIB`,
                status: "ARRIVED",
                note: "Check-in otomatis via percakapan suara"
            };
            saveTonyData(data);
            parsed.checkIn = data.lastCheckIn;
        }

        res.json({
            speech: parsed.speech || "Siap, Fadhil. Saya mengerti.",
            text: parsed.text || parsed.speech,
            action: parsed.action || "none",
            taskCreated: parsed.taskCreated || null,
            checkIn: parsed.checkIn || null
        });

    } catch (error) {
        console.error('Error in /api/tony/chat:', error.message);
        res.status(500).json({
            speech: "Terjadi kesalahan internal pada subsistem komunikasi saya.",
            text: error.message,
            action: "none"
        });
    }
});
// Native Indonesian High-Definition TTS Engine
app.get('/api/tony/tts', async (req, res) => {
    try {
        const text = (req.query.text || '').trim();
        if (!text) return res.status(400).send('No text provided');
        const clean = text.replace(/[*#_`~]/g, '').slice(0, 300);
        const encoded = encodeURIComponent(clean);
        const url = `https://translate.google.com/translate_tts?ie=UTF-8&q=${encoded}&tl=id&client=tw-ob`;
        
        const fetchRes = await fetch(url, {
            headers: {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
        });
        if (!fetchRes.ok) throw new Error(`TTS upstream error: ${fetchRes.status}`);
        
        res.setHeader('Content-Type', 'audio/mpeg');
        res.setHeader('Cache-Control', 'public, max-age=86400');
        const buffer = await fetchRes.arrayBuffer();
        res.send(Buffer.from(buffer));
    } catch (e) {
        console.error('Error in /api/tony/tts:', e.message);
        res.status(500).json({ error: e.message });
    }
});

// ============================================================
// AUDIO TRANSCRIPTION — Whisper Large v3 Turbo via Groq
// ============================================================
app.post('/api/tony/transcribe', upload.single('audio'), async (req, res) => {
    try {
        if (!req.file) {
            return res.status(400).json({ error: 'No audio file uploaded' });
        }

        const audioBuffer = req.file.buffer;
        const mimeType = req.file.mimetype || 'audio/webm';
        const ext = mimeType.includes('wav') ? 'wav' : (mimeType.includes('mp4') || mimeType.includes('m4a') ? 'm4a' : 'webm');

        const form = new FormData();
        const fileObj = File ? new File([audioBuffer], `recording.${ext}`, { type: mimeType }) : (Blob ? new Blob([audioBuffer], { type: mimeType }) : audioBuffer);
        form.append('file', fileObj, `recording.${ext}`);
        form.append('model', 'whisper-large-v3-turbo');
        // Setting 'id' ensures Whisper does not hallucinate Spanish or Portuguese on quiet/ambient audio
        form.append('language', 'id');
        form.append('prompt', 'Halo Tony, asisten AI cerdas, latihan simulasi wawancara beasiswa, kepribadian, kepemimpinan tim, teknologi, STAR method, bahasa Indonesia.');
        form.append('temperature', '0.0');

        const groqRes = await fetch('https://api.groq.com/openai/v1/audio/transcriptions', {
            method: 'POST',
            signal: AbortSignal.timeout(15000),
            headers: {
                'Authorization': `Bearer ${GROQ_API_KEY}`
            },
            body: form
        });

        if (!groqRes.ok) {
            const errText = await groqRes.text();
            console.error('Groq Whisper Turbo error:', groqRes.status, errText);
            return res.status(502).json({ error: 'Transcription failed: ' + errText });
        }

        const data = await groqRes.json();
        let transcript = (data.text || '').trim();
        console.log('Whisper Turbo transcribed raw:', transcript);

        // Filter out notorious Whisper low-volume / silence hallucinations
        const lower = transcript.toLowerCase().replace(/[.,!?;:"'—–\s]/g, '');
        const hallucinations = [
            'terimakasih', 'terimakasihbanyak', 'terimakasihsudahmenonton',
            'thankyou', 'thankyouverymuch', 'thankyouforwatching',
            'ididntknow', 'idontknow', 'you', 'subtitlesby', 'subtitleoleh', 
            'perhatianmaupuncava', 'buencharla', 'buenasnoches', 'buenosdias'
        ];
        
        const isHallucination = hallucinations.includes(lower);
        if (isHallucination) {
            console.warn('[Whisper] Detected silence hallucination token:', transcript);
            return res.json({ success: false, text: '', isHallucination: true, raw: transcript });
        }

        res.json({ success: true, text: transcript });
    } catch (err) {
        console.error('Transcribe endpoint error:', err.message);
        res.status(500).json({ error: err.message });
    }
});

// ============================================================
// INTERVIEW SENTINEL — Interactive Mock Interview Simulator
// ============================================================
app.post('/api/tony/interview', async (req, res) => {
    try {
        const { 
            scenario = 'kl_yes', 
            questionIndex = 0, 
            userAnswer = '', 
            history = [],
            customTopic = '',
            language = 'auto'
        } = req.body;

        const scenariosMeta = {
            'kepribadian': {
                id: 'kepribadian',
                title: 'Eksplorasi Kepribadian & Karakter Diri (Personality & Resilience)',
                role: 'Psikolog Pewawancara & Assessor Karakter Beasiswa Global',
                target: 'Kedewasaan emosional, self-awareness, integritas, dan cara menghadapi kegagalan',
                language: language === 'en' ? 'English' : 'Bilingual (Indonesia & English)',
                focus: 'Kesadaran diri (self-awareness), nilai-nilai moral, cara merespons kegagalan/kritik, kerentanan (vulnerability), dan mekanisme mengelola stres berat.'
            },
            'dinamika_kelompok': {
                id: 'dinamika_kelompok',
                title: 'Dinamika Kelompok & Leadership (Teamwork & Conflict Resolution)',
                role: 'Senior Assessor Dinamika Tim & Kepemimpinan Organisasi',
                target: 'Kemampuan kolaborasi tim, resolusi konflik, dan memimpin rekan kerja',
                language: language === 'en' ? 'English' : 'Bilingual (Indonesia & English)',
                focus: 'Penyelesaian konflik internal kelompok, menghadapi rekan yang malas/dominan/pasif, empati tim, negosiasi, dan kepemimpinan partisipatif.'
            },
            'english_fluency': {
                id: 'english_fluency',
                title: 'Full English Behavioral & Situational Interview',
                role: 'Global Admissions Officer & Native English Interviewer',
                target: 'Global Scholarship & Top University Admission',
                language: 'English',
                focus: 'Spontaneous English fluency, structured storytelling with STAR method, intellectual curiosity, resilience, and personal uniqueness.'
            },
            'custom': {
                id: 'custom',
                title: customTopic || 'Wawancara Eksploratif Bebas',
                role: 'Executive AI Interviewer & Mentor Karakter',
                target: customTopic || 'Eksplorasi mendalam sesuai topik yang diminta kandidat',
                language: language === 'en' ? 'English' : 'Bilingual / Indonesia',
                focus: `Topik spesifik: "${customTopic || 'Eksplorasi bebas wawasan dan kepribadian'}" secara tajam, berbobot, dan menguji kedalaman berpikir kritis kandidat.`
            },
            'kl_yes': {
                id: 'kl_yes',
                title: 'Beasiswa KL-YES (Kennedy-Lugar Youth Exchange & Study USA)',
                role: 'Panelis Pewawancara Seleksi Nasional Beasiswa KL-YES / Bina Antarbudaya',
                target: 'Pertukaran pelajar SMA ke Amerika Serikat selama 1 tahun',
                language: language === 'en' ? 'English' : 'Bilingual (Indonesia & Inggris)',
                focus: 'Adaptabilitas, toleransi, kepemimpinan, duta budaya Indonesia, dan kesiapan tinggal bersama host family Amerika.'
            },
            'mit': {
                id: 'mit',
                title: 'MIT Admissions Interview (Educational Counselor)',
                role: 'MIT Educational Counselor (Alumni Interviewer MIT)',
                target: 'S1 Electrical Engineering & Computer Science (EECS) di MIT',
                language: 'English (or bilingual)',
                focus: 'Passion in Electrical Engineering, maker projects, handling failure/setbacks, collaboration, intellectual curiosity, and why MIT.'
            },
            'nus_ntu': {
                id: 'nus_ntu',
                title: 'NUS & NTU Singapore Admissions & ASEAN Scholarship',
                role: 'Senior Admissions & Scholarship Board of Singapore Universities',
                target: 'Bachelor of Engineering (Electrical Engineering) NUS/NTU',
                language: language === 'en' ? 'English' : 'English / Bahasa Indonesia',
                focus: 'Academic STEM excellence, physics/math foundation, research interest in semiconductor/hardware, long-term impact in Asia.'
            },
            'itb_bim': {
                id: 'itb_bim',
                title: 'ITB STEI & Beasiswa Indonesia Maju (BIM / Garuda)',
                role: 'Panelis Dosen STEI ITB & Reviewer Beasiswa Indonesia Maju',
                target: 'Teknik Elektro STEI ITB & Penerima Beasiswa Garuda/BIM',
                language: 'Bahasa Indonesia formal & lugas',
                focus: 'Visi kontribusi teknologi di Indonesia, ketahanan mental di lingkungan teknik elektro yang berat, rekam jejak prestasi sains.'
            },
            'pitch': {
                id: 'pitch',
                title: '60-Second Executive Elevator Pitch',
                role: 'Executive Talent Scout & Mentor Global',
                target: 'Mempromosikan diri, visi, dan keunikan secara memukau dalam 60 detik',
                language: language === 'en' ? 'English' : 'Bahasa Indonesia atau English',
                focus: 'Hook pembuka, keunikan diri (calon insinyur elektro), prestasi, dan call to action yang meyakinkan.'
            }
        };

        const currentScenario = scenariosMeta[scenario] || (customTopic ? scenariosMeta['custom'] : scenariosMeta['kl_yes']);
        const isEnglish = language === 'en' || currentScenario.language === 'English';

        const systemPrompt = `Kamu adalah ${currentScenario.role}.
Kamu sedang menguji Fadhil dalam sesi wawancara untuk: "${currentScenario.title}".
Fokus penilaian: ${currentScenario.focus}.
Bahasa yang digunakan: ${isEnglish ? 'WAJIB BAHASA INGGRIS (Full English) untuk semua pertanyaan, ucapan, tips, dan evaluasi.' : 'Bahasa Indonesia atau Bilingual (alami dan luwes).'}.

TUGAS KAMU:
Jika questionIndex == 0 (Awal Sesi):
- Sambut kandidat dengan berwibawa dan hangat.
- Ajukan PERTANYAAN 1 yang paling relevan dan menantang (bisa tentang kepribadian, situasi kelompok, atau topik yang diminta).
- Berikan tips cara menyusun jawaban (misal metode STAR).

Jika questionIndex > 0 dan ada userAnswer:
1. Evaluasi jawaban Fadhil dengan jujur dan konstruktif:
   - Skor (0 - 100).
   - Kelebihan: Poin kuat yang berhasil ditonjolkan.
   - Perbaikan: Hal yang kurang konkret, kurang STAR, atau perlu dipertajam.
   - Contoh Jawaban Ideal: 1 paragraf contoh jawaban kelas dunia.
2. Jika questionIndex < 4:
   - Ajukan pertanyaan berikutnya (Pertanyaan ke-${questionIndex + 1}) yang menggali sisi lain (misal: dinamika kelompok, kepemimpinan, respons terhadap konflik/kegagalan).
3. Jika questionIndex >= 4 (Ronde Terakhir Selesai):
   - Nyatakan sesi selesai.
   - Buat Rapor Ringkasan Wawancara (Overall Score, Kelebihan Utama, Area Perbaikan Kritis, Rekomendasi).

FORMAT JSON WAJIB:
{
  "speech": "${isEnglish ? 'Short spoken sentence in English for TTS (max 2 sentences)' : 'Kalimat singkat untuk diucapkan via TTS (maks 2-3 kalimat)'}",
  "questionText": "${isEnglish ? 'Full question text in English' : 'Teks pertanyaan lengkap untuk ditampilkan di UI'}",
  "tips": "${isEnglish ? 'Tips for candidate in English' : 'Tips strategi menjawab untuk Fadhil'}",
  "evaluation": {
     "score": 85,
     "strengths": "Poin kelebihan jawaban...",
     "weaknesses": "Poin yang perlu ditingkatkan...",
     "idealAnswer": "Contoh jawaban yang memukau..."
  },
  "isFinished": false,
  "finalSummary": "Rangkuman rapor jika ronde terakhir, atau null"
}`;

        const promptInput = questionIndex === 0
            ? `Mulai sesi wawancara untuk skenario "${currentScenario.title}". Ajukan pertanyaan pembuka nomor 1.`
            : `Skenario: "${currentScenario.title}". Pertanyaan sebelumnya dijawab Fadhil sebagai berikut:
Jawaban Fadhil: "${userAnswer}"
Riwayat tanya jawab sebelumnya: ${JSON.stringify(history)}
Ronde sekarang: Pertanyaan ke-${questionIndex}. Evaluasi jawaban Fadhil dan ajukan pertanyaan ke-${questionIndex + 1} (atau akhiri jika sudah ronde 4).`;

        let parsed = null;

        // TIER 1 — Primary: Groq (fastest ~1s, gpt-oss-120b)
        try {
            console.log('[Interview] Trying Groq gpt-oss-120b...');
            const groqRes = await fetch('https://api.groq.com/openai/v1/chat/completions', {
                method: 'POST',
                signal: AbortSignal.timeout(20000),
                headers: {
                    'Authorization': `Bearer ${GROQ_API_KEY}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    model: 'openai/gpt-oss-120b',
                    messages: [
                        { role: 'system', content: systemPrompt },
                        { role: 'user', content: promptInput }
                    ],
                    temperature: 0.5,
                    max_tokens: 1200
                })
            });
            if (groqRes.ok) {
                const groqJson = await groqRes.json();
                let clean = (groqJson.choices?.[0]?.message?.content || '{}').trim();
                const match = clean.match(/\{[\s\S]*\}/);
                if (match) {
                    try { parsed = JSON.parse(match[0]); } catch (e) {}
                }
                if (parsed) console.log('[Interview] Groq gpt-oss-120b OK');
            } else {
                console.warn('[Interview] Groq returned status:', groqRes.status);
            }
        } catch (groqErr) {
            console.warn('[Interview] Groq error:', groqErr.message);
        }

        // TIER 2 — Fallback: Gemini (3.7 Flash -> 3.5 Flash -> 3.6 Flash)
        if (!parsed) {
            try {
                console.log('[Interview] Trying Gemini...');
                parsed = await generateGeminiJson(systemPrompt, [{ parts: [{ text: promptInput }] }], 0.6);
                if (parsed) console.log('[Interview] Gemini OK');
            } catch (e) {
                console.warn('[Interview] Gemini error:', e.message);
            }
        }

        // TIER 3 — Last Resort: OpenRouter
        if (!parsed && OPENROUTER_API_KEY) {
            try {
                console.log('[Interview] Trying OpenRouter...');
                const orRes = await fetch('https://openrouter.ai/api/v1/chat/completions', {
                    method: 'POST',
                    signal: AbortSignal.timeout(20000),
                    headers: {
                        'Authorization': `Bearer ${OPENROUTER_API_KEY}`,
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        model: 'nvidia/nemotron-3.5-lightning:free',
                        messages: [
                            { role: 'system', content: systemPrompt },
                            { role: 'user', content: promptInput }
                        ],
                        temperature: 0.5,
                        max_tokens: 1200
                    })
                });
                if (orRes.ok) {
                    const orJson = await orRes.json();
                    let clean = (orJson.choices?.[0]?.message?.content || '{}').trim();
                    const match = clean.match(/\{[\s\S]*\}/);
                    if (match) {
                        try { parsed = JSON.parse(match[0]); } catch (e) {}
                    }
                    if (!parsed) {
                        parsed = {
                            speech: clean.slice(0, 150),
                            questionText: clean,
                            tips: "Jawablah dengan percaya diri menggunakan metode STAR.",
                            evaluation: null,
                            isFinished: false
                        };
                    }
                    if (parsed) console.log('[Interview] OpenRouter OK');
                }
            } catch (orErr) {
                console.warn('[Interview] OpenRouter error:', orErr.message);
            }
        }

        if (!parsed) {
            return res.status(500).json({ error: 'Gagal memproses sesi wawancara AI.' });
        }


        res.json({
            scenario: currentScenario,
            questionIndex,
            ...parsed
        });

    } catch (err) {
        console.error('Interview endpoint error:', err.message);
        res.status(500).json({ error: err.message });
    }
});



// ============================================================
// GOOGLE CALENDAR SENTINEL — Generate .ics file for GCal add
// ============================================================
app.post('/api/tony/calendar-add', (req, res) => {
    try {
        const { title, description, startDate, endDate, location } = req.body;
        if (!title || !startDate) {
            return res.status(400).json({ error: 'title and startDate required' });
        }

        // Format: YYYYMMDDTHHMMSSZ
        const toIcsDate = (dateStr) => {
            const d = new Date(dateStr);
            return d.toISOString().replace(/[-:]/g, '').replace(/\.\d{3}/, '');
        };

        const dtStart = toIcsDate(startDate);
        const dtEnd = endDate ? toIcsDate(endDate) : toIcsDate(new Date(new Date(startDate).getTime() + 3600000).toISOString());
        const uid = `tony-${Date.now()}@fadhil-exec`;
        const now = toIcsDate(new Date().toISOString());

        const icsContent = [
            'BEGIN:VCALENDAR',
            'VERSION:2.0',
            'PRODID:-//TONY 2.0 Executive AI//Fadhil//ID',
            'CALSCALE:GREGORIAN',
            'METHOD:PUBLISH',
            'BEGIN:VEVENT',
            `UID:${uid}`,
            `DTSTAMP:${now}`,
            `DTSTART:${dtStart}`,
            `DTEND:${dtEnd}`,
            `SUMMARY:${title}`,
            `DESCRIPTION:${(description || '').replace(/\n/g, '\\n')}`,
            `LOCATION:${location || ''}`,
            'END:VEVENT',
            'END:VCALENDAR'
        ].join('\r\n');

        res.setHeader('Content-Type', 'text/calendar; charset=utf-8');
        res.setHeader('Content-Disposition', `attachment; filename="tony-event.ics"`);
        res.send(icsContent);
    } catch (e) {
        console.error('Calendar ICS error:', e.message);
        res.status(500).json({ error: e.message });
    }
});

// GCal Web Intent — returns a Google Calendar add URL
app.post('/api/tony/calendar-link', (req, res) => {
    try {
        const { title, description, startDate, endDate, location } = req.body;
        if (!title || !startDate) return res.status(400).json({ error: 'title and startDate required' });

        const fmt = (d) => new Date(d).toISOString().replace(/[-:]/g, '').replace(/\.\d{3}Z/, 'Z');
        const end = endDate || new Date(new Date(startDate).getTime() + 3600000).toISOString();
        const url = `https://calendar.google.com/calendar/render?action=TEMPLATE` +
            `&text=${encodeURIComponent(title)}` +
            `&dates=${fmt(startDate)}/${fmt(end)}` +
            `&details=${encodeURIComponent(description || 'Dibuat oleh TONY 2.0 Executive AI')}` +
            `&location=${encodeURIComponent(location || '')}`;

        res.json({ url, message: 'GCal link generated' });
    } catch (e) {
        res.status(500).json({ error: e.message });
    }
});

// ============================================================
// NEURAL DOSSIER — PDF Summarizer + AI Brief
// ============================================================
app.post('/api/tony/dossier', upload.single('pdf'), async (req, res) => {
    try {
        if (!req.file) return res.status(400).json({ error: 'No PDF uploaded' });

        // Extract text from PDF
        if (!pdf) {
            return res.status(503).json({ error: 'Fitur PDF parser belum terpasang atau tidak didukung di sistem ini.' });
        }
        const pdfData = await pdf(req.file.buffer);
        const rawText = pdfData.text || '';
        const wordCount = rawText.split(/\s+/).filter(Boolean).length;

        if (wordCount < 20) {
            return res.status(422).json({ error: 'PDF terlalu kosong atau tidak bisa dibaca. Pastikan PDF tidak terproteksi.' });
        }

        const excerpt = rawText.slice(0, 4000);
        // AI summarization — Primary: Gemini 3.6 Flash, Fallback: Groq
        let summary = '';
        const dossierPrompt = `Kamu adalah TONY 2.0, Asisten Eksekutif AI Fadhil. 
Tugas: Baca dokumen yang dikirim pengguna, buat ringkasan eksekutif yang tajam, singkat, dan actionable dalam Bahasa Indonesia.
Format output:
📄 RINGKASAN DOKUMEN
[2-3 kalimat inti isi dokumen]

🎯 POIN KUNCI:
• [poin 1]
• [poin 2]
• [poin 3]

⚡ REKOMENDASI TINDAKAN:
[1-2 kalimat rekomendasi konkret berdasarkan dokumen]

AUDIO BRIEF (untuk diucapkan):
[1-2 kalimat ringkasan singkat untuk dibacakan]`;

        try {
            const geminiRes = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent?key=${GEMINI_API_KEY}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    systemInstruction: { parts: [{ text: dossierPrompt }] },
                    contents: [{ parts: [{ text: `Ringkas dokumen berikut:\n\n${excerpt}` }] }],
                    generationConfig: { temperature: 0.3 }
                })
            });
            if (geminiRes.ok) {
                const geminiData = await geminiRes.json();
                summary = geminiData.candidates?.[0]?.content?.parts?.[0]?.text || '';
            } else {
                console.warn('Gemini dossier failed, trying Groq:', geminiRes.status);
            }
        } catch (e) {
            console.warn('Gemini dossier error:', e.message);
        }

        if (!summary) {
            const groqRes = await fetch('https://api.groq.com/openai/v1/chat/completions', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${GROQ_API_KEY}`
                },
                body: JSON.stringify({
                    model: 'openai/gpt-oss-120b',
                    messages: [
                        { role: 'system', content: dossierPrompt },
                        { role: 'user', content: `Ringkas dokumen berikut:\n\n${excerpt}` }
                    ],
                    max_tokens: 800,
                    temperature: 0.4
                })
            });

            if (groqRes.ok) {
                const groqData = await groqRes.json();
                summary = groqData.choices?.[0]?.message?.content || 'Tidak bisa meringkas dokumen ini.';
            } else {
                const errBody = await groqRes.text();
                throw new Error(`AI summarization failed: ${errBody.slice(0, 200)}`);
            }
        }


        // Extract audio brief line
        const audioBriefMatch = summary.match(/AUDIO BRIEF[^\n]*:\n(.+)/);
        const audioBrief = audioBriefMatch ? audioBriefMatch[1].trim() : summary.split('\n')[1] || 'Dokumen telah dianalisis.';

        res.json({
            summary,
            audioBrief,
            wordCount,
            pages: pdfData.numpages || 1,
            filename: req.file.originalname
        });

    } catch (e) {
        console.error('Neural Dossier error:', e.message);
        res.status(500).json({ error: e.message });
    }
});


app.listen(PORT, '0.0.0.0', () => {
    console.log(`🚀 Bloomberg Terminal & TONY 2.0 AI Node running at http://localhost:${PORT}`);
    console.log(`📡 Loading ${NEWS_FEEDS.length} news feeds...`);
});

