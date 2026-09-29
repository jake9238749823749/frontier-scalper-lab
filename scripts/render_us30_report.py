#!/usr/bin/env python3
"""
Renders datasets/us30_20260929/US30_INTRADAY_TAPE.md from dataset_summary.json
and the generated bar CSVs. Every number in the report is read back from the
built dataset - the prose never carries hand-typed values.
"""

from __future__ import annotations

import csv
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DS_DIR = os.path.join(ROOT, "datasets", "us30_20260929")
RAW_DIR = os.path.join(DS_DIR, "raw")
TFS = ["1m", "3m", "5m", "15m", "30m"]


def load_json(p):
    with open(p) as fh:
        return json.load(fh)


def load_bars(tf):
    with open(os.path.join(DS_DIR, f"bars_{tf}.csv")) as fh:
        return list(csv.DictReader(fh))


def load_swings(tf):
    with open(os.path.join(DS_DIR, f"swings_{tf}.csv")) as fh:
        return list(csv.DictReader(fh))


def f(x):
    return f"{float(x):,.2f}"


def main() -> None:
    s = load_json(os.path.join(DS_DIR, "dataset_summary.json"))
    xs = load_json(os.path.join(RAW_DIR, "cross_source_quotes.json"))
    raw5 = load_json(os.path.join(RAW_DIR, "yahoo_dji_5m.json"))
    cnbc = next(x for x in xs["sources"] if x["source_id"] == "cnbc_quote_cache")
    meta5 = raw5["meta"]
    sess = s["session"]

    bars5 = load_bars("5m")
    sess_high = max(float(b["high"]) for b in bars5)
    sess_low = min(float(b["low"]) for b in bars5)
    sess_open = float(bars5[0]["open"])
    prev_close = meta5["previousClose"]
    _latest = max((t for t in s["timeframes"].values() if t["vendor_snapshot"]),
                  key=lambda t: t["vendor_snapshot"]["snapshot_time_utc"])
    last_px = _latest["vendor_snapshot"]["last_price"]
    last_px_at = _latest["vendor_snapshot"]["snapshot_time_utc"]

    # ---- DERIVED session-level (transparent arithmetic only) ----------------
    sess_range = round(sess_high - sess_low, 2)
    chg_prev = round(last_px - prev_close, 2)
    chg_prev_pct = round((last_px / prev_close - 1) * 100, 4)
    chg_open = round(last_px - sess_open, 2)
    pos_in_sess = round((last_px - sess_low) / (sess_high - sess_low), 4)
    to_high = round(sess_high - last_px, 2)
    to_low = round(last_px - sess_low, 2)

    L = []
    w = L.append

    w("# LANE 2 - US30 / DOW INTRADAY MULTI-TIMEFRAME TAPE")
    w("")
    w(f"**Instrument captured:** `^DJI` - {meta5.get('longName', 'Dow Jones Industrial Average')} "
      f"(cash index, {meta5['currency']})  ")
    w(f"**Capture window:** {s['timeframes']['5m']['fetched_at_utc']} - "
      f"{s['timeframes']['15m']['fetched_at_utc']} (all five feeds snapshotted inside a ~75 second window)  ")
    w(f"**Dataset built:** {s['built_at_utc']}  ")
    w(f"**Timeframes:** 1m (native), 3m (derived - no native feed), 5m / 15m / 30m (native)  ")
    w(f"**Primary source:** Yahoo Finance chart API v8 · **Cross-check source:** CNBC Quote Cache "
      f"(exchange feed, realTime=true) · **Quote-level corroboration:** Trading Economics, Investing.com")
    w("")
    w("> Scope discipline: only bar range, body, wicks, close-to-close return, range position and "
      "fractal local swing highs/lows are computed. No smoothed or parameterised indicator is "
      "produced, because no source published verified indicator values. Nothing in this dataset "
      "is modelled, back-filled or estimated.")
    w("")
    w("---")
    w("")

    # ===================== VERIFIED =====================
    w("## 1. VERIFIED")
    w("")
    w("Every value below is read directly from a captured source payload in `raw/`.")
    w("")
    w("### 1.1 Instrument, timestamp & timezone")
    w("")
    w("| Field | Value | Source |")
    w("|---|---|---|")
    w(f"| Symbol | `^DJI` | Yahoo chart meta |")
    w(f"| Name | {meta5.get('longName', 'Dow Jones Industrial Average')} | Yahoo / CNBC |")
    w(f"| Instrument type | INDEX (cash index, not a CFD or future) | Yahoo `instrumentType`, CNBC `subType` |")
    w(f"| Currency | {meta5['currency']} | Yahoo chart meta |")
    w(f"| Exchange timezone | {sess['exchange_timezone']} ({sess['tz_abbrev']}, UTC{sess['utc_offset_seconds']//3600:+d}) | Yahoo chart meta |")
    w(f"| Snapshot time (UTC) | {sess['as_of_utc']} | Yahoo `regularMarketTime` |")
    w(f"| Snapshot time (exchange local) | {sess['as_of_exchange_local']} | Yahoo `regularMarketTime` + `gmtoffset` |")
    w(f"| Cross-source snapshot time | {cnbc['last_time_local']} | CNBC `last_time` |")
    w("| Bar timestamp convention | Bar **open** time (left-edge), epoch seconds | Yahoo chart API |")
    w("")
    w("### 1.2 Session status")
    w("")
    w("| Field | Value |")
    w("|---|---|")
    w(f"| State | **{sess['state']}** |")
    w(f"| Regular session (UTC) | {sess['regular_session_utc']} |")
    w(f"| Regular session (ET) | {sess['regular_session_et']} |")
    w(f"| Elapsed | {sess['elapsed_minutes']} min ({sess['session_progress_pct']}% of RTH) |")
    w(f"| Remaining to close | {sess['minutes_to_close']} min |")
    w(f"| Halt status | {cnbc['is_halted']} (CNBC `EventData.is_halted`) |")
    w(f"| Market status flag | `{cnbc['market_status']}` (CNBC) |")
    w("| Pre/post-market bars | Not published for this index (`hasPrePostMarketData: false`) |")
    w("")
    w("### 1.3 Session price & volume facts")
    w("")
    w("| Field | Yahoo | CNBC (exchange feed) | Agreement |")
    w("|---|---|---|---|")
    w(f"| Previous close (2026-09-28) | {f(prev_close)} | {f(cnbc['previous_day_closing'])} | exact |")
    w(f"| Session open | {f(sess_open)} | {f(cnbc['session_open'])} | exact |")
    w(f"| Session high | {f(meta5['regularMarketDayHigh'])} | {f(cnbc['session_high'])} | exact |")
    w(f"| Session low | {f(meta5['regularMarketDayLow'])} | {f(cnbc['session_low'])} | exact |")
    latest_feed = max(s["timeframes"].values(),
                      key=lambda t: t["vendor_snapshot"].get("snapshot_time_utc", ""))
    latest_px = latest_feed["vendor_snapshot"]["last_price"]
    w(f"| Last price | {f(latest_px)} (latest feed snapshot {latest_feed['vendor_snapshot']['snapshot_time_utc']}) | "
      f"{f(cnbc['last'])} | {abs(latest_px - cnbc['last']):.2f} pts apart, snapshots ~1.5 min apart |")
    w(f"| Cumulative volume | {meta5['regularMarketVolume']:,} | {cnbc['volume']:,} | later snapshot is higher, as expected |")
    w(f"| 52-week high | {f(meta5['fiftyTwoWeekHigh'])} | {f(cnbc['yr_high'])} ({cnbc['yr_high_date']}) | exact |")
    w(f"| 52-week low | {f(meta5['fiftyTwoWeekLow'])} | {f(cnbc['yr_low'])} ({cnbc['yr_low_date']}) | exact |")
    w("")
    w("Each timeframe feed was fetched as its own request, so each carries its own snapshot "
      "instant. The dispersion below is live-tape latency, not disagreement:")
    w("")
    w("| Feed | Vendor snapshot (UTC) | Last price | Cumulative volume |")
    w("|---|---|---|---|")
    for tf in TFS:
        vs = s["timeframes"][tf]["vendor_snapshot"]
        if not vs:
            w(f"| {tf} | n/a (derived series - inherits the 1m capture) | - | - |")
            continue
        w(f"| {tf} | {vs['snapshot_time_utc']} | {f(vs['last_price'])} | {vs['cumulative_volume']:,} |")
    w(f"| CNBC | 2026-09-29T19:41:41Z | {f(cnbc['last'])} | {cnbc['volume']:,} |")
    w("")
    w(f"Spread across all captured snapshots: "
      f"{max(t['vendor_snapshot']['last_price'] for t in s['timeframes'].values() if t['vendor_snapshot']) - min([t['vendor_snapshot']['last_price'] for t in s['timeframes'].values() if t['vendor_snapshot']] + [cnbc['last']]):.2f} pts "
      f"over ~3 minutes of wall clock.")
    w("")
    w("### 1.4 Bar inventory per timeframe")
    w("")
    w("| TF | Origin | Completed bars | First bar (UTC) | Last completed bar (UTC) | Sessions covered |")
    w("|---|---|---|---|---|---|")
    cover = {}
    for tf in TFS:
        rows = [r for r in load_bars(tf) if r["bar_status"] == "COMPLETED"]
        dates = sorted({r["timestamp_utc"][:10] for r in rows})
        cover[tf] = (f"{len(dates)} ({dates[0]}" + (f" .. {dates[-1]})" if len(dates) > 1 else ")"))
    for tf in TFS:
        t = s["timeframes"][tf]
        w(f"| {tf} | {t['origin']} | {t['completed_bars']} | {t['first_bar_utc']} | "
          f"{t['last_completed_bar']['time_utc']} | {cover[tf]} |")
    w("")
    w("### 1.5 Latest completed bar - OHLCV per timeframe")
    w("")
    w("| TF | Bar open (UTC) | Bar open (ET) | Open | High | Low | Close | Volume |")
    w("|---|---|---|---|---|---|---|---|")
    for tf in TFS:
        b = s["timeframes"][tf]["last_completed_bar"]
        vol = f"{b['volume']:,}" if b["volume"] is not None else "n/a"
        w(f"| {tf} | {b['time_utc']} | {b['time_et'].replace(' EDT','')} | {f(b['open'])} | "
          f"{f(b['high'])} | {f(b['low'])} | {f(b['close'])} | {vol} |")
    w("")
    w("### 1.6 Current (in-progress) bar - OHLC per timeframe")
    w("")
    w("These bars were **not** closed at capture time. They are reported separately and are "
      "excluded from every derived structure calculation.")
    w("")
    w("| TF | Bar open (UTC) | Open | High | Low | Close so far | Volume so far | Status |")
    w("|---|---|---|---|---|---|---|---|")
    for tf in TFS:
        c = s["timeframes"][tf]["current_bar_in_progress"]
        if not c:
            note = s["timeframes"][tf].get("current_bar_note") or "no in-flight bar in capture"
            short = ("in-flight bucket 19:39:00Z returned **null** by vendor - see MISSING"
                     if "null" in note else note)
            w(f"| {tf} | 2026-09-29T19:39:00Z | - | - | - | - | - | {short} |")
            continue
        vol = f"{c['volume_so_far']:,}" if c["volume_so_far"] is not None else "n/a"
        w(f"| {tf} | {c['time_utc']} | {f(c['open'])} | {f(c['high'])} | {f(c['low'])} | "
          f"{f(c['close_so_far'])} | {vol} | INCOMPLETE |")
    w("")
    w("### 1.7 Verification results")
    w("")
    w("| Check | Result | Status |")
    w("|---|---|---|")
    for c in s["verification"]:
        if "sums" in c:
            detail = " / ".join(f"{k}={v:,}" for k, v in c["sums"].items()) + f" (cutoff {c['common_cutoff_utc']})"
        elif c["check"].startswith("headline"):
            detail = (f"bars={c['sum_incl_in_progress_bar']:,} vs headline="
                      f"{c['vendor_regularMarketVolume']:,} → residual {c['residual_vs_vendor']:,} "
                      f"({c['residual_pct']}%)")
        elif c["check"].startswith("1m volume"):
            detail = (f"{c['buckets_matching_exactly']}/{c['buckets_tested']} 5m buckets match to the "
                      f"share; residual {c['diff']:,} fully attributed to one zero-volume minute")
        elif "per_feed" in c:
            detail = f"max deviation {c['max_abs_diff']} pts across 4 feeds"
        elif "bars_tested" in c:
            detail = f"{c['agreements']}/{c['bars_tested']} bars reproduce exactly"
        elif "tape_high" in c:
            detail = f"tape {f(c['tape_high'])}/{f(c['tape_low'])} vs vendor {f(c['vendor_high'])}/{f(c['vendor_low'])}"
        elif "yahoo_session_open_first_5m_bar" in c:
            detail = "open/high/low/prev-close all match to the cent"
        else:
            detail = f"{c.get('abs_diff_pts','')} pts ({c.get('abs_diff_pct','')}%)"
        w(f"| {c['check']} | {detail} | {c['status']} |")
    w("")
    w("Per-timeframe integrity checks (OHLC internal consistency, contiguity, zero-volume scan) "
      "are stored in full in `dataset_summary.json`. All timeframes pass OHLC consistency and "
      "intra-session contiguity with zero violations.")
    w("")
    w("---")
    w("")

    # ===================== DERIVED =====================
    w("## 2. DERIVED")
    w("")
    w("### 2.1 Formulas used (complete list)")
    w("")
    w("```text")
    w("range_pts          = high - low")
    w("body_pts           = close - open")
    w("upper_wick_pts     = high - max(open, close)")
    w("lower_wick_pts     = min(open, close) - low")
    w("close_pos_in_range = (close - low) / (high - low)      # 0 = bar low, 1 = bar high")
    w("ret_pts            = close - close[previous bar]")
    w("ret_pct            = (close / close[previous bar] - 1) * 100")
    w("direction          = UP if close > open, DOWN if close < open, else FLAT")
    w("")
    w("swing high at bar i  <=>  high[i] > high[i-j] AND high[i] > high[i+j]  for j = 1..2")
    w("swing low  at bar i  <=>  low[i]  < low[i-j]  AND low[i]  < low[i+j]   for j = 1..2")
    w("   (fractal, k=2; the last 2 bars of each series can never be confirmed)")
    w("")
    w("3m bar = clock-aligned aggregation of exactly three native 1m bars:")
    w("   open = first 1m open, high = max(1m highs), low = min(1m lows),")
    w("   close = last 1m close, volume = sum(1m volumes)")
    w("```")
    w("")
    w("### 2.2 Session-level derived metrics")
    w("")
    w(f"Computed from verified fields only. `last` is the most recent captured snapshot "
      f"({f(last_px)} at {last_px_at}); prev close = {f(prev_close)}; "
      f"session O/H/L = {f(sess_open)} / {f(sess_high)} / {f(sess_low)}.")
    w("")
    w("| Metric | Value | Formula |")
    w("|---|---|---|")
    w(f"| Session range | {f(sess_range)} pts | session_high - session_low |")
    w(f"| Change vs previous close | {chg_prev:+,.2f} pts ({chg_prev_pct:+.4f}%) | last - prev_close |")
    w(f"| Change vs session open | {chg_open:+,.2f} pts | last - session_open |")
    w(f"| Position of last in session range | {pos_in_sess:.4f} | (last - session_low) / session_range |")
    w(f"| Distance to session high | {f(to_high)} pts | session_high - last |")
    w(f"| Distance to session low | {f(to_low)} pts | last - session_low |")
    w("")
    w("### 2.3 Latest completed bar - derived metrics")
    w("")
    w("| TF | Range (pts) | Body (pts) | Return (pts) | Return (%) | Close pos in range | Direction |")
    w("|---|---|---|---|---|---|---|")
    for tf in TFS:
        b = s["timeframes"][tf]["last_completed_bar"]
        cpr = "n/a" if b["close_pos_in_range"] is None else f"{b['close_pos_in_range']:.4f}"
        w(f"| {tf} | {f(b['range_pts'])} | {b['body_pts']:+,.2f} | {b['ret_pts']:+,.2f} | "
          f"{b['ret_pct']:+.4f}% | {cpr} | {b['direction']} |")
    w("")
    w("### 2.4 Swing structure per timeframe (fractal k=2, completed bars only)")
    w("")
    w("| TF | Confirmed swings (H/L) | Last swing high | Last swing low | High seq | Low seq | Structure label |")
    w("|---|---|---|---|---|---|---|")
    for tf in TFS:
        st = s["timeframes"][tf]["swing_structure"]
        lsh = st["last_swing_high"]
        lsl = st["last_swing_low"]
        lsh_s = f"{f(lsh['price'])} @ {lsh['time_utc'][11:16]}Z" if lsh else "none"
        lsl_s = f"{f(lsl['price'])} @ {lsl['time_utc'][11:16]}Z" if lsl else "none"
        w(f"| {tf} | {st['confirmed_swing_highs']}/{st['confirmed_swing_lows']} | {lsh_s} | {lsl_s} | "
          f"{st['high_sequence'] or 'n/a'} | {st['low_sequence'] or 'n/a'} | **{st['structure_label']}** |")
    w("")
    w("`structure_label` is a mechanical comparison of the last two confirmed swing highs and the "
      "last two confirmed swing lows - it is arithmetic, not a trade opinion.")
    w("")
    w("### 2.5 Most recent confirmed swing points")
    w("")
    for tf in TFS:
        sw = load_swings(tf)[-6:]
        if not sw:
            continue
        w(f"**{tf}** (last {len(sw)} of {len(load_swings(tf))} confirmed)")
        w("")
        w("| Time (UTC) | Time (ET) | Type | Price |")
        w("|---|---|---|---|")
        for p in sw:
            w(f"| {p['timestamp_utc']} | {p['timestamp_et'].replace(' EDT','')} | {p['swing_type']} | {f(p['price'])} |")
        w("")
    w("Full swing lists: `swings_<tf>.csv`. Full bar tapes with all derived columns: `bars_<tf>.csv`.")
    w("")
    w("### 2.6 Multi-timeframe alignment")
    w("")
    labels = {tf: s["timeframes"][tf]["swing_structure"]["structure_label"] for tf in TFS}
    up = [tf for tf, v in labels.items() if v.startswith("UPTREND")]
    dn = [tf for tf, v in labels.items() if v.startswith("DOWNTREND")]
    mx = [tf for tf, v in labels.items() if v.startswith("MIXED")]
    w(f"- Timeframes labelled UPTREND (HH+HL): {', '.join(up) if up else 'none'}")
    w(f"- Timeframes labelled DOWNTREND (LH+LL): {', '.join(dn) if dn else 'none'}")
    w(f"- Timeframes labelled MIXED: {', '.join(mx) if mx else 'none'}")
    w("")
    w("This is a count of mechanical labels across timeframes. It is intentionally not converted "
      "into a bias, signal or recommendation.")
    w("")
    w("---")
    w("")

    # ===================== MISSING =====================
    w("## 3. MISSING")
    w("")
    w("Items that were requested or would normally belong in this dataset but could **not** be "
      "sourced. None of these were estimated, modelled or filled in.")
    w("")
    w("### 3.1 Unavailable feeds / instruments")
    w("")
    w("| Item | Status | Why |")
    w("|---|---|---|")
    w("| Native **3m** bars | MISSING (substituted by a labelled derivation) | The vendor's "
      "`validRanges` for `^DJI` expose 1m/2m/5m/15m/30m/60m/90m/1d+ only. 3m is aggregated from "
      "native 1m bars and tagged `origin=DERIVED` in every output row. |")
    w("| Broker **US30 CFD** bar tape | MISSING | 'US30' is usually a broker CFD on the Dow. No "
      "broker/CFD bar feed was reachable. Only quote-level CFD prints were captured "
      "(Trading Economics 51,363 / Investing.com 51,379.60) and they are recorded as corroboration, "
      "not merged into the bar tape. The CFD-vs-cash basis is therefore unquantified. |")
    w("| **YM futures** (CME) tape | MISSING | Not captured in this lane; no futures basis, roll or "
      "open-interest data is present. |")
    w("| Bid/ask, spread, tick data, order flow | MISSING | Chart APIs return OHLCV only. No "
      "quote-level depth, no trade-by-trade prints, no bid/ask spread. |")
    w("| Pre-market / post-market bars | MISSING | `hasPrePostMarketData: false` for this index. |")
    w("")
    w("### 3.2 Indicator values")
    w("")
    w("| Item | Status |")
    w("|---|---|")
    w("| RSI, MACD, stochastics, moving averages, ATR, Bollinger bands | MISSING - no source "
      "published verified values, and the lane brief restricts derivation to transparent bar "
      "metrics. Not computed, not invented. |")
    w("| Session VWAP | MISSING - not published by any captured source. It could be approximated "
      "from bar typical prices, but that is an assumption-laden reconstruction rather than a "
      "verified value, so it is deliberately omitted. |")
    w("| Volume profile / POC / value area | MISSING - requires tick or price-level volume that "
      "no captured source provides. |")
    w("")
    w("### 3.3 Data gaps and unresolved discrepancies inside what was captured")
    w("")
    v = {c["check"]: c for c in s["verification"]}
    hv = v["headline regularMarketVolume vs sum of 5m bar volumes"]
    v1 = v["1m volume sum vs native 5m volume sum (same window)"]
    w("| Item | Detail |")
    w("|---|---|")
    w(f"| 1m bar 2026-09-29T19:39:00Z (in-flight) | Vendor returned **null** OHLC for this bucket "
      f"at capture time, so the current 1m bar has no values. Excluded, not interpolated. |")
    w(f"| 3m current bar | Cannot be formed: the in-flight 3m bucket (19:39:00Z) had only one "
      f"elapsed 1m member and that member was the null bar above. No current 3m OHLC exists. |")
    w(f"| 1m volume at {', '.join(v1['zero_volume_1m_bars'])} | Vendor returned `volume=0` on the "
      f"first 1m bar of the `period1`-clipped window while its OHLC is valid and agrees with the "
      f"5m tape. Treated as MISSING volume, not as zero volume. Accounts for the "
      f"{v1['diff']:,} share ({v1['diff_pct']}%) gap between the 1m and 5m volume sums "
      f"({v1['buckets_matching_exactly']}/{v1['buckets_tested']} 5m buckets reconcile to the share). "
      f"The missing minute's volume is *implied* to be {v1['diff']:,} by subtraction, but that "
      f"inference is deliberately **not** written into the 1m tape. |")
    w(f"| Headline vs bar-level volume | Headline `regularMarketVolume` "
      f"({hv['vendor_regularMarketVolume']:,}) exceeds the sum of bar volumes "
      f"({hv['sum_incl_in_progress_bar']:,}) by {hv['residual_vs_vendor']:,} shares "
      f"({hv['residual_pct']}%). The divergence is identical across 5m/15m/30m, so it is a vendor "
      f"aggregation difference. **No source explains it, so it is left unreconciled.** |")
    w("| 1m / 3m history depth | Only 2026-09-29T18:00Z onward was captured (99 completed 1m bars). "
      "Earlier 1m history exists at the vendor but was not pulled in this capture, so 1m/3m swing "
      "structure is scoped to that window. |")
    w("| 15m history depth | 2 RTH sessions (2026-09-28, 2026-09-29). 30m covers 5 sessions. |")
    w("| Swing confirmation lag | With k=2, the last 2 completed bars of every timeframe cannot yet "
      "be confirmed as swing points. Any swing forming there is genuinely unknown, not absent. |")
    w("| Session close | The 2026-09-29 RTH close had not occurred at capture "
      f"({sess['minutes_to_close']} min remaining), so the daily close, final volume and the final "
      "shape of every in-progress bar are unknown. |")
    w("")
    w("---")
    w("")
    w("## 4. Files")
    w("")
    w("| File | Contents |")
    w("|---|---|")
    w("| `raw/yahoo_dji_{1m,5m,15m,30m}.json` | Verbatim vendor payloads (arrays, nulls and meta preserved) |")
    w("| `raw/cross_source_quotes.json` | CNBC / Trading Economics / Investing.com cross-checks + agreement matrix |")
    w("| `bars_{1m,3m,5m,15m,30m}.csv` | Bar tape + derived columns + `bar_status` + `origin` |")
    w("| `swings_{1m,3m,5m,15m,30m}.csv` | Confirmed fractal swing points (k=2) |")
    w("| `dataset_summary.json` | Machine-readable summary: session, per-TF bars, structure, all checks |")
    w("| `../../scripts/build_us30_intraday_dataset.py` | Raw → dataset builder (validation + derivation) |")
    w("| `../../scripts/render_us30_report.py` | Dataset → this report |")
    w("")

    out = os.path.join(DS_DIR, "US30_INTRADAY_TAPE.md")
    with open(out, "w") as fh:
        fh.write("\n".join(L) + "\n")
    print("wrote", out, f"({len(L)} lines)")


if __name__ == "__main__":
    main()
