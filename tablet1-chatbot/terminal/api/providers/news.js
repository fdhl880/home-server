'use strict';
const crypto = require('crypto');
const U = require('../util');
let Parser = null; try { Parser = require('rss-parser'); } catch (e) {}
const finnhub = require('./finnhub');

const FEEDS = [
  { name: 'CNBC Top', url: 'https://www.cnbc.com/id/100003114/device/rss/rss.html', cat: 'general' },
  { name: 'CNBC Markets', url: 'https://www.cnbc.com/id/15839069/device/rss/rss.html', cat: 'markets' },
  { name: 'MarketWatch', url: 'https://feeds.content.dowjones.io/public/rss/mw_topstories', cat: 'markets' },
  { name: 'Yahoo Finance', url: 'https://finance.yahoo.com/news/rssindex', cat: 'markets' },
  { name: 'CoinDesk', url: 'https://www.coindesk.com/arc/outboundfeeds/rss/', cat: 'crypto' },
  { name: 'Cointelegraph', url: 'https://cointelegraph.com/rss', cat: 'crypto' },
];
const strip = s => String(s || '').replace(/<[^>]+>/g, '').replace(/\s+/g, ' ').trim().slice(0, 400);
const id = s => crypto.createHash('sha1').update(s).digest('hex').slice(0, 12);

async function feed(f) {
  return U.cached('rss:' + f.url, 120000, async () => {
    const xml = await U.getText(f.url, { provider: 'news-rss', timeout: 12000, headers: { Accept: 'application/rss+xml,text/xml,*/*' } });
    const r = await new Parser().parseString(xml);
    return (r.items || []).map(i => ({ id: id(i.link || i.title), title: strip(i.title), url: i.link, publisher: f.name, ts: Date.parse(i.isoDate || i.pubDate) || null, category: f.cat, summary: strip(i.contentSnippet || i.content || i.summary) }));
  });
}
async function cryptopanic() {
  const k = process.env.CRYPTOPANIC_KEY; if (!k) throw new Error('CRYPTOPANIC_KEY not set');
  return U.cached('cp', 120000, async () => {
    const j = await U.getJson(`https://cryptopanic.com/api/v1/posts/?auth_token=${k}&public=true`, { provider: 'cryptopanic', mode: 'LIVE' });
    return j.results.map(p => ({ id: 'cp' + p.id, title: strip(p.title), url: p.url, publisher: (p.source && p.source.title) || 'CryptoPanic', ts: Date.parse(p.published_at), category: 'crypto', summary: '' }));
  });
}
if (!process.env.CRYPTOPANIC_KEY) U.setDisabled('cryptopanic', 'CRYPTOPANIC_KEY not set', 'LIVE');

// returns {items, sources:{name:{ok,error,count}}}
async function news({ q, cat, limit = 50 } = {}) {
  if (!Parser) throw new Error('rss-parser not installed');
  const jobs = FEEDS.filter(f => !cat || cat === 'all' || f.cat === cat || (cat === 'general' && f.cat === 'markets')).map(f => ({ n: f.name, p: feed(f) }));
  if (!cat || cat === 'crypto' || cat === 'all') jobs.push({ n: 'CryptoPanic', p: cryptopanic() });
  if (finnhub.enabled()) jobs.push({ n: 'Finnhub', p: finnhub.news(cat === 'crypto' ? 'crypto' : 'general') });
  const res = await Promise.allSettled(jobs.map(j => j.p));
  const sources = {}; let items = [];
  res.forEach((r, i) => { const n = jobs[i].n; if (r.status === 'fulfilled') { sources[n] = { ok: true, count: r.value.length }; items = items.concat(r.value); } else sources[n] = { ok: false, error: String(r.reason && r.reason.message || r.reason).slice(0, 120) }; });
  const seen = new Set(); const out = [];
  items.sort((a, b) => (b.ts || 0) - (a.ts || 0));
  for (const it of items) {
    if (!it.title) continue;
    const k = it.title.toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim().slice(0, 70); const u = (it.url || '').split('?')[0];
    if (seen.has(k) || (u && seen.has(u))) continue; seen.add(k); if (u) seen.add(u);
    if (q && !(it.title + ' ' + it.summary).toLowerCase().includes(String(q).toLowerCase())) continue;
    out.push(it);
  }
  return { items: out.slice(0, Math.min(+limit || 50, 100)), sources };
}
module.exports = { news };
