import os
import json
import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def load_env():
    env_path = os.path.join(BASE_DIR, ".env")
    env = {}
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
    return env

ENV = load_env()
OPENROUTER_API_KEY = ENV.get("OPENROUTER_API_KEY")
MODEL = ENV.get("OPENROUTER_MODEL", "deepseek/deepseek-v4.1-flash")

MAX_BUDGET_IDR = 50_000  # DIKUNCI MATI Rp 50.000

def call_ai(prompt: str, system_prompt: str, max_tokens: int = 1200):
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": max_tokens,
        "temperature": 0.2
    }
    resp = requests.post(url, headers=headers, json=data, timeout=40)
    if resp.status_code != 200:
        raise Exception(f"AI API Error {resp.status_code}: {resp.text}")
    res = resp.json()["choices"][0]["message"]
    content = res.get("content")
    if not content:
        content = res.get("reasoning", "")
    return content

def run_3_tier_analysis(market_data: dict):
    """
    Menjalankan 3 Tingkat Evaluasi Multi-Agent:
    Tier 1: Bullish Analyst (Peluang Keuntungan)
    Tier 2: Bearish Analyst (Audit Risiko & Kerugian)
    Tier 3: Supreme Risk Manager (Hakim / Penilai Ketat)
    """
    symbol = market_data.get("symbol")
    data_summary = json.dumps(market_data, indent=2)

    # -------------------------------------------------------------
    # TIER 1: BULLISH ANALYST (Mencari Sisi Positif & Potensi Cuan)
    # -------------------------------------------------------------
    sys_bull = (
        "Anda adalah 'Bullish Analyst' institusional. Tugas Anda mencari peluang kenaikan harga (upside) "
        "berdasarkan data teknikal (EMA, RSI, Volume, Support). "
        "ATURAN:\n"
        "- Jika RSI > 70, akui bahwa aset sudah overbought dan peluang beli terbatas.\n"
        "- Tentukan level Take Profit (TP) realistis dan level support terdekat.\n"
        "- Jelaskan tesis Bullish dalam Bahasa Indonesia padat dan berbasis data (maksimal 3-4 kalimat)."
    )
    prompt_bull = f"Data Pasar Real-Time untuk {symbol}:\n{data_summary}\n\nJelaskan tesis Bullish Anda secara singkat dan jelas:"
    bull_thesis = call_ai(prompt_bull, sys_bull, max_tokens=1000)

    # -------------------------------------------------------------
    # TIER 2: BEARISH AUDITOR (Audit Risiko & Skenario Terburuk)
    # -------------------------------------------------------------
    sys_bear = (
        "Anda adalah 'Bearish Auditor / Chief Risk Skeptic'. Tugas Anda adalah MEMBATALKAN rencana trading jika ada risiko!\n"
        "PERIKSA HAL-HAL BERIKUT DENGAN KETAT:\n"
        "1. Apakah resistance kuat berada sangat dekat di atas harga saat ini?\n"
        "2. Apakah volume trading rendah yang mengindikasikan 'fakeout' (kenaikan palsu)?\n"
        "3. Jika skenario gagal, seberapa dalam harga bisa jatuh (downside)?\n"
        "4. Tentukan level Stop Loss (SL) darurat yang masuk akal.\n"
        "Jelaskan analisis risiko Bearish dalam Bahasa Indonesia padat (maksimal 3-4 kalimat)."
    )
    prompt_bear = f"Data Pasar Real-Time untuk {symbol}:\n{data_summary}\nTesis Bullish Rekan Anda:\n{bull_thesis}\n\nJelaskan tesis Bearish dan risiko fatalnya:"
    bear_thesis = call_ai(prompt_bear, sys_bear, max_tokens=1000)

    # -------------------------------------------------------------
    # TIER 3: SUPREME RISK MANAGER (Hakim Ketat - The Gatekeeper)
    # -------------------------------------------------------------
    sys_judge = (
        "Anda adalah 'Supreme Risk Manager' dengan filosofi: 'MODAL PENGGUNA ADALAH NYAWA. LEBIH BAIK TIDAK TRADING DARIPADA RUGI'.\n"
        "Anda menimbang tesis Bullish vs audit Bearish secara objektif.\n\n"
        "CHECKLIST KELOLOSAN WAJIB DIPENUHI SEMUA (JIKA ADA 1 YANG GAGAL = WAJIB REJECT):\n"
        "1. Skor Keyakinan (Confidence Score) minimal 80%. Di bawah 80% = REJECT.\n"
        "2. Risk to Reward Ratio (RRR) minimal 1:2.0 (potensi untung minimal 2x lipat potensi rugi).\n"
        "3. Dilarang beli jika RSI > 70 (Overbought zone).\n"
        "4. Dilarang beli jika EMA Bearish kuat dan belum ada konfirmasi reversal.\n"
        "5. Jika pasar sideways atau sinyal meragukan: WAJIB REJECT (CASH IS A POSITION).\n"
        "6. Modal transaksi: Maksimal Rp 50.000.\n\n"
        "Keluarkan HANYA format JSON valid berikut tanpa kata pembuka/penutup:\n"
        "{\n"
        '  "status": "APPROVED" atau "REJECTED",\n'
        '  "confidence_score": 85,\n'
        '  "risk_reward_ratio": "1:2.5",\n'
        '  "target_profit_price": 86000,\n'
        '  "stop_loss_price": 80000,\n'
        '  "nominal_idr": 50000,\n'
        '  "reason": "Penjelasan pertimbangan ketat mengapa disetujui atau ditolak"\n'
        "}"
    )

    prompt_judge = (
        f"Data Market {symbol}:\n{data_summary}\n\n"
        f"1. Bullish Analyst:\n{bull_thesis}\n\n"
        f"2. Bearish Auditor:\n{bear_thesis}\n\n"
        f"Keluarkan HANYA JSON hasil evaluasi ketat:"
    )

    judge_raw = call_ai(prompt_judge, sys_judge, max_tokens=1000)
    
    # Parse JSON secara robust dengan regex
    import re
    try:
        clean_json = judge_raw.strip()
        match = re.search(r'\{[\s\S]*\}', clean_json)
        if match:
            judge_verdict = json.loads(match.group(0))
        else:
            raise ValueError("No JSON object found")
    except Exception as e:
        judge_verdict = {
            "status": "REJECTED",
            "confidence_score": 0,
            "risk_reward_ratio": "0:0",
            "nominal_idr": 0,
            "reason": f"Audit gagal diverifikasi secara kuantitatif. Demi keamanan dana, transaksi otomatis ditolak: {str(e)}"
        }

    # KUNCI MATI DARI SISI PYTHON (ANTI-TAMPERING)
    if judge_verdict.get("nominal_idr", 0) > MAX_BUDGET_IDR:
        judge_verdict["nominal_idr"] = MAX_BUDGET_IDR
    
    if judge_verdict.get("confidence_score", 0) < 80:
        judge_verdict["status"] = "REJECTED"

    return {
        "symbol": symbol,
        "market": market_data,
        "tier1_bullish": bull_thesis.strip(),
        "tier2_bearish": bear_thesis.strip(),
        "tier3_judge": judge_verdict
    }

if __name__ == "__main__":
    from market_data import get_market_indicators
    data = get_market_indicators("BTC-USD")
    print("[*] Menjalankan 3-Tier AI Committee untuk BTC-USD...")
    res = run_3_tier_analysis(data)
    print("\n=== HASIL AUDIT 3 AI ===")
    print(json.dumps(res, indent=2, ensure_ascii=False))
