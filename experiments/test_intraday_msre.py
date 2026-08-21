"""
========================================================================================
MSRE-INTRADAY (SESSION SWEEP SCALPER): 15-MINUTE DAILY EXECUTION ENGINE
========================================================================================
Adapts MSRE-v1 to 15-minute execution anchored to Asian session & rolling 6-hour extremes
to guarantee active daily trading (1-3 trades per day).
"""

import os
import numpy as np
import pandas as pd
from datetime import datetime, timezone

def generate_synthetic_15m(bars=10000, s0=1.2850, annual_vol=0.09, seed=101):
    np.random.seed(seed)
    dt = 15.0 / (252.0 * 24.0 * 60.0) # 15 min
    v = np.zeros(bars)
    v[0] = 0.0081
    kappa, theta, xi = 4.0, 0.0081, 0.25
    
    for i in range(1, bars):
        dv = kappa * (theta - v[i-1]) * dt + xi * np.sqrt(max(v[i-1], 1e-4)) * np.sqrt(dt) * np.random.randn()
        v[i] = max(v[i-1] + dv, 0.001)

    returns = np.zeros(bars)
    for i in range(1, bars):
        drift = 0.0
        diffusion = np.sqrt(v[i]) * np.sqrt(dt) * np.random.randn()
        # Intraday spikes / news jumps
        jump = -0.0025 if (i % 80 == 0) else (0.0025 if (i % 80 == 1) else 0.0)
        returns[i] = drift + diffusion + jump

    closes = s0 * np.exp(np.cumsum(returns))
    spread_noise = closes * (annual_vol / np.sqrt(252 * 24 * 4)) * 0.4
    highs = closes + np.abs(np.random.normal(0, spread_noise, bars))
    lows = closes - np.abs(np.random.normal(0, spread_noise, bars))
    opens = np.roll(closes, 1)
    opens[0] = s0

    highs = np.maximum(highs, np.maximum(opens, closes))
    lows = np.minimum(lows, np.minimum(opens, closes))
    volumes = np.random.lognormal(mean=8.0, sigma=0.5, size=bars)

    idx = pd.date_range(end=datetime.now(timezone.utc), periods=bars, freq='15min')
    df = pd.DataFrame({'open': opens, 'high': highs, 'low': lows, 'close': closes, 'volume': volumes}, index=idx)
    return df.round(5)

def run_intraday_msre(df, pip_size=0.0001, spread_pips=1.0, slippage_pips=0.2):
    eps = 1e-8
    df = df.copy()
    
    # 1. Session & Intraday Anchors
    # W = 24 bars (6 hours rolling session window: London/NY sweeps of Asian/London extremes)
    session_window = 24
    df['session_high'] = df['high'].shift(1).rolling(session_window).max()
    df['session_low'] = df['low'].shift(1).rolling(session_window).min()
    
    # Kaufman Efficiency on 24-bar window
    net_d = (df['close'].shift(1) - df['close'].shift(session_window)).abs()
    gross_p = (df['close'].shift(1) - df['close'].shift(2)).abs().rolling(session_window - 1).sum()
    df['session_eff'] = net_d / (gross_p + eps)

    # 15M Absorption Wick (Body <= 25% of bar)
    hl = np.where(df['high'] - df['low'] == 0, eps, df['high'] - df['low'])
    df['phi_dissipation'] = (df['close'] - df['open']).abs() / hl

    # Brownian Bridge
    num_h = (df['open'] - df['low']) * (df['high'] - df['close'])
    den_h = num_h + (df['high'] - df['open']) * (df['close'] - df['low']) + eps
    df['p_high_first'] = np.clip(num_h / den_h, 0.0, 1.0)

    # Session Time Filter (Focus on London 07:00-11:00 UTC and NY 13:00-17:00 UTC)
    hours = df.index.hour
    active_session = ((hours >= 7) & (hours <= 11)) | ((hours >= 13) & (hours <= 17))

    # Signals
    df['sig_long'] = (
        active_session &
        (df['session_eff'] < 0.38) &
        (df['low'] < df['session_low']) &
        (df['close'] > df['session_low']) &
        (df['phi_dissipation'] <= 0.25) &
        (df['p_high_first'] <= 0.35)
    )

    df['sig_short'] = (
        active_session &
        (df['session_eff'] < 0.38) &
        (df['high'] > df['session_high']) &
        (df['close'] < df['session_high']) &
        (df['phi_dissipation'] <= 0.25) &
        (df['p_high_first'] >= 0.65)
    )

    # Execution Simulation
    n = len(df)
    times = df.index
    opens = df['open'].values
    highs = df['high'].values
    lows = df['low'].values
    closes = df['close'].values
    sig_l = df['sig_long'].values
    sig_s = df['sig_short'].values

    friction = (0.5 * spread_pips + slippage_pips) * pip_size
    initial_equity = 100_000.0
    equity = initial_equity
    trades = []
    in_trade = False
    entry_p, sl_p, tp_p, direction = 0, 0, 0, ""
    entry_t, entry_idx = None, 0
    size, risk_dist, dollar_risk = 0, 0, 0

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
                reason = "Stop Loss (Priority)"
            elif hit_sl:
                exit_triggered = True
                raw_exit_p = sl_p
                reason = "Stop Loss"
            elif hit_tp:
                exit_triggered = True
                raw_exit_p = tp_p
                reason = "Take Profit (3.0R)"
            elif hold_bars >= 16: # 4-hour max intraday holding period
                exit_triggered = True
                raw_exit_p = c
                reason = "Intraday Time Stop (4 Hours)"

            if exit_triggered:
                eff_exit_p = raw_exit_p - friction if pos_dir == 1 else raw_exit_p + friction
                gross_diff = (eff_exit_p - entry_p) if pos_dir == 1 else (entry_p - eff_exit_p)
                pnl = gross_diff * size
                equity += pnl
                r_ret = pnl / (dollar_risk + 1e-9)

                trades.append({
                    "trade_id": len(trades) + 1,
                    "entry_time": entry_t,
                    "exit_time": times[t],
                    "direction": direction,
                    "r_return": r_ret,
                    "pnl": pnl,
                    "holding_bars": hold_bars,
                    "date": entry_t.date()
                })
                in_trade = False

        if not in_trade:
            prev = t - 1
            if sig_l[prev]:
                in_trade = True
                direction = "long"
                entry_idx = t
                entry_t = times[t]
                entry_p = o + friction
                sl_p = lows[prev] - (3.0 * pip_size) # 3 pips SL buffer on 15M
                risk_dist = abs(entry_p - sl_p)
                tp_p = entry_p + (3.0 * risk_dist)   # 3.0R Target for intraday
                dollar_risk = equity * 0.015
                size = dollar_risk / (risk_dist + 1e-9)

            elif sig_s[prev]:
                in_trade = True
                direction = "short"
                entry_idx = t
                entry_t = times[t]
                entry_p = o - friction
                sl_p = highs[prev] + (3.0 * pip_size)
                risk_dist = abs(entry_p - sl_p)
                tp_p = entry_p - (3.0 * risk_dist)
                dollar_risk = equity * 0.015
                size = dollar_risk / (risk_dist + 1e-9)

    df_trades = pd.DataFrame(trades)
    return df_trades

# Run simulation over 120 days (~8,000 15M bars)
df_15m = generate_synthetic_15m(bars=11520, s0=1.2850, seed=42) # ~120 days of 15m data
trades = run_intraday_msre(df_15m)

total_trades = len(trades)
unique_trading_days = len(trades["date"].unique())
total_calendar_days = (df_15m.index[-1] - df_15m.index[0]).days
trading_days_total = total_calendar_days * (5/7) # ~approx weekdays

wins = trades[trades["r_return"] > 0]
losses = trades[trades["r_return"] < 0]
win_rate = len(wins) / total_trades * 100.0
gw = wins["pnl"].sum()
gl = abs(losses["pnl"].sum())
pf = gw / gl
exp_r = trades["r_return"].mean()

print("=" * 80)
print("MSRE-INTRADAY (15-MINUTE SESSION SWEEP SCALPER) - VERIFICATION")
print("=" * 80)
print(f"Evaluation Window:       {df_15m.index[0].strftime('%Y-%m-%d')} to {df_15m.index[-1].strftime('%Y-%m-%d')} ({total_calendar_days} calendar days / ~{trading_days_total:.0f} weekdays)")
print(f"Total Trades Taken:      {total_trades} trades")
print(f"Active Trading Days:     {unique_trading_days} days with at least 1 trade")
print(f"Daily Trade Frequency:   {total_trades / trading_days_total:.2f} trades / weekday")
print(f"Days With >= 1 Trade:    {(unique_trading_days / trading_days_total) * 100:.1f}% of all trading days")
print("-" * 80)
print(f"Win Rate:                {win_rate:.1f}%")
print(f"Profit Factor:           {pf:.2f}")
print(f"Net Expectancy:          {exp_r:+.2f}R per trade")
print(f"Average Holding Time:    {trades['holding_bars'].mean() * 15:.1f} minutes ({trades['holding_bars'].mean():.1f} bars)")
print("=" * 80)
