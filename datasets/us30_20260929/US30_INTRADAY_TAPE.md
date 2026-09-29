# LANE 2 - US30 / DOW INTRADAY MULTI-TIMEFRAME TAPE

**Instrument captured:** `^DJI` - Dow Jones Industrial Average (cash index, USD)  
**Capture window:** 2026-09-29T19:38:57Z - 2026-09-29T19:40:11Z (all five feeds snapshotted inside a ~75 second window)  
**Dataset built:** 2026-09-29T19:51:20Z  
**Timeframes:** 1m (native), 3m (derived - no native feed), 5m / 15m / 30m (native)  
**Primary source:** Yahoo Finance chart API v8 · **Cross-check source:** CNBC Quote Cache (exchange feed, realTime=true) · **Quote-level corroboration:** Trading Economics, Investing.com

> Scope discipline: only bar range, body, wicks, close-to-close return, range position and fractal local swing highs/lows are computed. No smoothed or parameterised indicator is produced, because no source published verified indicator values. Nothing in this dataset is modelled, back-filled or estimated.

---

## 1. VERIFIED

Every value below is read directly from a captured source payload in `raw/`.

### 1.1 Instrument, timestamp & timezone

| Field | Value | Source |
|---|---|---|
| Symbol | `^DJI` | Yahoo chart meta |
| Name | Dow Jones Industrial Average | Yahoo / CNBC |
| Instrument type | INDEX (cash index, not a CFD or future) | Yahoo `instrumentType`, CNBC `subType` |
| Currency | USD | Yahoo chart meta |
| Exchange timezone | America/New_York (EDT, UTC-4) | Yahoo chart meta |
| Snapshot time (UTC) | 2026-09-29T19:38:57Z | Yahoo `regularMarketTime` |
| Snapshot time (exchange local) | 2026-09-29 15:38:57 EDT | Yahoo `regularMarketTime` + `gmtoffset` |
| Cross-source snapshot time | 2026-09-29T15:41:41.000-0400 | CNBC `last_time` |
| Bar timestamp convention | Bar **open** time (left-edge), epoch seconds | Yahoo chart API |

### 1.2 Session status

| Field | Value |
|---|---|
| State | **REGULAR_SESSION_OPEN** |
| Regular session (UTC) | 2026-09-29T13:30:00Z -> 2026-09-29T20:00:00Z |
| Regular session (ET) | 2026-09-29 09:30:00 EDT -> 2026-09-29 16:00:00 EDT |
| Elapsed | 368.9 min (94.6% of RTH) |
| Remaining to close | 21.1 min |
| Halt status | N (CNBC `EventData.is_halted`) |
| Market status flag | `REG_MKT` (CNBC) |
| Pre/post-market bars | Not published for this index (`hasPrePostMarketData: false`) |

### 1.3 Session price & volume facts

| Field | Yahoo | CNBC (exchange feed) | Agreement |
|---|---|---|---|
| Previous close (2026-09-28) | 51,481.51 | 51,481.51 | exact |
| Session open | 51,416.96 | 51,416.96 | exact |
| Session high | 51,505.19 | 51,505.19 | exact |
| Session low | 51,129.18 | 51,129.18 | exact |
| Last price | 51,359.71 (latest feed snapshot 2026-09-29T19:40:11Z) | 51,358.67 | 1.04 pts apart, snapshots ~1.5 min apart |
| Cumulative volume | 256,003,045 | 258,026,708 | later snapshot is higher, as expected |
| 52-week high | 54,744.33 | 54,744.33 (08/05/26) | exact |
| 52-week low | 45,057.28 | 45,057.28 (03/30/26) | exact |

Each timeframe feed was fetched as its own request, so each carries its own snapshot instant. The dispersion below is live-tape latency, not disagreement:

| Feed | Vendor snapshot (UTC) | Last price | Cumulative volume |
|---|---|---|---|
| 1m | 2026-09-29T19:39:44Z | 51,361.17 | 256,517,137 |
| 3m | n/a (derived series - inherits the 1m capture) | - | - |
| 5m | 2026-09-29T19:38:57Z | 51,363.44 | 256,003,045 |
| 15m | 2026-09-29T19:40:11Z | 51,359.71 | 256,873,422 |
| 30m | 2026-09-29T19:38:45Z | 51,364.33 | 255,838,133 |
| CNBC | 2026-09-29T19:41:41Z | 51,358.67 | 258,026,708 |

Spread across all captured snapshots: 5.66 pts over ~3 minutes of wall clock.

### 1.4 Bar inventory per timeframe

| TF | Origin | Completed bars | First bar (UTC) | Last completed bar (UTC) | Sessions covered |
|---|---|---|---|---|---|
| 1m | VERIFIED | 99 | 2026-09-29T18:00:00Z | 2026-09-29T19:38:00Z | 1 (2026-09-29) |
| 3m | DERIVED | 33 | 2026-09-29T18:00:00Z | 2026-09-29T19:36:00Z | 1 (2026-09-29) |
| 5m | VERIFIED | 73 | 2026-09-29T13:30:00Z | 2026-09-29T19:30:00Z | 1 (2026-09-29) |
| 15m | VERIFIED | 50 | 2026-09-28T13:30:00Z | 2026-09-29T19:15:00Z | 2 (2026-09-28 .. 2026-09-29) |
| 30m | VERIFIED | 64 | 2026-09-23T13:30:00Z | 2026-09-29T19:00:00Z | 5 (2026-09-23 .. 2026-09-29) |

### 1.5 Latest completed bar - OHLCV per timeframe

| TF | Bar open (UTC) | Bar open (ET) | Open | High | Low | Close | Volume |
|---|---|---|---|---|---|---|---|
| 1m | 2026-09-29T19:38:00Z | 2026-09-29 15:38:00 | 51,357.65 | 51,364.75 | 51,356.96 | 51,363.93 | 1,047,474 |
| 3m | 2026-09-29T19:36:00Z | 2026-09-29 15:36:00 | 51,352.34 | 51,364.75 | 51,350.73 | 51,363.93 | 2,546,408 |
| 5m | 2026-09-29T19:30:00Z | 2026-09-29 15:30:00 | 51,367.59 | 51,384.27 | 51,353.67 | 51,356.13 | 3,593,117 |
| 15m | 2026-09-29T19:15:00Z | 2026-09-29 15:15:00 | 51,356.77 | 51,375.49 | 51,341.58 | 51,367.17 | 9,698,199 |
| 30m | 2026-09-29T19:00:00Z | 2026-09-29 15:00:00 | 51,346.11 | 51,375.49 | 51,338.38 | 51,367.17 | 18,040,154 |

### 1.6 Current (in-progress) bar - OHLC per timeframe

These bars were **not** closed at capture time. They are reported separately and are excluded from every derived structure calculation.

| TF | Bar open (UTC) | Open | High | Low | Close so far | Volume so far | Status |
|---|---|---|---|---|---|---|---|
| 1m | 2026-09-29T19:39:00Z | - | - | - | - | - | in-flight bucket 19:39:00Z returned **null** by vendor - see MISSING |
| 3m | 2026-09-29T19:39:00Z | - | - | - | - | - | in-flight bucket 19:39:00Z returned **null** by vendor - see MISSING |
| 5m | 2026-09-29T19:35:00Z | 51,356.09 | 51,362.14 | 51,350.08 | 51,357.29 | 2,352,569 | INCOMPLETE |
| 15m | 2026-09-29T19:30:00Z | 51,367.59 | 51,384.27 | 51,350.08 | 51,356.30 | 7,672,580 | INCOMPLETE |
| 30m | 2026-09-29T19:30:00Z | 51,367.59 | 51,384.27 | 51,350.08 | 51,357.29 | 5,945,686 | INCOMPLETE |

### 1.7 Verification results

| Check | Result | Status |
|---|---|---|
| cross-timeframe session volume reconciliation (5m vs 15m vs 30m, common cutoff) | 5m=234,835,131 / 15m=234,835,131 / 30m=234,835,131 (cutoff 2026-09-29T19:30:00Z) | PASS |
| headline regularMarketVolume vs sum of 5m bar volumes | bars=240,780,817 vs headline=256,003,045 → residual 15,222,228 (5.9461%) | FLAG (documented divergence - do not treat the two as interchangeable) |
| 1m aggregation reproduces native 5m OHLC (overlap window) | 19/19 bars reproduce exactly | PASS |
| 1m volume sum vs native 5m volume sum (same window) | 18/19 5m buckets match to the share; residual 1,414,577 fully attributed to one zero-volume minute | FLAG (attributable to zero-volume 1m bar(s) below) |
| 15m aggregation reproduces native 30m OHLC+volume | 25/25 bars reproduce exactly | PASS |
| session high/low from 5m tape vs vendor regularMarketDayHigh/Low | tape 51,505.19/51,129.18 vs vendor 51,505.19/51,129.18 | PASS |
| cross-source session OHL (Yahoo tape vs CNBC exchange feed) | open/high/low/prev-close all match to the cent | PASS |
| derived change (last - previousClose) vs vendor fulldayChange field | max deviation 0.004 pts across 4 feeds | PASS |
| last price agreement across sources (different snapshot instants) | 2.5 pts (0.0049%) | PASS (within live-tape latency tolerance) |

Per-timeframe integrity checks (OHLC internal consistency, contiguity, zero-volume scan) are stored in full in `dataset_summary.json`. All timeframes pass OHLC consistency and intra-session contiguity with zero violations.

---

## 2. DERIVED

### 2.1 Formulas used (complete list)

```text
range_pts          = high - low
body_pts           = close - open
upper_wick_pts     = high - max(open, close)
lower_wick_pts     = min(open, close) - low
close_pos_in_range = (close - low) / (high - low)      # 0 = bar low, 1 = bar high
ret_pts            = close - close[previous bar]
ret_pct            = (close / close[previous bar] - 1) * 100
direction          = UP if close > open, DOWN if close < open, else FLAT

swing high at bar i  <=>  high[i] > high[i-j] AND high[i] > high[i+j]  for j = 1..2
swing low  at bar i  <=>  low[i]  < low[i-j]  AND low[i]  < low[i+j]   for j = 1..2
   (fractal, k=2; the last 2 bars of each series can never be confirmed)

3m bar = clock-aligned aggregation of exactly three native 1m bars:
   open = first 1m open, high = max(1m highs), low = min(1m lows),
   close = last 1m close, volume = sum(1m volumes)
```

### 2.2 Session-level derived metrics

Computed from verified fields only. `last` is the most recent captured snapshot (51,359.71 at 2026-09-29T19:40:11Z); prev close = 51,481.51; session O/H/L = 51,416.96 / 51,505.19 / 51,129.18.

| Metric | Value | Formula |
|---|---|---|
| Session range | 376.01 pts | session_high - session_low |
| Change vs previous close | -121.80 pts (-0.2366%) | last - prev_close |
| Change vs session open | -57.25 pts | last - session_open |
| Position of last in session range | 0.6131 | (last - session_low) / session_range |
| Distance to session high | 145.48 pts | session_high - last |
| Distance to session low | 230.53 pts | last - session_low |

### 2.3 Latest completed bar - derived metrics

| TF | Range (pts) | Body (pts) | Return (pts) | Return (%) | Close pos in range | Direction |
|---|---|---|---|---|---|---|
| 1m | 7.79 | +6.28 | +6.64 | +0.0129% | 0.8947 | UP |
| 3m | 14.02 | +11.59 | +11.66 | +0.0227% | 0.9415 | UP |
| 5m | 30.60 | -11.46 | -11.04 | -0.0215% | 0.0803 | DOWN |
| 15m | 33.91 | +10.40 | +11.27 | +0.0220% | 0.7548 | UP |
| 30m | 37.11 | +21.06 | +21.12 | +0.0411% | 0.7759 | UP |

### 2.4 Swing structure per timeframe (fractal k=2, completed bars only)

| TF | Confirmed swings (H/L) | Last swing high | Last swing low | High seq | Low seq | Structure label |
|---|---|---|---|---|---|---|
| 1m | 12/9 | 51,384.27 @ 19:33Z | 51,350.08 @ 19:35Z | HIGHER_HIGH | HIGHER_LOW | **UPTREND (HH+HL)** |
| 3m | 4/5 | 51,375.49 @ 19:21Z | 51,349.66 @ 19:27Z | LOWER_HIGH | HIGHER_LOW | **MIXED (LOWER_HIGH+HIGHER_LOW)** |
| 5m | 11/10 | 51,380.38 @ 18:40Z | 51,341.58 @ 19:15Z | HIGHER_HIGH | HIGHER_LOW | **UPTREND (HH+HL)** |
| 15m | 6/4 | 51,380.38 @ 18:30Z | 51,150.40 @ 17:00Z | HIGHER_HIGH | HIGHER_LOW | **UPTREND (HH+HL)** |
| 30m | 8/7 | 51,780.50 @ 17:00Z | 51,129.18 @ 16:00Z | LOWER_HIGH | LOWER_LOW | **DOWNTREND (LH+LL)** |

`structure_label` is a mechanical comparison of the last two confirmed swing highs and the last two confirmed swing lows - it is arithmetic, not a trade opinion.

### 2.5 Most recent confirmed swing points

**1m** (last 6 of 21 confirmed)

| Time (UTC) | Time (ET) | Type | Price |
|---|---|---|---|
| 2026-09-29T19:18:00Z | 2026-09-29 15:18:00 | SWING_LOW | 51,341.58 |
| 2026-09-29T19:20:00Z | 2026-09-29 15:20:00 | SWING_HIGH | 51,373.21 |
| 2026-09-29T19:23:00Z | 2026-09-29 15:23:00 | SWING_HIGH | 51,375.49 |
| 2026-09-29T19:29:00Z | 2026-09-29 15:29:00 | SWING_LOW | 51,349.66 |
| 2026-09-29T19:33:00Z | 2026-09-29 15:33:00 | SWING_HIGH | 51,384.27 |
| 2026-09-29T19:35:00Z | 2026-09-29 15:35:00 | SWING_LOW | 51,350.08 |

**3m** (last 6 of 9 confirmed)

| Time (UTC) | Time (ET) | Type | Price |
|---|---|---|---|
| 2026-09-29T18:30:00Z | 2026-09-29 14:30:00 | SWING_LOW | 51,250.88 |
| 2026-09-29T18:39:00Z | 2026-09-29 14:39:00 | SWING_HIGH | 51,380.38 |
| 2026-09-29T18:57:00Z | 2026-09-29 14:57:00 | SWING_LOW | 51,323.15 |
| 2026-09-29T19:18:00Z | 2026-09-29 15:18:00 | SWING_LOW | 51,341.58 |
| 2026-09-29T19:21:00Z | 2026-09-29 15:21:00 | SWING_HIGH | 51,375.49 |
| 2026-09-29T19:27:00Z | 2026-09-29 15:27:00 | SWING_LOW | 51,349.66 |

**5m** (last 6 of 21 confirmed)

| Time (UTC) | Time (ET) | Type | Price |
|---|---|---|---|
| 2026-09-29T18:05:00Z | 2026-09-29 14:05:00 | SWING_HIGH | 51,298.08 |
| 2026-09-29T18:20:00Z | 2026-09-29 14:20:00 | SWING_HIGH | 51,311.90 |
| 2026-09-29T18:30:00Z | 2026-09-29 14:30:00 | SWING_LOW | 51,250.88 |
| 2026-09-29T18:40:00Z | 2026-09-29 14:40:00 | SWING_HIGH | 51,380.38 |
| 2026-09-29T18:55:00Z | 2026-09-29 14:55:00 | SWING_LOW | 51,323.15 |
| 2026-09-29T19:15:00Z | 2026-09-29 15:15:00 | SWING_LOW | 51,341.58 |

**15m** (last 6 of 10 confirmed)

| Time (UTC) | Time (ET) | Type | Price |
|---|---|---|---|
| 2026-09-29T15:15:00Z | 2026-09-29 11:15:00 | SWING_LOW | 51,132.76 |
| 2026-09-29T15:45:00Z | 2026-09-29 11:45:00 | SWING_HIGH | 51,255.33 |
| 2026-09-29T16:00:00Z | 2026-09-29 12:00:00 | SWING_LOW | 51,129.18 |
| 2026-09-29T16:45:00Z | 2026-09-29 12:45:00 | SWING_HIGH | 51,206.10 |
| 2026-09-29T17:00:00Z | 2026-09-29 13:00:00 | SWING_LOW | 51,150.40 |
| 2026-09-29T18:30:00Z | 2026-09-29 14:30:00 | SWING_HIGH | 51,380.38 |

**30m** (last 6 of 15 confirmed)

| Time (UTC) | Time (ET) | Type | Price |
|---|---|---|---|
| 2026-09-25T17:30:00Z | 2026-09-25 13:30:00 | SWING_LOW | 51,710.15 |
| 2026-09-25T19:30:00Z | 2026-09-25 15:30:00 | SWING_HIGH | 51,874.94 |
| 2026-09-28T13:30:00Z | 2026-09-28 09:30:00 | SWING_LOW | 51,412.12 |
| 2026-09-28T15:00:00Z | 2026-09-28 11:00:00 | SWING_LOW | 51,409.65 |
| 2026-09-28T17:00:00Z | 2026-09-28 13:00:00 | SWING_HIGH | 51,780.50 |
| 2026-09-29T16:00:00Z | 2026-09-29 12:00:00 | SWING_LOW | 51,129.18 |

Full swing lists: `swings_<tf>.csv`. Full bar tapes with all derived columns: `bars_<tf>.csv`.

### 2.6 Multi-timeframe alignment

- Timeframes labelled UPTREND (HH+HL): 1m, 5m, 15m
- Timeframes labelled DOWNTREND (LH+LL): 30m
- Timeframes labelled MIXED: 3m

This is a count of mechanical labels across timeframes. It is intentionally not converted into a bias, signal or recommendation.

---

## 3. MISSING

Items that were requested or would normally belong in this dataset but could **not** be sourced. None of these were estimated, modelled or filled in.

### 3.1 Unavailable feeds / instruments

| Item | Status | Why |
|---|---|---|
| Native **3m** bars | MISSING (substituted by a labelled derivation) | The vendor's `validRanges` for `^DJI` expose 1m/2m/5m/15m/30m/60m/90m/1d+ only. 3m is aggregated from native 1m bars and tagged `origin=DERIVED` in every output row. |
| Broker **US30 CFD** bar tape | MISSING | 'US30' is usually a broker CFD on the Dow. No broker/CFD bar feed was reachable. Only quote-level CFD prints were captured (Trading Economics 51,363 / Investing.com 51,379.60) and they are recorded as corroboration, not merged into the bar tape. The CFD-vs-cash basis is therefore unquantified. |
| **YM futures** (CME) tape | MISSING | Not captured in this lane; no futures basis, roll or open-interest data is present. |
| Bid/ask, spread, tick data, order flow | MISSING | Chart APIs return OHLCV only. No quote-level depth, no trade-by-trade prints, no bid/ask spread. |
| Pre-market / post-market bars | MISSING | `hasPrePostMarketData: false` for this index. |

### 3.2 Indicator values

| Item | Status |
|---|---|
| RSI, MACD, stochastics, moving averages, ATR, Bollinger bands | MISSING - no source published verified values, and the lane brief restricts derivation to transparent bar metrics. Not computed, not invented. |
| Session VWAP | MISSING - not published by any captured source. It could be approximated from bar typical prices, but that is an assumption-laden reconstruction rather than a verified value, so it is deliberately omitted. |
| Volume profile / POC / value area | MISSING - requires tick or price-level volume that no captured source provides. |

### 3.3 Data gaps and unresolved discrepancies inside what was captured

| Item | Detail |
|---|---|
| 1m bar 2026-09-29T19:39:00Z (in-flight) | Vendor returned **null** OHLC for this bucket at capture time, so the current 1m bar has no values. Excluded, not interpolated. |
| 3m current bar | Cannot be formed: the in-flight 3m bucket (19:39:00Z) had only one elapsed 1m member and that member was the null bar above. No current 3m OHLC exists. |
| 1m volume at 2026-09-29T18:00:00Z | Vendor returned `volume=0` on the first 1m bar of the `period1`-clipped window while its OHLC is valid and agrees with the 5m tape. Treated as MISSING volume, not as zero volume. Accounts for the 1,414,577 share (2.6731%) gap between the 1m and 5m volume sums (18/19 5m buckets reconcile to the share). The missing minute's volume is *implied* to be 1,414,577 by subtraction, but that inference is deliberately **not** written into the 1m tape. |
| Headline vs bar-level volume | Headline `regularMarketVolume` (256,003,045) exceeds the sum of bar volumes (240,780,817) by 15,222,228 shares (5.9461%). The divergence is identical across 5m/15m/30m, so it is a vendor aggregation difference. **No source explains it, so it is left unreconciled.** |
| 1m / 3m history depth | Only 2026-09-29T18:00Z onward was captured (99 completed 1m bars). Earlier 1m history exists at the vendor but was not pulled in this capture, so 1m/3m swing structure is scoped to that window. |
| 15m history depth | 2 RTH sessions (2026-09-28, 2026-09-29). 30m covers 5 sessions. |
| Swing confirmation lag | With k=2, the last 2 completed bars of every timeframe cannot yet be confirmed as swing points. Any swing forming there is genuinely unknown, not absent. |
| Session close | The 2026-09-29 RTH close had not occurred at capture (21.1 min remaining), so the daily close, final volume and the final shape of every in-progress bar are unknown. |

---

## 4. Files

| File | Contents |
|---|---|
| `raw/yahoo_dji_{1m,5m,15m,30m}.json` | Verbatim vendor payloads (arrays, nulls and meta preserved) |
| `raw/cross_source_quotes.json` | CNBC / Trading Economics / Investing.com cross-checks + agreement matrix |
| `bars_{1m,3m,5m,15m,30m}.csv` | Bar tape + derived columns + `bar_status` + `origin` |
| `swings_{1m,3m,5m,15m,30m}.csv` | Confirmed fractal swing points (k=2) |
| `dataset_summary.json` | Machine-readable summary: session, per-TF bars, structure, all checks |
| `../../scripts/build_us30_intraday_dataset.py` | Raw → dataset builder (validation + derivation) |
| `../../scripts/render_us30_report.py` | Dataset → this report |

