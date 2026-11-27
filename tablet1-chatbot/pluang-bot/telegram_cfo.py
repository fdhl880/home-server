"""
===========================================================================
BLOOMBERG SINGLE FAMILY OFFICE & PERSONAL CFO — TELEGRAM CHAT BRIDGE
===========================================================================
Menghubungkan bot Telegram (@idrisginting_bot) langsung ke mesin keuangan
pribadi FIN <GO> pada server lokal (http://127.0.0.1:4000/api/finance/*)
sehingga user cukup chat santai dalam bahasa Indonesia:

  - Catat pengeluaran : "makan 15rb", "bensin 20k", "kopi 12rb", "/keluar 30rb buku"
  - Catat pemasukan   : "gaji 1jt", "masuk 250rb freelance", "/masuk 500rb"
  - Tabung / Invest   : "nabung 150rb darurat", "invest 250rb", "/nabung 200rb"
  - Pindah rekening   : "pindah 50rb ke darurat", "transfer 100rb ke invest"
  - Cek ringkasan     : "/uang", "cek uang", "neraca", "sisa budget"
  - Tanya Tim CFO     : "boleh beli sepatu 250rb ga?", "apakah futures aman?", "/tanya ..."
  - Tagihan / Aset    : "/tagihan Kuota 65rb tgl 25", "/aset Emas 3.2jt", "/hutang Cicilan 500rb 100rb"
  - Laporan PDF       : "/pdf", "kirim pdf keuangan", "/email_cfo"
  - Batalkan terakhir : "/undo"
===========================================================================
"""
import os
import re
import html
import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _esc(val):
    return html.escape(str("" if val is None else val), quote=False)


def _fmt_idr(v):
    try:
        n = int(round(float(v or 0)))
    except Exception:
        n = 0
    sign = "-Rp " if n < 0 else "Rp "
    return f"{sign}{abs(n):,}".replace(",", ".")


def get_terminal_base_url():
    port = str(os.getenv("PORT", "4000")).strip() or "4000"
    return str(os.getenv("TERMINAL_BASE_URL", f"http://127.0.0.1:{port}")).rstrip("/")


def get_dash_token():
    env_tok = str(os.getenv("DASH_TOKEN", "")).strip()
    if env_tok:
        return env_tok
    tok_path = os.path.join(BASE_DIR, ".dash_token")
    if os.path.exists(tok_path):
        try:
            with open(tok_path, "r", encoding="utf-8") as f:
                val = f.read().strip()
                if val:
                    return val
        except Exception:
            pass
    return ""


def _auth_headers():
    tok = get_dash_token()
    h = {"Content-Type": "application/json"}
    if tok:
        h["X-Dash-Token"] = tok
    return h


def cfo_api(method, path, payload=None, timeout=15, raw=False):
    url = get_terminal_base_url() + path
    try:
        r = requests.request(
            method.upper(),
            url,
            headers=_auth_headers(),
            json=payload if payload is not None else None,
            timeout=timeout,
        )
        if raw:
            return r.status_code, r.content, dict(r.headers)
        try:
            data = r.json()
        except Exception:
            data = {"ok": False, "error": f"Non-JSON response (HTTP {r.status_code})"}
        return r.status_code, data, dict(r.headers)
    except Exception as e:
        if raw:
            return 0, b"", {"error": str(e)}
        return 0, {"ok": False, "error": f"Server Terminal (port 4000) tidak merespons: {e}"}, {}


def send_telegram_document(tele_api_base, chat_id, filename, content_bytes, caption=""):
    url = f"{tele_api_base}/sendDocument"
    try:
        files = {"document": (filename, content_bytes, "application/pdf")}
        data = {"chat_id": chat_id}
        if caption:
            data["caption"] = caption[:1000]
            data["parse_mode"] = "HTML"
        r = requests.post(url, data=data, files=files, timeout=25)
        return r.json() if r.content else None
    except Exception as e:
        print(f"[-] Telegram sendDocument error: {e}")
        return None


# ===========================================================================
# INDONESIAN AMOUNT & NATURAL-LANGUAGE INTENT PARSER
# ===========================================================================
_AMOUNT_RE = re.compile(
    r"(?:rp\.?\s*)?(\d+(?:[.,]\d+)?)\s*(jt|juta|miliar|milyar|rb|ribu|k)?\b",
    re.IGNORECASE,
)


def parse_idr_amount(raw_text):
    """Extract rupiah amount from Indonesian text: '15rb', '1.5jt', '20k', '50.000', '25000'."""
    if not raw_text:
        return None
    text = str(raw_text)
    # Ignore dates like tgl 25 / tanggal 25 when scanning for rupiah amounts
    cleaned = re.sub(r"\b(?:tgl|tanggal|hari|day)\s*\d{1,2}\b", " ", text, flags=re.IGNORECASE)
    for m in _AMOUNT_RE.finditer(cleaned):
        num_str = m.group(1)
        unit = (m.group(2) or "").lower()
        try:
            if unit in ("jt", "juta", "miliar", "milyar", "rb", "ribu", "k"):
                # Decimal separator like 1.5jt or 1,5jt
                if "," in num_str and "." not in num_str:
                    val = float(num_str.replace(",", "."))
                elif num_str.count(".") == 1 and len(num_str.split(".")[1]) != 3:
                    val = float(num_str)
                else:
                    val = float(num_str.replace(".", "").replace(",", "."))
            else:
                # Plain number: 50.000 or 50,000 or 25000
                if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", num_str):
                    val = float(num_str.replace(".", "").replace(",", ""))
                else:
                    val = float(num_str.replace(",", "."))
        except Exception:
            continue

        if unit in ("jt", "juta"):
            val *= 1_000_000
        elif unit in ("miliar", "milyar"):
            val *= 1_000_000_000
        elif unit in ("rb", "ribu", "k"):
            val *= 1_000

        amt = int(round(val))
        # Avoid mistaking small standalone numbers like "2" (quantity) for rupiah
        if amt >= 500 or (unit in ("rb", "ribu", "k", "jt", "juta", "miliar", "milyar") and amt >= 100):
            return amt
    return None


def _strip_amount_and_keywords(text, keywords):
    s = str(text or "")
    s = _AMOUNT_RE.sub(" ", s, count=1)
    for kw in keywords:
        s = re.sub(rf"\b{re.escape(kw)}\b", " ", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+", " ", s).strip(" -:,.")
    return s


def infer_expense_category(text):
    low = str(text or "").lower()
    if any(w in low for w in (
        "makan", "minum", "kopi", "coffee", "jajan", "sarapan", "lunch", "dinner",
        "nasi", "bakso", "mie", "ayam", "cafe", "roti", "snack", "es ", "teh", "warteg", "gofood", "grabfood"
    )):
        return "Food & Refreshments"
    if any(w in low for w in (
        "bensin", "bbm", "pertalite", "pertamax", "gojek", "grab", "ojol", "ojek",
        "parkir", "tol", "kereta", "krl", "mrt", "bus", "transjakarta", "transport", "ongkos", "servis motor"
    )):
        return "Transportation"
    if any(w in low for w in (
        "kuota", "pulsa", "wifi", "internet", "listrik", "token", "air", "pdam",
        "kos", "kontrakan", "sewa", "langganan", "netflix", "spotify", "icloud", "tagihan", "cicilan", "bpjs"
    )):
        return "Fixed Bills"
    return "Other Operating"


def _resolve_vault_target(text):
    low = str(text or "").lower()
    if any(w in low for w in ("darurat", "emergency", "emg", "cadangan", "aman")):
        return "ACC-EMG"
    if any(w in low for w in ("invest", "saham", "emas", "rdpu", "tabung", "nabung", "inv")):
        return "ACC-INV"
    if any(w in low for w in ("dompet", "ewallet", "e-wallet", "gopay", "ovo", "dana", "shopeepay", "qris", "cash", "tunai")):
        return "ACC-WALLET"
    return "ACC-OPS"


def parse_finance_chat(msg_text):
    """
    Parse Telegram command or natural Indonesian sentence into a structured finance action.
    Returns None if the message is NOT a personal-finance intent (so trading bot handles it).
    """
    raw = str(msg_text or "").strip()
    if not raw:
        return None
    low = raw.lower().strip()

    # 1. Explicit slash commands (highest priority)
    if low in ("/uang", "/fin", "/keuangan", "/neraca", "/budget", "/dompet"):
        return {"action": "SUMMARY"}
    if low in ("/panduan", "/cara", "/cara_pakai", "/carapakai", "/guide", "/help_uang"):
        return {"action": "GUIDE"}
    if low in ("/pdf", "/cfo_pdf", "/pdf_keuangan", "/laporan_keuangan", "/laporan"):
        return {"action": "PDF"}
    if low in ("/email_cfo", "/kirim_email_cfo"):
        return {"action": "EMAIL_PDF"}
    if low in ("/undo", "/batal_tx"):
        return {"action": "UNDO"}
    if low in ("/tagihan", "/bills"):
        return {"action": "LIST_BILLS"}
    if low in ("/cfo", "/audit_uang"):
        return {"action": "CFO_ASK", "question": "Full Family Office Financial Health Review"}
    if low.startswith("/tanya ") or low.startswith("/cfo "):
        q = raw.split(" ", 1)[1].strip()
        return {"action": "CFO_ASK", "question": q}
    if low.startswith("/buffett"):
        amt = parse_idr_amount(raw) or 1_000_000
        return {"action": "BUFFETT", "amount": amt, "record_cycle": True}
    if low.startswith("/keluar") or low.startswith("/jajan") or low.startswith("/spent") or low.startswith("/pengeluaran"):
        amt = parse_idr_amount(raw)
        if not amt:
            return {"action": "NEED_AMOUNT", "hint": "Contoh: <code>/keluar 15rb makan siang</code> atau langsung ketik <code>makan 15rb</code>"}
        note = _strip_amount_and_keywords(raw, ["/keluar", "/jajan", "/spent", "/pengeluaran"])
        return {"action": "TX", "type": "EXPENSE", "amount": amt, "category": infer_expense_category(raw), "note": note or "Pengeluaran via Telegram"}
    if low.startswith("/masuk") or low.startswith("/gaji") or low.startswith("/income") or low.startswith("/pemasukan"):
        amt = parse_idr_amount(raw)
        if not amt:
            return {"action": "NEED_AMOUNT", "hint": "Contoh: <code>/masuk 1jt uang bulanan</code> atau langsung ketik <code>gaji 1jt</code>"}
        note = _strip_amount_and_keywords(raw, ["/masuk", "/gaji", "/income", "/pemasukan"])
        cat = "Trading Realized Profit" if "profit" in low or "trading" in low else ("Monthly Fixed Allowance" if any(w in low for w in ("gaji", "bulanan", "uang saku")) else "Additional Income")
        return {"action": "TX", "type": "INCOME", "amount": amt, "category": cat, "note": note or "Pemasukan via Telegram"}
    if low.startswith("/nabung") or low.startswith("/simpan") or low.startswith("/invest") or low.startswith("/tabung"):
        amt = parse_idr_amount(raw)
        if not amt:
            return {"action": "NEED_AMOUNT", "hint": "Contoh: <code>/nabung 150rb darurat</code> atau <code>/invest 250rb</code>"}
        is_emg = any(w in low for w in ("darurat", "emergency", "cadangan", "safety"))
        cat = "Emergency Margin of Safety" if is_emg else "Productive Investment Capital"
        to_acc = "ACC-EMG" if is_emg else "ACC-INV"
        note = _strip_amount_and_keywords(raw, ["/nabung", "/simpan", "/invest", "/tabung"])
        return {"action": "TX", "type": "SAVINGS", "amount": amt, "category": cat, "accountId": "ACC-OPS", "toAccountId": to_acc, "note": note or cat}
    if low.startswith("/pindah") or low.startswith("/geser"):
        amt = parse_idr_amount(raw)
        if not amt:
            return {"action": "NEED_AMOUNT", "hint": "Contoh: <code>/pindah 50rb darurat</code> atau <code>pindah 100rb ke invest</code>"}
        to_acc = _resolve_vault_target(raw)
        from_acc = "ACC-EMG" if (to_acc == "ACC-OPS" and "darurat" in low) else "ACC-OPS"
        if from_acc == to_acc:
            to_acc = "ACC-EMG"
        return {"action": "TX", "type": "TRANSFER", "amount": amt, "accountId": from_acc, "toAccountId": to_acc, "note": raw}
    if low.startswith("/aset "):
        rest = raw.split(" ", 1)[1].strip()
        amt = parse_idr_amount(rest)
        if not amt:
            return {"action": "NEED_AMOUNT", "hint": "Contoh: <code>/aset Emas Antam 2g 3.2jt</code>"}
        name = _strip_amount_and_keywords(rest, []) or "External Asset"
        cat = "LIQUID" if any(w in low for w in ("kas", "bank", "rdpu", "deposito")) else ("FIXED" if any(w in low for w in ("laptop", "motor", "hp", "rumah", "tanah")) else "INVESTMENT")
        return {"action": "ADD_ASSET", "name": name, "category": cat, "valueIdr": amt}
    if low.startswith("/hutang ") or low.startswith("/cicilan "):
        rest = raw.split(" ", 1)[1].strip()
        # Extract up to 2 amounts (principal, optional monthly payment)
        matches = list(_AMOUNT_RE.finditer(rest))
        amts = []
        for m in matches:
            v = parse_idr_amount(m.group(0))
            if v:
                amts.append(v)
        if not amts:
            return {"action": "NEED_AMOUNT", "hint": "Contoh: <code>/hutang PayLater 500rb 100rb</code> (nama, total hutang, cicilan/bulan)"}
        name = _AMOUNT_RE.sub(" ", rest).strip(" -:,.") or "Personal Liability"
        return {"action": "ADD_LIABILITY", "name": name, "principalIdr": amts[0], "monthlyPaymentIdr": amts[1] if len(amts) > 1 else 0}
    if low.startswith("/tagihan "):
        rest = raw.split(" ", 1)[1].strip()
        amt = parse_idr_amount(rest)
        if not amt:
            return {"action": "NEED_AMOUNT", "hint": "Contoh: <code>/tagihan Kuota Internet 65rb tgl 25</code>"}
        dm = re.search(r"\b(?:tgl|tanggal|day)\s*(\d{1,2})\b", rest, flags=re.IGNORECASE)
        due_day = max(1, min(31, int(dm.group(1)))) if dm else 1
        name = re.sub(r"\b(?:tgl|tanggal|day)\s*\d{1,2}\b", " ", rest, flags=re.IGNORECASE)
        name = _AMOUNT_RE.sub(" ", name).strip(" -:,.") or "Tagihan Bulanan"
        return {"action": "ADD_BILL", "name": name, "amountIdr": amt, "dueDay": due_day}

    # Skip slash commands belonging to crypto trading bot
    if low.startswith("/"):
        return None

    # 2. Natural-language Indonesian chat routing
    if any(p in low for p in ("cara pakai", "cara pake", "ga ngerti", "gak ngerti", "bingung pake", "panduan keuangan")):
        return {"action": "GUIDE"}
    if any(p in low for p in ("kirim pdf", "pdf keuangan", "laporan pdf", "cfo pdf", "laporan keuangan", "report keuangan")):
        return {"action": "PDF"}
    if any(p in low for p in ("email laporan", "kirim email keuangan", "email cfo")):
        return {"action": "EMAIL_PDF"}
    if any(p in low for p in ("batal transaksi", "batalkan transaksi", "hapus transaksi terakhir", "undo keuangan")):
        return {"action": "UNDO"}
    if any(p in low for p in ("cek tagihan", "daftar tagihan", "tagihan bulan ini")):
        return {"action": "LIST_BILLS"}
    if any(p in low for p in (
        "cek uang", "uangku", "uang aku", "kondisi keuangan", "keuangan aku", "keuanganku",
        "sisa budget", "jatah hari ini", "sisa jatah", "cek budget", "neraca pribadi", "total kekayaan", "saldo pribadi"
    )):
        return {"action": "SUMMARY"}

    # Question / Consultation check BEFORE transaction booking (so "boleh beli 200rb ga?" asks CFO!)
    is_question = (
        "?" in raw
        or bool(re.search(r"\b(boleh|aman|mampu|wajar|saran|gimana|bagaimana|berapa|strategi|audit|menurut|rekomendasi|cukup)\b", low))
    )
    is_fin_topic = bool(re.search(
        r"\b(uang|duit|budget|gaji|beli|pengeluaran|boros|hemat|tabung|nabung|darurat|hutang|cicilan|tagihan|invest|10\s*jt|10\s*juta|100\s*jt|1\s*m|kekayaan|neraca|cfo|runway|keuangan|futures)\b",
        low,
    ))
    if is_question and is_fin_topic:
        return {"action": "CFO_ASK", "question": raw}

    # Natural Transfer: "pindah 50rb ke darurat" / "transfer 100k ke invest"
    if re.search(r"\b(pindah|geser|transfer|tarik)\b", low) and re.search(r"\b(darurat|emergency|invest|tabung|dompet|ewallet|rekening|vault)\b", low):
        amt = parse_idr_amount(raw)
        if amt:
            to_acc = _resolve_vault_target(raw)
            from_acc = "ACC-EMG" if (to_acc == "ACC-OPS" and "darurat" in low) else "ACC-OPS"
            if from_acc == to_acc:
                to_acc = "ACC-EMG"
            return {"action": "TX", "type": "TRANSFER", "amount": amt, "accountId": from_acc, "toAccountId": to_acc, "note": raw}

    # Natural Buffett command: "buffett 1jt" / "atur gaji 1.5jt"
    if re.search(r"\b(buffett|atur gaji|bagi gaji|alokasi gaji)\b", low):
        amt = parse_idr_amount(raw)
        if amt:
            return {"action": "BUFFETT", "amount": amt, "record_cycle": True}

    # Natural Savings: "nabung 150rb", "simpan 200rb darurat", "tabung 50k"
    if re.search(r"\b(nabung|tabung|simpan|sisihkan|kunci)\b", low):
        amt = parse_idr_amount(raw)
        if amt:
            is_emg = any(w in low for w in ("darurat", "emergency", "cadangan"))
            cat = "Emergency Margin of Safety" if is_emg else "Productive Investment Capital"
            return {"action": "TX", "type": "SAVINGS", "amount": amt, "category": cat, "accountId": "ACC-OPS", "toAccountId": "ACC-EMG" if is_emg else "ACC-INV", "note": raw}

    # Natural Income: "gaji 1jt", "dapat 200rb", "uang bulanan 1jt", "masuk 500rb"
    if re.search(r"\b(gaji|gajian|pemasukan|income|uang bulanan|uang saku|dapat uang|terima|masuk|profit)\b", low):
        amt = parse_idr_amount(raw)
        if amt:
            cat = "Trading Realized Profit" if "profit" in low else ("Monthly Fixed Allowance" if any(w in low for w in ("gaji", "bulanan", "saku")) else "Additional Income")
            return {"action": "TX", "type": "INCOME", "amount": amt, "category": cat, "note": raw}

    # Natural Expense: "makan 15rb", "bensin 20k", "kopi 12rb", "beli buku 30rb", "bayar kuota 50rb"
    if re.search(
        r"\b(makan|minum|kopi|coffee|jajan|sarapan|nasi|bakso|mie|ayam|snack|warteg|gofood|grabfood|"
        r"bensin|bbm|gojek|grab|ojol|ojek|parkir|tol|kereta|bus|ongkos|"
        r"kuota|pulsa|wifi|listrik|kos|sewa|beli|bayar|keluar|habis|belanja)\b",
        low,
    ):
        amt = parse_idr_amount(raw)
        if amt:
            return {"action": "TX", "type": "EXPENSE", "amount": amt, "category": infer_expense_category(raw), "note": raw}

    return None


# ===========================================================================
# TELEGRAM RESPONSE FORMATTERS & EXECUTOR
# ===========================================================================
def _cfo_keyboard():
    return {
        "inline_keyboard": [
            [
                {"text": "📊 Ringkasan & Neraca", "callback_data": "cfo_summary"},
                {"text": "📄 Kirim PDF Report", "callback_data": "cfo_pdf"},
            ],
            [
                {"text": "🧠 Audit Tim CFO", "callback_data": "cfo_audit"},
                {"text": "📅 Cek Tagihan", "callback_data": "cfo_bills"},
            ],
            [
                {"text": "📧 Kirim PDF ke Email", "callback_data": "cfo_email"},
                {"text": "↩️ Undo Terakhir", "callback_data": "cfo_undo"},
            ],
        ]
    }


def format_summary_message(fin_data):
    s = fin_data.get("summary") or {}
    fo = s.get("familyOffice") or {}
    bs = fo.get("balanceSheet") or {}
    r = fo.get("ratios") or {}
    accounts = fo.get("accounts") or []
    team = fo.get("cfoTeam") or []

    grade = fo.get("healthGrade", "A")
    score = fo.get("healthScore", 85)
    runway = float(r.get("emergencyRunwayMonths", 0) or 0)
    nw = bs.get("trueNetWorthIdr", s.get("totalIntegratedWealthIdr", 0))

    acc_lines = []
    for a in accounts:
        bal = _fmt_idr(a.get("balanceIdr", 0))
        extra = f" (${a.get('balanceUsd', 0):.2f})" if a.get("balanceUsd") is not None else ""
        acc_lines.append(f"  • <b>{_esc(a.get('name'))}:</b> {bal}{extra}")

    top_dir = team[0].get("directive", "-") if team else "-"
    cro_dir = team[2].get("directive", "-") if len(team) >= 3 else "-"

    return (
        f"🏛️ <b>BLOOMBERG FAMILY OFFICE — TIM KEUANGAN PRIBADI</b>\n"
        f"────────────────────────\n"
        f"🏅 <b>Health Grade:</b> <b>{_esc(grade)}</b> ({score}/100) | <b>Disiplin:</b> {s.get('disciplineScore', 100)}/100\n"
        f"💎 <b>True Net Worth:</b> <b>{_fmt_idr(nw)}</b>\n"
        f"   <i>(Aset {_fmt_idr(bs.get('totalAssetsIdr', nw))} − Hutang {_fmt_idr(bs.get('totalLiabilitiesIdr', 0))})</i>\n"
        f"🛡️ <b>Emergency Runway:</b> <b>{runway:.1f} bulan</b> (Target ≥ 6.0 bln)\n"
        f"────────────────────────\n"
        f"💵 <b>Jatah Hari Ini:</b> {_fmt_idr(s.get('remainingTodayIdr', 0))} sisa "
        f"<i>(Terpakai {_fmt_idr(s.get('todayExpense', 0))} / {_fmt_idr(s.get('dailyLimitIdr', 20000))})</i>\n"
        f"🧭 <b>Batas Aman Harian:</b> <b>{_fmt_idr(s.get('dynamicSafeDailyIdr', 0))}/hari</b> "
        f"<i>({s.get('remainingDays', 1)} hari tersisa)</i>\n"
        f"📆 <b>Bulan Ini:</b> Keluar {_fmt_idr(s.get('monthExpense', 0))} / {_fmt_idr(s.get('monthlyBudgetIdr', 600000))} "
        f"| Tabung: {s.get('savingsRatePct', 0)}%\n"
        f"────────────────────────\n"
        f"🏦 <b>Saldo Rekening &amp; Vault:</b>\n"
        + "\n".join(acc_lines)
        + "\n────────────────────────\n"
        f"👔 <b>Arahan CFO:</b> <i>{_esc(top_dir)}</i>\n"
        f"🛡️ <b>Arahan Risk Officer:</b> <i>{_esc(cro_dir)}</i>\n\n"
        f"<i>Ketik santai aja: <code>makan 15rb</code>, <code>bensin 20k</code>, <code>nabung 100rb</code>, "
        f"<code>boleh beli sepatu 250rb ga?</code>, atau <code>/panduan</code>.</i>"
    )


def format_guide_message():
    return (
        "📘 <b>CARA PAKAI TIM KEUANGAN PRIBADI (SUPER SIMPEL)</b>\n"
        "────────────────────────\n"
        "Kamu <b>TIDAK PERLU</b> hafal menu ribet — cukup chat santai di sini setiap ada transaksi, otomatis tersinkron ke <code>FIN &lt;GO&gt;</code> di Terminal!\n\n"
        "<b>1️⃣ Catat Pengeluaran (Cukup Ketik Biasa):</b>\n"
        "• <code>makan 15rb</code>\n"
        "• <code>kopi 12k</code>\n"
        "• <code>bensin 20rb</code>\n"
        "• <code>kuota 50rb</code>\n"
        "• <code>/keluar 35rb beli buku</code>\n\n"
        "<b>2️⃣ Catat Pemasukan / Uang Bulanan:</b>\n"
        "• <code>gaji 1jt</code>  atau  <code>uang bulanan 1jt</code>\n"
        "• <code>/buffett 1jt</code> (otomatis bagi 40% tabungan/investasi + 60% belanja Rp 20rb/hari)\n\n"
        "<b>3️⃣ Nabung &amp; Pindah Rekening (Tidak Dihitung Boros):</b>\n"
        "• <code>nabung 150rb darurat</code>\n"
        "• <code>invest 250rb</code>\n"
        "• <code>pindah 50rb ke darurat</code>\n\n"
        "<b>4️⃣ Catat Neraca (Aset, Hutang, Tagihan Bulanan):</b>\n"
        "• <code>/aset Emas Antam 2g 3.2jt</code>\n"
        "• <code>/hutang PayLater 500rb 100rb</code>\n"
        "• <code>/tagihan Kuota 65rb tgl 25</code>  |  <code>/tagihan</code> (bayar 1 klik)\n\n"
        "<b>5️⃣ Konsultasi Langsung ke Tim CFO Kamu:</b>\n"
        "• <code>boleh beli headset 200rb bulan ini ga?</code>\n"
        "• <code>apakah modal futures aku aman?</code>\n"
        "• <code>strategi tercepat tembus 10 juta?</code>\n\n"
        "<b>6️⃣ Cek Saldo, PDF &amp; Undo Salah Ketik:</b>\n"
        "• <code>/uang</code> — Ringkasan lengkap + saldo tiap rekening\n"
        "• <code>/pdf</code> — Kirim laporan PDF resmi langsung ke chat ini\n"
        "• <code>/email_cfo</code> — Kirim laporan PDF ke email kamu\n"
        "• <code>/undo</code> — Batalkan transaksi terakhir jika salah ketik"
    )


def handle_finance_action(intent, chat_id, send_msg_fn, tele_api_base):
    """Execute a parsed finance intent against the local Terminal API and reply on Telegram."""
    act = intent.get("action")

    if act == "GUIDE":
        send_msg_fn(chat_id, format_guide_message(), reply_markup=_cfo_keyboard())
        return

    if act == "NEED_AMOUNT":
        send_msg_fn(chat_id, f"ℹ️ <b>Nominal belum terbaca.</b>\n{intent.get('hint', '')}")
        return

    if act == "SUMMARY":
        code, data, _ = cfo_api("GET", "/api/finance")
        if code != 200 or not data.get("ok"):
            send_msg_fn(chat_id, f"❌ Gagal membaca data keuangan: <code>{_esc(data.get('error', f'HTTP {code}'))}</code>")
            return
        send_msg_fn(chat_id, format_summary_message(data.get("data") or {}), reply_markup=_cfo_keyboard())
        return

    if act == "TX":
        payload = {
            "type": intent["type"],
            "amountIdr": intent["amount"],
            "category": intent.get("category") or "Other Operating",
            "note": intent.get("note") or "",
        }
        if intent.get("accountId"):
            payload["accountId"] = intent["accountId"]
        if intent.get("toAccountId"):
            payload["toAccountId"] = intent["toAccountId"]
        code, data, _ = cfo_api("POST", "/api/finance/tx", payload)
        if code != 200 or not data.get("ok"):
            send_msg_fn(chat_id, f"❌ Gagal mencatat transaksi: <code>{_esc(data.get('error', f'HTTP {code}'))}</code>")
            return
        fin = data.get("data") or {}
        s = fin.get("summary") or {}
        fo = s.get("familyOffice") or {}
        bs = fo.get("balanceSheet") or {}
        t = intent["type"]
        if t == "TRANSFER":
            msg = (
                f"🔁 <b>TRANSFER REKENING TERCATAT</b>\n"
                f"• Nominal: <b>{_fmt_idr(intent['amount'])}</b>\n"
                f"• Rute: <code>{_esc(intent.get('accountId'))}</code> ➔ <code>{_esc(intent.get('toAccountId'))}</code>\n"
                f"• <i>Tidak dihitung pengeluaran / tidak ganggu limit harian.</i>\n"
                f"• True Net Worth: <b>{_fmt_idr(bs.get('trueNetWorthIdr', 0))}</b>"
            )
        elif t == "INCOME":
            msg = (
                f"🟢 <b>PEMASUKAN TERCATAT</b>\n"
                f"• Nominal: <b>+{_fmt_idr(intent['amount'])}</b> ({_esc(intent.get('category'))})\n"
                f"• Catatan: <i>{_esc(intent.get('note'))}</i>\n"
                f"• Total Bank: <b>{_fmt_idr(s.get('bankTotalIdr', 0))}</b> | Net Worth: <b>{_fmt_idr(bs.get('trueNetWorthIdr', 0))}</b>\n\n"
                f"💡 <i>Mau langsung dibagi otomatis ala Warren Buffett 40/60? Ketik <code>/buffett {intent['amount']}</code></i>"
            )
        elif t == "SAVINGS":
            msg = (
                f"🏦 <b>TABUNGAN / KUNCI MODAL TERCATAT</b>\n"
                f"• Nominal: <b>+{_fmt_idr(intent['amount'])}</b> ({_esc(intent.get('category'))})\n"
                f"• Dana Darurat Vault: <b>{_fmt_idr(bs.get('emergencyFundIdr', 0))}</b> | Invest Vault: <b>{_fmt_idr(bs.get('investmentVaultIdr', 0))}</b>\n"
                f"• Emergency Runway: <b>{float((fo.get('ratios') or {}).get('emergencyRunwayMonths', 0)):.1f} bulan</b>"
            )
        else:
            rem_today = int(s.get("remainingTodayIdr", 0) or 0)
            over_warn = (
                f"\n⚠️ <b>PERINGATAN CFO:</b> Limit harian ({_fmt_idr(s.get('dailyLimitIdr', 20000))}) terlampaui <b>{_fmt_idr(abs(rem_today))}</b>!"
                if rem_today < 0
                else f"\n✅ Sisa jatah hari ini: <b>{_fmt_idr(rem_today)}</b>"
            )
            msg = (
                f"🧾 <b>PENGELUARAN TERCATAT</b>\n"
                f"• Nominal: <b>-{_fmt_idr(intent['amount'])}</b>\n"
                f"• Kategori: <b>{_esc(intent.get('category'))}</b>\n"
                f"• Catatan: <i>{_esc(intent.get('note'))}</i>"
                f"{over_warn}\n"
                f"• Batas Aman Harian Baru: <b>{_fmt_idr(s.get('dynamicSafeDailyIdr', 0))}/hari</b>\n"
                f"• Sisa Bulan Ini: <b>{_fmt_idr(s.get('remainingMonthIdr', 0))}</b> (Disiplin: {s.get('disciplineScore', 100)}/100)\n"
                f"<i>Salah ketik? Ketik <code>/undo</code></i>"
            )
        send_msg_fn(chat_id, msg)
        return

    if act == "BUFFETT":
        code, data, _ = cfo_api(
            "POST",
            "/api/finance/buffett-apply",
            {"monthlyIncomeIdr": intent["amount"], "recordMonthlyCycle": bool(intent.get("record_cycle", True))},
        )
        if code != 200 or not data.get("ok"):
            send_msg_fn(chat_id, f"❌ Gagal menjalankan Warren Buffett Auto-Split: <code>{_esc(data.get('error', f'HTTP {code}'))}</code>")
            return
        p = data.get("plan") or {}
        send_msg_fn(
            chat_id,
            f"🏛️ <b>WARREN BUFFETT 40/60 AUTO-CYCLE AKTIF!</b>\n"
            f"────────────────────────\n"
            f"💵 <b>Pemasukan Bulanan:</b> {_fmt_idr(p.get('monthlyIncomeIdr', 0))}\n"
            f"🔒 <b>Pay-Yourself-First (40% Dikunci Dulu):</b> {_fmt_idr(p.get('payYourselfFirstIdr', 0))}\n"
            f"   • Investasi Produktif (25%): {_fmt_idr(round(p.get('monthlyIncomeIdr', 0) * 0.25))}\n"
            f"   • Dana Darurat (15%): {_fmt_idr(round(p.get('monthlyIncomeIdr', 0) * 0.15))}\n"
            f"🍽️ <b>Budget Operasional (60%):</b> {_fmt_idr(p.get('spendableMonthlyIdr', 0))}\n"
            f"🧭 <b>Batas Belanja Harian:</b> <b>{_fmt_idr(p.get('dailyLimitIdr', 0))}/hari</b>",
            reply_markup=_cfo_keyboard(),
        )
        return

    if act == "ADD_ASSET":
        code, data, _ = cfo_api("POST", "/api/finance/asset", {
            "name": intent["name"],
            "category": intent["category"],
            "valueIdr": intent["valueIdr"],
        })
        if code != 200 or not data.get("ok"):
            send_msg_fn(chat_id, f"❌ Gagal tambah aset: <code>{_esc(data.get('error', f'HTTP {code}'))}</code>")
            return
        bs = ((data.get("data") or {}).get("summary") or {}).get("familyOffice", {}).get("balanceSheet", {})
        send_msg_fn(
            chat_id,
            f"💎 <b>ASET TERCATAT DI NERACA</b>\n"
            f"• Aset: <b>{_esc(intent['name'])}</b> ({_esc(intent['category'])})\n"
            f"• Nilai: <b>{_fmt_idr(intent['valueIdr'])}</b>\n"
            f"• True Net Worth Baru: <b>{_fmt_idr(bs.get('trueNetWorthIdr', 0))}</b>",
        )
        return

    if act == "ADD_LIABILITY":
        code, data, _ = cfo_api("POST", "/api/finance/liability", {
            "name": intent["name"],
            "principalIdr": intent["principalIdr"],
            "monthlyPaymentIdr": intent.get("monthlyPaymentIdr", 0),
        })
        if code != 200 or not data.get("ok"):
            send_msg_fn(chat_id, f"❌ Gagal catat hutang: <code>{_esc(data.get('error', f'HTTP {code}'))}</code>")
            return
        fo = ((data.get("data") or {}).get("summary") or {}).get("familyOffice", {})
        bs = fo.get("balanceSheet", {})
        r = fo.get("ratios", {})
        send_msg_fn(
            chat_id,
            f"📉 <b>LIABILITAS TERCATAT DI NERACA</b>\n"
            f"• Hutang/Cicilan: <b>{_esc(intent['name'])}</b>\n"
            f"• Pokok: <b>{_fmt_idr(intent['principalIdr'])}</b> | Cicilan/bln: {_fmt_idr(intent.get('monthlyPaymentIdr', 0))}\n"
            f"• Debt/Asset: <b>{float(r.get('debtToAssetPct', 0)):.1f}%</b> | True Net Worth: <b>{_fmt_idr(bs.get('trueNetWorthIdr', 0))}</b>",
        )
        return

    if act == "ADD_BILL":
        code, data, _ = cfo_api("POST", "/api/finance/bill", {
            "name": intent["name"],
            "amountIdr": intent["amountIdr"],
            "dueDay": intent["dueDay"],
            "category": "Fixed Bills",
        })
        if code != 200 or not data.get("ok"):
            send_msg_fn(chat_id, f"❌ Gagal simpan tagihan: <code>{_esc(data.get('error', f'HTTP {code}'))}</code>")
            return
        send_msg_fn(
            chat_id,
            f"📅 <b>TAGIHAN RUTIN TERJADWAL</b>\n"
            f"• Tagihan: <b>{_esc(intent['name'])}</b>\n"
            f"• Nominal: <b>{_fmt_idr(intent['amountIdr'])}/bulan</b> (Jatuh tempo tgl {intent['dueDay']})\n"
            f"<i>Ketik <code>/tagihan</code> untuk melihat daftar &amp; bayar 1 klik.</i>",
        )
        return

    if act == "LIST_BILLS":
        code, data, _ = cfo_api("GET", "/api/finance")
        if code != 200 or not data.get("ok"):
            send_msg_fn(chat_id, f"❌ Gagal membaca tagihan: <code>{_esc(data.get('error', f'HTTP {code}'))}</code>")
            return
        fo = ((data.get("data") or {}).get("summary") or {}).get("familyOffice") or {}
        bills = fo.get("recurringBills") or []
        if not bills:
            send_msg_fn(
                chat_id,
                "📅 <b>BELUM ADA TAGIHAN RUTIN</b>\n"
                "Tambahkan contoh: <code>/tagihan Kuota Internet 65rb tgl 25</code>",
            )
            return
        lines = [
            f"📅 <b>DAFTAR TAGIHAN BULANAN ({len(bills)})</b>",
            f"Total: <b>{_fmt_idr(fo.get('totalMonthlyRecurringIdr', 0))}/bln</b> | Belum Bayar: <b>{_fmt_idr(fo.get('unpaidRecurringMonthIdr', 0))}</b>",
            "────────────────────────",
        ]
        kb_rows = []
        for b in bills:
            st = "✅ LUNAS" if b.get("paidThisMonth") else ("🔴 TELAT" if b.get("isOverdue") else ("🟡 SEGERA" if b.get("isDueSoon") else "⏳ JADWAL"))
            lines.append(f"• <b>{_esc(b.get('name'))}</b> — {_fmt_idr(b.get('amountIdr', 0))} (tgl {b.get('dueDay', 1)}) [{st}]")
            if not b.get("paidThisMonth") and b.get("id"):
                kb_rows.append([{"text": f"✅ Bayar {b.get('name')} ({_fmt_idr(b.get('amountIdr', 0))})", "callback_data": f"cfo_paybill_{b.get('id')}"}])
        kb_rows.append([{"text": "📊 Ringkasan Keuangan", "callback_data": "cfo_summary"}])
        send_msg_fn(chat_id, "\n".join(lines), reply_markup={"inline_keyboard": kb_rows})
        return

    if act == "PAY_BILL":
        bill_id = intent.get("bill_id", "")
        code, data, _ = cfo_api("POST", f"/api/finance/bill/{bill_id}/pay", {})
        if code != 200 or not data.get("ok"):
            send_msg_fn(chat_id, f"❌ Gagal membayar tagihan: <code>{_esc(data.get('error', f'HTTP {code}'))}</code>")
            return
        tx = data.get("tx") or {}
        send_msg_fn(
            chat_id,
            f"✅ <b>TAGIHAN LUNAS &amp; TERCATAT</b>\n"
            f"• {_esc(tx.get('note', 'Recurring Bill'))}\n"
            f"• Nominal: <b>-{_fmt_idr(tx.get('amountIdr', 0))}</b>",
            reply_markup=_cfo_keyboard(),
        )
        return

    if act == "CFO_ASK":
        q = intent.get("question") or "Full Family Office Financial Health Review"
        code, data, _ = cfo_api("POST", "/api/finance/cfo-brief", {"question": q}, timeout=20)
        if code != 200 or not data.get("ok"):
            send_msg_fn(chat_id, f"❌ Tim CFO sedang tidak terjangkau: <code>{_esc(data.get('error', f'HTTP {code}'))}</code>")
            return
        memo = data.get("memo") or {}
        officers = memo.get("officers") or []
        lines = [
            f"👔 <b>DECISION MEMO — TIM KEUANGAN PRIBADI (FAMILY OFFICE)</b>",
            f"────────────────────────",
            f"📌 <b>Keputusan:</b> <b>{_esc(memo.get('verdict', 'ADVISORY'))}</b>",
            f"📝 {_esc(memo.get('recommendation', ''))}",
        ]
        if memo.get("aiAdvisory"):
            lines.append("\n🧠 <b>Analisis AI CFO Committee:</b>")
            lines.append(_esc(memo["aiAdvisory"]))
        elif officers:
            lines.append("\n🏛️ <b>Arahan 4 Officer:</b>")
            for o in officers:
                lines.append(f"• <b>{_esc(o.get('role'))} [{_esc(o.get('status'))}]:</b> <i>{_esc(o.get('note'))}</i>")
        send_msg_fn(chat_id, "\n".join(lines), reply_markup=_cfo_keyboard())
        return

    if act == "PDF":
        code, pdf_bytes, headers = cfo_api("GET", "/api/finance/report/pdf", timeout=20, raw=True)
        if code != 200 or not pdf_bytes or not pdf_bytes.startswith(b"%PDF-"):
            send_msg_fn(chat_id, f"❌ Gagal membuat PDF CFO Report (HTTP {code}). Pastikan server.js sedang jalan.")
            return
        cd = headers.get("Content-Disposition") or headers.get("content-disposition") or ""
        m = re.search(r'filename="([^"]+)"', cd)
        fname = m.group(1) if m else "Bloomberg_FamilyOffice_CFO_Report.pdf"
        res = send_telegram_document(
            tele_api_base,
            chat_id,
            fname,
            pdf_bytes,
            caption="📄 <b>Bloomberg Single Family Office — Personal CFO Report (PDF)</b>\n<i>Berisi Neraca, Saldo Vault, Rasio Runway, 4-Officer Directives &amp; Audit Ledger.</i>",
        )
        if not res or not res.get("ok"):
            send_msg_fn(chat_id, "❌ Gagal mengunggah file PDF ke Telegram.")
        return

    if act == "EMAIL_PDF":
        code, data, _ = cfo_api("POST", "/api/finance/report/email", {}, timeout=20)
        if code != 200 or not data.get("ok"):
            send_msg_fn(chat_id, f"❌ Gagal mengirim email CFO Report: <code>{_esc(data.get('error', f'HTTP {code}'))}</code>")
            return
        entry = data.get("entry") or {}
        send_msg_fn(
            chat_id,
            f"📧 <b>LAPORAN CFO PDF DIKIRIM KE EMAIL</b>\n"
            f"• File: <code>{_esc(data.get('filename', 'PDF'))}</code>\n"
            f"• Tujuan: <code>{_esc(entry.get('to', '-'))}</code>\n"
            f"• Status: <i>{_esc(entry.get('status', 'SENT'))}</i>",
        )
        return

    if act == "UNDO":
        code, data, _ = cfo_api("GET", "/api/finance")
        if code != 200 or not data.get("ok"):
            send_msg_fn(chat_id, "❌ Gagal mengambil transaksi terakhir.")
            return
        txs = (data.get("data") or {}).get("transactions") or []
        if not txs:
            send_msg_fn(chat_id, "ℹ️ Tidak ada transaksi untuk dibatalkan.")
            return
        latest = txs[0]
        if str(latest.get("id", "")).startswith("TX-INIT-"):
            send_msg_fn(chat_id, "ℹ️ Transaksi pembuka (opening balance) tidak dihapus otomatis lewat /undo.")
            return
        dcode, ddata, _ = cfo_api("DELETE", f"/api/finance/tx/{latest['id']}")
        if dcode != 200 or not ddata.get("ok"):
            send_msg_fn(chat_id, f"❌ Gagal membatalkan transaksi: <code>{_esc(ddata.get('error', f'HTTP {dcode}'))}</code>")
            return
        send_msg_fn(
            chat_id,
            f"↩️ <b>TRANSAKSI TERAKHIR DIBATALKAN</b>\n"
            f"• {_esc(latest.get('type'))} {_fmt_idr(latest.get('amountIdr', 0))} ({_esc(latest.get('category'))})\n"
            f"• Catatan: <i>{_esc(latest.get('note', '-'))}</i>",
        )
        return


def handle_finance_callback(cb_data, chat_id, cb_id, answer_cb_fn, send_msg_fn, tele_api_base):
    """Handle cfo_* inline button callbacks from Telegram."""
    if not cb_data or not cb_data.startswith("cfo_"):
        return False
    if cb_data == "cfo_summary":
        answer_cb_fn(cb_id, "📊 Memuat ringkasan Family Office...")
        handle_finance_action({"action": "SUMMARY"}, chat_id, send_msg_fn, tele_api_base)
        return True
    if cb_data == "cfo_pdf":
        answer_cb_fn(cb_id, "📄 Membuat & mengirim PDF CFO Report...")
        handle_finance_action({"action": "PDF"}, chat_id, send_msg_fn, tele_api_base)
        return True
    if cb_data == "cfo_email":
        answer_cb_fn(cb_id, "📧 Mengirim CFO Report PDF ke email...")
        handle_finance_action({"action": "EMAIL_PDF"}, chat_id, send_msg_fn, tele_api_base)
        return True
    if cb_data == "cfo_audit":
        answer_cb_fn(cb_id, "🧠 Meminta audit 4-Officer CFO Committee...")
        handle_finance_action({"action": "CFO_ASK", "question": "Full Family Office Financial Health Review"}, chat_id, send_msg_fn, tele_api_base)
        return True
    if cb_data == "cfo_bills":
        answer_cb_fn(cb_id, "📅 Memuat daftar tagihan rutin...")
        handle_finance_action({"action": "LIST_BILLS"}, chat_id, send_msg_fn, tele_api_base)
        return True
    if cb_data == "cfo_undo":
        answer_cb_fn(cb_id, "↩️ Membatalkan transaksi terakhir...")
        handle_finance_action({"action": "UNDO"}, chat_id, send_msg_fn, tele_api_base)
        return True
    if cb_data.startswith("cfo_paybill_"):
        bill_id = cb_data.replace("cfo_paybill_", "", 1).strip()
        answer_cb_fn(cb_id, "✅ Membayar tagihan...")
        handle_finance_action({"action": "PAY_BILL", "bill_id": bill_id}, chat_id, send_msg_fn, tele_api_base)
        return True
    return False
