"""
PYROFUEL BOT - QUANT BACKTEST ENGINE v2 (TRIPLE-BARRIER, PURGED WALK-FORWARD, CSCV/PBO & STRATEGY GATE)
Task T1.3 / WP-6: Menjalankan evaluasi historis bebas-lookahead (closed-bar only),
non-overlapping per simbol, dengan biaya bersih realistis (Historical Funding Rate +
Volatility/Size Slippage + Wick/Gap Stop Slippage + Maker GTX Fill Realism),
Two-Stage Asymmetric Sniper Mode, Purged & Embargoed Walk-Forward CV, Frozen OOS Bandit,
Genuine CSCV/PBO, Honest Multiple-Trial DSR, per-regime & per-symbol OOS breakdowns,
serta emisi `results/strategy_gate.json` dan Simulasi Ruin Akun $20.
"""
import copy
import csv
from datetime import datetime, timezone
import os
import sys
from typing import Any, Dict, List, Optional, Sequence

BACKTEST_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BACKTEST_DIR)
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import numpy as np
from features.regime import detect_market_regime
from state_io import atomic_write_json
from strategies import (
    SetupCandidate,
    ContextualThompsonBandit,
    generate_all_candidates,
)
from backtest.fetch import load_funding_history
from backtest.triple_barrier import simulate_triple_barrier
from backtest.cpcv import (
    generate_purged_walk_forward_splits,
    bootstrap_ci95,
    deflated_sharpe_ratio,
    compute_cpcv_pbo,
)
from backtest.stress_simulator import (
    run_all_stress_scenarios,
    simulate_account_ruin_monte_carlo,
)

DATA_DIR = os.path.join(BACKTEST_DIR, "data")
RESULTS_DIR = os.path.join(ROOT_DIR, "results")
DEFAULT_GATE_PATH = os.path.join(RESULTS_DIR, "strategy_gate.json")
STRATEGY_IDS = (
    "S1_TREND_PULLBACK",
    "S2_OI_VOL_BREAKOUT",
    "S3_LIQ_CASCADE_FADE",
    "S4_EXTREME_FUNDING_REVERSION",
)


class _InMemoryBandit(ContextualThompsonBandit):
    """Isolated in-memory bandit clone used inside walk-forward training folds (no disk I/O)."""

    def __init__(self, source_bandit: Optional[ContextualThompsonBandit] = None, seed: Optional[int] = 42):
        self._initial_arms = copy.deepcopy(source_bandit.arms) if source_bandit is not None else {}
        super().__init__(
            discount_factor=source_bandit.discount_factor if source_bandit else 0.96,
            prior_alpha=source_bandit.prior_alpha if source_bandit else 2.0,
            prior_beta=source_bandit.prior_beta if source_bandit else 2.0,
            state_path=os.path.join(BACKTEST_DIR, ".in_memory_bandit_unused.json"),
            seed=seed,
        )
        self.arms = copy.deepcopy(self._initial_arms)

    def load_state(self) -> None:
        return None

    def save_state(self) -> bool:
        return True


class _FrozenBanditProxy(_InMemoryBandit):
    """Immutable bandit snapshot for Out-Of-Sample windows: OOS bars never mutate posteriors."""

    def get_arm(self, strategy_id: str, regime: str = "UNKNOWN") -> Dict[str, float]:
        with self._lock:
            key = self._arm_key(strategy_id, regime)
            if key in self.arms:
                return dict(self.arms[key])
            return {
                "alpha": self.prior_alpha,
                "beta": self.prior_beta,
                "n_updates": 0,
            }

    def update(
        self,
        strategy_id: str,
        regime: str = "UNKNOWN",
        r_net: Optional[float] = None,
        won: Optional[bool] = None,
    ) -> Dict[str, float]:
        # Intentionally frozen in OOS to prevent lookahead / OOS posterior leakage
        return self.get_arm(strategy_id, regime)


def load_candles(csv_path: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            item: Dict[str, Any] = {
                "open_time": int(float(r["open_time"])),
                "open": float(r["open"]),
                "high": float(r["high"]),
                "low": float(r["low"]),
                "close": float(r["close"]),
                "volume": float(r["volume"]),
                "close_time": int(float(r.get("close_time", int(float(r["open_time"])) + 3600_000))),
            }
            if "taker_buy_base" in r and r["taker_buy_base"]:
                item["taker_buy_base"] = float(r["taker_buy_base"])
            if "taker_buy_quote" in r and r["taker_buy_quote"]:
                item["taker_buy_quote"] = float(r["taker_buy_quote"])
            rows.append(item)
    return rows


def _estimate_bar_atr_pct(candles: Sequence[Dict[str, Any]], bar_idx: int, period: int = 14) -> float:
    start = max(1, bar_idx - period + 1)
    trs: List[float] = []
    for i in range(start, bar_idx + 1):
        hi = float(candles[i]["high"])
        lo = float(candles[i]["low"])
        prev_cl = float(candles[i - 1]["close"])
        tr = max(hi - lo, abs(hi - prev_cl), abs(lo - prev_cl))
        trs.append(tr)
    ref_cl = max(float(candles[bar_idx]["close"]), 1e-12)
    if not trs:
        hi = float(candles[bar_idx]["high"])
        lo = float(candles[bar_idx]["low"])
        return max(0.25, (hi - lo) / ref_cl * 100.0)
    return max(0.15, float(np.mean(trs)) / ref_cl * 100.0)


def evaluate_bar_no_lookahead(
    candles: Sequence[Dict[str, Any]],
    bar_idx: int,
    btc_candles: Optional[Sequence[Dict[str, Any]]] = None,
    symbol: str = "BTCUSDT",
    bandit: Optional[ContextualThompsonBandit] = None,
) -> Dict[str, Any]:
    """
    Evaluate regime and candidate strategies strictly using closed candles up to `bar_idx`
    (`candles[:bar_idx + 1]`). Future bars `candles[bar_idx + 1:]` are NEVER accessed.
    """
    history_slice = candles[max(0, bar_idx - 150) : bar_idx + 1]
    if btc_candles is not None and len(btc_candles) > bar_idx:
        btc_slice = btc_candles[max(0, bar_idx - 150) : bar_idx + 1]
    else:
        btc_slice = history_slice

    regime_state = detect_market_regime(btc_slice, history_slice)
    candidates = generate_all_candidates(
        history_slice,
        regime_state,
        symbol=symbol,
        bandit=bandit,
        deterministic_bandit=True,
    )
    return {
        "regime_state": regime_state,
        "candidates": candidates,
    }


def run_symbol_walk_forward(
    symbol: str,
    candles: Sequence[Dict[str, Any]],
    btc_candles: Optional[Sequence[Dict[str, Any]]] = None,
    sniper_mode: bool = True,
    bandit: Optional[ContextualThompsonBandit] = None,
    freeze_oos: bool = True,
    funding_series: Optional[Any] = None,
    atr_pct: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Run Purged & Embargoed Walk-Forward simulation on a single symbol with strict
    non-overlapping trade enforcement (`next_allowed_idx = i + bars_held`).
    When `freeze_oos=True` (default), OOS bars use an immutable bandit snapshot
    and NEVER leak or mutate bandit posteriors across folds.
    """
    n = len(candles)
    splits = generate_purged_walk_forward_splits(
        n_samples=n,
        n_splits=3,
        min_train_bars=80,
        purge_bars=16,
        embargo_pct=0.01,
    )

    oos_trades: List[Dict[str, Any]] = []
    in_sample_trades: List[Dict[str, Any]] = []

    for sp in splits:
        # Per-fold isolated training bandit cloned from caller's initial state
        fold_bandit: Optional[ContextualThompsonBandit] = (
            _InMemoryBandit(bandit) if bandit is not None else None
        )

        # 1. Train window (with purging before test_start)
        next_idx = max(35, int(sp["train_start"]))
        train_limit = int(sp["train_end"])
        while next_idx < train_limit:
            eval_res = evaluate_bar_no_lookahead(
                candles,
                next_idx,
                btc_candles=btc_candles,
                symbol=symbol,
                bandit=fold_bandit,
            )
            cands: List[SetupCandidate] = eval_res["candidates"]
            if not cands:
                next_idx += 1
                continue

            chosen = cands[0]
            horizon = min(chosen.vertical_barrier_bars, train_limit - (next_idx + 1))
            if horizon < 2:
                break
            future_slice = candles[next_idx + 1 : next_idx + 1 + horizon]
            bar_atr_pct = atr_pct if atr_pct is not None else _estimate_bar_atr_pct(candles, next_idx)
            sim = simulate_triple_barrier(
                chosen,
                future_slice,
                sniper_mode=sniper_mode,
                funding_series=funding_series,
                atr_pct=bar_atr_pct,
            )
            if sim.get("outcome") == "MAKER_NO_FILL":
                next_idx += 1
                continue

            if fold_bandit is not None:
                fold_bandit.update(chosen.strategy_id, chosen.regime, r_net=sim["r_multiple_net"])

            exit_idx = min(n - 1, next_idx + max(1, int(sim["bars_held"])))
            tr_rec = {
                "symbol": symbol,
                "fold": sp["fold"],
                "split": "TRAIN",
                "entry_idx": next_idx,
                "exit_idx": exit_idx,
                "open_time": int(candles[next_idx].get("open_time", 0)),
                "close_time": int(candles[exit_idx].get("close_time", 0)),
                "strategy_id": chosen.strategy_id,
                "regime": chosen.regime,
                "direction": chosen.direction,
                "sl_distance_pct": chosen.sl_distance_pct,
                **sim,
            }
            in_sample_trades.append(tr_rec)
            next_idx = next_idx + max(1, int(sim["bars_held"]))

        # 2. Out-Of-Sample Test window (after purge + embargo gap) with FROZEN bandit
        if freeze_oos and fold_bandit is not None:
            oos_bandit: Optional[ContextualThompsonBandit] = _FrozenBanditProxy(fold_bandit)
        else:
            oos_bandit = fold_bandit

        next_idx = max(35, int(sp["test_start"]))
        test_limit = int(sp["test_end"])
        while next_idx < test_limit - 2:
            eval_res = evaluate_bar_no_lookahead(
                candles,
                next_idx,
                btc_candles=btc_candles,
                symbol=symbol,
                bandit=oos_bandit,
            )
            cands = eval_res["candidates"]
            if not cands:
                next_idx += 1
                continue

            chosen = cands[0]
            horizon = min(chosen.vertical_barrier_bars, test_limit - (next_idx + 1))
            if horizon < 2:
                break
            future_slice = candles[next_idx + 1 : next_idx + 1 + horizon]
            bar_atr_pct = atr_pct if atr_pct is not None else _estimate_bar_atr_pct(candles, next_idx)
            sim = simulate_triple_barrier(
                chosen,
                future_slice,
                sniper_mode=sniper_mode,
                funding_series=funding_series,
                atr_pct=bar_atr_pct,
            )
            if sim.get("outcome") == "MAKER_NO_FILL":
                next_idx += 1
                continue

            # Strictly NO bandit.update() during OOS when freeze_oos=True!
            if (not freeze_oos) and oos_bandit is not None:
                oos_bandit.update(chosen.strategy_id, chosen.regime, r_net=sim["r_multiple_net"])

            # Fast barrier perturbations for honest CSCV/PBO matrix evaluation
            sim_alt_nosniper = simulate_triple_barrier(
                chosen,
                future_slice,
                sniper_mode=not sniper_mode,
                funding_series=funding_series,
                atr_pct=bar_atr_pct,
            )
            short_h = max(2, len(future_slice) // 2)
            sim_alt_short = simulate_triple_barrier(
                chosen,
                future_slice[:short_h],
                sniper_mode=sniper_mode,
                funding_series=funding_series,
                atr_pct=bar_atr_pct,
            )

            exit_idx = min(n - 1, next_idx + max(1, int(sim["bars_held"])))
            tr_rec = {
                "symbol": symbol,
                "fold": sp["fold"],
                "split": "OOS",
                "entry_idx": next_idx,
                "exit_idx": exit_idx,
                "open_time": int(candles[next_idx].get("open_time", 0)),
                "close_time": int(candles[exit_idx].get("close_time", 0)),
                "strategy_id": chosen.strategy_id,
                "regime": chosen.regime,
                "direction": chosen.direction,
                "sl_distance_pct": chosen.sl_distance_pct,
                "r_variant_nosniper": float(sim_alt_nosniper["r_multiple_net"]),
                "r_variant_short": float(sim_alt_short["r_multiple_net"]),
                **sim,
            }
            oos_trades.append(tr_rec)
            next_idx = next_idx + max(1, int(sim["bars_held"]))

    return {
        "symbol": symbol,
        "splits": splits,
        "train_trades": in_sample_trades,
        "oos_trades": oos_trades,
    }


def summarize_trades(trades: Sequence[Dict[str, Any]], num_trials: int = 4) -> Dict[str, Any]:
    n = len(trades)
    if n == 0:
        return {
            "n": 0,
            "wins": 0,
            "losses": 0,
            "win_rate_pct": 0.0,
            "profit_factor": 0.0,
            "expectancy_r": 0.0,
            "ci95_low": 0.0,
            "ci95_high": 0.0,
            "dsr": 0.0,
            "sharpe": 0.0,
            "liquidations": 0,
        }

    r_nets = [float(t["r_multiple_net"]) for t in trades]
    wins = [r for r in r_nets if r > 0]
    losses = [r for r in r_nets if r <= 0]
    wr_pct = len(wins) / n * 100.0
    gw = sum(wins)
    gl = abs(sum(losses))
    pf = gw / gl if gl > 1e-9 else (99.0 if gw > 0 else 0.0)
    mean_r, ci_low, ci_high = bootstrap_ci95(r_nets, n_boot=1000, seed=42)
    dsr_info = deflated_sharpe_ratio(r_nets, num_trials=num_trials)
    liqs = sum(1 for t in trades if t.get("liquidated"))

    return {
        "n": n,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": round(wr_pct, 2),
        "profit_factor": round(pf, 3),
        "expectancy_r": mean_r,
        "ci95_low": ci_low,
        "ci95_high": ci_high,
        "dsr": dsr_info["dsr"],
        "sharpe": dsr_info["sharpe"],
        "liquidations": liqs,
    }


def summarize_by_group(
    trades: Sequence[Dict[str, Any]],
    group_key: str,
    num_trials: int = 4,
) -> Dict[str, Dict[str, Any]]:
    """Aggregate `summarize_trades` metrics grouped by `group_key` (e.g. `regime` or `symbol`)."""
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for t in trades:
        key = str(t.get(group_key) or "UNKNOWN")
        grouped.setdefault(key, []).append(t)
    return {
        k: summarize_trades(grouped[k], num_trials=num_trials)
        for k in sorted(grouped.keys())
    }


def _bucket_index(ts_ms: int, min_ts: int, max_ts: int, n_buckets: int) -> int:
    if max_ts <= min_ts or n_buckets <= 1:
        return 0
    pos = (ts_ms - min_ts) / max(1, max_ts - min_ts)
    return int(min(n_buckets - 1, max(0, int(pos * n_buckets))))


def _compute_strategy_pbo(
    strategy_id: str,
    strategy_oos_trades: Sequence[Dict[str, Any]],
    all_oos_trades: Sequence[Dict[str, Any]],
    min_ts: int,
    max_ts: int,
) -> float:
    """
    Evaluate genuine CSCV/PBO over time-bucketed trial columns for `strategy_id`:
    columns = `[primary, no_sniper, short_horizon, peer_strategies...]`.
    Returns conservative PBO in [0.0, 1.0] (`1.0` when `n_oos < 3`).
    """
    if len(strategy_oos_trades) < 3:
        return 1.0

    n_buckets = min(48, max(8, len(all_oos_trades) // 2))
    cols: Dict[str, np.ndarray] = {
        "primary": np.zeros(n_buckets, dtype=np.float64),
        "alt_nosniper": np.zeros(n_buckets, dtype=np.float64),
        "alt_short": np.zeros(n_buckets, dtype=np.float64),
    }

    for tr in strategy_oos_trades:
        b = _bucket_index(int(tr.get("open_time", 0)), min_ts, max_ts, n_buckets)
        cols["primary"][b] += float(tr["r_multiple_net"])
        cols["alt_nosniper"][b] += float(tr.get("r_variant_nosniper", tr["r_multiple_net"]))
        cols["alt_short"][b] += float(tr.get("r_variant_short", tr["r_multiple_net"]))

    for peer_id in STRATEGY_IDS:
        if peer_id == strategy_id:
            continue
        peer_trades = [t for t in all_oos_trades if t.get("strategy_id") == peer_id]
        if peer_trades:
            arr = np.zeros(n_buckets, dtype=np.float64)
            for tr in peer_trades:
                b = _bucket_index(int(tr.get("open_time", 0)), min_ts, max_ts, n_buckets)
                arr[b] += float(tr["r_multiple_net"])
            cols[f"peer_{peer_id}"] = arr

    res = compute_cpcv_pbo(cols, n_splits=min(8, n_buckets // 2 * 2), purge_bars=1, embargo_bars=1)
    if res["n_combinations"] == 0:
        return 1.0
    return round(float(max(res["pbo"], res["prob_loss_oos"])), 4)


def _compute_global_cscv(
    all_oos_trades: Sequence[Dict[str, Any]],
    min_ts: int,
    max_ts: int,
) -> Dict[str, Any]:
    if len(all_oos_trades) < 4:
        return {"pbo": 1.0, "n_combinations": 0, "n_trials": 0}

    n_buckets = min(48, max(8, len(all_oos_trades) // 2))
    cols: Dict[str, np.ndarray] = {}
    for s_id in STRATEGY_IDS:
        s_trades = [t for t in all_oos_trades if t.get("strategy_id") == s_id]
        if not s_trades:
            continue
        c_main = np.zeros(n_buckets, dtype=np.float64)
        c_ns = np.zeros(n_buckets, dtype=np.float64)
        c_sh = np.zeros(n_buckets, dtype=np.float64)
        for tr in s_trades:
            b = _bucket_index(int(tr.get("open_time", 0)), min_ts, max_ts, n_buckets)
            c_main[b] += float(tr["r_multiple_net"])
            c_ns[b] += float(tr.get("r_variant_nosniper", tr["r_multiple_net"]))
            c_sh[b] += float(tr.get("r_variant_short", tr["r_multiple_net"]))
        cols[f"{s_id}|SNIPER"] = c_main
        cols[f"{s_id}|NOSNIPER"] = c_ns
        cols[f"{s_id}|SHORT_H"] = c_sh

    if len(cols) < 2:
        return {"pbo": 1.0, "n_combinations": 0, "n_trials": len(cols)}
    return compute_cpcv_pbo(cols, n_splits=min(8, n_buckets // 2 * 2), purge_bars=1, embargo_bars=1)


def _discover_candle_files(target_data_dir: str, interval: str) -> List[str]:
    all_csv = sorted(os.listdir(target_data_dir))
    preferred_suffix = f"_{interval}.csv"
    files = [
        os.path.join(target_data_dir, f)
        for f in all_csv
        if f.endswith(preferred_suffix)
    ]
    if files:
        return files

    # Fallback cleanly without overwriting across multiple intervals for the same symbol
    seen_syms = set()
    fallback: List[str] = []
    for suf in ("_1h.csv", "_15m.csv"):
        for f in all_csv:
            if f.endswith(suf):
                sym = f.split("_")[0]
                if sym not in seen_syms:
                    seen_syms.add(sym)
                    fallback.append(os.path.join(target_data_dir, f))
    return fallback


def run_backtest(
    sniper_mode: bool = True,
    interval: str = "1h",
    data_dir: Optional[str] = None,
    gate_output_path: Optional[str] = None,
    report_output_path: Optional[str] = None,
    n_trials: Optional[int] = None,
    write_outputs: bool = True,
) -> Dict[str, Any]:
    target_data_dir = data_dir or DATA_DIR
    if not os.path.exists(target_data_dir):
        print(f"[!] Direktori {target_data_dir} tidak ditemukan.")
        return {}

    files = _discover_candle_files(target_data_dir, interval=interval)
    if not files:
        print(f"[!] Tidak ada data candle di {target_data_dir}. Jalankan fetch.py terlebih dahulu.")
        return {}

    candles_by_symbol: Dict[str, List[Dict[str, Any]]] = {}
    funding_by_symbol: Dict[str, Dict[int, float]] = {}
    min_ts = None
    max_ts = None

    for csv_file in files:
        sym = os.path.basename(csv_file).split("_")[0]
        c_list = load_candles(csv_file)
        if not c_list:
            continue
        candles_by_symbol[sym] = c_list
        t0 = int(c_list[0].get("open_time", 0))
        t1 = int(c_list[-1].get("close_time", c_list[-1].get("open_time", 0)))
        if t0 > 0:
            min_ts = t0 if min_ts is None else min(min_ts, t0)
        if t1 > 0:
            max_ts = t1 if max_ts is None else max(max_ts, t1)

        fund_csv = os.path.join(target_data_dir, f"{sym}_funding.csv")
        if os.path.exists(fund_csv):
            funding_by_symbol[sym] = load_funding_history(fund_csv)

    if not candles_by_symbol:
        print(f"[!] Semua file candle kosong di {target_data_dir}.")
        return {}

    min_ts_i = int(min_ts or 0)
    max_ts_i = int(max_ts or 0)
    data_days = round(max(0.0, (max_ts_i - min_ts_i) / 86_400_000.0), 2) if max_ts_i > min_ts_i else 0.0

    btc_candles = candles_by_symbol.get("BTCUSDT")
    base_bandit = _InMemoryBandit(seed=42)

    all_oos: List[Dict[str, Any]] = []
    all_train: List[Dict[str, Any]] = []

    for sym, c_list in candles_by_symbol.items():
        res = run_symbol_walk_forward(
            symbol=sym,
            candles=c_list,
            btc_candles=btc_candles,
            sniper_mode=sniper_mode,
            bandit=base_bandit,
            freeze_oos=True,
            funding_series=funding_by_symbol.get(sym),
        )
        all_train.extend(res["train_trades"])
        all_oos.extend(res["oos_trades"])

    # Honest total trial count: strategies (4) * barrier variants (3) * symbols
    n_variants = 3
    effective_n_trials = (
        max(1, int(n_trials))
        if n_trials is not None
        else max(len(STRATEGY_IDS), len(STRATEGY_IDS) * n_variants * max(1, len(candles_by_symbol)))
    )

    combined_non_overlap = all_train + all_oos
    oos_summary = summarize_trades(all_oos, num_trials=effective_n_trials)
    full_summary = summarize_trades(combined_non_overlap, num_trials=effective_n_trials)

    global_cscv = _compute_global_cscv(all_oos, min_ts_i, max_ts_i)
    by_regime_oos = summarize_by_group(all_oos, "regime", num_trials=effective_n_trials)
    by_symbol_oos = summarize_by_group(all_oos, "symbol", num_trials=effective_n_trials)

    now_iso = datetime.now(timezone.utc).isoformat()
    by_strategy: Dict[str, Dict[str, Any]] = {}
    strategy_gate_entries: Dict[str, Dict[str, Any]] = {}

    for s_id in STRATEGY_IDS:
        s_oos_trades = [t for t in all_oos if t["strategy_id"] == s_id]
        s_all_trades = [t for t in combined_non_overlap if t["strategy_id"] == s_id]

        s_oos_sum = summarize_trades(s_oos_trades, num_trials=effective_n_trials)
        s_full_sum = summarize_trades(s_all_trades, num_trials=effective_n_trials)
        pbo_s = _compute_strategy_pbo(s_id, s_oos_trades, all_oos, min_ts_i, max_ts_i)

        verdict = (
            "LIVE_APPROVED"
            if (
                s_oos_sum["n"] >= 3
                and s_oos_sum["dsr"] >= 0.90
                and s_oos_sum["ci95_low"] > 0.0
                and pbo_s < 0.50
            )
            else "SHADOW_ONLY"
        )

        s_by_regime_oos = summarize_by_group(s_oos_trades, "regime", num_trials=effective_n_trials)
        s_by_symbol_oos = summarize_by_group(s_oos_trades, "symbol", num_trials=effective_n_trials)

        gate_entry = {
            "strategy_id": s_id,
            "dsr": s_oos_sum["dsr"],
            "pbo": pbo_s,
            "ci95_low": s_oos_sum["ci95_low"],
            "ci95_high": s_oos_sum["ci95_high"],
            "n_oos": s_oos_sum["n"],
            "wins_oos": s_oos_sum["wins"],
            "losses_oos": s_oos_sum["losses"],
            "win_rate_oos_pct": s_oos_sum["win_rate_pct"],
            "pf_oos": s_oos_sum["profit_factor"],
            "expectancy_r_oos": s_oos_sum["expectancy_r"],
            "sharpe_oos": s_oos_sum["sharpe"],
            "verdict": verdict,
            "data_days": data_days,
            "updated_at": now_iso,
            "by_regime_oos": s_by_regime_oos,
            "by_symbol_oos": s_by_symbol_oos,
        }
        strategy_gate_entries[s_id] = gate_entry

        by_strategy[s_id] = {
            **s_full_sum,
            "n_oos": s_oos_sum["n"],
            "pf_oos": s_oos_sum["profit_factor"],
            "expectancy_r_oos": s_oos_sum["expectancy_r"],
            "ci95_low_oos": s_oos_sum["ci95_low"],
            "dsr_oos": s_oos_sum["dsr"],
            "pbo": pbo_s,
            "verdict": verdict,
            "enabled_recommendation": bool(verdict == "LIVE_APPROVED"),
        }

    oos_r_list = [float(t["r_multiple_net"]) for t in all_oos]
    all_r_list = [float(t["r_multiple_net"]) for t in combined_non_overlap]
    stress_res = run_all_stress_scenarios(oos_r_list if oos_r_list else all_r_list)
    mc_20 = simulate_account_ruin_monte_carlo(
        oos_r_list if oos_r_list else all_r_list,
        initial_equity=20.0,
        leverage=20,
        all_in_fraction=0.95,
        min_notional=5.0,
        breaker_losses=2,
        n_paths=1000,
    )

    strategy_gate_payload: Dict[str, Any] = {
        "schema_version": 1,
        "updated_at": now_iso,
        "data_days": data_days,
        "interval": interval,
        "n_symbols": len(candles_by_symbol),
        "n_trials": effective_n_trials,
        "global_pbo": global_cscv["pbo"],
        "global_oos": oos_summary,
        "strategies": strategy_gate_entries,
        "by_regime_oos": by_regime_oos,
        "by_symbol_oos": by_symbol_oos,
        "monte_carlo_20_account": mc_20,
    }

    report_md = f"""# LAPORAN VALIDASI BACKTEST v2 — PURGED WALK-FORWARD, CSCV/PBO & STRATEGY GATE

## 1. Ringkasan Eksekutif Out-of-Sample (OOS) & Walk-Forward Non-Overlapping
- **Metodologi Validasi**: Purged & Embargoed Walk-Forward CV + CSCV/PBO + Frozen OOS Bandit (`{data_days:.1f}` hari, `K={effective_n_trials}` trials)
- **Mode Manajemen Posisi**: `HIGH_PRECISION_SNIPER_MODE` (`TP1 = +0.55R` mengunci `SL = +0.38R`, Runner `TP2 >= +1.65R`)
- **Model Biaya Bersih**: Historical Funding 8h + Vol/Size Slippage + Wick/Gap SL Slippage + Maker GTX Realism
- **Total Sampel Non-Overlapping ($N$)**: `{full_summary['n']}` trade (`OOS Murni`: `{oos_summary['n']}` trade)
- **Realized Win-Rate (OOS)**: **`{oos_summary['win_rate_pct']:.2f}%`** (Combined: `{full_summary['win_rate_pct']:.2f}%`)
- **Profit Factor (OOS Net R)**: **`{oos_summary['profit_factor']:.2f}`** (Combined: `{full_summary['profit_factor']:.2f}`)
- **Ekspektasi Bersih OOS ($\\mathbb{{E}}[R]_{{\\text{{net}}}}$)**: **`{oos_summary['expectancy_r']:+.4f}R`** (95% CI: `[ {oos_summary['ci95_low']:+.4f}R, {oos_summary['ci95_high']:+.4f}R ]`)
- **Deflated Sharpe Ratio ($\\text{{DSR}}$ OOS, $K={effective_n_trials}$)**: **`{oos_summary['dsr']:.4f}`** (Global CSCV PBO: `{global_cscv['pbo']:.3f}`)
- **Jumlah Kejadian Likuidasi 20x Isolated**: **`{oos_summary['liquidations']}`**

---

## 2. Evaluasi OOS Per-Strategi & Strategy Gate (`S1` – `S4`)

| Strategi | $n_{{\\text{{OOS}}}}$ | WR OOS (%) | PF OOS | $\\mathbb{{E}}[R]_{{\\text{{OOS}}}}$ | 95% CI Low | $\\text{{DSR}}$ | $\\text{{PBO}}$ | Verdict |
|---|---|---|---|---|---|---|---|---|
"""
    for s_id in STRATEGY_IDS:
        ge = strategy_gate_entries[s_id]
        report_md += (
            f"| `{s_id}` | {ge['n_oos']} | {ge['win_rate_oos_pct']:.1f}% | {ge['pf_oos']:.2f} | "
            f"`{ge['expectancy_r_oos']:+.3f}R` | `{ge['ci95_low']:+.3f}R` | "
            f"`{ge['dsr']:.3f}` | `{ge['pbo']:.3f}` | **{ge['verdict']}** |\n"
        )

    report_md += f"""
---

## 3. Simulasi Stres Adversary & Monte Carlo Akun Nyata \\$20 (`20x ALL-IN`)
- **Skenario S-1 (Flash-Wick `-3.5%` Stop-Hunt vs `MARK_PRICE` + SL Shield)**: `{"PASS" if stress_res["S1_FLASH_WICK"]["passed"] else "FAIL"}` (Survived: `{stress_res["S1_FLASH_WICK"]["survived_flash_wick"]}`)
- **Skenario S-2 (Unmitigated Cascade `-10%` vs Breaker 2 Loss & Profit Vault)**: `{"PASS" if stress_res["S2_UNMITIGATED_CASCADE_10PCT"]["passed"] else "FAIL"}` (Liquidations: `{stress_res["S2_UNMITIGATED_CASCADE_10PCT"]["liquidations"]}`, Vault Preserved 100%: `{stress_res["S2_UNMITIGATED_CASCADE_10PCT"]["vault_preserved_100pct"]}`)
- **Skenario S-3 (API Latency Storm 10s vs Tri-State `UNKNOWN` Reconcile)**: `{"PASS" if stress_res["S3_API_LATENCY_STORM"]["passed"] else "FAIL"}` (Final SL State: `{stress_res["S3_API_LATENCY_STORM"]["final_sl_state"]}`)
- **Stationary Block-Bootstrap (200 Lintasan)**: Median Cum R = `{stress_res["BLOCK_BOOTSTRAP"]["median_cum_r"]:+.2f}R`, P05 Tail Cum R = `{stress_res["BLOCK_BOOTSTRAP"]["p05_cum_r"]:+.2f}R`, P95 Max Drawdown = `{stress_res["BLOCK_BOOTSTRAP"]["max_dd_p95_r"]:.2f}R`
- **Monte Carlo Akun \\$20 (1000 Lintasan, 20x ALL-IN, `minNotional=\\$5`, Breaker 2-Loss)**: Ruin Prob = `{mc_20['ruin_probability']:.2%}`, Median Final Equity = `\\${mc_20['median_final_equity']:.2f}`, P05 Equity = `\\${mc_20['p05_final_equity']:.2f}`
"""

    target_gate_path = gate_output_path or DEFAULT_GATE_PATH
    target_report_path = report_output_path or os.path.join(BACKTEST_DIR, "report_v2.md")

    if write_outputs:
        atomic_write_json(target_gate_path, strategy_gate_payload, make_bak=True)
        os.makedirs(os.path.dirname(os.path.abspath(target_report_path)), exist_ok=True)
        with open(target_report_path, "w", encoding="utf-8") as f:
            f.write(report_md)

    print(
        f"[OK] Backtest v2 selesai! Non-overlap n={full_summary['n']} (OOS n={oos_summary['n']}), "
        f"OOS WR={oos_summary['win_rate_pct']:.1f}%, OOS PF={oos_summary['profit_factor']:.2f}, "
        f"OOS E[R]_net={oos_summary['expectancy_r']:+.3f}R (CI95: [{oos_summary['ci95_low']:+.3f}R, {oos_summary['ci95_high']:+.3f}R]), "
        f"OOS DSR={oos_summary['dsr']:.3f} (K={effective_n_trials}), PBO={global_cscv['pbo']:.3f}"
    )

    return {
        "full_summary": full_summary,
        "oos_summary": oos_summary,
        "by_strategy": by_strategy,
        "by_regime_oos": by_regime_oos,
        "by_symbol_oos": by_symbol_oos,
        "strategy_gate": strategy_gate_payload,
        "stress_results": stress_res,
        "monte_carlo_20_account": mc_20,
        "trades": combined_non_overlap,
        "oos_trades": all_oos,
        "report_path": target_report_path,
        "gate_path": target_gate_path,
    }


if __name__ == "__main__":
    run_backtest()
