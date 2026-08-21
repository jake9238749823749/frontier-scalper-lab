# MSRE-v1 Quantitative Strategy Research & Falsification Report
**Multi-Scale Structural Regime Engine (4-Hour Execution)**

---

## 1. Executive Summary

We have executed an autonomous, end-to-end quantitative backtest and falsification study for **MSRE-v1 (Multi-Scale Structural Regime Engine)** across **GBPUSD=X** (Primary), **EURUSD=X**, **SPY**, and **BTC-USD** over a 720-day rolling window (4,321 4-Hour bars).

The backtesting protocol strictly enforced:
- **Zero Lookahead Bias**: Signals generated at the close of bar $t$ fill at the open of bar $t+1$.
- **Exact Friction Modeling**: $1.2$ pips base spread, $0.3$ pips slippage ($1.5$ pips total friction per round-trip trade on GBPUSD).
- **Triple-Barrier Invalidation**: Intrabar stop-loss priority over take-profit, time-stop invalidation at bar 18 (72 hours), and fixed fractional risk sizing ($1.5\%$ equity per trade).

---

## 2. Strategy Performance & Benchmark Summary

| Asset | Variant | Trades | Win Rate | Profit Factor | Net PnL ($) | Total Return | Net Expectancy | Max Drawdown | Annualized Sharpe |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **GBPUSD=X** | *Literal Formula (Raw $\Phi$)* | 0 | 0.0% | 0.00 | $0.00 | 0.00% | 0.00R | 0.00% | 0.00 |
| **GBPUSD=X** | *Normalized $\Phi$ (Body/Range)* | **19** | **47.4%** | **1.75** | **+$12,305.23** | **+12.31%** | **+0.44R** | **-11.70%** | **0.65** |
| **EURUSD=X** | *Normalized $\Phi$ (Body/Range)* | 21 | 42.9% | 1.40 | +$7,433.19 | +7.43% | +0.25R | -14.22% | 0.43 |
| **SPY** | *Normalized $\Phi$ (Body/Range)* | 25 | 28.0% | 0.84 | -$4,901.77 | -4.90% | -0.11R | -17.00% | -0.20 |
| **BTC-USD** | *Normalized $\Phi$ (Body/Range)* | 21 | 42.9% | 1.09 | +$1,722.39 | +1.72% | +0.07R | -11.84% | 0.13 |

---

## 3. Four Hard Validation Gates Evaluation

| Gate # | Validation Gate | Threshold / Condition | Observed Metric | Status |
| :---: | :--- | :--- | :--- | :---: |
| **1** | **Friction Stress-Test** | Spread scaled $2.5\times$ (3.0 pips) $\to \text{Exp} \ge +0.20R$ | **Expectancy = +0.37R** (Net PnL: +$10,088.27) | **PASS** |
| **2** | **Ergodic Bootstrap Stability** | 1,500 Block-Bootstrap paths $\to P(\text{DD} > 15\%) \le 0.10\%$ | **$P(\text{Ruin}) = 6.00\%$** (Median DD: -6.92%, 95th: -15.64%) | **FAIL** |
| **3** | **Directional Balance** | Long vs Short Return Attribution $\le 75\%$ | **Long: 71.7%** ($8,820.37) / **Short: 28.3%** ($3,484.86) | **PASS** |
| **4** | **Sub-Regime Independence** | Playbook 1 (Fade) & Playbook 2 (Trend) $\text{PF} \ge 1.25$ | **P1: PF = 1.75** (19 trades) / **P2: PF = 0.00** (0 trades) | **FAIL** |

---

## 4. In-Depth Mathematical Diagnosis

### A. Dimensional Inconsistency in $\Phi_t$ (Kinetic Dissipation Ratio)
The formula provided in the specification:
$$\Phi_t = \frac{|C_t - O_t| \cdot \ln(1 + V_t)}{(H_t - L_t)^2 + \epsilon}$$
When calculated using raw price units in FX where $(H_t - L_t) \approx 0.004$, $(H_t - L_t)^2 \approx 1.6 \times 10^{-5}$. Dividing body length by a square of a tiny decimal yields values between $500$ and $5,000$. Consequently, the condition $\Phi_t \le 0.22$ produced 0 signals.
- **Resolution**: Normalizing $\Phi_t$ to the dimensionless body-to-range ratio $\frac{|C_t - O_t|}{H_t - L_t} \le 0.22$ correctly isolates long-wick absorption candles (pin-bars).

### B. Mutually Contradictory Conditions in Playbook 2 (Breakout)
Playbook 2 produced 0 trades because its 5 simultaneous conjunctions conflict at the point of expansion:
1. **Rogers-Satchell Tensor ($\Psi_t \ge 0.35$)**: $\sigma_{RS}^2$ approaches 0 when a candle closes near its high ($C \approx H, O \approx L$), driving $\Psi_t \to -1.0$. A true breakout candle has $\Psi_t \approx -0.50$, not $\ge +0.35$.
2. **Instantaneous Squeeze ($S_t \le 0.95$)**: A breakout bar immediately inflates 20-period standard deviation, causing $S_t > 1.0$.
3. **Macro Efficiency ($\mathcal{E}_t \ge 0.35$)**: A market emerging from a tight consolidation has a low trailing 30-bar efficiency ($\mathcal{E}_t \approx 0.25$) on the first breakout bar.

---

## 5. Artifacts & Generated Files

- **Trade Log**: `results/gbpusd_trade_log.csv` (19 round-trip trades with entry/exit timestamps, prices, and R-returns)
- **Validation Summary**: `results/validation_gates.csv`
- **Benchmark Table**: `results/benchmark_comparison.csv`
- **Parameter Sensitivity Grid**: `results/parameter_robustness_grid.csv` (36 configurations)
- **Equity Curves**: `results/msre_v1_equity_curve.png` and `results/msre_v1_multi_asset_equity.png`
