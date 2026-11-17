'use strict';
const WebSocket = require('ws');
const U = require('./../util');

const REST = {
  spot: ['https://api.binance.com', 'https://data-api.binance.vision', 'https://api1.binance.com', 'https://api-gcp.binance.com'],
  futures: ['https://fapi.binance.com', 'https://fapi1.binance.com'],
};
const WSH = {
  spot: ['wss://stream.binance.com:9443/stream', 'wss://data-stream.binance.vision/stream', 'wss://stream.binance.com:443/stream'],
  futures: ['wss://fstream.binance.com/stream'],
};
const PROV = { spot: 'binance-spot', futures: 'binance-futures' };
const FUTURES_ONLY_TTL_MS = 10 * 60 * 1000;
const futuresOnlyPairs = new Map(); // pair -> expiresAtMs

function isKnownFuturesOnly(pair) {
  const exp = futuresOnlyPairs.get(pair);
  if (!exp) return false;
  if (exp > Date.now()) return true;
  futuresOnlyPairs.delete(pair);
  return false;
}
function markFuturesOnly(pair) {
  if (futuresOnlyPairs.size > 500) {
    const now = Date.now();
    for (const [k, exp] of futuresOnlyPairs) if (exp <= now) futuresOnlyPairs.delete(k);
  }
  futuresOnlyPairs.set(pair, Date.now() + FUTURES_ONLY_TTL_MS);
}

// "BTCUSDT.P" -> {market:'futures', pair:'BTCUSDT'}
function parse(symbol, marketHint) {
  let s = String(symbol).toUpperCase();
  let market = marketHint === 'futures' ? 'futures' : 'spot';
  if (s.endsWith('.P')) { market = 'futures'; s = s.slice(0, -2); }
  else if (!marketHint && isKnownFuturesOnly(s)) { market = 'futures'; }
  return { market, pair: s, symbol: market === 'futures' ? s + '.P' : s };
}
const get = (market, pathq) => U.getJsonFallback(REST[market], pathq, { provider: PROV[market], mode: 'LIVE' });
const prefix = m => (m === 'futures' ? '/fapi/v1' : '/api/v3');

async function withFuturesFallback(symbol, marketHint, fn) {
  const p = parse(symbol, marketHint);
  try {
    return await fn(p);
  } catch (err) {
    const rawUp = String(symbol).toUpperCase();
    if (marketHint === 'futures' || rawUp.endsWith('.P') || p.market !== 'spot') throw err;
    const pFut = { market: 'futures', pair: p.pair, symbol: p.pair + '.P' };
    const res = await fn(pFut);
    markFuturesOnly(pFut.pair);
    return res;
  }
}

function fromTicker24(market, symbol, t, book) {
  return U.tick({
    symbol, asset: market === 'futures' ? 'crypto-perp' : 'crypto', price: t.lastPrice, bid: book ? book.bidPrice : t.bidPrice, ask: book ? book.askPrice : t.askPrice,
    vol: t.volume, chg: t.priceChange, chgPct: t.priceChangePercent, high: t.highPrice, low: t.lowPrice, open: t.openPrice, prevClose: t.prevClosePrice || t.openPrice,
    ts: t.closeTime || Date.now(), source: PROV[market], mode: 'LIVE',
  });
}

async function quote(symbol, marketHint) {
  return withFuturesFallback(symbol, marketHint, async p => {
    const [t, b] = await Promise.all([
      U.cached(`bn24:${p.market}:${p.pair}`, 1000, () => get(p.market, `${prefix(p.market)}/ticker/24hr?symbol=${p.pair}`)),
      U.cached(`bnbk:${p.market}:${p.pair}`, 1000, () => get(p.market, `${prefix(p.market)}/ticker/bookTicker?symbol=${p.pair}`)).catch(() => null),
    ]);
    return fromTicker24(p.market, p.symbol, t, b);
  });
}

async function kline(symbol, interval = '1h', limit = 300, marketHint) {
  const ivNorm = interval === '1mo' ? '1M' : ({ '1d': '1d', '1w': '1w' }[interval] || interval);
  const fetchBars = async (mkt, barIv) => {
    const p = parse(symbol, mkt);
    const rows = await U.cached(
      `bnk:${mkt}:${p.pair}:${barIv}:${limit}`,
      barIv === '1s' ? 900 : 2000,
      () => get(mkt, `${prefix(mkt)}/klines?symbol=${p.pair}&interval=${barIv}&limit=${Math.min(+limit || 300, 1000)}`)
    );
    return {
      symbol: p.symbol,
      interval: barIv,
      source: PROV[mkt],
      mode: 'LIVE',
      candles: rows.map(r => ({ t: r[0], o: +r[1], h: +r[2], l: +r[3], c: +r[4], v: +r[5] })),
    };
  };

  if (ivNorm === '1s') {
    // Binance Futures lacks 1s klines; try Spot 1s first (unless futures-only), otherwise fall back to Futures 1m.
    const p0 = parse(symbol, marketHint);
    if (!isKnownFuturesOnly(p0.pair)) {
      try {
        return await fetchBars('spot', '1s');
      } catch (_) { /* fall through to futures 1m */ }
    }
    const res1m = await fetchBars('futures', '1m');
    if (!marketHint && !String(symbol).toUpperCase().endsWith('.P')) markFuturesOnly(p0.pair);
    return res1m;
  }

  return withFuturesFallback(symbol, marketHint, p => fetchBars(p.market, ivNorm));
}
async function depth(symbol, limit = 20, marketHint) {
  const lim = [5, 10, 20, 50, 100, 500].find(x => x >= limit) || 100;
  return withFuturesFallback(symbol, marketHint, async p => {
    const d = await get(p.market, `${prefix(p.market)}/depth?symbol=${p.pair}&limit=${lim}`);
    return { symbol: p.symbol, bids: d.bids.map(x => [+x[0], +x[1]]), asks: d.asks.map(x => [+x[0], +x[1]]), ts: d.E || d.T || Date.now(), source: PROV[p.market], mode: 'LIVE' };
  });
}
async function trades(symbol, limit = 50, marketHint) {
  return withFuturesFallback(symbol, marketHint, async p => {
    const r = await get(p.market, `${prefix(p.market)}/trades?symbol=${p.pair}&limit=${Math.min(+limit || 50, 100)}`);
    return r.reverse().map(t => ({ id: t.id, price: +t.price, qty: +t.qty, side: t.isBuyerMaker ? 'SELL' : 'BUY', ts: t.time, source: PROV[p.market], mode: 'LIVE' }));
  });
}
async function movers(market = 'spot', dir = 'gainers', limit = 20) {
  const all = await U.cached(`bnall:${market}`, 10000, () => get(market, `${prefix(market)}/ticker/24hr`));
  const suffix = market === 'futures' ? '.P' : '';
  let arr = all.filter(t => t.symbol.endsWith('USDT') && +t.quoteVolume > 2e6 && +t.lastPrice > 0);
  const key = dir === 'active' ? t => -(+t.quoteVolume) : dir === 'losers' ? t => +t.priceChangePercent : t => -(+t.priceChangePercent);
  arr.sort((a, b) => key(a) - key(b));
  return arr.slice(0, Math.min(+limit || 20, 100)).map(t => fromTicker24(market, t.symbol + suffix, t, null));
}
async function allSymbols() {
  const r = await Promise.all(['spot', 'futures'].map(m => U.cached('bnx:' + m, 3600000, () => get(m, `${prefix(m)}/exchangeInfo`)).catch(() => null)));
  const out = [];
  if (r[0]) r[0].symbols.filter(s => s.status === 'TRADING').forEach(s => out.push({ symbol: s.symbol, name: `${s.baseAsset}/${s.quoteAsset} spot`, asset: 'crypto', exchange: 'BINANCE', source: 'binance-spot' }));
  if (r[1]) r[1].symbols.filter(s => s.status === 'TRADING' && s.contractType === 'PERPETUAL').forEach(s => out.push({ symbol: s.symbol + '.P', name: `${s.baseAsset}/${s.quoteAsset} perp`, asset: 'crypto-perp', exchange: 'BINANCE-FUT', source: 'binance-futures' }));
  return out;
}

// ---------------- streaming ----------------
// One upstream ws per market, refcounted dynamic SUBSCRIBE. Emits normalized messages to handler(channelKey, msg).
class Stream {
  constructor(market, onMsg) {
    this.market = market; this.onMsg = onMsg; this.ws = null; this.want = new Map(); // stream -> refcount
    this.hostIdx = 0; this.backoff = 1000; this.state = {}; this.reqId = 1; this.timer = null; this.closed = false;
  }
  open() {
    if (this.ws || this.closed) return;
    const hosts = WSH[this.market]; const url = hosts[this.hostIdx % hosts.length];
    const ws = new WebSocket(url, { lookup: U.lookup, handshakeTimeout: 10000, headers: { 'User-Agent': 'PYRO-Terminal' } });
    this.ws = ws;
    ws.on('open', () => {
      this.backoff = 1000; U.record(PROV[this.market], true, null, null, 'LIVE');
      const s = [...this.want.keys()]; if (s.length) this.send({ method: 'SUBSCRIBE', params: s, id: this.reqId++ });
    });
    ws.on('message', raw => { try { this.handle(JSON.parse(raw)); } catch (e) {} });
    ws.on('ping', d => { try { ws.pong(d); } catch (e) {} });
    ws.on('error', e => { U.record(PROV[this.market], false, null, e); });
    ws.on('close', () => {
      this.ws = null; U.record(PROV[this.market], false, null, 'ws closed');
      if (this.closed || !this.want.size) return;
      this.hostIdx++; clearTimeout(this.timer);
      this.timer = setTimeout(() => this.open(), this.backoff); this.backoff = Math.min(this.backoff * 2, 30000);
    });
  }
  send(o) { if (this.ws && this.ws.readyState === 1) this.ws.send(JSON.stringify(o)); }
  add(stream) {
    const n = (this.want.get(stream) || 0) + 1; this.want.set(stream, n);
    if (n === 1) { if (this.ws && this.ws.readyState === 1) this.send({ method: 'SUBSCRIBE', params: [stream], id: this.reqId++ }); else this.open(); }
  }
  remove(stream) {
    const n = (this.want.get(stream) || 0) - 1;
    if (n > 0) return this.want.set(stream, n);
    this.want.delete(stream); this.send({ method: 'UNSUBSCRIBE', params: [stream], id: this.reqId++ });
    if (!this.want.size && this.ws) { try { this.ws.close(); } catch (e) {} }
  }
  handle(m) {
    if (!m.stream || !m.data) return;
    const d = m.data; const pair = (d.s || '').toUpperCase(); const sfx = this.market === 'futures' ? '.P' : '';
    const sym = pair + sfx; const src = PROV[this.market]; const asset = this.market === 'futures' ? 'crypto-perp' : 'crypto';
    const e = d.e;
    if (m.stream.endsWith('@bookTicker')) {
      const st = this.state[pair] || (this.state[pair] = {}); st.bid = d.b; st.ask = d.a;
      return; // merged into next 24h ticker push (1s cadence)
    }
    if (e === '24hrTicker') {
      const st = this.state[pair] || {};
      return this.onMsg(`ticker:${sym}`, 'tick', U.tick({ symbol: sym, asset, price: d.c, bid: st.bid, ask: st.ask, vol: d.v, chg: d.p, chgPct: d.P, high: d.h, low: d.l, open: d.o, prevClose: d.x, ts: d.E, source: src, mode: 'LIVE' }));
    }
    if (e === 'kline') {
      const k = d.k; return this.onMsg(`kline:${sym}:${k.i}`, 'kline', { t: k.t, o: +k.o, h: +k.h, l: +k.l, c: +k.c, v: +k.v, closed: k.x, ts: d.E, source: src, mode: 'LIVE' });
    }
    if (e === 'aggTrade') {
      return this.onMsg(`trades:${sym}`, 'trade', { id: d.a, price: +d.p, qty: +d.q, side: d.m ? 'SELL' : 'BUY', ts: d.T, source: src, mode: 'LIVE' });
    }
    if (m.stream.includes('@depth')) {
      const s2 = m.stream.split('@')[0].toUpperCase() + sfx;
      return this.onMsg(`depth:${s2}`, 'depth', { bids: (d.bids || d.b || []).map(x => [+x[0], +x[1]]), asks: (d.asks || d.a || []).map(x => [+x[0], +x[1]]), ts: d.E || d.T || Date.now(), source: src, mode: 'LIVE' });
    }
  }
  close() { this.closed = true; clearTimeout(this.timer); if (this.ws) try { this.ws.close(); } catch (e) {} }
}

// channel -> list of upstream stream names
function streamsFor(channel) {
  const [type, symbol, iv] = channel.split(':');
  const p = parse(symbol); const l = p.pair.toLowerCase();
  if (type === 'ticker') return { market: p.market, streams: [`${l}@ticker`, `${l}@bookTicker`] };
  if (type === 'kline') return { market: p.market, streams: [`${l}@kline_${iv || '1m'}`] };
  if (type === 'depth') return { market: p.market, streams: [`${l}@depth20@100ms`] };
  if (type === 'trades') return { market: p.market, streams: [`${l}@aggTrade`] };
  return null;
}

module.exports = { quote, kline, depth, trades, movers, allSymbols, Stream, streamsFor, parse };
