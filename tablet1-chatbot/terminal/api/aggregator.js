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
  const px = +base.price.toFixed(2);
  return U.tick({
    symbol: sym,
    asset: 'equity',
    price: px,
    bid: +(px - 0.15).toFixed(2),
    ask: +(px + 0.15).toFixed(2),
    vol: base.vol,
    high: base.high,
    low: base.low,
    prevClose: base.prevClose,
    ts: Date.now(),
    source: 'otc-indicative',
    mode: 'EOD'
  });
}

function otcKline(sym, interval = '1h', limit = 300) {
  return { symbol: sym, interval, source: 'otc-indicative', mode: 'N/A', candles: [] };
}

const DEFAULT_USD_IDR = 18218;

async function fetchErApiRates() {
  return U.cached('fx:erapi:usd', 180000, async () => {
    try {
      const j = await U.getJson('https://open.er-api.com/v6/latest/USD', { provider: 'open-er-api', timeout: 6000, mode: 'LIVE' });
      if (j && j.rates && Number(j.rates.IDR) > 10000) return { rates: j.rates, source: 'open-er-api' };
    } catch {}
    const f = await U.getJson('https://api.frankfurter.app/latest?from=USD', { provider: 'frankfurter', timeout: 6000, mode: 'LIVE' });
    if (f && f.rates && Number(f.rates.IDR) > 10000) return { rates: f.rates, source: 'frankfurter' };
    throw new Error('fx fallback providers unavailable');
  });
}

async function fxFallbackQuote(sym) {
  const clean = String(sym || '').toUpperCase().replace(/=X$/, '');
  const { rates, source } = await fetchErApiRates();
  let px = null;
  if (clean.startsWith('USD') && clean.length === 6) {
    px = Number(rates[clean.slice(3)]);
  } else if (clean.endsWith('USD') && clean.length === 6) {
    const r = Number(rates[clean.slice(0, 3)]);
    if (r > 0) px = 1 / r;
  } else if (clean.length === 3 && rates[clean]) {
    px = Number(rates[clean]);
  }
  if (!Number.isFinite(px) || px <= 0) throw new Error('fx pair not in fallback: ' + sym);
  return U.tick({ symbol: sym, asset: 'forex', price: px, prevClose: px, high: px, low: px, ts: Date.now(), source, mode: 'LIVE' });
}

async function getLiveUsdIdrRate(fallback = DEFAULT_USD_IDR) {
  try {
    const q = await U.cached('fx:usdidr:live', 120000, async () => {
      try {
        const y = await yahoo.quote('USDIDR=X');
        if (y && Number(y.price) > 10000 && Number(y.price) < 50000) return Number(y.price);
      } catch {}
      try {
        const fx = await fxFallbackQuote('USDIDR=X');
        if (fx && Number(fx.price) > 10000 && Number(fx.price) < 50000) return Number(fx.price);
      } catch {}
      return null;
    });
    if (Number.isFinite(q) && q > 10000 && q < 50000) return q;
  } catch {}
  return Number(fallback) > 10000 ? Number(fallback) : DEFAULT_USD_IDR;
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
      if (providerSym === 'USDIDR=X' && !(Number(q.price) > 10000 && Number(q.price) < 50000)) {
        throw new Error('invalid yahoo USDIDR price');
      }
      return { ...q, symbol: sym };
    } catch (e) { errs.push('yahoo: ' + e.message); }
    if (providerSym.endsWith('=X')) {
      try { const q = await fxFallbackQuote(providerSym); return { ...q, symbol: sym }; } catch (e) { errs.push('fx-fallback: ' + e.message); }
    }
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
module.exports = { quote, kline, search, isCrypto, resolveProviderSym, getLiveUsdIdrRate, DEFAULT_USD_IDR, OTC_DESK };
