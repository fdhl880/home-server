'use strict';
const WebSocket = require('ws');
const U = require('./../util');

const REST = {
  spot: ['https://api.binance.com', 'https://data-api.binance.vision', 'https://api1.binance.com', 'https://api-gcp.binance.com'],
  futures: ['https://fapi.binance.com'],
};
const WSH = {
  spot: ['wss://stream.binance.com:9443/stream', 'wss://data-stream.binance.vision/stream', 'wss://stream.binance.com:443/stream'],
  futures: ['wss://fstream.binance.com/stream'],
};
const PROV = { spot: 'binance-spot', futures: 'binance-futures' };

// "BTCUSDT.P" -> {market:'futures', pair:'BTCUSDT'}
function parse(symbol, marketHint) {
  let s = String(symbol).toUpperCase();
  let market = marketHint === 'futures' ? 'futures' : 'spot';
  if (s.endsWith('.P')) { market = 'futures'; s = s.slice(0, -2); }
  return { market, pair: s, symbol: market === 'futures' ? s + '.P' : s };
}
const get = (market, pathq) => U.getJsonFallback(REST[market], pathq, { provider: PROV[market], mode: 'LIVE' });
const prefix = m => (m === 'futures' ? '/fapi/v1' : '/api/v3');

function fromTicker24(market, symbol, t, book) {
  return U.tick({
    symbol, asset: market === 'futures' ? 'crypto-perp' : 'crypto', price: t.lastPrice, bid: book ? book.bidPrice : t.bidPrice, ask: book ? book.askPrice : t.askPrice,
    vol: t.volume, chg: t.priceChange, chgPct: t.priceChangePercent, high: t.highPrice, low: t.lowPrice, open: t.openPrice, prevClose: t.prevClosePrice || t.openPrice,
    ts: t.closeTime || Date.now(), source: PROV[market], mode: 'LIVE',
  });
}

async function quote(symbol, marketHint) {
  const p = parse(symbol, marketHint);
  const [t, b] = await Promise.all([
    U.cached(`bn24:${p.market}:${p.pair}`, 1000, () => get(p.market, `${prefix(p.market)}/ticker/24hr?symbol=${p.pair}`)),
    U.cached(`bnbk:${p.market}:${p.pair}`, 1000, () => get(p.market, `${prefix(p.market)}/ticker/bookTicker?symbol=${p.pair}`)).catch(() => null),
  ]);
  return fromTicker24(p.market, p.symbol, t, b);
}

async function kline(symbol, interval = '1h', limit = 300, marketHint) {
  const p = parse(symbol, marketHint);
  const iv = { '1d': '1d', '1w': '1w' }[interval] || interval;
  const rows = await U.cached(`bnk:${p.market}:${p.pair}:${iv}:${limit}`, 2000, () => get(p.market, `${prefix(p.market)}/klines?symbol=${p.pair}&interval=${iv}&limit=${Math.min(+limit || 300, 1000)}`));
  return { symbol: p.symbol, interval, source: PROV[p.market], mode: 'LIVE', candles: rows.map(r => ({ t: r[0], o: +r[1], h: +r[2], l: +r[3], c: +r[4], v: +r[5] })) };
}
async function depth(symbol, limit = 20) {
  const p = parse(symbol);
  const lim = [5, 10, 20, 50, 100, 500].find(x => x >= limit) || 100;
  const d = await get(p.market, `${prefix(p.market)}/depth?symbol=${p.pair}&limit=${lim}`);
  return { symbol: p.symbol, bids: d.bids.map(x => [+x[0], +x[1]]), asks: d.asks.map(x => [+x[0], +x[1]]), ts: d.E || d.T || Date.now(), source: PROV[p.market], mode: 'LIVE' };
}
async function trades(symbol, limit = 50) {
  const p = parse(symbol);
  const r = await get(p.market, `${prefix(p.market)}/trades?symbol=${p.pair}&limit=${Math.min(+limit || 50, 100)}`);
  return r.reverse().map(t => ({ id: t.id, price: +t.price, qty: +t.qty, side: t.isBuyerMaker ? 'SELL' : 'BUY', ts: t.time, source: PROV[p.market], mode: 'LIVE' }));
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
