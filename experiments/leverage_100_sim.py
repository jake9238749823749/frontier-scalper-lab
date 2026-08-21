import numpy as np
import pandas as pd
from engine.data_engine import RobustDataEngine
from engine.msre_execution import MSREBacktestRunner
from strategies.msre_v1 import MSRE_Strategy

df_raw = RobustDataEngine.get_h4_data(symbol="GBPUSD=X", lookback_days=720)
strat = MSRE_Strategy(pip_size=0.0001, use_normalized_phi=True)
df_sig = strat.generate_signals(df_raw)

# Load trade sequence
runner_base = MSREBacktestRunner(initial_capital=100.0, risk_pct=0.015, pip_size=0.0001, spread_pips=1.2, slippage_pips=0.3)
eq_100_base, trades_100_base = runner_base.run(df_sig, symbol="GBPUSD=X")

print("=" * 80)
print("MSRE-v1: $100 STARTING CAPITAL AT 1:500 LEVERAGE (2-YEAR SIMULATION)")
print("=" * 80)

# SCENARIO 1: Pure Institutional 1.5% Risk (Fractional compounding)
final_eq_base = eq_100_base["equity"].iloc[-1]
pnl_base = final_eq_base - 100.0
ret_base = (pnl_base / 100.0) * 100.0
max_dd_base = eq_100_base["drawdown"].min() * 100.0

print(f"\n[SCENARIO 1] Baseline Strategy Rules (1.5% Risk Per Trade, Compounded)")
print(f"Margin Used per Trade: ~$1.20 - $1.80 (0.2% margin rate at 1:500)")
print(f"Final Equity:          ${final_eq_base:.2f}")
print(f"Net Profit:            ${pnl_base:+.2f} ({ret_base:+.2f}%)")
print(f"Max Drawdown:          {max_dd_base:.2f}%")

# SCENARIO 2: Minimum Retail Lot Size (1 Fixed Micro-Lot = 0.01 lot / 1,000 units)
# On a $100 account, brokers require minimum 0.01 lot.
# At 1:500 leverage, 0.01 lot of GBPUSD requires only $2.57 in margin.
# 1 pip move = $0.10.
equity_micro = 100.0
peak_micro = 100.0
mdd_micro = 0.0
micro_records = []

for t in trades_100_base:
    pos_dir = 1 if t.direction == "long" else -1
    diff = (t.exit_price - t.entry_price) if pos_dir == 1 else (t.entry_price - t.exit_price)
    t_pnl = diff * 1000.0  # 1,000 units
    equity_micro += t_pnl
    peak_micro = max(peak_micro, equity_micro)
    dd = (equity_micro - peak_micro) / peak_micro * 100.0
    mdd_micro = min(mdd_micro, dd)
    micro_records.append({"Trade ID": t.trade_id, "Equity": round(equity_micro, 2), "Trade PnL": round(t_pnl, 2)})

print(f"\n[SCENARIO 2] Standard Retail Broker Minimum (Fixed 0.01 Micro-Lot / 1,000 units)")
print(f"Required Margin per Trade: ~$2.57 (Leaves $97.43 free margin)")
print(f"Risk per Trade:            ~$2.00 - $3.50 (2.0% - 3.5% of starting capital)")
print(f"Final Equity:              ${equity_micro:.2f}")
print(f"Net Profit:                ${equity_micro - 100.0:+.2f} ({(equity_micro - 100.0)/100.0*100.0:+.2f}%)")
print(f"Max Drawdown:              {mdd_micro:.2f}%")

# SCENARIO 3: Dynamic Compounding at Higher Leverage / Risk Levels
print(f"\n[SCENARIO 3] Compounded Risk Multipliers (Using 1:500 Margin Capacity)")
print(f"{'Risk % / Trade':<16} | {'Final Equity ($)':<18} | {'Net Return (%)':<16} | {'Max Drawdown (%)':<18} | {'Status'}")
print("-" * 88)

for risk in [0.015, 0.03, 0.05, 0.08, 0.10, 0.15, 0.20, 0.25, 0.50]:
    eq = 100.0
    pk = 100.0
    mdd = 0.0
    blown = False
    
    for t in trades_100_base:
        dollar_risk = eq * risk
        size = dollar_risk / t.risk_distance
        
        # Max position possible at 1:500 leverage is equity * 500 / price
        max_size_allowed = (eq * 500.0) / t.entry_price
        if size > max_size_allowed:
            size = max_size_allowed
            
        pos_dir = 1 if t.direction == "long" else -1
        diff = (t.exit_price - t.entry_price) if pos_dir == 1 else (t.entry_price - t.exit_price)
        t_pnl = diff * size
        
        # Check if stopped out during trade (stop out at 20% margin level)
        if eq + t_pnl <= (size * t.entry_price / 500.0) * 0.20:
            blown = True
            eq = 0.0
            mdd = -100.0
            break
            
        eq += t_pnl
        if eq <= 5.0:
            blown = True
            eq = 0.0
            mdd = -100.0
            break
            
        pk = max(pk, eq)
        dd = (eq - pk) / pk * 100.0
        mdd = min(mdd, dd)
        
    if blown:
        status = "LIQUIDATED (Stop-out / Margin Call)"
        print(f"{risk*100:5.1f}%{'':<10} | {'$0.00':<18} | {'-100.0%':<16} | {'-100.0%':<18} | {status}")
    else:
        status = "Survived"
        print(f"{risk*100:5.1f}%{'':<10} | ${eq:10.2f}{'':<7} | {((eq-100.0)/100.0)*100:+10.1f}%{'':<5} | {mdd:10.1f}%{'':<7} | {status}")

# SCENARIO 4: "Max All-In" 1:500 Leverage (Full Margin Sizing)
print(f"\n[SCENARIO 4] Max 1:500 Full-Margin 'YOLO' (100% Margin Allocated)")
eq_max = 100.0
blown_max = False
for idx, t in enumerate(trades_100_base):
    # Max size at 1:500 leverage = $100 * 500 / 1.2850 = ~38,900 units (0.38 lots)
    max_size = (eq_max * 500.0) / t.entry_price
    pos_dir = 1 if t.direction == "long" else -1
    diff = (t.exit_price - t.entry_price) if pos_dir == 1 else (t.entry_price - t.exit_price)
    t_pnl = diff * max_size
    print(f"Trade {t.trade_id} ({t.direction.upper()}): Size={max_size:.0f} units ({max_size/100000:.2f} lots). PnL: ${t_pnl:+.2f}")
    if eq_max + t_pnl <= 0 or diff < -0.0020: # 20 pips against 500x leverage wipes $100
        blown_max = True
        print(f"--> Margin Call & Liquidation on Trade {t.trade_id}! Account Balance: $0.00")
        break
    eq_max += t_pnl

print("=" * 80)
