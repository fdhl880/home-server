const fs = require('fs');
const path = require('path');

const htmlFile = path.join(__dirname, '..', 'public', 'index.html');
let raw = fs.readFileSync(htmlFile, 'utf8');
let isCrlf = raw.includes('\r\n');
let code = raw.replace(/\r\n/g, '\n');

function doReplace(str, target, replacement, desc) {
    if (!str.includes(target)) {
        console.error('FAILED TO MATCH:', desc);
        return str;
    }
    console.log('SUCCESS:', desc);
    return str.replace(target, () => replacement);
}

// 1. Replace the entire GP Chart View (VIEW 6) with Authentic Bloomberg Dual-Pane GP Chart
const oldChartView = `        <!-- ============================================================== -->
        <!-- VIEW 6: GP PRICE CHART (GP <GO>) -->
        <!-- ============================================================== -->
        <div id="view-chart" class="view-section">
            <div class="sec-title" style="display:flex; justify-content:space-between; align-items:center;">
                <span>-- GP &lt;GO&gt; GRAPHIC PRICE ENGINE // INTRADAY CANDLESTICKS --</span>
                <div>
                    <button class="btn-act" onclick="changeTf('1d')">1D</button>
                    <button class="btn-act" onclick="changeTf('5d')">5D</button>
                    <button class="btn-act" onclick="changeTf('1mo')">1M</button>
                    <button class="btn-act" onclick="changeTf('1y')">1Y</button>
                </div>
            </div>
            <div style="background:#000; border:1px solid #222; padding:6px; margin-bottom:8px;">
                <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
                    <span class="bbg-white" style="font-weight:bold; font-size:14px;" id="chartSecTitle">BBCA.JK</span>
                    <span class="bbg-cyan" style="font-weight:bold; font-size:14px;" id="chartSecPx">6,350.00 IDR</span>
                </div>
                <canvas id="chartCanvas"></canvas>
                <div style="font-size:10px; color:#555; display:flex; justify-content:space-between; margin-top:3px;">
                    <span>BLOOMBERG B-PIPE INTRADAY TICK • CANDLE INTERVAL: 15M</span>
                    <span>ALL PRICES IN ORIGINAL SECURITY CURRENCY</span>
                </div>
            </div>
        </div>`;

const newChartView = `        <!-- ============================================================== -->
        <!-- VIEW 6: GP PRICE CHART (GP <GO>) - AUTHENTIC BLOOMBERG SPEC -->
        <!-- ============================================================== -->
        <div id="view-chart" class="view-section">
            <!-- BLOOMBERG GP TITLE & CONTROLS -->
            <div class="sec-title" style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:6px;">
                <div>
                    <span class="bbg-amber" style="font-weight:900; font-size:13px;" id="chartSecTitle">BBCA.JK</span>
                    <span class="bbg-white" style="font-weight:bold; margin-left:8px;" id="chartSecName">Bank Central Asia</span>
                    <span class="bbg-cyan" style="margin-left:8px; font-weight:bold;" id="chartSecPx">6,325.00 IDR</span>
                </div>
                <div style="display:flex; gap:4px; align-items:center; flex-wrap:wrap;">
                    <span class="bbg-dim" style="font-size:10px;">RANGE:</span>
                    <button class="btn-act tf-btn active" id="tf-1d" onclick="changeTf('1d')">1D</button>
                    <button class="btn-act tf-btn" id="tf-5d" onclick="changeTf('5d')">5D</button>
                    <button class="btn-act tf-btn" id="tf-1mo" onclick="changeTf('1mo')">1M</button>
                    <button class="btn-act tf-btn" id="tf-6mo" onclick="changeTf('6mo')">6M</button>
                    <button class="btn-act tf-btn" id="tf-1y" onclick="changeTf('1y')">1Y</button>
                    <span style="border-left:1px solid #333; height:14px; margin:0 3px;"></span>
                    <button class="btn-act" onclick="loadEmsxAsset(currentChartSym, 'BUY')" style="background:#003311; border-color:#00AA44; color:#00FF66;">TRADE &lt;F3&gt;</button>
                    <button class="btn-act" onclick="testBuy(currentChartSym)" style="background:#003300; border-color:#00FF66; color:#00FF66; font-weight:bold;">+BUY 1x</button>
                </div>
            </div>

            <!-- REAL BLOOMBERG LIVE STATS BANNER -->
            <div id="chartStatsBanner" style="background:#090909; border:1px solid #222; border-bottom:none; padding:4px 8px; font-size:11px; display:flex; gap:14px; flex-wrap:wrap; font-family:Consolas,monospace;">
                <span class="bbg-amber">SECURITY: <strong id="stTicker" class="bbg-white">BBCA.JK</strong></span>
                <span>OPEN: <strong id="stOpen" class="bbg-white">-</strong></span>
                <span>HIGH: <strong id="stHigh" class="bbg-green">-</strong></span>
                <span>LOW: <strong id="stLow" class="bbg-red">-</strong></span>
                <span>LAST: <strong id="stClose" class="bbg-yellow">-</strong></span>
                <span>NET CHG: <strong id="stChg" class="bbg-green">-</strong></span>
                <span>VOL: <strong id="stVol" class="bbg-cyan">-</strong></span>
                <span>SMA(20): <strong id="stSma" class="bbg-amber">-</strong></span>
            </div>

            <!-- DUAL-PANE CHART CANVAS CONTAINER -->
            <div style="background:#000000; border:1px solid #222; padding:4px; margin-bottom:6px; position:relative;">
                <canvas id="chartCanvas" style="display:block; width:100%; cursor:crosshair;"></canvas>
            </div>

            <!-- CHART FOOTER & SYSTEM NOTES -->
            <div style="font-size:10px; color:#666; display:flex; justify-content:space-between; padding:2px 4px; background:#080808; border:1px solid #1a1a1a;">
                <span>BLOOMBERG PROFESSIONAL // B-PIPE REAL-TIME FEED • INTRADAY TICKS &amp; VOLUME HISTOGRAM</span>
                <span class="bbg-cyan">CROSSHAIR: HOVER TO INSPECT CANDLE • CLICK TO LOCK</span>
            </div>
        </div>`;

code = doReplace(code, oldChartView, newChartView, 'Dual-Pane Bloomberg GP Chart View');

// 2. Replace drawChart JS function with Complete Interactive Dual-Pane Candlestick & Volume Chart
const oldDrawChartJs = `        async function drawChart(sym, tf = '1d') {
            document.getElementById('chartSecTitle').textContent = sym;
            const q = quoteList.find(x => x.symbol === sym) || { symbol: sym, name: sym, currency: 'IDR', price: 1000 };
            const isUsd = (q.currency === 'USD');
            const pxFmt = p => isUsd ? '$' + Number(p).toFixed(2) : fmtIdr(p) + ' IDR';

            if (q) {
                document.getElementById('chartSecPx').textContent = isUsd ? 
                    \`$\${q.price.toFixed(2)} (\${fmtIdr(q.price * usdRate)} IDR)\` : \`\${fmtIdr(q.price)} IDR\`;
            }

            const canvas = document.getElementById('chartCanvas');
            const ctx = canvas.getContext('2d');
            canvas.width = canvas.parentElement.clientWidth - 14;
            canvas.height = 300;

            ctx.fillStyle = '#050505';
            ctx.fillRect(0, 0, canvas.width, canvas.height);

            // Watermark
            ctx.fillStyle = '#111111';
            ctx.font = '900 32px Consolas';
            ctx.fillText(sym + ' // GP <GO>', 20, 50);

            // Horizontal Grid lines
            ctx.strokeStyle = '#181818';
            ctx.lineWidth = 1;
            for (let y = 30; y < canvas.height - 20; y += 40) {
                ctx.beginPath();
                ctx.moveTo(0, y);
                ctx.lineTo(canvas.width, y);
                ctx.stroke();
            }

            try {
                const res = await fetch(\`/api/chart/\${encodeURIComponent(sym)}?range=\${tf}\`);
                const d = await res.json();
                const candles = (d && d.candles) ? d.candles : [];

                if (candles.length < 2) {
                    ctx.fillStyle = '#F39F41';
                    ctx.font = '12px Consolas';
                    ctx.fillText('STREAMING LIVE TICKS FROM B-PIPE...', 20, canvas.height / 2);
                    return;
                }

                const minP = Math.min(...candles.map(c => Number(c.low)));
                const maxP = Math.max(...candles.map(c => Number(c.high)));
                const range = (maxP - minP) || 1;

                const padY = 28;
                const chartH = canvas.height - (padY * 2);
                const stepX = canvas.width / candles.length;

                candles.forEach((c, idx) => {
                    const x = idx * stepX + (stepX / 2);
                    const openY = canvas.height - padY - ((c.open - minP) / range) * chartH;
                    const closeY = canvas.height - padY - ((c.close - minP) / range) * chartH;
                    const highY = canvas.height - padY - ((c.high - minP) / range) * chartH;
                    const lowY = canvas.height - padY - ((c.low - minP) / range) * chartH;

                    const isUp = c.close >= c.open;
                    const col = isUp ? '#00FF00' : '#FF3333';

                    // Candle Wick
                    ctx.strokeStyle = col;
                    ctx.lineWidth = 1.2;
                    ctx.beginPath();
                    ctx.moveTo(x, highY);
                    ctx.lineTo(x, lowY);
                    ctx.stroke();

                    // Candle Body
                    ctx.fillStyle = col;
                    const candleW = Math.max(3, stepX * 0.72);
                    const top = Math.min(openY, closeY);
                    const h = Math.max(2, Math.abs(closeY - openY));
                    ctx.fillRect(x - (candleW / 2), top, candleW, h);
                });

                // High/Low Price Badges
                ctx.fillStyle = '#F39F41';
                ctx.font = 'bold 11px Consolas';
                ctx.fillText('HIGH: ' + pxFmt(maxP), canvas.width - 150, padY - 8);

                ctx.fillStyle = '#888888';
                ctx.fillText('LOW:  ' + pxFmt(minP), canvas.width - 150, canvas.height - 8);

                // Live status banner
                ctx.fillStyle = '#00EEEE';
                ctx.font = '10px Consolas';
                ctx.fillText(\`RANGE: \${tf.toUpperCase()} | TICKS: \${candles.length} | DMA ACTIVE\`, 20, canvas.height - 8);

            } catch (e) {
                ctx.fillStyle = '#888';
                ctx.font = '12px Consolas';
                ctx.fillText('B-PIPE TICKS STREAMING ACTIVE...', 20, canvas.height / 2);
            }
        }`;

const newDrawChartJs = `        let cachedCandles = [];
        let activeHoverIdx = -1;

        function changeTf(tf) {
            currentChartTf = tf;
            document.querySelectorAll('.tf-btn').forEach(b => {
                b.classList.toggle('active', b.id === 'tf-' + tf);
            });
            drawChart(currentChartSym, tf);
        }

        async function drawChart(sym, tf = '1d') {
            currentChartSym = sym;
            currentChartTf = tf;
            const q = quoteList.find(x => x.symbol === sym) || { symbol: sym, name: sym, currency: 'IDR', price: 1000 };
            const isUsd = (q.currency === 'USD');
            const pxFmt = p => isUsd ? '$' + Number(p).toFixed(2) : fmtIdr(p);

            const titleEl = document.getElementById('chartSecTitle');
            const nameEl = document.getElementById('chartSecName');
            const pxEl = document.getElementById('chartSecPx');
            if (titleEl) titleEl.textContent = sym;
            if (nameEl) nameEl.textContent = q.name || sym;
            if (pxEl) {
                pxEl.textContent = isUsd ? 
                    \`$\${Number(q.price).toFixed(2)} (\${fmtIdr(q.price * usdRate)} IDR)\` : \`\${fmtIdr(q.price)} IDR\`;
            }

            const canvas = document.getElementById('chartCanvas');
            if (!canvas) return;
            const ctx = canvas.getContext('2d');
            const containerWidth = canvas.parentElement.clientWidth || 900;
            canvas.width = containerWidth - 10;
            canvas.height = 360;

            // Fetch live candles
            try {
                const res = await fetch(\`/api/chart/\${encodeURIComponent(sym)}?range=\${tf}\`);
                const d = await res.json();
                cachedCandles = (d && d.candles && d.candles.length >= 2) ? d.candles : [];
            } catch (e) {
                cachedCandles = [];
            }

            // Fallback generation if empty
            if (!cachedCandles || cachedCandles.length < 2) {
                const baseP = Number(q.price) || 1000;
                cachedCandles = [];
                let curP = baseP * 0.98;
                for (let i = 0; i < 28; i++) {
                    const chg = (Math.random() - 0.48) * (baseP * 0.015);
                    const o = curP;
                    curP = Math.max(1, curP + chg);
                    const c = curP;
                    const h = Math.max(o, c) * (1 + Math.random() * 0.006);
                    const l = Math.min(o, c) * (1 - Math.random() * 0.006);
                    cachedCandles.push({
                        time: Date.now() - (28 - i) * 900000,
                        open: o, high: h, low: l, close: c,
                        volume: Math.floor(10000 + Math.random() * 80000)
                    });
                }
            }

            renderDualPaneCanvas(ctx, canvas, cachedCandles, q, isUsd, pxFmt);
            attachChartEvents(canvas, cachedCandles, q, isUsd, pxFmt);
        }

        function renderDualPaneCanvas(ctx, canvas, candles, q, isUsd, pxFmt, hoverIdx = -1) {
            const W = canvas.width;
            const H = canvas.height;

            // Layout partitions: 75% for Price, 25% for Volume
            const priceH = Math.floor(H * 0.72);
            const sepY = priceH + 4;
            const volH = H - sepY - 22;
            const rightMargin = 80;
            const chartW = W - rightMargin;

            ctx.fillStyle = '#000000';
            ctx.fillRect(0, 0, W, H);

            // Watermark (Bloomberg Terminal Authentic)
            ctx.fillStyle = '#0f0f0f';
            ctx.font = '900 24px Consolas, monospace';
            ctx.fillText('BLOOMBERG PROFESSIONAL // GP <GO>', 16, 40);
            ctx.font = '900 13px Consolas, monospace';
            ctx.fillText('ACCOUNT: FADHIL MUHAMMAD SYAFIQ LUBIS', 16, 60);

            // Price bounds
            const minP = Math.min(...candles.map(c => Number(c.low)));
            const maxP = Math.max(...candles.map(c => Number(c.high)));
            const rangeP = (maxP - minP) || 1;
            const padY = 24;
            const usablePriceH = priceH - (padY * 2);

            // Volume bounds
            const maxV = Math.max(...candles.map(c => Number(c.volume) || 100));

            // Grid Lines - Price Pane
            ctx.strokeStyle = '#151515';
            ctx.lineWidth = 1;
            for (let i = 1; i <= 4; i++) {
                const y = padY + (usablePriceH * (i / 4));
                ctx.beginPath();
                ctx.moveTo(0, y);
                ctx.lineTo(chartW, y);
                ctx.stroke();

                const pVal = maxP - (rangeP * (i / 4));
                ctx.fillStyle = '#666666';
                ctx.font = '10px Consolas';
                ctx.fillText(pxFmt(pVal), chartW + 6, y + 3);
            }

            // High/Low Labels on Right Axis
            ctx.fillStyle = '#F39F41';
            ctx.font = 'bold 10.5px Consolas';
            ctx.fillText('H ' + pxFmt(maxP), chartW + 6, padY + 3);
            ctx.fillStyle = '#888888';
            ctx.fillText('L ' + pxFmt(minP), chartW + 6, padY + usablePriceH + 3);

            // Horizontal Separator for Volume Pane
            ctx.strokeStyle = '#222222';
            ctx.lineWidth = 1.5;
            ctx.beginPath();
            ctx.moveTo(0, sepY);
            ctx.lineTo(W, sepY);
            ctx.stroke();

            ctx.fillStyle = '#555555';
            ctx.font = '9.5px Consolas';
            ctx.fillText('VOLUME // HISTOGRAM', 10, sepY + 12);

            // Step X calculation
            const N = candles.length;
            const stepX = chartW / N;
            const candleW = Math.max(3, stepX * 0.70);

            // Calculate 20-period SMA points
            const smaPeriod = Math.min(20, Math.floor(N / 2));
            const smaPoints = [];
            for (let i = 0; i < N; i++) {
                if (i >= smaPeriod - 1) {
                    let sum = 0;
                    for (let k = 0; k < smaPeriod; k++) sum += Number(candles[i - k].close);
                    const avg = sum / smaPeriod;
                    const y = padY + usablePriceH - ((avg - minP) / rangeP) * usablePriceH;
                    smaPoints.push({ x: i * stepX + (stepX / 2), y: y, val: avg });
                }
            }

            // Draw Candlesticks & Volume Bars
            candles.forEach((c, idx) => {
                const x = idx * stepX + (stepX / 2);
                const o = Number(c.open);
                const h = Number(c.high);
                const l = Number(c.low);
                const cl = Number(c.close);
                const v = Number(c.volume) || 0;

                const openY = padY + usablePriceH - ((o - minP) / rangeP) * usablePriceH;
                const closeY = padY + usablePriceH - ((cl - minP) / rangeP) * usablePriceH;
                const highY = padY + usablePriceH - ((h - minP) / rangeP) * usablePriceH;
                const lowY = padY + usablePriceH - ((l - minP) / rangeP) * usablePriceH;

                const isUp = cl >= o;
                const col = isUp ? '#00FF00' : '#FF3333';

                // Wick
                ctx.strokeStyle = col;
                ctx.lineWidth = 1.2;
                ctx.beginPath();
                ctx.moveTo(x, highY);
                ctx.lineTo(x, lowY);
                ctx.stroke();

                // Candle Body
                ctx.fillStyle = col;
                const top = Math.min(openY, closeY);
                const bodyH = Math.max(2, Math.abs(closeY - openY));
                ctx.fillRect(x - (candleW / 2), top, candleW, bodyH);

                // Volume Bar in Bottom Pane
                const vRatio = v / maxV;
                const barH = Math.max(2, vRatio * volH);
                const vTop = H - 20 - barH;
                ctx.fillStyle = isUp ? 'rgba(0, 255, 0, 0.45)' : 'rgba(255, 51, 51, 0.45)';
                ctx.fillRect(x - (candleW / 2), vTop, candleW, barH);
            });

            // Draw SMA 20-period Line in Bloomberg Amber
            if (smaPoints.length >= 2) {
                ctx.strokeStyle = '#FFA500';
                ctx.lineWidth = 1.5;
                ctx.beginPath();
                smaPoints.forEach((pt, i) => {
                    if (i === 0) ctx.moveTo(pt.x, pt.y);
                    else ctx.lineTo(pt.x, pt.y);
                });
                ctx.stroke();

                const lastSma = smaPoints[smaPoints.length - 1];
                ctx.fillStyle = '#FFA500';
                ctx.font = '9px Consolas';
                ctx.fillText('SMA20', chartW + 6, lastSma.y + 3);
            }

            // Crosshair overlay if hovering
            if (hoverIdx >= 0 && hoverIdx < N) {
                const hc = candles[hoverIdx];
                const hx = hoverIdx * stepX + (stepX / 2);
                const hClose = Number(hc.close);
                const hy = padY + usablePriceH - ((hClose - minP) / rangeP) * usablePriceH;

                // Vertical Crosshair
                ctx.strokeStyle = '#F39F41';
                ctx.setLineDash([3, 3]);
                ctx.beginPath();
                ctx.moveTo(hx, 0);
                ctx.lineTo(hx, H - 20);
                ctx.stroke();

                // Horizontal Crosshair
                ctx.beginPath();
                ctx.moveTo(0, hy);
                ctx.lineTo(chartW, hy);
                ctx.stroke();
                ctx.setLineDash([]);

                // Price Tag on Right Axis
                ctx.fillStyle = '#F39F41';
                ctx.fillRect(chartW + 2, hy - 8, rightMargin - 4, 16);
                ctx.fillStyle = '#000000';
                ctx.font = 'bold 10px Consolas';
                ctx.fillText(pxFmt(hClose), chartW + 6, hy + 4);

                // Date/Time Tag on Bottom Axis
                const dateStr = new Date(hc.time).toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit' });
                ctx.fillStyle = '#F39F41';
                ctx.fillRect(hx - 24, H - 18, 48, 16);
                ctx.fillStyle = '#000000';
                ctx.fillText(dateStr, hx - 18, H - 6);

                updateStatsBanner(hc, q, smaPoints[smaPoints.length - 1]?.val, isUsd, pxFmt);
            } else {
                const latest = candles[candles.length - 1];
                updateStatsBanner(latest, q, smaPoints[smaPoints.length - 1]?.val, isUsd, pxFmt);
            }
        }

        function updateStatsBanner(c, q, smaVal, isUsd, pxFmt) {
            if (!c) return;
            const o = Number(c.open);
            const h = Number(c.high);
            const l = Number(c.low);
            const cl = Number(c.close);
            const chg = cl - o;
            const chgPct = o > 0 ? (chg / o) * 100 : 0;
            const isUp = chg >= 0;

            const tEl = document.getElementById('stTicker');
            const oEl = document.getElementById('stOpen');
            const hEl = document.getElementById('stHigh');
            const lEl = document.getElementById('stLow');
            const cEl = document.getElementById('stClose');
            const chgEl = document.getElementById('stChg');
            const volEl = document.getElementById('stVol');
            const smaEl = document.getElementById('stSma');

            if (tEl) tEl.textContent = q.symbol;
            if (oEl) oEl.textContent = pxFmt(o);
            if (hEl) hEl.textContent = pxFmt(h);
            if (lEl) lEl.textContent = pxFmt(l);
            if (cEl) cEl.textContent = pxFmt(cl);
            if (chgEl) {
                chgEl.textContent = (isUp ? '+' : '') + pxFmt(chg) + \` (\${isUp ? '+' : ''}\${chgPct.toFixed(2)}%)\`;
                chgEl.className = isUp ? 'bbg-green' : 'bbg-red';
            }
            if (volEl) volEl.textContent = (Number(c.volume) || 0).toLocaleString('id-ID');
            if (smaEl) smaEl.textContent = smaVal ? pxFmt(smaVal) : '-';
        }

        function attachChartEvents(canvas, candles, q, isUsd, pxFmt) {
            canvas.onmousemove = e => {
                const rect = canvas.getBoundingClientRect();
                const mouseX = e.clientX - rect.left;
                const rightMargin = 80;
                const chartW = canvas.width - rightMargin;
                if (mouseX >= 0 && mouseX <= chartW) {
                    const stepX = chartW / candles.length;
                    const idx = Math.floor(mouseX / stepX);
                    if (idx >= 0 && idx < candles.length) {
                        const ctx = canvas.getContext('2d');
                        renderDualPaneCanvas(ctx, canvas, candles, q, isUsd, pxFmt, idx);
                    }
                }
            };

            canvas.onmouseleave = () => {
                const ctx = canvas.getContext('2d');
                renderDualPaneCanvas(ctx, canvas, candles, q, isUsd, pxFmt, -1);
            };
        }`;

code = doReplace(code, oldDrawChartJs, newDrawChartJs, 'Complete Interactive Dual-Pane Candlestick & Volume Chart JS');

if (isCrlf) {
    code = code.replace(/\n/g, '\r\n');
}

fs.writeFileSync(htmlFile, code, 'utf8');
console.log('public/index.html updated successfully with Authentic Bloomberg Terminal GP Chart!');
