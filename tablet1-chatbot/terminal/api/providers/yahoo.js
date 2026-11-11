'use strict';
const U = require('../util');
const H = { Accept: 'application/json' };
const BASES = ['https://query1.finance.yahoo.com', 'https://query2.finance.yahoo.com'];
const enc = encodeURIComponent;

async function chart(symbol, interval, range) {
  return U.cached(`yc:${symbol}:${interval}:${range}`, interval === '1d' && range !== '1d' ? 60000 : 3000, async () => {
    const j = await U.getJsonFallback(BASES, `/v8/finance/chart/${enc(symbol)}?interval=${interval}&range=${range}&includePrePost=false`, { provider: 'yahoo', headers: H, mode: 'DELAYED' });
    const r = j.chart && j.chart.result && j.chart.result[0];
    if (!r) throw new Error((j.chart && j.chart.error && j.chart.error.description) || 'no data for ' + symbol);
    return r;
  });
}

async function quote(symbol) {
  const r = await chart(symbol, '1d', '1d');
  const m = r.meta;
  if (m.regularMarketPrice == null) throw new Error('no price for ' + symbol);
  return U.tick({
    symbol, price: m.regularMarketPrice, vol: m.regularMarketVolume, high: m.regularMarketDayHigh, low: m.regularMarketDayLow,
    prevClose: m.chartPreviousClose != null ? m.chartPreviousClose : m.previousClose, ts: (m.regularMarketTime || 0) * 1000 || Date.now(),
    source: 'yahoo', mode: 'DELAYED', open: null,
  });
}

const MAP = { '1m': ['1m', '1d'], '5m': ['5m', '5d'], '15m': ['15m', '1mo'], '1h': ['60m', '3mo'], '4h': ['60m', '6mo'], '1d': ['1d', '2y'], '1w': ['1wk', '10y'] };
async function kline(symbol, interval = '1h', limit = 300) {
  const [iv, range] = MAP[interval] || MAP['1h'];
  const r = await chart(symbol, iv, range);
  const q = r.indicators.quote[0]; const ts = r.timestamp || [];
  let c = [];
  for (let i = 0; i < ts.length; i++) if (q.close[i] != null && q.open[i] != null) c.push({ t: ts[i] * 1000, o: q.open[i], h: q.high[i], l: q.low[i], c: q.close[i], v: q.volume[i] || 0 });
  if (interval === '4h') { // aggregate 1h -> 4h
    const out = []; for (const x of c) { const b = Math.floor(x.t / 14400000) * 14400000; const l = out[out.length - 1]; if (l && l.t === b) { l.h = Math.max(l.h, x.h); l.l = Math.min(l.l, x.l); l.c = x.c; l.v += x.v; } else out.push({ ...x, t: b }); }
    c = out;
  }
  return { symbol, interval, source: 'yahoo', mode: 'DELAYED', candles: c.slice(-Math.min(+limit || 300, 1000)) };
}

async function search(q) {
  const j = await U.cached('ys:' + q.toLowerCase(), 300000, () => U.getJsonFallback(BASES, `/v1/finance/search?q=${enc(q)}&quotesCount=12&newsCount=0`, { provider: 'yahoo', headers: H }));
  const tm = { EQUITY: 'equity', INDEX: 'index', CURRENCY: 'forex', FUTURE: 'commodity', ETF: 'equity', MUTUALFUND: 'equity', CRYPTOCURRENCY: 'crypto' };
  return (j.quotes || []).filter(x => x.symbol).map(x => ({ symbol: x.symbol, name: x.shortname || x.longname || x.symbol, asset: tm[x.quoteType] || U.classify(x.symbol), exchange: x.exchDisp || x.exchange || null, source: 'yahoo' }));
}

const SCR = { gainers: 'day_gainers', losers: 'day_losers', active: 'most_actives' };
async function movers(dir = 'gainers', limit = 20) {
  const id = SCR[dir] || SCR.gainers;
  const j = await U.cached('ym:' + id, 30000, () => U.getJsonFallback(BASES, `/v1/finance/screener/predefined/saved?scrIds=${id}&count=${Math.min(+limit || 20, 50)}`, { provider: 'yahoo', headers: H }));
  const rs = j.finance && j.finance.result && j.finance.result[0] && j.finance.result[0].quotes;
  if (!rs) throw new Error('screener returned no quotes');
  return rs.map(m => U.tick({ symbol: m.symbol, asset: 'equity', price: m.regularMarketPrice, vol: m.regularMarketVolume, chg: m.regularMarketChange, chgPct: m.regularMarketChangePercent, high: m.regularMarketDayHigh, low: m.regularMarketDayLow, prevClose: m.regularMarketPreviousClose, bid: m.bid, ask: m.ask, ts: (m.regularMarketTime || 0) * 1000 || Date.now(), source: 'yahoo', mode: 'DELAYED' }));
}

module.exports = { quote, kline, search, movers };
