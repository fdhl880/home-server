'use strict';
/**
 * BLOOMBERG TERMINAL EXTENSIONS & PERSONAL FINANCE ENGINE
 * - GET  /api/terminal/factors        (100% Transparent Bot Glass-Box: Layer 1-6, 532 Factors, 28 Pillars, Gear & Vault)
 * - GET  /api/terminal/bot-xray       (Alias for full Bot Decision Transparency X-Ray)
 * - GET  /api/terminal/transcripts    (9-Agent Adversarial Debate Transcripts + AI Memory + Corporate Earnings Transcripts)
 * - GET  /api/terminal/intelligence   (Bloomberg Intelligence BI <GO> Research Dossier)
 * - GET  /api/terminal/flows          (Spot Crypto & Macro ETF Flows, Futures Squeeze Pressure & SEC Form-4 Insiders)
 * - GET/POST/DELETE /api/finance/*    (Personal Finance, Cashflow, Savings Goals & Anti-Boros Budget Manager)
 */
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const agg = require('./aggregator');
const edgarP = require('./providers/edgar_fundamentals');
const newsP = require('./providers/news');
const U = require('./util');

function buildWarrenBuffettPlan(monthlyIncomeRaw = 1000000) {
  const income = Math.max(100000, Math.round(Number(monthlyIncomeRaw) || 1000000));
  // Warren Buffett "Pay Yourself First" Principle (Tailored for Food & Transport Only):
  // "Do not save what is left after spending, but spend what is left after saving."
  // 40% Pay Yourself First (25% Productive Investment Capital + 15% Emergency Margin of Safety)
  // 60% Operating Expenses (45% Food & Refreshments + 15% Transportation)
  const investIdr = Math.round(income * 0.25);
  const emergencyIdr = Math.round(income * 0.15);
  const payYourselfFirstIdr = investIdr + emergencyIdr; // 40% locked first

  const spendableMonthlyIdr = income - payYourselfFirstIdr; // 60% spendable operating ceiling
  const foodIdr = Math.round(income * 0.45);
  const transportIdr = Math.max(0, spendableMonthlyIdr - foodIdr); // 15%

  // Clean daily ceiling (Rp 20.000/day for Rp 1.000.000/month)
  const dailyLimitIdr = Math.max(5000, Math.floor((spendableMonthlyIdr / 30) / 500) * 500);
  const foodDailyIdr = Math.floor((foodIdr / 30) / 500) * 500;
  const transportDailyIdr = Math.floor((transportIdr / 30) / 500) * 500;

  // Future value compounding projection (monthly investIdr at annual rate r + liquid emergencyIdr at 3%)
  const fv = (pmt, annualRate, years) => {
    const r = annualRate / 12;
    const n = years * 12;
    if (r <= 0) return Math.round(pmt * n);
    return Math.round(pmt * ((Math.pow(1 + r, n) - 1) / r));
  };

  const projections = [1, 3, 5, 10].map(yr => ({
    years: yr,
    principalIdr: payYourselfFirstIdr * yr * 12,
    conservativeIdr: fv(investIdr, 0.08, yr) + fv(emergencyIdr, 0.03, yr),
    benchmarkIdr: fv(investIdr, 0.12, yr) + fv(emergencyIdr, 0.04, yr)
  }));

  return {
    method: 'WARREN_BUFFETT',
    methodTitle: 'Warren Buffett Capital Allocation (Pay Yourself First)',
    principle: 'Sisihkan 40% tabungan & modal investasi di hari pertama; gunakan 60% sisanya khusus untuk Makan/Jajan (45%) dan Transportasi (15%).',
    monthlyIncomeIdr: income,
    payYourselfFirstIdr,
    payYourselfFirstPct: 40,
    spendableMonthlyIdr,
    spendableMonthlyPct: 60,
    dailyLimitIdr,
    foodDailyIdr,
    transportDailyIdr,
    buckets: [
      { id: 'INVEST', tier: 'PAY YOURSELF FIRST', name: 'Productive Investment Capital', pct: 25, amountIdr: investIdr, color: '#00d26a', desc: 'Modal investasi aset produktif jangka panjang (compounding).' },
      { id: 'EMERGENCY', tier: 'PAY YOURSELF FIRST', name: 'Emergency Margin of Safety', pct: 15, amountIdr: emergencyIdr, color: '#00e5ff', desc: 'Cadangan kas darurat likuid untuk keamanan & peluang.' },
      { id: 'FOOD', tier: 'OPERATING EXPENSE', name: 'Food & Refreshments', pct: 45, amountIdr: foodIdr, color: '#ffb000', desc: `Alokasi makan & jajan harian (~Rp ${foodDailyIdr.toLocaleString('id-ID')}/hari).` },
      { id: 'TRANSPORT', tier: 'OPERATING EXPENSE', name: 'Transportation', pct: 15, amountIdr: transportIdr, color: '#4da3ff', desc: `Alokasi transportasi & mobilitas harian (~Rp ${transportDailyIdr.toLocaleString('id-ID')}/hari).` }
    ],
    categoryLimits: {
      'Food & Refreshments': foodIdr,
      'Transportation': transportIdr
    },
    projections
  };
}

const _DEFAULT_WB = buildWarrenBuffettPlan(1000000);
const DEFAULT_FINANCE = {
  currency: 'IDR',
  allocationMethod: 'WARREN_BUFFETT',
  monthlyIncomeTarget: _DEFAULT_WB.monthlyIncomeIdr,
  monthlyBudgetIdr: _DEFAULT_WB.spendableMonthlyIdr,
  dailyLimitIdr: _DEFAULT_WB.dailyLimitIdr,
  categoryLimits: { ..._DEFAULT_WB.categoryLimits },
  goals: [
    { id: 'GOAL-10M', name: 'Milestone I: First Rp 10.000.000', targetIdr: 10000000, savedIdr: 516000, deadline: '2028-11-30', category: 'MILESTONE', autoIntegrate: true },
    { id: 'GOAL-100M', name: 'Milestone II: First Rp 100.000.000', targetIdr: 100000000, savedIdr: 516000, deadline: '2031-11-30', category: 'MILESTONE', autoIntegrate: true },
    { id: 'GOAL-1B', name: 'Milestone III: First Rp 1.000.000.000 (1 Miliar)', targetIdr: 1000000000, savedIdr: 516000, deadline: '2036-11-30', category: 'MILESTONE', autoIntegrate: true },
    { id: 'GOAL-EMERGENCY', name: 'Emergency Margin of Safety (6 Months Operating)', targetIdr: 3600000, savedIdr: 150000, deadline: '2027-11-30', category: 'SAFETY' },
    { id: 'GOAL-INVEST', name: 'Productive Investment Capital Reserve', targetIdr: 6000000, savedIdr: 226000, deadline: '2028-11-30', category: 'INVEST' }
  ],
  transactions: [
    {
      id: 'TX-INIT-INV',
      ts: 1795526402000,
      date: '2026-11-24',
      type: 'SAVINGS',
      category: 'Productive Investment Capital',
      amountIdr: 226000,
      note: 'Warren Buffett Surplus Lock — Productive Non-Leverage Reserve'
    },
    {
      id: 'TX-INIT-EMG',
      ts: 1795526401000,
      date: '2026-11-24',
      type: 'SAVINGS',
      category: 'Emergency Margin of Safety',
      amountIdr: 150000,
      note: 'Warren Buffett Emergency Margin of Safety (15% Cash Buffer)'
    },
    {
      id: 'TX-INIT-BAL',
      ts: 1795526400000,
      date: '2026-11-24',
      type: 'INCOME',
      category: 'Monthly Fixed Allowance',
      amountIdr: 516000,
      note: 'Opening Bank Account Balance (Operating Cash Remaining: Rp 140.000 for 7 days)'
    }
  ]
};

function normBotFilePrefix(sym) {
  const s = String(sym || 'BTCUSDT').trim().toUpperCase().replace(/\.P$/, '');
  if (s.endsWith('USDT')) return s.slice(0, -4) + '_USD';
  if (s.endsWith('-USD')) return s.replace('-', '_');
  if (s.includes('_')) return s;
  return s + '_USD';
}

function safeReadJson(filePath, fallback = null) {
  try {
    if (!filePath || !fs.existsSync(filePath)) return fallback;
    return JSON.parse(fs.readFileSync(filePath, 'utf8'));
  } catch {
    return fallback;
  }
}

function listScannedCoinFiles(resultsDir) {
  const out = [];
  try {
    if (!fs.existsSync(resultsDir)) return out;
    const files = fs.readdirSync(resultsDir).filter(f => f.endsWith('_latest.json'));
    for (const f of files) {
      const full = path.join(resultsDir, f);
      const st = fs.statSync(full);
      const data = safeReadJson(full, null);
      if (!data || typeof data !== 'object') continue;
      const l5 = data.layer5_final_call || {};
      const l2 = data.layer2_setup || {};
      const mp = data.math_proof || (data.layer1_scanning && data.layer1_scanning.math_proof) || {};
      out.push({
        file: f,
        symbol: data.symbol || f.replace('_latest.json', '').replace('_', '-'),
        mtimeMs: st.mtimeMs,
        timestamp: data.timestamp || new Date(st.mtimeMs).toISOString(),
        status: data.status || l5.status || 'UNKNOWN',
        direction: l5.direction || l2.direction || 'NONE',
        setup: l2.setup_name || l5.setup_name || 'N/A',
        confidence: Number(l5.confidence_score || 0),
        p_math: Number(mp.p_math_pct || 0),
        regime: mp.statistical_regime || 'NORMAL',
        committeeApproved: Boolean(data.committee && data.committee.approved),
        hasCommittee: Boolean(data.committee),
        reason: String(l5.final_reason || '').slice(0, 140)
      });
    }
    out.sort((a, b) => b.mtimeMs - a.mtimeMs);
  } catch {}
  return out;
}

function buildFactorRadarAndPillars(scanData, activePos, gearState, vaultState, cfg) {
  const l1 = (scanData && scanData.layer1_scanning) || {};
  const l2 = (scanData && scanData.layer2_setup) || {};
  const l3 = (scanData && scanData.layer3_plan) || {};
  const l4 = (scanData && scanData.layer4_risk) || {};
  const l5 = (scanData && scanData.layer5_final_call) || {};
  const com = (scanData && scanData.committee) || null;
  const mp = (scanData && scanData.math_proof) || l1.math_proof || (activePos && activePos.math_proof) || {};
  const qf = l1.quant_factors || {};
  const ns3 = l5.neuro_symbolic_3brain || (scanData && scanData.neuro_symbolic_3brain) || {};
  const tpPred = l3.tp_time_prediction || (scanData && scanData.tp_time_prediction) || {};
  const roiProj = l5.roi_pnl_projection || l3.roi_pnl_projection || (scanData && scanData.roi_pnl_projection) || (activePos && activePos.roi_pnl_projection) || {};

  const clamp = (v, lo = 0, hi = 100) => Math.max(lo, Math.min(hi, Number.isFinite(+v) ? +v : 0));
  const dirSign = String(l5.direction || l2.direction || (activePos && activePos.direction) || mp.preferred_direction || 'LONG').toUpperCase() === 'SHORT' ? -1 : 1;

  const q532 = Number(mp.composite_532_factors ?? qf.composite_quant_score ?? 50);
  const pMath = Number(mp.p_math_pct ?? l5.math_score_pct ?? 50);
  const pAi = Number(mp.p_ai_pct ?? l5.ai_score_pct ?? l2.probability_pct ?? 50);
  const sHybrid = Number(mp.s_hybrid_pct ?? l5.hybrid_score_pct ?? l5.confidence_score ?? 50);
  const obi20 = Number(mp.obi_weighted_20 ?? 0);
  const hurst = Number(mp.hurst_exponent ?? 0.50);
  const adx = Number(mp.adx_14 ?? 0);
  const vpin = Number(mp.vpin ?? 0.35);
  const vpinCdf = Number(mp.vpin_cdf ?? 0.50);
  const hmmP = Number(mp.hmm_cascade_prob ?? 0.10);
  const fptP1 = Number(tpPred.p_hit_tp1_before_sl_pct ?? 65);
  const newsScore = Number((l1.news_macro && l1.news_macro.sentiment_score) || 50);
  const riskPassPct = Number(l4.pass_rate_pct ?? ((Number(l4.total_score || 0) / Math.max(1, Number(l4.max_score || 8))) * 100));

  // 8-Axis Visual Radar for Transparent Decision Inspection
  const radarAxes = [
    { axis: '532-QUANT', score: clamp(50 + Math.abs(q532 - 50) * 2.2), raw: `${q532.toFixed(1)}/100` },
    { axis: 'TREND/ADX', score: clamp(adx * 2.1 + (hurst > 0.55 ? 20 : 0)), raw: `ADX ${adx.toFixed(1)} | H=${hurst.toFixed(2)}` },
    { axis: 'ORDERFLOW', score: clamp(50 + dirSign * obi20 * 75), raw: `OBI20 ${obi20 >= 0 ? '+' : ''}${obi20.toFixed(2)}` },
    { axis: 'CLEAN FLOW', score: clamp(100 - vpinCdf * 70 - hmmP * 30), raw: `VPIN ${vpin.toFixed(2)} | HMM ${(hmmP * 100).toFixed(0)}%` },
    { axis: 'AI SETUP', score: clamp(pAi), raw: `${l2.setup_name || 'N/A'} (${l2.confluence_count || 0} conf)` },
    { axis: 'FPT PROB', score: clamp(fptP1), raw: `P(TP1<SL) ${fptP1.toFixed(1)}%` },
    { axis: 'RISK AUDIT', score: clamp(riskPassPct), raw: `${l4.total_score || 0}/${l4.max_score || 8} PASS` },
    { axis: 'MACRO/NEWS', score: clamp(50 + dirSign * (newsScore - 50) * 1.4), raw: `News ${newsScore.toFixed(0)}/100` }
  ];

  // Contribution Waterfall for P_Math Formula
  const waterfall = [
    { label: 'Base Prior', pts: 54.0, note: 'Institutional neutral base' },
    { label: '532-Factor Edge', pts: +(Math.min(22, Math.abs(q532 - 50) * 1.45)).toFixed(2), note: `Q_532 = ${q532.toFixed(2)}` },
    { label: 'Orderbook OBI-20', pts: Number(mp.ofi_contribution_pts || 0), note: `L2 20-level OBI = ${obi20.toFixed(3)}` },
    { label: 'Hurst Regime', pts: Number(mp.hurst_contribution_pts || 0), note: `${mp.hurst_interpretation || 'NORMAL'} (H=${hurst.toFixed(3)})` },
    { label: 'MTF Alignment (1H+1D)', pts: Number(mp.mtf_contribution_pts || 0), note: `1H=${l1.ema_trend || '-'} / 1D=${(scanData && scanData.layer1_scanning && scanData.layer1_scanning.daily_trend) || '-'}` },
    { label: 'News & Macro', pts: Number(mp.news_contribution_pts || 0), note: (l1.news_macro && l1.news_macro.market_sentiment) || 'NEUTRAL' },
    { label: 'Retail Crowd Penalty', pts: Number(mp.crowd_trap_penalty_pts || 0), note: `L/S Ratio = ${(l1.long_short_ratio && l1.long_short_ratio.long_short_ratio) || '1.0'}` }
  ];

  // Transparent 7-Stage Pipeline Funnel
  const minConf = Number((cfg && cfg.min_confidence_score) || 68);
  const sniperCfg = (cfg && cfg.sniper_75_mode) || {};
  const minMath = Number(sniperCfg.min_math_pct || 58);
  const minFpt = Number(sniperCfg.min_first_passage_pct || 58);
  const entryPx = Number(l5.entry_price || l3.entry_price || (activePos && activePos.entry_price) || l1.current_price || 0);
  const slPx = Number(l5.stop_loss || l3.stop_loss || (activePos && activePos.stop_loss) || 0);
  const tp1Px = Number(l5.take_profit_1 || l3.take_profit_1 || (activePos && activePos.take_profit_1) || 0);
  const tp2Px = Number(l5.take_profit_2 || l5.take_profit || l3.take_profit_2 || (activePos && activePos.take_profit_2) || 0);
  const slDistPct = entryPx > 0 && slPx > 0 ? +(Math.abs(entryPx - slPx) / entryPx * 100).toFixed(2) : 0;
  const rrrVal = entryPx > 0 && slPx > 0 && tp2Px > 0 && Math.abs(entryPx - slPx) > 0
    ? +(Math.abs(tp2Px - entryPx) / Math.abs(entryPx - slPx)).toFixed(2)
    : 0;

  const pipelineStages = [
    {
      stage: 'LAYER 1',
      name: 'Quant Math + Microstructure + Regime',
      passed: pMath >= minMath,
      metric: `P_Math ${pMath.toFixed(1)}% (min ${minMath}%)`,
      detail: `Regime=${mp.statistical_regime || 'NORMAL'} | Q532=${q532.toFixed(1)} | ADX=${adx.toFixed(1)} | OBI20=${obi20.toFixed(2)} | VPIN=${vpin.toFixed(2)} | Hawkes=${mp.hawkes_state || 'BASELINE'}`
    },
    {
      stage: 'LAYER 2',
      name: 'AI Setup Hunter (gpt-oss-120b)',
      passed: Boolean(l2.setup_name && l2.setup_name !== 'NO_CLEAR_SETUP' && Number(l2.confluence_count || 0) >= 2),
      metric: `${l2.setup_name || 'NONE'} (${l2.direction || 'NONE'}) · ${l2.probability_pct || 0}%`,
      detail: (Array.isArray(l2.confluences) && l2.confluences.length ? l2.confluences.join(' • ') : (l2.explanation_id || 'Waiting for confluence'))
    },
    {
      stage: 'LAYER 3',
      name: 'Plan Architect + First-Passage Time (FPT)',
      passed: entryPx > 0 && slDistPct >= 0.85 && slDistPct <= 2.30 && rrrVal >= 1.75 && fptP1 >= minFpt,
      metric: `SL ${slDistPct}% | RRR 1:${rrrVal} | FPT ${fptP1.toFixed(1)}%`,
      detail: `Entry $${entryPx} | SL $${slPx} | TP1 $${tp1Px} | TP2 $${tp2Px} | ETA: ${tpPred.eta_label || 'N/A'}`
    },
    {
      stage: 'LAYER 4',
      name: 'Chief Risk Officer (8-Point Audit)',
      passed: Number(l4.total_score || 0) >= 5,
      metric: `Score ${l4.total_score || 0}/${l4.max_score || 8} (${l4.recommendation || 'N/A'})`,
      detail: l4.reasoning || 'Risk audit completed'
    },
    {
      stage: 'LAYER 5',
      name: 'Supreme Judge + 13 Python Safety Gates',
      passed: String(l5.status || '').toUpperCase().startsWith('APPROVED') || Boolean(activePos),
      metric: `Hybrid ${sHybrid.toFixed(1)}% (min ${minConf}%) · ${l5.status || 'N/A'}`,
      detail: l5.final_reason || 'Evaluated across 13 deterministic safety rails'
    },
    {
      stage: 'LAYER 6',
      name: 'Sidang 9-Agent Adversarial Veto Committee',
      passed: Boolean(com && com.approved) || Boolean(activePos && !com),
      metric: com ? `${com.approved ? 'APPROVED' : 'VETOED'} (${com.direction || 'SKIP'} · ${com.elapsed_sec || com.duration_sec || '?'}s)` : 'SKIPPED (Not reached)',
      detail: (com && com.portfolio_manager && com.portfolio_manager.decision) || (activePos ? 'Approved & Executed on Binance Futures' : 'Only invoked after Layer 5 APPROVED')
    }
  ];

  // Detailed 28-Pillar Telemetry Checklist
  const pillars = [
    { id: 'P01', group: 'QUANT', name: '532-Factor Composite Q_532', val: `${q532.toFixed(2)} / 100`, ok: q532 !== 50 },
    { id: 'P02', group: 'QUANT', name: 'Deterministic P_Math Edge', val: `${pMath.toFixed(2)}%`, ok: pMath >= minMath },
    { id: 'P03', group: 'REGIME', name: 'Hurst Exponent Persistence', val: `${hurst.toFixed(4)} (${mp.hurst_interpretation || '-'})`, ok: hurst < 0.45 || hurst > 0.55 },
    { id: 'P04', group: 'REGIME', name: 'Variance Ratio (q=4)', val: `${Number(mp.variance_ratio_q4 || 1).toFixed(3)} (z=${Number(mp.variance_ratio_z || 0).toFixed(2)})`, ok: true },
    { id: 'P05', group: 'REGIME', name: 'ADX-14 Trend Strength', val: `${adx.toFixed(2)} (${mp.statistical_regime || 'NORMAL'})`, ok: adx >= 20 },
    { id: 'P06', group: 'REGIME', name: '3-State Gaussian HMM', val: `${mp.hmm_state || 'STATE_0'} (Cascade ${(hmmP * 100).toFixed(1)}%)`, ok: hmmP < 0.85 },
    { id: 'P07', group: 'MICRO', name: 'L2 Orderbook Imbalance (OBI-20)', val: `${obi20 >= 0 ? '+' : ''}${obi20.toFixed(4)} | Spread ${Number(mp.spread_bps || 0).toFixed(2)} bps`, ok: dirSign * obi20 > -0.28 },
    { id: 'P08', group: 'MICRO', name: 'VPIN Toxic Flow Sensor', val: `VPIN ${vpin.toFixed(3)} (CDF ${(vpinCdf * 100).toFixed(0)}%)`, ok: !mp.vpin_toxic_veto },
    { id: 'P09', group: 'MICRO', name: 'Hawkes Self-Exciting Cascade', val: `${mp.hawkes_state || 'BASELINE'} (r+=${mp.hawkes_ratio_plus || 1}, r-=${mp.hawkes_ratio_minus || 1})`, ok: mp.hawkes_state === 'BASELINE' || !mp.hawkes_state },
    { id: 'P10', group: 'MICRO', name: '15m Exhaustion Micro-Timing', val: `RSI15m=${mp.rsi_15m ?? '-'} | EMA20 Dist=${mp.dist_ema20_atr_15m ?? '-'} ATR`, ok: true },
    { id: 'P11', group: 'DERIV', name: 'Perpetual Funding Rate', val: `${Number(mp.funding_rate_pct || 0).toFixed(4)}%`, ok: Math.abs(Number(mp.funding_rate_pct || 0)) < 0.05 },
    { id: 'P12', group: 'DERIV', name: 'Long/Short Crowd Ratio', val: `${(l1.long_short_ratio && l1.long_short_ratio.long_short_ratio) || '1.00'}x`, ok: Number(mp.crowd_trap_penalty_pts || 0) === 0 },
    { id: 'P13', group: 'DERIV', name: 'Synthetic Liquidation SL Shield', val: mp.sl_liq_shielded ? `SHIELDED -> $${mp.sl_liq_shielded_to}` : `LongMag $${mp.nearest_long_liq_magnet || '-'} / ShortMag $${mp.nearest_short_liq_magnet || '-'}`, ok: true },
    { id: 'P14', group: 'OPTIONS', name: 'Options Surface (DVOL / VRP / 25Δ)', val: `DVOL ${mp.options_dvol ?? '-'} | Skew ${mp.options_skew_25d ?? '-'} | ${mp.options_dealer_gamma || 'NEUTRAL'}`, ok: true },
    { id: 'P15', group: 'MACRO', name: 'BTC 4H Macro Anchor Guard', val: `${(l1.btc_macro && l1.btc_macro.btc_1h_trend) || '-'} (${(l1.btc_macro && l1.btc_macro.btc_4h_pct) || 0}%)`, ok: true },
    { id: 'P16', group: 'MACRO', name: 'News & Macro Sentiment Wire', val: `${(l1.news_macro && l1.news_macro.market_sentiment) || 'NEUTRAL'} (${newsScore.toFixed(0)}/100)`, ok: true },
    { id: 'P17', group: 'AI', name: '3-Brain Brain #1: Tabular Quant ML', val: `${ns3.brain1_tabular_prob_pct ?? pMath.toFixed(1)}%`, ok: true },
    { id: 'P18', group: 'AI', name: '3-Brain Brain #2: Episodic k-NN', val: `${ns3.brain2_episodic_knn_prob_pct ?? '-'}%`, ok: true },
    { id: 'P19', group: 'AI', name: '3-Brain Brain #3: LLM Meta-Judge', val: `${ns3.brain3_llm_prob_pct ?? pAi.toFixed(1)}%`, ok: pAi >= 65 },
    { id: 'P20', group: 'FPT', name: 'Kalman First-Passage P(TP1 < SL)', val: `${fptP1.toFixed(1)}% | ETA TP1: ${tpPred.eta_tp1_label || '-'}`, ok: fptP1 >= minFpt },
    { id: 'P21', group: 'EXEC', name: 'Sniper Two-Stage TP1/TP2 Structure', val: `BE +${sniperCfg.stage0_be_trigger_r || 0.65}R | TP1 +${sniperCfg.tp1_lock_trigger_r || 0.9}R (50%) | TP2 +${sniperCfg.tp2_runner_target_r || 2.0}R`, ok: true },
    { id: 'P22', group: 'RISK', name: 'Auto Gear-Shift Engine', val: gearState && gearState.active_profile ? `Gigi ${gearState.current_gear} (${gearState.active_profile.code}, ${gearState.active_profile.leverage}x)` : 'Gigi 1 (20x ALL-IN)', ok: true },
    { id: 'P23', group: 'RISK', name: 'Profit Ratchet Vault Protection', val: vaultState ? `Locked $${Number(vaultState.locked_profit_vault_usdt || 0).toFixed(2)} | HWM $${Number(vaultState.high_water_mark_usdt || 0).toFixed(2)}` : 'Active (35% lock / +15% HWM)', ok: true },
    { id: 'P24', group: 'RISK', name: 'Liquidation & SL Bounds Rail', val: `SL ${slDistPct}% inside [${(cfg && cfg.min_sl_pct) || 0.9}%..${(cfg && cfg.max_sl_pct) || 2.25}%]`, ok: slDistPct <= 2.25 }
  ];

  return {
    radarAxes,
    waterfall,
    pipelineStages,
    pillars,
    quantCategories: qf.category_scores || qf.categories || {},
    sampleFactors: qf.sample_factors || qf.factors || {},
    trajectoryCone: tpPred.trajectory_cone || [],
    roiProjection: roiProj,
    sniperPlan: l5.sniper_75_plan || sniperCfg,
    neuroSymbolic: ns3,
    mathProof: mp
  };
}

function mountTerminalExtensions(app, deps) {
  const {
    resultsDir,
    pluangDir,
    configPath,
    positionsPath,
    statePath,
    testMode,
    writeJsonAtomicSync,
    readJsonSafeSync,
    dispatchNativePushAlert,
    isAuthenticatedReq,
    getUsdIdr,
    baseDir
  } = deps;

  async function resolveLiveFxIdr() {
    const fallback = (typeof getUsdIdr === 'function' && Number(getUsdIdr()) > 10000)
      ? Number(getUsdIdr())
      : (agg.DEFAULT_USD_IDR || 18218);
    if (testMode) return fallback;
    try {
      const live = await agg.getLiveUsdIdrRate(fallback);
      if (Number.isFinite(live) && live > 10000 && live < 50000) return live;
    } catch {}
    return fallback;
  }

  const FINANCE_FILE = path.join(baseDir, 'personal-finance.json');

  // ------------------------------------------------------------------
  // 1. BOT TRANSPARENCY X-RAY & 532-FACTOR GLASS-BOX (/api/terminal/factors & /bot-xray)
  // ------------------------------------------------------------------
  function handleBotFactors(req, res) {
    const reqSym = String(req.query.symbol || '').trim().toUpperCase();
    const positions = safeReadJson(positionsPath, []) || [];
    const openPosList = Array.isArray(positions) ? positions.filter(p => p && p.status === 'OPEN') : [];
    const activePos = reqSym
      ? (openPosList.find(p => normBotFilePrefix(p.binance_pair || p.symbol) === normBotFilePrefix(reqSym)) || openPosList[0] || null)
      : (openPosList[0] || null);

    const scannedList = listScannedCoinFiles(resultsDir);
    let targetPrefix = reqSym ? normBotFilePrefix(reqSym) : (activePos ? normBotFilePrefix(activePos.binance_pair || activePos.symbol) : 'BTC_USD');
    let scanFile = path.join(resultsDir, `${targetPrefix}_latest.json`);
    let scanData = safeReadJson(scanFile, null);
    if (!scanData && scannedList.length) {
      scanData = safeReadJson(path.join(resultsDir, scannedList[0].file), null);
      if (scanData && scanData.symbol) targetPrefix = normBotFilePrefix(scanData.symbol);
    }

    const gearState = safeReadJson(path.join(resultsDir, 'gear_state.json'), null);
    const vaultState = safeReadJson(path.join(resultsDir, 'vault_state.json'), null);
    const autoState = safeReadJson(statePath, {}) || {};
    const breakerState = safeReadJson(path.join(resultsDir, 'risk_breaker_state.json'), null);
    const ledger = safeReadJson(path.join(resultsDir, 'performance_ledger.json'), null);
    const aiMemory = safeReadJson(path.join(resultsDir, 'ai_trade_memory.json'), null);
    const cfg = safeReadJson(configPath, {}) || {};

    const analysis = buildFactorRadarAndPillars(scanData, activePos, gearState, vaultState, cfg);
    res.json({
      ok: true,
      source: 'pyrofuel-glassbox',
      ts: Date.now(),
      mode: 'LIVE',
      data: {
        symbol: (scanData && scanData.symbol) || (activePos && activePos.symbol) || reqSym || 'BTC-USD',
        scanTimestamp: (scanData && scanData.timestamp) || null,
        scanStatus: (scanData && scanData.status) || (activePos ? 'OPEN_POSITION' : 'IDLE'),
        activePosition: activePos,
        openPositionsCount: openPosList.length,
        walletUsdt: Number(autoState.binance_wallet_balance_usdt || 0),
        availableUsdt: Number(autoState.binance_available_balance_usdt || 0),
        marketRegime: autoState.market_regime || null,
        gear: gearState,
        vault: vaultState,
        breaker: breakerState,
        ledgerSummary: ledger ? {
          closedTrades: ledger.closed_trades || 0,
          winRatePct: ledger.win_rate_pct || 0,
          realizedPnlUsd: ledger.realized_pnl_usd || 0,
          realizedPnlIdr: ledger.realized_pnl_idr || 0
        } : null,
        aiMemorySummary: aiMemory ? {
          totalClosed: Array.isArray(aiMemory.closed_trades) ? aiMemory.closed_trades.length : (aiMemory.stats && aiMemory.stats.total_trades) || 0,
          recentLessons: Array.isArray(aiMemory.lessons) ? aiMemory.lessons.slice(-6) : []
        } : null,
        layer1: (scanData && scanData.layer1_scanning) || {},
        layer2: (scanData && scanData.layer2_setup) || {},
        layer3: (scanData && scanData.layer3_plan) || {},
        layer4: (scanData && scanData.layer4_risk) || {},
        layer5: (scanData && scanData.layer5_final_call) || {},
        committee: (scanData && scanData.committee) || null,
        ...analysis,
        scannedCoins: scannedList.slice(0, 24)
      }
    });
  }

  app.get('/api/terminal/factors', handleBotFactors);
  app.get('/api/terminal/bot-xray', handleBotFactors);

  // ------------------------------------------------------------------
  // 2. TRANSCRIPTS HUB: 9-AGENT AI DEBATE TRANSCRIPTS + EARNINGS TRANSCRIPTS
  // ------------------------------------------------------------------
  app.get('/api/terminal/transcripts', async (req, res) => {
    const rawSym = String(req.query.symbol || 'BTCUSDT').trim().toUpperCase();
    const prefix = normBotFilePrefix(rawSym);
    const scanData = safeReadJson(path.join(resultsDir, `${prefix}_latest.json`), null);
    const comLogRaw = safeReadJson(path.join(resultsDir, 'committee_log.json'), []);
    const comLog = Array.isArray(comLogRaw) ? comLogRaw : (comLogRaw && Array.isArray(comLogRaw.sessions) ? comLogRaw.sessions : []);
    const aiMem = safeReadJson(path.join(resultsDir, 'ai_trade_memory.json'), null);

    // Build speaker-by-speaker 9-Agent Debate Transcripts
    const debateSessions = [];
    const pushSession = (src, tag) => {
      if (!src || typeof src !== 'object') return;
      const c = src.committee || src;
      if (!c || (!c.portfolio_manager && !c.bull_researcher && !c.bear_researcher && !c.analysts)) return;
      const turns = [];
      if (c.analysts && typeof c.analysts === 'object') {
        for (const [role, content] of Object.entries(c.analysts)) {
          const txt = typeof content === 'string' ? content : JSON.stringify(content);
          if (txt && txt.length > 2) turns.push({ speaker: role.toUpperCase(), role: 'ANALYST', stance: 'DATA', text: txt.slice(0, 600) });
        }
      }
      if (c.bull_researcher) {
        turns.push({
          speaker: 'ADVOCATE RESEARCHER (PRO-SETUP)',
          role: 'PRO',
          stance: 'APPROVE',
          text: c.bull_researcher.argument || c.bull_researcher.thesis || JSON.stringify(c.bull_researcher)
        });
      }
      if (c.bear_researcher) {
        turns.push({
          speaker: 'RED-TEAM ADVERSARY (SKEPTIC)',
          role: 'CONTRA',
          stance: 'CHALLENGE',
          text: c.bear_researcher.argument || c.bear_researcher.critique || JSON.stringify(c.bear_researcher)
        });
      }
      if (c.rebuttal || (c.bull_researcher && c.bull_researcher.rebuttal)) {
        turns.push({
          speaker: 'ADVOCATE REBUTTAL (STRUCTURAL DEFENSE)',
          role: 'REBUTTAL',
          stance: 'DEFEND',
          text: typeof c.rebuttal === 'string' ? c.rebuttal : (c.rebuttal && c.rebuttal.argument) || c.bull_researcher.rebuttal
        });
      }
      if (c.risk_officer) {
        turns.push({
          speaker: 'GEAR-AWARE RISK OFFICER',
          role: 'RISK',
          stance: c.risk_officer.approved === false ? 'VETO' : 'AUDIT',
          text: c.risk_officer.assessment || c.risk_officer.verdict || c.risk_officer.reasoning || JSON.stringify(c.risk_officer)
        });
      }
      if (c.portfolio_manager) {
        turns.push({
          speaker: 'SUPREME PORTFOLIO MANAGER (FINAL VERDICT)',
          role: 'JUDGE',
          stance: c.approved ? 'APPROVED' : 'VETOED',
          text: c.portfolio_manager.decision || c.portfolio_manager.rationale || JSON.stringify(c.portfolio_manager)
        });
      }
      if (turns.length) {
        debateSessions.push({
          id: src.pipeline_id || c.session_id || `${tag}-${debateSessions.length + 1}`,
          symbol: src.symbol || c.symbol || rawSym,
          timestamp: src.timestamp || c.timestamp || new Date().toISOString(),
          approved: Boolean(c.approved),
          direction: c.direction || 'SKIP',
          confidencePct: Number(c.confidence_pct || 0),
          elapsedSec: Number(c.elapsed_sec || c.duration_sec || 0),
          turns
        });
      }
    };

    if (scanData && scanData.committee) pushSession(scanData, 'LATEST');
    for (const s of comLog.slice(-10).reverse()) pushSession(s, 'LOG');

    // Step-by-step 5-Layer Reasoning Transcript for current symbol
    const pipelineTranscript = [];
    if (scanData) {
      const l1 = scanData.layer1_scanning || {};
      const mp = scanData.math_proof || l1.math_proof || {};
      const l2 = scanData.layer2_setup || {};
      const l3 = scanData.layer3_plan || {};
      const l4 = scanData.layer4_risk || {};
      const l5 = scanData.layer5_final_call || {};
      pipelineTranscript.push(
        { step: 'L1: QUANT ENGINE', speaker: 'MATHEMATICS & MICROSTRUCTURE', text: `P_Math=${mp.p_math_pct || 0}% | Preferred=${mp.preferred_direction || '-'} | Regime=${mp.statistical_regime || '-'} | Q532=${mp.composite_532_factors || 50} | ADX=${mp.adx_14 || 0} | Hurst=${mp.hurst_exponent || 0.5} | OBI20=${mp.obi_weighted_20 || 0} | VPIN=${mp.vpin || 0.35} | Hawkes=${mp.hawkes_state || 'BASELINE'}` },
        { step: 'L2: SETUP HUNTER', speaker: 'AI STRATEGIST', text: `Setup=${l2.setup_name || 'NO_CLEAR_SETUP'} (${l2.direction || 'NONE'}, prob=${l2.probability_pct || 0}%, confluences=${l2.confluence_count || 0}). Confluences: ${(l2.confluences || []).join('; ') || '-'}. Note: ${l2.explanation_id || l2.reasoning || '-'}` },
        { step: 'L3: PLAN ARCHITECT', speaker: 'EXECUTION & FPT ENGINE', text: `Entry=$${l3.entry_price || 0} | SL=$${l3.stop_loss || 0} | TP1=$${l3.take_profit_1 || 0} | TP2=$${l3.take_profit_2 || l3.take_profit || 0} | RRR=${l3.risk_reward_ratio || '-'} | ${(l3.tp_time_prediction && l3.tp_time_prediction.model_note) || l3.reasoning || '-'}` },
        { step: 'L4: RISK AUDITOR', speaker: 'CHIEF RISK OFFICER', text: `Score=${l4.total_score || 0}/${l4.max_score || 8} (${l4.recommendation || '-'}) | Verdict=${l4.risk_verdict || '-'} | ${l4.reasoning || '-'}` },
        { step: 'L5: SUPREME JUDGE', speaker: 'FINAL JUDGMENT + 13 GATES', text: `Status=${l5.status || '-'} | Hybrid Confidence=${l5.confidence_score || 0}% | Reason: ${l5.final_reason || '-'}` }
      );
    }

    // Corporate / Protocol Earnings Call & Filing Transcript Synthesis (live SEC EDGAR + News)
    let corporateTranscript = null;
    try {
      const [fData, nData] = await Promise.all([
        edgarP.fundamentals(rawSym).catch(() => null),
        newsP.news({ q: rawSym.replace(/USDT|\.P|-USD/g, ''), limit: 8 }).catch(() => ({ items: [] }))
      ]);
      const prof = (fData && fData.profile) || {};
      const fin = (fData && fData.edgar && fData.edgar.financials) || {};
      const filings = (fData && fData.edgar && fData.edgar.filings) || [];
      const items = (nData && nData.items) || [];
      const posWords = /\b(beat|surge|growth|record|upgrade|strong|profit|rally|expand|approve|bullish|gain)\b/i;
      const negWords = /\b(miss|drop|cut|lawsuit|warn|risk|decline|slump|bearish|loss|delay|probe|tariff)\b/i;
      let posHits = 0, negHits = 0;
      const qaSnippets = items.slice(0, 6).map((it, idx) => {
        const title = String(it.title || '');
        const pH = posWords.test(title);
        const nH = negWords.test(title);
        if (pH) posHits++;
        if (nH) negHits++;
        return {
          idx: idx + 1,
          speaker: idx % 2 === 0 ? `WIRE DESK (${it.source || 'NEWS'})` : `ANALYST CATALYST Q&A`,
          sentiment: pH && !nH ? 'POSITIVE' : (nH && !pH ? 'NEGATIVE' : 'NEUTRAL'),
          ts: it.pubDate || '',
          text: title,
          link: it.link || ''
        };
      });
      const toneScore = Math.max(15, Math.min(92, Math.round(52 + (posHits - negHits) * 11)));
      const revLatest = fin.revenue && fin.revenue[0] ? fin.revenue[0] : null;
      const epsLatest = fin.eps && fin.eps[0] ? fin.eps[0] : null;
      corporateTranscript = {
        symbol: rawSym,
        entityName: prof.name || rawSym,
        exchange: prof.exchange || (agg.isCrypto(rawSym) ? 'BINANCE FUTURES' : 'US EQUITY'),
        toneScore,
        toneLabel: toneScore >= 62 ? 'CONSTRUCTIVE / BULLISH TONE' : (toneScore <= 42 ? 'CAUTIOUS / DEFENSIVE TONE' : 'BALANCED / NEUTRAL TONE'),
        preparedRemarks: [
          revLatest ? `Latest SEC XBRL Revenue (${revLatest.end || revLatest.fy || 'FY'}): $${(revLatest.val / 1e9).toFixed(2)}B` : `Live Market Instrument: ${prof.name || rawSym} (${prof.exchange || 'Global Market'})`,
          epsLatest ? `Latest Diluted EPS (${epsLatest.end || epsLatest.fy || 'FY'}): $${Number(epsLatest.val).toFixed(2)}` : `Continuous 24/7 Derivative & Orderflow Coverage Active`,
          filings.length ? `Most Recent Official Regulatory Filing: ${filings[0].form} filed ${filings[0].date}` : `Real-Time Institutional News & Macro Wire Active (${items.length} recent dispatches)`
        ],
        recentFilings: filings.slice(0, 5),
        qaSnippets
      };
    } catch {}

    const postMortems = (aiMem && Array.isArray(aiMem.closed_trades))
      ? aiMem.closed_trades.slice(-10).reverse().map(t => ({
          id: t.id || t.trade_id,
          symbol: t.symbol,
          direction: t.direction,
          setup: t.setup_name || t.strategy_id,
          netPnlUsd: t.net_pnl_usd,
          exitReason: t.exit_reason,
          lesson: t.lesson || t.post_mortem || `${t.symbol} ${t.direction} closed (${t.exit_reason})`
        }))
      : [];

    res.json({
      ok: true,
      source: 'bbg-transcripts',
      ts: Date.now(),
      mode: 'LIVE',
      data: {
        symbol: rawSym,
        debateSessions,
        pipelineTranscript,
        postMortems,
        corporateTranscript
      }
    });
  });

  // ------------------------------------------------------------------
  // 3. BLOOMBERG INTELLIGENCE (BI <GO>) DEEP RESEARCH DOSSIER
  // ------------------------------------------------------------------
  app.get('/api/terminal/intelligence', async (req, res) => {
    const sym = String(req.query.symbol || 'BTCUSDT').trim().toUpperCase();
    const prefix = normBotFilePrefix(sym);
    const scanData = safeReadJson(path.join(resultsDir, `${prefix}_latest.json`), null);

    const [qRes, fRes, nRes] = await Promise.all([
      agg.quote(sym).catch(() => null),
      edgarP.fundamentals(sym).catch(() => null),
      newsP.news({ q: sym.replace(/USDT|\.P|-USD/g, ''), limit: 8 }).catch(() => ({ items: [] }))
    ]);

    const q = qRes || {};
    const prof = (fRes && fRes.profile) || {};
    const fin = (fRes && fRes.edgar && fRes.edgar.financials) || {};
    const mp = (scanData && scanData.math_proof) || {};
    const l2 = (scanData && scanData.layer2_setup) || {};
    const l5 = (scanData && scanData.layer5_final_call) || {};
    const chgPct = Number(q.chgPct || 0);
    const isCrypto = agg.isCrypto(sym);

    const bullPoints = [];
    const bearPoints = [];
    if (chgPct >= 0.5) bullPoints.push(`Positive 24h momentum (${chgPct >= 0 ? '+' : ''}${chgPct.toFixed(2)}%) supporting upward continuation.`);
    else if (chgPct <= -0.5) bearPoints.push(`Negative 24h momentum (${chgPct.toFixed(2)}%) signaling overhead supply pressure.`);
    if (mp.p_math_pct >= 62) bullPoints.push(`Pyrofuel 532-Factor P_Math score strong at ${mp.p_math_pct}% favoring ${mp.preferred_direction || 'trend'}.`);
    if (Number(mp.obi_weighted_20 || 0) > 0.12) bullPoints.push(`Orderbook L2 bid depth imbalance positive (OBI-20 = +${Number(mp.obi_weighted_20).toFixed(2)}).`);
    if (Number(mp.obi_weighted_20 || 0) < -0.12) bearPoints.push(`Orderbook L2 ask wall pressure detected (OBI-20 = ${Number(mp.obi_weighted_20).toFixed(2)}).`);
    if (Array.isArray(l2.confluences) && l2.confluences.length) {
      const targetArr = String(l2.direction || '').toUpperCase() === 'SHORT' ? bearPoints : bullPoints;
      l2.confluences.slice(0, 3).forEach(c => targetArr.push(`AI Confluence: ${c}`));
    }
    if (fin.revenue && fin.revenue.length >= 2) {
      const g = ((fin.revenue[0].val - fin.revenue[1].val) / Math.max(1, Math.abs(fin.revenue[1].val))) * 100;
      if (g >= 0) bullPoints.push(`SEC XBRL YoY Revenue expansion of +${g.toFixed(1)}% ($${(fin.revenue[0].val / 1e9).toFixed(2)}B).`);
      else bearPoints.push(`SEC XBRL YoY Revenue contraction of ${g.toFixed(1)}%.`);
    }
    if (!bullPoints.length) bullPoints.push(`Institutional liquidity and deep orderbook coverage active across ${isCrypto ? 'Binance Futures' : (prof.exchange || 'Primary Exchange')}.`);
    if (!bearPoints.length) bearPoints.push(`Macro rate volatility and sudden liquidity sweeps remain primary tail risks.`);

    const rating = (mp.p_math_pct >= 70 && String(mp.preferred_direction).toUpperCase() === 'LONG')
      ? 'OUTPERFORM / BULLISH CONVICTION'
      : (mp.p_math_pct >= 70 && String(mp.preferred_direction).toUpperCase() === 'SHORT')
      ? 'UNDERPERFORM / BEARISH CONVICTION'
      : (chgPct >= 2 ? 'CONSTRUCTIVE BIAS' : chgPct <= -2 ? 'CAUTIOUS / DEFENSIVE' : 'NEUTRAL / MONITOR');

    res.json({
      ok: true,
      source: 'bloomberg-intelligence',
      ts: Date.now(),
      mode: 'LIVE',
      data: {
        symbol: sym,
        name: prof.name || sym,
        assetClass: isCrypto ? 'CRYPTO DERIVATIVE / SPOT' : 'GLOBAL EQUITY / MACRO',
        rating,
        quote: q,
        quantSnapshot: {
          pMath: mp.p_math_pct || null,
          regime: mp.statistical_regime || null,
          adx14: mp.adx_14 || null,
          hurst: mp.hurst_exponent || null,
          obi20: mp.obi_weighted_20 || null,
          dvol: mp.options_dvol || null,
          hybridConf: l5.confidence_score || null,
          setup: l2.setup_name || null,
          direction: l5.direction || l2.direction || null
        },
        bullPoints,
        bearPoints,
        catalysts: ((nRes && nRes.items) || []).slice(0, 6).map(it => ({
          title: it.title,
          source: it.source,
          pubDate: it.pubDate,
          link: it.link
        })),
        filings: ((fRes && fRes.edgar && fRes.edgar.filings) || []).slice(0, 5)
      }
    });
  });

  // ------------------------------------------------------------------
  // 4. INSTITUTIONAL FLOWS: SPOT ETFs + FUTURES SQUEEZE + SEC FORM-4 INSIDERS
  // ------------------------------------------------------------------
  app.get('/api/terminal/flows', async (req, res) => {
    const etfList = [
      { symbol: 'IBIT', name: 'iShares Bitcoin Trust (BlackRock)', group: 'CRYPTO SPOT ETF' },
      { symbol: 'FBTC', name: 'Fidelity Wise Origin Bitcoin ETF', group: 'CRYPTO SPOT ETF' },
      { symbol: 'GBTC', name: 'Grayscale Bitcoin Trust', group: 'CRYPTO SPOT ETF' },
      { symbol: 'ETHA', name: 'iShares Ethereum Trust (BlackRock)', group: 'CRYPTO SPOT ETF' },
      { symbol: 'SPY', name: 'SPDR S&P 500 Institutional ETF', group: 'MACRO EQUITY ETF' },
      { symbol: 'QQQ', name: 'Invesco Nasdaq-100 Tech ETF', group: 'MACRO EQUITY ETF' },
      { symbol: 'TLT', name: 'iShares 20+ Year US Treasury Bond', group: 'RATES / BONDS ETF' },
      { symbol: 'GLD', name: 'SPDR Gold Shares Physical ETF', group: 'SAFE HAVEN ETF' },
      { symbol: 'EIDO', name: 'iShares MSCI Indonesia ETF', group: 'INDONESIA FLOW ETF' }
    ];

    const [etfQuotes, derivMat, insiderEdgar] = await Promise.all([
      Promise.all(etfList.map(async e => {
        const q = await agg.quote(e.symbol).catch(() => ({}));
        const px = Number(q.price || 0);
        const vol = Number(q.vol || 0);
        const chgPct = Number(q.chgPct || 0);
        const dollarVol = px * vol;
        // Signed Institutional Money Flow Proxy = DollarVolume * tanh(chgPct / 1.5)
        const signedFlowEstUsd = dollarVol > 0 ? dollarVol * Math.tanh(chgPct / 1.8) * 0.18 : 0;
        return { ...e, price: px, chgPct, vol, dollarVol, signedFlowEstUsd };
      })),
      edgarP.derivativesMatrix(12).catch(() => []),
      edgarP.fundamentals(String(req.query.symbol || 'NVDA').toUpperCase().replace(/USDT|\.P|-USD/g, '') || 'NVDA').catch(() => null)
    ]);

    const squeezeBoard = (Array.isArray(derivMat) ? derivMat : []).slice(0, 12).map(d => {
      const fr = Number(d.fundingRate || d.lastFundingRate || 0) * 100;
      const chg = Number(d.priceChangePercent || d.chgPct || 0);
      const squeezeBias = fr > 0.025 ? 'LONG_CROWDED (SHORT SQUEEZE RISK LOW / DUMP RISK)' : fr < -0.015 ? 'SHORT_CROWDED (SHORT SQUEEZE ALERT)' : 'BALANCED';
      const pressureScore = Math.min(100, Math.round(Math.abs(fr) * 1800 + Math.abs(chg) * 5));
      return {
        symbol: d.symbol,
        markPrice: Number(d.markPrice || d.price || 0),
        fundingPct: +fr.toFixed(4),
        annualizedPct: +(fr * 3 * 365).toFixed(1),
        basisPct: Number(d.basisPct || 0),
        squeezeBias,
        pressureScore
      };
    });

    const filings = (insiderEdgar && insiderEdgar.edgar && insiderEdgar.edgar.filings) || [];
    const form4 = filings.filter(f => String(f.form || '').startsWith('4') || String(f.form || '').includes('8-K') || String(f.form || '').includes('10-')).slice(0, 10);

    res.json({
      ok: true,
      source: 'yahoo+binance+edgar',
      ts: Date.now(),
      mode: 'LIVE',
      data: {
        etfs: etfQuotes,
        squeezeBoard,
        insiderFilings: form4,
        insiderSymbol: (insiderEdgar && insiderEdgar.profile && insiderEdgar.profile.symbol) || String(req.query.symbol || 'NVDA')
      }
    });
  });

  // ------------------------------------------------------------------
  // 5. PERSONAL FINANCE & ANTI-BOROS MONEY MANAGER (/api/finance/*)
  // ------------------------------------------------------------------
  function loadFinance() {
    const data = readJsonSafeSync(FINANCE_FILE, null);
    if (data && typeof data === 'object') {
      return {
        ...DEFAULT_FINANCE,
        ...data,
        categoryLimits: (data.categoryLimits && Object.keys(data.categoryLimits).length) ? data.categoryLimits : { ...DEFAULT_FINANCE.categoryLimits },
        goals: Array.isArray(data.goals) ? data.goals : [...DEFAULT_FINANCE.goals],
        transactions: Array.isArray(data.transactions) ? data.transactions : []
      };
    }
    return JSON.parse(JSON.stringify(DEFAULT_FINANCE));
  }

  function saveFinance(data) {
    writeJsonAtomicSync(FINANCE_FILE, data, 0o600);
  }

  function computeFinanceSummary(fin, liveFxIdr = null) {
    const now = new Date();
    const wibMs = now.getTime() + 7 * 3600 * 1000;
    const wibNow = new Date(wibMs);
    const todayStr = wibNow.toISOString().slice(0, 10);
    const monthPrefix = todayStr.slice(0, 7);
    const daysInMonth = new Date(wibNow.getUTCFullYear(), wibNow.getUTCMonth() + 1, 0).getUTCDate();
    const dayOfMonth = wibNow.getUTCDate();
    const remainingDays = Math.max(1, daysInMonth - dayOfMonth + 1);

    let totalIncomeAll = 0, totalExpenseAll = 0, totalSavingsAll = 0;
    let monthIncome = 0, monthExpense = 0, monthSavings = 0;
    let todayExpense = 0, todayIncome = 0;
    const byCategory = {};
    const dailyMap = {};

    for (let d = 13; d >= 0; d--) {
      const ds = new Date(wibMs - d * 86400000).toISOString().slice(0, 10);
      dailyMap[ds] = { date: ds, income: 0, expense: 0, savings: 0 };
    }

    for (const tx of (fin.transactions || [])) {
      if (!tx || typeof tx !== 'object') continue;
      const amt = Math.max(0, Number(tx.amountIdr || 0));
      const typ = String(tx.type || 'EXPENSE').toUpperCase();
      const cat = String(tx.category || 'Lainnya');
      const dStr = String(tx.date || new Date((tx.ts || Date.now()) + 7 * 3600000).toISOString().slice(0, 10));

      if (typ === 'INCOME') totalIncomeAll += amt;
      else if (typ === 'SAVINGS') totalSavingsAll += amt;
      else totalExpenseAll += amt;

      if (dStr.startsWith(monthPrefix)) {
        if (typ === 'INCOME') monthIncome += amt;
        else if (typ === 'SAVINGS') monthSavings += amt;
        else {
          monthExpense += amt;
          byCategory[cat] = (byCategory[cat] || 0) + amt;
        }
      }
      if (dStr === todayStr) {
        if (typ === 'INCOME') todayIncome += amt;
        else if (typ === 'EXPENSE') todayExpense += amt;
      }
      if (dailyMap[dStr]) {
        if (typ === 'INCOME') dailyMap[dStr].income += amt;
        else if (typ === 'SAVINGS') dailyMap[dStr].savings += amt;
        else dailyMap[dStr].expense += amt;
      }
    }

    const monthlyIncomeTarget = Math.max(100000, Number(fin.monthlyIncomeTarget || 1000000));
    const buffettPlan = buildWarrenBuffettPlan(monthlyIncomeTarget);
    const dailyLimit = Math.max(1000, Number(fin.dailyLimitIdr || buffettPlan.dailyLimitIdr));
    const monthlyBudget = Math.max(10000, Number(fin.monthlyBudgetIdr || buffettPlan.spendableMonthlyIdr));
    const remainingToday = dailyLimit - todayExpense;
    const remainingMonth = monthlyBudget - monthExpense;
    const dynamicSafeDaily = Math.max(0, Math.floor(remainingMonth / remainingDays));
    const dailyUsedPct = +(todayExpense / dailyLimit * 100).toFixed(1);
    const monthUsedPct = +(monthExpense / monthlyBudget * 100).toFixed(1);
    const savingsRatePct = monthIncome > 0 ? +(((monthSavings + Math.max(0, monthIncome - monthExpense - monthSavings)) / monthIncome) * 100).toFixed(1) : 0;

    let borosStatus = 'AMAN_TERKONTROL';
    let statusLabel = 'DISCIPLINED / ON TRACK';
    if (dailyUsedPct > 100 || monthUsedPct > 100) {
      borosStatus = 'BOROS_OVER_BUDGET';
      statusLabel = 'LIMIT EXCEEDED';
    } else if (dailyUsedPct >= 75 || monthUsedPct >= 80) {
      borosStatus = 'WASPADA_HAMPIR_LIMIT';
      statusLabel = 'BUDGET CAUTION (>=75%)';
    }

    // Discipline Score (0..100)
    let disciplineScore = 100;
    if (dailyUsedPct > 100) disciplineScore -= Math.min(35, (dailyUsedPct - 100) * 0.5);
    else if (dailyUsedPct > 75) disciplineScore -= 10;
    if (monthUsedPct > 100) disciplineScore -= Math.min(40, (monthUsedPct - 100) * 0.6);
    if (monthIncome > 0 && savingsRatePct < 40) disciplineScore -= Math.min(20, (40 - Math.max(0, savingsRatePct)) * 0.5);
    disciplineScore = Math.max(10, Math.min(100, Math.round(disciplineScore)));

    // Sync live Bot Binance Balance & Vault into Wealth Overview
    const autoState = safeReadJson(statePath, {}) || {};
    const vaultState = safeReadJson(path.join(resultsDir, 'vault_state.json'), {}) || {};
    const botWalletUsd = Number(autoState.binance_wallet_balance_usdt || 0);
    const botVaultUsd = Number(vaultState.locked_profit_vault_usdt || 0);
    const fxIdr = (Number(liveFxIdr) > 10000 && Number(liveFxIdr) < 50000)
      ? Number(liveFxIdr)
      : ((typeof getUsdIdr === 'function' && Number(getUsdIdr()) > 10000) ? Number(getUsdIdr()) : (agg.DEFAULT_USD_IDR || 18218));
    const botWalletIdr = Math.round(botWalletUsd * fxIdr);
    const netCashIdr = totalIncomeAll - totalExpenseAll - totalSavingsAll;
    const bankTotalIdr = Math.max(0, netCashIdr) + totalSavingsAll;
    const totalIntegratedWealthIdr = bankTotalIdr + botWalletIdr;

    // Live-Integrated Wealth Milestones (Rp 10M -> Rp 100M -> Rp 1B)
    // Automatically reflects Bank Cash + Locked Reserves + Live Binance Futures Equity
    const monthlySavePace = Math.max(50000, buffettPlan.payYourselfFirstIdr || 400000);
    const estimateMonthsToTarget = (current, target, monthlyContrib, annualRate = 0.12) => {
      if (current >= target) return 0;
      const r = annualRate / 12;
      let bal = current;
      let m = 0;
      while (bal < target && m < 600) {
        bal = bal * (1 + r) + monthlyContrib;
        m++;
      }
      return m;
    };

    const milestones = [
      { id: 'GOAL-10M', tier: 'TIER I', name: 'First Rp 10.000.000', shortLabel: 'Rp 10 Juta Pertama', targetIdr: 10000000, color: '#00d26a' },
      { id: 'GOAL-100M', tier: 'TIER II', name: 'First Rp 100.000.000', shortLabel: 'Rp 100 Juta Pertama', targetIdr: 100000000, color: '#ffb000' },
      { id: 'GOAL-1B', tier: 'TIER III', name: 'First Rp 1.000.000.000 (1 Miliar)', shortLabel: 'Rp 1 Miliar Pertama', targetIdr: 1000000000, color: '#ff6600' }
    ].map(ms => {
      const pct = Math.min(100, +((totalIntegratedWealthIdr / ms.targetIdr) * 100).toFixed(2));
      const rem = Math.max(0, ms.targetIdr - totalIntegratedWealthIdr);
      const estMonths = estimateMonthsToTarget(totalIntegratedWealthIdr, ms.targetIdr, monthlySavePace, 0.12);
      const etaLabel = estMonths === 0
        ? 'ACHIEVED'
        : estMonths < 12
        ? `~${estMonths} mo`
        : `~${(estMonths / 12).toFixed(1)} yr`;
      return {
        ...ms,
        currentIdr: totalIntegratedWealthIdr,
        remainingIdr: rem,
        progressPct: pct,
        achieved: totalIntegratedWealthIdr >= ms.targetIdr,
        etaLabel
      };
    });

    // Keep autoIntegrate goals synced with live integrated wealth
    for (const g of (fin.goals || [])) {
      if (g && (g.autoIntegrate || g.id === 'GOAL-10M' || g.id === 'GOAL-100M' || g.id === 'GOAL-1B')) {
        g.savedIdr = totalIntegratedWealthIdr;
        g.autoIntegrate = true;
      }
    }

    return {
      todayStr,
      monthPrefix,
      dayOfMonth,
      daysInMonth,
      remainingDays,
      allocationMethod: fin.allocationMethod || 'WARREN_BUFFETT',
      buffettPlan,
      netCashIdr,
      bankTotalIdr,
      totalSavingsIdr: totalSavingsAll,
      totalIntegratedWealthIdr,
      milestones,
      monthIncome,
      monthExpense,
      monthSavings,
      todayIncome,
      todayExpense,
      dailyLimitIdr: dailyLimit,
      monthlyBudgetIdr: monthlyBudget,
      monthlyIncomeTarget,
      remainingTodayIdr: remainingToday,
      remainingMonthIdr: remainingMonth,
      dynamicSafeDailyIdr: dynamicSafeDaily,
      dailyUsedPct,
      monthUsedPct,
      savingsRatePct,
      borosStatus,
      statusLabel,
      disciplineScore,
      byCategory,
      categoryLimits: fin.categoryLimits || {},
      dailyTrend14d: Object.values(dailyMap),
      botSync: {
        fxRateIdr: Math.round(fxIdr),
        walletUsd: botWalletUsd,
        walletIdr: botWalletIdr,
        vaultUsd: botVaultUsd,
        vaultIdr: Math.round(botVaultUsd * fxIdr)
      }
    };
  }

  app.get('/api/finance', async (req, res) => {
    const fin = loadFinance();
    const liveFx = await resolveLiveFxIdr();
    res.json({ ok: true, data: { ...fin, summary: computeFinanceSummary(fin, liveFx) } });
  });

  app.post('/api/finance/buffett-apply', async (req, res) => {
    const b = req.body || {};
    const monthlyIncomeIdr = Math.round(Number(b.monthlyIncomeIdr || 1000000));
    if (!Number.isFinite(monthlyIncomeIdr) || monthlyIncomeIdr < 100000 || monthlyIncomeIdr > 1e11) {
      return res.status(400).json({ ok: false, error: 'monthlyIncomeIdr must be between Rp 100.000 and Rp 100B' });
    }
    const plan = buildWarrenBuffettPlan(monthlyIncomeIdr);
    const fin = loadFinance();
    fin.allocationMethod = 'WARREN_BUFFETT';
    fin.monthlyIncomeTarget = plan.monthlyIncomeIdr;
    fin.monthlyBudgetIdr = plan.spendableMonthlyIdr;
    fin.dailyLimitIdr = plan.dailyLimitIdr;
    fin.categoryLimits = { ...plan.categoryLimits };

    // Ensure Warren Buffett priority goals exist
    if (!fin.goals.some(g => g.id === 'GOAL-EMERGENCY')) {
      fin.goals.unshift({
        id: 'GOAL-EMERGENCY',
        name: 'Emergency Margin of Safety (6 Months)',
        targetIdr: Math.round(plan.spendableMonthlyIdr * 6),
        savedIdr: 0,
        deadline: '2027-11-30',
        category: 'SAFETY'
      });
    }
    if (!fin.goals.some(g => g.id === 'GOAL-INVEST')) {
      fin.goals.push({
        id: 'GOAL-INVEST',
        name: 'Productive Investment Capital Reserve',
        targetIdr: Math.round(plan.monthlyIncomeIdr * 12),
        savedIdr: 0,
        deadline: '2028-11-30',
        category: 'INVEST'
      });
    }

    // Optional 1-click Monthly Allowance Booking + Pay Yourself First Automatic Lock
    const booked = [];
    if (b.recordMonthlyCycle === true) {
      const wibToday = new Date(Date.now() + 7 * 3600000).toISOString().slice(0, 10);
      const investAmt = Math.round(plan.monthlyIncomeIdr * 0.25);
      const emergAmt = Math.round(plan.monthlyIncomeIdr * 0.15);
      const mkTx = (type, category, amountIdr, note) => ({
        id: 'TX-' + Date.now().toString(36) + '-' + crypto.randomBytes(2).toString('hex'),
        ts: Date.now(),
        date: wibToday,
        type,
        category,
        amountIdr,
        note
      });
      const txInc = mkTx('INCOME', 'Monthly Fixed Allowance', plan.monthlyIncomeIdr, 'Fixed Monthly Income — Warren Buffett Auto-Cycle');
      const txInv = mkTx('SAVINGS', 'Productive Investment Capital', investAmt, 'Auto Pay-Yourself-First (25% Productive Capital)');
      const txEmg = mkTx('SAVINGS', 'Emergency Margin of Safety', emergAmt, 'Auto Pay-Yourself-First (15% Cash Reserve)');
      fin.transactions.unshift(txEmg, txInv, txInc);
      fin.transactions = fin.transactions.slice(0, 2000);
      const gInv = fin.goals.find(g => g.id === 'GOAL-INVEST');
      if (gInv) gInv.savedIdr = Number(gInv.savedIdr || 0) + investAmt;
      const gEmg = fin.goals.find(g => g.id === 'GOAL-EMERGENCY');
      if (gEmg) gEmg.savedIdr = Number(gEmg.savedIdr || 0) + emergAmt;
      booked.push(txInc, txInv, txEmg);
    }

    try {
      saveFinance(fin);
      const liveFx = await resolveLiveFxIdr();
      res.json({ ok: true, plan, bookedCount: booked.length, data: { ...fin, summary: computeFinanceSummary(fin, liveFx) } });
    } catch {
      res.status(500).json({ ok: false, error: 'Failed applying Warren Buffett allocation' });
    }
  });

  app.post('/api/finance/tx', async (req, res) => {
    const b = req.body || {};
    const type = String(b.type || 'EXPENSE').toUpperCase();
    if (!['INCOME', 'EXPENSE', 'SAVINGS'].includes(type)) {
      return res.status(400).json({ ok: false, error: 'type must be INCOME, EXPENSE, or SAVINGS' });
    }
    const amountIdr = Math.round(Number(b.amountIdr));
    if (!Number.isFinite(amountIdr) || amountIdr <= 0 || amountIdr > 1e12) {
      return res.status(400).json({ ok: false, error: 'Invalid amountIdr' });
    }
    const category = String(b.category || (type === 'INCOME' ? 'Monthly Fixed Allowance' : type === 'SAVINGS' ? 'Productive Investment Capital' : 'Food & Refreshments')).trim().slice(0, 60);
    const note = String(b.note || '').trim().slice(0, 160);
    const wibToday = new Date(Date.now() + 7 * 3600000).toISOString().slice(0, 10);
    const date = /^\d{4}-\d{2}-\d{2}$/.test(String(b.date || '')) ? String(b.date) : wibToday;

    const fin = loadFinance();
    const tx = {
      id: 'TX-' + Date.now().toString(36) + '-' + crypto.randomBytes(2).toString('hex'),
      ts: Date.now(),
      date,
      type,
      category,
      amountIdr,
      note
    };
    fin.transactions.unshift(tx);
    fin.transactions = fin.transactions.slice(0, 2000);
    if (type === 'SAVINGS' && b.goalId) {
      const g = fin.goals.find(x => x.id === b.goalId);
      if (g) g.savedIdr = Number(g.savedIdr || 0) + amountIdr;
    }
    try {
      saveFinance(fin);
    } catch {
      return res.status(500).json({ ok: false, error: 'Failed saving personal finance transaction' });
    }
    const liveFx = await resolveLiveFxIdr();
    const summary = computeFinanceSummary(fin, liveFx);

    // Budget Discipline Push Alert when daily ceiling is crossed
    if (type === 'EXPENSE' && summary.todayExpense > summary.dailyLimitIdr && typeof dispatchNativePushAlert === 'function' && !testMode) {
      const over = summary.todayExpense - summary.dailyLimitIdr;
      dispatchNativePushAlert({
        title: 'BLOOMBERG TERMINAL // DAILY BUDGET LIMIT EXCEEDED',
        body: `Pengeluaran hari ini Rp ${summary.todayExpense.toLocaleString('id-ID')} melampaui batas harian Warren Buffett Rp ${summary.dailyLimitIdr.toLocaleString('id-ID')} (+Rp ${over.toLocaleString('id-ID')}).`,
        eventType: 'FINANCE_LIMIT_ALERT',
        symbol: 'FIN',
        url: '/?w=BTCUSDT:FIN,BTCUSDT:BOT,BTCUSDT:GP,BTCUSDT:TOP&win=1'
      }).catch(() => {});
    }
    res.json({ ok: true, tx, data: { ...fin, summary } });
  });

  app.delete('/api/finance/tx/:id', (req, res) => {
    const id = String(req.params.id || '').trim();
    const fin = loadFinance();
    const before = fin.transactions.length;
    fin.transactions = fin.transactions.filter(t => t && t.id !== id);
    if (fin.transactions.length === before) return res.status(404).json({ ok: false, error: 'Transaction not found' });
    try {
      saveFinance(fin);
      res.json({ ok: true, data: { ...fin, summary: computeFinanceSummary(fin) } });
    } catch {
      res.status(500).json({ ok: false, error: 'Failed deleting transaction' });
    }
  });

  app.post('/api/finance/budget', (req, res) => {
    const b = req.body || {};
    const fin = loadFinance();
    if (b.dailyLimitIdr !== undefined) {
      const v = Math.round(Number(b.dailyLimitIdr));
      if (!Number.isFinite(v) || v < 1000) return res.status(400).json({ ok: false, error: 'Invalid dailyLimitIdr' });
      fin.dailyLimitIdr = v;
    }
    if (b.monthlyBudgetIdr !== undefined) {
      const v = Math.round(Number(b.monthlyBudgetIdr));
      if (!Number.isFinite(v) || v < 10000) return res.status(400).json({ ok: false, error: 'Invalid monthlyBudgetIdr' });
      fin.monthlyBudgetIdr = v;
    }
    if (b.monthlyIncomeTarget !== undefined) {
      const v = Math.round(Number(b.monthlyIncomeTarget));
      if (!Number.isFinite(v) || v < 0) return res.status(400).json({ ok: false, error: 'Invalid monthlyIncomeTarget' });
      fin.monthlyIncomeTarget = v;
    }
    if (b.categoryLimits && typeof b.categoryLimits === 'object') {
      for (const [k, val] of Object.entries(b.categoryLimits)) {
        const n = Math.round(Number(val));
        if (k && Number.isFinite(n) && n >= 0) fin.categoryLimits[String(k).slice(0, 60)] = n;
      }
    }
    try {
      saveFinance(fin);
      res.json({ ok: true, data: { ...fin, summary: computeFinanceSummary(fin) } });
    } catch {
      res.status(500).json({ ok: false, error: 'Failed saving budget settings' });
    }
  });

  app.post('/api/finance/goal', (req, res) => {
    const b = req.body || {};
    const name = String(b.name || '').trim().slice(0, 80);
    const targetIdr = Math.round(Number(b.targetIdr));
    const savedIdr = Math.max(0, Math.round(Number(b.savedIdr || 0)));
    if (!name || !Number.isFinite(targetIdr) || targetIdr <= 0) {
      return res.status(400).json({ ok: false, error: 'Valid goal name and targetIdr required' });
    }
    const fin = loadFinance();
    const existing = b.id ? fin.goals.find(g => g.id === b.id) : null;
    if (existing) {
      existing.name = name;
      existing.targetIdr = targetIdr;
      existing.savedIdr = savedIdr;
      if (b.deadline) existing.deadline = String(b.deadline).slice(0, 20);
    } else {
      fin.goals.push({
        id: 'GOAL-' + Date.now().toString(36),
        name,
        targetIdr,
        savedIdr,
        deadline: String(b.deadline || '2027-12-31').slice(0, 20),
        category: String(b.category || 'GOAL').slice(0, 20)
      });
    }
    try {
      saveFinance(fin);
      res.json({ ok: true, data: { ...fin, summary: computeFinanceSummary(fin) } });
    } catch {
      res.status(500).json({ ok: false, error: 'Failed saving goal' });
    }
  });

  app.delete('/api/finance/goal/:id', (req, res) => {
    const id = String(req.params.id || '').trim();
    const fin = loadFinance();
    fin.goals = fin.goals.filter(g => g && g.id !== id);
    try {
      saveFinance(fin);
      res.json({ ok: true, data: { ...fin, summary: computeFinanceSummary(fin) } });
    } catch {
      res.status(500).json({ ok: false, error: 'Failed deleting goal' });
    }
  });

  // ------------------------------------------------------------------
  // 6. BLOOMBERG TERMINAL LIVE WIDGET SUMMARY (/api/widget/summary)
  // ------------------------------------------------------------------
  app.get('/api/widget/summary', async (req, res) => {
    const syms = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'GC=F', 'USDIDR=X'];
    const [quotes, liveFx] = await Promise.all([
      Promise.all(syms.map(async s => {
        const q = await agg.quote(s).catch(() => ({}));
        return {
          symbol: s,
          label: s === 'GC=F' ? 'GOLD' : s === 'USDIDR=X' ? 'USD/IDR' : s.replace('USDT', ''),
          price: Number(q.price || 0),
          chgPct: Number(q.chgPct || 0)
        };
      })),
      resolveLiveFxIdr()
    ]);
    const fxTile = quotes.find(q => q.symbol === 'USDIDR=X');
    if (fxTile && !(fxTile.price > 10000 && fxTile.price < 50000)) {
      fxTile.price = Math.round(liveFx);
    }

    const authed = typeof isAuthenticatedReq === 'function' ? Boolean(isAuthenticatedReq(req)) : false;
    const positions = safeReadJson(positionsPath, []) || [];
    const openPos = Array.isArray(positions) ? positions.filter(p => p && p.status === 'OPEN') : [];
    const topPos = openPos[0] || null;
    const autoState = safeReadJson(statePath, {}) || {};

    const botSummary = {
      running: Boolean(autoState.is_running || autoState.autonomous_running),
      openCount: openPos.length,
      active: topPos ? {
        symbol: String(topPos.binance_pair || topPos.symbol || '').toUpperCase(),
        direction: String(topPos.direction || 'LONG').toUpperCase(),
        leverage: Number(topPos.leverage || 20),
        entryPrice: Number(topPos.entry_price || 0),
        markPrice: Number(topPos.current_price || 0),
        pnlPct: Number(topPos.pnl_pct || 0)
      } : null
    };

    let financeSummary = null;
    if (authed) {
      const fin = loadFinance();
      const s = computeFinanceSummary(fin, liveFx);
      financeSummary = {
        todayExpense: s.todayExpense,
        dailyLimitIdr: s.dailyLimitIdr,
        remainingTodayIdr: s.remainingTodayIdr,
        dynamicSafeDailyIdr: s.dynamicSafeDailyIdr,
        monthExpense: s.monthExpense,
        monthlyBudgetIdr: s.monthlyBudgetIdr,
        monthlyIncomeTarget: s.monthlyIncomeTarget,
        totalIntegratedWealthIdr: s.totalIntegratedWealthIdr,
        bankTotalIdr: s.bankTotalIdr,
        milestone10m: (s.milestones && s.milestones[0]) || null,
        disciplineScore: s.disciplineScore,
        statusLabel: s.statusLabel
      };
    }

    const fmtQ = (item) => item && item.price > 0 ? `$${item.price >= 100 ? item.price.toFixed(2) : item.price.toFixed(4)}` : 'N/A';
    const fmtC = (item) => item ? `${item.chgPct >= 0 ? '+' : ''}${item.chgPct.toFixed(2)}%` : '0.00%';
    const btc = quotes[0], eth = quotes[1], gold = quotes[3];
    const botHeadline = botSummary.active
      ? `${botSummary.active.symbol} ${botSummary.active.direction} ${botSummary.active.leverage}x (${botSummary.active.pnlPct >= 0 ? '+' : ''}${botSummary.active.pnlPct.toFixed(2)}%)`
      : (botSummary.running ? 'SCANNING MARKET — NO OPEN POSITION' : 'EXECUTION STANDBY');
    const dailyStatus = financeSummary
      ? `Rem Rp ${Math.round(financeSummary.remainingTodayIdr).toLocaleString('id-ID')} / Rp ${Math.round(financeSummary.dailyLimitIdr).toLocaleString('id-ID')} (${financeSummary.statusLabel})`
      : 'Open Terminal to View Capital Allocation';

    res.json({
      ok: true,
      ts: Date.now(),
      authenticated: authed,
      quotes,
      bot: botSummary,
      finance: financeSummary,
      // Flat fields for W3C PWA Adaptive Card Widget template
      btcPrice: fmtQ(btc),
      btcChg: fmtC(btc),
      ethPrice: fmtQ(eth),
      ethChg: fmtC(eth),
      goldPrice: fmtQ(gold),
      goldChg: fmtC(gold),
      botHeadline,
      dailyStatus,
      updatedAt: new Date().toISOString().slice(11, 19) + ' UTC'
    });
  });

  // ------------------------------------------------------------------
  // 7. EXECUTION ROE STUDIO FEED (/api/terminal/roe-feed — Authenticated)
  // ------------------------------------------------------------------
  app.get('/api/terminal/roe-feed', async (req, res) => {
    const liveFx = await resolveLiveFxIdr();
    const rawPositions = safeReadJson(positionsPath, []) || [];
    const ledger = safeReadJson(path.join(resultsDir, 'performance_ledger.json'), {}) || {};
    const aiMem = safeReadJson(path.join(resultsDir, 'ai_trade_memory.json'), {}) || {};

    const posArr = Array.isArray(rawPositions) ? rawPositions : [];
    const openRaw = posArr.filter(p => p && p.status === 'OPEN');

    const openPositions = await Promise.all(openRaw.map(async p => {
      const sym = String(p.binance_pair || p.symbol || 'BTCUSDT').toUpperCase().replace('-USD', 'USDT').replace(/\.P$/, '');
      const q = await agg.quote(sym, 'futures').catch(() => ({}));
      const entry = Number(p.entry_price || p.entryPrice || 0);
      const mark = Number(q.price || p.current_price || entry || 0);
      const lev = Number(p.leverage || 20);
      const dir = String(p.direction || p.side || 'LONG').toUpperCase();
      const sign = dir === 'SHORT' ? -1 : 1;
      const mUsd = Number(p.position_size_usd || 0);
      const roePct = (entry > 0 && mark > 0)
        ? +(sign * ((mark - entry) / entry) * lev * 100).toFixed(2)
        : Number(p.pnl_pct || 0);
      const pnlUsd = p.pnl_usd != null && !q.price
        ? Number(p.pnl_usd)
        : +(mUsd * (roePct / 100)).toFixed(3);
      const pnlIdr = Math.round(pnlUsd * liveFx);

      const prefix = normBotFilePrefix(sym);
      const scan = safeReadJson(path.join(resultsDir, `${prefix}_latest.json`), null);
      const mp = (scan && scan.math_proof) || {};
      const l5 = (scan && scan.layer5_final_call) || {};

      return {
        id: p.id || `OPEN-${sym}`,
        status: 'OPEN',
        symbol: sym,
        direction: dir,
        leverage: lev,
        marginMode: String(p.margin_type || 'ISOLATED').toUpperCase(),
        entryPrice: entry,
        markPrice: mark,
        stopLoss: Number(p.stop_loss || 0),
        tp1: Number(p.take_profit_1 || p.take_profit || 0),
        tp2: Number(p.take_profit_2 || p.take_profit || 0),
        marginUsd: mUsd,
        roePct,
        pnlUsd,
        pnlIdr,
        setup: p.setup_name || (scan && scan.layer2_setup && scan.layer2_setup.setup_name) || 'QUANT_EXECUTION',
        pMath: Number(mp.p_math_pct || l5.math_score_pct || 0),
        hybridConf: Number(l5.confidence_score || p.confidence_score || 0),
        openedAt: p.opened_at || p.timestamp || new Date().toISOString()
      };
    }));

    // Merge closed trades from active_positions.json, performance_ledger.json, and ai_trade_memory.json
    const seenIds = new Set();
    const closedTrades = [];
    const pushClosed = (raw) => {
      if (!raw || typeof raw !== 'object') return;
      const sym = String(raw.binance_pair || raw.symbol || '').toUpperCase().replace('-USD', 'USDT').replace(/\.P$/, '');
      if (!sym) return;
      const key = String(raw.id || raw.trade_id || `${sym}-${raw.closed_at || raw.exit_time || raw.timestamp || ''}-${raw.entry_price || ''}`);
      if (seenIds.has(key)) return;
      seenIds.add(key);

      const dir = String(raw.direction || raw.side || 'LONG').toUpperCase();
      const lev = Number(raw.leverage || 20);
      const entry = Number(raw.entry_price || raw.entryPrice || 0);
      const exit = Number(raw.exit_price || raw.close_price || raw.current_price || entry || 0);
      const mUsd = Number(raw.position_size_usd || raw.margin_usd || 0);
      const pnlUsd = Number(raw.net_pnl_usd ?? raw.pnl_usd ?? raw.realized_pnl_usd ?? 0);
      const sign = dir === 'SHORT' ? -1 : 1;
      let roePct = Number(raw.roe_pct ?? raw.pnl_pct ?? NaN);
      if (!Number.isFinite(roePct)) {
        if (mUsd > 0 && pnlUsd !== 0) roePct = +((pnlUsd / mUsd) * 100).toFixed(2);
        else if (entry > 0 && exit > 0 && exit !== entry) roePct = +(sign * ((exit - entry) / entry) * lev * 100).toFixed(2);
        else roePct = 0;
      }
      closedTrades.push({
        id: key,
        status: String(raw.status || raw.exit_reason || 'CLOSED').toUpperCase(),
        symbol: sym,
        direction: dir,
        leverage: lev,
        marginMode: String(raw.margin_type || 'ISOLATED').toUpperCase(),
        entryPrice: entry,
        markPrice: exit,
        marginUsd: mUsd,
        roePct: +Number(roePct).toFixed(2),
        pnlUsd: +Number(pnlUsd).toFixed(4),
        pnlIdr: Math.round(pnlUsd * liveFx),
        setup: raw.setup_name || raw.strategy_id || 'QUANT_SNIPER',
        closedAt: raw.closed_at || raw.exit_time || raw.timestamp || ''
      });
    };

    posArr.filter(p => p && p.status && String(p.status).startsWith('CLOSED')).reverse().forEach(pushClosed);
    if (Array.isArray(ledger.trades)) [...ledger.trades].reverse().forEach(pushClosed);
    if (Array.isArray(ledger.closed_positions)) [...ledger.closed_positions].reverse().forEach(pushClosed);
    if (Array.isArray(aiMem.closed_trades)) [...aiMem.closed_trades].reverse().forEach(pushClosed);

    const wins = closedTrades.filter(t => t.pnlUsd > 0 || t.roePct > 0).length;
    const winRatePct = closedTrades.length ? +((wins / closedTrades.length) * 100).toFixed(1) : Number(ledger.win_rate_pct || 0);

    res.json({
      ok: true,
      source: 'execution-roe-desk',
      ts: Date.now(),
      mode: 'LIVE',
      data: {
        fxRateIdr: Math.round(liveFx),
        openPositions,
        closedTrades: closedTrades.slice(0, 40),
        stats: {
          totalClosed: closedTrades.length || Number(ledger.closed_trades || 0),
          winRatePct,
          realizedPnlUsd: Number(ledger.realized_pnl_usd ?? closedTrades.reduce((s, x) => s + x.pnlUsd, 0)),
          profitFactor: Number(ledger.profit_factor || 0)
        }
      }
    });
  });

  // ------------------------------------------------------------------
  // 8. MARKET BREADTH, DOMINANCE & CROSS-ASSET REGIME (/api/terminal/breadth)
  // ------------------------------------------------------------------
  app.get('/api/terminal/breadth', async (req, res) => {
    const cryptoBasket = [
      'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT', 'DOGEUSDT', 'ADAUSDT', 'AVAXUSDT',
      'LINKUSDT', 'SUIUSDT', 'TONUSDT', 'DOTUSDT', 'NEARUSDT', 'LTCUSDT', 'ARBUSDT', 'INJUSDT'
    ];
    const macroBasket = [
      { symbol: '^GSPC', name: 'S&P 500 Index', role: 'EQUITY RISK' },
      { symbol: '^IXIC', name: 'Nasdaq Composite', role: 'TECH BETA' },
      { symbol: 'GC=F', name: 'Gold Futures', role: 'SAFE HAVEN' },
      { symbol: 'CL=F', name: 'WTI Crude Oil', role: 'INFLATION / ENERGY' },
      { symbol: '^TNX', name: 'US 10Y Treasury Yield', role: 'RATES ANCHOR' },
      { symbol: 'USDIDR=X', name: 'USD / IDR Spot', role: 'EM FX' }
    ];

    const [cryptoQuotes, macroQuotes] = await Promise.all([
      Promise.all(cryptoBasket.map(async s => {
        const q = await agg.quote(s).catch(() => ({}));
        const px = Number(q.price || 0);
        const chgPct = Number(q.chgPct || 0);
        const vol = Number(q.vol || 0);
        const high = Number(q.high || px);
        const low = Number(q.low || px);
        const rangePos = high > low ? ((px - low) / (high - low)) * 100 : 50;
        return { symbol: s, price: px, chgPct, dollarVol: px * vol, rangePos: +rangePos.toFixed(1) };
      })),
      Promise.all(macroBasket.map(async m => {
        const q = await agg.quote(m.symbol).catch(() => ({}));
        return { ...m, price: Number(q.price || 0), chgPct: Number(q.chgPct || 0) };
      }))
    ]);

    const validC = cryptoQuotes.filter(c => c.price > 0);
    const advancers = validC.filter(c => c.chgPct > 0.05).length;
    const decliners = validC.filter(c => c.chgPct < -0.05).length;
    const unchanged = Math.max(0, validC.length - advancers - decliners);
    const strongUp = validC.filter(c => c.chgPct >= 2.5).length;
    const strongDn = validC.filter(c => c.chgPct <= -2.5).length;
    const upperRangeCount = validC.filter(c => c.rangePos >= 55).length;
    const breadthPct = validC.length ? +((advancers / validC.length) * 100).toFixed(1) : 50;

    const totalVol = Math.max(1, validC.reduce((s, c) => s + c.dollarVol, 0));
    const btcVol = (validC.find(c => c.symbol === 'BTCUSDT') || {}).dollarVol || 0;
    const ethVol = (validC.find(c => c.symbol === 'ETHUSDT') || {}).dollarVol || 0;
    const solBnbVol = ((validC.find(c => c.symbol === 'SOLUSDT') || {}).dollarVol || 0) + ((validC.find(c => c.symbol === 'BNBUSDT') || {}).dollarVol || 0);
    const altVol = Math.max(0, totalVol - btcVol - ethVol - solBnbVol);

    const dominance = [
      { label: 'BTC Volume Share', pct: +((btcVol / totalVol) * 100).toFixed(1), dollarVol: btcVol, color: '#ff6600' },
      { label: 'ETH Volume Share', pct: +((ethVol / totalVol) * 100).toFixed(1), dollarVol: ethVol, color: '#4da3ff' },
      { label: 'SOL + BNB Majors', pct: +((solBnbVol / totalVol) * 100).toFixed(1), dollarVol: solBnbVol, color: '#ffb000' },
      { label: 'Altcoin Rotation Pool', pct: +((altVol / totalVol) * 100).toFixed(1), dollarVol: altVol, color: '#00d26a' }
    ];

    const spxChg = (macroQuotes.find(m => m.symbol === '^GSPC') || {}).chgPct || 0;
    const btcChg = (validC.find(c => c.symbol === 'BTCUSDT') || {}).chgPct || 0;
    const goldChg = (macroQuotes.find(m => m.symbol === 'GC=F') || {}).chgPct || 0;
    const tnxChg = (macroQuotes.find(m => m.symbol === '^TNX') || {}).chgPct || 0;

    const riskAppetite = Math.max(5, Math.min(95, Math.round(50 + breadthPct * 0.35 - 17.5 + btcChg * 3.2 + spxChg * 5.0 - goldChg * 2.0 - tnxChg * 1.8)));
    const regimeLabel = riskAppetite >= 65
      ? 'RISK-ON BROAD EXPANSION'
      : riskAppetite <= 35
      ? 'RISK-OFF DEFENSIVE / FLIGHT TO QUALITY'
      : (goldChg > 0.6 && btcChg < 0 ? 'SAFE-HAVEN ROTATION' : 'SELECTIVE / BALANCED REGIME');

    res.json({
      ok: true,
      source: 'binance+yahoo-breadth',
      ts: Date.now(),
      mode: 'LIVE',
      data: {
        breadth: {
          universeCount: validC.length,
          advancers,
          decliners,
          unchanged,
          strongUp,
          strongDn,
          breadthPct,
          upperRangePct: validC.length ? +((upperRangeCount / validC.length) * 100).toFixed(1) : 50,
          advDeclRatio: decliners > 0 ? +(advancers / decliners).toFixed(2) : advancers
        },
        dominance,
        riskAppetite,
        regimeLabel,
        macroPulse: macroQuotes,
        constituents: validC.sort((a, b) => b.chgPct - a.chgPct)
      }
    });
  });
}

module.exports = { mountTerminalExtensions, buildWarrenBuffettPlan };
