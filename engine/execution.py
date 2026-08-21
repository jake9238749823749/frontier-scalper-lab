import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import List, Dict, Optional, Literal, Tuple

@dataclass
class Trade:
    trade_id: int
    symbol: str
    direction: Literal["long", "short"]
    entry_time: pd.Timestamp
    entry_price: float
    exit_time: Optional[pd.Timestamp] = None
    exit_price: Optional[float] = None
    size: float = 0.0  # units/shares/contracts
    initial_cash: float = 0.0
    cost_basis: float = 0.0
    gross_pnl: float = 0.0
    net_pnl: float = 0.0
    fees_paid: float = 0.0
    pnl_pct: float = 0.0
    holding_bars: int = 0
    exit_reason: str = ""
    is_open: bool = True

@dataclass
class ExecutionConfig:
    initial_capital: float = 100_000.0
    commission_pct: float = 0.0005      # 5 bps (0.05%) default
    commission_fixed: float = 0.0       # Fixed per trade (e.g. $1)
    spread_pct: float = 0.0002          # 2 bps bid-ask half-spread
    slippage_pct: float = 0.0003        # 3 bps execution slippage
    allow_short: bool = True
    fractional_shares: bool = True
    intrabar_sl_priority: bool = True   # If both SL and TP hit in same bar, assume SL first (conservative)

class BacktestEngine:
    """
    Strictly Causal Event-Driven and Vector-Validated Backtesting Engine.
    Guarantees no lookahead bias. Signals generated at close of bar t execute at bar t+1.
    """
    def __init__(self, config: Optional[ExecutionConfig] = None):
        self.config = config or ExecutionConfig()

    def run(
        self,
        df: pd.DataFrame,
        signal_series: pd.Series,
        stop_loss_pct: Optional[float] = None,
        take_profit_pct: Optional[float] = None,
        trailing_stop_pct: Optional[float] = None,
        max_holding_bars: Optional[int] = None,
        sizing_mode: Literal["all_in", "fixed_fraction", "risk_parity"] = "all_in",
        sizing_param: float = 1.0,  # 1.0 = 100% equity allocated
        symbol: str = "ASSET"
    ) -> Tuple[pd.DataFrame, List[Trade]]:
        """
        Execute backtest bar-by-bar.
        signal_series: 1 for Long, -1 for Short, 0 for Flat.
                       Signal at index t indicates desired position target starting from t+1 open.
        """
        data = df.copy()
        if not isinstance(data.index, pd.DatetimeIndex):
            data.index = pd.to_datetime(data.index)

        # Align signal series
        signal_series = signal_series.reindex(data.index).fillna(0)

        n = len(data)
        times = data.index
        opens = data["open"].values
        highs = data["high"].values
        lows = data["low"].values
        closes = data["close"].values
        signals = signal_series.values

        cash = self.config.initial_capital
        equity = cash
        equity_series = np.zeros(n)
        cash_series = np.zeros(n)
        position_size = 0.0  # > 0 long, < 0 short
        current_trade: Optional[Trade] = None
        trades: List[Trade] = []
        trade_counter = 0

        # Cost multipliers
        total_friction_buy = self.config.commission_pct + self.config.spread_pct + self.config.slippage_pct
        total_friction_sell = self.config.commission_pct + self.config.spread_pct + self.config.slippage_pct

        for t in range(n):
            current_bar_time = times[t]
            open_p = opens[t]
            high_p = highs[t]
            low_p = lows[t]
            close_p = closes[t]

            # 1. Evaluate Intrabar Exits for open position (SL / TP / Trailing Stop / Time Stop)
            if current_trade is not None and current_trade.is_open:
                current_trade.holding_bars += 1
                exit_triggered = False
                exit_price = None
                exit_reason = ""

                pos_dir = 1 if current_trade.direction == "long" else -1
                entry_p = current_trade.entry_price

                # Check trailing stop reference update
                if trailing_stop_pct is not None and trailing_stop_pct > 0:
                    if pos_dir == 1:
                        peak_p = getattr(current_trade, "peak_price", entry_p)
                        if high_p > peak_p:
                            peak_p = high_p
                            setattr(current_trade, "peak_price", peak_p)
                        ts_price = peak_p * (1.0 - trailing_stop_pct)
                    else:
                        trough_p = getattr(current_trade, "trough_price", entry_p)
                        if low_p < trough_p:
                            trough_p = low_p
                            setattr(current_trade, "trough_price", trough_p)
                        ts_price = trough_p * (1.0 + trailing_stop_pct)
                else:
                    ts_price = None

                # Compute thresholds
                sl_price = entry_p * (1.0 - stop_loss_pct) if (stop_loss_pct and pos_dir == 1) else \
                           entry_p * (1.0 + stop_loss_pct) if (stop_loss_pct and pos_dir == -1) else None
                tp_price = entry_p * (1.0 + take_profit_pct) if (take_profit_pct and pos_dir == 1) else \
                           entry_p * (1.0 - take_profit_pct) if (take_profit_pct and pos_dir == -1) else None

                # Check SL hit
                hit_sl = False
                hit_tp = False
                hit_ts = False

                if pos_dir == 1:
                    if sl_price is not None and low_p <= sl_price:
                        hit_sl = True
                    if tp_price is not None and high_p >= tp_price:
                        hit_tp = True
                    if ts_price is not None and low_p <= ts_price:
                        hit_ts = True
                else:
                    if sl_price is not None and high_p >= sl_price:
                        hit_sl = True
                    if tp_price is not None and low_p <= tp_price:
                        hit_tp = True
                    if ts_price is not None and high_p >= ts_price:
                        hit_ts = True

                # Determine exit with conservative conflict resolution
                if hit_sl and hit_tp:
                    if self.config.intrabar_sl_priority:
                        exit_triggered = True
                        exit_price = sl_price
                        exit_reason = "Stop Loss (Intrabar Conflict Priority)"
                    else:
                        exit_triggered = True
                        exit_price = tp_price
                        exit_reason = "Take Profit"
                elif hit_sl:
                    exit_triggered = True
                    # Open gap down through SL?
                    if pos_dir == 1 and open_p < sl_price:
                        exit_price = open_p
                    elif pos_dir == -1 and open_p > sl_price:
                        exit_price = open_p
                    else:
                        exit_price = sl_price
                    exit_reason = "Stop Loss"
                elif hit_ts:
                    exit_triggered = True
                    if pos_dir == 1 and open_p < ts_price:
                        exit_price = open_p
                    elif pos_dir == -1 and open_p > ts_price:
                        exit_price = open_p
                    else:
                        exit_price = ts_price
                    exit_reason = "Trailing Stop"
                elif hit_tp:
                    exit_triggered = True
                    if pos_dir == 1 and open_p > tp_price:
                        exit_price = open_p
                    elif pos_dir == -1 and open_p < tp_price:
                        exit_price = open_p
                    else:
                        exit_price = tp_price
                    exit_reason = "Take Profit"
                elif max_holding_bars is not None and current_trade.holding_bars >= max_holding_bars:
                    exit_triggered = True
                    exit_price = open_p  # Exit at bar open
                    exit_reason = f"Time Stop ({max_holding_bars} bars)"

                # Process Exit if triggered
                if exit_triggered and exit_price is not None:
                    # Apply slippage & fees on exit
                    eff_exit_price = exit_price * (1.0 - total_friction_sell) if pos_dir == 1 else exit_price * (1.0 + total_friction_buy)
                    gross_pnl = (exit_price - entry_p) * position_size if pos_dir == 1 else (entry_p - exit_price) * abs(position_size)
                    fees = (entry_p * abs(position_size) * total_friction_buy) + (exit_price * abs(position_size) * total_friction_sell) + 2 * self.config.commission_fixed
                    net_pnl = gross_pnl - fees

                    cash += (position_size * eff_exit_price) if pos_dir == 1 else (abs(position_size) * (2 * entry_p - eff_exit_price))
                    current_trade.exit_time = current_bar_time
                    current_trade.exit_price = eff_exit_price
                    current_trade.gross_pnl = gross_pnl
                    current_trade.net_pnl = net_pnl
                    current_trade.fees_paid = fees
                    current_trade.pnl_pct = (net_pnl / current_trade.cost_basis) if current_trade.cost_basis > 0 else 0.0
                    current_trade.exit_reason = exit_reason
                    current_trade.is_open = False
                    trades.append(current_trade)

                    current_trade = None
                    position_size = 0.0

            # 2. Check Signals from previous bar (t-1) if no intrabar conflict
            # Signal generated at close of t-1 triggers action at open of t
            if t > 0:
                target_signal = signals[t - 1]
                # If target signal contradicts open position or demands entry
                desired_dir = "long" if target_signal > 0 else ("short" if target_signal < 0 and self.config.allow_short else "flat")

                if current_trade is not None and current_trade.is_open:
                    if (current_trade.direction == "long" and desired_dir != "long") or \
                       (current_trade.direction == "short" and desired_dir != "short"):
                        # Close position at open of t
                        pos_dir = 1 if current_trade.direction == "long" else -1
                        exec_p = open_p * (1.0 - total_friction_sell) if pos_dir == 1 else open_p * (1.0 + total_friction_buy)
                        gross_pnl = (open_p - current_trade.entry_price) * position_size if pos_dir == 1 else (current_trade.entry_price - open_p) * abs(position_size)
                        fees = (current_trade.entry_price * abs(position_size) * total_friction_buy) + (open_p * abs(position_size) * total_friction_sell) + 2 * self.config.commission_fixed
                        net_pnl = gross_pnl - fees

                        cash += (position_size * exec_p) if pos_dir == 1 else (abs(position_size) * (2 * current_trade.entry_price - exec_p))
                        current_trade.exit_time = current_bar_time
                        current_trade.exit_price = exec_p
                        current_trade.gross_pnl = gross_pnl
                        current_trade.net_pnl = net_pnl
                        current_trade.fees_paid = fees
                        current_trade.pnl_pct = (net_pnl / current_trade.cost_basis) if current_trade.cost_basis > 0 else 0.0
                        current_trade.exit_reason = "Signal Flip / Reversal"
                        current_trade.is_open = False
                        trades.append(current_trade)

                        current_trade = None
                        position_size = 0.0

                # If flat and desired_dir is active, enter new trade at open of t
                if current_trade is None and desired_dir in ["long", "short"]:
                    trade_counter += 1
                    pos_dir = 1 if desired_dir == "long" else -1
                    exec_entry_p = open_p * (1.0 + total_friction_buy) if pos_dir == 1 else open_p * (1.0 - total_friction_sell)

                    # Compute sizing
                    available_capital = max(0.0, cash * sizing_param)
                    if self.config.fractional_shares:
                        qty = available_capital / exec_entry_p
                    else:
                        qty = float(np.floor(available_capital / exec_entry_p))

                    if qty > 0:
                        position_size = qty * pos_dir
                        cost_basis = qty * exec_entry_p
                        cash -= cost_basis if pos_dir == 1 else 0.0  # Cash margin reservation for long

                        current_trade = Trade(
                            trade_id=trade_counter,
                            symbol=symbol,
                            direction=desired_dir,
                            entry_time=current_bar_time,
                            entry_price=exec_entry_p,
                            size=qty,
                            initial_cash=cash,
                            cost_basis=cost_basis,
                            holding_bars=0,
                            is_open=True
                        )
                        if trailing_stop_pct is not None and trailing_stop_pct > 0:
                            if pos_dir == 1:
                                setattr(current_trade, "peak_price", exec_entry_p)
                            else:
                                setattr(current_trade, "trough_price", exec_entry_p)

            # 3. Mark to market at bar close
            if position_size > 0:
                unrealized = position_size * close_p
                equity = cash + unrealized
            elif position_size < 0:
                unrealized = abs(position_size) * (2 * current_trade.entry_price - close_p)
                equity = cash + unrealized
            else:
                equity = cash

            equity_series[t] = equity
            cash_series[t] = cash

        # Close open trade at the very last bar close for accurate accounting
        if current_trade is not None and current_trade.is_open:
            last_p = closes[-1]
            pos_dir = 1 if current_trade.direction == "long" else -1
            exec_p = last_p * (1.0 - total_friction_sell) if pos_dir == 1 else last_p * (1.0 + total_friction_buy)
            gross_pnl = (last_p - current_trade.entry_price) * position_size if pos_dir == 1 else (current_trade.entry_price - last_p) * abs(position_size)
            fees = (current_trade.entry_price * abs(position_size) * total_friction_buy) + (last_p * abs(position_size) * total_friction_sell) + 2 * self.config.commission_fixed
            net_pnl = gross_pnl - fees

            current_trade.exit_time = times[-1]
            current_trade.exit_price = exec_p
            current_trade.gross_pnl = gross_pnl
            current_trade.net_pnl = net_pnl
            current_trade.fees_paid = fees
            current_trade.pnl_pct = (net_pnl / current_trade.cost_basis) if current_trade.cost_basis > 0 else 0.0
            current_trade.exit_reason = "End of Backtest Period"
            current_trade.is_open = False
            trades.append(current_trade)

        result_df = pd.DataFrame({
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "signal": signals,
            "equity": equity_series,
            "cash": cash_series,
            "drawdown": (equity_series - np.maximum.accumulate(equity_series)) / np.maximum.accumulate(equity_series)
        }, index=times)

        return result_df, trades
