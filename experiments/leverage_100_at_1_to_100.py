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

print("=" * 80)
print("MSRE-v1: $100 STARTING CAPITAL AT 1:100 LEVERAGE (2-YEAR SIMULATION)")
print("=" * 80)

# SCENARIO 1: Pure 1.5% Risk (Fractional Compounding)
final_eq_base = eq_100_base["equity"].iloc[-1]
pnl_base = final_eq_base - 100.0
ret_base = (pnl_base / 100.0) * 100.0
max_dd_base = eq_100_base["drawdown"].min() * 100.0

print(f"\n[SCENARIO 1] Baseline Strategy Rules (1.5% Risk Per Trade, Compounded)")
print(f"Margin Used per Trade: ~$6.00 - $9.00 (1.0% margin rate at 1:100)")
print(f"Final Equity:          ${final_eq_base:.2f}")
print(f"Net Profit:            ${pnl_base:+.2f} ({ret_base:+.2f}%)")
print(f"Max Drawdown:          {max_dd_base:.2f}%")

# SCENARIO 2: 1 Fixed Micro-Lot (0.01 lot = 1,000 units)
# At 1:100 leverage, 1,000 units requires $12.85 in margin.
equity_micro = 100.0
peak_micro = 100.0
mdd_micro = 0.0
min_free_margin = 100.0

for t in trades_100_base:
    req_margin = (1000.0 * t.entry_price) / 100.0  # ~$12.85
    free_margin = equity_micro - req_margin
    min_free_margin = min(min_free_margin, free_margin)
    
    pos_dir = 1 if t.direction == "long" else -1
    diff = (t.exit_price - t.entry_price) if pos_dir == 1 else (t.entry_price - t.exit_price)
    t_pnl = diff * 1000.0
    equity_micro += t_pnl
    peak_micro = max(peak_micro, equity_micro)
    dd = (equity_micro - peak_micro) / peak_micro * 100.0
    mdd_micro = min(mdd_micro, dd)

print(f"\n[SCENARIO 2] Standard Retail Broker Minimum (Fixed 0.01 Micro-Lot / 1,000 units)")
print(f"Required Margin per Trade: ~$12.85 (Leaves $87.15 free margin initially)")
print(f"Lowest Free Margin in DD:  ${min_free_margin:.2f}")
print(f"Risk per Trade:            ~$2.00 - $3.50 (2.0% - 3.5% of starting capital)")
print(f"Final Equity:              ${equity_micro:.2f}")
print(f"Net Profit:                ${equity_micro - 100.0:+.2f} ({(equity_micro - 100.0)/100.0*100.0:+.2f}%)")
print(f"Max Drawdown:              {mdd_micro:.2f}%")

# SCENARIO 3: Compounded Risk Levels with 1:100 Leverage Capacity
print(f"\n[SCENARIO 3] Compounded Risk Multipliers (Constrained by 1:100 Margin Capacity)")
print(f"{'Risk % / Trade':<16} | {'Margin Required ($)':<20} | {'Final Equity ($)':<16} | {'Net Return (%)':<16} | {'Max DD (%)':<12} | {'Status'}")
print("-" * 100)

for risk in [0.015, 0.03, 0.05, 0.08, 0.10, 0.15, 0.20, 0.25]:
    eq = 100.0
    pk = 100.0
    mdd = 0.0
    blown = False
    max_margin_used = 0.0
    
    for t in trades_100_base:
        dollar_risk = eq * risk
        size = dollar_risk / t.risk_distance
        
        # Max position possible at 1:100 leverage is equity * 100 / price
        max_size_allowed = (eq * 100.0) / t.entry_price
        capped = False
        if size > max_size_allowed:
            size = max_size_allowed
            capped = True
            
        req_margin = (size * t.entry_price) / 100.0
        max_margin_used = max(max_margin_used, req_margin)
        
        pos_dir = 1 if t.direction == "long" else -1
        diff = (t.exit_price - t.entry_price) if pos_dir == 1 else (t.entry_price - t.exit_price)
        t_pnl = diff * size
        
        # Check margin call / stop out at 50% margin level
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
        print(f"{risk*100:5.1f}%{'':<10} | {'N/A':<20} | {'$0.00':<16} | {'-100.0%':<16} | {'-100.0%':<12} | {status}")
    else:
        status = "Survived"
        print(f"{risk*100:5.1f}%{'':<10} | ${max_margin_used:7.2f}{'':<12} | ${eq:10.2f}{'':<5} | {((eq-100.0)/100.0)*100:+10.1f}%{'':<5} | {mdd:8.1f}%   | {status}")

# SCENARIO 4: "Max All-In" 1:100 Leverage (100% Margin Allocated)
print(f"\n[SCENARIO 4] Max 1:100 Full-Margin (100% Margin Allocated)")
eq_max = 100.0
blown_max = False
for idx, t in enumerate(trades_100_base):
    # Max size at 1:100 leverage = $100 * 100 / 1.2850 = ~7,780 units (0.078 lots)
    max_size = (eq_max * 100.0) / t.entry_price
    req_margin = (max_size * t.entry_price) / 100.0
    pos_dir = 1 if t.direction == "long" else -1
    diff = (t.exit_price - t.entry_price) if pos_dir == 1 else (t.entry_price - t.exit_price)
    t_pnl = diff * max_size
    print(f"Trade {t.trade_id} ({t.direction.upper()}): Size={max_size:.0f} units (0.0{max_size/100000*100:.0f} lots, Margin=${req_margin:.2f}). PnL: ${t_pnl:+.2f}")
    if eq_max + t_pnl <= req_margin * 0.50:
        blown_max = True
        print(f"--> Margin Call & Stop-Out on Trade {t.trade_id}! Account Balance: $0.00")
        break
    eq_max += t_pnl

print("=" * 80)
