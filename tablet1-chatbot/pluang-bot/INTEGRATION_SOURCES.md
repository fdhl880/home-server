# Integration Sources & Credits

Proyek ini mengintegrasikan konsep dan arsitektur dari repo-repo open source terbaik di bidang AI Trading:

## 1. TradingAgents — Tauric Research
**Repo:** https://github.com/TauricResearch/TradingAgents

**Konsep yang diadopsi:**
- Arsitektur multi-agent paralel: Technical Analyst, Sentiment Analyst, News/Fundamentals Analyst
- Bull Researcher vs Bear Researcher debate untuk mencapai konsensus
- Trader Agent yang mensintesis semua laporan analis
- Portfolio Manager sebagai final gatekeeper

**Implementasi di proyek ini:**
- `multi_agent_committee.py` — `run_technical_analyst()`, `run_sentiment_analyst()`, `run_bull_researcher()`, `run_bear_researcher()`, `run_trader_agent()`, `run_portfolio_manager()`

---

## 2. ai-hedge-fund — virattt
**Repo:** https://github.com/virattt/ai-hedge-fund

**Konsep yang diadopsi:**
- Investor-persona agents dengan gaya analisis berbeda
- Kelly Criterion untuk position sizing yang optimal
- Risk-adjusted return framework

**Implementasi di proyek ini:**
- `multi_agent_committee.py` — `run_fundamentals_agent()` dengan Kelly Criterion sizing
- `run_risk_officer()` menggunakan Kelly fraction untuk menentukan budget optimal

---

## 3. Vibe-Trading — HKUDS (Hong Kong University)
**Repo:** https://github.com/HKUDS/Vibe-Trading

**Konsep yang diadopsi:**
- Personal trading agent dengan shadow account tracking
- Backtest-aware risk management
- Macro analyst module untuk regime detection
- VaR (Value at Risk) calculation

**Implementasi di proyek ini:**
- `multi_agent_committee.py` — `run_macro_analyst()` dengan regime detection
- `run_risk_officer()` dengan VaR(95%) calculation
- Integration dengan existing pipeline 5-layer

---

## 4. LangAlpha — ginlix
**Repo:** https://github.com/ginlix-ai/LangAlpha

**Konsep yang diadopsi:**
- Agentic trading harness dengan persistent workspace
- Thesis-driven research loop (invest based on conviction, not single prompt)
- "A trade is a loop, not a tool call" philosophy
- Governance model: agent acts within user-defined permissions

**Implementasi di proyek ini:**
- `multi_agent_committee.py` — `save_thesis()` dan `get_active_thesis()` (persistent thesis per simbol)
- `THESIS_FILE` (active_thesis.json) — workspace persisten untuk setiap aset
- `/api/committee/thesis` endpoint untuk membaca active thesis

---

## 5. hummingbot — hummingbot Foundation
**Repo:** https://github.com/hummingbot/hummingbot

**Konsep yang diadopsi:**
- Market making spread calculator berdasarkan volatilitas dan volume
- Inventory management dan posisi seimbang
- Algorithmic trading patterns (bid-ask spread optimization)

**Implementasi di proyek ini:**
- `multi_agent_committee.py` — `calculate_optimal_spread()` untuk optimal bid-ask spread
- Spread info ditampilkan di UI setiap kali committee dijalankan
- `/api/committee/quick-screen` untuk screening massal universe (hummingbot-style)

---

## Arsitektur Multi-Agent Committee

```
                    +-------------------------------------+
                    ¦     ANALYST TEAM (Paralel)           ¦
                    ¦  +----------+  +------------------+ ¦
                    ¦  ¦Technical ¦  ¦Sentiment Analyst  ¦ ¦
                    ¦  ¦Analyst   ¦  ¦(TradingAgents)    ¦ ¦
                    ¦  +----------+  +------------------+ ¦
                    ¦  +----------+  +------------------+ ¦
                    ¦  ¦Fundament-¦  ¦Macro Analyst      ¦ ¦
                    ¦  ¦als Agent ¦  ¦(Vibe-Trading)     ¦ ¦
                    ¦  +----------+  +------------------+ ¦
                    +-------------------------------------+
                                   ¦
                    +--------------?----------------------+
                    ¦     RESEARCHER DEBATE                ¦
                    ¦  +-----------+  +-----------------+ ¦
                    ¦  ¦Bull       ¦  ¦Bear Researcher   ¦ ¦
                    ¦  ¦Researcher ¦  ¦(Risk Skeptic)    ¦ ¦
                    ¦  +-----------+  +-----------------+ ¦
                    +-------------------------------------+
                                   ¦
                    +--------------?----------------------+
                    ¦     EXECUTION LAYER                  ¦
                    ¦  Trader Agent ? Risk Officer         ¦
                    ¦  (Kelly Sizing + VaR)                ¦
                    ¦  ? Portfolio Manager (Final Gate)    ¦
                    +-------------------------------------+
                                   ¦
              +--------------------?------------------------+
              ¦     MARKET MAKING + THESIS (hummingbot +     ¦
              ¦     LangAlpha)                               ¦
              ¦     Spread Calculator + Persistent Workspace ¦
              +---------------------------------------------+
```

## API Endpoints Baru

| Endpoint | Method | Deskripsi |
|----------|--------|-----------|
| `/api/committee/run` | POST | Jalankan full 9-agent committee |
| `/api/committee/thesis` | GET | Baca persistent thesis workspace |
| `/api/committee/log` | GET | Log semua committee decisions |
| `/api/committee/quick-screen` | GET | Quick screening universe |
| `/api/committee/status` | GET | Status + source credits |

## Files Baru

- `multi_agent_committee.py` — Engine utama multi-agent committee
- `INTEGRATION_SOURCES.md` — Dokumentasi ini
