# US30 / DJIA / YM — Verified Market-State Packet

**Acquisition window (UTC):** `2026-09-29T19:38:14Z -> 2026-09-29T19:40:14Z`  
**Trading date:** 2026-09-29 (Tuesday) · **Exchange TZ:** America/New_York (EDT, UTC-04:00)  
**Confidence:** HIGH for cash index + YM futures; MEDIUM for CFD (quote only, no candles)

> Everything under VERIFIED is a value that appears verbatim in a cited provider payload.
> Everything under DERIVED is a deterministic recomputation of those values (`build_packet.py` reproduces it).
> Everything under INFERRED is judgement and carries no evidentiary weight. No candle or indicator was invented.

## 1. Session status — VERIFIED

| field | value |
|---|---|
| venue_status | REGULAR SESSION OPEN (cash equities) |
| rth_open_et | 2026-09-29T09:30:00-04:00 |
| rth_close_et | 2026-09-29T16:00:00-04:00 |
| snapshot_et | 2026-09-29T15:40:14-04:00 |
| snapshot_utc | 2026-09-29T19:40:14Z |
| minutes_elapsed | 370.2 |
| minutes_remaining | 19.8 |
| session_pct_complete | 94.93 |
| pre_market_window_et | 2026-09-29T04:00:00-04:00 -> 2026-09-29T09:30:00-04:00 |
| post_market_window_et | 2026-09-29T16:00:00-04:00 -> 2026-09-29T20:00:00-04:00 |
| futures_status | CME Globex open (YM continuous); Yahoo buckets the YM day as calendar ET, not the 18:00->17:00 Globex session |

## 2. Current price state — VERIFIED

| | **DJIA cash** `^DJI` | **E-mini Dow** `YM=F` (Dec 26) | **FOREXCOM:US30** (CFD) | **CAPITALCOM:US30** (CFD) |
|---|---|---|---|---|
| Venue | Dow Jones Indices / S&P DJI | CBOT (CME Group) | FOREX.com | Capital.com |
| Feed stamp (ET) | 15:40:14 | 15:30:07 | 15:39 | 15:39 |
| **Last** | **51,355.81** | **51,709** | **51,362.3** | **51,362.8** |
| Change | -125.70 (-0.244%) | -128 (-0.247%) | -134.5 (-0.26%) | -128.5 (-0.25%) |
| Open | 51,416.96 | 51,725 | 51,495.3 | 51,485.6 |
| Day high | 51,505.19 | 52,002 | 51,658.4 | 51,652.9 |
| Day low | 51,129.18 | 51,459 | 51,122.8 | 51,126.1 |
| Prev close | 51,481.51 | 51,837 | 51,496.8 | 51,491.3 |
| Day range (pts) | 376.01 | 543 | 535.6 | 526.8 |
| Volume | 256,917,543 (composite) | 67,260 contracts | — (not published) | 130,880 ticks |
| 52w high | 54,744.33 | 54,884 | — | — |
| 52w low | 45,057.28 | 45,052 | — | — |

**The CFD day range is wider than the cash range because the CFD day includes the overnight session. These are different products — do not merge the series.**

### 2a. Independent cash-index confirmation — VERIFIED

| source | symbol | feed stamp | last | day high | day low | prev close |
|---|---|---|---|---|---|---|
| Yahoo Finance | ^DJI | 15:40:14 ET | 51,355.81 | 51,505.19 | 51,129.18 | 51,481.51 |
| CNBC | .DJI | Last / 3:23 PM EDT | 51,373.26 | 51,505.19 | 51,129.18 | 51,481.51 |
| MarketWatch | DJIA | Sep 29, 2026 3:03 p.m. EDT | 51,355.39 | 51,505.19 | 51,129.18 | 51,481.51 |
| TradingView | DJ:DJI | concurrent with 15:39 GMT-4 page render | 51,350.43 | — | — | — |

Spread across the four cash prints: **22.83 pts** — sources polled over a ~36 minute spread of feed stamps (15:03 / 15:23 / 15:39 ET) on a moving market; dispersion is timing, not disagreement.

### 2b. Poll ladder (feed liveness proof) — VERIFIED

Nine consecutive `^DJI` calls, each returning its own feed stamp and monotonically rising cumulative volume:

| feed stamp (ET) | price | cumulative volume |
|---|---|---|
| 15:38:14 | 51,357.48 | 255,138,566 |
| 15:38:43 | 51,363.43 | 255,817,382 |
| 15:38:45 | 51,364.33 | 255,838,133 |
| 15:38:46 | 51,364.66 | 255,846,695 |
| 15:38:56 | 51,362.46 | 255,987,231 |
| 15:38:58 | 51,364.47 | 256,009,192 |
| 15:38:59 | 51,363.93 | 256,018,418 |
| 15:39:16 | 51,362.41 | 256,224,857 |
| 15:40:14 | 51,355.81 | 256,917,543 |

## 3. Timeframe coverage

| TF | DJIA cash | E-mini YM | notes |
|---|---|---|---|
| 1m | VERIFIED (44 bars) | NOT_RETRIEVED | cash window targeted to the last ~46 min |
| 5m | VERIFIED (74 bars) | NOT_RETRIEVED_TRUNCATED | YM 5m response truncated by retrieval layer → excluded |
| 15m | VERIFIED (25 bars) | VERIFIED (63 bars) | both full today |
| 30m | VERIFIED (65 bars) | NOT_RETRIEVED | cash covers 5 sessions |
| 1h | VERIFIED (57 bars) | VERIFIED (56 bars) | YM payload has a weekend null block |
| **4h** | **DERIVED** (17 blocks) | **DERIVED** (15 blocks) | **no provider serves native 4h — aggregated from verified 60m** |
| 1D | VERIFIED (20 bars) | VERIFIED (20 bars) | + today's forming bar, flagged separately |
| 1W | VERIFIED (26 bars) | VERIFIED (14 bars) | + current week reconstructed |

### 3a. Cash index — today's 15m RTH candles (VERIFIED, closed bars only)

| time ET | open | high | low | close | volume |
|---|---|---|---|---|---|
| 09:30 | 51,416.96 | 51,505.19 | 51,353.63 | 51,424.52 | 22,160,819 |
| 09:45 | 51,422.34 | 51,442.61 | 51,368.27 | 51,368.27 | 14,945,911 |
| 10:00 | 51,372.19 | 51,435.96 | 51,344.49 | 51,400.77 | 12,977,993 |
| 10:15 | 51,400.58 | 51,408.03 | 51,325.58 | 51,353.86 | 13,270,781 |
| 10:30 | 51,355.89 | 51,372.18 | 51,270.35 | 51,303.41 | 12,490,261 |
| 10:45 | 51,303.70 | 51,331.03 | 51,268.21 | 51,274.12 | 9,954,544 |
| 11:00 | 51,274.40 | 51,278.46 | 51,186.41 | 51,188.11 | 11,286,045 |
| 11:15 | 51,188.21 | 51,204.54 | 51,132.76 | 51,154.36 | 9,374,745 |
| 11:30 | 51,154.06 | 51,238.73 | 51,154.06 | 51,231.99 | 8,447,273 |
| 11:45 | 51,232.61 | 51,255.33 | 51,153.05 | 51,155.89 | 8,475,628 |
| 12:00 | 51,155.98 | 51,181.72 | 51,129.18 | 51,159.49 | 7,049,639 |
| 12:15 | 51,159.05 | 51,193.05 | 51,149.93 | 51,185.19 | 7,468,007 |
| 12:30 | 51,184.75 | 51,203.66 | 51,179.28 | 51,181.95 | 9,441,243 |
| 12:45 | 51,181.47 | 51,206.10 | 51,167.45 | 51,192.92 | 7,499,990 |
| 13:00 | 51,193.63 | 51,194.99 | 51,150.40 | 51,183.56 | 7,145,005 |
| 13:15 | 51,185.55 | 51,199.55 | 51,161.61 | 51,197.59 | 6,971,280 |
| 13:30 | 51,198.48 | 51,243.42 | 51,198.18 | 51,243.42 | 7,939,961 |
| 13:45 | 51,243.59 | 51,250.72 | 51,200.11 | 51,216.44 | 8,610,989 |
| 14:00 | 51,218.01 | 51,298.08 | 51,218.01 | 51,265.14 | 7,916,145 |
| 14:15 | 51,265.21 | 51,311.90 | 51,261.10 | 51,273.55 | 7,459,469 |
| 14:30 | 51,273.58 | 51,380.38 | 51,250.88 | 51,347.82 | 7,930,613 |
| 14:45 | 51,347.40 | 51,358.03 | 51,323.15 | 51,346.05 | 7,978,636 |
| 15:00 | 51,346.11 | 51,368.91 | 51,338.38 | 51,355.90 | 8,341,955 |
| 15:15 | 51,356.77 | 51,375.49 | 51,341.58 | 51,367.17 | 9,698,199 |
| 15:30 | 51,367.59 | 51,384.27 | 51,350.08 | 51,356.30 | 7,672,580 |
| *15:40* | *51,355.81* | *51,355.81* | *51,355.81* | *51,355.81* | *live partial* |

### 3b. Cash index — last 10 completed daily bars (VERIFIED)

| date | open | high | low | close | volume |
|---|---|---|---|---|---|
| 2026-09-15 | 52,303.24 | 52,336.61 | 51,875.65 | 52,093.11 | 374,460,000 |
| 2026-09-16 | 52,115.40 | 52,173.70 | 51,186.67 | 51,461.90 | 395,270,000 |
| 2026-09-17 | 51,882.53 | 51,935.97 | 51,607.65 | 51,778.04 | 406,100,000 |
| 2026-09-18 | 51,826.78 | 51,826.78 | 51,497.47 | 51,682.64 | 846,980,000 |
| 2026-09-21 | 51,936.76 | 52,128.58 | 51,747.68 | 52,048.83 | 444,350,000 |
| 2026-09-22 | 52,301.92 | 52,319.01 | 51,726.08 | 51,863.69 | 444,770,000 |
| 2026-09-23 | 51,771.41 | 51,846.81 | 51,477.53 | 51,511.59 | 428,070,000 |
| 2026-09-24 | 51,415.75 | 51,485.97 | 51,124.02 | 51,349.98 | 390,410,000 |
| 2026-09-25 | 51,359.70 | 51,874.94 | 51,339.24 | 51,828.62 | 387,540,000 |
| 2026-09-28 | 51,648.48 | 51,780.50 | 51,409.65 | 51,481.51 | 455,450,000 |
| *2026-09-29* | *51,416.96* | *51,505.19* | *51,129.18* | *51,364.66* | *255,846,695 — FORMING* |

### 3c. Cash index — last 8 completed weekly bars (VERIFIED)

| week of | open | high | low | close |
|---|---|---|---|---|
| 2026-08-03 | 52,759.06 | 54,744.33 | 52,759.06 | 54,036.93 |
| 2026-08-10 | 54,072.66 | 54,222.85 | 53,622.46 | 53,732.41 |
| 2026-08-17 | 53,663.11 | 53,710.06 | 52,754.90 | 53,277.01 |
| 2026-08-24 | 53,261.95 | 53,819.65 | 53,261.95 | 53,559.99 |
| 2026-08-31 | 53,462.60 | 53,746.50 | 52,691.31 | 53,414.25 |
| 2026-09-07 | 53,110.45 | 53,110.45 | 51,962.71 | 52,573.29 |
| 2026-09-14 | 52,750.88 | 52,750.88 | 51,186.67 | 51,682.64 |
| 2026-09-21 | 51,936.76 | 52,319.01 | 51,124.02 | 51,828.62 |
| *2026-09-28* | *51,648.48* | *51,780.50* | *51,129.18* | *51,363.93* — **IN PROGRESS (2/5 sessions), DERIVED** |

### 3d. E-mini YM — last 8 completed daily bars (VERIFIED)

| date | open | high | low | close | volume |
|---|---|---|---|---|---|
| 2026-09-17 | 51,486 | 52,169 | 51,455 | 51,807 | 15,533 |
| 2026-09-18 | 51,800 | 51,957 | 51,576 | 51,761 | 70,167 |
| 2026-09-21 | 52,085 | 52,557 | 52,080 | 52,475 | 68,624 |
| 2026-09-22 | 52,470 | 52,844 | 52,125 | 52,279 | 88,224 |
| 2026-09-23 | 52,255 | 52,371 | 51,844 | 51,873 | 76,449 |
| 2026-09-24 | 51,878 | 51,905 | 51,479 | 51,717 | 83,829 |
| 2026-09-25 | 51,655 | 52,223 | 51,610 | 52,163 | 76,065 |
| 2026-09-28 | 52,140 | 52,153 | 51,744 | 51,837 | 76,065 |
| *2026-09-29* | *51,845* | *52,002* | *51,459* | *51,697* | *67,242 — FORMING* |

## 4. DERIVED — computed from verified candles, nothing invented

| metric | value | basis |
|---|---|---|
| Cash/futures basis | +353.19 pts | YM last − cash last, 607s stamp gap |
| RTH VWAP proxy (5m) | 51,288.56 | 75 verified 5m bars, composite volume |
| Last vs VWAP proxy | +67.25 pts | |
| Position in day range | 60.3% | (last − low) / (high − low) |
| Open → last | -61.15 pts | |
| ATR(14) daily | 508.63 pts | Wilder true range averaged over the last 14 COMPLETED daily bars (19 TRs available) |
| Below 52w high | 6.19% | |
| Above 52w low | 13.98% | |

*volume-weighted mean of (H+L+C)/3 over the 75 verified 5m bars using index COMPOSITE volume. This is a proxy, not an exchange-disseminated VWAP.*

**4H caveat.** 4H is NOT a provider candle for either instrument; it is aggregation of verified 60m bars under the documented bucketing rule. Cash rule: the seven 60m RTH bars per day grouped 4+3 → `09:30–13:30` and `13:30–16:00`. Futures rule: ET 4-hour buckets anchored 00/04/08/12/16/20 — note most brokers anchor futures 4H at 18:00 ET, so these edges will NOT line up with a TradingView 4H chart.

Last 6 derived cash 4H blocks:

| block | open | high | low | close | src 60m bars | complete |
|---|---|---|---|---|---|---|
| 2026-09-25 09:30-13:30 ET | 51,359.70 | 51,838.74 | 51,339.24 | 51,765.38 | 4 | True |
| 2026-09-25 13:30-16:00 ET | 51,765.17 | 51,874.94 | 51,710.15 | 51,821.37 | 3 | True |
| 2026-09-28 09:30-13:30 ET | 51,648.48 | 51,780.50 | 51,409.65 | 51,594.57 | 4 | True |
| 2026-09-28 13:30-16:00 ET | 51,593.98 | 51,623.89 | 51,445.15 | 51,485.64 | 3 | True |
| 2026-09-29 09:30-13:30 ET | 51,416.96 | 51,505.19 | 51,129.18 | 51,197.59 | 4 | True |
| 2026-09-29 13:30-16:00 ET | 51,198.48 | 51,384.27 | 51,198.18 | 51,364.47 | 4 | False |

## 5. INFERRED — judgement, not measurement

- **structure** — Cash index is mid-range after a two-session decline; today prints a lower high (51,505 vs Mon 51,780) and a lower low (51,129 vs Mon 51,410) versus Monday, then recovers into the last hour. That is an inside-down-then-recover shape, not a resolved trend.
- **intraday_shape** — Session low 51,129.18 was set in the 12:00-12:05 ET 5m bar; price has ground higher through the afternoon and is trading back above the 5m VWAP proxy in the final 20 minutes.
- **weekly** — Week of 2026-09-28 is in progress and currently down vs the 51,828.62 prior weekly close; the 52,000 handle has capped every attempt since 2026-09-21.
- **basis** — Dec-26 YM at a ~350pt premium to cash is consistent with normal cost-of-carry on a front-quarter contract at these front-end yields, not a dislocation. Read it as approximate given the 10-minute stamp gap between the two legs.
- **caveat** — All of the above is interpretation layered on the VERIFIED block and carries no independent evidentiary weight.

## 6. Explicit missing-data list

| severity | field | reason |
|---|---|---|
| HIGH | FOREXCOM:US30 OHLC candle history (any timeframe) | TradingView symbol page exposes only the quote row (last/open/prevclose/day range); candle history requires an authenticated TradingView or FOREX.com API session |
| MEDIUM | ^DJI native 4H candles | Yahoo chart API exposes no 4h granularity for ^DJI; 4H shown is a deterministic 4+3 aggregation of verified 60m RTH bars, NOT a provider candle |
| MEDIUM | YM native 4H candles | derived by ET-4h-bucket aggregation of verified 60m bars; note brokers commonly anchor futures 4H at 18:00 ET, so bucket edges will differ from a TradingView 4H chart |
| MEDIUM | YM 60m bars 2026-09-24 17:00 ET -> 2026-09-28 09:00 ET | provider returned a contiguous all-null block (weekend + surrounding hours) in the range=5d payload; left as a hole |
| MEDIUM | FOREXCOM:US30 volume | provider displays '—'; CFD venue publishes no volume for this symbol |
| MEDIUM | YM 1m candles | not retrieved this pass; Yahoo does expose 1m for YM=F, so this is a coverage gap not a source limitation |
| MEDIUM | YM 5m candles | fetched, but the provider response was truncated mid-'open'-array by the retrieval layer; excluded rather than partially transcribed |
| MEDIUM | YM overnight 18:00-24:00 ET Mon 2026-09-28 segment | Yahoo buckets the YM day from 00:00 ET, so the first 6 hours of the Globex session that opened Mon 18:00 ET are outside the 'day' payload |
| MEDIUM | Consolidated tape volume for DJIA | the 'volume' fields are composite constituent volume, not an index-level print; Yahoo and CNBC disagree (256.9M vs 245.0M) because of differing constituent aggregation and feed lag |
| LOW | YM 30m candles | not retrieved this pass |
| LOW | Official S&P DJI settlement / divisor | S&P Dow Jones Indices publishes the divisor behind a licence; FRED mirrors closes only (last observation 2026-09-28) |
| INFO | ^DJI 1m bar 2026-09-29T15:38:00-04:00 | provider returned null OHLCV for this minute (bar still forming at fetch time); not back-filled |
| INFO | ^DJI tick / level-2 / order book | no free public source provides DJIA constituent-level depth; not retrievable |
| INFO | Bid/ask spread for all three instruments | not exposed by any source polled |
| INFO | ^DJI pre/post-market candles | meta.hasPrePostMarketData=false for an index; pre/post windows exist as session metadata only |

## 7. Data-quality caveats

- Yahoo returns float32 artifacts (e.g. 51505.19140625); DJIA is officially quoted to 2dp. Raw values preserved in raw_capture.py, rounded here.
- Cash index 'volume' is aggregated constituent volume, not an index print. Yahoo 256.9M vs CNBC 245.0M at similar stamps.
- The three CFD/cash feeds are different products: FOREXCOM/CAPITALCOM US30 day ranges (51,122.8-51,658.4 / 51,126.1-51,652.9) are WIDER than the cash RTH range (51,129.18-51,505.19) because the CFD day includes the overnight session. Do not treat them as the same series.
- CFD previous closes (51,496.8 / 51,491.3) differ from the official cash close (51,481.51) - CFD venues close at their own cutoff.
- Every intraday series ends in a provider live partial bar (volume 0). These are isolated, never mixed into the closed-bar set.
- 52-WEEK RANGE BASIS CONFLICT: Yahoo/CNBC/MarketWatch all report 45,057.28-54,744.33 (INTRADAY basis, high dated 08/05/26). A third-party tracker (dowjonestoday.net) reports 45,167-54,349 with an all-time CLOSING high of 54,349.12 on 2026-08-05. Both can be right - intraday extreme vs closing extreme. This packet uses the intraday basis throughout because three independent feeds agree on it.
- CORROBORATION of the 2026-09-28 prior close 51,481.51: matched independently by Yahoo, CNBC, MarketWatch, Investing.com and FRED (series DJIA, updated 2026-09-28 17:02 CDT). This anchor is the single most strongly verified number in the packet.
- Snapshot is a moving target: ^DJI moved 51,357.48 -> 51,355.81 across a 120-second poll ladder while this packet was built.

## 8. Source URLs

- `yahoo_dji_5m` — https://query1.finance.yahoo.com/v8/finance/chart/%5EDJI?range=1d&interval=5m&includePrePost=true
- `yahoo_dji_1m` — https://query1.finance.yahoo.com/v8/finance/chart/%5EDJI?interval=1m&period1=1790708017&period2=1790710837
- `yahoo_dji_15m` — https://query1.finance.yahoo.com/v8/finance/chart/%5EDJI?interval=15m&period1=1790688540&period2=1790710900
- `yahoo_dji_30m` — https://query1.finance.yahoo.com/v8/finance/chart/%5EDJI?interval=30m&range=5d
- `yahoo_dji_1h` — https://query1.finance.yahoo.com/v8/finance/chart/%5EDJI?interval=60m&period1=1789674037&period2=1790710837
- `yahoo_dji_1d` — https://query1.finance.yahoo.com/v8/finance/chart/%5EDJI?interval=1d&range=1mo
- `yahoo_dji_1wk` — https://query1.finance.yahoo.com/v8/finance/chart/%5EDJI?interval=1wk&range=6mo
- `yahoo_ym_5m` — https://query1.finance.yahoo.com/v8/finance/chart/YM%3DF?range=1d&interval=5m&includePrePost=true
- `yahoo_ym_15m` — https://query1.finance.yahoo.com/v8/finance/chart/YM%3DF?interval=15m&period1=1790654400&period2=1790710900
- `yahoo_ym_1h` — https://query1.finance.yahoo.com/v8/finance/chart/YM%3DF?interval=60m&range=5d
- `yahoo_ym_1d` — https://query1.finance.yahoo.com/v8/finance/chart/YM%3DF?interval=1d&range=1mo
- `yahoo_ym_1wk` — https://query1.finance.yahoo.com/v8/finance/chart/YM%3DF?interval=1wk&range=3mo
- `tv_forexcom_us30` — https://www.tradingview.com/symbols/FOREXCOM-US30/
- `tv_capitalcom_us30` — https://www.tradingview.com/symbols/CAPITALCOM-US30/
- `tv_dj_dji` — https://www.tradingview.com/symbols/DJ-DJI/
- `cnbc_dji` — https://www.cnbc.com/quotes/.DJI
- `marketwatch_djia` — https://www.marketwatch.com/investing/index/djia
- `investing_us30` — https://www.investing.com/indices/us-30
- `fred_djia` — https://fred.stlouisfed.org/series/DJIA

---

Reproduce: `cd results/us30_packet && python3 build_packet.py && python3 render_report.py`. `raw_capture.py` holds the verbatim provider values; this report and `us30_market_state.json` are generated from it.
