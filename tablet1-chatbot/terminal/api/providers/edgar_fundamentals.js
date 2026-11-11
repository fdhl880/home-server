'use strict';
const U = require('../util');
const binance = require('./binance');
const yahoo = require('./yahoo');

const SEC_HEADERS = {
  'User-Agent': 'BloombergPersonalTerminal/1.0 (quant-desk@personal.local)',
  Accept: 'application/json',
};

let cikMapPromise = null;
async function getCikMap() {
  if (!cikMapPromise) {
    cikMapPromise = U.cached('sec:tickers', 86400000, async () => {
      const raw = await U.getJson('https://www.sec.gov/files/company_tickers.json', {
        provider: 'sec-edgar',
        headers: SEC_HEADERS,
        timeout: 10000,
      });
      const map = {};
      for (const k of Object.keys(raw || {})) {
        const row = raw[k];
        if (row && row.ticker) {
          map[String(row.ticker).toUpperCase()] = {
            cik: String(row.cik_str).padStart(10, '0'),
            title: row.title,
            ticker: String(row.ticker).toUpperCase(),
          };
        }
      }
      return map;
    }).catch(e => {
      cikMapPromise = null;
      throw e;
    });
  }
  return cikMapPromise;
}

function extractAnnualSeries(usGaap, tags, unitKey = 'USD') {
  if (!usGaap) return [];
  for (const tag of tags) {
    const node = usGaap[tag];
    if (!node || !node.units) continue;
    const units = node.units[unitKey] || Object.values(node.units)[0];
    if (!Array.isArray(units)) continue;
    const annual = units.filter(x => (x.form === '10-K' || x.form === '20-F') && (x.fp === 'FY' || !x.frame || /CY\d{4}$/.test(x.frame)));
    const byYear = new Map();
    for (const item of annual) {
      const yr = item.fy || (item.end ? +String(item.end).slice(0, 4) : null);
      if (!yr || item.val == null) continue;
      const prev = byYear.get(yr);
      if (!prev || String(item.filed) >= String(prev.filed)) {
        byYear.set(yr, { year: yr, val: +item.val, end: item.end, filed: item.filed, tag });
      }
    }
    const arr = [...byYear.values()].sort((a, b) => b.year - a.year).slice(0, 6);
    if (arr.length >= 1) return arr;
  }
  return [];
}

async function secFundamentals(symbol) {
  const clean = String(symbol).toUpperCase().replace(/\..*$/, '');
  const map = await getCikMap();
  const entry = map[clean];
  if (!entry) return null;

  const [sub, facts] = await Promise.all([
    U.cached(`sec:sub:${entry.cik}`, 3600000, () =>
      U.getJson(`https://data.sec.gov/submissions/CIK${entry.cik}.json`, {
        provider: 'sec-edgar',
        headers: SEC_HEADERS,
        timeout: 10000,
      })
    ).catch(() => null),
    U.cached(`sec:facts:${entry.cik}`, 3600000, () =>
      U.getJson(`https://data.sec.gov/api/xbrl/companyfacts/CIK${entry.cik}.json`, {
        provider: 'sec-edgar',
        headers: SEC_HEADERS,
        timeout: 12000,
      })
    ).catch(() => null),
  ]);

  const filings = [];
  if (sub && sub.filings && sub.filings.recent) {
    const r = sub.filings.recent;
    const n = Math.min((r.accessionNumber || []).length, 60);
    for (const i of Array(n).keys()) {
      const form = r.form[i];
      if (!['10-K', '10-Q', '8-K', '4', 'DEF 14A', '13F-HR', 'S-1', '20-F', '6-K'].includes(form)) continue;
      const accNoDash = String(r.accessionNumber[i] || '').replace(/-/g, '');
      const doc = r.primaryDocument && r.primaryDocument[i];
      const url = accNoDash && doc
        ? `https://www.sec.gov/Archives/edgar/data/${parseInt(entry.cik, 10)}/${accNoDash}/${doc}`
        : `https://www.sec.gov/edgar/browse/?CIK=${entry.cik}`;
      filings.push({
        form,
        filingDate: r.filingDate[i],
        reportDate: r.reportDate[i] || r.filingDate[i],
        accessionNumber: r.accessionNumber[i],
        description: r.primaryDocDescription[i] || form,
        url,
      });
      if (filings.length >= 25) break;
    }
  }

  const gaap = facts && facts.facts && facts.facts['us-gaap'];
  const dei = facts && facts.facts && facts.facts.dei;

  const revenue = extractAnnualSeries(gaap, ['Revenues', 'RevenueFromContractWithCustomerExcludingAssessedTax', 'SalesRevenueNet', 'InterestAndDividendIncomeOperating']);
  const netIncome = extractAnnualSeries(gaap, ['NetIncomeLoss', 'ProfitLoss']);
  const opIncome = extractAnnualSeries(gaap, ['OperatingIncomeLoss']);
  const grossProfit = extractAnnualSeries(gaap, ['GrossProfit']);
  const eps = extractAnnualSeries(gaap, ['EarningsPerShareDiluted', 'EarningsPerShareBasic'], 'USD/shares');
  const assets = extractAnnualSeries(gaap, ['Assets']);
  const liabilities = extractAnnualSeries(gaap, ['Liabilities']);
  const equity = extractAnnualSeries(gaap, ['StockholdersEquity', 'StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest']);
  const cash = extractAnnualSeries(gaap, ['CashAndCashEquivalentsAtCarryingValue', 'CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents']);
  const debt = extractAnnualSeries(gaap, ['LongTermDebtNoncurrent', 'LongTermDebt', 'DebtInstrumentCarryingAmount']);
  const curAssets = extractAnnualSeries(gaap, ['AssetsCurrent']);
  const curLiab = extractAnnualSeries(gaap, ['LiabilitiesCurrent']);
  const ocf = extractAnnualSeries(gaap, ['NetCashProvidedByUsedInOperatingActivities']);
  const capex = extractAnnualSeries(gaap, ['PaymentsToAcquirePropertyPlantAndEquipment']);
  const shares = extractAnnualSeries(dei || gaap, ['EntityCommonStockSharesOutstanding', 'CommonStockSharesOutstanding'], 'shares');

  return {
    cik: entry.cik,
    name: (sub && sub.name) || entry.title,
    sic: sub && sub.sic,
    sicDescription: sub && sub.sicDescription,
    Category: sub && sub.category,
    fiscalYearEnd: sub && sub.fiscalYearEnd,
    stateOfIncorporation: sub && sub.stateOfIncorporation,
    exchanges: sub && sub.exchanges,
    filings,
    financials: {
      revenue,
      grossProfit,
      opIncome,
      netIncome,
      eps,
      assets,
      liabilities,
      equity,
      cash,
      debt,
      curAssets,
      curLiab,
      ocf,
      capex,
      shares,
    },
  };
}

async function yahooEvents(symbol) {
  return U.cached(`yev:${symbol}`, 300000, async () => {
    const BASES = ['https://query1.finance.yahoo.com', 'https://query2.finance.yahoo.com'];
    const j = await U.getJsonFallback(
      BASES,
      `/v8/finance/chart/${encodeURIComponent(symbol)}?interval=1d&range=5y&events=div%7Csplits`,
      { provider: 'yahoo', mode: 'DELAYED' }
    );
    const r = j.chart && j.chart.result && j.chart.result[0];
    if (!r) return null;
    const m = r.meta || {};
    const ev = r.events || {};
    const divs = Object.values(ev.dividends || {})
      .map(d => ({ date: d.date * 1000, amount: d.amount }))
      .sort((a, b) => b.date - a.date);
    const splits = Object.values(ev.splits || {})
      .map(s => ({ date: s.date * 1000, numerator: s.numerator, denominator: s.denominator, ratio: s.splitRatio }))
      .sort((a, b) => b.date - a.date);
    const q = (r.indicators && r.indicators.quote && r.indicators.quote[0]) || {};
    const closes = (q.close || []).filter(x => x != null);
    const high52w = m.fiftyTwoWeekHigh != null ? m.fiftyTwoWeekHigh : (closes.length ? Math.max(...closes.slice(-252)) : null);
    const low52w = m.fiftyTwoWeekLow != null ? m.fiftyTwoWeekLow : (closes.length ? Math.min(...closes.slice(-252)) : null);
    return {
      symbol: m.symbol || symbol,
      shortName: m.shortName || m.longName || symbol,
      longName: m.longName || m.shortName || symbol,
      currency: m.currency || 'USD',
      exchangeName: m.fullExchangeName || m.exchangeName || '',
      instrumentType: m.instrumentType || '',
      regularMarketPrice: m.regularMarketPrice,
      chartPreviousClose: m.chartPreviousClose,
      high52w,
      low52w,
      dividends: divs.slice(0, 30),
      splits: splits.slice(0, 20),
    };
  }).catch(() => null);
}

async function fundamentals(symbol) {
  const sym = String(symbol).trim().toUpperCase();
  const isCryp = U.classify(sym) === 'crypto' || U.classify(sym) === 'crypto-perp';
  if (isCryp) {
    const [q, kl] = await Promise.all([
      binance.quote(sym).catch(() => null),
      binance.kline(sym, '1d', 365).catch(() => null),
    ]);
    const candles = (kl && kl.candles) || [];
    const hi52 = candles.length ? Math.max(...candles.map(c => c.h)) : (q && q.high);
    const lo52 = candles.length ? Math.min(...candles.map(c => c.l)) : (q && q.low);
    return {
      symbol: sym,
      asset: U.classify(sym),
      source: 'binance-spot',
      mode: 'LIVE',
      profile: {
        name: sym.replace(/USDT(\.P)?$/, ' / USDT'),
        exchange: sym.endsWith('.P') ? 'BINANCE FUTURES PERPETUAL' : 'BINANCE SPOT',
        currency: 'USDT',
        instrumentType: sym.endsWith('.P') ? 'PERPETUAL_FUTURES' : 'CRYPTO_SPOT',
        high52w: hi52,
        low52w: lo52,
      },
      quote: q,
      edgar: null,
      dividends: [],
      splits: [],
    };
  }

  const [yev, sec, q] = await Promise.all([
    yahooEvents(sym),
    secFundamentals(sym).catch(() => null),
    yahoo.quote(sym).catch(() => null),
  ]);

  if (!yev && !sec && !q) throw new Error('No fundamentals found for ' + sym);
  return {
    symbol: sym,
    asset: U.classify(sym),
    source: [sec ? 'sec-edgar' : null, yev || q ? 'yahoo' : null].filter(Boolean).join('+') || 'yahoo',
    mode: 'DELAYED',
    profile: {
      name: (sec && sec.name) || (yev && (yev.longName || yev.shortName)) || sym,
      exchange: (yev && yev.exchangeName) || (sec && sec.exchanges && sec.exchanges[0]) || 'US',
      currency: (yev && yev.currency) || 'USD',
      instrumentType: (yev && yev.instrumentType) || 'EQUITY',
      sicDescription: sec && sec.sicDescription,
      cik: sec && sec.cik,
      fiscalYearEnd: sec && sec.fiscalYearEnd,
      stateOfIncorporation: sec && sec.stateOfIncorporation,
      high52w: yev && yev.high52w,
      low52w: yev && yev.low52w,
    },
    quote: q,
    edgar: sec,
    dividends: (yev && yev.dividends) || [],
    splits: (yev && yev.splits) || [],
  };
}

async function derivativesMatrix(limit = 30) {
  return U.cached('bn:premIdx', 5000, async () => {
    const [prem, t24] = await Promise.all([
      U.getJson('https://fapi.binance.com/fapi/v1/premiumIndex', { provider: 'binance-futures', mode: 'LIVE', timeout: 8000 }),
      U.getJson('https://fapi.binance.com/fapi/v1/ticker/24hr', { provider: 'binance-futures', mode: 'LIVE', timeout: 8000 }),
    ]);
    const volMap = new Map();
    for (const x of (Array.isArray(t24) ? t24 : [])) {
      volMap.set(x.symbol, { quoteVol: +x.quoteVolume || 0, chgPct: +x.priceChangePercent || 0 });
    }
    const rows = (Array.isArray(prem) ? prem : [])
      .filter(p => p.symbol && p.symbol.endsWith('USDT') && +p.markPrice > 0)
      .map(p => {
        const v = volMap.get(p.symbol) || { quoteVol: 0, chgPct: 0 };
        const mark = +p.markPrice;
        const idx = +p.indexPrice;
        const rate = +p.lastFundingRate;
        const basisPct = idx > 0 ? ((mark - idx) / idx) * 100 : 0;
        return {
          symbol: p.symbol + '.P',
          markPrice: mark,
          indexPrice: idx,
          basisPct,
          fundingRate: rate,
          fundingPct: rate * 100,
          annualizedPct: rate * 3 * 365 * 100,
          nextFundingTime: p.nextFundingTime,
          quoteVolume: v.quoteVol,
          chgPct: v.chgPct,
        };
      })
      .sort((a, b) => b.quoteVolume - a.quoteVolume)
      .slice(0, Math.min(+limit || 30, 100));
    return rows;
  });
}

module.exports = { fundamentals, derivativesMatrix };

