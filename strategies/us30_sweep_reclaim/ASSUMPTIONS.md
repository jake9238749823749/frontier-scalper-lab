# Assumptions register

Every place the original brief was underspecified, or where reality could not
be observed from this workspace. Each entry states the decision taken, why,
and how to overturn it. Nothing here is hidden inside the code.

Legend — **Impact**: how much the choice can move results.

---

## A. Modelling decisions (specification was ambiguous)

### A-01 — "Previous complete New York regular session" means 09:30–16:00 ET of the prior trading date
**Impact: high.** The brief names the session but not its bounds. Regular
trading hours are used; pre-market and after-hours bars are excluded from both
level construction and signal generation. A session must contain at least
`min_prior_session_bars` (300) 1-minute RTH bars to qualify.
*Overturn:* change `rth_start` / `rth_end`, or lower `min_prior_session_bars`.

### A-02 — An incomplete prior session stands the next day down
**Impact: medium.** Half days (early closes) and outage days produce a session
that is not "complete". Default `incomplete_prior_policy="skip"` takes the
brief literally: no complete prior session, no trading. The alternative,
`"carry"`, reuses the last complete session's levels and flags the day as
stale (`stats["stale_levels_sessions"]`). Neither is obviously right; the
conservative one is the default.
*Overturn:* `incomplete_prior_policy="carry"`.

### A-03 — A date with no RTH bars at all is ignored entirely
**Impact: low.** Holidays, and dates that only carry extended-hours bars, do
not overwrite the stored levels. Without this a single quiet date would blank
the levels and silently kill the following day. Covered by
`test_extended_hours_only_date_does_not_destroy_levels`.

### A-04 — One 15m bar may both sweep and reclaim
**Impact: medium.** The bullish rule says price breaches support, "then" a 15m
candle closes above the reclaim threshold — ambiguous about whether one candle
can do both. Default `allow_same_bar_reclaim=True` permits it, since a single
sweep-and-reclaim candle is the canonical expression of the pattern. The
bearish rule says "a **later** completed 15m close", so there the arming bar is
explicitly barred from confirming.
*Overturn:* `allow_same_bar_reclaim=False`.

### A-05 — "Enters the resistance zone" means the bar's high reaches within `rejection_zone_pts` of the prior high
**Impact: high.** The brief names a zone but not its width. Modelled as
`[resistance − rejection_zone_pts, ∞)`: touching or exceeding counts. The zone
is unbounded above, so an overshoot that closes back below still rejects.
Default 15.0 points; in the predeclared grid at 10 / 15 / 25.

### A-06 — The bearish confirmation threshold is the arming bar's low minus a buffer
**Impact: high.** "A later completed 15m close beneath the confirmation
threshold" does not define the threshold. It is fixed at arming time and does
not ratchet with later bars; a new rejection must re-arm. Fixing it keeps the
setup causal and auditable.

### A-07 — Stops sit `stop_buffer_pts` beyond the sweep low / rejection high, and that extreme extends
**Impact: high.** While a setup is armed, a deeper sweep low (or higher
rejection high) replaces the stored extreme, so the stop always sits beyond the
*worst* excursion of the setup. This widens stops and shrinks size.
`max_stop_pts` (150) rejects degenerate cases outright rather than taking a
trade with meaningless risk.

### A-08 — Conflicting simultaneous signals produce no trade
**Impact: low-medium.** If both state machines confirm on the same 15m bar,
neither is taken and both are cleared (`blocked_conflict`). Picking one would
require a tie-break rule with no evidence behind it.

### A-09 — Single full exit, no trade management
**Impact: high.** Exit is one full close at `target_r × stop_distance`, at the
stop, or at the flat-by time. No partials, no trailing, no breakeven. The brief
asks for exactly this, with management as *separate* experiments. Adding any of
them changes the distribution and must be evaluated against this baseline, not
merged into it.

---

## B. Execution and cost model (broker reality not observable here)

### B-01 — Instrument specification is a REQUIRED INPUT, not a default
**Impact: critical.** `value_per_point_per_lot`, `tick_size`, `lot_step`,
`min_lot`, `max_lot`, `spread_pts` vary by broker; there is no universal US30
CFD contract. The placeholders in `DEFAULT_SPEC` exist only so the arithmetic
runs. Every run prints a warning until they are overridden with `--spec`.
Position size scales **linearly** with `value_per_point_per_lot`; getting it
wrong misstates every cash figure by that factor.

### B-02 — Bars are assumed BID by default
**Impact: medium.** Most retail CFD history (including Dukascopy exports) is
bid. On a bid series a buy pays the full spread and a sell pays none; on `mid`
each side pays half. Round-trip spread cost is identical either way, and a test
asserts it.
*Overturn:* `price_basis: "mid"`.

### B-03 — Spread is constant
**Impact: medium-high.** A single `spread_pts` applies to every fill. Real US30
spreads widen at the open, around news and into the close — precisely when
these setups fire. This assumption is therefore **optimistic**, which is why
`--mode costs` reports 1x / 2x / 3x cost multiples. If the strategy only
survives at 1x, it does not survive.

### B-04 — Slippage is a fixed number of points per fill
**Impact: medium.** Applied symmetrically against the trader on entry and exit.
It does not scale with size, volatility or gap magnitude. A market close at a
1-minute bar open in a fast tape will do worse than this.

### B-05 — Stop and target triggers are evaluated on the bar's high/low, and fills are cost-adjusted afterwards
**Impact: medium.** Triggering uses the data series; the cost is applied to the
resulting fill price. This avoids double counting the spread (once in the
trigger, once in the fill). It does mean that if your feed is bid and you are
short, the true ask may have touched a stop the bid did not reach.

### B-06 — One 1-minute bar containing both stop and target resolves to the stop
**Impact: medium.** Tick order inside a bar is unknowable from OHLC. The
pessimistic branch is taken and the count is surfaced as `ambiguous_exits` in
every metrics block. If that count is material relative to trade count, the
result needs finer data before it can be believed.

### B-07 — Gaps fill at the bar open
**Impact: medium.** If a bar opens beyond the level, the fill is the open, not
the level, so realised losses can exceed 1R. This is visible in the R
distribution rather than being clipped away.

### B-08 — Risk is a fixed percentage of *current* simulated equity
**Impact: medium.** Equity compounds across trades. R is scale-free so
expectancy in R is unaffected, but cash figures and lot sizes are.

### B-09 — Lot rounding is always downward
**Impact: low.** `floor` to `lot_step`, so granularity never increases risk.
Below `min_lot` the trade is skipped and counted (`skipped_min_size`), never
rounded up. Above `max_lot` it is clamped and counted.

### B-10 — No overnight financing, no dividend adjustment, no commission tiering
**Impact: low.** All positions are flat by 15:55 ET, so swap does not apply.
Commission is a flat per-lot-per-side figure.

---

## C. Data assumptions

### C-01 — Bar timestamps are the bar's OPEN time
**Impact: critical.** The whole bucketing scheme assumes a bar stamped 09:45
covers `[09:45, 09:46)`. If your feed stamps the *close*, every signal shifts
by one bar. Dukascopy-node uses open time. **Verify this for your own feed
before running anything.**

### C-02 — 15-minute buckets align to `epoch % 900 == 0`
**Impact: low.** US Eastern offsets are whole hours, so UTC quarter-hours
coincide with New York quarter-hours, and 09:30 ET falls exactly on a boundary.
This would break for a market whose session start is not on a 15-minute grid.

### C-03 — Missing bars are never manufactured
**Impact: medium.** No forward-filling, no synthetic candles. A hole longer
than `max_gap_minutes` (3) invalidates armed setups and forces any open
position flat, counted as `gaps` / `data_gap`. Shorter holes are tolerated;
the affected 15m bucket simply contains fewer than 15 minutes, and its bar
count is available for auditing.

### C-04 — Duplicate timestamps: identical rows deduplicated, conflicting rows dropped and counted
**Impact: low-medium.** A conflicting duplicate means the vendor disagrees with
itself. The first is kept and `duplicates_conflicting` is reported. If that
count is non-zero, fix the data rather than trusting the run.

### C-05 — Rows failing `low ≤ open,close ≤ high` are dropped and counted
**Impact: low.** Malformed bars are excluded rather than repaired.

### C-06 — The DST rule is the post-2007 US rule, hard-coded
**Impact: medium.** Second Sunday of March to first Sunday of November. Correct
for 2007 onward. **It will be wrong if the US abolishes DST**, and it is wrong
for pre-2007 history. Cross-checked against `zoneinfo` every 3 hours from 2024
to 2028 in the test suite.

### C-07 — Exchange holidays are not enumerated
**Impact: low.** No holiday calendar is hard-coded. Holidays are handled
structurally: a date with no RTH bars is skipped (A-03), a short date fails the
completeness test (A-02). This means the system never disagrees with the data
about whether a session happened.

---

## D. Platform assumptions

### D-01 — Studio runs a standard-enough Backtrader that `self.buy()`, `self.sell()`, `self.close()`, `self.position` and `notify_order` behave conventionally
**Impact: high.** Only this minimal surface is used. No brackets, no OCO, no
`exectype`, no custom `CommInfo`, no `resampledata`.

### D-02 — Studio's Python has no third-party packages beyond Backtrader
**Impact: medium.** Nothing outside the standard library is imported — no
pandas, no numpy, no pytz, not even `zoneinfo`. Cost: date arithmetic is
implemented by hand. Benefit: the file cannot fail to import.

### D-03 — The strategy's own exit logic is the only protection
**Impact: high for live trading, low for backtesting.** With no documented
native stop-loss (C-3 in the README), a disconnect or an app close leaves a
position unprotected. **Do not run this live without an independent broker-side
stop**, or without first confirming Studio supports attaching one.

### D-04 — `self.p.<name>` reads work with dict-style `params`
**Impact: high — this one is load-bearing.** Backtrader's `AutoInfoClass`
exposes dict params as attributes, and Studio's own published bots rely on it.
If a paste fails at `__init__`, this is the first thing to check.

### D-05 — Studio passes exactly one data feed at the UI-selected resolution
**Impact: high.** `self.datas[0]` is assumed to be the 1-minute series. Running
the bot at any other resolution silently changes what a "15-minute bucket"
means. Run it at 1 minute.

---

## E. Known limitations of the evidence

### E-01 — No real multi-session US30 backtest has been run
The only real 1-minute US30 file available here is 99 bars of one partial
session. No expectancy, win rate or profit factor for the real Dow appears
anywhere in this package, because producing one would have required inventing
data.

### E-02 — Synthetic results describe the generator
Every number from `--self-test` comes from a random-walk-plus-drift generator.
Changing its seed moved zero-cost expectancy from −0.18 R to +0.10 R at ~120
sessions. They demonstrate that the pipeline runs; they say nothing about
markets.

### E-03 — The negative control bounds the direction of bias, not its size
`--mode control` shows the harness does not invent edge on noise (−0.0796 R
over 1,784 zero-cost trades, negative on all 12 seeds). It does **not** prove
the cost model matches your broker, only that the mechanics are not
optimistically biased.

### E-04 — Nothing has been reconciled against an execution feed
No reference broker feed has been selected, so no parity claim is made between
any research dataset and the prices Studio will actually fill against.
