# LANE 7 — US30 / Dow: Market Structure & Liquidity

**Generated:** 2026-09-29. ^DJI bars run **09:30–15:59 ET** (390 one-minute bars) — the **regular session is COMPLETE** (09:30–16:00 ET); the 16:00 closing auction print is captured separately at **51,350.99**.

YM=F futures bars run Mon 18:00 → Tue 15:50 ET; the Globex session continues past the cash close, so the futures picture below is current only to 15:50.

---

## 0. Instrument, data provenance, and what the data can/cannot support

### 0.1 Which "US30"?

"US30" is a broker CFD label, not an exchange instrument. There is no canonical US30 tape. This analysis is therefore run on the two instruments that a US30 quote is derived from, **kept strictly separate**:

| Role | Symbol | What it is | Last | Source |
|---|---|---|---|---|
| Cash index | `^DJI` | Dow Jones Industrial Average, price-weighted computed index | 51,350.99 (official close) | Yahoo `/v8/finance/chart` |
| Futures | `YM=F` | Mini Dow Jones Indus.-$5 Dec 26 (CBOT), 23h Globex | 51,717 (last bar 15:50) | Yahoo `/v8/finance/chart` |

**Observed basis near the cash close: YM − DJI = +354 points.** Futures levels and cash levels are **not interchangeable** and are never mixed below. A broker US30 feed will sit near one of these two, offset by that broker's own spread/financing — translate levels, do not copy them.

### 0.2 Capture and integrity

The analysis host has an allowlisted network (no market-data egress), so payloads were captured out-of-band and stored verbatim in `data/raw/`. Because hand-capture can corrupt digits, the capture is proved before any level is quoted, via `engine/lane7_verify.py`:

> The 390 one-minute bars (8 separate windowed requests) are resampled to 5 minutes and compared
> against a **separately downloaded** 5-minute payload. All 74 overlapping bars match on
> open/high/low/close with `max_abs_diff = 0.0000000000`. Session high/low/open also reconcile to
> Yahoo's independent `regularMarketDayHigh` / `regularMarketDayLow` / open meta fields, and YM's
> day high/low reconcile to its own meta.

Two independent downloads agreeing to the tick is the evidence that the numbers below are real. Re-run `python -m engine.lane7_verify` to reproduce.

| Payload | Symbol | TF | Bars | Coverage (ET) |
|---|---|---|---|---|
| `DJI_1m_s1..s7 + patch` | ^DJI | 1m | 390 | 09:30–15:59 (full RTH) |
| `DJI_5m_1d.json` (verification counterpart) | ^DJI | 5m | 74 | 09:30–15:35 |
| 5m used for analysis = resample of the 1m above | ^DJI | 5m | 78 | 09:30–15:55 |
| `DJI_30m_5d.json` | ^DJI | 30m | 65 | 09-23 → 09-29 |
| `DJI_1d_1mo.json` | ^DJI | 1d | 21 | 08-31 → 09-29 |
| `YM_5m_on_a/on_b/rth` | YM=F | 5m | 263 | Mon 18:00 → Tue 15:50 |
| `YM_1d_1mo.json` | YM=F | 1d | 21 | 08-31 → 09-29 |

### 0.3 Hard limits — what these bars CANNOT establish

1. **No order-book, no tape, no bid/ask, no delta.** Only OHLCV. Every "liquidity" statement below is an inference from *price geometry* (a level was exceeded and price returned), never from observed resting orders. Absorption, spoofing, iceberg fills, and delta divergence are **not testable here**.
2. **`^DJI` has no liquidity of its own.** It is a computed average of 30 constituent last-trade prices. There are no stops resting "at" 51,129 on the index. Cash-index wicks are an *artifact of the averaging*, not a stop run. **Sweep claims are therefore made on `YM=F`, where the book actually is, and the cash index is used only for corroboration.**
3. **Session scope.** The cash session is closed, so ^DJI statements are final for 2026-09-29. The futures picture is NOT final — YM Globex runs to 17:00 ET and my last YM bar is 15:50, so any futures level can still be revisited tonight.
4. **Volume caveats.** `^DJI` volume is summed constituent share volume — usable for *relative* activity only. Yahoo's `YM=F` volume is known to be partial (it reports 67,774 contracts for a full Globex day, which is implausibly low for the front Dow contract). **No conclusion below depends on YM volume.**
5. **1-minute volume has a known source artifact.** Yahoo zeroes the first bar of every `period1/period2` window; 7 bars (09:30, 10:44, 10:45, 13:12, 14:26, 15:13, 15:38) carry `volume=0`. *Prices on those bars are verified correct* by the redundancy check. All volume statements use the `range=1d` 5-minute payload instead.
6. **Closing-auction snapshot excluded from the bar series.** Yahoo emits the official close as a grid-aligned 16:00 row with `open==high==low==close==51,350.99` and `volume=0`. That is a settlement print, not a traded minute, and leaving it in manufactures a phantom 3-bar FVG. It is removed from all detectors (rule: flat OHLC **and** zero volume) and reported separately as the close.
7. **Futures daily bars are ET calendar-day buckets, not 18:00–17:00 exchange sessions.** Verified by reconciliation: my 5-minute YM bars grouped by ET date give 52002/51459 for 09-29, exactly matching the daily payload. Prior-day futures levels below are therefore labelled "ET calendar day".

### 0.4 Detector definitions and parameters

All events come from `engine/lane7_structure.py`. Definitions are mechanical:

| Event | Definition |
|---|---|
| Swing (fractal) | high beats all *k* bars each side (strict). `*` = edge pivot, provisional. |
| FVG / imbalance | 3-bar gap: bullish `low[i] > high[i-2]`; bearish `high[i] < low[i-2]`. Fill measured by later bars re-entering the band. |
| Displacement | run of ≤ *maxbars* with \|net\| ≥ *mult* × ATR(n) measured **before** the run, directional efficiency ≥ 0.70, **and** containing a same-direction FVG. |
| SWEEP | wick pierces level, **same bar closes back inside**, stays inside for *confirm* bars. |
| FAILED BREAK | ≥1 bar **closes** beyond level, then closes back inside within *confirm* bars. |
| BREAK+HOLD | closes beyond and is still beyond after *confirm* bars. |
| RECLAIM | ≥ *away* closes on the wrong side, then a close back that holds *hold* bars. |
| Consolidation | *window*-bar stretch with Kaufman ER ≤ *er_max* **and** range ≤ *range_atr* × ATR. |
| BOS / CHoCH | close beyond the last confirmed swing (pivot only usable *k* bars after it prints — no look-ahead). |

Parameters used: `swing_k_5m=3, swing_k_1m=5, disp_atr_n_5m=14, disp_mult_5m=2.0, disp_maxbars_5m=5, disp_er=0.7, disp_atr_n_1m=30, disp_mult_1m=2.5, disp_maxbars_1m=10, fvg_min_5m=5.0, fvg_min_1m=10.0, cons_window=12, cons_er_max=0.25, cons_range_atr=2.5, confirm_bars=6, reclaim_away=5, reclaim_hold=5`

---

# PART A — VERIFIED OBSERVATIONS

Everything in Part A is a direct arithmetic consequence of the captured bars. Each row names the bar, the level, the timeframe and the payload.

## A1. Reference levels (with provenance)

**^DJI cash**

| Level | Price | Source |
|---|---:|---|
| PDH  (prior day high, 09-28) | 51,780.50 | DJI_1d_1mo.json bar 19 |
| PDC  (prior day close, 09-28) | 51,481.51 | DJI_1d_1mo.json bar 19 |
| PDL  (prior day low, 09-28) | 51,409.65 | DJI_1d_1mo.json bar 19 |
| RTH open (today) | 51,416.96 | DJI 1m 09:30 open |
| IB high (09:30-10:30) | 51,505.19 | DJI 1m 09:30-10:29 |
| IB low  (09:30-10:30) | 51,325.58 | DJI 1m 09:30-10:29 |
| HOD (today) | 51,505.19 | DJI 1m 09:42 |
| LOD (today) | 51,129.18 | DJI 1m 12:02 |
| RTH close (official print) | 51,350.99 | Yahoo 16:00 close snapshot |
| 09-24 swing low (daily) | 51,124.02 | DJI_1d_1mo.json bar 17 |
| 09-16 swing low (daily) | 51,186.67 | DJI_1d_1mo.json bar 11 |

**YM=F futures (Dec-26)**

| Level | Price | Source |
|---|---:|---|
| ON high (Globex 18:00-09:30) | 52,002 | YM 5m Tue 08:00 |
| ON low  (Globex 18:00-09:30) | 51,644 | YM 5m Tue 01:35 |
| Prev close - upside test | 51,837 | YM meta chartPreviousClose |
| Prev close - downside acceptance | 51,837 | YM meta chartPreviousClose |
| 09-24 low (ET calendar day) | 51,479 | YM_1d_1mo.json bar 17 |
| 09-28 low (ET calendar day) | 51,744 | YM_1d_1mo.json bar 19 |
| RTH low (today) | 51,459 | YM 5m 12:00 |
| RTH high (today) | 51,848 | YM 5m 09:40 |

## A2. Session skeleton (^DJI, 1m + 5m)

- **RTH open** 51,416.96 at 09:30 — opened **below** PDC 51,481.51 and **above** PDL 51,409.65.
- **HOD 51,505.19 at 09:42** (1m bar, `DJI_1m_s1.json`; confirmed on 5m bar 2 09:40 high 51,505.19).
- **LOD 51,129.18 at 12:02** (1m bar; confirmed on 5m bar 30 12:00 low 51,129.18).
- **Session range: 376.01 points** (0.74%). Time from HOD to LOD: 140 minutes.
- **Initial Balance (09:30–10:30, 5m bars 0–11): 51,325.58 – 51,505.19** (height 179.61). The IB low was broken at 10:30+ and the session low printed 51,129.18, i.e. an **IB-low breakout day**; the IB high was never revisited after 09:42.
- **Official close 51,350.99** (16:00 auction print, `regularMarketPrice`), -130.52 vs PDC — closed **back above** the IB low (+25.41) but 154.20 pts below the IB high, and +221.81 pts off the session low.
- **Close location in range: 59.0%** of the 376.01-pt session range — upper-middle, i.e. the day closed nearer its high than its low despite being a net down day.

## A3. Confirmed swing points

**^DJI 5m, k=3** (^DJI 5m (resampled from verified 1m)):

| # | Type | Bar | Time | Price |
|---|---|---:|---|---:|
| 0 | Swing Low (edge, provisional) | 0 | 09:30 | 51,353.63 |
| 1 | Swing High (edge, provisional) | 2 | 09:40 | 51,505.19 |
| 2 | Swing Low | 22 | 11:20 | 51,132.76 |
| 3 | Swing High | 27 | 11:45 | 51,255.33 |
| 4 | Swing Low | 30 | 12:00 | 51,129.18 |
| 5 | Swing High | 40 | 12:50 | 51,206.10 |
| 6 | Swing Low | 44 | 13:10 | 51,150.40 |
| 7 | Swing Low | 53 | 13:55 | 51,200.11 |
| 8 | Swing Low | 60 | 14:30 | 51,250.88 |
| 9 | Swing High | 62 | 14:40 | 51,380.38 |
| 10 | Swing Low | 65 | 14:55 | 51,323.15 |
| 11 | Swing High | 72 | 15:30 | 51,384.27 |
| 12 | Swing Low (edge, provisional) | 75 | 15:45 | 51,341.93 |
| 13 | Swing High (edge, provisional) | 77 | 15:55 | 51,381.48 |

^DJI 1m k=5 produced 49 pivots (see `bars_dji_1m.csv`).

*Edge pivots* are the first and last extremes: they lack 3 confirming bars on one side, so they are reported but never used to trigger a BOS/CHoCH in A9. With the session closed, the trailing edge pivots can no longer be confirmed on cash at all — nothing trades until 09:30 tomorrow.

## A4. Displacement legs

### ^DJI 5m

| kind              | tf   |   bar | time   | source                               | from_bar   | to_bar   |   bars |    open |   close |   net_pts |   atr_ref |   atr_mult |   efficiency |
|:------------------|:-----|------:|:-------|:-------------------------------------|:-----------|:---------|-------:|--------:|--------:|----------:|----------:|-----------:|-------------:|
| displacement_down | 5m   |    18 | 11:00  | ^DJI 5m (resampled from verified 1m) | 11:00      | 11:20    |      5 | 51274.4 | 51149.3 |   -125.08 |     56.05 |       2.23 |         1    |
| displacement_up   | 5m   |    46 | 13:20  | ^DJI 5m (resampled from verified 1m) | 13:20      | 13:40    |      5 | 51177.2 | 51243.4 |     66.24 |     25.2  |       2.63 |         1    |
| displacement_up   | 5m   |    53 | 13:55  | ^DJI 5m (resampled from verified 1m) | 13:55      | 14:00    |      2 | 51209.3 | 51279.6 |     70.33 |     26.15 |       2.69 |         1    |
| displacement_up   | 5m   |    56 | 14:10  | ^DJI 5m (resampled from verified 1m) | 14:10      | 14:20    |      3 | 51223.1 | 51288.9 |     65.78 |     32.33 |       2.03 |         1    |
| displacement_up   | 5m   |    60 | 14:30  | ^DJI 5m (resampled from verified 1m) | 14:30      | 14:40    |      3 | 51273.6 | 51347.8 |     74.24 |     32.84 |       2.26 |         0.95 |

Reading: the **only** qualifying down-leg of the day is **11:00→11:20, −125.08 pts at 2.23× the pre-leg ATR with efficiency 1.00** (five consecutive lower closes, zero retracement). Everything before it was a *grind*, not displacement — the largest 3-bar down-run in the 09:30–11:00 window reached only ~1.8× ATR, below the 2.0 threshold, because morning ATR was elevated (~56–66 pts). Four qualifying up-legs then cluster between 13:20 and 14:40.

### ^DJI 1m

| kind              | tf   |   bar | time   | source                  | from_bar   | to_bar   |   bars |    open |   close |   net_pts |   atr_ref |   atr_mult |   efficiency |
|:------------------|:-----|------:|:-------|:------------------------|:-----------|:---------|-------:|--------:|--------:|----------:|----------:|-----------:|-------------:|
| displacement_down | 1m   |    45 | 10:15  | ^DJI 1m (DJI_1m_s1..s7) | 10:15      | 10:24    |     10 | 51400.6 | 51331.4 |    -69.2  |     24.38 |       2.84 |         0.74 |
| displacement_down | 1m   |    61 | 10:31  | ^DJI 1m (DJI_1m_s1..s7) | 10:31      | 10:32    |      2 | 51371.2 | 51308.8 |    -62.46 |     21.8  |       2.87 |         1    |
| displacement_down | 1m   |    87 | 10:57  | ^DJI 1m (DJI_1m_s1..s7) | 10:57      | 11:06    |     10 | 51318.7 | 51241   |    -77.75 |     20.17 |       3.85 |         0.74 |
| displacement_down | 1m   |    97 | 11:07  | ^DJI 1m (DJI_1m_s1..s7) | 11:07      | 11:14    |      8 | 51239.2 | 51188.1 |    -51.05 |     18.8  |       2.72 |         0.76 |
| displacement_down | 1m   |   107 | 11:17  | ^DJI 1m (DJI_1m_s1..s7) | 11:17      | 11:23    |      7 | 51203.3 | 51137.1 |    -66.18 |     17.04 |       3.88 |         0.78 |
| displacement_up   | 1m   |   120 | 11:30  | ^DJI 1m (DJI_1m_s1..s7) | 11:30      | 11:39    |     10 | 51154.1 | 51227.9 |     73.87 |     14.76 |       5    |         0.86 |
| displacement_down | 1m   |   140 | 11:50  | ^DJI 1m (DJI_1m_s1..s7) | 11:50      | 11:59    |     10 | 51224.7 | 51155.9 |    -68.81 |     18.24 |       3.77 |         0.97 |
| displacement_up   | 1m   |   172 | 12:22  | ^DJI 1m (DJI_1m_s1..s7) | 12:22      | 12:30    |      9 | 51155.4 | 51192.2 |     36.79 |     12.36 |       2.98 |         0.83 |
| displacement_down | 1m   |   210 | 13:00  | ^DJI 1m (DJI_1m_s1..s7) | 13:00      | 13:03    |      4 | 51193.6 | 51161.8 |    -31.81 |     11.98 |       2.65 |         0.96 |
| displacement_up   | 1m   |   238 | 13:28  | ^DJI 1m (DJI_1m_s1..s7) | 13:28      | 13:37    |     10 | 51185.3 | 51224.9 |     39.58 |     10.65 |       3.72 |         0.74 |
| displacement_down | 1m   |   255 | 13:45  | ^DJI 1m (DJI_1m_s1..s7) | 13:45      | 13:53    |      9 | 51243.6 | 51208.4 |    -35.2  |      9.89 |       3.56 |         0.72 |
| displacement_up   | 1m   |   264 | 13:54  | ^DJI 1m (DJI_1m_s1..s7) | 13:54      | 14:00    |      7 | 51208.5 | 51269.4 |     60.9  |      9.76 |       6.24 |         0.78 |
| displacement_up   | 1m   |   272 | 14:02  | ^DJI 1m (DJI_1m_s1..s7) | 14:02      | 14:06    |      5 | 51249.5 | 51296.2 |     46.74 |     12.39 |       3.77 |         0.82 |
| displacement_down | 1m   |   277 | 14:07  | ^DJI 1m (DJI_1m_s1..s7) | 14:07      | 14:12    |      6 | 51296   | 51231.8 |    -64.19 |     13.46 |       4.77 |         0.79 |
| displacement_up   | 1m   |   283 | 14:13  | ^DJI 1m (DJI_1m_s1..s7) | 14:13      | 14:22    |     10 | 51232.5 | 51311.1 |     78.61 |     15.89 |       4.95 |         1    |
| displacement_down | 1m   |   293 | 14:23  | ^DJI 1m (DJI_1m_s1..s7) | 14:23      | 14:31    |      9 | 51311.9 | 51252.5 |    -59.43 |     16.55 |       3.59 |         0.85 |
| displacement_up   | 1m   |   303 | 14:33  | ^DJI 1m (DJI_1m_s1..s7) | 14:33      | 14:42    |     10 | 51264.8 | 51368.3 |    103.52 |     14.97 |       6.91 |         0.89 |
| displacement_up   | 1m   |   328 | 14:58  | ^DJI 1m (DJI_1m_s1..s7) | 14:58      | 15:06    |      9 | 51327   | 51364.8 |     37.8  |     14.33 |       2.64 |         0.73 |
| displacement_up   | 1m   |   348 | 15:18  | ^DJI 1m (DJI_1m_s1..s7) | 15:18      | 15:23    |      6 | 51342.7 | 51368.2 |     25.42 |      9.44 |       2.69 |         0.87 |
| displacement_up   | 1m   |   358 | 15:28  | ^DJI 1m (DJI_1m_s1..s7) | 15:28      | 15:32    |      5 | 51355.1 | 51383.3 |     28.24 |      9.75 |       2.89 |         0.74 |
| displacement_down | 1m   |   363 | 15:33  | ^DJI 1m (DJI_1m_s1..s7) | 15:33      | 15:37    |      5 | 51382.7 | 51357.3 |    -25.44 |      9.25 |       2.75 |         0.72 |
| displacement_up   | 1m   |   376 | 15:46  | ^DJI 1m (DJI_1m_s1..s7) | 15:46      | 15:47    |      2 | 51346.2 | 51370.6 |     24.39 |      9.73 |       2.51 |         1    |


### YM=F 5m (RTH only)

| kind              | tf   |   bar | time   | source         | from_bar   | to_bar   |   bars |   open |   close |   net_pts |   atr_ref |   atr_mult |   efficiency |
|:------------------|:-----|------:|:-------|:---------------|:-----------|:---------|-------:|-------:|--------:|----------:|----------:|-----------:|-------------:|
| displacement_down | 5m   |    18 | 11:00  | YM_5m_rth.json | 11:00      | 11:20    |      5 |  51615 |   51485 |      -130 |     62.43 |       2.08 |         1    |
| displacement_up   | 5m   |    46 | 13:20  | YM_5m_rth.json | 13:20      | 13:40    |      5 |  51506 |   51576 |        70 |     29.14 |       2.4  |         1    |
| displacement_up   | 5m   |    53 | 13:55  | YM_5m_rth.json | 13:55      | 14:00    |      2 |  51536 |   51618 |        82 |     30.14 |       2.72 |         1    |
| displacement_up   | 5m   |    58 | 14:20  | YM_5m_rth.json | 14:20      | 14:40    |      5 |  51611 |   51688 |        77 |     37.43 |       2.06 |         0.73 |


## A5. Imbalance / Fair-Value Gaps — only where bars actually gap

Strict 3-bar gaps, ^DJI 5m, ≥ 5 pts:

| kind        | tf   |   bar | time   | source                               |   gap_low |   gap_high |   size_pts | displacement_bar   |   pct_filled | status   |
|:------------|:-----|------:|:-------|:-------------------------------------|----------:|-----------:|-----------:|:-------------------|-------------:|:---------|
| FVG_bearish | 5m   |    19 | 11:05  | ^DJI 5m (resampled from verified 1m) |   51247.3 |    51273.1 |      25.77 | 11:00              |        100   | FILLED   |
| FVG_bearish | 5m   |    20 | 11:10  | ^DJI 5m (resampled from verified 1m) |   51232.2 |    51239.6 |       7.35 | 11:05              |        100   | FILLED   |
| FVG_bearish | 5m   |    21 | 11:15  | ^DJI 5m (resampled from verified 1m) |   51204.5 |    51210.4 |       5.86 | 11:10              |        100   | FILLED   |
| FVG_bearish | 5m   |    22 | 11:20  | ^DJI 5m (resampled from verified 1m) |   51180.4 |    51186.4 |       5.97 | 11:15              |        100   | FILLED   |
| FVG_bullish | 5m   |    25 | 11:35  | ^DJI 5m (resampled from verified 1m) |   51168.8 |    51215.3 |      46.43 | 11:30              |        100   | FILLED   |
| FVG_bearish | 5m   |    29 | 11:55  | ^DJI 5m (resampled from verified 1m) |   51170.8 |    51195.9 |      25.07 | 11:50              |        100   | FILLED   |
| FVG_bullish | 5m   |    48 | 13:30  | ^DJI 5m (resampled from verified 1m) |   51191.2 |    51198.2 |       7    | 13:25              |          0   | UNFILLED |
| FVG_bullish | 5m   |    49 | 13:35  | ^DJI 5m (resampled from verified 1m) |   51199.6 |    51212   |      12.49 | 13:30              |         95.5 | PARTIAL  |
| FVG_bearish | 5m   |    53 | 13:55  | ^DJI 5m (resampled from verified 1m) |   51219.1 |    51225.3 |       6.26 | 13:50              |        100   | FILLED   |
| FVG_bullish | 5m   |    58 | 14:20  | ^DJI 5m (resampled from verified 1m) |   51266.9 |    51274.6 |       7.64 | 14:15              |        100   | FILLED   |
| FVG_bullish | 5m   |    62 | 14:40  | ^DJI 5m (resampled from verified 1m) |   51303.8 |    51333.3 |      29.48 | 14:35              |         34.4 | PARTIAL  |
| FVG_bullish | 5m   |    67 | 15:05  | ^DJI 5m (resampled from verified 1m) |   51348   |    51357.3 |       9.33 | 15:00              |        100   | FILLED   |

**Unfilled or partially filled at the close (5m):**
- `FVG_bullish` **51,191.18 – 51,198.18** (7.00 pts, created by the 13:25 bar, 0.0% filled).
- `FVG_bullish` **51,199.55 – 51,212.04** (12.49 pts, created by the 13:30 bar, 95.5% filled).
- `FVG_bullish` **51,303.80 – 51,333.28** (29.48 pts, created by the 14:35 bar, 34.4% filled).

^DJI 1m, ≥ 10 pts — 40 gaps; unfilled/partial only:

| kind        | tf   |   bar | time   | source                  |   gap_low |   gap_high |   size_pts | displacement_bar   |   pct_filled | status   |
|:------------|:-----|------:|:-------|:------------------------|----------:|-----------:|-----------:|:-------------------|-------------:|:---------|
| FVG_bearish | 1m   |    14 | 09:44  | ^DJI 1m (DJI_1m_s1..s7) |   51443.6 |    51480.9 |      37.38 | 09:43              |          0   | UNFILLED |
| FVG_bullish | 1m   |   271 | 14:01  | ^DJI 1m (DJI_1m_s1..s7) |   51219.1 |    51251.5 |      32.42 | 14:00              |         88.1 | PARTIAL  |
| FVG_bullish | 1m   |   284 | 14:14  | ^DJI 1m (DJI_1m_s1..s7) |   51232.6 |    51255   |      22.43 | 14:13              |         18.5 | PARTIAL  |
| FVG_bullish | 1m   |   309 | 14:39  | ^DJI 1m (DJI_1m_s1..s7) |   51294.7 |    51328   |      33.27 | 14:38              |         14.5 | PARTIAL  |


YM=F 5m RTH, ≥ 5 pts — unfilled/partial only:

| kind        | tf   |   bar | time   | source         |   gap_low |   gap_high |   size_pts | displacement_bar   |   pct_filled | status   |
|:------------|:-----|------:|:-------|:---------------|----------:|-----------:|-----------:|:-------------------|-------------:|:---------|
| FVG_bullish | 5m   |    48 | 13:30  | YM_5m_rth.json |     51522 |      51529 |          7 | 13:25              |          0   | UNFILLED |
| FVG_bullish | 5m   |    55 | 14:05  | YM_5m_rth.json |     51550 |      51558 |          8 | 14:00              |         25   | PARTIAL  |
| FVG_bullish | 5m   |    62 | 14:40  | YM_5m_rth.json |     51645 |      51669 |         24 | 14:35              |         37.5 | PARTIAL  |


## A6. Consolidations / balance areas (^DJI 5m)

| kind          | tf   |   bar | time   | source                               | from_bar   | to_bar   |   bars |      hi |      lo |   height_pts |   height_atr |   min_er |   max_er |
|:--------------|:-----|------:|:-------|:-------------------------------------|:-----------|:---------|-------:|--------:|--------:|-------------:|-------------:|---------:|---------:|
| consolidation | 5m   |    32 | 12:10  | ^DJI 5m (resampled from verified 1m) | 12:10      | 13:25    |     16 | 51206.1 | 51149.8 |        56.31 |         1.39 |     0.01 |     0.3  |
| consolidation | 5m   |    62 | 14:40  | ^DJI 5m (resampled from verified 1m) | 14:40      | 15:55    |     16 | 51384.3 | 51323.2 |        61.12 |         1.5  |     0.07 |     0.67 |


## A7. Level interactions — sweeps, failed breaks, breaks that held

### ^DJI cash, 5m

| kind                   | tf   |   bar | time   | source                               | level                         |   level_price | origin                 | from   | to    |   bars |   max_penetration_pts |   episode_extreme |   bars_closed_beyond |   reaction_next_6b_pts |
|:-----------------------|:-----|------:|:-------|:-------------------------------------|:------------------------------|--------------:|:-----------------------|:-------|:------|-------:|----------------------:|------------------:|---------------------:|-----------------------:|
| SWEEP_high             | 5m   |     2 | 09:40  | ^DJI 5m (resampled from verified 1m) | PDC  (prior day close, 09-28) |       51481.5 | DJI_1d_1mo.json bar 19 | 09:40  | 09:40 |      1 |                 23.68 |           51505.2 |                    0 |                 160.7  |
| FAILED_BREAK_low       | 5m   |     0 | 09:30  | ^DJI 5m (resampled from verified 1m) | PDL  (prior day low, 09-28)   |       51409.7 | DJI_1d_1mo.json bar 19 | 09:30  | 09:35 |      2 |                 56.02 |           51353.6 |                    1 |                 151.56 |
| BREAK_HOLD_low         | 5m   |     3 | 09:45  | ^DJI 5m (resampled from verified 1m) | PDL  (prior day low, 09-28)   |       51409.7 | DJI_1d_1mo.json bar 19 | 09:45  | 15:55 |     75 |                280.47 |           51129.2 |                   74 |                 nan    |
| FAILED_BREAK_low       | 5m   |     0 | 09:30  | ^DJI 5m (resampled from verified 1m) | RTH open (today)              |       51417   | DJI 1m 09:30 open      | 09:30  | 09:35 |      2 |                 63.33 |           51353.6 |                    1 |                 151.56 |
| BREAK_HOLD_low         | 5m   |     3 | 09:45  | ^DJI 5m (resampled from verified 1m) | RTH open (today)              |       51417   | DJI 1m 09:30 open      | 09:45  | 15:55 |     75 |                287.78 |           51129.2 |                   75 |                 nan    |
| BREAK_then_RECLAIM_low | 5m   |    12 | 10:30  | ^DJI 5m (resampled from verified 1m) | IB low  (09:30-10:30)         |       51325.6 | DJI 1m 09:30-10:29     | 10:30  | 14:35 |     50 |                196.4  |           51129.2 |                   47 |                 251.2  |
| SWEEP_low              | 5m   |    64 | 14:50  | ^DJI 5m (resampled from verified 1m) | IB low  (09:30-10:30)         |       51325.6 | DJI 1m 09:30-10:29     | 14:50  | 14:55 |      2 |                  2.43 |           51323.2 |                    0 |                  52.34 |
| FAILED_BREAK_low       | 5m   |    20 | 11:10  | ^DJI 5m (resampled from verified 1m) | 09-16 swing low (daily)       |       51186.7 | DJI_1d_1mo.json bar 11 | 11:10  | 11:30 |      5 |                 53.91 |           51132.8 |                    3 |                 122.57 |
| BREAK_then_RECLAIM_low | 5m   |    28 | 11:50  | ^DJI 5m (resampled from verified 1m) | 09-16 swing low (daily)       |       51186.7 | DJI_1d_1mo.json bar 11 | 11:50  | 12:30 |      9 |                 57.49 |           51129.2 |                    8 |                  76.92 |
| BREAK_then_RECLAIM_low | 5m   |    38 | 12:40  | ^DJI 5m (resampled from verified 1m) | 09-16 swing low (daily)       |       51186.7 | DJI_1d_1mo.json bar 11 | 12:40  | 13:25 |     10 |                 36.27 |           51150.4 |                    6 |                 100.32 |


### YM=F futures, 5m, RTH

| kind                   | tf   |   bar | time   | source         | level                            |   level_price | origin                     | from   | to    |   bars |   max_penetration_pts |   episode_extreme |   bars_closed_beyond |   reaction_next_6b_pts |
|:-----------------------|:-----|------:|:-------|:---------------|:---------------------------------|--------------:|:---------------------------|:-------|:------|-------:|----------------------:|------------------:|---------------------:|-----------------------:|
| BREAK_then_RECLAIM_low | 5m   |    12 | 10:30  | YM_5m_rth.json | ON low  (Globex 18:00-09:30)     |         51644 | YM 5m Tue 01:35            | 10:30  | 14:35 |     50 |                   185 |             51459 |                   45 |                    261 |
| SWEEP_high             | 5m   |     2 | 09:40  | YM_5m_rth.json | Prev close - upside test         |         51837 | YM meta chartPreviousClose | 09:40  | 09:40 |      1 |                    11 |             51848 |                    0 |                    172 |
| BREAK_HOLD_low         | 5m   |     0 | 09:30  | YM_5m_rth.json | Prev close - downside acceptance |         51837 | YM meta chartPreviousClose | 09:30  | 15:50 |     77 |                   378 |             51459 |                   77 |                    nan |
| SWEEP_low              | 5m   |    22 | 11:20  | YM_5m_rth.json | 09-24 low (ET calendar day)      |         51479 | YM_1d_1mo.json bar 17      | 11:20  | 11:25 |      2 |                    15 |             51464 |                    0 |                    136 |
| SWEEP_low              | 5m   |    30 | 12:00  | YM_5m_rth.json | 09-24 low (ET calendar day)      |         51479 | YM_1d_1mo.json bar 17      | 12:00  | 12:05 |      2 |                    20 |             51459 |                    0 |                     78 |
| FAILED_BREAK_low       | 5m   |     0 | 09:30  | YM_5m_rth.json | 09-28 low (ET calendar day)      |         51744 | YM_1d_1mo.json bar 19      | 09:30  | 09:35 |      2 |                    64 |             51680 |                    1 |                    168 |
| BREAK_HOLD_low         | 5m   |     3 | 09:45  | YM_5m_rth.json | 09-28 low (ET calendar day)      |         51744 | YM_1d_1mo.json bar 19      | 09:45  | 15:50 |     74 |                   285 |             51459 |                   73 |                    nan |


## A8. The one genuine liquidity event of the session

This is the single observation where cash and futures **disagree**, and it is the most load-bearing fact in this report.

| | Futures `YM=F` | Cash `^DJI` |
|---|---:|---:|
| 09-24 low (prior swing low) | 51,479 | 51,124.02 |
| Today's low | 51,459 @ 12:00 | 51,129.18 @ 12:02 |
| Difference | **-20 pts (TAKEN)** | **+5.16 pts (NOT taken)** |

- **Futures took the sell-side.** YM traded to 51,459 at 12:00, i.e. **20 points through** the 09-24 calendar-day low of 51,479, then closed the session back above it and sat +238 pts above it at my last futures bar (15:50). That is a completed penetrate-and-reverse at a multi-day reference low.
- **Cash did not.** ^DJI bottomed at 51,129.18, which is **5.16 points ABOVE** the 09-24 cash low of 51,124.02 — a gap of 1.0 basis points. The cash index printed an *equal-lows* structure, not a sweep.
- **Timing corroborates.** Both instruments bottomed in the same 5-minute bucket (12:00 futures / 12:02 cash), so this is one event, not two.

Also on futures: the Globex overnight low **51,644 (Tue 01:35)** was broken decisively during RTH (down to 51,459, 185 pts through) — a break-and-hold, *not* a sweep — and was then **reclaimed**: YM last 51,717 is +73 pts back above it.

## A8b. Timeframe sensitivity — the same contact, classified two ways

Sweep-vs-failed-break is **resolution dependent**, and pretending otherwise is how these reports go wrong. The clearest case today is the prior-day close:

| Timeframe | Classification | Why |
|---|---|---|
| ^DJI 5m | `SWEEP_high` | no 5-minute bar *closed* above 51,481.51 |
| ^DJI 1m | `FAILED_BREAK_high` | two 1-minute bars closed above it — 09:41 @ 51,490.14 and 09:42 @ 51,494.47 — before 09:43 closed back at 51,447.55 |

Both are correct for their timeframe. Stated plainly: **buy-side above the prior close was taken and rejected inside three minutes**; on a 5-minute chart that leaves only a wick. Full 1-minute episode table: `events_dji_level_interactions_1m.csv`.

| kind                   | tf   |   bar | time   | source                  | level                         |   level_price | origin                 | from   | to    |   bars |   max_penetration_pts |   episode_extreme |   bars_closed_beyond |   reaction_next_6b_pts |
|:-----------------------|:-----|------:|:-------|:------------------------|:------------------------------|--------------:|:-----------------------|:-------|:------|-------:|----------------------:|------------------:|---------------------:|-----------------------:|
| FAILED_BREAK_high      | 1m   |    11 | 09:41  | ^DJI 1m (DJI_1m_s1..s7) | PDC  (prior day close, 09-28) |       51481.5 | DJI_1d_1mo.json bar 19 | 09:41  | 09:43 |      3 |                 23.68 |           51505.2 |                    2 |                 118.75 |
| FAILED_BREAK_low       | 1m   |     3 | 09:33  | ^DJI 1m (DJI_1m_s1..s7) | PDL  (prior day low, 09-28)   |       51409.7 | DJI_1d_1mo.json bar 19 | 09:33  | 09:35 |      3 |                 56.02 |           51353.6 |                    2 |                 141.65 |
| FAILED_BREAK_low       | 1m   |     7 | 09:37  | ^DJI 1m (DJI_1m_s1..s7) | PDL  (prior day low, 09-28)   |       51409.7 | DJI_1d_1mo.json bar 19 | 09:37  | 09:39 |      3 |                 17.88 |           51391.8 |                    1 |                 113.42 |
| BREAK_HOLD_low         | 1m   |    15 | 09:45  | ^DJI 1m (DJI_1m_s1..s7) | PDL  (prior day low, 09-28)   |       51409.7 | DJI_1d_1mo.json bar 19 | 09:45  | 15:59 |    375 |                280.47 |           51129.2 |                  369 |                 nan    |
| FAILED_BREAK_low       | 1m   |     2 | 09:32  | ^DJI 1m (DJI_1m_s1..s7) | RTH open (today)              |       51417   | DJI 1m 09:30 open      | 09:32  | 09:35 |      4 |                 63.33 |           51353.6 |                    3 |                 141.65 |
| FAILED_BREAK_low       | 1m   |     7 | 09:37  | ^DJI 1m (DJI_1m_s1..s7) | RTH open (today)              |       51417   | DJI 1m 09:30 open      | 09:37  | 09:39 |      3 |                 25.19 |           51391.8 |                    1 |                 113.42 |
| BREAK_HOLD_low         | 1m   |    15 | 09:45  | ^DJI 1m (DJI_1m_s1..s7) | RTH open (today)              |       51417   | DJI 1m 09:30 open      | 09:45  | 15:59 |    375 |                287.78 |           51129.2 |                  372 |                 nan    |
| FAILED_BREAK_low       | 1m   |    62 | 10:32  | ^DJI 1m (DJI_1m_s1..s7) | IB low  (09:30-10:30)         |       51325.6 | DJI 1m 09:30-10:29     | 10:32  | 10:34 |      3 |                 26.6  |           51299   |                    2 |                  55.64 |
| BREAK_then_RECLAIM_low | 1m   |    67 | 10:37  | ^DJI 1m (DJI_1m_s1..s7) | IB low  (09:30-10:30)         |       51325.6 | DJI 1m 09:30-10:29     | 10:37  | 14:38 |    242 |                196.4  |           51129.2 |                  240 |                 251.2  |
| SWEEP_low              | 1m   |   320 | 14:50  | ^DJI 1m (DJI_1m_s1..s7) | IB low  (09:30-10:30)         |       51325.6 | DJI 1m 09:30-10:29     | 14:50  | 14:50 |      1 |                  0.94 |           51324.6 |                    0 |                  14.96 |
| SWEEP_low              | 1m   |   322 | 14:52  | ^DJI 1m (DJI_1m_s1..s7) | IB low  (09:30-10:30)         |       51325.6 | DJI 1m 09:30-10:29     | 14:52  | 14:52 |      1 |                  1.19 |           51324.4 |                    0 |                  12.9  |
| SWEEP_low              | 1m   |   327 | 14:57  | ^DJI 1m (DJI_1m_s1..s7) | IB low  (09:30-10:30)         |       51325.6 | DJI 1m 09:30-10:29     | 14:57  | 14:58 |      2 |                  2.43 |           51323.2 |                    0 |                  40.26 |
| SWEEP_low              | 1m   |   102 | 11:12  | ^DJI 1m (DJI_1m_s1..s7) | 09-16 swing low (daily)       |       51186.7 | DJI_1d_1mo.json bar 11 | 11:12  | 11:12 |      1 |                  0.26 |           51186.4 |                    0 |                  18.13 |
| BREAK_then_RECLAIM_low | 1m   |   108 | 11:18  | ^DJI 1m (DJI_1m_s1..s7) | 09-16 swing low (daily)       |       51186.7 | DJI_1d_1mo.json bar 11 | 11:18  | 11:33 |     16 |                 53.91 |           51132.8 |                   15 |                 105.97 |
| BREAK_then_RECLAIM_low | 1m   |   141 | 11:51  | ^DJI 1m (DJI_1m_s1..s7) | 09-16 swing low (daily)       |       51186.7 | DJI_1d_1mo.json bar 11 | 11:51  | 12:33 |     43 |                 57.49 |           51129.2 |                   40 |                  74.48 |
| SWEEP_low              | 1m   |   192 | 12:42  | ^DJI 1m (DJI_1m_s1..s7) | 09-16 swing low (daily)       |       51186.7 | DJI_1d_1mo.json bar 11 | 12:42  | 12:42 |      1 |                  1.8  |           51184.9 |                    0 |                  18.08 |
| FAILED_BREAK_low       | 1m   |   194 | 12:44  | ^DJI 1m (DJI_1m_s1..s7) | 09-16 swing low (daily)       |       51186.7 | DJI_1d_1mo.json bar 11 | 12:44  | 12:47 |      4 |                 19.22 |           51167.4 |                    3 |                  38.65 |
| FAILED_BREAK_low       | 1m   |   199 | 12:49  | ^DJI 1m (DJI_1m_s1..s7) | 09-16 swing low (daily)       |       51186.7 | DJI_1d_1mo.json bar 11 | 12:49  | 12:50 |      2 |                  7.07 |           51179.6 |                    1 |                  26.5  |
| BREAK_then_RECLAIM_low | 1m   |   206 | 12:56  | ^DJI 1m (DJI_1m_s1..s7) | 09-16 swing low (daily)       |       51186.7 | DJI_1d_1mo.json bar 11 | 12:56  | 13:24 |     29 |                 36.27 |           51150.4 |                   27 |                  54.48 |
| FAILED_BREAK_low       | 1m   |   236 | 13:26  | ^DJI 1m (DJI_1m_s1..s7) | 09-16 swing low (daily)       |       51186.7 | DJI_1d_1mo.json bar 11 | 13:26  | 13:28 |      3 |                  9.08 |           51177.6 |                    2 |                  39.39 |


## A9. Market-structure shifts (^DJI 5m, no look-ahead)

| kind   | tf   |   bar | time   | source                               | broken_swing      |   swing_price |   close | swing_confirmed_at   |
|:-------|:-----|------:|:-------|:-------------------------------------|:------------------|--------------:|--------:|:---------------------|
| BOS_up | 5m   |    48 | 13:30  | ^DJI 5m (resampled from verified 1m) | SH@12:50=51206.10 |       51206.1 | 51217   | 13:05                |
| BOS_up | 5m   |    54 | 14:00  | ^DJI 5m (resampled from verified 1m) | SH@11:45=51255.33 |       51255.3 | 51279.6 | 12:00                |


## A10. Reclaims / regains

**^DJI cash, 5m** — a reclaim requires >= 5 closes on the wrong side followed by a close back that holds 5 bars:

| kind                        | tf   |   bar | time   | source                               | level                   |   level_price | origin                 |   bars_below_before |   reclaim_close |   closes_held_above |   hold_required | note   |
|:----------------------------|:-----|------:|:-------|:-------------------------------------|:------------------------|--------------:|:-----------------------|--------------------:|----------------:|--------------------:|----------------:|:-------|
| RECLAIM_confirmed           | 5m   |    61 | 14:35  | ^DJI 5m (resampled from verified 1m) | IB low  (09:30-10:30)   |       51325.6 | DJI 1m 09:30-10:29     |                  47 |         51349.8 |                   5 |               5 |        |
| RECLAIM_attempt_unconfirmed | 5m   |    36 | 12:30  | ^DJI 5m (resampled from verified 1m) | 09-16 swing low (daily) |       51186.7 | DJI_1d_1mo.json bar 11 |                   8 |         51187.6 |                   3 |               5 |        |


**YM=F futures, 5m RTH:**

| kind              | tf   |   bar | time   | source         | level                        |   level_price | origin          |   bars_below_before |   reclaim_close |   closes_held_above |   hold_required | note   |
|:------------------|:-----|------:|:-------|:---------------|:-----------------------------|--------------:|:----------------|--------------------:|----------------:|--------------------:|----------------:|:-------|
| RECLAIM_confirmed | 5m   |    61 | 14:35  | YM_5m_rth.json | ON low  (Globex 18:00-09:30) |         51644 | YM 5m Tue 01:35 |                  44 |           51681 |                   5 |               5 |        |


## A10b. The closing hour and the 16:00 auction

The final 60 minutes (15:00–15:59, 60 1m bars) traded **51,338.38 – 51,384.27**, a range of **45.89 pts = 12% of the day's 376.01-pt range**. High 51,384.27 at 15:33, low 51,338.38 at 15:01. There was **no closing drive** — the day ended inside the balance it built after 14:40.

Volume ramp into the bell (1m, ^DJI summed constituent volume):

| bar | close | volume |
|---|---:|---:|
| 15:53 | 51,376.95 | 1,903,670 |
| 15:54 | 51,370.80 | 1,910,215 |
| 15:55 | 51,359.92 | 3,524,793 |
| 15:56 | 51,358.92 | 3,228,674 |
| 15:57 | 51,374.47 | 3,680,141 |
| 15:58 | 51,368.42 | 4,422,512 |
| 15:59 | 51,358.99 | 8,684,423 |

- The 15:59 bar alone traded **8,684,423** — **14.3×** the 15:00 bar — and had the widest range of the closing hour (28.29 pts: 51,343.71–51,372.00).
- **The auction printed 51,350.99, which is -8.00 pts versus the 15:59 close of 51,358.99** — a small sell imbalance on the cross. The print sits *inside* the 15:59 bar's range, so it is consistent with the tape rather than a gap.
- The last seven 1m bars (15:53–15:59) carry **27,354,428** of the **279,328,701** summed across all 390 bars — **9.8% of the session's bar volume in the last 7 minutes.** Front-loading into the bell is normal auction mechanics and is **not** evidence of directional intent; it is reported here only so the wide 15:59 range is not mistaken for a displacement leg.
- Yahoo's post-close `regularMarketVolume` is **374,936,624** (meta timestamp 16:02:48), materially above the 279,328,701 summed from bars. The difference is the closing cross, which settles after 16:00 and is never attributed to an intraday bar. **Do not reconcile these two numbers** — they measure different things.

## A11. Levels never traded through today (pools still resting)

**^DJI cash** (vs 09:30-15:59 bars):

| Level | Price | Side | Source |
|---|---:|---|---|
| PDH  (prior day high, 09-28) | 51,780.50 | high | DJI_1d_1mo.json bar 19 |
| IB high (09:30-10:30) | 51,505.19 | high | DJI 1m 09:30-10:29 |
| 09-24 swing low (daily) | 51,124.02 | low | DJI_1d_1mo.json bar 17 |

**YM=F futures** (vs RTH bars):

| Level | Price | Side | Source |
|---|---:|---|---|
| ON high (Globex 18:00-09:30) | 52,002 | high | YM 5m Tue 08:00 |

---

# PART B — INFERRED STRUCTURE

Part B is interpretation. It is consistent with Part A but is **not** proved by it.

## B1. The day in one sentence

A failed opening push above the prior close, a single genuine down-displacement at 11:00–11:20 that delivered price into the 09-24 low region, a two-hour base that *stopped 5.16 points short of the obvious cash liquidity*, and an afternoon repair driven by four stacked up-displacements — closing at 51,350.99, 59% of the way up the session range, back above the initial-balance low but still below the prior day's low, with the sell-side pool under 51,124.02 still intact.

## B2. Phase map (inferred boundaries)

| Phase | Window | Character | Evidence from Part A |
|---|---|---|---|
| 1. Open / failed extension | 09:30–09:42 | Push to 51,505.19, above PDC, immediately rejected | A2, unfilled bearish 1m FVG 51,443.57–51,480.95 from 09:43 |
| 2. Grind lower | 09:42–11:00 | Trend, but *below* displacement threshold | A4 — no qualifying 5m down-leg |
| 3. Displacement down | 11:00–11:20 | −125.08 pts, ER 1.00, 2.23× ATR | A4 |
| 4. Base / accumulation | 12:10–13:25 | ER 0.01–0.17, 56.31-pt box 51,149.79–51,206.10 | A6 |
| 5. Repair | 13:20–14:40 | Four up-displacements, BOS_up ×2 | A4, A9 |
| 6. Balance at highs | 14:40–15:59 | ER 0.07, 61.12-pt box 51,323.15–51,384.27 | A6 |

## B3. Inferred liquidity map

Ranked by how well the bars support each pool.

| Pool | Cash level | Futures level | Strength of evidence |
|---|---:|---:|---|
| Untaken sell-side under the double bottom | **< 51,124.02** | — (already taken) | **Strong on cash.** Two session lows 5.16 pts apart, 3 sessions apart, neither breached. |
| Buy-side over today's high | **> 51,505.19** | > 51,848 | **Strong.** Single rejected extreme, never revisited for the remaining 377 min of the session. |
| Buy-side over PDC | **> 51,481.51** | — | Moderate. Rejected once at the open. |
| Buy-side over ON high | — | **> 52,002** (08:00) | Moderate. Globex extreme, not revisited in RTH. |

**Directional read (low confidence):** futures already ran the sell-side and reversed, cash left its pool untouched. That asymmetry usually resolves one of two ways — either the futures sweep was the low and cash simply never needed to print the extra 5 points, or the cash pool below 51,124.02 remains a magnet into a later session. **The bars on hand cannot distinguish these.**

## B4. Structural invalidation levels

These are the prices at which the Part-B reading is **wrong**, not stop-loss advice.

| The claim | Invalidated by | Level |
|---|---|---:|
| "Afternoon recovery is intact" | 5m **close** below the 14:55 swing low | **51,323.15** (^DJI) |
| "The 12:00 low is the session low" | any trade below it | **51,129.18** (^DJI) / **51,459** (YM) |
| "The double bottom holds" | trade below the 09-24 low | **51,124.02** (^DJI) |
| "Balance at highs, not breakout" | 5m close above the 15:30 high | **51,505.19** (^DJI) |
| "Day stays below prior close" | 5m close above PDC | **51,481.51** (^DJI) |
| "ON low reclaim is real" (futures) | YM close back below it | **51,644** (YM) |

## B5. Structures I looked for and did NOT find

Stated explicitly so absence is not mistaken for oversight:

- **No sweep of PDH** — 51,780.50 was never approached; today's high fell 275.31 pts short.
- **No qualifying morning displacement leg** on 5m despite a ~376-pt decline: the move was delivered as a grind. Calling 09:42–11:00 "displacement" would not survive an ATR-relative test.
- **No large unfilled 5m FVG below price** — the morning bearish gaps (11:05, 11:10, 11:15, 11:20, 11:55) are **100% filled**, so they are spent and carry no forward inference.
- **No verifiable absorption / delta divergence** anywhere — requires tape or footprint data that does not exist in this dataset.

---

# PART C — DECLARED INSUFFICIENCIES

| Question | Status | Why |
|---|---|---|
| Where were resting stops actually clustered? | **Cannot answer** | No book/tape. Price geometry only. |
| Was the 12:00 low absorbed or just exhausted? | **Cannot answer** | Needs footprint/delta. |
| Did the CFD (broker "US30") print the same wicks? | **Cannot answer** | No broker feed; CFD wicks differ from both cash and futures. |
| What is the true YM traded volume? | **Cannot answer** | Yahoo futures volume is partial (see 0.3 #4). |
| What is the session close / final structure? | **Answered** | Cash closed at 51,350.99; all 390 RTH minutes captured. |
| Does the futures picture hold overnight? | **Cannot answer** | YM Globex trades until 17:00 ET and reopens 18:00; captured only to 15:50. |
| Overnight ^DJI structure | **Does not exist** | Cash index is only computed 09:30–16:00. Overnight structure is a futures-only concept — that is why Globex levels are quoted on YM. |
| Multi-day 1m/5m cash structure | **Not captured** | Only today at 1m/5m; 09-23→09-29 available at 30m, 08-31→09-29 at 1d. |

---

## Reproduce

```bash
python -m engine.lane7_verify                      # integrity gate
python -m experiments.lane7_us30_structure         # this report
```

Raw payloads: `data/raw/*.json` (verbatim Yahoo `/v8/finance/chart` responses). Derived bars and every event table: `results/lane7_us30_structure/*.csv`.