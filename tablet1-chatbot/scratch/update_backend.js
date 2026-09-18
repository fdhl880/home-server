const fs = require('fs');
const path = require('path');

const serverFile = path.join(__dirname, '..', 'server.js');
let raw = fs.readFileSync(serverFile, 'utf8');
let isCrlf = raw.includes('\r\n');
let code = raw.replace(/\r\n/g, '\n');

// 1. Add IPO Stocks to TRACKED_ASSETS
const ipoAssetsCode = `
    // ------------------------------------------------------------
    // 1b. HOT IPO & RECENT LISTINGS (SAHAM IPO IDX & US) - 40 ASSETS
    // ------------------------------------------------------------
    { symbol: 'BREN.JK', name: 'Barito Renewables Energy (IPO Hot)',category:'Saham IPO', currency: 'IDR', lotSize: 100, price: 9250 },
    { symbol: 'CUAN.JK', name: 'Petrindo Jaya Kreasi (IPO Hot)',  category:'Saham IPO', currency: 'IDR', lotSize: 100, price: 7850 },
    { symbol: 'AMMN.JK', name: 'Amman Mineral Internasional (Mega IPO)',category:'Saham IPO',currency:'IDR',lotSize: 100, price: 9550 },
    { symbol: 'PGEO.JK', name: 'Pertamina Geothermal Energy (IPO)', category:'Saham IPO', currency: 'IDR', lotSize: 100, price: 1180 },
    { symbol: 'MBMA.JK', name: 'Merdeka Battery Materials (IPO)', category:'Saham IPO', currency: 'IDR', lotSize: 100, price: 540 },
    { symbol: 'NCKL.JK', name: 'Trimegah Bangun Persada (Harita IPO)',category:'Saham IPO',currency:'IDR',lotSize: 100, price: 890 },
    { symbol: 'VKTR.JK', name: 'VKTR Teknologi Mobilitas (EV IPO)', category:'Saham IPO', currency: 'IDR', lotSize: 100, price: 135 },
    { symbol: 'BELI.JK', name: 'Global Digital Niaga (Blibli IPO)',category:'Saham IPO', currency: 'IDR', lotSize: 100, price: 460 },
    { symbol: 'GOTO.JK', name: 'GoTo Gojek Tokopedia (Mega IPO)',  category:'Saham IPO', currency: 'IDR', lotSize: 100, price: 52 },
    { symbol: 'HILL.JK', name: 'Hillcon Tbk (IPO)',               category:'Saham IPO', currency: 'IDR', lotSize: 100, price: 2150 },
    { symbol: 'MUTU.JK', name: 'Mutuagung Lestari (Carbon Credit IPO)',category:'Saham IPO',currency:'IDR',lotSize: 100, price: 98 },
    { symbol: 'BDKR.JK', name: 'Berdikari Pondasi Perkasa (IPO)', category:'Saham IPO', currency: 'IDR', lotSize: 100, price: 420 },
    { symbol: 'DATA.JK', name: 'Remala Abadi (Telco ISP IPO)',    category:'Saham IPO', currency: 'IDR', lotSize: 100, price: 480 },
    { symbol: 'MSJA.JK', name: 'Multi Spunindo Jaya (IPO)',       category:'Saham IPO', currency: 'IDR', lotSize: 100, price: 310 },
    { symbol: 'GRPH.JK', name: 'Griptha Putra Persada (IPO)',     category:'Saham IPO', currency: 'IDR', lotSize: 100, price: 68 },
    { symbol: 'CGAS.JK', name: 'Citra Nusantara Gemilang (CNG IPO)',category:'Saham IPO',currency:'IDR',lotSize: 100, price: 155 },
    { symbol: 'SMGA.JK', name: 'Sumber Mineral Global Abadi (IPO)',category:'Saham IPO', currency: 'IDR', lotSize: 100, price: 85 },
    { symbol: 'ALII.JK', name: 'Ancara Logistics Indonesia (IPO)',category:'Saham IPO', currency: 'IDR', lotSize: 100, price: 620 },
    { symbol: 'MKAP.JK', name: 'Multikarya Asia Pasifik (IPO)',   category:'Saham IPO', currency: 'IDR', lotSize: 100, price: 240 },
    { symbol: 'LIVE.JK', name: 'Homeco Victoria Makmur (IPO)',    category:'Saham IPO', currency: 'IDR', lotSize: 100, price: 195 },
    { symbol: 'HYGN.JK', name: 'Ecocare Indo Pasifik (IPO)',      category:'Saham IPO', currency: 'IDR', lotSize: 100, price: 145 },
    { symbol: 'AREA.JK', name: 'Dunia Virtual Online (Data Center IPO)',category:'Saham IPO',currency:'IDR',lotSize: 100, price: 130 },
    { symbol: 'VISI.JK', name: 'Satu Visi Putra (IPO)',           category:'Saham IPO', currency: 'IDR', lotSize: 100, price: 170 },
    { symbol: 'RAAM.JK', name: 'Tripar Multivision Plus (Movie IPO)',category:'Saham IPO',currency:'IDR',lotSize: 100, price: 410 },
    { symbol: 'STRK.JK', name: 'Lovina Beach Brewery (IPO)',      category:'Saham IPO', currency: 'IDR', lotSize: 100, price: 60 },
    { symbol: 'PTPS.JK', name: 'Pulau Subur (Sawit IPO)',         category:'Saham IPO', currency: 'IDR', lotSize: 100, price: 110 },
    { symbol: 'AYAM.JK', name: 'Janu Putra Sejahtera (Poultry IPO)',category:'Saham IPO',currency:'IDR',lotSize: 100, price: 95 },
    { symbol: 'BATR.JK', name: 'Benteng Multi Indotbk (IPO)',     category:'Saham IPO', currency: 'IDR', lotSize: 100, price: 80 },
    { symbol: 'NEST.JK', name: 'Esta Multi Usaha (IPO)',          category:'Saham IPO', currency: 'IDR', lotSize: 100, price: 120 },
    { symbol: 'FAPA.JK', name: 'FAP Agri (Agro IPO)',             category:'Saham IPO', currency: 'IDR', lotSize: 100, price: 4900 },
    // Global & Wall Street Hot IPOs
    { symbol: 'RDDT',    name: 'Reddit Inc (US Tech IPO)',        category:'Saham IPO', currency: 'USD', lotSize: 1, price: 64.50 },
    { symbol: 'ARM',     name: 'Arm Holdings plc (AI Chip IPO)',  category:'Saham IPO', currency: 'USD', lotSize: 1, price: 138.20 },
    { symbol: 'ALAB',    name: 'Astera Labs (Semiconductor IPO)', category:'Saham IPO', currency: 'USD', lotSize: 1, price: 72.80 },
    { symbol: 'RBRK',    name: 'Rubrik Inc (Cybersecurity IPO)',  category:'Saham IPO', currency: 'USD', lotSize: 1, price: 34.10 },
    { symbol: 'BIRK',    name: 'Birkenstock Holding (Footwear IPO)',category:'Saham IPO',currency: 'USD', lotSize: 1, price: 56.40 },
    { symbol: 'CART',    name: 'Maplebear Inc (Instacart IPO)',   category:'Saham IPO', currency: 'USD', lotSize: 1, price: 37.90 },
    { symbol: 'KVUE',    name: 'Kenvue Inc (J&J Spin-off IPO)',   category:'Saham IPO', currency: 'USD', lotSize: 1, price: 21.30 },
    { symbol: 'CAVA',    name: 'CAVA Group (Restaurant IPO)',     category:'Saham IPO', currency: 'USD', lotSize: 1, price: 118.50 },
    { symbol: 'TEM',     name: 'Tempus AI Inc (Healthcare AI IPO)',category:'Saham IPO',currency: 'USD', lotSize: 1, price: 48.60 },
    { symbol: 'KYTX',    name: 'Kyverna Therapeutics (Biotech IPO)',category:'Saham IPO',currency:'USD', lotSize: 1, price: 9.80 },
`;

// Insert IPO assets right before US TECH
const usTechHeader = `    // ------------------------------------------------------------\n    // 2. US TECH & WALL STREET MEGA-CAPS (SAHAM US) - 68 ASSETS`;
if (code.includes(usTechHeader)) {
    code = code.replace(usTechHeader, () => ipoAssetsCode + '\n' + usTechHeader);
    console.log('Inserted 40 IPO assets into TRACKED_ASSETS');
} else {
    console.error('Failed to locate usTechHeader');
}

// 2. Add GET and POST /api/portfolio/reset support
const oldResetRoute = `// 3. POST /api/portfolio/reset -> Reset to initial Rp 200 Juta
app.post('/api/portfolio/reset', (req, res) => {
    try {
        const fresh = {
            initialCapital: INITIAL_CAPITAL,
            cash: INITIAL_CAPITAL,
            realizedPnL: 0,
            holdings: [],
            trades: []
        };
        savePortfolio(fresh);
        res.json({ success: true, message: 'Portofolio berhasil di-reset ke modal awal tunai.' });
    } catch (e) {
        res.status(500).json({ error: e.message });
    }
});`;

const newResetRoute = `// 3. POST & GET /api/portfolio/reset -> Reset to initial Rp 200 Juta
const handlePortfolioReset = (req, res) => {
    try {
        const fresh = {
            initialCapital: INITIAL_CAPITAL,
            cash: INITIAL_CAPITAL,
            realizedPnL: 0,
            holdings: [],
            trades: []
        };
        savePortfolio(fresh);
        res.json({ success: true, message: 'Portofolio berhasil di-reset ke modal awal tunai Rp 200.000.000.' });
    } catch (e) {
        res.status(500).json({ error: e.message });
    }
};
app.post('/api/portfolio/reset', handlePortfolioReset);
app.get('/api/portfolio/reset', handlePortfolioReset);`;

if (code.includes(oldResetRoute)) {
    code = code.replace(oldResetRoute, () => newResetRoute);
    console.log('Updated /api/portfolio/reset route to support both GET and POST');
} else {
    console.error('Failed to locate oldResetRoute');
}

// 3. Add fetchYahooChart, generateSyntheticCandles, and GET /api/chart/:symbol route
const chartRouteCode = `
// ============================================================
// CANDLESTICK CHART DATA ENGINE (YAHOO FINANCE + SYNTHETIC FALLBACK)
// ============================================================
function fetchYahooChart(sym, range, interval) {
    return new Promise((resolve) => {
        const url = \`https://query1.finance.yahoo.com/v8/finance/chart/\${encodeURIComponent(sym)}?interval=\${interval}&range=\${range}\`;
        const req = https.get(url, {
            headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36' },
            timeout: 5000
        }, (res) => {
            let data = '';
            res.on('data', chunk => data += chunk);
            res.on('end', () => {
                try {
                    const parsed = JSON.parse(data);
                    const r = parsed.chart?.result?.[0];
                    if (r && r.timestamp && r.indicators?.quote?.[0]) {
                        const q = r.indicators.quote[0];
                        const timestamps = r.timestamp;
                        const candles = [];
                        for (let i = 0; i < timestamps.length; i++) {
                            const o = q.open[i];
                            const h = q.high[i];
                            const l = q.low[i];
                            const c = q.close[i];
                            const v = q.volume?.[i] || 0;
                            if (o !== null && h !== null && l !== null && c !== null && !isNaN(o) && !isNaN(c)) {
                                candles.push({
                                    timestamp: timestamps[i] * 1000,
                                    open: Math.round(o * 100) / 100,
                                    high: Math.round(h * 100) / 100,
                                    low: Math.round(l * 100) / 100,
                                    close: Math.round(c * 100) / 100,
                                    volume: v
                                });
                            }
                        }
                        if (candles.length >= 2) {
                            return resolve(candles);
                        }
                    }
                } catch (e) {}
                resolve(null);
            });
        });
        req.on('error', () => resolve(null));
        req.on('timeout', () => { req.destroy(); resolve(null); });
    });
}

function generateSyntheticCandles(sym, count, range) {
    const q = quoteCache.data[sym] || quoteCache.data[sym.toUpperCase()];
    const assetDef = TRACKED_ASSETS.find(a => a.symbol.toUpperCase() === sym.toUpperCase());
    const basePrice = q?.price || assetDef?.price || 1000;
    const now = Date.now();
    const stepMs = range === '1y' ? 7 * 86400000 : (range === '1mo' ? 86400000 : (range === '5d' ? 3600000 : 900000));

    const rawWalk = [];
    let current = basePrice * (1 - ((Math.random() - 0.5) * 0.04));
    const volatility = 0.012;

    for (let i = 0; i < count; i++) {
        const changePct = (Math.random() - 0.49) * volatility;
        const open = current;
        current = current * (1 + changePct);
        const close = current;
        const high = Math.max(open, close) * (1 + Math.random() * 0.008);
        const low = Math.min(open, close) * (1 - Math.random() * 0.008);
        const volume = Math.floor(10000 + Math.random() * 90000);
        rawWalk.push({ open, high, low, close, volume });
    }

    const lastClose = rawWalk[rawWalk.length - 1].close;
    const ratio = lastClose > 0 ? basePrice / lastClose : 1;
    const candles = [];

    for (let i = 0; i < count; i++) {
        const t = now - ((count - 1 - i) * stepMs);
        const w = rawWalk[i];
        candles.push({
            timestamp: t,
            open: Math.round(w.open * ratio * 100) / 100,
            high: Math.round(w.high * ratio * 100) / 100,
            low: Math.round(w.low * ratio * 100) / 100,
            close: Math.round(w.close * ratio * 100) / 100,
            volume: w.volume
        });
    }
    return candles;
}

// 5. GET /api/chart/:symbol -> Live or synthetic candlestick history for ANY asset
// Usage: GET /api/chart/BBCA.JK?range=1d
app.get('/api/chart/:symbol', async (req, res) => {
    try {
        const sym = (req.params.symbol || '').trim().toUpperCase();
        const range = req.query.range || '1d';
        let interval = '15m';
        let candleCount = 28;

        if (range === '5d') {
            interval = '60m';
            candleCount = 35;
        } else if (range === '1mo') {
            interval = '1d';
            candleCount = 30;
        } else if (range === '1y') {
            interval = '1wk';
            candleCount = 52;
        } else {
            interval = '15m';
            candleCount = 28;
        }

        let candles = await fetchYahooChart(sym, range, interval);

        if (!candles || candles.length < 2) {
            candles = generateSyntheticCandles(sym, candleCount, range);
        }

        res.json({
            symbol: sym,
            range: range,
            interval: interval,
            candles: candles
        });
    } catch (e) {
        console.error('Chart API error:', e.message);
        const fallback = generateSyntheticCandles(req.params.symbol, 28, '1d');
        res.json({ symbol: req.params.symbol, range: '1d', candles: fallback });
    }
});
`;

const quotesRouteTarget = `app.get('/api/market/quotes', (req, res) => {
    const list = Object.values(quoteCache.data);
    res.json({
        quotes: list,
        count: list.length,
        usdRate: quoteCache.usdIdr,
        timestamp: quoteCache.lastFetched
    });
});`;

if (code.includes(quotesRouteTarget)) {
    code = code.replace(quotesRouteTarget, () => quotesRouteTarget + '\n' + chartRouteCode);
    console.log('Inserted /api/chart/:symbol route and candlestick engine');
} else {
    console.error('Failed to locate quotesRouteTarget');
}

if (isCrlf) {
    code = code.replace(/\n/g, '\r\n');
}

fs.writeFileSync(serverFile, code, 'utf8');
console.log('server.js updated successfully!');
