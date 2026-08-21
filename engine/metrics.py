import numpy as np
import pandas as pd
from typing import List, Dict, Any
from .execution import Trade

class QuantMetrics:
    """
    Computes comprehensive, institutional-grade quantitative trading performance metrics.
    """
    @staticmethod
    def calculate(
        equity_df: pd.DataFrame,
        trades: List[Trade],
        initial_capital: float = 100_000.0,
        risk_free_rate: float = 0.04,  # 4% annual risk-free rate
        periods_per_year: int = 252     # 252 for daily, ~6300 for 1h, etc.
    ) -> Dict[str, Any]:
        equity = equity_df["equity"].values
        drawdowns = equity_df["drawdown"].values

        if len(equity) < 2:
            return {"error": "Insufficient bars to compute metrics."}

        # Returns
        total_net_return = (equity[-1] - initial_capital) / initial_capital
        total_pnl = equity[-1] - initial_capital

        # Duration
        start_date = equity_df.index[0]
        end_date = equity_df.index[-1]
        days_span = max(1, (end_date - start_date).total_seconds() / 86400.0)
        years_span = days_span / 365.25

        if years_span > 0 and equity[-1] > 0:
            cagr = (equity[-1] / initial_capital) ** (1.0 / years_span) - 1.0
        else:
            cagr = -1.0 if equity[-1] <= 0 else 0.0

        # Bar returns
        bar_returns = pd.Series(equity).pct_change().dropna().values
        mean_ret = np.mean(bar_returns) if len(bar_returns) > 0 else 0.0
        std_ret = np.std(bar_returns, ddof=1) if len(bar_returns) > 1 else 1e-9

        # Annualized Sharpe
        rf_per_period = (1.0 + risk_free_rate) ** (1.0 / periods_per_year) - 1.0
        excess_returns = bar_returns - rf_per_period
        sharpe = (np.mean(excess_returns) / (np.std(excess_returns, ddof=1) + 1e-9)) * np.sqrt(periods_per_year) if len(excess_returns) > 1 else 0.0

        # Annualized Sortino
        downside_returns = excess_returns[excess_returns < 0]
        downside_std = np.std(downside_returns, ddof=1) if len(downside_returns) > 1 else 1e-9
        sortino = (np.mean(excess_returns) / (downside_std + 1e-9)) * np.sqrt(periods_per_year) if len(excess_returns) > 1 else 0.0

        # Max Drawdown
        max_dd = float(np.min(drawdowns)) if len(drawdowns) > 0 else 0.0
        calmar = cagr / abs(max_dd) if abs(max_dd) > 1e-6 else 0.0

        # Max DD duration (bars)
        dd_is_zero = (drawdowns == 0)
        dd_durations = []
        current_dd_len = 0
        for d in drawdowns:
            if d < 0:
                current_dd_len += 1
            else:
                if current_dd_len > 0:
                    dd_durations.append(current_dd_len)
                    current_dd_len = 0
        if current_dd_len > 0:
            dd_durations.append(current_dd_len)
        max_dd_duration_bars = max(dd_durations) if dd_durations else 0

        # Trade analytics
        total_trades = len(trades)
        closed_trades = [t for t in trades if not t.is_open]
        if not closed_trades and trades:
            closed_trades = trades

        long_trades = [t for t in closed_trades if t.direction == "long"]
        short_trades = [t for t in closed_trades if t.direction == "short"]

        winning_trades = [t for t in closed_trades if t.net_pnl > 0]
        losing_trades = [t for t in closed_trades if t.net_pnl < 0]
        scratch_trades = [t for t in closed_trades if t.net_pnl == 0]

        win_rate = (len(winning_trades) / total_trades) if total_trades > 0 else 0.0
        long_win_rate = (len([t for t in long_trades if t.net_pnl > 0]) / len(long_trades)) if len(long_trades) > 0 else 0.0
        short_win_rate = (len([t for t in short_trades if t.net_pnl > 0]) / len(short_trades)) if len(short_trades) > 0 else 0.0

        gross_profits = sum(t.net_pnl for t in winning_trades)
        gross_losses = abs(sum(t.net_pnl for t in losing_trades))
        profit_factor = (gross_profits / gross_losses) if gross_losses > 0 else (np.inf if gross_profits > 0 else 0.0)

        avg_win = (gross_profits / len(winning_trades)) if winning_trades else 0.0
        avg_loss = (gross_losses / len(losing_trades)) if losing_trades else 0.0
        win_loss_ratio = (avg_win / avg_loss) if avg_loss > 0 else (np.inf if avg_win > 0 else 0.0)

        expectancy_cash = (sum(t.net_pnl for t in closed_trades) / total_trades) if total_trades > 0 else 0.0
        expectancy_pct = (sum(t.pnl_pct for t in closed_trades) / total_trades) if total_trades > 0 else 0.0

        total_fees = sum(t.fees_paid for t in closed_trades)
        avg_holding_bars = (sum(t.holding_bars for t in closed_trades) / total_trades) if total_trades > 0 else 0.0

        long_pnl = sum(t.net_pnl for t in long_trades)
        short_pnl = sum(t.net_pnl for t in short_trades)

        best_trade_pnl = max([t.net_pnl for t in closed_trades]) if closed_trades else 0.0
        worst_trade_pnl = min([t.net_pnl for t in closed_trades]) if closed_trades else 0.0

        exposure_bars = sum(1 for s in equity_df["signal"] if s != 0)
        exposure_pct = exposure_bars / len(equity_df) if len(equity_df) > 0 else 0.0

        return {
            "initial_capital": initial_capital,
            "final_equity": equity[-1],
            "total_net_pnl": total_pnl,
            "net_return_pct": total_net_return * 100.0,
            "cagr_pct": cagr * 100.0,
            "sharpe_ratio": sharpe,
            "sortino_ratio": sortino,
            "calmar_ratio": calmar,
            "max_drawdown_pct": max_dd * 100.0,
            "max_drawdown_duration_bars": max_dd_duration_bars,
            "total_trades": total_trades,
            "long_trades": len(long_trades),
            "short_trades": len(short_trades),
            "win_rate_pct": win_rate * 100.0,
            "long_win_rate_pct": long_win_rate * 100.0,
            "short_win_rate_pct": short_win_rate * 100.0,
            "profit_factor": profit_factor,
            "avg_win_cash": avg_win,
            "avg_loss_cash": avg_loss,
            "win_loss_payoff_ratio": win_loss_ratio,
            "expectancy_cash": expectancy_cash,
            "expectancy_pct": expectancy_pct * 100.0,
            "total_fees_paid": total_fees,
            "market_exposure_pct": exposure_pct * 100.0,
            "avg_holding_bars": avg_holding_bars,
            "long_pnl": long_pnl,
            "short_pnl": short_pnl,
            "best_trade_pnl": best_trade_pnl,
            "worst_trade_pnl": worst_trade_pnl,
            "start_date": str(start_date),
            "end_date": str(end_date),
            "total_bars": len(equity_df)
        }

    @staticmethod
    def to_dataframe(trades: List[Trade]) -> pd.DataFrame:
        records = []
        for t in trades:
            records.append({
                "Trade ID": t.trade_id,
                "Symbol": t.symbol,
                "Direction": t.direction.upper(),
                "Entry Time": t.entry_time,
                "Entry Price": round(t.entry_price, 4),
                "Exit Time": t.exit_time,
                "Exit Price": round(t.exit_price, 4) if t.exit_price else None,
                "Size": round(t.size, 4),
                "Gross PnL ($)": round(t.gross_pnl, 2),
                "Fees ($)": round(t.fees_paid, 2),
                "Net PnL ($)": round(t.net_pnl, 2),
                "Return (%)": round(t.pnl_pct * 100, 2),
                "Holding Bars": t.holding_bars,
                "Exit Reason": t.exit_reason
            })
        return pd.DataFrame(records)

    @staticmethod
    def format_summary_table(metrics: Dict[str, Any]) -> str:
        lines = []
        lines.append("=" * 60)
        lines.append(f"{'QUANTITATIVE STRATEGY PERFORMANCE REPORT':^60}")
        lines.append("=" * 60)
        lines.append(f"Period:               {metrics.get('start_date', '')[:10]} to {metrics.get('end_date', '')[:10]} ({metrics.get('total_bars', 0)} bars)")
        lines.append(f"Initial Capital:      ${metrics.get('initial_capital', 0):,.2f}")
        lines.append(f"Final Equity:         ${metrics.get('final_equity', 0):,.2f}")
        lines.append(f"Total Net PnL:        ${metrics.get('total_net_pnl', 0):,.2f} ({metrics.get('net_return_pct', 0):.2f}%)")
        lines.append(f"CAGR (Annualized):    {metrics.get('cagr_pct', 0):.2f}%")
        lines.append("-" * 60)
        lines.append(f"Sharpe Ratio:         {metrics.get('sharpe_ratio', 0):.2f}")
        lines.append(f"Sortino Ratio:        {metrics.get('sortino_ratio', 0):.2f}")
        lines.append(f"Calmar Ratio:         {metrics.get('calmar_ratio', 0):.2f}")
        lines.append(f"Max Drawdown:         {metrics.get('max_drawdown_pct', 0):.2f}% ({metrics.get('max_drawdown_duration_bars', 0)} bars)")
        lines.append(f"Market Exposure:      {metrics.get('market_exposure_pct', 0):.2f}%")
        lines.append("-" * 60)
        lines.append(f"Total Trades:         {metrics.get('total_trades', 0)} (Long: {metrics.get('long_trades', 0)}, Short: {metrics.get('short_trades', 0)})")
        lines.append(f"Win Rate:             {metrics.get('win_rate_pct', 0):.2f}% (L: {metrics.get('long_win_rate_pct', 0):.1f}%, S: {metrics.get('short_win_rate_pct', 0):.1f}%)")
        lines.append(f"Profit Factor:        {metrics.get('profit_factor', 0):.2f}")
        lines.append(f"Expectancy:           ${metrics.get('expectancy_cash', 0):,.2f} ({metrics.get('expectancy_pct', 0):.2f}%)")
        lines.append(f"Avg Win / Avg Loss:   ${metrics.get('avg_win_cash', 0):,.2f} / ${metrics.get('avg_loss_cash', 0):,.2f} (Ratio: {metrics.get('win_loss_payoff_ratio', 0):.2f})")
        lines.append(f"Long / Short PnL:     ${metrics.get('long_pnl', 0):,.2f} / ${metrics.get('short_pnl', 0):,.2f}")
        lines.append(f"Best / Worst Trade:   ${metrics.get('best_trade_pnl', 0):,.2f} / ${metrics.get('worst_trade_pnl', 0):,.2f}")
        lines.append(f"Avg Holding Bars:     {metrics.get('avg_holding_bars', 0):.1f} bars")
        lines.append(f"Total Friction Paid:  ${metrics.get('total_fees_paid', 0):,.2f}")
        lines.append("=" * 60)
        return "\n".join(lines)
