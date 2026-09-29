# LANE 4 — US30 Cash Session-Level Map

**Snapshot:** Tuesday, 2026-09-29, **15:39:05 EDT / 19:39:05 UTC**<br>
**Canonical instrument:** Dow Jones Industrial Average cash index (**^DJI / .DJI**), USD points.<br>
**Cash-session convention:** New York regular session, 09:30–16:00 EDT (13:30–20:00 UTC). The session was still open when captured, so current-session high/low are **as-of** values, not final settlement values.

> **Instrument control.** “US30” commonly denotes a provider-specific CFD. This map does **not** present a CME YM futures quote or a CFD quote as cash DJIA. A broker execution map needs that broker’s own bid/ask and daily-reset convention; otherwise it must remain MISSING.

## Verified price map

| ID | Level | Price (USD points) | Classification | Source, source timestamp, and definition |
| --- | --- | ---: | --- | --- |
| PX | Current cash price | 51,365.36 | observed | [Yahoo Finance — US market live](https://finance.yahoo.com/markets/live/stock-market-today-tuesday-september-29-dow-sp-500-nasdaq-080526442.html) — `2026-09-29T19:39:05Z`<br>Source-reported ^DJI last 51,365.36 at 15:39:05 EDT; market open.<br>Last reported ^DJI cash-index value; this is not a broker-specific US30 CFD quote. |
| S-O | Regular-session / cash open | 51,416.96 | observed | [Google Finance — .DJI:INDEXDJX](https://www.google.com/finance/quote/.DJI:INDEXDJX) — `2026-09-29T19:37:02Z`<br>Source-reported quote timestamp 15:37:02 EDT; regular cash session open/high/low.<br>Provider-reported DJIA regular-session open at 09:30 EDT (13:30 UTC). |
| S-H | Regular-session high | 51,505.19 | observed | [Google Finance — .DJI:INDEXDJX](https://www.google.com/finance/quote/.DJI:INDEXDJX) — `2026-09-29T19:37:02Z`<br>Source-reported quote timestamp 15:37:02 EDT; regular cash session open/high/low.<br>Provider-reported DJIA cash-session high from 09:30 EDT through the source timestamp. |
| S-L | Regular-session low | 51,129.18 | observed | [Google Finance — .DJI:INDEXDJX](https://www.google.com/finance/quote/.DJI:INDEXDJX) — `2026-09-29T19:37:02Z`<br>Source-reported quote timestamp 15:37:02 EDT; regular cash session open/high/low.<br>Provider-reported DJIA cash-session low from 09:30 EDT through the source timestamp. |
| PDH | Prior-day high | 51,780.50 | observed | [Yahoo Finance — ^DJI historical prices](https://finance.yahoo.com/quote/%5EDJI/history/) — `2026-09-28T20:00:00Z`<br>2026-09-28 regular-session daily OHLC; 16:00 EDT cash close.<br>DJIA regular-session high for Monday, 2026-09-28. |
| PDL | Prior-day low | 51,409.65 | observed | [Yahoo Finance — ^DJI historical prices](https://finance.yahoo.com/quote/%5EDJI/history/) — `2026-09-28T20:00:00Z`<br>2026-09-28 regular-session daily OHLC; 16:00 EDT cash close.<br>DJIA regular-session low for Monday, 2026-09-28. |
| PDC | Prior-day close | 51,481.51 | observed | [Yahoo Finance — ^DJI historical prices](https://finance.yahoo.com/quote/%5EDJI/history/) — `2026-09-28T20:00:00Z`<br>2026-09-28 regular-session daily OHLC; 16:00 EDT cash close.<br>DJIA regular-session close for Monday, 2026-09-28. |
| S-MID | Session midpoint | 51,317.19 | derived | [Lane 4 calculation](https://www.google.com/finance/quote/.DJI:INDEXDJX) — `2026-09-29T19:40:34Z`<br>Arithmetic performed from the cited S-H and S-L values; no market-data estimate.<br>(Regular-session high + regular-session low) / 2. Inputs: S-H, S-L. |

### Price ladder — highest to lowest

| Price | Reference |
| ---: | --- |
| 51,780.50 | Prior-day high (PDH) |
| 51,505.19 | Regular-session high (S-H) |
| 51,481.51 | Prior-day close (PDC) |
| 51,416.96 | Cash open (S-O) |
| 51,409.65 | Prior-day low (PDL) |
| 51,365.36 | Current cash price (PX) |
| 51,317.19 | Session midpoint (S-MID) |
| 51,129.18 | Regular-session low (S-L) |

## Conditional structural references

A price extreme is observable; a “liquidity pool” is an execution hypothesis. The following rows are therefore **conditional**, never an assertion that orders are resting there.

| ID | Reference | Price (USD points) | Classification | Source, source timestamp, and definition |
| --- | --- | ---: | --- | --- |
| LQ-PDH | Prior-day-high reference | 51,780.50 | conditional | [Yahoo Finance — ^DJI historical prices](https://finance.yahoo.com/quote/%5EDJI/history/) — `2026-09-28T20:00:00Z`<br>2026-09-28 regular-session daily OHLC; 16:00 EDT cash close.<br>Conditional buy-side liquidity reference; no resting orders are asserted. Inputs: PDH. |
| LQ-PDL | Prior-day-low reference | 51,409.65 | conditional | [Yahoo Finance — ^DJI historical prices](https://finance.yahoo.com/quote/%5EDJI/history/) — `2026-09-28T20:00:00Z`<br>2026-09-28 regular-session daily OHLC; 16:00 EDT cash close.<br>Conditional sell-side liquidity reference; no resting orders are asserted. Inputs: PDL. |
| LQ-S-H | Session-high reference | 51,505.19 | conditional | [Google Finance — .DJI:INDEXDJX](https://www.google.com/finance/quote/.DJI:INDEXDJX) — `2026-09-29T19:37:02Z`<br>Source-reported quote timestamp 15:37:02 EDT; regular cash session open/high/low.<br>Conditional buy-side liquidity reference while the session remains open. Inputs: S-H. |
| LQ-S-L | Session-low reference | 51,129.18 | conditional | [Google Finance — .DJI:INDEXDJX](https://www.google.com/finance/quote/.DJI:INDEXDJX) — `2026-09-29T19:37:02Z`<br>Source-reported quote timestamp 15:37:02 EDT; regular cash session open/high/low.<br>Conditional sell-side liquidity reference while the session remains open. Inputs: S-L. |

## Required fields that remain unverified

The 30-minute opening range is explicitly 09:30:00–09:59:59 EDT. VWAP bands mean session VWAP ± one or two *volume-weighted intraday* standard deviations; that methodology cannot be reproduced from a daily OHLC aggregate.

| ID | Level | Price (USD points) | Classification | Source, source timestamp, and definition |
| --- | --- | ---: | --- | --- |
| ON-H | Overnight high | **MISSING** | — | CME YM window 18:00 EDT (prior business day) to 09:30 EDT (cash open).<br><strong>Why:</strong> No verified YM intraday series/basis adjustment was supplied. Cash ^DJI itself does not trade overnight. |
| ON-L | Overnight low | **MISSING** | — | CME YM window 18:00 EDT (prior business day) to 09:30 EDT (cash open).<br><strong>Why:</strong> No verified YM intraday series/basis adjustment was supplied. Cash ^DJI itself does not trade overnight. |
| OR30-H | Opening-range high (30 min) | **MISSING** | — | High from 09:30:00 to 09:59:59 EDT; the convention is explicitly 30 minutes.<br><strong>Why:</strong> Verified sources supplied daily/session aggregates, not 1-minute cash bars for the defined window. |
| OR30-L | Opening-range low (30 min) | **MISSING** | — | Low from 09:30:00 to 09:59:59 EDT; the convention is explicitly 30 minutes.<br><strong>Why:</strong> Verified sources supplied daily/session aggregates, not 1-minute cash bars for the defined window. |
| VWAP | Regular-session VWAP | **MISSING** | — | Volume-weighted average price from 09:30 EDT cash open to the snapshot time.<br><strong>Why:</strong> No verified intraday price-and-volume series for a defined DJIA VWAP calculation was available. Do not use a cash-index proxy or synthetic volume. |
| VWAP+1SD | VWAP +1 standard deviation | **MISSING** | — | VWAP plus one volume-weighted intraday standard deviation, using the same cash-session bars.<br><strong>Why:</strong> VWAP and a verified intraday price-and-volume series are MISSING. |
| VWAP-1SD | VWAP −1 standard deviation | **MISSING** | — | VWAP minus one volume-weighted intraday standard deviation, using the same cash-session bars.<br><strong>Why:</strong> VWAP and a verified intraday price-and-volume series are MISSING. |
| VWAP+2SD | VWAP +2 standard deviations | **MISSING** | — | VWAP plus two volume-weighted intraday standard deviations, using the same cash-session bars.<br><strong>Why:</strong> VWAP and a verified intraday price-and-volume series are MISSING. |
| VWAP-2SD | VWAP −2 standard deviations | **MISSING** | — | VWAP minus two volume-weighted intraday standard deviations, using the same cash-session bars.<br><strong>Why:</strong> VWAP and a verified intraday price-and-volume series are MISSING. |
| EQH | Verified equal-high pool | **MISSING** | — | Two or more separately timestamped intraday swing highs within a declared tolerance.<br><strong>Why:</strong> No verified intraday bar series was available to test equality, tolerance, or swing separation. |
| EQL | Verified equal-low pool | **MISSING** | — | Two or more separately timestamped intraday swing lows within a declared tolerance.<br><strong>Why:</strong> No verified intraday bar series was available to test equality, tolerance, or swing separation. |

## Source ledger and handling notes

1. **Current price:** Yahoo Finance’s live market page reported ^DJI at **51,365.36** at **15:39:05 EDT**. It is the freshest verified price used here.
2. **Current session OHLC:** Google Finance’s .DJI quote page reported the **51,416.96 / 51,505.19 / 51,129.18** open/high/low at **15:37:02 EDT**. Because the later cash price was inside that range, the cited high and low remain valid at the snapshot time; the map does not imply they were final values.
3. **Prior-day OHLC:** Yahoo Finance’s historical-price table reports the 2026-09-28 cash-session OHLC. Its close is independently consistent with the FRED DJIA daily-close series, whose source is S&P Dow Jones Indices.
4. **No silent proxies:** Cash DJIA has no overnight cash session. CME YM is a distinct futures instrument and can have a basis to cash. Overnight, OR, VWAP, VWAP deviations, and equal-high/equal-low rows stay **MISSING** until a timestamped intraday source for the exact instrument and definition is supplied.

*This is an auditable market-data map, not investment advice. Prices may differ by vendor, index dissemination latency, and any broker’s CFD spread.*
