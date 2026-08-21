import pytest
import numpy as np
import pandas as pd
from engine.data_engine import RobustDataEngine
from engine.execution import BacktestEngine, ExecutionConfig
from engine.metrics import QuantMetrics
from engine.stress import StressTester

def test_robust_data_engine():
    # Test FX H4 extraction
    df_fx = RobustDataEngine.get_h4_data(symbol="GBPUSD=X", lookback_days=30)
    assert not df_fx.empty
    assert list(df_fx.columns) == ["open", "high", "low", "close", "volume"]
    assert (df_fx["high"] >= df_fx["low"]).all()
    assert (df_fx["high"] >= df_fx[["open", "close"]].min(axis=1)).all()
    assert (df_fx["low"] <= df_fx[["open", "close"]].max(axis=1)).all()
    assert (df_fx["volume"] > 0).all()

    # Test SPY
    df_spy = RobustDataEngine.get_h4_data(symbol="SPY", lookback_days=30)
    assert not df_spy.empty
    assert df_spy["close"].mean() > 100

def test_causality_and_no_lookahead():
    df = RobustDataEngine.get_h4_data(symbol="GBPUSD=X", lookback_days=100)
    # Simple signal: buy if close > open, flat otherwise
    signals = (df["close"] > df["open"]).astype(int)

    engine = BacktestEngine(ExecutionConfig(commission_pct=0.0001, spread_pct=0.0001, slippage_pct=0.0001))
    equity_df, trades = engine.run(df, signals)

    # Verify that trades enter on bar t when signal was at t-1
    for t in trades:
        entry_idx = df.index.get_loc(t.entry_time)
        if entry_idx > 0:
            prev_time = df.index[entry_idx - 1]
            assert signals.loc[prev_time] == 1, "Trade entered without previous bar signal trigger"

def test_metrics_and_stress():
    df = RobustDataEngine.get_h4_data(symbol="SPY", lookback_days=150)
    signals = pd.Series(1, index=df.index)  # Long bias
    engine = BacktestEngine()
    equity_df, trades = engine.run(df, signals, stop_loss_pct=0.02, take_profit_pct=0.04)
    metrics = QuantMetrics.calculate(equity_df, trades)

    assert "sharpe_ratio" in metrics
    assert "max_drawdown_pct" in metrics
    assert "profit_factor" in metrics
    assert metrics["total_trades"] >= 1

    # Test cost sensitivity
    def dummy_sig_gen(data, params):
        return pd.Series(1, index=data.index)

    stress_df = StressTester.cost_sensitivity_analysis(df, dummy_sig_gen, {"stop_loss_pct": 0.02, "take_profit_pct": 0.04})
    assert len(stress_df) == 5

if __name__ == "__main__":
    pytest.main(["-v", "tests/test_engine.py"])
