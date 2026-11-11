import { h, fmtPx, fmtPct, fmtChg, fmtVol, fmtNum, fmtTime, dirCls, LS } from '../util.js';
import { get, getRaw, tickOk } from '../api.js';

export function mountBOT(body, ctx) {
  body.classList.add('fill');
  const tb = h('div', { class: 'tb' }, h('span', { class: 'lbl', text: 'BOT PYROFUEL 28-PILLAR AI CRYPTO FUTURES ENGINE (READ-ONLY LIVE TELEMETRY)' }));
  const sc = h('div', { class: 'pb' });
  body.append(tb, sc);

  async function load() {
    const [wRes, pRes, cRes] = await Promise.all([
      getRaw('/api/futures/wallet'),
      getRaw('/api/futures/positions'),
      getRaw('/api/committee/auto-status')
    ]);
    ctx.status({ source: 'pyrofuel-bot', ts: Date.now(), mode: (wRes.ok || pRes.ok || cRes.ok) ? 'LIVE' : 'N/A' });
    sc.textContent = '';

    const w = (wRes.ok && wRes.data) || {};
    const posList = (pRes.ok && pRes.data && (pRes.data.positions || pRes.data)) || [];
    const auto = (cRes.ok && cRes.data) || {};

    const kv = h('div', { class: 'kv', style: 'border-bottom:1px solid var(--border);background:#060606;padding:6px 8px' },
      h('div', { class: 'k', text: 'ENGINE STATUS' }), h('div', { class: 'v ' + (auto.autonomous_active !== false ? 'up sym' : 'dn sym'), text: auto.autonomous_active !== false ? 'ACTIVE (20x ISOLATED)' : 'PAUSED' }),
      h('div', { class: 'k', text: 'TOTAL SCANS / APPROVED' }), h('div', { class: 'v am', text: `${auto.total_scans_done ?? 0} scans / ${auto.signals_approved_count ?? 0} signals` }),
      h('div', { class: 'k', text: 'LAST SCAN TIME' }), h('div', { class: 'v lb', text: auto.last_scan_time || 'Standby' }),
      h('div', { class: 'k', text: 'FUTURES WALLET BALANCE' }), h('div', { class: 'v am sym', text: w.total_balance_usdt != null ? `$${fmtNum(+w.total_balance_usdt, 2)} USDT` : (w.balance_idr != null ? `Rp ${fmtVol(+w.balance_idr)}` : 'Connected via Binance API') }),
      h('div', { class: 'k', text: 'ACTIVE POSITIONS' }), h('div', { class: 'v am sym', text: String(Array.isArray(posList) ? posList.length : 0) })
    );
    sc.append(kv);

    if (Array.isArray(posList) && posList.length) {
      sc.append(
        h('div', { class: 'tb', style: 'background:#070707' }, h('span', { class: 'lbl', text: 'ACTIVE BINANCE FUTURES POSITIONS' })),
        h('table', { class: 't' },
          h('thead', null, h('tr', null, ['Symbol', 'Side', 'Lev', 'Entry Px', 'Mark Px', 'SL', 'TP', 'PnL / ROE %'].map(x => h('th', { text: x })))),
          h('tbody', null, posList.map(p => {
            const sym = (p.symbol || p.pair || '').replace('-', '');
            const side = p.side || p.direction || (p.positionAmt > 0 ? 'LONG' : 'SHORT');
            const pnl = +(p.unrealizedProfit ?? p.pnl_usd ?? p.roe_pct ?? 0);
            return h('tr', { class: 'row', onclick: () => sym && ctx.setSymbol(sym.endsWith('USDT') ? sym + '.P' : sym) },
              h('td', { class: 'l sym am', text: sym }),
              h('td', { class: (side === 'LONG' ? 'up' : 'dn') + ' sym', text: side }),
              h('td', { class: 'lb', text: (p.leverage || 20) + 'x' }),
              h('td', { text: fmtPx(+(p.entryPrice || p.entry_price || 0)) }),
              h('td', { class: 'am', text: fmtPx(+(p.markPrice || p.current_price || 0)) }),
              h('td', { class: 'dn', text: fmtPx(+(p.stop_loss || p.sl_price || 0)) }),
              h('td', { class: 'up', text: fmtPx(+(p.take_profit || p.tp_price || 0)) }),
              h('td', { class: dirCls(pnl) + ' sym', text: (pnl >= 0 ? '+' : '') + fmtNum(pnl, 2) })
            );
          }))
        )
      );
    } else {
      sc.append(h('div', { class: 'empty', text: 'No open positions currently registered in active_positions.json.' }));
    }

    const sigs = Array.isArray(auto.recent_signals) ? auto.recent_signals : [];
    if (sigs.length) {
      sc.append(
        h('div', { class: 'tb', style: 'background:#070707;margin-top:6px' }, h('span', { class: 'lbl', text: 'RECENT 5-LAYER PIPELINE SIGNALS' })),
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
  }
  load();
  const iv = setInterval(load, 8000);
  ctx.cleanup(() => clearInterval(iv));
}

export function mountPORT(body, ctx) {
  body.classList.add('fill');
  const key = 'bbg_port_holdings_v1';
  let holdings = LS.get(key, [
    { symbol: 'BTCUSDT', qty: 0.15, avgCost: 62500 },
    { symbol: 'ETHUSDT', qty: 2.0, avgCost: 2450 },
    { symbol: 'SOLUSDT', qty: 25, avgCost: 145 },
    { symbol: 'AAPL', qty: 40, avgCost: 210 },
    { symbol: 'NVDA', qty: 50, avgCost: 118 }
  ]);

  const tb = h('div', { class: 'tb' });
  const sc = h('div', { class: 'pb' });
  body.append(tb, sc);

  function save() { LS.set(key, holdings); }

  async function load() {
    tb.textContent = '';
    const iSym = h('input', { placeholder: 'SYMBOL', style: 'width:85px;text-transform:uppercase' });
    const iQty = h('input', { placeholder: 'QTY', style: 'width:65px' });
    const iCost = h('input', { placeholder: 'AVG COST', style: 'width:80px' });
    tb.append(
      h('span', { class: 'lbl', text: 'PORT / PRTU HOLDINGS:' }),
      iSym, iQty, iCost,
      h('button', { class: 'on', text: '+ADD LOT', onclick: () => {
        const s = iSym.value.trim().toUpperCase();
        const q = parseFloat(iQty.value), c = parseFloat(iCost.value);
        if (s && isFinite(q) && isFinite(c)) { holdings.push({ symbol: s, qty: q, avgCost: c }); save(); load(); }
      } })
    );

    sc.textContent = '';
    const syms = [...new Set(holdings.map(x => x.symbol))];
    if (!syms.length) {
      sc.append(h('div', { class: 'empty', text: 'Portfolio empty. Add a position above.' }));
      return;
    }
    const env = await get('quote', { symbols: syms.join(',') }, 3000);
    ctx.status(env);
    const pxMap = {};
    if (env.ok && Array.isArray(env.data)) env.data.forEach(t => { if (tickOk(t)) pxMap[t.symbol] = t; });

    let totCost = 0, totVal = 0, dayPnl = 0;
    const rows = holdings.map((hItem, idx) => {
      const t = pxMap[hItem.symbol] || {};
      const px = tickOk(t) ? t.price : null;
      const cost = hItem.qty * hItem.avgCost;
      const val = px != null ? hItem.qty * px : cost;
      const pnl = px != null ? val - cost : 0;
      const pnlPct = cost > 0 ? (pnl / cost) * 100 : 0;
      const dPnl = (px != null && t.chg != null) ? hItem.qty * t.chg : 0;
      totCost += cost; totVal += val; dayPnl += dPnl;
      return { ...hItem, idx, px, cost, val, pnl, pnlPct, dPnl };
    });

    const totPnl = totVal - totCost;
    const totPnlPct = totCost > 0 ? (totPnl / totCost) * 100 : 0;

    sc.append(
      h('div', { class: 'tb', style: 'background:#070707' },
        h('span', { class: 'am sym', text: `NAV: $${fmtNum(totVal, 2)}` }),
        h('span', { class: 'lbl', text: `COST: $${fmtNum(totCost, 2)}` }),
        h('span', { class: dirCls(totPnl) + ' sym', text: `TOTAL P&L: ${totPnl >= 0 ? '+' : ''}$${fmtNum(totPnl, 2)} (${fmtPct(totPnlPct)})` }),
        h('span', { class: dirCls(dayPnl), text: `1D P&L: ${dayPnl >= 0 ? '+' : ''}$${fmtNum(dayPnl, 2)}` })
      ),
      h('table', { class: 't' },
        h('thead', null, h('tr', null, ['Security', 'Qty', 'Avg Cost', 'Last Px', 'Mkt Value', 'Weight %', '1D P&L', 'Total P&L ($)', 'P&L %', ''].map(x => h('th', { text: x })))),
        h('tbody', null, rows.map(r => h('tr', { class: 'row', onclick: () => ctx.setSymbol(r.symbol) },
          h('td', { class: 'l sym am', text: r.symbol }),
          h('td', { text: fmtNum(r.qty, 4) }),
          h('td', { text: '$' + fmtPx(r.avgCost) }),
          h('td', { class: 'am', text: r.px != null ? '$' + fmtPx(r.px) : 'N/A' }),
          h('td', { class: 'am sym', text: '$' + fmtNum(r.val, 2) }),
          h('td', { class: 'lb', text: totVal > 0 ? ((r.val / totVal) * 100).toFixed(1) + '%' : '0%' }),
          h('td', { class: dirCls(r.dPnl), text: (r.dPnl >= 0 ? '+' : '') + '$' + fmtNum(r.dPnl, 2) }),
          h('td', { class: dirCls(r.pnl) + ' sym', text: (r.pnl >= 0 ? '+' : '') + '$' + fmtNum(r.pnl, 2) }),
          h('td', { class: dirCls(r.pnlPct), text: fmtPct(r.pnlPct) }),
          h('td', null, h('button', { text: 'X', onclick: ev => { ev.stopPropagation(); holdings.splice(r.idx, 1); save(); load(); } }))
        )))
      )
    );
  }
  load();
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

    sc.append(
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
      const qEnv = await get('quote', { symbols: ctx.symbol }, 3000);
      const q = (qEnv.ok && qEnv.data && qEnv.data[0]) || {};
      const prompt = `[Bloomberg Terminal Context: ${ctx.symbol} Last=${q.price ?? 'N/A'} Chg%=${q.chgPct ?? 'N/A'}%] Trader query: ${txt}`;
      const r = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: prompt })
      });
      const j = await r.json();
      const reply = j.reply || j.response || j.message || `Quant Snapshot ${ctx.symbol}: Last ${fmtPx(q.price)} (${fmtPct(q.chgPct)}).`;
      msgs.push({ ts: Date.now(), from: 'ASKB-AI', text: reply });
    } catch {
      msgs.push({ ts: Date.now(), from: 'ASKB-AI', text: `Note saved to IB Desk Log for ${ctx.symbol}.` });
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

