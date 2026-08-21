"""
========================================================================================
MSRE-v1: MULTI-SCALE STRUCTURAL REGIME ENGINE
========================================================================================
Implements 5-day macro structural context, Kaufman efficiency ratio, Rogers-Satchell /
Garman-Klass drift tensors, kinetic dissipation ratios, and Brownian bridge probabilities.
"""

import numpy as np
import pandas as pd
from typing import Dict, Any, Optional

class MSRE_Strategy:
    def __init__(
        self,
        macro_window: int = 30,
        pip_size: float = 0.0001,
        risk_pct: float = 0.015,
        max_hold_bars: int = 18,
        use_normalized_phi: bool = True,  # When True, phi = body / range (0 to 1)
        drift_threshold: float = 0.35,
        eff_fade_thresh: float = 0.32,
        eff_trend_thresh: float = 0.35,
        squeeze_thresh: float = 0.95
    ):
        self.macro_window = macro_window
        self.pip_size = pip_size
        self.risk_pct = risk_pct
        self.max_hold_bars = max_hold_bars
        self.use_normalized_phi = use_normalized_phi
        self.drift_threshold = drift_threshold
        self.eff_fade_thresh = eff_fade_thresh
        self.eff_trend_thresh = eff_trend_thresh
        self.squeeze_thresh = squeeze_thresh

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        eps = 1e-8
        df = df.copy()

        # 1. Macro Profile (strictly lagged t-30 to t-1)
        df['macro_high'] = df['high'].shift(1).rolling(self.macro_window).max()
        df['macro_low'] = df['low'].shift(1).rolling(self.macro_window).min()
        df['macro_mid'] = (df['macro_high'] + df['macro_low']) / 2.0

        # 2. Kaufman Macro Efficiency
        net_d = (df['close'].shift(1) - df['close'].shift(self.macro_window)).abs()
        gross_p = (df['close'].shift(1) - df['close'].shift(2)).abs().rolling(self.macro_window - 1).sum()
        df['macro_eff'] = net_d / (gross_p + eps)

        # 3. ATR & Volatility Squeeze
        tr = np.maximum(
            df['high'] - df['low'],
            np.maximum(
                (df['high'] - df['close'].shift(1)).abs(),
                (df['low'] - df['close'].shift(1)).abs()
            )
        )
        df['atr_14'] = tr.rolling(14).mean()
        df['atr_20'] = tr.rolling(20).mean()

        sma_20 = df['close'].rolling(20).mean()
        std_20 = df['close'].rolling(20).std()
        df['squeeze'] = (4.0 * std_20) / (3.0 * df['atr_20'] + eps)
        df['recent_squeeze'] = df['squeeze'].rolling(3).min()

        # 4. Rogers-Satchell / Garman-Klass Drift Tensor (Psi_t)
        log_hl = np.log(np.maximum(df['high'] / np.maximum(df['low'], eps), 1.0 + eps))
        log_co = np.log(np.maximum(df['close'] / np.maximum(df['open'], eps), 1.0 + eps))
        sigma_gk = np.maximum(0.5 * (log_hl**2) - (2.0 * np.log(2.0) - 1.0) * (log_co**2), eps)

        log_hc = np.log(np.maximum(df['high'] / np.maximum(df['close'], eps), 1.0 + eps))
        log_ho = np.log(np.maximum(df['high'] / np.maximum(df['open'], eps), 1.0 + eps))
        log_lc = np.log(np.maximum(df['low'] / np.maximum(df['close'], eps), 1.0 + eps))
        log_lo = np.log(np.maximum(df['low'] / np.maximum(df['open'], eps), 1.0 + eps))
        sigma_rs = np.maximum((log_hc * log_ho) + (log_lc * log_lo), 0.0)
        df['psi_drift'] = (sigma_rs / sigma_gk) - 1.0

        # 5. Kinetic Dissipation Ratio (Phi_t)
        hl_safe = np.where(df['high'] - df['low'] == 0, eps, df['high'] - df['low'])
        if self.use_normalized_phi:
            # Normalized body-to-range ratio (absorption wick signature)
            df['phi_dissipation'] = (df['close'] - df['open']).abs() / hl_safe
        else:
            # Literal raw formula
            df['phi_dissipation'] = ((df['close'] - df['open']).abs() * np.log1p(np.maximum(df['volume'], 0.0))) / (hl_safe**2)

        # 6. Brownian Bridge Sequence Probability P(H < L)
        num_h = (df['open'] - df['low']) * (df['high'] - df['close'])
        den_h = num_h + (df['high'] - df['open']) * (df['close'] - df['low']) + eps
        df['p_high_first'] = np.clip(num_h / den_h, 0.0, 1.0)

        # 7. Volume Quantile
        df['vol_p85'] = df['volume'].rolling(60).quantile(0.85)

        # Signals
        # Playbook 1: 5-Day Structural Sweep (Mean-Reversion)
        df['sig_sweep_long'] = (
            (df['macro_eff'] < self.eff_fade_thresh) &
            (df['low'] < df['macro_low']) &
            (df['close'] > df['macro_low']) &
            (df['phi_dissipation'] <= 0.22) &
            (df['p_high_first'] <= 0.30)
        )
        df['sig_sweep_short'] = (
            (df['macro_eff'] < self.eff_fade_thresh) &
            (df['high'] > df['macro_high']) &
            (df['close'] < df['macro_high']) &
            (df['phi_dissipation'] <= 0.22) &
            (df['p_high_first'] >= 0.70)
        )

        # Playbook 2: Squeeze Drift Breakout (Trend Expansion)
        df['sig_breakout_long'] = (
            (df['macro_eff'] >= self.eff_trend_thresh) &
            (df['recent_squeeze'] <= self.squeeze_thresh) &
            (df['close'] > df['macro_high']) &
            (df['psi_drift'] >= self.drift_threshold) &
            (df['volume'] >= df['vol_p85'])
        )
        df['sig_breakout_short'] = (
            (df['macro_eff'] >= self.eff_trend_thresh) &
            (df['recent_squeeze'] <= self.squeeze_thresh) &
            (df['close'] < df['macro_low']) &
            (df['psi_drift'] >= self.drift_threshold) &
            (df['volume'] >= df['vol_p85'])
        )

        return df
