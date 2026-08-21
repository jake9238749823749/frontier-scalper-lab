"""
========================================================================================
MSRE-v1 EXPERIMENTATION, VALIDATION & FALSIFICATION HARNESS
========================================================================================
Executes:
1. Primary Benchmark on GBPUSD=X (4H, 720 Days)
2. Cross-Asset Secondary Validation (EURUSD=X, SPY, BTC-USD)
3. 4 Hard Validation Gates:
   - Gate 1: Friction Stress-Test (2.5x baseline spread)
   - Gate 2: Ergodic Block-Bootstrap Stability (1,500 paths) & Ruin Probability (>15% DD)
   - Gate 3: Directional Balance (Long vs Short Contribution)
   - Gate 4: Sub-Regime Independence (Playbook 1 Fade vs Playbook 2 Trend)
4. Parameter Neighborhood & Robustness Sweeps
5. Saves CSV logs, performance metrics, and plots to results/
"""

import os
import sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from engine.data_engine import RobustDataEngine
from engine.msre_execution import MSREBacktestRunner, MSRETrade
from strategies.msre_v1 import MSRE_Strategy

RESULTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "results")
os.makedirs(RESULTS_DIR, exist_ok=True)

def compute_trade_metrics(trades: list[MSRETrade], initial_capital: float = 100_000.0, df_equity: pd.DataFrame = None) -> dict:
    if not trades:
        return {
            "total_trades": 0,
            "win_rate_pct": 0.0,
            "profit_factor": 0.0,
            "net_pnl": 0.0,
            "net_return_pct": 0.0,
            "expectancy_r": 0.0,
            "expectancy_cash": 0.0,
            "max_drawdown_pct": 0.0,
            "sharpe_ratio": 0.0,
            "long_trades": 0,
            "short_trades": 0,
            "long_pnl": 0.0,
            "short_pnl": 0.0,
            "long_attribution_pct": 0.0,
            "short_attribution_pct": 0.0,
            "p1_trades": 0,
            "p1_profit_factor": 0.0,
            "p2_trades": 0,
            "p2_profit_factor": 0.0
        }

    closed = [t for t in trades if not t.is_open]
    if not closed:
        closed = trades

    total_trades = len(closed)
    wins = [t for t in closed if t.net_pnl > 0]
    losses = [t for t in closed if t.net_pnl < 0]

    win_rate = (len(wins) / total_trades) * 100.0 if total_trades > 0 else 0.0
    gross_win = sum(t.net_pnl for t in wins)
    gross_loss = abs(sum(t.net_pnl for t in losses))
    pf = (gross_win / gross_loss) if gross_loss > 0 else (np.inf if gross_win > 0 else 0.0)

    net_pnl = sum(t.net_pnl for t in closed)
    net_ret = (net_pnl / initial_capital) * 100.0
    exp_r = np.mean([t.return_r for t in closed]) if total_trades > 0 else 0.0
    exp_cash = net_pnl / total_trades if total_trades > 0 else 0.0

    long_t = [t for t in closed if t.direction == "long"]
    short_t = [t for t in closed if t.direction == "short"]
    long_pnl = sum(t.net_pnl for t in long_t)
    short_pnl = sum(t.net_pnl for t in short_t)

    long_attr = (long_pnl / net_pnl * 100.0) if abs(net_pnl) > 1e-6 else 0.0
    short_attr = (short_pnl / net_pnl * 100.0) if abs(net_pnl) > 1e-6 else 0.0

    # Playbook breakdown
    p1_t = [t for t in closed if "Fade" in t.playbook]
    p2_t = [t for t in closed if "Trend" in t.playbook]

    p1_win = sum(t.net_pnl for t in p1_t if t.net_pnl > 0)
    p1_loss = abs(sum(t.net_pnl for t in p1_t if t.net_pnl < 0))
    p1_pf = (p1_win / p1_loss) if p1_loss > 0 else (np.inf if p1_win > 0 else 0.0)

    p2_win = sum(t.net_pnl for t in p2_t if t.net_pnl > 0)
    p2_loss = abs(sum(t.net_pnl for t in p2_t if t.net_pnl < 0))
    p2_pf = (p2_win / p2_loss) if p2_loss > 0 else (np.inf if p2_win > 0 else 0.0)

    # Max Drawdown & Sharpe from bar series
    if df_equity is not None and not df_equity.empty:
        max_dd = float(df_equity['drawdown'].min() * 100.0)
        bar_rets = df_equity['equity'].pct_change().dropna()
        # 4H bars = ~1575 periods per year (252 days * 6.25 bars/day)
        sharpe = (bar_rets.mean() / (bar_rets.std(ddof=1) + 1e-9)) * np.sqrt(1575) if len(bar_rets) > 1 else 0.0
    else:
        max_dd = 0.0
        sharpe = 0.0

    return {
        "total_trades": total_trades,
        "win_rate_pct": win_rate,
        "profit_factor": pf,
        "net_pnl": net_pnl,
        "net_return_pct": net_ret,
        "expectancy_r": exp_r,
        "expectancy_cash": exp_cash,
        "max_drawdown_pct": max_dd,
        "sharpe_ratio": sharpe,
        "long_trades": len(long_t),
        "short_trades": len(short_t),
        "long_pnl": long_pnl,
        "short_pnl": short_pnl,
        "long_attribution_pct": long_attr,
        "short_attribution_pct": short_attr,
        "p1_trades": len(p1_t),
        "p1_profit_factor": p1_pf,
        "p2_trades": len(p2_t),
        "p2_profit_factor": p2_pf
    }

def run_bootstrap_ruin_analysis(trades: list[MSRETrade], n_sims: int = 1500, dd_threshold_pct: float = 15.0, initial_cap: float = 100_000.0) -> dict:
    if not trades or len(trades) < 5:
        return {
            "n_sims": n_sims,
            "prob_ruin_pct": 0.0,
            "median_max_dd_pct": 0.0,
            "p95_max_dd_pct": 0.0,
            "p99_max_dd_pct": 0.0
        }

    closed = [t for t in trades if not t.is_open]
    pnls = np.array([t.net_pnl for t in closed])
    m = len(pnls)

    max_dds = []
    ruin_count = 0

    np.random.seed(42)
    # Block Bootstrap with block size ~ 3
    block_size = min(3, m)
    for _ in range(n_sims):
        # Sample blocks
        indices = []
        while len(indices) < m:
            start_idx = np.random.randint(0, max(1, m - block_size + 1))
            indices.extend(range(start_idx, min(m, start_idx + block_size)))
        indices = indices[:m]

        sample_pnls = pnls[indices]
        equity_path = initial_cap + np.cumsum(sample_pnls)
        peaks = np.maximum.accumulate(equity_path)
        dds = (equity_path - peaks) / peaks * 100.0
        worst_dd = np.min(dds)
        max_dds.append(worst_dd)
        if abs(worst_dd) >= dd_threshold_pct:
            ruin_count += 1

    max_dds = np.array(max_dds)
    return {
        "n_sims": n_sims,
        "prob_ruin_pct": (ruin_count / n_sims) * 100.0,
        "median_max_dd_pct": float(np.median(max_dds)),
        "p95_max_dd_pct": float(np.percentile(max_dds, 5)),  # 5th percentile = worst 5%
        "p99_max_dd_pct": float(np.percentile(max_dds, 1))
    }

def main():
    print("=" * 85)
    print("MSRE-v1 STRATEGY RESEARCH, EXECUTION & FALSIFICATION SUITE")
    print("=" * 85)

    symbols_config = [
        {"symbol": "GBPUSD=X", "pip_size": 0.0001, "spread_pips": 1.2, "slippage_pips": 0.3},
        {"symbol": "EURUSD=X", "pip_size": 0.0001, "spread_pips": 1.0, "slippage_pips": 0.2},
        {"symbol": "SPY",      "pip_size": 0.01,   "spread_pips": 2.0, "slippage_pips": 1.0},
        {"symbol": "BTC-USD",  "pip_size": 1.0,    "spread_pips": 5.0, "slippage_pips": 3.0}
    ]

    all_benchmark_results = []
    trade_logs_dict = {}
    equity_curves_dict = {}

    # -----------------------------------------------------------------
    # STEP 1: RUN PRIMARY & SECONDARY BENCHMARKS
    # -----------------------------------------------------------------
    for cfg in symbols_config:
        sym = cfg["symbol"]
        print(f"\n[DATA INGESTION] Fetching H4 dataset for {sym}...")
        df_raw = RobustDataEngine.get_h4_data(symbol=sym, lookback_days=720)

        # 1A. Exact Literal Baseline (use_normalized_phi=False)
        strategy_literal = MSRE_Strategy(pip_size=cfg["pip_size"], use_normalized_phi=False)
        df_sig_literal = strategy_literal.generate_signals(df_raw)
        runner_literal = MSREBacktestRunner(
            pip_size=cfg["pip_size"],
            spread_pips=cfg["spread_pips"],
            slippage_pips=cfg["slippage_pips"]
        )
        eq_lit, trades_lit = runner_literal.run(df_sig_literal, symbol=sym)
        m_lit = compute_trade_metrics(trades_lit, df_equity=eq_lit)

        # 1B. Normalized Dimension Baseline (use_normalized_phi=True)
        strategy_norm = MSRE_Strategy(pip_size=cfg["pip_size"], use_normalized_phi=True)
        df_sig_norm = strategy_norm.generate_signals(df_raw)
        runner_norm = MSREBacktestRunner(
            pip_size=cfg["pip_size"],
            spread_pips=cfg["spread_pips"],
            slippage_pips=cfg["slippage_pips"]
        )
        eq_norm, trades_norm = runner_norm.run(df_sig_norm, symbol=sym)
        m_norm = compute_trade_metrics(trades_norm, df_equity=eq_norm)

        trade_logs_dict[f"{sym}_norm"] = trades_norm
        equity_curves_dict[f"{sym}_norm"] = eq_norm

        all_benchmark_results.append({
            "Asset": sym,
            "Variant": "Literal Formula (Raw Phi)",
            "Trades": m_lit["total_trades"],
            "Win Rate (%)": round(m_lit["win_rate_pct"], 1),
            "PF": round(m_lit["profit_factor"], 2),
            "Net PnL ($)": round(m_lit["net_pnl"], 2),
            "Return (%)": round(m_lit["net_return_pct"], 2),
            "Expectancy (R)": round(m_lit["expectancy_r"], 2),
            "Max DD (%)": round(m_lit["max_drawdown_pct"], 2),
            "Sharpe": round(m_lit["sharpe_ratio"], 2)
        })

        all_benchmark_results.append({
            "Asset": sym,
            "Variant": "Normalized Phi (Body/Range)",
            "Trades": m_norm["total_trades"],
            "Win Rate (%)": round(m_norm["win_rate_pct"], 1),
            "PF": round(m_norm["profit_factor"], 2),
            "Net PnL ($)": round(m_norm["net_pnl"], 2),
            "Return (%)": round(m_norm["net_return_pct"], 2),
            "Expectancy (R)": round(m_norm["expectancy_r"], 2),
            "Max DD (%)": round(m_norm["max_drawdown_pct"], 2),
            "Sharpe": round(m_norm["sharpe_ratio"], 2)
        })

    df_bench = pd.DataFrame(all_benchmark_results)
    df_bench.to_csv(os.path.join(RESULTS_DIR, "benchmark_comparison.csv"), index=False)
    print("\n" + "=" * 85)
    print("MSRE-v1 BENCHMARK SUMMARY")
    print("=" * 85)
    print(df_bench.to_string(index=False))

    # -----------------------------------------------------------------
    # STEP 2: HARD VALIDATION GATES ON PRIMARY (GBPUSD=X) & EURUSD=X
    # -----------------------------------------------------------------
    print("\n" + "=" * 85)
    print("EVALUATING 4 HARD VALIDATION GATES")
    print("=" * 85)

    primary_sym = "GBPUSD=X"
    df_gbp = RobustDataEngine.get_h4_data(symbol=primary_sym, lookback_days=720)
    strat_gbp = MSRE_Strategy(pip_size=0.0001, use_normalized_phi=True)
    df_sig_gbp = strat_gbp.generate_signals(df_gbp)

    # GATE 1: FRICTION STRESS-TEST (2.5x spread)
    runner_stress = MSREBacktestRunner(
        pip_size=0.0001,
        spread_pips=1.2 * 2.5,   # 3.0 pips
        slippage_pips=0.3 * 2.5  # 0.75 pips
    )
    eq_stress, trades_stress = runner_stress.run(df_sig_gbp, symbol=primary_sym)
    m_stress = compute_trade_metrics(trades_stress, df_equity=eq_stress)

    gate1_passed = m_stress["expectancy_r"] >= 0.20
    gate1_status = "PASS" if gate1_passed else "FAIL"

    # GATE 2: ERGODIC BOOTSTRAP STABILITY (1,500 paths, Ruin > 15% DD)
    trades_base_gbp = trade_logs_dict["GBPUSD=X_norm"]
    boot_res = run_bootstrap_ruin_analysis(trades_base_gbp, n_sims=1500, dd_threshold_pct=15.0)
    gate2_passed = boot_res["prob_ruin_pct"] <= 0.10
    gate2_status = "PASS" if gate2_passed else "FAIL"

    # GATE 3: DIRECTIONAL BALANCE (Long vs Short attribution <= 75%)
    m_base_gbp = compute_trade_metrics(trades_base_gbp, df_equity=equity_curves_dict["GBPUSD=X_norm"])
    long_attr = abs(m_base_gbp["long_attribution_pct"])
    short_attr = abs(m_base_gbp["short_attribution_pct"])
    gate3_passed = (long_attr <= 75.0) and (short_attr <= 75.0) and (m_base_gbp["long_trades"] > 0) and (m_base_gbp["short_trades"] > 0)
    gate3_status = "PASS" if gate3_passed else "FAIL"

    # GATE 4: SUB-REGIME INDEPENDENCE (Playbook 1 vs Playbook 2 PF >= 1.25)
    p1_pf = m_base_gbp["p1_profit_factor"]
    p2_pf = m_base_gbp["p2_profit_factor"]
    p1_t_count = m_base_gbp["p1_trades"]
    p2_t_count = m_base_gbp["p2_trades"]
    gate4_passed = (p1_pf >= 1.25 and p1_t_count > 0) and (p2_pf >= 1.25 and p2_t_count > 0)
    gate4_status = "PASS" if gate4_passed else "FAIL"

    gates_summary = [
        {
            "Gate #": 1,
            "Validation Gate": "Friction Stress-Test",
            "Condition / Threshold": "2.5x Spread (3.0 pips) -> Net Exp >= +0.20R",
            "Observed Metric": f"Expectancy = {m_stress['expectancy_r']:+.2f}R (Net PnL: ${m_stress['net_pnl']:,.2f})",
            "Status": gate1_status
        },
        {
            "Gate #": 2,
            "Validation Gate": "Ergodic Bootstrap Stability",
            "Condition / Threshold": "1,500 Block-Bootstrap paths -> P(DD > 15%) <= 0.10%",
            "Observed Metric": f"P(Ruin) = {boot_res['prob_ruin_pct']:.2f}% (Med DD: {boot_res['median_max_dd_pct']:.2f}%, 95th: {boot_res['p95_max_dd_pct']:.2f}%)",
            "Status": gate2_status
        },
        {
            "Gate #": 3,
            "Validation Gate": "Directional Balance",
            "Condition / Threshold": "Long / Short Return Attribution <= 75%",
            "Observed Metric": f"Long: {m_base_gbp['long_attribution_pct']:.1f}% (${m_base_gbp['long_pnl']:,.2f}, {m_base_gbp['long_trades']} trades) | Short: {m_base_gbp['short_attribution_pct']:.1f}% (${m_base_gbp['short_pnl']:,.2f}, {m_base_gbp['short_trades']} trades)",
            "Status": gate3_status
        },
        {
            "Gate #": 4,
            "Validation Gate": "Sub-Regime Independence",
            "Condition / Threshold": "Both Playbook 1 (Fade) & Playbook 2 (Trend) PF >= 1.25",
            "Observed Metric": f"Playbook 1 (Fade): PF = {p1_pf:.2f} ({p1_t_count} trades) | Playbook 2 (Trend): PF = {p2_pf:.2f} ({p2_t_count} trades)",
            "Status": gate4_status
        }
    ]

    df_gates = pd.DataFrame(gates_summary)
    df_gates.to_csv(os.path.join(RESULTS_DIR, "validation_gates.csv"), index=False)
    print(df_gates.to_string(index=False))

    # -----------------------------------------------------------------
    # STEP 3: PARAMETER ROBUSTNESS & NEIGHBORHOOD SWEEPS
    # -----------------------------------------------------------------
    print("\n" + "=" * 85)
    print("PARAMETER ROBUSTNESS & BREAKOUT CONDITION HARMONIZATION")
    print("=" * 85)

    # Let's test harmonized breakout parameter grid:
    # Test varying drift_threshold (-0.50, -0.20, 0.00, 0.20, 0.35)
    # Test varying eff_trend_thresh (0.25, 0.30, 0.35)
    # Test varying eff_fade_thresh (0.28, 0.32, 0.36)
    robust_records = []
    for eff_fade in [0.28, 0.32, 0.36]:
        for eff_trend in [0.25, 0.30, 0.35]:
            for drift_th in [-0.50, -0.20, 0.0, 0.35]:
                strat_test = MSRE_Strategy(
                    pip_size=0.0001,
                    use_normalized_phi=True,
                    eff_fade_thresh=eff_fade,
                    eff_trend_thresh=eff_trend,
                    drift_threshold=drift_th
                )
                df_sig = strat_test.generate_signals(df_gbp)
                runner_test = MSREBacktestRunner(pip_size=0.0001, spread_pips=1.2, slippage_pips=0.3)
                eq_t, tr_t = runner_test.run(df_sig, symbol=primary_sym)
                mt = compute_trade_metrics(tr_t, df_equity=eq_t)
                robust_records.append({
                    "Eff_Fade": eff_fade,
                    "Eff_Trend": eff_trend,
                    "Drift_Thresh": drift_th,
                    "Trades": mt["total_trades"],
                    "P1_Trades": mt["p1_trades"],
                    "P2_Trades": mt["p2_trades"],
                    "Win_Rate_%": round(mt["win_rate_pct"], 1),
                    "PF": round(mt["profit_factor"], 2),
                    "Net_PnL_$": round(mt["net_pnl"], 2),
                    "Return_%": round(mt["net_return_pct"], 2),
                    "Exp_R": round(mt["expectancy_r"], 2),
                    "Max_DD_%": round(mt["max_drawdown_pct"], 2),
                    "Sharpe": round(mt["sharpe_ratio"], 2)
                })

    df_robust = pd.DataFrame(robust_records)
    df_robust.to_csv(os.path.join(RESULTS_DIR, "parameter_robustness_grid.csv"), index=False)
    print(f"Computed {len(df_robust)} parameter configurations. Top 5 by Profit Factor (with >= 10 trades):")
    valid_sub = df_robust[df_robust["Trades"] >= 10].sort_values("PF", ascending=False)
    print(valid_sub.head(5).to_string(index=False))

    # -----------------------------------------------------------------
    # STEP 4: SAVE TRADE LOGS & GENERATE PLOTS
    # -----------------------------------------------------------------
    # Save detailed trade logs for GBPUSD
    trade_rows = []
    for t in trades_base_gbp:
        trade_rows.append({
            "Trade ID": t.trade_id,
            "Symbol": t.symbol,
            "Playbook": t.playbook,
            "Direction": t.direction.upper(),
            "Entry Time": t.entry_time,
            "Entry Price": round(t.entry_price, 5),
            "Stop Loss": round(t.stop_loss, 5),
            "Take Profit": round(t.take_profit, 5),
            "Exit Time": t.exit_time,
            "Exit Price": round(t.exit_price, 5) if t.exit_price else None,
            "Size": round(t.size, 2),
            "Gross PnL ($)": round(t.gross_pnl, 2),
            "Net PnL ($)": round(t.net_pnl, 2),
            "Return (R)": round(t.return_r, 2),
            "Return (%)": round(t.pnl_pct * 100.0, 2),
            "Holding Bars": t.holding_bars,
            "Exit Reason": t.exit_reason
        })
    df_trade_log = pd.DataFrame(trade_rows)
    df_trade_log.to_csv(os.path.join(RESULTS_DIR, "gbpusd_trade_log.csv"), index=False)
    print(f"\n[OUTPUT] Saved trade log with {len(df_trade_log)} trades to results/gbpusd_trade_log.csv")

    # Generate Equity Curves and Drawdown Chart
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True, gridspec_kw={'height_ratios': [2.5, 1]})

    eq_gbp = equity_curves_dict["GBPUSD=X_norm"]
    ax1.plot(eq_gbp.index, eq_gbp['equity'], color='#1f77b4', lw=2, label=f"GBPUSD=X Equity (Final: ${eq_gbp['equity'].iloc[-1]:,.2f})")
    ax1.axhline(100_000, color='gray', linestyle='--', alpha=0.7, label='Initial Capital ($100k)')
    ax1.set_title("MSRE-v1 Performance: 5-Day Macro Structural Regime Engine (GBPUSD=X 4H)", fontsize=14, fontweight='bold', pad=12)
    ax1.set_ylabel("Portfolio Equity ($)", fontsize=11)
    ax1.grid(True, alpha=0.3)
    ax1.legend(loc='upper left', frameon=True)

    ax2.fill_between(eq_gbp.index, eq_gbp['drawdown'] * 100.0, 0, color='#d62728', alpha=0.35, label='Drawdown (%)')
    ax2.plot(eq_gbp.index, eq_gbp['drawdown'] * 100.0, color='#d62728', lw=1.2)
    ax2.set_ylabel("Drawdown (%)", fontsize=11)
    ax2.set_xlabel("Date", fontsize=11)
    ax2.grid(True, alpha=0.3)
    ax2.legend(loc='lower left', frameon=True)

    plt.tight_layout()
    chart_path = os.path.join(RESULTS_DIR, "msre_v1_equity_curve.png")
    plt.savefig(chart_path, dpi=200)
    plt.close()
    print(f"[OUTPUT] Generated performance chart at {chart_path}")

    # Generate Multi-Asset Comparative Chart
    fig, ax = plt.subplots(figsize=(12, 6))
    for sym_key, eq_df in equity_curves_dict.items():
        norm_eq = (eq_df['equity'] / 100_000.0 - 1.0) * 100.0
        ax.plot(norm_eq.index, norm_eq, lw=1.8, label=f"{sym_key.replace('_norm', '')} (Net: {norm_eq.iloc[-1]:+.2f}%)")

    ax.axhline(0, color='gray', linestyle='--', alpha=0.6)
    ax.set_title("MSRE-v1 Multi-Asset Comparative Performance (4H Execution)", fontsize=13, fontweight='bold')
    ax.set_ylabel("Cumulative Return (%)", fontsize=11)
    ax.set_xlabel("Date", fontsize=11)
    ax.grid(True, alpha=0.3)
    ax.legend(loc='upper left', frameon=True)
    plt.tight_layout()
    multi_chart_path = os.path.join(RESULTS_DIR, "msre_v1_multi_asset_equity.png")
    plt.savefig(multi_chart_path, dpi=200)
    plt.close()
    print(f"[OUTPUT] Generated multi-asset chart at {multi_chart_path}")

if __name__ == "__main__":
    main()
