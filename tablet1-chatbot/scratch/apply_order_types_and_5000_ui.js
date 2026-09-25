// Script to apply Order Types (Limit/Stop), Working Orders Blotter, and 5000+ pagination in public/index.html
const fs = require('fs');
const path = require('path');

const filePath = path.join(__dirname, '../public/index.html');
let html = fs.readFileSync(filePath, 'utf8');

// 1. Add CSS for Order Types & TIF
const cssToInsert = `
        .btn-ordertype {
            background: #181818;
            color: #888888;
            border: 1px solid #333333;
            font-family: inherit;
            font-size: 10px;
            font-weight: bold;
            padding: 2px 7px;
            cursor: pointer;
        }
        .btn-ordertype.active {
            background: #F39F41;
            color: #000000;
            border-color: #F39F41;
        }
        .btn-tif {
            background: #111111;
            color: #888888;
            border: 1px solid #282828;
            font-size: 9.5px;
            font-weight: bold;
            padding: 1px 6px;
            cursor: pointer;
        }
        .btn-tif.active {
            background: #004455;
            color: #00FFFF;
            border-color: #00EEEE;
        }
`;

if (!html.includes('.btn-ordertype {')) {
    html = html.replace('.btn-side.sell.active {', cssToInsert + '\n        .btn-side.sell.active {');
}

// 2. Update EMSX Left Inputs: add Order Type, Limit Price, Stop Price, TIF
const oldEmsxLines = `<div class="emsx-line">
                            <span class="emsx-label" id="emsxQtyTitle">QUANTITY (LOTS - 1 LOT = 100 SHARES):</span>
                            <div class="emsx-in-cell">
                                <input type="number" id="emsxQtyInput" class="bbg-input" value="10" min="1" step="1" oninput="calcEmsx()">
                            </div>
                        </div>`;

const newEmsxLines = `<div class="emsx-line">
                            <span class="emsx-label">ORDER TYPE:</span>
                            <div class="emsx-in-cell" style="flex-wrap:wrap; gap:3px;">
                                <button class="btn-ordertype active" id="btnOtMarket" onclick="setEmsxOrderType('MARKET')">MARKET</button>
                                <button class="btn-ordertype" id="btnOtLimit" onclick="setEmsxOrderType('LIMIT')">LIMIT</button>
                                <button class="btn-ordertype" id="btnOtStop" onclick="setEmsxOrderType('STOP')">STOP</button>
                                <button class="btn-ordertype" id="btnOtStopLimit" onclick="setEmsxOrderType('STOP_LIMIT')">STOP-LIMIT</button>
                                <button class="btn-ordertype" id="btnOtTrail" onclick="setEmsxOrderType('TRAILING_STOP')">TRAIL</button>
                            </div>
                        </div>
                        <div class="emsx-line" id="emsxLimitPriceRow" style="display:none; background:#0e0a02; border:1px dashed #F39F41; padding:3px 6px; margin:2px 0;">
                            <span class="emsx-label bbg-amber">LIMIT PRICE:</span>
                            <div class="emsx-in-cell">
                                <button class="pct-tag" onclick="adjustLimitPct(-0.02)">-2%</button>
                                <button class="pct-tag" onclick="adjustLimitPct(-0.01)">-1%</button>
                                <input type="number" id="emsxLimitPriceInput" class="bbg-input" style="width:105px; border-color:#FFBB00;" step="any" oninput="calcEmsx()">
                                <button class="pct-tag" onclick="resetLimitToMarket()">MKT</button>
                                <button class="pct-tag" onclick="adjustLimitPct(0.01)">+1%</button>
                                <button class="pct-tag" onclick="adjustLimitPct(0.02)">+2%</button>
                            </div>
                        </div>
                        <div class="emsx-line" id="emsxStopPriceRow" style="display:none; background:#0c0202; border:1px dashed #FF3344; padding:3px 6px; margin:2px 0;">
                            <span class="emsx-label bbg-red">STOP TRIGGER PX:</span>
                            <div class="emsx-in-cell">
                                <input type="number" id="emsxStopPriceInput" class="bbg-input" style="width:110px; border-color:#FF3344;" step="any" oninput="calcEmsx()">
                            </div>
                        </div>
                        <div class="emsx-line">
                            <span class="emsx-label">TIME IN FORCE (TIF):</span>
                            <div class="emsx-in-cell">
                                <button class="btn-tif active" id="btnTifGtc" onclick="setEmsxTif('GTC')">GTC</button>
                                <button class="btn-tif" id="btnTifDay" onclick="setEmsxTif('DAY')">DAY</button>
                                <button class="btn-tif" id="btnTifIoc" onclick="setEmsxTif('IOC')">IOC</button>
                                <button class="btn-tif" id="btnTifFok" onclick="setEmsxTif('FOK')">FOK</button>
                            </div>
                        </div>
                        <div class="emsx-line">
                            <span class="emsx-label" id="emsxQtyTitle">QUANTITY (LOTS - 1 LOT = 100 SHARES):</span>
                            <div class="emsx-in-cell">
                                <input type="number" id="emsxQtyInput" class="bbg-input" value="10" min="1" step="1" oninput="calcEmsx()">
                            </div>
                        </div>`;

if (html.includes(oldEmsxLines)) {
    html = html.replace(oldEmsxLines, newEmsxLines);
}

// 3. Add Working Orders Blotter right below the EMSX Panel
const oldEmsxPanelEnd = `</div>
                </div>
            </div>

            <!-- TRADEABLE ASSETS TABLE -->`;

const newWorkingOrdersBlotter = `</div>
                </div>
            </div>

            <!-- EMSX LIVE WORKING ORDERS BLOTTER -->
            <div class="sec-title" style="display:flex; justify-content:space-between; align-items:center; margin-top:12px;">
                <span>-- EMSX LIVE WORKING ORDERS // PENDING LIMIT &amp; STOP ORDER BOOK --</span>
                <span class="bbg-amber" id="workingOrdersCount" style="font-weight:bold;">0 WORKING ORDERS</span>
            </div>
            <div class="table-frame" style="max-height:160px; margin-bottom:12px;">
                <table class="bbg-tbl">
                    <thead>
                        <tr>
                            <th>ORDER ID</th>
                            <th>TIME (WIB)</th>
                            <th>TICKER</th>
                            <th>SECURITY NAME</th>
                            <th>SIDE</th>
                            <th>TYPE</th>
                            <th>LIMIT / STOP PX</th>
                            <th>LAST MKT PX</th>
                            <th>QTY</th>
                            <th>TIF</th>
                            <th>STATUS</th>
                            <th style="text-align:center;">ACTION</th>
                        </tr>
                    </thead>
                    <tbody id="emsxWorkingOrdersBody">
                        <tr>
                            <td colspan="12" style="text-align:center; color:#666; padding:10px;">
                                [ORDER BOOK CLEAR] Tidak ada working limit order yang aktif. Semua order DMA telah terisi (FILLED).
                            </td>
                        </tr>
                    </tbody>
                </table>
            </div>

            <!-- TRADEABLE ASSETS TABLE -->`;

if (html.includes(oldEmsxPanelEnd)) {
    html = html.replace(oldEmsxPanelEnd, newWorkingOrdersBlotter);
}

// 4. Update Universe Category Pills and Add Pagination Controls for EMSX Universe
const oldEmsxUniverseTitle = `<span>TRADEABLE ASSET UNIVERSE // 1,350+ INSTRUMENTS (CLICK TICKER ATAU +BUY)</span>`;
const newEmsxUniverseTitle = `<span>TRADEABLE ASSET UNIVERSE // 5,000+ INSTRUMENTS (CLICK TICKER TO TRADE)</span>`;
html = html.replace(oldEmsxUniverseTitle, newEmsxUniverseTitle);

const oldEmsxPills = `<div class="cat-pill-bar">
                <button class="cat-pill active" onclick="setUniverseFilter('ALL')">ALL (1,350+)</button>
                <button class="cat-pill" style="border-color:#FF8800; color:#FF8800; font-weight:bold;" onclick="setUniverseFilter('Space Tech')">🚀 SPACE TECH &amp; PRE-IPO (16)</button>
                <button class="cat-pill" style="border-color:#00EEEE; color:#00EEEE;" onclick="setUniverseFilter('Saham IPO')">HOT IPOs (40)</button>
                <button class="cat-pill" onclick="setUniverseFilter('Saham Indo')">IDX INDONESIA (850+)</button>
                <button class="cat-pill" onclick="setUniverseFilter('Saham US')">WALL STREET (100+)</button>
                <button class="cat-pill" onclick="setUniverseFilter('Saham Global')">GLOBAL ADRs (10)</button>
                <button class="cat-pill" onclick="setUniverseFilter('Crypto')">CRYPTO (100+)</button>
                <button class="cat-pill" onclick="setUniverseFilter('Komoditas')">KOMODITAS (16)</button>
                <button class="cat-pill" onclick="setUniverseFilter('Forex')">FOREX (15)</button>
                <button class="cat-pill" onclick="setUniverseFilter('Index')">INDICES &amp; RATES (11)</button>
                <span class="cat-pill-count" id="emsxAssetCount">SHOWING: 1,350+ ASSETS</span>
            </div>`;

const newEmsxPillsAndPagination = `<div class="cat-pill-bar">
                <button class="cat-pill active" onclick="setUniverseFilter('ALL')">ALL (5,300+)</button>
                <button class="cat-pill" style="border-color:#FF8800; color:#FF8800; font-weight:bold;" onclick="setUniverseFilter('Space Tech')">🚀 SPACE TECH &amp; PRE-IPO (75)</button>
                <button class="cat-pill" style="border-color:#00EEEE; color:#00EEEE;" onclick="setUniverseFilter('Saham IPO')">HOT IPOs (60)</button>
                <button class="cat-pill" onclick="setUniverseFilter('Saham Indo')">IDX INDONESIA (880+)</button>
                <button class="cat-pill" onclick="setUniverseFilter('Saham US')">WALL STREET (2,700+)</button>
                <button class="cat-pill" onclick="setUniverseFilter('Saham Global')">GLOBAL EQUITIES (700+)</button>
                <button class="cat-pill" onclick="setUniverseFilter('Crypto')">CRYPTO (550+)</button>
                <button class="cat-pill" onclick="setUniverseFilter('Komoditas')">KOMODITAS (100+)</button>
                <button class="cat-pill" onclick="setUniverseFilter('Forex')">FOREX (100+)</button>
                <button class="cat-pill" onclick="setUniverseFilter('Index')">INDICES &amp; BENCHMARKS (150+)</button>
                <span class="cat-pill-count" id="emsxAssetCount">SHOWING: 5,300+ ASSETS</span>
            </div>
            <!-- EMSX PAGINATION CONTROLS -->
            <div id="emsxPaginationBar" style="display:flex; justify-content:space-between; align-items:center; background:#080808; border:1px solid #222; padding:3px 8px; font-size:10.5px; margin-bottom:4px;">
                <div style="display:flex; gap:4px; align-items:center;">
                    <button class="btn-act" onclick="changeEmsxPage(-1)">&lt; PREV</button>
                    <span id="emsxPageInfo" class="bbg-cyan" style="font-weight:bold; margin:0 4px;">PAGE 1 OF 54</span>
                    <button class="btn-act" onclick="changeEmsxPage(1)">NEXT &gt;</button>
                </div>
                <div style="display:flex; gap:6px; align-items:center;">
                    <span class="bbg-dim">PER PAGE:</span>
                    <select id="emsxPageSizeSelect" class="bbg-select" style="width:70px; padding:1px 4px;" onchange="changeEmsxPageSize(this.value)">
                        <option value="50">50</option>
                        <option value="100" selected>100</option>
                        <option value="250">250</option>
                        <option value="500">500</option>
                    </select>
                </div>
            </div>`;

if (html.includes(oldEmsxPills)) {
    html = html.replace(oldEmsxPills, newEmsxPillsAndPagination);
}

// 5. Update Market Monitor Pills & Add Pagination
const oldMonTitle = `<span>-- GLOBAL MULTI-ASSET MARKET MONITOR (1,350+ ASSETS ACROSS ALL EXCHANGES) --</span>`;
const newMonTitle = `<span>-- GLOBAL MULTI-ASSET MARKET MONITOR (5,000+ ASSETS ACROSS ALL EXCHANGES) --</span>`;
html = html.replace(oldMonTitle, newMonTitle);

const oldMonPills = `<div class="cat-pill-bar">
                <button class="cat-pill active" onclick="setMonitorFilter('ALL')">ALL (1,350+)</button>
                <button class="cat-pill" style="border-color:#FF8800; color:#FF8800; font-weight:bold;" onclick="setMonitorFilter('Space Tech')">🚀 SPACE TECH &amp; PRE-IPO (16)</button>
                <button class="cat-pill" style="border-color:#00EEEE; color:#00EEEE;" onclick="setMonitorFilter('Saham IPO')">HOT IPOs (40)</button>
                <button class="cat-pill" onclick="setMonitorFilter('Saham Indo')">IDX INDONESIA (850+)</button>
                <button class="cat-pill" onclick="setMonitorFilter('Saham US')">WALL STREET (100+)</button>
                <button class="cat-pill" onclick="setMonitorFilter('Saham Global')">GLOBAL ADRs (10)</button>
                <button class="cat-pill" onclick="setMonitorFilter('Crypto')">CRYPTO (100+)</button>
                <button class="cat-pill" onclick="setMonitorFilter('Komoditas')">KOMODITAS (16)</button>
                <button class="cat-pill" onclick="setMonitorFilter('Forex')">FOREX (15)</button>
                <button class="cat-pill" onclick="setMonitorFilter('Index')">INDICES &amp; RATES (11)</button>
                <span class="cat-pill-count" id="monAssetCount">SHOWING: 1,350+ ASSETS</span>
            </div>`;

const newMonPillsAndPagination = `<div class="cat-pill-bar">
                <button class="cat-pill active" onclick="setMonitorFilter('ALL')">ALL (5,300+)</button>
                <button class="cat-pill" style="border-color:#FF8800; color:#FF8800; font-weight:bold;" onclick="setMonitorFilter('Space Tech')">🚀 SPACE TECH &amp; PRE-IPO (75)</button>
                <button class="cat-pill" style="border-color:#00EEEE; color:#00EEEE;" onclick="setMonitorFilter('Saham IPO')">HOT IPOs (60)</button>
                <button class="cat-pill" onclick="setMonitorFilter('Saham Indo')">IDX INDONESIA (880+)</button>
                <button class="cat-pill" onclick="setMonitorFilter('Saham US')">WALL STREET (2,700+)</button>
                <button class="cat-pill" onclick="setMonitorFilter('Saham Global')">GLOBAL EQUITIES (700+)</button>
                <button class="cat-pill" onclick="setMonitorFilter('Crypto')">CRYPTO (550+)</button>
                <button class="cat-pill" onclick="setMonitorFilter('Komoditas')">KOMODITAS (100+)</button>
                <button class="cat-pill" onclick="setMonitorFilter('Forex')">FOREX (100+)</button>
                <button class="cat-pill" onclick="setMonitorFilter('Index')">INDICES &amp; BENCHMARKS (150+)</button>
                <span class="cat-pill-count" id="monAssetCount">SHOWING: 5,300+ ASSETS</span>
            </div>
            <!-- MONITOR PAGINATION CONTROLS -->
            <div id="monPaginationBar" style="display:flex; justify-content:space-between; align-items:center; background:#080808; border:1px solid #222; padding:3px 8px; font-size:10.5px; margin-bottom:4px;">
                <div style="display:flex; gap:4px; align-items:center;">
                    <button class="btn-act" onclick="changeMonPage(-1)">&lt; PREV</button>
                    <span id="monPageInfo" class="bbg-cyan" style="font-weight:bold; margin:0 4px;">PAGE 1 OF 54</span>
                    <button class="btn-act" onclick="changeMonPage(1)">NEXT &gt;</button>
                </div>
                <div style="display:flex; gap:6px; align-items:center;">
                    <span class="bbg-dim">PER PAGE:</span>
                    <select id="monPageSizeSelect" class="bbg-select" style="width:70px; padding:1px 4px;" onchange="changeMonPageSize(this.value)">
                        <option value="50">50</option>
                        <option value="100" selected>100</option>
                        <option value="250">250</option>
                        <option value="500">500</option>
                    </select>
                </div>
            </div>`;

if (html.includes(oldMonPills)) {
    html = html.replace(oldMonPills, newMonPillsAndPagination);
}

fs.writeFileSync(filePath, html, 'utf8');
console.log('Successfully updated HTML structure for Order Types and 5000+ pagination!');
