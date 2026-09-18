const fs = require('fs');
const path = require('path');

const filePath = path.join(__dirname, '..', 'public', 'index.html');
// Read and normalize to \n for robust replacement
let rawContent = fs.readFileSync(filePath, 'utf8');
let isCrlf = rawContent.includes('\r\n');
let content = rawContent.replace(/\r\n/g, '\n');

function doReplace(str, target, replacement, desc) {
    if (!str.includes(target)) {
        console.error('FAILED TO MATCH:', desc);
        return str;
    }
    console.log('SUCCESS:', desc);
    return str.replace(target, () => replacement);
}

// 1. User text changes
content = doReplace(
    content,
    '<title>BLOOMBERG TERMINAL // PORT <GO> - FADHIL-ALPHA-200M</title>',
    '<title>BLOOMBERG TERMINAL // PORT <GO> - FADHIL MUHAMMAD SYAFIQ LUBIS</title>',
    'Page Title'
);

content = doReplace(
    content,
    '<span>PORTFOLIO: <strong class="bbg-white">FADHIL-ALPHA-200M</strong></span>',
    '<span>PORTFOLIO: <strong class="bbg-white">FADHIL MUHAMMAD SYAFIQ LUBIS</strong></span>',
    'Top Bar Portfolio Name'
);

content = doReplace(
    content,
    '<span>PORTFOLIO &amp; RISK ANALYTICS // PORTFOLIO: FADHIL-ALPHA-200M (IDR)</span>',
    '<span>PORTFOLIO &amp; RISK ANALYTICS // PORTFOLIO: FADHIL MUHAMMAD SYAFIQ LUBIS (IDR)</span>',
    'Analytics Section Portfolio Name'
);

content = doReplace(
    content,
    '<span class="p-metric-sub" id="sReturn">Return: +0.00% (Awal: Rp 200 Jt)</span>',
    '<span class="p-metric-sub" id="sReturn">Return: +0.00%</span>',
    'Return metric initial capital text'
);

content = doReplace(
    content,
    'retEl.textContent = `Return: ${fmtPct(portState.overallReturn)} (Awal: Rp 200 Jt)`;',
    'retEl.textContent = `Return: ${fmtPct(portState.overallReturn)}`;',
    'JS Return metric display without Awal: Rp 200 Jt'
);

content = doReplace(
    content,
    '[NO ACTIVE POSITIONS] Portofolio Anda memiliki modal Rp 200.000.000 (100% Cash).',
    '[NO ACTIVE POSITIONS] Portofolio FADHIL MUHAMMAD SYAFIQ LUBIS (100% Cash).',
    'Empty holdings placeholder 1'
);

content = doReplace(
    content,
    '[NO ACTIVE POSITIONS] Portofolio Anda memiliki modal Rp 200.000.000 (100% Cash).',
    '[NO ACTIVE POSITIONS] Portofolio FADHIL MUHAMMAD SYAFIQ LUBIS (100% Cash).',
    'Empty holdings placeholder 2'
);

content = doReplace(
    content,
    '<span class="bbg-cyan">ACCOUNT: FADHIL-ALPHA-200M | ROUTE: BEST-EXEC</span>',
    '<span class="bbg-cyan">ACCOUNT: FADHIL MUHAMMAD SYAFIQ LUBIS | ROUTE: BEST-EXEC</span>',
    'EMSX Account Name'
);

content = doReplace(
    content,
    'Portfolio: FADHIL-ALPHA-200M | Modal: Rp 200.000.000.',
    'Portfolio: FADHIL MUHAMMAD SYAFIQ LUBIS.',
    'Chatbot prompt banner'
);

content = doReplace(
    content,
    `<button class="btn-act" onclick="askAi('Berikan rekomendasi alokasi modal Rp 200 Juta saya secara terperinci.')">Rekomendasi Alokasi 200 Juta</button>`,
    `<button class="btn-act" onclick="askAi('Berikan rekomendasi alokasi portofolio FADHIL MUHAMMAD SYAFIQ LUBIS secara terperinci.')">Rekomendasi Alokasi Portofolio</button>`,
    'Chatbot suggestion button'
);

content = doReplace(
    content,
    `<p><strong class="bbg-amber">1&lt;GO&gt; PORT</strong> - Portfolio &amp; Risk Analytics (Modal Rp 200 Juta)</p>`,
    `<p><strong class="bbg-amber">1&lt;GO&gt; PORT</strong> - Portfolio &amp; Risk Analytics</p>`,
    'Help screen PORT description'
);

// 2. CSS for Category Pills
const cssPills = `
        /* ASSET UNIVERSE & MONITOR CATEGORY FILTER PILLS */
        .cat-pill-bar {
            display: flex;
            gap: 4px;
            flex-wrap: wrap;
            padding: 4px 6px;
            background: #080808;
            border: 1px solid #1a1a1a;
            margin-bottom: 6px;
            align-items: center;
        }
        .cat-pill {
            background: #111111;
            border: 1px solid #333333;
            color: #aaaaaa;
            font-family: inherit;
            font-size: 10px;
            font-weight: bold;
            padding: 3px 8px;
            cursor: pointer;
            text-transform: uppercase;
            transition: all 0.15s ease;
        }
        .cat-pill:hover {
            background: #222222;
            color: #F39F41;
            border-color: #F39F41;
        }
        .cat-pill.active {
            background: #F39F41;
            color: #000000;
            border-color: #F39F41;
            box-shadow: 0 0 6px rgba(243, 159, 65, 0.4);
        }
        .cat-pill-count {
            margin-left: auto;
            font-size: 10px;
            color: #00EEEE;
            font-weight: bold;
        }
`;

content = doReplace(
    content,
    '/* NOTIFICATION TOAST */',
    cssPills + '\n        /* NOTIFICATION TOAST */',
    'Category Pills CSS'
);

// 3. EMSX Execute button + Quick Buy button
const oldExecBtn = `<button class="btn-exec" id="btnEmsxExec" onclick="executeEmsxOrder()">
                            &lt;TRANSACT / EXECUTE DMA ORDER &lt;GO&gt;&gt;
                        </button>`;

const newExecBtn = `<div style="display:flex; gap:6px; margin-top:8px;">
                            <button class="btn-exec" id="btnEmsxExec" onclick="executeEmsxOrder()" style="flex:1; margin-top:0;">
                                &lt;TRANSACT / EXECUTE DMA ORDER &lt;GO&gt;&gt;
                            </button>
                            <button class="btn-act" id="btnEmsxQuickBuy" onclick="testBuyCurrentEmsx()" style="background:#003311; border:1px solid #00AA44; color:#00FF66; font-weight:bold; font-size:11px; padding:0 12px; cursor:pointer;" title="Langsung beli 1 lot/unit aset ini untuk pengujian">
                                +TEST BUY
                            </button>
                        </div>`;

content = doReplace(content, oldExecBtn, newExecBtn, 'EMSX Order Desk Quick Test-Buy Button');

// 4. EMSX Tradeable Universe Header & Table
const oldUniverseHeader = `            <!-- TRADEABLE ASSETS TABLE -->
            <div class="sec-title">
                <span>TRADEABLE ASSET UNIVERSE (CLICK TICKER TO LOAD INTO EMSX)</span>
                <span class="bbg-cyan">REAL-TIME PRICES</span>
            </div>`;

const newUniverseHeader = `            <!-- TRADEABLE ASSETS TABLE -->
            <div class="sec-title" style="display:flex; justify-content:space-between; align-items:center;">
                <span>TRADEABLE ASSET UNIVERSE // 218+ INSTRUMENTS (CLICK TICKER ATAU +BUY)</span>
                <div style="display:flex; gap:8px; align-items:center;">
                    <input type="text" id="emsxSearchInput" oninput="filterEmsxUniverse()" class="bbg-input"
                        placeholder="FILTER UNIVERSE..."
                        style="width:230px; font-size:10.5px; padding:2px 6px; text-transform:uppercase;">
                    <span class="bbg-cyan" style="font-size:10px;">B-PIPE DMA</span>
                </div>
            </div>
            <div class="cat-pill-bar">
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

content = doReplace(content, oldUniverseHeader, newUniverseHeader, 'EMSX Universe Header & Category Pills');

// Add QUICK BUY column to EMSX table header
const oldUniverseTh = `                        <tr>
                            <th>TICKER</th>
                            <th>SECURITY NAME</th>
                            <th>ASSET CLASS</th>
                            <th>ORIGINAL PX</th>
                            <th>PRICE (IDR)</th>
                            <th>1D MOVE %</th>
                            <th>DAY HIGH</th>
                            <th>DAY LOW</th>
                        </tr>`;

const newUniverseTh = `                        <tr>
                            <th>TICKER</th>
                            <th>SECURITY NAME</th>
                            <th>ASSET CLASS</th>
                            <th>ORIGINAL PX</th>
                            <th>PRICE (IDR)</th>
                            <th>1D MOVE %</th>
                            <th>DAY HIGH</th>
                            <th>DAY LOW</th>
                            <th style="text-align:center;">QUICK BUY</th>
                        </tr>`;

content = doReplace(content, oldUniverseTh, newUniverseTh, 'EMSX Universe Table QUICK BUY Column');

// 5. Market Monitor Header
const oldMonHeader = `            <div class="sec-title">
                <span>-- GLOBAL MULTI-ASSET MARKET MONITOR (EQUITIES, CRYPTO, COMMODITIES, FOREX) --</span>
                <button class="btn-act" onclick="fetchQuotesData()">PULL LIVE DATA &lt;GO&gt;</button>
            </div>`;

const newMonHeader = `            <div class="sec-title" style="display:flex; justify-content:space-between; align-items:center;">
                <span>-- GLOBAL MULTI-ASSET MARKET MONITOR (218+ ASSETS ACROSS ALL EXCHANGES) --</span>
                <div style="display:flex; gap:8px; align-items:center;">
                    <input type="text" id="monitorSearchInput" oninput="renderMonitorGrid()" class="bbg-input"
                        placeholder="FILTER MONITOR..."
                        style="width:200px; font-size:10.5px; padding:2px 6px; text-transform:uppercase;">
                    <button class="btn-act" onclick="fetchQuotesData()">PULL LIVE DATA &lt;GO&gt;</button>
                </div>
            </div>
            <div class="cat-pill-bar">
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

content = doReplace(content, oldMonHeader, newMonHeader, 'Market Monitor Header & Category Pills');

// 6. JavaScript Functions: renderMonitorGrid & populateEmsxDropdown replacement
const oldJsSection = `        function renderMonitorGrid() {
            const tbody = document.getElementById('monitorGridBody');
            tbody.innerHTML = quoteList.map(q => {
                const isUp = q.changePct >= 0;
                const cls = isUp ? 'bbg-green' : 'bbg-red';
                const sign = isUp ? '+' : '';
                const origPx = q.currency === 'USD' ? '$' + q.price.toFixed(2) : fmtIdr(q.price);
                const idrPx = fmtIdr(q.priceIdr || (q.currency === 'USD' ? q.price * usdRate : q.price));

                return \`
                    <tr>
                        <td><strong class="bbg-amber" style="cursor:pointer;" onclick="openGp('\${q.symbol}')">\${q.symbol}</strong></td>
                        <td class="bbg-white">\${q.name}</td>
                        <td class="bbg-dim" style="font-size:10px;">\${q.category}</td>
                        <td class="bbg-cyan">\${origPx}</td>
                        <td class="bbg-white"><strong>\${idrPx}</strong></td>
                        <td class="\${cls}">\${sign}\${fmtIdr(q.change)}</td>
                        <td class="\${cls}">\${sign}\${q.changePct.toFixed(2)}%</td>
                        <td>\${q.currency === 'USD' ? '$'+q.high.toFixed(2) : fmtIdr(q.high)}</td>
                        <td>\${q.currency === 'USD' ? '$'+q.low.toFixed(2) : fmtIdr(q.low)}</td>
                        <td style="text-align:center;">
                            <button class="btn-act" onclick="loadEmsxAsset('\${q.symbol}', 'BUY')">TRADE</button>
                            <button class="btn-act" onclick="openGp('\${q.symbol}')">GP</button>
                        </td>
                    </tr>
                \`;
            }).join('');
        }

        // ============================================================
        // EMSX ORDER EXECUTION
        // ============================================================
        function populateEmsxDropdown() {
            const sel = document.getElementById('emsxTickerSelect');
            const cur = sel.value;
            sel.innerHTML = quoteList.map(q => \`<option value="\${q.symbol}">\${q.symbol} - \${q.name} [\${q.category}]</option>\`).join('');
            if (cur) sel.value = cur;
            else if (quoteList.length > 1) sel.value = quoteList[1].symbol;

            // Also populate universe table in EMSX
            const ubody = document.getElementById('emsxUniverseBody');
            ubody.innerHTML = quoteList.map(q => {
                const cls = q.changePct >= 0 ? 'bbg-green' : 'bbg-red';
                const idrPx = fmtIdr(q.priceIdr || (q.currency === 'USD' ? q.price * usdRate : q.price));
                return \`
                    <tr style="cursor:pointer;" onclick="setEmsxTicker('\${q.symbol}')">
                        <td><strong class="bbg-amber">\${q.symbol}</strong></td>
                        <td class="bbg-white">\${q.name}</td>
                        <td class="bbg-dim" style="font-size:10px;">\${q.category}</td>
                        <td class="bbg-cyan">\${q.currency === 'USD' ? '$'+q.price.toFixed(2) : fmtIdr(q.price)}</td>
                        <td class="bbg-white"><strong>\${idrPx}</strong></td>
                        <td class="\${cls}">\${q.changePct >= 0 ? '+' : ''}\${q.changePct.toFixed(2)}%</td>
                        <td>\${q.currency === 'USD' ? '$'+q.high.toFixed(2) : fmtIdr(q.high)}</td>
                        <td>\${q.currency === 'USD' ? '$'+q.low.toFixed(2) : fmtIdr(q.low)}</td>
                    </tr>
                \`;
            }).join('');

            onEmsxTickerChanged();
        }`;

const newJsSection = `        // ============================================================
        // CATEGORY FILTERING & LIVE SEARCH FOR 218+ ASSETS
        // ============================================================
        let currentUniverseFilter = 'ALL';
        let currentMonitorFilter = 'ALL';

        function setUniverseFilter(cat) {
            currentUniverseFilter = cat;
            document.querySelectorAll('#view-emsx .cat-pill').forEach(btn => {
                btn.classList.toggle('active', btn.textContent.includes(cat) || (cat === 'ALL' && btn.textContent.includes('ALL')));
            });
            filterEmsxUniverse();
        }

        function setMonitorFilter(cat) {
            currentMonitorFilter = cat;
            document.querySelectorAll('#view-monitor .cat-pill').forEach(btn => {
                btn.classList.toggle('active', btn.textContent.includes(cat) || (cat === 'ALL' && btn.textContent.includes('ALL')));
            });
            renderMonitorGrid();
        }

        // ============================================================
        // QUICK TEST BUY (DMA SIMULATION FOR ANY ASSET)
        // ============================================================
        async function testBuy(sym, qty = 1) {
            showPopup(\`[TEST-BUY DMA] SUBMITTING BUY ORDER FOR '\${sym}'...\`);
            try {
                const res = await fetch(\`/api/test-buy?symbol=\${encodeURIComponent(sym)}&qty=\${qty}\`);
                const data = await res.json();
                if (data.success) {
                    showPopup(data.message);
                    await fetchPortfolioData();
                    await fetchQuotesData();
                } else {
                    showPopup(\`[REJECTED] \${data.error || 'Test-buy failed'}\`, true);
                }
            } catch (e) {
                showPopup(\`[ERROR] \${e.message}\`, true);
            }
        }

        function testBuyCurrentEmsx() {
            const sym = document.getElementById('emsxTickerSelect').value;
            if (!sym) return;
            const qtyVal = parseFloat(document.getElementById('emsxQtyInput').value) || 1;
            testBuy(sym, qtyVal);
        }

        function renderMonitorGrid() {
            const tbody = document.getElementById('monitorGridBody');
            const searchEl = document.getElementById('monitorSearchInput');
            const term = searchEl ? searchEl.value.trim().toUpperCase() : '';

            let filtered = quoteList.filter(q => {
                if (currentMonitorFilter !== 'ALL') {
                    if (currentMonitorFilter === 'Index') {
                        if (!q.category.includes('Index') && !q.category.includes('Rates') && !q.symbol.startsWith('^')) return false;
                    } else if (q.category !== currentMonitorFilter) {
                        return false;
                    }
                }
                if (term) {
                    const match = (q.symbol + ' ' + q.name + ' ' + q.category).toUpperCase();
                    if (!match.includes(term)) return false;
                }
                return true;
            });

            const countEl = document.getElementById('monAssetCount');
            if (countEl) countEl.textContent = \`SHOWING: \${filtered.length} / \${quoteList.length} ASSETS\`;

            tbody.innerHTML = filtered.map(q => {
                const isUp = q.changePct >= 0;
                const cls = isUp ? 'bbg-green' : 'bbg-red';
                const sign = isUp ? '+' : '';
                const origPx = q.currency === 'USD' ? '$' + q.price.toFixed(2) : fmtIdr(q.price);
                const idrPx = fmtIdr(q.priceIdr || (q.currency === 'USD' ? q.price * usdRate : q.price));

                return \`
                    <tr>
                        <td><strong class="bbg-amber" style="cursor:pointer;" onclick="openGp('\${q.symbol}')">\${q.symbol}</strong></td>
                        <td class="bbg-white">\${q.name}</td>
                        <td class="bbg-dim" style="font-size:10px;">\${q.category}</td>
                        <td class="bbg-cyan">\${origPx}</td>
                        <td class="bbg-white"><strong>\${idrPx}</strong></td>
                        <td class="\${cls}">\${sign}\${fmtIdr(q.change)}</td>
                        <td class="\${cls}">\${sign}\${q.changePct.toFixed(2)}%</td>
                        <td>\${q.currency === 'USD' ? '$' + q.high.toFixed(2) : fmtIdr(q.high)}</td>
                        <td>\${q.currency === 'USD' ? '$' + q.low.toFixed(2) : fmtIdr(q.low)}</td>
                        <td style="text-align:center; white-space:nowrap;">
                            <button class="btn-act" style="background:#003311; border:1px solid #00AA44; color:#00FF66; font-weight:bold; margin-right:3px;" onclick="testBuy('\${q.symbol}')" title="Uji beli langsung 1 lot">+BUY 1x</button>
                            <button class="btn-act" onclick="loadEmsxAsset('\${q.symbol}', 'BUY')">TRADE &lt;F3&gt;</button>
                            <button class="btn-act" onclick="openGp('\${q.symbol}')">GP</button>
                        </td>
                    </tr>
                \`;
            }).join('');
        }

        // ============================================================
        // EMSX ORDER EXECUTION
        // ============================================================
        function populateEmsxDropdown() {
            const sel = document.getElementById('emsxTickerSelect');
            const cur = sel.value;

            // Group quotes into categories for clean selection
            const categories = [
                { name: 'SAHAM INDONESIA (IDX)', filter: q => q.category === 'Saham Indo' },
                { name: 'WALL STREET & US MEGA-CAPS', filter: q => q.category === 'Saham US' },
                { name: 'GLOBAL ADRs & ASIAN GIANTS', filter: q => q.category === 'Saham Global' },
                { name: 'TOP CRYPTOCURRENCIES', filter: q => q.category === 'Crypto' },
                { name: 'GLOBAL COMMODITIES & FUTURES', filter: q => q.category === 'Komoditas' },
                { name: 'FOREX CURRENCY PAIRS', filter: q => q.category === 'Forex' },
                { name: 'GLOBAL INDICES & BENCHMARKS', filter: q => q.category.includes('Index') || q.category.includes('Rates') || q.symbol.startsWith('^') }
            ];

            let html = '';
            categories.forEach(cat => {
                const items = quoteList.filter(cat.filter);
                if (items.length > 0) {
                    html += \`<optgroup label="-- \${cat.name} (\${items.length}) --">\`;
                    items.forEach(q => {
                        const pxStr = q.currency === 'USD' ? '$' + q.price.toFixed(2) : fmtIdr(q.price) + ' IDR';
                        html += \`<option value="\${q.symbol}">\${q.symbol} - \${q.name} [\${pxStr}]</option>\`;
                    });
                    html += \`</optgroup>\`;
                }
            });

            if (!html) {
                html = quoteList.map(q => \`<option value="\${q.symbol}">\${q.symbol} - \${q.name} [\${q.category}]</option>\`).join('');
            }
            sel.innerHTML = html;

            if (cur && quoteList.some(x => x.symbol === cur)) {
                sel.value = cur;
            } else if (quoteList.length > 0) {
                sel.value = quoteList[0].symbol;
            }

            filterEmsxUniverse();
            onEmsxTickerChanged();
        }

        function filterEmsxUniverse() {
            const inEl = document.getElementById('emsxSearchInput');
            const term = inEl ? inEl.value.trim().toUpperCase() : '';

            let filtered = quoteList.filter(q => {
                if (currentUniverseFilter !== 'ALL') {
                    if (currentUniverseFilter === 'Index') {
                        if (!q.category.includes('Index') && !q.category.includes('Rates') && !q.symbol.startsWith('^')) return false;
                    } else if (q.category !== currentUniverseFilter) {
                        return false;
                    }
                }
                if (term) {
                    const match = (q.symbol + ' ' + q.name + ' ' + q.category).toUpperCase();
                    if (!match.includes(term)) return false;
                }
                return true;
            });

            const countEl = document.getElementById('emsxAssetCount');
            if (countEl) countEl.textContent = \`SHOWING: \${filtered.length} / \${quoteList.length} ASSETS\`;

            const ubody = document.getElementById('emsxUniverseBody');
            ubody.innerHTML = filtered.map(q => {
                const cls = q.changePct >= 0 ? 'bbg-green' : 'bbg-red';
                const idrPx = fmtIdr(q.priceIdr || (q.currency === 'USD' ? q.price * usdRate : q.price));
                return \`
                    <tr style="cursor:pointer;" onclick="setEmsxTicker('\${q.symbol}')">
                        <td><strong class="bbg-amber">\${q.symbol}</strong></td>
                        <td class="bbg-white">\${q.name}</td>
                        <td class="bbg-dim" style="font-size:10px;">\${q.category}</td>
                        <td class="bbg-cyan">\${q.currency === 'USD' ? '$' + q.price.toFixed(2) : fmtIdr(q.price)}</td>
                        <td class="bbg-white"><strong>\${idrPx}</strong></td>
                        <td class="\${cls}">\${q.changePct >= 0 ? '+' : ''}\${q.changePct.toFixed(2)}%</td>
                        <td>\${q.currency === 'USD' ? '$' + q.high.toFixed(2) : fmtIdr(q.high)}</td>
                        <td>\${q.currency === 'USD' ? '$' + q.low.toFixed(2) : fmtIdr(q.low)}</td>
                        <td style="text-align:center;">
                            <button class="btn-act" style="background:#003311; border:1px solid #00AA44; color:#00FF66; font-weight:bold; padding:1px 6px;" onclick="event.stopPropagation(); testBuy('\${q.symbol}')" title="Uji beli langsung 1 lot">+BUY 1x</button>
                        </td>
                    </tr>
                \`;
            }).join('');
        }`;

content = doReplace(content, oldJsSection, newJsSection, 'renderMonitorGrid & populateEmsxDropdown & testBuy JS');

// 7. Command line support for TESTBUY
const oldCmdSection = `            if (raw === 'PORT' || raw === 'PRTU' || raw === '1') {`;
const newCmdSection = `            if (raw.startsWith('TESTBUY ') || raw.startsWith('TBUY ') || raw.startsWith('BUY ')) {
                const parts = raw.split(/\\s+/);
                let sym = parts[1];
                let qty = 1;
                if (parts.length >= 3 && !isNaN(parseFloat(parts[1]))) {
                    qty = parseFloat(parts[1]);
                    sym = parts[2];
                }
                if (sym) {
                    testBuy(sym, qty);
                    return;
                }
            }

            if (raw === 'PORT' || raw === 'PRTU' || raw === '1') {`;

content = doReplace(content, oldCmdSection, newCmdSection, 'Command line direct TESTBUY handler');

// Restore original CRLF if needed
if (isCrlf) {
    content = content.replace(/\n/g, '\r\n');
}

fs.writeFileSync(filePath, content, 'utf8');
console.log('ALL UPDATES APPLIED CLEANLY AND SAFELY!');
