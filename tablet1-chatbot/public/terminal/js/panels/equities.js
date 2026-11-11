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

  const navFns = ['GP', 'GIP', 'HP', 'FA', 'CF', 'DVD', 'RV', 'COMP', 'CN', 'BETA', 'HVT', 'OMON'];
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

    const grid = h('div', { style: 'display:grid;grid-template-columns:1fr 1fr;gap:8px;padding:6px' });

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
      sc.append(h('div', { class: 'na', text: `N/A — SEC EDGAR XBRL standardized statements apply to US SEC-reporting equities (current: ${ctx.symbol}). Try AAPL, MSFT, NVDA, TSLA, JPM.` }));
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
      sc.append(h('div', { class: 'na', text: `N/A — No SEC EDGAR filings for ${ctx.symbol} (try US equity ticker like AAPL, NVDA, TSLA)` }));
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

