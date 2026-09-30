# US30 Sweep-and-Reclaim / Rejection-and-Confirmation — TradeLocker Studio

A complete, paste-ready TradeLocker Studio strategy plus the offline research
apparatus needed to check that it does what it claims.

**Read this first.** No profitability claim is made anywhere in this package.
The strategy has never been run on real multi-session US30 history, because no
such dataset exists in this workspace and none could be downloaded here. What
*has* been established is that the mechanics are correct, and that the harness
does not manufacture edge out of noise. See [§6 Verification](#6-verification-what-was-actually-run)
for exactly which experiments were executed, and [§9](#9-what-still-has-to-be-done-inside-studio)
for what only you can check inside Studio.

---

## 1. Platform contract

Established from official sources before a line of strategy code was written.

| Fact | Evidence |
|---|---|
| Studio bots are **Python + Backtrader** | `import backtrader as bt` in the published Studio bot source, [MACDominator](https://tradelocker.com/hub/bots/macdominator-13); Studio page shows `class MACDStrategy(bt.Strategy)` with `bt.indicators.MACD` / `bt.indicators.CrossOver` ([tradelocker.com/studio](https://tradelocker.com/studio/)) |
| Strategy shape is `class X(bt.Strategy)` | same two sources |
| **`params` is a dict**, not Backtrader's usual tuple-of-tuples | MACDominator: `params = {"fast_ema_period": 12, "slow_ema_period": 26, "signal_period": 9, "sizer": "AssignedMarginPercentSizer", "sizer_assigned_margin_percent": 2.75}`; also [ScalperBotStrategy](https://tradelocker.com/hub/bots/scalperbotstrategy-15) |
| Sizing is selected **by string name inside `params`** | [How to use a bot sizer](https://tradelocker.com/how-to/use-a-bot-sizer/) |
| Supported sizers: `FixedLotSizer` (`sizer_lots`), `FixedCashSizer` (`sizer_cash`), `AssignedMarginPercentSizer` (`sizer_assigned_margin_percent`), `CustomSizer` (`sizer_value`, subclass `bt.Sizer`, implement `_getsizing`) | same |
| `CustomSizer` requires **TradeLocker Desktop ≥ 2.36** | same page, explicit version note |
| `AssignedMarginPercentSizer` computes lot size **once, at the first trade action**, and reuses it | same page — this is why it is *not* the baseline here |
| Backtest configuration — **instrument, resolution, time period, margin** — is set in the **Studio UI**, not in code | [tradelocker.com/studio](https://tradelocker.com/studio/) |
| Studio is **desktop-app only** and needs a linked live or demo broker account | [MACDominator "How to get"](https://tradelocker.com/hub/bots/macdominator-13); [support article 13704288](https://support.tradelocker.com/en/articles/13704288-studio) |
| Bots run **on your local machine**; the app must stay open and logged in | MACDominator FAQ |
| Code validation checks Python syntax and resolves referenced indicators; it does **not** execute the bot | [disable bot code checks](https://tradelocker.com/how-to/disable-bot-code-checks/); corroborated by third-party [tradescriptai](https://tradescriptai.com/tradelocker-bot-builder) |

**Explicitly out of scope:** the `tradelocker-python` REST package (`TLAPI`,
`get_price_history`, `create_order`). That is the external trading API for
bots running *outside* the platform. It is not the Studio backtester interface
and is not used anywhere in this package.

### Undocumented behaviour, isolated as compatibility limitations

These could not be confirmed from any official source, so the code is written
to **not depend on them**:

- **C-1 Timestamp semantics.** Backtrader exposes naive datetimes; nothing
  documents whether Studio's feed is UTC or broker-local. The strategy
  therefore takes an explicit `data_utc_offset_minutes` parameter and logs its
  interpretation of the very first bar so you can verify in one glance.
- **C-2 Multi-timeframe feeds.** Studio's UI selects a single resolution and
  owns the `cerebro` object, so `cerebro.resampledata` is not reachable. 15-minute
  bars are therefore aggregated **in-strategy** from the 1-minute feed.
- **C-3 Native protective orders.** No source documents stop-loss/take-profit
  arguments on Studio's `self.buy()`/`self.sell()`. Exits are issued as market
  closes via `self.close()`, using only the minimal documented surface.
- **C-4 Order lifecycle.** `notify_order` is standard Backtrader, but Studio's
  broker simulation details (fill price convention, partial fills, rejection
  reasons) are not published. The strategy never stacks a second order while
  one is unresolved, so it is safe under any of these.

---

## 2. The two hypotheses, as state machines

Both run per session, both reset at the session boundary, and both are driven
**only** by completed 15-minute bars. `support` / `resistance` are the previous
complete New York regular session's low / high.

### Bullish — sweep and reclaim

```
IDLE ──[15m bar low ≤ support − sweep_min_pts]──────────────► ARMED
                                                              (record sweep_low)
ARMED ──[deeper low]────────────────────────────────────────► ARMED (extend sweep_low)
ARMED ──[15m close > support + reclaim_buffer_pts]──────────► CONFIRMED → entry next bar
ARMED ──[setup_expiry_bars elapsed]─────────────────────────► IDLE
ARMED ──[data gap > max_gap_minutes]────────────────────────► IDLE
```

`allow_same_bar_reclaim` (default `True`) decides whether a single 15m bar may
both sweep and reclaim. Set `False` to require a strictly later bar.

### Bearish — rejection and confirmation

```
IDLE ──[high ≥ resistance − rejection_zone_pts
        AND close < resistance − rejection_close_buffer_pts]─► ARMED
                                                               (record rej_high,
                                                                confirm_level = bar low
                                                                              − confirm_buffer_pts)
ARMED ──[higher high]───────────────────────────────────────► ARMED (extend rej_high)
ARMED ──[15m close < confirm_level]─────────────────────────► CONFIRMED → entry next bar
ARMED ──[15m close > rej_high]──────────────────────────────► IDLE (structure failed)
ARMED ──[setup_expiry_bars elapsed]─────────────────────────► IDLE
ARMED ──[data gap > max_gap_minutes]────────────────────────► IDLE
```

The arming bar can **never** also be the confirming bar — the brief says "a
*later* completed 15m close". `confirm_level` is fixed at arming time and does
not follow later bars; a new rejection must re-arm the setup.

### Conflict and position rules

| Situation | Behaviour |
|---|---|
| Long and short confirm on the **same** 15m bar | **Neither** is taken, both setups cleared, counted as `blocked_conflict`. Contradictory evidence is not a trade. |
| A setup confirms while a position is open | Ignored. One position at a time; no pyramiding, no reversal. |
| Session trade cap reached | Ignored (`max_trades_per_session`, default 2). |
| Confirmation at/after `entry_cutoff` (15:30 ET) | Ignored. |
| Implied stop outside `[min_stop_pts, max_stop_pts]` | Trade rejected, counted as `rejected_stop_bounds`. |

### Exits

Single full exit, no scaling, no trailing, no breakeven moves. Management
variants are deliberately excluded from the baseline so they can be evaluated
later as separate experiments against it.

| Reason | Trigger | Fill reference |
|---|---|---|
| `target` | 1m bar trades through `entry ± target_r × stop_distance` | target, or the bar open if it gapped past |
| `stop` | 1m bar trades through the stop | stop, or the bar open if it gapped past |
| `stop_ambiguous` | one 1m bar contains **both** stop and target | **stop** (pessimistic), and counted |
| `flat_by_time` | 15:55 ET | bar open |
| `data_gap` | hole larger than `max_gap_minutes` | bar open |
| `session_rollover` / `outside_rth` | safety net | bar open |

---

## 3. Data and timing

- **Execution feed: 1-minute.** Set the Studio resolution to 1 minute.
- **15-minute bars are constructed in code** by bucketing on `epoch % 900 == 0`,
  which aligns to :00/:15/:30/:45. US Eastern offsets are whole hours, so these
  buckets coincide with New York quarter-hours, and 09:30 ET is exactly on a
  boundary.
- **A bucket is only usable once its last minute has completed.** `[09:30,09:45)`
  becomes actionable when the 09:45 bar arrives — not at 09:44.
- **Same-bar execution is structurally impossible.** In `on_bar`, the previous
  bucket is finalised and evaluated *before* the current bar is accumulated, so
  the bar that triggers the decision is never inside the bar that produced it.
  Entry is the **open of the 1-minute bar starting at the bucket boundary** —
  the first genuinely executable price.
- **Everything is computed in UTC epoch seconds**, converted to New York only
  for session logic, via a self-contained implementation of the post-2007 US
  DST rule (second Sunday of March 02:00 EST → first Sunday of November 02:00
  EDT). No `pytz`, no `zoneinfo` dependency at runtime; the test suite
  cross-checks every 3 hours from 2024 to 2028 against `zoneinfo` when present.

---

## 4. Instrument, costs and sizing

There is no universal US30 CFD contract, so these are **required inputs, not
defaults**. The harness prints a warning on every run until you override them.

| Input | Meaning |
|---|---|
| `value_per_point_per_lot` | account-currency P/L per 1.0 index point per 1.0 lot |
| `tick_size` | minimum price increment; all fills are rounded to it |
| `lot_step`, `min_lot`, `max_lot` | lot granularity and bounds |
| `price_basis` | `bid` or `mid` — what your CSV's prices represent |
| `spread_pts`, `slippage_pts`, `commission_per_lot_per_side` | costs |
| `account_currency`, `starting_equity`, `risk_per_trade_pct` | simulated account |

Supply them as JSON: `--spec my_broker.json`.

**Sizing.** `lots = floor(equity × risk% / (stop_distance × value_per_point) / lot_step) × lot_step`,
where `stop_distance` is measured from the **actual entry fill** (cost-inclusive),
not the signal price. Rounding is always *down*, so granularity can never
increase risk. Below `min_lot` the trade is **skipped and counted**, never
rounded up.

**Costs, applied once per round trip.** On a bid series a buy pays
`spread + slippage` and a sell pays `slippage`; on a mid series each side pays
`spread/2 + slippage`. Trigger levels live on the data series, cost is applied
to the fill — so no double counting. A test asserts the round-trip spread cost
equals exactly `spread_pts` under both conventions.

**Gaps and ambiguity.** If a bar opens beyond the level, the fill is the open,
not the level. If a single 1-minute bar contains both stop and target, tick
order is unknowable, so the **stop** is taken and the case is reported as
`ambiguous_exits` in every metrics block.

---

## 5. Baseline parameters

```python
rth_start "09:30"   rth_end "16:00"   entry_cutoff "15:30"   flat_by "15:55"
min_prior_session_bars 300            incomplete_prior_policy "skip"
sweep_min_pts 1.0                     reclaim_buffer_pts 1.0
allow_same_bar_reclaim True
rejection_zone_pts 15.0               rejection_close_buffer_pts 1.0
confirm_buffer_pts 1.0                setup_expiry_bars 8
stop_buffer_pts 5.0                   target_r 2.0
min_stop_pts 5.0                      max_stop_pts 150.0
max_trades_per_session 2              max_gap_minutes 3
```

These are **starting points chosen for plausibility, not fitted values.** No
data selected them. A test asserts the Studio `params` dict and the engine
defaults cannot drift apart.

### Predeclared grid (54 configurations)

Declared before any result was examined:

| Parameter | Values |
|---|---|
| `target_r` | 1.5, 2.0, 3.0 |
| `stop_buffer_pts` | 3.0, 5.0, 10.0 |
| `rejection_zone_pts` | 10.0, 15.0, 25.0 |
| `setup_expiry_bars` | 4, 8 |

Every configuration is written to the grid log — not just the winner — so the
real number of comparisons stays visible. The grid runs on the **dev split
only**. Configurations with fewer than 30 dev trades are excluded from ranking,
and if none qualifies the tool refuses to rank at all.

---

## 6. Verification: what was actually run

Full console output: [`artifacts/verification_runs.txt`](artifacts/verification_runs.txt),
[`artifacts/test_run.txt`](artifacts/test_run.txt).

### 6.1 Mechanics suite — 37/37 passing

`python3 tests/test_us30_sweep_reclaim.py`. Backtrader is stubbed, so **the
exact file you paste into Studio is the file under test**. Coverage:

- **Time** — DST boundary dates for 2026; 09:30 ET maps to 14:30Z in winter and
  13:30Z in summer; offsets match `zoneinfo` at every 3-hour step from 2024 to
  2028 (≈11,700 checks).
- **Causal levels** — the first session never trades; levels come from the
  previous session; a half day does not seed the next day; a date carrying only
  extended-hours bars does not destroy levels.
- **Signal timing** — entry lands on the open of the bar at the bucket
  boundary; truncating the feed one bar early kills the signal; the 15m bucket
  is an exact aggregation of its 15 constituent 1m bars; the bearish arming bar
  cannot also confirm.
- **Exits** — stop sits beyond the sweep extreme; ambiguous bars resolve to the
  stop and are counted; a gap-through fills at the open, not the level; a
  20-minute hole forces a flat position; 15:55 flattening is unconditional; no
  entries after 15:30.
- **Lifecycle** — setups expire; a close back above the rejection high
  invalidates the short; one position at a time; session trade cap holds.
- **Execution model** — size follows risk and the *actual* stop distance;
  rounding never increases risk; sub-minimum size is skipped not rounded up;
  round-trip cost is charged exactly once under both `bid` and `mid`; fills
  round to an arbitrary tick.
- **Data hygiene** — out-of-order bars raise; identical duplicates, conflicting
  duplicates and `high < low` rows are classified separately; epoch-ms and ISO
  timestamps parse identically.
- **Paste integrity** — the Studio file parses under `ast.parse` (the exact
  check Studio runs), is pure ASCII, imports nothing but `backtrader`, and its
  end-of-file sentinel advertises the true line count.
- **Reconciliation** — one trade's entry, exit, lots, P/L and R are recomputed
  by hand from the underlying bars and matched.

### 6.2 Negative control — PASS

`python3 research_backtest.py --mode control`

A driftless random walk with **zero costs**. A harness that peeks ahead,
executes on the signal bar, or resolves ambiguity optimistically would print a
positive edge here.

```
12 seeds x 150 sessions, 1784 trades
mean expectancy        -0.0796 R
stdev across seeds      0.0500 R
seeds positive          0 / 12
verdict                 PASS
```

Negative on **every** seed. The small negative value is expected and is the
right sign: end-of-day truncation of runners and the pessimistic ambiguous-bar
rule each cost a little. The machinery is conservatively biased, not
optimistically biased.

### 6.3 Real-data ingestion — runs, and honestly returns nothing

The only real US30 1-minute file in this repository
(`datasets/us30_20260929/bars_1m.csv`) is **99 bars of one partial session**.
It parses cleanly and the engine reports:

```
rth_sessions 1 | rth_bars 99 | sessions_below_300_bars 1
NO TRADES.
```

Correct: with no prior complete session there is no level to trade against.
This exercises the ingestion path. **It is not a backtest.**

### 6.4 Synthetic runs — plumbing only

Cost sensitivity, dev/val/test splits and the full 54-configuration grid were
executed end to end on the synthetic generator
([`artifacts/synthetic_grid_log.csv`](artifacts/synthetic_grid_log.csv),
[`artifacts/synthetic_baseline_trades.csv`](artifacts/synthetic_baseline_trades.csv)).
Their **numbers describe the generator, not the Dow**, and are reported only as
evidence that the reporting pipeline works. As a caution about sample size:
switching the generator seed moved zero-cost expectancy from −0.18 R to +0.10 R
at ~120 sessions. At these sample sizes the estimate is dominated by noise —
which is exactly why the grid refuses to rank on thin evidence.

### 6.5 Not run

**No backtest on real multi-session US30 history.** No such data exists in this
workspace, network egress here is restricted, and Backtrader and Studio are not
installed. Any expectancy figure for the real Dow would have been fabricated,
so none is given.

---

## 7. Setup in TradeLocker Studio

1. Install the [TradeLocker desktop app](https://tradelocker.com/desktop/) and
   log into a live or demo broker account. Studio exists only there.
2. Open Studio → create a new bot → paste the **entire** contents of
   [`tradelocker_studio_us30.py`](tradelocker_studio_us30.py).

   **Verify the paste landed whole.** The file is 638 lines / ~27 KB and ends
   with an `# END OF FILE - paste integrity check` banner. If that banner is
   not the last thing in the Studio editor, the copy was truncated and Studio
   will report a syntax error like `'(' was never closed` pointing at whatever
   line the paste stopped on. That message means *the file is incomplete*, not
   that the logic is wrong. Re-copy and paste again.
3. Backtest settings in the UI: instrument **US30** (your broker's symbol),
   resolution **1 minute** — this is required, the 15m logic is built from it —
   your date range, and your margin.
4. Set the sizer in `params`. The baseline is `FixedLotSizer` with
   `sizer_lots` because it is the only option whose lot size is both explicit
   and constant. `AssignedMarginPercentSizer` computes size *once at the first
   trade* and reuses it, which breaks risk-based sizing. If your Desktop build
   is ≥ 2.36 and you want true per-trade risk sizing inside Studio, implement a
   `CustomSizer` — note that Studio's sizer runs at order time and does not see
   this strategy's intended stop, so you would need to read
   `self.strategy.engine.pos_stop`.
5. Run the backtest, then **reconcile**: the strategy logs every entry with its
   stop and target, and every exit with its reason. Check a handful against the
   chart before trusting anything.
6. Confirm the first log line reports the correct New York time. If it does
   not, set `data_utc_offset_minutes` and re-run. **Every session rule depends
   on this.**

---

## 8. Reproduction

From the repository root:

```bash
# mechanics suite (34 tests, no dependencies)
python3 tests/test_us30_sweep_reclaim.py
# pytest-compatible too, but pytest is not installed in this workspace,
# so only the standalone runner above was actually executed:
python3 -m pytest tests/test_us30_sweep_reclaim.py -q

cd strategies/us30_sweep_reclaim

# lookahead / optimism control
python3 research_backtest.py --mode control

# real 1-minute history (Dukascopy-node export or any OHLC CSV)
python3 research_backtest.py --csv M1.csv --spec broker.json --mode baseline \
        --out trades.csv
python3 research_backtest.py --csv M1.csv --spec broker.json --mode splits
python3 research_backtest.py --csv M1.csv --spec broker.json --mode grid \
        --out grid_log.csv
python3 research_backtest.py --csv M1.csv --spec broker.json --mode costs

# synthetic plumbing demo (NOT a market)
python3 research_backtest.py --self-test --sessions 120 --mode baseline
```

Accepted CSV shapes (header required):

- Dukascopy-node: `timestamp,open,high,low,close,volume` with epoch-ms UTC
- Generic ISO: `time|datetime|timestamp,open,high,low,close[,volume]`
- A `bar_status` column, if present, must say `COMPLETED` or the row is dropped

Use `--tz-offset-min` if the file's clock is not UTC. **Your broker's US30 feed
is not the same instrument as any free index data** — cash index, futures and
CFD tapes differ in level, hours and spread. Nothing here has been reconciled
against your execution feed, because you have not selected one.

---

## 9. What still has to be done inside Studio

Not answerable from outside the desktop app:

1. **Timestamp convention** — verify the first-bar log line shows the true New
   York time (C-1).
2. **Paste and validate** — confirm Studio's code check accepts the file. It
   only parses syntax and resolves indicators; it does not prove the bot runs.
3. **Fill convention** — Studio's broker simulator decides actual fill prices.
   Compare its trade log against the `ref_in`/`fill_in` columns this harness
   would produce for the same bars, and quantify the difference.
4. **Sizer behaviour** — confirm your chosen sizer's lot sizes in the trade log
   match what you intended, especially if you use `AssignedMarginPercentSizer`.
5. **Rejected orders / margin** — trigger a rejection and confirm
   `notify_order` handles it without leaving a stale position.
6. **Intra-bar protection** — with no native stop order (C-3), measure how
   often a 1-minute close-based exit differs from a resting stop.
7. **Then, and only then, a real backtest** over multiple years, followed by
   the dev/validation/test protocol in §5. The untouched test split must be
   evaluated **once**.

---

## 10. Files

| Path | Purpose |
|---|---|
| `tradelocker_studio_us30.py` | The deliverable. Paste this into Studio. Contains the time layer, the rule engine, and the `bt.Strategy` wrapper. |
| `research_backtest.py` | Offline harness. Imports the engine from the file above — never reimplements it. Data loading, integrity, execution model, metrics, splits, grid, negative control. |
| `../../tests/test_us30_sweep_reclaim.py` | 37 mechanics tests against the paste-ready file. |
| `ASSUMPTIONS.md` | Every modelling decision made where the brief was underspecified. |
| `artifacts/` | Console output and CSV logs of the runs reported in §6. |
