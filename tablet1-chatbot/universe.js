// Comprehensive Bloomberg Terminal Multi-Asset Global Universe
// 1,000+ Tradeable Assets: SpaceX, Space Tech, Pre-IPOs, All 850+ IDX Stocks,
// US S&P500/Nasdaq Mega-caps, Hot IPOs, Top 100 Cryptos, Commodities, Forex, and Global Indices.

const SPACE_TECH_ASSETS = [
    {
        "symbol": "SPACEX",
        "name": "Space Exploration Technologies (Pre-IPO)",
        "category": "Space Tech & Pre-IPO",
        "currency": "USD",
        "lotSize": 1,
        "price": 135
    },
    {
        "symbol": "DXYZ",
        "name": "Destiny Tech100 Inc (SpaceX Portfolio)",
        "category": "Space Tech & Pre-IPO",
        "currency": "USD",
        "lotSize": 1,
        "price": 28.5
    },
    {
        "symbol": "RKLB",
        "name": "Rocket Lab USA Inc",
        "category": "Space Tech & Pre-IPO",
        "currency": "USD",
        "lotSize": 1,
        "price": 22.8
    },
    {
        "symbol": "ASTS",
        "name": "AST SpaceMobile Inc",
        "category": "Space Tech & Pre-IPO",
        "currency": "USD",
        "lotSize": 1,
        "price": 27.6
    },
    {
        "symbol": "LUNR",
        "name": "Intuitive Machines Inc (Moon Lander)",
        "category": "Space Tech & Pre-IPO",
        "currency": "USD",
        "lotSize": 1,
        "price": 11.4
    },
    {
        "symbol": "ARKX",
        "name": "ARK Space Exploration & Innovation ETF",
        "category": "Space Tech & Pre-IPO",
        "currency": "USD",
        "lotSize": 1,
        "price": 17.5
    },
    {
        "symbol": "UFO",
        "name": "Procure Space ETF",
        "category": "Space Tech & Pre-IPO",
        "currency": "USD",
        "lotSize": 1,
        "price": 18.2
    },
    {
        "symbol": "PL",
        "name": "Planet Labs PBC (Earth Observation)",
        "category": "Space Tech & Pre-IPO",
        "currency": "USD",
        "lotSize": 1,
        "price": 3.25
    },
    {
        "symbol": "RDW",
        "name": "Redwire Corporation (Space Infrastructure)",
        "category": "Space Tech & Pre-IPO",
        "currency": "USD",
        "lotSize": 1,
        "price": 9.8
    },
    {
        "symbol": "MNTS",
        "name": "Momentus Inc (Space Transport)",
        "category": "Space Tech & Pre-IPO",
        "currency": "USD",
        "lotSize": 1,
        "price": 1.45
    },
    {
        "symbol": "BKSY",
        "name": "BlackSky Technology Inc",
        "category": "Space Tech & Pre-IPO",
        "currency": "USD",
        "lotSize": 1,
        "price": 7.9
    },
    {
        "symbol": "SPCE",
        "name": "Virgin Galactic Holdings",
        "category": "Space Tech & Pre-IPO",
        "currency": "USD",
        "lotSize": 1,
        "price": 5.8
    },
    {
        "symbol": "OPENAI",
        "name": "OpenAI Inc (Pre-IPO Secondary Desk)",
        "category": "Space Tech & Pre-IPO",
        "currency": "USD",
        "lotSize": 1,
        "price": 155
    },
    {
        "symbol": "ANTHROPIC",
        "name": "Anthropic PBC (Pre-IPO Secondary Desk)",
        "category": "Space Tech & Pre-IPO",
        "currency": "USD",
        "lotSize": 1,
        "price": 42
    },
    {
        "symbol": "STRIPE",
        "name": "Stripe Inc (Pre-IPO Secondary Desk)",
        "category": "Space Tech & Pre-IPO",
        "currency": "USD",
        "lotSize": 1,
        "price": 29.5
    },
    {
        "symbol": "BYTEDANCE",
        "name": "ByteDance Ltd (Pre-IPO Valuation)",
        "category": "Space Tech & Pre-IPO",
        "currency": "USD",
        "lotSize": 1,
        "price": 185
    }
];

const HOT_IPO_ASSETS = [
    {
        "symbol": "BREN.JK",
        "name": "Barito Renewables Energy Tbk",
        "category": "Saham IPO",
        "currency": "IDR",
        "lotSize": 100,
        "price": 6850
    },
    {
        "symbol": "CUAN.JK",
        "name": "Petrindo Jaya Kreasi Tbk",
        "category": "Saham IPO",
        "currency": "IDR",
        "lotSize": 100,
        "price": 6450
    },
    {
        "symbol": "AMMN.JK",
        "name": "Amman Mineral Internasional Tbk",
        "category": "Saham IPO",
        "currency": "IDR",
        "lotSize": 100,
        "price": 8900
    },
    {
        "symbol": "PGEO.JK",
        "name": "Pertamina Geothermal Energy Tbk",
        "category": "Saham IPO",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1040
    },
    {
        "symbol": "MBMA.JK",
        "name": "Merdeka Battery Materials Tbk",
        "category": "Saham IPO",
        "currency": "IDR",
        "lotSize": 100,
        "price": 520
    },
    {
        "symbol": "NCKL.JK",
        "name": "Trimegah Bangun Persada Tbk",
        "category": "Saham IPO",
        "currency": "IDR",
        "lotSize": 100,
        "price": 890
    },
    {
        "symbol": "VKTR.JK",
        "name": "VKTR Teknologi Mobilitas Tbk",
        "category": "Saham IPO",
        "currency": "IDR",
        "lotSize": 100,
        "price": 135
    },
    {
        "symbol": "BELI.JK",
        "name": "Global Digital Niaga Tbk (Blibli)",
        "category": "Saham IPO",
        "currency": "IDR",
        "lotSize": 100,
        "price": 440
    },
    {
        "symbol": "GOTO.JK",
        "name": "GoTo Gojek Tokopedia Tbk",
        "category": "Saham IPO",
        "currency": "IDR",
        "lotSize": 100,
        "price": 52
    },
    {
        "symbol": "HILL.JK",
        "name": "Hillcon Tbk",
        "category": "Saham IPO",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2150
    },
    {
        "symbol": "MUTU.JK",
        "name": "Mutuagung Lestari Tbk",
        "category": "Saham IPO",
        "currency": "IDR",
        "lotSize": 100,
        "price": 98
    },
    {
        "symbol": "BDKR.JK",
        "name": "Berdikari Pondasi Perkasa Tbk",
        "category": "Saham IPO",
        "currency": "IDR",
        "lotSize": 100,
        "price": 420
    },
    {
        "symbol": "DATA.JK",
        "name": "Remala Abadi Tbk",
        "category": "Saham IPO",
        "currency": "IDR",
        "lotSize": 100,
        "price": 480
    },
    {
        "symbol": "MSJA.JK",
        "name": "Multi Spunindo Jaya Tbk",
        "category": "Saham IPO",
        "currency": "IDR",
        "lotSize": 100,
        "price": 310
    },
    {
        "symbol": "GRPH.JK",
        "name": "Griptha Putra Persada Tbk",
        "category": "Saham IPO",
        "currency": "IDR",
        "lotSize": 100,
        "price": 68
    },
    {
        "symbol": "CGAS.JK",
        "name": "Citra Nusantara Gemilang Tbk",
        "category": "Saham IPO",
        "currency": "IDR",
        "lotSize": 100,
        "price": 155
    },
    {
        "symbol": "SMGA.JK",
        "name": "Sumber Mineral Global Abadi Tbk",
        "category": "Saham IPO",
        "currency": "IDR",
        "lotSize": 100,
        "price": 85
    },
    {
        "symbol": "ALII.JK",
        "name": "Ancara Logistics Indonesia Tbk",
        "category": "Saham IPO",
        "currency": "IDR",
        "lotSize": 100,
        "price": 620
    },
    {
        "symbol": "MKAP.JK",
        "name": "Multikarya Asia Pasifik Raya Tbk",
        "category": "Saham IPO",
        "currency": "IDR",
        "lotSize": 100,
        "price": 240
    },
    {
        "symbol": "LIVE.JK",
        "name": "Homeco Victoria Makmur Tbk",
        "category": "Saham IPO",
        "currency": "IDR",
        "lotSize": 100,
        "price": 195
    },
    {
        "symbol": "HYGN.JK",
        "name": "Ecocare Indo Pasifik Tbk",
        "category": "Saham IPO",
        "currency": "IDR",
        "lotSize": 100,
        "price": 145
    },
    {
        "symbol": "AREA.JK",
        "name": "Dunia Virtual Online Tbk",
        "category": "Saham IPO",
        "currency": "IDR",
        "lotSize": 100,
        "price": 130
    },
    {
        "symbol": "VISI.JK",
        "name": "Satu Visi Putra Tbk",
        "category": "Saham IPO",
        "currency": "IDR",
        "lotSize": 100,
        "price": 170
    },
    {
        "symbol": "RAAM.JK",
        "name": "Tripar Multivision Plus Tbk",
        "category": "Saham IPO",
        "currency": "IDR",
        "lotSize": 100,
        "price": 410
    },
    {
        "symbol": "STRK.JK",
        "name": "Lovina Beach Brewery Tbk",
        "category": "Saham IPO",
        "currency": "IDR",
        "lotSize": 100,
        "price": 60
    },
    {
        "symbol": "PTPS.JK",
        "name": "Pulau Subur Tbk",
        "category": "Saham IPO",
        "currency": "IDR",
        "lotSize": 100,
        "price": 110
    },
    {
        "symbol": "AYAM.JK",
        "name": "Janu Putra Sejahtera Tbk",
        "category": "Saham IPO",
        "currency": "IDR",
        "lotSize": 100,
        "price": 95
    },
    {
        "symbol": "BATR.JK",
        "name": "Benteng Multi Indotbk Tbk",
        "category": "Saham IPO",
        "currency": "IDR",
        "lotSize": 100,
        "price": 80
    },
    {
        "symbol": "NEST.JK",
        "name": "Esta Multi Usaha Tbk",
        "category": "Saham IPO",
        "currency": "IDR",
        "lotSize": 100,
        "price": 120
    },
    {
        "symbol": "FAPA.JK",
        "name": "FAP Agri Tbk",
        "category": "Saham IPO",
        "currency": "IDR",
        "lotSize": 100,
        "price": 4900
    },
    {
        "symbol": "RDDT",
        "name": "Reddit Inc",
        "category": "Saham IPO",
        "currency": "USD",
        "lotSize": 1,
        "price": 159.6
    },
    {
        "symbol": "ARM",
        "name": "Arm Holdings plc",
        "category": "Saham IPO",
        "currency": "USD",
        "lotSize": 1,
        "price": 138.2
    },
    {
        "symbol": "ALAB",
        "name": "Astera Labs Inc",
        "category": "Saham IPO",
        "currency": "USD",
        "lotSize": 1,
        "price": 72.8
    },
    {
        "symbol": "RBRK",
        "name": "Rubrik Inc",
        "category": "Saham IPO",
        "currency": "USD",
        "lotSize": 1,
        "price": 34.1
    },
    {
        "symbol": "BIRK",
        "name": "Birkenstock Holding plc",
        "category": "Saham IPO",
        "currency": "USD",
        "lotSize": 1,
        "price": 56.4
    },
    {
        "symbol": "CART",
        "name": "Maplebear Inc (Instacart)",
        "category": "Saham IPO",
        "currency": "USD",
        "lotSize": 1,
        "price": 37.9
    },
    {
        "symbol": "KVUE",
        "name": "Kenvue Inc",
        "category": "Saham IPO",
        "currency": "USD",
        "lotSize": 1,
        "price": 21.3
    },
    {
        "symbol": "CAVA",
        "name": "CAVA Group Inc",
        "category": "Saham IPO",
        "currency": "USD",
        "lotSize": 1,
        "price": 118.5
    },
    {
        "symbol": "TEM",
        "name": "Tempus AI Inc",
        "category": "Saham IPO",
        "currency": "USD",
        "lotSize": 1,
        "price": 48.6
    },
    {
        "symbol": "KYTX",
        "name": "Kyverna Therapeutics",
        "category": "Saham IPO",
        "currency": "USD",
        "lotSize": 1,
        "price": 9.8
    }
];

const IDX_FULL_ASSETS = [
    {
        "symbol": "AALI.JK",
        "name": "AALI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 6350
    },
    {
        "symbol": "ABBA.JK",
        "name": "ABBA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1309
    },
    {
        "symbol": "ABDA.JK",
        "name": "ABDA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1309
    },
    {
        "symbol": "ABMM.JK",
        "name": "ABMM Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1309
    },
    {
        "symbol": "ACES.JK",
        "name": "ACES Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 840
    },
    {
        "symbol": "ACST.JK",
        "name": "ACST Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1328
    },
    {
        "symbol": "ADCP.JK",
        "name": "ADCP Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1347
    },
    {
        "symbol": "ADHI.JK",
        "name": "ADHI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 270
    },
    {
        "symbol": "ADMF.JK",
        "name": "ADMF Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1347
    },
    {
        "symbol": "ADMR.JK",
        "name": "ADMR Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1350
    },
    {
        "symbol": "ADRO.JK",
        "name": "ADRO Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 3680
    },
    {
        "symbol": "AGAR.JK",
        "name": "AGAR Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1404
    },
    {
        "symbol": "AGII.JK",
        "name": "AGII Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1680
    },
    {
        "symbol": "AGRO.JK",
        "name": "AGRO Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1404
    },
    {
        "symbol": "AGRS.JK",
        "name": "AGRS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1404
    },
    {
        "symbol": "AHAP.JK",
        "name": "AHAP Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1423
    },
    {
        "symbol": "AIMS.JK",
        "name": "AIMS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1442
    },
    {
        "symbol": "AISA.JK",
        "name": "AISA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1442
    },
    {
        "symbol": "AKKU.JK",
        "name": "AKKU Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1480
    },
    {
        "symbol": "AKPI.JK",
        "name": "AKPI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1480
    },
    {
        "symbol": "AKRA.JK",
        "name": "AKRA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1350
    },
    {
        "symbol": "ALDO.JK",
        "name": "ALDO Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1499
    },
    {
        "symbol": "ALII.JK",
        "name": "ALII Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1499
    },
    {
        "symbol": "ALKA.JK",
        "name": "ALKA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1499
    },
    {
        "symbol": "ALMI.JK",
        "name": "ALMI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1499
    },
    {
        "symbol": "ALTO.JK",
        "name": "ALTO Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1499
    },
    {
        "symbol": "AMAR.JK",
        "name": "AMAR Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1518
    },
    {
        "symbol": "AMFG.JK",
        "name": "AMFG Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1518
    },
    {
        "symbol": "AMIN.JK",
        "name": "AMIN Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1518
    },
    {
        "symbol": "AMMN.JK",
        "name": "AMMN Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 8900
    },
    {
        "symbol": "AMMS.JK",
        "name": "AMMS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1518
    },
    {
        "symbol": "AMOR.JK",
        "name": "AMOR Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1518
    },
    {
        "symbol": "AMRT.JK",
        "name": "AMRT Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2950
    },
    {
        "symbol": "ANDI.JK",
        "name": "ANDI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1537
    },
    {
        "symbol": "ANJT.JK",
        "name": "ANJT Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1537
    },
    {
        "symbol": "ANTM.JK",
        "name": "ANTM Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1510
    },
    {
        "symbol": "APEX.JK",
        "name": "APEX Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1575
    },
    {
        "symbol": "APIC.JK",
        "name": "APIC Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1575
    },
    {
        "symbol": "APII.JK",
        "name": "APII Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1575
    },
    {
        "symbol": "APLI.JK",
        "name": "APLI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1575
    },
    {
        "symbol": "APLN.JK",
        "name": "APLN Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1575
    },
    {
        "symbol": "ARCI.JK",
        "name": "ARCI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1613
    },
    {
        "symbol": "ARGO.JK",
        "name": "ARGO Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1613
    },
    {
        "symbol": "ARII.JK",
        "name": "ARII Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1613
    },
    {
        "symbol": "ARKA.JK",
        "name": "ARKA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1613
    },
    {
        "symbol": "ARKO.JK",
        "name": "ARKO Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1613
    },
    {
        "symbol": "ARNA.JK",
        "name": "ARNA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1613
    },
    {
        "symbol": "ARTA.JK",
        "name": "ARTA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1613
    },
    {
        "symbol": "ARTI.JK",
        "name": "ARTI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1613
    },
    {
        "symbol": "ARTO.JK",
        "name": "ARTO Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2150
    },
    {
        "symbol": "ASBI.JK",
        "name": "ASBI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1632
    },
    {
        "symbol": "ASDF.JK",
        "name": "ASDF Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1632
    },
    {
        "symbol": "ASDM.JK",
        "name": "ASDM Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1632
    },
    {
        "symbol": "ASGR.JK",
        "name": "ASGR Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1632
    },
    {
        "symbol": "ASIA.JK",
        "name": "ASIA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1632
    },
    {
        "symbol": "ASII.JK",
        "name": "ASII Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 4890
    },
    {
        "symbol": "ASJT.JK",
        "name": "ASJT Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1632
    },
    {
        "symbol": "ASLC.JK",
        "name": "ASLC Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1632
    },
    {
        "symbol": "ASMI.JK",
        "name": "ASMI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1632
    },
    {
        "symbol": "ASPI.JK",
        "name": "ASPI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1632
    },
    {
        "symbol": "ASRI.JK",
        "name": "ASRI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 185
    },
    {
        "symbol": "ASRM.JK",
        "name": "ASRM Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1632
    },
    {
        "symbol": "ASSA.JK",
        "name": "ASSA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 760
    },
    {
        "symbol": "ATAU.JK",
        "name": "ATAU Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1651
    },
    {
        "symbol": "ATIC.JK",
        "name": "ATIC Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1651
    },
    {
        "symbol": "ATLA.JK",
        "name": "ATLA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1651
    },
    {
        "symbol": "AUTO.JK",
        "name": "AUTO Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2180
    },
    {
        "symbol": "AVIA.JK",
        "name": "AVIA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 480
    },
    {
        "symbol": "AWAN.JK",
        "name": "AWAN Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1708
    },
    {
        "symbol": "AXIO.JK",
        "name": "AXIO Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1727
    },
    {
        "symbol": "AYAM.JK",
        "name": "AYAM Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1746
    },
    {
        "symbol": "AYLS.JK",
        "name": "AYLS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1746
    },
    {
        "symbol": "BABP.JK",
        "name": "BABP Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1327
    },
    {
        "symbol": "BACA.JK",
        "name": "BACA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1327
    },
    {
        "symbol": "BAJA.JK",
        "name": "BAJA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1327
    },
    {
        "symbol": "BALI.JK",
        "name": "BALI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1327
    },
    {
        "symbol": "BANK.JK",
        "name": "BANK Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1327
    },
    {
        "symbol": "BAPA.JK",
        "name": "BAPA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1327
    },
    {
        "symbol": "BAPI.JK",
        "name": "BAPI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1327
    },
    {
        "symbol": "BATA.JK",
        "name": "BATA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1327
    },
    {
        "symbol": "BATR.JK",
        "name": "BATR Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1327
    },
    {
        "symbol": "BAUT.JK",
        "name": "BAUT Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1327
    },
    {
        "symbol": "BBCA.JK",
        "name": "BBCA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 6325
    },
    {
        "symbol": "BBHI.JK",
        "name": "BBHI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1346
    },
    {
        "symbol": "BBKP.JK",
        "name": "BBKP Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1346
    },
    {
        "symbol": "BBLD.JK",
        "name": "BBLD Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1346
    },
    {
        "symbol": "BBMD.JK",
        "name": "BBMD Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1346
    },
    {
        "symbol": "BBNI.JK",
        "name": "BBNI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 3740
    },
    {
        "symbol": "BBRI.JK",
        "name": "BBRI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 3330
    },
    {
        "symbol": "BBRM.JK",
        "name": "BBRM Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1346
    },
    {
        "symbol": "BBSI.JK",
        "name": "BBSI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1346
    },
    {
        "symbol": "BBTN.JK",
        "name": "BBTN Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1280
    },
    {
        "symbol": "BBYB.JK",
        "name": "BBYB Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1346
    },
    {
        "symbol": "BCAP.JK",
        "name": "BCAP Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1365
    },
    {
        "symbol": "BCIC.JK",
        "name": "BCIC Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1365
    },
    {
        "symbol": "BCIP.JK",
        "name": "BCIP Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1365
    },
    {
        "symbol": "BDKR.JK",
        "name": "BDKR Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1384
    },
    {
        "symbol": "BDMN.JK",
        "name": "BDMN Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2640
    },
    {
        "symbol": "BEBS.JK",
        "name": "BEBS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1403
    },
    {
        "symbol": "BEEF.JK",
        "name": "BEEF Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1403
    },
    {
        "symbol": "BEER.JK",
        "name": "BEER Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1403
    },
    {
        "symbol": "BEKS.JK",
        "name": "BEKS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1403
    },
    {
        "symbol": "BELI.JK",
        "name": "BELI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1403
    },
    {
        "symbol": "BESS.JK",
        "name": "BESS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1403
    },
    {
        "symbol": "BEST.JK",
        "name": "BEST Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1403
    },
    {
        "symbol": "BFIN.JK",
        "name": "BFIN Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 970
    },
    {
        "symbol": "BGTG.JK",
        "name": "BGTG Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1441
    },
    {
        "symbol": "BGYA.JK",
        "name": "BGYA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1441
    },
    {
        "symbol": "BIHI.JK",
        "name": "BIHI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1479
    },
    {
        "symbol": "BIKE.JK",
        "name": "BIKE Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1479
    },
    {
        "symbol": "BIMA.JK",
        "name": "BIMA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1479
    },
    {
        "symbol": "BINA.JK",
        "name": "BINA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1479
    },
    {
        "symbol": "BIPI.JK",
        "name": "BIPI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1479
    },
    {
        "symbol": "BIPP.JK",
        "name": "BIPP Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1479
    },
    {
        "symbol": "BIRD.JK",
        "name": "BIRD Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1890
    },
    {
        "symbol": "BISI.JK",
        "name": "BISI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1479
    },
    {
        "symbol": "BJBR.JK",
        "name": "BJBR Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1040
    },
    {
        "symbol": "BJTM.JK",
        "name": "BJTM Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 580
    },
    {
        "symbol": "BKDP.JK",
        "name": "BKDP Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1517
    },
    {
        "symbol": "BKSL.JK",
        "name": "BKSL Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1517
    },
    {
        "symbol": "BKSW.JK",
        "name": "BKSW Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1517
    },
    {
        "symbol": "BLTA.JK",
        "name": "BLTA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1536
    },
    {
        "symbol": "BLTZ.JK",
        "name": "BLTZ Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1536
    },
    {
        "symbol": "BLUE.JK",
        "name": "BLUE Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1536
    },
    {
        "symbol": "BMAS.JK",
        "name": "BMAS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1555
    },
    {
        "symbol": "BMBL.JK",
        "name": "BMBL Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1555
    },
    {
        "symbol": "BMHS.JK",
        "name": "BMHS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1555
    },
    {
        "symbol": "BMRI.JK",
        "name": "BMRI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 4280
    },
    {
        "symbol": "BMSR.JK",
        "name": "BMSR Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1555
    },
    {
        "symbol": "BMTR.JK",
        "name": "BMTR Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1555
    },
    {
        "symbol": "BNBA.JK",
        "name": "BNBA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1574
    },
    {
        "symbol": "BNBR.JK",
        "name": "BNBR Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1574
    },
    {
        "symbol": "BNGA.JK",
        "name": "BNGA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1820
    },
    {
        "symbol": "BNII.JK",
        "name": "BNII Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1574
    },
    {
        "symbol": "BNLI.JK",
        "name": "BNLI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1574
    },
    {
        "symbol": "BOBA.JK",
        "name": "BOBA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1593
    },
    {
        "symbol": "BOGA.JK",
        "name": "BOGA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1593
    },
    {
        "symbol": "BOLA.JK",
        "name": "BOLA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1593
    },
    {
        "symbol": "BOLT.JK",
        "name": "BOLT Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1593
    },
    {
        "symbol": "BOSS.JK",
        "name": "BOSS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1593
    },
    {
        "symbol": "BPFI.JK",
        "name": "BPFI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1612
    },
    {
        "symbol": "BPII.JK",
        "name": "BPII Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1612
    },
    {
        "symbol": "BRAM.JK",
        "name": "BRAM Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1650
    },
    {
        "symbol": "BREN.JK",
        "name": "BREN Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 6850
    },
    {
        "symbol": "BRIS.JK",
        "name": "BRIS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2950
    },
    {
        "symbol": "BRMS.JK",
        "name": "BRMS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 380
    },
    {
        "symbol": "BRNA.JK",
        "name": "BRNA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1650
    },
    {
        "symbol": "BRPT.JK",
        "name": "BRPT Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 960
    },
    {
        "symbol": "BSDE.JK",
        "name": "BSDE Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1160
    },
    {
        "symbol": "BSIM.JK",
        "name": "BSIM Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1669
    },
    {
        "symbol": "BSML.JK",
        "name": "BSML Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1669
    },
    {
        "symbol": "BSSR.JK",
        "name": "BSSR Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1669
    },
    {
        "symbol": "BSUD.JK",
        "name": "BSUD Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1669
    },
    {
        "symbol": "BTEK.JK",
        "name": "BTEK Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1688
    },
    {
        "symbol": "BTEL.JK",
        "name": "BTEL Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1688
    },
    {
        "symbol": "BTON.JK",
        "name": "BTON Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1688
    },
    {
        "symbol": "BTPN.JK",
        "name": "BTPN Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1688
    },
    {
        "symbol": "BTPS.JK",
        "name": "BTPS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1020
    },
    {
        "symbol": "BUKA.JK",
        "name": "BUKA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 118
    },
    {
        "symbol": "BUKK.JK",
        "name": "BUKK Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1707
    },
    {
        "symbol": "BULL.JK",
        "name": "BULL Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1707
    },
    {
        "symbol": "BUMI.JK",
        "name": "BUMI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 138
    },
    {
        "symbol": "BURP.JK",
        "name": "BURP Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1707
    },
    {
        "symbol": "BUVA.JK",
        "name": "BUVA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1707
    },
    {
        "symbol": "BVIC.JK",
        "name": "BVIC Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1726
    },
    {
        "symbol": "BWPT.JK",
        "name": "BWPT Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1745
    },
    {
        "symbol": "BYAN.JK",
        "name": "BYAN Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 15800
    },
    {
        "symbol": "CAKK.JK",
        "name": "CAKK Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1364
    },
    {
        "symbol": "CAMP.JK",
        "name": "CAMP Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1364
    },
    {
        "symbol": "CANI.JK",
        "name": "CANI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1364
    },
    {
        "symbol": "CARE.JK",
        "name": "CARE Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1364
    },
    {
        "symbol": "CARS.JK",
        "name": "CARS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1364
    },
    {
        "symbol": "CASA.JK",
        "name": "CASA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1364
    },
    {
        "symbol": "CASH.JK",
        "name": "CASH Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1364
    },
    {
        "symbol": "CASS.JK",
        "name": "CASS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1364
    },
    {
        "symbol": "CAST.JK",
        "name": "CAST Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1364
    },
    {
        "symbol": "CBMF.JK",
        "name": "CBMF Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1383
    },
    {
        "symbol": "CEKA.JK",
        "name": "CEKA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1440
    },
    {
        "symbol": "CENT.JK",
        "name": "CENT Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1440
    },
    {
        "symbol": "CFIN.JK",
        "name": "CFIN Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1459
    },
    {
        "symbol": "CGAS.JK",
        "name": "CGAS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1478
    },
    {
        "symbol": "CHEB.JK",
        "name": "CHEB Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1497
    },
    {
        "symbol": "CHIP.JK",
        "name": "CHIP Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1497
    },
    {
        "symbol": "CINT.JK",
        "name": "CINT Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1516
    },
    {
        "symbol": "CITA.JK",
        "name": "CITA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2850
    },
    {
        "symbol": "CITY.JK",
        "name": "CITY Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1516
    },
    {
        "symbol": "CLAY.JK",
        "name": "CLAY Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1573
    },
    {
        "symbol": "CLEO.JK",
        "name": "CLEO Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1250
    },
    {
        "symbol": "CLPI.JK",
        "name": "CLPI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1573
    },
    {
        "symbol": "CMNT.JK",
        "name": "CMNT Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1592
    },
    {
        "symbol": "CMPP.JK",
        "name": "CMPP Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1592
    },
    {
        "symbol": "CMRY.JK",
        "name": "CMRY Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 5150
    },
    {
        "symbol": "CNKO.JK",
        "name": "CNKO Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1611
    },
    {
        "symbol": "CNMA.JK",
        "name": "CNMA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 210
    },
    {
        "symbol": "CNTA.JK",
        "name": "CNTA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1611
    },
    {
        "symbol": "CNTR.JK",
        "name": "CNTR Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1611
    },
    {
        "symbol": "COAL.JK",
        "name": "COAL Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1630
    },
    {
        "symbol": "COCO.JK",
        "name": "COCO Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1630
    },
    {
        "symbol": "COWL.JK",
        "name": "COWL Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1630
    },
    {
        "symbol": "CPIN.JK",
        "name": "CPIN Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 4950
    },
    {
        "symbol": "CPRO.JK",
        "name": "CPRO Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1649
    },
    {
        "symbol": "CRAB.JK",
        "name": "CRAB Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1687
    },
    {
        "symbol": "CRSN.JK",
        "name": "CRSN Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1687
    },
    {
        "symbol": "CSAP.JK",
        "name": "CSAP Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1706
    },
    {
        "symbol": "CSIS.JK",
        "name": "CSIS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1706
    },
    {
        "symbol": "CSMI.JK",
        "name": "CSMI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1706
    },
    {
        "symbol": "CSRA.JK",
        "name": "CSRA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1706
    },
    {
        "symbol": "CTBN.JK",
        "name": "CTBN Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1725
    },
    {
        "symbol": "CTRA.JK",
        "name": "CTRA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1250
    },
    {
        "symbol": "CTTH.JK",
        "name": "CTTH Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1725
    },
    {
        "symbol": "CUAN.JK",
        "name": "CUAN Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 6450
    },
    {
        "symbol": "CYBR.JK",
        "name": "CYBR Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1820
    },
    {
        "symbol": "DADA.JK",
        "name": "DADA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1401
    },
    {
        "symbol": "DATA.JK",
        "name": "DATA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1401
    },
    {
        "symbol": "DAYA.JK",
        "name": "DAYA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1401
    },
    {
        "symbol": "DCII.JK",
        "name": "DCII Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1439
    },
    {
        "symbol": "DEAL.JK",
        "name": "DEAL Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1477
    },
    {
        "symbol": "DEFI.JK",
        "name": "DEFI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1477
    },
    {
        "symbol": "DEPO.JK",
        "name": "DEPO Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1477
    },
    {
        "symbol": "DEWA.JK",
        "name": "DEWA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1477
    },
    {
        "symbol": "DFAM.JK",
        "name": "DFAM Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1496
    },
    {
        "symbol": "DGIK.JK",
        "name": "DGIK Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1515
    },
    {
        "symbol": "DGNS.JK",
        "name": "DGNS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1515
    },
    {
        "symbol": "DIGI.JK",
        "name": "DIGI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1553
    },
    {
        "symbol": "DILD.JK",
        "name": "DILD Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1553
    },
    {
        "symbol": "DIVA.JK",
        "name": "DIVA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1553
    },
    {
        "symbol": "DKFT.JK",
        "name": "DKFT Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1591
    },
    {
        "symbol": "DLTA.JK",
        "name": "DLTA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1610
    },
    {
        "symbol": "DMAS.JK",
        "name": "DMAS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1629
    },
    {
        "symbol": "DMMX.JK",
        "name": "DMMX Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1629
    },
    {
        "symbol": "DMND.JK",
        "name": "DMND Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1629
    },
    {
        "symbol": "DNAR.JK",
        "name": "DNAR Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1648
    },
    {
        "symbol": "DNET.JK",
        "name": "DNET Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1648
    },
    {
        "symbol": "DOID.JK",
        "name": "DOID Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 620
    },
    {
        "symbol": "DOSS.JK",
        "name": "DOSS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1667
    },
    {
        "symbol": "DPNS.JK",
        "name": "DPNS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1686
    },
    {
        "symbol": "DPUM.JK",
        "name": "DPUM Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1686
    },
    {
        "symbol": "DRMA.JK",
        "name": "DRMA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1050
    },
    {
        "symbol": "DSFI.JK",
        "name": "DSFI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1743
    },
    {
        "symbol": "DSNG.JK",
        "name": "DSNG Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 780
    },
    {
        "symbol": "DSSA.JK",
        "name": "DSSA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 39500
    },
    {
        "symbol": "DUCK.JK",
        "name": "DUCK Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1781
    },
    {
        "symbol": "DUTI.JK",
        "name": "DUTI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1781
    },
    {
        "symbol": "DVLA.JK",
        "name": "DVLA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1800
    },
    {
        "symbol": "DWGL.JK",
        "name": "DWGL Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1819
    },
    {
        "symbol": "DYAN.JK",
        "name": "DYAN Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1857
    },
    {
        "symbol": "EAST.JK",
        "name": "EAST Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1438
    },
    {
        "symbol": "ECII.JK",
        "name": "ECII Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1476
    },
    {
        "symbol": "EDGE.JK",
        "name": "EDGE Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1495
    },
    {
        "symbol": "EKAD.JK",
        "name": "EKAD Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1628
    },
    {
        "symbol": "ELIT.JK",
        "name": "ELIT Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1647
    },
    {
        "symbol": "ELPI.JK",
        "name": "ELPI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1647
    },
    {
        "symbol": "ELSA.JK",
        "name": "ELSA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 460
    },
    {
        "symbol": "ELTY.JK",
        "name": "ELTY Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1647
    },
    {
        "symbol": "EMDE.JK",
        "name": "EMDE Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1666
    },
    {
        "symbol": "EMET.JK",
        "name": "EMET Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1666
    },
    {
        "symbol": "EMTK.JK",
        "name": "EMTK Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 420
    },
    {
        "symbol": "ENAK.JK",
        "name": "ENAK Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1685
    },
    {
        "symbol": "ENRG.JK",
        "name": "ENRG Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 210
    },
    {
        "symbol": "ENVY.JK",
        "name": "ENVY Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1685
    },
    {
        "symbol": "ENZO.JK",
        "name": "ENZO Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1685
    },
    {
        "symbol": "EPAC.JK",
        "name": "EPAC Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1723
    },
    {
        "symbol": "EPMT.JK",
        "name": "EPMT Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1723
    },
    {
        "symbol": "ERAA.JK",
        "name": "ERAA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 430
    },
    {
        "symbol": "ERAL.JK",
        "name": "ERAL Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1761
    },
    {
        "symbol": "ERTX.JK",
        "name": "ERTX Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1761
    },
    {
        "symbol": "ESIP.JK",
        "name": "ESIP Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1780
    },
    {
        "symbol": "ESSA.JK",
        "name": "ESSA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 920
    },
    {
        "symbol": "ESTA.JK",
        "name": "ESTA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1780
    },
    {
        "symbol": "ESTI.JK",
        "name": "ESTI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1780
    },
    {
        "symbol": "ETWA.JK",
        "name": "ETWA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1799
    },
    {
        "symbol": "EURO.JK",
        "name": "EURO Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1818
    },
    {
        "symbol": "EXCL.JK",
        "name": "EXCL Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2240
    },
    {
        "symbol": "FAPA.JK",
        "name": "FAPA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1475
    },
    {
        "symbol": "FAST.JK",
        "name": "FAST Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1475
    },
    {
        "symbol": "FASW.JK",
        "name": "FASW Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1475
    },
    {
        "symbol": "FILE.JK",
        "name": "FILE Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1627
    },
    {
        "symbol": "FILM.JK",
        "name": "FILM Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 3850
    },
    {
        "symbol": "FIMP.JK",
        "name": "FIMP Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1627
    },
    {
        "symbol": "FIRE.JK",
        "name": "FIRE Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1627
    },
    {
        "symbol": "FISH.JK",
        "name": "FISH Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1627
    },
    {
        "symbol": "FITT.JK",
        "name": "FITT Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1627
    },
    {
        "symbol": "FLMC.JK",
        "name": "FLMC Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1684
    },
    {
        "symbol": "FMII.JK",
        "name": "FMII Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1703
    },
    {
        "symbol": "FOOD.JK",
        "name": "FOOD Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1741
    },
    {
        "symbol": "FORU.JK",
        "name": "FORU Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1741
    },
    {
        "symbol": "FPNI.JK",
        "name": "FPNI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1760
    },
    {
        "symbol": "FREN.JK",
        "name": "FREN Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1798
    },
    {
        "symbol": "FUJI.JK",
        "name": "FUJI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1855
    },
    {
        "symbol": "FUTR.JK",
        "name": "FUTR Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1855
    },
    {
        "symbol": "FWCT.JK",
        "name": "FWCT Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1893
    },
    {
        "symbol": "GAMA.JK",
        "name": "GAMA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1512
    },
    {
        "symbol": "GDST.JK",
        "name": "GDST Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1569
    },
    {
        "symbol": "GDYR.JK",
        "name": "GDYR Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1569
    },
    {
        "symbol": "GEMA.JK",
        "name": "GEMA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1588
    },
    {
        "symbol": "GEMR.JK",
        "name": "GEMR Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1588
    },
    {
        "symbol": "GEMS.JK",
        "name": "GEMS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1588
    },
    {
        "symbol": "GGRM.JK",
        "name": "GGRM Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1626
    },
    {
        "symbol": "GIAA.JK",
        "name": "GIAA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1664
    },
    {
        "symbol": "GJTL.JK",
        "name": "GJTL Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1140
    },
    {
        "symbol": "GLOB.JK",
        "name": "GLOB Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1721
    },
    {
        "symbol": "GLVA.JK",
        "name": "GLVA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1721
    },
    {
        "symbol": "GMFI.JK",
        "name": "GMFI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1740
    },
    {
        "symbol": "GMTD.JK",
        "name": "GMTD Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1740
    },
    {
        "symbol": "GOLD.JK",
        "name": "GOLD Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1778
    },
    {
        "symbol": "GOOD.JK",
        "name": "GOOD Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1778
    },
    {
        "symbol": "GOTO.JK",
        "name": "GOTO Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1778
    },
    {
        "symbol": "GPFI.JK",
        "name": "GPFI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1797
    },
    {
        "symbol": "GPSO.JK",
        "name": "GPSO Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1797
    },
    {
        "symbol": "GRIA.JK",
        "name": "GRIA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1835
    },
    {
        "symbol": "GRPH.JK",
        "name": "GRPH Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1835
    },
    {
        "symbol": "GSMF.JK",
        "name": "GSMF Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1854
    },
    {
        "symbol": "GTBO.JK",
        "name": "GTBO Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1873
    },
    {
        "symbol": "GTRA.JK",
        "name": "GTRA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1873
    },
    {
        "symbol": "GWSA.JK",
        "name": "GWSA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1930
    },
    {
        "symbol": "GZCO.JK",
        "name": "GZCO Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1987
    },
    {
        "symbol": "HAIS.JK",
        "name": "HAIS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1549
    },
    {
        "symbol": "HATM.JK",
        "name": "HATM Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1549
    },
    {
        "symbol": "HDFA.JK",
        "name": "HDFA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1606
    },
    {
        "symbol": "HDIT.JK",
        "name": "HDIT Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1606
    },
    {
        "symbol": "HDTX.JK",
        "name": "HDTX Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1606
    },
    {
        "symbol": "HEAL.JK",
        "name": "HEAL Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1380
    },
    {
        "symbol": "HELI.JK",
        "name": "HELI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1625
    },
    {
        "symbol": "HERO.JK",
        "name": "HERO Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1625
    },
    {
        "symbol": "HEXA.JK",
        "name": "HEXA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1625
    },
    {
        "symbol": "HITS.JK",
        "name": "HITS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1701
    },
    {
        "symbol": "HKMU.JK",
        "name": "HKMU Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1739
    },
    {
        "symbol": "HILL.JK",
        "name": "HILL Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1701
    },
    {
        "symbol": "HMSP.JK",
        "name": "HMSP Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1777
    },
    {
        "symbol": "HOKI.JK",
        "name": "HOKI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 140
    },
    {
        "symbol": "HOME.JK",
        "name": "HOME Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1815
    },
    {
        "symbol": "HOPE.JK",
        "name": "HOPE Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1815
    },
    {
        "symbol": "HOTL.JK",
        "name": "HOTL Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1815
    },
    {
        "symbol": "HRME.JK",
        "name": "HRME Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1872
    },
    {
        "symbol": "HRTA.JK",
        "name": "HRTA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 390
    },
    {
        "symbol": "HRUM.JK",
        "name": "HRUM Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1120
    },
    {
        "symbol": "HUMI.JK",
        "name": "HUMI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1929
    },
    {
        "symbol": "HYGN.JK",
        "name": "HYGN Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2005
    },
    {
        "symbol": "IATA.JK",
        "name": "IATA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1586
    },
    {
        "symbol": "IBFN.JK",
        "name": "IBFN Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1605
    },
    {
        "symbol": "IBOS.JK",
        "name": "IBOS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1605
    },
    {
        "symbol": "IBST.JK",
        "name": "IBST Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1605
    },
    {
        "symbol": "ICBP.JK",
        "name": "ICBP Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 11200
    },
    {
        "symbol": "ICON.JK",
        "name": "ICON Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1624
    },
    {
        "symbol": "IDEA.JK",
        "name": "IDEA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1643
    },
    {
        "symbol": "IDPR.JK",
        "name": "IDPR Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1643
    },
    {
        "symbol": "IFII.JK",
        "name": "IFII Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1681
    },
    {
        "symbol": "IFSH.JK",
        "name": "IFSH Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1681
    },
    {
        "symbol": "IGAR.JK",
        "name": "IGAR Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1700
    },
    {
        "symbol": "IIKP.JK",
        "name": "IIKP Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1738
    },
    {
        "symbol": "IKAI.JK",
        "name": "IKAI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1776
    },
    {
        "symbol": "IKAN.JK",
        "name": "IKAN Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1776
    },
    {
        "symbol": "IKBI.JK",
        "name": "IKBI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1776
    },
    {
        "symbol": "IMAS.JK",
        "name": "IMAS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1280
    },
    {
        "symbol": "IMJS.JK",
        "name": "IMJS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1814
    },
    {
        "symbol": "IMPC.JK",
        "name": "IMPC Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1814
    },
    {
        "symbol": "INAF.JK",
        "name": "INAF Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 180
    },
    {
        "symbol": "INAI.JK",
        "name": "INAI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1833
    },
    {
        "symbol": "INCF.JK",
        "name": "INCF Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1833
    },
    {
        "symbol": "INCI.JK",
        "name": "INCI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1833
    },
    {
        "symbol": "INCO.JK",
        "name": "INCO Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 3780
    },
    {
        "symbol": "INDF.JK",
        "name": "INDF Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 6850
    },
    {
        "symbol": "INDO.JK",
        "name": "INDO Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1833
    },
    {
        "symbol": "INDR.JK",
        "name": "INDR Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1833
    },
    {
        "symbol": "INDS.JK",
        "name": "INDS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1833
    },
    {
        "symbol": "INDY.JK",
        "name": "INDY Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1833
    },
    {
        "symbol": "INET.JK",
        "name": "INET Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1833
    },
    {
        "symbol": "INFY.JK",
        "name": "INFY Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1833
    },
    {
        "symbol": "INGO.JK",
        "name": "INGO Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1833
    },
    {
        "symbol": "INKP.JK",
        "name": "INKP Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 7850
    },
    {
        "symbol": "INOV.JK",
        "name": "INOV Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1833
    },
    {
        "symbol": "INPC.JK",
        "name": "INPC Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1833
    },
    {
        "symbol": "INPP.JK",
        "name": "INPP Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1833
    },
    {
        "symbol": "INPS.JK",
        "name": "INPS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1833
    },
    {
        "symbol": "INRU.JK",
        "name": "INRU Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1833
    },
    {
        "symbol": "INTD.JK",
        "name": "INTD Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1833
    },
    {
        "symbol": "INTG.JK",
        "name": "INTG Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1833
    },
    {
        "symbol": "INTP.JK",
        "name": "INTP Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 6850
    },
    {
        "symbol": "IPAC.JK",
        "name": "IPAC Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1871
    },
    {
        "symbol": "IPCM.JK",
        "name": "IPCM Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1871
    },
    {
        "symbol": "IPPE.JK",
        "name": "IPPE Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1871
    },
    {
        "symbol": "IPTV.JK",
        "name": "IPTV Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1871
    },
    {
        "symbol": "IPUR.JK",
        "name": "IPUR Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1871
    },
    {
        "symbol": "IRRA.JK",
        "name": "IRRA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1909
    },
    {
        "symbol": "ISAP.JK",
        "name": "ISAP Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1928
    },
    {
        "symbol": "ISAT.JK",
        "name": "ISAT Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2250
    },
    {
        "symbol": "ITIC.JK",
        "name": "ITIC Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1947
    },
    {
        "symbol": "ITMA.JK",
        "name": "ITMA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1947
    },
    {
        "symbol": "ITMG.JK",
        "name": "ITMG Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 25600
    },
    {
        "symbol": "JARR.JK",
        "name": "JARR Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1623
    },
    {
        "symbol": "JAST.JK",
        "name": "JAST Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1623
    },
    {
        "symbol": "JATI.JK",
        "name": "JATI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1623
    },
    {
        "symbol": "JAWA.JK",
        "name": "JAWA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1623
    },
    {
        "symbol": "JAYA.JK",
        "name": "JAYA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1623
    },
    {
        "symbol": "JECC.JK",
        "name": "JECC Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1699
    },
    {
        "symbol": "JGLE.JK",
        "name": "JGLE Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1737
    },
    {
        "symbol": "JIHD.JK",
        "name": "JIHD Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1775
    },
    {
        "symbol": "JKON.JK",
        "name": "JKON Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1813
    },
    {
        "symbol": "JKSW.JK",
        "name": "JKSW Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1813
    },
    {
        "symbol": "JMAS.JK",
        "name": "JMAS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1851
    },
    {
        "symbol": "JPFA.JK",
        "name": "JPFA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1650
    },
    {
        "symbol": "JRPT.JK",
        "name": "JRPT Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1946
    },
    {
        "symbol": "JSMR.JK",
        "name": "JSMR Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 4520
    },
    {
        "symbol": "JSPT.JK",
        "name": "JSPT Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1965
    },
    {
        "symbol": "JTPE.JK",
        "name": "JTPE Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1984
    },
    {
        "symbol": "KAEF.JK",
        "name": "KAEF Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 620
    },
    {
        "symbol": "KAIS.JK",
        "name": "KAIS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1660
    },
    {
        "symbol": "KARW.JK",
        "name": "KARW Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1660
    },
    {
        "symbol": "KAYU.JK",
        "name": "KAYU Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1660
    },
    {
        "symbol": "KBAG.JK",
        "name": "KBAG Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1679
    },
    {
        "symbol": "KBLI.JK",
        "name": "KBLI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1679
    },
    {
        "symbol": "KBLM.JK",
        "name": "KBLM Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1679
    },
    {
        "symbol": "KBLV.JK",
        "name": "KBLV Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1679
    },
    {
        "symbol": "KBRI.JK",
        "name": "KBRI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1679
    },
    {
        "symbol": "KDSI.JK",
        "name": "KDSI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1717
    },
    {
        "symbol": "KDTN.JK",
        "name": "KDTN Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1717
    },
    {
        "symbol": "KEEN.JK",
        "name": "KEEN Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1736
    },
    {
        "symbol": "KEJU.JK",
        "name": "KEJU Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1736
    },
    {
        "symbol": "KETR.JK",
        "name": "KETR Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1736
    },
    {
        "symbol": "KIAS.JK",
        "name": "KIAS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1812
    },
    {
        "symbol": "KICI.JK",
        "name": "KICI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1812
    },
    {
        "symbol": "KIJA.JK",
        "name": "KIJA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 150
    },
    {
        "symbol": "KINO.JK",
        "name": "KINO Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1812
    },
    {
        "symbol": "KIOS.JK",
        "name": "KIOS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1812
    },
    {
        "symbol": "KJEN.JK",
        "name": "KJEN Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1831
    },
    {
        "symbol": "KKGI.JK",
        "name": "KKGI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1850
    },
    {
        "symbol": "KLAS.JK",
        "name": "KLAS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1869
    },
    {
        "symbol": "KLBF.JK",
        "name": "KLBF Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1580
    },
    {
        "symbol": "KMDS.JK",
        "name": "KMDS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1888
    },
    {
        "symbol": "KMED.JK",
        "name": "KMED Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1888
    },
    {
        "symbol": "KMTR.JK",
        "name": "KMTR Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1888
    },
    {
        "symbol": "KOBX.JK",
        "name": "KOBX Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1926
    },
    {
        "symbol": "KOIN.JK",
        "name": "KOIN Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1926
    },
    {
        "symbol": "KOKA.JK",
        "name": "KOKA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1926
    },
    {
        "symbol": "KOKI.JK",
        "name": "KOKI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1926
    },
    {
        "symbol": "KOTA.JK",
        "name": "KOTA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1926
    },
    {
        "symbol": "KPAL.JK",
        "name": "KPAL Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1945
    },
    {
        "symbol": "KPAS.JK",
        "name": "KPAS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1945
    },
    {
        "symbol": "KPIG.JK",
        "name": "KPIG Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1945
    },
    {
        "symbol": "KRAS.JK",
        "name": "KRAS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1983
    },
    {
        "symbol": "KREN.JK",
        "name": "KREN Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1983
    },
    {
        "symbol": "KRYA.JK",
        "name": "KRYA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1983
    },
    {
        "symbol": "KTIC.JK",
        "name": "KTIC Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2021
    },
    {
        "symbol": "KUAS.JK",
        "name": "KUAS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2040
    },
    {
        "symbol": "KUTN.JK",
        "name": "KUTN Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2040
    },
    {
        "symbol": "LABA.JK",
        "name": "LABA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1697
    },
    {
        "symbol": "LAJU.JK",
        "name": "LAJU Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1697
    },
    {
        "symbol": "LAND.JK",
        "name": "LAND Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1697
    },
    {
        "symbol": "LAPD.JK",
        "name": "LAPD Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1697
    },
    {
        "symbol": "LARK.JK",
        "name": "LARK Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1697
    },
    {
        "symbol": "LCGP.JK",
        "name": "LCGP Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1735
    },
    {
        "symbol": "LCKM.JK",
        "name": "LCKM Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1735
    },
    {
        "symbol": "LEAD.JK",
        "name": "LEAD Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1773
    },
    {
        "symbol": "LEAP.JK",
        "name": "LEAP Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1773
    },
    {
        "symbol": "LFLO.JK",
        "name": "LFLO Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1792
    },
    {
        "symbol": "LIFE.JK",
        "name": "LIFE Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1849
    },
    {
        "symbol": "LINK.JK",
        "name": "LINK Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1849
    },
    {
        "symbol": "LION.JK",
        "name": "LION Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1849
    },
    {
        "symbol": "LIVE.JK",
        "name": "LIVE Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1849
    },
    {
        "symbol": "LMAS.JK",
        "name": "LMAS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1925
    },
    {
        "symbol": "LMPI.JK",
        "name": "LMPI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1925
    },
    {
        "symbol": "LMSH.JK",
        "name": "LMSH Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1925
    },
    {
        "symbol": "LOPI.JK",
        "name": "LOPI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1963
    },
    {
        "symbol": "LPIN.JK",
        "name": "LPIN Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1982
    },
    {
        "symbol": "LPLI.JK",
        "name": "LPLI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1982
    },
    {
        "symbol": "LPPF.JK",
        "name": "LPPF Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1982
    },
    {
        "symbol": "LPPS.JK",
        "name": "LPPS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1982
    },
    {
        "symbol": "LPRT.JK",
        "name": "LPRT Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1982
    },
    {
        "symbol": "LPVI.JK",
        "name": "LPVI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1982
    },
    {
        "symbol": "LRMS.JK",
        "name": "LRMS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2020
    },
    {
        "symbol": "LSIP.JK",
        "name": "LSIP Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 980
    },
    {
        "symbol": "LTLS.JK",
        "name": "LTLS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2058
    },
    {
        "symbol": "LUCK.JK",
        "name": "LUCK Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2077
    },
    {
        "symbol": "LUMI.JK",
        "name": "LUMI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2077
    },
    {
        "symbol": "MABA.JK",
        "name": "MABA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1734
    },
    {
        "symbol": "MAHA.JK",
        "name": "MAHA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1734
    },
    {
        "symbol": "MAIN.JK",
        "name": "MAIN Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1734
    },
    {
        "symbol": "MAND.JK",
        "name": "MAND Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1734
    },
    {
        "symbol": "MAPA.JK",
        "name": "MAPA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 820
    },
    {
        "symbol": "MAPB.JK",
        "name": "MAPB Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1734
    },
    {
        "symbol": "MAPI.JK",
        "name": "MAPI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1480
    },
    {
        "symbol": "MARI.JK",
        "name": "MARI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1734
    },
    {
        "symbol": "MARK.JK",
        "name": "MARK Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1734
    },
    {
        "symbol": "MAXI.JK",
        "name": "MAXI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1734
    },
    {
        "symbol": "MCOL.JK",
        "name": "MCOL Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 4950
    },
    {
        "symbol": "MCOR.JK",
        "name": "MCOR Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1772
    },
    {
        "symbol": "MDIA.JK",
        "name": "MDIA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1791
    },
    {
        "symbol": "MDKA.JK",
        "name": "MDKA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2180
    },
    {
        "symbol": "MDKI.JK",
        "name": "MDKI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1791
    },
    {
        "symbol": "MDLA.JK",
        "name": "MDLA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1791
    },
    {
        "symbol": "MDRN.JK",
        "name": "MDRN Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1791
    },
    {
        "symbol": "MECO.JK",
        "name": "MECO Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1810
    },
    {
        "symbol": "MEDC.JK",
        "name": "MEDC Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1180
    },
    {
        "symbol": "MEGA.JK",
        "name": "MEGA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 4800
    },
    {
        "symbol": "MENN.JK",
        "name": "MENN Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1810
    },
    {
        "symbol": "META.JK",
        "name": "META Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1810
    },
    {
        "symbol": "MFCO.JK",
        "name": "MFCO Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1829
    },
    {
        "symbol": "MFII.JK",
        "name": "MFII Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1829
    },
    {
        "symbol": "MFMI.JK",
        "name": "MFMI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1829
    },
    {
        "symbol": "MFIN.JK",
        "name": "MFIN Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1829
    },
    {
        "symbol": "MGNA.JK",
        "name": "MGNA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1848
    },
    {
        "symbol": "MGRO.JK",
        "name": "MGRO Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1848
    },
    {
        "symbol": "MICE.JK",
        "name": "MICE Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1886
    },
    {
        "symbol": "MIDI.JK",
        "name": "MIDI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 410
    },
    {
        "symbol": "MIKA.JK",
        "name": "MIKA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2850
    },
    {
        "symbol": "MINA.JK",
        "name": "MINA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1886
    },
    {
        "symbol": "MIRA.JK",
        "name": "MIRA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1886
    },
    {
        "symbol": "MITI.JK",
        "name": "MITI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1886
    },
    {
        "symbol": "MKAP.JK",
        "name": "MKAP Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1924
    },
    {
        "symbol": "MKNT.JK",
        "name": "MKNT Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1924
    },
    {
        "symbol": "MKPI.JK",
        "name": "MKPI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1924
    },
    {
        "symbol": "MKTR.JK",
        "name": "MKTR Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1924
    },
    {
        "symbol": "MLBI.JK",
        "name": "MLBI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1943
    },
    {
        "symbol": "MLIA.JK",
        "name": "MLIA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1943
    },
    {
        "symbol": "MLPL.JK",
        "name": "MLPL Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1943
    },
    {
        "symbol": "MLPT.JK",
        "name": "MLPT Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1943
    },
    {
        "symbol": "MMAI.JK",
        "name": "MMAI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1962
    },
    {
        "symbol": "MMIS.JK",
        "name": "MMIS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1962
    },
    {
        "symbol": "MNCN.JK",
        "name": "MNCN Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 290
    },
    {
        "symbol": "MNDS.JK",
        "name": "MNDS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1981
    },
    {
        "symbol": "MOLI.JK",
        "name": "MOLI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2000
    },
    {
        "symbol": "MORA.JK",
        "name": "MORA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2000
    },
    {
        "symbol": "MPAC.JK",
        "name": "MPAC Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2019
    },
    {
        "symbol": "MPAX.JK",
        "name": "MPAX Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2019
    },
    {
        "symbol": "MPMX.JK",
        "name": "MPMX Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2019
    },
    {
        "symbol": "MPOW.JK",
        "name": "MPOW Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2019
    },
    {
        "symbol": "MPPA.JK",
        "name": "MPPA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2019
    },
    {
        "symbol": "MPPR.JK",
        "name": "MPPR Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2019
    },
    {
        "symbol": "MPXL.JK",
        "name": "MPXL Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2019
    },
    {
        "symbol": "MSIN.JK",
        "name": "MSIN Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2076
    },
    {
        "symbol": "MSJA.JK",
        "name": "MSJA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2076
    },
    {
        "symbol": "MSKY.JK",
        "name": "MSKY Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2076
    },
    {
        "symbol": "MTDL.JK",
        "name": "MTDL Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2095
    },
    {
        "symbol": "MTEL.JK",
        "name": "MTEL Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 610
    },
    {
        "symbol": "MTFN.JK",
        "name": "MTFN Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2095
    },
    {
        "symbol": "MTLA.JK",
        "name": "MTLA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2095
    },
    {
        "symbol": "MTPS.JK",
        "name": "MTPS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2095
    },
    {
        "symbol": "MTWI.JK",
        "name": "MTWI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2095
    },
    {
        "symbol": "MUKO.JK",
        "name": "MUKO Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2114
    },
    {
        "symbol": "MUTU.JK",
        "name": "MUTU Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2114
    },
    {
        "symbol": "MYOH.JK",
        "name": "MYOH Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2190
    },
    {
        "symbol": "MYOR.JK",
        "name": "MYOR Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2450
    },
    {
        "symbol": "MYRX.JK",
        "name": "MYRX Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2190
    },
    {
        "symbol": "MYTX.JK",
        "name": "MYTX Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2190
    },
    {
        "symbol": "NANO.JK",
        "name": "NANO Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1771
    },
    {
        "symbol": "NASA.JK",
        "name": "NASA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1771
    },
    {
        "symbol": "NASI.JK",
        "name": "NASI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1771
    },
    {
        "symbol": "NAYZ.JK",
        "name": "NAYZ Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1771
    },
    {
        "symbol": "NCKL.JK",
        "name": "NCKL Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 890
    },
    {
        "symbol": "NDIN.JK",
        "name": "NDIN Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1828
    },
    {
        "symbol": "NELI.JK",
        "name": "NELI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1847
    },
    {
        "symbol": "NEST.JK",
        "name": "NEST Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1847
    },
    {
        "symbol": "NETV.JK",
        "name": "NETV Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1847
    },
    {
        "symbol": "NFCX.JK",
        "name": "NFCX Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1866
    },
    {
        "symbol": "NICE.JK",
        "name": "NICE Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1923
    },
    {
        "symbol": "NICK.JK",
        "name": "NICK Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1923
    },
    {
        "symbol": "NICL.JK",
        "name": "NICL Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1923
    },
    {
        "symbol": "NIKL.JK",
        "name": "NIKL Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1923
    },
    {
        "symbol": "NINE.JK",
        "name": "NINE Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1923
    },
    {
        "symbol": "NIPS.JK",
        "name": "NIPS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1923
    },
    {
        "symbol": "NIRO.JK",
        "name": "NIRO Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1923
    },
    {
        "symbol": "NISP.JK",
        "name": "NISP Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1923
    },
    {
        "symbol": "NOBU.JK",
        "name": "NOBU Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2037
    },
    {
        "symbol": "NPGF.JK",
        "name": "NPGF Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2056
    },
    {
        "symbol": "NRCA.JK",
        "name": "NRCA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2094
    },
    {
        "symbol": "NSSS.JK",
        "name": "NSSS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2113
    },
    {
        "symbol": "NTBK.JK",
        "name": "NTBK Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2132
    },
    {
        "symbol": "NTRX.JK",
        "name": "NTRX Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2132
    },
    {
        "symbol": "NUSA.JK",
        "name": "NUSA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2151
    },
    {
        "symbol": "NYNI.JK",
        "name": "NYNI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2227
    },
    {
        "symbol": "OASA.JK",
        "name": "OASA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1808
    },
    {
        "symbol": "OBMD.JK",
        "name": "OBMD Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1827
    },
    {
        "symbol": "OBMH.JK",
        "name": "OBMH Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1827
    },
    {
        "symbol": "OCBC.JK",
        "name": "OCBC Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1846
    },
    {
        "symbol": "OKAS.JK",
        "name": "OKAS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1998
    },
    {
        "symbol": "OKTA.JK",
        "name": "OKTA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1998
    },
    {
        "symbol": "OLIV.JK",
        "name": "OLIV Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2017
    },
    {
        "symbol": "OMRE.JK",
        "name": "OMRE Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2036
    },
    {
        "symbol": "OPMS.JK",
        "name": "OPMS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2093
    },
    {
        "symbol": "OPTY.JK",
        "name": "OPTY Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2093
    },
    {
        "symbol": "PADA.JK",
        "name": "PADA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1845
    },
    {
        "symbol": "PACK.JK",
        "name": "PACK Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1845
    },
    {
        "symbol": "PADI.JK",
        "name": "PADI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1845
    },
    {
        "symbol": "PALM.JK",
        "name": "PALM Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1845
    },
    {
        "symbol": "PAMG.JK",
        "name": "PAMG Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1845
    },
    {
        "symbol": "PANI.JK",
        "name": "PANI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 14800
    },
    {
        "symbol": "PANR.JK",
        "name": "PANR Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1845
    },
    {
        "symbol": "PANS.JK",
        "name": "PANS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1845
    },
    {
        "symbol": "PBID.JK",
        "name": "PBID Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1864
    },
    {
        "symbol": "PBRX.JK",
        "name": "PBRX Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1864
    },
    {
        "symbol": "PBSA.JK",
        "name": "PBSA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 340
    },
    {
        "symbol": "PCAR.JK",
        "name": "PCAR Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1883
    },
    {
        "symbol": "PDES.JK",
        "name": "PDES Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1902
    },
    {
        "symbol": "PEGE.JK",
        "name": "PEGE Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1921
    },
    {
        "symbol": "PEHA.JK",
        "name": "PEHA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1921
    },
    {
        "symbol": "PEVE.JK",
        "name": "PEVE Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1921
    },
    {
        "symbol": "PGAS.JK",
        "name": "PGAS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1510
    },
    {
        "symbol": "PGEO.JK",
        "name": "PGEO Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1959
    },
    {
        "symbol": "PGLI.JK",
        "name": "PGLI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1959
    },
    {
        "symbol": "PGUN.JK",
        "name": "PGUN Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1959
    },
    {
        "symbol": "PICO.JK",
        "name": "PICO Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1997
    },
    {
        "symbol": "PJAA.JK",
        "name": "PJAA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2016
    },
    {
        "symbol": "PKPK.JK",
        "name": "PKPK Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2035
    },
    {
        "symbol": "PLAN.JK",
        "name": "PLAN Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2054
    },
    {
        "symbol": "PLAS.JK",
        "name": "PLAS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2054
    },
    {
        "symbol": "PLIN.JK",
        "name": "PLIN Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2054
    },
    {
        "symbol": "PMJS.JK",
        "name": "PMJS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2073
    },
    {
        "symbol": "PMMP.JK",
        "name": "PMMP Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2073
    },
    {
        "symbol": "PNBN.JK",
        "name": "PNBN Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2092
    },
    {
        "symbol": "PNBS.JK",
        "name": "PNBS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2092
    },
    {
        "symbol": "PNGO.JK",
        "name": "PNGO Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2092
    },
    {
        "symbol": "PNIN.JK",
        "name": "PNIN Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2092
    },
    {
        "symbol": "PNLF.JK",
        "name": "PNLF Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2092
    },
    {
        "symbol": "PNSE.JK",
        "name": "PNSE Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2092
    },
    {
        "symbol": "POLA.JK",
        "name": "POLA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2111
    },
    {
        "symbol": "POLI.JK",
        "name": "POLI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2111
    },
    {
        "symbol": "POLL.JK",
        "name": "POLL Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2111
    },
    {
        "symbol": "POLU.JK",
        "name": "POLU Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2111
    },
    {
        "symbol": "POLY.JK",
        "name": "POLY Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2111
    },
    {
        "symbol": "POOL.JK",
        "name": "POOL Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2111
    },
    {
        "symbol": "PORT.JK",
        "name": "PORT Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2111
    },
    {
        "symbol": "POWR.JK",
        "name": "POWR Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2111
    },
    {
        "symbol": "PPGL.JK",
        "name": "PPGL Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2130
    },
    {
        "symbol": "PPRE.JK",
        "name": "PPRE Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2130
    },
    {
        "symbol": "PPRO.JK",
        "name": "PPRO Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2130
    },
    {
        "symbol": "PRAS.JK",
        "name": "PRAS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2168
    },
    {
        "symbol": "PRDA.JK",
        "name": "PRDA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2168
    },
    {
        "symbol": "PRIM.JK",
        "name": "PRIM Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2168
    },
    {
        "symbol": "PRNA.JK",
        "name": "PRNA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2168
    },
    {
        "symbol": "PSAB.JK",
        "name": "PSAB Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2187
    },
    {
        "symbol": "PSDN.JK",
        "name": "PSDN Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2187
    },
    {
        "symbol": "PSGO.JK",
        "name": "PSGO Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2187
    },
    {
        "symbol": "PSKT.JK",
        "name": "PSKT Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2187
    },
    {
        "symbol": "PSSI.JK",
        "name": "PSSI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2187
    },
    {
        "symbol": "PTBA.JK",
        "name": "PTBA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2720
    },
    {
        "symbol": "PTDU.JK",
        "name": "PTDU Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2206
    },
    {
        "symbol": "PTIS.JK",
        "name": "PTIS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2206
    },
    {
        "symbol": "PTMV.JK",
        "name": "PTMV Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2206
    },
    {
        "symbol": "PTMP.JK",
        "name": "PTMP Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2206
    },
    {
        "symbol": "PTNZ.JK",
        "name": "PTNZ Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2206
    },
    {
        "symbol": "PTPS.JK",
        "name": "PTPS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2206
    },
    {
        "symbol": "PTPP.JK",
        "name": "PTPP Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 410
    },
    {
        "symbol": "PTRO.JK",
        "name": "PTRO Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2206
    },
    {
        "symbol": "PUDP.JK",
        "name": "PUDP Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2225
    },
    {
        "symbol": "PURE.JK",
        "name": "PURE Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2225
    },
    {
        "symbol": "PURI.JK",
        "name": "PURI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2225
    },
    {
        "symbol": "PWON.JK",
        "name": "PWON Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 440
    },
    {
        "symbol": "PYFA.JK",
        "name": "PYFA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2301
    },
    {
        "symbol": "PZZA.JK",
        "name": "PZZA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2320
    },
    {
        "symbol": "RAAM.JK",
        "name": "RAAM Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1919
    },
    {
        "symbol": "RAFI.JK",
        "name": "RAFI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1919
    },
    {
        "symbol": "RAJA.JK",
        "name": "RAJA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1919
    },
    {
        "symbol": "RALS.JK",
        "name": "RALS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 430
    },
    {
        "symbol": "RANC.JK",
        "name": "RANC Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1919
    },
    {
        "symbol": "RBMS.JK",
        "name": "RBMS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1938
    },
    {
        "symbol": "RCCC.JK",
        "name": "RCCC Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1957
    },
    {
        "symbol": "RDTX.JK",
        "name": "RDTX Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1976
    },
    {
        "symbol": "REAL.JK",
        "name": "REAL Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1995
    },
    {
        "symbol": "RELI.JK",
        "name": "RELI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1995
    },
    {
        "symbol": "REPO.JK",
        "name": "REPO Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1995
    },
    {
        "symbol": "RICY.JK",
        "name": "RICY Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2071
    },
    {
        "symbol": "RIGS.JK",
        "name": "RIGS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2071
    },
    {
        "symbol": "RIMO.JK",
        "name": "RIMO Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2071
    },
    {
        "symbol": "RISE.JK",
        "name": "RISE Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2071
    },
    {
        "symbol": "RMKE.JK",
        "name": "RMKE Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 680
    },
    {
        "symbol": "RMKO.JK",
        "name": "RMKO Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2147
    },
    {
        "symbol": "ROCK.JK",
        "name": "ROCK Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2185
    },
    {
        "symbol": "RODA.JK",
        "name": "RODA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2185
    },
    {
        "symbol": "RONI.JK",
        "name": "RONI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2185
    },
    {
        "symbol": "ROPO.JK",
        "name": "ROPO Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2185
    },
    {
        "symbol": "ROTI.JK",
        "name": "ROTI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 980
    },
    {
        "symbol": "RSCH.JK",
        "name": "RSCH Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2261
    },
    {
        "symbol": "RSHI.JK",
        "name": "RSHI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2261
    },
    {
        "symbol": "RSGK.JK",
        "name": "RSGK Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2261
    },
    {
        "symbol": "RUIS.JK",
        "name": "RUIS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2299
    },
    {
        "symbol": "RUNS.JK",
        "name": "RUNS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2299
    },
    {
        "symbol": "SAGE.JK",
        "name": "SAGE Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1956
    },
    {
        "symbol": "SAIP.JK",
        "name": "SAIP Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1956
    },
    {
        "symbol": "SAME.JK",
        "name": "SAME Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1956
    },
    {
        "symbol": "SAMF.JK",
        "name": "SAMF Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1956
    },
    {
        "symbol": "SAPX.JK",
        "name": "SAPX Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1956
    },
    {
        "symbol": "SATU.JK",
        "name": "SATU Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1956
    },
    {
        "symbol": "SBAT.JK",
        "name": "SBAT Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1975
    },
    {
        "symbol": "SBMA.JK",
        "name": "SBMA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1975
    },
    {
        "symbol": "SCCO.JK",
        "name": "SCCO Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1994
    },
    {
        "symbol": "SCMA.JK",
        "name": "SCMA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 130
    },
    {
        "symbol": "SCNP.JK",
        "name": "SCNP Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1994
    },
    {
        "symbol": "SCPX.JK",
        "name": "SCPX Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1994
    },
    {
        "symbol": "SDMU.JK",
        "name": "SDMU Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2013
    },
    {
        "symbol": "SDPC.JK",
        "name": "SDPC Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2013
    },
    {
        "symbol": "SDRX.JK",
        "name": "SDRX Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2013
    },
    {
        "symbol": "SDRA.JK",
        "name": "SDRA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2013
    },
    {
        "symbol": "SEAT.JK",
        "name": "SEAT Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2032
    },
    {
        "symbol": "SGER.JK",
        "name": "SGER Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2070
    },
    {
        "symbol": "SGRO.JK",
        "name": "SGRO Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2070
    },
    {
        "symbol": "SHID.JK",
        "name": "SHID Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2089
    },
    {
        "symbol": "SHIP.JK",
        "name": "SHIP Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2089
    },
    {
        "symbol": "SICO.JK",
        "name": "SICO Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2108
    },
    {
        "symbol": "SIDO.JK",
        "name": "SIDO Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 640
    },
    {
        "symbol": "SILO.JK",
        "name": "SILO Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2890
    },
    {
        "symbol": "SIMP.JK",
        "name": "SIMP Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2108
    },
    {
        "symbol": "SINI.JK",
        "name": "SINI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2108
    },
    {
        "symbol": "SIPD.JK",
        "name": "SIPD Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2108
    },
    {
        "symbol": "SKBM.JK",
        "name": "SKBM Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2146
    },
    {
        "symbol": "SKLT.JK",
        "name": "SKLT Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2146
    },
    {
        "symbol": "SKRN.JK",
        "name": "SKRN Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2146
    },
    {
        "symbol": "SLIS.JK",
        "name": "SLIS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2165
    },
    {
        "symbol": "SMAR.JK",
        "name": "SMAR Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2184
    },
    {
        "symbol": "SMDM.JK",
        "name": "SMDM Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2184
    },
    {
        "symbol": "SMDR.JK",
        "name": "SMDR Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 315
    },
    {
        "symbol": "SMGA.JK",
        "name": "SMGA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2184
    },
    {
        "symbol": "SMGR.JK",
        "name": "SMGR Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 3950
    },
    {
        "symbol": "SMIL.JK",
        "name": "SMIL Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2184
    },
    {
        "symbol": "SMKL.JK",
        "name": "SMKL Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2184
    },
    {
        "symbol": "SMMA.JK",
        "name": "SMMA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2184
    },
    {
        "symbol": "SMMT.JK",
        "name": "SMMT Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2184
    },
    {
        "symbol": "SMRA.JK",
        "name": "SMRA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 590
    },
    {
        "symbol": "SMRU.JK",
        "name": "SMRU Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2184
    },
    {
        "symbol": "SMSM.JK",
        "name": "SMSM Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1980
    },
    {
        "symbol": "SNLK.JK",
        "name": "SNLK Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2203
    },
    {
        "symbol": "SOBI.JK",
        "name": "SOBI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2222
    },
    {
        "symbol": "SOCHI.JK",
        "name": "SOCHI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2222
    },
    {
        "symbol": "SOHO.JK",
        "name": "SOHO Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2222
    },
    {
        "symbol": "SOLA.JK",
        "name": "SOLA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2222
    },
    {
        "symbol": "SONA.JK",
        "name": "SONA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2222
    },
    {
        "symbol": "SOSS.JK",
        "name": "SOSS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2222
    },
    {
        "symbol": "SOTS.JK",
        "name": "SOTS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2222
    },
    {
        "symbol": "SPMA.JK",
        "name": "SPMA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 240
    },
    {
        "symbol": "SPTO.JK",
        "name": "SPTO Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2241
    },
    {
        "symbol": "SQMI.JK",
        "name": "SQMI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2260
    },
    {
        "symbol": "SRAJ.JK",
        "name": "SRAJ Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2279
    },
    {
        "symbol": "SREN.JK",
        "name": "SREN Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2279
    },
    {
        "symbol": "SRIL.JK",
        "name": "SRIL Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2279
    },
    {
        "symbol": "SRSN.JK",
        "name": "SRSN Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2279
    },
    {
        "symbol": "SRTG.JK",
        "name": "SRTG Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2250
    },
    {
        "symbol": "SSIA.JK",
        "name": "SSIA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2298
    },
    {
        "symbol": "SSMS.JK",
        "name": "SSMS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1120
    },
    {
        "symbol": "SSTM.JK",
        "name": "SSTM Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2298
    },
    {
        "symbol": "STAR.JK",
        "name": "STAR Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2317
    },
    {
        "symbol": "STAA.JK",
        "name": "STAA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 920
    },
    {
        "symbol": "STTP.JK",
        "name": "STTP Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2317
    },
    {
        "symbol": "SULI.JK",
        "name": "SULI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2336
    },
    {
        "symbol": "SUPR.JK",
        "name": "SUPR Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2336
    },
    {
        "symbol": "SURE.JK",
        "name": "SURE Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2336
    },
    {
        "symbol": "SWAT.JK",
        "name": "SWAT Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2374
    },
    {
        "symbol": "SWID.JK",
        "name": "SWID Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2374
    },
    {
        "symbol": "TALF.JK",
        "name": "TALF Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1993
    },
    {
        "symbol": "TAMA.JK",
        "name": "TAMA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1993
    },
    {
        "symbol": "TAMU.JK",
        "name": "TAMU Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1993
    },
    {
        "symbol": "TAPG.JK",
        "name": "TAPG Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 850
    },
    {
        "symbol": "TARA.JK",
        "name": "TARA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1993
    },
    {
        "symbol": "TAYS.JK",
        "name": "TAYS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1993
    },
    {
        "symbol": "TBIG.JK",
        "name": "TBIG Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1720
    },
    {
        "symbol": "TBLA.JK",
        "name": "TBLA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2012
    },
    {
        "symbol": "TBMS.JK",
        "name": "TBMS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2012
    },
    {
        "symbol": "TCID.JK",
        "name": "TCID Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2031
    },
    {
        "symbol": "TCPI.JK",
        "name": "TCPI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2031
    },
    {
        "symbol": "TDPM.JK",
        "name": "TDPM Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2050
    },
    {
        "symbol": "TEBE.JK",
        "name": "TEBE Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 720
    },
    {
        "symbol": "TECH.JK",
        "name": "TECH Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2069
    },
    {
        "symbol": "TELE.JK",
        "name": "TELE Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2069
    },
    {
        "symbol": "TFAS.JK",
        "name": "TFAS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2088
    },
    {
        "symbol": "TFCO.JK",
        "name": "TFCO Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2088
    },
    {
        "symbol": "TGKA.JK",
        "name": "TGKA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2107
    },
    {
        "symbol": "TGRA.JK",
        "name": "TGRA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2107
    },
    {
        "symbol": "TIFA.JK",
        "name": "TIFA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2145
    },
    {
        "symbol": "TINS.JK",
        "name": "TINS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1150
    },
    {
        "symbol": "TIRA.JK",
        "name": "TIRA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2145
    },
    {
        "symbol": "TIRT.JK",
        "name": "TIRT Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2145
    },
    {
        "symbol": "TKIM.JK",
        "name": "TKIM Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 6750
    },
    {
        "symbol": "TLDN.JK",
        "name": "TLDN Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2202
    },
    {
        "symbol": "TLKM.JK",
        "name": "TLKM Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2670
    },
    {
        "symbol": "TMAH.JK",
        "name": "TMAH Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2221
    },
    {
        "symbol": "TMAS.JK",
        "name": "TMAS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 160
    },
    {
        "symbol": "TMPO.JK",
        "name": "TMPO Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2221
    },
    {
        "symbol": "TNCA.JK",
        "name": "TNCA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2240
    },
    {
        "symbol": "TOBA.JK",
        "name": "TOBA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 540
    },
    {
        "symbol": "TOKO.JK",
        "name": "TOKO Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2259
    },
    {
        "symbol": "TOOL.JK",
        "name": "TOOL Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2259
    },
    {
        "symbol": "TOPS.JK",
        "name": "TOPS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2259
    },
    {
        "symbol": "TOTI.JK",
        "name": "TOTI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2259
    },
    {
        "symbol": "TOTO.JK",
        "name": "TOTO Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2259
    },
    {
        "symbol": "TOWR.JK",
        "name": "TOWR Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 780
    },
    {
        "symbol": "TOYS.JK",
        "name": "TOYS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2259
    },
    {
        "symbol": "TPIA.JK",
        "name": "TPIA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 7200
    },
    {
        "symbol": "TPMA.JK",
        "name": "TPMA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2278
    },
    {
        "symbol": "TRAM.JK",
        "name": "TRAM Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2316
    },
    {
        "symbol": "TRGU.JK",
        "name": "TRGU Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2316
    },
    {
        "symbol": "TRIM.JK",
        "name": "TRIM Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2316
    },
    {
        "symbol": "TRIN.JK",
        "name": "TRIN Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2316
    },
    {
        "symbol": "TRIS.JK",
        "name": "TRIS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2316
    },
    {
        "symbol": "TRJA.JK",
        "name": "TRJA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2316
    },
    {
        "symbol": "TRON.JK",
        "name": "TRON Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2316
    },
    {
        "symbol": "TRST.JK",
        "name": "TRST Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2316
    },
    {
        "symbol": "TRUK.JK",
        "name": "TRUK Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2316
    },
    {
        "symbol": "TRUS.JK",
        "name": "TRUS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2316
    },
    {
        "symbol": "TSPC.JK",
        "name": "TSPC Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2335
    },
    {
        "symbol": "TUGU.JK",
        "name": "TUGU Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2373
    },
    {
        "symbol": "TYRE.JK",
        "name": "TYRE Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2449
    },
    {
        "symbol": "UANG.JK",
        "name": "UANG Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2030
    },
    {
        "symbol": "UCID.JK",
        "name": "UCID Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2068
    },
    {
        "symbol": "UFOE.JK",
        "name": "UFOE Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2125
    },
    {
        "symbol": "ULTJ.JK",
        "name": "ULTJ Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1620
    },
    {
        "symbol": "UNIC.JK",
        "name": "UNIC Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2277
    },
    {
        "symbol": "UNIQ.JK",
        "name": "UNIQ Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2277
    },
    {
        "symbol": "UNIT.JK",
        "name": "UNIT Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2277
    },
    {
        "symbol": "UNSP.JK",
        "name": "UNSP Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2277
    },
    {
        "symbol": "UNTR.JK",
        "name": "UNTR Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 26075
    },
    {
        "symbol": "UNVR.JK",
        "name": "UNVR Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1980
    },
    {
        "symbol": "URBN.JK",
        "name": "URBN Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2353
    },
    {
        "symbol": "UVCR.JK",
        "name": "UVCR Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2429
    },
    {
        "symbol": "VAST.JK",
        "name": "VAST Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2067
    },
    {
        "symbol": "VAUL.JK",
        "name": "VAUL Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2067
    },
    {
        "symbol": "VAYU.JK",
        "name": "VAYU Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2067
    },
    {
        "symbol": "VBLA.JK",
        "name": "VBLA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2086
    },
    {
        "symbol": "VCKP.JK",
        "name": "VCKP Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2105
    },
    {
        "symbol": "VICO.JK",
        "name": "VICO Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2219
    },
    {
        "symbol": "VINS.JK",
        "name": "VINS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2219
    },
    {
        "symbol": "VIPT.JK",
        "name": "VIPT Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2219
    },
    {
        "symbol": "VISA.JK",
        "name": "VISA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2219
    },
    {
        "symbol": "VISI.JK",
        "name": "VISI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2219
    },
    {
        "symbol": "VITA.JK",
        "name": "VITA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2219
    },
    {
        "symbol": "VKTR.JK",
        "name": "VKTR Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2257
    },
    {
        "symbol": "VOKS.JK",
        "name": "VOKS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2333
    },
    {
        "symbol": "VRNA.JK",
        "name": "VRNA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2390
    },
    {
        "symbol": "VTNY.JK",
        "name": "VTNY Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2428
    },
    {
        "symbol": "WAPO.JK",
        "name": "WAPO Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2104
    },
    {
        "symbol": "WEGE.JK",
        "name": "WEGE Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2180
    },
    {
        "symbol": "WEHA.JK",
        "name": "WEHA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2180
    },
    {
        "symbol": "WGSH.JK",
        "name": "WGSH Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2218
    },
    {
        "symbol": "WICO.JK",
        "name": "WICO Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2256
    },
    {
        "symbol": "WIDI.JK",
        "name": "WIDI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2256
    },
    {
        "symbol": "WIFE.JK",
        "name": "WIFE Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2256
    },
    {
        "symbol": "WIFI.JK",
        "name": "WIFI Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 280
    },
    {
        "symbol": "WIIM.JK",
        "name": "WIIM Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 1050
    },
    {
        "symbol": "WIKA.JK",
        "name": "WIKA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 280
    },
    {
        "symbol": "WIKB.JK",
        "name": "WIKB Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2256
    },
    {
        "symbol": "WINR.JK",
        "name": "WINR Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2256
    },
    {
        "symbol": "WINS.JK",
        "name": "WINS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2256
    },
    {
        "symbol": "WIRG.JK",
        "name": "WIRG Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 95
    },
    {
        "symbol": "WMPP.JK",
        "name": "WMPP Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2332
    },
    {
        "symbol": "WMUU.JK",
        "name": "WMUU Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2332
    },
    {
        "symbol": "WOMF.JK",
        "name": "WOMF Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2370
    },
    {
        "symbol": "WOOD.JK",
        "name": "WOOD Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 220
    },
    {
        "symbol": "WOWS.JK",
        "name": "WOWS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2370
    },
    {
        "symbol": "WSBP.JK",
        "name": "WSBP Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2446
    },
    {
        "symbol": "WSKT.JK",
        "name": "WSKT Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2446
    },
    {
        "symbol": "WTON.JK",
        "name": "WTON Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2465
    },
    {
        "symbol": "YELO.JK",
        "name": "YELO Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2254
    },
    {
        "symbol": "YPAS.JK",
        "name": "YPAS Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2463
    },
    {
        "symbol": "YULE.JK",
        "name": "YULE Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2558
    },
    {
        "symbol": "ZATA.JK",
        "name": "ZATA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2215
    },
    {
        "symbol": "ZBRA.JK",
        "name": "ZBRA Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2234
    },
    {
        "symbol": "ZINC.JK",
        "name": "ZINC Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 2367
    },
    {
        "symbol": "ZYRX.JK",
        "name": "ZYRX Indonesia Tbk",
        "category": "Saham Indo",
        "currency": "IDR",
        "lotSize": 100,
        "price": 171
    }
];

const US_GLOBAL_ASSETS = [
    {
        "symbol": "NVDA",
        "name": "NVIDIA Corp",
        "category": "Saham US",
        "currency": "USD",
        "lotSize": 1,
        "price": 219.4
    },
    {
        "symbol": "AAPL",
        "name": "Apple Inc",
        "category": "Saham US",
        "currency": "USD",
        "lotSize": 1,
        "price": 228.5
    },
    {
        "symbol": "MSFT",
        "name": "Microsoft Corp",
        "category": "Saham US",
        "currency": "USD",
        "lotSize": 1,
        "price": 432.1
    },
    {
        "symbol": "AMZN",
        "name": "Amazon.com Inc",
        "category": "Saham US",
        "currency": "USD",
        "lotSize": 1,
        "price": 189.4
    },
    {
        "symbol": "GOOGL",
        "name": "Alphabet Inc (Google A)",
        "category": "Saham US",
        "currency": "USD",
        "lotSize": 1,
        "price": 168.2
    },
    {
        "symbol": "META",
        "name": "Meta Platforms Inc",
        "category": "Saham US",
        "currency": "USD",
        "lotSize": 1,
        "price": 585
    },
    {
        "symbol": "TSLA",
        "name": "Tesla Inc",
        "category": "Saham US",
        "currency": "USD",
        "lotSize": 1,
        "price": 245.8
    },
    {
        "symbol": "BRK-B",
        "name": "Berkshire Hathaway Inc",
        "category": "Saham US",
        "currency": "USD",
        "lotSize": 1,
        "price": 452
    },
    {
        "symbol": "AVGO",
        "name": "Broadcom Inc",
        "category": "Saham US",
        "currency": "USD",
        "lotSize": 1,
        "price": 172.5
    },
    {
        "symbol": "LLY",
        "name": "Eli Lilly and Company",
        "category": "Saham US",
        "currency": "USD",
        "lotSize": 1,
        "price": 785
    },
    {
        "symbol": "JPM",
        "name": "JPMorgan Chase & Co",
        "category": "Saham US",
        "currency": "USD",
        "lotSize": 1,
        "price": 225.4
    },
    {
        "symbol": "V",
        "name": "Visa Inc",
        "category": "Saham US",
        "currency": "USD",
        "lotSize": 1,
        "price": 282
    },
    {
        "symbol": "UNH",
        "name": "UnitedHealth Group",
        "category": "Saham US",
        "currency": "USD",
        "lotSize": 1,
        "price": 580
    },
    {
        "symbol": "XOM",
        "name": "Exxon Mobil Corp",
        "category": "Saham US",
        "currency": "USD",
        "lotSize": 1,
        "price": 118.6
    },
    {
        "symbol": "MA",
        "name": "Mastercard Inc",
        "category": "Saham US",
        "currency": "USD",
        "lotSize": 1,
        "price": 495
    },
    {
        "symbol": "COST",
        "name": "Costco Wholesale Corp",
        "category": "Saham US",
        "currency": "USD",
        "lotSize": 1,
        "price": 895
    },
    {
        "symbol": "HD",
        "name": "Home Depot Inc",
        "category": "Saham US",
        "currency": "USD",
        "lotSize": 1,
        "price": 395
    },
    {
        "symbol": "PG",
        "name": "Procter & Gamble Co",
        "category": "Saham US",
        "currency": "USD",
        "lotSize": 1,
        "price": 172
    },
    {
        "symbol": "JNJ",
        "name": "Johnson & Johnson",
        "category": "Saham US",
        "currency": "USD",
        "lotSize": 1,
        "price": 161.5
    },
    {
        "symbol": "NFLX",
        "name": "Netflix Inc",
        "category": "Saham US",
        "currency": "USD",
        "lotSize": 1,
        "price": 720
    },
    {
        "symbol": "AMD",
        "name": "Advanced Micro Devices",
        "category": "Saham US",
        "currency": "USD",
        "lotSize": 1,
        "price": 156.4
    },
    {
        "symbol": "ABBV",
        "name": "AbbVie Inc",
        "category": "Saham US",
        "currency": "USD",
        "lotSize": 1,
        "price": 188.2
    },
    {
        "symbol": "BAC",
        "name": "Bank of America Corp",
        "category": "Saham US",
        "currency": "USD",
        "lotSize": 1,
        "price": 42.5
    },
    {
        "symbol": "CRM",
        "name": "Salesforce Inc",
        "category": "Saham US",
        "currency": "USD",
        "lotSize": 1,
        "price": 290
    },
    {
        "symbol": "KO",
        "name": "The Coca-Cola Company",
        "category": "Saham US",
        "currency": "USD",
        "lotSize": 1,
        "price": 68.5
    },
    {
        "symbol": "PEP",
        "name": "PepsiCo Inc",
        "category": "Saham US",
        "currency": "USD",
        "lotSize": 1,
        "price": 174
    },
    {
        "symbol": "ADBE",
        "name": "Adobe Inc",
        "category": "Saham US",
        "currency": "USD",
        "lotSize": 1,
        "price": 512
    },
    {
        "symbol": "WMT",
        "name": "Walmart Inc",
        "category": "Saham US",
        "currency": "USD",
        "lotSize": 1,
        "price": 82.5
    },
    {
        "symbol": "CVX",
        "name": "Chevron Corp",
        "category": "Saham US",
        "currency": "USD",
        "lotSize": 1,
        "price": 152
    },
    {
        "symbol": "ORCL",
        "name": "Oracle Corp",
        "category": "Saham US",
        "currency": "USD",
        "lotSize": 1,
        "price": 175.5
    },
    {
        "symbol": "QCOM",
        "name": "QUALCOMM Inc",
        "category": "Saham US",
        "currency": "USD",
        "lotSize": 1,
        "price": 168
    },
    {
        "symbol": "INTC",
        "name": "Intel Corp",
        "category": "Saham US",
        "currency": "USD",
        "lotSize": 1,
        "price": 23.4
    },
    {
        "symbol": "CSCO",
        "name": "Cisco Systems Inc",
        "category": "Saham US",
        "currency": "USD",
        "lotSize": 1,
        "price": 54
    },
    {
        "symbol": "IBM",
        "name": "International Business Machines",
        "category": "Saham US",
        "currency": "USD",
        "lotSize": 1,
        "price": 215
    },
    {
        "symbol": "PLTR",
        "name": "Palantir Technologies Inc",
        "category": "Saham US",
        "currency": "USD",
        "lotSize": 1,
        "price": 44.5
    },
    {
        "symbol": "UBER",
        "name": "Uber Technologies Inc",
        "category": "Saham US",
        "currency": "USD",
        "lotSize": 1,
        "price": 78.2
    },
    {
        "symbol": "SNOW",
        "name": "Snowflake Inc",
        "category": "Saham US",
        "currency": "USD",
        "lotSize": 1,
        "price": 118
    },
    {
        "symbol": "DIS",
        "name": "Walt Disney Co",
        "category": "Saham US",
        "currency": "USD",
        "lotSize": 1,
        "price": 96.5
    },
    {
        "symbol": "CAT",
        "name": "Caterpillar Inc",
        "category": "Saham US",
        "currency": "USD",
        "lotSize": 1,
        "price": 388
    },
    {
        "symbol": "GE",
        "name": "General Electric Co",
        "category": "Saham US",
        "currency": "USD",
        "lotSize": 1,
        "price": 185
    },
    {
        "symbol": "NOW",
        "name": "ServiceNow Inc",
        "category": "Saham US",
        "currency": "USD",
        "lotSize": 1,
        "price": 920
    },
    {
        "symbol": "AMAT",
        "name": "Applied Materials Inc",
        "category": "Saham US",
        "currency": "USD",
        "lotSize": 1,
        "price": 198
    },
    {
        "symbol": "TXN",
        "name": "Texas Instruments Inc",
        "category": "Saham US",
        "currency": "USD",
        "lotSize": 1,
        "price": 205
    },
    {
        "symbol": "INTU",
        "name": "Intuit Inc",
        "category": "Saham US",
        "currency": "USD",
        "lotSize": 1,
        "price": 645
    },
    {
        "symbol": "ISRG",
        "name": "Intuitive Surgical Inc",
        "category": "Saham US",
        "currency": "USD",
        "lotSize": 1,
        "price": 495
    },
    {
        "symbol": "SPGI",
        "name": "S&P Global Inc",
        "category": "Saham US",
        "currency": "USD",
        "lotSize": 1,
        "price": 508
    },
    {
        "symbol": "GS",
        "name": "Goldman Sachs Group Inc",
        "category": "Saham US",
        "currency": "USD",
        "lotSize": 1,
        "price": 512
    },
    {
        "symbol": "MS",
        "name": "Morgan Stanley",
        "category": "Saham US",
        "currency": "USD",
        "lotSize": 1,
        "price": 114
    },
    {
        "symbol": "BLK",
        "name": "BlackRock Inc",
        "category": "Saham US",
        "currency": "USD",
        "lotSize": 1,
        "price": 985
    },
    {
        "symbol": "SPY",
        "name": "SPDR S&P 500 ETF Trust",
        "category": "Saham US",
        "currency": "USD",
        "lotSize": 1,
        "price": 580.5
    },
    {
        "symbol": "QQQ",
        "name": "Invesco QQQ Trust (Nasdaq 100)",
        "category": "Saham US",
        "currency": "USD",
        "lotSize": 1,
        "price": 492
    },
    {
        "symbol": "SMH",
        "name": "VanEck Semiconductor ETF",
        "category": "Saham US",
        "currency": "USD",
        "lotSize": 1,
        "price": 255
    },
    {
        "symbol": "TSM",
        "name": "Taiwan Semiconductor (TSMC)",
        "category": "Saham Global",
        "currency": "USD",
        "lotSize": 1,
        "price": 195
    },
    {
        "symbol": "BABA",
        "name": "Alibaba Group Holding Ltd",
        "category": "Saham Global",
        "currency": "USD",
        "lotSize": 1,
        "price": 98.4
    },
    {
        "symbol": "PDD",
        "name": "PDD Holdings Inc (Temu)",
        "category": "Saham Global",
        "currency": "USD",
        "lotSize": 1,
        "price": 122
    },
    {
        "symbol": "ASML",
        "name": "ASML Holding NV",
        "category": "Saham Global",
        "currency": "USD",
        "lotSize": 1,
        "price": 710
    },
    {
        "symbol": "NVO",
        "name": "Novo Nordisk A/S",
        "category": "Saham Global",
        "currency": "USD",
        "lotSize": 1,
        "price": 118
    },
    {
        "symbol": "SAP",
        "name": "SAP SE",
        "category": "Saham Global",
        "currency": "USD",
        "lotSize": 1,
        "price": 228
    },
    {
        "symbol": "TM",
        "name": "Toyota Motor Corp",
        "category": "Saham Global",
        "currency": "USD",
        "lotSize": 1,
        "price": 178
    },
    {
        "symbol": "SONY",
        "name": "Sony Group Corp",
        "category": "Saham Global",
        "currency": "USD",
        "lotSize": 1,
        "price": 92
    }
];

const CRYPTO_ASSETS = [
    {
        "symbol": "BTC-USD",
        "name": "Bitcoin (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 64200
    },
    {
        "symbol": "ETH-USD",
        "name": "Ethereum (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 2650
    },
    {
        "symbol": "SOL-USD",
        "name": "Solana (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 158.5
    },
    {
        "symbol": "BNB-USD",
        "name": "BNB Chain (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 595
    },
    {
        "symbol": "XRP-USD",
        "name": "Ripple XRP (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 0.585
    },
    {
        "symbol": "ADA-USD",
        "name": "Cardano (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 0.365
    },
    {
        "symbol": "DOGE-USD",
        "name": "Dogecoin (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 0.125
    },
    {
        "symbol": "AVAX-USD",
        "name": "Avalanche (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 28.4
    },
    {
        "symbol": "DOT-USD",
        "name": "Polkadot (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 4.5
    },
    {
        "symbol": "LINK-USD",
        "name": "Chainlink (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 11.8
    },
    {
        "symbol": "SHIB-USD",
        "name": "Shiba Inu (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 0.000018
    },
    {
        "symbol": "NEAR-USD",
        "name": "NEAR Protocol (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 4.85
    },
    {
        "symbol": "SUI-USD",
        "name": "Sui Network (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 2.15
    },
    {
        "symbol": "UNI-USD",
        "name": "Uniswap (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 7.8
    },
    {
        "symbol": "PEPE-USD",
        "name": "Pepe Token (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 0.00001
    },
    {
        "symbol": "APT-USD",
        "name": "Aptos (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 9.2
    },
    {
        "symbol": "ICP-USD",
        "name": "Internet Computer (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 8.5
    },
    {
        "symbol": "FET-USD",
        "name": "Artificial Superintelligence (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 1.45
    },
    {
        "symbol": "RENDER-USD",
        "name": "Render Token (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 5.6
    },
    {
        "symbol": "KAS-USD",
        "name": "Kaspa (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 0.135
    },
    {
        "symbol": "TIA-USD",
        "name": "Celestia (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 5.8
    },
    {
        "symbol": "OP-USD",
        "name": "Optimism (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 1.65
    },
    {
        "symbol": "ARB-USD",
        "name": "Arbitrum (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 0.58
    },
    {
        "symbol": "INJ-USD",
        "name": "Injective (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 21.5
    },
    {
        "symbol": "FIL-USD",
        "name": "Filecoin (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 3.8
    },
    {
        "symbol": "IMX-USD",
        "name": "Immutable X (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 1.55
    },
    {
        "symbol": "STX-USD",
        "name": "Stacks (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 1.85
    },
    {
        "symbol": "TAO-USD",
        "name": "Bittensor (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 560
    },
    {
        "symbol": "AAVE-USD",
        "name": "Aave DeFi (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 155
    },
    {
        "symbol": "FTM-USD",
        "name": "Fantom (Sonic) (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 0.68
    },
    {
        "symbol": "GRT-USD",
        "name": "The Graph (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 0.165
    },
    {
        "symbol": "THETA-USD",
        "name": "Theta Network (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 1.35
    },
    {
        "symbol": "MKR-USD",
        "name": "MakerDAO (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 1650
    },
    {
        "symbol": "FLOKI-USD",
        "name": "Floki Inu (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 0.00015
    },
    {
        "symbol": "BONK-USD",
        "name": "Bonk Solana (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 0.000022
    },
    {
        "symbol": "WIF-USD",
        "name": "dogwifhat (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 2.45
    },
    {
        "symbol": "PENDLE-USD",
        "name": "Pendle Finance (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 4.5
    },
    {
        "symbol": "RUNE-USD",
        "name": "THORChain (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 5.1
    },
    {
        "symbol": "ALGO-USD",
        "name": "Algorand (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 0.13
    },
    {
        "symbol": "JUP-USD",
        "name": "Jupiter DEX (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 0.95
    },
    {
        "symbol": "BEAM-USD",
        "name": "Beam Gaming (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 0.018
    },
    {
        "symbol": "OM-USD",
        "name": "MANTRA RWA (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 1.45
    },
    {
        "symbol": "SEI-USD",
        "name": "Sei Network (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 0.44
    },
    {
        "symbol": "GALA-USD",
        "name": "Gala Games (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 0.024
    },
    {
        "symbol": "PYTH-USD",
        "name": "Pyth Network (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 0.35
    },
    {
        "symbol": "ONDO-USD",
        "name": "Ondo Finance (RWA) (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 0.78
    },
    {
        "symbol": "STRK-USD",
        "name": "Starknet (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 0.42
    },
    {
        "symbol": "DYDX-USD",
        "name": "dYdX Protocol (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 1.15
    },
    {
        "symbol": "CORE-USD",
        "name": "Core DAO (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 1.05
    },
    {
        "symbol": "CHZ-USD",
        "name": "Chiliz (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 0.068
    },
    {
        "symbol": "HBAR-USD",
        "name": "Hedera (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 0.055
    },
    {
        "symbol": "VET-USD",
        "name": "VeChain (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 0.023
    },
    {
        "symbol": "QNT-USD",
        "name": "Quant (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 72
    },
    {
        "symbol": "MATIC-USD",
        "name": "Polygon (POL) (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 0.38
    },
    {
        "symbol": "LTC-USD",
        "name": "Litecoin (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 68.5
    },
    {
        "symbol": "BCH-USD",
        "name": "Bitcoin Cash (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 345
    },
    {
        "symbol": "ETC-USD",
        "name": "Ethereum Classic (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 19.5
    },
    {
        "symbol": "ATOM-USD",
        "name": "Cosmos Hub (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 4.6
    },
    {
        "symbol": "XLM-USD",
        "name": "Stellar Lumens (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 0.095
    },
    {
        "symbol": "SAND-USD",
        "name": "The Sandbox (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 0.28
    },
    {
        "symbol": "MANA-USD",
        "name": "Decentraland (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 0.31
    },
    {
        "symbol": "AXS-USD",
        "name": "Axie Infinity (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 5.1
    },
    {
        "symbol": "FLOW-USD",
        "name": "Flow (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 0.58
    },
    {
        "symbol": "EGLD-USD",
        "name": "MultiversX (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 28.5
    },
    {
        "symbol": "EOS-USD",
        "name": "EOS Network (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 0.52
    },
    {
        "symbol": "XTZ-USD",
        "name": "Tezos (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 0.72
    },
    {
        "symbol": "IOTA-USD",
        "name": "IOTA (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 0.135
    },
    {
        "symbol": "NEO-USD",
        "name": "NEO (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 10.8
    },
    {
        "symbol": "KAVA-USD",
        "name": "Kava (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 0.38
    },
    {
        "symbol": "ROSE-USD",
        "name": "Oasis Network (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 0.065
    },
    {
        "symbol": "CFX-USD",
        "name": "Conflux (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 0.155
    },
    {
        "symbol": "SNX-USD",
        "name": "Synthetix (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 1.6
    },
    {
        "symbol": "CRV-USD",
        "name": "Curve DAO (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 0.285
    },
    {
        "symbol": "1INCH-USD",
        "name": "1inch Network (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 0.29
    },
    {
        "symbol": "LDO-USD",
        "name": "Lido DAO (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 1.25
    },
    {
        "symbol": "RPL-USD",
        "name": "Rocket Pool (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 11.2
    },
    {
        "symbol": "BLUR-USD",
        "name": "Blur NFT (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 0.26
    },
    {
        "symbol": "DYM-USD",
        "name": "Dymension (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 1.65
    },
    {
        "symbol": "ALT-USD",
        "name": "Altlayer (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 0.115
    },
    {
        "symbol": "PIXEL-USD",
        "name": "Pixels Gaming (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 0.16
    },
    {
        "symbol": "PORTAL-USD",
        "name": "Portal Gaming (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 0.32
    },
    {
        "symbol": "W-USD",
        "name": "Wormhole (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 0.32
    },
    {
        "symbol": "ENA-USD",
        "name": "Ethena USDe (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 0.38
    },
    {
        "symbol": "TNSR-USD",
        "name": "Tensor Solana (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 0.48
    },
    {
        "symbol": "REZ-USD",
        "name": "Renzo Protocol (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 0.045
    },
    {
        "symbol": "BB-USD",
        "name": "BounceBit (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 0.31
    },
    {
        "symbol": "NOT-USD",
        "name": "Notcoin TON (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 0.0085
    },
    {
        "symbol": "IO-USD",
        "name": "io.net DePIN (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 1.95
    },
    {
        "symbol": "ZK-USD",
        "name": "ZKsync (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 0.145
    },
    {
        "symbol": "LAYER-USD",
        "name": "Solayer (Crypto)",
        "category": "Crypto",
        "currency": "USD",
        "lotSize": 1,
        "price": 0.85
    }
];

const COMMODITY_ASSETS = [
    {
        "symbol": "GC=F",
        "name": "Gold Futures (Emas Dunia)",
        "category": "Komoditas",
        "currency": "USD",
        "lotSize": 1,
        "price": 2650.4
    },
    {
        "symbol": "SI=F",
        "name": "Silver Futures (Perak)",
        "category": "Komoditas",
        "currency": "USD",
        "lotSize": 1,
        "price": 31.8
    },
    {
        "symbol": "CL=F",
        "name": "Crude Oil WTI Futures",
        "category": "Komoditas",
        "currency": "USD",
        "lotSize": 1,
        "price": 71.2
    },
    {
        "symbol": "BZ=F",
        "name": "Brent Crude Oil Futures",
        "category": "Komoditas",
        "currency": "USD",
        "lotSize": 1,
        "price": 75.2
    },
    {
        "symbol": "NG=F",
        "name": "Natural Gas Futures",
        "category": "Komoditas",
        "currency": "USD",
        "lotSize": 1,
        "price": 2.85
    },
    {
        "symbol": "HG=F",
        "name": "Copper Futures (Tembaga)",
        "category": "Komoditas",
        "currency": "USD",
        "lotSize": 1,
        "price": 4.35
    },
    {
        "symbol": "PL=F",
        "name": "Platinum Futures",
        "category": "Komoditas",
        "currency": "USD",
        "lotSize": 1,
        "price": 985
    },
    {
        "symbol": "PA=F",
        "name": "Palladium Futures",
        "category": "Komoditas",
        "currency": "USD",
        "lotSize": 1,
        "price": 1040
    },
    {
        "symbol": "ZC=F",
        "name": "Corn Futures (Jagung)",
        "category": "Komoditas",
        "currency": "USD",
        "lotSize": 1,
        "price": 415
    },
    {
        "symbol": "ZS=F",
        "name": "Soybean Futures (Kedelai)",
        "category": "Komoditas",
        "currency": "USD",
        "lotSize": 1,
        "price": 1020
    },
    {
        "symbol": "ZW=F",
        "name": "Wheat Futures (Gandum)",
        "category": "Komoditas",
        "currency": "USD",
        "lotSize": 1,
        "price": 580
    },
    {
        "symbol": "KC=F",
        "name": "Coffee Futures (Kopi)",
        "category": "Komoditas",
        "currency": "USD",
        "lotSize": 1,
        "price": 255
    },
    {
        "symbol": "SB=F",
        "name": "Sugar Futures (Gula)",
        "category": "Komoditas",
        "currency": "USD",
        "lotSize": 1,
        "price": 22.4
    },
    {
        "symbol": "CC=F",
        "name": "Cocoa Futures (Kakao)",
        "category": "Komoditas",
        "currency": "USD",
        "lotSize": 1,
        "price": 7850
    },
    {
        "symbol": "CT=F",
        "name": "Cotton Futures (Kapas)",
        "category": "Komoditas",
        "currency": "USD",
        "lotSize": 1,
        "price": 72.8
    },
    {
        "symbol": "FCPO=F",
        "name": "Crude Palm Oil (CPO Sawit)",
        "category": "Komoditas",
        "currency": "USD",
        "lotSize": 1,
        "price": 980
    }
];

const FOREX_ASSETS = [
    {
        "symbol": "USDIDR=X",
        "name": "US Dollar / Indonesian Rupiah",
        "category": "Forex",
        "currency": "IDR",
        "price": 16250
    },
    {
        "symbol": "EURUSD=X",
        "name": "Euro / US Dollar",
        "category": "Forex",
        "currency": "USD",
        "price": 1.085
    },
    {
        "symbol": "USDJPY=X",
        "name": "US Dollar / Japanese Yen",
        "category": "Forex",
        "currency": "USD",
        "price": 152.4
    },
    {
        "symbol": "GBPUSD=X",
        "name": "British Pound / US Dollar",
        "category": "Forex",
        "currency": "USD",
        "price": 1.298
    },
    {
        "symbol": "AUDUSD=X",
        "name": "Australian Dollar / US Dollar",
        "category": "Forex",
        "currency": "USD",
        "price": 0.665
    },
    {
        "symbol": "USDCAD=X",
        "name": "US Dollar / Canadian Dollar",
        "category": "Forex",
        "currency": "USD",
        "price": 1.385
    },
    {
        "symbol": "USDCHF=X",
        "name": "US Dollar / Swiss Franc",
        "category": "Forex",
        "currency": "USD",
        "price": 0.865
    },
    {
        "symbol": "NZDUSD=X",
        "name": "New Zealand Dollar / US Dollar",
        "category": "Forex",
        "currency": "USD",
        "price": 0.602
    },
    {
        "symbol": "EURIDR=X",
        "name": "Euro / Indonesian Rupiah",
        "category": "Forex",
        "currency": "IDR",
        "price": 17650
    },
    {
        "symbol": "SGDIDR=X",
        "name": "Singapore Dollar / Indonesian Rupiah",
        "category": "Forex",
        "currency": "IDR",
        "price": 12380
    },
    {
        "symbol": "MYRIDR=X",
        "name": "Malaysian Ringgit / Indonesian Rupiah",
        "category": "Forex",
        "currency": "IDR",
        "price": 3750
    },
    {
        "symbol": "CNYIDR=X",
        "name": "Chinese Yuan / Indonesian Rupiah",
        "category": "Forex",
        "currency": "IDR",
        "price": 2280
    },
    {
        "symbol": "JPYIDR=X",
        "name": "Japanese Yen (100) / Rupiah",
        "category": "Forex",
        "currency": "IDR",
        "price": 10650
    },
    {
        "symbol": "GBPIDR=X",
        "name": "British Pound / Rupiah",
        "category": "Forex",
        "currency": "IDR",
        "price": 21100
    },
    {
        "symbol": "AUDIDR=X",
        "name": "Australian Dollar / Rupiah",
        "category": "Forex",
        "currency": "IDR",
        "price": 10820
    }
];

const INDEX_ASSETS = [
    {
        "symbol": "^JKSE",
        "name": "IHSG Composite Jakarta",
        "category": "Index",
        "currency": "IDR",
        "price": 6480
    },
    {
        "symbol": "^GSPC",
        "name": "S&P 500 Index",
        "category": "Index",
        "currency": "USD",
        "price": 5815
    },
    {
        "symbol": "^IXIC",
        "name": "Nasdaq Composite",
        "category": "Index",
        "currency": "USD",
        "price": 18450
    },
    {
        "symbol": "^DJI",
        "name": "Dow Jones Industrial",
        "category": "Index",
        "currency": "USD",
        "price": 42800
    },
    {
        "symbol": "^N225",
        "name": "Nikkei 225 Tokyo",
        "category": "Index",
        "currency": "USD",
        "price": 38900
    },
    {
        "symbol": "^HSI",
        "name": "Hang Seng Index Hong Kong",
        "category": "Index",
        "currency": "USD",
        "price": 20600
    },
    {
        "symbol": "^FTSE",
        "name": "FTSE 100 London",
        "category": "Index",
        "currency": "USD",
        "price": 8250
    },
    {
        "symbol": "^GDAXI",
        "name": "DAX Frankfurt",
        "category": "Index",
        "currency": "USD",
        "price": 19500
    },
    {
        "symbol": "DX-Y.NYB",
        "name": "US Dollar Index (DXY)",
        "category": "Index",
        "currency": "USD",
        "price": 104.2
    },
    {
        "symbol": "^TNX",
        "name": "US 10Y Treasury Yield",
        "category": "Rates",
        "currency": "USD",
        "price": 4.25
    },
    {
        "symbol": "^VIX",
        "name": "CBOE Volatility VIX",
        "category": "Rates",
        "currency": "USD",
        "price": 15.5
    }
];

const ALL_UNIVERSE = [
    ...SPACE_TECH_ASSETS,
    ...HOT_IPO_ASSETS,
    ...IDX_FULL_ASSETS,
    ...US_GLOBAL_ASSETS,
    ...CRYPTO_ASSETS,
    ...COMMODITY_ASSETS,
    ...FOREX_ASSETS,
    ...INDEX_ASSETS
];

const MACRO_MICRO_DATA = {
    "indonesia": {
        "biRate": "6.00%",
        "biRateChange": "0.00%",
        "inflationYoY": "2.12%",
        "inflationMoM": "0.08%",
        "gdpGrowthYoY": "5.05%",
        "foreignReserves": "$150.2B",
        "tradeBalance": "+$2.9B Surplus",
        "debtToGdp": "38.6%",
        "currAccountDeficit": "-0.9% of GDP",
        "tenYearYield": "6.68%",
        "jisdorFx": "Rp 16,250"
    },
    "global": {
        "fedRate": "4.75% - 5.00%",
        "fedRateExpectation": "Cut 25bps in Dec",
        "usCpiInflation": "3.2% YoY",
        "usGdpAnnualized": "2.8%",
        "usUnemployment": "4.1%",
        "us10YYield": "4.25%",
        "us2YYield": "4.15%",
        "yieldCurveSpread": "+10 bps (Uninverted)",
        "dxyIndex": "104.20",
        "brentCrude": "$75.20 / bbl",
        "globalGdpGrowth": "3.1% IMF Forecast"
    },
    "microKeyMetrics": [
        {
            "symbol": "BBCA.JK",
            "name": "Bank Central Asia",
            "pe": 21.4,
            "pbv": 4.8,
            "roe": "22.8%",
            "divYield": "2.8%",
            "mktCapIdr": "1,120 T"
        },
        {
            "symbol": "BBRI.JK",
            "name": "Bank Rakyat Indonesia",
            "pe": 11.2,
            "pbv": 2.1,
            "roe": "18.9%",
            "divYield": "6.4%",
            "mktCapIdr": "680 T"
        },
        {
            "symbol": "BMRI.JK",
            "name": "Bank Mandiri",
            "pe": 10.8,
            "pbv": 2.2,
            "roe": "20.1%",
            "divYield": "5.6%",
            "mktCapIdr": "595 T"
        },
        {
            "symbol": "TLKM.JK",
            "name": "Telkom Indonesia",
            "pe": 14.5,
            "pbv": 2.4,
            "roe": "16.5%",
            "divYield": "5.8%",
            "mktCapIdr": "264 T"
        },
        {
            "symbol": "ASII.JK",
            "name": "Astra International",
            "pe": 7.2,
            "pbv": 1.05,
            "roe": "15.2%",
            "divYield": "8.4%",
            "mktCapIdr": "198 T"
        },
        {
            "symbol": "BREN.JK",
            "name": "Barito Renewables Energy",
            "pe": 125,
            "pbv": 48,
            "roe": "38.4%",
            "divYield": "0.4%",
            "mktCapIdr": "915 T"
        },
        {
            "symbol": "CUAN.JK",
            "name": "Petrindo Jaya Kreasi",
            "pe": 95,
            "pbv": 22,
            "roe": "23.0%",
            "divYield": "0.5%",
            "mktCapIdr": "88 T"
        },
        {
            "symbol": "AMMN.JK",
            "name": "Amman Mineral",
            "pe": 34,
            "pbv": 6.8,
            "roe": "20.0%",
            "divYield": "0.8%",
            "mktCapIdr": "648 T"
        },
        {
            "symbol": "NVDA",
            "name": "NVIDIA Corp",
            "pe": 58.2,
            "pbv": 48.5,
            "roe": "115.0%",
            "divYield": "0.03%",
            "mktCapUsd": "$3.52 T"
        },
        {
            "symbol": "AAPL",
            "name": "Apple Inc",
            "pe": 34.8,
            "pbv": 45,
            "roe": "148.0%",
            "divYield": "0.45%",
            "mktCapUsd": "$3.45 T"
        },
        {
            "symbol": "MSFT",
            "name": "Microsoft Corp",
            "pe": 35.2,
            "pbv": 12.8,
            "roe": "38.5%",
            "divYield": "0.75%",
            "mktCapUsd": "$3.18 T"
        },
        {
            "symbol": "SPACEX",
            "name": "SpaceX (Pre-IPO)",
            "pe": 85,
            "pbv": 18.5,
            "roe": "21.5%",
            "divYield": "0.00%",
            "mktCapUsd": "$210.0 B"
        }
    ]
};

module.exports = {
    ALL_UNIVERSE,
    SPACE_TECH_ASSETS,
    HOT_IPO_ASSETS,
    IDX_FULL_ASSETS,
    US_GLOBAL_ASSETS,
    CRYPTO_ASSETS,
    COMMODITY_ASSETS,
    FOREX_ASSETS,
    INDEX_ASSETS,
    MACRO_MICRO_DATA
};
