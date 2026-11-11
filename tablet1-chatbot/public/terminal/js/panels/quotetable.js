import { h, fmtPx, fmtPct, fmtChg, fmtVol, dirCls, flash, setText } from '../util.js';
import { get, tickOk } from '../api.js';

export const NAMES = {
  '^GSPC': 'S&P 500', '^DJI': 'Dow Jones', '^IXIC': 'Nasdaq Comp', '^RUT': 'Russell 2000', '^GSPTSE': 'S&P/TSX', '^FTSE': 'FTSE 100', '^GDAXI': 'DAX',
  '^FCHI': 'CAC 40', '^STOXX50E': 'Euro Stoxx 50', '^N225': 'Nikkei 225', '^HSI': 'Hang Seng', '^JKSE': 'IDX Composite', '^AXJO': 'ASX 200', '^KS11': 'KOSPI',
  '^NSEI': 'Nifty 50', '^TNX': 'US 10Y yield', '^FVX': 'US 5Y yield', '^TYX': 'US 30Y yield', 'GC=F': 'Gold fut', 'CL=F': 'WTI fut'
};

export const COLS = {
  sym: { k: 'sym', label: 'Security', f: t => t.symbol, cls: () => 'sym am l' },
  name: { k: 'name', label: 'Name', f: t => NAMES[t.symbol] || '', cls: () => 'mu l' },
  last: { k: 'last', label: 'Last', f: t => fmtPx(t.price), cls: () => 'am', flash: true },
  chg: { k: 'chg', label: 'Chg', f: t => fmtChg(t.chg), cls: t => dirCls(t.chg) },
  pct: { k: 'pct', label: '%Chg', f: t => fmtPct(t.chgPct), cls: t => dirCls(t.chgPct) },
  bid: { k: 'bid', label: 'Bid', f: t => fmtPx(t.bid), cls: () => 'lb' },
  ask: { k: 'ask', label: 'Ask', f: t => fmtPx(t.ask), cls: () => 'lb' },
  high: { k: 'high', label: 'High', f: t => fmtPx(t.high), cls: () => '' },
  low: { k: 'low', label: 'Low', f: t => fmtPx(t.low), cls: () => '' },
  open: { k: 'open', label: 'Open', f: t => fmtPx(t.open), cls: () => '' },
  vol: { k: 'vol', label: 'Volume', f: t => fmtVol(t.vol), cls: () => 'mu' },
  mode: { k: 'mode', label: 'Mode', f: t => t.mode || 'N/A', cls: t => t.mode === 'LIVE' ? 'up' : 'am' }
};

// rows: array of symbols; '#Title' entries are group headers.
export function quoteTable(ctx, cols, { onPick, ws = true } = {}) {
  const tbl = h('table', { class: 't' });
  const thead = h('thead', null, h('tr', null, cols.map(c => h('th', { text: c.label }))));
  const tbody = h('tbody');
  tbl.append(thead, tbody);
  let symbols = [], rows = new Map(), ticks = new Map(), unsubs = [];

  function paint(sym) {
    const r = rows.get(sym), t = ticks.get(sym);
    if (!r) return;
    const tt = t || { symbol: sym };
    const ok = tickOk(tt);
    cols.forEach((c, i) => {
      const td = r.tds[i];
      const txt = c.k === 'sym' ? sym : ok ? c.f(tt) : (c.k === 'last' ? (t ? 'N/A' : '...') : c.k === 'name' ? c.f(tt) : '');
      const prev = td._last;
      setText(td, txt, ok || c.k === 'sym' || c.k === 'name' ? c.cls(tt) : 'dn');
      td._last = txt;
      if (c.flash && ok && r.px != null && tt.price !== r.px) flash(td, tt.price > r.px ? 1 : -1);
      if (c.k === 'last' && ok) r.px = tt.price;
    });
  }
  function apply(t) {
    if (!t || !t.symbol) return;
    const old = ticks.get(t.symbol);
    if (old && t.ts && old.ts && t.ts < old.ts) return;
    ticks.set(t.symbol, { ...old, ...t });
    paint(t.symbol);
  }
  function setSymbols(list) {
    unsubs.forEach(u => u()); unsubs = [];
    symbols = list; rows = new Map(); tbody.textContent = '';
    for (const s of list) {
      if (s.startsWith('#')) { tbody.append(h('tr', { class: 'grp' }, h('td', { colspan: cols.length, text: s.slice(1) }))); continue; }
      const tds = cols.map(() => h('td'));
      const tr = h('tr', { class: 'row', onclick: () => onPick && onPick(s) }, tds);
      rows.set(s, { tr, tds, px: null });
      tbody.append(tr);
      paint(s);
    }
    if (ws) for (const s of rows.keys()) unsubs.push(ctx.sub('ticker:' + s, apply));
  }
  async function refresh() {
    const syms = [...rows.keys()];
    if (!syms.length) return null;
    const out = [];
    for (let i = 0; i < syms.length; i += 50) {
      const env = await get('quote', { symbols: syms.slice(i, i + 50).join(',') }, 3000);
      out.push(env);
      if (env.ok && Array.isArray(env.data)) env.data.forEach(apply);
    }
    const bad = out.find(e => !e.ok);
    const last = out[0];
    ctx.status({ source: last.source, ts: last.ts, mode: bad ? 'N/A' : last.mode, error: bad ? bad.error : null });
    return last;
  }
  ctx.cleanup(() => unsubs.forEach(u => u()));
  return { el: tbl, setSymbols, refresh, apply, ticks, rows, get symbols() { return symbols; } };
}
