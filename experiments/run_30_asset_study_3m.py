"""
========================================================================================
MSRE-v1: 30-INSTRUMENT GLOBAL CROSS-ASSET VALIDATION STUDY (LAST 3 MONTHS / 90 DAYS)
========================================================================================
Evaluates 3-month out-of-sample / recent regime performance across the 30 global instruments.
"""

import os
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from engine.data_engine import RobustDataEngine

RESULTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "results")
TRADE_LOGS_3M_DIR = os.path.join(RESULTS_DIR, "trade_logs_3m")
EQUITY_CURVES_3M_DIR = os.path.join(RESULTS_DIR, "equity_curves_3m")
os.makedirs(TRADE_LOGS_3M_DIR, exist_ok=True)
os.makedirs(EQUITY_CURVES_3M_DIR, exist_ok=True)

UNIVERSE = [
    # Forex (10)
    {"symbol": "GBPUSD=X", "name": "British Pound / US Dollar",      "class": "Forex",          "tick": 0.0001, "friction_type": "pips", "friction_val": 1.5},
    {"symbol": "EURUSD=X", "name": "Euro / US Dollar",               "class": "Forex",          "tick": 0.0001, "friction_type": "pips", "friction_val": 1.2},
    {"symbol": "USDJPY=X", "name": "US Dollar / Japanese Yen",       "class": "Forex",          "tick": 0.01,   "friction_type": "pips", "friction_val": 1.5},
    {"symbol": "AUDUSD=X", "name": "Australian Dollar / US Dollar",  "class": "Forex",          "tick": 0.0001, "friction_type": "pips", "friction_val": 1.4},
    {"symbol": "USDCAD=X", "name": "US Dollar / Canadian Dollar",    "class": "Forex",          "tick": 0.0001, "friction_type": "pips", "friction_val": 1.6},
    {"symbol": "USDCHF=X", "name": "US Dollar / Swiss Franc",        "class": "Forex",          "tick": 0.0001, "friction_type": "pips", "friction_val": 1.7},
    {"symbol": "NZDUSD=X", "name": "New Zealand Dollar / US Dollar", "class": "Forex",          "tick": 0.0001, "friction_type": "pips", "friction_val": 1.8},
    {"symbol": "EURGBP=X", "name": "Euro / British Pound",           "class": "Forex",          "tick": 0.0001, "friction_type": "pips", "friction_val": 1.5},
    {"symbol": "EURJPY=X", "name": "Euro / Japanese Yen",            "class": "Forex",          "tick": 0.01,   "friction_type": "pips", "friction_val": 1.8},
    {"symbol": "GBPJPY=X", "name": "British Pound / Japanese Yen",   "class": "Forex",          "tick": 0.01,   "friction_type": "pips", "friction_val": 2.2},

    # Equity Indices / ETFs (6)
    {"symbol": "SPY",      "name": "SPDR S&P 500 ETF Trust",         "class": "Indices / ETFs", "tick": 0.01,   "friction_type": "bps",  "friction_val": 2.0},
    {"symbol": "QQQ",      "name": "Invesco QQQ Trust (Nasdaq-100)", "class": "Indices / ETFs", "tick": 0.01,   "friction_type": "bps",  "friction_val": 2.0},
    {"symbol": "DIA",      "name": "SPDR Dow Jones Ind. Average",    "class": "Indices / ETFs", "tick": 0.01,   "friction_type": "bps",  "friction_val": 2.5},
    {"symbol": "IWM",      "name": "iShares Russell 2000 ETF",       "class": "Indices / ETFs", "tick": 0.01,   "friction_type": "bps",  "friction_val": 3.0},
    {"symbol": "^FTSE",    "name": "FTSE 100 Index",                 "class": "Indices / ETFs", "tick": 0.10,   "friction_type": "bps",  "friction_val": 2.5},
    {"symbol": "^N225",    "name": "Nikkei 225 Index",               "class": "Indices / ETFs", "tick": 1.00,   "friction_type": "bps",  "friction_val": 3.0},

    # Blue-Chip Equities (6)
    {"symbol": "AAPL",     "name": "Apple Inc.",                     "class": "Single Equities","tick": 0.01,   "friction_type": "bps",  "friction_val": 2.0},
    {"symbol": "MSFT",     "name": "Microsoft Corporation",          "class": "Single Equities","tick": 0.01,   "friction_type": "bps",  "friction_val": 2.0},
    {"symbol": "NVDA",     "name": "NVIDIA Corporation",             "class": "Single Equities","tick": 0.01,   "friction_type": "bps",  "friction_val": 2.5},
    {"symbol": "AMZN",     "name": "Amazon.com Inc.",                "class": "Single Equities","tick": 0.01,   "friction_type": "bps",  "friction_val": 2.0},
    {"symbol": "GOOGL",    "name": "Alphabet Inc. (Class A)",        "class": "Single Equities","tick": 0.01,   "friction_type": "bps",  "friction_val": 2.0},
    {"symbol": "TSLA",     "name": "Tesla Inc.",                     "class": "Single Equities","tick": 0.01,   "friction_type": "bps",  "friction_val": 3.5},

    # Metals Commodities (4)
    {"symbol": "GC=F",     "name": "Gold Futures",                   "class": "Metals",         "tick": 0.10,   "friction_type": "bps",  "friction_val": 2.0},
    {"symbol": "SI=F",     "name": "Silver Futures",                 "class": "Metals",         "tick": 0.005,  "friction_type": "bps",  "friction_val": 3.5},
    {"symbol": "PL=F",     "name": "Platinum Futures",               "class": "Metals",         "tick": 0.10,   "friction_type": "bps",  "friction_val": 4.0},
    {"symbol": "HG=F",     "name": "Copper Futures",                 "class": "Metals",         "tick": 0.0005, "friction_type": "bps",  "friction_val": 3.0},

    # Energy Commodities (2)
    {"symbol": "CL=F",     "name": "Crude Oil WTI Futures",          "class": "Energy",         "tick": 0.01,   "friction_type": "bps",  "friction_val": 3.0},
    {"symbol": "NG=F",     "name": "Natural Gas Futures",            "class": "Energy",         "tick": 0.001,  "friction_type": "bps",  "friction_val": 5.0},

    # Crypto Assets (2)
    {"symbol": "BTC-USD",  "name": "Bitcoin / US Dollar",            "class": "Crypto",         "tick": 0.01,   "friction_type": "bps",  "friction_val": 6.0},
    {"symbol": "ETH-USD",  "name": "Ethereum / US Dollar",           "class": "Crypto",         "tick": 0.01,   "friction_type": "bps",  "friction_val": 7.0}
]

def run_single_asset_backtest_3m(cfg: dict) -> tuple[dict, pd.DataFrame, pd.DataFrame]:
    sym = cfg["symbol"]
    tick = cfg["tick"]

    # 1. Fetch Full Data (to compute 40-bar warm-up correctly) then slice last 90 days (3 months)
    df_full = RobustDataEngine.get_h4_data(symbol=sym, lookback_days=720)
    eps = 1e-8

    # 2. Compute Features on Full Data (strictly causal)
    macro_window = 40
    df_full['macro_high'] = df_full['high'].shift(1).rolling(macro_window).max()
    df_full['macro_low'] = df_full['low'].shift(1).rolling(macro_window).min()

    # Kaufman Macro Efficiency
    net_d = (df_full['close'].shift(1) - df_full['close'].shift(macro_window)).abs()
    gross_p = (df_full['close'].shift(1) - df_full['close'].shift(2)).abs().rolling(macro_window - 1).sum()
    df_full['macro_eff'] = net_d / (gross_p + eps)

    # Normalized Kinetic Dissipation (Body/Range)
    hl_safe = np.where(df_full['high'] - df_full['low'] == 0, eps, df_full['high'] - df_full['low'])
    df_full['phi_dissipation'] = (df_full['close'] - df_full['open']).abs() / hl_safe

    # Brownian Bridge
    num_h = (df_full['open'] - df_full['low']) * (df_full['high'] - df_full['close'])
    den_h = num_h + (df_full['high'] - df_full['open']) * (df_full['close'] - df_full['low']) + eps
    df_full['p_high_first'] = np.clip(num_h / den_h, 0.0, 1.0)

    # Signal Generation
    df_full['sig_long'] = (
        (df_full['macro_eff'] < 0.32) &
        (df_full['low'] < df_full['macro_low']) &
        (df_full['close'] > df_full['macro_low']) &
        (df_full['phi_dissipation'] <= 0.20) &
        (df_full['p_high_first'] <= 0.30)
    )

    df_full['sig_short'] = (
        (df_full['macro_eff'] < 0.32) &
        (df_full['high'] > df_full['macro_high']) &
        (df_full['close'] < df_full['macro_high']) &
        (df_full['phi_dissipation'] <= 0.20) &
        (df_full['p_high_first'] >= 0.70)
    )

    # Slice Last 90 Days (3 Months)
    cutoff_time = df_full.index[-1] - pd.Timedelta(days=90)
    df = df_full[df_full.index >= cutoff_time].copy()

    sig_long = df['sig_long'].values
    sig_short = df['sig_short'].values

    n = len(df)
    times = df.index
    opens = df['open'].values
    highs = df['high'].values
    lows = df['low'].values
    closes = df['close'].values

    # Setup execution simulator
    initial_equity = 100_000.0
    equity = initial_equity
    equity_series = np.zeros(n)
    trades = []

    in_trade = False
    entry_p, sl_p, tp_p, direction = 0, 0, 0, ""
    entry_t, entry_idx = None, 0
    size, risk_dist, dollar_risk = 0, 0, 0

    for t in range(n):
        current_time = times[t]
        o, h, l, c = opens[t], highs[t], lows[t], closes[t]

        if cfg["friction_type"] == "pips":
            bar_friction = cfg["friction_val"] * tick
        else:
            bar_friction = o * (cfg["friction_val"] * 0.0001)

        # 1. Manage existing open trade
        if in_trade:
            hold_bars = t - entry_idx
            pos_dir = 1 if direction == "long" else -1
            hit_sl = (l <= sl_p) if pos_dir == 1 else (h >= sl_p)
            hit_tp = (h >= tp_p) if pos_dir == 1 else (l <= tp_p)

            exit_triggered = False
            raw_exit_p = None
            reason = ""

            if hit_sl and hit_tp:
                exit_triggered = True
                raw_exit_p = sl_p
                reason = "Stop Loss (Pessimistic Resolution)"
            elif hit_sl:
                exit_triggered = True
                raw_exit_p = o if (pos_dir == 1 and o < sl_p) or (pos_dir == -1 and o > sl_p) else sl_p
                reason = "Stop Loss"
            elif hit_tp:
                exit_triggered = True
                raw_exit_p = o if (pos_dir == 1 and o > tp_p) or (pos_dir == -1 and o < tp_p) else tp_p
                reason = "Take Profit (4.5R)"
            elif hold_bars >= 18:
                exit_triggered = True
                raw_exit_p = c
                reason = "Time Barrier (18 Bars)"

            if exit_triggered and raw_exit_p is not None:
                eff_exit_p = raw_exit_p - bar_friction if pos_dir == 1 else raw_exit_p + bar_friction
                gross_diff = (eff_exit_p - entry_p) if pos_dir == 1 else (entry_p - eff_exit_p)
                trade_net_pnl = gross_diff * size
                equity += trade_net_pnl
                r_ret = trade_net_pnl / (dollar_risk + 1e-9)

                trades.append({
                    "Trade ID": len(trades) + 1,
                    "Symbol": sym,
                    "Asset Class": cfg["class"],
                    "Direction": direction.upper(),
                    "Entry Time": entry_t,
                    "Entry Price": round(entry_p, 5),
                    "Stop Loss": round(sl_p, 5),
                    "Take Profit": round(tp_p, 5),
                    "Exit Time": current_time,
                    "Exit Price": round(eff_exit_p, 5),
                    "Size": round(size, 4),
                    "Net PnL ($)": round(trade_net_pnl, 2),
                    "Return (R)": round(r_ret, 2),
                    "Holding Bars": hold_bars,
                    "Exit Reason": reason
                })
                in_trade = False

        # 2. Check entry signals from completed bar t-1 (filled at open of t)
        if not in_trade and t > 0:
            prev = t - 1
            if sig_long[prev]:
                in_trade = True
                direction = "long"
                entry_idx = t
                entry_t = current_time
                entry_p = o + bar_friction
                sl_p = lows[prev] - (6.0 * tick)
                risk_dist = abs(entry_p - sl_p)
                tp_p = entry_p + (4.5 * risk_dist)
                dollar_risk = equity * 0.015
                size = dollar_risk / (risk_dist + 1e-9)

            elif sig_short[prev]:
                in_trade = True
                direction = "short"
                entry_idx = t
                entry_t = current_time
                entry_p = o - bar_friction
                sl_p = highs[prev] + (6.0 * tick)
                risk_dist = abs(entry_p - sl_p)
                tp_p = entry_p - (4.5 * risk_dist)
                dollar_risk = equity * 0.015
                size = dollar_risk / (risk_dist + 1e-9)

        # 3. Mark to market at bar close
        if in_trade:
            pos_dir = 1 if direction == "long" else -1
            unrealized = (c - entry_p) * size if pos_dir == 1 else (entry_p - c) * size
            equity_series[t] = equity + unrealized
        else:
            equity_series[t] = equity

    # Close trade on last bar if open
    if in_trade:
        pos_dir = 1 if direction == "long" else -1
        eff_exit_p = closes[-1] - bar_friction if pos_dir == 1 else closes[-1] + bar_friction
        trade_net_pnl = (eff_exit_p - entry_p) * size if pos_dir == 1 else (entry_p - eff_exit_p) * size
        equity += trade_net_pnl
        trades.append({
            "Trade ID": len(trades) + 1,
            "Symbol": sym,
            "Asset Class": cfg["class"],
            "Direction": direction.upper(),
            "Entry Time": entry_t,
            "Entry Price": round(entry_p, 5),
            "Stop Loss": round(sl_p, 5),
            "Take Profit": round(tp_p, 5),
            "Exit Time": times[-1],
            "Exit Price": round(eff_exit_p, 5),
            "Size": round(size, 4),
            "Net PnL ($)": round(trade_net_pnl, 2),
            "Return (R)": round(trade_net_pnl / (dollar_risk + 1e-9), 2),
            "Holding Bars": n - 1 - entry_idx,
            "Exit Reason": "End of 3-Month Horizon"
        })

    peaks = np.maximum.accumulate(equity_series)
    dds = (equity_series - peaks) / peaks

    df_equity = pd.DataFrame({
        "equity": equity_series,
        "drawdown": dds
    }, index=times)

    df_trades = pd.DataFrame(trades)
    if not df_trades.empty:
        total_trades = len(df_trades)
        wins = df_trades[df_trades["Net PnL ($)"] > 0]
        losses = df_trades[df_trades["Net PnL ($)"] < 0]
        win_rate = (len(wins) / total_trades) * 100.0
        
        gross_w = wins["Net PnL ($)"].sum()
        gross_l = abs(losses["Net PnL ($)"].sum())
        pf = (gross_w / gross_l) if gross_l > 0 else (99.0 if gross_w > 0 else 0.0)
        
        avg_w = wins["Net PnL ($)"].mean() if len(wins) > 0 else 0.0
        avg_l = abs(losses["Net PnL ($)"].mean()) if len(losses) > 0 else 1.0
        payoff_b = avg_w / avg_l if avg_l > 0 else 0.0
        
        exp_r = df_trades["Return (R)"].mean()
        net_pnl = equity_series[-1] - initial_equity
        net_ret = (net_pnl / initial_equity) * 100.0
        max_dd = float(dds.min() * 100.0)
        
        bar_rets = df_equity["equity"].pct_change().dropna()
        # Annualized Sharpe for 3 months (~1575 4H periods/year)
        sharpe = (bar_rets.mean() / (bar_rets.std(ddof=1) + 1e-9)) * np.sqrt(1575) if len(bar_rets) > 1 else 0.0
    else:
        total_trades = 0
        win_rate = 0.0
        pf = 0.0
        payoff_b = 0.0
        exp_r = 0.0
        net_pnl = 0.0
        net_ret = 0.0
        max_dd = 0.0
        sharpe = 0.0

    metrics = {
        "Ticker": sym,
        "Asset Name": cfg["name"],
        "Asset Class": cfg["class"],
        "Total Trades": total_trades,
        "Win Rate (%)": round(win_rate, 1),
        "Payoff Ratio (b)": round(payoff_b, 2),
        "Net Expectancy (R)": round(exp_r, 2),
        "Profit Factor": round(pf, 2),
        "Max Drawdown (%)": round(max_dd, 2),
        "Net Return (%)": round(net_ret, 2),
        "Net PnL ($)": round(net_pnl, 2),
        "Annualized Sharpe": round(sharpe, 2)
    }

    return metrics, df_trades, df_equity

def main():
    print("=" * 95)
    print("MSRE-v1: 30-INSTRUMENT GLOBAL VALIDATION STUDY (LAST 3 MONTHS / 90 DAYS)")
    print("=" * 95)

    all_metrics = []
    trades_dict = {}
    equity_dict = {}

    for idx, cfg in enumerate(UNIVERSE, 1):
        sym = cfg["symbol"]
        print(f"[{idx:02d}/30] Ingesting & Simulating 3-Month Window for {sym:<10} ({cfg['name']})...")
        metrics, df_t, df_eq = run_single_asset_backtest_3m(cfg)
        all_metrics.append(metrics)
        trades_dict[sym] = df_t
        equity_dict[sym] = df_eq
        
        safe_sym = sym.replace("^", "IDX_").replace("=", "_").replace("/", "_").replace("-", "_")
        df_eq.to_parquet(os.path.join(EQUITY_CURVES_3M_DIR, f"{safe_sym}_equity_3m.parquet"))

    df_summary = pd.DataFrame(all_metrics)
    
    # Sort and rank by composite score: Profit Factor and Sharpe (handling 0 trade assets cleanly)
    df_summary["Rank Score"] = df_summary["Profit Factor"] * 0.5 + df_summary["Annualized Sharpe"] * 0.5
    df_summary = df_summary.sort_values(["Rank Score", "Net Return (%)"], ascending=[False, False]).reset_index(drop=True)
    df_summary.index = df_summary.index + 1
    df_summary.index.name = "Rank"
    df_summary = df_summary.reset_index()

    # Save summary metrics
    summary_path = os.path.join(RESULTS_DIR, "summary_metrics_3m.csv")
    df_summary.to_csv(summary_path, index=False)
    print(f"\n[OUTPUT] Saved complete 3-month metrics to {summary_path}")

    # Save trade logs for top 5 performers
    top5_tickers = df_summary.head(5)["Ticker"].tolist()
    print(f"\nTop 5 Champions (3 Months): {', '.join(top5_tickers)}")
    for t_sym in top5_tickers:
        safe_sym = t_sym.replace("^", "IDX_").replace("=", "_").replace("/", "_").replace("-", "_")
        log_path = os.path.join(TRADE_LOGS_3M_DIR, f"{safe_sym}_trades_3m.csv")
        trades_dict[t_sym].to_csv(log_path, index=False)
        print(f"[OUTPUT] Exported 3-month trade log for {t_sym} ({len(trades_dict[t_sym])} trades) to {log_path}")

    # Generate Asset Class Decomposition
    class_agg = df_summary.groupby("Asset Class").agg({
        "Ticker": "count",
        "Total Trades": "mean",
        "Win Rate (%)": "mean",
        "Payoff Ratio (b)": "mean",
        "Net Expectancy (R)": "mean",
        "Profit Factor": "mean",
        "Net Return (%)": "mean",
        "Max Drawdown (%)": "mean",
        "Annualized Sharpe": "mean"
    }).rename(columns={"Ticker": "Instrument Count"}).round(2)

    class_agg = class_agg.sort_values("Profit Factor", ascending=False)
    class_agg_path = os.path.join(RESULTS_DIR, "asset_class_decomposition_3m.csv")
    class_agg.to_csv(class_agg_path)
    print(f"\n[OUTPUT] Saved 3-Month Asset Class Decomposition to {class_agg_path}")

    # Generate Leaderboard Chart
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 8))
    
    colors = ['#2ca02c' if x > 1.25 else ('#ff7f0e' if x >= 1.0 else '#d62728') for x in df_summary['Profit Factor']]
    ax1.barh(df_summary['Ticker'][::-1], df_summary['Profit Factor'][::-1], color=colors[::-1])
    ax1.axvline(1.0, color='gray', linestyle='--', alpha=0.7, label='Breakeven (PF=1.0)')
    ax1.axvline(1.25, color='blue', linestyle=':', alpha=0.7, label='Institutional Gate (PF=1.25)')
    ax1.set_title("MSRE-v1 Profit Factor by Instrument (Last 3 Months)", fontsize=12, fontweight='bold')
    ax1.set_xlabel("Profit Factor", fontsize=11)
    ax1.legend(loc='lower right')
    ax1.grid(True, alpha=0.25)

    sharpe_colors = ['#1f77b4' if x > 0 else '#d62728' for x in df_summary['Annualized Sharpe']]
    ax2.barh(df_summary['Ticker'][::-1], df_summary['Annualized Sharpe'][::-1], color=sharpe_colors[::-1])
    ax2.axvline(0.0, color='gray', linestyle='--', alpha=0.7)
    ax2.set_title("Annualized Sharpe Ratio (Last 3 Months)", fontsize=12, fontweight='bold')
    ax2.set_xlabel("Sharpe Ratio", fontsize=11)
    ax2.grid(True, alpha=0.25)

    plt.tight_layout()
    chart_path = os.path.join(RESULTS_DIR, "leaderboard_30_assets_3m.png")
    plt.savefig(chart_path, dpi=200)
    plt.close()
    print(f"[OUTPUT] Generated 3-Month Leaderboard Chart at {chart_path}")

    # Generate Equity Curve Chart for Top 5 Champions in 3-Month Window
    fig, ax = plt.subplots(figsize=(12, 7))
    for t_sym in top5_tickers:
        eq_df = equity_dict[t_sym]
        norm_ret = (eq_df["equity"] / 100_000.0 - 1.0) * 100.0
        ax.plot(norm_ret.index, norm_ret, lw=2.0, label=f"{t_sym} (3M Return: {norm_ret.iloc[-1]:+.1f}%)")

    spy_eq = (equity_dict["SPY"]["equity"] / 100_000.0 - 1.0) * 100.0
    ax.plot(spy_eq.index, spy_eq, lw=1.5, color='black', linestyle='--', label=f"SPY (3M Return: {spy_eq.iloc[-1]:+.1f}%)")

    ax.axhline(0, color='gray', linestyle=':', alpha=0.5)
    ax.set_title("MSRE-v1 Top 5 Champions Equity Curves (Last 3 Months / 90 Days)", fontsize=13, fontweight='bold')
    ax.set_ylabel("Net Return (%)", fontsize=11)
    ax.set_xlabel("Date", fontsize=11)
    ax.grid(True, alpha=0.3)
    ax.legend(loc='upper left', frameon=True)
    plt.tight_layout()
    multi_path = os.path.join(RESULTS_DIR, "top5_equity_curves_3m.png")
    plt.savefig(multi_path, dpi=200)
    plt.close()
    print(f"[OUTPUT] Generated Top 5 Equity Curves (3M) at {multi_path}")

    # Console display
    print("\n" + "=" * 95)
    print("CROSS-ASSET BENCHMARK LEADERBOARD (LAST 3 MONTHS / 90 DAYS)")
    print("=" * 95)
    disp_cols = ["Rank", "Ticker", "Asset Class", "Total Trades", "Win Rate (%)", "Payoff Ratio (b)", "Net Expectancy (R)", "Profit Factor", "Max Drawdown (%)", "Net Return (%)", "Annualized Sharpe"]
    print(df_summary[disp_cols].to_string(index=False))

    print("\n" + "=" * 95)
    print("ASSET CLASS DECOMPOSITION (LAST 3 MONTHS)")
    print("=" * 95)
    print(class_agg.to_string())

if __name__ == "__main__":
    main()
