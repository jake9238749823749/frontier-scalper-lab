import numpy as np
import pandas as pd
from typing import Dict, List, Any, Callable
from .execution import BacktestEngine, ExecutionConfig, Trade
from .metrics import QuantMetrics

class StressTester:
    """
    Tools for falsification testing, parameter robustness, cost sensitivity, and Monte Carlo verification.
    """
    @staticmethod
    def cost_sensitivity_analysis(
        df: pd.DataFrame,
        signal_generator: Callable[[pd.DataFrame, Dict[str, Any]], pd.Series],
        base_params: Dict[str, Any],
        cost_scenarios: List[Dict[str, float]] = None
    ) -> pd.DataFrame:
        """
        Evaluate strategy under escalating transaction friction (spread, slippage, commission).
        """
        if cost_scenarios is None:
            cost_scenarios = [
                {"name": "Zero Friction (Theoretical)", "comm": 0.0, "spread": 0.0, "slip": 0.0},
                {"name": "Low Friction (Institutional)", "comm": 0.0001, "spread": 0.0001, "slip": 0.0001},
                {"name": "Base Realistic Friction", "comm": 0.0005, "spread": 0.0002, "slip": 0.0003},
                {"name": "Elevated Friction / Illiquid", "comm": 0.0010, "spread": 0.0005, "slip": 0.0008},
                {"name": "Severe Stress (Extreme)", "comm": 0.0020, "spread": 0.0010, "slip": 0.0015}
            ]

        results = []
        for s in cost_scenarios:
            cfg = ExecutionConfig(
                commission_pct=s["comm"],
                spread_pct=s["spread"],
                slippage_pct=s["slip"]
            )
            signals = signal_generator(df, base_params)
            engine = BacktestEngine(config=cfg)
            equity_df, trades = engine.run(
                df, signals,
                stop_loss_pct=base_params.get("stop_loss_pct"),
                take_profit_pct=base_params.get("take_profit_pct")
            )
            m = QuantMetrics.calculate(equity_df, trades)
            results.append({
                "Scenario": s["name"],
                "Total Friction (bps)": (s["comm"] + s["spread"] + s["slip"]) * 10_000,
                "Net Return (%)": round(m["net_return_pct"], 2),
                "CAGR (%)": round(m["cagr_pct"], 2),
                "Sharpe": round(m["sharpe_ratio"], 2),
                "Profit Factor": round(m["profit_factor"], 2),
                "Max DD (%)": round(m["max_drawdown_pct"], 2),
                "Total Trades": m["total_trades"],
                "Fees Paid ($)": round(m["total_fees_paid"], 2)
            })

        return pd.DataFrame(results)

    @staticmethod
    def monte_carlo_trade_shuffle(trades: List[Trade], simulations: int = 1000, initial_capital: float = 100_000.0) -> Dict[str, float]:
        """
        Shuffles the sequence of trade PnLs to evaluate path dependency and maximum drawdown risk distribution.
        """
        if not trades:
            return {}

        pnls = np.array([t.net_pnl for t in trades if not t.is_open])
        if len(pnls) < 5:
            return {"note": "Too few trades for meaningful Monte Carlo."}

        max_drawdowns = []
        final_equities = []

        for _ in range(simulations):
            shuffled = np.random.permutation(pnls)
            eq_curve = initial_capital + np.cumsum(shuffled)
            peaks = np.maximum.accumulate(eq_curve)
            dds = (eq_curve - peaks) / peaks
            max_drawdowns.append(np.min(dds) * 100.0)
            final_equities.append(eq_curve[-1])

        return {
            "mc_simulations": simulations,
            "mc_median_max_dd_pct": float(np.median(max_drawdowns)),
            "mc_95th_pct_worst_dd_pct": float(np.percentile(max_drawdowns, 5)), # worst 5%
            "mc_99th_pct_worst_dd_pct": float(np.percentile(max_drawdowns, 1)),
            "mc_prob_ruin_or_50pct_loss": float(np.mean(np.array(max_drawdowns) <= -50.0) * 100.0)
        }
