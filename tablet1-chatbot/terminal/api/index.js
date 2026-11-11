'use strict';
// PYRO Terminal API + WebSocket hub.  Usage: require('./terminal/api')(app, server?)
const express = require('express');
const U = require('./util');
const agg = require('./aggregator');
const binance = require('./providers/binance');
const yahoo = require('./providers/yahoo');
const fred = require('./providers/fred');
const finnhub = require('./providers/finnhub');
const newsP = require('./providers/news');
const misc = require('./providers/macro_misc');
const { createHub, WS_PATH } = require('./hub');

const KEYS = ['FINNHUB_KEY', 'TWELVE_KEY', 'FRED_KEY', 'CRYPTOPANIC_KEY'];

module.exports = (app, server) => {
  const hub = createHub(server);
  // The existing server.js calls app.listen() after mounting and exposes no server handle: capture it.
  if (!server && typeof app.listen === 'function') {
    const orig = app.listen.bind(app);
    app.listen = function () { const s = orig.apply(null, arguments); try { hub.attach(s); } catch (e) { console.error('[terminal] ws attach failed', e.message); } return s; };
  }

  const r = express.Router();
  r.use((req, res, next) => { res.set('Access-Control-Allow-Origin', '*'); res.set('Cache-Control', 'no-store'); next(); });
  r.use(U.rateLimit(120, 60000));

  const env = (source, data, extra) => Object.assign({ ok: true, source, ts: Date.now(), mode: 'LIVE', status: 'OK', error: null, data }, extra);
  const fail = (res, source, e, code) => res.status(code || 502).json({ ok: false, source, ts: Date.now(), mode: 'N/A', status: 'N/A', error: String(e && e.message || e), data: null });
  const wrap = (source, fn) => async (req, res) => { try { await fn(req, res); } catch (e) { fail(res, typeof source === 'function' ? source(req) : source, e, e.badRequest ? 400 : 502); } };
  const bad = m => { const e = new Error(m); e.badRequest = true; return e; };
  const srcOf = sym => (agg.isCrypto(sym) ? (U.classify(sym) === 'crypto-perp' ? 'binance-futures' : 'binance-spot') : 'yahoo');
  const needSym = req => { const s = String(req.query.symbol || '').trim().toUpperCase(); if (!s) throw bad('symbol required'); return s; };
  const mkt = req => (req.query.market === 'futures' ? 'futures' : undefined);

  r.get('/quote', wrap('hub', async (req, res) => {
    const syms = [...new Set(String(req.query.symbols || req.query.symbol || '').split(',').map(s => s.trim().toUpperCase()).filter(Boolean))];
    if (!syms.length) throw bad('symbols required'); if (syms.length > 50) throw bad('max 50 symbols');
    const data = []; for (let i = 0; i < syms.length; i += 10) data.push(...await Promise.all(syms.slice(i, i + 10).map(s => agg.quote(s, mkt(req)))));
    const okN = data.filter(t => t.price != null).length;
    res.json(env([...new Set(data.map(t => t.source).filter(Boolean))].join('+') || 'hub', data, { status: okN === data.length ? 'OK' : okN ? 'PARTIAL' : 'N/A', mode: data.some(t => t.mode === 'DELAYED') ? 'DELAYED' : 'LIVE' }));
  }));
  r.get('/kline', wrap(req => srcOf(String(req.query.symbol || '').toUpperCase()), async (req, res) => {
    const s = needSym(req); const d = await agg.kline(s, req.query.interval || '1h', req.query.limit || 300, mkt(req));
    res.json(env(d.source, { symbol: d.symbol, interval: d.interval, candles: d.candles }, { mode: d.mode }));
  }));
  r.get('/depth', wrap('binance-spot', async (req, res) => {
    const s = needSym(req);
    const { providerSym } = agg.resolveProviderSym(s);
    const target = agg.isCrypto(s) ? providerSym : 'BTCUSDT';
    const d = await binance.depth(target, +req.query.limit || 20); res.json(env(d.source, d));
  }));
  r.get('/trades', wrap('binance-spot', async (req, res) => {
    const s = needSym(req);
    const { providerSym } = agg.resolveProviderSym(s);
    const target = agg.isCrypto(s) ? providerSym : 'BTCUSDT';
    const d = await binance.trades(target, +req.query.limit || 50); res.json(env(d[0] ? d[0].source : 'binance-spot', d));
  }));
  r.get('/news', wrap('news-rss', async (req, res) => {
    const d = await newsP.news({ q: req.query.q, cat: req.query.cat, limit: req.query.limit });
    const anyOk = Object.values(d.sources).some(s => s.ok);
    if (!anyOk) throw new Error('all news sources down: ' + JSON.stringify(d.sources));
    res.json(env('news-rss', d.items, { sources: d.sources, status: Object.values(d.sources).every(s => s.ok) ? 'OK' : 'PARTIAL' }));
  }));
  r.get('/macro', wrap('fred', async (req, res) => {
    const mode = fred.enabled() ? 'EOD' : 'EOD';
    if (req.query.curve) { const c = await fred.curve(); return res.json(env('fred', { curve: c }, { mode })); }
    const ids = String(req.query.series || '').split(',').map(s => s.trim().toUpperCase()).filter(Boolean);
    if (!ids.length) throw bad('series or curve=1 required');
    res.json(env('fred', { series: await fred.series(ids, Math.min(+req.query.limit || 120, 1000)) }, { mode }));
  }));
  r.get('/calendar', wrap('calendar', async (req, res) => res.json(env('calendar', await misc.calendar(req.query.week, req.query.impact), { mode: 'SCHEDULED' }))));
  r.get('/fng', wrap('feargreed', async (req, res) => res.json(env('feargreed', await misc.fearGreed(req.query.history || 30)))));
  r.get('/movers', wrap('hub', async (req, res) => {
    const asset = req.query.asset || 'crypto'; const dir = req.query.dir || 'gainers'; const lim = req.query.limit || 20;
    if (asset === 'crypto' || asset === 'crypto-perp') {
      const m = asset === 'crypto' ? 'spot' : 'futures'; return res.json(env('binance-' + m, await binance.movers(m, dir, lim)));
    }
    if (asset === 'equity') return res.json(env('yahoo', await yahoo.movers(dir, lim), { mode: 'DELAYED' }));
    throw bad('asset must be crypto|crypto-perp|equity');
  }));
  r.get('/search', wrap('hub', async (req, res) => {
    const q = String(req.query.q || '').trim(); if (!q) throw bad('q required');
    res.json(env('yahoo+binance', await agg.search(q.slice(0, 40)), { mode: 'N/A' }));
  }));
  const edgarP = require('./providers/edgar_fundamentals');
  r.get('/fundamentals', wrap('sec-edgar+yahoo', async (req, res) => {
    const s = needSym(req);
    const d = await edgarP.fundamentals(s);
    res.json(env(d.source, d, { mode: d.mode }));
  }));
  r.get('/derivatives', wrap('binance-futures', async (req, res) => {
    const d = await edgarP.derivativesMatrix(req.query.limit || 30);
    res.json(env('binance-futures', d, { mode: 'LIVE' }));
  }));

  async function probe() {
    const P = {
      'binance-spot': () => U.getJsonFallback(['https://api.binance.com', 'https://data-api.binance.vision'], '/api/v3/ping', { provider: 'binance-spot', mode: 'LIVE', timeout: 6000 }),
      'binance-futures': () => U.getJson('https://fapi.binance.com/fapi/v1/ping', { provider: 'binance-futures', mode: 'LIVE', timeout: 6000 }),
      yahoo: () => yahoo.quote('^GSPC'),
      fred: () => fred.series(['DGS10'], 5),
      'news-rss': () => newsP.news({ limit: 1 }),
      calendar: () => misc.calendar('this'),
      feargreed: () => misc.fearGreed(1),
    };
    if (finnhub.enabled()) P.finnhub = () => finnhub.quote('AAPL');
    if (process.env.TWELVE_KEY) P.twelvedata = () => require('./providers/twelve').quote('AAPL');
    await Promise.allSettled(Object.entries(P).filter(([k]) => { const h = U.hp(k); return !h.lastOk || Date.now() - h.lastOk > 60000 || h.status !== 'UP'; }).map(([k, f]) => f().catch(e => U.record(k, false, null, e))));
  }
  r.get('/health', wrap('hub', async (req, res) => {
    await Promise.race([probe(), new Promise(r2 => setTimeout(r2, 12000))]);
    const providers = {}; for (const k of Object.keys(U.health)) providers[k] = U.health[k];
    ['binance-spot', 'binance-futures', 'yahoo', 'finnhub', 'twelvedata', 'fred', 'news-rss', 'cryptopanic', 'calendar', 'feargreed'].forEach(k => { providers[k] = U.hp(k); });
    const keys = {}; KEYS.forEach(k => { keys[k] = !!process.env[k]; });
    res.json(env('hub', Object.assign(hub.stats(), { wsPath: WS_PATH, providers, keys })));
  }));
  r.use((req, res) => res.status(404).json({ ok: false, source: 'hub', ts: Date.now(), status: 'N/A', error: 'unknown route', data: null }));

  app.use('/api/terminal', r);
  console.log('[terminal] PYRO Terminal API mounted at /api/terminal, ws at ' + WS_PATH);
  return hub;
};
