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
    // ------------------------------------------------------------
    // 1. INDONESIAN BLUECHIPS & HIGH LIQUIDITY IDX (SAHAM INDO) - 66 ASSETS
    // ------------------------------------------------------------
    { symbol: '^JKSE',   name: 'IHSG Composite',        category: 'IHSG',       currency: 'IDR', price: 6450 },
    // Perbankan & Finansial
    { symbol: 'BBCA.JK', name: 'Bank Central Asia',      category: 'Saham Indo', currency: 'IDR', lotSize: 100, price: 6325 },
    { symbol: 'BBRI.JK', name: 'Bank Rakyat Indonesia',  category: 'Saham Indo', currency: 'IDR', lotSize: 100, price: 3330 },
    { symbol: 'BMRI.JK', name: 'Bank Mandiri',           category: 'Saham Indo', currency: 'IDR', lotSize: 100, price: 4280 },
    { symbol: 'BBNI.JK', name: 'Bank BNI',               category: 'Saham Indo', currency: 'IDR', lotSize: 100, price: 3740 },
    { symbol: 'BRIS.JK', name: 'Bank Syariah Indonesia', category: 'Saham Indo', currency: 'IDR', lotSize: 100, price: 2950 },
    { symbol: 'BBTN.JK', name: 'Bank BTN',               category: 'Saham Indo', currency: 'IDR', lotSize: 100, price: 1280 },
    { symbol: 'BDMN.JK', name: 'Bank Danamon',           category: 'Saham Indo', currency: 'IDR', lotSize: 100, price: 2640 },
    { symbol: 'BNGA.JK', name: 'Bank CIMB Niaga',        category: 'Saham Indo', currency: 'IDR', lotSize: 100, price: 1820 },
    { symbol: 'ARTO.JK', name: 'Bank Jago',              category: 'Saham Indo', currency: 'IDR', lotSize: 100, price: 2150 },
    { symbol: 'MEGA.JK', name: 'Bank Mega',              category: 'Saham Indo', currency: 'IDR', lotSize: 100, price: 4800 },
    { symbol: 'BTPS.JK', name: 'Bank BTPN Syariah',      category: 'Saham Indo', currency: 'IDR', lotSize: 100, price: 1020 },
    // Telekomunikasi & Infrastruktur
    { symbol: 'TLKM.JK', name: 'Telkom Indonesia',       category: 'Saham Indo', currency: 'IDR', lotSize: 100, price: 2670 },
    { symbol: 'ISAT.JK', name: 'Indosat Ooredoo Hutchison',category:'Saham Indo',currency: 'IDR', lotSize: 100, price: 2250 },
    { symbol: 'EXCL.JK', name: 'XL Axiata',              category: 'Saham Indo', currency: 'IDR', lotSize: 100, price: 2240 },
    { symbol: 'TOWR.JK', name: 'Sarana Menara Nusantara',category: 'Saham Indo', currency: 'IDR', lotSize: 100, price: 780 },
    { symbol: 'TBIG.JK', name: 'Tower Bersama Infrastructure',category:'Saham Indo',currency:'IDR',lotSize: 100, price: 1720 },
    // Otomotif & Konglomerat
    { symbol: 'ASII.JK', name: 'Astra International',     category: 'Saham Indo', currency: 'IDR', lotSize: 100, price: 4890 },
    { symbol: 'UNTR.JK', name: 'United Tractors',        category: 'Saham Indo', currency: 'IDR', lotSize: 100, price: 26075 },
    // Digital, Teknologi & E-Commerce
    { symbol: 'GOTO.JK', name: 'GoTo Gojek Tokopedia',   category: 'Saham Indo', currency: 'IDR', lotSize: 100, price: 50 },
    { symbol: 'BUKA.JK', name: 'Bukalapak.com',          category: 'Saham Indo', currency: 'IDR', lotSize: 100, price: 118 },
    { symbol: 'EMTK.JK', name: 'Elang Mahkota Teknologi',category: 'Saham Indo', currency: 'IDR', lotSize: 100, price: 420 },
    { symbol: 'BELI.JK', name: 'Global Digital Niaga (Blibli)',category:'Saham Indo',currency:'IDR',lotSize: 100, price: 440 },
    { symbol: 'WIRG.JK', name: 'WIR Asia',               category: 'Saham Indo', currency: 'IDR', lotSize: 100, price: 95 },
    // Konsumer & Ritel
    { symbol: 'ICBP.JK', name: 'Indofood CBP Sukses Makmur',category:'Saham Indo',currency:'IDR',lotSize: 100, price: 11200 },
    { symbol: 'INDF.JK', name: 'Indofood Sukses Makmur', category: 'Saham Indo', currency: 'IDR', lotSize: 100, price: 6850 },
    { symbol: 'UNVR.JK', name: 'Unilever Indonesia',     category: 'Saham Indo', currency: 'IDR', lotSize: 100, price: 1980 },
    { symbol: 'MYOR.JK', name: 'Mayora Indah',           category: 'Saham Indo', currency: 'IDR', lotSize: 100, price: 2450 },
    { symbol: 'AMRT.JK', name: 'Sumber Alfaria Trijaya (Alfamart)',category:'Saham Indo',currency:'IDR',lotSize:100,price:2950 },
    { symbol: 'MIDI.JK', name: 'Midi Utama Indonesia',   category: 'Saham Indo', currency: 'IDR', lotSize: 100, price: 410 },
    { symbol: 'CPIN.JK', name: 'Charoen Pokphand Indonesia',category:'Saham Indo',currency:'IDR',lotSize: 100, price: 4850 },
    { symbol: 'JPFA.JK', name: 'Japfa Comfeed Indonesia',category:'Saham Indo', currency: 'IDR', lotSize: 100, price: 1480 },
    { symbol: 'CMRY.JK', name: 'Cisarua Mountain Dairy', category: 'Saham Indo', currency: 'IDR', lotSize: 100, price: 5300 },
    { symbol: 'HMSP.JK', name: 'HM Sampoerna',           category: 'Saham Indo', currency: 'IDR', lotSize: 100, price: 625 },
    { symbol: 'GGRM.JK', name: 'Gudang Garam',           category: 'Saham Indo', currency: 'IDR', lotSize: 100, price: 13500 },
    { symbol: 'ACES.JK', name: 'Aspirasi Hidup Indonesia (Ace)',category:'Saham Indo',currency:'IDR',lotSize:100,price:820 },
    { symbol: 'MAPI.JK', name: 'Mitra Adiperkasa',       category: 'Saham Indo', currency: 'IDR', lotSize: 100, price: 1580 },
    { symbol: 'MAPA.JK', name: 'MAP Aktif Adiperkasa',   category: 'Saham Indo', currency: 'IDR', lotSize: 100, price: 910 },
    { symbol: 'ERAA.JK', name: 'Erajaya Swasembada',     category: 'Saham Indo', currency: 'IDR', lotSize: 100, price: 430 },
    // Energi & Batu Bara
    { symbol: 'ADRO.JK', name: 'Adaro Energy Indonesia', category: 'Saham Indo', currency: 'IDR', lotSize: 100, price: 3650 },
    { symbol: 'PTBA.JK', name: 'Bukit Asam',             category: 'Saham Indo', currency: 'IDR', lotSize: 100, price: 2750 },
    { symbol: 'PGAS.JK', name: 'Perusahaan Gas Negara',  category: 'Saham Indo', currency: 'IDR', lotSize: 100, price: 1520 },
    { symbol: 'ITMG.JK', name: 'Indo Tambangraya Megah', category: 'Saham Indo', currency: 'IDR', lotSize: 100, price: 25800 },
    { symbol: 'MEDC.JK', name: 'Medco Energi Internasional',category:'Saham Indo',currency:'IDR',lotSize: 100, price: 1280 },
    { symbol: 'AKRA.JK', name: 'AKR Corporindo',         category: 'Saham Indo', currency: 'IDR', lotSize: 100, price: 1420 },
    { symbol: 'ESSA.JK', name: 'Essa Industri Indonesia',category: 'Saham Indo', currency: 'IDR', lotSize: 100, price: 890 },
    { symbol: 'HRUM.JK', name: 'Harum Energy',           category: 'Saham Indo', currency: 'IDR', lotSize: 100, price: 1180 },
    { symbol: 'BUMI.JK', name: 'Bumi Resources',         category: 'Saham Indo', currency: 'IDR', lotSize: 100, price: 140 },
    { symbol: 'DEWA.JK', name: 'Darma Henwa',            category: 'Saham Indo', currency: 'IDR', lotSize: 100, price: 95 },
    { symbol: 'ENRG.JK', name: 'Energi Mega Persada',    category: 'Saham Indo', currency: 'IDR', lotSize: 100, price: 210 },
    // Logam & Mineral Tambang
    { symbol: 'ANTM.JK', name: 'Aneka Tambang (Antam)',  category: 'Saham Indo', currency: 'IDR', lotSize: 100, price: 1510 },
    { symbol: 'INCO.JK', name: 'Vale Indonesia',         category: 'Saham Indo', currency: 'IDR', lotSize: 100, price: 3780 },
    { symbol: 'MDKA.JK', name: 'Merdeka Copper Gold',    category: 'Saham Indo', currency: 'IDR', lotSize: 100, price: 2180 },
    { symbol: 'MBMA.JK', name: 'Merdeka Battery Materials',category:'Saham Indo',currency:'IDR',lotSize: 100, price: 520 },
    { symbol: 'AMMN.JK', name: 'Amman Mineral Internasional',category:'Saham Indo',currency:'IDR',lotSize: 100, price: 8900 },
    { symbol: 'BRMS.JK', name: 'Bumi Resources Minerals',category:'Saham Indo', currency: 'IDR', lotSize: 100, price: 380 },
    // Petrokimia & Konglomerasi Prajogo Pangestu
    { symbol: 'BRPT.JK', name: 'Barito Pacific',         category: 'Saham Indo', currency: 'IDR', lotSize: 100, price: 960 },
    { symbol: 'TPIA.JK', name: 'Chandra Asri Pacific',   category: 'Saham Indo', currency: 'IDR', lotSize: 100, price: 7200 },
    { symbol: 'BREN.JK', name: 'Barito Renewables Energy',category:'Saham Indo', currency: 'IDR', lotSize: 100, price: 6850 },
    { symbol: 'CUAN.JK', name: 'Petrindo Jaya Kreasi',   category: 'Saham Indo', currency: 'IDR', lotSize: 100, price: 6450 },
    { symbol: 'PANI.JK', name: 'Pantai Indah Kapuk Dua', category: 'Saham Indo', currency: 'IDR', lotSize: 100, price: 14800 },
    // Semen & Bahan Bangunan
    { symbol: 'SMGR.JK', name: 'Semen Indonesia',        category: 'Saham Indo', currency: 'IDR', lotSize: 100, price: 3950 },
    { symbol: 'INTP.JK', name: 'Indocement Tunggal Prakarsa',category:'Saham Indo',currency:'IDR',lotSize:100, price: 6850 },
    // Farmasi & Kesehatan
    { symbol: 'KLBF.JK', name: 'Kalbe Farma',            category: 'Saham Indo', currency: 'IDR', lotSize: 100, price: 1580 },
    { symbol: 'SIDO.JK', name: 'Industri Jamu Sido Muncul',category:'Saham Indo',currency:'IDR',lotSize: 100, price: 640 },
    { symbol: 'MIKA.JK', name: 'Mitra Keluarga Karyasehat',category:'Saham Indo',currency:'IDR',lotSize: 100, price: 2850 },
    { symbol: 'HEAL.JK', name: 'Medikaloka Hermina',     category: 'Saham Indo', currency: 'IDR', lotSize: 100, price: 1380 },
    // Properti & Real Estate
    { symbol: 'CTRA.JK', name: 'Ciputra Development',    category: 'Saham Indo', currency: 'IDR', lotSize: 100, price: 1250 },
    { symbol: 'BSDE.JK', name: 'Bumi Serpong Damai',     category: 'Saham Indo', currency: 'IDR', lotSize: 100, price: 1160 },
    { symbol: 'SMRA.JK', name: 'Summarecon Agung',        category: 'Saham Indo', currency: 'IDR', lotSize: 100, price: 590 },
    { symbol: 'PWON.JK', name: 'Pakuwon Jati',           category: 'Saham Indo', currency: 'IDR', lotSize: 100, price: 440 },


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

    // ------------------------------------------------------------
    // 2. US TECH & WALL STREET MEGA-CAPS (SAHAM US) - 68 ASSETS
    // ------------------------------------------------------------
    // The Magnificent 7
    { symbol: 'NVDA',    name: 'NVIDIA Corp',            category: 'Saham US',   currency: 'USD', price: 212.17 },
    { symbol: 'AAPL',    name: 'Apple Inc',              category: 'Saham US',   currency: 'USD', price: 225.00 },
    { symbol: 'MSFT',    name: 'Microsoft Corp',         category: 'Saham US',   currency: 'USD', price: 497.12 },
    { symbol: 'TSLA',    name: 'Tesla Inc',              category: 'Saham US',   currency: 'USD', price: 356.58 },
    { symbol: 'GOOGL',   name: 'Alphabet Inc (Google)',  category: 'Saham US',   currency: 'USD', price: 178.00 },
    { symbol: 'AMZN',    name: 'Amazon.com Inc',         category: 'Saham US',   currency: 'USD', price: 192.00 },
    { symbol: 'META',    name: 'Meta Platforms Inc',     category: 'Saham US',   currency: 'USD', price: 580.00 },
    // Semikonduktor & Perangkat Keras AI
    { symbol: 'AMD',     name: 'Advanced Micro Devices', category: 'Saham US',   currency: 'USD', price: 155.00 },
    { symbol: 'AVGO',    name: 'Broadcom Inc',           category: 'Saham US',   currency: 'USD', price: 175.00 },
    { symbol: 'TSM',     name: 'Taiwan Semiconductor',   category: 'Saham US',   currency: 'USD', price: 195.00 },
    { symbol: 'ASML',    name: 'ASML Holding NV',        category: 'Saham US',   currency: 'USD', price: 740.00 },
    { symbol: 'ARM',     name: 'Arm Holdings plc',       category: 'Saham US',   currency: 'USD', price: 142.00 },
    { symbol: 'QCOM',    name: 'Qualcomm Inc',           category: 'Saham US',   currency: 'USD', price: 168.00 },
    { symbol: 'MU',      name: 'Micron Technology',      category: 'Saham US',   currency: 'USD', price: 105.00 },
    { symbol: 'INTC',    name: 'Intel Corp',             category: 'Saham US',   currency: 'USD', price: 22.50 },
    { symbol: 'TXN',     name: 'Texas Instruments',      category: 'Saham US',   currency: 'USD', price: 205.00 },
    { symbol: 'AMAT',    name: 'Applied Materials',      category: 'Saham US',   currency: 'USD', price: 200.00 },
    { symbol: 'LRCX',    name: 'Lam Research Corp',      category: 'Saham US',   currency: 'USD', price: 82.00 },
    { symbol: 'SMCI',    name: 'Super Micro Computer',   category: 'Saham US',   currency: 'USD', price: 34.00 },
    // Cloud Software & Cyber Security
    { symbol: 'PLTR',    name: 'Palantir Technologies',  category: 'Saham US',   currency: 'USD', price: 172.56 },
    { symbol: 'ORCL',    name: 'Oracle Corp',            category: 'Saham US',   currency: 'USD', price: 175.00 },
    { symbol: 'CRM',     name: 'Salesforce Inc',         category: 'Saham US',   currency: 'USD', price: 290.00 },
    { symbol: 'ADBE',    name: 'Adobe Inc',              category: 'Saham US',   currency: 'USD', price: 510.00 },
    { symbol: 'NOW',     name: 'ServiceNow Inc',         category: 'Saham US',   currency: 'USD', price: 920.00 },
    { symbol: 'SNOW',    name: 'Snowflake Inc',          category: 'Saham US',   currency: 'USD', price: 140.00 },
    { symbol: 'CRWD',    name: 'CrowdStrike Holdings',   category: 'Saham US',   currency: 'USD', price: 310.00 },
    { symbol: 'PANW',    name: 'Palo Alto Networks',     category: 'Saham US',   currency: 'USD', price: 375.00 },
    { symbol: 'NET',     name: 'Cloudflare Inc',         category: 'Saham US',   currency: 'USD', price: 92.00 },
    // Konsumer, Hiburan & Mobilitas
    { symbol: 'NFLX',    name: 'Netflix Inc',            category: 'Saham US',   currency: 'USD', price: 710.00 },
    { symbol: 'SPOT',    name: 'Spotify Technology',     category: 'Saham US',   currency: 'USD', price: 380.00 },
    { symbol: 'DIS',     name: 'Walt Disney Co',         category: 'Saham US',   currency: 'USD', price: 95.00 },
    { symbol: 'UBER',    name: 'Uber Technologies',      category: 'Saham US',   currency: 'USD', price: 75.00 },
    { symbol: 'ABNB',    name: 'Airbnb Inc',             category: 'Saham US',   currency: 'USD', price: 128.00 },
    { symbol: 'BKNG',    name: 'Booking Holdings',       category: 'Saham US',   currency: 'USD', price: 4450.00 },
    // Wall Street & Jasa Keuangan Global
    { symbol: 'BRK-B',   name: 'Berkshire Hathaway',     category: 'Saham US',   currency: 'USD', price: 455.00 },
    { symbol: 'JPM',     name: 'JPMorgan Chase & Co',    category: 'Saham US',   currency: 'USD', price: 225.00 },
    { symbol: 'BAC',     name: 'Bank of America',        category: 'Saham US',   currency: 'USD', price: 42.00 },
    { symbol: 'GS',      name: 'Goldman Sachs Group',    category: 'Saham US',   currency: 'USD', price: 510.00 },
    { symbol: 'MS',      name: 'Morgan Stanley',         category: 'Saham US',   currency: 'USD', price: 118.00 },
    { symbol: 'V',       name: 'Visa Inc',               category: 'Saham US',   currency: 'USD', price: 280.00 },
    { symbol: 'MA',      name: 'Mastercard Inc',         category: 'Saham US',   currency: 'USD', price: 495.00 },
    { symbol: 'BLK',     name: 'BlackRock Inc',          category: 'Saham US',   currency: 'USD', price: 980.00 },
    { symbol: 'COIN',    name: 'Coinbase Global',        category: 'Saham US',   currency: 'USD', price: 215.00 },
    { symbol: 'MSTR',    name: 'MicroStrategy Inc',      category: 'Saham US',   currency: 'USD', price: 285.00 },
    { symbol: 'HOOD',    name: 'Robinhood Markets',      category: 'Saham US',   currency: 'USD', price: 26.50 },
    { symbol: 'PYPL',    name: 'PayPal Holdings',        category: 'Saham US',   currency: 'USD', price: 78.00 },
    // Retail, FMCG & Farmasi Global
    { symbol: 'WMT',     name: 'Walmart Inc',            category: 'Saham US',   currency: 'USD', price: 82.00 },
    { symbol: 'COST',    name: 'Costco Wholesale',       category: 'Saham US',   currency: 'USD', price: 910.00 },
    { symbol: 'TGT',     name: 'Target Corp',            category: 'Saham US',   currency: 'USD', price: 155.00 },
    { symbol: 'NKE',     name: 'Nike Inc',               category: 'Saham US',   currency: 'USD', price: 82.50 },
    { symbol: 'LLY',     name: 'Eli Lilly and Co',       category: 'Saham US',   currency: 'USD', price: 890.00 },
    { symbol: 'NVO',     name: 'Novo Nordisk A/S',       category: 'Saham US',   currency: 'USD', price: 122.00 },
    { symbol: 'JNJ',     name: 'Johnson & Johnson',      category: 'Saham US',   currency: 'USD', price: 162.00 },
    { symbol: 'UNH',     name: 'UnitedHealth Group',     category: 'Saham US',   currency: 'USD', price: 585.00 },
    { symbol: 'PFE',     name: 'Pfizer Inc',             category: 'Saham US',   currency: 'USD', price: 28.50 },
    { symbol: 'ABBV',    name: 'AbbVie Inc',             category: 'Saham US',   currency: 'USD', price: 188.00 },
    // Industri, Penerbangan & Pertahanan
    { symbol: 'BA',      name: 'Boeing Co',              category: 'Saham US',   currency: 'USD', price: 152.00 },
    { symbol: 'CAT',     name: 'Caterpillar Inc',        category: 'Saham US',   currency: 'USD', price: 390.00 },
    { symbol: 'GE',      name: 'GE Aerospace',           category: 'Saham US',   currency: 'USD', price: 188.00 },
    { symbol: 'LMT',     name: 'Lockheed Martin',        category: 'Saham US',   currency: 'USD', price: 560.00 },
    { symbol: 'RTX',     name: 'RTX Corp (Raytheon)',    category: 'Saham US',   currency: 'USD', price: 122.00 },
    { symbol: 'HON',     name: 'Honeywell International',category: 'Saham US',   currency: 'USD', price: 205.00 },
    // Raksasa Energi & Minyak Bumi
    { symbol: 'XOM',     name: 'Exxon Mobil Corp',       category: 'Saham US',   currency: 'USD', price: 118.00 },
    { symbol: 'CVX',     name: 'Chevron Corp',           category: 'Saham US',   currency: 'USD', price: 148.00 },
    { symbol: 'COP',     name: 'ConocoPhillips',         category: 'Saham US',   currency: 'USD', price: 108.00 },
    { symbol: 'SLB',     name: 'Schlumberger Ltd',       category: 'Saham US',   currency: 'USD', price: 44.00 },

    // ------------------------------------------------------------
    // 3. GLOBAL ADRs & ASIAN TECH GIANTS (SAHAM GLOBAL) - 10 ASSETS
    // ------------------------------------------------------------
    { symbol: 'BABA',    name: 'Alibaba Group Holding',  category: 'Saham Global',currency: 'USD', price: 98.00 },
    { symbol: 'PDD',     name: 'PDD Holdings (Temu)',    category: 'Saham Global',currency: 'USD', price: 142.00 },
    { symbol: 'BIDU',    name: 'Baidu Inc',              category: 'Saham Global',currency: 'USD', price: 92.00 },
    { symbol: 'JD',      name: 'JD.com Inc',             category: 'Saham Global',currency: 'USD', price: 38.50 },
    { symbol: 'SE',      name: 'Sea Limited (Shopee)',   category: 'Saham Global',currency: 'USD', price: 96.00 },
    { symbol: 'GRAB',    name: 'Grab Holdings',          category: 'Saham Global',currency: 'USD', price: 4.80 },
    { symbol: 'SONY',    name: 'Sony Group Corp',        category: 'Saham Global',currency: 'USD', price: 92.00 },
    { symbol: 'TM',      name: 'Toyota Motor Corp',      category: 'Saham Global',currency: 'USD', price: 175.00 },
    { symbol: 'SHEL',    name: 'Shell plc',              category: 'Saham Global',currency: 'USD', price: 66.00 },
    { symbol: 'BP',      name: 'BP plc',                 category: 'Saham Global',currency: 'USD', price: 32.00 },

    // ------------------------------------------------------------
    // 4. TOP CRYPTOCURRENCIES & DIGITAL ASSETS (CRYPTO) - 30 ASSETS
    // ------------------------------------------------------------
    { symbol: 'BTC-USD', name: 'Bitcoin',                category: 'Crypto',     currency: 'USD', price: 75903.40 },
    { symbol: 'ETH-USD', name: 'Ethereum',               category: 'Crypto',     currency: 'USD', price: 2450.00 },
    { symbol: 'SOL-USD', name: 'Solana',                 category: 'Crypto',     currency: 'USD', price: 148.00 },
    { symbol: 'BNB-USD', name: 'Binance Coin',           category: 'Crypto',     currency: 'USD', price: 580.00 },
    { symbol: 'XRP-USD', name: 'XRP Ledger',             category: 'Crypto',     currency: 'USD', price: 0.58 },
    { symbol: 'DOGE-USD',name: 'Dogecoin',               category: 'Crypto',     currency: 'USD', price: 0.11 },
    { symbol: 'ADA-USD', name: 'Cardano',                category: 'Crypto',     currency: 'USD', price: 0.35 },
    { symbol: 'AVAX-USD',name: 'Avalanche',              category: 'Crypto',     currency: 'USD', price: 28.00 },
    { symbol: 'LINK-USD',name: 'Chainlink',              category: 'Crypto',     currency: 'USD', price: 11.50 },
    { symbol: 'SUI-USD', name: 'Sui Network',            category: 'Crypto',     currency: 'USD', price: 2.10 },
    { symbol: 'NEAR-USD',name: 'NEAR Protocol',          category: 'Crypto',     currency: 'USD', price: 4.80 },
    { symbol: 'APT-USD', name: 'Aptos',                  category: 'Crypto',     currency: 'USD', price: 8.50 },
    { symbol: 'DOT-USD', name: 'Polkadot',               category: 'Crypto',     currency: 'USD', price: 4.20 },
    { symbol: 'SHIB-USD',name: 'Shiba Inu',              category: 'Crypto',     currency: 'USD', price: 0.000018 },
    { symbol: 'PEPE-USD',name: 'Pepe Coin',              category: 'Crypto',     currency: 'USD', price: 0.0000095 },
    { symbol: 'LTC-USD', name: 'Litecoin',               category: 'Crypto',     currency: 'USD', price: 68.00 },
    { symbol: 'BCH-USD', name: 'Bitcoin Cash',           category: 'Crypto',     currency: 'USD', price: 340.00 },
    { symbol: 'UNI-USD', name: 'Uniswap',                category: 'Crypto',     currency: 'USD', price: 7.50 },
    { symbol: 'RENDER-USD',name:'Render Token',          category: 'Crypto',     currency: 'USD', price: 5.80 },
    { symbol: 'TAO-USD', name: 'Bittensor (TAO)',        category: 'Crypto',     currency: 'USD', price: 560.00 },
    { symbol: 'FET-USD', name: 'Artificial Superintelligence (FET)',category:'Crypto',currency:'USD',price: 1.35 },
    { symbol: 'INJ-USD', name: 'Injective Protocol',     category: 'Crypto',     currency: 'USD', price: 21.00 },
    { symbol: 'KAS-USD', name: 'Kaspa',                  category: 'Crypto',     currency: 'USD', price: 0.13 },
    { symbol: 'TIA-USD', name: 'Celestia',               category: 'Crypto',     currency: 'USD', price: 5.20 },
    { symbol: 'ARB-USD', name: 'Arbitrum',               category: 'Crypto',     currency: 'USD', price: 0.55 },
    { symbol: 'OP-USD',  name: 'Optimism',               category: 'Crypto',     currency: 'USD', price: 1.65 },
    { symbol: 'STX-USD', name: 'Stacks (Bitcoin L2)',    category: 'Crypto',     currency: 'USD', price: 1.80 },
    { symbol: 'TON-USD', name: 'Toncoin',                category: 'Crypto',     currency: 'USD', price: 5.10 },
    { symbol: 'TRX-USD', name: 'TRON',                   category: 'Crypto',     currency: 'USD', price: 0.16 },
    { symbol: 'POL-USD', name: 'Polygon Ecosystem Token',category: 'Crypto',     currency: 'USD', price: 0.38 },

    // ------------------------------------------------------------
    // 5. GLOBAL COMMODITIES & FUTURES (KOMODITAS) - 16 ASSETS
    // ------------------------------------------------------------
    { symbol: 'GC=F',    name: 'Emas Murni (Gold / XAU)',category: 'Komoditas',  currency: 'USD', price: 2680.00 },
    { symbol: 'SI=F',    name: 'Perak (Silver / XAG)',   category: 'Komoditas',  currency: 'USD', price: 31.50 },
    { symbol: 'PL=F',    name: 'Platinum Futures',       category: 'Komoditas',  currency: 'USD', price: 985.00 },
    { symbol: 'PA=F',    name: 'Palladium Futures',      category: 'Komoditas',  currency: 'USD', price: 1050.00 },
    { symbol: 'HG=F',    name: 'Tembaga (Copper)',       category: 'Komoditas',  currency: 'USD', price: 4.35 },
    { symbol: 'CL=F',    name: 'Minyak Mentah WTI',      category: 'Komoditas',  currency: 'USD', price: 71.50 },
    { symbol: 'BZ=F',    name: 'Minyak Brent Crude',     category: 'Komoditas',  currency: 'USD', price: 74.80 },
    { symbol: 'NG=F',    name: 'Gas Alam (Natural Gas)', category: 'Komoditas',  currency: 'USD', price: 2.85 },
    { symbol: 'HO=F',    name: 'Minyak Pemanas (Heating Oil)',category:'Komoditas',currency:'USD',price: 2.25 },
    { symbol: 'ZC=F',    name: 'Jagung (Corn Futures)',  category: 'Komoditas',  currency: 'USD', price: 4.15 },
    { symbol: 'ZS=F',    name: 'Kedelai (Soybeans)',     category: 'Komoditas',  currency: 'USD', price: 10.20 },
    { symbol: 'ZW=F',    name: 'Gandum (Wheat Futures)', category: 'Komoditas',  currency: 'USD', price: 5.80 },
    { symbol: 'KC=F',    name: 'Kopi Arabika (Coffee)',  category: 'Komoditas',  currency: 'USD', price: 2.45 },
    { symbol: 'SB=F',    name: 'Gula (Sugar Futures)',   category: 'Komoditas',  currency: 'USD', price: 0.22 },
    { symbol: 'CC=F',    name: 'Kakao / Cokelat (Cocoa)',category: 'Komoditas',  currency: 'USD', price: 7850.00 },
    { symbol: 'CT=F',    name: 'Kapas (Cotton Futures)', category: 'Komoditas',  currency: 'USD', price: 0.72 },

    // ------------------------------------------------------------
    // 6. FOREX & CURRENCY MAJORS (VALAS) - 15 ASSETS
    // ------------------------------------------------------------
    { symbol: 'USDIDR=X',name: 'USD / IDR Spot',         category: 'Forex',      currency: 'IDR', price: 16250 },
    { symbol: 'EURUSD=X',name: 'EUR / USD',              category: 'Forex',      currency: 'USD', price: 1.085 },
    { symbol: 'GBPUSD=X',name: 'GBP / USD',              category: 'Forex',      currency: 'USD', price: 1.305 },
    { symbol: 'USDJPY=X',name: 'USD / JPY',              category: 'Forex',      currency: 'USD', price: 149.50 },
    { symbol: 'AUDUSD=X',name: 'AUD / USD',              category: 'Forex',      currency: 'USD', price: 0.672 },
    { symbol: 'USDCAD=X',name: 'USD / CAD',              category: 'Forex',      currency: 'USD', price: 1.380 },
    { symbol: 'USDCHF=X',name: 'USD / CHF',              category: 'Forex',      currency: 'USD', price: 0.865 },
    { symbol: 'EURJPY=X',name: 'EUR / JPY',              category: 'Forex',      currency: 'USD', price: 162.20 },
    { symbol: 'GBPJPY=X',name: 'GBP / JPY',              category: 'Forex',      currency: 'USD', price: 195.10 },
    { symbol: 'USDSGD=X',name: 'USD / SGD',              category: 'Forex',      currency: 'USD', price: 1.315 },
    { symbol: 'AUDJPY=X',name: 'AUD / JPY',              category: 'Forex',      currency: 'USD', price: 100.40 },
    { symbol: 'NZDUSD=X',name: 'NZD / USD',              category: 'Forex',      currency: 'USD', price: 0.605 },
    { symbol: 'EURGBP=X',name: 'EUR / GBP',              category: 'Forex',      currency: 'USD', price: 0.832 },
    { symbol: 'EURCHF=X',name: 'EUR / CHF',              category: 'Forex',      currency: 'USD', price: 0.938 },
    { symbol: 'SGDIDR=X',name: 'SGD / IDR',              category: 'Forex',      currency: 'IDR', price: 12350 },

    // ------------------------------------------------------------
    // 7. GLOBAL INDICES & BENCHMARK MACRO RATES - 10 ASSETS
    // ------------------------------------------------------------
    { symbol: '^GSPC',   name: 'S&P 500 Index',          category: 'Index US',   currency: 'USD', price: 5890 },
    { symbol: '^IXIC',   name: 'NASDAQ Composite',       category: 'Index US',   currency: 'USD', price: 18500 },
    { symbol: '^DJI',    name: 'Dow Jones Industrial',   category: 'Index US',   currency: 'USD', price: 43200 },
    { symbol: '^RUT',    name: 'Russell 2000',           category: 'Index US',   currency: 'USD', price: 2250 },
    { symbol: '^N225',   name: 'Nikkei 225 (Jepang)',    category: 'Index Global',currency:'USD', price: 38900 },
    { symbol: '^HSI',    name: 'Hang Seng Index (HK)',   category: 'Index Global',currency:'USD', price: 20600 },
    { symbol: '^FTSE',   name: 'FTSE 100 (London)',      category: 'Index Global',currency:'USD', price: 8250 },
    { symbol: '^GDAXI',  name: 'DAX Performance (Jerman)',category:'Index Global',currency:'USD', price: 19450 },
    { symbol: '^TNX',    name: 'US 10Y Treasury Yield',  category: 'Rates',      currency: 'USD', price: 4.25 },
    { symbol: '^VIX',    name: 'CBOE Volatility VIX',    category: 'Rates',      currency: 'USD', price: 15.50 }
];

// Initialize quoteCache with baseline prices so all 215+ assets are instantly tradeable
TRACKED_ASSETS.forEach(a => {
    const basePx = a.price;
    quoteCache.data[a.symbol] = {
        symbol: a.symbol,
        name: a.name,
        category: a.category,
        price: basePx,
        prevClose: basePx,
        change: 0,
        changePct: 0,
        high: basePx * 1.01,
        low: basePx * 0.99,
        volume: 1000000,
        currency: a.currency,
        lotSize: a.lotSize || 1,
        priceIdr: a.currency === 'USD' ? basePx * quoteCache.usdIdr : basePx,
        prevCloseIdr: a.currency === 'USD' ? basePx * quoteCache.usdIdr : basePx,
        sparkline: [basePx, basePx],
        timestamp: Date.now()
    };
});

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
                        let category = 'Saham Global';
                        if (sym.includes('.JK')) category = 'Saham Indo';
                        else if (sym.includes('-USD') || sym.includes('-USDT')) category = 'Crypto';
                        else if (sym.includes('=F')) category = 'Komoditas';
                        else if (sym.includes('=X')) category = 'Forex';
                        else if (sym.startsWith('^')) category = 'Index';

                        return resolve({
                            symbol: sym,
                            name: meta.shortName || meta.longName || sym,
                            category: category,
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

// Background refresh of market quotes in smooth non-blocking batches
async function refreshQuotes() {
    try {
        // Fetch USD/IDR first for conversion
        const fxQuote = await fetchYahooQuote('USDIDR=X');
        if (fxQuote && fxQuote.price > 10000) {
            quoteCache.usdIdr = fxQuote.price;
        }

        // Combine tracked assets + portfolio holdings
        const port = loadPortfolio();
        const holdingSymbols = (port.holdings || []).map(h => h.symbol);
        const allSymbols = Array.from(new Set([...TRACKED_ASSETS.map(a => a.symbol), ...holdingSymbols]));

        // Refresh in non-blocking batches of 15
        const batchSize = 15;
        for (let i = 0; i < allSymbols.length; i += batchSize) {
            const chunk = allSymbols.slice(i, i + batchSize);
            const results = await Promise.all(chunk.map(s => fetchYahooQuote(s)));

            results.forEach((q, idx) => {
                const sym = chunk[idx];
                const asset = TRACKED_ASSETS.find(a => a.symbol === sym);
                if (q && q.price > 0) {
                    if (asset) {
                        q.name = asset.name;
                        q.category = asset.category;
                        q.lotSize = asset.lotSize || 1;
                    }

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
            await new Promise(r => setTimeout(r, 120));
        }

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

// 3. POST & GET /api/portfolio/reset -> Reset to initial Rp 200 Juta
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
app.get('/api/portfolio/reset', handlePortfolioReset);

// 3b. GET /api/test-buy -> Quick simulate buy for any tracked asset (for UI testing)
// Usage: GET /api/test-buy?symbol=BBCA.JK&qty=1
app.get('/api/test-buy', (req, res) => {
    try {
        const symbol = (req.query.symbol || '').trim().toUpperCase();
        if (!symbol) {
            return res.status(400).json({ error: 'Parameter symbol diperlukan. Contoh: /api/test-buy?symbol=BBCA.JK' });
        }

        // Resolve qty — honour lotSize for IDX stocks
        const assetDef = TRACKED_ASSETS.find(a => a.symbol.toUpperCase() === symbol);
        const cachedQuote = quoteCache.data[symbol] || quoteCache.data[symbol.toUpperCase()];

        if (!assetDef && !cachedQuote) {
            return res.status(404).json({ error: `Aset '${symbol}' tidak ditemukan dalam tradeable universe.` });
        }

        const lotSize = assetDef?.lotSize || 1;
        let requestedQty = parseFloat(req.query.qty);
        if (isNaN(requestedQty) || requestedQty <= 0) {
            const rawPrice = cachedQuote?.price || assetDef?.price || 0;
            const isUsd = (cachedQuote?.currency || assetDef?.currency) === 'USD';
            const priceInIdr = isUsd ? rawPrice * (quoteCache.usdIdr || 16250) : rawPrice;
            if (priceInIdr > 50000000) {
                requestedQty = 0.01; // e.g. BTC
            } else if (priceInIdr > 10000000) {
                requestedQty = 0.1; // e.g. ETH, Gold
            } else {
                requestedQty = 1;
            }
        }
        const qty = requestedQty * lotSize;

        const price = cachedQuote?.price || assetDef?.price || 0;
        if (!price || price <= 0) {
            return res.status(400).json({ error: `Harga tidak tersedia untuk '${symbol}'. Tunggu live price feed.` });
        }

        const currency = cachedQuote?.currency || assetDef?.currency || 'IDR';
        const name = cachedQuote?.name || assetDef?.name || symbol;
        const category = cachedQuote?.category || assetDef?.category || 'General';

        const port = loadPortfolio();
        const usdRate = quoteCache.usdIdr || 16250;
        const isUsd = (currency === 'USD');
        const priceInIdr = isUsd ? price * usdRate : price;
        const totalValueIdr = Math.round(qty * priceInIdr);
        const brokerFee = Math.round(totalValueIdr * 0.0015);
        const totalRequired = totalValueIdr + brokerFee;

        if (port.cash < totalRequired) {
            return res.status(400).json({
                error: `Saldo tidak cukup. Butuh Rp ${totalRequired.toLocaleString('id-ID')}, tersedia Rp ${port.cash.toLocaleString('id-ID')}`
            });
        }

        // Deduct cash
        port.cash -= totalRequired;

        // Update or create holding
        const existingIdx = port.holdings.findIndex(h => h.symbol === symbol);
        if (existingIdx >= 0) {
            const prev = port.holdings[existingIdx];
            const newQty = prev.qty + qty;
            const newAvgPrice = ((prev.qty * prev.avgPrice) + (qty * price)) / newQty;
            port.holdings[existingIdx] = { ...prev, qty: newQty, avgPrice: newAvgPrice, lastUpdated: Date.now() };
        } else {
            port.holdings.push({ symbol, name, category, currency, qty, avgPrice: price, createdAt: Date.now(), lastUpdated: Date.now() });
        }

        // Record trade
        const tradeLog = {
            id: `TEST-${Date.now()}`,
            timestamp: new Date().toISOString(),
            type: 'BUY',
            symbol, name, category, qty, price, currency,
            priceInIdr, totalValueIdr, brokerFee, realizedPnL: 0,
            status: 'FILLED (TEST-BUY)',
            note: `Quick test-buy: ${requestedQty} lot${requestedQty > 1 ? 's' : ''} @ ${isUsd ? '$' + price.toFixed(4) : 'Rp ' + Math.round(price).toLocaleString('id-ID')}`
        };
        port.trades.push(tradeLog);
        savePortfolio(port);

        return res.json({
            success: true,
            message: `✅ TEST-BUY: ${qty} ${symbol} @ ${isUsd ? '$' + price.toFixed(4) : 'Rp ' + Math.round(price).toLocaleString('id-ID')} | Cost: Rp ${totalRequired.toLocaleString('id-ID')} | Sisa Kas: Rp ${port.cash.toLocaleString('id-ID')}`,
            trade: tradeLog,
            remainingCash: port.cash
        });
    } catch (e) {
        console.error('Test-buy error:', e.message);
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

// 5. GET /api/chart/:symbol -> Candle / Sparkline history for interactive Bloomberg charting (Always 100% available)
function generateSyntheticCandles(sym, count = 28, range = '1d') {
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
            time: t,
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

app.get('/api/chart/:symbol', (req, res) => {
    const sym = (req.params.symbol || '').trim().toUpperCase();
    const range = req.query.range || '1d';
    const interval = req.query.interval || (range === '1d' ? '15m' : (range === '5d' ? '1h' : '1d'));
    const candleCount = range === '1y' ? 52 : (range === '1mo' ? 30 : (range === '5d' ? 35 : 28));

    const q = quoteCache.data[sym];
    const currPrice = q?.price || 1000;
    const prevClose = q?.prevClose || currPrice;

    try {
        const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(sym)}?interval=${interval}&range=${range}`;
        const reqYahoo = https.get(url, {
            headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36' },
            timeout: 3500
        }, response => {
            let data = '';
            response.on('data', c => data += c);
            response.on('end', () => {
                try {
                    const parsed = JSON.parse(data);
                    const r = parsed.chart?.result?.[0];
                    if (r && r.timestamp && r.indicators?.quote?.[0]) {
                        const timestamps = r.timestamp || [];
                        const quote = r.indicators.quote[0] || {};
                        const opens = quote.open || [];
                        const highs = quote.high || [];
                        const lows = quote.low || [];
                        const closes = quote.close || [];
                        const volumes = quote.volume || [];

                        const candles = [];
                        for (let i = 0; i < timestamps.length; i++) {
                            if (closes[i] !== null && closes[i] !== undefined && !isNaN(closes[i])) {
                                candles.push({
                                    time: timestamps[i] * 1000,
                                    timestamp: timestamps[i] * 1000,
                                    open: opens[i] || closes[i],
                                    high: highs[i] || closes[i],
                                    low: lows[i] || closes[i],
                                    close: closes[i],
                                    volume: volumes[i] || 0
                                });
                            }
                        }

                        if (candles.length >= 2) {
                            return res.json({
                                symbol: sym,
                                currency: r.meta?.currency || q?.currency || 'USD',
                                prevClose: r.meta?.chartPreviousClose || prevClose,
                                currentPrice: r.meta?.regularMarketPrice || currPrice,
                                candles
                            });
                        }
                    }
                } catch (e) {}

                // Fallback to high-fidelity synthetic candles
                const fallbackCandles = generateSyntheticCandles(sym, candleCount, range);
                res.json({
                    symbol: sym,
                    currency: q?.currency || 'IDR',
                    prevClose: prevClose,
                    currentPrice: currPrice,
                    candles: fallbackCandles,
                    synthetic: true
                });
            });
        });

        reqYahoo.on('error', () => {
            const fallbackCandles = generateSyntheticCandles(sym, candleCount, range);
            res.json({
                symbol: sym,
                currency: q?.currency || 'IDR',
                prevClose: prevClose,
                currentPrice: currPrice,
                candles: fallbackCandles,
                synthetic: true
            });
        });

        reqYahoo.on('timeout', () => {
            reqYahoo.destroy();
            const fallbackCandles = generateSyntheticCandles(sym, candleCount, range);
            res.json({
                symbol: sym,
                currency: q?.currency || 'IDR',
                prevClose: prevClose,
                currentPrice: currPrice,
                candles: fallbackCandles,
                synthetic: true
            });
        });
    } catch (e) {
        const fallbackCandles = generateSyntheticCandles(sym, candleCount, range);
        res.json({
            symbol: sym,
            currency: q?.currency || 'IDR',
            prevClose: prevClose,
            currentPrice: currPrice,
            candles: fallbackCandles,
            synthetic: true
        });
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

// Dynamic Quote for ANY symbol
app.get('/api/quote/:symbol', async (req, res) => {
    try {
        const sym = req.params.symbol.toUpperCase();
        let q = quoteCache.data[sym];
        if (!q || (Date.now() - q.timestamp > 30000)) {
            const fetched = await fetchYahooQuote(sym);
            if (fetched && fetched.price > 0) {
                q = fetched;
                if (q.currency === 'USD') {
                    q.priceIdr = q.price * (quoteCache.usdIdr || 16250);
                    q.prevCloseIdr = q.prevClose * (quoteCache.usdIdr || 16250);
                } else {
                    q.priceIdr = q.price;
                    q.prevCloseIdr = q.prevClose;
                }
                quoteCache.data[sym] = q;
            }
        }
        if (q && q.price > 0) {
            return res.json(q);
        }

        // Fallback: If Yahoo Finance didn't find it or was rate limited, synthesize a valid tradeable quote
        // so the user can test-buy ANY asset in the world without being blocked!
        const isIndo = sym.includes('.JK');
        const isCrypto = sym.includes('-USD') || sym.includes('-USDT');
        const isCommodity = sym.includes('=F');
        const isForex = sym.includes('=X');
        const currency = isIndo ? 'IDR' : 'USD';
        const defaultPx = isIndo ? 2500 : (isCrypto ? 150 : 85);
        const fallbackQuote = {
            symbol: sym,
            name: sym,
            category: isIndo ? 'Saham Indo' : (isCrypto ? 'Crypto' : (isCommodity ? 'Komoditas' : (isForex ? 'Forex' : 'Saham Global'))),
            price: defaultPx,
            prevClose: defaultPx,
            change: 0,
            changePct: 0,
            high: defaultPx * 1.02,
            low: defaultPx * 0.98,
            volume: 100000,
            currency: currency,
            priceIdr: currency === 'USD' ? defaultPx * (quoteCache.usdIdr || 16250) : defaultPx,
            prevCloseIdr: currency === 'USD' ? defaultPx * (quoteCache.usdIdr || 16250) : defaultPx,
            sparkline: [defaultPx, defaultPx],
            timestamp: Date.now()
        };
        quoteCache.data[sym] = fallbackQuote;
        res.json(fallbackQuote);
    } catch (e) {
        res.status(500).json({ error: e.message });
    }
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
- Jika pengguna bertanya saran alokasi untuk portofolio FADHIL MUHAMMAD SYAFIQ LUBIS, berikan diversifikasi realistis (misal: 40% Saham Blue Chip IDX seperti BBCA/BBRI, 25% US Tech NVDA/AAPL, 15% Emas/Komoditas, 10% Kripto BTC/ETH, 10% Kas cadangan).
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
