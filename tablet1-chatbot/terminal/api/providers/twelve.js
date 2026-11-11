'use strict';
const U = require('../util');
const enc = encodeURIComponent;
const key = () => process.env.TWELVE_KEY || '';
if (!key()) U.setDisabled('twelvedata', 'TWELVE_KEY not set', 'DELAYED');

// Twelve Data symbols: AAPL, EUR/USD, BTC/USD. Convert from Yahoo style.
function toTD(s) {
  if (s.endsWith('=X')) { const p = s.slice(0, -2); return p.length === 6 ? p.slice(0, 3) + '/' + p.slice(3) : null; }
  if (s.startsWith('^') || s.endsWith('=F')) return null;
  return s;
}
async function quote(symbol) {
  if (!key()) throw new Error('TWELVE_KEY not set');
  const td = toTD(symbol); if (!td) throw new Error('symbol unsupported on twelvedata');
  const q = await U.cached('tdq:' + td, 5000, () => U.getJson(`https://api.twelvedata.com/quote?symbol=${enc(td)}&apikey=${key()}`, { provider: 'twelvedata' }));
  if (q.status === 'error' || !q.close) throw new Error(q.message || 'twelvedata no data');
  return U.tick({ symbol, price: q.close, high: q.high, low: q.low, open: q.open, prevClose: q.previous_close, chg: q.change, chgPct: q.percent_change, vol: q.volume, ts: (q.timestamp || 0) * 1000 || Date.now(), source: 'twelvedata', mode: 'DELAYED' });
}
const IV = { '1m': '1min', '5m': '5min', '15m': '15min', '1h': '1h', '4h': '4h', '1d': '1day', '1w': '1week' };
async function kline(symbol, interval = '1h', limit = 300) {
  if (!key()) throw new Error('TWELVE_KEY not set');
  const td = toTD(symbol); if (!td) throw new Error('symbol unsupported on twelvedata');
  const j = await U.cached(`tdk:${td}:${interval}:${limit}`, 15000, () => U.getJson(`https://api.twelvedata.com/time_series?symbol=${enc(td)}&interval=${IV[interval] || '1h'}&outputsize=${Math.min(+limit || 300, 1000)}&apikey=${key()}`, { provider: 'twelvedata' }));
  if (j.status === 'error' || !j.values) throw new Error(j.message || 'twelvedata no data');
  return { symbol, interval, source: 'twelvedata', mode: 'DELAYED', candles: j.values.reverse().map(v => ({ t: Date.parse(v.datetime.replace(' ', 'T') + 'Z'), o: +v.open, h: +v.high, l: +v.low, c: +v.close, v: +v.volume || 0 })) };
}
module.exports = { quote, kline, enabled: () => !!key() };
