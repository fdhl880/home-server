'use strict';

// Zero-dependency Institutional Bloomberg PDF 1.4 Generator (A4 Portrait, Base-14 Type1 Fonts)
// Produces standards-compliant binary PDFs readable in Gmail, Chrome, Android PDF Viewer & Acrobat.

const PAGE_W = 595.28;
const PAGE_H = 841.89;
const MARGIN = 36;
const CONTENT_W = PAGE_W - MARGIN * 2;

const FONT_CHAR_W = {
    F1: 0.52, // Helvetica
    F2: 0.56, // Helvetica-Bold
    F3: 0.60, // Courier (fixed width)
    F4: 0.60  // Courier-Bold (fixed width)
};

function sanitizePdfText(raw) {
    return String(raw == null ? '' : raw)
        .replace(/[\u2013\u2014]/g, '-')
        .replace(/[\u2018\u2019]/g, "'")
        .replace(/[\u201C\u201D]/g, '"')
        .replace(/\u2022/g, '*')
        .replace(/\u2192/g, '->')
        .replace(/\u2713/g, 'OK')
        .replace(/[^\x20-\x7E]/g, ' ')
        .replace(/\s+/g, ' ')
        .trim();
}

function pdfEscape(str) {
    return sanitizePdfText(str)
        .replace(/\\/g, '\\\\')
        .replace(/\(/g, '\\(')
        .replace(/\)/g, '\\)');
}

function approxTextWidth(str, font, size) {
    const s = sanitizePdfText(str);
    const factor = FONT_CHAR_W[font] || 0.55;
    return s.length * size * factor;
}

function truncateText(str, maxWidth, font, size) {
    const s = sanitizePdfText(str);
    if (!maxWidth || approxTextWidth(s, font, size) <= maxWidth) return s;
    const avg = size * (FONT_CHAR_W[font] || 0.55);
    const maxChars = Math.max(2, Math.floor(maxWidth / avg) - 2);
    return s.length > maxChars ? s.slice(0, maxChars) + '..' : s;
}

function wrapLines(str, maxWidth, font, size, maxLines = 3) {
    const clean = sanitizePdfText(str);
    if (!clean) return [];
    const avg = size * (FONT_CHAR_W[font] || 0.55);
    const limit = Math.max(12, Math.floor(maxWidth / avg));
    const words = clean.split(' ');
    const lines = [];
    let cur = '';
    for (const w of words) {
        const candidate = cur ? `${cur} ${w}` : w;
        if (candidate.length <= limit) {
            cur = candidate;
        } else {
            if (cur) lines.push(cur);
            cur = w;
            if (lines.length >= maxLines - 1) break;
        }
    }
    if (cur && lines.length < maxLines) lines.push(cur);
    if (lines.length === maxLines) {
        lines[maxLines - 1] = truncateText(lines[maxLines - 1], maxWidth, font, size);
    }
    return lines;
}

function rgbStr(rgb) {
    const [r, g, b] = rgb;
    return `${(r / 255).toFixed(3)} ${(g / 255).toFixed(3)} ${(b / 255).toFixed(3)}`;
}

class BloombergPdfDoc {
    constructor(title = 'Bloomberg Terminal Document', footerLeft = 'Bloomberg Terminal | Institutional Account Document') {
        this.title = sanitizePdfText(title);
        this.footerLeft = sanitizePdfText(footerLeft);
        this.pages = [];
        this.cur = null;
        this.y = 0; // Top-down coordinate (0 at top of page, PAGE_H at bottom)
        this.addPage();
    }

    addPage() {
        this.cur = [];
        this.pages.push(this.cur);
        this.y = MARGIN;
    }

    ensureSpace(neededPts) {
        if (this.y + neededPts > PAGE_H - MARGIN - 28) {
            this.addPage();
            this.y = MARGIN + 8;
        }
    }

    // Convert top-down y to PDF bottom-up y
    _py(yTop) {
        return PAGE_H - yTop;
    }

    fillRect(x, yTop, w, h, rgb) {
        const yBot = PAGE_H - (yTop + h);
        this.cur.push(`${rgbStr(rgb)} rg ${x.toFixed(2)} ${yBot.toFixed(2)} ${w.toFixed(2)} ${h.toFixed(2)} re f`);
    }

    strokeRect(x, yTop, w, h, rgb, lineWidth = 0.7) {
        const yBot = PAGE_H - (yTop + h);
        this.cur.push(`${lineWidth.toFixed(2)} w ${rgbStr(rgb)} RG ${x.toFixed(2)} ${yBot.toFixed(2)} ${w.toFixed(2)} ${h.toFixed(2)} re S`);
    }

    hLine(x1, x2, yTop, rgb, lineWidth = 0.7) {
        const py = this._py(yTop);
        this.cur.push(`${lineWidth.toFixed(2)} w ${rgbStr(rgb)} RG ${x1.toFixed(2)} ${py.toFixed(2)} m ${x2.toFixed(2)} ${py.toFixed(2)} l S`);
    }

    text(rawStr, x, yBaselineTop, { font = 'F1', size = 9, color = [17, 22, 28], align = 'left', maxWidth = 0 } = {}) {
        const clean = maxWidth > 0 ? truncateText(rawStr, maxWidth, font, size) : sanitizePdfText(rawStr);
        if (!clean) return;
        let tx = x;
        if (align === 'right') {
            tx = x - approxTextWidth(clean, font, size);
        } else if (align === 'center') {
            tx = x - approxTextWidth(clean, font, size) / 2;
        }
        const py = this._py(yBaselineTop);
        this.cur.push(`BT /${font} ${size.toFixed(1)} Tf ${rgbStr(color)} rg 1 0 0 1 ${tx.toFixed(2)} ${py.toFixed(2)} Tm (${pdfEscape(clean)}) Tj ET`);
    }

    drawBloombergHeader(subtitle, rightTag, metaLeftLines = [], metaRightLines = []) {
        // Top orange accent bar
        this.fillRect(MARGIN, this.y, CONTENT_W, 4, [255, 102, 0]);
        this.y += 4;
        // Solid black Bloomberg header band
        this.fillRect(MARGIN, this.y, CONTENT_W, 38, [0, 0, 0]);
        this.text('Bloomberg', MARGIN + 12, this.y + 24, { font: 'F2', size: 17, color: [255, 255, 255] });
        this.text(`| ${subtitle}`, MARGIN + 105, this.y + 23, { font: 'F1', size: 10, color: [175, 184, 196] });
        this.text(rightTag, MARGIN + CONTENT_W - 12, this.y + 23, { font: 'F4', size: 9.5, color: [255, 176, 0], align: 'right' });
        this.y += 38;

        // Metadata strip
        const rows = Math.max(metaLeftLines.length, metaRightLines.length, 1);
        const stripH = 12 + rows * 12;
        this.fillRect(MARGIN, this.y, CONTENT_W, stripH, [243, 244, 246]);
        this.strokeRect(MARGIN, this.y, CONTENT_W, stripH, [207, 214, 223], 0.6);
        for (let i = 0; i < metaLeftLines.length; i++) {
            this.text(metaLeftLines[i], MARGIN + 10, this.y + 14 + i * 12, { font: i === 0 ? 'F2' : 'F1', size: 8.5, color: i === 0 ? [17, 22, 28] : [75, 85, 99] });
        }
        for (let i = 0; i < metaRightLines.length; i++) {
            this.text(metaRightLines[i], MARGIN + CONTENT_W - 10, this.y + 14 + i * 12, { font: i === 0 ? 'F4' : 'F3', size: 8.2, color: i === 0 ? [17, 22, 28] : [75, 85, 99], align: 'right' });
        }
        this.y += stripH + 12;
    }

    drawSectionTitle(title) {
        this.ensureSpace(28);
        this.text(title, MARGIN, this.y + 10, { font: 'F2', size: 9.5, color: [17, 22, 28] });
        this.y += 14;
        this.hLine(MARGIN, MARGIN + CONTENT_W, this.y, [0, 0, 0], 1.2);
        this.y += 7;
    }

    drawKpiRow(cards) {
        this.ensureSpace(58);
        const gap = 8;
        const w = (CONTENT_W - gap * (cards.length - 1)) / cards.length;
        const h = 48;
        cards.forEach((c, idx) => {
            const x = MARGIN + idx * (w + gap);
            this.fillRect(x, this.y, w, h, [250, 251, 252]);
            this.strokeRect(x, this.y, w, h, [209, 213, 219], 0.7);
            this.fillRect(x, this.y, w, 2.2, c.accent || [255, 102, 0]);
            this.text(c.label, x + 7, this.y + 13, { font: 'F2', size: 7.0, color: [107, 114, 128], maxWidth: w - 14 });
            this.text(c.value, x + 7, this.y + 28, { font: 'F4', size: 10.2, color: c.color || [17, 22, 28], maxWidth: w - 14 });
            if (c.sub) {
                this.text(c.sub, x + 7, this.y + 40, { font: 'F3', size: 7.4, color: c.subColor || [107, 114, 128], maxWidth: w - 14 });
            }
        });
        this.y += h + 12;
    }

    drawTable(columns, rows, emptyMsg = 'No records available.') {
        const headerH = 17;
        const rowH = 15;
        this.ensureSpace(headerH + rowH + 6);

        const drawHeader = () => {
            this.fillRect(MARGIN, this.y, CONTENT_W, headerH, [24, 28, 34]);
            let cx = MARGIN;
            for (const col of columns) {
                const tx = col.align === 'right' ? (cx + col.w - 4) : (cx + 4);
                this.text(col.label, tx, this.y + 11.5, { font: 'F2', size: 7.2, color: [255, 176, 0], align: col.align || 'left', maxWidth: col.w - 6 });
                cx += col.w;
            }
            this.y += headerH;
        };

        drawHeader();

        if (!rows.length) {
            this.fillRect(MARGIN, this.y, CONTENT_W, 20, [250, 251, 252]);
            this.strokeRect(MARGIN, this.y, CONTENT_W, 20, [229, 233, 239], 0.5);
            this.text(emptyMsg, MARGIN + CONTENT_W / 2, this.y + 13, { font: 'F1', size: 8.0, color: [107, 114, 128], align: 'center' });
            this.y += 28;
            return;
        }

        rows.forEach((row, rIdx) => {
            if (this.y + rowH > PAGE_H - MARGIN - 28) {
                this.addPage();
                this.y = MARGIN + 8;
                drawHeader();
            }
            if (rIdx % 2 === 1) {
                this.fillRect(MARGIN, this.y, CONTENT_W, rowH, [248, 250, 252]);
            }
            let cx = MARGIN;
            columns.forEach((col, cIdx) => {
                const cell = row[cIdx];
                const val = (cell && typeof cell === 'object') ? cell.text : cell;
                const color = (cell && typeof cell === 'object' && cell.color) ? cell.color : [17, 22, 28];
                const font = (cell && typeof cell === 'object' && cell.font) ? cell.font : (col.font || 'F3');
                const tx = col.align === 'right' ? (cx + col.w - 4) : (cx + 4);
                this.text(String(val == null ? '' : val), tx, this.y + 10.5, {
                    font,
                    size: 7.4,
                    color,
                    align: col.align || 'left',
                    maxWidth: col.w - 6
                });
                cx += col.w;
            });
            this.hLine(MARGIN, MARGIN + CONTENT_W, this.y + rowH, [229, 233, 239], 0.45);
            this.y += rowH;
        });
        this.y += 10;
    }

    buildBuffer() {
        const totalPages = this.pages.length;
        const stamp = new Date().toISOString().replace('T', ' ').slice(0, 19) + ' UTC';
        // Append footer onto every page
        this.pages.forEach((ops, idx) => {
            const fy = PAGE_H - MARGIN - 10;
            const pyLine = PAGE_H - (fy - 8);
            const pyText = PAGE_H - (fy + 2);
            ops.push(`0.60 w ${rgbStr([207, 214, 223])} RG ${MARGIN.toFixed(2)} ${pyLine.toFixed(2)} m ${(MARGIN + CONTENT_W).toFixed(2)} ${pyLine.toFixed(2)} l S`);
            const leftTxt = `${this.footerLeft} | Generated ${stamp}`;
            const rightTxt = `Page ${idx + 1} of ${totalPages}`;
            ops.push(`BT /F3 7.4 Tf ${rgbStr([107, 114, 128])} rg 1 0 0 1 ${MARGIN.toFixed(2)} ${pyText.toFixed(2)} Tm (${pdfEscape(leftTxt)}) Tj ET`);
            const rx = MARGIN + CONTENT_W - approxTextWidth(rightTxt, 'F3', 7.4);
            ops.push(`BT /F3 7.4 Tf ${rgbStr([107, 114, 128])} rg 1 0 0 1 ${rx.toFixed(2)} ${pyText.toFixed(2)} Tm (${pdfEscape(rightTxt)}) Tj ET`);
        });

        // Object layout:
        // 1: Catalog, 2: Pages, 3: Info, 4..7: Base-14 Fonts (F1..F4)
        // Per page i: Content stream (8 + 2*i), Page object (9 + 2*i)
        const objects = [];
        const addObj = (body) => { objects.push(body); return objects.length; };

        const pageObjIds = [];
        const basePageStart = 8;
        for (let i = 0; i < totalPages; i++) {
            pageObjIds.push(basePageStart + i * 2 + 1);
        }

        addObj(`<< /Type /Catalog /Pages 2 0 R >>`); // 1
        addObj(`<< /Type /Pages /Kids [${pageObjIds.map(id => `${id} 0 R`).join(' ')}] /Count ${totalPages} >>`); // 2
        addObj(`<< /Title (${pdfEscape(this.title)}) /Author (Bloomberg Terminal) /Creator (Bloomberg Terminal PDF Engine) >>`); // 3
        addObj(`<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>`); // 4 -> F1
        addObj(`<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>`); // 5 -> F2
        addObj(`<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>`); // 6 -> F3
        addObj(`<< /Type /Font /Subtype /Type1 /BaseFont /Courier-Bold >>`); // 7 -> F4

        for (let i = 0; i < totalPages; i++) {
            const streamData = this.pages[i].join('\n');
            const streamLen = Buffer.byteLength(streamData, 'latin1');
            const contentId = addObj(`<< /Length ${streamLen} >>\nstream\n${streamData}\nendstream`);
            addObj(`<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${PAGE_W.toFixed(2)} ${PAGE_H.toFixed(2)}] /Resources << /Font << /F1 4 0 R /F2 5 0 R /F3 6 0 R /F4 7 0 R >> >> /Contents ${contentId} 0 R >>`);
        }

        const chunks = [];
        const header = '%PDF-1.4\n%\xE2\xE3\xCF\xD3\n';
        chunks.push(Buffer.from(header, 'latin1'));
        let offset = chunks[0].length;
        const offsets = [0];

        for (let i = 0; i < objects.length; i++) {
            offsets.push(offset);
            const entry = Buffer.from(`${i + 1} 0 obj\n${objects[i]}\nendobj\n`, 'latin1');
            chunks.push(entry);
            offset += entry.length;
        }

        const xrefStart = offset;
        let xref = `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
        for (let i = 1; i <= objects.length; i++) {
            xref += `${String(offsets[i]).padStart(10, '0')} 00000 n \n`;
        }
        xref += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R /Info 3 0 R >>\nstartxref\n${xrefStart}\n%%EOF\n`;
        chunks.push(Buffer.from(xref, 'latin1'));

        return Buffer.concat(chunks);
    }
}

function fmtIdr(n) {
    const v = Number(n) || 0;
    return (v < 0 ? '-Rp ' : 'Rp ') + Math.round(Math.abs(v)).toLocaleString('en-US');
}

function fmtUsd(n) {
    const v = Number(n) || 0;
    const dec = Math.abs(v) > 0 && Math.abs(v) < 1 ? 4 : 2;
    return (v < 0 ? '-$' : '$') + Math.abs(v).toLocaleString('en-US', { minimumFractionDigits: dec, maximumFractionDigits: dec });
}

function fmtPct(n) {
    const v = Number(n) || 0;
    return `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`;
}

function fmtQty(q) {
    const v = Number(q) || 0;
    return Math.abs(v) < 1 ? v.toFixed(4) : v.toLocaleString('en-US', { maximumFractionDigits: 4 });
}

const GREEN = [0, 135, 62];
const RED = [198, 40, 40];
const ORANGE = [217, 83, 0];
const DARK = [17, 22, 28];
const MUTED = [90, 98, 110];

// 1. Monthly Portfolio Account Statement PDF (PORT <GO>)
function buildMonthlyStatementPdf(stmt, snap) {
    const s = snap || {};
    const sum = (stmt && stmt.summary) || {};
    const periodLabel = (stmt && stmt.periodLabel) || 'Current Period';
    const monthKey = (stmt && stmt.monthKey) || new Date().toISOString().slice(0, 7);
    const navIdr = Number(sum.totalNetWorth ?? s.totalNetWorth ?? 0);
    const usdRate = Number(sum.usdRate ?? s.usdRate ?? 18218);
    const navUsd = usdRate > 0 ? navIdr / usdRate : 0;
    const initCap = Number(sum.initialCapital ?? s.initialCapital ?? 200000000);
    const cashIdr = Number(sum.cash ?? s.cash ?? 0);
    const cashWt = navIdr > 0 ? (cashIdr / navIdr) * 100 : 100;
    const retPct = Number(sum.overallReturn ?? s.overallReturn ?? 0);
    const uPnl = Number(sum.unrealizedPnL ?? s.unrealizedPnL ?? 0);
    const rPnl = Number(sum.realizedPnL ?? s.realizedPnL ?? 0);

    const doc = new BloombergPdfDoc(
        `Bloomberg PORT Monthly Statement - ${periodLabel}`,
        'Bloomberg Terminal * PORT <GO> Monthly Account Statement * Confidential'
    );

    doc.drawBloombergHeader(
        'PORTFOLIO & RISK ANALYTICS',
        'PORT <GO> MONTHLY STATEMENT',
        [
            'ACCOUNT HOLDER: FADHIL MUHAMMAD SYAFIQ LUBIS (UUID: 38492018)',
            `Contributed Capital Basis: ${fmtIdr(initCap)}  |  Base Currency: IDR / USD`
        ],
        [
            `STATEMENT PERIOD: ${periodLabel}`,
            `Ref FX USD/IDR: ${fmtIdr(usdRate)}`
        ]
    );

    doc.drawKpiRow([
        { label: 'NET ASSET VALUE (NAV)', value: fmtIdr(navIdr), sub: `${fmtUsd(navUsd)} USD`, color: DARK, accent: [255, 102, 0] },
        { label: 'CUMULATIVE RETURN', value: fmtPct(retPct), sub: `vs ${fmtIdr(initCap)}`, color: retPct >= 0 ? GREEN : RED, accent: retPct >= 0 ? GREEN : RED },
        { label: 'AVAILABLE CASH', value: fmtIdr(cashIdr), sub: `${cashWt.toFixed(1)}% of Total NAV`, color: DARK, accent: [77, 163, 255] },
        { label: 'UNREALIZED / REALIZED P&L', value: fmtIdr(uPnl), sub: `Realized: ${fmtIdr(rPnl)}`, color: uPnl >= 0 ? GREEN : RED, subColor: rPnl >= 0 ? GREEN : RED, accent: [255, 176, 0] }
    ]);

    // Treasury & Linked Futures Strip
    const depIdr = Number(s.totalDepositedIdr || 0);
    const wdIdr = Number(s.totalWithdrawnIdr || 0);
    const netFlow = Number(s.netDepositsIdr || 0);
    const futUsdt = Number(sum.futuresWalletUsdt || 0);
    if (depIdr > 0 || wdIdr > 0 || futUsdt > 0) {
        doc.ensureSpace(26);
        doc.fillRect(MARGIN, doc.y, CONTENT_W, 20, [255, 250, 243]);
        doc.strokeRect(MARGIN, doc.y, CONTENT_W, 20, [209, 213, 219], 0.6);
        doc.fillRect(MARGIN, doc.y, 3, 20, [255, 102, 0]);
        const parts = [`TREASURY FLOWS: Deposits ${fmtIdr(depIdr)} | Withdrawals ${fmtIdr(wdIdr)} | Net ${fmtIdr(netFlow)}`];
        if (futUsdt > 0) parts.push(`LINKED FUTURES: ${fmtUsd(futUsdt)} USDT`);
        doc.text(parts.join('   ||   '), MARGIN + 9, doc.y + 13, { font: 'F4', size: 7.5, color: DARK, maxWidth: CONTENT_W - 16 });
        doc.y += 28;
    }

    // Section 1: Holdings
    const holdings = Array.isArray(s.holdings) ? s.holdings : [];
    doc.drawSectionTitle(`1. PORTFOLIO HOLDINGS & WEIGHT ATTRIBUTION (${holdings.length} ACTIVE POSITIONS)`);
    doc.drawTable(
        [
            { label: 'TICKER', w: 58, align: 'left', font: 'F4' },
            { label: 'SECURITY', w: 92, align: 'left', font: 'F1' },
            { label: 'QTY', w: 46, align: 'right', font: 'F3' },
            { label: 'AVG COST', w: 66, align: 'right', font: 'F3' },
            { label: 'LAST PX', w: 66, align: 'right', font: 'F4' },
            { label: 'MKT VALUE (IDR)', w: 84, align: 'right', font: 'F4' },
            { label: 'WT%', w: 34, align: 'right', font: 'F3' },
            { label: 'UNREAL P&L', w: CONTENT_W - 446, align: 'right', font: 'F4' }
        ],
        holdings.map(h => {
            const wt = navIdr > 0 ? ((Number(h.marketValue) || 0) / navIdr) * 100 : 0;
            const isUsd = h.currency === 'USD';
            const pnl = Number(h.unrealizedPnL || 0);
            return [
                { text: h.symbol, color: ORANGE, font: 'F4' },
                { text: h.name || h.symbol, color: DARK, font: 'F1' },
                fmtQty(h.qty),
                { text: isUsd ? fmtUsd(h.avgPrice) : fmtIdr(h.avgPrice), color: MUTED },
                isUsd ? fmtUsd(h.currentPrice) : fmtIdr(h.currentPrice),
                fmtIdr(h.marketValue),
                `${wt.toFixed(1)}%`,
                { text: `${fmtIdr(pnl)} (${fmtPct(h.unrealizedPnLPct)})`, color: pnl >= 0 ? GREEN : RED, font: 'F4' }
            ];
        }),
        `Portfolio is currently 100% Liquid Cash (${fmtIdr(cashIdr)}).`
    );

    // Section 2: Recent Trades
    const trades = Array.isArray(s.trades) ? s.trades.slice(0, 20) : [];
    doc.drawSectionTitle(`2. AUDITED DMA EXECUTION BLOTTER (RECENT ${trades.length} OF ${s.allTradesCount || trades.length} ORDERS)`);
    doc.drawTable(
        [
            { label: 'DATE', w: 58, align: 'left', font: 'F3' },
            { label: 'SIDE', w: 34, align: 'left', font: 'F4' },
            { label: 'TYPE', w: 46, align: 'left', font: 'F3' },
            { label: 'TICKER', w: 62, align: 'left', font: 'F4' },
            { label: 'QTY', w: 44, align: 'right', font: 'F3' },
            { label: 'EXEC PX', w: 68, align: 'right', font: 'F3' },
            { label: 'FEE (IDR)', w: 58, align: 'right', font: 'F3' },
            { label: 'TOTAL (IDR)', w: 86, align: 'right', font: 'F4' },
            { label: 'STATUS', w: CONTENT_W - 456, align: 'right', font: 'F4' }
        ],
        trades.map(t => [
            String(t.timestamp || '').slice(0, 10),
            { text: t.type || '-', color: t.type === 'BUY' ? GREEN : RED, font: 'F4' },
            t.orderType || 'MARKET',
            { text: t.symbol || '-', color: DARK, font: 'F4' },
            fmtQty(t.qty),
            t.currency === 'USD' ? fmtUsd(t.price) : fmtIdr(t.price),
            { text: fmtIdr(t.brokerFee || 0), color: MUTED },
            fmtIdr(t.totalValueIdr || 0),
            { text: t.status || 'FILLED', color: t.status === 'FILLED' ? GREEN : ORANGE, font: 'F4' }
        ]),
        'No settled DMA executions recorded in this period.'
    );

    // Section 3: Treasury Wires (if present)
    const flows = Array.isArray(s.capitalFlows) ? s.capitalFlows.slice(0, 15) : [];
    if (flows.length) {
        doc.drawSectionTitle(`3. PRIME BROKERAGE TREASURY WIRES & CAPITAL FLOWS (${flows.length} SETTLED)`);
        doc.drawTable(
            [
                { label: 'SWIFT REF', w: 68, align: 'left', font: 'F4' },
                { label: 'DATE', w: 58, align: 'left', font: 'F3' },
                { label: 'DIR', w: 54, align: 'left', font: 'F4' },
                { label: 'COUNTERPARTY', w: 145, align: 'left', font: 'F1' },
                { label: 'SETTLED (IDR)', w: 94, align: 'right', font: 'F4' },
                { label: 'POST-WIRE CASH', w: CONTENT_W - 419, align: 'right', font: 'F3' }
            ],
            flows.map(f => [
                { text: f.reference || f.id, color: ORANGE, font: 'F4' },
                String(f.timestamp || '').slice(0, 10),
                { text: f.type, color: f.type === 'DEPOSIT' ? GREEN : RED, font: 'F4' },
                f.counterparty || '-',
                { text: `${f.type === 'DEPOSIT' ? '+' : '-'}${fmtIdr(f.amountIdr)}`, color: f.type === 'DEPOSIT' ? GREEN : RED, font: 'F4' },
                fmtIdr(f.cashAfterIdr || 0)
            ])
        );
    }

    const safePeriod = monthKey.replace(/[^0-9A-Za-z_-]/g, '');
    return {
        filename: `Bloomberg_PORT_Statement_${safePeriod}.pdf`,
        buffer: doc.buildBuffer()
    };
}

// 2. DMA / EMSX Trade Confirmation Ticket PDF (EMSX <GO>)
function buildDmaTradeConfirmPdf(trade, portSnap = {}, schedule = null) {
    const t = trade || {};
    const side = String(t.type || 'BUY').toUpperCase();
    const sym = String(t.symbol || 'ASSET').toUpperCase();
    const isUsd = t.currency === 'USD';
    const status = String(t.status || 'FILLED').toUpperCase();
    const isFilled = status === 'FILLED';
    const isCancelled = status === 'CANCELLED';
    const statusRgb = isFilled ? GREEN : (isCancelled ? RED : ORANGE);
    const sideRgb = side === 'BUY' ? GREEN : RED;
    const pxStr = isUsd ? fmtUsd(t.price) : fmtIdr(t.price);
    const totalIdr = Number(t.totalValueIdr || 0);
    const feeIdr = Number(t.brokerFee || 0);
    const netSettlement = side === 'BUY' ? (totalIdr + feeIdr) : (totalIdr - feeIdr);
    const usdRate = Number(portSnap.usdRate || 18218);
    const tsIso = String(t.timestamp || new Date().toISOString());
    const tsUtc = tsIso.replace('T', ' ').slice(0, 19) + ' UTC';
    const exchange = (schedule && schedule.exchange) || t.exchange || 'DIRECT MARKET ACCESS (DMA)';

    const doc = new BloombergPdfDoc(
        `Bloomberg EMSX Trade Confirmation - ${side} ${sym}`,
        `Bloomberg EMSX <GO> * Electronic DMA Trade Confirmation * Ref ${t.id || 'N/A'}`
    );

    doc.drawBloombergHeader(
        'EXECUTION MANAGEMENT SYSTEM (EMSX)',
        `DMA ${side} TRADE CONFIRMATION`,
        [
            'ACCOUNT HOLDER: FADHIL MUHAMMAD SYAFIQ LUBIS (UUID: 38492018)',
            `Order Reference: ${t.id || 'N/A'}  |  Execution Venue: ${exchange}`
        ],
        [
            `STATUS: ${status}`,
            `Timestamp: ${tsUtc}`
        ]
    );

    // Status Hero Strip
    doc.fillRect(MARGIN, doc.y, CONTENT_W, 32, isFilled ? [232, 247, 239] : (isCancelled ? [253, 236, 236] : [255, 246, 230]));
    doc.strokeRect(MARGIN, doc.y, CONTENT_W, 32, statusRgb, 1.0);
    doc.fillRect(MARGIN, doc.y, 5, 32, statusRgb);
    doc.text(`${side} ${fmtQty(t.qty)} ${sym} @ ${pxStr}`, MARGIN + 14, doc.y + 15, { font: 'F4', size: 12, color: sideRgb });
    doc.text(`${t.name || sym}  [${t.category || 'Multi-Asset'} | ${t.orderType || 'MARKET'} | TIF ${t.tif || 'GTC'}]`, MARGIN + 14, doc.y + 26, { font: 'F1', size: 8.2, color: MUTED });
    doc.text(status, MARGIN + CONTENT_W - 12, doc.y + 20, { font: 'F4', size: 11, color: statusRgb, align: 'right' });
    doc.y += 44;

    // 4-Card Summary
    doc.drawKpiRow([
        { label: 'EXECUTION PRICE', value: pxStr, sub: isUsd ? fmtIdr(t.priceInIdr || (Number(t.price) * usdRate)) : 'IDR Spot', color: DARK, accent: sideRgb },
        { label: 'GROSS PRINCIPAL', value: fmtIdr(totalIdr), sub: `Qty: ${fmtQty(t.qty)} ${sym}`, color: DARK, accent: [255, 102, 0] },
        { label: 'BROKERAGE & LEVY (0.15%)', value: fmtIdr(feeIdr), sub: 'Institutional DMA Rate', color: MUTED, accent: [107, 114, 128] },
        { label: side === 'BUY' ? 'NET DEBIT (IDR)' : 'NET CREDIT (IDR)', value: fmtIdr(netSettlement), sub: side === 'SELL' ? `Realized P&L: ${fmtIdr(t.realizedPnL || 0)}` : 'T+0 Settlement', color: sideRgb, accent: sideRgb }
    ]);

    // 2-Column Detail Boxes
    doc.drawSectionTitle('1. EXECUTION TICKET & SETTLEMENT BREAKDOWN');
    const colGap = 12;
    const colW = (CONTENT_W - colGap) / 2;
    const leftPairs = [
        ['Order Ticket ID', t.id || '-'],
        ['Execution Time', tsUtc],
        ['Order Side', side],
        ['Order Type', `${t.orderType || 'MARKET'} (${t.tif || 'GTC'})`],
        ['Security Ticker', sym],
        ['Security Name', t.name || sym],
        ['Asset Class', t.category || 'Multi-Asset'],
        ['Exchange Venue', exchange],
        ['Market Session', t.marketStatus || (schedule && schedule.status) || 'OPEN']
    ];
    const rightPairs = [
        ['Executed Quantity', fmtQty(t.qty)],
        ['Execution Price', `${pxStr} (${t.currency || 'IDR'})`],
        ['Limit / Stop Price', t.limitPrice ? (isUsd ? fmtUsd(t.limitPrice) : fmtIdr(t.limitPrice)) : 'MARKET BEST EXEC'],
        ['Reference FX Rate', isUsd ? `USD/IDR ${fmtIdr(usdRate)}` : '1.0000 (Domestic IDR)'],
        ['Unit Price (IDR)', fmtIdr(t.priceInIdr || (isUsd ? Number(t.price) * usdRate : Number(t.price)))],
        ['Gross Principal', fmtIdr(totalIdr)],
        ['Commission & Levy', `${fmtIdr(feeIdr)} (0.15%)`],
        ['Net Settlement', fmtIdr(netSettlement)],
        ['Realized P&L', side === 'SELL' ? fmtIdr(t.realizedPnL || 0) : 'N/A (Opening Entry)']
    ];

    const boxH = 16 + leftPairs.length * 16;
    doc.ensureSpace(boxH + 10);
    const startY = doc.y;

    const drawKvBox = (x, title, pairs) => {
        doc.fillRect(x, startY, colW, 18, [24, 28, 34]);
        doc.text(title, x + 8, startY + 12, { font: 'F2', size: 7.8, color: [255, 176, 0] });
        doc.strokeRect(x, startY + 18, colW, boxH - 18, [209, 213, 219], 0.6);
        pairs.forEach(([k, v], i) => {
            const ry = startY + 18 + i * 16;
            if (i % 2 === 1) doc.fillRect(x + 0.5, ry, colW - 1, 16, [248, 250, 252]);
            doc.text(k, x + 8, ry + 11, { font: 'F1', size: 7.8, color: MUTED, maxWidth: colW * 0.44 });
            doc.text(String(v), x + colW - 8, ry + 11, { font: 'F4', size: 7.8, color: DARK, align: 'right', maxWidth: colW * 0.54 });
        });
    };

    drawKvBox(MARGIN, 'ORDER PARAMETERS', leftPairs);
    drawKvBox(MARGIN + colW + colGap, 'FINANCIAL SETTLEMENT', rightPairs);
    doc.y = startY + boxH + 14;

    // Post-Trade Portfolio Impact
    const holdings = Array.isArray(portSnap.holdings) ? portSnap.holdings : [];
    const heldPos = holdings.find(h => String(h.symbol || '').toUpperCase() === sym);
    doc.drawSectionTitle('2. POST-TRADE PORTFOLIO SNAPSHOT (PORT <GO>)');
    doc.drawKpiRow([
        { label: 'POST-TRADE CASH BALANCE', value: fmtIdr(portSnap.cash || 0), sub: 'Available Buying Power', color: DARK, accent: [77, 163, 255] },
        { label: 'ENDING PORTFOLIO NAV', value: fmtIdr(portSnap.totalNetWorth || 0), sub: `Return: ${fmtPct(portSnap.overallReturn || 0)}`, color: DARK, accent: [255, 102, 0] },
        { label: `POSITION IN ${sym}`, value: heldPos ? `${fmtQty(heldPos.qty)} units` : 'FLAT (0)', sub: heldPos ? `Avg: ${heldPos.currency === 'USD' ? fmtUsd(heldPos.avgPrice) : fmtIdr(heldPos.avgPrice)}` : 'Position closed / queued', color: heldPos ? GREEN : MUTED, accent: [0, 135, 62] }
    ]);

    if (t.note) {
        doc.ensureSpace(26);
        doc.fillRect(MARGIN, doc.y, CONTENT_W, 20, [243, 244, 246]);
        doc.strokeRect(MARGIN, doc.y, CONTENT_W, 20, [209, 213, 219], 0.5);
        doc.text(`EXECUTION NOTE: ${t.note}`, MARGIN + 8, doc.y + 13, { font: 'F3', size: 7.6, color: MUTED, maxWidth: CONTENT_W - 16 });
        doc.y += 28;
    }

    const safeSym = sym.replace(/[^A-Za-z0-9_-]/g, '');
    const safeId = String(t.id || Date.now()).replace(/[^A-Za-z0-9_-]/g, '').slice(-14);
    return {
        filename: `Bloomberg_EMSX_Confirm_${side}_${safeSym}_${safeId}.pdf`,
        buffer: doc.buildBuffer()
    };
}

// 3. Full EMSX Execution Blotter & Active Orders PDF
function buildEmsxBlotterPdf(portSnap = {}) {
    const s = portSnap || {};
    const today = new Date().toISOString().slice(0, 10);
    const trades = Array.isArray(s.trades) ? s.trades : [];
    const working = Array.isArray(s.workingOrders) ? s.workingOrders : [];
    const holdings = Array.isArray(s.holdings) ? s.holdings : [];

    const doc = new BloombergPdfDoc(
        `Bloomberg EMSX Execution Blotter - ${today}`,
        'Bloomberg Terminal * EMSX <GO> Audited Execution Blotter * Confidential'
    );

    doc.drawBloombergHeader(
        'EXECUTION MANAGEMENT SYSTEM (EMSX)',
        'EMSX <GO> AUDITED BLOTTER',
        [
            'ACCOUNT HOLDER: FADHIL MUHAMMAD SYAFIQ LUBIS (UUID: 38492018)',
            `Active Holdings: ${holdings.length}  |  Working Orders: ${working.length}  |  Total Executions: ${s.allTradesCount || trades.length}`
        ],
        [
            `REPORT DATE: ${today}`,
            `Cash: ${fmtIdr(s.cash || 0)} | NAV: ${fmtIdr(s.totalNetWorth || 0)}`
        ]
    );

    doc.drawSectionTitle(`1. ACTIVE WORKING / QUEUED ORDERS (${working.length})`);
    doc.drawTable(
        [
            { label: 'ORDER ID', w: 72, align: 'left', font: 'F3' },
            { label: 'TIME', w: 68, align: 'left', font: 'F3' },
            { label: 'SIDE', w: 36, align: 'left', font: 'F4' },
            { label: 'TYPE', w: 46, align: 'left', font: 'F3' },
            { label: 'TICKER', w: 64, align: 'left', font: 'F4' },
            { label: 'QTY', w: 46, align: 'right', font: 'F3' },
            { label: 'PRICE', w: 72, align: 'right', font: 'F3' },
            { label: 'STATUS', w: CONTENT_W - 404, align: 'right', font: 'F4' }
        ],
        working.map(o => [
            String(o.id || '').slice(-12),
            String(o.timestamp || '').replace('T', ' ').slice(5, 16),
            { text: o.type, color: o.type === 'BUY' ? GREEN : RED, font: 'F4' },
            o.orderType || 'MARKET',
            { text: o.symbol, color: ORANGE, font: 'F4' },
            fmtQty(o.qty),
            o.currency === 'USD' ? fmtUsd(o.limitPrice || o.price) : fmtIdr(o.limitPrice || o.price),
            { text: o.status || 'WORKING', color: ORANGE, font: 'F4' }
        ]),
        'No active working or queued orders.'
    );

    doc.drawSectionTitle(`2. AUDITED EXECUTION BLOTTER (${trades.length} RECENT EXECUTIONS)`);
    doc.drawTable(
        [
            { label: 'ORDER ID', w: 66, align: 'left', font: 'F3' },
            { label: 'DATE', w: 56, align: 'left', font: 'F3' },
            { label: 'SIDE', w: 34, align: 'left', font: 'F4' },
            { label: 'TYPE', w: 44, align: 'left', font: 'F3' },
            { label: 'TICKER', w: 58, align: 'left', font: 'F4' },
            { label: 'QTY', w: 42, align: 'right', font: 'F3' },
            { label: 'EXEC PX', w: 66, align: 'right', font: 'F3' },
            { label: 'TOTAL (IDR)', w: 86, align: 'right', font: 'F4' },
            { label: 'STATUS', w: CONTENT_W - 452, align: 'right', font: 'F4' }
        ],
        trades.map(t => [
            String(t.id || '').slice(-10),
            String(t.timestamp || '').slice(0, 10),
            { text: t.type, color: t.type === 'BUY' ? GREEN : RED, font: 'F4' },
            t.orderType || 'MARKET',
            { text: t.symbol, color: DARK, font: 'F4' },
            fmtQty(t.qty),
            t.currency === 'USD' ? fmtUsd(t.price) : fmtIdr(t.price),
            fmtIdr(t.totalValueIdr || 0),
            { text: t.status || 'FILLED', color: t.status === 'FILLED' ? GREEN : ORANGE, font: 'F4' }
        ]),
        'No DMA executions recorded yet.'
    );

    return {
        filename: `Bloomberg_EMSX_Blotter_${today}.pdf`,
        buffer: doc.buildBuffer()
    };
}

// 4. Single Family Office & Personal CFO Monthly Financial Report PDF (FIN <GO>)
function buildPersonalCfoReportPdf(finData = {}) {
    const s = (finData && finData.summary) || {};
    const fo = s.familyOffice || {};
    const bs = fo.balanceSheet || {};
    const ratios = fo.ratios || {};
    const team = Array.isArray(fo.cfoTeam) ? fo.cfoTeam : [];
    const accounts = Array.isArray(fo.accounts) ? fo.accounts : [];
    const bills = Array.isArray(fo.recurringBills) ? fo.recurringBills : [];
    const txs = Array.isArray(finData.transactions) ? finData.transactions.slice(0, 18) : [];
    const monthKey = s.monthPrefix || new Date().toISOString().slice(0, 7);

    const doc = new BloombergPdfDoc(
        `Bloomberg Family Office Personal CFO Report - ${monthKey}`,
        'Bloomberg Terminal * FIN <GO> Single Family Office & Personal CFO Report * Confidential'
    );

    doc.drawBloombergHeader(
        'SINGLE FAMILY OFFICE & PERSONAL CFO',
        `FIN <GO> EXECUTIVE REPORT (${fo.healthGrade || 'A'})`,
        [
            'PRINCIPAL: FADHIL MUHAMMAD SYAFIQ LUBIS (UUID: 38492018)',
            `Framework: Warren Buffett 40/60 + Wall Street Family Office Governance | FX USD/IDR: ${fmtIdr((s.botSync && s.botSync.fxRateIdr) || 18218)}`
        ],
        [
            `REPORTING MONTH: ${monthKey}`,
            `Health Grade: ${fo.healthGrade || 'A'} (${fo.healthScore || 85}/100)`
        ]
    );

    const netWorth = Number(bs.trueNetWorthIdr ?? s.totalIntegratedWealthIdr ?? 0);
    const runway = Number(ratios.emergencyRunwayMonths || 0);
    const saveRate = Number(s.savingsRatePct || 0);
    const dta = Number(ratios.debtToAssetPct || 0);
    doc.drawKpiRow([
        { label: 'TRUE NET WORTH', value: fmtIdr(netWorth), sub: `Assets ${fmtIdr(bs.totalAssetsIdr || netWorth)} | Debt ${fmtIdr(bs.totalLiabilitiesIdr || 0)}`, color: netWorth >= 0 ? GREEN : RED, accent: [255, 102, 0] },
        { label: 'EMERGENCY RUNWAY', value: `${runway.toFixed(1)} Months`, sub: `Target >= 6.0 mo (${fmtIdr(bs.liquidAndEmergencyIdr || 0)})`, color: runway >= 6 ? GREEN : (runway >= 3 ? ORANGE : RED), accent: [0, 135, 62] },
        { label: 'SAVINGS / DISCIPLINE', value: `${saveRate.toFixed(1)}% | ${s.disciplineScore || 100}/100`, sub: `Safe Daily: ${fmtIdr(s.dynamicSafeDailyIdr || 0)}/day`, color: saveRate >= 30 ? GREEN : ORANGE, accent: [255, 176, 0] },
        { label: 'SOLVENCY & RISK CAP', value: `Debt ${dta.toFixed(1)}%`, sub: `Futures Risk: ${Number(ratios.riskCapitalPct || 0).toFixed(1)}% of Assets`, color: dta <= 20 ? GREEN : RED, accent: [77, 163, 255] }
    ]);

    // Section 1: Personal Balance Sheet & Multi-Account Vaults
    doc.drawSectionTitle('1. PERSONAL BALANCE SHEET & MULTI-ACCOUNT TREASURY');
    const bsRows = accounts.map(a => [
        { text: a.name, font: 'F4', color: DARK },
        a.type || 'CASH',
        a.institution || '-',
        { text: fmtIdr(a.balanceIdr || 0), font: 'F4', color: (a.balanceIdr || 0) >= 0 ? GREEN : RED }
    ]);
    for (const ast of (finData.assets || [])) {
        bsRows.push([
            { text: ast.name, font: 'F4', color: DARK },
            `ASSET:${ast.category || 'INVEST'}`,
            ast.institution || '-',
            { text: fmtIdr(ast.valueIdr || 0), font: 'F4', color: GREEN }
        ]);
    }
    for (const lb of (finData.liabilities || [])) {
        bsRows.push([
            { text: lb.name, font: 'F4', color: RED },
            'LIABILITY',
            `${lb.lender || '-'} (${lb.aprPct || 0}% APR)`,
            { text: '-' + fmtIdr(lb.principalIdr || 0), font: 'F4', color: RED }
        ]);
    }
    doc.drawTable(
        [
            { label: 'ACCOUNT / BALANCE SHEET LINE', w: 185, align: 'left', font: 'F4' },
            { label: 'CLASSIFICATION', w: 92, align: 'left', font: 'F3' },
            { label: 'INSTITUTION / COUNTERPARTY', w: 130, align: 'left', font: 'F1' },
            { label: 'CURRENT BALANCE (IDR)', w: CONTENT_W - 407, align: 'right', font: 'F4' }
        ],
        bsRows,
        'No balance sheet accounts configured.'
    );

    // Section 2: 4-Role Virtual Family Office Committee Memo (Wrapped Executive Cards — Zero Truncation)
    doc.drawSectionTitle('2. FAMILY OFFICE COMMITTEE BRIEFING (YOUR PERSONAL FINANCE TEAM)');
    if (team.length) {
        for (const m of team) {
            const stCol = m.status === 'STRONG' ? GREEN : (m.status === 'WATCH' ? ORANGE : RED);
            const headLines = wrapLines(m.headline || '', CONTENT_W - 22, 'F1', 7.8, 2);
            const dirLines = wrapLines(`DIRECTIVE: ${m.directive || ''}`, CONTENT_W - 22, 'F2', 7.6, 2);
            const cardH = 18 + headLines.length * 10.5 + dirLines.length * 10.5 + 8;
            doc.ensureSpace(cardH + 6);
            doc.fillRect(MARGIN, doc.y, CONTENT_W, cardH, [249, 250, 252]);
            doc.strokeRect(MARGIN, doc.y, CONTENT_W, cardH, [209, 213, 219], 0.6);
            doc.fillRect(MARGIN, doc.y, 3.5, cardH, stCol);
            doc.text(m.role || 'OFFICER', MARGIN + 10, doc.y + 12, { font: 'F2', size: 8.2, color: ORANGE });
            doc.text(m.status || 'ACTIVE', MARGIN + CONTENT_W - 10, doc.y + 12, { font: 'F4', size: 7.8, color: stCol, align: 'right' });
            let cy = doc.y + 23;
            for (const hl of headLines) {
                doc.text(hl, MARGIN + 10, cy, { font: 'F1', size: 7.8, color: DARK });
                cy += 10.5;
            }
            for (const dl of dirLines) {
                doc.text(dl, MARGIN + 10, cy, { font: 'F2', size: 7.6, color: [15, 76, 129] });
                cy += 10.5;
            }
            doc.y += cardH + 6;
        }
        doc.y += 4;
    } else {
        doc.drawTable(
            [{ label: 'OFFICER ROLE', w: CONTENT_W, align: 'left', font: 'F1' }],
            [],
            'Committee briefing unavailable.'
        );
    }

    // Section 3: Monthly Cashflow Statement & Operating Envelopes
    doc.drawSectionTitle(`3. MONTHLY CASHFLOW & OPERATING ENVELOPES (${monthKey})`);
    const envCats = Array.from(new Set([...Object.keys(s.categoryLimits || {}), ...Object.keys(s.byCategory || {})]));
    doc.drawTable(
        [
            { label: 'OPERATING CATEGORY', w: 180, align: 'left', font: 'F4' },
            { label: 'BUDGET CEILING', w: 110, align: 'right', font: 'F3' },
            { label: 'ACTUAL SPENT', w: 110, align: 'right', font: 'F4' },
            { label: 'UTILIZATION', w: CONTENT_W - 400, align: 'right', font: 'F4' }
        ],
        envCats.map(cat => {
            const spent = Number((s.byCategory && s.byCategory[cat]) || 0);
            const lim = Number((s.categoryLimits && s.categoryLimits[cat]) || 0);
            const util = lim > 0 ? (spent / lim) * 100 : (spent > 0 ? 100 : 0);
            return [
                cat,
                lim > 0 ? fmtIdr(lim) : 'Unallocated',
                fmtIdr(spent),
                { text: `${util.toFixed(1)}%`, color: util > 100 ? RED : (util >= 75 ? ORANGE : GREEN), font: 'F4' }
            ];
        }),
        'No operating category spending recorded this month.'
    );

    // Section 4: Recurring Bills & Stress-Test Summary
    if (bills.length) {
        doc.drawSectionTitle(`4. FIXED MONTHLY COMMITMENTS & RECURRING BILLS (${bills.length})`);
        doc.drawTable(
            [
                { label: 'COMMITMENT / BILL', w: 160, align: 'left', font: 'F4' },
                { label: 'CATEGORY', w: 100, align: 'left', font: 'F1' },
                { label: 'DUE DAY', w: 62, align: 'right', font: 'F3' },
                { label: 'AMOUNT (IDR)', w: 100, align: 'right', font: 'F4' },
                { label: 'STATUS', w: CONTENT_W - 422, align: 'right', font: 'F4' }
            ],
            bills.map(b => [
                b.name,
                b.category || 'Fixed',
                `Day ${b.dueDay || 1}`,
                fmtIdr(b.amountIdr || 0),
                { text: b.paidThisMonth ? 'PAID' : (b.isDueSoon ? 'DUE SOON' : 'UPCOMING'), color: b.paidThisMonth ? GREEN : (b.isDueSoon ? RED : ORANGE), font: 'F4' }
            ])
        );
    }

    // Section 5: Recent Ledger Entries
    doc.drawSectionTitle(`5. GENERAL LEDGER AUDIT TRAIL (RECENT ${txs.length} ENTRIES)`);
    doc.drawTable(
        [
            { label: 'DATE', w: 62, align: 'left', font: 'F3' },
            { label: 'TYPE', w: 58, align: 'left', font: 'F4' },
            { label: 'CATEGORY', w: 112, align: 'left', font: 'F1' },
            { label: 'DESCRIPTION', w: 185, align: 'left', font: 'F1' },
            { label: 'AMOUNT (IDR)', w: CONTENT_W - 417, align: 'right', font: 'F4' }
        ],
        txs.map(t => [
            t.date || '-',
            { text: t.type || '-', color: t.type === 'INCOME' ? GREEN : (t.type === 'EXPENSE' ? RED : ORANGE), font: 'F4' },
            t.category || '-',
            t.note || '-',
            { text: `${t.type === 'EXPENSE' ? '-' : (t.type === 'TRANSFER' ? '' : '+')}${fmtIdr(t.amountIdr || 0)}`, color: t.type === 'EXPENSE' ? RED : (t.type === 'INCOME' ? GREEN : DARK), font: 'F4' }
        ]),
        'No ledger transactions recorded.'
    );

    const safeMonth = String(monthKey).replace(/[^0-9A-Za-z_-]/g, '');
    return {
        filename: `Bloomberg_FamilyOffice_CFO_Report_${safeMonth}.pdf`,
        buffer: doc.buildBuffer()
    };
}

module.exports = {
    buildMonthlyStatementPdf,
    buildDmaTradeConfirmPdf,
    buildEmsxBlotterPdf,
    buildPersonalCfoReportPdf
};
