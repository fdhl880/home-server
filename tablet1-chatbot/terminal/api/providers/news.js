'use strict';
const crypto = require('crypto');
const U = require('../util');
let Parser = null; try { Parser = require('rss-parser'); } catch (e) {}
const finnhub = require('./finnhub');

// Worldwide Institutional & Bloomberg News Wires (Bloomberg BN feeds prioritized first)
const FEEDS = [
  // Official Bloomberg Live Feeds (Priority 1 - BN Wire)
  { name: 'BN Markets', wire: 'BN', priority: 1, url: 'https://feeds.bloomberg.com/markets/news.rss', cat: 'bloomberg', desk: 'markets' },
  { name: 'BN Economics', wire: 'BN', priority: 1, url: 'https://feeds.bloomberg.com/economics/news.rss', cat: 'bloomberg', desk: 'macro' },
  { name: 'BN Tech', wire: 'BN', priority: 1, url: 'https://feeds.bloomberg.com/technology/news.rss', cat: 'bloomberg', desk: 'tech' },
  { name: 'BN Politics', wire: 'BN', priority: 1, url: 'https://feeds.bloomberg.com/politics/news.rss', cat: 'bloomberg', desk: 'world' },
  { name: 'BN Industries', wire: 'BN', priority: 1, url: 'https://feeds.bloomberg.com/industries/news.rss', cat: 'bloomberg', desk: 'markets' },
  { name: 'Bloomberg Wire', wire: 'BN', priority: 1, url: 'https://news.google.com/rss/search?q=Bloomberg+markets+OR+economy&hl=en-US&gl=US&ceid=US:en', cat: 'bloomberg', desk: 'markets' },

  // Global Institutional Wires (Reuters, WSJ, Financial Times, CNBC, BBC)
  { name: 'Reuters Global', wire: 'RTRS', priority: 2, url: 'https://news.google.com/rss/search?q=Reuters+markets+OR+economy+OR+central+bank&hl=en-US&gl=US&ceid=US:en', cat: 'macro', desk: 'macro' },
  { name: 'WSJ Markets', wire: 'WSJ', priority: 2, url: 'https://feeds.a.dj.com/rss/RSSMarketsMain.xml', cat: 'markets', desk: 'markets' },
  { name: 'WSJ World', wire: 'WSJ', priority: 2, url: 'https://feeds.a.dj.com/rss/RSSWorldNews.xml', cat: 'world', desk: 'world' },
  { name: 'Financial Times', wire: 'FT', priority: 2, url: 'https://www.ft.com/rss/home', cat: 'world', desk: 'world' },
  { name: 'CNBC Top', wire: 'CNBC', priority: 3, url: 'https://www.cnbc.com/id/100003114/device/rss/rss.html', cat: 'general', desk: 'markets' },
  { name: 'CNBC World', wire: 'CNBC', priority: 3, url: 'https://www.cnbc.com/id/100727362/device/rss/rss.html', cat: 'world', desk: 'world' },
  { name: 'CNBC Markets', wire: 'CNBC', priority: 3, url: 'https://www.cnbc.com/id/15839069/device/rss/rss.html', cat: 'markets', desk: 'markets' },
  { name: 'MarketWatch', wire: 'DJ', priority: 3, url: 'https://feeds.content.dowjones.io/public/rss/mw_topstories', cat: 'markets', desk: 'markets' },
  { name: 'BBC Business', wire: 'BBC', priority: 3, url: 'https://feeds.bbci.co.uk/news/business/rss.xml', cat: 'emea', desk: 'emea' },
  { name: 'BBC World', wire: 'BBC', priority: 3, url: 'https://feeds.bbci.co.uk/news/world/rss.xml', cat: 'world', desk: 'world' },

  // Regional Desks: Asia-Pacific, EMEA, Indonesia, Commodities & Crypto
  { name: 'APAC & Nikkei', wire: 'APAC', priority: 2, url: 'https://news.google.com/rss/search?q=Asia+markets+OR+Nikkei+OR+Hang+Seng+OR+PBOC+OR+BOJ&hl=en-US&gl=US&ceid=US:en', cat: 'apac', desk: 'apac' },
  { name: 'EMEA & ECB', wire: 'EMEA', priority: 2, url: 'https://news.google.com/rss/search?q=Europe+markets+OR+ECB+OR+FTSE+OR+DAX+OR+Middle+East+economy&hl=en-US&gl=US&ceid=US:en', cat: 'emea', desk: 'emea' },
  { name: 'IDX Indonesia', wire: 'IDN', priority: 2, url: 'https://news.google.com/rss/search?q=IHSG+OR+rupiah+OR+saham+OR+ekonomi+indonesia&hl=id&gl=ID&ceid=ID:id', cat: 'indonesia', desk: 'indonesia' },
  { name: 'Antara Ekonomi', wire: 'ANT', priority: 3, url: 'https://www.antaranews.com/rss/ekonomi.xml', cat: 'indonesia', desk: 'indonesia' },
  { name: 'Commodities Wire', wire: 'CMDTY', priority: 2, url: 'https://news.google.com/rss/search?q=crude+oil+OR+OPEC+OR+gold+price+OR+copper+OR+LNG+markets&hl=en-US&gl=US&ceid=US:en', cat: 'commodities', desk: 'commodities' },
  { name: 'Yahoo Finance', wire: 'YFIN', priority: 3, url: 'https://finance.yahoo.com/news/rssindex', cat: 'markets', desk: 'markets' },
  { name: 'CoinDesk', wire: 'CDESK', priority: 3, url: 'https://www.coindesk.com/arc/outboundfeeds/rss/', cat: 'crypto', desk: 'crypto' },
  { name: 'Cointelegraph', wire: 'CTEL', priority: 3, url: 'https://cointelegraph.com/rss', cat: 'crypto', desk: 'crypto' },
];

const strip = s => String(s || '').replace(/<[^>]+>/g, '').replace(/&nbsp;/g, ' ').replace(/&amp;/g, '&').replace(/&#39;/g, "'").replace(/&quot;/g, '"').replace(/\s+/g, ' ').trim().slice(0, 650);
const id = s => crypto.createHash('sha1').update(s).digest('hex').slice(0, 12);

async function feed(f) {
  return U.cached('rss:' + f.url, 90000, async () => {
    const xml = await U.getText(f.url, { provider: 'news-rss', timeout: 8500, headers: { Accept: 'application/rss+xml,text/xml,*/*' } });
    const r = await new Parser().parseString(xml);
    return (r.items || []).map(i => {
      const rawTitle = strip(i.title);
      const isBbg = f.wire === 'BN' || /\bbloomberg\b/i.test(rawTitle);
      return {
        id: id(i.link || i.title),
        title: rawTitle.replace(/\s*-\s*Bloomberg(\.com)?$/i, ''),
        url: i.link,
        publisher: isBbg && f.wire !== 'BN' ? 'BN Bloomberg' : f.name,
        wire: isBbg ? 'BN' : f.wire,
        priority: isBbg ? 1 : (f.priority || 3),
        ts: Date.parse(i.isoDate || i.pubDate) || Date.now(),
        category: f.cat,
        desk: f.desk || f.cat,
        summary: strip(i.contentSnippet || i.content || i.summary || i.description || rawTitle),
      };
    });
  });
}

async function cryptopanic() {
  const k = process.env.CRYPTOPANIC_KEY; if (!k) throw new Error('CRYPTOPANIC_KEY not set');
  return U.cached('cp', 120000, async () => {
    const j = await U.getJson(`https://cryptopanic.com/api/v1/posts/?auth_token=${k}&public=true`, { provider: 'cryptopanic', mode: 'LIVE' });
    return j.results.map(p => ({ id: 'cp' + p.id, title: strip(p.title), url: p.url, publisher: (p.source && p.source.title) || 'CryptoPanic', wire: 'CRYP', priority: 3, ts: Date.parse(p.published_at), category: 'crypto', desk: 'crypto', summary: '' }));
  });
}
if (!process.env.CRYPTOPANIC_KEY) U.setDisabled('cryptopanic', 'CRYPTOPANIC_KEY not set', 'LIVE');

async function news({ q, cat, limit = 100 } = {}) {
  if (!Parser) throw new Error('rss-parser not installed');
  const normCat = (cat || 'all').toLowerCase();
  const jobs = FEEDS.filter(f => {
    if (!normCat || normCat === 'all' || normCat === 'general') return true;
    if (normCat === 'bloomberg' || normCat === 'bn') return f.wire === 'BN' || f.cat === 'bloomberg';
    return f.cat === normCat || f.desk === normCat;
  }).map(f => ({ n: f.name, p: feed(f) }));

  if (!normCat || normCat === 'crypto' || normCat === 'all') jobs.push({ n: 'CryptoPanic', p: cryptopanic() });
  if (finnhub.enabled()) jobs.push({ n: 'Finnhub', p: finnhub.news(normCat === 'crypto' ? 'crypto' : 'general') });

  const res = await Promise.allSettled(jobs.map(j => j.p));
  const sources = {}; let items = [];
  res.forEach((r, i) => {
    const n = jobs[i].n;
    if (r.status === 'fulfilled') {
      sources[n] = { ok: true, count: r.value.length };
      items = items.concat(r.value);
    } else {
      sources[n] = { ok: false, error: String(r.reason && r.reason.message || r.reason).slice(0, 120) };
    }
  });

  // Sort: Prioritize fresh Bloomberg (BN) headlines first within recency bands, then chronological
  const now = Date.now();
  items.sort((a, b) => {
    const ta = a.ts || 0, tb = b.ts || 0;
    const ageA = Math.max(0, now - ta), ageB = Math.max(0, now - tb);
    // Give Bloomberg (priority 1) a 3-hour recency boost so live Bloomberg news leads the terminal
    const scoreA = ta + (a.priority === 1 ? 3 * 3600000 : a.priority === 2 ? 45 * 60000 : 0);
    const scoreB = tb + (b.priority === 1 ? 3 * 3600000 : b.priority === 2 ? 45 * 60000 : 0);
    if (ageA < 86400000 && ageB < 86400000) return scoreB - scoreA;
    return tb - ta;
  });

  const seen = new Set(); const out = [];
  for (const it of items) {
    if (!it.title) continue;
    const k = it.title.toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim().slice(0, 65);
    const u = (it.url || '').split('?')[0];
    if (seen.has(k) || (u && seen.has(u))) continue;
    seen.add(k); if (u) seen.add(u);
    if (q && !(it.title + ' ' + (it.summary || '') + ' ' + (it.publisher || '')).toLowerCase().includes(String(q).toLowerCase())) continue;
    out.push(it);
  }
  return { items: out.slice(0, Math.min(+limit || 100, 200)), sources };
}
module.exports = { news };
