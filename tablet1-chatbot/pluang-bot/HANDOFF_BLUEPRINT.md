# PYROFUEL BOT — HANDOFF BLUEPRINT (v1, 2026-10-27)

Tujuan akhir (dari user):
1. Analisa **akurat & profit** (terukur, bukan klaim).
2. **AI tidak terblokir / tidak perlu cari API key terus-menerus**.
3. **Jalan lancar di Termux** (tablet Android).
4. Analisa dilakukan **AI sebisa mungkin**, bukan rumus buta.

Root dir kerja (SATU-SATUNYA sumber kode): `c:\Users\Asus\.antigravity\tablet-dashboards\tablet1-chatbot\pluang-bot\`
(Folder duplikat `c:\Users\Asus\.antigravity\pluang-bot\` = salinan lama, jangan dipakai — lihat T5.1.)

> **Aturan untuk semua sub-agent**
> - JANGAN pernah menulis API key/secret/token ke file yang di-commit (termasuk base64). Secret hanya di `.env` (di-gitignore).
> - Jangan commit/push tanpa diminta. Jangan `git push --force` tanpa persetujuan user.
> - Pertahankan komentar/docstring lama yang tidak terkait perubahan.
> - Setiap task punya **Acceptance** berupa perintah yang bisa dijalankan. Task belum selesai sebelum acceptance PASS.
> - Hanya sentuh file yang tercantum di kolom *Owns* (hindari konflik antar-agent paralel).
> - Pesan user-facing (Telegram/log) tetap Bahasa Indonesia.

---

## 0. DIAGNOSIS (bukti dari audit kode & data)

| # | Masalah | Bukti | Dampak |
|---|---------|-------|--------|
| D1 | **SEMUA AI cloud mati saat ini** | Probe 2026-10-27 20:33: Groq `DAILY LIMIT` (TPD habis), Gemini `429`, OpenRouter `402 Insufficient credits` (`openrouter/auto` butuh kredit — bukan free) → `ALL_AI_FAILED` | Bot jatuh ke rule-based; "AI-first" tidak terjadi |
| D2 | **Konsumsi AI >10× kuota gratis** | Universe 523 koin; per siklus 5 koin × (L2+L3+L4+L5 = 4 call + committee ≈ 7 call) ≈ 55 call / 5 menit ≈ **~15.800 call/hari (estimasi batas atas)**. Kuota gratis Groq ≈ 1.000 req/hari & TPD terbatas, OpenRouter free 50 req/hari | Penyebab utama "kena blokir/limit" → cari key terus |
| D3 | **Tidak ada pengukuran akurasi** | `active_positions.json` hanya 2 posisi tercatat; `autotrader_state.json`: 49 approved / 422 rejected (≈10% approve), tapi tidak ada tabel sinyal→hasil | Tidak bisa tahu apakah analisa akurat/profit |
| D4 | **PnL dicatat tidak akurat** | `auto_trader.py` L505–523: `final_pnl_pct` dihitung dari `curr_px` saat bot *mendeteksi* posisi tutup, bukan dari fill nyata Binance. 2 trade SL: SL 1.47% @5x seharusnya ≈ −7.4% tapi tercatat **−15.2%**; posisi dibuka 20-Okt, "closed" 25-Okt (5 hari) | Data hasil tak bisa dipercaya; kemungkinan SL tidak terpasang/terlambat (BELUM terbukti → T1.2) |
| D5 | **Manajemen risiko merusak profit** | `trading_config.json`: `ALL_IN_WALLET` (98% saldo) + leverage **20× tetap**. SL ≈1.5% × 20× = **−30% margin per loss**; 3 loss beruntun ≈ saldo habis. Fee taker 0.05%×2×20× ≈ **2% margin per round-trip** | Win-rate 60% pun bisa rugi; ini faktor terbesar vs "profit" |
| D6 | **Confidence AI tidak terkalibrasi** | `pipeline.py` L1326: Layer 5 menaruh `"confidence_score":{prob}` langsung di template output → hanya menyalin `probability_pct` Layer 2 (angka karangan AI). Gate `min_confidence=45` ≈ tidak memfilter | "Confidence 82% NO_CLEAR_SETUP" muncul di log; sinyal bukan probabilitas nyata |
| D7 | **JSON/Reasoning bocor** | Tes sebelumnya: `gpt-oss-20b` mengembalikan teks "The user says…" (chain-of-thought) bukan JSON | Parse gagal → fallback → kualitas turun |
| D8 | **Committee berkualitas rendah & mahal** | `committee_log`/`active_thesis.json`: debat bull/bear tercampur ("Bear: Bull Researcher…"), kemungkinan model kecil (`OLLAMA_MODEL=llama3.2:1b` di `.env` bila Ollama online) | ~7 call/koin tanpa nilai prediktif terbukti |
| D9 | **Data universe kotor** | Universe memuat simbol aneh (`AXTIB`, `SNDKB`, `SOXLB`, `WDCB`, `US`, `A`, …) & koin ilikuid | Sinyal pada aset tipis = slippage/SL tersapu |
| D10 | **Dua sumber konfigurasi bertabrakan** | `autotrader_state.json`: `max_leverage 5`, `max_budget_idr 50000`; `trading_config.json`: `20x`, `0`. `last_scan_time` = 2026-10-20 (scan berhenti), `all_in_reason` basi | Perilaku tak terprediksi |
| D11 | **Termux rapuh** | `pip install numpy` di Termux sering gagal/kompilasi lama (harus `pkg install python-numpy`); IP Binance di-hardcode (`market_data.py` L30–35, bisa basi); `verify=False` dipakai luas; tidak ada watchdog/wake-lock/autostart; sinyal SHORT Pluang spot gagal (`execution_log.json`: "hanya mendukung LONG") | Mati saat layar off / Android membunuh proses |
| D12 | 🔴 **SECRET BOCOR DI REPO PUBLIK** | `start_termux.sh` berisi kredensial base64 (Groq, Gemini, OpenRouter, **Telegram bot token, Binance API key+secret**); commit `e46d931` & `50b4374`; repo `fdhl880/home-server` = **`private:false` (PUBLIK)**. Base64 ≠ enkripsi | Siapa pun bisa trading/menguras akun Binance & mengambil alih bot |

---

## FASE 0 — DARURAT (lakukan SEKARANG, sebelum yang lain)

### 0-A. Manual oleh USER (sub-agent tidak bisa)
1. **Binance**: hapus API key lama → buat baru: *Enable Futures* saja, **Withdrawals OFF**, (opsional) IP restriction bila IP stabil.
2. **Telegram**: BotFather → `/revoke` token bot → token baru.
3. **Groq / Gemini / OpenRouter**: revoke & buat ulang (atau hapus bila tidak dipakai).
4. Simpan hanya ke `.env` lokal (Windows & Termux). Jangan chat/commit key.

### T0.1 — Scrub repo  (Agent **A0**) · *Owns:* `start_termux.sh`, `.gitignore`, `.env.example`, `client_config.json`
Steps:
1. Hapus blok `B64_CRED=...` dari `start_termux.sh`. Ganti: jika `.env` tidak ada → `cp .env.example .env` lalu prompt interaktif (`read -s -p`) untuk key wajib (Binance, Telegram, minimal 1 AI) dan tulis ke `.env` (`chmod 600`).
2. Pastikan `.gitignore` memuat `.env`, `tokens.json`, `pending_auth.json`, `login_url.txt`, `results/*.json` (state), `*.log`.
3. Periksa `client_config.json` (tracked) — buang nilai rahasia bila ada.
4. **KEPUTUSAN USER: repo tetap publik & history TIDAK dibersihkan** (push dilakukan dari Termux). Konsekuensi yang harus dijaga: (a) key lama yang sudah terlanjur ter-push tetap dianggap bocor → wajib dirotasi (0-A); (b) commit baru dari Termux **tidak boleh** memuat secret → `.gitignore` + pre-commit hook (T5.1) wajib aktif; (c) opsional nanti: `git filter-repo --replace-text` + force-push hanya dengan persetujuan eksplisit user.
Acceptance:
```
git grep -nE "gsk_|AIza|AQ\.Ab|sk-or-v1|QUlfUFJPVklERVI9|[0-9]{8,}:AA[A-Za-z0-9_-]{30,}" -- . ":!*.md"   # harus kosong
bash -n start_termux.sh
```

---

## FASE 1 — PENGUKURAN (fondasi; tanpa ini "akurat" tidak bisa dibuktikan)

### T1.1 — Jurnal sinyal & PnL nyata  (Agent **A1**) · *Owns:* `journal.py` (baru), `auto_trader.py` bagian close/reconcile (L400–560)
1. Buat `journal.py` (SQLite `results/journal.db`, WAL mode). Tabel `signals(id, ts, symbol, tf, direction, setup, ai_prob, calibrated_prob, entry, sl, tp, rrr, features_json, provider, model, decision, reject_reason)` dan `trades(id, signal_id, open_ts, close_ts, entry_fill, exit_fill, qty, fee_usd, pnl_usd, pnl_pct_margin, r_multiple, exit_reason, mae, mfe)`.
2. Catat **setiap** keputusan pipeline (approved & rejected) ke `signals`.
3. Ganti perhitungan PnL close: ambil dari Binance `GET /fapi/v1/userTrades` + `GET /fapi/v1/income` (REALIZED_PNL, COMMISSION, FUNDING_FEE) untuk symbol & rentang waktu posisi; simpan fill nyata. Fallback ke estimasi hanya jika API gagal (tandai `estimated=1`).
4. CLI `python journal.py report` → win-rate, profit factor, expectancy (R), avg R, max drawdown, per-setup, per-provider.
Acceptance: `python -m pytest tests/test_journal.py` (insert/close/report dengan data fiktif) + `python journal.py report` jalan tanpa error pada DB kosong.

### T1.2 — Forensik 2 loss SOL  (Agent **A1**, read-only analisis → `docs/forensics_sol.md`)
Jawab dengan bukti (log/API income): (a) apakah SL & TP `algoOrder` benar-benar terpasang setelah entry (`binance_futures.py` L436–490)? (b) kenapa loss −15.2%/−16.9% ≠ jarak SL×leverage? (c) kenapa 5 hari baru "closed"? (d) apakah monitor (`auto_trader.py` L1720, loop 10 dtk) sempat mati?
Acceptance: dokumen berisi akar masalah + patch yang direkomendasikan (patch dikerjakan di T3.4).

### T1.3 — Backtest/replay harness  (Agent **A3**) · *Owns:* `backtest/` (baru)
1. `backtest/fetch.py`: unduh klines 1h (+4h, 1d) 120 hari untuk 30 koin likuid (volume 24h > $100M; endpoint `fapi` lalu `data-api.binance.vision`) → `backtest/data/*.parquet|csv` (hindari pandas jika berat; boleh CSV + numpy).
2. `backtest/engine.py`: replay candle-by-candle memakai fungsi `_rule_based_setup/_rule_based_plan` (`pipeline.py` L542/L693) **tanpa lookahead**; model biaya: taker 0.05%/sisi, slippage 0.03%, funding 8 jam; SL/TP intrabar (jika keduanya tersentuh di candle yang sama → asumsikan SL dulu).
3. Output `backtest/report.md`: per-setup win-rate, expectancy (R), profit factor, max DD, hasil **walk-forward** (train 60 hr / test 30 hr) & per-leverage (5×/10×/20×).
Acceptance: `python backtest/engine.py --coins BTC,ETH,SOL --days 90` menghasilkan `report.md` dengan tabel metrik; unit test: strategi dummy "selalu long" menghasilkan hasil yang cocok hitungan manual.
**Keputusan yang dipakai Fase 3:** setup mana yang punya expectancy > 0 setelah fee. Setup yang negatif → dibuang dari daftar yang boleh diajukan ke AI.

---

## FASE 2 — AI TIDAK TERBLOKIR (gateway + hemat kuota)

> Prinsip jujur: **tidak ada API gratis yang unlimited**. "Tidak perlu cari key lagi" dicapai dengan: (1) mengurangi konsumsi ≥10×, (2) pooling banyak provider/key, (3) circuit-breaker + cache, (4) degrade terkontrol yang tetap memakai AI semampunya.

### T2.1 — `ai_gateway.py`  (Agent **A2**) · *Owns:* `ai_gateway.py` (baru), `pipeline.py` fungsi `call_ai` (L331–535: hanya delegasi), `.env.example`
Requirements:
1. **Provider registry** data-driven (YAML/dict): groq, gemini, cerebras, mistral, nvidia-nim, cloudflare-workers-ai, openrouter(**hanya model `:free`**), ollama(opsional, nonaktif di Termux).
2. **Multi-key pool**: env `GROQ_API_KEYS=k1,k2`, dst. Round-robin + skip key yang sedang cooldown.
3. **Klasifikasi error → cooldown**: 429 TPM → tunggu `Retry-After` (≤60 dtk); 429/limit harian (RPD/TPD) → cooldown sampai reset (default 6 jam / tengah malam UTC); **402/401/403 → disable permanen sesi + log WARNING sekali**; 5xx/timeout → exponential backoff. Persist ke `results/ai_health.json` (bertahan setelah restart).
4. **Model discovery**: saat start & tiap 6 jam `GET /models` (Groq, OpenRouter) → pilih model aktif; model yang 404/deprecated otomatis dicoret (tidak hard-code nama).
5. **Token-bucket per provider** (RPM) + **budget harian global** (`AI_MAX_CALLS_PER_DAY`, default 400) + prioritas panggilan (`judge` > `analyst` > `commentary`).
6. **Cache**: key = `(symbol, tf, candle_close_ts, prompt_hash)` TTL = durasi candle → tidak memanggil ulang untuk candle yang sama.
7. **Routing by task**: tugas kritis (final judge) → model terkuat tersedia; tugas ringan → model cepat/kecil.
8. `call_ai()` lama tetap ada sebagai wrapper (signature sama) agar tidak merusak `multi_agent_committee.py`, `telegram_bot.py`, `server.py`.
9. Hapus `OpenRouter-Auto` (402). Hapus provider yang terbukti mati.
Acceptance:
```
python -m pytest tests/test_ai_gateway.py   # fake HTTP server: 429(TPM), 429(RPD), 402, 503, timeout, invalid JSON
python scratch/ai_json_probe.py             # bila ≥1 key hidup: tidak ada ALL_AI_FAILED
```
Tes wajib: dengan 3 provider disimulasikan mati & 1 hidup → tetap sukses; dengan semua mati → exception `ALL_AI_FAILED` + status jelas di `/health`.

### T2.2 — Keandalan JSON  (Agent **A2**)
1. Pakai structured output bila didukung: OpenAI-compatible `response_format={"type":"json_schema",...}` / `json_object`; Gemini `responseMimeType: application/json` + `responseSchema`.
2. Untuk model reasoning (`gpt-oss-*`, `qwen3*`): set `reasoning_effort="low"`, `max_tokens` cukup, buang `<think>…</think>` & teks sebelum `{`.
3. `parse_json_from_text` (pipeline.py L826) + **1× repair-retry** ("kembalikan JSON valid saja") sebelum dianggap gagal; validasi dengan schema (field wajib, tipe, rentang).
Acceptance: probe 20 panggilan/provider pada prompt Layer 2 asli → **parse success ≥ 95%**, median latensi dilaporkan.

### T2.3 — Funnel hemat kuota  (Agent **A5**, setelah T2.1) · *Owns:* `pipeline.py` (L903–1700), `auto_trader.py` scheduler bagian scan
Arsitektur (target **≤ ~100 call/hari**):
```
[Python, 0 AI call]  Universe filter  → likuid (vol24h ≥ $50M, spread kecil, bukan simbol tokenized/ETF-like)
[Python, 0 AI call]  Quant+rule score → top-N (N=3) kandidat per candle close
[AI call #1/kandidat] "One-shot analyst" (gabung Layer 2+3+4): setup, arah, entry/SL/TP, alasan, ai_prob
[AI call #2, hanya 1 kandidat terbaik] "Judge + devil's advocate" (gantikan committee 7 call)
[Python] EV/Risk gates → eksekusi
```
- Jalankan **hanya saat candle 1h close** (menit :01) + event trigger (breakout volume ekstrem), bukan tiap 5 menit.
- Saat posisi terbuka: AI hanya dipanggil untuk manajemen (trail/BE/exit) maks 1×/15 menit, selebihnya SL/TP native.
- Committee 7-agent → dinonaktifkan default (flag `COMMITTEE_ENABLED=false`), sisakan sebagai opsi manual `/committee SYMBOL`.
Acceptance: log harian `ai_calls_today` ≤ 120 pada simulasi 24 jam (replay data); jumlah sinyal approved tidak turun >30% vs pipeline lama pada replay yang sama.

---

## FASE 3 — AKURASI & PROFIT

### T3.1 — Kualitas sinyal  (Agent **A5**)
1. Filter regime: BTC 1h/4h trend & volatilitas — jangan LONG alt saat BTC dump (>−1.5%/jam), jangan SHORT saat squeeze naik.
2. Konfirmasi multi-timeframe (1h entry searah 4h & 1d); tolak counter-trend kecuali setup `MEAN_REVERSION` dengan RSI ekstrem + level S/R.
3. Hanya setup yang lolos expectancy>0 di T1.3 yang boleh diajukan.
4. Input ke AI: fitur ringkas + **hasil backtest setup tsb** (win-rate & avg R historis) agar AI menimbang base-rate, bukan menebak.
5. AI = **ranker + veto**, bukan generator bebas: AI boleh membatalkan/menurunkan skor, tidak boleh menaikkan leverage/ukuran.

### T3.2 — Kalibrasi probabilitas  (Agent **A7**, butuh data T1.1/T1.3) · *Owns:* `calibration.py` (baru), `pipeline.py` `layer5_final_judgment`
1. Perbaiki D6: Layer 5 **tidak** menyalin `prob`; hitung `calibrated_prob` dari isotonic/binning atas `ai_prob` vs hasil nyata (jurnal + backtest).
2. Ganti gate `min_confidence` dengan **EV gate**: `EV_R = p·RRR − (1−p) − fee_R > 0.15` (fee_R = biaya round-trip dalam satuan R).
3. Hingga data cukup (<40 sinyal ber-hasil): pakai base-rate backtest per setup sebagai prior.
Acceptance: unit test kalibrasi (data sintetis) + laporan reliability-diagram di `docs/calibration.md`.

### T3.3 — Risk engine  (Agent **A6**) · *Owns:* `pipeline.py` `_apply_safety_gates`, `auto_trader.py` sizing, `trading_config.json`
> **KEPUTUSAN USER: leverage TETAP 20×, ISOLATED.** Risiko dikendalikan lewat **ukuran margin**, bukan leverage. Di 20× likuidasi ≈ 4.5–5% dari entry, sehingga jarak SL harus sempit.
1. **Fixed-fractional risk**: `risk_usd = equity × RISK_PCT` (config; default **5%** per trade, hard max 10%). Margin yang dipakai = `risk_usd / (sl_pct × 20)` ⇒ saat SL kena, rugi (termasuk fee) ≈ `RISK_PCT` equity. **Hapus `ALL_IN_WALLET` 98%**.
2. **Guard likuidasi 20×**: tolak entri bila `sl_pct > 2.5%` (likuidasi harus ≥ ~1.8× jarak SL). Hitung harga likuidasi dari Binance (`positionRisk`/formula isolated + maintenance margin) dan verifikasi SL ada di dalamnya.
3. **SL berbasis ATR/struktur**: `SL = max(1.2×ATR(1h), di luar swing terdekat)`; tolak bila SL < 0.8×ATR (tersapu noise). Konsekuensi di 20×: koin dengan `1.2×ATR(1h) > 2.5%` **otomatis dikeluarkan** dari kandidat (terlalu volatil).
4. **Fee dalam EV**: taker 0.05%/sisi ⇒ round-trip 0.10% harga ≈ `0.10/sl_pct` R (SL 1.5% ⇒ 0.067R). TP minimal RRR 1.5 **setelah** fee; partial TP 50% di 1R + SL ke break-even.
5. **Circuit breaker**: rugi harian ≥ 15% equity, atau 3 loss beruntun, atau drawdown ≥ 25% dari puncak equity ⇒ stop entri 12 jam (drawdown 25% ⇒ stop sampai user `/resume`); alert Telegram.
6. **Min notional Binance**: bila margin hasil rumus < min notional simbol, boleh naikkan `RISK_PCT` efektif **hanya** sampai `RISK_PCT_MAX_FOR_MIN_NOTIONAL` (default 15%); bila masih tidak cukup ⇒ lewati koin & kirim pesan "saldo terlalu kecil untuk simbol ini" (jangan paksa). Prioritaskan koin dengan min notional kecil ($5) saat saldo kecil.
7. Satu sumber konfigurasi: `trading_config.json` (hapus override di `autotrader_state.json`, lihat T5.1). Tambah kunci `risk_pct`, `fixed_leverage=20`, `max_sl_pct=2.5`, `breaker_*`.
Acceptance: `pytest tests/test_risk.py` — kasus: equity $100, RISK_PCT 5%, SL 1.5% ⇒ margin ≈ $16.67, notional ≈ $333, rugi di SL ≈ $5 ± fee; SL 3% ⇒ ditolak; `1.2×ATR` > 2.5% ⇒ ditolak; breaker aktif setelah 3 loss; saldo $2.27 + simbol min-notional $5 ⇒ order valid atau pesan skip yang jelas.

### T3.4 — Integritas eksekusi  (Agent **A6**)
1. Setelah entry: query `openAlgoOrders`/`openOrders` → **pastikan SL & TP ada**; bila SL gagal terpasang dalam 3 detik → **tutup posisi MARKET reduceOnly** + alert.
2. Reconcile tiap 30 dtk: posisi di exchange vs `active_positions.json`; bila beda → sinkronkan & alert (menyelesaikan D4).
3. Time-stop (mis. 24 jam tanpa progres) & hapus order yatim saat posisi tutup.
4. Pastikan venue = **Binance Futures** untuk LONG/SHORT; matikan jalur Pluang spot untuk SHORT (`auto_execute_on_pluang=false` atau route hanya LONG).
Acceptance: skenario testnet (`https://testnet.binancefuture.com`) — entry → SL ada → cabut SL manual → bot mendeteksi & menutup/memasang ulang dalam ≤ 30 dtk.

### T3.5 — Live dengan masa percobaan (probation)  (Agent **A7**)
> **KEPUTUSAN USER: trading real.** Tidak ada masa shadow wajib; pengamanan diganti dengan *probation* otomatis. `MODE=SHADOW` tetap tersedia (flag) untuk uji perubahan besar.
1. **Probation**: 20 trade pertama memakai `RISK_PCT=2%` (leverage tetap 20×). Setelah ≥ 20 trade ber-hasil dan `profit factor ≥ 1.2` & `expectancy > 0` setelah fee (dihitung `journal.py report --gate`) → otomatis naik ke `RISK_PCT` target (default 5%).
2. **Auto-pause**: rolling 20 trade terakhir dengan `profit factor < 0.8`, atau drawdown ≥ 25% dari puncak equity ⇒ bot berhenti entri, kirim ringkasan ke Telegram, menunggu `/resume`.
3. **EV gate (T3.2) wajib aktif sejak hari pertama**; sebelum ada data hasil nyata gunakan base-rate dari backtest (T1.3).
4. Laporan harian otomatis ke Telegram: trade, win-rate, PF, expectancy, equity, panggilan AI terpakai.
> Tidak ada yang bisa menjamin profit — apalagi di 20×. Yang dijamin blueprint ini: **angka hasil nyata, kerugian per trade dibatasi `RISK_PCT`, dan bot berhenti sendiri bila edge hilang.**

---

## FASE 4 — TERMUX

### T4.1 — `start_termux.sh` v4  (Agent **A4**) · *Owns:* `start_termux.sh`, `requirements.txt`, `requirements-termux.txt`, `termux_boot.sh` (baru)
1. `pkg update`, `pkg install -y python python-numpy openssl libffi tmux termux-api git`; **jangan** `pip install numpy` (pakai paket Termux); `pip install -r requirements-termux.txt` (flask, flask-cors, requests, python-dotenv, urllib3 — tanpa numpy).
2. Kerja di `$HOME/pyrofuel` (bukan `/sdcard`: tidak bisa exec/chmod).
3. `.env`: dari `.env.example` + prompt interaktif (T0.1); validasi key terisi, `chmod 600`.
4. `termux-wake-lock`; jalankan di `tmux` session `pyrofuel` dengan **supervisor loop**: restart otomatis dengan backoff (5→60 dtk), log rotasi (`logs/bot.log` maks 5×5 MB).
5. Autostart: tulis `~/.termux/boot/pyrofuel.sh` (butuh app Termux:Boot).
6. Cetak instruksi manual: matikan *Battery optimization* untuk Termux; Android 12+ nonaktifkan phantom-process killer: `adb shell "settings put global settings_enable_monitor_phantom_procs false"` (atau `device_config put activity_manager max_phantom_processes 2147483647`).
7. Cek **sinkron jam** (`/fapi/v1/time` vs jam lokal) — selisih >1 dtk → peringatkan & pakai offset (signed request Binance gagal bila drift).
Acceptance (di tablet): `bash start_termux.sh --selftest` → semua baris PASS; `tmux ls` menampilkan `pyrofuel`; `kill -9` proses python → hidup lagi ≤ 60 dtk.

### T4.2 — Ketahanan jaringan/anti-blokir ISP  (Agent **A4**) · *Owns:* `market_data.py` L1–100 & fetch helper, `binance_futures.py` `_request`
1. Hapus IP Binance hard-coded; resolusi via DoH (Cloudflare → Google → Quad9) dengan **TTL cache** (5 mnt) dan validasi (IP berubah → refresh).
2. Failover endpoint: `fapi` → `fapi1/2/3` → `data-api.binance.vision` (market data saja); circuit breaker per host.
3. TLS: bila koneksi ke IP, gunakan `HTTPAdapter` dengan `server_hostname` = host asli sehingga **`verify=True`** tetap bisa; `verify=False` hanya fallback terakhir + log warning.
4. Timeout & retry terukur; semua panggilan lewat satu `http_get()` helper (hilangkan `requests.get` tersebar).
Acceptance: jalankan dengan DNS ISP di-blok (set `DOH_ONLY=1` dan resolver sistem dimatikan) → klines BTC 1h berhasil; tes unit failover dengan host palsu.

### T4.3 — `termux_selftest.py`  (Agent **A4**)
Cek & cetak tabel PASS/FAIL: versi Python (≥3.10), import paket, tulis disk, RAM bebas, waktu & drift Binance, DoH, klines BTC, **1 panggilan kecil ke tiap provider AI yang berkunci** (via gateway), Telegram `getMe`, Binance `account` (read-only), `.env` permission 600.
Acceptance: exit code 0 hanya bila semua kritikal PASS (≥1 AI hidup, Binance, Telegram).

---

## FASE 5 — KONSOLIDASI

### T5.1 — Satu sumber kebenaran  (Agent **A8**)
1. Putuskan folder kanonik = `tablet-dashboards/tablet1-chatbot/pluang-bot`; hapus/arsipkan `c:\Users\Asus\.antigravity\pluang-bot\` (md5 `pipeline.py` sudah berbeda).
2. Hapus `max_leverage/max_budget_idr` dari `autotrader_state.json` (state ≠ config). Perbaiki `last_scan_time` basi — cari kenapa scan berhenti sejak 2026-10-20 (mode `ALL_IN` fokus-posisi?) dan tambahkan heartbeat/`/health`.
3. Hapus file scratch berisi kredensial; tambahkan pre-commit hook (gitleaks atau regex pada D12) agar kebocoran tak terulang.
Acceptance: `git ls-files | rg "pluang-bot"` hanya satu lokasi; `curl localhost:PORT/health` menampilkan `last_scan_age_sec`, `ai_health`, `positions`, `mode`.

---

## URUTAN EKSEKUSI (wave) & PEMILIK FILE

| Wave | Task (paralel dalam wave) | Agent | Bergantung pada |
|------|---------------------------|-------|-----------------|
| **0** | 0-A (USER rotate key) + T0.1 | A0 | — (blok semua) |
| **1** | T1.1 + T1.2 | A1 | W0 |
| **1** | T2.1 + T2.2 | A2 | W0 |
| **1** | T1.3 | A3 | W0 |
| **1** | T4.1 + T4.2 + T4.3 | A4 | W0 (T4.3 pakai gateway → rilis akhir wave) |
| **2** | T2.3 + T3.1 | A5 | T2.1, T1.3 |
| **2** | T3.3 + T3.4 | A6 | T1.1, T1.2 |
| **3** | T3.2 + T3.5 | A7 | T1.1, T1.3, T2.3 |
| **3** | T5.1 | A8 | semua |
| **4** | Uji terpadu di tablet → live probation (T3.5) | user + A4 | semua |

File ownership (anti-konflik): `pipeline.py` → A2 (hanya `call_ai`) lalu A5 (layer) lalu A6 (gates) lalu A7 (layer5) — **serial**, merge per wave. `auto_trader.py` → A1 (close/reconcile) & A6 (sizing/exec) — beda blok, koordinasi lewat PR kecil.

## KEPUTUSAN USER (2026-10-27 20:40) & DEFAULT
| # | Pertanyaan | Keputusan |
|---|-----------|-----------|
| 1 | Top-up OpenRouter $10 | *Tidak dijawab* → **default: tidak**, pakai pool gratis (bisa ditambah kapan saja) |
| 2 | Leverage | **20× tetap, isolated** (dikunci). Risk/trade tidak dijawab → **default `RISK_PCT=5%`** (probation 2%), configurable |
| 3 | Gaya trading | **Bebas** → default **intraday/swing 1h** (paling hemat AI & fee; scalping 5–15m ditolak karena kuota & fee 20×) |
| 4 | Mode | **Trading real** (tanpa shadow wajib; pakai probation + auto-pause, T3.5) |
| 5 | Repo | **Tetap publik, history tidak dibersihkan**; push dilakukan dari Termux. Secret baru tidak boleh masuk repo; key lama tetap harus dirotasi |

## DEFINISI SELESAI (Definition of Done)
- [ ] Tidak ada secret di repo; semua key sudah dirotasi.
- [ ] `journal.py report` menampilkan metrik nyata dari fill Binance.
- [ ] Backtest menunjukkan setup mana yang expectancy > 0 setelah fee.
- [ ] 1 siklus penuh ≤ ~4 panggilan AI; `ai_calls_today` ≤ 120; tidak ada `ALL_AI_FAILED` selama ≥1 provider hidup.
- [ ] Parse JSON AI ≥ 95%.
- [ ] Leverage 20× isolated; rugi per trade di SL ≈ `RISK_PCT` equity; SL ≤ 2.5% & di dalam harga likuidasi; SL/TP terverifikasi di exchange setiap entry.
- [ ] Termux: selftest PASS, auto-restart, autostart saat boot, bertahan ≥ 48 jam layar mati.
- [ ] Probation T3.5 aktif: 20 trade pertama @2%, auto-naik ke target hanya bila PF ≥ 1.2; auto-pause saat PF < 0.8 / DD ≥ 25%.
