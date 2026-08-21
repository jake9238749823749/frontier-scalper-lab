import pytest
import numpy as np
import pandas as pd
from engine.execution import BacktestEngine, ExecutionConfig
from engine.metrics import QuantMetrics
from engine.stress import StressTester

def create_synthetic_bars(n=100, trend=0.001, noise=0.01):
    dates = pd.date_range("2023-01-01", periods=n, freq="D")
    prices = [100.0]
    for i in range(1, n):
        ret = trend + np.random.normal(0, noise)
        prices.append(prices[-1] * (1.0 + ret))
    
    prices = np.array(prices)
    opens = prices * (1.0 + np.random.uniform(-0.002, 0.002, n))
    highs = np.maximum(opens, prices) * (1.0 + np.random.uniform(0.001, 0.01, n))
    lows = np.minimum(opens, prices) * (1.0 - np.random.uniform(0.001, 0.01, n))
    closes = prices
    volume = np.random.uniform(1000, 5000, n)
    
    df = pd.DataFrame({
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "adj_close": closes,
        "volume": volume
    }, index=dates)
    return df

def test_causality_and_no_lookahead():
    df = create_synthetic_bars(50)
    # Simple signal: buy if close > open, flat otherwise
    signals = (df["close"] > df["open"]).astype(int)
    
    engine = BacktestEngine(ExecutionConfig(commission_pct=0.0, spread_pct=0.0, slippage_pct=0.0))
    equity_df, trades = engine.run(df, signals)
    
    # Check that trades enter on bar t when signal was at t-1
    for t in trades:
        entry_idx = df.index.get_loc(t.entry_time)
        if entry_idx > 0:
            prev_time = df.index[entry_idx - 1]
            assert signals.loc[prev_time] == 1, "Trade entered without previous bar signal trigger"

def test_metrics_calculation():
    df = create_synthetic_bars(100)
    signals = pd.Series(1, index=df.index)  # Buy and hold
    engine = BacktestEngine()
    equity_df, trades = engine.run(df, signals)
    metrics = QuantMetrics.calculate(equity_df, trades)
    
    assert "sharpe_ratio" in metrics
    assert "max_drawdown_pct" in metrics
    assert "profit_factor" in metrics
    assert metrics["total_trades"] >= 1

if __name__ == "__main__":
    test_causality_and_no_lookahead()
    test_metrics_calculation()
    print("All engine tests passed successfully!")
