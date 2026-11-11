import { h, fmtPx, fmtPct, fmtChg, fmtVol, fmtDate, fmtTime, dirCls } from '../util.js';
import { get } from '../api.js';

function calcSMA(candles, period) {
  const out = [];
  let sum = 0;
  for (let i = 0; i < candles.length; i++) {
    sum += candles[i].c;
    if (i >= period) sum -= candles[i - period].c;
    if (i >= period - 1) out.push({ time: Math.floor(candles[i].t / 1000), value: sum / period });
  }
  return out;
}

function calcEMA(candles, period) {
  const out = [];
  if (!candles.length) return out;
  const k = 2 / (period + 1);
  let ema = candles[0].c;
  for (let i = 0; i < candles.length; i++) {
    ema = i === 0 ? candles[i].c : candles[i].c * k + ema * (1 - k);
    if (i >= period - 1) out.push({ time: Math.floor(candles[i].t / 1000), value: ema });
  }
  return out;
}

function calcBB(candles, period = 20, mult = 2) {
  const up = [], lo = [];
  for (let i = period - 1; i < candles.length; i++) {
    let sum = 0;
    for (let j = i - period + 1; j <= i; j++) sum += candles[j].c;
    const mean = sum / period;
    let sq = 0;
    for (let j = i - period + 1; j <= i; j++) sq += (candles[j].c - mean) ** 2;
    const sd = Math.sqrt(sq / period);
    const t = Math.floor(candles[i].t / 1000);
    up.push({ time: t, value: mean + mult * sd });
    lo.push({ time: t, value: mean - mult * sd });
  }
  return { up, lo };
}

function calcVWAP(candles) {
  const out = [];
  let cumPV = 0, cumV = 0;
  for (const c of candles) {
    const typ = (c.h + c.l + c.c) / 3;
    const v = c.v || 1;
    cumPV += typ * v;
    cumV += v;
    out.push({ time: Math.floor(c.t / 1000), value: cumPV / cumV });
  }
  return out;
}

function calcRSI(candles, period = 14) {
  const out = [];
  if (candles.length <= period) return out;
  let gains = 0, losses = 0;
  for (let i = 1; i <= period; i++) {
    const d = candles[i].c - candles[i - 1].c;
    if (d >= 0) gains += d; else losses -= d;
  }
  let avgG = gains / period, avgL = losses / period;
  for (let i = period; i < candles.length; i++) {
    if (i > period) {
      const d = candles[i].c - candles[i - 1].c;
      avgG = (avgG * (period - 1) + (d > 0 ? d : 0)) / period;
      avgL = (avgL * (period - 1) + (d < 0 ? -d : 0)) / period;
    }
    const rs = avgL === 0 ? 100 : avgG / avgL;
    out.push({ time: Math.floor(candles[i].t / 1000), value: 100 - 100 / (1 + rs) });
  }
  return out;
}

function dedupeByTime(arr) {
  const m = new Map();
  for (const x of arr) m.set(x.time, x);
  return [...m.values()].sort((a, b) => a.time - b.time);
}

export function mountGP(body, ctx, { intraday = false } = {}) {
  body.classList.add('fill');
  let iv = intraday ? '5m' : '1h';
  let style = 'candle';
  let showSMA = true, showEMA = true, showBB = false, showVWAP = intraday, showRSI = !intraday;
  let unsub = null;

  const intervals = intraday ? ['1m', '5m', '15m', '1h'] : ['1m', '5m', '15m', '1h', '4h', '1d', '1w'];
  const tb = h('div', { class: 'tb' });
  const wrap = h('div', { class: 'chart' });
  const leg = h('div', { class: 'legend am' });
  const rsiStrip = h('div', { style: 'height:54px;border-top:1px solid var(--border);position:relative;flex:none;background:#050505;display:' + (showRSI ? 'block' : 'none') });
  wrap.append(leg);
  body.append(tb, wrap, rsiStrip);

  let chart = null, mainSeries = null, volSeries = null, smaS = null, emaS = null, bbUpS = null, bbLoS = null, vwapS = null;
  let lastCandles = [];

  function buildToolbar() {
    tb.textContent = '';
    tb.append(h('span', { class: 'lbl', text: intraday ? 'GIP INTRADAY:' : 'GPTF:' }));
    for (const i of intervals) {
      tb.append(h('button', { class: i === iv ? 'on' : '', text: i.toUpperCase(), onclick: () => { iv = i; buildToolbar(); load(); } }));
    }
    tb.append(h('span', { class: 'lbl', text: 'TYPE:' }));
    for (const t of ['candle', 'line', 'area']) {
      tb.append(h('button', { class: t === style ? 'on' : '', text: t.toUpperCase(), onclick: () => { style = t; buildToolbar(); renderChart(lastCandles); } }));
    }
    tb.append(h('span', { class: 'lbl', text: 'STUDIES:' }));
    const stBtn = (lbl, on, toggle) => h('button', { class: on ? 'on' : '', text: lbl, onclick: () => { toggle(); buildToolbar(); renderChart(lastCandles); } });
    tb.append(
      stBtn('SMA20', showSMA, () => { showSMA = !showSMA; }),
      stBtn('EMA50', showEMA, () => { showEMA = !showEMA; }),
      stBtn('BB(20,2)', showBB, () => { showBB = !showBB; }),
      stBtn('VWAP', showVWAP, () => { showVWAP = !showVWAP; }),
      stBtn('RSI14', showRSI, () => { showRSI = !showRSI; rsiStrip.style.display = showRSI ? 'block' : 'none'; })
    );
  }

  function renderRSI(candles) {
    rsiStrip.textContent = '';
    if (!showRSI || candles.length < 16) return;
    const pts = calcRSI(candles, 14);
    if (pts.length < 2) return;
    const lastR = pts[pts.length - 1].value;
    const lbl = h('div', { style: 'position:absolute;left:6px;top:2px;font-size:10px;color:var(--label);z-index:2', text: `RSI(14): ${lastR.toFixed(1)}  [70 OVERBOUGHT / 30 OVERSOLD]` });
    const ns = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('viewBox', '0 0 600 52');
    svg.setAttribute('preserveAspectRatio', 'none');
    svg.style.cssText = 'width:100%;height:100%;display:block';
    const yOf = v => 50 - (v / 100) * 46;
    for (const lv of [30, 70]) {
      const ln = document.createElementNS(ns, 'line');
      ln.setAttribute('x1', '0'); ln.setAttribute('x2', '600');
      ln.setAttribute('y1', yOf(lv)); ln.setAttribute('y2', yOf(lv));
      ln.setAttribute('stroke', '#2a2a2a'); ln.setAttribute('stroke-dasharray', '3,3');
      svg.append(ln);
    }
    const poly = document.createElementNS(ns, 'polyline');
    poly.setAttribute('fill', 'none');
    poly.setAttribute('stroke', lastR > 70 ? '#ff3b30' : lastR < 30 ? '#00d26a' : '#ffb000');
    poly.setAttribute('stroke-width', '1.3');
    poly.setAttribute('points', pts.map((p, idx) => `${((idx / (pts.length - 1)) * 600).toFixed(1)},${yOf(p.value).toFixed(1)}`).join(' '));
    svg.append(poly);
    rsiStrip.append(lbl, svg);
  }

  function renderChart(candles) {
    if (!candles || !candles.length) return;
    if (chart) { try { chart.remove(); } catch {} chart = null; }
    wrap.querySelectorAll('.tv-lightweight-charts, .na').forEach(e => e.remove());

    const LWC = window.LightweightCharts;
    if (!LWC) {
      wrap.append(h('div', { class: 'na', text: 'LightweightCharts vendor bundle missing' }));
      return;
    }
    chart = LWC.createChart(wrap, {
      width: wrap.clientWidth || 480,
      height: wrap.clientHeight || 260,
      layout: { background: { color: '#000000' }, textColor: '#ffb000', fontFamily: 'JetBrains Mono, monospace', fontSize: 11 },
      grid: { vertLines: { color: '#141414' }, horzLines: { color: '#141414' } },
      crosshair: { mode: LWC.CrosshairMode.Normal },
      rightPriceScale: { borderColor: '#2a2a2a' },
      timeScale: { borderColor: '#2a2a2a', timeVisible: true, secondsVisible: false },
    });

    const mapped = dedupeByTime(candles.map(c => ({
      time: Math.floor(c.t / 1000), open: +c.o, high: +c.h, low: +c.l, close: +c.c, value: +c.c, vol: +(c.v || 0)
    })));

    if (style === 'candle') {
      mainSeries = chart.addCandlestickSeries({ upColor: '#00d26a', downColor: '#ff3b30', borderUpColor: '#00d26a', borderDownColor: '#ff3b30', wickUpColor: '#00d26a', wickDownColor: '#ff3b30' });
      mainSeries.setData(mapped);
    } else if (style === 'area') {
      mainSeries = chart.addAreaSeries({ lineColor: '#ffb000', topColor: 'rgba(255,176,0,0.28)', bottomColor: 'rgba(255,176,0,0.02)', lineWidth: 2 });
      mainSeries.setData(mapped.map(x => ({ time: x.time, value: x.close })));
    } else {
      mainSeries = chart.addLineSeries({ color: '#ffb000', lineWidth: 2 });
      mainSeries.setData(mapped.map(x => ({ time: x.time, value: x.close })));
    }

    volSeries = chart.addHistogramSeries({ priceFormat: { type: 'volume' }, priceScaleId: '' });
    volSeries.priceScale().applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
    volSeries.setData(mapped.map(x => ({ time: x.time, value: x.vol, color: x.close >= x.open ? 'rgba(0,210,106,0.35)' : 'rgba(255,59,48,0.35)' })));

    if (showSMA && candles.length >= 20) {
      smaS = chart.addLineSeries({ color: '#4da3ff', lineWidth: 1, priceLineVisible: false });
      smaS.setData(dedupeByTime(calcSMA(candles, 20)));
    }
    if (showEMA && candles.length >= 50) {
      emaS = chart.addLineSeries({ color: '#e040fb', lineWidth: 1, priceLineVisible: false });
      emaS.setData(dedupeByTime(calcEMA(candles, 50)));
    }
    if (showBB && candles.length >= 20) {
      const bb = calcBB(candles, 20, 2);
      bbUpS = chart.addLineSeries({ color: '#8a8a8a', lineWidth: 1, lineStyle: 2, priceLineVisible: false });
      bbLoS = chart.addLineSeries({ color: '#8a8a8a', lineWidth: 1, lineStyle: 2, priceLineVisible: false });
      bbUpS.setData(dedupeByTime(bb.up));
      bbLoS.setData(dedupeByTime(bb.lo));
    }
    if (showVWAP && candles.length >= 2) {
      vwapS = chart.addLineSeries({ color: '#ffd600', lineWidth: 1, priceLineVisible: false });
      vwapS.setData(dedupeByTime(calcVWAP(candles)));
    }

    const updateLegend = bar => {
      if (!bar) return;
      const o = bar.open ?? bar.value, hi = bar.high ?? bar.value, lo = bar.low ?? bar.value, cl = bar.close ?? bar.value;
      const chg = o ? ((cl - o) / o) * 100 : 0;
      leg.textContent = `${ctx.symbol} [${iv.toUpperCase()}]  O:${fmtPx(o)}  H:${fmtPx(hi)}  L:${fmtPx(lo)}  C:${fmtPx(cl)} (${fmtPct(chg)})`;
    };
    updateLegend(mapped[mapped.length - 1]);
    chart.subscribeCrosshairMove(param => {
      if (!param || !param.time) return updateLegend(mapped[mapped.length - 1]);
      const b = param.seriesData.get(mainSeries);
      if (b) updateLegend(b);
    });
    chart.timeScale().fitContent();
    renderRSI(candles);
  }

  const ro = new ResizeObserver(() => {
    if (chart) chart.applyOptions({ width: wrap.clientWidth || 480, height: wrap.clientHeight || 260 });
  });
  ro.observe(wrap);
  ctx.cleanup(() => { ro.disconnect(); if (unsub) unsub(); if (chart) try { chart.remove(); } catch {} });

  async function load() {
    if (unsub) { unsub(); unsub = null; }
    leg.textContent = `Loading ${ctx.symbol} (${iv})...`;
    const env = await get('kline', { symbol: ctx.symbol, interval: iv, limit: 300 }, 2000);
    ctx.status(env);
    if (!env.ok || !env.data || !Array.isArray(env.data.candles) || !env.data.candles.length) {
      if (chart) { try { chart.remove(); } catch {} chart = null; }
      wrap.querySelectorAll('.na').forEach(e => e.remove());
      wrap.append(h('div', { class: 'na', text: `N/A (${env.error || 'source down'})` }));
      return;
    }
    lastCandles = env.data.candles;
    renderChart(lastCandles);

    unsub = ctx.sub(`kline:${ctx.symbol}:${iv}`, k => {
      if (!k || !mainSeries) return;
      const t = Math.floor(k.t / 1000);
      if (style === 'candle') mainSeries.update({ time: t, open: +k.o, high: +k.h, low: +k.l, close: +k.c });
      else mainSeries.update({ time: t, value: +k.c });
      if (volSeries) volSeries.update({ time: t, value: +(k.v || 0), color: +k.c >= +k.o ? 'rgba(0,210,106,0.35)' : 'rgba(255,59,48,0.35)' });
      leg.textContent = `${ctx.symbol} [${iv.toUpperCase()} LIVE]  O:${fmtPx(+k.o)}  H:${fmtPx(+k.h)}  L:${fmtPx(+k.l)}  C:${fmtPx(+k.c)}`;
    });
  }

  buildToolbar();
  load();
}

export function mountHP(body, ctx) {
  body.classList.add('fill');
  let iv = '1d';
  const tb = h('div', { class: 'tb' });
  const sc = h('div', { class: 'pb' });
  body.append(tb, sc);
  let rowsData = [];

  function exportCSV() {
    if (!rowsData.length) return;
    const csv = ['Date,Open,High,Low,Close,Change,%Change,Volume']
      .concat(rowsData.map(r => `${fmtDate(r.t)},${r.o},${r.h},${r.l},${r.c},${(r.c - r.o).toFixed(4)},${(((r.c - r.o) / r.o) * 100).toFixed(2)}%,${r.v}`))
      .join('\n');
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
    a.download = `${ctx.symbol}_HP_${iv}.csv`;
    a.click();
  }

  async function load() {
    tb.textContent = '';
    tb.append(h('span', { class: 'lbl', text: `HP HISTORICAL PRICE TABLE [${ctx.symbol}] PERIOD:` }));
    for (const i of ['1h', '4h', '1d', '1w']) {
      tb.append(h('button', { class: i === iv ? 'on' : '', text: i.toUpperCase(), onclick: () => { iv = i; load(); } }));
    }
    tb.append(h('button', { text: 'EXPORT CSV', onclick: exportCSV }));

    sc.textContent = '';
    const env = await get('kline', { symbol: ctx.symbol, interval: iv, limit: 200 }, 3000);
    ctx.status(env);
    if (!env.ok || !env.data || !Array.isArray(env.data.candles) || !env.data.candles.length) {
      sc.append(h('div', { class: 'na', text: `N/A (${env.error || 'source down'})` }));
      return;
    }
    rowsData = [...env.data.candles].reverse();
    const highs = rowsData.map(r => r.h), lows = rowsData.map(r => r.l), closes = rowsData.map(r => r.c);
    const maxH = Math.max(...highs), minL = Math.min(...lows);
    const avgC = closes.reduce((a, b) => a + b, 0) / closes.length;

    const sumBar = h('div', { class: 'tb', style: 'background:#070707' },
      h('span', { class: 'lbl', text: `HIGH: ${fmtPx(maxH)}` }),
      h('span', { class: 'lbl', text: `LOW: ${fmtPx(minL)}` }),
      h('span', { class: 'lbl', text: `AVG: ${fmtPx(avgC)}` }),
      h('span', { class: 'lbl', text: `COUNT: ${rowsData.length} BARS` })
    );
    sc.append(sumBar);

    const tbl = h('table', { class: 't' },
      h('thead', null, h('tr', null, ['Date/Time', 'Close', 'Change', '%Chg', 'Open', 'High', 'Low', 'Volume'].map(x => h('th', { text: x })))),
      h('tbody', null, rowsData.map((r, idx) => {
        const prev = rowsData[idx + 1] ? rowsData[idx + 1].c : r.o;
        const chg = r.c - prev;
        const pct = prev ? (chg / prev) * 100 : 0;
        const cl = dirCls(chg);
        return h('tr', { class: 'row' },
          h('td', { class: 'l lb', text: iv === '1d' || iv === '1w' ? fmtDate(r.t) : fmtTime(r.t, true) }),
          h('td', { class: 'am', text: fmtPx(r.c) }),
          h('td', { class: cl, text: fmtChg(chg) }),
          h('td', { class: cl, text: fmtPct(pct) }),
          h('td', { text: fmtPx(r.o) }),
          h('td', { text: fmtPx(r.h) }),
          h('td', { text: fmtPx(r.l) }),
          h('td', { class: 'mu', text: fmtVol(r.v) })
        );
      }))
    );
    sc.append(tbl);
  }
  load();
}

export function mountCOMP(body, ctx) {
  body.classList.add('fill');
  let peers = [ctx.symbol, 'BTCUSDT', '^GSPC', 'GC=F'];
  peers = [...new Set(peers)];
  let range = 90;

  const tb = h('div', { class: 'tb' });
  const chartBox = h('div', { style: 'height:55%;border-bottom:1px solid var(--border);position:relative;background:#000' });
  const tblBox = h('div', { class: 'pb' });
  body.append(tb, chartBox, tblBox);

  const COLORS = ['#ffb000', '#4da3ff', '#00d26a', '#e040fb', '#ff3b30'];

  async function load() {
    tb.textContent = '';
    const inp = h('input', { placeholder: 'Add symbol (e.g. ETHUSDT, NVDA)', style: 'width:170px' });
    tb.append(
      h('span', { class: 'lbl', text: 'COMP NORMALIZED RETURN:' }),
      ...[30, 90, 180, 365].map(d => h('button', { class: range === d ? 'on' : '', text: d + 'D', onclick: () => { range = d; load(); } })),
      inp,
      h('button', { text: '+ADD', onclick: () => { const v = inp.value.trim().toUpperCase(); if (v && !peers.includes(v)) { peers.push(v); load(); } } })
    );

    chartBox.textContent = '';
    tblBox.textContent = '';

    const res = await Promise.all(peers.map(s => get('kline', { symbol: s, interval: '1d', limit: range }, 5000)));
    const okAny = res.find(r => r.ok);
    ctx.status(okAny || res[0]);

    const seriesList = [];
    for (let i = 0; i < peers.length; i++) {
      const r = res[i];
      const c = (r.ok && r.data && r.data.candles) || [];
      if (c.length >= 2) {
        const base = c[0].c;
        const pts = c.map((x, idx) => ({ idx, t: x.t, pct: base ? ((x.c - base) / base) * 100 : 0, px: x.c }));
        const rets = [];
        for (let k = 1; k < c.length; k++) rets.push((c[k].c - c[k - 1].c) / c[k - 1].c);
        const mean = rets.reduce((a, b) => a + b, 0) / (rets.length || 1);
        const sd = Math.sqrt(rets.reduce((a, b) => a + (b - mean) ** 2, 0) / (rets.length || 1)) * Math.sqrt(252) * 100;
        const sharpe = sd > 0 ? ((pts[pts.length - 1].pct * (252 / range)) / sd) : 0;
        seriesList.push({ sym: peers[i], color: COLORS[i % COLORS.length], pts, totalPct: pts[pts.length - 1].pct, startPx: base, endPx: c[c.length - 1].c, volAnn: sd, sharpe });
      }
    }

    if (!seriesList.length) {
      chartBox.append(h('div', { class: 'na', text: 'N/A (source down)' }));
      return;
    }

    const allY = seriesList.flatMap(s => s.pts.map(p => p.pct));
    const minY = Math.min(...allY, -1), maxY = Math.max(...allY, 1);
    const ns = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('viewBox', '0 0 700 220');
    svg.setAttribute('preserveAspectRatio', 'none');
    svg.style.cssText = 'width:100%;height:100%;display:block';

    const yOf = v => 205 - ((v - minY) / (maxY - minY || 1)) * 185;
    const zY = yOf(0);
    const zLine = document.createElementNS(ns, 'line');
    zLine.setAttribute('x1', '0'); zLine.setAttribute('x2', '700');
    zLine.setAttribute('y1', zY); zLine.setAttribute('y2', zY);
    zLine.setAttribute('stroke', '#333'); zLine.setAttribute('stroke-dasharray', '4,4');
    svg.append(zLine);

    for (const s of seriesList) {
      const poly = document.createElementNS(ns, 'polyline');
      poly.setAttribute('fill', 'none');
      poly.setAttribute('stroke', s.color);
      poly.setAttribute('stroke-width', '1.8');
      poly.setAttribute('points', s.pts.map((p, idx) => `${((idx / (s.pts.length - 1 || 1)) * 690 + 5).toFixed(1)},${yOf(p.pct).toFixed(1)}`).join(' '));
      svg.append(poly);
    }
    const legRow = h('div', { style: 'position:absolute;left:8px;top:4px;display:flex;gap:12px;font-size:11px;background:rgba(0,0,0,0.75);padding:2px 6px' },
      seriesList.map(s => h('span', { style: `color:${s.color};font-weight:bold`, text: `■ ${s.sym}: ${fmtPct(s.totalPct)}` }))
    );
    chartBox.append(legRow, svg);

    tblBox.append(h('table', { class: 't' },
      h('thead', null, h('tr', null, ['Security', 'Start Px', 'Last Px', `${range}D Return`, 'Ann. Vol %', 'Sharpe Est.', 'Action'].map(x => h('th', { text: x })))),
      h('tbody', null, seriesList.map(s => h('tr', { class: 'row', onclick: () => ctx.setSymbol(s.sym) },
        h('td', { class: 'l sym', style: `color:${s.color}`, text: s.sym }),
        h('td', { text: fmtPx(s.startPx) }),
        h('td', { class: 'am', text: fmtPx(s.endPx) }),
        h('td', { class: dirCls(s.totalPct), text: fmtPct(s.totalPct) }),
        h('td', { text: s.volAnn.toFixed(2) + '%' }),
        h('td', { class: dirCls(s.sharpe), text: s.sharpe.toFixed(2) }),
        h('td', null, peers.length > 1 ? h('button', { text: 'X', onclick: ev => { ev.stopPropagation(); peers = peers.filter(x => x !== s.sym); load(); } }) : '')
      )))
    ));
  }
  load();
}

