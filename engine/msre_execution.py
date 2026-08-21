"""
========================================================================================
MSRE-v1 TRIPLE-BARRIER CAUSAL EXECUTION ENGINE
========================================================================================
Implements fixed fractional risk budgeting (1.5%), exact pip friction modeling,
SL/TP triple barrier tracking, pessimistic intrabar resolution, and time stop invalidation.
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple, Literal

@dataclass
class MSRETrade:
    trade_id: int
    symbol: str
    playbook: Literal["Playbook 1 (Fade)", "Playbook 2 (Trend)"]
    direction: Literal["long", "short"]
    entry_bar_idx: int
    entry_time: pd.Timestamp
    entry_price: float
    stop_loss: float
    take_profit: float
    risk_distance: float
    size: float
    initial_equity: float
    exit_bar_idx: Optional[int] = None
    exit_time: Optional[pd.Timestamp] = None
    exit_price: Optional[float] = None
    gross_pnl: float = 0.0
    fees_paid: float = 0.0
    net_pnl: float = 0.0
    return_r: float = 0.0      # PnL in multiples of initial Risk R ($)
    pnl_pct: float = 0.0       # Return on instantaneous portfolio equity
    holding_bars: int = 0
    exit_reason: str = ""
    is_open: bool = True

class MSREBacktestRunner:
    def __init__(
        self,
        initial_capital: float = 100_000.0,
        risk_pct: float = 0.015,         # 1.50% equity risk per trade
        pip_size: float = 0.0001,
        spread_pips: float = 1.2,
        slippage_pips: float = 0.3,
        commission_per_trade: float = 0.0,
        max_holding_bars: int = 18
    ):
        self.initial_capital = initial_capital
        self.risk_pct = risk_pct
        self.pip_size = pip_size
        self.spread_pips = spread_pips
        self.slippage_pips = slippage_pips
        self.commission_per_trade = commission_per_trade
        self.max_holding_bars = max_holding_bars

    def run(self, df_with_signals: pd.DataFrame, symbol: str = "GBPUSD=X") -> Tuple[pd.DataFrame, List[MSRETrade]]:
        df = df_with_signals.copy()
        n = len(df)
        times = df.index
        opens = df['open'].values
        highs = df['high'].values
        lows = df['low'].values
        closes = df['close'].values

        sig_sw_long = df['sig_sweep_long'].values
        sig_sw_short = df['sig_sweep_short'].values
        sig_brk_long = df['sig_breakout_long'].values
        sig_brk_short = df['sig_breakout_short'].values

        macro_highs = df['macro_high'].values
        macro_lows = df['macro_low'].values
        macro_mids = df['macro_mid'].values
        atr_14s = df['atr_14'].values

        # Half spread + slippage in price units
        friction_per_unit = (0.5 * self.spread_pips + self.slippage_pips) * self.pip_size

        equity = self.initial_capital
        equity_series = np.zeros(n)
        current_trade: Optional[MSRETrade] = None
        trades: List[MSRETrade] = []
        trade_id = 0

        for t in range(n):
            current_time = times[t]
            o = opens[t]
            h = highs[t]
            l = lows[t]
            c = closes[t]

            # -------------------------------------------------------------
            # 1. EVALUATE EXITS FOR EXISTING OPEN TRADE
            # -------------------------------------------------------------
            if current_trade is not None and current_trade.is_open:
                current_trade.holding_bars += 1
                exit_triggered = False
                raw_exit_p = None
                exit_reason = ""

                pos_dir = 1 if current_trade.direction == "long" else -1
                sl = current_trade.stop_loss
                tp = current_trade.take_profit

                # Check barriers
                hit_sl = False
                hit_tp = False

                if pos_dir == 1:
                    if l <= sl:
                        hit_sl = True
                    if h >= tp:
                        hit_tp = True
                else:
                    if h >= sl:
                        hit_sl = True
                    if l <= tp:
                        hit_tp = True

                # Pessimistic intrabar resolution
                if hit_sl and hit_tp:
                    exit_triggered = True
                    raw_exit_p = sl
                    exit_reason = "Stop Loss (Pessimistic Intrabar Resolution)"
                elif hit_sl:
                    exit_triggered = True
                    # Open gap through SL check
                    if pos_dir == 1 and o < sl:
                        raw_exit_p = o
                    elif pos_dir == -1 and o > sl:
                        raw_exit_p = o
                    else:
                        raw_exit_p = sl
                    exit_reason = "Stop Loss"
                elif hit_tp:
                    exit_triggered = True
                    if pos_dir == 1 and o > tp:
                        raw_exit_p = o
                    elif pos_dir == -1 and o < tp:
                        raw_exit_p = o
                    else:
                        raw_exit_p = tp
                    exit_reason = "Take Profit"
                elif current_trade.holding_bars >= self.max_holding_bars:
                    exit_triggered = True
                    raw_exit_p = c  # Exit at market close on bar 18
                    exit_reason = f"Time Barrier Invalidation ({self.max_holding_bars} H4 Bars)"

                if exit_triggered and raw_exit_p is not None:
                    # Apply friction on exit
                    eff_exit_p = raw_exit_p - friction_per_unit if pos_dir == 1 else raw_exit_p + friction_per_unit

                    gross_pnl = (eff_exit_p - current_trade.entry_price) * current_trade.size if pos_dir == 1 else (current_trade.entry_price - eff_exit_p) * current_trade.size
                    fees = (2.0 * friction_per_unit * current_trade.size) + self.commission_per_trade
                    net_pnl = gross_pnl - self.commission_per_trade

                    equity += net_pnl
                    dollar_risk = current_trade.initial_equity * self.risk_pct
                    return_r = net_pnl / (dollar_risk + 1e-9)

                    current_trade.exit_bar_idx = t
                    current_trade.exit_time = current_time
                    current_trade.exit_price = eff_exit_p
                    current_trade.gross_pnl = gross_pnl
                    current_trade.fees_paid = fees
                    current_trade.net_pnl = net_pnl
                    current_trade.return_r = return_r
                    current_trade.pnl_pct = net_pnl / current_trade.initial_equity
                    current_trade.exit_reason = exit_reason
                    current_trade.is_open = False
                    trades.append(current_trade)

                    current_trade = None

            # -------------------------------------------------------------
            # 2. EVALUATE NEW ENTRIES AT BAR OPEN FROM (t-1) SIGNAL
            # -------------------------------------------------------------
            if current_trade is None and t > 0:
                prev_idx = t - 1
                entry_signal = None
                playbook_type = None
                direction = None
                calc_sl = None
                calc_tp = None

                # Check Playbook 1 (Fade) priority / evaluation
                if sig_sw_long[prev_idx]:
                    entry_signal = True
                    playbook_type = "Playbook 1 (Fade)"
                    direction = "long"
                    calc_sl = lows[prev_idx] - (8.0 * self.pip_size)
                    calc_tp = macro_mids[prev_idx]
                elif sig_sw_short[prev_idx]:
                    entry_signal = True
                    playbook_type = "Playbook 1 (Fade)"
                    direction = "short"
                    calc_sl = highs[prev_idx] + (8.0 * self.pip_size)
                    calc_tp = macro_mids[prev_idx]
                elif sig_brk_long[prev_idx]:
                    entry_signal = True
                    playbook_type = "Playbook 2 (Trend)"
                    direction = "long"
                    atr_val = atr_14s[prev_idx] if not np.isnan(atr_14s[prev_idx]) else 20.0 * self.pip_size
                    risk_dist = max(1.2 * atr_val, 20.0 * self.pip_size)
                    calc_sl = o - risk_dist
                    calc_tp = o + 3.2 * risk_dist
                elif sig_brk_short[prev_idx]:
                    entry_signal = True
                    playbook_type = "Playbook 2 (Trend)"
                    direction = "short"
                    atr_val = atr_14s[prev_idx] if not np.isnan(atr_14s[prev_idx]) else 20.0 * self.pip_size
                    risk_dist = max(1.2 * atr_val, 20.0 * self.pip_size)
                    calc_sl = o + risk_dist
                    calc_tp = o - 3.2 * risk_dist

                if entry_signal and calc_sl is not None and calc_tp is not None:
                    trade_id += 1
                    pos_dir = 1 if direction == "long" else -1
                    eff_entry_p = o + friction_per_unit if pos_dir == 1 else o - friction_per_unit

                    risk_distance = abs(eff_entry_p - calc_sl)
                    if risk_distance > 0:
                        dollar_risk = equity * self.risk_pct
                        size = dollar_risk / risk_distance

                        current_trade = MSRETrade(
                            trade_id=trade_id,
                            symbol=symbol,
                            playbook=playbook_type,
                            direction=direction,
                            entry_bar_idx=t,
                            entry_time=current_time,
                            entry_price=eff_entry_p,
                            stop_loss=calc_sl,
                            take_profit=calc_tp,
                            risk_distance=risk_distance,
                            size=size,
                            initial_equity=equity,
                            is_open=True
                        )

            # -------------------------------------------------------------
            # 3. MARK TO MARKET AT BAR CLOSE
            # -------------------------------------------------------------
            if current_trade is not None and current_trade.is_open:
                pos_dir = 1 if current_trade.direction == "long" else -1
                unrealized_pnl = (c - current_trade.entry_price) * current_trade.size if pos_dir == 1 else (current_trade.entry_price - c) * current_trade.size
                current_bar_equity = equity + unrealized_pnl
            else:
                current_bar_equity = equity

            equity_series[t] = current_bar_equity

        # Close any lingering trade on last bar
        if current_trade is not None and current_trade.is_open:
            pos_dir = 1 if current_trade.direction == "long" else -1
            eff_exit_p = closes[-1] - friction_per_unit if pos_dir == 1 else closes[-1] + friction_per_unit
            gross_pnl = (eff_exit_p - current_trade.entry_price) * current_trade.size if pos_dir == 1 else (current_trade.entry_price - eff_exit_p) * current_trade.size
            net_pnl = gross_pnl - self.commission_per_trade
            equity += net_pnl

            current_trade.exit_bar_idx = n - 1
            current_trade.exit_time = times[-1]
            current_trade.exit_price = eff_exit_p
            current_trade.gross_pnl = gross_pnl
            current_trade.net_pnl = net_pnl
            current_trade.return_r = net_pnl / (current_trade.initial_equity * self.risk_pct)
            current_trade.pnl_pct = net_pnl / current_trade.initial_equity
            current_trade.exit_reason = "End of Backtest Period"
            current_trade.is_open = False
            trades.append(current_trade)

        peaks = np.maximum.accumulate(equity_series)
        drawdowns = (equity_series - peaks) / peaks

        results_df = pd.DataFrame({
            "equity": equity_series,
            "drawdown": drawdowns,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes
        }, index=times)

        return results_df, trades
