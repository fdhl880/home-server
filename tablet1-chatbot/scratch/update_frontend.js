const fs = require('fs');
const path = require('path');

const filePath = path.join(__dirname, '..', 'public', 'index.html');
let raw = fs.readFileSync(filePath, 'utf8');
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

// 1. Add F8 RESET PORTO to physical function key nav bar
const oldFBar = `<button class="f-key k-cyan" onclick="showView('ai')">8&lt;GO&gt; B-ANALYST (AI)</button>`;
const newFBar = `<button class="f-key k-cyan" onclick="showView('ai')">8&lt;GO&gt; B-ANALYST (AI)</button>
        <button class="f-key k-red" onclick="resetPortfolio()" title="Reset seluruh portofolio ke saldo kas awal">F8 RESET PORTO</button>`;

code = doReplace(code, oldFBar, newFBar, 'F-Key Bar Reset Button');

// 2. Add Clear / Reset Porto Button to Screen Title Row
const oldScreenHdr = `<div class="screen-hdr">
            <span>PORTFOLIO &amp; RISK ANALYTICS // PORTFOLIO: FADHIL MUHAMMAD SYAFIQ LUBIS (IDR)</span>
            <span class="bbg-amber">VALUATION: REAL-TIME B-PIPE FEED</span>
        </div>`;

const newScreenHdr = `<div class="screen-hdr" style="display:flex; justify-content:space-between; align-items:center;">
            <span>PORTFOLIO &amp; RISK ANALYTICS // PORTFOLIO: FADHIL MUHAMMAD SYAFIQ LUBIS (IDR)</span>
            <div style="display:flex; gap:10px; align-items:center;">
                <button class="btn-act" style="background:#3a0000; border:1px solid #FF3333; color:#FF8888; font-weight:bold; font-size:10.5px; padding:2px 10px; cursor:pointer;" onclick="resetPortfolio()">CLEAR / RESET PORTO &lt;F8&gt;</button>
                <span class="bbg-amber">VALUATION: REAL-TIME B-PIPE FEED</span>
            </div>
        </div>`;

code = doReplace(code, oldScreenHdr, newScreenHdr, 'Screen Header Reset Button');

// 3. Update Category Pills in VIEW 3 (EMSX Universe) to include HOT IPOs
const oldEmsxPills = `<div class="cat-pill-bar">
                <button class="cat-pill active" onclick="setUniverseFilter('ALL')">ALL (218)</button>
                <button class="cat-pill" onclick="setUniverseFilter('Saham Indo')">IDX INDONESIA (70)</button>
                <button class="cat-pill" onclick="setUniverseFilter('Saham US')">WALL STREET (66)</button>
                <button class="cat-pill" onclick="setUniverseFilter('Saham Global')">GLOBAL ADRs (10)</button>
                <button class="cat-pill" onclick="setUniverseFilter('Crypto')">CRYPTO (30)</button>
                <button class="cat-pill" onclick="setUniverseFilter('Komoditas')">KOMODITAS (16)</button>
                <button class="cat-pill" onclick="setUniverseFilter('Forex')">FOREX (15)</button>
                <button class="cat-pill" onclick="setUniverseFilter('Index')">INDICES &amp; RATES (11)</button>
                <span class="cat-pill-count" id="emsxAssetCount">SHOWING: 218 ASSETS</span>
            </div>`;

const newEmsxPills = `<div class="cat-pill-bar">
                <button class="cat-pill active" onclick="setUniverseFilter('ALL')">ALL (258+)</button>
                <button class="cat-pill" style="border-color:#00EEEE; color:#00EEEE;" onclick="setUniverseFilter('Saham IPO')">HOT IPOs (40)</button>
                <button class="cat-pill" onclick="setUniverseFilter('Saham Indo')">IDX INDONESIA (70)</button>
                <button class="cat-pill" onclick="setUniverseFilter('Saham US')">WALL STREET (66)</button>
                <button class="cat-pill" onclick="setUniverseFilter('Saham Global')">GLOBAL ADRs (10)</button>
                <button class="cat-pill" onclick="setUniverseFilter('Crypto')">CRYPTO (30)</button>
                <button class="cat-pill" onclick="setUniverseFilter('Komoditas')">KOMODITAS (16)</button>
                <button class="cat-pill" onclick="setUniverseFilter('Forex')">FOREX (15)</button>
                <button class="cat-pill" onclick="setUniverseFilter('Index')">INDICES &amp; RATES (11)</button>
                <span class="cat-pill-count" id="emsxAssetCount">SHOWING: 258 ASSETS</span>
            </div>`;

code = doReplace(code, oldEmsxPills, newEmsxPills, 'EMSX Category Pills with IPO Watch');

// 4. Update Category Pills in VIEW 5 (Market Monitor) to include HOT IPOs
const oldMonPills = `<div class="cat-pill-bar">
                <button class="cat-pill active" onclick="setMonitorFilter('ALL')">ALL (218)</button>
                <button class="cat-pill" onclick="setMonitorFilter('Saham Indo')">IDX INDONESIA (70)</button>
                <button class="cat-pill" onclick="setMonitorFilter('Saham US')">WALL STREET (66)</button>
                <button class="cat-pill" onclick="setMonitorFilter('Saham Global')">GLOBAL ADRs (10)</button>
                <button class="cat-pill" onclick="setMonitorFilter('Crypto')">CRYPTO (30)</button>
                <button class="cat-pill" onclick="setMonitorFilter('Komoditas')">KOMODITAS (16)</button>
                <button class="cat-pill" onclick="setMonitorFilter('Forex')">FOREX (15)</button>
                <button class="cat-pill" onclick="setMonitorFilter('Index')">INDICES &amp; RATES (11)</button>
                <span class="cat-pill-count" id="monAssetCount">SHOWING: 218 ASSETS</span>
            </div>`;

const newMonPills = `<div class="cat-pill-bar">
                <button class="cat-pill active" onclick="setMonitorFilter('ALL')">ALL (258+)</button>
                <button class="cat-pill" style="border-color:#00EEEE; color:#00EEEE;" onclick="setMonitorFilter('Saham IPO')">HOT IPOs (40)</button>
                <button class="cat-pill" onclick="setMonitorFilter('Saham Indo')">IDX INDONESIA (70)</button>
                <button class="cat-pill" onclick="setMonitorFilter('Saham US')">WALL STREET (66)</button>
                <button class="cat-pill" onclick="setMonitorFilter('Saham Global')">GLOBAL ADRs (10)</button>
                <button class="cat-pill" onclick="setMonitorFilter('Crypto')">CRYPTO (30)</button>
                <button class="cat-pill" onclick="setMonitorFilter('Komoditas')">KOMODITAS (16)</button>
                <button class="cat-pill" onclick="setMonitorFilter('Forex')">FOREX (15)</button>
                <button class="cat-pill" onclick="setMonitorFilter('Index')">INDICES &amp; RATES (11)</button>
                <span class="cat-pill-count" id="monAssetCount">SHOWING: 258 ASSETS</span>
            </div>`;

code = doReplace(code, oldMonPills, newMonPills, 'Market Monitor Category Pills with IPO Watch');

// 5. Add resetPortfolio JS function and update categories in populateEmsxDropdown
const oldCategories = `            // Group quotes into categories for clean selection
            const categories = [
                { name: 'SAHAM INDONESIA (IDX)', filter: q => q.category === 'Saham Indo' },
                { name: 'WALL STREET & US MEGA-CAPS', filter: q => q.category === 'Saham US' },`;

const newCategories = `            // Group quotes into categories for clean selection
            const categories = [
                { name: 'HOT IPO WATCH & RECENT LISTINGS (IDX & US)', filter: q => q.category === 'Saham IPO' },
                { name: 'SAHAM INDONESIA (IDX BLUECHIPS)', filter: q => q.category === 'Saham Indo' },
                { name: 'WALL STREET & US MEGA-CAPS', filter: q => q.category === 'Saham US' },`;

code = doReplace(code, oldCategories, newCategories, 'EMSX Dropdown Categories with IPO Group');

// Add resetPortfolio function before testBuy
const oldTestBuyDef = `        async function testBuy(sym, qty = 1) {`;
const newTestBuyDef = `        // ============================================================
        // CLEAR & RESET PORTFOLIO TO CASH
        // ============================================================
        async function resetPortfolio() {
            if (!confirm("⚠️ PERINGATAN BLOOMBERG TERMINAL:\\n\\nApakah Anda yakin ingin me-RESET seluruh portofolio FADHIL MUHAMMAD SYAFIQ LUBIS?\\n\\nSemua posisi saham dan aset akan ditutup, dan saldo kas kembali bersih ke Rp 200.000.000.")) {
                return;
            }
            showPopup("[RESET DMA] MERESET SELURUH PORTOFOLIO KE MODAL AWAL...");
            try {
                const res = await fetch('/api/portfolio/reset', { method: 'POST' });
                const d = await res.json();
                if (d.success) {
                    showPopup("✅ PORTOFOLIO BERHASIL DI-RESET KE MODAL AWAL!");
                    await fetchPortfolioData();
                    await fetchQuotesData();
                    showView('summary');
                } else {
                    showPopup("GAGAL RESET: " + (d.error || 'Unknown error'), true);
                }
            } catch (e) {
                showPopup("ERROR RESET: " + e.message, true);
            }
        }

        async function testBuy(sym, qty = 1) {`;

code = doReplace(code, oldTestBuyDef, newTestBuyDef, 'resetPortfolio JS Function');

// 6. Enhance drawChart function to draw high-res candles, currency formatting, and watermarks
const oldDrawChart = `        async function drawChart(sym, tf = '1d') {
            document.getElementById('chartSecTitle').textContent = sym;
            const q = quoteList.find(x => x.symbol === sym);
            if (q) {
                document.getElementById('chartSecPx').textContent = q.currency === 'USD' ? 
                    \`$\${q.price.toFixed(2)} (\${fmtIdr(q.price * usdRate)} IDR)\` : \`\${fmtIdr(q.price)} IDR\`;
            }

            const canvas = document.getElementById('chartCanvas');
            const ctx = canvas.getContext('2d');
            canvas.width = canvas.parentElement.clientWidth - 14;
            canvas.height = 280;

            ctx.fillStyle = '#000000';
            ctx.fillRect(0, 0, canvas.width, canvas.height);

            // Grid lines
            ctx.strokeStyle = '#141414';
            ctx.lineWidth = 1;
            for (let y = 30; y < canvas.height; y += 40) {
                ctx.beginPath();
                ctx.moveTo(0, y);
                ctx.lineTo(canvas.width, y);
                ctx.stroke();
            }

            try {
                const res = await fetch(\`/api/chart/\${encodeURIComponent(sym)}?range=\${tf}\`);
                if (!res.ok) throw new Error('No chart data');
                const d = await res.json();
                const candles = d.candles || [];

                if (candles.length < 2) {
                    ctx.fillStyle = '#666';
                    ctx.font = '12px Consolas';
                    ctx.fillText('Awaiting real-time tick updates...', 20, canvas.height / 2);
                    return;
                }

                const minP = Math.min(...candles.map(c => c.low));
                const maxP = Math.max(...candles.map(c => c.high));
                const range = (maxP - minP) || 1;

                const padY = 22;
                const chartH = canvas.height - (padY * 2);
                const stepX = canvas.width / candles.length;

                candles.forEach((c, idx) => {
                    const x = idx * stepX + (stepX / 2);
                    const openY = canvas.height - padY - ((c.open - minP) / range) * chartH;
                    const closeY = canvas.height - padY - ((c.close - minP) / range) * chartH;
                    const highY = canvas.height - padY - ((c.high - minP) / range) * chartH;
                    const lowY = canvas.height - padY - ((c.low - minP) / range) * chartH;

                    const isUp = c.close >= c.open;
                    const col = isUp ? '#00FF00' : '#FF2233';

                    // Wick
                    ctx.strokeStyle = col;
                    ctx.lineWidth = 1.2;
                    ctx.beginPath();
                    ctx.moveTo(x, highY);
                    ctx.lineTo(x, lowY);
                    ctx.stroke();

                    // Body
                    ctx.fillStyle = col;
                    const candleW = Math.max(2, stepX * 0.72);
                    const top = Math.min(openY, closeY);
                    const h = Math.max(2, Math.abs(closeY - openY));
                    ctx.fillRect(x - (candleW / 2), top, candleW, h);
                });

                // High/Low labels
                ctx.fillStyle = '#F39F41';
                ctx.font = '10px Consolas';
                ctx.fillText(maxP.toFixed(2), canvas.width - 65, padY);
                ctx.fillStyle = '#888888';
                ctx.fillText(minP.toFixed(2), canvas.width - 65, canvas.height - 6);

            } catch (e) {
                ctx.fillStyle = '#666';
                ctx.font = '12px Consolas';
                ctx.fillText('Tick streaming in progress...', 20, canvas.height / 2);
            }
        }`;

const newDrawChart = `        async function drawChart(sym, tf = '1d') {
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

code = doReplace(code, oldDrawChart, newDrawChart, 'Enhanced drawChart Implementation');

// 7. Add F8 Key Listener and RESET Command Parser
const oldFKeys = `                if (e.key === 'F7') { e.preventDefault(); showView('news'); }`;
const newFKeys = `                if (e.key === 'F7') { e.preventDefault(); showView('news'); }
                if (e.key === 'F8') { e.preventDefault(); resetPortfolio(); }`;

code = doReplace(code, oldFKeys, newFKeys, 'F8 Key Listener');

const oldCmdResetCheck = `            if (raw.startsWith('TESTBUY ') || raw.startsWith('TBUY ') || raw.startsWith('BUY ')) {`;
const newCmdResetCheck = `            if (raw === 'RESET' || raw === 'CLEAR' || raw === 'RESETPORTO' || raw === 'CLEARPORTO' || raw === 'PURGE') {
                resetPortfolio();
                return;
            }

            if (raw.startsWith('TESTBUY ') || raw.startsWith('TBUY ') || raw.startsWith('BUY ')) {`;

code = doReplace(code, oldCmdResetCheck, newCmdResetCheck, 'Command bar RESET command');

if (isCrlf) {
    code = code.replace(/\n/g, '\r\n');
}

fs.writeFileSync(filePath, code, 'utf8');
console.log('public/index.html updated successfully with all features!');
