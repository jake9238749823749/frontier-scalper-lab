import numpy as np
import pandas as pd
from engine.data_engine import RobustDataEngine
from strategies.msre_v1 import MSRE_Strategy

df_raw = RobustDataEngine.get_h4_data(symbol="GBPUSD=X", lookback_days=720)
strat = MSRE_Strategy(pip_size=0.0001, use_normalized_phi=True)
df_sig = strat.generate_signals(df_raw)

print("=" * 95)
print("THEORETICAL MAXIMUM GROWTH & HIGH R:R EXPERIMENTATION (GBPUSD=X 4H)")
print("=" * 95)

# Extract raw price and signal arrays
n = len(df_sig)
times = df_sig.index
opens = df_sig["open"].values
highs = df_sig["high"].values
lows = df_sig["low"].values
closes = df_sig["close"].values
pip_size = 0.0001
friction = (0.5 * 1.2 + 0.3) * pip_size  # 0.9 pips per side

sig_sw_long = df_sig["sig_sweep_long"].values
sig_sw_short = df_sig["sig_sweep_short"].values
macro_highs = df_sig["macro_high"].values
macro_lows = df_sig["macro_low"].values
macro_mids = df_sig["macro_mid"].values

# -------------------------------------------------------------------------
# PART 1: TEST R:R TARGET MULTIPLIERS (From 2R to 10R and Opposing Macro Band)
# -------------------------------------------------------------------------
def simulate_target_rules(target_mode="multiplier", r_mult=3.0, time_stop_bars=18):
    """
    Simulates trades with specific R:R target logic.
    target_mode:
      - 'midpoint': Original S_eq
      - 'opposing_band': Target is Opposing 30-bar Macro Extreme (Full Range Expansion)
      - 'multiplier': Fixed R-multiple (e.g. 3R, 5R, 8R, 10R)
    """
    trades = []
    in_trade = False
    entry_p, sl_p, tp_p, direction = 0, 0, 0, ""
    entry_t, entry_idx = None, 0
    risk_dist = 0

    for t in range(1, n):
        o, h, l, c = opens[t], highs[t], lows[t], closes[t]

        # 1. Manage open trade
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
                reason = "SL (Conflict Priority)"
            elif hit_sl:
                exit_triggered = True
                raw_exit_p = sl_p
                reason = "Stop Loss"
            elif hit_tp:
                exit_triggered = True
                raw_exit_p = tp_p
                reason = "Take Profit"
            elif hold_bars >= time_stop_bars:
                exit_triggered = True
                raw_exit_p = c
                reason = "Time Stop"

            if exit_triggered:
                eff_exit_p = raw_exit_p - friction if pos_dir == 1 else raw_exit_p + friction
                gross_diff = (eff_exit_p - entry_p) if pos_dir == 1 else (entry_p - eff_exit_p)
                r_return = gross_diff / (risk_dist + 1e-9)
                trades.append({
                    "entry_time": entry_t,
                    "exit_time": times[t],
                    "direction": direction,
                    "r_return": r_return,
                    "holding_bars": hold_bars,
                    "reason": reason
                })
                in_trade = False

        # 2. Check new entries from t-1
        if not in_trade:
            prev = t - 1
            if sig_sw_long[prev]:
                in_trade = True
                direction = "long"
                entry_idx = t
                entry_t = times[t]
                entry_p = o + friction
                sl_p = lows[prev] - (8.0 * pip_size)
                risk_dist = abs(entry_p - sl_p)
                
                if target_mode == "midpoint":
                    tp_p = macro_mids[prev]
                elif target_mode == "opposing_band":
                    tp_p = macro_highs[prev]  # Aim for the entire 5-day range!
                elif target_mode == "multiplier":
                    tp_p = entry_p + (r_mult * risk_dist)

            elif sig_sw_short[prev]:
                in_trade = True
                direction = "short"
                entry_idx = t
                entry_t = times[t]
                entry_p = o - friction
                sl_p = highs[prev] + (8.0 * pip_size)
                risk_dist = abs(entry_p - sl_p)
                
                if target_mode == "midpoint":
                    tp_p = macro_mids[prev]
                elif target_mode == "opposing_band":
                    tp_p = macro_lows[prev]  # Aim for the entire 5-day range!
                elif target_mode == "multiplier":
                    tp_p = entry_p - (r_mult * risk_dist)

    return pd.DataFrame(trades)

# Test target models
target_configs = [
    {"name": "Original Midpoint (S_eq)", "mode": "midpoint", "mult": 0.0, "time_stop": 18},
    {"name": "Opposing 5-Day Macro Extreme", "mode": "opposing_band", "mult": 0.0, "time_stop": 36},
    {"name": "Fixed 3.0R Target (Extended Time)", "mode": "multiplier", "mult": 3.0, "time_stop": 36},
    {"name": "Fixed 4.0R Target (Extended Time)", "mode": "multiplier", "mult": 4.0, "time_stop": 48},
    {"name": "Fixed 5.0R Target (Extended Time)", "mode": "multiplier", "mult": 5.0, "time_stop": 60},
    {"name": "Fixed 8.0R Target (Ultra R:R)", "mode": "multiplier", "mult": 8.0, "time_stop": 90},
    {"name": "Fixed 10.0R Target (Extreme R:R)", "mode": "multiplier", "mult": 10.0, "time_stop": 120}
]

results_summary = []
trade_dfs = {}

print(f"{'Target Strategy / R:R':<32} | {'Trades':<7} | {'Win %':<7} | {'PF':<6} | {'Avg Win':<9} | {'Exp (R)':<8} | {'Kelly f*':<9}")
print("-" * 95)

for cfg in target_configs:
    tdf = simulate_target_rules(target_mode=cfg["mode"], r_mult=cfg["mult"], time_stop_bars=cfg["time_stop"])
    trade_dfs[cfg["name"]] = tdf
    if tdf.empty:
        continue
    
    total_t = len(tdf)
    wins = tdf[tdf["r_return"] > 0]
    losses = tdf[tdf["r_return"] < 0]
    win_rate = (len(wins) / total_t) * 100.0 if total_t > 0 else 0
    
    gross_w = wins["r_return"].sum()
    gross_l = abs(losses["r_return"].sum())
    pf = (gross_w / gross_l) if gross_l > 0 else np.inf
    
    avg_win_r = wins["r_return"].mean() if len(wins) > 0 else 0
    avg_loss_r = abs(losses["r_return"].mean()) if len(losses) > 0 else 1.0
    exp_r = tdf["r_return"].mean()
    
    # Kelly Criterion: f* = (p * b - q) / b where b = avg_win / avg_loss, p = win_rate, q = 1 - p
    b = avg_win_r / avg_loss_r if avg_loss_r > 0 else 0
    p = win_rate / 100.0
    q = 1.0 - p
    kelly_f = (p * b - q) / b if b > 0 else 0
    
    results_summary.append({
        "name": cfg["name"],
        "trades": total_t,
        "win_rate": win_rate,
        "pf": pf,
        "avg_win_r": avg_win_r,
        "exp_r": exp_r,
        "kelly_f": kelly_f
    })
    
    print(f"{cfg['name']:<32} | {total_t:<7} | {win_rate:5.1f}% | {pf:5.2f} | {avg_win_r:6.2f}R   | {exp_r:+6.2f}R | {kelly_f*100:6.1f}%")

# -------------------------------------------------------------------------
# PART 2: THEORETICAL MAXIMUM GROWTH SIMULATION ($100 Starting Capital)
# -------------------------------------------------------------------------
print("\n" + "=" * 95)
print("THEORETICAL MAXIMUM COMPOUNDED ACCOUNT GROWTH FROM $100")
print("=" * 95)

# Simulate optimal compounding for each strategy at Kelly optimal, 1/2 Kelly, and aggressive high leverage
for res in results_summary:
    name = res["name"]
    tdf = trade_dfs[name]
    if tdf.empty:
        continue
    
    print(f"\nTarget Model: {name} (Expectancy = {res['exp_r']:+.2f}R, Kelly f* = {res['kelly_f']*100:.1f}%)")
    print(f"{'Compounding Scheme':<30} | {'Risk / Trade':<14} | {'Final Balance ($)':<20} | {'Return (%)':<15} | {'Max DD (%)'}")
    print("-" * 95)
    
    for scheme, risk_mult in [
        ("Conservative (1.5% Risk)", 0.015),
        ("Half-Kelly (Institutional Peak)", max(0.02, res["kelly_f"] * 0.5)),
        ("Full-Kelly (Theoretical Peak)", max(0.04, res["kelly_f"])),
        ("Aggressive High-RR Scalp (15%)", 0.15),
        ("Max Aggressive (20% Risk)", 0.20)
    ]:
        eq = 100.0
        pk = 100.0
        mdd = 0.0
        blown = False
        
        for _, row in tdf.iterrows():
            r_ret = row["r_return"]
            dollar_risk = eq * risk_mult
            trade_pnl = dollar_risk * r_ret
            
            if eq + trade_pnl <= 5.0:
                blown = True
                eq = 0.0
                mdd = -100.0
                break
                
            eq += trade_pnl
            pk = max(pk, eq)
            dd = (eq - pk) / pk * 100.0
            mdd = min(mdd, dd)
            
        if blown:
            print(f"{scheme:<30} | {risk_mult*100:5.1f}%        | {'$0.00 (LIQUIDATED)':<20} | {'-100.0%':<15} | -100.0%")
        else:
            print(f"{scheme:<30} | {risk_mult*100:5.1f}%        | ${eq:14.2f}{'':<5} | {((eq-100.0)/100.0)*100:+12.1f}% | {mdd:8.1f}%")

print("=" * 95)
