'use strict';
const crypto = require('crypto');
let WebSocket = null;
try { WebSocket = require('ws'); } catch (e) { console.warn('[terminal] optional ws module missing, running REST-only mode'); }
const U = require('./util');
const agg = require('./aggregator');
const binance = require('./providers/binance');
const finnhub = require('./providers/finnhub');

const WS_PATH = '/terminal/ws';
const MAX_CH = 100;
const POLL_MS = 5000;
const MAX_BUFFERED_BYTES = 512 * 1024;
const DEFAULT_MAX_PER_IP = 10;

function safeTokenMatch(provided, expected) {
  if (!provided || !expected || typeof provided !== 'string' || typeof expected !== 'string') return false;
  const ha = crypto.createHash('sha256').update(provided, 'utf8').digest();
  const hb = crypto.createHash('sha256').update(expected, 'utf8').digest();
  return crypto.timingSafeEqual(ha, hb);
}

function parseAllowedOrigins(extra) {
  const raw = [
    ...(process.env.ALLOWED_ORIGINS ? process.env.ALLOWED_ORIGINS.split(',') : []),
    ...(Array.isArray(extra) ? extra : (extra ? [extra] : []))
  ];
  const set = new Set();
  for (const item of raw) {
    const s = String(item || '').trim().replace(/\/+$/, '').toLowerCase();
    if (s) set.add(s);
  }
  return set;
}

function extractWsToken(req) {
  if (!req || !req.headers) return '';
  const auth = req.headers.authorization;
  if (typeof auth === 'string') {
    const m = auth.match(/^Bearer\s+(.+)$/i);
    if (m) return m[1].trim();
  }
  const hdr = req.headers['x-dash-token'];
  if (typeof hdr === 'string' && hdr.trim()) return hdr.trim();

  try {
    const u = new URL(req.url || '', 'http://localhost');
    const qt = u.searchParams.get('token');
    if (qt && qt.trim()) return qt.trim();
  } catch {}

  const protoHdr = req.headers['sec-websocket-protocol'];
  if (typeof protoHdr === 'string' && protoHdr.trim()) {
    const parts = protoHdr.split(',').map(x => x.trim()).filter(Boolean);
    for (const part of parts) {
      if (part === 'pyro-v1' || part === 'dash-token') continue;
      if (part.startsWith('bearer.')) return part.slice(7);
      if (part.startsWith('dash-token.')) return part.slice(11);
      return part;
    }
  }
  return '';
}

function resolveWsIp(req) {
  const xff = req && req.headers && req.headers['x-forwarded-for'];
  if (typeof xff === 'string' && xff.trim()) {
    return xff.split(',')[0].trim();
  }
  return String((req && req.socket && req.socket.remoteAddress) || 'unknown');
}

function createHub(server, opts = {}) {
  if (!WebSocket || !WebSocket.WebSocketServer) {
    return { attach() {}, close() {}, broadcast() {}, stats: () => ({ uptimeSec: 0, wsClients: 0, wsSubscriptions: 0, wsDisabled: true }) };
  }

  const allowedOrigins = parseAllowedOrigins(opts.allowedOrigins);
  const maxPerIp = Math.max(1, Number(opts.maxPerIp || opts.maxWsPerIp) || Number(process.env.WS_MAX_PER_IP) || DEFAULT_MAX_PER_IP);
  const clients = new Set();
  const chans = new Map(); // channelKey -> Set(client)
  const ipCounts = new Map(); // ip -> active count
  const started = Date.now();

  function checkToken(token) {
    if (typeof opts.verifyToken === 'function') {
      return Boolean(opts.verifyToken(token));
    }
    const envTok = process.env.DASH_TOKEN ? process.env.DASH_TOKEN.trim() : '';
    if (envTok) return safeTokenMatch(token, envTok);
    return opts.allowUnauthenticated === true;
  }

  function isOriginAllowed(req) {
    const origin = req && req.headers && req.headers.origin;
    if (!origin) return true; // Non-browser WS client (still authenticated via token)
    let u;
    try { u = new URL(origin); } catch { return false; }
    if (u.protocol !== 'http:' && u.protocol !== 'https:') return false;
    const reqHost = String((req.headers && req.headers.host) || '').toLowerCase();
    if (reqHost && u.host.toLowerCase() === reqHost) return true;
    return allowedOrigins.has(u.origin.toLowerCase());
  }

  function verifyClient(info, cb) {
    const req = info && info.req;
    if (!req) return cb(false, 400, 'Bad Request');
    if (!isOriginAllowed(req)) {
      return cb(false, 403, 'Origin Denied');
    }
    const tok = extractWsToken(req);
    if (!checkToken(tok)) {
      return cb(false, 401, 'Unauthorized');
    }
    const ip = resolveWsIp(req);
    const curCount = ipCounts.get(ip) || 0;
    if (curCount >= maxPerIp) {
      return cb(false, 429, 'Too Many Connections');
    }
    return cb(true);
  }

  function handleProtocols(protocols) {
    if (!protocols || typeof protocols.has !== 'function') return false;
    if (protocols.has('pyro-v1')) return 'pyro-v1';
    if (protocols.has('dash-token')) return 'dash-token';
    for (const p of protocols) return p;
    return false;
  }

  const wss = new WebSocket.WebSocketServer({
    noServer: true,
    maxPayload: 64 * 1024,
    handleProtocols,
    verifyClient
  });

  // ---- upstreams ----
  const send = (c, o) => {
    if (!c || c.readyState !== 1) return;
    if (c.bufferedAmount > MAX_BUFFERED_BYTES) {
      if (c.bufferedAmount > MAX_BUFFERED_BYTES * 4) {
        try { c.terminate(); } catch {}
      }
      return;
    }
    try { c.send(JSON.stringify(o)); } catch (e) {}
  };
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
  function ensurePoll() {
    if (!pollTimer && poll.size) {
      pollTimer = setInterval(() => pollOnce().catch(() => {}), POLL_MS);
      if (typeof pollTimer.unref === 'function') pollTimer.unref();
    }
    if (!poll.size && pollTimer) { clearInterval(pollTimer); pollTimer = null; }
  }

  function norm(ch) {
    const p = String(ch).split(':'); if (p.length < 2) return null;
    const type = p[0].toLowerCase(); if (!['ticker', 'kline', 'depth', 'trades'].includes(type)) return null;
    const sym = p[1].trim(); if (!sym || sym.length > 24 || !/^[A-Za-z0-9^=.\-_/]+$/.test(sym)) return null;
    const S = sym.toUpperCase();
    return type === 'kline' ? `kline:${S}:${p[2] || '1m'}` : `${type}:${S}`;
  }
  function upstreamAdd(key) {
    const [, sym] = key.split(':');
    if (agg.isCrypto(sym)) { const d = binance.streamsFor(key); d.streams.forEach(s => bn[d.market].add(s)); return; }
    if (finnhub.enabled() && finnhub.eligible(sym)) fh.add(sym);
    poll.set(sym, (poll.get(sym) || 0) + 1); ensurePoll();
  }
  function upstreamRemove(key) {
    const [, sym] = key.split(':');
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
  function drop(c) {
    if (c._dropped) return;
    c._dropped = true;
    clients.delete(c);
    if (c._clientIp) {
      const n = (ipCounts.get(c._clientIp) || 1) - 1;
      if (n <= 0) ipCounts.delete(c._clientIp);
      else ipCounts.set(c._clientIp, n);
    }
    unsub(c, [...c.chans]);
  }

  wss.on('connection', (c, req) => {
    const ip = resolveWsIp(req);
    c._clientIp = ip;
    c._dropped = false;
    ipCounts.set(ip, (ipCounts.get(ip) || 0) + 1);
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

  const onStatus = (provider, status) => { const m = { type: 'status', provider, status, ts: Date.now() }; for (const c of clients) send(c, m); };
  U.hubEvents.push(onStatus);

  function attach(srv) {
    srv.on('upgrade', (req, socket, head) => {
      let p;
      try { p = new URL(req.url, 'http://x').pathname; } catch (e) { try { socket.destroy(); } catch {} return; }
      if (p !== WS_PATH) {
        try { socket.write('HTTP/1.1 404 Not Found\r\nConnection: close\r\n\r\n'); } catch {}
        try { socket.destroy(); } catch {}
        return;
      }
      verifyClient({ req, origin: req.headers.origin, secure: Boolean(req.socket && req.socket.encrypted) }, (ok, code, msg) => {
        if (!ok) {
          const status = code || 403;
          const reason = msg || 'Forbidden';
          try { socket.write(`HTTP/1.1 ${status} ${reason}\r\nConnection: close\r\n\r\n`); } catch {}
          try { socket.destroy(); } catch {}
          return;
        }
        wss.handleUpgrade(req, socket, head, ws => wss.emit('connection', ws, req));
      });
    });
  }
  if (server) attach(server);
  function close() {
    clearInterval(hb);
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
    const idx = U.hubEvents.indexOf(onStatus);
    if (idx >= 0) U.hubEvents.splice(idx, 1);
    for (const c of clients) { try { c.terminate(); } catch {} }
    try { wss.close(); } catch {}
  }
  const broadcast = (type, data) => {
    const m = { type, data, ts: Date.now() };
    for (const c of clients) send(c, m);
  };
  const stats = () => ({ uptimeSec: Math.round((Date.now() - started) / 1000), wsClients: clients.size, wsSubscriptions: chans.size });
  return { attach, close, verifyClient, broadcast, stats };
}
module.exports = { createHub, WS_PATH };
