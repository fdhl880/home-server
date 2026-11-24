// Data access: REST envelope client + WebSocket hub. Contract: terminal/API.md
// A dev adapter (synthetic data) can replace both, but is OFF unless ?dev=1 (see dev-adapter.js).
const BASE = '/api/terminal';
const TOKEN_STORAGE_KEY = 'pyro_dash_token';
export const net = { adapter: null, backoffUntil: 0 };
const cache = new Map();

const _nativeFetch = typeof window !== 'undefined' && typeof window.fetch === 'function'
  ? window.fetch.bind(window)
  : fetch;
let _onAuthRequired = null;
let _fetchHookInstalled = false;

export function getDashToken() {
  try { return (localStorage.getItem(TOKEN_STORAGE_KEY) || '').trim(); } catch { return ''; }
}

export function clearResponseCache() {
  cache.clear();
}

export function setDashToken(tok) {
  try {
    const clean = String(tok || '').trim();
    if (clean) localStorage.setItem(TOKEN_STORAGE_KEY, clean);
    else localStorage.removeItem(TOKEN_STORAGE_KEY);
  } catch { /* ignore storage errors */ }
  clearResponseCache();
}

export function clearDashToken() {
  setDashToken('');
}

export function setAuthRequiredHandler(fn) {
  _onAuthRequired = typeof fn === 'function' ? fn : null;
}

function notifyAuthRequired(reason) {
  if (_onAuthRequired) _onAuthRequired(reason);
}

export function authHeaders(extra = {}) {
  const h = new Headers(extra || {});
  const tok = getDashToken();
  if (tok && !h.has('X-Dash-Token') && !h.has('Authorization')) {
    h.set('X-Dash-Token', tok);
  }
  return h;
}

function isSameOriginApiUrl(input) {
  try {
    const raw = typeof input === 'string' ? input : (input && input.url) || '';
    if (!raw) return false;
    const u = new URL(raw, location.origin);
    return u.origin === location.origin && u.pathname.startsWith('/api/');
  } catch {
    return false;
  }
}

export async function apiFetch(url, opts = {}, timeoutMs = 12000) {
  const { timeoutMs: optTimeout, skipAuthModal, signal: outerSignal, ...fetchOpts } = opts || {};
  const effectiveTimeout = Number.isFinite(optTimeout) && optTimeout > 0 ? optTimeout : timeoutMs;
  const ctrl = new AbortController();
  let timedOut = false;
  let timer = null;
  let onOuterAbort = null;

  if (outerSignal) {
    if (outerSignal.aborted) ctrl.abort();
    else {
      onOuterAbort = () => ctrl.abort();
      outerSignal.addEventListener('abort', onOuterAbort, { once: true });
    }
  }
  if (effectiveTimeout > 0) {
    timer = setTimeout(() => { timedOut = true; ctrl.abort(); }, effectiveTimeout);
  }

  try {
    const headers = isSameOriginApiUrl(url) ? authHeaders(fetchOpts.headers) : new Headers(fetchOpts.headers || {});
    const res = await _nativeFetch(url, {
      cache: 'no-store',
      ...fetchOpts,
      headers,
      signal: ctrl.signal,
    });
    if (res.status === 401 && !skipAuthModal && isSameOriginApiUrl(url)) {
      notifyAuthRequired('HTTP 401');
    }
    return res;
  } catch (err) {
    if (timedOut) throw new Error(`Request timeout (${effectiveTimeout}ms)`);
    throw err;
  } finally {
    if (timer) clearTimeout(timer);
    if (outerSignal && onOuterAbort) outerSignal.removeEventListener('abort', onOuterAbort);
  }
}

// Wrap same-origin /api/ window.fetch calls so panels that do not import apiFetch still authenticate.
export function installFetchAuthHook() {
  if (_fetchHookInstalled || typeof window === 'undefined' || typeof window.fetch !== 'function') return;
  _fetchHookInstalled = true;
  window.fetch = function hookedFetch(input, init = {}) {
    if (!isSameOriginApiUrl(input)) return _nativeFetch(input, init);
    const raw = typeof input === 'string' ? input : (input && input.url) || '';
    const u = new URL(raw, location.origin);
    if (u.pathname === '/api/auth/verify') return _nativeFetch(input, init);
    return apiFetch(input, init, 15000);
  };
}
installFetchAuthHook();

export function naEnvelope(error) {
  return { ok: false, source: '-', ts: Date.now(), mode: 'N/A', status: 'N/A', error: error || 'source down', data: null };
}

export async function get(route, params = {}, ttl = 1500) {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v != null && v !== '') qs.set(k, v);
  const url = `${BASE}/${route}?${qs}`;
  const hit = cache.get(url);
  if (hit && Date.now() - hit.at < ttl) return hit.p;

  const p = (async () => {
    if (net.adapter) return net.adapter.get(route, params);
    for (let attempt = 0; attempt < 2; attempt++) {
      try {
        const r = await apiFetch(url, { cache: 'no-store' }, 12000);
        if (r.status === 401 || r.status === 403 || r.status === 400) {
          return naEnvelope('HTTP ' + r.status);
        }
        if (r.status === 429) {
          await new Promise(res => setTimeout(res, 400));
          continue;
        }
        if (!r.ok) {
          if (attempt === 0 && r.status >= 500) { await new Promise(res => setTimeout(res, 300)); continue; }
          return naEnvelope('HTTP ' + r.status);
        }
        const env = await r.json();
        if (env && env.ok === false) return { ...naEnvelope(env.error), ...env };
        return env;
      } catch (e) {
        if (attempt === 0) { await new Promise(res => setTimeout(res, 300)); continue; }
        return naEnvelope(e && e.message && e.message.includes('timeout') ? 'timeout' : 'source down');
      }
    }
    return naEnvelope('rate_limited');
  })().then(
    res => {
      if (!res || res.ok === false) cache.delete(url);
      return res;
    },
    err => {
      cache.delete(url);
      throw err;
    }
  );

  cache.set(url, { at: Date.now(), p });
  if (cache.size > 200) for (const k of cache.keys()) { cache.delete(k); if (cache.size < 100) break; }
  return p;
}

// Existing (read-only) endpoint of the bot dashboard, not part of the terminal contract.
export async function getRaw(path, opts = {}) {
  try {
    const r = await apiFetch(path, { cache: 'no-store', ...opts }, opts.timeoutMs || 12000);
    if (!r.ok) return { ok: false, error: 'HTTP ' + r.status, data: null, ts: Date.now() };
    return { ok: true, data: await r.json(), ts: Date.now() };
  } catch (e) {
    return { ok: false, error: e && e.message ? e.message : 'source down', data: null, ts: Date.now() };
  }
}

export const tickOk = t => t && t.price != null && isFinite(t.price);

const WS_TOKEN_RE = /^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$/;

class Hub {
  constructor() {
    this.subs = new Map();
    this.state = 'CONNECTING';
    this.ws = null;
    this.retry = 0;
    this.retryTimer = null;
    this.hb = null;
    this.listeners = new Set();
    if (typeof document !== 'undefined') {
      document.addEventListener('visibilitychange', () => {
        if (!document.hidden && this.ws && this.ws.readyState === 1) {
          this.send({ op: 'ping' });
        }
      });
    }
    this.connect();
  }
  setState(s) { this.state = s; this.listeners.forEach(f => f(s)); }
  reconnect() {
    clearTimeout(this.retryTimer);
    this.retryTimer = null;
    this.retry = 0;
    if (this.ws) {
      try { this.ws.onclose = null; this.ws.onerror = null; this.ws.close(); } catch { /* */ }
      this.ws = null;
    }
    clearInterval(this.hb);
    this.connect();
  }
  connect() {
    clearTimeout(this.retryTimer);
    this.retryTimer = null;
    if (net.adapter) { this.setState('DEV'); return; }
    const tok = getDashToken();
    if (!tok) {
      this.setState('AUTH_REQUIRED');
      notifyAuthRequired('WS token missing');
      return;
    }
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    let ws;
    try {
      if (WS_TOKEN_RE.test(tok)) {
        ws = new WebSocket(`${proto}://${location.host}/terminal/ws`, ['pyro-v1', `bearer.${tok}`]);
      } else {
        ws = new WebSocket(`${proto}://${location.host}/terminal/ws?token=${encodeURIComponent(tok)}`);
      }
    } catch {
      return this.later();
    }
    this.ws = ws;
    ws.onopen = () => {
      this.retry = 0;
      this.setState('OPEN');
      const ch = [...this.subs.keys()];
      if (ch.length) this.send({ op: 'subscribe', channels: ch });
      clearInterval(this.hb);
      this.hb = setInterval(() => {
        if (typeof document !== 'undefined' && document.hidden) return;
        this.send({ op: 'ping' });
      }, 25000);
    };
    ws.onmessage = ev => {
      let m; try { m = JSON.parse(ev.data); } catch { return; }
      if (m.channel) { const s = this.subs.get(m.channel); if (s) s.forEach(cb => cb(m.data, m)); }
      else if (m.type === 'status') this.status && this.status(m);
      else if (m.type === 'push_alert') this.onPushAlert && this.onPushAlert(m.data);
    };
    ws.onclose = ev => {
      clearInterval(this.hb);
      this.setState('CLOSED');
      if (ev && (ev.code === 1008 || ev.code === 4401)) {
        notifyAuthRequired('WebSocket unauthorized');
        return;
      }
      this.later();
    };
    ws.onerror = () => { try { ws.close(); } catch { /* */ } };
  }
  later() {
    clearTimeout(this.retryTimer);
    if (!getDashToken()) { this.setState('AUTH_REQUIRED'); return; }
    this.retry++;
    this.retryTimer = setTimeout(() => this.connect(), Math.min(15000, 1000 * 2 ** Math.min(4, this.retry)));
  }
  send(o) { if (this.ws && this.ws.readyState === 1) this.ws.send(JSON.stringify(o)); }
  sub(channel, cb) {
    let s = this.subs.get(channel);
    if (!s) { s = new Set(); this.subs.set(channel, s); this.send({ op: 'subscribe', channels: [channel] }); if (net.adapter) net.adapter.subscribe(channel, this); }
    s.add(cb);
    return () => {
      s.delete(cb);
      if (!s.size) { this.subs.delete(channel); this.send({ op: 'unsubscribe', channels: [channel] }); if (net.adapter) net.adapter.unsubscribe(channel); }
    };
  }
  emit(channel, data) { const s = this.subs.get(channel); if (s) s.forEach(cb => cb(data, { channel })); }
}
export let hub = null;
export function startHub() { hub = new Hub(); return hub; }
