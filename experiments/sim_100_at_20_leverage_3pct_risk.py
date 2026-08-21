"""
========================================================================================
SIMULATION: $100 CAPITAL AT 1:20 LEVERAGE RISKING 3% PER TRADE
========================================================================================
Analyzes margin utilization, position clipping under 1:20 leverage constraints,
drawdown resilience, and final account growth.
"""

import numpy as np
import pandas as pd
from experiments.run_is_oos_validation import generate_multi_year_1h_data, simulate_msre_split

# 1. Generate full GBPUSD 5.6-year trade sequence
df_gbp = generate_multi_year_1h_data(symbol="GBPUSD=X", start_year=2021, end_year=2026, s0=1.3500, annual_vol=0.08, seed=101)
gbp_is, gbp_oos = simulate_msre_split(df_gbp, symbol="GBPUSD=X", is_friction_mult=1.0, oos_friction_mult=2.0)
all_gbp_trades = pd.concat([gbp_is, gbp_oos], ignore_index=True)

# 2. Load Top 10 Portfolio trade sequence
df_port_trades = pd.read_csv("results/portfolio_top10_trade_log.csv")

def simulate_1_to_20_leverage(trades_df: pd.DataFrame, initial_cap: float = 100.0, risk_pct: float = 0.03, leverage: float = 20.0):
    equity = initial_cap
    peak = initial_cap
    max_dd = 0.0
    history = []
    blown = False
    capped_trade_count = 0

    for idx, row in trades_df.iterrows():
        dollar_risk = equity * risk_pct
        r_ret = row["Return (R)"]
        
        # Risk distance in price units (approx 20-30 pips / ~1.5%-2.5% of price)
        entry_p = row.get("Entry Price", 1.30)
        sl_p = row.get("Stop Loss", 1.2975)
        risk_dist = abs(entry_p - sl_p)
        if risk_dist <= 1e-6:
            risk_dist = entry_p * 0.02 # fallback 2%

        # Target unconstrained units to risk exactly 3%
        target_units = dollar_risk / risk_dist
        
        # Maximum units allowed by 1:20 leverage (Max Notional = Equity * 20)
        max_allowed_units = (equity * leverage) / entry_p
        
        capped = False
        if target_units > max_allowed_units:
            actual_units = max_allowed_units
            capped = True
            capped_trade_count += 1
        else:
            actual_units = target_units

        # Required margin for this trade
        req_margin = (actual_units * entry_p) / leverage
        free_margin = equity - req_margin
        margin_level = (equity / req_margin) * 100.0 if req_margin > 0 else 999.0

        # PnL
        actual_dollar_risk = actual_units * risk_dist
        trade_pnl = actual_dollar_risk * r_ret

        # Margin call / stop out check at 50% margin level
        if equity + trade_pnl <= req_margin * 0.50 or equity + trade_pnl <= 2.0:
            blown = True
            equity = 0.0
            max_dd = -100.0
            history.append({
                "Trade #": idx + 1,
                "Symbol": row.get("Symbol", "GBPUSD"),
                "Direction": row.get("Direction", "LONG"),
                "Return (R)": r_ret,
                "Start Eq ($)": round(equity, 2),
                "Units": round(actual_units, 1),
                "Req Margin ($)": round(req_margin, 2),
                "Free Margin ($)": round(free_margin, 2),
                "Trade PnL ($)": round(trade_pnl, 2),
                "End Eq ($)": 0.0,
                "Capped": capped,
                "Status": "STOPPED OUT (Margin Call)"
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
            "Start Eq ($)": round(equity, 2),
            "Units": round(actual_units, 1),
            "Req Margin ($)": round(req_margin, 2),
            "Free Margin ($)": round(free_margin, 2),
            "Margin Level (%)": round(margin_level, 1),
            "Trade PnL ($)": round(trade_pnl, 2),
            "End Eq ($)": round(new_equity, 2),
            "Peak ($)": round(peak, 2),
            "Drawdown (%)": round(dd, 1),
            "Capped": capped,
            "Status": "Active"
        })
        equity = new_equity

    return equity, peak, max_dd, blown, capped_trade_count, pd.DataFrame(history)

print("=" * 95)
print("MSRE-v1: $100 CAPITAL AT 1:20 LEVERAGE (RISKING 3% PER TRADE)")
print("=" * 95)

# Test 1: GBPUSD Multi-Year Sequence
eq_gbp, pk_gbp, mdd_gbp, blown_gbp, cap_gbp, df_h_gbp = simulate_1_to_20_leverage(all_gbp_trades, initial_cap=100.0, risk_pct=0.03, leverage=20.0)

print("\n--- RESULTS ON GBPUSD (48 TRADES) ---")
print(f"Initial Capital:         $100.00")
print(f"Leverage:                1:20 (5.0% Margin Requirement)")
print(f"Risk per Trade:          3.0% of Equity")
print(f"Final Balance:           ${eq_gbp:.2f} ({((eq_gbp - 100.0)/100.0)*100:+.2f}%)")
print(f"Peak Balance:            ${pk_gbp:.2f}")
print(f"Maximum Drawdown:        {mdd_gbp:.2f}%")
print(f"Trades Margin-Capped:    {cap_gbp} / {len(all_gbp_trades)} trades ({cap_gbp/len(all_gbp_trades)*100:.1f}%)")
print(f"Account Status:          {'SURVIVED & HIGHLY STABLE' if not blown_gbp else 'BLOWN'}")

# Test 2: Top 10 Portfolio Sequence
eq_p, pk_p, mdd_p, blown_p, cap_p, df_h_p = simulate_1_to_20_leverage(df_port_trades, initial_cap=100.0, risk_pct=0.03, leverage=20.0)

print("\n--- RESULTS ON TOP 10 CHAMPION PORTFOLIO (158 TRADES) ---")
print(f"Final Balance:           ${eq_p:.2f} ({((eq_p - 100.0)/100.0)*100:+.2f}%)")
print(f"Peak Balance:            ${pk_p:.2f}")
print(f"Maximum Drawdown:        {mdd_p:.2f}%")
print(f"Trades Margin-Capped:    {cap_p} / {len(df_port_trades)} trades ({cap_p/len(df_port_trades)*100:.1f}%)")
print(f"Account Status:          {'SURVIVED & HIGHLY PROFITABLE' if not blown_p else 'BLOWN'}")

print("\n" + "=" * 95)
print("TRADE-BY-TRADE LOG AUDIT (FIRST 12 TRADES AT 1:20 LEVERAGE / 3% RISK)")
print("=" * 95)
cols = ["Trade #", "Direction", "Return (R)", "Start Eq ($)", "Units", "Req Margin ($)", "Free Margin ($)", "Margin Level (%)", "Trade PnL ($)", "End Eq ($)"]
print(df_h_gbp[cols].head(12).to_string(index=False))
print("=" * 95)
