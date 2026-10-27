# FORENSIK 2 PERDAGANGAN SOL-USD

## Ringkasan Eksekutif
Dua posisi terakhir pada SOL-USD (`active_positions.json`) mengalami kerugian berturut-turut dengan deviasi tajam antara rencana Stop Loss (SL) teoritis dan realisasi PnL:

1. **Trade 1: SOL-USD LONG (2026-10-20 s/d 2026-10-25)**
   - Entry: $105.76 | Leverage: 5x | Jarak SL Teori: 1.475% ($104.20)
   - Ekspektasi Rugi: -7.38% margin
   - Realisasi Tercatat: **-15.20% margin** (-0.421 USD)
   - Durasi: **4 hari 19 jam**

2. **Trade 2: SOL-USD SHORT (2026-10-25 s/d 2026-10-26)**
   - Entry: $100.55 | Leverage: 20x | Jarak SL Teori: 1.50% ($102.0583)
   - Ekspektasi Rugi: -30.0% margin
   - Realisasi Tercatat: **-16.91% margin** (-0.4856 USD)
   - Durasi: **22 jam 22 menit**

---

## Akar Masalah Utama

1. **Ketiadaan Native Conditional Stop Loss di Exchange**
   - Bot tidak memverifikasi apakah pesanan `STOP_MARKET` (algoOrder) benar-benar terdaftar di server Binance setelah pembukaan posisi.
   - Posisi bergantung pada `time.sleep` monitoring loop lokal di `auto_trader.py`. Saat proses komputer/termux tertidur atau koneksi terputus, posisi mengambang tanpa proteksi.

2. **Slippage Ekstrem & Delay Deteksi (5 Hari Terbuka)**
   - Pada Trade 1, harga meluncur jauh melewati $104.20 hingga ke ~$102.54 sebelum bot mendeteksi penutupan. Ini melipatgandakan kerugian dari -7.38% menjadi -15.20%.

3. **Perhitungan PnL Tidak Berbasis Fill Riil Exchange**
   - `auto_trader.py` menghitung PnL dari `curr_px` saat pengecekan, bukan dari `GET /fapi/v1/userTrades` yang mencatat harga eksekusi aktual Binance dan potongan komisi.

---

## Solusi yang Diimplementasikan dalam Blueprint

1. **T3.4 Execution Verification**:
   - Setelah order MARKET masuk, query `GET /fapi/v1/openOrders` dalam 3 detik untuk memastikan pesanan STOP_MARKET aktif di bursa Binance. Jika gagal, posisi langsung ditutup darurat.
2. **T1.1 Real Fills via Journal.py**:
   - Menghubungkan audit PnL langsung ke `userTrades` dan `income` Binance.
3. **T3.3 Dynamic Margin Sizing**:
   - Mengganti `ALL_IN_WALLET` dengan sizing risiko persentase (5% per trade), menjaga agar kerugian di SL 20x terisolasi maksimal pada persentase yang ditetapkan.
