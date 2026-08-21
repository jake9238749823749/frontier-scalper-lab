from engine.data_engine import RobustDataEngine
import pandas as pd
import numpy as np

df = RobustDataEngine.get_h4_data(symbol="TSLA", lookback_days=720, force_refresh=True)
last_bar = df.iloc[-1]
macro_low = df["low"].iloc[-41:-1].min()
macro_high = df["high"].iloc[-41:-1].max()

print("=== TSLA Live-Calibrated Pricing ($362 Baseline) ===")
print(f"Current Price Level:          ${last_bar['close']:.2f}")
print(f"40-Bar Macro Low:             ${macro_low:.2f}")
print(f"40-Bar Macro High:            ${macro_high:.2f}")
print(f"Recent Range (High - Low):    ${macro_high - macro_low:.2f}")
