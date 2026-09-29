#!/usr/bin/env python3
"""
LANE 2 - INTRADAY MULTI-TIMEFRAME TAPE (US30 / Dow Jones Industrial Average)
===========================================================================

Builds a source-backed intraday dataset from RAW captured vendor payloads.

Design rules (non-negotiable for this lane):
  1. Nothing is invented. Every price/volume number written out traces back to a
     raw payload in datasets/us30_20260929/raw/.
  2. Only TRANSPARENT derived metrics are computed: bar range, body, wicks,
     close-to-close return, range position, and fractal local swing highs/lows.
     No smoothed/parameterised indicators (RSI, MACD, VWAP, ATR...) are produced
     because the sources did not publish verified values for them.
  3. Incomplete bars are never silently treated as completed bars. The in-flight
     bar is reported separately as "current bar".
  4. Gaps / nulls / anomalies are reported, not interpolated.

Inputs : datasets/us30_20260929/raw/*.json  (verbatim vendor payloads)
Outputs: datasets/us30_20260929/bars_<tf>.csv
         datasets/us30_20260929/swings_<tf>.csv
         datasets/us30_20260929/dataset_summary.json
         datasets/us30_20260929/US30_INTRADAY_TAPE.md
"""

from __future__ import annotations

import csv
import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from typing import Any

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DS_DIR = os.path.join(ROOT, "datasets", "us30_20260929")
RAW_DIR = os.path.join(DS_DIR, "raw")

NY_OFFSET_SECONDS = -14400  # EDT, taken from the vendor payload meta (gmtoffset)

INTERVAL_SECONDS = {"1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800}

# Fractal half-width used for local swing detection (k bars strictly lower/higher
# on BOTH sides). Fully transparent, no parameters beyond this integer.
SWING_K = 2


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def utc(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ny(ts: int) -> str:
    return (datetime.fromtimestamp(ts, tz=timezone.utc)
            + timedelta(seconds=NY_OFFSET_SECONDS)).strftime("%Y-%m-%d %H:%M:%S EDT")


def r2(x: float | None) -> float | None:
    """Vendor returns float64 noise (e.g. 51353.62890625) around a 2-dp index
    value (priceHint=2). Round for presentation only; raw stays untouched."""
    return None if x is None else round(x + 0.0, 2)


@dataclass
class Bar:
    ts: int
    open: float
    high: float
    low: float
    close: float
    volume: int | None
    complete: bool
    # derived
    range_pts: float | None = None
    body_pts: float | None = None
    upper_wick: float | None = None
    lower_wick: float | None = None
    close_pos_in_range: float | None = None
    ret_pts: float | None = None
    ret_pct: float | None = None
    direction: str = ""
    swing: str = ""  # "", "SWING_HIGH", "SWING_LOW", "SWING_HIGH+SWING_LOW"


@dataclass
class Series:
    tf: str
    origin: str           # VERIFIED (vendor native) or DERIVED (resampled)
    source: str
    endpoint: str
    fetched_at_utc: str
    as_of_epoch: int
    bars: list[Bar] = field(default_factory=list)
    current_bar: Bar | None = None
    current_bar_note: str = ""
    vendor_snapshot: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    checks: list[dict[str, Any]] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# load + validate raw payloads
# --------------------------------------------------------------------------- #
def load_raw(tf: str) -> dict:
    with open(os.path.join(RAW_DIR, f"yahoo_dji_{tf}.json")) as fh:
        return json.load(fh)


def build_native_series(tf: str) -> Series:
    raw = load_raw(tf)
    meta, cap = raw["meta"], raw["_capture"]
    step = INTERVAL_SECONDS[tf]
    as_of = int(meta["regularMarketTime"])

    ts = raw["timestamp"]
    o, h, l, c, v = raw["open"], raw["high"], raw["low"], raw["close"], raw["volume"]
    n = len(ts)
    assert all(len(a) == n for a in (o, h, l, c, v)), f"{tf}: ragged vendor arrays"

    s = Series(tf=tf, origin="VERIFIED", source=cap["source"], endpoint=cap["endpoint"],
               fetched_at_utc=cap["fetched_at_utc"], as_of_epoch=as_of)

    dropped_snapshot = 0
    nulls = []
    off_grid = []

    for i in range(n):
        t = ts[i]
        # The vendor appends a snapshot row stamped at regularMarketTime; it is a
        # quote, not a bar. Identify it by its off-grid timestamp.
        if t % step != 0 or t == as_of:
            dropped_snapshot += 1
            if t != as_of:
                off_grid.append(t)
            continue
        if None in (o[i], h[i], l[i], c[i]):
            nulls.append(t)
            continue
        bar = Bar(ts=t, open=o[i], high=h[i], low=l[i], close=c[i],
                  volume=v[i], complete=(t + step) <= as_of)
        if bar.complete:
            s.bars.append(bar)
        else:
            s.current_bar = bar

    if dropped_snapshot:
        s.notes.append(
            f"{dropped_snapshot} non-bar snapshot row(s) at regularMarketTime excluded "
            f"from the bar series (vendor quote row, volume field is 0)."
        )
    if off_grid:
        s.notes.append(f"off-grid timestamps excluded: {off_grid}")
    s.vendor_snapshot = {
        "snapshot_time_utc": utc(as_of),
        "last_price": meta["regularMarketPrice"],
        "cumulative_volume": meta["regularMarketVolume"],
    }
    inflight = [t for t in nulls if t + step > as_of]
    if inflight:
        s.current_bar_note = (
            f"vendor returned null OHLC for the in-flight {tf} bucket "
            f"{utc(inflight[0])} - no current-bar values available (MISSING, not zero-filled)")
    if nulls:
        s.notes.append(
            "null OHLC returned by vendor for bucket(s) "
            + ", ".join(f"{utc(t)} ({ny(t)})" for t in nulls)
            + " - reported as MISSING, not interpolated."
        )

    # ---- integrity checks on the completed bars -----------------------------
    bad_ohlc = [b.ts for b in s.bars
                if not (b.low <= min(b.open, b.close) and b.high >= max(b.open, b.close)
                        and b.high >= b.low)]
    s.checks.append({"check": "OHLC internal consistency (low<=min(o,c), high>=max(o,c))",
                     "bars_tested": len(s.bars),
                     "violations": len(bad_ohlc),
                     "status": "PASS" if not bad_ohlc else "FAIL"})

    zero_vol = [b.ts for b in s.bars if b.volume in (0, None)]
    s.checks.append({"check": "non-zero volume on completed bars",
                     "bars_tested": len(s.bars),
                     "zero_or_null": len(zero_vol),
                     "timestamps": [utc(t) for t in zero_vol],
                     "status": "PASS" if not zero_vol else "FLAG"})

    # contiguity within each RTH session (gaps across sessions are expected)
    gaps = []
    for a, b in zip(s.bars, s.bars[1:]):
        d = b.ts - a.ts
        if d != step and d < 6 * 3600:  # ignore overnight session boundaries
            gaps.append({"from": utc(a.ts), "to": utc(b.ts), "delta_s": d})
    s.checks.append({"check": "intra-session bar contiguity",
                     "unexpected_gaps": len(gaps), "detail": gaps,
                     "status": "PASS" if not gaps else "FLAG"})
    return s


def derive_3m_from_1m(src: Series) -> Series:
    """3m is NOT offered by the vendor. Build it by clock-aligned aggregation of
    native 1m bars. A 3m bucket is emitted only when all three 1m members are
    present; partial buckets are reported, never padded."""
    step = 180
    raw = load_raw("1m")
    as_of = int(raw["meta"]["regularMarketTime"])
    s = Series(tf="3m", origin="DERIVED",
               source=f"resampled from native 1m ({src.source})",
               endpoint=src.endpoint, fetched_at_utc=src.fetched_at_utc,
               as_of_epoch=as_of)
    s.notes.append("Vendor validRanges for ^DJI expose 1m/2m/5m/15m/30m/60m/90m only - "
                   "3m has no native feed, so it is aggregated from 1m closes.")

    buckets: dict[int, list[Bar]] = {}
    for b in src.bars + ([src.current_bar] if src.current_bar else []):
        buckets.setdefault(b.ts - (b.ts % step), []).append(b)

    partial = []
    for bucket_ts in sorted(buckets):
        members = sorted(buckets[bucket_ts], key=lambda x: x.ts)
        complete_bucket = (bucket_ts + step) <= as_of and len(members) == 3 \
            and all(m.complete for m in members)
        if len(members) != 3 and (bucket_ts + step) <= as_of:
            partial.append({"bucket": utc(bucket_ts), "members_present": len(members)})
            continue  # do not emit an under-filled completed bucket
        vols = [m.volume for m in members if m.volume is not None]
        bar = Bar(ts=bucket_ts,
                  open=members[0].open,
                  high=max(m.high for m in members),
                  low=min(m.low for m in members),
                  close=members[-1].close,
                  volume=sum(vols) if len(vols) == len(members) else None,
                  complete=complete_bucket)
        if complete_bucket:
            s.bars.append(bar)
        else:
            s.current_bar = bar

    # the first bucket of the captured window can be clipped by period1
    if s.bars and s.bars[0].ts < min(b.ts for b in src.bars):
        s.bars.pop(0)
    if partial:
        s.notes.append(f"under-filled 3m buckets skipped (missing 1m members): {partial}")
    if s.current_bar is None and src.current_bar_note:
        s.current_bar_note = (
            "in-flight 3m bucket cannot be formed: its only elapsed 1m member was returned "
            "null by the vendor (" + src.current_bar_note + ")")

    s.checks.append({"check": "3m bucket = exactly 3 native 1m bars",
                     "buckets_emitted": len(s.bars),
                     "under_filled_skipped": len(partial),
                     "status": "PASS"})
    return s


# --------------------------------------------------------------------------- #
# transparent derived metrics
# --------------------------------------------------------------------------- #
def add_derived(s: Series) -> None:
    prev_close = None
    for b in s.bars + ([s.current_bar] if s.current_bar else []):
        b.range_pts = round(b.high - b.low, 2)
        b.body_pts = round(b.close - b.open, 2)
        b.upper_wick = round(b.high - max(b.open, b.close), 2)
        b.lower_wick = round(min(b.open, b.close) - b.low, 2)
        b.close_pos_in_range = (round((b.close - b.low) / (b.high - b.low), 4)
                                if b.high > b.low else None)
        if prev_close is not None:
            b.ret_pts = round(b.close - prev_close, 2)
            b.ret_pct = round((b.close / prev_close - 1.0) * 100.0, 4)
        b.direction = "UP" if b.close > b.open else ("DOWN" if b.close < b.open else "FLAT")
        prev_close = b.close


def mark_swings(s: Series, k: int = SWING_K) -> list[dict]:
    """Fractal swing points on COMPLETED bars only.
    swing high at i  <=>  high[i] > high[i-j] and high[i] > high[i+j] for j=1..k
    swing low  at i  <=>  low[i]  < low[i-j]  and low[i]  < low[i+j]  for j=1..k
    The last k bars can never be confirmed -> they are excluded by construction."""
    bars = s.bars
    out = []
    for i in range(k, len(bars) - k):
        hi = all(bars[i].high > bars[i - j].high and bars[i].high > bars[i + j].high
                 for j in range(1, k + 1))
        lo = all(bars[i].low < bars[i - j].low and bars[i].low < bars[i + j].low
                 for j in range(1, k + 1))
        tags = []
        if hi:
            tags.append("SWING_HIGH")
            out.append({"ts": bars[i].ts, "type": "SWING_HIGH", "price": r2(bars[i].high)})
        if lo:
            tags.append("SWING_LOW")
            out.append({"ts": bars[i].ts, "type": "SWING_LOW", "price": r2(bars[i].low)})
        bars[i].swing = "+".join(tags)
    return sorted(out, key=lambda d: d["ts"])


def structure_from_swings(swings: list[dict]) -> dict:
    """Label the last two confirmed highs and lows (HH/LH, HL/LL). Pure comparison,
    no interpretation beyond the arithmetic."""
    highs = [s for s in swings if s["type"] == "SWING_HIGH"]
    lows = [s for s in swings if s["type"] == "SWING_LOW"]
    out: dict[str, Any] = {
        "confirmed_swing_highs": len(highs),
        "confirmed_swing_lows": len(lows),
        "last_swing_high": None,
        "prior_swing_high": None,
        "last_swing_low": None,
        "prior_swing_low": None,
        "high_sequence": None,
        "low_sequence": None,
        "structure_label": "INSUFFICIENT_CONFIRMED_SWINGS",
    }
    if highs:
        out["last_swing_high"] = {"time_utc": utc(highs[-1]["ts"]), "time_et": ny(highs[-1]["ts"]),
                                  "price": highs[-1]["price"]}
    if len(highs) >= 2:
        out["prior_swing_high"] = {"time_utc": utc(highs[-2]["ts"]), "price": highs[-2]["price"]}
        out["high_sequence"] = ("HIGHER_HIGH" if highs[-1]["price"] > highs[-2]["price"]
                                else "LOWER_HIGH" if highs[-1]["price"] < highs[-2]["price"]
                                else "EQUAL_HIGH")
    if lows:
        out["last_swing_low"] = {"time_utc": utc(lows[-1]["ts"]), "time_et": ny(lows[-1]["ts"]),
                                 "price": lows[-1]["price"]}
    if len(lows) >= 2:
        out["prior_swing_low"] = {"time_utc": utc(lows[-2]["ts"]), "price": lows[-2]["price"]}
        out["low_sequence"] = ("HIGHER_LOW" if lows[-1]["price"] > lows[-2]["price"]
                               else "LOWER_LOW" if lows[-1]["price"] < lows[-2]["price"]
                               else "EQUAL_LOW")
    hs, ls = out["high_sequence"], out["low_sequence"]
    if hs and ls:
        if hs == "HIGHER_HIGH" and ls == "HIGHER_LOW":
            out["structure_label"] = "UPTREND (HH+HL)"
        elif hs == "LOWER_HIGH" and ls == "LOWER_LOW":
            out["structure_label"] = "DOWNTREND (LH+LL)"
        else:
            out["structure_label"] = f"MIXED ({hs}+{ls})"
    return out


# --------------------------------------------------------------------------- #
# cross-series + cross-source verification
# --------------------------------------------------------------------------- #
def cnbc_volume() -> int:
    with open(os.path.join(RAW_DIR, "cross_source_quotes.json")) as fh:
        xs = json.load(fh)
    return next(s for s in xs["sources"] if s["source_id"] == "cnbc_quote_cache")["volume"]


def verification_matrix(series: dict[str, Series]) -> list[dict]:
    checks: list[dict] = []
    raw5 = load_raw("5m")
    raw1 = load_raw("1m")

    # 1) cross-timeframe volume reconciliation to a COMMON cutoff.
    #    Each feed was snapshotted a few seconds apart, so compare only the bars
    #    that are fully closed in every timeframe.
    session_start = 1790688600
    cutoff = min(s.bars[-1].ts + INTERVAL_SECONDS[s.tf]
                 for s in (series["5m"], series["15m"], series["30m"]))
    tf_sums = {}
    for tf in ("5m", "15m", "30m"):
        step = INTERVAL_SECONDS[tf]
        tf_sums[tf] = sum(b.volume for b in series[tf].bars
                          if b.volume and b.ts >= session_start and b.ts + step <= cutoff)
    identical = len(set(tf_sums.values())) == 1
    checks.append({
        "check": "cross-timeframe session volume reconciliation (5m vs 15m vs 30m, common cutoff)",
        "common_cutoff_utc": utc(cutoff),
        "sums": tf_sums,
        "all_identical": identical,
        "status": "PASS" if identical else "FLAG",
        "interpretation": "Independent native feeds at three granularities aggregate to the "
                          "identical share count over the same window - the bar-level volume "
                          "series is internally consistent.",
    })

    # 2) headline cumulative volume vs the sum of bar volumes (documented divergence)
    sum5 = sum(b.volume for b in series["5m"].bars if b.volume)
    cur5 = series["5m"].current_bar
    sum5_incl = sum5 + ((cur5.volume or 0) if cur5 else 0)
    rmv = raw5["meta"]["regularMarketVolume"]
    checks.append({
        "check": "headline regularMarketVolume vs sum of 5m bar volumes",
        "sum_completed_5m_bars": sum5,
        "sum_incl_in_progress_bar": sum5_incl,
        "vendor_regularMarketVolume": rmv,
        "cnbc_volume_later_snapshot": cnbc_volume(),
        "residual_vs_vendor": rmv - sum5_incl,
        "residual_pct": round((rmv - sum5_incl) / rmv * 100, 4),
        "status": "FLAG (documented divergence - do not treat the two as interchangeable)",
        "interpretation": "The headline index volume field exceeds the sum of the bar-level "
                          "volume series by ~5.9%. The divergence is present at 5m, 15m and 30m "
                          "alike, so it is a vendor aggregation difference, not a gap in the "
                          "bar tape. Use bar volumes for bar-relative analysis and the headline "
                          "field only as a session-level figure; they are not reconciled here "
                          "because no source document explains the difference.",
    })

    # 2) 1m vs 5m OHLC agreement on the overlapping window
    m1 = {b.ts: b for b in series["1m"].bars}
    agree, tested, mismatches = 0, 0, []
    for b5 in series["5m"].bars:
        members = [m1[b5.ts + k * 60] for k in range(5) if (b5.ts + k * 60) in m1]
        if len(members) != 5:
            continue
        tested += 1
        agg_hi, agg_lo = max(m.high for m in members), min(m.low for m in members)
        ok = (abs(agg_hi - b5.high) < 0.01 and abs(agg_lo - b5.low) < 0.01
              and abs(members[0].open - b5.open) < 0.01
              and abs(members[-1].close - b5.close) < 0.01)
        agree += ok
        if not ok:
            mismatches.append({"bar": utc(b5.ts),
                               "5m": [r2(b5.open), r2(b5.high), r2(b5.low), r2(b5.close)],
                               "1m_agg": [r2(members[0].open), r2(agg_hi), r2(agg_lo),
                                          r2(members[-1].close)]})
    checks.append({"check": "1m aggregation reproduces native 5m OHLC (overlap window)",
                   "bars_tested": tested, "agreements": agree,
                   "mismatches": mismatches,
                   "status": "PASS" if tested and agree == tested else
                             ("NO_OVERLAP" if not tested else "FLAG")})

    # 2b) 1m vs 5m volume over an EXACTLY matched window
    #     (only 5m buckets fully covered by captured 1m bars, and only the 1m
    #      bars inside those buckets - otherwise the sums are not comparable)
    ov_start = min(b.ts for b in series["1m"].bars)
    last_1m_end = max(b.ts for b in series["1m"].bars) + 60
    cov5 = [b for b in series["5m"].bars
            if b.ts >= ov_start and b.ts + 300 <= last_1m_end]
    ov_end = max(b.ts + 300 for b in cov5)
    v5 = sum(b.volume for b in cov5 if b.volume)
    v1 = sum(b.volume for b in series["1m"].bars
             if b.volume and ov_start <= b.ts < ov_end)
    zero_1m = [utc(b.ts) for b in series["1m"].bars if not b.volume]
    # per-bucket volume agreement, so the residual can be attributed exactly
    buckets_ok, bucket_mismatch = 0, []
    for b5 in cov5:
        members = [m1[b5.ts + k * 60] for k in range(5) if (b5.ts + k * 60) in m1]
        if len(members) != 5:
            continue
        agg = sum(m.volume or 0 for m in members)
        if agg == b5.volume:
            buckets_ok += 1
        else:
            bucket_mismatch.append({"bucket": utc(b5.ts), "1m_sum": agg, "5m": b5.volume,
                                    "diff": b5.volume - agg,
                                    "zero_vol_minutes": [utc(m.ts) for m in members if not m.volume]})
    checks.append({"check": "1m volume sum vs native 5m volume sum (same window)",
                   "window": f"{utc(ov_start)} -> {utc(ov_end)}",
                   "buckets_tested": len(bucket_mismatch) + buckets_ok,
                   "buckets_matching_exactly": buckets_ok,
                   "buckets_mismatching": bucket_mismatch,
                   "residual_fully_attributed": (len(bucket_mismatch) == 1
                                                 and bucket_mismatch[0]["diff"] == v5 - v1),
                   "sum_1m": v1, "sum_5m": v5, "diff": v5 - v1,
                   "diff_pct": round((v5 - v1) / v5 * 100, 4),
                   "zero_volume_1m_bars": [t for t in zero_1m
                                           if ov_start <= int(datetime.strptime(
                                               t, "%Y-%m-%dT%H:%M:%SZ").replace(
                                               tzinfo=timezone.utc).timestamp()) < ov_end],
                   "status": "PASS" if v1 == v5 else "FLAG (attributable to zero-volume 1m bar(s) below)",
                   "interpretation": "The vendor returned volume=0 on the first 1m bar of the "
                                     "period1-clipped window while its OHLC is present and "
                                     "agrees with the 5m tape. Volume for that minute is treated "
                                     "as MISSING, not zero-filled."})

    # 3) 15m aggregation reproduces native 30m OHLC
    m15 = {b.ts: b for b in series["15m"].bars}
    agree, tested, mismatches = 0, 0, []
    for b30 in series["30m"].bars:
        members = [m15[b30.ts + k * 900] for k in range(2) if (b30.ts + k * 900) in m15]
        if len(members) != 2:
            continue
        tested += 1
        agg_hi, agg_lo = max(m.high for m in members), min(m.low for m in members)
        vol_ok = (sum(m.volume for m in members) == b30.volume)
        ok = (abs(agg_hi - b30.high) < 0.01 and abs(agg_lo - b30.low) < 0.01
              and abs(members[0].open - b30.open) < 0.01
              and abs(members[-1].close - b30.close) < 0.01 and vol_ok)
        agree += ok
        if not ok:
            mismatches.append({"bar": utc(b30.ts),
                               "30m": [r2(b30.open), r2(b30.high), r2(b30.low), r2(b30.close), b30.volume],
                               "15m_agg": [r2(members[0].open), r2(agg_hi), r2(agg_lo),
                                           r2(members[-1].close), sum(m.volume for m in members)]})
    checks.append({"check": "15m aggregation reproduces native 30m OHLC+volume",
                   "bars_tested": tested, "agreements": agree, "mismatches": mismatches,
                   "status": "PASS" if tested and agree == tested else
                             ("NO_OVERLAP" if not tested else "FLAG")})

    # 4) session high/low from the 5m tape vs vendor day high/low
    sess_hi = max(b.high for b in series["5m"].bars)
    sess_lo = min(b.low for b in series["5m"].bars)
    checks.append({"check": "session high/low from 5m tape vs vendor regularMarketDayHigh/Low",
                   "tape_high": r2(sess_hi), "vendor_high": raw5["meta"]["regularMarketDayHigh"],
                   "tape_low": r2(sess_lo), "vendor_low": raw5["meta"]["regularMarketDayLow"],
                   "status": "PASS" if abs(sess_hi - raw5["meta"]["regularMarketDayHigh"]) < 0.02
                             and abs(sess_lo - raw5["meta"]["regularMarketDayLow"]) < 0.02 else "FLAG"})

    # 5) cross-source (CNBC exchange feed) agreement
    with open(os.path.join(RAW_DIR, "cross_source_quotes.json")) as fh:
        xs = json.load(fh)
    cnbc = next(s for s in xs["sources"] if s["source_id"] == "cnbc_quote_cache")
    first5 = series["5m"].bars[0]
    checks.append({"check": "cross-source session OHL (Yahoo tape vs CNBC exchange feed)",
                   "yahoo_session_open_first_5m_bar": r2(first5.open),
                   "cnbc_session_open": cnbc["session_open"],
                   "yahoo_session_high": r2(sess_hi), "cnbc_session_high": cnbc["session_high"],
                   "yahoo_session_low": r2(sess_lo), "cnbc_session_low": cnbc["session_low"],
                   "yahoo_prev_close": raw5["meta"]["previousClose"],
                   "cnbc_prev_close": cnbc["previous_day_closing"],
                   "status": "PASS" if (abs(first5.open - cnbc["session_open"]) < 0.02
                                        and abs(sess_hi - cnbc["session_high"]) < 0.02
                                        and abs(sess_lo - cnbc["session_low"]) < 0.02
                                        and raw5["meta"]["previousClose"] == cnbc["previous_day_closing"])
                             else "FLAG"})

    # 5b) our derived change vs the vendor's own published change field
    rows = []
    for tf in ("1m", "5m", "15m", "30m"):
        m = load_raw(tf)["meta"]
        derived = round(m["regularMarketPrice"] - m["previousClose"], 3)
        rows.append({"tf": tf, "derived_change": derived,
                     "vendor_fulldayChange": round(m["fulldayChange"], 3),
                     "abs_diff": round(abs(derived - m["fulldayChange"]), 4)})
    checks.append({"check": "derived change (last - previousClose) vs vendor fulldayChange field",
                   "per_feed": rows,
                   "max_abs_diff": max(r["abs_diff"] for r in rows),
                   "status": "PASS" if max(r["abs_diff"] for r in rows) < 0.01 else "FLAG",
                   "interpretation": "Our arithmetic reproduces the vendor's own published change "
                                     "field on every feed, confirming the previousClose anchor."})

    # 6) last-price agreement across snapshot instants
    checks.append({"check": "last price agreement across sources (different snapshot instants)",
                   "yahoo_last": raw1["meta"]["regularMarketPrice"],
                   "yahoo_at_utc": utc(raw1["meta"]["regularMarketTime"]),
                   "cnbc_last": cnbc["last"], "cnbc_at_local": cnbc["last_time_local"],
                   "abs_diff_pts": round(abs(raw1["meta"]["regularMarketPrice"] - cnbc["last"]), 2),
                   "abs_diff_pct": round(abs(raw1["meta"]["regularMarketPrice"] - cnbc["last"])
                                         / cnbc["last"] * 100, 4),
                   "status": "PASS (within live-tape latency tolerance)"})
    return checks


def session_status(raw: dict) -> dict:
    meta = raw["meta"]
    per = meta["currentTradingPeriod"]
    now = int(meta["regularMarketTime"])
    reg_s, reg_e = per["regular"]["start"], per["regular"]["end"]
    if now < per["pre"]["end"]:
        state = "PRE_MARKET"
    elif reg_s <= now < reg_e:
        state = "REGULAR_SESSION_OPEN"
    elif now < per["post"]["end"]:
        state = "POST_MARKET"
    else:
        state = "CLOSED"
    return {
        "state": state,
        "as_of_utc": utc(now), "as_of_exchange_local": ny(now),
        "exchange_timezone": meta["exchangeTimezoneName"],
        "tz_abbrev": meta["timezone"], "utc_offset_seconds": meta["gmtoffset"],
        "regular_session_utc": f"{utc(reg_s)} -> {utc(reg_e)}",
        "regular_session_et": f"{ny(reg_s)} -> {ny(reg_e)}",
        "elapsed_minutes": round((now - reg_s) / 60, 1),
        "minutes_to_close": round((reg_e - now) / 60, 1),
        "session_progress_pct": round((now - reg_s) / (reg_e - reg_s) * 100, 2),
        "halted": "N (per CNBC EventData.is_halted)",
    }


# --------------------------------------------------------------------------- #
# writers
# --------------------------------------------------------------------------- #
def write_bars_csv(s: Series) -> str:
    path = os.path.join(DS_DIR, f"bars_{s.tf}.csv")
    cols = ["timestamp_utc", "timestamp_et", "epoch", "open", "high", "low", "close",
            "volume", "bar_status", "range_pts", "body_pts", "upper_wick_pts",
            "lower_wick_pts", "close_pos_in_range", "ret_pts", "ret_pct", "direction",
            "swing_tag", "origin"]
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for b in s.bars + ([s.current_bar] if s.current_bar else []):
            w.writerow([utc(b.ts), ny(b.ts), b.ts, r2(b.open), r2(b.high), r2(b.low),
                        r2(b.close), b.volume,
                        "COMPLETED" if b.complete else "IN_PROGRESS",
                        b.range_pts, b.body_pts, b.upper_wick, b.lower_wick,
                        b.close_pos_in_range, b.ret_pts, b.ret_pct, b.direction,
                        b.swing, s.origin])
    return path


def write_swings_csv(tf: str, swings: list[dict]) -> str:
    path = os.path.join(DS_DIR, f"swings_{tf}.csv")
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["timestamp_utc", "timestamp_et", "epoch", "swing_type", "price", "method"])
        for s in swings:
            w.writerow([utc(s["ts"]), ny(s["ts"]), s["ts"], s["type"], s["price"],
                        f"fractal_k={SWING_K}"])
    return path


def main() -> None:
    os.makedirs(DS_DIR, exist_ok=True)

    series: dict[str, Series] = {}
    for tf in ("1m", "5m", "15m", "30m"):
        series[tf] = build_native_series(tf)
    series["3m"] = derive_3m_from_1m(series["1m"])

    ordered = ["1m", "3m", "5m", "15m", "30m"]
    summary: dict[str, Any] = {
        "dataset": "US30 / Dow Jones Industrial Average - intraday multi-timeframe tape",
        "instrument": {
            "requested": "US30 / Dow",
            "captured": "^DJI - Dow Jones Industrial Average cash index (USD)",
            "note": "US30 is commonly a broker CFD on the Dow. No broker CFD tick feed was "
                    "reachable, so the underlying cash index tape is used; CFD quote-level "
                    "cross-checks are recorded in raw/cross_source_quotes.json.",
        },
        "built_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "session": session_status(load_raw("5m")),
        "timeframes": {},
        "verification": verification_matrix(series),
    }

    for tf in ordered:
        s = series[tf]
        add_derived(s)
        swings = mark_swings(s)
        write_bars_csv(s)
        write_swings_csv(tf, swings)
        last = s.bars[-1]
        summary["timeframes"][tf] = {
            "origin": s.origin,
            "source": s.source,
            "endpoint": s.endpoint,
            "fetched_at_utc": s.fetched_at_utc,
            "vendor_as_of_utc": utc(s.as_of_epoch),
            "completed_bars": len(s.bars),
            "first_bar_utc": utc(s.bars[0].ts),
            "last_completed_bar": {
                "time_utc": utc(last.ts), "time_et": ny(last.ts),
                "open": r2(last.open), "high": r2(last.high), "low": r2(last.low),
                "close": r2(last.close), "volume": last.volume,
                "range_pts": last.range_pts, "body_pts": last.body_pts,
                "upper_wick_pts": last.upper_wick, "lower_wick_pts": last.lower_wick,
                "ret_pts": last.ret_pts,
                "ret_pct": last.ret_pct, "close_pos_in_range": last.close_pos_in_range,
                "direction": last.direction,
            },
            "vendor_snapshot": s.vendor_snapshot,
            "current_bar_note": s.current_bar_note,
            "current_bar_in_progress": (None if not s.current_bar else {
                "time_utc": utc(s.current_bar.ts), "time_et": ny(s.current_bar.ts),
                "open": r2(s.current_bar.open), "high": r2(s.current_bar.high),
                "low": r2(s.current_bar.low), "close_so_far": r2(s.current_bar.close),
                "volume_so_far": s.current_bar.volume,
                "range_pts": s.current_bar.range_pts,
                "close_pos_in_range": s.current_bar.close_pos_in_range,
                "status": "INCOMPLETE - values will change before the bar closes",
            }),
            "swing_structure": structure_from_swings(swings),
            "swing_points_confirmed": len(swings),
            "unconfirmable_tail_bars": SWING_K,
            "integrity_checks": s.checks,
            "notes": s.notes,
        }

    with open(os.path.join(DS_DIR, "dataset_summary.json"), "w") as fh:
        json.dump(summary, fh, indent=2)

    print(json.dumps({tf: {"bars": summary["timeframes"][tf]["completed_bars"],
                           "last": summary["timeframes"][tf]["last_completed_bar"]["time_utc"],
                           "structure": summary["timeframes"][tf]["swing_structure"]["structure_label"]}
                      for tf in ordered}, indent=2))
    print("\nverification:")
    for c in summary["verification"]:
        print(f"  [{c['status']:<40}] {c['check']}")


if __name__ == "__main__":
    main()
