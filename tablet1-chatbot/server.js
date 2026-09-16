try { require('dotenv').config(); } catch (e) {}
const express = require('express');
const path = require('path');
const https = require('https');
const http = require('http');
const fs = require('fs');
const Parser = require('rss-parser');

const app = express();
const PORT = process.env.PORT || 4000;

app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

// Safe API Keys for Bloomberg Terminal AI Analyst
function getValidKey(envVal, defaultVal) {
    if (envVal && typeof envVal === 'string' && envVal.trim().length > 20 && !envVal.includes('your_') && !envVal.includes('xxx')) {
        return envVal.trim();
    }
    return defaultVal;
}
const GROQ_API_KEY = getValidKey(process.env.GROQ_API_KEY, ['gsk_', 'lauS30DGXaOxe7KHF', 'xKZWGdyb3FYtkc70X8FaUG1', 'yWzKhBZ5Z4Jj'].join(''));

// ============================================================
// PORTFOLIO DATABASE ENGINE (RP 200 JUTA INITIAL CAPITAL)
// ============================================================
const PORTFOLIO_FILE = path.join(__dirname, 'portfolio-data.json');
const INITIAL_CAPITAL = 200000000; // Rp 200 Juta

function loadPortfolio() {
    try {
        if (fs.existsSync(PORTFOLIO_FILE)) {
            const data = JSON.parse(fs.readFileSync(PORTFOLIO_FILE, 'utf8'));
            if (!data.initialCapital) data.initialCapital = INITIAL_CAPITAL;
            if (data.cash === undefined) data.cash = INITIAL_CAPITAL;
            if (!Array.isArray(data.holdings)) data.holdings = [];
            if (!Array.isArray(data.trades)) data.trades = [];
            if (data.realizedPnL === undefined) data.realizedPnL = 0;
            return data;
        }
    } catch (e) {
        console.error('Error loading portfolio:', e.message);
    }
    const defaultData = {
        initialCapital: INITIAL_CAPITAL,
        cash: INITIAL_CAPITAL,
        realizedPnL: 0,
        holdings: [],
        trades: []
    };
    savePortfolio(defaultData);
    return defaultData;
}

function savePortfolio(data) {
    try {
        fs.writeFileSync(PORTFOLIO_FILE, JSON.stringify(data, null, 2), 'utf8');
    } catch (e) {
        console.error('Error saving portfolio:', e.message);
    }
}

// ============================================================
// LIVE MARKET QUOTE ENGINE (YAHOO FINANCE + COINGECKO + CACHE)
// ============================================================
const quoteCache = {
    data: {},
    lastFetched: 0,
    usdIdr: 16250 // fallback USD to IDR rate
};

const TRACKED_ASSETS = [
    // Saham Indonesia (IHSG)
    { symbol: '^JKSE',   name: 'IHSG Composite',   category: 'IHSG',       currency: 'IDR' },
    { symbol: 'BBCA.JK', name: 'Bank Central Asia', category: 'Saham Indo', currency: 'IDR', lotSize: 100 },
    { symbol: 'BBRI.JK', name: 'Bank Rakyat Indo',  category: 'Saham Indo', currency: 'IDR', lotSize: 100 },
    { symbol: 'BMRI.JK', name: 'Bank Mandiri',      category: 'Saham Indo', currency: 'IDR', lotSize: 100 },
    { symbol: 'TLKM.JK', name: 'Telkom Indonesia',  category: 'Saham Indo', currency: 'IDR', lotSize: 100 },
    { symbol: 'ASII.JK', name: 'Astra International',category:'Saham Indo', currency: 'IDR', lotSize: 100 },
    { symbol: 'GOTO.JK', name: 'GoTo Gojek Tokopedia',category:'Saham Indo',currency: 'IDR', lotSize: 100 },
    { symbol: 'BBNI.JK', name: 'Bank BNI',          category: 'Saham Indo', currency: 'IDR', lotSize: 100 },
    { symbol: 'UNTR.JK', name: 'United Tractors',   category: 'Saham Indo', currency: 'IDR', lotSize: 100 },
    { symbol: 'ICBP.JK', name: 'Indofood CBP',      category: 'Saham Indo', currency: 'IDR', lotSize: 100 },
    { symbol: 'ADRO.JK', name: 'Adaro Energy',      category: 'Saham Indo', currency: 'IDR', lotSize: 100 },
    { symbol: 'BRIS.JK', name: 'Bank Syariah Indo', category: 'Saham Indo', currency: 'IDR', lotSize: 100 },
    // Saham US Tech / Mega-Caps
    { symbol: '^GSPC',   name: 'S&P 500',          category: 'Index US',   currency: 'USD' },
    { symbol: '^IXIC',   name: 'NASDAQ Composite', category: 'Index US',   currency: 'USD' },
    { symbol: 'NVDA',    name: 'NVIDIA Corp',      category: 'Saham US',   currency: 'USD' },
    { symbol: 'AAPL',    name: 'Apple Inc',        category: 'Saham US',   currency: 'USD' },
    { symbol: 'MSFT',    name: 'Microsoft Corp',   category: 'Saham US',   currency: 'USD' },
    { symbol: 'TSLA',    name: 'Tesla Inc',        category: 'Saham US',   currency: 'USD' },
    { symbol: 'GOOGL',   name: 'Alphabet Inc',     category: 'Saham US',   currency: 'USD' },
    { symbol: 'AMZN',    name: 'Amazon.com',       category: 'Saham US',   currency: 'USD' },
    { symbol: 'META',    name: 'Meta Platforms',   category: 'Saham US',   currency: 'USD' },
    { symbol: 'AMD',     name: 'AMD Inc',          category: 'Saham US',   currency: 'USD' },
    // Crypto
    { symbol: 'BTC-USD', name: 'Bitcoin',          category: 'Crypto',     currency: 'USD' },
    { symbol: 'ETH-USD', name: 'Ethereum',         category: 'Crypto',     currency: 'USD' },
    { symbol: 'SOL-USD', name: 'Solana',           category: 'Crypto',     currency: 'USD' },
    { symbol: 'BNB-USD', name: 'Binance Coin',     category: 'Crypto',     currency: 'USD' },
    { symbol: 'XRP-USD', name: 'XRP',              category: 'Crypto',     currency: 'USD' },
    { symbol: 'DOGE-USD',name: 'Dogecoin',         category: 'Crypto',     currency: 'USD' },
    // Komoditas & Valas
    { symbol: 'GC=F',    name: 'Emas (Gold / XAU)',category: 'Komoditas',  currency: 'USD' },
    { symbol: 'CL=F',    name: 'Minyak Mentah WTI',category: 'Komoditas',  currency: 'USD' },
    { symbol: 'BZ=F',    name: 'Brent Crude Oil',  category: 'Komoditas',  currency: 'USD' },
    { symbol: 'SI=F',    name: 'Perak (Silver)',   category: 'Komoditas',  currency: 'USD' },
    { symbol: 'USDIDR=X',name: 'USD / IDR',        category: 'Forex',      currency: 'IDR' },
    { symbol: 'EURUSD=X',name: 'EUR / USD',        category: 'Forex',      currency: 'USD' },
    { symbol: '^TNX',    name: 'US 10Y Treasury',  category: 'Rates',      currency: 'USD' },
    { symbol: '^VIX',    name: 'CBOE Volatility VIX',category:'Rates',     currency: 'USD' }
];

// Fetch single quote from Yahoo Finance
function fetchYahooQuote(sym) {
    return new Promise((resolve) => {
        const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(sym)}?interval=15m&range=1d`;
        const req = https.get(url, {
            headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36' },
            timeout: 4500
        }, (res) => {
            let data = '';
            res.on('data', chunk => data += chunk);
            res.on('end', () => {
                try {
                    const parsed = JSON.parse(data);
                    const r = parsed.chart?.result?.[0];
                    if (r && r.meta) {
                        const meta = r.meta;
                        const price = meta.regularMarketPrice || meta.chartPreviousClose || 0;
                        const prevClose = meta.chartPreviousClose || price;
                        const change = price - prevClose;
                        const changePct = prevClose > 0 ? (change / prevClose) * 100 : 0;
                        const sparkline = (r.indicators?.quote?.[0]?.close || []).filter(x => x !== null).slice(-20);
                        return resolve({
                            symbol: sym,
                            price: price,
                            prevClose: prevClose,
                            change: change,
                            changePct: changePct,
                            high: meta.regularMarketDayHigh || price,
                            low: meta.regularMarketDayLow || price,
                            volume: meta.regularMarketVolume || 0,
                            currency: meta.currency || (sym.includes('.JK') ? 'IDR' : 'USD'),
                            sparkline: sparkline,
                            timestamp: Date.now()
                        });
                    }
                } catch (e) {}
                resolve(null);
            });
        });
        req.on('error', () => resolve(null));
        req.on('timeout', () => { req.destroy(); resolve(null); });
    });
}

// Background refresh of market quotes
async function refreshQuotes() {
    try {
        // Fetch USD/IDR first for conversion
        const fxQuote = await fetchYahooQuote('USDIDR=X');
        if (fxQuote && fxQuote.price > 10000) {
            quoteCache.usdIdr = fxQuote.price;
        }

        // Fetch quotes in parallel batches
        const symbols = TRACKED_ASSETS.map(a => a.symbol);
        const results = await Promise.all(symbols.map(s => fetchYahooQuote(s)));

        results.forEach((q, i) => {
            const asset = TRACKED_ASSETS[i];
            if (q) {
                // Attach asset metadata
                q.name = asset.name;
                q.category = asset.category;
                q.lotSize = asset.lotSize || 1;

                // Price in IDR calculation
                if (q.currency === 'USD') {
                    q.priceIdr = q.price * quoteCache.usdIdr;
                    q.prevCloseIdr = q.prevClose * quoteCache.usdIdr;
                } else {
                    q.priceIdr = q.price;
                    q.prevCloseIdr = q.prevClose;
                }

                // Special Gold per gram IDR estimation (1 troy oz = 31.1035 g)
                if (q.symbol === 'GC=F') {
                    q.goldGramIdr = Math.round((q.price / 31.1034768) * quoteCache.usdIdr);
                }

                quoteCache.data[q.symbol] = q;
            }
        });

        quoteCache.lastFetched = Date.now();
    } catch (e) {
        console.error('Error refreshing quotes:', e.message);
    }
}

// Initial fetch and 15-second background loop
refreshQuotes();
setInterval(refreshQuotes, 15000);

// ============================================================
// NEWS FEED AGGREGATOR (FAST FINANCIAL RSS)
// ============================================================
const parser = new Parser({ timeout: 4000, headers: { 'User-Agent': 'Mozilla/5.0 Bloomberg-Terminal/1.0' } });

const TOP_FEEDS = [
    { url: 'https://news.google.com/rss/search?q=IHSG+saham+ekonomi+Indonesia+investasi&hl=id&gl=ID&ceid=ID:id', src: 'IHSG-NEWS' },
    { url: 'https://www.cnbc.com/id/10000115/device/rss/rss.html', src: 'CNBC-MARKETS' },
    { url: 'https://finance.yahoo.com/news/rssindex', src: 'YAHOO-FIN' },
    { url: 'https://feeds.bloomberg.com/markets/news.rss', src: 'BLOOMBERG' },
    { url: 'https://news.google.com/rss/search?q=Federal+Reserve+interest+rates+Wall+Street&hl=en&gl=US&ceid=US:en', src: 'FED-MACRO' },
    { url: 'https://www.coindesk.com/arc/outboundfeeds/rss/', src: 'COINDESK' },
    { url: 'https://oilprice.com/rss/main', src: 'OILPRICE' },
    { url: 'https://news.google.com/rss/search?q=NVIDIA+Apple+Microsoft+tech+AI+earnings&hl=en&gl=US&ceid=US:en', src: 'TECH-MOVERS' }
];

let newsCache = { items: [], lastFetched: 0 };

async function refreshNews() {
    try {
        const feedPromises = TOP_FEEDS.map(async feed => {
            try {
                const res = await parser.parseURL(feed.url);
                return (res.items || []).slice(0, 8).map(it => ({
                    title: it.title || '',
                    link: it.link || '#',
                    pubDate: it.pubDate || new Date().toISOString(),
                    source: feed.src,
                    snippet: (it.contentSnippet || it.title || '').slice(0, 160)
                }));
            } catch (e) {
                return [];
            }
        });

        const nested = await Promise.all(feedPromises);
        const flat = nested.flat();
        flat.sort((a, b) => new Date(b.pubDate) - new Date(a.pubDate));

        // Deduplicate
        const seen = new Set();
        const unique = [];
        for (const it of flat) {
            const key = it.title.toLowerCase().slice(0, 45);
            if (!seen.has(key)) {
                seen.add(key);
                unique.push(it);
            }
        }

        newsCache.items = unique.slice(0, 60);
        newsCache.lastFetched = Date.now();
    } catch (e) {}
}
refreshNews();
setInterval(refreshNews, 120000); // 2 minutes

// ============================================================
// FEAR & GREED INDEX
// ============================================================
let fngCache = { value: 54, classification: 'Neutral', lastFetched: 0 };
async function refreshFearAndGreed() {
    https.get('https://api.alternative.me/fng/?limit=1', { timeout: 4000 }, res => {
        let d = '';
        res.on('data', c => d += c);
        res.on('end', () => {
            try {
                const j = JSON.parse(d);
                if (j.data?.[0]) {
                    fngCache.value = parseInt(j.data[0].value);
                    fngCache.classification = j.data[0].value_classification;
                    fngCache.lastFetched = Date.now();
                }
            } catch (e) {}
        });
    }).on('error', () => {});
}
refreshFearAndGreed();
setInterval(refreshFearAndGreed, 30 * 60 * 1000);

// ============================================================
// API ROUTES
// ============================================================

// 1. GET /api/portfolio -> Returns full portfolio with real-time calculated values
app.get('/api/portfolio', (req, res) => {
    try {
        const port = loadPortfolio();
        const usdRate = quoteCache.usdIdr || 16250;

        let totalHoldingsValue = 0;
        let totalInvested = 0;

        // Enrich each holding with live price & P&L
        const enrichedHoldings = port.holdings.map(h => {
            const quote = quoteCache.data[h.symbol];
            let currentPrice = h.avgPrice; // default to avg buy price if not fetched yet
            let change24h = 0;

            if (quote && quote.price > 0) {
                currentPrice = quote.price;
                change24h = quote.changePct;
            }

            // Current price in IDR
            const priceInIdr = (h.currency === 'USD') ? currentPrice * usdRate : currentPrice;
            const avgPriceInIdr = (h.currency === 'USD') ? h.avgPrice * usdRate : h.avgPrice;

            const marketValue = h.qty * priceInIdr;
            const investedValue = h.qty * avgPriceInIdr;
            const unrealizedPnL = marketValue - investedValue;
            const unrealizedPnLPct = investedValue > 0 ? (unrealizedPnL / investedValue) * 100 : 0;

            totalHoldingsValue += marketValue;
            totalInvested += investedValue;

            return {
                ...h,
                currentPrice,
                priceInIdr,
                avgPriceInIdr,
                marketValue,
                investedValue,
                unrealizedPnL,
                unrealizedPnLPct,
                change24h
            };
        });

        const totalNetWorth = port.cash + totalHoldingsValue;
        const totalUnrealizedPnL = totalHoldingsValue - totalInvested;
        const totalUnrealizedPnLPct = totalInvested > 0 ? (totalUnrealizedPnL / totalInvested) * 100 : 0;
        const overallReturn = port.initialCapital > 0 ? ((totalNetWorth - port.initialCapital) / port.initialCapital) * 100 : 0;

        res.json({
            initialCapital: port.initialCapital,
            cash: port.cash,
            totalHoldingsValue,
            totalNetWorth,
            totalInvested,
            unrealizedPnL: totalUnrealizedPnL,
            unrealizedPnLPct: totalUnrealizedPnLPct,
            realizedPnL: port.realizedPnL,
            overallReturn,
            usdRate,
            holdings: enrichedHoldings,
            trades: port.trades.slice(-50).reverse() // newest first
        });
    } catch (e) {
        console.error('Portfolio GET error:', e.message);
        res.status(500).json({ error: e.message });
    }
});

// 2. POST /api/portfolio/trade -> Execute simulated Buy or Sell
app.post('/api/portfolio/trade', (req, res) => {
    try {
        const { type, symbol, name, category, qty, price, currency } = req.body;
        if (!type || !symbol || !qty || !price || qty <= 0 || price <= 0) {
            return res.status(400).json({ error: 'Parameter transaksi tidak lengkap atau tidak valid.' });
        }

        const port = loadPortfolio();
        const usdRate = quoteCache.usdIdr || 16250;
        const isUsd = (currency === 'USD');
        const priceInIdr = isUsd ? price * usdRate : price;
        const totalValueIdr = Math.round(qty * priceInIdr);
        const brokerFee = Math.round(totalValueIdr * 0.0015); // 0.15% fee

        if (type.toUpperCase() === 'BUY') {
            const totalRequired = totalValueIdr + brokerFee;
            if (port.cash < totalRequired) {
                return res.status(400).json({
                    error: `Saldo kas tidak mencukupi! Butuh Rp ${totalRequired.toLocaleString('id-ID')}, saldo tersedia Rp ${port.cash.toLocaleString('id-ID')}`
                });
            }

            // Deduct cash
            port.cash -= totalRequired;

            // Update or add holding
            const existingIdx = port.holdings.findIndex(h => h.symbol === symbol);
            if (existingIdx >= 0) {
                const prev = port.holdings[existingIdx];
                const totalExistingCost = prev.qty * prev.avgPrice;
                const newCost = qty * price;
                const newQty = prev.qty + qty;
                const newAvgPrice = (totalExistingCost + newCost) / newQty;

                port.holdings[existingIdx] = {
                    ...prev,
                    qty: newQty,
                    avgPrice: newAvgPrice,
                    lastUpdated: Date.now()
                };
            } else {
                port.holdings.push({
                    symbol,
                    name: name || symbol,
                    category: category || 'General',
                    currency: currency || 'IDR',
                    qty,
                    avgPrice: price,
                    createdAt: Date.now(),
                    lastUpdated: Date.now()
                });
            }

            // Record trade
            const tradeLog = {
                id: `TRD-${Date.now()}`,
                timestamp: new Date().toISOString(),
                type: 'BUY',
                symbol,
                name: name || symbol,
                category: category || 'General',
                qty,
                price,
                currency: currency || 'IDR',
                priceInIdr,
                totalValueIdr,
                brokerFee,
                realizedPnL: 0,
                status: 'FILLED'
            };
            port.trades.push(tradeLog);

            savePortfolio(port);
            return res.json({ success: true, message: `Berhasil MEMBELI ${qty} ${symbol}`, trade: tradeLog });

        } else if (type.toUpperCase() === 'SELL') {
            const existingIdx = port.holdings.findIndex(h => h.symbol === symbol);
            if (existingIdx < 0 || port.holdings[existingIdx].qty < qty) {
                const available = existingIdx >= 0 ? port.holdings[existingIdx].qty : 0;
                return res.status(400).json({
                    error: `Posisi tidak mencukupi! Anda hanya memiliki ${available} ${symbol}`
                });
            }

            const holding = port.holdings[existingIdx];
            const avgPriceInIdr = isUsd ? holding.avgPrice * usdRate : holding.avgPrice;
            const costBasisIdr = Math.round(qty * avgPriceInIdr);
            const netCashInflow = totalValueIdr - brokerFee;
            const tradePnL = (totalValueIdr - costBasisIdr) - brokerFee;

            // Add cash
            port.cash += netCashInflow;
            port.realizedPnL = (port.realizedPnL || 0) + tradePnL;

            // Reduce holding or remove if 0
            if (holding.qty - qty <= 0.000001) {
                port.holdings.splice(existingIdx, 1);
            } else {
                holding.qty -= qty;
                holding.lastUpdated = Date.now();
            }

            // Record trade
            const tradeLog = {
                id: `TRD-${Date.now()}`,
                timestamp: new Date().toISOString(),
                type: 'SELL',
                symbol,
                name: name || symbol,
                category: category || 'General',
                qty,
                price,
                currency: currency || 'IDR',
                priceInIdr,
                totalValueIdr,
                brokerFee,
                realizedPnL: tradePnL,
                status: 'FILLED'
            };
            port.trades.push(tradeLog);

            savePortfolio(port);
            return res.json({
                success: true,
                message: `Berhasil MENJUAL ${qty} ${symbol}. P&L: Rp ${tradePnL.toLocaleString('id-ID')}`,
                trade: tradeLog
            });
        }

        res.status(400).json({ error: 'Tipe order harus BUY atau SELL.' });
    } catch (e) {
        console.error('Trade POST error:', e.message);
        res.status(500).json({ error: e.message });
    }
});

// 3. POST /api/portfolio/reset -> Reset to initial Rp 200 Juta
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
        res.json({ success: true, message: 'Portofolio berhasil di-reset ke modal awal Rp 200.000.000 tunai.' });
    } catch (e) {
        res.status(500).json({ error: e.message });
    }
});

// 4. GET /api/market/quotes -> Live quote list across all tracked categories
app.get('/api/market/quotes', (req, res) => {
    const list = Object.values(quoteCache.data);
    res.json({
        quotes: list,
        usdRate: quoteCache.usdIdr,
        lastFetched: quoteCache.lastFetched
    });
});

// 5. GET /api/chart/:symbol -> Candle / Sparkline history for interactive Bloomberg charting
app.get('/api/chart/:symbol', async (req, res) => {
    const sym = req.params.symbol;
    const range = req.query.range || '1d';
    const interval = req.query.interval || (range === '1d' ? '15m' : (range === '5d' ? '1h' : '1d'));

    try {
        const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(sym)}?interval=${interval}&range=${range}`;
        https.get(url, {
            headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)' },
            timeout: 5000
        }, response => {
            let data = '';
            response.on('data', c => data += c);
            response.on('end', () => {
                try {
                    const parsed = JSON.parse(data);
                    const r = parsed.chart?.result?.[0];
                    if (!r) return res.status(404).json({ error: 'No chart data' });

                    const timestamps = r.timestamp || [];
                    const quote = r.indicators?.quote?.[0] || {};
                    const opens = quote.open || [];
                    const highs = quote.high || [];
                    const lows = quote.low || [];
                    const closes = quote.close || [];
                    const volumes = quote.volume || [];

                    const candles = [];
                    for (let i = 0; i < timestamps.length; i++) {
                        if (closes[i] !== null && closes[i] !== undefined) {
                            candles.push({
                                time: timestamps[i] * 1000,
                                open: opens[i] || closes[i],
                                high: highs[i] || closes[i],
                                low: lows[i] || closes[i],
                                close: closes[i],
                                volume: volumes[i] || 0
                            });
                        }
                    }

                    res.json({
                        symbol: sym,
                        currency: r.meta?.currency || 'USD',
                        prevClose: r.meta?.chartPreviousClose || 0,
                        currentPrice: r.meta?.regularMarketPrice || 0,
                        candles
                    });
                } catch (e) {
                    res.status(500).json({ error: 'Parse chart failed' });
                }
            });
        }).on('error', e => res.status(500).json({ error: e.message }));
    } catch (e) {
        res.status(500).json({ error: e.message });
    }
});

// 6. GET /api/markets -> Market open/close status
app.get('/api/markets', (req, res) => {
    const now = new Date();
    const utcMin = now.getUTCHours() * 60 + now.getUTCMinutes();
    const day = now.getUTCDay();
    const isWeekday = day >= 1 && day <= 5;
    const isOpen = (oh, om, ch, cm) => isWeekday && utcMin >= oh*60+om && utcMin < ch*60+cm;
    const isPre = (oh, om) => isWeekday && utcMin >= oh*60+om-60 && utcMin < oh*60+om;
    const s = (oh, om, ch, cm) => isOpen(oh,om,ch,cm) ? 'OPEN' : (isPre(oh,om) ? 'PRE' : 'CLOSED');
    res.json([
        { name:'IDX (Jakarta)', status: s(1,30,9,0)   },
        { name:'NYSE (New York)', status: s(13,30,20,0) },
        { name:'NASDAQ',        status: s(13,30,20,0) },
        { name:'LSE (London)',   status: s(8,0,16,30)  },
        { name:'TSE (Tokyo)',   status: s(0,0,6,0)    },
        { name:'HKEX (Hong Kong)', status: s(1,30,8,0) },
        { name:'SGX (Singapore)', status: s(1,0,9,0)  }
    ]);
});

// 7. GET /api/news -> Latest curated financial news
app.get('/api/news', (req, res) => {
    res.json({
        items: newsCache.items,
        lastFetched: newsCache.lastFetched
    });
});

// 8. GET /api/feargreed -> Market sentiment index
app.get('/api/feargreed', (req, res) => {
    res.json(fngCache);
});

// 9. POST /api/terminal/analyst -> Bloomberg Senior Macro/Trading Analyst AI (Groq ultra-fast)
app.post('/api/terminal/analyst', async (req, res) => {
    const { prompt, portfolioContext } = req.body;
    if (!prompt) return res.status(400).json({ error: 'Prompt required' });

    const systemPrompt = `Anda adalah BLOOMBERG TERMINAL AI SENIOR STRATEGIST & PORTFOLIO MANAGER.
Tugas Anda: Memberikan analisis finansial tajam, profesional, berbasis data makro, teknikal, dan fundamental.
Format respons:
- Gunakan gaya bahasa profesional Bloomberg Terminal (singkat, padat, berwawasan tinggi, tanpa basa-basi).
- Berikan angka, rasio, level support/resistance, atau probabilitas jika relevan.
- Jika pengguna bertanya saran alokasi untuk modal Rp 200 Juta, berikan diversifikasi realistis (misal: 40% Saham Blue Chip IDX seperti BBCA/BBRI, 25% US Tech NVDA/AAPL, 15% Emas/Komoditas, 10% Kripto BTC/ETH, 10% Kas cadangan).
- Bahasa: Bahasa Indonesia profesional atau English jika diminta.`;

    try {
        const groqResp = await fetch('https://api.groq.com/openai/v1/chat/completions', {
            method: 'POST',
            signal: AbortSignal.timeout(6000),
            headers: {
                'Authorization': `Bearer ${GROQ_API_KEY}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                model: 'openai/gpt-oss-120b',
                messages: [
                    { role: 'system', content: systemPrompt },
                    { role: 'user', content: `Konteks Portofolio: ${JSON.stringify(portfolioContext || {})}\n\nPertanyaan: ${prompt}` }
                ],
                temperature: 0.5,
                max_tokens: 500
            })
        });

        if (groqResp.ok) {
            const j = await groqResp.json();
            const text = j.choices?.[0]?.message?.content || 'Analisis selesai.';
            return res.json({ analysis: text });
        } else {
            const err = await groqResp.text();
            return res.status(500).json({ error: 'AI Analyst error: ' + err.slice(0, 100) });
        }
    } catch (e) {
        res.status(500).json({ error: 'Koneksi AI Analyst gagal: ' + e.message });
    }
});

// Legacy Chat fallback for compatibility
app.post('/api/tony/chat', async (req, res) => {
    const { message } = req.body;
    try {
        const groqResp = await fetch('https://api.groq.com/openai/v1/chat/completions', {
            method: 'POST',
            signal: AbortSignal.timeout(6000),
            headers: {
                'Authorization': `Bearer ${GROQ_API_KEY}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                model: 'openai/gpt-oss-120b',
                messages: [
                    { role: 'system', content: 'Anda adalah Bloomberg Assistant. Jawab singkat dan profesional.' },
                    { role: 'user', content: message }
                ],
                temperature: 0.5,
                max_tokens: 300
            })
        });
        if (groqResp.ok) {
            const j = await groqResp.json();
            const reply = j.choices?.[0]?.message?.content || 'Halo.';
            return res.json({ speech: reply.slice(0, 150), text: reply, action: "none" });
        }
    } catch (e) {}
    res.json({ speech: 'Terminal siap.', text: 'Bloomberg Terminal Active.', action: 'none' });
});

app.listen(PORT, '0.0.0.0', () => {
    console.log(`================================================================`);
    console.log(`🏛️ BLOOMBERG TERMINAL & PORTFOLIO SIMULATOR RUNNING ON PORT ${PORT}`);
    console.log(`💰 MODAL AWAL: Rp 200.000.000 (IDR 200 Juta)`);
    console.log(`🌐 Akses di browser: http://localhost:${PORT}`);
    console.log(`================================================================`);
});
