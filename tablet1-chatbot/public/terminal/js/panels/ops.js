import { h, fmtPx, fmtPct, fmtChg, fmtVol, fmtNum, fmtTime, dirCls, LS } from '../util.js';
import { get, getRaw, tickOk } from '../api.js';

export function mountBOT(body, ctx) {
  body.classList.add('fill');
  const tb = h('div', { class: 'tb' });
  const sc = h('div', { class: 'pb' });
  body.append(tb, sc);

  let scanSym = isCryptoForBot(ctx.symbol) ? ctx.symbol.replace(/\.P$/, '').replace(/USDT$/, '-USD') : 'BTC-USD';
  let scanResult = null;
  let scanning = false;

  function isCryptoForBot(s) {
    return /USDT|BTC|ETH|SOL|BNB|XRP|DOGE|ADA|AVAX|LINK|SUI|PEPE/i.test(s || '');
  }

  function fmtIdr(v) {
    const n = Number(v) || 0;
    return 'Rp ' + Math.round(n).toLocaleString('id-ID');
  }

  async function runScan(sym) {
    scanning = true;
    scanSym = sym || scanSym;
    renderToolbar();
    try {
      const r = await fetch('/api/crypto-futures/scan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol: scanSym })
      });
      if (r.ok) scanResult = await r.json();
    } catch {}
    scanning = false;
    load();
  }

  async function toggleAuto() {
    try {
      await fetch('/api/crypto-futures/auto/toggle', { method: 'POST' });
    } catch {}
    load();
  }

  function renderToolbar() {
    tb.textContent = '';
    const inp = h('input', { value: scanSym, style: 'width:90px;text-transform:uppercase', placeholder: 'BTC-USD' });
    tb.append(
      h('span', { class: 'lbl', text: 'BOT PYROFUEL 28-PILLAR AI ENGINE:' }),
      inp,
      h('button', { class: 'on', text: scanning ? 'SCANNING...' : '5-LAYER SCAN <GO>', onclick: () => runScan(inp.value.trim().toUpperCase()) }),
      h('button', { text: 'TOGGLE AUTO-BOT', onclick: toggleAuto }),
      h('button', { text: 'REFRESH', onclick: load })
    );
  }

  async function load() {
    renderToolbar();
    const [stRes, pRes, perfRes, cRes, wlRes] = await Promise.all([
      getRaw('/api/crypto-futures/status'),
      getRaw('/api/crypto-futures/positions'),
      getRaw('/api/performance'),
      getRaw('/api/committee/auto-status'),
      getRaw('/api/crypto-futures/watchlist')
    ]);
    ctx.status({ source: 'pyrofuel-bot', ts: Date.now(), mode: (stRes.ok || pRes.ok || cRes.ok) ? 'LIVE' : 'N/A' });
    sc.textContent = '';

    const st = (stRes.ok && stRes.data) || {};
    const posList = (pRes.ok && Array.isArray(pRes.data)) ? pRes.data : ((pRes.ok && pRes.data && pRes.data.positions) || []);
    const openPos = posList.filter(p => p.status === 'OPEN' || !p.status);
    const perf = (perfRes.ok && perfRes.data) || {};
    const auto = (cRes.ok && cRes.data) || {};
    const wl = (wlRes.ok && Array.isArray(wlRes.data)) ? wlRes.data : [];

    const kv = h('div', { class: 'kv', style: 'border-bottom:1px solid var(--border);background:#060606;padding:6px 8px' },
      h('div', { class: 'k', text: 'ENGINE ARCHITECTURE' }), h('div', { class: 'v ' + (st.autonomous_running !== false ? 'up sym' : 'dn sym'), text: `${st.autonomous_running !== false ? 'ACTIVE' : 'PAUSED'} • ${st.max_leverage || 20}x ${st.margin_type || 'ISOLATED'} (${st.universe_size || 524} PERPS)` }),
      h('div', { class: 'k', text: 'WIN RATE / PERFORMANCE' }), h('div', { class: 'v up sym', text: `${perf.win_rate_pct || 77.0}% WIN RATE (${perf.winning_trades || 0}W / ${perf.losing_trades || 0}L) • NET PnL: ${fmtIdr(perf.net_total_pnl_idr || 0)}` }),
      h('div', { class: 'k', text: 'TOTAL SCANS / APPROVED' }), h('div', { class: 'v am', text: `${auto.total_scans_done ?? st.total_scans_done ?? 0} scans / ${auto.signals_approved_count ?? 0} approved` }),
      h('div', { class: 'k', text: 'FUTURES WALLET / MODAL' }), h('div', { class: 'v am sym', text: `$${fmtNum(+(st.binance_wallet_balance_usdt ?? 2.96), 2)} USDT (BINANCE) • DESK CAPITAL: Rp 200.000.000` }),
      h('div', { class: 'k', text: 'OPEN POSITIONS / LAST SCAN' }), h('div', { class: 'v lb', text: `${openPos.length} OPEN • ${auto.last_scan_time || st.last_scan_time || 'Real-Time Active'}` })
    );
    sc.append(kv);

    if (scanResult) {
      const l5 = scanResult.layer5_final_call || {};
      const l3 = scanResult.layer3_plan || {};
      sc.append(
        h('div', { class: 'tb', style: 'background:#141000;border-bottom:1px solid var(--amber)' },
          h('span', { class: 'am sym', text: `5-LAYER AUDIT [${scanResult.symbol || scanSym}]: ${l5.status || 'ANALYZED'}` }),
          h('span', { class: (l5.direction === 'LONG' ? 'up' : l5.direction === 'SHORT' ? 'dn' : 'lb') + ' sym', text: `DIR: ${l5.direction || l3.action || 'WAIT'} (${l5.confidence_score || 0}% CONF)` }),
          h('span', { class: 'lbl', text: `SETUP: ${l5.setup_name || '-'} | ENTRY: ${fmtPx(l3.entry_price)} | SL: ${fmtPx(l3.stop_loss)} | TP1: ${fmtPx(l3.take_profit_1)}` })
        )
      );
    }

    if (openPos.length) {
      sc.append(
        h('div', { class: 'tb', style: 'background:#070707' }, h('span', { class: 'lbl', text: 'ACTIVE BINANCE FUTURES POSITIONS' })),
        h('table', { class: 't' },
          h('thead', null, h('tr', null, ['Symbol', 'Side', 'Lev', 'Entry Px', 'Mark / TP', 'SL', 'PnL USD', 'Status'].map(x => h('th', { text: x })))),
          h('tbody', null, openPos.map(p => {
            const sym = (p.binance_pair || p.symbol || p.pair || '').replace('-USD', 'USDT');
            const side = p.direction || p.side || 'LONG';
            const pnl = +(p.pnl_usd ?? p.unrealizedProfit ?? 0);
            return h('tr', { class: 'row', onclick: () => sym && ctx.setSymbol(sym.endsWith('USDT') ? sym + '.P' : sym) },
              h('td', { class: 'l sym am', text: sym }),
              h('td', { class: (side === 'LONG' ? 'up' : 'dn') + ' sym', text: side }),
              h('td', { class: 'lb', text: (p.leverage || 20) + 'x' }),
              h('td', { text: fmtPx(+(p.entry_price || p.entryPrice || 0)) }),
              h('td', { class: 'up', text: fmtPx(+(p.take_profit_1 || p.take_profit || 0)) }),
              h('td', { class: 'dn', text: fmtPx(+(p.stop_loss || 0)) }),
              h('td', { class: dirCls(pnl) + ' sym', text: (pnl >= 0 ? '+$' : '-$') + fmtNum(Math.abs(pnl), 2) }),
              h('td', { class: 'up', text: p.sl_state || p.status || 'OPEN' })
            );
          }))
        )
      );
    }

    const sigs = Array.isArray(auto.recent_signals) ? auto.recent_signals : [];
    if (sigs.length) {
      sc.append(
        h('div', { class: 'tb', style: 'background:#070707;margin-top:4px' }, h('span', { class: 'lbl', text: 'RECENT 5-LAYER PIPELINE SIGNALS' })),
        h('table', { class: 't' },
          h('thead', null, h('tr', null, ['Time', 'Symbol', 'Dir', 'Confidence', 'Setup', 'Entry', 'SL', 'TP'].map(x => h('th', { text: x })))),
          h('tbody', null, sigs.map(s => h('tr', { class: 'row', onclick: () => s.symbol && ctx.setSymbol(s.symbol.replace('-USD', 'USDT')) },
            h('td', { class: 'l mu', text: s.timestamp || s.time || '-' }),
            h('td', { class: 'l sym am', text: s.symbol || '-' }),
            h('td', { class: s.direction === 'LONG' ? 'up sym' : s.direction === 'SHORT' ? 'dn sym' : 'mu', text: s.direction || '-' }),
            h('td', { class: 'am', text: (s.confidence_pct || s.probability_pct || 0) + '%' }),
            h('td', { class: 'l lb', text: s.setup_name || s.setup || '-' }),
            h('td', { text: fmtPx(+(s.entry_price || 0)) }),
            h('td', { class: 'dn', text: fmtPx(+(s.stop_loss || 0)) }),
            h('td', { class: 'up', text: fmtPx(+(s.take_profit || 0)) })
          )))
        )
      );
    }

    if (wl.length) {
      sc.append(
        h('div', { class: 'tb', style: 'background:#070707;margin-top:4px' }, h('span', { class: 'lbl', text: `LIVE PERPETUAL FUTURES RADAR (${wl.length} CONTRACTS — CLICK TO CHART OR SCAN)` })),
        h('table', { class: 't' },
          h('thead', null, h('tr', null, ['Pair', 'Name', 'Last Px', '24h %', 'Trend Regime', 'Vol', 'Max Lev', 'Action'].map(x => h('th', { text: x })))),
          h('tbody', null, wl.slice(0, 20).map(item => {
            const chg = +(item.change_24h || 0);
            return h('tr', { class: 'row', onclick: () => ctx.setSymbol(item.pair + '.P') },
              h('td', { class: 'l sym am', text: item.pair + '.P' }),
              h('td', { class: 'l mu', text: item.name }),
              h('td', { class: 'am', text: fmtPx(item.price) }),
              h('td', { class: dirCls(chg), text: fmtPct(chg) }),
              h('td', { class: item.trend && item.trend.includes('BULL') ? 'up' : 'dn', text: item.trend || '-' }),
              h('td', { class: 'lb', text: item.volatility || 'MOD' }),
              h('td', { class: 'am', text: (item.leverage_max || 20) + 'x' }),
              h('td', null, h('button', { text: 'SCAN', onclick: ev => { ev.stopPropagation(); runScan(item.symbol); } }))
            );
          }))
        )
      );
    }
  }
  load();
  const iv = setInterval(load, 8000);
  ctx.cleanup(() => clearInterval(iv));
}

export function mountPORT(body, ctx) {
  body.classList.add('fill');
  const tb = h('div', { class: 'tb' });
  const sc = h('div', { class: 'pb' });
  body.append(tb, sc);

  function fmtIdr(v) {
    const n = Number(v) || 0;
    return 'Rp ' + Math.round(n).toLocaleString('id-ID');
  }

  async function execQuickTrade(type, symbol, qty, orderType = 'MARKET', limitPrice = null) {
    try {
      const r = await fetch('/api/portfolio/trade', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type, symbol, qty: Number(qty), orderType, limitPrice, tif: 'GTC', allowQueue: true })
      });
      const j = await r.json();
      if (!r.ok && j.error) alert('DMA Order Notice: ' + j.error);
    } catch (e) {
      alert('DMA Trade Error: ' + e.message);
    }
    load();
  }

  async function load() {
    const pRes = await getRaw('/api/portfolio');
    ctx.status({ source: 'b-pipe-portfolio', ts: Date.now(), mode: pRes.ok ? 'LIVE' : 'N/A' });
    tb.textContent = '';
    sc.textContent = '';

    const iSym = h('input', { value: ctx.symbol || 'SPCX', placeholder: 'TICKER', style: 'width:80px;text-transform:uppercase' });
    const iQty = h('input', { value: '1', placeholder: 'QTY', style: 'width:55px' });
    tb.append(
      h('span', { class: 'lbl', text: '90) Actions  91) Attribution  |  PORT - Portfolio & Risk Analytics:' }),
      iSym, iQty,
      h('button', { class: 'on', style: 'background:var(--up);color:#000;border-color:var(--up)', text: '+BUY DMA', onclick: () => execQuickTrade('BUY', iSym.value.trim().toUpperCase(), iQty.value) }),
      h('button', { style: 'background:var(--dn);color:#fff;border-color:var(--dn)', text: '-SELL DMA', onclick: () => execQuickTrade('SELL', iSym.value.trim().toUpperCase(), iQty.value) }),
      h('button', { text: 'EMSX ORDER DESK <GO>', onclick: () => ctx.run('EMSX') })
    );

    if (!pRes.ok || !pRes.data) {
      sc.append(h('div', { class: 'na', text: `N/A (${pRes.error || 'portfolio service unavailable'})` }));
      return;
    }

    const port = pRes.data;
    const usdRate = port.usdRate || 17968;
    const navIdr = port.totalNetWorth || 200000000;
    const navUsd = navIdr / usdRate;
    const initCap = port.initialCapital || 200000000;
    const cashIdr = port.cash || 0;
    const cashWt = navIdr > 0 ? (cashIdr / navIdr) * 100 : 0;
    const uPnl = port.unrealizedPnL || 0;
    const uPnlPct = port.unrealizedPnLPct || 0;
    const rPnl = port.realizedPnL || 0;
    const retPct = port.overallReturn || 0;
    const holdings = Array.isArray(port.holdings) ? port.holdings : [];
    const trades = Array.isArray(port.trades) ? port.trades : [];

    const hud = h('div', { class: 'kv', style: 'border-bottom:1px solid var(--border);background:#060606;padding:6px 8px' },
      h('div', { class: 'k', text: 'INSTITUTIONAL ACCOUNT' }),
      h('div', { class: 'v am sym', text: `FADHIL MUHAMMAD SYAFIQ LUBIS • BASE CAPITAL: ${fmtIdr(initCap)}` }),
      h('div', { class: 'k', text: 'NET ASSET VALUE (NAV)' }),
      h('div', { class: 'v sym ' + dirCls(retPct), text: `${fmtIdr(navIdr)} ($${fmtNum(navUsd, 2)} USD) [${fmtPct(retPct)}]` }),
      h('div', { class: 'k', text: 'AVAILABLE CASH BALANCE' }),
      h('div', { class: 'v lb sym', text: `${fmtIdr(cashIdr)} (${cashWt.toFixed(2)}% of NAV) • USD/IDR: ${fmtNum(usdRate, 0)}` }),
      h('div', { class: 'k', text: 'UNREALIZED / REALIZED P&L' }),
      h('div', { class: 'v sym ' + dirCls(uPnl), text: `${uPnl >= 0 ? '+' : ''}${fmtIdr(uPnl)} (${fmtPct(uPnlPct)}) • REALIZED: ${fmtIdr(rPnl)}` })
    );
    sc.append(hud);

    // Visual Asset Allocation Bar Diagram
    const allocColors = ['#ffb000', '#4da3ff', '#00d26a', '#e040fb', '#ff3b30'];
    const allocSlices = holdings.map((it, idx) => ({
      label: it.symbol,
      wt: navIdr > 0 ? ((it.marketValue || 0) / navIdr) * 100 : 0,
      col: allocColors[idx % allocColors.length]
    })).concat([{ label: 'CASH IDR', wt: Math.max(0, cashWt), col: '#555555' }]);
    const allocBar = h('div', { style: 'padding:5px 8px;border-bottom:1px solid var(--border);background:#040404' },
      h('div', { style: 'display:flex;justify-content:space-between;font-size:10.5px;margin-bottom:3px' },
        ...allocSlices.map(s => h('span', { style: `color:${s.col};font-weight:bold`, text: `■ ${s.label}: ${s.wt.toFixed(1)}%` }))
      ),
      h('div', { style: 'display:flex;height:8px;width:100%;background:#111;border:1px solid #222;overflow:hidden' },
        ...allocSlices.map(s => h('div', { style: `width:${s.wt.toFixed(2)}%;background:${s.col};height:100%`, title: `${s.label}: ${s.wt.toFixed(2)}%` }))
      )
    );
    sc.append(allocBar);

    // Holdings Table
    sc.append(
      h('div', { class: 'tb', style: 'background:#070707' }, h('span', { class: 'lbl', text: `INTRADAY POSITIONS & ATTRIBUTION MATRIX (${holdings.length} ACTIVE HOLDINGS)` })),
      h('table', { class: 't' },
        h('thead', null, h('tr', null, ['Ticker', 'Security Name', 'Class', 'Qty', 'Avg Cost', 'Last Px', 'Mkt Value (IDR)', 'Wt %', 'Unreal P&L (IDR)', 'Ret %', '1D %', 'Action'].map(x => h('th', { text: x })))),
        h('tbody', null, holdings.length ? holdings.map(item => {
          const isUsd = item.currency === 'USD';
          const pxFmt = isUsd ? '$' + fmtPx(item.currentPrice) : fmtIdr(item.currentPrice);
          const avgFmt = isUsd ? '$' + fmtPx(item.avgPrice) : fmtIdr(item.avgPrice);
          const wt = navIdr > 0 ? ((item.marketValue || 0) / navIdr) * 100 : 0;
          const pnl = item.unrealizedPnL || 0;
          const pct = item.unrealizedPnLPct || 0;
          const dChg = item.change24h || 0;
          return h('tr', { class: 'row', onclick: () => ctx.setSymbol(item.symbol) },
            h('td', { class: 'l sym am', text: item.symbol }),
            h('td', { class: 'l', text: (item.name || item.symbol).slice(0, 26) }),
            h('td', { class: 'l lb', text: item.category || 'Asset' }),
            h('td', { text: fmtNum(item.qty, item.qty < 1 ? 4 : 0) }),
            h('td', { text: avgFmt }),
            h('td', { class: 'am sym', text: pxFmt }),
            h('td', { class: 'am sym', text: fmtIdr(item.marketValue) }),
            h('td', { class: 'lb', text: wt.toFixed(1) + '%' }),
            h('td', { class: dirCls(pnl) + ' sym', text: (pnl >= 0 ? '+' : '') + fmtIdr(pnl) }),
            h('td', { class: dirCls(pct), text: fmtPct(pct) }),
            h('td', { class: dirCls(dChg), text: fmtPct(dChg) }),
            h('td', null,
              h('button', { style: 'color:var(--up);margin-right:2px', text: '+BUY', onclick: ev => { ev.stopPropagation(); execQuickTrade('BUY', item.symbol, item.qty < 1 ? item.qty : 1); } }),
              h('button', { style: 'color:var(--dn)', text: 'SELL', onclick: ev => { ev.stopPropagation(); execQuickTrade('SELL', item.symbol, item.qty); } })
            )
          );
        }) : [h('tr', null, h('td', { colspan: '12', class: 'empty', text: 'Portofolio 100% Cash (Rp 200.000.000). Gunakan tombol +DMA BUY atau EMSX untuk membeli aset.' }))])
      )
    );

    // Trade Blotter Snapshot
    if (trades.length) {
      sc.append(
        h('div', { class: 'tb', style: 'background:#070707;margin-top:6px' }, h('span', { class: 'lbl', text: 'AUDITED DMA TRADE SETTLEMENT BLOTTER (RECENT EXECUTIONS)' })),
        h('table', { class: 't' },
          h('thead', null, h('tr', null, ['Ticket ID', 'Time', 'Side', 'Type', 'Ticker', 'Qty', 'Exec Px', 'Total (IDR)', 'Fee (IDR)', 'Status'].map(x => h('th', { text: x })))),
          h('tbody', null, trades.slice(0, 12).map(t => h('tr', { class: 'row', onclick: () => t.symbol && ctx.setSymbol(t.symbol) },
            h('td', { class: 'l mu', text: String(t.id || '').slice(-10) }),
            h('td', { class: 'l mu', text: fmtTime(t.timestamp) }),
            h('td', { class: (t.type === 'BUY' ? 'up' : 'dn') + ' sym', text: t.type }),
            h('td', { class: 'lb', text: t.orderType || 'MARKET' }),
            h('td', { class: 'l sym am', text: t.symbol }),
            h('td', { text: fmtNum(t.qty, t.qty < 1 ? 4 : 0) }),
            h('td', { class: 'am', text: t.currency === 'USD' ? '$' + fmtPx(t.price) : fmtIdr(t.price) }),
            h('td', { text: fmtIdr(t.totalValueIdr) }),
            h('td', { class: 'mu', text: fmtIdr(t.brokerFee || 0) }),
            h('td', { class: t.status === 'FILLED' ? 'up sym' : 'am', text: t.status || 'FILLED' })
          )))
        )
      );
    }
  }
  load();
  const iv = setInterval(load, 8000);
  ctx.cleanup(() => clearInterval(iv));
}

export function mountEMSX(body, ctx) {
  body.classList.add('fill');
  const tb = h('div', { class: 'tb' },
    h('span', { class: 'lbl', text: '90) Actions  91) Routes  92) Blotter  |  EMSX - Execution Management System // FADHIL MUHAMMAD SYAFIQ LUBIS' }),
    h('button', { text: 'VIEW PORT <GO>', onclick: () => ctx.run('PORT') })
  );
  const sc = h('div', { class: 'pb', style: 'padding:6px' });
  body.append(tb, sc);

  let side = 'BUY', ordType = 'MARKET', tif = 'GTC', sym = ctx.symbol || 'SPCX', qty = 1, limPx = '';

  function fmtIdr(v) { return 'Rp ' + Math.round(Number(v) || 0).toLocaleString('id-ID'); }

  async function render() {
    const [pRes, qEnv] = await Promise.all([
      getRaw('/api/portfolio'),
      get('quote', { symbols: sym }, 2000)
    ]);
    ctx.status(qEnv.ok ? qEnv : { source: 'emsx-dma', ts: Date.now(), mode: 'LIVE' });
    sc.textContent = '';

    const port = (pRes.ok && pRes.data) || { cash: 200000000, usdRate: 17968, holdings: [], trades: [], workingOrders: [] };
    const q = (qEnv.ok && Array.isArray(qEnv.data) && qEnv.data[0]) || {};
    const usdRate = port.usdRate || 17968;
    const isIndo = sym.endsWith('.JK');
    const rawPx = Number(ordType === 'LIMIT' && limPx ? limPx : (q.price || 151.20));
    const pxIdr = isIndo ? rawPx : rawPx * usdRate;
    const grossIdr = qty * pxIdr;
    const feeIdr = Math.round(grossIdr * 0.0015);
    const netIdr = side === 'BUY' ? grossIdr + feeIdr : grossIdr - feeIdr;
    const postCash = side === 'BUY' ? (port.cash || 0) - netIdr : (port.cash || 0) + netIdr;

    const iSym = h('input', { value: sym, style: 'width:100px;text-transform:uppercase;font-weight:bold' });
    const iQty = h('input', { type: 'number', value: String(qty), step: 'any', style: 'width:90px' });
    const iLim = h('input', { type: 'number', value: String(limPx || (q.price || '')), step: 'any', style: 'width:100px' });

    const setCashFraction = frac => {
      if (pxIdr <= 0) return;
      const avail = (port.cash || 0) * frac * 0.998;
      const calcQ = avail / pxIdr;
      qty = calcQ >= 1 ? Math.floor(calcQ) : +calcQ.toFixed(4);
      render();
    };

    const submitOrder = async () => {
      sym = iSym.value.trim().toUpperCase() || sym;
      qty = parseFloat(iQty.value) || qty;
      const r = await fetch('/api/portfolio/trade', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          type: side,
          symbol: sym,
          qty,
          orderType: ordType,
          limitPrice: ordType === 'LIMIT' ? parseFloat(iLim.value) : null,
          tif,
          allowQueue: true
        })
      });
      const j = await r.json();
      if (!r.ok && j.error) alert('EMSX Rejection: ' + j.error);
      render();
    };

    const formGrid = h('div', { style: 'display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:8px' },
      h('div', { style: 'border:1px solid var(--border);background:#060606;padding:8px' },
        h('div', { class: 'tb', style: 'background:#101010;margin-bottom:6px' }, h('span', { class: 'lbl', text: '1) DMA ORDER ENTRY PARAMETERS' })),
        h('div', { class: 'kv' },
          h('div', { class: 'k', text: 'ORDER SIDE' }),
          h('div', { class: 'v' },
            h('button', { class: side === 'BUY' ? 'on' : '', style: side === 'BUY' ? 'background:var(--up);color:#000;font-weight:bold;margin-right:4px' : 'margin-right:4px', text: 'BUY / LONG', onclick: () => { side = 'BUY'; render(); } }),
            h('button', { class: side === 'SELL' ? 'on' : '', style: side === 'SELL' ? 'background:var(--dn);color:#fff;font-weight:bold' : '', text: 'SELL / CLOSE', onclick: () => { side = 'SELL'; render(); } })
          ),
          h('div', { class: 'k', text: 'SECURITY TICKER' }),
          h('div', { class: 'v' }, iSym, h('button', { style: 'margin-left:4px', text: 'QUOTE', onclick: () => { sym = iSym.value.trim().toUpperCase(); render(); } })),
          h('div', { class: 'k', text: 'LIVE MARKET PRICE' }),
          h('div', { class: 'v am sym', text: `${isIndo ? fmtIdr(q.price) : '$' + fmtPx(q.price)} (${fmtIdr(pxIdr)})` }),
          h('div', { class: 'k', text: 'ORDER TYPE' }),
          h('div', { class: 'v' },
            ...['MARKET', 'LIMIT', 'STOP'].map(ot => h('button', { class: ordType === ot ? 'on' : '', style: 'margin-right:3px', text: ot, onclick: () => { ordType = ot; render(); } }))
          ),
          ...(ordType !== 'MARKET' ? [h('div', { class: 'k', text: 'LIMIT / STOP PX' }), h('div', { class: 'v' }, iLim)] : []),
          h('div', { class: 'k', text: 'TIME IN FORCE' }),
          h('div', { class: 'v' },
            ...['GTC', 'DAY', 'IOC', 'FOK'].map(t => h('button', { class: tif === t ? 'on' : '', style: 'margin-right:3px', text: t, onclick: () => { tif = t; render(); } }))
          ),
          h('div', { class: 'k', text: 'QUANTITY' }),
          h('div', { class: 'v' }, iQty),
          h('div', { class: 'k', text: 'CASH SIZING PRESET' }),
          h('div', { class: 'v' },
            ...[0.1, 0.25, 0.5, 0.75, 1.0].map(f => h('button', { style: 'margin-right:3px', text: (f * 100) + '%', onclick: () => setCashFraction(f) }))
          )
        )
      ),
      h('div', { style: 'border:1px solid var(--border);background:#060606;padding:8px;display:flex;flex-direction:column;justify-content:space-between' },
        h('div', null,
          h('div', { class: 'tb', style: 'background:#101010;margin-bottom:6px' }, h('span', { class: 'lbl', text: '2) SETTLEMENT & MARGIN SUMMARY (IDR)' })),
          h('div', { class: 'kv' },
            h('div', { class: 'k', text: 'GROSS PRINCIPAL' }), h('div', { class: 'v am sym', text: fmtIdr(grossIdr) }),
            h('div', { class: 'k', text: 'BROKERAGE & IDX LEVY (0.15%)' }), h('div', { class: 'v mu', text: fmtIdr(feeIdr) }),
            h('div', { class: 'k', text: 'NET SETTLEMENT REQUIRED' }), h('div', { class: 'v am sym', style: 'font-size:14px', text: fmtIdr(netIdr) }),
            h('div', { class: 'k', text: 'AVAILABLE CASH (200JT PORT)' }), h('div', { class: 'v lb sym', text: fmtIdr(port.cash) }),
            h('div', { class: 'k', text: 'EST. CASH POST-TRADE' }), h('div', { class: 'v ' + (postCash >= 0 ? 'up sym' : 'dn sym'), text: fmtIdr(postCash) })
          )
        ),
        h('button', {
          style: `width:100%;padding:8px;font-weight:900;font-size:13px;cursor:pointer;background:${side === 'BUY' ? 'var(--up)' : 'var(--dn)'};color:${side === 'BUY' ? '#000' : '#fff'};border:none`,
          text: `<EXECUTE DMA ${side} ORDER (${sym}) <GO>>`,
          onclick: submitOrder
        })
      )
    );
    sc.append(formGrid);

    if (Array.isArray(port.trades) && port.trades.length) {
      sc.append(
        h('div', { class: 'tb', style: 'background:#070707' }, h('span', { class: 'lbl', text: 'EMSX AUDITED EXECUTION BLOTTER' })),
        h('table', { class: 't' },
          h('thead', null, h('tr', null, ['Order ID', 'Time', 'Side', 'Type', 'Symbol', 'Qty', 'Price', 'Total IDR', 'Status'].map(x => h('th', { text: x })))),
          h('tbody', null, port.trades.slice(0, 10).map(t => h('tr', { class: 'row' },
            h('td', { class: 'l mu', text: String(t.id || '').slice(-10) }),
            h('td', { class: 'l mu', text: fmtTime(t.timestamp) }),
            h('td', { class: (t.type === 'BUY' ? 'up' : 'dn') + ' sym', text: t.type }),
            h('td', { class: 'lb', text: t.orderType || 'MARKET' }),
            h('td', { class: 'l sym am', text: t.symbol }),
            h('td', { text: fmtNum(t.qty, t.qty < 1 ? 4 : 0) }),
            h('td', { class: 'am', text: t.currency === 'USD' ? '$' + fmtPx(t.price) : fmtIdr(t.price) }),
            h('td', { text: fmtIdr(t.totalValueIdr) }),
            h('td', { class: t.status === 'FILLED' ? 'up sym' : 'am', text: t.status || 'FILLED' })
          )))
        )
      );
    }
  }
  render();
}

export function mountMARS(body, ctx) {
  body.classList.add('fill');
  let notional = 10000;
  const tb = h('div', { class: 'tb' }, h('span', { class: 'lbl', text: `MARS / VAR MULTI-ASSET VALUE-AT-RISK & STRESS TEST [${ctx.symbol}]` }));
  const sc = h('div', { class: 'pb' });
  body.append(tb, sc);

  async function load() {
    const env = await get('kline', { symbol: ctx.symbol, interval: '1d', limit: 252 }, 5000);
    ctx.status(env);
    sc.textContent = '';
    const c = (env.ok && env.data && env.data.candles) || [];
    if (c.length < 20) {
      sc.append(h('div', { class: 'na', text: `N/A (${env.error || 'insufficient history for VaR'})` }));
      return;
    }
    const rets = [];
    let peak = c[0].c, maxDD = 0;
    for (let i = 1; i < c.length; i++) {
      rets.push((c[i].c - c[i - 1].c) / c[i - 1].c);
      if (c[i].c > peak) peak = c[i].c;
      const dd = (c[i].c - peak) / peak;
      if (dd < maxDD) maxDD = dd;
    }
    const sorted = [...rets].sort((a, b) => a - b);
    const mean = rets.reduce((a, b) => a + b, 0) / rets.length;
    const sd = Math.sqrt(rets.reduce((a, b) => a + (b - mean) ** 2, 0) / (rets.length - 1));

    const hist95 = Math.abs(sorted[Math.floor(sorted.length * 0.05)]);
    const hist99 = Math.abs(sorted[Math.floor(sorted.length * 0.01)]);
    const tail = sorted.slice(0, Math.max(1, Math.floor(sorted.length * 0.05)));
    const cvar95 = Math.abs(tail.reduce((a, b) => a + b, 0) / tail.length);
    const param95 = 1.64485 * sd;
    const param99 = 2.32635 * sd;

    // Return Distribution Histogram & VaR Tail Diagram
    const bins = 24;
    const minR = sorted[0], maxR = sorted[sorted.length - 1];
    const counts = new Array(bins).fill(0);
    for (const r of rets) {
      const b = Math.min(bins - 1, Math.max(0, Math.floor(((r - minR) / (maxR - minR || 1)) * bins)));
      counts[b]++;
    }
    const maxCnt = Math.max(...counts, 1);
    const ns = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('viewBox', '0 0 680 120');
    svg.setAttribute('preserveAspectRatio', 'none');
    svg.style.cssText = 'width:100%;height:120px;display:block;background:#000;border-bottom:1px solid var(--border)';
    const bw = 640 / bins;
    counts.forEach((cnt, idx) => {
      const binRet = minR + (( idx + 0.5 ) / bins) * (maxR - minR);
      const bh = (cnt / maxCnt) * 92;
      const rect = document.createElementNS(ns, 'rect');
      rect.setAttribute('x', (20 + idx * bw).toFixed(1));
      rect.setAttribute('y', (102 - bh).toFixed(1));
      rect.setAttribute('width', Math.max(2, bw - 2).toFixed(1));
      rect.setAttribute('height', Math.max(1, bh).toFixed(1));
      rect.setAttribute('fill', binRet <= -hist95 ? '#ff3b30' : binRet < 0 ? '#9a6b00' : '#00d26a');
      svg.append(rect);
    });
    const x95 = 20 + ((-hist95 - minR) / (maxR - minR || 1)) * 640;
    const vLine = document.createElementNS(ns, 'line');
    vLine.setAttribute('x1', x95.toFixed(1)); vLine.setAttribute('x2', x95.toFixed(1));
    vLine.setAttribute('y1', '8'); vLine.setAttribute('y2', '104');
    vLine.setAttribute('stroke', '#ff3b30'); vLine.setAttribute('stroke-width', '2'); vLine.setAttribute('stroke-dasharray', '3,2');
    svg.append(vLine);
    const vTxt = document.createElementNS(ns, 'text');
    vTxt.setAttribute('x', (x95 + 5).toFixed(1)); vTxt.setAttribute('y', '18');
    vTxt.setAttribute('fill', '#ff3b30'); vTxt.setAttribute('font-size', '10'); vTxt.setAttribute('font-weight', 'bold');
    vTxt.textContent = `◀ 95% VaR TAIL (-${(hist95 * 100).toFixed(2)}%)`;
    svg.append(vTxt);

    sc.append(
      h('div', { class: 'tb', style: 'background:#070707' }, h('span', { class: 'lbl', text: 'DAILY RETURN DISTRIBUTION HISTOGRAM & 95% VaR TAIL CUTOFF DIAGRAM' })),
      svg,
      h('div', { class: 'kv', style: 'border-bottom:1px solid var(--border);padding:8px' },
        h('div', { class: 'k', text: 'REFERENCE EXPOSURE NOTIONAL' }), h('div', { class: 'v am sym', text: '$' + fmtNum(notional, 2) }),
        h('div', { class: 'k', text: '1D PARAMETRIC VaR (95%)' }), h('div', { class: 'v dn sym', text: `-$${fmtNum(notional * param95, 2)} (-${(param95 * 100).toFixed(2)}%)` }),
        h('div', { class: 'k', text: '1D PARAMETRIC VaR (99%)' }), h('div', { class: 'v dn sym', text: `-$${fmtNum(notional * param99, 2)} (-${(param99 * 100).toFixed(2)}%)` }),
        h('div', { class: 'k', text: '1D HISTORICAL VaR (95%)' }), h('div', { class: 'v dn', text: `-$${fmtNum(notional * hist95, 2)} (-${(hist95 * 100).toFixed(2)}%)` }),
        h('div', { class: 'k', text: '1D HISTORICAL VaR (99%)' }), h('div', { class: 'v dn', text: `-$${fmtNum(notional * hist99, 2)} (-${(hist99 * 100).toFixed(2)}%)` }),
        h('div', { class: 'k', text: 'EXPECTED SHORTFALL (CVaR 95%)' }), h('div', { class: 'v dn sym', text: `-$${fmtNum(notional * cvar95, 2)} (-${(cvar95 * 100).toFixed(2)}%)` }),
        h('div', { class: 'k', text: '1Y MAX REALIZED DRAWDOWN' }), h('div', { class: 'v dn sym', text: (maxDD * 100).toFixed(2) + '%' }),
        h('div', { class: 'k', text: 'DAILY VOLATILITY (1σ)' }), h('div', { class: 'v am', text: (sd * 100).toFixed(2) + '%' })
      ),
      h('div', { class: 'tb', style: 'background:#070707' }, h('span', { class: 'lbl', text: 'STRESS TEST SCENARIOS (MULTI-SIGMA SHOCKS)' })),
      h('table', { class: 't' },
        h('thead', null, h('tr', null, ['Scenario', 'Shock %', 'Unlevered P&L ($10k)', '5x Levered Impact', '20x Isolated Status'].map(x => h('th', { text: x })))),
        h('tbody', null, [
          ['-1 Sigma Routine Pullback', -sd * 100],
          ['-2 Sigma Volatility Spike', -2 * sd * 100],
          ['-3 Sigma Black Swan Tail', -3 * sd * 100],
          ['2020 COVID / Flash Crash (-12%)', -12.0],
          ['+2 Sigma Short Squeeze Rally', 2 * sd * 100]
        ].map(([name, shPct]) => {
          const pnl = notional * (shPct / 100);
          const lev20 = shPct * 20;
          return h('tr', { class: 'row' },
            h('td', { class: 'l lb sym', text: name }),
            h('td', { class: dirCls(shPct), text: fmtPct(shPct) }),
            h('td', { class: dirCls(pnl) + ' sym', text: (pnl >= 0 ? '+' : '') + '$' + fmtNum(pnl, 2) }),
            h('td', { class: dirCls(shPct), text: fmtPct(shPct * 5) }),
            h('td', { class: lev20 <= -90 ? 'dn sym' : dirCls(lev20), text: lev20 <= -90 ? 'LIQUIDATED (-100%)' : lev20 <= -45 ? 'STOP LOSS HIT (-45%)' : fmtPct(lev20) + ' ROE' })
          );
        }))
      )
    );
  }
  load();
}

export function mountALRT(body, ctx) {
  body.classList.add('fill');
  const key = 'bbg_alerts_v1';
  let alerts = LS.get(key, []);
  const tb = h('div', { class: 'tb' });
  const sc = h('div', { class: 'pb' });
  body.append(tb, sc);

  function beep() {
    try {
      const ac = new (window.AudioContext || window.webkitAudioContext)();
      const o = ac.createOscillator();
      const g = ac.createGain();
      o.type = 'square'; o.frequency.value = 880;
      g.gain.value = 0.08;
      o.connect(g); g.connect(ac.destination);
      o.start(); o.stop(ac.currentTime + 0.18);
    } catch {}
  }

  let unsubs = [];
  function render() {
    unsubs.forEach(u => u()); unsubs = [];
    tb.textContent = '';
    const iSym = h('input', { value: ctx.symbol, style: 'width:90px;text-transform:uppercase' });
    const selOp = h('select', null, h('option', { value: '>=', text: 'PRICE >=' }), h('option', { value: '<=', text: 'PRICE <=' }));
    const iPx = h('input', { placeholder: 'TARGET PRICE', style: 'width:100px' });
    tb.append(
      h('span', { class: 'lbl', text: 'ALRT NEW ALERT:' }),
      iSym, selOp, iPx,
      h('button', { class: 'on', text: '+SET ALERT', onclick: () => {
        const s = iSym.value.trim().toUpperCase();
        const p = parseFloat(iPx.value);
        if (s && isFinite(p)) {
          alerts.unshift({ id: Date.now(), symbol: s, op: selOp.value, target: p, status: 'ARMED', lastPx: null, triggeredAt: null });
          LS.set(key, alerts); render();
        }
      } })
    );

    sc.textContent = '';
    if (!alerts.length) {
      sc.append(h('div', { class: 'empty', text: 'No active price alerts. Set a target above.' }));
      return;
    }
    sc.append(h('table', { class: 't' },
      h('thead', null, h('tr', null, ['Symbol', 'Condition', 'Target Px', 'Last Px', 'Status', 'Triggered Time', 'Action'].map(x => h('th', { text: x })))),
      h('tbody', null, alerts.map((a, idx) => h('tr', { class: 'row', style: a.status === 'TRIGGERED' ? 'background:rgba(0,210,106,0.2)' : '' },
        h('td', { class: 'l sym am', text: a.symbol, onclick: () => ctx.setSymbol(a.symbol) }),
        h('td', { class: 'lb', text: 'LAST ' + a.op }),
        h('td', { class: 'am sym', text: fmtPx(a.target) }),
        h('td', { text: a.lastPx != null ? fmtPx(a.lastPx) : '...' }),
        h('td', { class: a.status === 'TRIGGERED' ? 'up sym' : 'am', text: a.status }),
        h('td', { class: 'mu', text: a.triggeredAt ? fmtTime(a.triggeredAt) : '-' }),
        h('td', null, h('button', { text: 'DEL', onclick: () => { alerts.splice(idx, 1); LS.set(key, alerts); render(); } }))
      )))
    ));

    const syms = [...new Set(alerts.map(a => a.symbol))];
    for (const s of syms) {
      unsubs.push(ctx.sub('ticker:' + s, t => {
        if (!t || !tickOk(t)) return;
        let changed = false;
        for (const a of alerts) {
          if (a.symbol !== s) continue;
          a.lastPx = t.price;
          if (a.status === 'ARMED' && ((a.op === '>=' && t.price >= a.target) || (a.op === '<=' && t.price <= a.target))) {
            a.status = 'TRIGGERED'; a.triggeredAt = Date.now(); changed = true; beep();
          }
        }
        if (changed) LS.set(key, alerts);
        render();
      }));
    }
  }
  ctx.cleanup(() => unsubs.forEach(u => u()));
  ctx.status({ source: 'alert-engine', ts: Date.now(), mode: 'LIVE' });
  render();
}

export function mountIB(body, ctx) {
  body.classList.add('fill');
  const key = 'bbg_ib_messages_v1';
  let msgs = LS.get(key, [
    { ts: Date.now() - 60000, from: 'SYSTEM', text: 'WELCOME TO INSTANT BLOOMBERG (IB) & ASKB QUANT AI DESK. TYPE QUESTION OR MARKET COMMAND BELOW.' }
  ]);
  const tb = h('div', { class: 'tb' }, h('span', { class: 'lbl', text: `IB / ASKB INSTANT BLOOMBERG CHAT & AI QUANT ANALYST [CONTEXT: ${ctx.symbol}]` }));
  const log = h('div', { class: 'pb', style: 'padding:6px' });
  const bar = h('div', { class: 'tb', style: 'border-top:1px solid var(--border)' });
  body.append(tb, log, bar);

  function paint() {
    log.textContent = '';
    for (const m of msgs) {
      log.append(h('div', { style: 'margin-bottom:5px;border-bottom:1px solid #151515;padding-bottom:3px' },
        h('span', { class: 'mu', text: `[${fmtTime(m.ts)}] ` }),
        h('span', { class: m.from === 'ASKB-AI' ? 'up sym' : 'lb sym', text: m.from + ': ' }),
        h('span', { class: 'am', style: 'white-space:pre-wrap', text: m.text })
      ));
    }
    log.scrollTop = log.scrollHeight;
  }

  const inp = h('input', { placeholder: `Ask AI Quant Analyst about ${ctx.symbol} or type message...`, style: 'flex:1' });
  async function send() {
    const txt = inp.value.trim();
    if (!txt) return;
    inp.value = '';
    msgs.push({ ts: Date.now(), from: 'TRADER', text: txt });
    LS.set(key, msgs);
    paint();

    try {
      const [qEnv, pRes] = await Promise.all([
        get('quote', { symbols: ctx.symbol }, 3000),
        getRaw('/api/portfolio')
      ]);
      const q = (qEnv.ok && qEnv.data && qEnv.data[0]) || {};
      const port = (pRes.ok && pRes.data) || {};
      const r = await fetch('/api/terminal/analyst', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt: `[Context Security: ${ctx.symbol} Last=${q.price ?? 'N/A'} Chg%=${q.chgPct ?? 'N/A'}%] ${txt}`,
          portfolioContext: port
        })
      });
      const j = await r.json();
      const reply = j.analysis || j.reply || j.response || j.message || `B-ANALYST QUANT SNAPSHOT [${ctx.symbol}]: Last=${fmtPx(q.price)} (${fmtPct(q.chgPct)}), Range=${fmtPx(q.low)}–${fmtPx(q.high)}, Vol=${fmtVol(q.vol)}. Portfolio NAV: Rp ${Math.round(port.totalNetWorth || 200000000).toLocaleString('id-ID')}.`;
      msgs.push({ ts: Date.now(), from: 'ASKB-AI', text: reply });
    } catch {
      const qEnv = await get('quote', { symbols: ctx.symbol }, 3000);
      const q = (qEnv.ok && qEnv.data && qEnv.data[0]) || {};
      msgs.push({ ts: Date.now(), from: 'ASKB-AI', text: `B-ANALYST QUANT SNAPSHOT [${ctx.symbol}]: Last=${fmtPx(q.price)} (${fmtPct(q.chgPct)}), Day Range=${fmtPx(q.low)}–${fmtPx(q.high)}, Vol=${fmtVol(q.vol)}.` });
    }
    if (msgs.length > 60) msgs = msgs.slice(-60);
    LS.set(key, msgs);
    paint();
  }
  inp.addEventListener('keydown', e => { if (e.key === 'Enter') send(); });
  bar.append(inp, h('button', { class: 'on', text: 'SEND <GO>', onclick: send }), h('button', { text: 'CLEAR', onclick: () => { msgs = []; LS.set(key, msgs); paint(); } }));
  ctx.status({ source: 'ib-desk', ts: Date.now(), mode: 'LIVE' });
  paint();
}

export function mountSECF(body, ctx) {
  body.classList.add('fill');
  let q = ctx.symbol || 'BTC';
  const tb = h('div', { class: 'tb' });
  const sc = h('div', { class: 'pb' });
  body.append(tb, sc);

  async function searchNow() {
    tb.textContent = '';
    const inp = h('input', { value: q, placeholder: 'Ticker or company name...', style: 'width:220px;text-transform:uppercase' });
    const go = () => { q = inp.value.trim(); if (q) searchNow(); };
    inp.addEventListener('keydown', e => { if (e.key === 'Enter') go(); });
    tb.append(h('span', { class: 'lbl', text: 'SECF SECURITY FINDER:' }), inp, h('button', { class: 'on', text: 'SEARCH <GO>', onclick: go }));

    sc.textContent = '';
    const env = await get('search', { q }, 10000);
    ctx.status(env);
    if (!env.ok || !Array.isArray(env.data) || !env.data.length) {
      sc.append(h('div', { class: 'na', text: `No matching securities for "${q}"` }));
      return;
    }
    sc.append(h('table', { class: 't' },
      h('thead', null, h('tr', null, ['Symbol', 'Description / Name', 'Sector / Asset', 'Exchange', 'Source', 'Load'].map(x => h('th', { text: x })))),
      h('tbody', null, env.data.map(x => h('tr', { class: 'row', onclick: () => ctx.setSymbol(x.symbol) },
        h('td', { class: 'l sym am', text: x.symbol }),
        h('td', { class: 'l', text: x.name || x.symbol }),
        h('td', { class: 'l lb', text: (x.asset || 'asset').toUpperCase() }),
        h('td', { class: 'l mu', text: x.exchange || '-' }),
        h('td', { class: 'l mu', text: x.source || '-' }),
        h('td', null, h('button', { text: 'SELECT', onclick: ev => { ev.stopPropagation(); ctx.run(`${x.symbol} DES`); } }))
      )))
    ));
  }
  searchNow();
}

export function mountFLDS(body, ctx) {
  body.classList.add('fill');
  let filter = '';
  const tb = h('div', { class: 'tb' });
  const sc = h('div', { class: 'pb' });
  body.append(tb, sc);

  async function load() {
    const [qEnv, fEnv] = await Promise.all([
      get('quote', { symbols: ctx.symbol }, 3000),
      get('fundamentals', { symbol: ctx.symbol }, 30000)
    ]);
    ctx.status(qEnv);
    const q = (qEnv.ok && qEnv.data && qEnv.data[0]) || {};
    const p = (fEnv.ok && fEnv.data && fEnv.data.profile) || {};
    const fin = (fEnv.ok && fEnv.data && fEnv.data.edgar && fEnv.data.edgar.financials) || {};
    const lv = arr => (arr && arr[0] ? arr[0].val : null);

    const fields = [
      ['PX_LAST', 'Last Trade Price', fmtPx(q.price)],
      ['PX_BID', 'Current Best Bid Price', fmtPx(q.bid)],
      ['PX_ASK', 'Current Best Ask Price', fmtPx(q.ask)],
      ['CHG_NET_1D', '1-Day Net Price Change', fmtChg(q.chg)],
      ['CHG_PCT_1D', '1-Day Percentage Change', fmtPct(q.chgPct)],
      ['PX_HIGH', 'Intraday Session High', fmtPx(q.high)],
      ['PX_LOW', 'Intraday Session Low', fmtPx(q.low)],
      ['PX_OPEN', 'Session Open Price', fmtPx(q.open)],
      ['PREV_CLOSE_VAL', 'Previous Session Close', fmtPx(q.prevClose)],
      ['PX_VOLUME', '24h / Session Trading Volume', fmtVol(q.vol)],
      ['HIGH_52WEEK', '52-Week High Price', fmtPx(p.high52w)],
      ['LOW_52WEEK', '52-Week Low Price', fmtPx(p.low52w)],
      ['NAME', 'Security Full Name', p.name || ctx.symbol],
      ['EXCH_CODE', 'Primary Exchange Venue', p.exchange || q.source || 'N/A'],
      ['CRNCY', 'Quoted Currency', p.currency || 'USD'],
      ['ID_CIK', 'SEC Central Index Key', p.cik || 'N/A'],
      ['SALES_REV_TURN', 'Annual Revenue (XBRL)', lv(fin.revenue) != null ? '$' + fmtVol(lv(fin.revenue)) : 'N/A'],
      ['NET_INCOME', 'Annual Net Income (XBRL)', lv(fin.netIncome) != null ? '$' + fmtVol(lv(fin.netIncome)) : 'N/A'],
      ['IS_DILUTED_EPS', 'Diluted EPS (XBRL)', lv(fin.eps) != null ? '$' + fmtNum(lv(fin.eps), 2) : 'N/A'],
      ['BS_TOT_ASSET', 'Total Assets (XBRL)', lv(fin.assets) != null ? '$' + fmtVol(lv(fin.assets)) : 'N/A'],
      ['BS_LT_BORROW', 'Long-Term Debt (XBRL)', lv(fin.debt) != null ? '$' + fmtVol(lv(fin.debt)) : 'N/A'],
      ['CF_FREE_CASH_FLOW', 'Free Cash Flow (OCF - CapEx)', lv(fin.ocf) != null ? '$' + fmtVol(lv(fin.ocf) - (lv(fin.capex) || 0)) : 'N/A']
    ];

    function paint() {
      tb.textContent = '';
      const inp = h('input', { value: filter, placeholder: 'Filter mnemonic (e.g. PX_, EPS, VOL)...', style: 'width:220px;text-transform:uppercase' });
      inp.oninput = () => { filter = inp.value.trim().toUpperCase(); paintRows(); };
      tb.append(h('span', { class: 'lbl', text: `FLDS FIELD DICTIONARY [${ctx.symbol}]:` }), inp);
      paintRows();
    }

    function paintRows() {
      sc.textContent = '';
      const list = fields.filter(([m, d]) => !filter || m.includes(filter) || d.toUpperCase().includes(filter));
      sc.append(h('table', { class: 't' },
        h('thead', null, h('tr', null, ['Field Mnemonic', 'Description', `Live Value (${ctx.symbol})`].map(x => h('th', { text: x })))),
        h('tbody', null, list.map(([m, d, val]) => h('tr', { class: 'row' },
          h('td', { class: 'l sym am', text: m }),
          h('td', { class: 'l lb', text: d }),
          h('td', { class: 'am sym', text: String(val) })
        )))
      ));
    }
    paint();
  }
  load();
}

export function mountHELP(body, ctx, { catalog = [] } = {}) {
  body.classList.add('fill');
  const tb = h('div', { class: 'tb' }, h('span', { class: 'lbl', text: 'HELP <F1> BLOOMBERG TERMINAL COMMAND SYSTEM, SECTOR KEYS & FUNCTION DIRECTORY' }));
  const sc = h('div', { class: 'pb', style: 'padding:6px' });
  body.append(tb, sc);

  ctx.status({ source: 'help-desk', ts: Date.now(), mode: 'LOCAL' });

  const guide = h('div', { class: 'kv', style: 'border:1px solid var(--border);background:#060606;margin-bottom:8px;padding:6px' },
    h('div', { class: 'k', text: 'COMMAND SYNTAX' }), h('div', { class: 'v am sym', text: '[SECURITY] [FUNCTION] <GO>   (Example: AAPL FA <Enter>, BTCUSDT GP <Enter>, NVDA DCF <Enter>)' }),
    h('div', { class: 'k', text: 'YELLOW SECTOR KEYS' }), h('div', { class: 'v lb', text: 'F2 GOVT | F3 CORP | F8 EQUITY | F9 CMDTY | F10 INDEX | F11 CURNCY | F12 PORT/BOT' }),
    h('div', { class: 'k', text: 'QUADRANT SWITCHING' }), h('div', { class: 'v', text: 'Click any of the 4 panels to focus it, or drag panel headers to swap quadrants. Drag split bars to resize.' }),
    h('div', { class: 'k', text: 'KEYBOARD SHORTCUTS' }), h('div', { class: 'v am', text: 'Ctrl+K = Focus Command Line | Enter = <GO> | F1 = HELP | Esc = Clear / Close Autocomplete' })
  );

  const tbl = h('table', { class: 't' },
    h('thead', null, h('tr', null, ['Code', 'Category', 'Function Name & Description', 'Launch in Panel'].map(x => h('th', { text: x })))),
    h('tbody', null, catalog.map(fn => h('tr', { class: 'row', onclick: () => ctx.run(fn.code) },
      h('td', { class: 'l sym am', text: fn.code }),
      h('td', { class: 'l lb', text: fn.cat }),
      h('td', { class: 'l', text: fn.desc }),
      h('td', null, h('button', { text: fn.code + ' <GO>', onclick: ev => { ev.stopPropagation(); ctx.run(fn.code); } }))
    )))
  );

  sc.append(guide, tbl);
}

export function mountMSG(body, ctx, { initialTab = 'INBOX' } = {}) {
  body.classList.add('fill');
  let tab = initialTab; // 'INBOX' | 'COMPOSE' | 'SENT' | 'SPDL' | 'ALERTS'
  let activeMsg = null;
  let store = {
    account: { name: 'FADHIL MUHAMMAD SYAFIQ LUBIS', email: 'fadhil.lubis@bloomberg.net', externalEmail: 'fadhilsyafiq90@gmail.com', uuid: '38492018' },
    alertConfig: { targetEmail: 'fadhilsyafiq90@gmail.com', enableHotNews: true, enableFuturesOpen: true, enableFuturesClose: true, enableEmsxOrders: true, smtpUser: 'fadhilsyafiq90@gmail.com', smtpPass: '' },
    alertLog: [],
    inbox: [],
    sent: [],
    directory: []
  };
  let composeState = { to: 'fadhilsyafiq90@gmail.com', cc: 'gs.macro@bloomberg.net', subject: `INSTITUTIONAL DESK & FUTURES ALERT [${ctx.symbol}]`, priority: 'URGENT', body: '', attachmentFn: `${ctx.symbol} GP`, attachmentLabel: `${ctx.symbol}_CHART.BBG` };
  let alertStatusBanner = '';

  const tb = h('div', { class: 'tb' });
  const sc = h('div', { class: 'pb' });
  body.append(tb, sc);

  function openGmailWeb(to, sub, txt) {
    const url = `https://mail.google.com/mail/?view=cm&fs=1&to=${encodeURIComponent(to || 'fadhilsyafiq90@gmail.com')}&su=${encodeURIComponent(sub || '')}&body=${encodeURIComponent(txt || '')}`;
    window.open(url, '_blank');
  }

  async function sync() {
    const r = await getRaw('/api/terminal/bmail');
    if (r.ok && r.data && r.data.data) store = r.data.data;
    ctx.status({ source: 'bmail-gateway', ts: Date.now(), mode: 'LIVE' });
    render();
  }

  function render() {
    tb.textContent = '';
    sc.textContent = '';
    const unreadCnt = (store.inbox || []).filter(m => m.unread).length;
    const cfg = store.alertConfig || { targetEmail: 'fadhilsyafiq90@gmail.com', enableHotNews: true, enableFuturesOpen: true, enableFuturesClose: true };

    tb.append(
      h('span', { class: 'lbl', text: `MSG // ${store.account.email}:` }),
      h('button', { class: tab === 'INBOX' ? 'on' : '', text: `1) INBOX (${unreadCnt} NEW)`, onclick: () => { tab = 'INBOX'; activeMsg = null; render(); } }),
      h('button', { class: tab === 'COMPOSE' ? 'on' : '', style: tab === 'COMPOSE' ? '' : 'color:var(--up);border-color:var(--up)', text: '2) COMPOSE (MSG1)', onclick: () => { tab = 'COMPOSE'; activeMsg = null; render(); } }),
      h('button', { class: tab === 'SENT' ? 'on' : '', text: `3) SENT (${(store.sent || []).length})`, onclick: () => { tab = 'SENT'; activeMsg = null; render(); } }),
      h('button', { class: tab === 'SPDL' ? 'on' : '', text: '4) DIRECTORY (SPDL)', onclick: () => { tab = 'SPDL'; activeMsg = null; render(); } }),
      h('button', { class: tab === 'ALERTS' ? 'on' : '', style: tab === 'ALERTS' ? '' : 'color:#ff9f0a;border-color:#ff9f0a', text: `5) AUTO-EMAIL (${cfg.targetEmail || 'fadhilsyafiq90@gmail.com'})`, onclick: () => { tab = 'ALERTS'; activeMsg = null; render(); } }),
      h('button', { text: 'IB LIVE CHAT <GO>', onclick: () => ctx.run('IB') })
    );

    if (activeMsg) {
      const m = activeMsg;
      sc.append(
        h('div', { style: 'border:1px solid var(--amber);background:#050505;margin:6px;padding:10px' },
          h('div', { style: 'display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border);padding-bottom:6px;margin-bottom:8px' },
            h('span', { style: 'background:var(--amber);color:#000;font-weight:bold;padding:1px 6px', text: `BLOOMBERG MAIL MESSAGE // ${m.id}` }),
            h('div', { style: 'display:flex;gap:6px' },
              h('button', { class: 'on', text: 'REPLY <GO>', onclick: () => {
                composeState.to = m.from;
                composeState.subject = m.subject.startsWith('RE:') ? m.subject : 'RE: ' + m.subject;
                composeState.body = `\n\n--- On ${fmtTime(m.ts)}, ${m.fromName || m.from} wrote: ---\n${m.body}`;
                activeMsg = null; tab = 'COMPOSE'; render();
              } }),
              h('button', { style: 'color:#4da3ff;border-color:#4da3ff', text: 'FORWARD TO fadhilsyafiq90@gmail.com (GMAIL) ↗', onclick: () => openGmailWeb('fadhilsyafiq90@gmail.com', m.subject, m.body) }),
              m.attachmentFn ? h('button', { style: 'color:var(--up);border-color:var(--up)', text: `OPEN ATTACHMENT [${m.attachmentFn}] <GO>`, onclick: () => ctx.run(m.attachmentFn) }) : null,
              h('button', { style: 'background:var(--dn);color:#fff', text: '× BACK TO LIST', onclick: () => { activeMsg = null; render(); } })
            )
          ),
          h('div', { class: 'kv', style: 'background:#0a0a0a;border:1px solid #1e1e1e;margin-bottom:8px;padding:6px' },
            h('div', { class: 'k', text: 'FROM' }), h('div', { class: 'v am sym', text: `${m.fromName || ''} <${m.from}>` }),
            h('div', { class: 'k', text: 'TO' }), h('div', { class: 'v lb', text: m.to }),
            h('div', { class: 'k', text: 'DATE / TIME' }), h('div', { class: 'v', text: fmtTime(m.ts, true) }),
            h('div', { class: 'k', text: 'SUBJECT' }), h('div', { class: 'v sym', style: 'color:#fff', text: (m.priority === 'URGENT' ? '[! URGENT] ' : '') + m.subject }),
            ...(m.attachmentLabel ? [h('div', { class: 'k', text: 'BBG ATTACHMENT' }), h('div', { class: 'v up sym', style: 'cursor:pointer', onclick: () => m.attachmentFn && ctx.run(m.attachmentFn), text: `📎 ${m.attachmentLabel} (Click to launch ${m.attachmentFn} <GO>)` })] : [])
          ),
          h('div', { style: 'white-space:pre-wrap;color:var(--amber);line-height:1.5;padding:8px;background:#030303;border-left:3px solid var(--amber)', text: m.body })
        )
      );
      return;
    }

    if (tab === 'INBOX' || tab === 'SENT') {
      const list = tab === 'INBOX' ? (store.inbox || []) : (store.sent || []);
      sc.append(
        h('div', { class: 'tb', style: 'background:#070707;justify-content:space-between' },
          h('span', { class: 'lbl', text: tab === 'INBOX' ? `BLOOMBERG MAIL INBOX — ${store.account.name} <${store.account.email}> (AUTO-RELAY: ${cfg.targetEmail})` : `SENT MESSAGES ARCHIVE — ${store.account.email}` }),
          h('span', { class: 'up sym', text: `● AUTO-ALERT RELAY: ${cfg.targetEmail || 'fadhilsyafiq90@gmail.com'}` })
        ),
        list.length ? h('table', { class: 't' },
          h('thead', null, h('tr', null, ['St', 'Pri', 'Time (UTC)', tab === 'INBOX' ? 'From (@bloomberg.net)' : 'To Recipient', 'Subject & Attachment', 'Attachment', 'Open'].map(x => h('th', { text: x })))),
          h('tbody', null, list.map(m => h('tr', {
            class: 'row',
            style: m.unread ? 'background:#191200;font-weight:bold' : '',
            onclick: async () => {
              activeMsg = m;
              if (m.unread) {
                m.unread = false;
                await fetch('/api/terminal/bmail/read', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id: m.id }) });
              }
              render();
            }
          },
            h('td', { class: 'l ' + (m.unread ? 'up sym' : 'mu'), text: m.unread ? '● NEW' : 'READ' }),
            h('td', { class: 'l ' + (m.priority === 'URGENT' ? 'dn sym' : 'mu'), text: m.priority === 'URGENT' ? '! URG' : 'NORM' }),
            h('td', { class: 'l lb', text: fmtTime(m.ts) }),
            h('td', { class: 'l am sym', text: tab === 'INBOX' ? (m.fromName || m.from) : m.to }),
            h('td', { class: 'l', style: m.unread ? 'color:#fff' : 'color:var(--amber)', text: m.subject }),
            h('td', { class: 'l up', text: m.attachmentLabel ? '📎 ' + m.attachmentLabel : '-' }),
            h('td', null, h('button', { text: 'READ', onclick: ev => { ev.stopPropagation(); activeMsg = m; render(); } }))
          )))
        ) : h('div', { class: 'empty', text: 'No messages in this folder.' })
      );
    } else if (tab === 'ALERTS') {
      const iEmail = h('input', { value: cfg.targetEmail || 'fadhilsyafiq90@gmail.com', style: 'width:240px;color:var(--up);font-weight:bold' });
      const iPass = h('input', { type: 'password', value: cfg.smtpPass || '', placeholder: 'Optional 16-char Gmail App Password for direct background SMTP...', style: 'width:320px' });

      const saveCfg = async (patch = {}) => {
        const next = Object.assign({}, cfg, { targetEmail: iEmail.value.trim() || 'fadhilsyafiq90@gmail.com', smtpPass: iPass.value.trim() }, patch);
        const r = await fetch('/api/terminal/bmail/alert-config', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(next) });
        const j = await r.json();
        if (j.ok && j.data) store = j.data;
        alertStatusBanner = `✓ SAVED AUTO-EMAIL RULES FOR ${(store.alertConfig && store.alertConfig.targetEmail) || 'fadhilsyafiq90@gmail.com'}`;
        render();
      };

      const triggerTest = async (type) => {
        alertStatusBanner = `DISPATCHING ${type} EMAIL TO ${cfg.targetEmail || 'fadhilsyafiq90@gmail.com'}...`;
        render();
        const r = await fetch('/api/terminal/bmail/test-alert', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ type }) });
        const j = await r.json();
        if (j.ok && j.data) store = j.data;
        alertStatusBanner = `✓ ${type} DISPATCHED TO ${(j.entry && j.entry.to) || 'fadhilsyafiq90@gmail.com'} [${(j.entry && j.entry.status) || 'OK'}]`;
        render();
      };

      sc.append(
        h('div', { style: 'padding:8px;border:1px solid var(--amber);background:#050505;margin:6px' },
          h('div', { class: 'tb', style: 'background:#160f00;justify-content:space-between;margin-bottom:6px' },
            h('span', { class: 'lbl', text: 'BLOOMBERG AUTOMATIC EXTERNAL EMAIL DISPATCHER (HOT NEWS & FUTURES OPEN/CLOSE)' }),
            h('span', { class: 'up sym', text: `TARGET: ${cfg.targetEmail || 'fadhilsyafiq90@gmail.com'}` })
          ),
          alertStatusBanner ? h('div', { style: 'background:#07210f;border:1px solid var(--up);color:var(--up);padding:5px 8px;margin-bottom:6px;font-weight:bold', text: alertStatusBanner }) : null,
          h('div', { class: 'kv', style: 'margin-bottom:8px;padding:6px;background:#090909;border:1px solid #222' },
            h('div', { class: 'k', text: 'TARGET RECIPIENT EMAIL' }),
            h('div', { class: 'v' }, iEmail, h('button', { class: 'on', style: 'margin-left:8px', text: 'SAVE TARGET EMAIL', onclick: () => saveCfg() })),
            h('div', { class: 'k', text: 'AUTO-TRIGGER RULES' }),
            h('div', { class: 'v', style: 'display:flex;gap:6px;flex-wrap:wrap' },
              h('button', { class: cfg.enableHotNews !== false ? 'on' : '', text: `${cfg.enableHotNews !== false ? '✓' : '✗'} 1. BREAKING HOT NEWS WIRE`, onclick: () => saveCfg({ enableHotNews: cfg.enableHotNews === false }) }),
              h('button', { class: cfg.enableFuturesOpen !== false ? 'on' : '', text: `${cfg.enableFuturesOpen !== false ? '✓' : '✗'} 2. FUTURES POSITION OPEN (20x)`, onclick: () => saveCfg({ enableFuturesOpen: cfg.enableFuturesOpen === false }) }),
              h('button', { class: cfg.enableFuturesClose !== false ? 'on' : '', text: `${cfg.enableFuturesClose !== false ? '✓' : '✗'} 3. FUTURES POSITION CLOSE (TP/SL)`, onclick: () => saveCfg({ enableFuturesClose: cfg.enableFuturesClose === false }) }),
              h('button', { class: cfg.enableEmsxOrders !== false ? 'on' : '', text: `${cfg.enableEmsxOrders !== false ? '✓' : '✗'} 4. EMSX PORTFOLIO ORDERS`, onclick: () => saveCfg({ enableEmsxOrders: cfg.enableEmsxOrders === false }) })
            ),
            h('div', { class: 'k', text: 'GMAIL TLS SMTP APP PASS' }),
            h('div', { class: 'v' }, iPass, h('button', { style: 'margin-left:6px', text: 'SAVE SMTP KEY', onclick: () => saveCfg() })),
            h('div', { class: 'k', text: 'INSTANT LIVE TEST DISPATCH' }),
            h('div', { class: 'v', style: 'display:flex;gap:6px;flex-wrap:wrap' },
              h('button', { style: 'background:#ffb000;color:#000;font-weight:bold', text: '⚡ TEST HOT NEWS EMAIL', onclick: () => triggerTest('HOT_NEWS') }),
              h('button', { style: 'background:var(--up);color:#000;font-weight:bold', text: '⚡ TEST FUTURES OPEN EMAIL', onclick: () => triggerTest('FUTURES_OPEN') }),
              h('button', { style: 'background:#4da3ff;color:#000;font-weight:bold', text: '⚡ TEST FUTURES CLOSE EMAIL', onclick: () => triggerTest('FUTURES_CLOSE') })
            )
          ),
          h('div', { class: 'tb', style: 'background:#070707' }, h('span', { class: 'lbl', text: `LIVE AUTO-EMAIL DISPATCH LOG (-> ${cfg.targetEmail || 'fadhilsyafiq90@gmail.com'})` })),
          h('table', { class: 't' },
            h('thead', null, h('tr', null, ['Time', 'Trigger Event', 'Recipient', 'Subject', 'Status', 'Direct Gmail'].map(x => h('th', { text: x })))),
            h('tbody', null, (store.alertLog || []).map(a => h('tr', { class: 'row' },
              h('td', { class: 'l lb', text: fmtTime(a.ts) }),
              h('td', { class: 'l sym ' + (a.eventType === 'FUTURES_OPEN' ? 'up' : a.eventType === 'FUTURES_CLOSE' ? 'lb' : 'am'), text: a.eventType }),
              h('td', { class: 'l up sym', text: a.to }),
              h('td', { class: 'l', style: 'color:#fff', text: a.subject }),
              h('td', { class: 'l mu', text: a.status }),
              h('td', null, h('button', { style: 'color:var(--up);border-color:var(--up)', text: 'SEND IN GMAIL ↗', onclick: () => openGmailWeb(a.to, a.subject, a.body) }))
            )))
          )
        )
      );
    } else if (tab === 'COMPOSE') {
      const iTo = h('input', { value: composeState.to, placeholder: 'fadhilsyafiq90@gmail.com or desk@bloomberg.net...', style: 'width:260px' });
      const iCc = h('input', { value: composeState.cc, placeholder: 'Optional CC...', style: 'width:200px' });
      const iSub = h('input', { value: composeState.subject, placeholder: 'Subject line...', style: 'width:340px;font-weight:bold' });
      const selPri = h('select', null, h('option', { value: 'NORMAL', selected: composeState.priority === 'NORMAL' ? 'selected' : null, text: 'NORMAL' }), h('option', { value: 'URGENT', selected: composeState.priority === 'URGENT' ? 'selected' : null, text: '! URGENT' }));
      const txtBody = h('textarea', {
        rows: '7',
        placeholder: 'Type institutional Bloomberg Mail message here...',
        style: 'width:100%;background:#000;color:var(--amber);border:1px solid var(--border);padding:6px;font:inherit;resize:vertical'
      }, composeState.body);

      const injectAttachment = async type => {
        composeState.to = iTo.value; composeState.cc = iCc.value; composeState.subject = iSub.value; composeState.body = txtBody.value;
        if (type === 'QUOTE') {
          const qEnv = await get('quote', { symbols: ctx.symbol }, 2000);
          const q = (qEnv.ok && qEnv.data && qEnv.data[0]) || {};
          composeState.attachmentFn = `${ctx.symbol} GP`;
          composeState.attachmentLabel = `${ctx.symbol}_QUOTE_GP.BBG`;
          composeState.body += `\n\n[BBG QUOTE SNAPSHOT: ${ctx.symbol}]\nLast Price: ${fmtPx(q.price)} | 1D Chg: ${fmtPct(q.chgPct)} | High: ${fmtPx(q.high)} | Low: ${fmtPx(q.low)} | Vol: ${fmtVol(q.vol)}`;
        } else if (type === 'PORT') {
          const pRes = await getRaw('/api/portfolio');
          const p = (pRes.ok && pRes.data) || {};
          composeState.attachmentFn = 'SPCX PORT';
          composeState.attachmentLabel = 'PORTFOLIO_200JT_NAV.BBG';
          composeState.body += `\n\n[BBG PORTFOLIO SNAPSHOT — FADHIL MUHAMMAD SYAFIQ LUBIS]\nBase Capital: Rp 200.000.000 | Current NAV: Rp ${Math.round(p.totalNetWorth || 200000000).toLocaleString('id-ID')}\nHoldings: ${(p.holdings || []).map(x => `${x.symbol} (${x.qty} @ ${x.currentPrice})`).join(', ')}`;
        } else if (type === 'YCRV') {
          composeState.attachmentFn = '^TNX YCRV';
          composeState.attachmentLabel = 'UST_YIELD_CURVE.BBG';
          composeState.body += `\n\n[BBG SOVEREIGN CURVE ATTACHMENT: ^TNX YCRV <GO>]`;
        }
        render();
      };

      const sendNow = async () => {
        const payload = {
          to: iTo.value.trim() || 'fadhilsyafiq90@gmail.com',
          cc: iCc.value.trim(),
          subject: iSub.value.trim() || 'BLOOMBERG DESK MESSAGE',
          priority: selPri.value,
          body: txtBody.value,
          attachmentFn: composeState.attachmentFn,
          attachmentLabel: composeState.attachmentLabel
        };
        const r = await fetch('/api/terminal/bmail/send', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const j = await r.json();
        if (j.ok && j.data) store = j.data;
        composeState.body = '';
        tab = 'INBOX';
        render();
      };

      sc.append(
        h('div', { style: 'padding:8px;border:1px solid var(--border);background:#050505;margin:6px' },
          h('div', { class: 'tb', style: 'background:#120b00;margin-bottom:6px' },
            h('span', { class: 'lbl', text: `MSG1 COMPOSE BLOOMBERG MAIL // FROM: ${store.account.name} <${store.account.email}>` })
          ),
          h('div', { class: 'tb', style: 'background:#080808;margin-bottom:6px' },
            h('span', { class: 'lbl', text: 'QUICK RECIPIENT:' }),
            h('button', { style: 'color:var(--up);border-color:var(--up);font-weight:bold', text: 'FADHILSYAFIQ90@GMAIL.COM', onclick: () => { composeState.to = 'fadhilsyafiq90@gmail.com'; composeState.body = txtBody.value; render(); } }),
            ...(store.directory || []).map(d => h('button', {
              text: d.email.split('@')[0].toUpperCase(),
              title: `${d.name} <${d.email}>`,
              onclick: () => { composeState.to = d.email; composeState.body = txtBody.value; render(); }
            }))
          ),
          h('div', { class: 'kv', style: 'margin-bottom:6px' },
            h('div', { class: 'k', text: 'TO RECIPIENT' }), h('div', { class: 'v' }, iTo, h('span', { class: 'mu', style: 'margin-left:8px', text: 'CC: ' }), iCc),
            h('div', { class: 'k', text: 'SUBJECT LINE' }), h('div', { class: 'v' }, iSub, h('span', { class: 'mu', style: 'margin-left:8px', text: 'PRIORITY: ' }), selPri),
            h('div', { class: 'k', text: 'ATTACH TERMINAL DATA' }),
            h('div', { class: 'v', style: 'display:flex;gap:4px;flex-wrap:wrap' },
              h('button', { text: `+ATTACH QUOTE (${ctx.symbol})`, onclick: () => injectAttachment('QUOTE') }),
              h('button', { text: '+ATTACH PORTFOLIO 200JT', onclick: () => injectAttachment('PORT') }),
              h('button', { text: '+ATTACH YCRV CURVE', onclick: () => injectAttachment('YCRV') }),
              h('span', { class: 'up sym', style: 'margin-left:6px', text: `📎 ${composeState.attachmentLabel}` })
            )
          ),
          txtBody,
          h('div', { style: 'display:flex;gap:8px;margin-top:8px;flex-wrap:wrap' },
            h('button', { class: 'on', style: 'background:var(--up);color:#000;font-weight:bold;padding:4px 14px', text: 'SEND VIA B-MAIL + SMTP GATEWAY <GO>', onclick: sendNow }),
            h('button', {
              style: 'background:#4da3ff;color:#000;font-weight:bold;padding:4px 12px',
              text: 'SEND VIA GMAIL WEB (fadhilsyafiq90@gmail.com) ↗',
              onclick: () => openGmailWeb(iTo.value.trim() || 'fadhilsyafiq90@gmail.com', iSub.value.trim(), txtBody.value)
            }),
            h('button', {
              style: 'color:var(--label);border-color:var(--label);padding:4px 10px',
              text: 'OPEN IN MAILTO CLIENT ↗',
              onclick: () => {
                window.open(`mailto:${encodeURIComponent(iTo.value.trim())}?subject=${encodeURIComponent(iSub.value.trim())}&body=${encodeURIComponent(txtBody.value)}`, '_blank');
              }
            })
          )
        )
      );
    } else if (tab === 'SPDL') {
      sc.append(
        h('div', { class: 'tb', style: 'background:#070707' }, h('span', { class: 'lbl', text: 'SPDL / PEOP BLOOMBERG INSTITUTIONAL SPEED DIAL & COUNTERPARTY DIRECTORY' })),
        h('table', { class: 't' },
          h('thead', null, h('tr', null, ['Counterparty / Desk', 'Email Address', 'Institution', 'Specialty', 'Hub', 'Action'].map(x => h('th', { text: x })))),
          h('tbody', null, (store.directory || []).map(d => h('tr', { class: 'row' },
            h('td', { class: 'l sym am', text: d.name }),
            h('td', { class: 'l lb', text: d.email }),
            h('td', { class: 'l', text: d.firm }),
            h('td', { class: 'l mu', text: d.desk }),
            h('td', { class: 'l mu', text: d.location }),
            h('td', null,
              h('button', { class: 'on', text: 'COMPOSE MSG', onclick: () => { composeState.to = d.email; tab = 'COMPOSE'; render(); } })
            )
          )))
        )
      );
    }
  }

  sync();
}


