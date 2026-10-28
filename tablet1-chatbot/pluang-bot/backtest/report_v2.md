# LAPORAN VALIDASI BACKTEST v2 — PURGED WALK-FORWARD & TRIPLE-BARRIER (20x ISOLATED)

## 1. Ringkasan Eksekutif Out-of-Sample (OOS) & Walk-Forward Non-Overlapping
- **Metodologi Validasi**: Purged & Embargoed Walk-Forward CV (López de Prado) + Non-Overlapping Per-Symbol Execution
- **Mode Manajemen Posisi**: `HIGH_PRECISION_SNIPER_MODE` (`TP1 = +0.55R` mengunci `SL = +0.38R`, Runner `TP2 >= +1.65R`)
- **Model Biaya Bersih**: Maker Fee `0.02%` / Taker Fee `0.05%` + Dynamic Slippage + Funding Rate 8h UTC
- **Total Sampel Non-Overlapping ($N$)**: `287` trade (`OOS Murni`: `111` trade)
- **Realized Win-Rate (Net of Fees)**: **`69.34%`** (OOS: `60.36%`)
- **Profit Factor (Net R)**: **`1.32`** (OOS: `0.85`)
- **Ekspektasi Bersih ($\mathbb{E}[R]_{\text{net}}$)**: **`+0.0995R`** (95% Bootstrap CI: `[ +0.0030R, +0.1961R ]`)
- **Deflated Sharpe Ratio ($\text{DSR}$)**: **`0.8160`** (Sharpe per-trade: `0.116`)
- **Jumlah Kejadian Likuidasi 20x Isolated**: **`0`** (0 Likuidasi berkat Sniper SL Clamping $\le 1.80\%$)

---

## 2. Evaluasi Per-Strategi Triple-Barrier (`S1` – `S4`)

| Strategi | Sampel ($n$) | Win-Rate (%) | Profit Factor | $\mathbb{E}[R]_{\text{net}}$ | Bootstrap 95% CI | $\text{DSR}$ | Status Gate G2 |
|---|---|---|---|---|---|---|---|
| `S1_TREND_PULLBACK` | 80 | 67.5% | 1.66 | `+0.181R` | `[-0.016R, +0.378R]` | `0.791` | **SHADOW_ONLY** |
| `S2_OI_VOL_BREAKOUT` | 96 | 67.7% | 1.06 | `+0.022R` | `[-0.160R, +0.214R]` | `0.207` | **SHADOW_ONLY** |
| `S3_LIQ_CASCADE_FADE` | 57 | 71.9% | 1.18 | `+0.048R` | `[-0.132R, +0.221R]` | `0.297` | **SHADOW_ONLY** |
| `S4_EXTREME_FUNDING_REVERSION` | 54 | 72.2% | 1.59 | `+0.171R` | `[-0.052R, +0.405R]` | `0.646` | **SHADOW_ONLY** |

---

## 3. Hasil Simulasi Stres Adversary & Tail-Risk (`T1.4`)
- **Skenario S-1 (Flash-Wick `-3.5%` Stop-Hunt vs `MARK_PRICE` + SL Shield)**: `PASS` (Survived: `True`)
- **Skenario S-2 (Unmitigated Cascade `-10%` vs Breaker 2 Loss & Profit Vault)**: `PASS` (Liquidations: `0`, Vault Preserved 100%: `True`)
- **Skenario S-3 (API Latency Storm 10s vs Tri-State `UNKNOWN` Reconcile)**: `PASS` (Final SL State: `CONFIRMED`)
- **Stationary Block-Bootstrap (200 Lintasan)**: Median Cum R = `+30.78R`, P05 Tail Cum R = `+1.81R`, P95 Max Drawdown = `18.24R`
