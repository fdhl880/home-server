'use strict';
const WebSocket = require('ws');
const U = require('./util');
const agg = require('./aggregator');
const binance = require('./providers/binance');
const finnhub = require('./providers/finnhub');

const WS_PATH = '/terminal/ws';
const MAX_CH = 100;
const POLL_MS = 5000;

function createHub(server) {
  const wss = new WebSocket.WebSocketServer({ noServer: true, maxPayload: 64 * 1024 });
  const clients = new Set();
  const chans = new Map(); // channelKey -> Set(client)
  const started = Date.now();

  // ---- upstreams ----
  const send = (c, o) => { if (c.readyState === 1) { try { c.send(JSON.stringify(o)); } catch (e) {} } };
  const fan = (key, type, data) => { const s = chans.get(key); if (s) for (const c of s) send(c, { type, channel: key, data }); };
  const bn = { spot: new binance.Stream('spot', fan), futures: new binance.Stream('futures', fan) };
  const fh = new finnhub.FinnhubStream((sym, t) => fan('ticker:' + sym, 'tick', t));
  const poll = new Map(); // symbol -> refcount (yahoo polling for non-crypto)
  let pollTimer = null;
  async function pollOnce() {
    const syms = [...poll.keys()].filter(s => !(finnhub.enabled() && finnhub.eligible(s) && fh.syms.has(s)));
    for (let i = 0; i < syms.length; i += 4) {
      await Promise.all(syms.slice(i, i + 4).map(async s => { const t = await agg.quote(s); if (t.price != null) fan('ticker:' + s, 'tick', t); }));
    }
  }
  function ensurePoll() { if (!pollTimer && poll.size) pollTimer = setInterval(() => pollOnce().catch(() => {}), POLL_MS); if (!poll.size && pollTimer) { clearInterval(pollTimer); pollTimer = null; } }

  function norm(ch) {
    const p = String(ch).split(':'); if (p.length < 2) return null;
    const type = p[0].toLowerCase(); if (!['ticker', 'kline', 'depth', 'trades'].includes(type)) return null;
    const sym = p[1].trim(); if (!sym || sym.length > 24 || !/^[A-Za-z0-9^=.\-_/]+$/.test(sym)) return null;
    const S = sym.toUpperCase();
    return type === 'kline' ? `kline:${S}:${p[2] || '1m'}` : `${type}:${S}`;
  }
  function upstreamAdd(key) {
    const [type, sym] = key.split(':');
    if (agg.isCrypto(sym)) { const d = binance.streamsFor(key); d.streams.forEach(s => bn[d.market].add(s)); return; }
    if (finnhub.enabled() && finnhub.eligible(sym)) fh.add(sym);
    poll.set(sym, (poll.get(sym) || 0) + 1); ensurePoll();
  }
  function upstreamRemove(key) {
    const [type, sym] = key.split(':');
    if (agg.isCrypto(sym)) { const d = binance.streamsFor(key); d.streams.forEach(s => bn[d.market].remove(s)); return; }
    if (finnhub.enabled() && finnhub.eligible(sym)) fh.remove(sym);
    const n = (poll.get(sym) || 0) - 1; if (n > 0) poll.set(sym, n); else poll.delete(sym); ensurePoll();
  }

  function sub(c, raw) {
    const ok = [], rejected = [];
    for (const r of raw) {
      const key = norm(r);
      if (!key) { rejected.push({ channel: r, reason: 'invalid channel' }); continue; }
      const [type, sym] = key.split(':');
      if (type !== 'ticker' && !agg.isCrypto(sym)) { rejected.push({ channel: key, reason: type + ' only available for crypto' }); continue; }
      if (c.chans.has(key)) { ok.push(key); continue; }
      if (c.chans.size >= MAX_CH) { rejected.push({ channel: key, reason: 'max channels' }); continue; }
      c.chans.add(key);
      let s = chans.get(key); if (!s) { s = new Set(); chans.set(key, s); upstreamAdd(key); }
      s.add(c); ok.push(key);
      if (type === 'ticker') agg.quote(sym).then(t => { if (t.price != null && c.chans.has(key)) send(c, { type: 'tick', channel: key, data: t }); }); // snapshot
    }
    send(c, { type: 'subscribed', channels: ok, rejected });
  }
  function unsub(c, raw) {
    for (const r of raw) { const key = norm(r); if (!key || !c.chans.delete(key)) continue; const s = chans.get(key); if (s) { s.delete(c); if (!s.size) { chans.delete(key); upstreamRemove(key); } } }
    send(c, { type: 'unsubscribed', channels: raw });
  }
  function drop(c) { clients.delete(c); unsub(c, [...c.chans]); }

  wss.on('connection', c => {
    c.chans = new Set(); c.alive = true; clients.add(c);
    c.on('pong', () => { c.alive = true; });
    c.on('message', raw => {
      let m; try { m = JSON.parse(raw); } catch (e) { return send(c, { type: 'error', error: 'bad json' }); }
      const list = Array.isArray(m.channels) ? m.channels.map(String).slice(0, MAX_CH) : [];
      if (m.op === 'subscribe') sub(c, list); else if (m.op === 'unsubscribe') unsub(c, list);
      else if (m.op === 'ping') send(c, { type: 'pong', ts: Date.now() });
      else send(c, { type: 'error', error: 'unknown op' });
    });
    c.on('close', () => drop(c)); c.on('error', () => drop(c));
    send(c, { type: 'hello', ts: Date.now(), channels: ['ticker', 'kline', 'depth', 'trades'] });
  });
  const hb = setInterval(() => { for (const c of clients) { if (!c.alive) { c.terminate(); continue; } c.alive = false; try { c.ping(); } catch (e) {} } }, 25000); hb.unref();

  U.hubEvents.push((provider, status) => { const m = { type: 'status', provider, status, ts: Date.now() }; for (const c of clients) send(c, m); });

  function attach(srv) {
    srv.on('upgrade', (req, socket, head) => {
      let p; try { p = new URL(req.url, 'http://x').pathname; } catch (e) { return; }
      if (p !== WS_PATH) return; // leave other upgrade handlers alone
      wss.handleUpgrade(req, socket, head, ws => wss.emit('connection', ws, req));
    });
  }
  if (server) attach(server);
  const stats = () => ({ uptimeSec: Math.round((Date.now() - started) / 1000), wsClients: clients.size, wsSubscriptions: chans.size });
  return { attach, stats };
}
module.exports = { createHub, WS_PATH };
