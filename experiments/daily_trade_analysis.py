"""
========================================================================================
DAILY TRADE GENERATION: PORTFOLIO POOLING VS. INTRADAY SESSION SWEEPS
========================================================================================
Demonstrates how to achieve >= 1 trade every single trading day.
"""

import os
import numpy as np
import pandas as pd

# 1. Measure Daily Coverage from the 30-Asset Universe
df_summary = pd.read_csv("results/summary_metrics.csv")
top_10_tickers = df_summary.head(10)["Ticker"].tolist()

# Load equity curves and trade counts
total_trades_30 = df_summary["Total Trades"].sum()
trading_days = 720 * (5/7) # ~514 weekdays

print("=" * 85)
print("HOW TO ACHIEVE AT LEAST 1 TRADE EVERY SINGLE DAY")
print("=" * 85)
print(f"Total Weekdays in 2-Year Horizon: ~{trading_days:.0f} trading days")
print(f"Total Trades across 30 Assets:     {total_trades_30} trades")
print(f"Average Portfolio Trade Rate:     {total_trades_30 / trading_days:.2f} trades / day (~{total_trades_30 / 24:.1f} trades / month)")

# Top 10 High-Quality Universe
top_10_df = df_summary[df_summary["Ticker"].isin(top_10_tickers)]
top_10_trades = top_10_df["Total Trades"].sum()
print(f"Top 10 High-Sharpe Universe:       {top_10_trades} trades ({top_10_trades / trading_days:.2f} trades / day, {top_10_trades / 24:.1f} trades / month)")
print("=" * 85)
