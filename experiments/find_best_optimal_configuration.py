import os
import itertools
import numpy as np
import pandas as pd
from engine.data_engine import RobustDataEngine

# Load datasets
assets = ["GBPUSD=X", "EURUSD=X", "BTC-USD"]
data_dict = {}
for a in assets:
    data_dict[a] = RobustDataEngine.get_h4_data(symbol=a, lookback_days=720)

print("=" * 95)
print("COMPREHENSIVE OPTIMIZATION & PARAMETER GRID SEARCH (MSRE-v1)")
print("=" * 95)

def evaluate_configuration(
    df,
    pip_size=0.0001,
    macro_window=30,
    eff_fade=0.32,
    phi_thresh=0.22,
    p_bridge_thresh=0.30,
    sl_buffer_pips=8.0,
    tp_mode="4.0R",         # "midpoint", "3.0R", "4.0R", "5.0R"
    time_stop_bars=36,
    spread_pips=1.2,
    slippage_pips=0.3
):
    eps = 1e-8
    df = df.copy()
    
    # 1. Macro Profile
    df['macro_high'] = df['high'].shift(1).rolling(macro_window).max()
    df['macro_low'] = df['low'].shift(1).rolling(macro_window).min()
    df['macro_mid'] = (df['macro_high'] + df['macro_low']) / 2.0

    # 2. Kaufman Macro Efficiency
    net_d = (df['close'].shift(1) - df['close'].shift(macro_window)).abs()
    gross_p = (df['close'].shift(1) - df['close'].shift(2)).abs().rolling(macro_window - 1).sum()
    df['macro_eff'] = net_d / (gross_p + eps)

    # 3. Normalized Dissipation
    hl_safe = np.where(df['high'] - df['low'] == 0, eps, df['high'] - df['low'])
    df['phi_dissipation'] = (df['close'] - df['open']).abs() / hl_safe

    # 4. Brownian Bridge
    num_h = (df['open'] - df['low']) * (df['high'] - df['close'])
    den_h = num_h + (df['high'] - df['open']) * (df['close'] - df['low']) + eps
    df['p_high_first'] = np.clip(num_h / den_h, 0.0, 1.0)

    # Signals
    sig_l = (
        (df['macro_eff'] < eff_fade) &
        (df['low'] < df['macro_low']) &
        (df['close'] > df['macro_low']) &
        (df['phi_dissipation'] <= phi_thresh) &
        (df['p_high_first'] <= p_bridge_thresh)
    ).values

    sig_s = (
        (df['macro_eff'] < eff_fade) &
        (df['high'] > df['macro_high']) &
        (df['close'] < df['macro_high']) &
        (df['phi_dissipation'] <= phi_thresh) &
        (df['p_high_first'] >= (1.0 - p_bridge_thresh))
    ).values

    n = len(df)
    times = df.index
    opens = df['open'].values
    highs = df['high'].values
    lows = df['low'].values
    closes = df['close'].values
    macro_mids = df['macro_mid'].values
    friction = (0.5 * spread_pips + slippage_pips) * pip_size

    trades = []
    in_trade = False
    entry_p, sl_p, tp_p, direction = 0, 0, 0, ""
    entry_t, entry_idx = None, 0
    risk_dist = 0

    for t in range(1, n):
        o, h, l, c = opens[t], highs[t], lows[t], closes[t]

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
                reason = "SL Priority"
            elif hit_sl:
                exit_triggered = True
                raw_exit_p = sl_p
                reason = "SL"
            elif hit_tp:
                exit_triggered = True
                raw_exit_p = tp_p
                reason = "TP"
            elif hold_bars >= time_stop_bars:
                exit_triggered = True
                raw_exit_p = c
                reason = "Time Stop"

            if exit_triggered:
                eff_exit_p = raw_exit_p - friction if pos_dir == 1 else raw_exit_p + friction
                gross_diff = (eff_exit_p - entry_p) if pos_dir == 1 else (entry_p - eff_exit_p)
                r_ret = gross_diff / (risk_dist + 1e-9)
                trades.append(r_ret)
                in_trade = False

        if not in_trade:
            prev = t - 1
            if sig_l[prev]:
                in_trade = True
                direction = "long"
                entry_idx = t
                entry_t = times[t]
                entry_p = o + friction
                sl_p = lows[prev] - (sl_buffer_pips * pip_size)
                risk_dist = abs(entry_p - sl_p)
                if tp_mode == "midpoint":
                    tp_p = macro_mids[prev]
                else:
                    mult = float(tp_mode.replace("R", ""))
                    tp_p = entry_p + (mult * risk_dist)

            elif sig_s[prev]:
                in_trade = True
                direction = "short"
                entry_idx = t
                entry_t = times[t]
                entry_p = o - friction
                sl_p = highs[prev] + (sl_buffer_pips * pip_size)
                risk_dist = abs(entry_p - sl_p)
                if tp_mode == "midpoint":
                    tp_p = macro_mids[prev]
                else:
                    mult = float(tp_mode.replace("R", ""))
                    tp_p = entry_p - (mult * risk_dist)

    if not trades:
        return {"trades": 0, "pf": 0.0, "win_rate": 0.0, "exp_r": 0.0, "final_100_equity": 100.0, "max_dd": 0.0}

    r_arr = np.array(trades)
    total_t = len(r_arr)
    wins = r_arr[r_arr > 0]
    losses = r_arr[r_arr < 0]
    win_rate = len(wins) / total_t * 100.0
    gw = wins.sum()
    gl = abs(losses.sum())
    pf = (gw / gl) if gl > 0 else 99.0
    exp_r = r_arr.mean()

    # Simulate $100 starting capital with 10% risk compounding
    eq = 100.0
    pk = 100.0
    mdd = 0.0
    for r in r_arr:
        dollar_risk = eq * 0.10
        trade_pnl = dollar_risk * r
        eq += trade_pnl
        if eq <= 5.0:
            eq = 0.0
            mdd = -100.0
            break
        pk = max(pk, eq)
        mdd = min(mdd, (eq - pk) / pk * 100.0)

    return {
        "trades": total_t,
        "win_rate": win_rate,
        "pf": pf,
        "exp_r": exp_r,
        "final_100_equity": eq,
        "max_dd": mdd
    }

# Parameter grid
grid = {
    "macro_window": [20, 30, 40],
    "eff_fade": [0.28, 0.32, 0.36],
    "phi_thresh": [0.20, 0.22, 0.25],
    "p_bridge_thresh": [0.30, 0.35],
    "sl_buffer_pips": [6.0, 8.0, 10.0],
    "tp_mode": ["midpoint", "3.0R", "4.0R", "4.5R"],
    "time_stop_bars": [18, 36, 48]
}

keys, values = zip(*grid.items())
combinations = [dict(zip(keys, v)) for v in itertools.product(*values)]

print(f"Testing {len(combinations)} total parameter combinations on GBPUSD=X...")

results = []
for p in combinations:
    metrics = evaluate_configuration(
        data_dict["GBPUSD=X"],
        pip_size=0.0001,
        macro_window=p["macro_window"],
        eff_fade=p["eff_fade"],
        phi_thresh=p["phi_thresh"],
        p_bridge_thresh=p["p_bridge_thresh"],
        sl_buffer_pips=p["sl_buffer_pips"],
        tp_mode=p["tp_mode"],
        time_stop_bars=p["time_stop_bars"]
    )
    if metrics["trades"] >= 15:
        results.append({**p, **metrics})

df_res = pd.DataFrame(results)
# Rank by composite score: Expectancy (R) * Profit Factor * sqrt(Trades)
df_res["composite_score"] = df_res["exp_r"] * df_res["pf"] * np.sqrt(df_res["trades"])
df_res = df_res.sort_values("composite_score", ascending=False)

print(f"\nTop 5 Optimal Parameter Sets:")
top_cols = ["macro_window", "eff_fade", "phi_thresh", "tp_mode", "sl_buffer_pips", "time_stop_bars", "trades", "win_rate", "pf", "exp_r", "final_100_equity", "max_dd"]
print(df_res[top_cols].head(5).to_string(index=False))

best_cfg = df_res.iloc[0].to_dict()
print("\n" + "=" * 95)
print("SINGLE BEST OPTIMAL CONFIGURATION DETAILS")
print("=" * 95)
for k, v in best_cfg.items():
    print(f"{k:<25}: {v}")

