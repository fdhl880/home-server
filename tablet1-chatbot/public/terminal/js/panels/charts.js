import { h, fmtPx, fmtPct, fmtChg, fmtVol, fmtDate, fmtTime, dirCls } from '../util.js';
import { get } from '../api.js';

function calcSMA(candles, period, field = 'c') {
  const out = [];
  let sum = 0;
  for (let i = 0; i < candles.length; i++) {
    const val = +(candles[i][field] || 0);
    sum += val;
    if (i >= period) sum -= +(candles[i - period][field] || 0);
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

function calcMACD(candles, fast = 12, slow = 26, sigP = 9) {
  if (candles.length < slow + sigP) return [];
  const kF = 2 / (fast + 1), kS = 2 / (slow + 1), kSig = 2 / (sigP + 1);
  let eF = candles[0].c, eS = candles[0].c, sig = 0;
  const out = [];
  for (let i = 0; i < candles.length; i++) {
    const c = candles[i].c;
    eF = i === 0 ? c : c * kF + eF * (1 - kF);
    eS = i === 0 ? c : c * kS + eS * (1 - kS);
    const macd = eF - eS;
    if (i === slow - 1) sig = macd;
    else if (i >= slow) sig = macd * kSig + sig * (1 - kSig);
    if (i >= slow) {
      out.push({ time: Math.floor(candles[i].t / 1000), macd, signal: sig, hist: macd - sig });
    }
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
  let showSMA = true, showEMA = true, showBB = false, showVWAP = true, showVol = true, oscMode = 'RSI'; // 'RSI' | 'MACD' | 'NONE'
  let unsub = null;

  const intervals = intraday ? ['1m', '5m', '15m', '1h'] : ['1m', '5m', '15m', '1h', '4h', '1d', '1w'];
  const tb = h('div', { class: 'tb' });
  const statStrip = h('div', { class: 'tb', style: 'background:#060606;font-size:11px;gap:10px;border-bottom:1px solid #1e1e1e;padding:2px 6px' });
  const wrap = h('div', { class: 'chart', style: 'flex:1;min-height:140px;position:relative;background:#000' });
  const leg = h('div', { class: 'legend am', style: 'background:rgba(0,0,0,0.72);padding:2px 6px;border:1px solid #222;font-size:11px' });
  const volTag = h('div', { style: 'position:absolute;left:6px;bottom:22%;z-index:3;font-size:10px;color:#4da3ff;background:rgba(0,0,0,0.75);padding:1px 5px;pointer-events:none;border-left:2px solid #ffb000' });
  const oscStrip = h('div', { style: 'height:66px;border-top:1px solid var(--border);position:relative;flex:none;background:#030303' });
  wrap.append(leg, volTag);
  body.append(tb, statStrip, wrap, oscStrip);

  let chart = null, mainSeries = null, volSeries = null, volMaSeries = null, smaS = null, emaS = null, bbUpS = null, bbLoS = null, vwapS = null;
  let lastCandles = [];

  function buildToolbar() {
    tb.textContent = '';
    tb.append(h('span', { class: 'lbl', text: intraday ? 'GIP INTRADAY:' : 'GP PERIOD:' }));
    for (const i of intervals) {
      tb.append(h('button', { class: i === iv ? 'on' : '', text: i.toUpperCase(), onclick: () => { iv = i; buildToolbar(); load(); } }));
    }
    tb.append(h('span', { class: 'lbl', text: 'CHART:' }));
    for (const t of ['candle', 'line', 'area']) {
      tb.append(h('button', { class: t === style ? 'on' : '', text: t.toUpperCase(), onclick: () => { style = t; buildToolbar(); renderChart(lastCandles); } }));
    }
    tb.append(h('span', { class: 'lbl', text: 'OVERLAYS:' }));
    const stBtn = (lbl, on, toggle) => h('button', { class: on ? 'on' : '', text: lbl, onclick: () => { toggle(); buildToolbar(); renderChart(lastCandles); } });
    tb.append(
      stBtn('VOL+MA20', showVol, () => { showVol = !showVol; }),
      stBtn('SMA20', showSMA, () => { showSMA = !showSMA; }),
      stBtn('EMA50', showEMA, () => { showEMA = !showEMA; }),
      stBtn('BB(20,2)', showBB, () => { showBB = !showBB; }),
      stBtn('VWAP', showVWAP, () => { showVWAP = !showVWAP; })
    );
    tb.append(h('span', { class: 'lbl', text: 'LOWER STUDY:' }));
    for (const m of ['RSI', 'MACD', 'NONE']) {
      tb.append(h('button', {
        class: oscMode === m ? 'on' : '',
        text: m === 'RSI' ? 'RSI(14)' : m === 'MACD' ? 'MACD(12,26,9)' : 'OFF',
        onclick: () => {
          oscMode = m;
          oscStrip.style.display = oscMode === 'NONE' ? 'none' : 'block';
          buildToolbar();
          renderChart(lastCandles);
        }
      }));
    }
  }

  function renderOscillator(candles) {
    oscStrip.textContent = '';
    if (oscMode === 'NONE' || candles.length < 16) return;
    const ns = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('viewBox', '0 0 700 64');
    svg.setAttribute('preserveAspectRatio', 'none');
    svg.style.cssText = 'width:100%;height:100%;display:block';

    if (oscMode === 'RSI') {
      const pts = calcRSI(candles, 14);
      if (pts.length < 2) return;
      const lastR = pts[pts.length - 1].value;
      const stateTxt = lastR >= 70 ? 'OVERBOUGHT (>70)' : lastR <= 30 ? 'OVERSOLD (<30)' : 'NEUTRAL REGIME';
      const stateCol = lastR >= 70 ? '#ff3b30' : lastR <= 30 ? '#00d26a' : '#ffb000';
      const lbl = h('div', {
        style: 'position:absolute;left:6px;top:2px;font-size:10.5px;color:var(--label);z-index:2;background:rgba(0,0,0,0.75);padding:0 4px'
      },
        h('span', { text: `RSI(14): ` }),
        h('b', { style: `color:${stateCol}`, text: `${lastR.toFixed(2)} [${stateTxt}]` }),
        h('span', { class: 'mu', text: `   BANDS: 70 / 50 / 30` })
      );
      const yOf = v => 58 - (v / 100) * 52;
      for (const [lv, col] of [[30, '#00d26a55'], [50, '#333333'], [70, '#ff3b3055']]) {
        const ln = document.createElementNS(ns, 'line');
        ln.setAttribute('x1', '0'); ln.setAttribute('x2', '700');
        ln.setAttribute('y1', yOf(lv)); ln.setAttribute('y2', yOf(lv));
        ln.setAttribute('stroke', col); ln.setAttribute('stroke-dasharray', lv === 50 ? '2,4' : '4,3');
        svg.append(ln);
      }
      const poly = document.createElementNS(ns, 'polyline');
      poly.setAttribute('fill', 'none');
      poly.setAttribute('stroke', stateCol);
      poly.setAttribute('stroke-width', '1.6');
      poly.setAttribute('points', pts.map((p, idx) => `${((idx / (pts.length - 1)) * 700).toFixed(1)},${yOf(p.value).toFixed(1)}`).join(' '));
      svg.append(poly);
      oscStrip.append(lbl, svg);
    } else if (oscMode === 'MACD') {
      const mPts = calcMACD(candles, 12, 26, 9);
      if (mPts.length < 2) return;
      const lastM = mPts[mPts.length - 1];
      const allVals = mPts.flatMap(x => [x.macd, x.signal, x.hist]);
      const maxAbs = Math.max(...allVals.map(Math.abs), 0.0001);
      const yOf = v => 32 - (v / maxAbs) * 26;

      const zLn = document.createElementNS(ns, 'line');
      zLn.setAttribute('x1', '0'); zLn.setAttribute('x2', '700');
      zLn.setAttribute('y1', '32'); zLn.setAttribute('y2', '32');
      zLn.setAttribute('stroke', '#333');
      svg.append(zLn);

      const barW = Math.max(1.5, 680 / mPts.length);
      mPts.forEach((p, idx) => {
        const x = (idx / (mPts.length - 1)) * 690 + 5;
        const y = yOf(p.hist);
        const rect = document.createElementNS(ns, 'rect');
        rect.setAttribute('x', (x - barW / 2).toFixed(1));
        rect.setAttribute('y', Math.min(32, y).toFixed(1));
        rect.setAttribute('width', barW.toFixed(1));
        rect.setAttribute('height', Math.max(1, Math.abs(32 - y)).toFixed(1));
        rect.setAttribute('fill', p.hist >= 0 ? 'rgba(0,210,106,0.55)' : 'rgba(255,59,48,0.55)');
        svg.append(rect);
      });

      const pMacd = document.createElementNS(ns, 'polyline');
      pMacd.setAttribute('fill', 'none'); pMacd.setAttribute('stroke', '#ffb000'); pMacd.setAttribute('stroke-width', '1.5');
      pMacd.setAttribute('points', mPts.map((p, idx) => `${((idx / (mPts.length - 1)) * 690 + 5).toFixed(1)},${yOf(p.macd).toFixed(1)}`).join(' '));

      const pSig = document.createElementNS(ns, 'polyline');
      pSig.setAttribute('fill', 'none'); pSig.setAttribute('stroke', '#4da3ff'); pSig.setAttribute('stroke-width', '1.3');
      pSig.setAttribute('points', mPts.map((p, idx) => `${((idx / (mPts.length - 1)) * 690 + 5).toFixed(1)},${yOf(p.signal).toFixed(1)}`).join(' '));
      svg.append(pMacd, pSig);

      const lbl = h('div', {
        style: 'position:absolute;left:6px;top:2px;font-size:10.5px;color:var(--label);z-index:2;background:rgba(0,0,0,0.75);padding:0 4px'
      },
        h('span', { style: 'color:#ffb000;font-weight:bold', text: `MACD(12,26): ${lastM.macd.toFixed(3)}   ` }),
        h('span', { style: 'color:#4da3ff;font-weight:bold', text: `SIGNAL(9): ${lastM.signal.toFixed(3)}   ` }),
        h('span', { style: `color:${lastM.hist >= 0 ? '#00d26a' : '#ff3b30'};font-weight:bold`, text: `HIST: ${lastM.hist >= 0 ? '+' : ''}${lastM.hist.toFixed(3)}` })
      );
      oscStrip.append(lbl, svg);
    }
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
    const w = wrap.clientWidth || 520;
    const ht = wrap.clientHeight || 280;
    chart = LWC.createChart(wrap, {
      width: w,
      height: ht,
      layout: { background: { color: '#000000' }, textColor: '#ffb000', fontFamily: 'JetBrains Mono, monospace', fontSize: 11 },
      grid: { vertLines: { color: '#161616' }, horzLines: { color: '#161616' } },
      crosshair: { mode: LWC.CrosshairMode.Normal },
      rightPriceScale: {
        borderColor: '#333333',
        scaleMargins: { top: 0.06, bottom: showVol ? 0.28 : 0.06 }
      },
      timeScale: { borderColor: '#333333', timeVisible: true, secondsVisible: false },
    });

    const mapped = dedupeByTime(candles.map(c => ({
      time: Math.floor(c.t / 1000), open: +c.o, high: +c.h, low: +c.l, close: +c.c, value: +c.c, vol: +(c.v || 0)
    })));
    const volByTime = new Map(mapped.map(x => [x.time, x.vol]));

    if (style === 'candle') {
      mainSeries = chart.addCandlestickSeries({
        upColor: '#00d26a', downColor: '#ff3b30',
        borderUpColor: '#00d26a', borderDownColor: '#ff3b30',
        wickUpColor: '#00d26a', wickDownColor: '#ff3b30',
        priceLineVisible: true, lastValueVisible: true
      });
      mainSeries.setData(mapped);
    } else if (style === 'area') {
      mainSeries = chart.addAreaSeries({ lineColor: '#ffb000', topColor: 'rgba(255,176,0,0.32)', bottomColor: 'rgba(255,176,0,0.02)', lineWidth: 2 });
      mainSeries.setData(mapped.map(x => ({ time: x.time, value: x.close })));
    } else {
      mainSeries = chart.addLineSeries({ color: '#ffb000', lineWidth: 2 });
      mainSeries.setData(mapped.map(x => ({ time: x.time, value: x.close })));
    }

    // High & Low price markers on mainSeries
    if (mapped.length >= 5 && typeof mainSeries.setMarkers === 'function') {
      let maxBar = mapped[0], minBar = mapped[0];
      for (const b of mapped) {
        if (b.high > maxBar.high) maxBar = b;
        if (b.low < minBar.low) minBar = b;
      }
      const markers = [
        { time: minBar.time, position: 'belowBar', color: '#ff3b30', shape: 'arrowUp', text: `LOW ${fmtPx(minBar.low)}` },
        { time: maxBar.time, position: 'aboveBar', color: '#00d26a', shape: 'arrowDown', text: `HIGH ${fmtPx(maxBar.high)}` }
      ].sort((a, b) => a.time - b.time);
      try { mainSeries.setMarkers(markers); } catch {}
    }

    // Dedicated Volume Sub-Region (Bottom 25% of Chart) + Volume SMA(20) Line
    const volSmaArr = dedupeByTime(calcSMA(candles, 20, 'v'));
    const lastVolSma = volSmaArr.length ? volSmaArr[volSmaArr.length - 1].value : 0;
    if (showVol) {
      volSeries = chart.addHistogramSeries({
        priceFormat: { type: 'volume' },
        priceScaleId: 'vol',
        lastValueVisible: true,
        priceLineVisible: false
      });
      chart.priceScale('vol').applyOptions({
        scaleMargins: { top: 0.75, bottom: 0.0 },
        borderVisible: true
      });
      volSeries.setData(mapped.map(x => ({
        time: x.time,
        value: x.vol,
        color: x.close >= x.open ? 'rgba(0, 210, 106, 0.70)' : 'rgba(255, 59, 48, 0.70)'
      })));

      if (volSmaArr.length >= 2) {
        volMaSeries = chart.addLineSeries({
          color: '#00e5ff',
          lineWidth: 1.5,
          priceScaleId: 'vol',
          priceLineVisible: false,
          lastValueVisible: false
        });
        volMaSeries.setData(volSmaArr);
      }
      const lastBarVol = mapped[mapped.length - 1].vol;
      volTag.style.display = 'block';
      volTag.textContent = `VOLUME PANE  |  BAR VOL: ${fmtVol(lastBarVol)}  •  VOL SMA(20): ${fmtVol(lastVolSma)}`;
    } else {
      volTag.style.display = 'none';
    }

    const smaArr = dedupeByTime(calcSMA(candles, 20, 'c'));
    const emaArr = dedupeByTime(calcEMA(candles, 50));
    const vwapArr = dedupeByTime(calcVWAP(candles));

    if (showSMA && smaArr.length) {
      smaS = chart.addLineSeries({ color: '#4da3ff', lineWidth: 1.3, priceLineVisible: false, lastValueVisible: false });
      smaS.setData(smaArr);
    }
    if (showEMA && emaArr.length) {
      emaS = chart.addLineSeries({ color: '#e040fb', lineWidth: 1.3, priceLineVisible: false, lastValueVisible: false });
      emaS.setData(emaArr);
    }
    if (showBB && candles.length >= 20) {
      const bb = calcBB(candles, 20, 2);
      bbUpS = chart.addLineSeries({ color: '#8a8a8a', lineWidth: 1, lineStyle: 2, priceLineVisible: false, lastValueVisible: false });
      bbLoS = chart.addLineSeries({ color: '#8a8a8a', lineWidth: 1, lineStyle: 2, priceLineVisible: false, lastValueVisible: false });
      bbUpS.setData(dedupeByTime(bb.up));
      bbLoS.setData(dedupeByTime(bb.lo));
    }
    if (showVWAP && vwapArr.length) {
      vwapS = chart.addLineSeries({ color: '#ffd600', lineWidth: 1.3, lineStyle: 1, priceLineVisible: false, lastValueVisible: false });
      vwapS.setData(vwapArr);
    }

    const total24Vol = mapped.slice(-24).reduce((s, x) => s + (x.vol || 0), 0);
    const periodHigh = Math.max(...mapped.map(x => x.high));
    const periodLow = Math.min(...mapped.map(x => x.low));
    const lastSmaVal = smaArr.length ? smaArr[smaArr.length - 1].value : null;
    const lastEmaVal = emaArr.length ? emaArr[emaArr.length - 1].value : null;
    const lastVwapVal = vwapArr.length ? vwapArr[vwapArr.length - 1].value : null;

    const updateLegend = (bar, barVol) => {
      if (!bar) return;
      const o = bar.open ?? bar.value, hi = bar.high ?? bar.value, lo = bar.low ?? bar.value, cl = bar.close ?? bar.value;
      const v = barVol != null ? barVol : (volByTime.get(bar.time) ?? 0);
      const chg = o ? cl - o : 0;
      const chgPct = o ? ((cl - o) / o) * 100 : 0;
      leg.innerHTML = `<b style="color:#fff">${ctx.symbol}</b> [${iv.toUpperCase()}]  O:<b style="color:#ffb000">${fmtPx(o)}</b>  H:<b style="color:#00d26a">${fmtPx(hi)}</b>  L:<b style="color:#ff3b30">${fmtPx(lo)}</b>  C:<b style="color:#ffb000">${fmtPx(cl)}</b> (<span class="${dirCls(chgPct)}">${fmtPct(chgPct)}</span>)  VOL:<b style="color:#00e5ff">${fmtVol(v)}</b>`;

      statStrip.innerHTML = '';
      statStrip.append(
        h('span', { class: 'sym am', text: `LAST: ${fmtPx(cl)}` }),
        h('span', { class: dirCls(chg), text: `CHG: ${fmtChg(chg)} (${fmtPct(chgPct)})` }),
        h('span', { class: 'lb', text: `RANGE HI: ${fmtPx(periodHigh)} / LO: ${fmtPx(periodLow)}` }),
        h('span', { style: 'color:#00e5ff;font-weight:bold', text: `BAR VOL: ${fmtVol(v)} • 24B VOL: ${fmtVol(total24Vol)}` }),
        lastVwapVal != null ? h('span', { style: 'color:#ffd600', text: `VWAP: ${fmtPx(lastVwapVal)}` }) : null,
        lastSmaVal != null ? h('span', { style: 'color:#4da3ff', text: `SMA20: ${fmtPx(lastSmaVal)}` }) : null,
        lastEmaVal != null ? h('span', { style: 'color:#e040fb', text: `EMA50: ${fmtPx(lastEmaVal)}` }) : null
      );
    };

    const latestBar = mapped[mapped.length - 1];
    updateLegend(latestBar, latestBar.vol);

    chart.subscribeCrosshairMove(param => {
      if (!param || !param.time) return updateLegend(latestBar, latestBar.vol);
      const b = param.seriesData.get(mainSeries);
      const vBar = volSeries ? param.seriesData.get(volSeries) : null;
      if (b) updateLegend(b, vBar ? vBar.value : volByTime.get(param.time));
    });
    chart.timeScale().fitContent();
    renderOscillator(candles);
  }

  const ro = new ResizeObserver(() => {
    if (chart && wrap.clientWidth > 0 && wrap.clientHeight > 0) {
      chart.applyOptions({ width: wrap.clientWidth, height: wrap.clientHeight });
    }
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
    requestAnimationFrame(() => renderChart(lastCandles));

    unsub = ctx.sub(`kline:${ctx.symbol}:${iv}`, k => {
      if (!k || !mainSeries) return;
      const t = Math.floor(k.t / 1000);
      if (style === 'candle') mainSeries.update({ time: t, open: +k.o, high: +k.h, low: +k.l, close: +k.c });
      else mainSeries.update({ time: t, value: +k.c });
      if (volSeries) volSeries.update({ time: t, value: +(k.v || 0), color: +k.c >= +k.o ? 'rgba(0, 210, 106, 0.70)' : 'rgba(255, 59, 48, 0.70)' });
      leg.innerHTML = `<b style="color:#fff">${ctx.symbol}</b> [${iv.toUpperCase()} LIVE]  O:<b>${fmtPx(+k.o)}</b>  H:<b style="color:#00d26a">${fmtPx(+k.h)}</b>  L:<b style="color:#ff3b30">${fmtPx(+k.l)}</b>  C:<b style="color:#ffb000">${fmtPx(+k.c)}</b>  VOL:<b style="color:#00e5ff">${fmtVol(+(k.v || 0))}</b>`;
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
    tb.append(h('span', { class: 'lbl', text: `HP HISTORICAL PRICE & VOLUME TABLE [${ctx.symbol}] PERIOD:` }));
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
    const highs = rowsData.map(r => r.h), lows = rowsData.map(r => r.l), closes = rowsData.map(r => r.c), vols = rowsData.map(r => r.v || 0);
    const maxH = Math.max(...highs), minL = Math.min(...lows);
    const avgC = closes.reduce((a, b) => a + b, 0) / closes.length;
    const avgV = vols.reduce((a, b) => a + b, 0) / (vols.length || 1);
    const maxV = Math.max(...vols, 1);

    const sumBar = h('div', { class: 'tb', style: 'background:#070707;gap:14px' },
      h('span', { class: 'up sym', text: `HIGH: ${fmtPx(maxH)}` }),
      h('span', { class: 'dn sym', text: `LOW: ${fmtPx(minL)}` }),
      h('span', { class: 'am sym', text: `MEAN PX: ${fmtPx(avgC)}` }),
      h('span', { style: 'color:#00e5ff;font-weight:bold', text: `AVG VOLUME: ${fmtVol(avgV)}` }),
      h('span', { class: 'lbl', text: `COUNT: ${rowsData.length} BARS` })
    );
    sc.append(sumBar);

    const tbl = h('table', { class: 't' },
      h('thead', null, h('tr', null, ['Date/Time', 'Close', 'Change', '%Chg', 'Open', 'High', 'Low', 'Volume', 'Vol Bar'].map(x => h('th', { text: x })))),
      h('tbody', null, rowsData.map((r, idx) => {
        const prev = rowsData[idx + 1] ? rowsData[idx + 1].c : r.o;
        const chg = r.c - prev;
        const pct = prev ? (chg / prev) * 100 : 0;
        const cl = dirCls(chg);
        const vPct = Math.min(100, ((r.v || 0) / maxV) * 100).toFixed(1);
        return h('tr', { class: 'row' },
          h('td', { class: 'l lb', text: iv === '1d' || iv === '1w' ? fmtDate(r.t) : fmtTime(r.t, true) }),
          h('td', { class: 'am sym', text: fmtPx(r.c) }),
          h('td', { class: cl, text: fmtChg(chg) }),
          h('td', { class: cl, text: fmtPct(pct) }),
          h('td', { text: fmtPx(r.o) }),
          h('td', { class: 'up', text: fmtPx(r.h) }),
          h('td', { class: 'dn', text: fmtPx(r.l) }),
          h('td', { style: 'color:#00e5ff', text: fmtVol(r.v) }),
          h('td', { class: 'bar', style: 'width:80px' },
            h('i', { style: `width:${vPct}%;background:${chg >= 0 ? 'var(--up)' : 'var(--dn)'}` }),
            h('span', { class: 'mu', text: `${((r.v || 0) / (avgV || 1)).toFixed(1)}x` })
          )
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
  const chartBox = h('div', { style: 'height:56%;border-bottom:1px solid var(--border);position:relative;background:#000' });
  const tblBox = h('div', { class: 'pb' });
  body.append(tb, chartBox, tblBox);

  const COLORS = ['#ffb000', '#4da3ff', '#00d26a', '#e040fb', '#ff3b30'];

  async function load() {
    tb.textContent = '';
    const inp = h('input', { placeholder: 'Add symbol (e.g. ETHUSDT, NVDA)', style: 'width:170px' });
    tb.append(
      h('span', { class: 'lbl', text: 'COMP NORMALIZED TOTAL RETURN:' }),
      ...[30, 90, 180, 365].map(d => h('button', { class: range === d ? 'on' : '', text: d + 'D', onclick: () => { range = d; load(); } })),
      inp,
      h('button', { text: '+ADD SECURITY', onclick: () => { const v = inp.value.trim().toUpperCase(); if (v && !peers.includes(v)) { peers.push(v); load(); } } })
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
        const totVol = c.reduce((s, x) => s + (x.v || 0), 0);
        seriesList.push({ sym: peers[i], color: COLORS[i % COLORS.length], pts, totalPct: pts[pts.length - 1].pct, startPx: base, endPx: c[c.length - 1].c, volAnn: sd, sharpe, totVol });
      }
    }

    if (!seriesList.length) {
      chartBox.append(h('div', { class: 'na', text: 'N/A (source down)' }));
      return;
    }

    const allY = seriesList.flatMap(s => s.pts.map(p => p.pct));
    const minY = Math.min(...allY, -2), maxY = Math.max(...allY, 2);
    const ns = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('viewBox', '0 0 720 220');
    svg.setAttribute('preserveAspectRatio', 'none');
    svg.style.cssText = 'width:100%;height:100%;display:block';

    const yOf = v => 205 - ((v - minY) / (maxY - minY || 1)) * 180;
    for (let g = 0; g <= 4; g++) {
      const val = maxY - ((maxY - minY) * g) / 4;
      const gy = yOf(val);
      const gl = document.createElementNS(ns, 'line');
      gl.setAttribute('x1', '8'); gl.setAttribute('x2', '660');
      gl.setAttribute('y1', gy.toFixed(1)); gl.setAttribute('y2', gy.toFixed(1));
      gl.setAttribute('stroke', '#181818');
      svg.append(gl);
      const gt = document.createElementNS(ns, 'text');
      gt.setAttribute('x', '715'); gt.setAttribute('y', (gy + 3).toFixed(1));
      gt.setAttribute('text-anchor', 'end'); gt.setAttribute('fill', '#777'); gt.setAttribute('font-size', '10');
      gt.textContent = (val >= 0 ? '+' : '') + val.toFixed(1) + '%';
      svg.append(gt);
    }

    const zY = yOf(0);
    const zLine = document.createElementNS(ns, 'line');
    zLine.setAttribute('x1', '8'); zLine.setAttribute('x2', '660');
    zLine.setAttribute('y1', zY); zLine.setAttribute('y2', zY);
    zLine.setAttribute('stroke', '#444'); zLine.setAttribute('stroke-dasharray', '4,4');
    svg.append(zLine);

    for (const s of seriesList) {
      const poly = document.createElementNS(ns, 'polyline');
      poly.setAttribute('fill', 'none');
      poly.setAttribute('stroke', s.color);
      poly.setAttribute('stroke-width', '2.0');
      poly.setAttribute('points', s.pts.map((p, idx) => `${((idx / (s.pts.length - 1 || 1)) * 650 + 10).toFixed(1)},${yOf(p.pct).toFixed(1)}`).join(' '));
      svg.append(poly);
    }
    const legRow = h('div', { style: 'position:absolute;left:8px;top:4px;display:flex;gap:12px;font-size:11px;background:rgba(0,0,0,0.82);padding:2px 6px;border:1px solid #222' },
      seriesList.map(s => h('span', { style: `color:${s.color};font-weight:bold`, text: `■ ${s.sym}: ${fmtPct(s.totalPct)}` }))
    );
    chartBox.append(legRow, svg);

    tblBox.append(h('table', { class: 't' },
      h('thead', null, h('tr', null, ['Security', 'Start Px', 'Last Px', `${range}D Return`, 'Ann. Vol %', 'Sharpe Ratio', 'Cum. Volume', 'Action'].map(x => h('th', { text: x })))),
      h('tbody', null, seriesList.map(s => h('tr', { class: 'row', onclick: () => ctx.setSymbol(s.sym) },
        h('td', { class: 'l sym', style: `color:${s.color}`, text: '■ ' + s.sym }),
        h('td', { text: fmtPx(s.startPx) }),
        h('td', { class: 'am sym', text: fmtPx(s.endPx) }),
        h('td', { class: dirCls(s.totalPct) + ' sym', text: fmtPct(s.totalPct) }),
        h('td', { text: s.volAnn.toFixed(2) + '%' }),
        h('td', { class: dirCls(s.sharpe), text: s.sharpe.toFixed(2) }),
        h('td', { style: 'color:#00e5ff', text: fmtVol(s.totVol) }),
        h('td', null, peers.length > 1 ? h('button', { text: 'REMOVE', onclick: ev => { ev.stopPropagation(); peers = peers.filter(x => x !== s.sym); load(); } }) : '')
      )))
    ));
  }
  load();
}
