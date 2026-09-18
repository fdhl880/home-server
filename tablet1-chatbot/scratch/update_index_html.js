const fs = require('fs');

const indexFile = 'c:\\Users\\Asus\\.antigravity\\tablet-dashboards\\tablet1-chatbot\\public\\index.html';
let content = fs.readFileSync(indexFile, 'utf8');

// 1. Text changes requested by user:
// "itu fadhil alpha ganti jadid fadhil muhammad syafiq lubis kemudian itu yg tulisan awal 200 jt hapus"
content = content.replace(
    'PORTFOLIO &amp; RISK ANALYTICS // PORTFOLIO: FADHIL MUHAMMAD SYAFIQ LUBIS(IDR)',
    'PORTFOLIO &amp; RISK ANALYTICS // PORTFOLIO: FADHIL MUHAMMAD SYAFIQ LUBIS (IDR)'
);

content = content.replace(
    '<span class="p-metric-sub" id="sReturn">Return: +0.00% (Awal: Rp 200 Jt)</span>',
    '<span class="p-metric-sub" id="sReturn">Return: +0.00%</span>'
);

content = content.replace(
    '[NO ACTIVE POSITIONS] Portofolio Anda memiliki modal Rp 200.000.000 (100% Cash).',
    '[NO ACTIVE POSITIONS] Portofolio FADHIL MUHAMMAD SYAFIQ LUBIS (100% Cash).'
);

content = content.replace(
    '<span class="bbg-cyan">ACCOUNT: FADHIL-ALPHA-200M | ROUTE: BEST-EXEC</span>',
    '<span class="bbg-cyan">ACCOUNT: FADHIL MUHAMMAD SYAFIQ LUBIS | ROUTE: BEST-EXEC</span>'
);

content = content.replace(
    'Portfolio: FADHIL-ALPHA-200M | Modal: Rp 200.000.000.',
    'Portfolio: FADHIL MUHAMMAD SYAFIQ LUBIS.'
);

content = content.replace(
    `onclick="askAi('Berikan rekomendasi alokasi modal Rp 200 Juta saya secara terperinci.')">Rekomendasi\n                        Alokasi 200 Juta</button>`,
    `onclick="askAi('Berikan rekomendasi alokasi portofolio FADHIL MUHAMMAD SYAFIQ LUBIS secara terperinci.')">Rekomendasi Alokasi Portofolio</button>`
);

content = content.replace(
    `<p><strong class="bbg-amber">1&lt;GO&gt; PORT</strong> - Portfolio &amp; Risk Analytics (Modal Rp 200\n                    Juta)</p>`,
    `<p><strong class="bbg-amber">1&lt;GO&gt; PORT</strong> - Portfolio &amp; Risk Analytics</p>`
);

content = content.replace(
    'retEl.textContent = `Return: ${fmtPct(portState.overallReturn)} (Awal: Rp 200 Jt)`;',
    'retEl.textContent = `Return: ${fmtPct(portState.overallReturn)}`;'
);

content = content.replace(
    '[NO ACTIVE POSITIONS] Portofolio Anda memiliki modal Rp 200.000.000 (100% Cash).<br>',
    '[NO ACTIVE POSITIONS] Portofolio FADHIL MUHAMMAD SYAFIQ LUBIS (100% Cash).<br>'
);

// 2. Add category pill styling in CSS
if (!content.includes('.cat-pill-bar')) {
    const cssToInsert = `
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
    content = content.replace('/* NOTIFICATION TOAST */', cssToInsert + '\n        /* NOTIFICATION TOAST */');
}

// 3. Add Category Filter UI to VIEW 3: EMSX TRADEABLE ASSET UNIVERSE
const emsxUniverseOldHeader = `<div class="sec-title" style="display:flex; justify-content:space-between; align-items:center;">
                <span>TRADEABLE ASSET UNIVERSE (CLICK ROW TO LOAD INTO EMSX)</span>
                <div style="display:flex; gap:8px; align-items:center;">
                    <input type="text" id="emsxSearchInput" oninput="filterEmsxUniverse()" class="bbg-input"
                        placeholder="FILTER UNIVERSE..."
                        style="width:220px; font-size:10.5px; padding:2px 6px; text-transform:uppercase;">
                    <span class="bbg-cyan" style="font-size:10px;">B-PIPE STREAMING</span>
                </div>
            </div>`;

const emsxUniverseNewHeader = `<div class="sec-title" style="display:flex; justify-content:space-between; align-items:center;">
                <span>TRADEABLE ASSET UNIVERSE // 215+ GLOBAL INSTRUMENTS (CLICK ROW TO LOAD)</span>
                <div style="display:flex; gap:8px; align-items:center;">
                    <input type="text" id="emsxSearchInput" oninput="filterEmsxUniverse()" class="bbg-input"
                        placeholder="SEARCH ANY TICKER OR NAME..."
                        style="width:230px; font-size:10.5px; padding:2px 6px; text-transform:uppercase;">
                    <span class="bbg-cyan" style="font-size:10px;">B-PIPE DMA GATEWAY</span>
                </div>
            </div>
            <div class="cat-pill-bar">
                <button class="cat-pill active" onclick="setUniverseFilter('ALL')">ALL (215+)</button>
                <button class="cat-pill" onclick="setUniverseFilter('Saham Indo')">IDX INDONESIA (66)</button>
                <button class="cat-pill" onclick="setUniverseFilter('Saham US')">WALL STREET (68)</button>
                <button class="cat-pill" onclick="setUniverseFilter('Saham Global')">GLOBAL ADRs (10)</button>
                <button class="cat-pill" onclick="setUniverseFilter('Crypto')">CRYPTO (30)</button>
                <button class="cat-pill" onclick="setUniverseFilter('Komoditas')">KOMODITAS (16)</button>
                <button class="cat-pill" onclick="setUniverseFilter('Forex')">FOREX (15)</button>
                <button class="cat-pill" onclick="setUniverseFilter('Index')">INDICES & RATES (10)</button>
                <span class="cat-pill-count" id="emsxAssetCount">SHOWING: 215 ASSETS</span>
            </div>`;

content = content.replace(emsxUniverseOldHeader, emsxUniverseNewHeader);

// 4. Add Category Filter UI to VIEW 5: MARKET MONITOR
const monitorOldHeader = `<div class="sec-title">
                <span>-- GLOBAL MULTI-ASSET MARKET MONITOR (EQUITIES, CRYPTO, COMMODITIES, FOREX) --</span>
                <button class="btn-act" onclick="fetchQuotesData()">PULL LIVE DATA &lt;GO&gt;</button>
            </div>`;

const monitorNewHeader = `<div class="sec-title" style="display:flex; justify-content:space-between; align-items:center;">
                <span>-- GLOBAL MULTI-ASSET MARKET MONITOR (215+ ASSETS ACROSS ALL EXCHANGES) --</span>
                <div style="display:flex; gap:8px; align-items:center;">
                    <input type="text" id="monitorSearchInput" oninput="renderMonitorGrid()" class="bbg-input"
                        placeholder="FILTER MONITOR..."
                        style="width:200px; font-size:10.5px; padding:2px 6px; text-transform:uppercase;">
                    <button class="btn-act" onclick="fetchQuotesData()">PULL LIVE DATA &lt;GO&gt;</button>
                </div>
            </div>
            <div class="cat-pill-bar">
                <button class="cat-pill active" onclick="setMonitorFilter('ALL')">ALL (215+)</button>
                <button class="cat-pill" onclick="setMonitorFilter('Saham Indo')">IDX INDONESIA (66)</button>
                <button class="cat-pill" onclick="setMonitorFilter('Saham US')">WALL STREET (68)</button>
                <button class="cat-pill" onclick="setMonitorFilter('Saham Global')">GLOBAL ADRs (10)</button>
                <button class="cat-pill" onclick="setMonitorFilter('Crypto')">CRYPTO (30)</button>
                <button class="cat-pill" onclick="setMonitorFilter('Komoditas')">KOMODITAS (16)</button>
                <button class="cat-pill" onclick="setMonitorFilter('Forex')">FOREX (15)</button>
                <button class="cat-pill" onclick="setMonitorFilter('Index')">INDICES & RATES (10)</button>
                <span class="cat-pill-count" id="monAssetCount">SHOWING: 215 ASSETS</span>
            </div>`;

content = content.replace(monitorOldHeader, monitorNewHeader);

// 5. Update Javascript functions for categorized dropdown, filtering, and pills
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
                        <td>\${q.currency === 'USD' ? '$' + q.high.toFixed(2) : fmtIdr(q.high)}</td>
                        <td>\${q.currency === 'USD' ? '$' + q.low.toFixed(2) : fmtIdr(q.low)}</td>
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
            if (cur && quoteList.some(x => x.symbol === cur)) {
                sel.value = cur;
            } else if (quoteList.length > 0) {
                sel.value = quoteList[0].symbol;
            }

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
                        <td class="bbg-cyan">\${q.currency === 'USD' ? '$' + q.price.toFixed(2) : fmtIdr(q.price)}</td>
                        <td class="bbg-white"><strong>\${idrPx}</strong></td>
                        <td class="\${cls}">\${q.changePct >= 0 ? '+' : ''}\${q.changePct.toFixed(2)}%</td>
                        <td>\${q.currency === 'USD' ? '$' + q.high.toFixed(2) : fmtIdr(q.high)}</td>
                        <td>\${q.currency === 'USD' ? '$' + q.low.toFixed(2) : fmtIdr(q.low)}</td>
                    </tr>
                \`;
            }).join('');

            filterEmsxUniverse();
            onEmsxTickerChanged();
        }

        function filterEmsxUniverse() {
            const inEl = document.getElementById('emsxSearchInput');
            if (!inEl) return;
            const term = inEl.value.trim().toUpperCase();
            const rows = document.querySelectorAll('#emsxUniverseBody tr');
            rows.forEach(row => {
                const txt = row.textContent.toUpperCase();
                row.style.display = term && !txt.includes(term) ? 'none' : '';
            });
        }`;

const newJsSection = `        let currentUniverseFilter = 'ALL';
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
                        <td style="text-align:center;">
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

            // Group quotes by category for institutional elegance
            const categories = [
                { name: 'SAHAM INDONESIA (IDX BLUECHIP & LQ45)', filter: q => q.category === 'Saham Indo' },
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

            // Fallback if none categorized
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
                    </tr>
                \`;
            }).join('');
        }`;

if (content.includes(oldJsSection)) {
    content = content.replace(oldJsSection, newJsSection);
    console.log('Successfully updated JavaScript in index.html');
} else {
    console.error('Failed to locate oldJsSection in index.html');
    process.exit(1);
}

fs.writeFileSync(indexFile, content, 'utf8');
console.log('Successfully updated index.html!');
