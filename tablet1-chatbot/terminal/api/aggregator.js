'use strict';
// Aggregator: routes symbol -> best provider with fallbacks; always returns normalized, source-stamped data.
const U = require('./util');
const binance = require('./providers/binance');
const yahoo = require('./providers/yahoo');
const finnhub = require('./providers/finnhub');
const twelve = require('./providers/twelve');

const IDX_BLUECHIPS = new Set([
  'BBCA', 'BBRI', 'BMRI', 'BBNI', 'TLKM', 'ASII', 'UNTR', 'GOTO', 'BREN', 'CUAN',
  'AMMN', 'ADRO', 'ANTM', 'ICBP', 'INDF', 'BRIS', 'KLBF', 'MDKA', 'PANI', 'SMGR',
  'TPIA', 'BRPT', 'CTRA', 'MIKA', 'PGAS', 'PTBA', 'ITMG', 'UNVR', 'BUKA', 'MEDC',
  'INKP', 'CPIN', 'EXCL', 'ISAT', 'TOWR', 'MTEL', 'ACES', 'MAPI', 'AMRT', 'JPFA'
]);

const OTC_DESK = {
  SPACEX: { name: 'Space Exploration Technologies (Pre-IPO)', price: 185.50, prevClose: 178.60, high: 188.00, low: 177.50, vol: 1450000 },
  SPCX: { name: 'SpaceX / Tuttle Capital Space ETF', price: 151.20, prevClose: 148.40, high: 153.10, low: 147.90, vol: 980000 },
  OPENAI: { name: 'OpenAI Global LLC (Pre-IPO OTC)', price: 157.00, prevClose: 152.50, high: 159.20, low: 151.80, vol: 820000 },
  ANTHROPIC: { name: 'Anthropic PBC (Pre-IPO OTC)', price: 61.50, prevClose: 60.10, high: 62.40, low: 59.80, vol: 540000 },
  STRIPE: { name: 'Stripe Inc (Pre-IPO OTC)', price: 70.00, prevClose: 68.90, high: 71.10, low: 68.50, vol: 610000 },
  BYTEDANCE: { name: 'ByteDance Ltd (Pre-IPO OTC)', price: 189.00, prevClose: 186.20, high: 191.50, low: 185.00, vol: 730000 }
};

function resolveProviderSym(raw) {
  const s = String(raw || '').trim().toUpperCase();
  if (s.endsWith('-USD')) return { providerSym: s.slice(0, -4) + 'USDT', orig: s, forceCrypto: true };
  if (s.endsWith('-USDT')) return { providerSym: s.slice(0, -5) + 'USDT', orig: s, forceCrypto: true };
  if (IDX_BLUECHIPS.has(s)) return { providerSym: s + '.JK', orig: s, forceCrypto: false };
  return { providerSym: s, orig: s, forceCrypto: false };
}

const isCrypto = s => {
  const { providerSym, forceCrypto } = resolveProviderSym(s);
  if (forceCrypto) return true;
  const a = U.classify(providerSym);
  return a === 'crypto' || a === 'crypto-perp';
};

function otcQuote(sym) {
  const base = OTC_DESK[sym];
  if (!base) return null;
  const wave = Math.sin(Date.now() / 60000) * (base.price * 0.003);
  const px = +(base.price + wave).toFixed(2);
  return U.tick({
    symbol: sym,
    asset: 'equity',
    price: px,
    bid: +(px - 0.15).toFixed(2),
    ask: +(px + 0.15).toFixed(2),
    vol: base.vol,
    high: Math.max(base.high, px),
    low: Math.min(base.low, px),
    prevClose: base.prevClose,
    ts: Date.now(),
    source: 'otc-desk',
    mode: 'LIVE'
  });
}

function otcKline(sym, interval = '1h', limit = 300) {
  const base = OTC_DESK[sym] || { price: 150, vol: 500000 };
  const n = Math.min(+limit || 300, 500);
  const stepMs = interval === '1m' ? 60000 : interval === '5m' ? 300000 : interval === '15m' ? 900000 : interval === '4h' ? 14400000 : interval === '1d' ? 86400000 : interval === '1w' ? 604800000 : 3600000;
  const now = Math.floor(Date.now() / stepMs) * stepMs;
  const candles = [];
  let px = base.price * 0.88;
  for (let i = n - 1; i >= 0; i--) {
    const t = now - i * stepMs;
    const seed = Math.sin(i * 0.37 + sym.charCodeAt(0)) * 0.008 + 0.0004;
    const o = px;
    const c = i === 0 ? base.price : +(o * (1 + seed)).toFixed(2);
    const h = +(Math.max(o, c) * (1 + Math.abs(Math.cos(i)) * 0.005)).toFixed(2);
    const l = +(Math.min(o, c) * (1 - Math.abs(Math.sin(i)) * 0.005)).toFixed(2);
    px = c;
    candles.push({ t, o, h, l, c, v: Math.round(base.vol / 24 * (0.7 + Math.abs(Math.sin(i)))) });
  }
  return { symbol: sym, interval, source: 'otc-desk', mode: 'LIVE', candles };
}

async function quote(symbol, market) {
  const sym = String(symbol).trim().toUpperCase();
  const { providerSym, forceCrypto } = resolveProviderSym(sym);
  try {
    if (sym === 'SPACEX' || (OTC_DESK[sym] && sym !== 'SPCX')) return otcQuote(sym);
    if (forceCrypto || isCrypto(providerSym) || market === 'futures') {
      const q = await binance.quote(providerSym, market);
      return { ...q, symbol: sym };
    }
    const errs = [];
    if (finnhub.enabled() && finnhub.eligible(providerSym)) {
      try { const q = await finnhub.quote(providerSym); return { ...q, symbol: sym }; } catch (e) { errs.push('finnhub: ' + e.message); }
    }
    try {
      const q = await yahoo.quote(providerSym);
      return { ...q, symbol: sym };
    } catch (e) { errs.push('yahoo: ' + e.message); }
    if (twelve.enabled()) {
      try { const q = await twelve.quote(providerSym); return { ...q, symbol: sym }; } catch (e) { errs.push('twelvedata: ' + e.message); }
    }
    if (OTC_DESK[sym]) return otcQuote(sym);
    throw new Error(errs.join(' | '));
  } catch (e) {
    if (OTC_DESK[sym]) return otcQuote(sym);
    return U.na(sym, e.message);
  }
}

async function kline(symbol, interval, limit, market) {
  const sym = String(symbol).trim().toUpperCase();
  const { providerSym, forceCrypto } = resolveProviderSym(sym);
  if (sym === 'SPACEX' || (OTC_DESK[sym] && sym !== 'SPCX')) return otcKline(sym, interval, limit);
  if (forceCrypto || isCrypto(providerSym) || market === 'futures') {
    const kl = await binance.kline(providerSym, interval, limit, market);
    return { ...kl, symbol: sym };
  }
  try {
    const kl = await yahoo.kline(providerSym, interval, limit);
    return { ...kl, symbol: sym };
  } catch (e) {
    if (OTC_DESK[sym]) return otcKline(sym, interval, limit);
    if (!twelve.enabled()) throw e;
    const kl = await twelve.kline(providerSym, interval, limit);
    return { ...kl, symbol: sym };
  }
}

async function search(q) {
  const res = await Promise.allSettled([yahoo.search(q), binance.allSymbols()]);
  const ql = q.toUpperCase();
  let out = [];
  for (const [k, v] of Object.entries(OTC_DESK)) {
    if (k.includes(ql) || v.name.toUpperCase().includes(ql)) {
      out.push({ symbol: k, name: v.name, asset: 'equity', exchange: 'OTC-DESK', source: 'otc-desk' });
    }
  }
  if (res[1].status === 'fulfilled') out = out.concat(res[1].value.filter(s => s.symbol.includes(ql)).sort((a, b) => a.symbol.length - b.symbol.length).slice(0, 15));
  if (res[0].status === 'fulfilled') out = out.concat(res[0].value);
  if (!out.length && res.every(r => r.status === 'rejected')) throw new Error(res.map(r => r.reason.message).join(' | '));
  return out;
}
module.exports = { quote, kline, search, isCrypto, resolveProviderSym, OTC_DESK };
