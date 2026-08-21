"""
========================================================================================
SCANNER: FIND THE MOST RECENT TRADE TRIGGER ACROSS ALL ASSETS
========================================================================================
Scans backwards bar-by-bar from the latest available timestamp across the 30-asset
universe to identify the exact last company / instrument that triggered an entry.
"""

import os
import pandas as pd
import numpy as np
from engine.data_engine import RobustDataEngine
from experiments.run_30_asset_study import UNIVERSE

def find_most_recent_trade_trigger():
    eps = 1e-8
    macro_window = 40
    all_signals = []

    print("=" * 95)
    print("SCANNING FOR THE MOST RECENT TRADE TRIGGER ACROSS THE 30-ASSET UNIVERSE...")
    print("=" * 95)

    for cfg in UNIVERSE:
        sym = cfg["symbol"]
        df = RobustDataEngine.get_h4_data(symbol=sym, lookback_days=720)
        df = df.copy()

        df['macro_high'] = df['high'].shift(1).rolling(macro_window).max()
        df['macro_low'] = df['low'].shift(1).rolling(macro_window).min()
        
        net_d = (df['close'].shift(1) - df['close'].shift(macro_window)).abs()
        gross_p = (df['close'].shift(1) - df['close'].shift(2)).abs().rolling(macro_window - 1).sum()
        df['macro_eff'] = net_d / (gross_p + eps)

        hl_safe = np.where(df['high'] - df['low'] == 0, eps, df['high'] - df['low'])
        df['phi_dissipation'] = (df['close'] - df['open']).abs() / hl_safe

        num_h = (df['open'] - df['low']) * (df['high'] - df['close'])
        den_h = num_h + (df['high'] - df['open']) * (df['close'] - df['low']) + eps
        df['p_high_first'] = np.clip(num_h / den_h, 0.0, 1.0)

        # Long Signal
        sig_l_mask = (
            (df['macro_eff'] < 0.32) &
            (df['low'] < df['macro_low']) &
            (df['close'] > df['macro_low']) &
            (df['phi_dissipation'] <= 0.20) &
            (df['p_high_first'] <= 0.30)
        )

        # Short Signal
        sig_s_mask = (
            (df['macro_eff'] < 0.32) &
            (df['high'] > df['macro_high']) &
            (df['close'] < df['macro_high']) &
            (df['phi_dissipation'] <= 0.20) &
            (df['p_high_first'] >= 0.70)
        )

        # Extract trigger bars
        for idx in df[sig_l_mask].index:
            loc = df.index.get_loc(idx)
            if loc + 1 < len(df):
                fill_bar = df.iloc[loc + 1]
                fill_time = df.index[loc + 1]
                sweep_bar = df.loc[idx]
                tick = cfg["tick"]
                
                # Friction
                if cfg["friction_type"] == "pips":
                    bar_friction = cfg["friction_val"] * tick
                else:
                    bar_friction = fill_bar['open'] * (cfg["friction_val"] * 0.0001)

                entry_p = fill_bar['open'] + bar_friction
                sl = sweep_bar['low'] - (6.0 * tick)
                risk_dist = abs(entry_p - sl)
                tp = entry_p + (4.5 * risk_dist)

                all_signals.append({
                    "Signal Time (Completed Bar)": idx,
                    "Execution Time (Open Fill)": fill_time,
                    "Ticker": sym,
                    "Asset Name": cfg["name"],
                    "Asset Class": cfg["class"],
                    "Direction": "LONG",
                    "Sweep Price": sweep_bar['low'],
                    "Macro Level": sweep_bar['macro_low'],
                    "Efficiency (E_40)": round(sweep_bar['macro_eff'], 3),
                    "Body/Range (Phi)": round(sweep_bar['phi_dissipation'], 3),
                    "Entry Price": round(entry_p, 4),
                    "Stop Loss": round(sl, 4),
                    "Take Profit": round(tp, 4),
                    "Risk Distance": round(risk_dist, 4)
                })

        for idx in df[sig_s_mask].index:
            loc = df.index.get_loc(idx)
            if loc + 1 < len(df):
                fill_bar = df.iloc[loc + 1]
                fill_time = df.index[loc + 1]
                sweep_bar = df.loc[idx]
                tick = cfg["tick"]

                if cfg["friction_type"] == "pips":
                    bar_friction = cfg["friction_val"] * tick
                else:
                    bar_friction = fill_bar['open'] * (cfg["friction_val"] * 0.0001)

                entry_p = fill_bar['open'] - bar_friction
                sl = sweep_bar['high'] + (6.0 * tick)
                risk_dist = abs(entry_p - sl)
                tp = entry_p - (4.5 * risk_dist)

                all_signals.append({
                    "Signal Time (Completed Bar)": idx,
                    "Execution Time (Open Fill)": fill_time,
                    "Ticker": sym,
                    "Asset Name": cfg["name"],
                    "Asset Class": cfg["class"],
                    "Direction": "SHORT",
                    "Sweep Price": sweep_bar['high'],
                    "Macro Level": sweep_bar['macro_high'],
                    "Efficiency (E_40)": round(sweep_bar['macro_eff'], 3),
                    "Body/Range (Phi)": round(sweep_bar['phi_dissipation'], 3),
                    "Entry Price": round(entry_p, 4),
                    "Stop Loss": round(sl, 4),
                    "Take Profit": round(tp, 4),
                    "Risk Distance": round(risk_dist, 4)
                })

    df_all_sig = pd.DataFrame(all_signals)
    df_all_sig = df_all_sig.sort_values("Execution Time (Open Fill)", ascending=False).reset_index(drop=True)
    return df_all_sig

if __name__ == "__main__":
    df_triggers = find_most_recent_trade_trigger()
    
    print("\n" + "=" * 95)
    print("CHRONOLOGICAL AUDIT: TOP 10 MOST RECENT ACTIVATED TRADES ACROSS THE UNIVERSE")
    print("=" * 95)
    cols = ["Execution Time (Open Fill)", "Ticker", "Asset Name", "Direction", "Entry Price", "Stop Loss", "Take Profit", "Efficiency (E_40)", "Body/Range (Phi)"]
    print(df_triggers[cols].head(10).to_string(index=False))

    latest_trade = df_triggers.iloc[0]
    print("\n" + "=" * 95)
    print(f"THE SINGLE MOST RECENT ACTIVATED TRADE: {latest_trade['Ticker']} ({latest_trade['Asset Name']})")
    print("=" * 95)
    for k, v in latest_trade.items():
        print(f"{k:<30}: {v}")
