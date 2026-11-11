// DEV ADAPTER - SYNTHETIC DATA. OFF by default. Enable with ?dev=1 (or localStorage pyro.dev=1).
// Every envelope is labelled source "DEV-SYNTHETIC" / mode "DEV". Never use for decisions.
const SRC = 'DEV-SYNTHETIC';
const base = { BTCUSDT: 67000, ETHUSDT: 3400, SOLUSDT: 150, BNBUSDT: 580, XRPUSDT: 0.52, DOGEUSDT: 0.15, ADAUSDT: 0.45, AVAXUSDT: 35, LINKUSDT: 14, TRXUSDT: 0.12,
  AAPL: 190, MSFT: 420, NVDA: 900, TSLA: 180, AMZN: 180, '^GSPC': 5200, '^DJI': 39000, '^IXIC': 16300, '^N225': 38000, '^JKSE': 7200, '^FTSE': 8000, '^GDAXI': 18000,
  '^HSI': 17000, '^FCHI': 8000, '^TNX': 4.3, 'EURUSD=X': 1.085, 'GBPUSD=X': 1.27, 'AUDUSD=X': 0.66, 'NZDUSD=X': 0.6, 'USDJPY=X': 151, 'USDCHF=X': 0.9, 'USDCAD=X': 1.36, 'USDIDR=X': 15800, 'GC=F': 2300, 'CL=F': 80 };
const st = {};
function seed(s) { let h = 2166136261; for (const c of s) h = Math.imul(h ^ c.charCodeAt(0), 16777619); return () => ((h = Math.imul(h ^ (h >>> 15), 2246822507) >>> 0) / 4294967296); }
function px0(sym) { return base[sym.replace(/\.P$/, '')] ?? (50 + seed(sym)() * 100); }
function state(sym) {
  if (!st[sym]) { const p = px0(sym); st[sym] = { p, o: p, hi: p, lo: p, v: 1000 * (1 + seed(sym)() * 50), prev: p * (1 + (seed(sym + 'x')() - 0.5) * 0.04) }; }
  return st[sym];
}
function step(sym) {
  const s = state(sym); s.p *= 1 + (Math.random() - 0.5) * 0.0016; s.hi = Math.max(s.hi, s.p); s.lo = Math.min(s.lo, s.p); s.v += Math.random() * 5; return s;
}
function tick(sym) {
  const s = state(sym), asset = /USDT/.test(sym) ? 'crypto' : sym.startsWith('^') ? 'index' : sym.includes('=X') ? 'forex' : 'equity';
  return { symbol: sym, asset, price: s.p, bid: s.p * 0.9999, ask: s.p * 1.0001, vol: s.v, chg: s.p - s.prev, chgPct: (s.p / s.prev - 1) * 100, high: s.hi, low: s.lo, open: s.o, prevClose: s.prev, ts: Date.now(), source: SRC, mode: 'DEV' };
}
const env = data => ({ ok: true, source: SRC, ts: Date.now(), mode: 'DEV', status: 'OK', error: null, data });
const IV = { '1m': 60, '5m': 300, '15m': 900, '1h': 3600, '4h': 14400, '1d': 86400, '1w': 604800 };
function klines(sym, iv, n) {
  const step_ = IV[iv] * 1000, now = Math.floor(Date.now() / step_) * step_, r = seed(sym + iv), out = []; let p = px0(sym) * (0.9 + r() * 0.1);
  for (let i = n - 1; i >= 0; i--) { const o = p; p *= 1 + (r() - 0.48) * 0.02; out.push({ t: now - i * step_, o, h: Math.max(o, p) * (1 + r() * 0.004), l: Math.min(o, p) * (1 - r() * 0.004), c: p, v: 100 + r() * 1000 }); }
  return out;
}
const timers = {};
export const dev = {
  get(route, q) {
    switch (route) {
      case 'quote': return env((q.symbols || '').split(',').filter(Boolean).map(s => (step(s), tick(s))));
      case 'kline': return env({ symbol: q.symbol, interval: q.interval, candles: klines(q.symbol, q.interval || '1d', Math.min(+q.limit || 300, 500)) });
      case 'depth': { const p = state(q.symbol).p, b = [], a = []; for (let i = 1; i <= 20; i++) { b.push([p * (1 - i * 0.0002), Math.random() * 5]); a.push([p * (1 + i * 0.0002), Math.random() * 5]); } return env({ symbol: q.symbol, bids: b, asks: a, ts: Date.now() }); }
      case 'trades': return env(Array.from({ length: 30 }, (_, i) => ({ id: i, price: step(q.symbol).p, qty: Math.random(), side: Math.random() > .5 ? 'BUY' : 'SELL', ts: Date.now() - i * 900 })));
      case 'movers': return env(Object.keys(base).filter(s => q.asset === 'equity' ? /^[A-Z]+$/.test(s) : /USDT/.test(s)).map(s => (step(s), tick(s))).sort((a, b) => q.dir === 'losers' ? a.chgPct - b.chgPct : q.dir === 'active' ? b.vol - a.vol : b.chgPct - a.chgPct).slice(0, +q.limit || 20));
      case 'search': return env(Object.keys(base).filter(s => s.includes((q.q || '').toUpperCase())).slice(0, 8).map(s => ({ symbol: s, name: 'DEV ' + s, asset: tick(s).asset, exchange: 'DEV', source: SRC })));
      case 'health': return env({ uptimeSec: 0, wsClients: 0, wsSubscriptions: 0, providers: { 'dev-adapter': { status: 'UP', latencyMs: 0, mode: 'DEV' } }, keys: {} });
      default: return { ...env(null), ok: false, status: 'N/A', error: 'dev adapter: no ' + route, mode: 'N/A' };
    }
  },
  subscribe(channel, hub) {
    const [kind, sym, iv] = channel.split(':');
    timers[channel] = setInterval(() => {
      if (kind === 'ticker') { step(sym); hub.emit(channel, tick(sym)); }
      else if (kind === 'trades') hub.emit(channel, { id: Date.now(), price: step(sym).p, qty: Math.random(), side: Math.random() > .5 ? 'BUY' : 'SELL', ts: Date.now(), source: SRC, mode: 'DEV' });
      else if (kind === 'depth') hub.emit(channel, dev.get('depth', { symbol: sym }).data);
      else if (kind === 'kline') { const c = klines(sym, iv, 1)[0]; c.c = step(sym).p; hub.emit(channel, { ...c, closed: false, ts: Date.now(), source: SRC, mode: 'DEV' }); }
    }, kind === 'depth' ? 700 : 1000);
  },
  unsubscribe(channel) { clearInterval(timers[channel]); delete timers[channel]; }
};
