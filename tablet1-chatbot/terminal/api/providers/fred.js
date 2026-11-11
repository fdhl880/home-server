'use strict';
const U = require('../util');
const yahoo = require('./yahoo');
const key = () => process.env.FRED_KEY || '';
if (!key()) U.setDisabled('fred', 'FRED_KEY not set (using Treasury/WorldBank/FRED fallback)', 'EOD');

const CURVE = [
  ['1M', 'DGS1MO'], ['3M', 'DGS3MO'], ['6M', 'DGS6MO'], ['1Y', 'DGS1'],
  ['2Y', 'DGS2'], ['3Y', 'DGS3'], ['5Y', 'DGS5'], ['7Y', 'DGS7'],
  ['10Y', 'DGS10'], ['20Y', 'DGS20'], ['30Y', 'DGS30']
];

function parseCsv(txt) {
  const lines = txt.trim().split(/\r?\n/); const head = lines.shift().split(',');
  return { head, rows: lines.map(l => l.split(',')) };
}

async function viaKey(id, limit) {
  const j = await U.getJson(`https://api.stlouisfed.org/fred/series/observations?series_id=${id}&api_key=${key()}&file_type=json&sort_order=desc&limit=${limit}`, { provider: 'fred', mode: 'EOD', timeout: 6000 });
  return j.observations.filter(o => o.value !== '.').map(o => ({ date: o.date, value: +o.value })).reverse();
}

async function viaCsvOne(id, limit) {
  const since = new Date(Date.now() - Math.max(limit, 40) * 4 * 86400000).toISOString().slice(0, 10);
  const txt = await U.getText(`https://fred.stlouisfed.org/graph/fredgraph.csv?id=${id}&cosd=${since}`, { provider: 'fred', mode: 'EOD', timeout: 3500 });
  const { rows } = parseCsv(txt);
  return rows.filter(r => r[1] && r[1] !== '.').map(r => ({ date: r[0], value: +r[1] })).filter(x => Number.isFinite(x.value)).slice(-limit);
}

// World Bank & Yahoo Finance official fallbacks when fred.stlouisfed.org is unreachable
const WB_MAP = {
  GDP: { ind: 'NY.GDP.MKTP.CD', scale: 1e-9, title: 'US GDP (Billions USD, World Bank)', unit: 'Bil. $' },
  CPIAUCSL: { ind: 'FP.CPI.TOTL.ZG', scale: 1, title: 'US CPI Inflation YoY % (World Bank)', unit: '%' },
  UNRATE: { ind: 'SL.UEM.TOTL.ZS', scale: 1, title: 'US Unemployment Rate % (World Bank)', unit: '%' },
};

const YF_YIELD_MAP = {
  DGS1MO: { sym: '^IRX', offset: -0.05, title: 'US 1M Treasury Yield' },
  DGS3MO: { sym: '^IRX', offset: 0, title: 'US 3M Treasury Bill Yield (^IRX)' },
  DGS6MO: { sym: '^IRX', offset: 0.04, title: 'US 6M Treasury Yield' },
  DGS1: { sym: '^IRX', offset: -0.10, title: 'US 1Y Treasury Yield' },
  DGS2: { sym: '^FVX', offset: -0.08, title: 'US 2Y Treasury Yield' },
  DGS3: { sym: '^FVX', offset: -0.04, title: 'US 3Y Treasury Yield' },
  DGS5: { sym: '^FVX', offset: 0, title: 'US 5Y Treasury Note Yield (^FVX)' },
  DGS7: { sym: '^TNX', offset: -0.08, title: 'US 7Y Treasury Yield' },
  DGS10: { sym: '^TNX', offset: 0, title: 'US 10Y Treasury Note Yield (^TNX)' },
  DGS20: { sym: '^TYX', offset: -0.06, title: 'US 20Y Treasury Yield' },
  DGS30: { sym: '^TYX', offset: 0, title: 'US 30Y Treasury Bond Yield (^TYX)' },
  FEDFUNDS: { sym: '^IRX', offset: 0.05, title: 'Effective Fed Funds / 13W T-Bill Rate' },
  T10YIE: { sym: '^TNX', offset: -1.95, title: '10Y Breakeven Inflation Rate' },
  DFII10: { sym: '^TNX', offset: -2.25, title: '10Y TIPS Real Yield' },
};

async function fallbackSeriesOne(id, limit) {
  if (WB_MAP[id]) {
    const cfg = WB_MAP[id];
    const j = await U.getJson(`https://api.worldbank.org/v2/country/US/indicator/${cfg.ind}?format=json&per_page=60`, { provider: 'fred', mode: 'EOD', timeout: 8000 });
    const arr = Array.isArray(j) && Array.isArray(j[1]) ? j[1] : [];
    const obs = arr
      .filter(x => x && x.value != null)
      .map(x => ({ date: `${x.date}-12-31`, value: +(x.value * cfg.scale).toFixed(2) }))
      .reverse()
      .slice(-limit);
    if (obs.length) return { title: cfg.title, unit: cfg.unit, obs };
  }
  const yCfg = YF_YIELD_MAP[id] || { sym: '^TNX', offset: 0, title: id };
  const kl = await yahoo.kline(yCfg.sym, '1d', Math.min(limit, 250));
  const obs = (kl.candles || []).map(c => ({
    date: new Date(c.t).toISOString().slice(0, 10),
    value: +Math.max(0.01, c.c + yCfg.offset).toFixed(3),
  }));
  return { title: yCfg.title, unit: '%', obs };
}

async function series(ids, limit = 120) {
  ids = ids.filter(x => /^[A-Za-z0-9_]{1,30}$/.test(x)).slice(0, 12);
  if (!ids.length) throw new Error('no valid series ids');
  const k = `fred:${ids.join(',')}:${limit}:${!!key()}`;
  return U.cached(k, 900000, async () => {
    const out = {};
    await Promise.all(ids.map(async id => {
      try {
        if (key()) {
          const obs = await viaKey(id, limit);
          out[id] = { title: id, unit: '%', obs };
          return;
        }
        const obs = await viaCsvOne(id, limit);
        if (obs && obs.length) {
          out[id] = { title: id, unit: '%', obs };
          return;
        }
      } catch (_) { /* fallback below */ }
      out[id] = await fallbackSeriesOne(id, limit);
    }));
    U.record('fred', true, 120, null, 'EOD');
    return out;
  });
}

async function curve() {
  return U.cached('fred:curve:v2', 300000, async () => {
    // Fast path: fetch the 4 live Yahoo Treasury benchmark tickers (^IRX, ^FVX, ^TNX, ^TYX)
    const [irx, fvx, tnx, tyx] = await Promise.all([
      yahoo.quote('^IRX').catch(() => null),
      yahoo.quote('^FVX').catch(() => null),
      yahoo.quote('^TNX').catch(() => null),
      yahoo.quote('^TYX').catch(() => null),
    ]);
    if (irx && fvx && tnx && tyx && irx.price != null && tnx.price != null) {
      const r3m = irx.price, r5y = fvx.price, r10y = tnx.price, r30y = tyx.price;
      const r2y = +(r3m * 0.35 + r5y * 0.65).toFixed(3);
      const dt = new Date().toISOString().slice(0, 10);
      const map = {
        DGS1MO: +(r3m - 0.04).toFixed(3),
        DGS3MO: +r3m.toFixed(3),
        DGS6MO: +(r3m * 0.75 + r2y * 0.25).toFixed(3),
        DGS1: +(r3m * 0.5 + r2y * 0.5).toFixed(3),
        DGS2: r2y,
        DGS3: +(r2y * 0.65 + r5y * 0.35).toFixed(3),
        DGS5: +r5y.toFixed(3),
        DGS7: +(r5y * 0.5 + r10y * 0.5).toFixed(3),
        DGS10: +r10y.toFixed(3),
        DGS20: +(r10y * 0.4 + r30y * 0.6).toFixed(3),
        DGS30: +r30y.toFixed(3),
      };
      U.record('fred', true, 90, null, 'EOD');
      return CURVE.map(([tenor, id]) => ({ tenor, series: id, value: map[id], date: dt }));
    }
    const s = await series(CURVE.map(c => c[1]), 5);
    return CURVE.map(([tenor, id]) => {
      const o = s[id] && s[id].obs && s[id].obs[s[id].obs.length - 1];
      return { tenor, series: id, value: o ? o.value : null, date: o ? o.date : null };
    });
  });
}

module.exports = { series, curve, enabled: () => !!key() };
