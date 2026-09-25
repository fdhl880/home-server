// Script to apply complete Order Types logic, Working Orders Blotter, and 5000+ pagination in public/index.html
const fs = require('fs');
const path = require('path');

const filePath = path.join(__dirname, '../public/index.html');
let html = fs.readFileSync(filePath, 'utf8');

// Replace calcEmsx and executeEmsxOrder with full support for Limit, Stop, TIF
const oldCalcAndExec = `        function calcEmsx() {
            const sym = document.getElementById('emsxTickerSelect').value;
            const q = quoteList.find(x => x.symbol === sym);
            if (!q) return;

            const inputVal = parseFloat(document.getElementById('emsxQtyInput').value) || 0;
            const isIndo = q.symbol.includes('.JK') || q.category === 'Saham Indo';
            const actualQty = isIndo ? inputVal * 100 : inputVal;

            const price = q.price;
            const priceInIdr = (q.currency === 'USD') ? price * usdRate : price;

            const gross = actualQty * priceInIdr;
            const comm = gross * 0.0015;
            const net = emsxSide === 'BUY' ? gross + comm : gross - comm;
            const postCash = emsxSide === 'BUY' ? portState.cash - net : portState.cash + net;

            document.getElementById('emsxGrossOut').textContent = \`\${fmtIdr(gross)} IDR\`;
            document.getElementById('emsxCommOut').textContent = \`\${fmtIdr(comm)} IDR\`;
            document.getElementById('emsxNetOut').textContent = \`\${fmtIdr(net)} IDR\`;
            document.getElementById('emsxCashOut').textContent = \`\${fmtIdr(portState.cash)} IDR\`;

            const postEl = document.getElementById('emsxPostCashOut');
            postEl.textContent = \`\${fmtIdr(postCash)} IDR\`;
            postEl.className = postCash >= 0 ? 'bbg-white' : 'bbg-red';
        }

        function presetEmsxCash(pct) {
            const sym = document.getElementById('emsxTickerSelect').value;
            const q = quoteList.find(x => x.symbol === sym);
            if (!q) return;

            const budget = portState.cash * pct;
            const priceInIdr = (q.currency === 'USD') ? q.price * usdRate : q.price;
            if (priceInIdr <= 0) return;

            let units = Math.floor(budget / (priceInIdr * 1.0015));
            const isIndo = q.symbol.includes('.JK') || q.category === 'Saham Indo';

            if (isIndo) {
                let lots = Math.floor(units / 100);
                if (lots < 1) lots = 1;
                document.getElementById('emsxQtyInput').value = lots;
            } else {
                if (units < 1) units = 1;
                document.getElementById('emsxQtyInput').value = units;
            }
            calcEmsx();
        }

        async function executeEmsxOrder() {
            const sym = document.getElementById('emsxTickerSelect').value;
            const q = quoteList.find(x => x.symbol === sym);
            if (!q) return;

            const inputVal = parseFloat(document.getElementById('emsxQtyInput').value);
            if (!inputVal || inputVal <= 0) {
                showPopup('REJECTED: Quantity must be greater than zero.', true);
                return;
            }

            const isIndo = q.symbol.includes('.JK') || q.category === 'Saham Indo';
            const actualQty = isIndo ? inputVal * 100 : inputVal;

            const queueAllowed = document.getElementById('emsxQueueCheckbox') ? document.getElementById('emsxQueueCheckbox').checked : true;
            const payload = {
                type: emsxSide,
                symbol: q.symbol,
                name: q.name,
                category: q.category,
                qty: actualQty,
                price: q.price,
                currency: q.currency,
                queueIfClosed: queueAllowed
            };

            try {
                const res = await fetch('/api/portfolio/trade', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const d = await res.json();
                if (res.ok && d.success) {
                    if (d.trade && d.trade.status && d.trade.status.includes('QUEUED')) {
                        showPopup(\`⏳ DMA ORDER QUEUED: \${d.trade.type} \${d.trade.qty} \${d.trade.symbol} dimasukkan ke antrean pembukaan pasar (\${d.trade.exchange} TUTUP)\`, false);
                    } else {
                        showPopup(\`DMA FILL CONFIRMED: \${d.trade.type} \${d.trade.qty} \${d.trade.symbol} @ \${fmtIdr(d.trade.priceInIdr)} IDR\`, false);
                    }
                    await fetchPortfolioData();
                    showView('summary');
                } else {
                    showPopup(\`DMA REJECTED: \${d.error || 'Execution failed'}\`, true);
                }
            } catch (e) {
                showPopup('COMMUNICATION ERROR: ' + e.message, true);
            }
        }`;

const newCalcAndExec = `        // ============================================================
        // EMSX ORDER TYPES & TIME IN FORCE (TIF)
        // ============================================================
        let emsxOrderType = 'MARKET';
        let emsxTif = 'GTC';

        function setEmsxOrderType(ot) {
            emsxOrderType = ot;
            document.querySelectorAll('.btn-ordertype').forEach(b => b.classList.remove('active'));
            const btnMap = {
                'MARKET': 'btnOtMarket',
                'LIMIT': 'btnOtLimit',
                'STOP': 'btnOtStop',
                'STOP_LIMIT': 'btnOtStopLimit',
                'TRAILING_STOP': 'btnOtTrail'
            };
            if (btnMap[ot]) {
                const el = document.getElementById(btnMap[ot]);
                if (el) el.classList.add('active');
            }

            const limitRow = document.getElementById('emsxLimitPriceRow');
            const stopRow = document.getElementById('emsxStopPriceRow');

            if (ot === 'LIMIT' || ot === 'STOP_LIMIT') {
                if (limitRow) limitRow.style.display = 'flex';
                const sym = document.getElementById('emsxTickerSelect').value;
                const q = quoteList.find(x => x.symbol === sym);
                const limitIn = document.getElementById('emsxLimitPriceInput');
                if (q && limitIn && (!limitIn.value || parseFloat(limitIn.value) <= 0)) {
                    limitIn.value = q.price;
                }
            } else {
                if (limitRow) limitRow.style.display = 'none';
            }

            if (ot === 'STOP' || ot === 'STOP_LIMIT') {
                if (stopRow) stopRow.style.display = 'flex';
                const sym = document.getElementById('emsxTickerSelect').value;
                const q = quoteList.find(x => x.symbol === sym);
                const stopIn = document.getElementById('emsxStopPriceInput');
                if (q && stopIn && (!stopIn.value || parseFloat(stopIn.value) <= 0)) {
                    stopIn.value = (q.price * 0.95).toFixed(2);
                }
            } else {
                if (stopRow) stopRow.style.display = 'none';
            }

            calcEmsx();
        }

        function adjustLimitPct(pct) {
            const inEl = document.getElementById('emsxLimitPriceInput');
            if (!inEl) return;
            const cur = parseFloat(inEl.value) || 0;
            if (cur > 0) {
                const nextVal = cur * (1 + pct);
                inEl.value = nextVal > 100 ? nextVal.toFixed(2) : nextVal.toFixed(4);
                calcEmsx();
            }
        }

        function resetLimitToMarket() {
            const sym = document.getElementById('emsxTickerSelect').value;
            const q = quoteList.find(x => x.symbol === sym);
            const inEl = document.getElementById('emsxLimitPriceInput');
            if (q && inEl) {
                inEl.value = q.price;
                calcEmsx();
            }
        }

        function setEmsxTif(tif) {
            emsxTif = tif;
            document.querySelectorAll('.btn-tif').forEach(b => b.classList.remove('active'));
            const tifMap = {
                'GTC': 'btnTifGtc',
                'DAY': 'btnTifDay',
                'IOC': 'btnTifIoc',
                'FOK': 'btnTifFok'
            };
            if (tifMap[tif]) {
                const el = document.getElementById(tifMap[tif]);
                if (el) el.classList.add('active');
            }
        }

        function calcEmsx() {
            const sym = document.getElementById('emsxTickerSelect').value;
            const q = quoteList.find(x => x.symbol === sym);
            if (!q) return;

            const inputVal = parseFloat(document.getElementById('emsxQtyInput').value) || 0;
            const isIndo = q.symbol.includes('.JK') || q.category === 'Saham Indo';
            const actualQty = isIndo ? inputVal * 100 : inputVal;

            let price = q.price;
            if (emsxOrderType === 'LIMIT' || emsxOrderType === 'STOP_LIMIT') {
                const limitIn = document.getElementById('emsxLimitPriceInput');
                if (limitIn && parseFloat(limitIn.value) > 0) {
                    price = parseFloat(limitIn.value);
                }
            }

            const priceInIdr = (q.currency === 'USD') ? price * usdRate : price;
            const gross = actualQty * priceInIdr;
            const comm = gross * 0.0015;
            const net = emsxSide === 'BUY' ? gross + comm : gross - comm;
            const postCash = emsxSide === 'BUY' ? portState.cash - net : portState.cash + net;

            document.getElementById('emsxGrossOut').textContent = \`\${fmtIdr(gross)} IDR\`;
            document.getElementById('emsxCommOut').textContent = \`\${fmtIdr(comm)} IDR\`;
            document.getElementById('emsxNetOut').textContent = \`\${fmtIdr(net)} IDR\`;
            document.getElementById('emsxCashOut').textContent = \`\${fmtIdr(portState.cash)} IDR\`;

            const postEl = document.getElementById('emsxPostCashOut');
            postEl.textContent = \`\${fmtIdr(postCash)} IDR\`;
            postEl.className = postCash >= 0 ? 'bbg-white' : 'bbg-red';
        }

        function presetEmsxCash(pct) {
            const sym = document.getElementById('emsxTickerSelect').value;
            const q = quoteList.find(x => x.symbol === sym);
            if (!q) return;

            const budget = portState.cash * pct;
            let price = q.price;
            if (emsxOrderType === 'LIMIT' && document.getElementById('emsxLimitPriceInput') && parseFloat(document.getElementById('emsxLimitPriceInput').value) > 0) {
                price = parseFloat(document.getElementById('emsxLimitPriceInput').value);
            }
            const priceInIdr = (q.currency === 'USD') ? price * usdRate : price;
            if (priceInIdr <= 0) return;

            let units = Math.floor(budget / (priceInIdr * 1.0015));
            const isIndo = q.symbol.includes('.JK') || q.category === 'Saham Indo';

            if (isIndo) {
                let lots = Math.floor(units / 100);
                if (lots < 1) lots = 1;
                document.getElementById('emsxQtyInput').value = lots;
            } else {
                if (units < 1) units = 1;
                document.getElementById('emsxQtyInput').value = units;
            }
            calcEmsx();
        }

        async function executeEmsxOrder() {
            const sym = document.getElementById('emsxTickerSelect').value;
            const q = quoteList.find(x => x.symbol === sym);
            if (!q) return;

            const inputVal = parseFloat(document.getElementById('emsxQtyInput').value);
            if (!inputVal || inputVal <= 0) {
                showPopup('REJECTED: Quantity must be greater than zero.', true);
                return;
            }

            const isIndo = q.symbol.includes('.JK') || q.category === 'Saham Indo';
            const actualQty = isIndo ? inputVal * 100 : inputVal;

            let limitVal = null;
            if (emsxOrderType === 'LIMIT' || emsxOrderType === 'STOP_LIMIT') {
                limitVal = parseFloat(document.getElementById('emsxLimitPriceInput').value) || q.price;
            }

            let stopVal = null;
            if (emsxOrderType === 'STOP' || emsxOrderType === 'STOP_LIMIT') {
                stopVal = parseFloat(document.getElementById('emsxStopPriceInput').value) || null;
            }

            const queueAllowed = document.getElementById('emsxQueueCheckbox') ? document.getElementById('emsxQueueCheckbox').checked : true;
            const payload = {
                type: emsxSide,
                orderType: emsxOrderType,
                tif: emsxTif,
                symbol: q.symbol,
                name: q.name,
                category: q.category,
                qty: actualQty,
                price: q.price,
                limitPrice: limitVal,
                stopPrice: stopVal,
                currency: q.currency,
                queueIfClosed: queueAllowed
            };

            try {
                const res = await fetch('/api/portfolio/trade', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const d = await res.json();
                if (res.ok && d.success) {
                    showPopup(d.message, false);
                    await fetchPortfolioData();
                    showView('emsx');
                } else {
                    showPopup(\`DMA REJECTED: \${d.error || 'Execution failed'}\`, true);
                }
            } catch (e) {
                showPopup('COMMUNICATION ERROR: ' + e.message, true);
            }
        }`;

if (html.includes(oldCalcAndExec)) {
    html = html.replace(oldCalcAndExec, newCalcAndExec);
}

// 2. Add Working Orders rendering & cancelOrder function
const workingOrdersLogic = `
        // ============================================================
        // EMSX WORKING ORDERS BLOTTER & CANCEL ACTION
        // ============================================================
        function renderWorkingOrders(workingOrders = []) {
            const tbody = document.getElementById('emsxWorkingOrdersBody');
            const countEl = document.getElementById('workingOrdersCount');
            if (!tbody) return;

            if (!workingOrders || workingOrders.length === 0) {
                tbody.innerHTML = \`<tr><td colspan="12" style="text-align:center; color:#666; padding:10px;">[ORDER BOOK CLEAR] Tidak ada working limit order yang aktif. Semua order DMA telah terisi (FILLED).</td></tr>\`;
                if (countEl) countEl.textContent = '0 WORKING ORDERS';
                return;
            }

            if (countEl) countEl.textContent = \`\${workingOrders.length} ACTIVE WORKING ORDERS\`;

            tbody.innerHTML = workingOrders.map(o => {
                const sideCls = o.type === 'BUY' ? 'bbg-green' : 'bbg-red';
                const isUsd = (o.currency === 'USD');
                const limitStr = o.limitPrice ? (isUsd ? '$' + o.limitPrice.toFixed(2) : fmtIdr(o.limitPrice)) : (o.stopPrice ? 'STOP ' + (isUsd ? '$' + o.stopPrice.toFixed(2) : fmtIdr(o.stopPrice)) : 'MKT');
                const quote = quoteList.find(q => q.symbol === o.symbol);
                const curPxStr = quote ? (isUsd ? '$' + quote.price.toFixed(2) : fmtIdr(quote.price)) : '-';
                const timeStr = o.timestamp ? new Date(o.timestamp).toLocaleTimeString('id-ID') : '-';

                return \`
                    <tr>
                        <td><strong class="bbg-amber">\${o.id}</strong></td>
                        <td>\${timeStr}</td>
                        <td><strong class="bbg-cyan">\${o.symbol}</strong></td>
                        <td class="bbg-white">\${o.name}</td>
                        <td class="\${sideCls}" style="font-weight:bold;">\${o.type}</td>
                        <td>\${o.orderType}</td>
                        <td class="bbg-amber" style="font-weight:bold;">\${limitStr}</td>
                        <td class="bbg-white">\${curPxStr}</td>
                        <td>\${o.qty}</td>
                        <td class="bbg-cyan">\${o.tif || 'GTC'}</td>
                        <td><span style="background:#332200; border:1px solid #FF8800; color:#FFB000; padding:1px 5px; font-size:9.5px; font-weight:bold;">\${o.status}</span></td>
                        <td style="text-align:center;">
                            <button class="btn-act" style="background:#330000; border:1px solid #FF2233; color:#FF5566; font-weight:bold; padding:1px 6px;" onclick="cancelOrder('\${o.id}')">CANCEL</button>
                        </td>
                    </tr>
                \`;
            }).join('');
        }

        async function cancelOrder(orderId) {
            if (!confirm(\`Batalkan Working Order \${orderId}?\`)) return;
            showPopup(\`[EMSX CANCEL] Membatalkan order #\${orderId}...\`);
            try {
                const res = await fetch('/api/portfolio/orders/cancel', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ orderId })
                });
                const d = await res.json();
                if (d.success) {
                    showPopup(d.message);
                    await fetchPortfolioData();
                } else {
                    showPopup(d.error || 'Gagal membatalkan order', true);
                }
            } catch (e) {
                showPopup('Error: ' + e.message, true);
            }
        }
`;

if (!html.includes('renderWorkingOrders(workingOrders = [])')) {
    html = html.replace('function loadEmsxAsset(sym, side = \'BUY\') {', workingOrdersLogic + '\n        function loadEmsxAsset(sym, side = \'BUY\') {');
}

// 3. Update fetchPortfolioData to fetch working orders
const oldFetchPort = `                renderSummary(data);
                renderHoldingsTable(data.holdings);
                renderBlotter(data.trades);`;

const newFetchPort = `                renderSummary(data);
                renderHoldingsTable(data.holdings);
                renderBlotter(data.trades);
                renderWorkingOrders(data.workingOrders || []);`;

if (html.includes(oldFetchPort)) {
    html = html.replace(oldFetchPort, newFetchPort);
}

// 4. Update Pagination for Market Monitor & EMSX Universe
const oldRenderMon = `        function renderMonitorGrid() {
            const tbody = document.getElementById('monitorGridBody');
            const searchEl = document.getElementById('monitorSearchInput');
            const term = searchEl ? searchEl.value.trim().toUpperCase() : '';

            let filtered = quoteList.filter(q => {
                if (currentMonitorFilter !== 'ALL') {
                    if (currentMonitorFilter === 'Space Tech') {
                        if (!q.category.includes('Space Tech') && !q.category.includes('Pre-IPO') && !['SPACEX', 'OPENAI', 'DXYZ', 'RKLB', 'ASTS', 'LUNR', 'ARKX', 'UFO', 'PL', 'RDW', 'MNTS', 'BKSY', 'SPCE', 'STRIPE', 'ANTHROPIC', 'BYTEDANCE'].includes(q.symbol)) return false;
                    } else if (currentMonitorFilter === 'Index') {
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
                const cls = q.changePct >= 0 ? 'bbg-green' : 'bbg-red';
                const sign = q.changePct >= 0 ? '+' : '';
                const idrPx = fmtIdr(q.priceIdr || (q.currency === 'USD' ? q.price * usdRate : q.price));
                return \`
                    <tr>
                        <td><strong class="bbg-amber">\${q.symbol}</strong></td>
                        <td class="bbg-white">\${q.name}</td>
                        <td class="bbg-dim" style="font-size:10px;">\${q.category}</td>
                        <td class="bbg-cyan">\${q.currency === 'USD' ? '$' + q.price.toFixed(2) : fmtIdr(q.price)}</td>
                        <td class="bbg-white"><strong>\${idrPx}</strong></td>
                        <td class="\${cls}">\${sign}\${fmtIdr(q.change)}</td>
                        <td class="\${cls}">\${sign}\${q.changePct.toFixed(2)}%</td>
                        <td>\${q.currency === 'USD' ? '$' + q.high.toFixed(2) : fmtIdr(q.high)}</td>
                        <td>\${q.currency === 'USD' ? '$' + q.low.toFixed(2) : fmtIdr(q.low)}</td>
                        <td style="text-align:center; white-space:nowrap;">
                            <button class="btn-act" style="background:#003311; border:1px solid #00AA44; color:#00FF66; font-weight:bold; margin-right:3px;" onclick="testBuy('\${q.symbol}')" title="Eksekusi beli langsung 1 lot via DMA">+BUY 1x</button>
                            <button class="btn-act" onclick="loadEmsxAsset('\${q.symbol}', 'BUY')">TRADE &lt;F3&gt;</button>
                            <button class="btn-act" onclick="openGp('\${q.symbol}')">GP</button>
                        </td>
                    </tr>
                \`;
            }).join('');
        }`;

const newRenderMon = `        let monCurrentPage = 1;
        let monPageSize = 100;
        let emsxCurrentPage = 1;
        let emsxPageSize = 100;

        function changeMonPage(delta) {
            monCurrentPage += delta;
            if (monCurrentPage < 1) monCurrentPage = 1;
            renderMonitorGrid();
        }

        function changeMonPageSize(sz) {
            monPageSize = parseInt(sz) || 100;
            monCurrentPage = 1;
            renderMonitorGrid();
        }

        function changeEmsxPage(delta) {
            emsxCurrentPage += delta;
            if (emsxCurrentPage < 1) emsxCurrentPage = 1;
            filterEmsxUniverse();
        }

        function changeEmsxPageSize(sz) {
            emsxPageSize = parseInt(sz) || 100;
            emsxCurrentPage = 1;
            filterEmsxUniverse();
        }

        function renderMonitorGrid() {
            const tbody = document.getElementById('monitorGridBody');
            const searchEl = document.getElementById('monitorSearchInput');
            const term = searchEl ? searchEl.value.trim().toUpperCase() : '';

            let filtered = quoteList.filter(q => {
                if (currentMonitorFilter !== 'ALL') {
                    if (currentMonitorFilter === 'Space Tech') {
                        if (!q.category.includes('Space Tech') && !q.category.includes('Pre-IPO') && !['SPACEX', 'SPCX', 'OPENAI', 'DXYZ', 'RKLB', 'ASTS', 'LUNR', 'ARKX', 'UFO', 'PL', 'RDW', 'MNTS', 'BKSY', 'SPCE', 'STRIPE', 'ANTHROPIC', 'BYTEDANCE'].includes(q.symbol)) return false;
                    } else if (currentMonitorFilter === 'Index') {
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

            const totalFiltered = filtered.length;
            const totalPages = Math.ceil(totalFiltered / monPageSize) || 1;
            if (monCurrentPage > totalPages) monCurrentPage = totalPages;
            if (monCurrentPage < 1) monCurrentPage = 1;

            const countEl = document.getElementById('monAssetCount');
            if (countEl) countEl.textContent = \`TOTAL: \${totalFiltered.toLocaleString('id-ID')} ASSETS\`;

            const pageInfoEl = document.getElementById('monPageInfo');
            if (pageInfoEl) pageInfoEl.textContent = \`PAGE \${monCurrentPage} OF \${totalPages} (\${totalFiltered} ASSETS)\`;

            const startIdx = (monCurrentPage - 1) * monPageSize;
            const pageItems = filtered.slice(startIdx, startIdx + monPageSize);

            tbody.innerHTML = pageItems.map(q => {
                const cls = q.changePct >= 0 ? 'bbg-green' : 'bbg-red';
                const sign = q.changePct >= 0 ? '+' : '';
                const idrPx = fmtIdr(q.priceIdr || (q.currency === 'USD' ? q.price * usdRate : q.price));
                return \`
                    <tr>
                        <td><strong class="bbg-amber">\${q.symbol}</strong></td>
                        <td class="bbg-white">\${q.name}</td>
                        <td class="bbg-dim" style="font-size:10px;">\${q.category}</td>
                        <td class="bbg-cyan">\${q.currency === 'USD' ? '$' + q.price.toFixed(2) : fmtIdr(q.price)}</td>
                        <td class="bbg-white"><strong>\${idrPx}</strong></td>
                        <td class="\${cls}">\${sign}\${fmtIdr(q.change)}</td>
                        <td class="\${cls}">\${sign}\${q.changePct.toFixed(2)}%</td>
                        <td>\${q.currency === 'USD' ? '$' + q.high.toFixed(2) : fmtIdr(q.high)}</td>
                        <td>\${q.currency === 'USD' ? '$' + q.low.toFixed(2) : fmtIdr(q.low)}</td>
                        <td style="text-align:center; white-space:nowrap;">
                            <button class="btn-act" style="background:#003311; border:1px solid #00AA44; color:#00FF66; font-weight:bold; margin-right:3px;" onclick="testBuy('\${q.symbol}')" title="Eksekusi beli langsung 1 lot via DMA">+BUY 1x</button>
                            <button class="btn-act" onclick="loadEmsxAsset('\${q.symbol}', 'BUY')">TRADE &lt;F3&gt;</button>
                            <button class="btn-act" onclick="openGp('\${q.symbol}')">GP</button>
                        </td>
                    </tr>
                \`;
            }).join('');
        }`;

if (html.includes(oldRenderMon)) {
    html = html.replace(oldRenderMon, newRenderMon);
}

// 5. Update filterEmsxUniverse with pagination
const oldFilterEmsx = `        function filterEmsxUniverse() {
            const inEl = document.getElementById('emsxSearchInput');
            const term = inEl ? inEl.value.trim().toUpperCase() : '';

            let filtered = quoteList.filter(q => {
                if (currentUniverseFilter !== 'ALL') {
                    if (currentUniverseFilter === 'Space Tech') {
                        if (!q.category.includes('Space Tech') && !q.category.includes('Pre-IPO') && !['SPACEX', 'OPENAI', 'DXYZ', 'RKLB', 'ASTS', 'LUNR', 'ARKX', 'UFO', 'PL', 'RDW', 'MNTS', 'BKSY', 'SPCE', 'STRIPE', 'ANTHROPIC', 'BYTEDANCE'].includes(q.symbol)) return false;
                    } else if (currentUniverseFilter === 'Index') {
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
                            <button class="btn-act" style="background:#003311; border:1px solid #00AA44; color:#00FF66; font-weight:bold; padding:1px 6px;" onclick="event.stopPropagation(); testBuy('\${q.symbol}')" title="Eksekusi beli langsung 1 lot via DMA">+BUY 1x</button>
                        </td>
                    </tr>
                \`;
            }).join('');
        }`;

const newFilterEmsx = `        function filterEmsxUniverse() {
            const inEl = document.getElementById('emsxSearchInput');
            const term = inEl ? inEl.value.trim().toUpperCase() : '';

            let filtered = quoteList.filter(q => {
                if (currentUniverseFilter !== 'ALL') {
                    if (currentUniverseFilter === 'Space Tech') {
                        if (!q.category.includes('Space Tech') && !q.category.includes('Pre-IPO') && !['SPACEX', 'SPCX', 'OPENAI', 'DXYZ', 'RKLB', 'ASTS', 'LUNR', 'ARKX', 'UFO', 'PL', 'RDW', 'MNTS', 'BKSY', 'SPCE', 'STRIPE', 'ANTHROPIC', 'BYTEDANCE'].includes(q.symbol)) return false;
                    } else if (currentUniverseFilter === 'Index') {
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

            const totalFiltered = filtered.length;
            const totalPages = Math.ceil(totalFiltered / emsxPageSize) || 1;
            if (emsxCurrentPage > totalPages) emsxCurrentPage = totalPages;
            if (emsxCurrentPage < 1) emsxCurrentPage = 1;

            const countEl = document.getElementById('emsxAssetCount');
            if (countEl) countEl.textContent = \`TOTAL: \${totalFiltered.toLocaleString('id-ID')} ASSETS\`;

            const pageInfoEl = document.getElementById('emsxPageInfo');
            if (pageInfoEl) pageInfoEl.textContent = \`PAGE \${emsxCurrentPage} OF \${totalPages} (\${totalFiltered} ASSETS)\`;

            const startIdx = (emsxCurrentPage - 1) * emsxPageSize;
            const pageItems = filtered.slice(startIdx, startIdx + emsxPageSize);

            const ubody = document.getElementById('emsxUniverseBody');
            ubody.innerHTML = pageItems.map(q => {
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
                            <button class="btn-act" style="background:#003311; border:1px solid #00AA44; color:#00FF66; font-weight:bold; padding:1px 6px;" onclick="event.stopPropagation(); testBuy('\${q.symbol}')" title="Eksekusi beli langsung 1 lot via DMA">+BUY 1x</button>
                        </td>
                    </tr>
                \`;
            }).join('');
        }`;

if (html.includes(oldFilterEmsx)) {
    html = html.replace(oldFilterEmsx, newFilterEmsx);
}

fs.writeFileSync(filePath, html, 'utf8');
console.log('Successfully updated JavaScript logic for Order Types, Blotter, and 5000+ pagination!');
