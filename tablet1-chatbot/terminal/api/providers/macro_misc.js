'use strict';
const U = require('../util');

// Economic calendar: public weekly JSON feed (Forex Factory / FairEconomy). No "actual" values in this feed.
async function calendar(week = 'this', impact) {
  const w = week === 'next' ? 'nextweek' : 'thisweek';
  const raw = await U.cached('cal:' + w, 1800000, () => U.getJson(`https://nfs.faireconomy.media/ff_calendar_${w}.json`, { provider: 'calendar', timeout: 15000 }));
  let items = raw.map(e => ({ title: e.title, country: e.country, impact: e.impact, ts: Date.parse(e.date) || null, forecast: e.forecast || null, previous: e.previous || null, actual: e.actual || null }));
  if (impact) items = items.filter(e => e.impact && e.impact.toLowerCase() === String(impact).toLowerCase());
  return items.sort((a, b) => a.ts - b.ts);
}
async function fearGreed(history = 30) {
  const j = await U.cached('fng:' + history, 300000, () => U.getJson(`https://api.alternative.me/fng/?limit=${Math.min(+history || 30, 365)}`, { provider: 'feargreed', mode: 'LIVE' }));
  const d = j.data; if (!d || !d.length) throw new Error('no fng data');
  return { value: +d[0].value, label: d[0].value_classification, ts: +d[0].timestamp * 1000, history: d.map(x => ({ ts: +x.timestamp * 1000, value: +x.value, label: x.value_classification })) };
}
module.exports = { calendar, fearGreed };
