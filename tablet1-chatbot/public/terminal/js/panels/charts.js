import { h, fmtPx, fmtPct, fmtChg, fmtVol, fmtDate, fmtTime, dirCls } from '../util.js';
import { get, getRaw } from '../api.js';

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

function calcHeikinAshi(mapped) {
  const out = [];
  for (let i = 0; i < mapped.length; i++) {
    const b = mapped[i];
    const haClose = (b.open + b.high + b.low + b.close) / 4;
    const haOpen = i === 0 ? (b.open + b.close) / 2 : (out[i - 1].open + out[i - 1].close) / 2;
    const haHigh = Math.max(b.high, haOpen, haClose);
    const haLow = Math.min(b.low, haOpen, haClose);
    out.push({ ...b, open: haOpen, high: haHigh, low: haLow, close: haClose, value: haClose });
  }
  return out;
}

function calcIchimoku(mapped) {
  const n = mapped ? mapped.length : 0;
  if (n < 26) return [];
  const midHL = (end, len) => {
    const s = Math.max(0, end - len + 1);
    let hi = -Infinity, lo = Infinity;
    for (let i = s; i <= end; i++) {
      if (mapped[i].high > hi) hi = mapped[i].high;
      if (mapped[i].low < lo) lo = mapped[i].low;
    }
    return (hi + lo) / 2;
  };
  const raw = [];
  for (let i = 0; i < n; i++) {
    const tenkan = i >= 8 ? midHL(i, 9) : null;
    const kijun = i >= 25 ? midHL(i, 26) : null;
    const spanB = i >= 51 ? midHL(i, 52) : (i >= 25 ? midHL(i, i + 1) : null);
    const spanA = (tenkan != null && kijun != null) ? (tenkan + kijun) / 2 : null;
    raw.push({ idx: i, tenkan, kijun, spanA, spanB });
  }
  return raw;
}

function calcSuperTrend(mapped, period = 10, mult = 3.0) {
  const n = mapped ? mapped.length : 0;
  if (n < period + 2) return [];
  const tr = new Array(n).fill(0);
  for (let i = 0; i < n; i++) {
    const prevC = i > 0 ? mapped[i - 1].close : mapped[i].open;
    tr[i] = Math.max(
      mapped[i].high - mapped[i].low,
      Math.abs(mapped[i].high - prevC),
      Math.abs(mapped[i].low - prevC)
    );
  }
  const atr = new Array(n).fill(0);
  let sum = 0;
  for (let i = 0; i < n; i++) {
    sum += tr[i];
    if (i === period - 1) atr[i] = sum / period;
    else if (i >= period) atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period;
  }
  const out = [];
  let finalUp = 0, finalLo = 0, dir = 1;
  for (let i = period - 1; i < n; i++) {
    const hl2 = (mapped[i].high + mapped[i].low) / 2;
    const basicUp = hl2 + mult * atr[i];
    const basicLo = hl2 - mult * atr[i];
    if (i === period - 1) {
      finalUp = basicUp;
      finalLo = basicLo;
      dir = mapped[i].close >= hl2 ? 1 : -1;
    } else {
      const prevC = mapped[i - 1].close;
      finalUp = (basicUp < finalUp || prevC > finalUp) ? basicUp : finalUp;
      finalLo = (basicLo > finalLo || prevC < finalLo) ? basicLo : finalLo;
      if (dir === -1 && mapped[i].close > finalUp) dir = 1;
      else if (dir === 1 && mapped[i].close < finalLo) dir = -1;
    }
    const prevDir = out.length ? out[out.length - 1].dir : dir;
    out.push({
      idx: i,
      dir,
      line: dir === 1 ? finalLo : finalUp,
      flipped: out.length > 0 && dir !== prevDir
    });
  }
  return out;
}

/**
 * Computes institutional Technical Master overlays strictly from real OHLCV bars:
 * - Fractal Market Structure (HH/HL/LH/LL) + BOS/CHoCH breaks
 * - OLS Linear Regression Channel (+/- 1.5 sigma) & Swing Trendlines
 * - Unmitigated 3-bar Fair Value Gaps (FVG) & Supply/Demand Order Blocks
 * - Auto-Fibonacci Retracement + 0.618 Golden Pocket
 * - Visible-range Volume Profile (VPVR) + POC / VAH / VAL
 */
export function computeTechnicalMasterSignals(mapped, visibleFromIdx = 0, visibleToIdx = null) {
  const n = mapped ? mapped.length : 0;
  if (n < 6) {
    return { bias: 'NEUTRAL', swings: [], breaks: [], reg: null, trendlines: [], fvgs: [], obs: [], fib: null, vpvr: null };
  }
  const endIdx = visibleToIdx != null ? Math.min(n - 1, Math.max(4, Math.floor(visibleToIdx))) : n - 1;
  const startIdx = Math.max(0, Math.min(endIdx - 4, Math.floor(visibleFromIdx || 0)));

  // True Range ATR(14) for spacing/displacement filters
  let atrSum = 0, atrCnt = 0;
  for (let i = Math.max(1, n - 30); i < n; i++) {
    const tr = Math.max(
      mapped[i].high - mapped[i].low,
      Math.abs(mapped[i].high - mapped[i - 1].close),
      Math.abs(mapped[i].low - mapped[i - 1].close)
    );
    atrSum += tr;
    atrCnt++;
  }
  const atr = atrCnt ? (atrSum / atrCnt) : Math.max(1e-8, mapped[n - 1].close * 0.003);

  // 1. Fractal Swings (left/right window = 3)
  const k = Math.max(2, Math.min(4, Math.floor(n / 28)));
  const rawHighs = [];
  const rawLows = [];
  for (let i = k; i < n - Math.max(1, Math.floor(k / 2)); i++) {
    let isH = true, isL = true;
    const rightBound = Math.min(n - 1, i + k);
    for (let j = i - k; j <= rightBound; j++) {
      if (j === i) continue;
      if (mapped[j].high >= mapped[i].high) isH = false;
      if (mapped[j].low <= mapped[i].low) isL = false;
    }
    if (isH) rawHighs.push({ idx: i, time: mapped[i].time, price: mapped[i].high, type: 'H' });
    if (isL) rawLows.push({ idx: i, time: mapped[i].time, price: mapped[i].low, type: 'L' });
  }

  // Classify HH/LH & HL/LL (throttled spacing >= 7 bars so structural labels never crowd)
  const filterSpaced = (arr) => {
    const res = [];
    for (const p of arr) {
      if (!res.length || p.idx - res[res.length - 1].idx >= 7) res.push(p);
      else {
        const last = res[res.length - 1];
        if ((p.type === 'H' && p.price > last.price) || (p.type === 'L' && p.price < last.price)) {
          res[res.length - 1] = p;
        }
      }
    }
    return res;
  };
  const swingHighs = filterSpaced(rawHighs);
  const swingLows = filterSpaced(rawLows);
  const labeledHighs = swingHighs.map((s, i) => ({
    ...s,
    tag: i === 0 ? 'SH' : (s.price > swingHighs[i - 1].price ? 'HH' : 'LH')
  }));
  const labeledLows = swingLows.map((s, i) => ({
    ...s,
    tag: i === 0 ? 'SL' : (s.price > swingLows[i - 1].price ? 'HL' : 'LL')
  }));
  const swings = [...labeledHighs, ...labeledLows].sort((a, b) => a.idx - b.idx);

  // Market Structure Breaks (BOS / CHoCH)
  let bias = 'NEUTRAL';
  if (labeledHighs.length >= 2 && labeledLows.length >= 2) {
    const lh = labeledHighs[labeledHighs.length - 1];
    const ll = labeledLows[labeledLows.length - 1];
    if (lh.tag === 'HH' && ll.tag === 'HL') bias = 'BULLISH';
    else if (lh.tag === 'LH' && ll.tag === 'LL') bias = 'BEARISH';
  }
  const breaks = [];
  let trendDir = 0; // 1 bull, -1 bear
  let activeHigh = swingHighs.length ? swingHighs[0] : null;
  let activeLow = swingLows.length ? swingLows[0] : null;
  const hMap = new Map(swingHighs.map(x => [x.idx, x]));
  const lMap = new Map(swingLows.map(x => [x.idx, x]));
  for (let i = 1; i < n; i++) {
    if (activeHigh && mapped[i].close > activeHigh.price && i > activeHigh.idx) {
      const kind = trendDir === -1 ? 'CHoCH' : 'BOS';
      breaks.push({ kind, dir: 'BULL', fromIdx: activeHigh.idx, toIdx: i, price: activeHigh.price });
      trendDir = 1;
      activeHigh = null;
    } else if (activeLow && mapped[i].close < activeLow.price && i > activeLow.idx) {
      const kind = trendDir === 1 ? 'CHoCH' : 'BOS';
      breaks.push({ kind, dir: 'BEAR', fromIdx: activeLow.idx, toIdx: i, price: activeLow.price });
      trendDir = -1;
      activeLow = null;
    }
    if (hMap.has(i)) activeHigh = hMap.get(i);
    if (lMap.has(i)) activeLow = lMap.get(i);
  }
  const recentBreaks = breaks.slice(-3);
  if (trendDir === 1 && bias === 'NEUTRAL') bias = 'BULLISH';
  if (trendDir === -1 && bias === 'NEUTRAL') bias = 'BEARISH';

  // 2. OLS Linear Regression Channel (+/- 1.5 sigma) over recent window + Pivot Trendlines
  const regLen = Math.min(80, n);
  const regStart = n - regLen;
  let sumX = 0, sumY = 0, sumXX = 0, sumXY = 0;
  for (let i = 0; i < regLen; i++) {
    const y = mapped[regStart + i].close;
    sumX += i; sumY += y; sumXX += i * i; sumXY += i * y;
  }
  const denom = regLen * sumXX - sumX * sumX || 1;
  const slope = (regLen * sumXY - sumX * sumY) / denom;
  const intercept = (sumY - slope * sumX) / regLen;
  let sqErr = 0;
  for (let i = 0; i < regLen; i++) {
    const est = slope * i + intercept;
    sqErr += (mapped[regStart + i].close - est) ** 2;
  }
  const sigma = Math.sqrt(sqErr / Math.max(1, regLen));
  const reg = {
    startIdx: regStart,
    endIdx: n - 1,
    yStart: intercept,
    yEnd: slope * (regLen - 1) + intercept,
    sigma15: sigma * 1.5
  };

  const trendlines = [];
  if (swingHighs.length >= 2) {
    const p1 = swingHighs[swingHighs.length - 2];
    const p2 = swingHighs[swingHighs.length - 1];
    if (p2.idx > p1.idx) {
      const slp = (p2.price - p1.price) / (p2.idx - p1.idx);
      const yEnd = p2.price + slp * (n + 6 - p2.idx);
      trendlines.push({ x1: p1.idx, y1: p1.price, x2: n + 6, y2: yEnd, kind: 'RES' });
    }
  }
  if (swingLows.length >= 2) {
    const p1 = swingLows[swingLows.length - 2];
    const p2 = swingLows[swingLows.length - 1];
    if (p2.idx > p1.idx) {
      const slp = (p2.price - p1.price) / (p2.idx - p1.idx);
      const yEnd = p2.price + slp * (n + 6 - p2.idx);
      trendlines.push({ x1: p1.idx, y1: p1.price, x2: n + 6, y2: yEnd, kind: 'SUP' });
    }
  }

  // 3. Fair Value Gaps (unmitigated 3-candle imbalances) & Supply/Demand Order Blocks
  const fvgs = [];
  for (let i = 2; i < n; i++) {
    const c0 = mapped[i - 2], c2 = mapped[i];
    if (c2.low > c0.high && (c2.low - c0.high) > atr * 0.12) {
      let mitigated = false;
      for (let j = i + 1; j < n; j++) {
        if (mapped[j].low <= c0.high) { mitigated = true; break; }
      }
      if (!mitigated) fvgs.push({ dir: 'BULL', startIdx: i - 1, top: c2.low, bot: c0.high });
    } else if (c2.high < c0.low && (c0.low - c2.high) > atr * 0.12) {
      let mitigated = false;
      for (let j = i + 1; j < n; j++) {
        if (mapped[j].high >= c0.low) { mitigated = true; break; }
      }
      if (!mitigated) fvgs.push({ dir: 'BEAR', startIdx: i - 1, top: c0.low, bot: c2.high });
    }
  }
  const obs = [];
  for (let i = n - 3; i >= 2; i--) {
    const prev = mapped[i], imp = mapped[i + 1];
    const bodyPrev = Math.abs(prev.close - prev.open);
    const bodyImp = Math.abs(imp.close - imp.open);
    if (prev.close < prev.open && imp.close > imp.open && bodyImp > Math.max(atr * 0.9, bodyPrev * 1.4)) {
      let broken = false;
      for (let j = i + 2; j < n; j++) { if (mapped[j].close < prev.low) { broken = true; break; } }
      if (!broken) { obs.push({ dir: 'BULL', startIdx: i, top: prev.high, bot: prev.low }); break; }
    }
  }
  for (let i = n - 3; i >= 2; i--) {
    const prev = mapped[i], imp = mapped[i + 1];
    const bodyPrev = Math.abs(prev.close - prev.open);
    const bodyImp = Math.abs(imp.close - imp.open);
    if (prev.close > prev.open && imp.close < imp.open && bodyImp > Math.max(atr * 0.9, bodyPrev * 1.4)) {
      let broken = false;
      for (let j = i + 2; j < n; j++) { if (mapped[j].close > prev.high) { broken = true; break; } }
      if (!broken) { obs.push({ dir: 'BEAR', startIdx: i, top: prev.high, bot: prev.low }); break; }
    }
  }

  // 4. Auto-Fibonacci Retracement & 0.618 Golden Pocket
  const fibWinStart = Math.max(0, n - Math.min(120, n));
  let maxH = -Infinity, minL = Infinity, maxIdx = fibWinStart, minIdx = fibWinStart;
  for (let i = fibWinStart; i < n; i++) {
    if (mapped[i].high > maxH) { maxH = mapped[i].high; maxIdx = i; }
    if (mapped[i].low < minL) { minL = mapped[i].low; minIdx = i; }
  }
  let fib = null;
  if (maxH > minL) {
    const up = minIdx <= maxIdx;
    const rng = maxH - minL;
    const ratios = [0, 0.236, 0.382, 0.5, 0.618, 0.65, 0.786, 1.0];
    const levels = ratios.map(r => ({
      ratio: r,
      price: up ? (maxH - rng * r) : (minL + rng * r)
    }));
    fib = { up, maxH, minL, anchorIdx: Math.max(fibWinStart, Math.min(minIdx, maxIdx)), levels };
  }

  // 5. Visible-Range Volume Profile (VPVR) + POC / VAH / VAL
  const slice = mapped.slice(startIdx, endIdx + 1);
  let vpvr = null;
  if (slice.length >= 4) {
    const lo = Math.min(...slice.map(x => x.low));
    const hi = Math.max(...slice.map(x => x.high));
    const bins = 26;
    if (hi > lo) {
      const step = (hi - lo) / bins;
      const buckets = Array.from({ length: bins }, (_, idx) => ({
        idx,
        mid: lo + (idx + 0.5) * step,
        bot: lo + idx * step,
        top: lo + (idx + 1) * step,
        buyVol: 0,
        sellVol: 0,
        totVol: 0
      }));
      let totalVol = 0;
      for (const b of slice) {
        const typ = (b.high + b.low + b.close) / 3;
        const bIdx = Math.min(bins - 1, Math.max(0, Math.floor((typ - lo) / step)));
        const v = Math.max(0, b.vol || 0);
        if (b.close >= b.open) buckets[bIdx].buyVol += v;
        else buckets[bIdx].sellVol += v;
        buckets[bIdx].totVol += v;
        totalVol += v;
      }
      if (totalVol > 0) {
        let pocIdx = 0;
        for (let i = 1; i < bins; i++) {
          if (buckets[i].totVol > buckets[pocIdx].totVol) pocIdx = i;
        }
        // Value Area 70% expansion outward from POC
        let vaVol = buckets[pocIdx].totVol;
        let loI = pocIdx, hiI = pocIdx;
        while (vaVol < totalVol * 0.7 && (loI > 0 || hiI < bins - 1)) {
          const downV = loI > 0 ? buckets[loI - 1].totVol : -1;
          const upV = hiI < bins - 1 ? buckets[hiI + 1].totVol : -1;
          if (upV >= downV && hiI < bins - 1) { hiI++; vaVol += upV; }
          else if (loI > 0) { loI--; vaVol += downV; }
          else break;
        }
        vpvr = {
          buckets,
          maxBinVol: Math.max(...buckets.map(x => x.totVol), 1e-9),
          pocPrice: buckets[pocIdx].mid,
          vahPrice: buckets[hiI].top,
          valPrice: buckets[loI].bot
        };
      }
    }
  }

  return { bias, atr, swings: swings.slice(-14), breaks: recentBreaks, reg, trendlines, fvgs: fvgs.slice(-4), obs: obs.slice(0, 2), fib, vpvr };
}

/**
 * Attaches an HTML5 `<canvas>` overlay strictly aligned to LightweightCharts' timeScale & priceScale.
 */
export function attachTechnicalMasterCanvas({ wrap, chart, getSeries, getMapped, getLayers, getTradePlan }) {
  wrap.querySelectorAll('.tm-overlay-canvas').forEach(e => e.remove());
  const cvs = document.createElement('canvas');
  cvs.className = 'tm-overlay-canvas';
  cvs.style.cssText = 'position:absolute;left:0;top:0;width:100%;height:100%;pointer-events:none;z-index:2';
  wrap.appendChild(cvs);

  let rafPending = false;
  let lastSignals = null;

  const draw = () => {
    rafPending = false;
    const mainSeries = getSeries();
    const mapped = getMapped();
    if (!chart || !mainSeries || !mapped || mapped.length < 4) return;
    const w = wrap.clientWidth || 0;
    const hPx = wrap.clientHeight || 0;
    if (w < 40 || hPx < 40) return;

    const dpr = Math.min(2, window.devicePixelRatio || 1);
    if (cvs.width !== Math.floor(w * dpr) || cvs.height !== Math.floor(hPx * dpr)) {
      cvs.width = Math.floor(w * dpr);
      cvs.height = Math.floor(hPx * dpr);
    }
    const ctx2d = cvs.getContext('2d');
    if (!ctx2d) return;
    ctx2d.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx2d.clearRect(0, 0, w, hPx);

    // Clip to plot area excluding right price axis (~66px) & bottom time axis (~26px)
    const plotW = Math.max(40, w - 66);
    const plotH = Math.max(40, hPx - 26);

    const ts = chart.timeScale();
    const visRange = typeof ts.getVisibleLogicalRange === 'function' ? ts.getVisibleLogicalRange() : null;
    const visFrom = visRange ? Math.max(0, Math.floor(visRange.from)) : 0;
    const visTo = visRange ? Math.min(mapped.length - 1, Math.ceil(visRange.to)) : mapped.length - 1;
    const sig = computeTechnicalMasterSignals(mapped, visFrom, visTo);
    lastSignals = sig;
    const layers = getLayers ? getLayers() : { struct: true, trend: true, fvg: true, fib: true, vpvr: true };
    const plan = getTradePlan ? getTradePlan() : null;

    const xOfIdx = (idx) => {
      if (typeof ts.logicalToCoordinate === 'function') {
        const lx = ts.logicalToCoordinate(idx);
        if (lx != null && Number.isFinite(lx)) return lx;
      }
      const cIdx = Math.max(0, Math.min(mapped.length - 1, Math.round(idx)));
      const tx = ts.timeToCoordinate(mapped[cIdx].time);
      return (tx != null && Number.isFinite(tx)) ? tx : null;
    };
    const yOfPx = (p) => {
      if (p == null || !Number.isFinite(p)) return null;
      const py = mainSeries.priceToCoordinate(p);
      return (py != null && Number.isFinite(py)) ? py : null;
    };
    const placedPillBoxes = [];
    const drawPill = (text, x, y, bg, fg, border, allowCollision = false) => {
      ctx2d.font = 'bold 9.5px JetBrains Mono, monospace';
      const tw = ctx2d.measureText(text).width + 8;
      const px = Math.max(2, Math.min(plotW - tw - 2, x));
      const py = Math.max(10, Math.min(plotH - 6, y));
      const box = { l: px, r: px + tw + 2, t: py - 10, b: py + 5 };
      if (!allowCollision) {
        const collides = placedPillBoxes.some(b => !(box.r < b.l || box.l > b.r || box.b < b.t || box.t > b.b));
        if (collides) return;
      }
      placedPillBoxes.push(box);
      ctx2d.fillStyle = bg;
      ctx2d.fillRect(px, py - 9, tw, 13);
      if (border) {
        ctx2d.strokeStyle = border;
        ctx2d.lineWidth = 1;
        ctx2d.strokeRect(px, py - 9, tw, 13);
      }
      ctx2d.fillStyle = fg;
      ctx2d.fillText(text, px + 4, py + 1);
    };

    ctx2d.save();
    ctx2d.beginPath();
    ctx2d.rect(0, 0, plotW, plotH);
    ctx2d.clip();

    // A. VPVR Volume Profile + POC / VAH / VAL
    if (layers.vpvr && sig.vpvr) {
      const vp = sig.vpvr;
      const maxBarW = Math.max(28, plotW * 0.14);
      for (const bk of vp.buckets) {
        const yTop = yOfPx(bk.top), yBot = yOfPx(bk.bot);
        if (yTop == null || yBot == null) continue;
        const bh = Math.max(1.5, Math.abs(yBot - yTop) - 1);
        const y0 = Math.min(yTop, yBot);
        const totW = (bk.totVol / vp.maxBinVol) * maxBarW;
        if (totW < 1) continue;
        const buyFrac = bk.totVol > 0 ? (bk.buyVol / bk.totVol) : 0.5;
        const wBuy = totW * buyFrac;
        const wSell = totW - wBuy;
        ctx2d.fillStyle = 'rgba(0, 210, 106, 0.24)';
        ctx2d.fillRect(plotW - wBuy, y0, wBuy, bh);
        ctx2d.fillStyle = 'rgba(255, 176, 0, 0.22)';
        ctx2d.fillRect(plotW - totW, y0, wSell, bh);
      }
      const pocY = yOfPx(vp.pocPrice);
      if (pocY != null) {
        ctx2d.save();
        ctx2d.strokeStyle = 'rgba(255, 176, 0, 0.78)';
        ctx2d.lineWidth = 1.2;
        ctx2d.setLineDash([5, 4]);
        ctx2d.beginPath(); ctx2d.moveTo(0, pocY); ctx2d.lineTo(plotW, pocY); ctx2d.stroke();
        ctx2d.restore();
        drawPill(`POC ${fmtPx(vp.pocPrice)}`, plotW - 110, pocY - 2, 'rgba(32,20,0,0.88)', '#ffb000', '#ffb00066');
      }
      const vahY = yOfPx(vp.vahPrice), valY = yOfPx(vp.valPrice);
      for (const [yy, lbl] of [[vahY, 'VAH'], [valY, 'VAL']]) {
        if (yy == null) continue;
        ctx2d.save();
        ctx2d.strokeStyle = 'rgba(0, 229, 255, 0.30)';
        ctx2d.setLineDash([2, 4]);
        ctx2d.beginPath(); ctx2d.moveTo(plotW * 0.45, yy); ctx2d.lineTo(plotW, yy); ctx2d.stroke();
        ctx2d.restore();
        drawPill(lbl, plotW - 36, yy - 1, 'rgba(0,18,24,0.8)', '#00e5ff', '#00e5ff44');
      }
    }

    // B. FVG Fair Value Gaps & Supply/Demand Order Blocks
    if (layers.fvg) {
      const xRight = Math.min(plotW, (xOfIdx(mapped.length - 1) ?? plotW - 60) + 38);
      for (const fvg of sig.fvgs) {
        const x1 = xOfIdx(fvg.startIdx);
        const y1 = yOfPx(fvg.top), y2 = yOfPx(fvg.bot);
        if (x1 == null || y1 == null || y2 == null) continue;
        const left = Math.max(0, x1);
        const width = Math.max(12, xRight - left);
        const top = Math.min(y1, y2), ht = Math.max(4, Math.abs(y2 - y1));
        const bull = fvg.dir === 'BULL';
        ctx2d.fillStyle = bull ? 'rgba(0, 210, 106, 0.12)' : 'rgba(255, 59, 48, 0.12)';
        ctx2d.fillRect(left, top, width, ht);
        ctx2d.strokeStyle = bull ? 'rgba(0, 210, 106, 0.42)' : 'rgba(255, 59, 48, 0.42)';
        ctx2d.lineWidth = 1;
        ctx2d.strokeRect(left, top, width, ht);
        drawPill(bull ? 'FVG+ DEM' : 'FVG- SUP', left + 3, top + Math.min(11, ht / 2 + 4), 'rgba(0,0,0,0.72)', bull ? '#00d26a' : '#ff5a52');
      }
      for (const ob of sig.obs) {
        const x1 = xOfIdx(ob.startIdx);
        const y1 = yOfPx(ob.top), y2 = yOfPx(ob.bot);
        if (x1 == null || y1 == null || y2 == null) continue;
        const left = Math.max(0, x1);
        const width = Math.max(16, xRight - left);
        const top = Math.min(y1, y2), ht = Math.max(5, Math.abs(y2 - y1));
        const bull = ob.dir === 'BULL';
        ctx2d.save();
        ctx2d.fillStyle = bull ? 'rgba(0, 229, 255, 0.09)' : 'rgba(224, 64, 251, 0.09)';
        ctx2d.fillRect(left, top, width, ht);
        ctx2d.setLineDash([4, 3]);
        ctx2d.strokeStyle = bull ? 'rgba(0, 229, 255, 0.55)' : 'rgba(224, 64, 251, 0.55)';
        ctx2d.strokeRect(left, top, width, ht);
        ctx2d.restore();
        drawPill(bull ? 'OB DEMAND' : 'OB SUPPLY', left + 3, top + ht - 2, 'rgba(0,0,0,0.75)', bull ? '#00e5ff' : '#e040fb');
      }
    }

    // C. OLS Linear Regression Channel (+/- 1.5 sigma) & Structural Pivot Trendlines
    if (layers.trend) {
      if (sig.reg) {
        const r = sig.reg;
        const x1 = xOfIdx(r.startIdx), x2 = xOfIdx(r.endIdx);
        const y1Mid = yOfPx(r.yStart), y2Mid = yOfPx(r.yEnd);
        const y1Up = yOfPx(r.yStart + r.sigma15), y2Up = yOfPx(r.yEnd + r.sigma15);
        const y1Lo = yOfPx(r.yStart - r.sigma15), y2Lo = yOfPx(r.yEnd - r.sigma15);
        if (x1 != null && x2 != null && y1Up != null && y2Up != null && y1Lo != null && y2Lo != null) {
          ctx2d.fillStyle = 'rgba(0, 229, 255, 0.035)';
          ctx2d.beginPath();
          ctx2d.moveTo(x1, y1Up); ctx2d.lineTo(x2, y2Up); ctx2d.lineTo(x2, y2Lo); ctx2d.lineTo(x1, y1Lo);
          ctx2d.closePath(); ctx2d.fill();

          ctx2d.save();
          ctx2d.strokeStyle = 'rgba(0, 229, 255, 0.45)';
          ctx2d.lineWidth = 1.1;
          ctx2d.beginPath(); ctx2d.moveTo(x1, y1Up); ctx2d.lineTo(x2, y2Up); ctx2d.stroke();
          ctx2d.beginPath(); ctx2d.moveTo(x1, y1Lo); ctx2d.lineTo(x2, y2Lo); ctx2d.stroke();
          if (y1Mid != null && y2Mid != null) {
            ctx2d.strokeStyle = 'rgba(255, 176, 0, 0.45)';
            ctx2d.setLineDash([4, 4]);
            ctx2d.beginPath(); ctx2d.moveTo(x1, y1Mid); ctx2d.lineTo(x2, y2Mid); ctx2d.stroke();
          }
          ctx2d.restore();
        }
      }
      for (const tl of sig.trendlines) {
        const x1 = xOfIdx(tl.x1), x2 = xOfIdx(tl.x2);
        const y1 = yOfPx(tl.y1), y2 = yOfPx(tl.y2);
        if (x1 == null || x2 == null || y1 == null || y2 == null) continue;
        ctx2d.save();
        ctx2d.strokeStyle = tl.kind === 'SUP' ? 'rgba(0, 210, 106, 0.75)' : 'rgba(255, 59, 48, 0.75)';
        ctx2d.lineWidth = 1.6;
        ctx2d.beginPath(); ctx2d.moveTo(x1, y1); ctx2d.lineTo(x2, y2); ctx2d.stroke();
        ctx2d.restore();
      }
    }

    // D. Auto-Fibonacci Retracement + 0.618 Golden Pocket
    if (layers.fib && sig.fib) {
      const f = sig.fib;
      const xStart = Math.max(plotW * 0.48, xOfIdx(f.anchorIdx) ?? plotW * 0.55);
      const y618 = yOfPx(f.levels.find(l => l.ratio === 0.618)?.price);
      const y65 = yOfPx(f.levels.find(l => l.ratio === 0.65)?.price);
      if (y618 != null && y65 != null) {
        ctx2d.fillStyle = 'rgba(255, 176, 0, 0.10)';
        ctx2d.fillRect(xStart, Math.min(y618, y65), plotW - xStart, Math.max(3, Math.abs(y65 - y618)));
      }
      for (const lv of f.levels) {
        if (lv.ratio === 0.65) continue;
        const yy = yOfPx(lv.price);
        if (yy == null) continue;
        const isGolden = lv.ratio === 0.618;
        ctx2d.save();
        ctx2d.strokeStyle = isGolden ? 'rgba(255, 214, 0, 0.85)' : 'rgba(138, 160, 190, 0.42)';
        ctx2d.lineWidth = isGolden ? 1.4 : 1;
        ctx2d.setLineDash([3, 3]);
        ctx2d.beginPath(); ctx2d.moveTo(xStart, yy); ctx2d.lineTo(plotW, yy); ctx2d.stroke();
        ctx2d.restore();
        const tag = isGolden ? `0.618 GP • ${fmtPx(lv.price)}` : `${lv.ratio.toFixed(3)} • ${fmtPx(lv.price)}`;
        drawPill(tag, xStart + 4, yy - 2, 'rgba(6,8,12,0.82)', isGolden ? '#ffd600' : '#9eb3cc');
      }
    }

    // E. Market Structure Pivots (HH/HL/LH/LL) + BOS / CHoCH
    if (layers.struct) {
      for (const br of sig.breaks) {
        const x1 = xOfIdx(br.fromIdx), x2 = xOfIdx(br.toIdx), yy = yOfPx(br.price);
        if (x1 == null || x2 == null || yy == null) continue;
        const bull = br.dir === 'BULL';
        ctx2d.save();
        ctx2d.strokeStyle = bull ? '#00d26a' : '#ff3b30';
        ctx2d.lineWidth = br.kind === 'CHoCH' ? 1.6 : 1.1;
        ctx2d.setLineDash(br.kind === 'CHoCH' ? [] : [4, 3]);
        ctx2d.beginPath(); ctx2d.moveTo(x1, yy); ctx2d.lineTo(x2, yy); ctx2d.stroke();
        ctx2d.restore();
        drawPill(br.kind, (x1 + x2) / 2 - 14, yy - (bull ? 3 : -10), bull ? 'rgba(0,32,16,0.92)' : 'rgba(38,6,6,0.92)', bull ? '#00d26a' : '#ff5a52', bull ? '#00d26a66' : '#ff3b3066');
      }
      for (const sw of sig.swings) {
        const xx = xOfIdx(sw.idx), yy = yOfPx(sw.price);
        if (xx == null || yy == null || xx < 6 || xx > plotW - 14) continue;
        const isHigh = sw.type === 'H';
        const col = (sw.tag === 'HH' || sw.tag === 'HL') ? '#00d26a' : (sw.tag === 'LH' || sw.tag === 'LL') ? '#ff5a52' : '#ffb000';
        drawPill(sw.tag, xx - 10, isHigh ? yy - 5 : yy + 14, 'rgba(0,0,0,0.82)', col, col + '55');
      }
    }

    // F0. Ichimoku Kinko Hyo Cloud, SuperTrend(10,3), and Session PDH/PDL Liquidity Lines
    if (layers.ichimoku && mapped.length >= 26) {
      const ichi = calcIchimoku(mapped);
      const cloudPtsA = [], cloudPtsB = [];
      for (const pt of ichi) {
        if (pt.spanA == null || pt.spanB == null) continue;
        const x = xOfIdx(pt.idx), ya = yOfPx(pt.spanA), yb = yOfPx(pt.spanB);
        if (x == null || ya == null || yb == null) continue;
        cloudPtsA.push([x, ya, pt.spanA >= pt.spanB]);
        cloudPtsB.unshift([x, yb]);
      }
      if (cloudPtsA.length >= 2) {
        const lastBull = cloudPtsA[cloudPtsA.length - 1][2];
        ctx2d.save();
        ctx2d.fillStyle = lastBull ? 'rgba(0, 210, 106, 0.11)' : 'rgba(255, 59, 48, 0.11)';
        ctx2d.beginPath();
        cloudPtsA.forEach(([x, y], i) => { if (i === 0) ctx2d.moveTo(x, y); else ctx2d.lineTo(x, y); });
        cloudPtsB.forEach(([x, y]) => ctx2d.lineTo(x, y));
        ctx2d.closePath();
        ctx2d.fill();
        ctx2d.restore();
      }
      const drawIchiLine = (field, color, width = 1.2) => {
        ctx2d.save();
        ctx2d.strokeStyle = color;
        ctx2d.lineWidth = width;
        ctx2d.beginPath();
        let started = false;
        for (const pt of ichi) {
          if (pt[field] == null) continue;
          const x = xOfIdx(pt.idx), y = yOfPx(pt[field]);
          if (x == null || y == null) continue;
          if (!started) { ctx2d.moveTo(x, y); started = true; } else ctx2d.lineTo(x, y);
        }
        ctx2d.stroke();
        ctx2d.restore();
      };
      drawIchiLine('tenkan', '#00e5ff', 1.2);
      drawIchiLine('kijun', '#ff6600', 1.3);
      drawIchiLine('spanA', 'rgba(0,210,106,0.55)', 1.0);
      drawIchiLine('spanB', 'rgba(255,90,82,0.55)', 1.0);
    }

    if (layers.supertrend && mapped.length >= 14) {
      const stArr = calcSuperTrend(mapped, 10, 3.0);
      for (let i = 1; i < stArr.length; i++) {
        const p0 = stArr[i - 1], p1 = stArr[i];
        if (p0.dir !== p1.dir) continue;
        const x0 = xOfIdx(p0.idx), y0 = yOfPx(p0.line);
        const x1 = xOfIdx(p1.idx), y1 = yOfPx(p1.line);
        if (x0 == null || y0 == null || x1 == null || y1 == null) continue;
        ctx2d.save();
        ctx2d.strokeStyle = p1.dir === 1 ? '#00ff88' : '#ff453a';
        ctx2d.lineWidth = 1.8;
        ctx2d.beginPath(); ctx2d.moveTo(x0, y0); ctx2d.lineTo(x1, y1); ctx2d.stroke();
        ctx2d.restore();
      }
      for (const p of stArr) {
        if (!p.flipped) continue;
        const x = xOfIdx(p.idx), y = yOfPx(p.line);
        if (x == null || y == null || x < 10 || x > plotW - 30) continue;
        const bull = p.dir === 1;
        drawPill(bull ? 'ST BUY' : 'ST SELL', x - 16, bull ? y + 13 : y - 4, bull ? 'rgba(0,38,18,0.94)' : 'rgba(42,6,6,0.94)', bull ? '#00ff88' : '#ff5a52', bull ? '#00ff8888' : '#ff453a88');
      }
    }

    if (layers.pdhl && mapped.length >= 30) {
      const slice = mapped.slice(-48, -12);
      if (slice.length >= 10) {
        const pdh = Math.max(...slice.map(b => b.high));
        const pdl = Math.min(...slice.map(b => b.low));
        const xStart = Math.max(0, xOfIdx(mapped.length - 36) ?? plotW * 0.35);
        for (const [px, lbl, col] of [[pdh, 'PDH LIQ', '#ffb000'], [pdl, 'PDL LIQ', '#4da3ff']]) {
          const yy = yOfPx(px);
          if (yy == null) continue;
          ctx2d.save();
          ctx2d.strokeStyle = col;
          ctx2d.lineWidth = 1.1;
          ctx2d.setLineDash([6, 4]);
          ctx2d.beginPath(); ctx2d.moveTo(xStart, yy); ctx2d.lineTo(plotW, yy); ctx2d.stroke();
          ctx2d.restore();
          drawPill(`${lbl} ${fmtPx(px)}`, xStart + 6, yy - 2, 'rgba(8,10,14,0.88)', col, col + '66');
        }
      }
    }

    // F. Trade Plan Risk / Reward Boxes (used for LIVE Open Positions in GP/GIP & BOT <GO>)
    if (plan && plan.entry > 0) {
      const boxStart = Math.max(plotW * 0.58, (xOfIdx(mapped.length - 12) ?? plotW * 0.65));
      const boxW = Math.max(44, plotW - boxStart);
      const yEnt = yOfPx(plan.entry), ySl = plan.sl > 0 ? yOfPx(plan.sl) : null, yTp1 = plan.tp1 > 0 ? yOfPx(plan.tp1) : null;
      const yTp2 = plan.tp2 > 0 ? yOfPx(plan.tp2) : null;
      const yLiq = plan.liq > 0 ? yOfPx(plan.liq) : null;
      if (yEnt != null) {
        ctx2d.save();
        ctx2d.strokeStyle = '#ffb000';
        ctx2d.lineWidth = 1.4;
        ctx2d.beginPath(); ctx2d.moveTo(boxStart, yEnt); ctx2d.lineTo(plotW, yEnt); ctx2d.stroke();
        ctx2d.restore();
        drawPill(plan.entryLabel || `${plan.isOpen ? 'OPEN ' : ''}ENTRY ${plan.dir || ''} ${fmtPx(plan.entry)}`, boxStart + 4, yEnt - 3, 'rgba(32,20,0,0.92)', '#ffb000', '#ffb000', true);
      }
      if (yEnt != null && ySl != null) {
        ctx2d.fillStyle = 'rgba(255, 59, 48, 0.14)';
        ctx2d.fillRect(boxStart, Math.min(yEnt, ySl), boxW, Math.max(2, Math.abs(ySl - yEnt)));
        drawPill(plan.slLabel || `SL ${fmtPx(plan.sl)}`, boxStart + 4, ySl + (plan.sl < plan.entry ? 11 : -3), 'rgba(38,6,6,0.92)', '#ff5a52', '#ff3b30', true);
      }
      if (yEnt != null && yTp1 != null) {
        ctx2d.fillStyle = 'rgba(0, 229, 255, 0.12)';
        ctx2d.fillRect(boxStart, Math.min(yEnt, yTp1), boxW, Math.max(2, Math.abs(yTp1 - yEnt)));
        drawPill(plan.tp1Label || `TP1 ${fmtPx(plan.tp1)}`, boxStart + 4, yTp1 - 2, 'rgba(0,22,28,0.92)', '#00e5ff', '#00e5ff', true);
      }
      if (yTp1 != null && yTp2 != null && Math.abs(yTp2 - yTp1) > 4) {
        ctx2d.fillStyle = 'rgba(0, 210, 106, 0.11)';
        ctx2d.fillRect(boxStart, Math.min(yTp1, yTp2), boxW, Math.max(2, Math.abs(yTp2 - yTp1)));
        drawPill(plan.tp2Label || `TP2 ${fmtPx(plan.tp2)}`, boxStart + 4, yTp2 - 2, 'rgba(0,28,12,0.92)', '#00d26a', '#00d26a', true);
      }
      if (yLiq != null) {
        ctx2d.save();
        ctx2d.strokeStyle = 'rgba(224, 64, 251, 0.85)';
        ctx2d.lineWidth = 1.2;
        ctx2d.setLineDash([3, 3]);
        ctx2d.beginPath(); ctx2d.moveTo(boxStart, yLiq); ctx2d.lineTo(plotW, yLiq); ctx2d.stroke();
        ctx2d.restore();
        drawPill(`LIQ ${fmtPx(plan.liq)}`, boxStart + 4, yLiq - 2, 'rgba(34,6,38,0.92)', '#e040fb', '#e040fb', true);
      }
    }

    ctx2d.restore();
  };

  const scheduleDraw = () => {
    if (!rafPending) {
      rafPending = true;
      requestAnimationFrame(draw);
    }
  };

  try {
    chart.timeScale().subscribeVisibleLogicalRangeChange(scheduleDraw);
  } catch {}
  scheduleDraw();
  return { scheduleDraw, getLastSignals: () => lastSignals, canvas: cvs };
}

export function mountGP(body, ctx, { intraday = false } = {}) {
  body.classList.add('fill');
  let iv = intraday ? '1m' : '1h';
  let style = 'candle';
  let showSMA = true, showEMA = true, showBB = false, showVWAP = true, showVol = true, oscMode = 'RSI'; // 'RSI' | 'MACD' | 'NONE'
  let showStruct = true, showTrend = true, showFvg = true, showFib = false, showVpvr = true;
  let showIchimoku = false, showSupertrend = false, showPdhl = false;
  let unsubs = [];
  let secTimer = null;
  let lastTickTs = Date.now();
  let tickCount = 0;

  const intervals = intraday ? ['1s', '1m', '5m', '15m', '1h'] : ['1s', '1m', '5m', '15m', '1h', '4h', '1d', '1w'];
  const tb = h('div', { class: 'tb' });
  const statStrip = h('div', { class: 'tb', style: 'background:#060606;font-size:11px;gap:10px;border-bottom:1px solid #1e1e1e;padding:2px 6px' });
  const wrap = h('div', { class: 'chart', style: 'flex:1;min-height:140px;position:relative;background:#000' });
  const leg = h('div', { class: 'legend am', style: 'background:rgba(0,0,0,0.78);padding:2px 6px;border:1px solid #222;font-size:11px' });
  const rtBadge = h('div', { style: 'position:absolute;right:74px;top:6px;z-index:4;font-size:10px;color:#00d26a;background:rgba(0,18,8,0.88);padding:2px 6px;border:1px solid #00d26a66;pointer-events:none;font-family:JetBrains Mono,monospace' }, '● LIVE FEED');
  const volTag = h('div', { style: 'position:absolute;left:6px;bottom:22%;z-index:3;font-size:10px;color:#4da3ff;background:rgba(0,0,0,0.75);padding:1px 5px;pointer-events:none;border-left:2px solid #ffb000' });
  const oscStrip = h('div', { style: 'height:66px;border-top:1px solid var(--border);position:relative;flex:none;background:#030303' });
  wrap.append(leg, rtBadge, volTag);
  body.append(tb, statStrip, wrap, oscStrip);

  let chart = null, mainSeries = null, volSeries = null, volMaSeries = null, smaS = null, emaS = null, bbUpS = null, bbLoS = null, vwapS = null;
  let tmOverlay = null;
  let activeTradePlan = null;
  let lastCandles = [];
  let mappedBars = [];
  let activeBar = null;
  let effectiveFeedNote = '';

  function normPosPair(s) {
    const u = String(s || '').toUpperCase().replace(/\.P$/, '').replace('-USD', 'USDT');
    return u.endsWith('USDT') ? u : u + 'USDT';
  }

  function ivSeconds(intervalStr) {
    const map = { '1s': 1, '1m': 60, '5m': 300, '15m': 900, '1h': 3600, '4h': 14400, '1d': 86400, '1w': 604800 };
    return map[intervalStr] || 60;
  }

  function buildToolbar() {
    tb.textContent = '';
    tb.append(h('span', { class: 'lbl', text: intraday ? 'GIP INTRADAY:' : 'GP PERIOD:' }));
    for (const i of intervals) {
      tb.append(h('button', { class: i === iv ? 'on' : '', text: i.toUpperCase(), onclick: () => { iv = i; buildToolbar(); load(); } }));
    }
    tb.append(h('span', { class: 'lbl', text: 'CHART:' }));
    for (const [t, lbl] of [['candle', 'CANDLE'], ['heikin', 'HEIKIN'], ['bar', 'BAR'], ['line', 'LINE'], ['area', 'AREA']]) {
      tb.append(h('button', { class: t === style ? 'on' : '', text: lbl, onclick: () => { style = t; buildToolbar(); renderChart(lastCandles); } }));
    }
    tb.append(h('span', { class: 'lbl', text: 'OVERLAYS:' }));
    const stBtn = (lbl, on, toggle, repaintOnly = false) => h('button', {
      class: on ? 'on' : '',
      text: lbl,
      onclick: () => {
        toggle();
        buildToolbar();
        if (repaintOnly && tmOverlay) tmOverlay.scheduleDraw();
        else renderChart(lastCandles);
      }
    });
    tb.append(
      stBtn('VOL+MA20', showVol, () => { showVol = !showVol; }),
      stBtn('SMA20', showSMA, () => { showSMA = !showSMA; }),
      stBtn('EMA50', showEMA, () => { showEMA = !showEMA; }),
      stBtn('BB(20,2)', showBB, () => { showBB = !showBB; }),
      stBtn('VWAP', showVWAP, () => { showVWAP = !showVWAP; })
    );
    tb.append(h('span', { class: 'lbl', text: 'TECH MASTER:' }));
    tb.append(
      stBtn('STRUCT(BOS)', showStruct, () => { showStruct = !showStruct; }, true),
      stBtn('TREND/CH', showTrend, () => { showTrend = !showTrend; }, true),
      stBtn('FVG/OB', showFvg, () => { showFvg = !showFvg; }, true),
      stBtn('FIB 0.618', showFib, () => { showFib = !showFib; }, true),
      stBtn('VPVR(POC)', showVpvr, () => { showVpvr = !showVpvr; }, true),
      stBtn('ICHIMOKU', showIchimoku, () => { showIchimoku = !showIchimoku; }, true),
      stBtn('STREND', showSupertrend, () => { showSupertrend = !showSupertrend; }, true),
      stBtn('PDH/PDL', showPdhl, () => { showPdhl = !showPdhl; }, true)
    );
    tb.append(h('span', { class: 'lbl', text: 'LOWER:' }));
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

    // 2x Retina HiDPI Institutional Tear-Sheet PNG Exporter + Save to Archive (G <GO>)
    const snapBtn = h('button', {
      style: 'border-color:#00e5ff;color:#00e5ff;font-weight:700',
      text: 'SNAP PNG (HD)',
      title: 'Export 2x Retina Institutional Chart Tear-Sheet (with Overlays + RSI/MACD + Stats) as PNG',
      onclick: () => {
        try {
          const SCALE = 2;
          const rect = wrap.getBoundingClientRect();
          const W = Math.max(760, Math.round(rect.width || 960));
          const H = Math.max(340, Math.round(rect.height || 440));
          const hdrH = 48;
          const oscH = oscMode !== 'NONE' && lastCandles.length >= 20 ? 74 : 0;
          const ftrH = 28;
          const totalH = hdrH + H + oscH + ftrH;

          const out = document.createElement('canvas');
          out.width = W * SCALE;
          out.height = totalH * SCALE;
          const g = out.getContext('2d');
          g.scale(SCALE, SCALE);

          g.fillStyle = '#040608';
          g.fillRect(0, 0, W, totalH);

          // 1. Institutional Bloomberg Header Bar
          g.fillStyle = '#0c1017';
          g.fillRect(0, 0, W, hdrH);
          g.fillStyle = '#ff6600';
          g.fillRect(0, hdrH - 2, W, 2);
          g.fillStyle = '#ff6600';
          g.fillRect(10, 9, 20, 20);
          g.fillStyle = '#000';
          g.font = 'bold 14px Consolas, monospace';
          g.fillText('B', 15, 24);

          const lastC = lastCandles.length ? lastCandles[lastCandles.length - 1] : null;
          const firstC = lastCandles.length ? lastCandles[0] : null;
          const chgPct = (firstC && lastC && firstC.c > 0) ? ((lastC.c - firstC.c) / firstC.c) * 100 : 0;
          const tmSig = mappedBars.length >= 6 ? computeTechnicalMasterSignals(mappedBars) : { bias: 'NEUTRAL', vpvr: null };

          g.fillStyle = '#ffffff';
          g.font = 'bold 13px Consolas, monospace';
          g.fillText(`BLOOMBERG TERMINAL // ${ctx.symbol} [${iv.toUpperCase()} • ${style.toUpperCase()}]`, 38, 19);

          g.font = '11px Consolas, monospace';
          g.fillStyle = '#ffb000';
          const pxTxt = lastC ? `O:${fmtPx(lastC.o)}  H:${fmtPx(lastC.h)}  L:${fmtPx(lastC.l)}  C:${fmtPx(lastC.c)} (${fmtPct(chgPct)})` : '';
          g.fillText(`${pxTxt}   |   STRUCT: ${tmSig.bias}${tmSig.vpvr ? '   |   POC: ' + fmtPx(tmSig.vpvr.pocPrice) : ''}`, 38, 37);

          g.fillStyle = '#9aa7b8';
          const tsStr = new Date().toISOString().replace('T', ' ').slice(0, 19) + ' UTC';
          g.fillText(tsStr, Math.max(10, W - g.measureText(tsStr).width - 12), 19);

          // 2. Composite all chart canvases + Technical Master HiDPI overlay
          const canvases = wrap.querySelectorAll('canvas');
          canvases.forEach(cv => {
            try {
              const cr = cv.getBoundingClientRect();
              const dx = Math.round(cr.left - rect.left);
              const dy = Math.round(cr.top - rect.top) + hdrH;
              if (cv.width > 0 && cv.height > 0 && cr.width > 0 && cr.height > 0) {
                g.drawImage(cv, dx, dy, Math.round(cr.width), Math.round(cr.height));
              }
            } catch {}
          });

          // 3. Render RSI(14) or MACD(12,26,9) Lower Pane directly at 2x resolution
          if (oscH > 0) {
            const oy = hdrH + H;
            g.fillStyle = '#06080c';
            g.fillRect(0, oy, W, oscH);
            g.strokeStyle = '#222834';
            g.lineWidth = 1;
            g.beginPath(); g.moveTo(0, oy); g.lineTo(W, oy); g.stroke();

            if (oscMode === 'RSI') {
              const pts = calcRSI(lastCandles, 14);
              if (pts.length >= 2) {
                const yOfR = v => oy + oscH - 8 - (Math.max(0, Math.min(100, v)) / 100) * (oscH - 18);
                g.strokeStyle = 'rgba(255,90,82,0.35)'; g.setLineDash([3, 3]);
                g.beginPath(); g.moveTo(0, yOfR(70)); g.lineTo(W, yOfR(70)); g.stroke();
                g.strokeStyle = 'rgba(0,210,106,0.35)';
                g.beginPath(); g.moveTo(0, yOfR(30)); g.lineTo(W, yOfR(30)); g.stroke();
                g.setLineDash([]);
                const lastR = pts[pts.length - 1].value;
                g.strokeStyle = lastR >= 70 ? '#ff453a' : lastR <= 30 ? '#00d26a' : '#ffb000';
                g.lineWidth = 1.6;
                g.beginPath();
                pts.forEach((p, i) => {
                  const x = 8 + (i / (pts.length - 1)) * (W - 64);
                  const y = yOfR(p.value);
                  if (i === 0) g.moveTo(x, y); else g.lineTo(x, y);
                });
                g.stroke();
                g.fillStyle = '#ffb000';
                g.font = 'bold 10.5px Consolas, monospace';
                g.fillText(`RSI(14): ${lastR.toFixed(2)}`, 10, oy + 13);
              }
            } else if (oscMode === 'MACD') {
              const mPts = calcMACD(lastCandles, 12, 26, 9);
              if (mPts.length >= 2) {
                const maxA = Math.max(...mPts.flatMap(x => [Math.abs(x.macd), Math.abs(x.signal), Math.abs(x.hist)]), 1e-5);
                const midY = oy + oscH / 2 + 4;
                const yOfM = v => midY - (v / maxA) * (oscH * 0.36);
                const bw = Math.max(1.5, (W - 72) / mPts.length);
                mPts.forEach((p, i) => {
                  const x = 8 + (i / (mPts.length - 1)) * (W - 72);
                  const y = yOfM(p.hist);
                  g.fillStyle = p.hist >= 0 ? 'rgba(0,210,106,0.55)' : 'rgba(255,59,48,0.55)';
                  g.fillRect(x - bw / 2, Math.min(midY, y), bw, Math.max(1, Math.abs(midY - y)));
                });
                const drawMLine = (key, col) => {
                  g.strokeStyle = col; g.lineWidth = 1.4; g.beginPath();
                  mPts.forEach((p, i) => {
                    const x = 8 + (i / (mPts.length - 1)) * (W - 72);
                    if (i === 0) g.moveTo(x, yOfM(p[key])); else g.lineTo(x, yOfM(p[key]));
                  });
                  g.stroke();
                };
                drawMLine('macd', '#ffb000');
                drawMLine('signal', '#4da3ff');
                const lm = mPts[mPts.length - 1];
                g.fillStyle = '#ffb000';
                g.font = 'bold 10.5px Consolas, monospace';
                g.fillText(`MACD(12,26,9): ${lm.macd.toFixed(3)}  SIG: ${lm.signal.toFixed(3)}  HIST: ${lm.hist >= 0 ? '+' : ''}${lm.hist.toFixed(3)}`, 10, oy + 13);
              }
            }
          }

          // 4. Institutional Tear-Sheet Footer
          const fy = hdrH + H + oscH;
          g.fillStyle = '#0a0d13';
          g.fillRect(0, fy, W, ftrH);
          g.strokeStyle = '#1f2633';
          g.beginPath(); g.moveTo(0, fy); g.lineTo(W, fy); g.stroke();
          g.fillStyle = '#7c8799';
          g.font = '10px Consolas, monospace';
          const studies = [
            showSMA ? 'SMA20' : '', showEMA ? 'EMA50' : '', showBB ? 'BB(20,2)' : '', showVWAP ? 'VWAP' : '',
            showStruct ? 'BOS/CHoCH' : '', showFvg ? 'FVG/OB' : '', showVpvr ? 'VPVR' : '',
            showIchimoku ? 'ICHIMOKU' : '', showSupertrend ? 'SUPERTREND' : '', showPdhl ? 'PDH/PDL' : ''
          ].filter(Boolean).join(' • ');
          g.fillText(`STUDIES: ${studies || 'PRICE ACTION'}`, 10, fy + 17);
          const posInfo = activeTradePlan && activeTradePlan.entry > 0
            ? `ACTIVE ${activeTradePlan.dir} ${activeTradePlan.lev}x @ ${fmtPx(activeTradePlan.entry)} (ROE ${activeTradePlan.pnlPct >= 0 ? '+' : ''}${Number(activeTradePlan.pnlPct).toFixed(2)}%)`
            : 'BLOOMBERG TERMINAL // QUANTITATIVE CHARTING DESK';
          g.fillStyle = '#ffb000';
          g.fillText(posInfo, Math.max(10, W - g.measureText(posInfo).width - 12), fy + 17);

          const dataUrl = out.toDataURL('image/png');
          try {
            const key = 'bbg_chart_snapshots_v1';
            const prev = JSON.parse(localStorage.getItem(key) || '[]');
            const arr = Array.isArray(prev) ? prev : [];
            arr.unshift({
              id: 'SNAP-' + Date.now(),
              symbol: ctx.symbol,
              interval: iv.toUpperCase(),
              ts: Date.now(),
              price: lastC ? lastC.c : 0,
              note: activeTradePlan ? `OPEN ${activeTradePlan.dir} ${activeTradePlan.lev}x` : '2X RETINA TEAR-SHEET',
              dataUrl,
              img: dataUrl
            });
            localStorage.setItem(key, JSON.stringify(arr.slice(0, 10)));
          } catch {}

          const a = document.createElement('a');
          a.href = dataUrl;
          a.download = `Bloomberg_Terminal_${ctx.symbol.replace(/[^A-Z0-9_-]/gi, '_')}_${iv.toUpperCase()}_HD_${Date.now()}.png`;
          a.click();
          snapBtn.textContent = 'SAVED HD PNG';
          setTimeout(() => { snapBtn.textContent = 'SNAP PNG (HD)'; }, 1800);
        } catch (err) {
          alert('Snapshot error: ' + err.message);
        }
      }
    });
    tb.append(
      snapBtn,
      h('button', { style: 'border-color:#00d26a;color:#00d26a;font-weight:700', text: 'SHARE ROE', title: 'Open Institutional ROE Card Studio (ROE <GO>)', onclick: () => ctx.run(`${ctx.symbol} ROE`) }),
      h('button', { style: 'border-color:#ff6600;color:#ff6600', text: 'MTF SCAN', title: 'Multi-Timeframe Technical Matrix (TECH <GO>)', onclick: () => ctx.run(`${ctx.symbol} TECH`) }),
      h('button', { style: 'border-color:#ffb000;color:#ffb000', text: 'X-RAY', title: 'Inspect Transparent Execution Factors (FACT <GO>)', onclick: () => ctx.run(`${ctx.symbol} FACT`) }),
      h('button', { style: 'border-color:#4da3ff;color:#4da3ff', text: 'ARCHIVE', title: 'Open Multi-Chart Studio & PNG Archive (G <GO>)', onclick: () => ctx.run(`${ctx.symbol} G`) })
    );
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
    if (chart) { try { chart.remove(); } catch {} chart = null; }
    wrap.querySelectorAll('.tv-lightweight-charts, .na, .tm-overlay-canvas').forEach(e => e.remove());
    tmOverlay = null;
    if (!candles || !candles.length) {
      leg.style.display = 'none';
      volTag.style.display = 'none';
      rtBadge.textContent = '● FEED N/A';
      rtBadge.style.color = '#ff5a52';
      rtBadge.style.borderColor = '#ff3b3066';
      wrap.append(h('div', { class: 'na', text: `No historical OHLCV data available for ${ctx.symbol} (${iv.toUpperCase()})` }));
      return;
    }
    leg.style.display = 'block';
    rtBadge.style.color = '#00d26a';
    rtBadge.style.borderColor = '#00d26a66';

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
      timeScale: { borderColor: '#333333', timeVisible: true, secondsVisible: iv === '1s' || iv === '1m' },
    });

    const mapped = dedupeByTime(candles.map(c => ({
      time: Math.floor(c.t / 1000), open: +c.o, high: +c.h, low: +c.l, close: +c.c, value: +c.c, vol: +(c.v || 0)
    })));
    mappedBars = mapped;
    const volByTime = new Map(mapped.map(x => [x.time, x.vol]));
    activeBar = mapped.length ? { ...mapped[mapped.length - 1] } : null;

    const seriesData = style === 'heikin' ? calcHeikinAshi(mapped) : mapped;

    if (style === 'candle' || style === 'heikin') {
      mainSeries = chart.addCandlestickSeries({
        upColor: style === 'heikin' ? '#00ff88' : '#00d26a',
        downColor: '#ff3b30',
        borderUpColor: style === 'heikin' ? '#00ff88' : '#00d26a',
        borderDownColor: '#ff3b30',
        wickUpColor: style === 'heikin' ? '#00ff88' : '#00d26a',
        wickDownColor: '#ff3b30',
        priceLineVisible: true, lastValueVisible: true
      });
      mainSeries.setData(seriesData);
    } else if (style === 'bar' && typeof chart.addBarSeries === 'function') {
      mainSeries = chart.addBarSeries({
        upColor: '#00d26a', downColor: '#ff3b30',
        thinBars: false, priceLineVisible: true, lastValueVisible: true
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

    const tmSummary = computeTechnicalMasterSignals(mapped);
    const fib618Val = tmSummary.fib ? tmSummary.fib.levels.find(l => l.ratio === 0.618)?.price : null;
    const pocVal = tmSummary.vpvr ? tmSummary.vpvr.pocPrice : null;

    const updateLegend = (bar, barVol) => {
      if (!bar) return;
      const o = bar.open ?? bar.value, hi = bar.high ?? bar.value, lo = bar.low ?? bar.value, cl = bar.close ?? bar.value;
      const v = barVol != null ? barVol : (volByTime.get(bar.time) ?? 0);
      const chg = o ? cl - o : 0;
      const chgPct = o ? ((cl - o) / o) * 100 : 0;
      const ivSec = ivSeconds(iv);
      const nowS = Math.floor(Date.now() / 1000);
      const remSec = ivSec <= 1 ? 1 : Math.max(0, ivSec - (nowS % ivSec));
      const remFmt = ivSec <= 1 ? '1S REALTIME' : `${String(Math.floor(remSec / 60)).padStart(2, '0')}:${String(remSec % 60).padStart(2, '0')}s`;
      const feedLbl = effectiveFeedNote ? `${iv.toUpperCase()} (${effectiveFeedNote})` : iv.toUpperCase();
      leg.innerHTML = `<b style="color:#fff">${ctx.symbol}</b> [${feedLbl}]  O:<b style="color:#ffb000">${fmtPx(o)}</b>  H:<b style="color:#00d26a">${fmtPx(hi)}</b>  L:<b style="color:#ff3b30">${fmtPx(lo)}</b>  C:<b style="color:#ffb000">${fmtPx(cl)}</b> (<span class="${dirCls(chgPct)}">${fmtPct(chgPct)}</span>)  VOL:<b style="color:#00e5ff">${fmtVol(v)}</b>  <span style="color:#00d26a">⏱ ${remFmt}</span>`;

      const biasCol = tmSummary.bias === 'BULLISH' ? '#00d26a' : tmSummary.bias === 'BEARISH' ? '#ff3b30' : '#ffb000';
      const stripItems = [];
      if (activeTradePlan && activeTradePlan.entry > 0) {
        const pnlCl = activeTradePlan.pnlPct >= 0 ? '#00d26a' : '#ff3b30';
        stripItems.push(
          h('span', {
            style: `color:${pnlCl};font-weight:bold;border:1px solid ${pnlCl}66;padding:0 5px;background:rgba(12,8,4,0.9)`,
            text: `● OPEN ${activeTradePlan.dir} ${activeTradePlan.lev}x | ENT:${fmtPx(activeTradePlan.entry)} | P&L:${activeTradePlan.pnlPct >= 0 ? '+' : ''}${Number(activeTradePlan.pnlPct).toFixed(2)}% ($${Number(activeTradePlan.pnlUsd).toFixed(2)}) | SL:${activeTradePlan.slState}`
          })
        );
      }
      stripItems.push(
        h('span', { class: 'sym am', text: `LAST: ${fmtPx(cl)}` }),
        h('span', { class: dirCls(chg), text: `CHG: ${fmtChg(chg)} (${fmtPct(chgPct)})` }),
        h('span', { style: `color:${biasCol};font-weight:bold`, text: `STRUCT: ${tmSummary.bias}` }),
        pocVal != null ? h('span', { style: 'color:#ffb000;font-weight:bold', text: `POC: ${fmtPx(pocVal)}` }) : null,
        h('span', { style: 'color:#00e5ff', text: `FVGs: ${tmSummary.fvgs.length}` }),
        fib618Val != null ? h('span', { style: 'color:#ffd600', text: `GP 0.618: ${fmtPx(fib618Val)}` }) : null,
        h('span', { style: 'color:#00d26a', text: `NEXT: ${remFmt} • TICKS:${tickCount}` }),
        lastVwapVal != null ? h('span', { style: 'color:#ffd600', text: `VWAP: ${fmtPx(lastVwapVal)}` }) : null,
        lastSmaVal != null ? h('span', { style: 'color:#4da3ff', text: `SMA20: ${fmtPx(lastSmaVal)}` }) : null,
        lastEmaVal != null ? h('span', { style: 'color:#e040fb', text: `EMA50: ${fmtPx(lastEmaVal)}` }) : null
      );
      statStrip.innerHTML = '';
      statStrip.append(...stripItems.filter(Boolean));
    };

    const latestBar = mapped[mapped.length - 1];
    updateLegend(latestBar, latestBar.vol);

    chart.subscribeCrosshairMove(param => {
      if (!param || !param.time) return updateLegend(activeBar || latestBar, (activeBar || latestBar).vol);
      const b = param.seriesData.get(mainSeries);
      const vBar = volSeries ? param.seriesData.get(volSeries) : null;
      if (b) updateLegend(b, vBar ? vBar.value : volByTime.get(param.time));
    });
    if (activeTradePlan && activeTradePlan.entry > 0 && typeof mainSeries.createPriceLine === 'function') {
      mainSeries.createPriceLine({ price: activeTradePlan.entry, color: '#ffb000', lineWidth: 2, lineStyle: 0, axisLabelVisible: true, title: '' });
      if (activeTradePlan.sl > 0) mainSeries.createPriceLine({ price: activeTradePlan.sl, color: '#ff3b30', lineWidth: 2, lineStyle: 2, axisLabelVisible: true, title: '' });
      if (activeTradePlan.tp1 > 0) mainSeries.createPriceLine({ price: activeTradePlan.tp1, color: '#00e5ff', lineWidth: 1.5, lineStyle: 2, axisLabelVisible: true, title: '' });
      if (activeTradePlan.tp2 > 0) mainSeries.createPriceLine({ price: activeTradePlan.tp2, color: '#00d26a', lineWidth: 2, lineStyle: 0, axisLabelVisible: true, title: '' });
      if (activeTradePlan.liq > 0) mainSeries.createPriceLine({ price: activeTradePlan.liq, color: '#e040fb', lineWidth: 1.5, lineStyle: 3, axisLabelVisible: true, title: '' });
    }
    chart.timeScale().fitContent();
    tmOverlay = attachTechnicalMasterCanvas({
      wrap,
      chart,
      getSeries: () => mainSeries,
      getMapped: () => mappedBars,
      getLayers: () => ({ struct: showStruct, trend: showTrend, fvg: showFvg, fib: showFib, vpvr: showVpvr, ichimoku: showIchimoku, supertrend: showSupertrend, pdhl: showPdhl }),
      getTradePlan: () => activeTradePlan
    });
    renderOscillator(candles);
  }

  function applyLiveTick(px, qty = 0) {
    const price = Number(px);
    if (!mainSeries || !Number.isFinite(price) || price <= 0) return;
    lastTickTs = Date.now();
    tickCount++;
    const ivSec = ivSeconds(iv);
    const nowSec = Math.floor(lastTickTs / 1000);
    const bucketSec = ivSec <= 1 ? nowSec : Math.floor(nowSec / ivSec) * ivSec;
    if (!activeBar || bucketSec > activeBar.time) {
      const prevClose = activeBar ? activeBar.close : price;
      activeBar = {
        time: bucketSec,
        open: prevClose,
        high: Math.max(prevClose, price),
        low: Math.min(prevClose, price),
        close: price,
        vol: Math.max(0, Number(qty) || 0)
      };
      lastCandles.push({ t: bucketSec * 1000, o: activeBar.open, h: activeBar.high, l: activeBar.low, c: activeBar.close, v: activeBar.vol });
      mappedBars.push({ ...activeBar, value: activeBar.close });
      if (lastCandles.length > 360) lastCandles.shift();
      if (mappedBars.length > 360) mappedBars.shift();
    } else {
      activeBar.close = price;
      if (price > activeBar.high) activeBar.high = price;
      if (price < activeBar.low) activeBar.low = price;
      activeBar.vol = (activeBar.vol || 0) + (Number(qty) || 0);
      if (lastCandles.length) {
        const lc = lastCandles[lastCandles.length - 1];
        lc.c = activeBar.close;
        lc.h = activeBar.high;
        lc.l = activeBar.low;
        lc.v = activeBar.vol;
      }
      if (mappedBars.length) {
        const mb = mappedBars[mappedBars.length - 1];
        mb.close = activeBar.close;
        mb.value = activeBar.close;
        mb.high = activeBar.high;
        mb.low = activeBar.low;
        mb.vol = activeBar.vol;
      }
    }
    try {
      if (style === 'candle') mainSeries.update({ time: activeBar.time, open: activeBar.open, high: activeBar.high, low: activeBar.low, close: activeBar.close });
      else mainSeries.update({ time: activeBar.time, value: activeBar.close });
      if (volSeries) volSeries.update({ time: activeBar.time, value: activeBar.vol || 0, color: activeBar.close >= activeBar.open ? 'rgba(0, 210, 106, 0.70)' : 'rgba(255, 59, 48, 0.70)' });
    } catch {}
    tmOverlay?.scheduleDraw();
    const ivSecNow = ivSeconds(iv);
    const remSec = ivSecNow <= 1 ? 1 : Math.max(0, ivSecNow - (nowSec % ivSecNow));
    const remFmt = ivSecNow <= 1 ? '1S REALTIME' : `${String(Math.floor(remSec / 60)).padStart(2, '0')}:${String(remSec % 60).padStart(2, '0')}s`;
    rtBadge.textContent = `● REALTIME TICK (${new Date(lastTickTs).toLocaleTimeString('en-GB')}) | NEXT: ${remFmt}`;
    leg.innerHTML = `<b style="color:#fff">${ctx.symbol}</b> [${iv.toUpperCase()} LIVE]  O:<b>${fmtPx(activeBar.open)}</b>  H:<b style="color:#00d26a">${fmtPx(activeBar.high)}</b>  L:<b style="color:#ff3b30">${fmtPx(activeBar.low)}</b>  C:<b style="color:#ffb000">${fmtPx(activeBar.close)}</b>  VOL:<b style="color:#00e5ff">${fmtVol(activeBar.vol || 0)}</b>  <span style="color:#00d26a">⏱ ${remFmt}</span>`;
  }

  function clearSubs() {
    unsubs.forEach(u => { try { u(); } catch {} });
    unsubs = [];
    if (secTimer) { clearInterval(secTimer); secTimer = null; }
  }

  const ro = new ResizeObserver(() => {
    if (chart && wrap.clientWidth > 0 && wrap.clientHeight > 0) {
      chart.applyOptions({ width: wrap.clientWidth, height: wrap.clientHeight });
      tmOverlay?.scheduleDraw();
    }
  });
  ro.observe(wrap);
  ctx.cleanup(() => { ro.disconnect(); clearSubs(); if (chart) try { chart.remove(); } catch {} });

  function paintOpenPosStrip() {
    if (!activeTradePlan || activeTradePlan.entry <= 0) return;
    const pnlCl = activeTradePlan.pnlPct >= 0 ? '#00d26a' : '#ff3b30';
    const existing = statStrip.querySelector('[data-open-pos-pill]');
    const txt = `● OPEN ${activeTradePlan.dir} ${activeTradePlan.lev}x | ENT:${fmtPx(activeTradePlan.entry)} | P&L:${activeTradePlan.pnlPct >= 0 ? '+' : ''}${Number(activeTradePlan.pnlPct).toFixed(2)}% ($${Number(activeTradePlan.pnlUsd).toFixed(2)}) | SL:${activeTradePlan.slState}`;
    if (existing) {
      existing.textContent = txt;
      existing.style.color = pnlCl;
      return;
    }
    statStrip.prepend(
      h('span', {
        'data-open-pos-pill': '1',
        style: `color:${pnlCl};font-weight:bold;border:1px solid ${pnlCl}66;padding:0 5px;background:rgba(12,8,4,0.9)`,
        text: txt
      })
    );
  }

  async function load() {
    clearSubs();
    effectiveFeedNote = '';
    leg.textContent = `Loading ${ctx.symbol} (${iv})...`;
    const posPromise = getRaw('/api/crypto-futures/positions').catch(() => ({ ok: false })).then(posEnv => {
      const targetPair = normPosPair(ctx.symbol);
      const posList = (posEnv && posEnv.ok && Array.isArray(posEnv.data)) ? posEnv.data : [];
      const matchedPos = posList.find(p => p && (p.status === 'OPEN' || !p.status) && normPosPair(p.binance_pair || p.symbol) === targetPair);
      if (matchedPos && Number(matchedPos.entry_price || 0) > 0) {
        const ePx = Number(matchedPos.entry_price);
        const dirP = String(matchedPos.direction || 'LONG').toUpperCase();
        const sgn = dirP === 'SHORT' ? -1 : 1;
        const slPx = Number(matchedPos.stop_loss || 0);
        const rDist = slPx > 0 ? Math.abs(ePx - slPx) : ePx * 0.015;
        let tp1Px = Number(matchedPos.take_profit_1 || 0);
        let tp2Px = Number(matchedPos.take_profit_2 || matchedPos.take_profit || 0);
        if (tp1Px <= 0) tp1Px = ePx + sgn * 0.55 * rDist;
        if (tp2Px <= 0 || Math.abs(tp2Px - tp1Px) < ePx * 0.001) tp2Px = ePx + sgn * Math.max(2.0 * rDist, Math.abs(tp1Px - ePx) * 1.8);
        activeTradePlan = {
          isOpen: true,
          dir: dirP,
          lev: Number(matchedPos.leverage || 20),
          entry: ePx,
          sl: slPx,
          tp1: tp1Px,
          tp2: tp2Px,
          liq: Number(matchedPos.liquidation_price || 0),
          pnlPct: Number(matchedPos.pnl_pct || 0),
          pnlUsd: Number(matchedPos.pnl_usd || 0),
          slState: matchedPos.sl_state || 'MONITORED'
        };
        paintOpenPosStrip();
      } else {
        activeTradePlan = null;
      }
      return posEnv;
    });
    let [env] = await Promise.all([
      get('kline', { symbol: ctx.symbol, interval: iv, limit: iv === '1s' ? 180 : 300 }, 3000),
      posPromise
    ]);
    let srcCandles = (env.ok && env.data && Array.isArray(env.data.candles) && env.data.candles.length) ? env.data.candles : null;

    if (!srcCandles && iv === '1s') {
      // Non-Binance instruments (equities/FX) only expose >= 1m OHLCV upstream
      const mEnv = await get('kline', { symbol: ctx.symbol, interval: '1m', limit: 120 }, 3000);
      if (mEnv.ok && mEnv.data && Array.isArray(mEnv.data.candles) && mEnv.data.candles.length) {
        env = mEnv;
        srcCandles = mEnv.data.candles;
        effectiveFeedNote = '1M EXCHANGE BAR + LIVE TICK';
      }
    }

    ctx.status(env.ok ? env : { source: env.source || 'offline', ts: Date.now(), mode: srcCandles ? 'LIVE' : 'DOWN' });
    lastCandles = srcCandles || [];
    paintOpenPosStrip();
    requestAnimationFrame(() => renderChart(lastCandles));

    if (!lastCandles.length) return;

    if (iv !== '1s') {
      unsubs.push(ctx.sub(`kline:${ctx.symbol}:${iv}`, k => {
        if (!k || !mainSeries) return;
        const t = Math.floor(k.t / 1000);
        activeBar = { time: t, open: +k.o, high: +k.h, low: +k.l, close: +k.c, vol: +(k.v || 0) };
        try {
          if (style === 'candle') mainSeries.update(activeBar);
          else mainSeries.update({ time: t, value: +k.c });
          if (volSeries) volSeries.update({ time: t, value: +(k.v || 0), color: +k.c >= +k.o ? 'rgba(0, 210, 106, 0.70)' : 'rgba(255, 59, 48, 0.70)' });
        } catch {}
        tmOverlay?.scheduleDraw();
      }));
    }

    // Sub-second trade stream + quote ticker stream for instant candle responsiveness
    unsubs.push(ctx.sub(`trades:${ctx.symbol}`, tr => {
      if (tr && tr.price) applyLiveTick(+tr.price, +(tr.qty || tr.size || 0));
    }));
    unsubs.push(ctx.sub(`ticker:${ctx.symbol}`, tk => {
      if (tk && tk.price) applyLiveTick(+tk.price, 0);
    }));

    // Real-time countdown & status badge (no synthetic price jitter!)
    secTimer = setInterval(() => {
      if (!activeBar || !mainSeries) return;
      const nowSec = Math.floor(Date.now() / 1000);
      const ivSec = ivSeconds(iv);
      const remSec = ivSec <= 1 ? 1 : Math.max(0, ivSec - (nowSec % ivSec));
      const remFmt = ivSec <= 1 ? '1S REALTIME' : `${String(Math.floor(remSec / 60)).padStart(2, '0')}:${String(remSec % 60).padStart(2, '0')}s`;
      rtBadge.textContent = `● LIVE FEED (${new Date(lastTickTs).toLocaleTimeString('en-GB')}) | NEXT: ${remFmt}`;
    }, 1000);
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
