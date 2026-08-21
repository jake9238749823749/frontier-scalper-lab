import numpy as np
import pandas as pd
from engine.data_engine import RobustDataEngine
from engine.msre_execution import MSREBacktestRunner
from strategies.msre_v1 import MSRE_Strategy

df_raw = RobustDataEngine.get_h4_data(symbol="GBPUSD=X", lookback_days=720)
strat = MSRE_Strategy(pip_size=0.0001, use_normalized_phi=True)
df_sig = strat.generate_signals(df_raw)

runner_base = MSREBacktestRunner(initial_capital=100.0, risk_pct=0.015, pip_size=0.0001, spread_pips=1.2, slippage_pips=0.3)
eq_100_base, trades_100_base = runner_base.run(df_sig, symbol="GBPUSD=X")

print("=" * 95)
print("MSRE-v1: INCREMENTAL POSITION SIZING FROM $100 (1:100 LEVERAGE)")
print("=" * 95)

# -------------------------------------------------------------------------
# MODEL 1: DISCRETE STEP SCALING (0.01 Lot per $X increment)
# -------------------------------------------------------------------------
print("\n--- MODEL 1: Step Scaling (+0.01 lot per $X Account Increment) ---")
print(f"{'Step Threshold':<20} | {'Final Equity ($)':<18} | {'Net Return (%)':<16} | {'Max DD (%)':<14} | {'Peak Lot Size':<14} | {'Status'}")
print("-" * 95)

for step_dollars in [10.0, 20.0, 25.0, 30.0, 50.0, 75.0, 100.0]:
    eq = 100.0
    pk = 100.0
    mdd = 0.0
    peak_lots = 0.01
    blown = False
    
    for t in trades_100_base:
        # Calculate lot size based on current equity
        lots = max(0.01, round(np.floor(eq / step_dollars) * 0.01, 2))
        peak_lots = max(peak_lots, lots)
        units = lots * 100_000.0
        
        req_margin = (units * t.entry_price) / 100.0  # 1:100 leverage
        
        # If margin exceeds equity, cap lots to max allowable
        if req_margin > eq:
            lots = max(0.01, round(np.floor((eq * 100.0 / t.entry_price) / 1000.0) * 0.01, 2))
            units = lots * 100_000.0
            req_margin = (units * t.entry_price) / 100.0
            
        pos_dir = 1 if t.direction == "long" else -1
        diff = (t.exit_price - t.entry_price) if pos_dir == 1 else (t.entry_price - t.exit_price)
        t_pnl = diff * units
        
        if eq + t_pnl <= req_margin * 0.50 or eq + t_pnl <= 5.0:
            blown = True
            eq = 0.0
            mdd = -100.0
            break
            
        eq += t_pnl
        pk = max(pk, eq)
        dd = (eq - pk) / pk * 100.0
        mdd = min(mdd, dd)
        
    if blown:
        status = "STOPPED OUT (Margin Call)"
        print(f"+0.01 lot / ${step_dollars:<6.0f}     | {'$0.00':<18} | {'-100.0%':<16} | {'-100.0%':<14} | {peak_lots:.2f} lots       | {status}")
    else:
        status = "Survived"
        print(f"+0.01 lot / ${step_dollars:<6.0f}     | ${eq:10.2f}{'':<7} | {((eq-100.0)/100.0)*100:+10.1f}%{'':<5} | {mdd:8.1f}%      | {peak_lots:.2f} lots       | {status}")


# -------------------------------------------------------------------------
# MODEL 2: DYNAMIC PROPORTIONAL RISK COMPOUNDING (With 0.01 lot resolution)
# -------------------------------------------------------------------------
print("\n--- MODEL 2: Proportional Fractional Risk Compounding (0.01 lot resolution) ---")
print(f"{'Risk % / Trade':<20} | {'Final Equity ($)':<18} | {'Net Return (%)':<16} | {'Max DD (%)':<14} | {'Peak Lot Size':<14} | {'Status'}")
print("-" * 95)

for risk_pct in [0.015, 0.02, 0.03, 0.04, 0.05, 0.06, 0.08, 0.10]:
    eq = 100.0
    pk = 100.0
    mdd = 0.0
    peak_lots = 0.01
    blown = False
    
    for t in trades_100_base:
        dollar_risk = eq * risk_pct
        calc_units = dollar_risk / t.risk_distance
        # Round to 0.01 lot (1,000 unit) increments
        lots = max(0.01, round(calc_units / 1000.0) * 0.01)
        peak_lots = max(peak_lots, lots)
        units = lots * 100_000.0
        
        req_margin = (units * t.entry_price) / 100.0  # 1:100 leverage
        
        if req_margin > eq:
            lots = max(0.01, round(np.floor((eq * 100.0 / t.entry_price) / 1000.0) * 0.01, 2))
            units = lots * 100_000.0
            req_margin = (units * t.entry_price) / 100.0
            
        pos_dir = 1 if t.direction == "long" else -1
        diff = (t.exit_price - t.entry_price) if pos_dir == 1 else (t.entry_price - t.exit_price)
        t_pnl = diff * units
        
        if eq + t_pnl <= req_margin * 0.50 or eq + t_pnl <= 5.0:
            blown = True
            eq = 0.0
            mdd = -100.0
            break
            
        eq += t_pnl
        pk = max(pk, eq)
        dd = (eq - pk) / pk * 100.0
        mdd = min(mdd, dd)
        
    if blown:
        status = "STOPPED OUT (Margin Call)"
        print(f"{risk_pct*100:5.1f}% Risk            | {'$0.00':<18} | {'-100.0%':<16} | {'-100.0%':<14} | {peak_lots:.2f} lots       | {status}")
    else:
        status = "Survived"
        print(f"{risk_pct*100:5.1f}% Risk            | ${eq:10.2f}{'':<7} | {((eq-100.0)/100.0)*100:+10.1f}%{'':<5} | {mdd:8.1f}%      | {peak_lots:.2f} lots       | {status}")

# -------------------------------------------------------------------------
# DETAILED TRADE LOG FOR THE SWEET SPOT (+0.01 lot per $25 increment)
# -------------------------------------------------------------------------
print("\n" + "=" * 95)
print("TRADE-BY-TRADE AUDIT: +0.01 LOT PER $25 INCREMENT (SWEET SPOT)")
print("=" * 95)

eq = 100.0
step_dollars = 25.0
print(f"{'Tr #':<5} | {'Type':<6} | {'Entry Time':<16} | {'Account ($)':<12} | {'Lots Traded':<12} | {'Margin ($)':<11} | {'PnL ($)':<11} | {'New Balance ($)'}")
print("-" * 95)

for idx, t in enumerate(trades_100_base):
    lots = max(0.01, round(np.floor(eq / step_dollars) * 0.01, 2))
    units = lots * 100_000.0
    req_margin = (units * t.entry_price) / 100.0
    
    pos_dir = 1 if t.direction == "long" else -1
    diff = (t.exit_price - t.entry_price) if pos_dir == 1 else (t.entry_price - t.exit_price)
    t_pnl = diff * units
    new_eq = eq + t_pnl
    
    print(f"{t.trade_id:<5} | {t.direction.upper():<6} | {str(t.entry_time)[:16]:<16} | ${eq:10.2f}  | {lots:5.2f} lots  | ${req_margin:7.2f}   | ${t_pnl:+8.2f}  | ${new_eq:10.2f}")
    eq = new_eq

print("=" * 95)
