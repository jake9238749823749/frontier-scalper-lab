"""
========================================================================================
SIMULATION: $100 CAPITAL AT 1:220 LEVERAGE RISKING 25% TO 50% PER TRADE
========================================================================================
Evaluates ultra-aggressive compounding, geometric peak growth, volatility drag,
and margin-call / liquidation dynamics across the multi-year backtest trade sequence.
"""

import numpy as np
import pandas as pd
from experiments.run_is_oos_validation import generate_multi_year_1h_data, simulate_msre_split

# Generate full 5.6-year continuous data for GBPUSD and Gold
df_gbp = generate_multi_year_1h_data(symbol="GBPUSD=X", start_year=2021, end_year=2026, s0=1.3500, annual_vol=0.08, seed=101)
gbp_is, gbp_oos = simulate_msre_split(df_gbp, symbol="GBPUSD=X", is_friction_mult=1.0, oos_friction_mult=2.0)
all_gbp_trades = pd.concat([gbp_is, gbp_oos], ignore_index=True)

# Also test on Top-10 Portfolio trade sequence
df_port_trades = pd.read_csv("results/portfolio_top10_trade_log.csv")

def simulate_aggressive_leverage(
    trades_df: pd.DataFrame,
    initial_cap: float = 100.0,
    leverage: float = 220.0,
    risk_pct: float = 0.25,
    stop_out_level: float = 0.50 # 50% margin call / liquidation level
):
    equity = initial_cap
    peak = initial_cap
    max_dd = 0.0
    history = []
    blown = False
    liquidation_trade = None

    for idx, row in trades_df.iterrows():
        r_ret = row["Return (R)"]
        dollar_risk = equity * risk_pct
        
        # In MSRE-v1, unit risk distance is ~0.0025 (25 pips on GBPUSD)
        # Position size in dollars = dollar_risk / (risk_distance_pct)
        # Required margin at 1:220 leverage = Position_Value / 220
        # If risk is 25%, size is 0.25 * equity / 0.02 = 12.5x equity
        # Required margin = 12.5x equity / 220 = 5.68% of equity (well within 1:220 margin)
        # At 50% risk, size is 0.50 * equity / 0.02 = 25x equity
        # Required margin = 25x / 220 = 11.36% of equity
        
        trade_pnl = dollar_risk * r_ret
        
        # Check if trade causes stop out / liquidation
        # If a single loss is >= equity (e.g. -1.0R at 100% risk) or equity drops below minimum margin
        if equity + trade_pnl <= equity * 0.05 or equity + trade_pnl <= 2.0:
            blown = True
            liquidation_trade = idx + 1
            equity = 0.0
            max_dd = -100.0
            history.append({
                "Trade #": idx + 1,
                "Symbol": row.get("Symbol", "GBPUSD"),
                "Direction": row.get("Direction", "LONG"),
                "Return (R)": r_ret,
                "Start Balance ($)": round(equity, 2),
                "Trade PnL ($)": round(trade_pnl, 2),
                "End Balance ($)": 0.0,
                "Status": "LIQUIDATED (Stop-out)"
            })
            break

        new_equity = equity + trade_pnl
        peak = max(peak, new_equity)
        dd = (new_equity - peak) / peak * 100.0
        max_dd = min(max_dd, dd)

        history.append({
            "Trade #": idx + 1,
            "Symbol": row.get("Symbol", "GBPUSD"),
            "Direction": row.get("Direction", "LONG"),
            "Return (R)": r_ret,
            "Start Balance ($)": round(equity, 2),
            "Trade PnL ($)": round(trade_pnl, 2),
            "End Balance ($)": round(new_equity, 2),
            "Peak ($)": round(peak, 2),
            "Drawdown (%)": round(dd, 1),
            "Status": "Active"
        })
        equity = new_equity

    return equity, peak, max_dd, blown, liquidation_trade, pd.DataFrame(history)

print("=" * 95)
print("MSRE-v1: $100 ACCOUNT AT 1:220 LEVERAGE (RISKING 25% TO 50% PER TRADE)")
print("=" * 95)

# Test GBPUSD Trade Sequence across risk levels
print("\n--- TEST A: GBPUSD Multi-Year Trade Sequence (48 Trades) ---")
print(f"{'Risk % / Trade':<16} | {'Final Balance ($)':<20} | {'Peak Balance ($)':<18} | {'Max Drawdown (%)':<16} | {'Status'}")
print("-" * 95)

for r_pct in [0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50]:
    final_eq, peak_eq, mdd, blown, liq_tr, df_hist = simulate_aggressive_leverage(all_gbp_trades, initial_cap=100.0, leverage=220.0, risk_pct=r_pct)
    status_str = f"LIQUIDATED on Trade #{liq_tr}" if blown else "Survived"
    print(f"{r_pct*100:5.1f}% Risk       | ${final_eq:14.2f}{'':<5} | ${peak_eq:12.2f}{'':<5} | {mdd:10.1f}%{'':<6} | {status_str}")

# Test Top 10 Champion Portfolio Sequence (158 Trades)
print("\n--- TEST B: Top 10 Champion Portfolio Trade Sequence (158 Trades) ---")
print(f"{'Risk % / Trade':<16} | {'Final Balance ($)':<20} | {'Peak Balance ($)':<18} | {'Max Drawdown (%)':<16} | {'Status'}")
print("-" * 95)

for r_pct in [0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50]:
    final_eq, peak_eq, mdd, blown, liq_tr, df_hist_p = simulate_aggressive_leverage(df_port_trades, initial_cap=100.0, leverage=220.0, risk_pct=r_pct)
    status_str = f"LIQUIDATED on Trade #{liq_tr}" if blown else "Survived"
    print(f"{r_pct*100:5.1f}% Risk       | ${final_eq:14.2f}{'':<5} | ${peak_eq:12.2f}{'':<5} | {mdd:10.1f}%{'':<6} | {status_str}")

# Print Detailed Trade Log for 25% Risk on GBPUSD
_, _, _, _, _, df_gbp_25 = simulate_aggressive_leverage(all_gbp_trades, initial_cap=100.0, leverage=220.0, risk_pct=0.25)
print("\n" + "=" * 95)
print("TRADE-BY-TRADE AUDIT: $100 AT 1:220 LEVERAGE RISKING 25% PER TRADE (GBPUSD)")
print("=" * 95)
print(df_gbp_25[["Trade #", "Direction", "Return (R)", "Start Balance ($)", "Trade PnL ($)", "End Balance ($)", "Peak ($)", "Drawdown (%)"]].head(15).to_string(index=False))
print("...")
print(df_gbp_25[["Trade #", "Direction", "Return (R)", "Start Balance ($)", "Trade PnL ($)", "End Balance ($)", "Peak ($)", "Drawdown (%)"]].tail(10).to_string(index=False))
print("=" * 95)
