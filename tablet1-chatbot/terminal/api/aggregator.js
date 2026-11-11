'use strict';
// Aggregator: routes symbol -> best provider with fallbacks; always returns normalized, source-stamped data.
const U = require('./util');
const binance = require('./providers/binance');
const yahoo = require('./providers/yahoo');
const finnhub = require('./providers/finnhub');
const twelve = require('./providers/twelve');

const isCrypto = s => { const a = U.classify(s); return a === 'crypto' || a === 'crypto-perp'; };

async function quote(symbol, market) {
  const sym = String(symbol).trim();
  try {
    if (isCrypto(sym) || market === 'futures') return await binance.quote(sym, market);
    const errs = [];
    if (finnhub.enabled() && finnhub.eligible(sym)) { try { return await finnhub.quote(sym); } catch (e) { errs.push('finnhub: ' + e.message); } }
    try { return await yahoo.quote(sym); } catch (e) { errs.push('yahoo: ' + e.message); }
    if (twelve.enabled()) { try { return await twelve.quote(sym); } catch (e) { errs.push('twelvedata: ' + e.message); } }
    throw new Error(errs.join(' | '));
  } catch (e) { return U.na(sym, e.message); }
}
async function kline(symbol, interval, limit, market) {
  if (isCrypto(symbol) || market === 'futures') return binance.kline(symbol, interval, limit, market);
  try { return await yahoo.kline(symbol, interval, limit); }
  catch (e) { if (!twelve.enabled()) throw e; return twelve.kline(symbol, interval, limit); }
}
async function search(q) {
  const res = await Promise.allSettled([yahoo.search(q), binance.allSymbols()]);
  const ql = q.toUpperCase(); let out = [];
  if (res[1].status === 'fulfilled') out = out.concat(res[1].value.filter(s => s.symbol.includes(ql)).sort((a, b) => a.symbol.length - b.symbol.length).slice(0, 15));
  if (res[0].status === 'fulfilled') out = out.concat(res[0].value);
  if (!out.length && res.every(r => r.status === 'rejected')) throw new Error(res.map(r => r.reason.message).join(' | '));
  return out;
}
module.exports = { quote, kline, search, isCrypto };
