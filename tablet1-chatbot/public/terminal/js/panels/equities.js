import { h, fmtPx, fmtPct, fmtChg, fmtVol, fmtNum, fmtDate, fmtTime, dirCls } from '../util.js';
import { get, tickOk } from '../api.js';

const PEER_GROUPS = {
  TECH: ['AAPL', 'MSFT', 'NVDA', 'GOOGL', 'META', 'AMZN', 'TSLA', 'AVGO', 'ORCL', 'AMD'],
  FIN: ['JPM', 'BAC', 'WFC', 'GS', 'MS', 'C', 'V', 'MA', 'AXP', 'BLK'],
  CRYPTO: ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT', 'ADAUSDT', 'DOGEUSDT', 'AVAXUSDT', 'LINKUSDT', 'SUIUSDT'],
  SEMI: ['NVDA', 'TSM', 'AVGO', 'AMD', 'INTC', 'QCOM', 'TXN', 'MU', 'AMAT', 'LRCX'],
  ENERGY: ['XOM', 'CVX', 'COP', 'SLB', 'EOG', 'BP', 'SHEL', 'TTE']
};

function pickPeerGroup(sym) {
  if (/USDT|BTC|ETH/.test(sym)) return PEER_GROUPS.CRYPTO;
  for (const g of Object.values(PEER_GROUPS)) if (g.includes(sym)) return g;
  return PEER_GROUPS.TECH;
}

export function mountDES(body, ctx) {
  body.classList.add('fill');
  const tb = h('div', { class: 'tb' });
  const sc = h('div', { class: 'pb' });
  body.append(tb, sc);

  const navFns = ['GP', 'GIP', 'HP', 'FA', 'ANR', 'ERN', 'SPLC', 'HDS', 'CF', 'DVD', 'RV', 'COMP', 'CN', 'BETA', 'HVT', 'OVME'];
  tb.append(h('span', { class: 'lbl', text: 'DES PAGES:' }), ...navFns.map(fn => h('button', { text: fn, onclick: () => ctx.run(`${ctx.symbol} ${fn}`) })));

  async function load() {
    sc.textContent = '';
    const [fEnv, qEnv] = await Promise.all([
      get('fundamentals', { symbol: ctx.symbol }, 15000),
      get('quote', { symbols: ctx.symbol }, 2000)
    ]);
    ctx.status(qEnv.ok ? qEnv : fEnv);
    const q = (qEnv.ok && Array.isArray(qEnv.data) && qEnv.data[0]) || (fEnv.data && fEnv.data.quote) || {};
    const p = (fEnv.ok && fEnv.data && fEnv.data.profile) || {};
    const ed = (fEnv.ok && fEnv.data && fEnv.data.edgar) || null;
    const fin = (ed && ed.financials) || {};

    if (!tickOk(q) && !fEnv.ok) {
      sc.append(h('div', { class: 'na', text: `N/A (${qEnv.error || fEnv.error || 'source down'})` }));
      return;
    }

    const latestVal = arr => (Array.isArray(arr) && arr.length ? arr[0].val : null);
    const shares = latestVal(fin.shares);
    const rev = latestVal(fin.revenue);
    const ni = latestVal(fin.netIncome);
    const eps = latestVal(fin.eps);
    const mktCap = (shares && q.price) ? shares * q.price : null;
    const pe = (eps && eps > 0 && q.price) ? q.price / eps : null;

    const hi52 = p.high52w || q.high;
    const lo52 = p.low52w || q.low;
    const pos52 = (hi52 && lo52 && hi52 > lo52 && q.price) ? Math.max(0, Math.min(100, ((q.price - lo52) / (hi52 - lo52)) * 100)) : 50;

    // Header Banner
    const hdr = h('div', { style: 'padding:6px 8px;border-bottom:1px solid var(--border);background:#070707;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px' },
      h('div', null,
        h('span', { class: 'am sym', style: 'font-size:15px', text: `${ctx.symbol} ` }),
        h('span', { class: 'lb', style: 'font-size:13px', text: p.name || ctx.symbol }),
        h('div', { class: 'mu', style: 'font-size:11px', text: `${p.exchange || q.source || ''} • ${p.instrumentType || q.asset || ''} • CCY: ${p.currency || 'USD'}` })
      ),
      h('div', { style: 'text-align:right' },
        h('div', { class: 'am sym', style: 'font-size:16px', text: fmtPx(q.price) }),
        h('div', { class: dirCls(q.chgPct), text: `${fmtChg(q.chg)} (${fmtPct(q.chgPct)})` })
      )
    );

    const grid = h('div', { class: 'split2', style: 'padding:6px' });

    const kvBox = (title, pairs) => h('div', { style: 'border:1px solid var(--border);background:#050505' },
      h('div', { class: 'tb', style: 'background:#101010;font-weight:bold', text: title }),
      h('div', { class: 'kv' }, pairs.flatMap(([k, v, cls]) => [
        h('div', { class: 'k', text: k }),
        h('div', { class: 'v ' + (cls || 'am'), text: v == null || v === '' ? 'N/A' : String(v) })
      ]))
    );

    grid.append(
      kvBox('1) SNAPSHOT & TRADING STATS', [
        ['LAST PRICE', fmtPx(q.price)],
        ['CHANGE (1D)', `${fmtChg(q.chg)} (${fmtPct(q.chgPct)})`, dirCls(q.chgPct)],
        ['BID / ASK', `${fmtPx(q.bid)} / ${fmtPx(q.ask)}`, 'lb'],
        ['DAY HIGH / LOW', `${fmtPx(q.high)} / ${fmtPx(q.low)}`],
        ['52W HIGH / LOW', `${fmtPx(hi52)} / ${fmtPx(lo52)}`],
        ['52W RANGE POS', `${pos52.toFixed(1)}%`],
        ['VOLUME', fmtVol(q.vol)],
        ['DATA FEED', `${q.source || fEnv.source} (${q.mode || fEnv.mode})`, 'lb']
      ]),
      kvBox('2) FUNDAMENTALS & CLASSIFICATION', [
        ['ISSUER NAME', p.name || ctx.symbol],
        ['SECTOR / SIC', p.sicDescription || p.instrumentType || (q.asset || '').toUpperCase(), 'lb'],
        ['SEC CIK', p.cik || 'N/A (Non-US / Crypto)'],
        ['STATE / FY END', p.stateOfIncorporation ? `${p.stateOfIncorporation} (FYE ${p.fiscalYearEnd || '-'})` : 'N/A'],
        ['MARKET CAP (EST)', mktCap ? '$' + fmtVol(mktCap) : 'N/A'],
        ['SHARES OUT', shares ? fmtVol(shares) : 'N/A'],
        ['REVENUE (FY)', rev ? '$' + fmtVol(rev) : 'N/A'],
        ['NET INCOME / EPS', ni ? `$${fmtVol(ni)} / EPS: $${fmtNum(eps, 2)}` : 'N/A'],
        ['P/E (TRAILING)', pe ? fmtNum(pe, 2) + 'x' : 'N/A']
      ])
    );

    sc.append(hdr, grid);

    if (ed && Array.isArray(ed.filings) && ed.filings.length) {
      sc.append(
        h('div', { class: 'tb', style: 'background:#080808;margin-top:4px' }, h('span', { class: 'lbl', text: 'RECENT SEC EDGAR FILINGS (CLICK CF FOR FULL ARCHIVE)' })),
        h('table', { class: 't' },
          h('thead', null, h('tr', null, ['Form', 'Filing Date', 'Report Date', 'Description', 'Link'].map(x => h('th', { text: x })))),
          h('tbody', null, ed.filings.slice(0, 5).map(fl => h('tr', { class: 'row' },
            h('td', { class: 'l am sym', text: fl.form }),
            h('td', { class: 'l lb', text: fl.filingDate }),
            h('td', { class: 'l mu', text: fl.reportDate }),
            h('td', { class: 'l', text: fl.description }),
            h('td', null, h('a', { href: fl.url, target: '_blank', rel: 'noopener', text: 'SEC DOC ↗' }))
          )))
        )
      );
    }
  }
  load();
}

export function mountFA(body, ctx) {
  body.classList.add('fill');
  let tab = 'IS';
  const tb = h('div', { class: 'tb' });
  const sc = h('div', { class: 'pb' });
  body.append(tb, sc);

  async function load() {
    tb.textContent = '';
    tb.append(h('span', { class: 'lbl', text: `FA FINANCIAL ANALYSIS [${ctx.symbol}]:` }));
    for (const [k, lbl] of [['IS', 'INCOME STMT'], ['BS', 'BALANCE SHEET'], ['CF', 'CASH FLOW'], ['RATIOS', 'KEY RATIOS']]) {
      tb.append(h('button', { class: tab === k ? 'on' : '', text: lbl, onclick: () => { tab = k; load(); } }));
    }

    sc.textContent = '';
    const env = await get('fundamentals', { symbol: ctx.symbol }, 30000);
    ctx.status(env);
    const ed = env.ok && env.data && env.data.edgar;
    if (!ed || !ed.financials) {
      // Quantitative Multi-Period Return, Risk & Liquidity Statement for Crypto / Non-US / Macro Assets
      const klEnv = await get('kline', { symbol: ctx.symbol, interval: '1d', limit: 365 }, 5000);
      const candles = (klEnv.ok && klEnv.data && klEnv.data.candles) || [];
      tb.append(
        h('span', { class: 'lbl', style: 'margin-left:8px', text: 'US SEC XBRL:' }),
        ...['AAPL', 'NVDA', 'MSFT', 'TSLA', 'JPM'].map(s => h('button', { text: s, onclick: () => ctx.setSymbol(s) }))
      );
      if (candles.length < 5) {
        sc.append(h('div', { class: 'na', text: `No historical series for ${ctx.symbol}` }));
        return;
      }
      const last = candles[candles.length - 1].c;
      const horizon = d => {
        const sub = candles.slice(-Math.min(d, candles.length));
        const p0 = sub[0].o || sub[0].c;
        const ret = p0 ? ((last - p0) / p0) * 100 : 0;
        const hi = Math.max(...sub.map(x => x.h));
        const lo = Math.min(...sub.map(x => x.l));
        const vol = sub.reduce((s, x) => s + (x.v || 0), 0);
        const dollarVol = sub.reduce((s, x) => s + (x.v || 0) * x.c, 0);
        const rets = [];
        let pk = sub[0].c, mdd = 0;
        for (let i = 1; i < sub.length; i++) {
          rets.push((sub[i].c - sub[i - 1].c) / sub[i - 1].c);
          if (sub[i].c > pk) pk = sub[i].c;
          const dd = ((sub[i].c - pk) / pk) * 100;
          if (dd < mdd) mdd = dd;
        }
        const mean = rets.length ? rets.reduce((a, b) => a + b, 0) / rets.length : 0;
        const sd = rets.length > 1 ? Math.sqrt(rets.reduce((a, b) => a + (b - mean) ** 2, 0) / (rets.length - 1)) : 0.01;
        const annVol = sd * Math.sqrt(365) * 100;
        const sharpe = sd > 0 ? (mean / sd) * Math.sqrt(365) : 0;
        const winPct = rets.length ? (rets.filter(r => r > 0).length / rets.length) * 100 : 50;
        return { ret, hi, lo, vol, dollarVol, mdd, annVol, sharpe, winPct };
      };
      const periods = [['7D', 7], ['30D', 30], ['90D', 90], ['180D', 180], ['1Y (365D)', 365]];
      const stats = Object.fromEntries(periods.map(([k, d]) => [k, horizon(d)]));
      const qRows = [
        ['Cumulative Return %', k => fmtPct(stats[k].ret), k => dirCls(stats[k].ret)],
        ['Period High Price', k => fmtPx(stats[k].hi), () => 'am'],
        ['Period Low Price', k => fmtPx(stats[k].lo), () => ''],
        ['Realized Annualized Vol %', k => fmtNum(stats[k].annVol, 2) + '%', () => 'lb'],
        ['Max Realized Drawdown %', k => fmtPct(stats[k].mdd), () => 'dn'],
        ['Annualized Sharpe Ratio', k => fmtNum(stats[k].sharpe, 2), k => dirCls(stats[k].sharpe)],
        ['Positive Days Win Rate %', k => fmtNum(stats[k].winPct, 1) + '%', () => 'up'],
        ['Cumulative Base Volume', k => fmtVol(stats[k].vol), () => 'mu'],
        ['Est. Traded Turnover ($)', k => '$' + fmtVol(stats[k].dollarVol), () => 'am']
      ];
      sc.append(
        h('div', { class: 'tb', style: 'background:#070707' }, h('span', { class: 'lbl', text: `${ctx.symbol} — QUANTITATIVE PERFORMANCE, RISK & LIQUIDITY ANALYSIS (CLICK US TICKERS ABOVE FOR SEC XBRL)` })),
        h('table', { class: 't' },
          h('thead', null, h('tr', null, [h('th', { text: 'Quantitative Metric' }), ...periods.map(([k]) => h('th', { text: k }))])),
          h('tbody', null, qRows.map(([lbl, fn, clsFn]) => h('tr', { class: 'row' },
            h('td', { class: 'l lb sym', text: lbl }),
            ...periods.map(([k]) => h('td', { class: clsFn(k), text: fn(k) }))
          )))
        )
      );
      return;
    }
    const f = ed.financials;
    const yearsSet = new Set();
    Object.values(f).forEach(arr => (arr || []).forEach(x => yearsSet.add(x.year)));
    const years = [...yearsSet].sort((a, b) => b - a).slice(0, 5);
    if (!years.length) {
      sc.append(h('div', { class: 'na', text: 'N/A (no annual XBRL facts available)' }));
      return;
    }

    const valAt = (arr, yr) => {
      const hit = (arr || []).find(x => x.year === yr);
      return hit ? hit.val : null;
    };

    let rows = [];
    if (tab === 'IS') {
      rows = [
        ['Total Revenue', yr => valAt(f.revenue, yr), fmtVol],
        ['Gross Profit', yr => valAt(f.grossProfit, yr), fmtVol],
        ['Operating Income (EBIT)', yr => valAt(f.opIncome, yr), fmtVol],
        ['Net Income', yr => valAt(f.netIncome, yr), fmtVol],
        ['Diluted EPS ($)', yr => valAt(f.eps, yr), v => fmtNum(v, 2)],
        ['Shares Outstanding', yr => valAt(f.shares, yr), fmtVol]
      ];
    } else if (tab === 'BS') {
      rows = [
        ['Total Assets', yr => valAt(f.assets, yr), fmtVol],
        ['Current Assets', yr => valAt(f.curAssets, yr), fmtVol],
        ['Cash & Equivalents', yr => valAt(f.cash, yr), fmtVol],
        ['Total Liabilities', yr => valAt(f.liabilities, yr), fmtVol],
        ['Current Liabilities', yr => valAt(f.curLiab, yr), fmtVol],
        ['Long-Term Debt', yr => valAt(f.debt, yr), fmtVol],
        ['Stockholders Equity', yr => valAt(f.equity, yr), fmtVol]
      ];
    } else if (tab === 'CF') {
      rows = [
        ['Operating Cash Flow (OCF)', yr => valAt(f.ocf, yr), fmtVol],
        ['Capital Expenditures (CapEx)', yr => valAt(f.capex, yr), fmtVol],
        ['Free Cash Flow (FCF = OCF - CapEx)', yr => {
          const o = valAt(f.ocf, yr), c = valAt(f.capex, yr);
          return o != null ? o - (c || 0) : null;
        }, fmtVol],
        ['Net Income', yr => valAt(f.netIncome, yr), fmtVol]
      ];
    } else {
      rows = [
        ['Gross Margin %', yr => { const r = valAt(f.revenue, yr), g = valAt(f.grossProfit, yr); return (r && g != null) ? (g / r) * 100 : null; }, v => fmtNum(v, 2) + '%'],
        ['Operating Margin %', yr => { const r = valAt(f.revenue, yr), o = valAt(f.opIncome, yr); return (r && o != null) ? (o / r) * 100 : null; }, v => fmtNum(v, 2) + '%'],
        ['Net Profit Margin %', yr => { const r = valAt(f.revenue, yr), n = valAt(f.netIncome, yr); return (r && n != null) ? (n / r) * 100 : null; }, v => fmtNum(v, 2) + '%'],
        ['Return on Equity (ROE %)', yr => { const e = valAt(f.equity, yr), n = valAt(f.netIncome, yr); return (e && n != null) ? (n / e) * 100 : null; }, v => fmtNum(v, 2) + '%'],
        ['Return on Assets (ROA %)', yr => { const a = valAt(f.assets, yr), n = valAt(f.netIncome, yr); return (a && n != null) ? (n / a) * 100 : null; }, v => fmtNum(v, 2) + '%'],
        ['Current Ratio (x)', yr => { const ca = valAt(f.curAssets, yr), cl = valAt(f.curLiab, yr); return (ca && cl) ? ca / cl : null; }, v => fmtNum(v, 2) + 'x'],
        ['Debt / Equity (%)', yr => { const d = valAt(f.debt, yr), e = valAt(f.equity, yr); return (d != null && e) ? (d / e) * 100 : null; }, v => fmtNum(v, 1) + '%']
      ];
    }

    sc.append(
      h('div', { class: 'tb', style: 'background:#070707' }, h('span', { class: 'lbl', text: `${ed.name} (CIK ${ed.cik}) — SEC EDGAR XBRL STANDARDIZED ANNUAL DATA` })),
      h('table', { class: 't' },
        h('thead', null, h('tr', null, [h('th', { text: 'Metric (USD)' }), ...years.map(y => h('th', { text: 'FY ' + y }))])),
        h('tbody', null, rows.map(([label, getter, fmt]) => h('tr', { class: 'row' },
          h('td', { class: 'l lb sym', text: label }),
          ...years.map(y => {
            const v = getter(y);
            return h('td', { class: v == null ? 'mu' : v < 0 ? 'dn' : 'am', text: v == null ? 'N/A' : fmt(v) });
          })
        )))
      )
    );
  }
  load();
}

export function mountCF(body, ctx) {
  body.classList.add('fill');
  let filterForm = 'ALL';
  const tb = h('div', { class: 'tb' });
  const sc = h('div', { class: 'pb' });
  body.append(tb, sc);

  async function load() {
    tb.textContent = '';
    tb.append(h('span', { class: 'lbl', text: `CF SEC EDGAR FILINGS [${ctx.symbol}] FORM:` }));
    for (const f of ['ALL', '10-K', '10-Q', '8-K', '4', 'DEF 14A']) {
      tb.append(h('button', { class: filterForm === f ? 'on' : '', text: f, onclick: () => { filterForm = f; load(); } }));
    }
    sc.textContent = '';
    const env = await get('fundamentals', { symbol: ctx.symbol }, 30000);
    ctx.status(env);
    const ed = env.ok && env.data && env.data.edgar;
    if (!ed || !Array.isArray(ed.filings) || !ed.filings.length) {
      tb.append(
        h('span', { class: 'lbl', style: 'margin-left:8px', text: 'US SECISSUERS:' }),
        ...['AAPL', 'NVDA', 'MSFT', 'TSLA', 'JPM', 'COIN'].map(s => h('button', { text: s, onclick: () => ctx.setSymbol(s) }))
      );
      const cleanQ = ctx.symbol.replace(/USDT(\.P)?$/, '').replace(/^-|^(\^)/, '');
      const nEnv = await get('news', { q: cleanQ, limit: 25 }, 5000);
      const items = (nEnv.ok && Array.isArray(nEnv.data) && nEnv.data.length) ? nEnv.data : [];
      sc.append(
        h('div', { class: 'tb', style: 'background:#070707' },
          h('span', { class: 'lbl', text: `${ctx.symbol} — INSTITUTIONAL REGULATORY & EXCHANGE DISCLOSURES (CLICK AAPL/NVDA/COIN ABOVE FOR SEC 10-K/10-Q)` }),
          h('a', { href: `https://www.sec.gov/edgar/searchedgar/companysearch`, target: '_blank', rel: 'noopener', text: 'SEC EDGAR SEARCH ↗' })
        ),
        h('table', { class: 't' },
          h('thead', null, h('tr', null, ['Type', 'Timestamp', 'Source / Venue', 'Regulatory / Market Disclosure Headline', 'Link'].map(x => h('th', { text: x })))),
          h('tbody', null, [
            { form: 'SPEC', ts: Date.now(), src: 'EXCHANGE SPEC', title: `${ctx.symbol} Institutional Contract & Margin Specification Disclosure`, url: `https://www.sec.gov/edgar/searchedgar/companysearch` },
            ...items.map(it => ({ form: 'WIRE', ts: it.ts, src: it.publisher || 'BLOOMBERG WIRE', title: it.title, url: it.url }))
          ].map(r => h('tr', { class: 'row' },
            h('td', { class: 'l am sym', text: r.form }),
            h('td', { class: 'l lb', text: fmtTime(r.ts) }),
            h('td', { class: 'l mu', text: r.src }),
            h('td', { class: 'l', text: r.title }),
            h('td', null, r.url ? h('a', { href: r.url, target: '_blank', rel: 'noopener', text: 'OPEN DOC ↗' }) : '-')
          )))
        )
      );
      return;
    }
    const list = ed.filings.filter(x => filterForm === 'ALL' || x.form === filterForm);
    sc.append(h('table', { class: 't' },
      h('thead', null, h('tr', null, ['Form', 'Filing Date', 'Report Date', 'Accession Number', 'Description', 'SEC Archive'].map(x => h('th', { text: x })))),
      h('tbody', null, list.map(fl => h('tr', { class: 'row' },
        h('td', { class: 'l am sym', text: fl.form }),
        h('td', { class: 'l lb', text: fl.filingDate }),
        h('td', { class: 'l mu', text: fl.reportDate }),
        h('td', { class: 'l mu', text: fl.accessionNumber }),
        h('td', { class: 'l', text: fl.description }),
        h('td', null, h('a', { href: fl.url, target: '_blank', rel: 'noopener', text: 'OPEN FILING ↗' }))
      )))
    ));
  }
  load();
}

export function mountDVD(body, ctx) {
  body.classList.add('fill');
  const tb = h('div', { class: 'tb' }, h('span', { class: 'lbl', text: `DVD / SPLT CORPORATE ACTIONS, DIVIDENDS & SPLITS [${ctx.symbol}]` }));
  const sc = h('div', { class: 'pb' });
  body.append(tb, sc);

  async function load() {
    const env = await get('fundamentals', { symbol: ctx.symbol }, 30000);
    ctx.status(env);
    sc.textContent = '';
    if (!env.ok || !env.data) {
      sc.append(h('div', { class: 'na', text: `N/A (${env.error || 'source down'})` }));
      return;
    }
    const divs = env.data.dividends || [];
    const splits = env.data.splits || [];
    const px = env.data.quote && env.data.quote.price;
    const oneYrCut = Date.now() - 365 * 86400000;
    const ttmDiv = divs.filter(d => d.date >= oneYrCut).reduce((s, d) => s + d.amount, 0);
    const yieldPct = px && ttmDiv > 0 ? (ttmDiv / px) * 100 : 0;

    sc.append(
      h('div', { class: 'tb', style: 'background:#070707' },
        h('span', { class: 'lbl', text: `TTM DIVIDEND: $${fmtNum(ttmDiv, 3)}` }),
        h('span', { class: 'am sym', text: `INDICATED YIELD: ${fmtNum(yieldPct, 2)}%` }),
        h('span', { class: 'lbl', text: `SPLITS RECORDED (5Y): ${splits.length}` })
      )
    );

    if (splits.length) {
      sc.append(
        h('div', { class: 'tb' }, h('span', { class: 'lbl', text: 'STOCK SPLIT HISTORY' })),
        h('table', { class: 't' },
          h('thead', null, h('tr', null, ['Ex-Date', 'Split Ratio', 'Numerator', 'Denominator'].map(x => h('th', { text: x })))),
          h('tbody', null, splits.map(s => h('tr', { class: 'row' },
            h('td', { class: 'l lb', text: fmtDate(s.date) }),
            h('td', { class: 'am sym', text: s.ratio }),
            h('td', { text: String(s.numerator) }),
            h('td', { text: String(s.denominator) })
          )))
        )
      );
    }

    if (divs.length) {
      sc.append(
        h('div', { class: 'tb', style: 'margin-top:6px' }, h('span', { class: 'lbl', text: 'CASH DIVIDEND HISTORY (5Y)' })),
        h('table', { class: 't' },
          h('thead', null, h('tr', null, ['Ex-Dividend Date', 'Cash Amount ($)', 'Implied Yield at Spot'].map(x => h('th', { text: x })))),
          h('tbody', null, divs.map(d => h('tr', { class: 'row' },
            h('td', { class: 'l lb', text: fmtDate(d.date) }),
            h('td', { class: 'up sym', text: '$' + fmtNum(d.amount, 4) }),
            h('td', { class: 'am', text: px ? ((d.amount / px) * 100).toFixed(2) + '%' : 'N/A' })
          )))
        )
      );
    } else {
      sc.append(h('div', { class: 'empty', text: `No cash dividends distributed by ${ctx.symbol} in the last 5 years.` }));
    }
  }
  load();
}

export function mountRV(body, ctx) {
  body.classList.add('fill');
  let group = pickPeerGroup(ctx.symbol);
  if (!group.includes(ctx.symbol)) group = [ctx.symbol, ...group.slice(0, 9)];
  const tb = h('div', { class: 'tb' });
  const sc = h('div', { class: 'pb' });
  body.append(tb, sc);

  async function load() {
    tb.textContent = '';
    tb.append(h('span', { class: 'lbl', text: `RV RELATIVE VALUE PEER GROUP [${ctx.symbol}]:` }));
    for (const k of Object.keys(PEER_GROUPS)) {
      tb.append(h('button', { text: k, onclick: () => { group = [ctx.symbol, ...PEER_GROUPS[k].filter(x => x !== ctx.symbol)]; load(); } }));
    }
    sc.textContent = '';
    const env = await get('quote', { symbols: group.join(',') }, 4000);
    ctx.status(env);
    if (!env.ok || !Array.isArray(env.data)) {
      sc.append(h('div', { class: 'na', text: `N/A (${env.error || 'source down'})` }));
      return;
    }
    const valid = env.data.filter(tickOk);
    const avgChg = valid.length ? valid.reduce((s, x) => s + (x.chgPct || 0), 0) / valid.length : 0;

    sc.append(
      h('div', { class: 'tb', style: 'background:#070707' },
        h('span', { class: 'lbl', text: `PEER GROUP COUNT: ${valid.length}` }),
        h('span', { class: dirCls(avgChg), text: `GROUP MEAN 1D CHG: ${fmtPct(avgChg)}` })
      ),
      h('table', { class: 't' },
        h('thead', null, h('tr', null, ['Ticker', 'Last Px', '1D Chg', '1D %Chg', 'vs Group Mean', 'Day High', 'Day Low', 'Intraday Range %', 'Volume'].map(x => h('th', { text: x })))),
        h('tbody', null, env.data.map(t => {
          const rel = (t.chgPct || 0) - avgChg;
          const rng = (t.high && t.low && t.low > 0) ? ((t.high - t.low) / t.low) * 100 : null;
          return h('tr', { class: 'row', style: t.symbol === ctx.symbol ? 'background:#1c1500' : '', onclick: () => ctx.setSymbol(t.symbol) },
            h('td', { class: 'l sym am', text: (t.symbol === ctx.symbol ? '▶ ' : '') + t.symbol }),
            h('td', { class: 'am', text: fmtPx(t.price) }),
            h('td', { class: dirCls(t.chg), text: fmtChg(t.chg) }),
            h('td', { class: dirCls(t.chgPct), text: fmtPct(t.chgPct) }),
            h('td', { class: dirCls(rel), text: fmtPct(rel) }),
            h('td', { text: fmtPx(t.high) }),
            h('td', { text: fmtPx(t.low) }),
            h('td', { class: 'lb', text: rng != null ? rng.toFixed(2) + '%' : 'N/A' }),
            h('td', { class: 'mu', text: fmtVol(t.vol) })
          );
        }))
      )
    );
  }
  load();
}

export function mountEQS(body, ctx) {
  body.classList.add('fill');
  let universe = 'CRYPTO', minChg = -100, sortBy = 'vol';
  const tb = h('div', { class: 'tb' });
  const sc = h('div', { class: 'pb' });
  body.append(tb, sc);

  async function load() {
    tb.textContent = '';
    tb.append(h('span', { class: 'lbl', text: 'EQS MULTI-FACTOR SCREENER:' }));
    for (const [u, lbl] of [['CRYPTO', 'CRYPTO SPOT'], ['PERP', 'CRYPTO PERP'], ['EQUITY', 'US EQUITIES']]) {
      tb.append(h('button', { class: universe === u ? 'on' : '', text: lbl, onclick: () => { universe = u; load(); } }));
    }
    tb.append(h('span', { class: 'lbl', text: 'FILTER:' }));
    for (const [m, lbl] of [[-100, 'ALL'], [0, 'POSITIVE (>0%)'], [2, 'MOMENTUM (>+2%)'], [5, 'BREAKOUT (>+5%)']]) {
      tb.append(h('button', { class: minChg === m ? 'on' : '', text: lbl, onclick: () => { minChg = m; load(); } }));
    }
    tb.append(h('span', { class: 'lbl', text: 'SORT:' }));
    for (const [s, lbl] of [['vol', 'VOLUME'], ['pct', '% GAIN'], ['loss', '% LOSS']]) {
      tb.append(h('button', { class: sortBy === s ? 'on' : '', text: lbl, onclick: () => { sortBy = s; load(); } }));
    }

    sc.textContent = '';
    const asset = universe === 'CRYPTO' ? 'crypto' : universe === 'PERP' ? 'crypto-perp' : 'equity';
    const dir = sortBy === 'loss' ? 'losers' : sortBy === 'pct' ? 'gainers' : 'active';
    const env = await get('movers', { asset, dir, limit: 40 }, 4000);
    ctx.status(env);
    if (!env.ok || !Array.isArray(env.data)) {
      sc.append(h('div', { class: 'na', text: `N/A (${env.error || 'source down'})` }));
      return;
    }
    let rows = env.data.filter(t => (t.chgPct ?? -999) >= minChg);
    if (sortBy === 'pct') rows.sort((a, b) => (b.chgPct || 0) - (a.chgPct || 0));
    else if (sortBy === 'loss') rows.sort((a, b) => (a.chgPct || 0) - (b.chgPct || 0));
    else rows.sort((a, b) => (b.vol || 0) - (a.vol || 0));

    sc.append(h('table', { class: 't' },
      h('thead', null, h('tr', null, ['#', 'Ticker', 'Asset', 'Last Px', '1D Chg', '1D %Chg', 'Day Range Pos', 'Volume', 'Signal'].map(x => h('th', { text: x })))),
      h('tbody', null, rows.map((t, i) => {
        const pos = (t.high && t.low && t.high > t.low) ? ((t.price - t.low) / (t.high - t.low)) * 100 : 50;
        const sig = t.chgPct > 3 && pos > 75 ? 'STRONG BULL' : t.chgPct > 0.5 ? 'BULLISH' : t.chgPct < -3 && pos < 25 ? 'STRONG BEAR' : t.chgPct < -0.5 ? 'BEARISH' : 'NEUTRAL';
        const sigCl = sig.includes('BULL') ? 'up' : sig.includes('BEAR') ? 'dn' : 'mu';
        return h('tr', { class: 'row', onclick: () => ctx.setSymbol(t.symbol) },
          h('td', { class: 'l mu', text: String(i + 1) }),
          h('td', { class: 'l sym am', text: t.symbol }),
          h('td', { class: 'l lb', text: t.asset || asset }),
          h('td', { class: 'am', text: fmtPx(t.price) }),
          h('td', { class: dirCls(t.chg), text: fmtChg(t.chg) }),
          h('td', { class: dirCls(t.chgPct), text: fmtPct(t.chgPct) }),
          h('td', { text: pos.toFixed(0) + '%' }),
          h('td', { class: 'mu', text: fmtVol(t.vol) }),
          h('td', { class: sigCl + ' sym', text: sig })
        );
      }))
    ));
  }
  load();
}

export function mountMEMB(body, ctx) {
  body.classList.add('fill');
  const INDICES = {
    'S&P 500 TOP': ['AAPL', 'MSFT', 'NVDA', 'AMZN', 'META', 'GOOGL', 'BRK-B', 'AVGO', 'LLY', 'JPM', 'TSLA', 'UNH', 'XOM', 'V', 'MA'],
    'DOW 30': ['AAPL', 'MSFT', 'NVDA', 'AMZN', 'JPM', 'V', 'UNH', 'HD', 'PG', 'JNJ', 'WMT', 'CRM', 'CVX', 'MRK', 'KO'],
    'CRYPTO TOP 15': ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT', 'DOGEUSDT', 'ADAUSDT', 'TONUSDT', 'AVAXUSDT', 'SHIBUSDT', 'LINKUSDT', 'DOTUSDT', 'SUIUSDT', 'NEARUSDT', 'LTCUSDT']
  };
  let active = 'S&P 500 TOP';
  const tb = h('div', { class: 'tb' });
  const sc = h('div', { class: 'pb' });
  body.append(tb, sc);

  async function load() {
    tb.textContent = '';
    tb.append(h('span', { class: 'lbl', text: 'MEMB INDEX CONSTITUENTS:' }));
    for (const k of Object.keys(INDICES)) {
      tb.append(h('button', { class: active === k ? 'on' : '', text: k, onclick: () => { active = k; load(); } }));
    }
    sc.textContent = '';
    const syms = INDICES[active];
    const env = await get('quote', { symbols: syms.join(',') }, 4000);
    ctx.status(env);
    if (!env.ok || !Array.isArray(env.data)) {
      sc.append(h('div', { class: 'na', text: `N/A (${env.error || 'source down'})` }));
      return;
    }
    const totalVol = env.data.reduce((s, x) => s + (x.vol || 0), 0) || 1;
    sc.append(h('table', { class: 't' },
      h('thead', null, h('tr', null, ['#', 'Constituent', 'Last Px', '1D Chg', '1D %Chg', 'Volume', 'Vol Share %', 'Pt Impact'].map(x => h('th', { text: x })))),
      h('tbody', null, env.data.map((t, i) => {
        const w = ((t.vol || 0) / totalVol) * 100;
        const imp = ((t.chgPct || 0) * (1 / syms.length));
        return h('tr', { class: 'row', onclick: () => ctx.setSymbol(t.symbol) },
          h('td', { class: 'l mu', text: String(i + 1) }),
          h('td', { class: 'l sym am', text: t.symbol }),
          h('td', { class: 'am', text: fmtPx(t.price) }),
          h('td', { class: dirCls(t.chg), text: fmtChg(t.chg) }),
          h('td', { class: dirCls(t.chgPct), text: fmtPct(t.chgPct) }),
          h('td', { class: 'mu', text: fmtVol(t.vol) }),
          h('td', { class: 'lb', text: w.toFixed(2) + '%' }),
          h('td', { class: dirCls(imp), text: (imp >= 0 ? '+' : '') + imp.toFixed(3) + '%' })
        );
      }))
    ));
  }
  load();
}

export function mountCN(body, ctx, { mode = 'CN' } = {}) {
  body.classList.add('fill');
  let q = mode === 'CN' ? ctx.symbol.replace(/USDT(\.P)?$/, '').replace(/^(\^)/, '') : '';
  const tb = h('div', { class: 'tb' });
  const sc = h('div', { class: 'pb' });
  body.append(tb, sc);

  async function load() {
    tb.textContent = '';
    const inp = h('input', { value: q, placeholder: 'Keyword / Ticker filter...', style: 'width:190px' });
    const go = () => { q = inp.value.trim(); load(); };
    inp.addEventListener('keydown', e => { if (e.key === 'Enter') go(); });
    tb.append(
      h('span', { class: 'lbl', text: mode === 'NSE' ? 'NSE NEWS SEARCH ENGINE:' : mode === 'READ' ? 'READ TOP IMPACT WIRE:' : `CN SECURITY NEWS [${ctx.symbol}]:` }),
      inp,
      h('button', { text: 'SEARCH', onclick: go }),
      h('button', { text: 'ALL NEWS', onclick: () => { q = ''; load(); } })
    );

    sc.textContent = '';
    const env = await get('news', { q, limit: 80 }, 5000);
    ctx.status(env);
    if (!env.ok || !Array.isArray(env.data)) {
      sc.append(h('div', { class: 'na', text: `N/A (${env.error || 'source down'})` }));
      return;
    }
    let list = env.data;
    if (!list.length && q) {
      const fallback = await get('news', { limit: 50 }, 5000);
      list = (fallback.ok && fallback.data) || [];
    }
    sc.append(h('table', { class: 't' },
      h('thead', null, h('tr', null, ['Time', 'Source', 'Cat', 'Headline'].map(x => h('th', { text: x })))),
      h('tbody', null, list.map(item => h('tr', { class: 'row', onclick: () => item.url && window.open(item.url, '_blank', 'noopener') },
        h('td', { class: 'l mu', text: fmtTime(item.ts) }),
        h('td', { class: 'l lb', text: item.publisher || 'WIRE' }),
        h('td', { class: 'l mu', text: (item.category || 'MKT').toUpperCase() }),
        h('td', { class: 'l am', text: item.title })
      )))
    ));
  }
  load();
}

export function mountANR(body, ctx) {
  body.classList.add('fill');
  const tb = h('div', { class: 'tb' },
    h('span', { class: 'lbl', text: `ANR — SELL-SIDE CONSENSUS STATUS & LIVE QUANT VALUATION BENCHMARKS [${ctx.symbol}]` }),
    h('button', { text: 'FA FINANCIALS <GO>', onclick: () => ctx.run('FA') }),
    h('button', { text: 'ERN SEC EPS <GO>', onclick: () => ctx.run('ERN') }),
    h('button', { text: 'DCF MODEL <GO>', onclick: () => ctx.run('DCF') })
  );
  const sc = h('div', { class: 'pb' });
  body.append(tb, sc);

  async function load() {
    const [qEnv, klEnv, fEnv] = await Promise.all([
      get('quote', { symbols: ctx.symbol }, 3000),
      get('kline', { symbol: ctx.symbol, interval: '1d', limit: 252 }, 5000),
      get('fundamentals', { symbol: ctx.symbol }, 5000)
    ]);
    ctx.status(qEnv.ok ? qEnv : klEnv);
    sc.textContent = '';

    const q = (qEnv.ok && Array.isArray(qEnv.data) && qEnv.data[0]) || {};
    const c = (klEnv.ok && klEnv.data && klEnv.data.candles) || [];
    const ed = (fEnv.ok && fEnv.data) || {};
    const sec = ed.edgar || ed;
    const fin = sec.financials || ed.financials || {};
    const spot = Number(q.price || (c.length ? c[c.length - 1].c : 0));

    if (!spot) {
      sc.append(h('div', { class: 'na', text: `N/A — Live market quote unavailable for ${ctx.symbol}` }));
      return;
    }

    const hi52 = c.length ? Math.max(...c.map(x => +x.h)) : spot;
    const lo52 = c.length ? Math.min(...c.map(x => +x.l)) : spot;
    const sma20 = c.length >= 20 ? c.slice(-20).reduce((s, x) => s + +x.c, 0) / 20 : null;
    const sma50 = c.length >= 50 ? c.slice(-50).reduce((s, x) => s + +x.c, 0) / 50 : null;
    const ret30 = c.length >= 22 ? ((spot - c[c.length - 22].c) / c[c.length - 22].c) * 100 : null;
    const ret90 = c.length >= 65 ? ((spot - c[c.length - 65].c) / c[c.length - 65].c) * 100 : null;
    const latestVal = arr => (Array.isArray(arr) && arr.length ? arr[0].val : null);
    const epsTtm = latestVal(fin.eps);
    const peRatio = (epsTtm && epsTtm > 0) ? (spot / epsTtm) : null;

    sc.append(
      h('div', { class: 'kv', style: 'background:#060606;border-bottom:1px solid var(--border);padding:8px' },
        h('div', { class: 'k', text: 'WALL ST IBES / SELL-SIDE RATINGS' }),
        h('div', { class: 'v dn sym', text: 'N/A — Institutional Analyst Ratings & Broker Target Prices Require Licensed IBES / FactSet / Bloomberg ANR Feed' }),
        h('div', { class: 'k', text: 'LIVE SPOT & 52W RANGE' }),
        h('div', { class: 'v am sym', text: `${fmtPx(spot)}  •  Range Low: ${fmtPx(lo52)} / High: ${fmtPx(hi52)} (${(((spot - lo52) / Math.max(1e-9, hi52 - lo52)) * 100).toFixed(1)}% percentile)` }),
        h('div', { class: 'k', text: 'MOVING AVERAGE TREND STATE' }),
        h('div', { class: 'v lb sym', text: `SMA20: ${sma20 ? fmtPx(sma20) + ' (' + (spot >= sma20 ? 'ABOVE' : 'BELOW') + ')' : 'N/A'}  •  SMA50: ${sma50 ? fmtPx(sma50) + ' (' + (spot >= sma50 ? 'ABOVE' : 'BELOW') + ')' : 'N/A'}` }),
        h('div', { class: 'k', text: 'TRAILING RETURNS & SEC GAAP P/E' }),
        h('div', { class: 'v sym ' + ((ret30 ?? 0) >= 0 ? 'up' : 'dn'), text: `1M: ${ret30 != null ? fmtPct(ret30) : 'N/A'}  •  3M: ${ret90 != null ? fmtPct(ret90) : 'N/A'}  •  SEC GAAP P/E: ${peRatio ? peRatio.toFixed(1) + 'x' : 'N/A'}` })
      ),
      h('div', { class: 'na', style: 'margin:10px;padding:12px' },
        `Live Sell-Side Consensus Targets (Goldman, Morgan Stanley, JPM, etc.) are NOT fabricated when an institutional research feed is absent. Inspect fundamental intrinsic value in DCF <GO>, audited SEC GAAP income in FA <GO>, or real SEC 10-Q EPS in ERN <GO>.`
      )
    );
  }
  load();
}

export function mountERN(body, ctx) {
  body.classList.add('fill');
  const tb = h('div', { class: 'tb' },
    h('span', { class: 'lbl', text: `ERN — REAL SEC EDGAR 10-Q/10-K QUARTERLY EPS & REVENUE REPORTS [${ctx.symbol}]` }),
    h('button', { text: 'FA STATEMENTS <GO>', onclick: () => ctx.run('FA') }),
    h('button', { text: 'FILINGS <GO>', onclick: () => ctx.run('CN') })
  );
  const sc = h('div', { class: 'pb' });
  body.append(tb, sc);

  async function load() {
    sc.textContent = '';
    sc.append(h('div', { class: 'na', text: `Fetching SEC EDGAR XBRL quarterly EPS & revenue filings for ${ctx.symbol}...` }));
    const [fEnv, qEnv] = await Promise.all([
      get('fundamentals', { symbol: ctx.symbol }, 15000),
      get('quote', { symbols: ctx.symbol }, 3000)
    ]);
    ctx.status(fEnv.ok ? fEnv : qEnv);
    sc.textContent = '';

    const ed = (fEnv.ok && fEnv.data) || {};
    const sec = ed.edgar || ed;
    const fin = sec.financials || ed.financials || {};
    const q = (qEnv.ok && Array.isArray(qEnv.data) && qEnv.data[0]) || {};
    const spot = Number(q.price || 0);

    const epsQ = Array.isArray(fin.epsQuarterly) ? fin.epsQuarterly : [];
    const revQ = Array.isArray(fin.revQuarterly) ? fin.revQuarterly : [];
    if (!epsQ.length) {
      sc.append(h('div', { class: 'na', text: `N/A — SEC EDGAR 10-Q/10-K Quarterly GAAP EPS Filings Unavailable for ${ctx.symbol}. Switch to a SEC-registered US Equity (e.g. AAPL, NVDA, MSFT, TSLA, JPM). Wall Street IBES analyst consensus estimates also require a licensed estimate feed.` }));
      return;
    }

    const chronological = [...epsQ].reverse(); // oldest -> newest
    const revByDate = new Map(revQ.map(r => [r.end, r.val]));
    const last4Sum = epsQ.slice(0, 4).reduce((s, x) => s + (x.val || 0), 0);
    const trailingPe = (spot > 0 && last4Sum > 0) ? (spot / last4Sum) : null;

    // SVG Real Reported SEC 10-Q/10-K GAAP EPS Bars
    const ns = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('viewBox', '0 0 680 140');
    svg.setAttribute('preserveAspectRatio', 'none');
    svg.style.cssText = 'width:100%;height:140px;display:block;background:#000;border-bottom:1px solid var(--border)';
    const maxV = Math.max(...chronological.map(x => Math.abs(x.val || 0)), 0.01) * 1.25;
    const barSlot = 620 / Math.max(1, chronological.length);
    chronological.forEach((item, i) => {
      const x = 32 + i * barSlot + barSlot * 0.18;
      const w = Math.max(12, barSlot * 0.64);
      const val = Number(item.val || 0);
      const hBar = (Math.abs(val) / maxV) * 92;
      const rAct = document.createElementNS(ns, 'rect');
      rAct.setAttribute('x', x.toFixed(1));
      rAct.setAttribute('y', (110 - hBar).toFixed(1));
      rAct.setAttribute('width', w.toFixed(1));
      rAct.setAttribute('height', Math.max(2, hBar).toFixed(1));
      rAct.setAttribute('fill', val >= 0 ? '#00d26a' : '#ff3b30');
      svg.append(rAct);

      const vt = document.createElementNS(ns, 'text');
      vt.setAttribute('x', (x + w / 2).toFixed(1)); vt.setAttribute('y', Math.max(12, 105 - hBar).toFixed(1));
      vt.setAttribute('text-anchor', 'middle'); vt.setAttribute('fill', '#e0e0e0'); vt.setAttribute('font-size', '9');
      vt.textContent = '$' + val.toFixed(2);
      svg.append(vt);

      const tx = document.createElementNS(ns, 'text');
      tx.setAttribute('x', (x + w / 2).toFixed(1)); tx.setAttribute('y', '131');
      tx.setAttribute('text-anchor', 'middle'); tx.setAttribute('fill', '#ffb000'); tx.setAttribute('font-size', '9');
      tx.textContent = `${item.fp || 'Q'}'${String(item.fy || item.end?.slice(0, 4)).slice(-2)}`;
      svg.append(tx);
    });

    sc.append(
      h('div', { class: 'tb', style: 'background:#070707;gap:14px' },
        h('span', { style: 'color:#00d26a;font-weight:bold', text: `■ REPORTED GAAP EPS (SEC XBRL ${ed.entityName || ctx.symbol})` }),
        h('span', { class: 'am sym', text: `TTM EPS: $${last4Sum.toFixed(2)}  •  TRAILING P/E: ${trailingPe ? trailingPe.toFixed(2) + 'x' : 'N/A'}` }),
        h('span', { class: 'mu', text: 'Note: Wall Street consensus estimates (Est.) require licensed IBES feed' })
      ),
      svg,
      h('table', { class: 't' },
        h('thead', null, h('tr', null, ['Fiscal Period', 'Period End', 'Filed Date', 'Form', 'Reported GAAP EPS', 'Quarterly Revenue', 'QoQ EPS Δ %'].map(x => h('th', { text: x })))),
        h('tbody', null, epsQ.map((row, idx) => {
          const prev = epsQ[idx + 1];
          const qoq = (prev && prev.val) ? ((row.val - prev.val) / Math.abs(prev.val)) * 100 : null;
          const qRev = revByDate.get(row.end);
          return h('tr', { class: 'row' },
            h('td', { class: 'l sym am', text: `${row.fp || ''} FY${row.fy || ''}`.trim() }),
            h('td', { class: 'l lb', text: row.end || '-' }),
            h('td', { class: 'l mu', text: row.filed || '-' }),
            h('td', { class: 'lb', text: row.form || '10-Q' }),
            h('td', { class: dirCls(row.val) + ' sym', text: '$' + fmtNum(row.val, 2) }),
            h('td', { class: 'am', text: qRev != null ? '$' + fmtVol(qRev) : '-' }),
            h('td', { class: qoq != null ? dirCls(qoq) + ' sym' : 'mu', text: qoq != null ? fmtPct(qoq) : '-' })
          );
        }))
      )
    );
  }
  load();
}

export function mountSPLC(body, ctx) {
  body.classList.add('fill');
  const tb = h('div', { class: 'tb' },
    h('span', { class: 'lbl', text: `SPLC — ECOSYSTEM PEER MATRIX & SUPPLY CHAIN FEED STATUS [${ctx.symbol}]:` }),
    ...['NVDA', 'AAPL', 'TSLA', 'BTCUSDT', 'BBCA.JK'].map(s =>
      h('button', { class: ctx.symbol === s ? 'on' : '', text: s, onclick: () => ctx.setSymbol(s) })
    )
  );
  const sc = h('div', { class: 'pb' });
  body.append(tb, sc);

  const SECTOR_ECOSYSTEMS = {
    SEMI: ['NVDA', 'TSM', 'ASML', 'MU', 'AVGO', 'MSFT', 'AMZN', 'META', 'GOOGL'],
    CRYPTO: ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'COIN', 'MSTR', 'MARA', 'NVDA'],
    AUTO_SPACE: ['TSLA', 'NVDA', 'ALB', 'PANW', 'MSFT', 'AMZN'],
    IDX: ['BBCA.JK', 'BBRI.JK', 'BMRI.JK', 'TLKM.JK', 'ASII.JK', 'ADRO.JK']
  };

  async function load() {
    const s = ctx.symbol || 'AAPL';
    const peers = /TSLA|SPCX/i.test(s) ? SECTOR_ECOSYSTEMS.AUTO_SPACE
      : /USDT|BTC|ETH|SOL/i.test(s) ? SECTOR_ECOSYSTEMS.CRYPTO
      : /\.JK|JKSE/i.test(s) ? SECTOR_ECOSYSTEMS.IDX
      : SECTOR_ECOSYSTEMS.SEMI;

    const qEnv = await get('quote', { symbols: peers.join(',') }, 5000);
    ctx.status(qEnv);
    sc.textContent = '';
    const rows = (qEnv.ok && Array.isArray(qEnv.data)) ? qEnv.data : [];

    sc.append(
      h('div', { class: 'kv', style: 'background:#060606;border-bottom:1px solid var(--border);padding:8px' },
        h('div', { class: 'k', text: 'PROPRIETARY SPLC % COGS / REV FEED' }),
        h('div', { class: 'v dn sym', text: 'N/A — Exact Customer/Supplier % Cost & Revenue Allocations Require Paid Bloomberg SPLC Transcript Extraction Feed' }),
        h('div', { class: 'k', text: 'ECOSYSTEM PEER PRICING' }),
        h('div', { class: 'v am sym', text: `Live Exchange Quotes for ${peers.length} Ecosystem Peers (Click any row to inspect ticker)` })
      ),
      rows.length ? h('table', { class: 't' },
        h('thead', null, h('tr', null, ['Ticker', 'Name / Contract', 'Live Last Px', '24h / Day Chg %', '24h / Day Volume', 'Ecosystem Link'].map(x => h('th', { text: x })))),
        h('tbody', null, rows.map(r => h('tr', { class: 'row', onclick: () => ctx.setSymbol(r.symbol) },
          h('td', { class: 'l sym am', text: r.symbol }),
          h('td', { class: 'l', text: r.name || r.symbol }),
          h('td', { class: 'am sym', text: fmtPx(r.price) }),
          h('td', { class: dirCls(r.changePct) + ' sym', text: fmtPct(r.changePct) }),
          h('td', { class: 'lb', text: fmtVol(r.volume) }),
          h('td', { class: 'l mu', text: 'Click to pivot terminal' })
        )))
      ) : h('div', { class: 'na', text: 'No live quotes returned for sector ecosystem' })
    );
  }
  load();
}

export function mountHDS(body, ctx) {
  body.classList.add('fill');
  const tb = h('div', { class: 'tb' },
    h('span', { class: 'lbl', text: `HDS / OWN — SHARE FLOAT STRUCTURE & SEC 13F/13D REGISTRY [${ctx.symbol}]` }),
    h('button', { text: 'CN SEC FILINGS <GO>', onclick: () => ctx.run('CN') }),
    h('button', { text: 'DES OVERVIEW <GO>', onclick: () => ctx.run('DES') })
  );
  const sc = h('div', { class: 'pb' });
  body.append(tb, sc);

  async function load() {
    const [fEnv, qEnv] = await Promise.all([
      get('fundamentals', { symbol: ctx.symbol }, 8000),
      get('quote', { symbols: ctx.symbol }, 3000)
    ]);
    ctx.status(fEnv.ok ? fEnv : qEnv);
    sc.textContent = '';

    const ed = (fEnv.ok && fEnv.data) || {};
    const sec = ed.edgar || ed;
    const fin = sec.financials || ed.financials || {};
    const q = (qEnv.ok && Array.isArray(qEnv.data) && qEnv.data[0]) || {};
    const latestVal = arr => (Array.isArray(arr) && arr.length ? arr[0].val : null);
    const shares = fin.shares ? (Array.isArray(fin.shares) ? latestVal(fin.shares) : fin.shares) : null;
    const mktCap = (shares && q.price) ? shares * q.price : null;
    const ownershipFilings = (sec.filings || ed.filings || []).filter(f => /13F|13D|13G|DEF 14A|4\b/i.test(f.form || ''));

    sc.append(
      h('div', { class: 'kv', style: 'background:#060606;border-bottom:1px solid var(--border);padding:8px' },
        h('div', { class: 'k', text: 'PARSED 13F HOLDER TABLE FEED' }),
        h('div', { class: 'v dn sym', text: 'N/A — Parsed Fund-by-Fund Institutional Holdings (13F-HR Aggregator) Feed Not Connected (requires paid SEC 13F index vendor)' }),
        h('div', { class: 'k', text: 'SEC EDGAR ENTITY / CIK' }),
        h('div', { class: 'v am sym', text: sec.cik ? `${sec.entityName || ctx.symbol} (CIK ${sec.cik})` : `Non-SEC Instrument (${ctx.symbol})` }),
        h('div', { class: 'k', text: 'REPORTED WEIGHTED SHARES & MKT CAP' }),
        h('div', { class: 'v lb sym', text: shares ? `${fmtVol(shares)} shares  •  Implied Mkt Cap: ${mktCap ? '$' + fmtVol(mktCap) : 'N/A'}` : 'N/A' })
      ),
      sec.cik ? h('div', { style: 'padding:8px 10px;border-bottom:1px solid var(--border);background:#070a0f' },
        h('a', {
          href: `https://www.sec.gov/edgar/browse/?CIK=${sec.cik}`,
          target: '_blank',
          style: 'color:#00e5ff;font-weight:bold;text-decoration:underline',
          text: `↗ OPEN OFFICIAL SEC EDGAR REGISTRY FOR ${sec.entityName || ctx.symbol} (13D / 13G / DEF 14A / FORM 4)`
        })
      ) : null,
      ownershipFilings.length ? h('table', { class: 't' },
        h('thead', null, h('tr', null, ['Form Type', 'Filed Date', 'Primary SEC Document', 'Direct EDGAR Link'].map(x => h('th', { text: x })))),
        h('tbody', null, ownershipFilings.slice(0, 12).map(fl => h('tr', { class: 'row' },
          h('td', { class: 'l sym am', text: fl.form }),
          h('td', { class: 'lb', text: fl.filingDate }),
          h('td', { class: 'l', text: fl.primaryDocDescription || fl.form }),
          h('td', { class: 'l' }, fl.url ? h('a', { href: fl.url, target: '_blank', style: 'color:#00d26a', text: 'SEC DOC ↗' }) : '-')
        )))
      ) : h('div', { class: 'na', text: 'No parsed 13F aggregator connected. Real SEC EDGAR company filings are available in CN <GO>.' })
    );
  }
  load();
}

export function mountMGMT(body, ctx) {
  body.classList.add('fill');
  const tb = h('div', { class: 'tb' },
    h('span', { class: 'lbl', text: `MGMT — GOVERNANCE FILINGS & SEC PROXY REGISTRY [${ctx.symbol}]` }),
    h('button', { text: 'HDS OWNERSHIP <GO>', onclick: () => ctx.run('HDS') }),
    h('button', { text: 'CN SEC FILINGS <GO>', onclick: () => ctx.run('CN') })
  );
  const sc = h('div', { class: 'pb' });
  body.append(tb, sc);

  async function load() {
    const fEnv = await get('fundamentals', { symbol: ctx.symbol }, 8000);
    ctx.status(fEnv);
    sc.textContent = '';

    const ed = (fEnv.ok && fEnv.data) || {};
    const sec = ed.edgar || ed;
    const proxyFilings = (sec.filings || ed.filings || []).filter(f => /DEF 14A|PRE 14A|10-K|8-K/i.test(f.form || ''));

    sc.append(
      h('div', { class: 'kv', style: 'background:#060606;border-bottom:1px solid var(--border);padding:8px' },
        h('div', { class: 'k', text: 'PARSED EXEC COMP / FORM 4 TABLE' }),
        h('div', { class: 'v dn sym', text: 'N/A — Parsed DEF 14A Executive Compensation & Insider Ownership Feed Not Connected' }),
        h('div', { class: 'k', text: 'SEC EDGAR ISSUER IDENTITY' }),
        h('div', { class: 'v am sym', text: sec.cik ? `${sec.entityName || ctx.symbol} (CIK ${sec.cik} • ${sec.sicDescription || ed.profile?.sicDescription || 'SEC Registrant'})` : `Not a SEC EDGAR Corporate Issuer (${ctx.symbol})` })
      ),
      proxyFilings.length ? h('table', { class: 't' },
        h('thead', null, h('tr', null, ['SEC Form', 'Filing Date', 'Report Date', 'Document Description', 'Official Link'].map(x => h('th', { text: x })))),
        h('tbody', null, proxyFilings.slice(0, 15).map(fl => h('tr', { class: 'row' },
          h('td', { class: 'l sym am', text: fl.form }),
          h('td', { class: 'lb', text: fl.filingDate }),
          h('td', { class: 'mu', text: fl.reportDate || '-' }),
          h('td', { class: 'l', text: fl.primaryDocDescription || 'Official Proxy / Governance Filing' }),
          h('td', { class: 'l' }, fl.url ? h('a', { href: fl.url, target: '_blank', style: 'color:#00e5ff', text: 'OPEN SEC ↗' }) : '-')
        )))
      ) : h('div', { class: 'na', text: `N/A — No live parsed proxy/insider feed for ${ctx.symbol}. Synthetic CEO compensation rows have been permanently removed.` })
    );
  }
  load();
}

function mountUnavailableInstitutionalModule(body, ctx, code, title, explanation, navActions) {
  body.classList.add('fill');
  const tb = h('div', { class: 'tb' },
    h('span', { class: 'lbl', text: `${code} — ${title} [${ctx.symbol}]` }),
    ...navActions.map(([lbl, cmd]) => h('button', { text: `${lbl} <GO>`, onclick: () => ctx.run(cmd) }))
  );
  const sc = h('div', { class: 'pb' });
  body.append(tb, sc);
  ctx.status({ source: 'feed-audit', ts: Date.now(), mode: 'N/A' });
  sc.append(
    h('div', { class: 'na', style: 'margin:14px;padding:16px;text-align:left;line-height:1.6' },
      h('div', { class: 'am sym', style: 'font-size:13px;margin-bottom:6px', text: `${code}: LIVE INSTITUTIONAL FEED NOT CONNECTED (N/A)` }),
      h('div', { style: 'color:#ccc', text: explanation })
    )
  );
}

export function mountMA(body, ctx) {
  mountUnavailableInstitutionalModule(
    body, ctx, 'MA',
    'MERGERS & ACQUISITIONS ARBITRAGE DESK',
    'Hardcoded M&A deal spreads and fabricated offer prices have been removed. Live Merger Arbitrage spreads and EV/EBITDA deal comparables require an institutional Capital IQ / Dealogic / Bloomberg MA data subscription.',
    [['FA SEC DATA', 'FA'], ['TOP NEWS', 'TOP'], ['COMP CHART', 'COMP']]
  );
}

export function mountIPO(body, ctx) {
  mountUnavailableInstitutionalModule(
    body, ctx, 'IPO / EVTS',
    'EQUITY OFFERINGS & CORPORATE EVENTS CALENDAR',
    'Fabricated pre-IPO syndicate bookbuilding valuations and static dividend dates have been removed. Live S-1 syndicate pipelines and ex-dividend corporate action feeds require an institutional IPO / CACS vendor license. Real SEC EDGAR 10-K/10-Q/8-K/S-1 filings are available in CN <GO>.',
    [['CN SEC FILINGS', 'CN'], ['ERN SEC EPS', 'ERN'], ['TOP NEWS', 'TOP']]
  );
}

export function mountESG(body, ctx) {
  mountUnavailableInstitutionalModule(
    body, ctx, 'ESG / GUID',
    'SUSTAINABILITY SCORECARD & MANAGEMENT GUIDANCE',
    'Fabricated MSCI ESG scores and synthetic street guidance spreads have been removed. Live Sustainalytics/MSCI ESG ratings and IBES corporate guidance consensus require licensed institutional feeds. Live audited SEC income & balance sheet items remain available in FA <GO>.',
    [['FA FINANCIALS', 'FA'], ['DCF VALUATION', 'DCF'], ['CRPR ALTMAN Z', 'CRPR']]
  );
}




