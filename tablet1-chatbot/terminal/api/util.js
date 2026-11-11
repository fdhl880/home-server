'use strict';
// Shared infra: HTTP client w/ DoH fallback, TTL cache, provider rate limiter, health registry, normalizer.
const https = require('https');
const http = require('http');
const dns = require('dns');
const { URL } = require('url');

const UA = 'Mozilla/5.0 (PYRO-Terminal)';

// ---------- DNS-over-HTTPS fallback ----------
const dohCache = new Map(); // host -> {ip, exp}
function rawGet(url, headers, timeout) {
  return new Promise((resolve, reject) => {
    const u = new URL(url);
    const req = https.request({ hostname: u.hostname, path: u.pathname + u.search, headers, timeout }, res => {
      let b = ''; res.on('data', d => b += d); res.on('end', () => resolve(b));
    });
    req.on('timeout', () => req.destroy(new Error('doh timeout')));
    req.on('error', reject); req.end();
  });
}
async function dohResolve(host) {
  const c = dohCache.get(host);
  if (c && c.exp > Date.now()) return c.ip;
  const eps = [
    `https://1.1.1.1/dns-query?name=${host}&type=A`,
    `https://8.8.8.8/resolve?name=${host}&type=A`,
  ];
  for (const ep of eps) {
    try {
      const j = JSON.parse(await rawGet(ep, { accept: 'application/dns-json' }, 5000));
      const a = (j.Answer || []).find(x => x.type === 1);
      if (a) { dohCache.set(host, { ip: a.data, exp: Date.now() + Math.max(60, a.TTL || 60) * 1000 }); return a.data; }
    } catch (e) { /* try next */ }
  }
  throw new Error('DoH resolve failed for ' + host);
}
// custom lookup: for binance domains use DoH first to avoid ISP DNS poisoning; otherwise system DNS first, DoH on failure.
const STATIC_IPS = { 'fapi.binance.com': '65.8.76.49', 'fstream.binance.com': '65.8.76.49', 'api.binance.com': '65.8.76.49' };
function lookup(host, opts, cb) {
  if (typeof opts === 'function') { cb = opts; opts = {}; }
  const replyIp = ip => (opts && opts.all) ? cb(null, [{ address: ip, family: 4 }]) : cb(null, ip, 4);
  if (/binance\.(com|vision)$/i.test(host)) {
    return dohResolve(host).then(replyIp).catch(() => {
      if (STATIC_IPS[host]) return replyIp(STATIC_IPS[host]);
      dns.lookup(host, opts, cb);
    });
  }
  dns.lookup(host, opts, (err, addr, fam) => {
    if (!err) return cb(null, addr, fam);
    dohResolve(host).then(replyIp).catch(() => cb(err));
  });
}

// ---------- health registry ----------
const health = {};
const hubEvents = []; // listeners for status change
function hp(name) { return health[name] || (health[name] = { status: 'UNKNOWN', latencyMs: null, lastOk: null, lastError: null, mode: null }); }
function record(name, ok, latencyMs, err, mode) {
  const h = hp(name); const prev = h.status;
  if (ok) { h.status = 'UP'; h.lastOk = Date.now(); h.lastError = null; if (latencyMs != null) h.latencyMs = latencyMs; }
  else { h.status = 'DOWN'; h.lastError = String(err && err.message || err || 'error').slice(0, 200); }
  if (mode) h.mode = mode;
  if (prev !== h.status) hubEvents.forEach(f => { try { f(name, h.status); } catch (e) {} });
}
function setDisabled(name, why, mode) { const h = hp(name); h.status = 'DISABLED'; h.lastError = why; if (mode) h.mode = mode; }

// ---------- cache ----------
const cache = new Map();
function cget(k) { const e = cache.get(k); if (e && e.exp > Date.now()) return e.v; return undefined; }
function cstale(k) { const e = cache.get(k); return e ? e.v : undefined; }
function cset(k, v, ttlMs) {
  cache.set(k, { v, exp: Date.now() + ttlMs });
  if (cache.size > 2000) { const now = Date.now(); for (const [kk, e] of cache) if (e.exp < now - 600000) cache.delete(kk); }
}
const inflight = new Map();
async function cached(key, ttlMs, fn) {
  const v = cget(key); if (v !== undefined) return v;
  if (inflight.has(key)) return inflight.get(key);
  const p = (async () => { try { const r = await fn(); cset(key, r, ttlMs); return r; } finally { inflight.delete(key); } })();
  inflight.set(key, p); return p;
}

// ---------- outgoing per-provider rate limiter (min gap between calls) ----------
const gaps = { 'binance-spot': 15, 'binance-futures': 15, yahoo: 20, finnhub: 1100, twelvedata: 8000, fred: 15, 'news-rss': 40, cryptopanic: 1000, calendar: 200, feargreed: 200 };
const lastCall = {};
const chain = {};
function throttle(provider) {
  const gap = gaps[provider] || 100;
  const prev = chain[provider] || Promise.resolve();
  const next = prev.then(async () => {
    const wait = (lastCall[provider] || 0) + gap - Date.now();
    if (wait > 0) await new Promise(r => setTimeout(r, wait));
    lastCall[provider] = Date.now();
  });
  chain[provider] = next.catch(() => {});
  return next;
}

// ---------- HTTP ----------
function getText(url, { provider, headers = {}, timeout = 10000, redirects = 3, mode } = {}) {
  return new Promise(async (resolve, reject) => {
    if (provider) await throttle(provider);
    const t0 = Date.now();
    const u = new URL(url);
    const lib = u.protocol === 'http:' ? http : https;
    const req = lib.request({
      hostname: u.hostname, servername: u.hostname, port: u.port || undefined, path: u.pathname + u.search, method: 'GET', lookup,
      headers: Object.assign({ 'User-Agent': UA, Accept: '*/*' }, headers), timeout,
    }, res => {
      if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location && redirects > 0) {
        res.resume();
        return resolve(getText(new URL(res.headers.location, url).toString(), { provider, headers, timeout, redirects: redirects - 1, mode }));
      }
      const chunks = []; res.on('data', d => chunks.push(d));
      res.on('end', () => {
        const body = Buffer.concat(chunks).toString('utf8');
        if (res.statusCode >= 200 && res.statusCode < 300) { if (provider) record(provider, true, Date.now() - t0, null, mode); resolve(body); }
        else { const e = new Error(`HTTP ${res.statusCode} ${u.hostname} ${body.slice(0, 120).replace(/\s+/g, ' ')}`); e.status = res.statusCode; if (provider) record(provider, false, null, e); reject(e); }
      });
    });
    req.on('timeout', () => req.destroy(new Error('timeout ' + u.hostname)));
    req.on('error', e => { if (provider) record(provider, false, null, e); reject(e); });
    req.end();
  });
}
async function getJson(url, opts) { return JSON.parse(await getText(url, opts)); }
// try several base hosts in order
async function getJsonFallback(bases, pathq, opts) {
  let last;
  for (const b of bases) { try { return await getJson(b + pathq, opts); } catch (e) { last = e; if (e.status === 400) throw e; } }
  throw last;
}

// ---------- normalizer ----------
const num = v => { const n = typeof v === 'string' ? parseFloat(v) : v; return Number.isFinite(n) ? n : null; };
function classify(sym) {
  const s = String(sym).toUpperCase();
  if (s.endsWith('.P')) return 'crypto-perp';
  if (/-(USD|USDT)$/.test(s)) return 'crypto';
  if (/(USDT|USDC|BUSD|FDUSD|BTC|ETH|BNB)$/.test(s) && !s.includes('=') && !s.startsWith('^') && !s.includes('.') && s.length > 5) return 'crypto';
  if (s.startsWith('^')) return /^\^(TNX|FVX|TYX|IRX)$/.test(s) ? 'bond' : 'index';
  if (s.endsWith('=X')) return 'forex';
  if (s.endsWith('=F')) return 'commodity';
  return 'equity';
}
function tick(o) {
  const price = num(o.price);
  const prev = num(o.prevClose);
  let chg = num(o.chg), chgPct = num(o.chgPct);
  if (chg == null && price != null && prev != null) chg = price - prev;
  if (chgPct == null && chg != null && prev) chgPct = chg / prev * 100;
  return {
    symbol: o.symbol, asset: o.asset || classify(o.symbol), price, bid: num(o.bid), ask: num(o.ask), vol: num(o.vol),
    chg, chgPct, high: num(o.high), low: num(o.low), open: num(o.open), prevClose: prev,
    ts: o.ts || Date.now(), source: o.source, mode: o.mode || 'DELAYED',
  };
}
const na = (symbol, error, source) => ({ symbol, asset: classify(symbol), price: null, bid: null, ask: null, vol: null, ts: Date.now(), source: source || null, mode: 'N/A', status: 'N/A', error: String(error && error.message || error) });

// ---------- inbound rate limit (per IP) ----------
const buckets = new Map();
function rateLimit(max = 5000, windowMs = 60000) {
  return (req, res, next) => {
    const ip = req.ip || req.socket.remoteAddress || 'x';
    if (ip === '127.0.0.1' || ip === '::1' || ip === '::ffff:127.0.0.1') return next();
    const now = Date.now();
    let b = buckets.get(ip);
    if (!b || b.reset < now) { b = { n: 0, reset: now + windowMs }; buckets.set(ip, b); }
    if (++b.n > max) { res.status(429).json({ ok: false, source: 'hub', ts: now, status: 'N/A', error: 'rate_limited', retryAfterSec: Math.ceil((b.reset - now) / 1000) }); return; }
    next();
  };
}
setInterval(() => { const n = Date.now(); for (const [k, b] of buckets) if (b.reset < n) buckets.delete(k); }, 60000).unref();

module.exports = { lookup, health, hp, record, setDisabled, hubEvents, cached, cget, cstale, cset, getText, getJson, getJsonFallback, tick, na, num, classify, rateLimit };
