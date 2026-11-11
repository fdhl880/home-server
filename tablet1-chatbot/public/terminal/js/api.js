// Data access: REST envelope client + WebSocket hub. Contract: terminal/API.md
// A dev adapter (synthetic data) can replace both, but is OFF unless ?dev=1 (see dev-adapter.js).
const BASE = '/api/terminal';
export const net = { adapter: null, backoffUntil: 0 };
const cache = new Map();

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
        const r = await fetch(url, { cache: 'no-store' });
        if (r.status === 429) {
          await new Promise(res => setTimeout(res, 400));
          continue;
        }
        if (!r.ok) {
          if (attempt === 0) { await new Promise(res => setTimeout(res, 300)); continue; }
          return naEnvelope('HTTP ' + r.status);
        }
        const env = await r.json();
        if (env && env.ok === false) return { ...naEnvelope(env.error), ...env };
        return env;
      } catch (e) {
        if (attempt === 0) { await new Promise(res => setTimeout(res, 300)); continue; }
        return naEnvelope('source down');
      }
    }
    return naEnvelope('rate_limited');
  })();
  cache.set(url, { at: Date.now(), p });
  if (cache.size > 200) for (const k of cache.keys()) { cache.delete(k); if (cache.size < 100) break; }
  return p;
}

// Existing (read-only) endpoint of the bot dashboard, not part of the terminal contract.
export async function getRaw(path) {
  try {
    const r = await fetch(path, { cache: 'no-store' });
    if (!r.ok) return { ok: false, error: 'HTTP ' + r.status, data: null, ts: Date.now() };
    return { ok: true, data: await r.json(), ts: Date.now() };
  } catch { return { ok: false, error: 'source down', data: null, ts: Date.now() }; }
}

export const tickOk = t => t && t.price != null && isFinite(t.price);

class Hub {
  constructor() { this.subs = new Map(); this.state = 'CONNECTING'; this.ws = null; this.retry = 0; this.listeners = new Set(); this.connect(); }
  setState(s) { this.state = s; this.listeners.forEach(f => f(s)); }
  connect() {
    if (net.adapter) { this.setState('DEV'); return; }
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    let ws;
    try { ws = new WebSocket(`${proto}://${location.host}/terminal/ws`); } catch { return this.later(); }
    this.ws = ws;
    ws.onopen = () => {
      this.retry = 0; this.setState('OPEN');
      const ch = [...this.subs.keys()];
      if (ch.length) this.send({ op: 'subscribe', channels: ch });
      clearInterval(this.hb); this.hb = setInterval(() => this.send({ op: 'ping' }), 25000);
    };
    ws.onmessage = ev => {
      let m; try { m = JSON.parse(ev.data); } catch { return; }
      if (m.channel) { const s = this.subs.get(m.channel); if (s) s.forEach(cb => cb(m.data, m)); }
      else if (m.type === 'status') this.status && this.status(m);
    };
    ws.onclose = () => { clearInterval(this.hb); this.setState('CLOSED'); this.later(); };
    ws.onerror = () => { try { ws.close(); } catch { /* */ } };
  }
  later() { this.retry++; setTimeout(() => this.connect(), Math.min(15000, 1000 * 2 ** this.retry)); }
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
