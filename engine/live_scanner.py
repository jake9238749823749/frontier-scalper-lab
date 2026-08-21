"""
========================================================================================
MSRE-v1 LIVE OPPORTUNITY SCANNER (TOP-10 CHAMPION UNIVERSE)
========================================================================================
Scans the latest 4-Hour bars across the 10 champions to detect active triggers,
pending setups near weekly extremes, and immediate trade recommendations.
"""

import os
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from engine.data_engine import RobustDataEngine

TOP10_CHAMPIONS = [
    {"symbol": "NVDA",     "name": "NVIDIA Corporation",          "class": "Single Equities", "tick": 0.01,   "friction_type": "bps",  "friction_val": 2.5},
    {"symbol": "GC=F",     "name": "Gold Futures",                "class": "Metals",          "tick": 0.10,   "friction_type": "bps",  "friction_val": 2.0},
    {"symbol": "AUDUSD=X", "name": "Australian Dollar / US Dollar","class": "Forex",          "tick": 0.0001, "friction_type": "pips", "friction_val": 1.4},
    {"symbol": "BTC-USD",  "name": "Bitcoin / US Dollar",         "class": "Crypto",          "tick": 0.01,   "friction_type": "bps",  "friction_val": 6.0},
    {"symbol": "GBPJPY=X", "name": "British Pound / Japanese Yen", "class": "Forex",          "tick": 0.01,   "friction_type": "pips", "friction_val": 2.2},
    {"symbol": "NG=F",     "name": "Natural Gas Futures",         "class": "Energy",         "tick": 0.001,  "friction_type": "bps",  "friction_val": 5.0},
    {"symbol": "MSFT",     "name": "Microsoft Corporation",       "class": "Single Equities", "tick": 0.01,   "friction_type": "bps",  "friction_val": 2.0},
    {"symbol": "AMZN",     "name": "Amazon.com Inc.",             "class": "Single Equities", "tick": 0.01,   "friction_type": "bps",  "friction_val": 2.0},
    {"symbol": "EURJPY=X", "name": "Euro / Japanese Yen",         "class": "Forex",          "tick": 0.01,   "friction_type": "pips", "friction_val": 1.8},
    {"symbol": "^N225",    "name": "Nikkei 225 Index",            "class": "Indices / ETFs",  "tick": 1.00,   "friction_type": "bps",  "friction_val": 3.0}
]

def scan_latest_market_opportunities(universe: list[dict] = TOP10_CHAMPIONS) -> pd.DataFrame:
    eps = 1e-8
    macro_window = 40
    scanner_results = []

    for cfg in universe:
        sym = cfg["symbol"]
        df = RobustDataEngine.get_h4_data(symbol=sym, lookback_days=720)
        
        # Calculate features
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

        # Get latest bar
        last_row = df.iloc[-1]
        last_time = df.index[-1]

        # Check conditions
        is_range = last_row['macro_eff'] < 0.32
        is_sweep_l = (last_row['low'] < last_row['macro_low']) and (last_row['close'] > last_row['macro_low'])
        is_sweep_s = (last_row['high'] > last_row['macro_high']) and (last_row['close'] < last_row['macro_high'])
        is_absorption = last_row['phi_dissipation'] <= 0.20
        is_bridge_l = last_row['p_high_first'] <= 0.30
        is_bridge_s = last_row['p_high_first'] >= 0.70

        # Distance to macro extremes
        dist_to_low_pct = ((last_row['close'] - last_row['macro_low']) / last_row['close']) * 100.0
        dist_to_high_pct = ((last_row['macro_high'] - last_row['close']) / last_row['close']) * 100.0

        if is_range and is_sweep_l and is_absorption and is_bridge_l:
            signal_status = "TRIGGER: BUY (Long Sweep Absorption)"
            action = "ENTER LONG AT NEXT OPEN"
        elif is_range and is_sweep_s and is_absorption and is_bridge_s:
            signal_status = "TRIGGER: SELL (Short Sweep Absorption)"
            action = "ENTER SHORT AT NEXT OPEN"
        elif abs(dist_to_low_pct) < 1.0 or abs(dist_to_high_pct) < 1.0:
            signal_status = "WATCHLIST: Near Macro Extreme (<1.0%)"
            action = "Monitor for Sweep Wick"
        elif is_range:
            signal_status = "RANGING: Macro Efficiency Low"
            action = "Waiting for Sweep"
        else:
            signal_status = "TRENDING: Filter Active"
            action = "No Trade"

        scanner_results.append({
            "Ticker": sym,
            "Asset Class": cfg["class"],
            "Latest Bar (UTC)": str(last_time)[:16],
            "Last Price": round(last_row['close'], 4),
            "Macro Low": round(last_row['macro_low'], 4),
            "Macro High": round(last_row['macro_high'], 4),
            "Efficiency (E_40)": round(last_row['macro_eff'], 3),
            "Body/Range (Phi)": round(last_row['phi_dissipation'], 2),
            "Signal Status": signal_status,
            "Recommended Action": action
        })

    return pd.DataFrame(scanner_results)

if __name__ == "__main__":
    print("=" * 105)
    print("MSRE-v1: LIVE OPPORTUNITY SCANNER (TOP-10 CHAMPION UNIVERSE)")
    print("=" * 105)
    df_scan = scan_latest_market_opportunities()
    print(df_scan[["Ticker", "Last Price", "Macro Low", "Macro High", "Efficiency (E_40)", "Body/Range (Phi)", "Signal Status"]].to_string(index=False))
    print("=" * 105)
