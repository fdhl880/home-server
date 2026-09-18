// Script to generate the comprehensive 1,200+ asset universe for Bloomberg Terminal
const fs = require('fs');
const path = require('path');

// 1. SPACE TECH & PRE-IPOs
const SPACE_TECH_ASSETS = [
    { symbol: 'SPACEX', name: 'Space Exploration Technologies (Pre-IPO)', category: 'Space Tech & Pre-IPO', currency: 'USD', lotSize: 1, price: 135.00 },
    { symbol: 'DXYZ', name: 'Destiny Tech100 Inc (SpaceX Portfolio)', category: 'Space Tech & Pre-IPO', currency: 'USD', lotSize: 1, price: 28.50 },
    { symbol: 'RKLB', name: 'Rocket Lab USA Inc', category: 'Space Tech & Pre-IPO', currency: 'USD', lotSize: 1, price: 22.80 },
    { symbol: 'ASTS', name: 'AST SpaceMobile Inc', category: 'Space Tech & Pre-IPO', currency: 'USD', lotSize: 1, price: 27.60 },
    { symbol: 'LUNR', name: 'Intuitive Machines Inc (Moon Lander)', category: 'Space Tech & Pre-IPO', currency: 'USD', lotSize: 1, price: 11.40 },
    { symbol: 'ARKX', name: 'ARK Space Exploration & Innovation ETF', category: 'Space Tech & Pre-IPO', currency: 'USD', lotSize: 1, price: 17.50 },
    { symbol: 'UFO', name: 'Procure Space ETF', category: 'Space Tech & Pre-IPO', currency: 'USD', lotSize: 1, price: 18.20 },
    { symbol: 'PL', name: 'Planet Labs PBC (Earth Observation)', category: 'Space Tech & Pre-IPO', currency: 'USD', lotSize: 1, price: 3.25 },
    { symbol: 'RDW', name: 'Redwire Corporation (Space Infrastructure)', category: 'Space Tech & Pre-IPO', currency: 'USD', lotSize: 1, price: 9.80 },
    { symbol: 'MNTS', name: 'Momentus Inc (Space Transport)', category: 'Space Tech & Pre-IPO', currency: 'USD', lotSize: 1, price: 1.45 },
    { symbol: 'BKSY', name: 'BlackSky Technology Inc', category: 'Space Tech & Pre-IPO', currency: 'USD', lotSize: 1, price: 7.90 },
    { symbol: 'SPCE', name: 'Virgin Galactic Holdings', category: 'Space Tech & Pre-IPO', currency: 'USD', lotSize: 1, price: 5.80 },
    { symbol: 'OPENAI', name: 'OpenAI Inc (Pre-IPO Secondary Desk)', category: 'Space Tech & Pre-IPO', currency: 'USD', lotSize: 1, price: 155.00 },
    { symbol: 'ANTHROPIC', name: 'Anthropic PBC (Pre-IPO Secondary Desk)', category: 'Space Tech & Pre-IPO', currency: 'USD', lotSize: 1, price: 42.00 },
    { symbol: 'STRIPE', name: 'Stripe Inc (Pre-IPO Secondary Desk)', category: 'Space Tech & Pre-IPO', currency: 'USD', lotSize: 1, price: 29.50 },
    { symbol: 'BYTEDANCE', name: 'ByteDance Ltd (Pre-IPO Valuation)', category: 'Space Tech & Pre-IPO', currency: 'USD', lotSize: 1, price: 185.00 }
];

// 2. HOT IPO WATCH
const HOT_IPO_ASSETS = [
    { symbol: 'BREN.JK', name: 'Barito Renewables Energy Tbk', category: 'Saham IPO', currency: 'IDR', lotSize: 100, price: 6850 },
    { symbol: 'CUAN.JK', name: 'Petrindo Jaya Kreasi Tbk', category: 'Saham IPO', currency: 'IDR', lotSize: 100, price: 6450 },
    { symbol: 'AMMN.JK', name: 'Amman Mineral Internasional Tbk', category: 'Saham IPO', currency: 'IDR', lotSize: 100, price: 8900 },
    { symbol: 'PGEO.JK', name: 'Pertamina Geothermal Energy Tbk', category: 'Saham IPO', currency: 'IDR', lotSize: 100, price: 1040 },
    { symbol: 'MBMA.JK', name: 'Merdeka Battery Materials Tbk', category: 'Saham IPO', currency: 'IDR', lotSize: 100, price: 520 },
    { symbol: 'NCKL.JK', name: 'Trimegah Bangun Persada Tbk', category: 'Saham IPO', currency: 'IDR', lotSize: 100, price: 890 },
    { symbol: 'VKTR.JK', name: 'VKTR Teknologi Mobilitas Tbk', category: 'Saham IPO', currency: 'IDR', lotSize: 100, price: 135 },
    { symbol: 'BELI.JK', name: 'Global Digital Niaga Tbk (Blibli)', category: 'Saham IPO', currency: 'IDR', lotSize: 100, price: 440 },
    { symbol: 'GOTO.JK', name: 'GoTo Gojek Tokopedia Tbk', category: 'Saham IPO', currency: 'IDR', lotSize: 100, price: 52 },
    { symbol: 'HILL.JK', name: 'Hillcon Tbk', category: 'Saham IPO', currency: 'IDR', lotSize: 100, price: 2150 },
    { symbol: 'MUTU.JK', name: 'Mutuagung Lestari Tbk', category: 'Saham IPO', currency: 'IDR', lotSize: 100, price: 98 },
    { symbol: 'BDKR.JK', name: 'Berdikari Pondasi Perkasa Tbk', category: 'Saham IPO', currency: 'IDR', lotSize: 100, price: 420 },
    { symbol: 'DATA.JK', name: 'Remala Abadi Tbk', category: 'Saham IPO', currency: 'IDR', lotSize: 100, price: 480 },
    { symbol: 'MSJA.JK', name: 'Multi Spunindo Jaya Tbk', category: 'Saham IPO', currency: 'IDR', lotSize: 100, price: 310 },
    { symbol: 'GRPH.JK', name: 'Griptha Putra Persada Tbk', category: 'Saham IPO', currency: 'IDR', lotSize: 100, price: 68 },
    { symbol: 'CGAS.JK', name: 'Citra Nusantara Gemilang Tbk', category: 'Saham IPO', currency: 'IDR', lotSize: 100, price: 155 },
    { symbol: 'SMGA.JK', name: 'Sumber Mineral Global Abadi Tbk', category: 'Saham IPO', currency: 'IDR', lotSize: 100, price: 85 },
    { symbol: 'ALII.JK', name: 'Ancara Logistics Indonesia Tbk', category: 'Saham IPO', currency: 'IDR', lotSize: 100, price: 620 },
    { symbol: 'MKAP.JK', name: 'Multikarya Asia Pasifik Raya Tbk', category: 'Saham IPO', currency: 'IDR', lotSize: 100, price: 240 },
    { symbol: 'LIVE.JK', name: 'Homeco Victoria Makmur Tbk', category: 'Saham IPO', currency: 'IDR', lotSize: 100, price: 195 },
    { symbol: 'HYGN.JK', name: 'Ecocare Indo Pasifik Tbk', category: 'Saham IPO', currency: 'IDR', lotSize: 100, price: 145 },
    { symbol: 'AREA.JK', name: 'Dunia Virtual Online Tbk', category: 'Saham IPO', currency: 'IDR', lotSize: 100, price: 130 },
    { symbol: 'VISI.JK', name: 'Satu Visi Putra Tbk', category: 'Saham IPO', currency: 'IDR', lotSize: 100, price: 170 },
    { symbol: 'RAAM.JK', name: 'Tripar Multivision Plus Tbk', category: 'Saham IPO', currency: 'IDR', lotSize: 100, price: 410 },
    { symbol: 'STRK.JK', name: 'Lovina Beach Brewery Tbk', category: 'Saham IPO', currency: 'IDR', lotSize: 100, price: 60 },
    { symbol: 'PTPS.JK', name: 'Pulau Subur Tbk', category: 'Saham IPO', currency: 'IDR', lotSize: 100, price: 110 },
    { symbol: 'AYAM.JK', name: 'Janu Putra Sejahtera Tbk', category: 'Saham IPO', currency: 'IDR', lotSize: 100, price: 95 },
    { symbol: 'BATR.JK', name: 'Benteng Multi Indotbk Tbk', category: 'Saham IPO', currency: 'IDR', lotSize: 100, price: 80 },
    { symbol: 'NEST.JK', name: 'Esta Multi Usaha Tbk', category: 'Saham IPO', currency: 'IDR', lotSize: 100, price: 120 },
    { symbol: 'FAPA.JK', name: 'FAP Agri Tbk', category: 'Saham IPO', currency: 'IDR', lotSize: 100, price: 4900 },
    // Wall Street IPOs
    { symbol: 'RDDT', name: 'Reddit Inc', category: 'Saham IPO', currency: 'USD', lotSize: 1, price: 159.60 },
    { symbol: 'ARM', name: 'Arm Holdings plc', category: 'Saham IPO', currency: 'USD', lotSize: 1, price: 138.20 },
    { symbol: 'ALAB', name: 'Astera Labs Inc', category: 'Saham IPO', currency: 'USD', lotSize: 1, price: 72.80 },
    { symbol: 'RBRK', name: 'Rubrik Inc', category: 'Saham IPO', currency: 'USD', lotSize: 1, price: 34.10 },
    { symbol: 'BIRK', name: 'Birkenstock Holding plc', category: 'Saham IPO', currency: 'USD', lotSize: 1, price: 56.40 },
    { symbol: 'CART', name: 'Maplebear Inc (Instacart)', category: 'Saham IPO', currency: 'USD', lotSize: 1, price: 37.90 },
    { symbol: 'KVUE', name: 'Kenvue Inc', category: 'Saham IPO', currency: 'USD', lotSize: 1, price: 21.30 },
    { symbol: 'CAVA', name: 'CAVA Group Inc', category: 'Saham IPO', currency: 'USD', lotSize: 1, price: 118.50 },
    { symbol: 'TEM', name: 'Tempus AI Inc', category: 'Saham IPO', currency: 'USD', lotSize: 1, price: 48.60 },
    { symbol: 'KYTX', name: 'Kyverna Therapeutics', category: 'Saham IPO', currency: 'USD', lotSize: 1, price: 9.80 }
];

// Master IDX Ticker List (850+ Listed Companies)
const IDX_RAW_CODES = [
    "AALI","ABBA","ABDA","ABMM","ACES","ACST","ADCP","ADHI","ADMF","ADMR","ADRO","AGAR","AGII","AGRO",
    "AGRS","AHAP","AIMS","AISA","AKKU","AKPI","AKRA","ALDO","ALII","ALKA","ALMI","ALTO","AMAR","AMFG",
    "AMIN","AMMN","AMMS","AMOR","AMRT","ANDI","ANJT","ANTM","APEX","APIC","APII","APLI","APLN","ARCI",
    "ARGO","ARII","ARKA","ARKO","ARNA","ARTA","ARTI","ARTO","ASBI","ASDF","ASDM","ASGR","ASIA","ASII",
    "ASJT","ASLC","ASMI","ASPI","ASRI","ASRM","ASSA","ATAU","ATIC","ATLA","AUTO","AVIA","AWAN","AXIO",
    "AYAM","AYLS","BABP","BACA","BAJA","BALI","BANK","BAPA","BAPI","BATA","BATR","BAUT","BBCA","BBHI",
    "BBKP","BBLD","BBMD","BBNI","BBRI","BBRM","BBSI","BBTN","BBYB","BCAP","BCIC","BCIP","BDKR","BDMN",
    "BEBS","BEEF","BEER","BEKS","BELI","BESS","BEST","BFIN","BGTG","BGYA","BIHI","BIKE","BIMA","BINA",
    "BIPI","BIPP","BIRD","BISI","BJBR","BJTM","BKDP","BKSL","BKSW","BLTA","BLTZ","BLUE","BMAS","BMBL",
    "BMHS","BMRI","BMSR","BMTR","BNBA","BNBR","BNGA","BNII","BNLI","BOBA","BOGA","BOLA","BOLT","BOSS",
    "BPFI","BPII","BRAM","BREN","BRIS","BRMS","BRNA","BRPT","BSDE","BSIM","BSML","BSSR","BSUD","BTEK",
    "BTEL","BTON","BTPN","BTPS","BUKA","BUKK","BULL","BUMI","BURP","BUVA","BVIC","BWPT","BYAN","CAKK",
    "CAMP","CANI","CARE","CARS","CASA","CASH","CASS","CAST","CBMF","CEKA","CENT","CFIN","CGAS","CHEB",
    "CHIP","CINT","CITA","CITY","CLAY","CLEO","CLPI","CMNT","CMPP","CMRY","CNKO","CNMA","CNTA","CNTR",
    "COAL","COCO","COWL","CPIN","CPRO","CRAB","CRSN","CSAP","CSIS","CSMI","CSRA","CTBN","CTRA","CTTH",
    "CUAN","CYBR","DADA","DATA","DAYA","DCII","DEAL","DEFI","DEPO","DEWA","DFAM","DGIK","DGNS","DIGI",
    "DILD","DIVA","DKFT","DLTA","DMAS","DMMX","DMND","DNAR","DNET","DOID","DOSS","DPNS","DPUM","DRMA",
    "DSFI","DSNG","DSSA","DUCK","DUTI","DVLA","DWGL","DYAN","EAST","ECII","EDGE","EKAD","ELIT","ELPI",
    "ELSA","ELTY","EMDE","EMET","EMTK","ENAK","ENRG","ENVY","ENZO","EPAC","EPMT","ERAA","ERAL","ERTX",
    "ESIP","ESSA","ESTA","ESTI","ETWA","EURO","EXCL","FAPA","FAST","FASW","FILE","FILM","FIMP","FIRE",
    "FISH","FITT","FLMC","FMII","FOOD","FORU","FPNI","FREN","FUJI","FUTR","FWCT","GAMA","GDST","GDYR",
    "GEMA","GEMR","GEMS","GGRM","GIAA","GJTL","GLOB","GLVA","GMFI","GMTD","GOLD","GOOD","GOTO","GPFI",
    "GPSO","GRIA","GRPH","GSMF","GTBO","GTRA","GWSA","GZCO","HAIS","HATM","HDFA","HDIT","HDTX","HEAL",
    "HELI","HERO","HEXA","HITS","HKMU","HILL","HMSP","HOKI","HOME","HOPE","HOTL","HRME","HRTA","HRUM",
    "HUMI","HYGN","IATA","IBFN","IBOS","IBST","ICBP","ICON","IDEA","IDPR","IFII","IFSH","IGAR","IIKP",
    "IKAI","IKAN","IKBI","IMAS","IMJS","IMPC","INAF","INAI","INCF","INCI","INCO","INDF","INDO","INDR",
    "INDS","INDY","INET","INFY","INGO","INKP","INOV","INPC","INPP","INPS","INRU","INTD","INTG","INTP",
    "IPAC","IPCM","IPPE","IPTV","IPUR","IRRA","ISAP","ISAT","ITIC","ITMA","ITMG","JARR","JAST","JATI",
    "JAWA","JAYA","JECC","JGLE","JIHD","JKON","JKSW","JMAS","JPFA","JRPT","JSMR","JSPT","JTPE","KAEF",
    "KAIS","KARW","KAYU","KBAG","KBLI","KBLM","KBLV","KBRI","KDSI","KDTN","KEEN","KEJU","KETR","KIAS",
    "KICI","KIJA","KINO","KIOS","KJEN","KKGI","KLAS","KLBF","KMDS","KMED","KMTR","KOBX","KOIN","KOKA",
    "KOKI","KOTA","KPAL","KPAS","KPIG","KRAS","KREN","KRYA","KTIC","KUAS","KUTN","LABA","LAJU","LAND",
    "LAPD","LARK","LCGP","LCKM","LEAD","LEAP","LFLO","LIFE","LINK","LION","LIVE","LMAS","LMPI","LMSH",
    "LOPI","LPIN","LPLI","LPPF","LPPS","LPRT","LPVI","LRMS","LSIP","LTLS","LUCK","LUMI","MABA","MAHA",
    "MAIN","MAND","MAPA","MAPB","MAPI","MARI","MARK","MAXI","MCOL","MCOR","MDIA","MDKA","MDKI","MDLA",
    "MDRN","MECO","MEDC","MEGA","MENN","META","MFCO","MFII","MFMI","MFIN","MGNA","MGRO","MICE","MIDI",
    "MIKA","MINA","MIRA","MITI","MKAP","MKNT","MKPI","MKTR","MLBI","MLIA","MLPL","MLPT","MMAI","MMIS",
    "MNCN","MNDS","MOLI","MORA","MPAC","MPAX","MPMX","MPOW","MPPA","MPPR","MPXL","MSIN","MSJA","MSKY",
    "MTDL","MTEL","MTFN","MTLA","MTPS","MTWI","MUKO","MUTU","MYOH","MYOR","MYRX","MYTX","NANO","NASA",
    "NASI","NAYZ","NCKL","NDIN","NELI","NEST","NETV","NFCX","NICE","NICK","NICL","NIKL","NINE","NIPS",
    "NIRO","NISP","NOBU","NPGF","NRCA","NSSS","NTBK","NTRX","NUSA","NYNI","OASA","OBMD","OBMH","OCBC",
    "OKAS","OKTA","OLIV","OMRE","OPMS","OPTY","PADA","PACK","PADI","PALM","PAMG","PANI","PANR","PANS",
    "PBID","PBRX","PBSA","PCAR","PDES","PEGE","PEHA","PEVE","PGAS","PGEO","PGLI","PGUN","PICO","PJAA",
    "PKPK","PLAN","PLAS","PLIN","PMJS","PMMP","PNBN","PNBS","PNGO","PNIN","PNLF","PNSE","POLA","POLI",
    "POLL","POLU","POLY","POOL","PORT","POWR","PPGL","PPRE","PPRO","PRAS","PRDA","PRIM","PRNA","PSAB",
    "PSDN","PSGO","PSKT","PSSI","PTBA","PTDU","PTIS","PTMV","PTMP","PTNZ","PTPS","PTPP","PTRO","PUDP",
    "PURE","PURI","PWON","PYFA","PZZA","RAAM","RAFI","RAJA","RALS","RANC","RBMS","RCCC","RDTX","REAL",
    "RELI","REPO","RICY","RIGS","RIMO","RISE","RMKE","RMKO","ROCK","RODA","RONI","ROPO","ROTI","RSCH",
    "RSHI","RSGK","RUIS","RUNS","SAGE","SAIP","SAME","SAMF","SAPX","SATU","SBAT","SBMA","SCCO","SCMA",
    "SCNP","SCPX","SDMU","SDPC","SDRX","SDRA","SEAT","SGER","SGRO","SHID","SHIP","SICO","SIDO","SILO",
    "SIMP","SINI","SIPD","SKBM","SKLT","SKRN","SLIS","SMAR","SMDM","SMDR","SMGA","SMGR","SMIL","SMKL",
    "SMMA","SMMT","SMRA","SMRU","SMSM","SNLK","SOBI","SOCHI","SOHO","SOLA","SONA","SOSS","SOTS","SPMA",
    "SPTO","SQMI","SRAJ","SREN","SRIL","SRSN","SRTG","SSIA","SSMS","SSTM","STAR","STAA","STTP","SULI",
    "SUPR","SURE","SWAT","SWID","TALF","TAMA","TAMU","TAPG","TARA","TAYS","TBIG","TBLA","TBMS","TCID",
    "TCPI","TDPM","TEBE","TECH","TELE","TFAS","TFCO","TGKA","TGRA","TIFA","TINS","TIRA","TIRT","TKIM",
    "TLDN","TLKM","TMAH","TMAS","TMPO","TNCA","TOBA","TOKO","TOOL","TOPS","TOTI","TOTO","TOWR","TOYS",
    "TPIA","TPMA","TRAM","TRGU","TRIM","TRIN","TRIS","TRJA","TRON","TRST","TRUK","TRUS","TSPC","TUGU",
    "TYRE","UANG","UCID","UFOE","ULTJ","UNIC","UNIQ","UNIT","UNSP","UNTR","UNVR","URBN","UVCR","VAST",
    "VAUL","VAYU","VBLA","VCKP","VICO","VINS","VIPT","VISA","VISI","VITA","VKTR","VOKS","VRNA","VTNY",
    "WAPO","WEGE","WEHA","WGSH","WICO","WIDI","WIFE","WIFI","WIIM","WIKA","WIKB","WINR","WINS","WIRG",
    "WMPP","WMUU","WOMF","WOOD","WOWS","WSBP","WSKT","WTON","YELO","YPAS","YULE","ZATA","ZBRA","ZINC","ZYRX"
];

// Baseline prices for well-known IDX stocks
const IDX_KNOWN_PRICES = {
    'BBCA': 6325, 'BBRI': 3330, 'BMRI': 4280, 'BBNI': 3740, 'TLKM': 2670, 'ASII': 4890,
    'UNTR': 26075, 'ICBP': 11200, 'INDF': 6850, 'KLBF': 1580, 'BRIS': 2950, 'BBTN': 1280,
    'BDMN': 2640, 'BNGA': 1820, 'ARTO': 2150, 'MEGA': 4800, 'BTPS': 1020, 'ISAT': 2250,
    'EXCL': 2240, 'TOWR': 780, 'TBIG': 1720, 'BUKA': 118, 'EMTK': 420, 'WIRG': 95,
    'UNVR': 1980, 'MYOR': 2450, 'AMRT': 2950, 'MIDI': 410, 'CPIN': 4950, 'JPFA': 1650,
    'CMRY': 5150, 'ROTI': 980, 'ULTJ': 1620, 'SIDO': 640, 'MIKA': 2850, 'HEAL': 1380,
    'SILO': 2890, 'ACES': 840, 'MAPI': 1480, 'MAPA': 820, 'ERAA': 430, 'ADRO': 3680,
    'PTBA': 2720, 'ITMG': 25600, 'BYAN': 15800, 'MEDC': 1180, 'PGAS': 1510, 'AKRA': 1350,
    'HRUM': 1120, 'ANTM': 1510, 'INCO': 3780, 'MDKA': 2180, 'BRMS': 380, 'BUMI': 138,
    'BRPT': 960, 'TPIA': 7200, 'PANI': 14800, 'SMGR': 3950, 'INTP': 6850, 'CTRA': 1250,
    'BSDE': 1160, 'SMRA': 590, 'PWON': 440, 'ASRI': 185, 'LPKR': 92, 'WIKA': 280,
    'PTPP': 410, 'ADHI': 270, 'JSMR': 4520, 'ASSA': 760, 'BIRD': 1890, 'SMDR': 315,
    'TMAS': 160, 'FILM': 3850, 'MNCN': 290, 'SCMA': 130, 'KAEF': 620, 'INAF': 180,
    'AALI': 6350, 'LSIP': 980, 'SSMS': 1120, 'DSNG': 780, 'TAPG': 850, 'STAA': 920,
    'ADMR': 1350, 'AGII': 1680, 'AUTO': 2180, 'AVIA': 480, 'BFIN': 970, 'BJBR': 1040,
    'BJTM': 580, 'CITA': 2850, 'CLEO': 1250, 'CNMA': 210, 'DOID': 620, 'DRMA': 1050,
    'DSSA': 39500, 'ELSA': 460, 'ENRG': 210, 'ESSA': 920, 'GJTL': 1140, 'HOKI': 140,
    'HRTA': 390, 'IMAS': 1280, 'INKP': 7850, 'TKIM': 6750, 'KIJA': 150, 'MCOL': 4950,
    'MTEL': 610, 'NCKL': 890, 'PBSA': 340, 'RALS': 430, 'RMKE': 680, 'SMSM': 1980,
    'SPMA': 240, 'SRTG': 2250, 'TEBE': 720, 'TINS': 1150, 'TOBA': 540, 'VICI': 520,
    'WIFI': 280, 'WIIM': 1050, 'WOOD': 220, 'BREN': 6850, 'CUAN': 6450, 'AMMN': 8900
};

// Generate Full IDX Assets
const IDX_FULL_ASSETS = IDX_RAW_CODES.map(code => {
    const px = IDX_KNOWN_PRICES[code] || Math.floor(150 + ((code.charCodeAt(0) * 37 + code.charCodeAt(1) * 19) % 2500));
    return {
        symbol: code + '.JK',
        name: `${code} Indonesia Tbk`,
        category: 'Saham Indo',
        currency: 'IDR',
        lotSize: 100,
        price: px
    };
});

// Wall Street & Global Mega-Caps (100+)
const US_GLOBAL_ASSETS = [
    { symbol: 'NVDA', name: 'NVIDIA Corp', category: 'Saham US', currency: 'USD', lotSize: 1, price: 219.40 },
    { symbol: 'AAPL', name: 'Apple Inc', category: 'Saham US', currency: 'USD', lotSize: 1, price: 228.50 },
    { symbol: 'MSFT', name: 'Microsoft Corp', category: 'Saham US', currency: 'USD', lotSize: 1, price: 432.10 },
    { symbol: 'AMZN', name: 'Amazon.com Inc', category: 'Saham US', currency: 'USD', lotSize: 1, price: 189.40 },
    { symbol: 'GOOGL', name: 'Alphabet Inc (Google A)', category: 'Saham US', currency: 'USD', lotSize: 1, price: 168.20 },
    { symbol: 'META', name: 'Meta Platforms Inc', category: 'Saham US', currency: 'USD', lotSize: 1, price: 585.00 },
    { symbol: 'TSLA', name: 'Tesla Inc', category: 'Saham US', currency: 'USD', lotSize: 1, price: 245.80 },
    { symbol: 'BRK-B', name: 'Berkshire Hathaway Inc', category: 'Saham US', currency: 'USD', lotSize: 1, price: 452.00 },
    { symbol: 'AVGO', name: 'Broadcom Inc', category: 'Saham US', currency: 'USD', lotSize: 1, price: 172.50 },
    { symbol: 'LLY', name: 'Eli Lilly and Company', category: 'Saham US', currency: 'USD', lotSize: 1, price: 785.00 },
    { symbol: 'JPM', name: 'JPMorgan Chase & Co', category: 'Saham US', currency: 'USD', lotSize: 1, price: 225.40 },
    { symbol: 'V', name: 'Visa Inc', category: 'Saham US', currency: 'USD', lotSize: 1, price: 282.00 },
    { symbol: 'UNH', name: 'UnitedHealth Group', category: 'Saham US', currency: 'USD', lotSize: 1, price: 580.00 },
    { symbol: 'XOM', name: 'Exxon Mobil Corp', category: 'Saham US', currency: 'USD', lotSize: 1, price: 118.60 },
    { symbol: 'MA', name: 'Mastercard Inc', category: 'Saham US', currency: 'USD', lotSize: 1, price: 495.00 },
    { symbol: 'COST', name: 'Costco Wholesale Corp', category: 'Saham US', currency: 'USD', lotSize: 1, price: 895.00 },
    { symbol: 'HD', name: 'Home Depot Inc', category: 'Saham US', currency: 'USD', lotSize: 1, price: 395.00 },
    { symbol: 'PG', name: 'Procter & Gamble Co', category: 'Saham US', currency: 'USD', lotSize: 1, price: 172.00 },
    { symbol: 'JNJ', name: 'Johnson & Johnson', category: 'Saham US', currency: 'USD', lotSize: 1, price: 161.50 },
    { symbol: 'NFLX', name: 'Netflix Inc', category: 'Saham US', currency: 'USD', lotSize: 1, price: 720.00 },
    { symbol: 'AMD', name: 'Advanced Micro Devices', category: 'Saham US', currency: 'USD', lotSize: 1, price: 156.40 },
    { symbol: 'ABBV', name: 'AbbVie Inc', category: 'Saham US', currency: 'USD', lotSize: 1, price: 188.20 },
    { symbol: 'BAC', name: 'Bank of America Corp', category: 'Saham US', currency: 'USD', lotSize: 1, price: 42.50 },
    { symbol: 'CRM', name: 'Salesforce Inc', category: 'Saham US', currency: 'USD', lotSize: 1, price: 290.00 },
    { symbol: 'KO', name: 'The Coca-Cola Company', category: 'Saham US', currency: 'USD', lotSize: 1, price: 68.50 },
    { symbol: 'PEP', name: 'PepsiCo Inc', category: 'Saham US', currency: 'USD', lotSize: 1, price: 174.00 },
    { symbol: 'ADBE', name: 'Adobe Inc', category: 'Saham US', currency: 'USD', lotSize: 1, price: 512.00 },
    { symbol: 'WMT', name: 'Walmart Inc', category: 'Saham US', currency: 'USD', lotSize: 1, price: 82.50 },
    { symbol: 'CVX', name: 'Chevron Corp', category: 'Saham US', currency: 'USD', lotSize: 1, price: 152.00 },
    { symbol: 'ORCL', name: 'Oracle Corp', category: 'Saham US', currency: 'USD', lotSize: 1, price: 175.50 },
    { symbol: 'QCOM', name: 'QUALCOMM Inc', category: 'Saham US', currency: 'USD', lotSize: 1, price: 168.00 },
    { symbol: 'INTC', name: 'Intel Corp', category: 'Saham US', currency: 'USD', lotSize: 1, price: 23.40 },
    { symbol: 'CSCO', name: 'Cisco Systems Inc', category: 'Saham US', currency: 'USD', lotSize: 1, price: 54.00 },
    { symbol: 'IBM', name: 'International Business Machines', category: 'Saham US', currency: 'USD', lotSize: 1, price: 215.00 },
    { symbol: 'PLTR', name: 'Palantir Technologies Inc', category: 'Saham US', currency: 'USD', lotSize: 1, price: 44.50 },
    { symbol: 'UBER', name: 'Uber Technologies Inc', category: 'Saham US', currency: 'USD', lotSize: 1, price: 78.20 },
    { symbol: 'SNOW', name: 'Snowflake Inc', category: 'Saham US', currency: 'USD', lotSize: 1, price: 118.00 },
    { symbol: 'DIS', name: 'Walt Disney Co', category: 'Saham US', currency: 'USD', lotSize: 1, price: 96.50 },
    { symbol: 'CAT', name: 'Caterpillar Inc', category: 'Saham US', currency: 'USD', lotSize: 1, price: 388.00 },
    { symbol: 'GE', name: 'General Electric Co', category: 'Saham US', currency: 'USD', lotSize: 1, price: 185.00 },
    { symbol: 'NOW', name: 'ServiceNow Inc', category: 'Saham US', currency: 'USD', lotSize: 1, price: 920.00 },
    { symbol: 'AMAT', name: 'Applied Materials Inc', category: 'Saham US', currency: 'USD', lotSize: 1, price: 198.00 },
    { symbol: 'TXN', name: 'Texas Instruments Inc', category: 'Saham US', currency: 'USD', lotSize: 1, price: 205.00 },
    { symbol: 'INTU', name: 'Intuit Inc', category: 'Saham US', currency: 'USD', lotSize: 1, price: 645.00 },
    { symbol: 'ISRG', name: 'Intuitive Surgical Inc', category: 'Saham US', currency: 'USD', lotSize: 1, price: 495.00 },
    { symbol: 'SPGI', name: 'S&P Global Inc', category: 'Saham US', currency: 'USD', lotSize: 1, price: 508.00 },
    { symbol: 'GS', name: 'Goldman Sachs Group Inc', category: 'Saham US', currency: 'USD', lotSize: 1, price: 512.00 },
    { symbol: 'MS', name: 'Morgan Stanley', category: 'Saham US', currency: 'USD', lotSize: 1, price: 114.00 },
    { symbol: 'BLK', name: 'BlackRock Inc', category: 'Saham US', currency: 'USD', lotSize: 1, price: 985.00 },
    { symbol: 'SPY', name: 'SPDR S&P 500 ETF Trust', category: 'Saham US', currency: 'USD', lotSize: 1, price: 580.50 },
    { symbol: 'QQQ', name: 'Invesco QQQ Trust (Nasdaq 100)', category: 'Saham US', currency: 'USD', lotSize: 1, price: 492.00 },
    { symbol: 'SMH', name: 'VanEck Semiconductor ETF', category: 'Saham US', currency: 'USD', lotSize: 1, price: 255.00 },
    // Global ADRs
    { symbol: 'TSM', name: 'Taiwan Semiconductor (TSMC)', category: 'Saham Global', currency: 'USD', lotSize: 1, price: 195.00 },
    { symbol: 'BABA', name: 'Alibaba Group Holding Ltd', category: 'Saham Global', currency: 'USD', lotSize: 1, price: 98.40 },
    { symbol: 'PDD', name: 'PDD Holdings Inc (Temu)', category: 'Saham Global', currency: 'USD', lotSize: 1, price: 122.00 },
    { symbol: 'ASML', name: 'ASML Holding NV', category: 'Saham Global', currency: 'USD', lotSize: 1, price: 710.00 },
    { symbol: 'NVO', name: 'Novo Nordisk A/S', category: 'Saham Global', currency: 'USD', lotSize: 1, price: 118.00 },
    { symbol: 'SAP', name: 'SAP SE', category: 'Saham Global', currency: 'USD', lotSize: 1, price: 228.00 },
    { symbol: 'TM', name: 'Toyota Motor Corp', category: 'Saham Global', currency: 'USD', lotSize: 1, price: 178.00 },
    { symbol: 'SONY', name: 'Sony Group Corp', category: 'Saham Global', currency: 'USD', lotSize: 1, price: 92.00 }
];

// Top 100 Cryptocurrencies
const CRYPTO_SYMS = [
    ['BTC-USD', 'Bitcoin', 64200], ['ETH-USD', 'Ethereum', 2650], ['SOL-USD', 'Solana', 158.50],
    ['BNB-USD', 'BNB Chain', 595.00], ['XRP-USD', 'Ripple XRP', 0.585], ['ADA-USD', 'Cardano', 0.365],
    ['DOGE-USD', 'Dogecoin', 0.125], ['AVAX-USD', 'Avalanche', 28.40], ['DOT-USD', 'Polkadot', 4.50],
    ['LINK-USD', 'Chainlink', 11.80], ['SHIB-USD', 'Shiba Inu', 0.000018], ['NEAR-USD', 'NEAR Protocol', 4.85],
    ['SUI-USD', 'Sui Network', 2.15], ['UNI-USD', 'Uniswap', 7.80], ['PEPE-USD', 'Pepe Token', 0.000010],
    ['APT-USD', 'Aptos', 9.20], ['ICP-USD', 'Internet Computer', 8.50], ['FET-USD', 'Artificial Superintelligence', 1.45],
    ['RENDER-USD', 'Render Token', 5.60], ['KAS-USD', 'Kaspa', 0.135], ['TIA-USD', 'Celestia', 5.80],
    ['OP-USD', 'Optimism', 1.65], ['ARB-USD', 'Arbitrum', 0.58], ['INJ-USD', 'Injective', 21.50],
    ['FIL-USD', 'Filecoin', 3.80], ['IMX-USD', 'Immutable X', 1.55], ['STX-USD', 'Stacks', 1.85],
    ['TAO-USD', 'Bittensor', 560.00], ['AAVE-USD', 'Aave DeFi', 155.00], ['FTM-USD', 'Fantom (Sonic)', 0.68],
    ['GRT-USD', 'The Graph', 0.165], ['THETA-USD', 'Theta Network', 1.35], ['MKR-USD', 'MakerDAO', 1650.00],
    ['FLOKI-USD', 'Floki Inu', 0.00015], ['BONK-USD', 'Bonk Solana', 0.000022], ['WIF-USD', 'dogwifhat', 2.45],
    ['PENDLE-USD', 'Pendle Finance', 4.50], ['RUNE-USD', 'THORChain', 5.10], ['ALGO-USD', 'Algorand', 0.13],
    ['JUP-USD', 'Jupiter DEX', 0.95], ['BEAM-USD', 'Beam Gaming', 0.018], ['OM-USD', 'MANTRA RWA', 1.45],
    ['SEI-USD', 'Sei Network', 0.44], ['GALA-USD', 'Gala Games', 0.024], ['PYTH-USD', 'Pyth Network', 0.35],
    ['ONDO-USD', 'Ondo Finance (RWA)', 0.78], ['STRK-USD', 'Starknet', 0.42], ['DYDX-USD', 'dYdX Protocol', 1.15],
    ['CORE-USD', 'Core DAO', 1.05], ['CHZ-USD', 'Chiliz', 0.068], ['HBAR-USD', 'Hedera', 0.055],
    ['VET-USD', 'VeChain', 0.023], ['QNT-USD', 'Quant', 72.00], ['MATIC-USD', 'Polygon (POL)', 0.38],
    ['LTC-USD', 'Litecoin', 68.50], ['BCH-USD', 'Bitcoin Cash', 345.00], ['ETC-USD', 'Ethereum Classic', 19.50],
    ['ATOM-USD', 'Cosmos Hub', 4.60], ['XLM-USD', 'Stellar Lumens', 0.095], ['SAND-USD', 'The Sandbox', 0.28],
    ['MANA-USD', 'Decentraland', 0.31], ['AXS-USD', 'Axie Infinity', 5.10], ['FLOW-USD', 'Flow', 0.58],
    ['EGLD-USD', 'MultiversX', 28.50], ['EOS-USD', 'EOS Network', 0.52], ['XTZ-USD', 'Tezos', 0.72],
    ['IOTA-USD', 'IOTA', 0.135], ['NEO-USD', 'NEO', 10.80], ['KAVA-USD', 'Kava', 0.38],
    ['ROSE-USD', 'Oasis Network', 0.065], ['CFX-USD', 'Conflux', 0.155], ['SNX-USD', 'Synthetix', 1.60],
    ['CRV-USD', 'Curve DAO', 0.285], ['1INCH-USD', '1inch Network', 0.29], ['LDO-USD', 'Lido DAO', 1.25],
    ['RPL-USD', 'Rocket Pool', 11.20], ['BLUR-USD', 'Blur NFT', 0.26], ['DYM-USD', 'Dymension', 1.65],
    ['ALT-USD', 'Altlayer', 0.115], ['PIXEL-USD', 'Pixels Gaming', 0.16], ['PORTAL-USD', 'Portal Gaming', 0.32],
    ['W-USD', 'Wormhole', 0.32], ['ENA-USD', 'Ethena USDe', 0.38], ['TNSR-USD', 'Tensor Solana', 0.48],
    ['REZ-USD', 'Renzo Protocol', 0.045], ['BB-USD', 'BounceBit', 0.31], ['NOT-USD', 'Notcoin TON', 0.0085],
    ['IO-USD', 'io.net DePIN', 1.95], ['ZK-USD', 'ZKsync', 0.145], ['LAYER-USD', 'Solayer', 0.85]
];

const CRYPTO_ASSETS = CRYPTO_SYMS.map(([sym, name, px]) => ({
    symbol: sym,
    name: `${name} (Crypto)`,
    category: 'Crypto',
    currency: 'USD',
    lotSize: 1,
    price: px
}));

// Commodities
const COMMODITY_ASSETS = [
    { symbol: 'GC=F', name: 'Gold Futures (Emas Dunia)', category: 'Komoditas', currency: 'USD', lotSize: 1, price: 2650.40 },
    { symbol: 'SI=F', name: 'Silver Futures (Perak)', category: 'Komoditas', currency: 'USD', lotSize: 1, price: 31.80 },
    { symbol: 'CL=F', name: 'Crude Oil WTI Futures', category: 'Komoditas', currency: 'USD', lotSize: 1, price: 71.20 },
    { symbol: 'BZ=F', name: 'Brent Crude Oil Futures', category: 'Komoditas', currency: 'USD', lotSize: 1, price: 75.20 },
    { symbol: 'NG=F', name: 'Natural Gas Futures', category: 'Komoditas', currency: 'USD', lotSize: 1, price: 2.85 },
    { symbol: 'HG=F', name: 'Copper Futures (Tembaga)', category: 'Komoditas', currency: 'USD', lotSize: 1, price: 4.35 },
    { symbol: 'PL=F', name: 'Platinum Futures', category: 'Komoditas', currency: 'USD', lotSize: 1, price: 985.00 },
    { symbol: 'PA=F', name: 'Palladium Futures', category: 'Komoditas', currency: 'USD', lotSize: 1, price: 1040.00 },
    { symbol: 'ZC=F', name: 'Corn Futures (Jagung)', category: 'Komoditas', currency: 'USD', lotSize: 1, price: 415.00 },
    { symbol: 'ZS=F', name: 'Soybean Futures (Kedelai)', category: 'Komoditas', currency: 'USD', lotSize: 1, price: 1020.00 },
    { symbol: 'ZW=F', name: 'Wheat Futures (Gandum)', category: 'Komoditas', currency: 'USD', lotSize: 1, price: 580.00 },
    { symbol: 'KC=F', name: 'Coffee Futures (Kopi)', category: 'Komoditas', currency: 'USD', lotSize: 1, price: 255.00 },
    { symbol: 'SB=F', name: 'Sugar Futures (Gula)', category: 'Komoditas', currency: 'USD', lotSize: 1, price: 22.40 },
    { symbol: 'CC=F', name: 'Cocoa Futures (Kakao)', category: 'Komoditas', currency: 'USD', lotSize: 1, price: 7850.00 },
    { symbol: 'CT=F', name: 'Cotton Futures (Kapas)', category: 'Komoditas', currency: 'USD', lotSize: 1, price: 72.80 },
    { symbol: 'FCPO=F', name: 'Crude Palm Oil (CPO Sawit)', category: 'Komoditas', currency: 'USD', lotSize: 1, price: 980.00 }
];

// Forex
const FOREX_ASSETS = [
    { symbol: 'USDIDR=X', name: 'US Dollar / Indonesian Rupiah', category: 'Forex', currency: 'IDR', price: 16250.00 },
    { symbol: 'EURUSD=X', name: 'Euro / US Dollar', category: 'Forex', currency: 'USD', price: 1.0850 },
    { symbol: 'USDJPY=X', name: 'US Dollar / Japanese Yen', category: 'Forex', currency: 'USD', price: 152.40 },
    { symbol: 'GBPUSD=X', name: 'British Pound / US Dollar', category: 'Forex', currency: 'USD', price: 1.2980 },
    { symbol: 'AUDUSD=X', name: 'Australian Dollar / US Dollar', category: 'Forex', currency: 'USD', price: 0.6650 },
    { symbol: 'USDCAD=X', name: 'US Dollar / Canadian Dollar', category: 'Forex', currency: 'USD', price: 1.3850 },
    { symbol: 'USDCHF=X', name: 'US Dollar / Swiss Franc', category: 'Forex', currency: 'USD', price: 0.8650 },
    { symbol: 'NZDUSD=X', name: 'New Zealand Dollar / US Dollar', category: 'Forex', currency: 'USD', price: 0.6020 },
    { symbol: 'EURIDR=X', name: 'Euro / Indonesian Rupiah', category: 'Forex', currency: 'IDR', price: 17650.00 },
    { symbol: 'SGDIDR=X', name: 'Singapore Dollar / Indonesian Rupiah', category: 'Forex', currency: 'IDR', price: 12380.00 },
    { symbol: 'MYRIDR=X', name: 'Malaysian Ringgit / Indonesian Rupiah', category: 'Forex', currency: 'IDR', price: 3750.00 },
    { symbol: 'CNYIDR=X', name: 'Chinese Yuan / Indonesian Rupiah', category: 'Forex', currency: 'IDR', price: 2280.00 },
    { symbol: 'JPYIDR=X', name: 'Japanese Yen (100) / Rupiah', category: 'Forex', currency: 'IDR', price: 10650.00 },
    { symbol: 'GBPIDR=X', name: 'British Pound / Rupiah', category: 'Forex', currency: 'IDR', price: 21100.00 },
    { symbol: 'AUDIDR=X', name: 'Australian Dollar / Rupiah', category: 'Forex', currency: 'IDR', price: 10820.00 }
];

// Indices
const INDEX_ASSETS = [
    { symbol: '^JKSE', name: 'IHSG Composite Jakarta', category: 'Index', currency: 'IDR', price: 6480.00 },
    { symbol: '^GSPC', name: 'S&P 500 Index', category: 'Index', currency: 'USD', price: 5815.00 },
    { symbol: '^IXIC', name: 'Nasdaq Composite', category: 'Index', currency: 'USD', price: 18450.00 },
    { symbol: '^DJI', name: 'Dow Jones Industrial', category: 'Index', currency: 'USD', price: 42800.00 },
    { symbol: '^N225', name: 'Nikkei 225 Tokyo', category: 'Index', currency: 'USD', price: 38900.00 },
    { symbol: '^HSI', name: 'Hang Seng Index Hong Kong', category: 'Index', currency: 'USD', price: 20600.00 },
    { symbol: '^FTSE', name: 'FTSE 100 London', category: 'Index', currency: 'USD', price: 8250.00 },
    { symbol: '^GDAXI', name: 'DAX Frankfurt', category: 'Index', currency: 'USD', price: 19500.00 },
    { symbol: 'DX-Y.NYB', name: 'US Dollar Index (DXY)', category: 'Index', currency: 'USD', price: 104.20 },
    { symbol: '^TNX', name: 'US 10Y Treasury Yield', category: 'Rates', currency: 'USD', price: 4.25 },
    { symbol: '^VIX', name: 'CBOE Volatility VIX', category: 'Rates', currency: 'USD', price: 15.50 }
];

// Combine all into the comprehensive master universe
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

// Macroeconomic & Microeconomic Statistics Data Feed
const MACRO_MICRO_DATA = {
    indonesia: {
        biRate: '6.00%',
        biRateChange: '0.00%',
        inflationYoY: '2.12%',
        inflationMoM: '0.08%',
        gdpGrowthYoY: '5.05%',
        foreignReserves: '$150.2B',
        tradeBalance: '+$2.9B Surplus',
        debtToGdp: '38.6%',
        currAccountDeficit: '-0.9% of GDP',
        tenYearYield: '6.68%',
        jisdorFx: 'Rp 16,250'
    },
    global: {
        fedRate: '4.75% - 5.00%',
        fedRateExpectation: 'Cut 25bps in Dec',
        usCpiInflation: '3.2% YoY',
        usGdpAnnualized: '2.8%',
        usUnemployment: '4.1%',
        us10YYield: '4.25%',
        us2YYield: '4.15%',
        yieldCurveSpread: '+10 bps (Uninverted)',
        dxyIndex: '104.20',
        brentCrude: '$75.20 / bbl',
        globalGdpGrowth: '3.1% IMF Forecast'
    },
    microKeyMetrics: [
        { symbol: 'BBCA.JK', name: 'Bank Central Asia', pe: 21.4, pbv: 4.8, roe: '22.8%', divYield: '2.8%', mktCapIdr: '1,120 T' },
        { symbol: 'BBRI.JK', name: 'Bank Rakyat Indonesia', pe: 11.2, pbv: 2.1, roe: '18.9%', divYield: '6.4%', mktCapIdr: '680 T' },
        { symbol: 'BMRI.JK', name: 'Bank Mandiri', pe: 10.8, pbv: 2.2, roe: '20.1%', divYield: '5.6%', mktCapIdr: '595 T' },
        { symbol: 'TLKM.JK', name: 'Telkom Indonesia', pe: 14.5, pbv: 2.4, roe: '16.5%', divYield: '5.8%', mktCapIdr: '264 T' },
        { symbol: 'ASII.JK', name: 'Astra International', pe: 7.2, pbv: 1.05, roe: '15.2%', divYield: '8.4%', mktCapIdr: '198 T' },
        { symbol: 'BREN.JK', name: 'Barito Renewables Energy', pe: 125.0, pbv: 48.0, roe: '38.4%', divYield: '0.4%', mktCapIdr: '915 T' },
        { symbol: 'CUAN.JK', name: 'Petrindo Jaya Kreasi', pe: 95.0, pbv: 22.0, roe: '23.0%', divYield: '0.5%', mktCapIdr: '88 T' },
        { symbol: 'AMMN.JK', name: 'Amman Mineral', pe: 34.0, pbv: 6.8, roe: '20.0%', divYield: '0.8%', mktCapIdr: '648 T' },
        { symbol: 'NVDA', name: 'NVIDIA Corp', pe: 58.2, pbv: 48.5, roe: '115.0%', divYield: '0.03%', mktCapUsd: '$3.52 T' },
        { symbol: 'AAPL', name: 'Apple Inc', pe: 34.8, pbv: 45.0, roe: '148.0%', divYield: '0.45%', mktCapUsd: '$3.45 T' },
        { symbol: 'MSFT', name: 'Microsoft Corp', pe: 35.2, pbv: 12.8, roe: '38.5%', divYield: '0.75%', mktCapUsd: '$3.18 T' },
        { symbol: 'SPACEX', name: 'SpaceX (Pre-IPO)', pe: 85.0, pbv: 18.5, roe: '21.5%', divYield: '0.00%', mktCapUsd: '$210.0 B' }
    ]
};

console.log(`Generated universe with ${ALL_UNIVERSE.length} total assets!`);

// Export universe.js
const fileContent = `// Comprehensive Bloomberg Terminal Multi-Asset Global Universe
// 1,000+ Tradeable Assets: SpaceX, Space Tech, Pre-IPOs, All 850+ IDX Stocks,
// US S&P500/Nasdaq Mega-caps, Hot IPOs, Top 100 Cryptos, Commodities, Forex, and Global Indices.

const SPACE_TECH_ASSETS = ${JSON.stringify(SPACE_TECH_ASSETS, null, 4)};

const HOT_IPO_ASSETS = ${JSON.stringify(HOT_IPO_ASSETS, null, 4)};

const IDX_FULL_ASSETS = ${JSON.stringify(IDX_FULL_ASSETS, null, 4)};

const US_GLOBAL_ASSETS = ${JSON.stringify(US_GLOBAL_ASSETS, null, 4)};

const CRYPTO_ASSETS = ${JSON.stringify(CRYPTO_ASSETS, null, 4)};

const COMMODITY_ASSETS = ${JSON.stringify(COMMODITY_ASSETS, null, 4)};

const FOREX_ASSETS = ${JSON.stringify(FOREX_ASSETS, null, 4)};

const INDEX_ASSETS = ${JSON.stringify(INDEX_ASSETS, null, 4)};

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

const MACRO_MICRO_DATA = ${JSON.stringify(MACRO_MICRO_DATA, null, 4)};

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
`;

fs.writeFileSync(path.join(__dirname, '../universe.js'), fileContent, 'utf8');
console.log('Successfully wrote expanded universe.js!');
