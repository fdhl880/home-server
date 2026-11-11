'use strict';
const WebSocket = require('ws');
const U = require('../util');
const enc = encodeURIComponent;
const key = () => process.env.FINNHUB_KEY || '';

if (!key()) U.setDisabled('finnhub', 'FINNHUB_KEY not set', 'LIVE');

async function quote(symbol) {
  if (!key()) throw new Error('FINNHUB_KEY not set');
  const q = await U.cached('fh:' + symbol, 2000, () => U.getJson(`https://finnhub.io/api/v1/quote?symbol=${enc(symbol)}&token=${key()}`, { provider: 'finnhub', mode: 'LIVE' }));
  if (!q || !q.c) throw new Error('finnhub no data for ' + symbol);
  return U.tick({ symbol, price: q.c, chg: q.d, chgPct: q.dp, high: q.h, low: q.l, open: q.o, prevClose: q.pc, ts: (q.t || 0) * 1000 || Date.now(), source: 'finnhub', mode: 'LIVE' });
}
async function news(cat = 'general') {
  if (!key()) throw new Error('FINNHUB_KEY not set');
  const c = ['general', 'forex', 'crypto', 'merger'].includes(cat) ? cat : 'general';
  const r = await U.cached('fhn:' + c, 120000, () => U.getJson(`https://finnhub.io/api/v1/news?category=${c}&token=${key()}`, { provider: 'finnhub' }));
  return r.map(n => ({ id: 'fh' + n.id, title: n.headline, url: n.url, publisher: n.source, ts: n.datetime * 1000, category: c === 'crypto' ? 'crypto' : 'general', summary: n.summary }));
}
function eligible(sym) { return /^[A-Z]{1,5}(\.[A-Z])?$/.test(sym); }

// Live trade stream for US equities; onTick(symbol, tick)
class FinnhubStream {
  constructor(onTick) { this.onTick = onTick; this.ws = null; this.syms = new Map(); this.backoff = 2000; this.last = {}; }
  ok() { return !!key(); }
  open() {
    if (this.ws || !key() || !this.syms.size) return;
    const ws = this.ws = new WebSocket('wss://ws.finnhub.io?token=' + key(), { lookup: U.lookup });
    ws.on('open', () => { this.backoff = 2000; U.record('finnhub', true, null, null, 'LIVE'); for (const s of this.syms.keys()) ws.send(JSON.stringify({ type: 'subscribe', symbol: s })); });
    ws.on('message', raw => {
      try {
        const m = JSON.parse(raw); if (m.type !== 'trade') return;
        for (const t of m.data) { const prev = (this.last[t.s] || {}); this.last[t.s] = { p: t.p };
          this.onTick(t.s, U.tick({ symbol: t.s, asset: 'equity', price: t.p, vol: t.v, ts: t.t, source: 'finnhub', mode: 'LIVE', prevClose: prev.pc })); }
      } catch (e) {}
    });
    ws.on('error', e => U.record('finnhub', false, null, e));
    ws.on('close', () => { this.ws = null; if (this.syms.size) setTimeout(() => this.open(), this.backoff = Math.min(this.backoff * 2, 60000)); });
  }
  add(s) { const n = (this.syms.get(s) || 0) + 1; this.syms.set(s, n); if (n === 1) { if (this.ws && this.ws.readyState === 1) this.ws.send(JSON.stringify({ type: 'subscribe', symbol: s })); else this.open(); } }
  remove(s) { const n = (this.syms.get(s) || 0) - 1; if (n > 0) return this.syms.set(s, n); this.syms.delete(s); if (this.ws && this.ws.readyState === 1) this.ws.send(JSON.stringify({ type: 'unsubscribe', symbol: s })); if (!this.syms.size && this.ws) this.ws.close(); }
}
module.exports = { quote, news, eligible, FinnhubStream, enabled: () => !!key() };
