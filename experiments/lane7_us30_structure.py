"""
LANE 7 — US30 / Dow intraday market structure & liquidity.

Runs the Lane-7 detectors over the captured ^DJI (cash) and YM=F (E-mini Dow
futures) bars and writes an auditable report.

    python -m experiments.lane7_us30_structure

Outputs
    results/lane7_us30_structure/LANE7_MARKET_STRUCTURE.md
    results/lane7_us30_structure/events_*.csv
    results/lane7_us30_structure/bars_*.csv
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

from engine.yahoo_chart_ingest import load_chart, load_and_stitch, bar_table
from engine.lane7_verify import build_dji_1m, YM_SLICES
from engine.lane7_structure import (
    Level, atr, swings, detect_fvg, detect_displacement, detect_consolidation,
    classify_level_interaction, detect_reclaim, structure_shifts, events_to_frame,
    untouched_levels,
)

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "results", "lane7_us30_structure")

# detector parameters — printed into the report so results are reproducible
P = dict(
    swing_k_5m=3, swing_k_1m=5,
    disp_atr_n_5m=14, disp_mult_5m=2.0, disp_maxbars_5m=5, disp_er=0.70,
    disp_atr_n_1m=30, disp_mult_1m=2.5, disp_maxbars_1m=10,
    fvg_min_5m=5.0, fvg_min_1m=10.0,
    cons_window=12, cons_er_max=0.25, cons_range_atr=2.5,
    confirm_bars=6, reclaim_away=5, reclaim_hold=5,
)



def day_row(df: pd.DataFrame, date: str) -> pd.Series:
    """Single daily bar for `date`, regardless of whether .loc returns a row or a frame."""
    sel = df.loc[date]
    return sel.iloc[0] if isinstance(sel, pd.DataFrame) else sel


def resample_5m(df: pd.DataFrame) -> pd.DataFrame:
    """
    5-minute series built from the VERIFIED 1-minute series rather than from the
    5-minute payload. Both agree exactly over their overlap (integrity gate), but
    the 1m capture runs to 15:59 while the 5m payload was pulled at 15:35, so
    resampling is the only way to cover the full session at 5m.
    """
    out = df.resample("5min", closed="left", label="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    ).dropna(subset=["open", "high", "low", "close"])
    out.index.name = "ts_utc"
    return out


def build():
    dji1 = build_dji_1m()
    dji5 = load_chart("DJI_5m_1d.json")
    dji30 = load_chart("DJI_30m_5d.json")
    djid = load_chart("DJI_1d_1mo.json")
    ym5 = load_and_stitch(YM_SLICES)
    ymd = load_chart("YM_1d_1mo.json")
    return dji1, dji5, dji30, djid, ym5, ymd


def dji_levels(dji1, dji5, djid, close_px: float) -> list[Level]:
    d = djid.bars
    prev = d.iloc[-2]                     # Mon 2026-09-28
    sep24 = day_row(d, "2026-09-24")
    sep16 = day_row(d, "2026-09-16")
    b = dji1.bars
    ib = b.loc["2026-09-29 09:30":"2026-09-29 10:29"]   # Initial Balance, first 60 min
    return [
        Level("PDH  (prior day high, 09-28)", float(prev["high"]), "high", "DJI_1d_1mo.json bar 19"),
        Level("PDC  (prior day close, 09-28)", float(prev["close"]), "high", "DJI_1d_1mo.json bar 19"),
        Level("PDL  (prior day low, 09-28)", float(prev["low"]), "low", "DJI_1d_1mo.json bar 19"),
        Level("RTH open (today)", float(b["open"].iloc[0]), "low", "DJI 1m 09:30 open"),
        Level("IB high (09:30-10:30)", float(ib["high"].max()), "high", "DJI 1m 09:30-10:29"),
        Level("IB low  (09:30-10:30)", float(ib["low"].min()), "low", "DJI 1m 09:30-10:29"),
        Level("HOD (today)", float(b["high"].max()), "high", f"DJI 1m {b['high'].idxmax():%H:%M}"),
        Level("LOD (today)", float(b["low"].min()), "low", f"DJI 1m {b['low'].idxmin():%H:%M}"),
        Level("RTH close (official print)", float(close_px), "high", "Yahoo 16:00 close snapshot"),
        Level("09-24 swing low (daily)", float(sep24["low"]), "low", "DJI_1d_1mo.json bar 17"),
        Level("09-16 swing low (daily)", float(sep16["low"]), "low", "DJI_1d_1mo.json bar 11"),
    ]


def ym_levels(ym5, ymd) -> list[Level]:
    b = ym5.bars
    on = b.loc["2026-09-28 18:00":"2026-09-29 09:25"]
    rth = b.loc["2026-09-29 09:30":]
    d = ymd.bars
    return [
        Level("ON high (Globex 18:00-09:30)", float(on["high"].max()), "high",
              f"YM 5m {on['high'].idxmax():%a %H:%M}"),
        Level("ON low  (Globex 18:00-09:30)", float(on["low"].min()), "low",
              f"YM 5m {on['low'].idxmin():%a %H:%M}"),
        Level("Prev close - upside test", float(ym5.meta["chartPreviousClose"]), "high",
              "YM meta chartPreviousClose"),
        Level("Prev close - downside acceptance", float(ym5.meta["chartPreviousClose"]), "low",
              "YM meta chartPreviousClose"),
        Level("09-24 low (ET calendar day)", float(day_row(d, "2026-09-24")["low"]), "low",
              "YM_1d_1mo.json bar 17"),
        Level("09-28 low (ET calendar day)", float(day_row(d, "2026-09-28")["low"]), "low",
              "YM_1d_1mo.json bar 19"),
        Level("RTH low (today)", float(rth["low"].min()), "low",
              f"YM 5m {rth['low'].idxmin():%H:%M}"),
        Level("RTH high (today)", float(rth["high"].max()), "high",
              f"YM 5m {rth['high'].idxmax():%H:%M}"),
    ]


def md_table(df: pd.DataFrame) -> str:
    if df is None or len(df) == 0:
        return "_(no events matched the stated criteria)_\n"
    return df.to_markdown(index=False) + "\n"


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    dji1, dji5, dji30, djid, ym5, ymd = build()
    b1, bym = dji1.bars, ym5.bars
    b5 = resample_5m(b1)
    SRC5 = "^DJI 5m (resampled from verified 1m)"
    SRC1 = "^DJI 1m (DJI_1m_s1..s7)"

    now_bar = b1.index[-1]
    rth_end = pd.Timestamp("2026-09-29 16:00", tz="America/New_York")
    mins_left = max(0, int((rth_end - now_bar).total_seconds() // 60) - 1)
    official_close = float(dji1.snapshots["close"].iloc[-1]) if len(dji1.snapshots) else float(b1["close"].iloc[-1])
    session_complete = mins_left <= 0

    # ---------------- detectors ----------------
    sw5 = swings(b5, P["swing_k_5m"])
    sw1 = swings(b1, P["swing_k_1m"])
    disp5 = detect_displacement(b5, "5m", SRC5, P["disp_atr_n_5m"],
                                P["disp_mult_5m"], P["disp_maxbars_5m"], P["disp_er"])
    disp1 = detect_displacement(b1, "1m", SRC1, P["disp_atr_n_1m"],
                                P["disp_mult_1m"], P["disp_maxbars_1m"], P["disp_er"])
    fvg5 = detect_fvg(b5, "5m", SRC5, P["fvg_min_5m"])
    fvg1 = detect_fvg(b1, "1m", SRC1, P["fvg_min_1m"])
    cons5 = detect_consolidation(b5, "5m", SRC5, P["cons_window"],
                                 P["cons_er_max"], P["cons_range_atr"])
    shifts5 = structure_shifts(b5, "5m", SRC5, P["swing_k_5m"])

    dlv = dji_levels(dji1, dji5, djid, official_close)
    ylv = ym_levels(ym5, ymd)

    ym_rth_bars = bym.loc["2026-09-29 09:30":]
    dji_test = [lv for lv in dlv if not lv.name.startswith(("HOD", "LOD", "RTH close"))]
    ym_test = [lv for lv in ylv if not lv.name.startswith(("RTH low", "RTH high"))]

    dji_inter, ym_inter, reclaims, ym_reclaims = [], [], [], []
    for lv in dji_test:
        dji_inter += classify_level_interaction(b5, lv, "5m", SRC5,
                                                confirm_bars=P["confirm_bars"])
        reclaims += detect_reclaim(b5, lv, "5m", SRC5,
                                   P["reclaim_away"], P["reclaim_hold"])
    for lv in ym_test:
        ym_inter += classify_level_interaction(ym_rth_bars, lv, "5m", "YM_5m_rth.json",
                                               tol=1.0, confirm_bars=P["confirm_bars"])
        ym_reclaims += detect_reclaim(ym_rth_bars, lv, "5m", "YM_5m_rth.json",
                                      P["reclaim_away"], P["reclaim_hold"])

    dji_inter_1m = []
    for lv in dji_test:
        dji_inter_1m += classify_level_interaction(b1, lv, "1m", SRC1,
                                                   confirm_bars=P["confirm_bars"])

    dji_untouched = untouched_levels(b5, dji_test)
    ym_untouched = untouched_levels(ym_rth_bars, ym_test, tol=1.0)

    ym_disp = detect_displacement(bym.loc["2026-09-29 09:30":], "5m", "YM_5m_rth.json",
                                  14, 2.0, 5, P["disp_er"])
    ym_fvg = detect_fvg(bym.loc["2026-09-29 09:30":], "5m", "YM_5m_rth.json", 5.0)

    # ---------------- persist ----------------
    frames = {
        "events_dji_displacement_5m": events_to_frame(disp5),
        "events_dji_displacement_1m": events_to_frame(disp1),
        "events_dji_fvg_5m": events_to_frame(fvg5),
        "events_dji_fvg_1m": events_to_frame(fvg1),
        "events_dji_consolidation_5m": events_to_frame(cons5),
        "events_dji_structure_shift_5m": events_to_frame(shifts5),
        "events_dji_level_interactions_5m": events_to_frame(dji_inter),
        "events_dji_level_interactions_1m": events_to_frame(dji_inter_1m),
        "events_dji_reclaims_5m": events_to_frame(reclaims),
        "events_ym_level_interactions_5m": events_to_frame(ym_inter),
        "events_ym_reclaims_5m": events_to_frame(ym_reclaims),
        "events_ym_displacement_5m": events_to_frame(ym_disp),
        "events_ym_fvg_5m": events_to_frame(ym_fvg),
    }
    for name, f in frames.items():
        if len(f):
            f.to_csv(os.path.join(OUT, f"{name}.csv"), index=False)
    bar_table(b5).to_csv(os.path.join(OUT, "bars_dji_5m.csv"))
    bar_table(b1).to_csv(os.path.join(OUT, "bars_dji_1m.csv"))
    bar_table(bym).to_csv(os.path.join(OUT, "bars_ym_5m.csv"))

    # ---------------- derived facts ----------------
    lod_ts, hod_ts = b1["low"].idxmin(), b1["high"].idxmax()
    lod, hod = float(b1["low"].min()), float(b1["high"].max())
    sep24_cash_low = float(day_row(djid.bars, "2026-09-24")["low"])
    ym_rth = bym.loc["2026-09-29 09:30":]
    ym_lod, ym_lod_ts = float(ym_rth["low"].min()), ym_rth["low"].idxmin()
    ym_sep24 = float(day_row(ymd.bars, "2026-09-24")["low"])
    on_low = float(bym.loc["2026-09-28 18:00":"2026-09-29 09:25"]["low"].min())
    on_low_ts = bym.loc["2026-09-28 18:00":"2026-09-29 09:25"]["low"].idxmin()
    on_high = float(bym.loc["2026-09-28 18:00":"2026-09-29 09:25"]["high"].max())
    on_high_ts = bym.loc["2026-09-28 18:00":"2026-09-29 09:25"]["high"].idxmax()
    _bt = bym.index[-1]
    basis = float(bym["close"].iloc[-1] - b1["close"].asof(_bt))

    ib = b5.iloc[0:12]
    ib_hi, ib_lo = float(ib["high"].max()), float(ib["low"].min())

    day_by_day = bym.groupby(bym.index.date).agg(h=("high", "max"), l=("low", "min"))

    # ---------------- report ----------------
    L: list[str] = []
    A = L.append
    A("# LANE 7 — US30 / Dow: Market Structure & Liquidity")
    A("")
    status = ("the **regular session is COMPLETE** (09:30–16:00 ET); the 16:00 closing auction print is "
              f"captured separately at **{official_close:,.2f}**."
              if session_complete else
              f"**{mins_left} minutes of RTH remain — session INCOMPLETE and all day-level statements are provisional**.")
    A(f"**Generated:** 2026-09-29. ^DJI bars run **{b1.index[0]:%H:%M}–{b1.index[-1]:%H:%M} ET** ({len(b1)} one-minute bars) — {status}")
    A("")
    A(f"YM=F futures bars run Mon 18:00 → Tue {bym.index[-1]:%H:%M} ET; the Globex session continues past the "
      f"cash close, so the futures picture below is current only to {bym.index[-1]:%H:%M}.")
    A("")
    A("---")
    A("")
    A("## 0. Instrument, data provenance, and what the data can/cannot support")
    A("")
    A("### 0.1 Which \"US30\"?")
    A("")
    A("\"US30\" is a broker CFD label, not an exchange instrument. There is no canonical US30 tape. "
      "This analysis is therefore run on the two instruments that a US30 quote is derived from, "
      "**kept strictly separate**:")
    A("")
    A("| Role | Symbol | What it is | Last | Source |")
    A("|---|---|---|---|---|")
    A(f"| Cash index | `^DJI` | Dow Jones Industrial Average, price-weighted computed index | {official_close:,.2f} (official close) | Yahoo `/v8/finance/chart` |")
    A(f"| Futures | `YM=F` | {ym5.meta.get('shortName')} (CBOT), 23h Globex | {float(bym['close'].iloc[-1]):,.0f} (last bar {bym.index[-1]:%H:%M}) | Yahoo `/v8/finance/chart` |")
    A("")
    A(f"**Observed basis near the cash close: YM − DJI = {basis:+.0f} points.** Futures levels and cash levels are "
      f"**not interchangeable** and are never mixed below. A broker US30 feed will sit near one of these two, "
      f"offset by that broker's own spread/financing — translate levels, do not copy them.")
    A("")
    A("### 0.2 Capture and integrity")
    A("")
    A("The analysis host has an allowlisted network (no market-data egress), so payloads were captured "
      "out-of-band and stored verbatim in `data/raw/`. Because hand-capture can corrupt digits, the capture "
      "is proved before any level is quoted, via `engine/lane7_verify.py`:")
    A("")
    A(f"> The {len(b1)} one-minute bars (8 separate windowed requests) are resampled to 5 minutes and compared")
    A("> against a **separately downloaded** 5-minute payload. All 74 overlapping bars match on")
    A("> open/high/low/close with `max_abs_diff = 0.0000000000`. Session high/low/open also reconcile to")
    A("> Yahoo's independent `regularMarketDayHigh` / `regularMarketDayLow` / open meta fields, and YM's")
    A("> day high/low reconcile to its own meta.")
    A("")
    A("Two independent downloads agreeing to the tick is the evidence that the numbers below are real. "
      "Re-run `python -m engine.lane7_verify` to reproduce.")
    A("")
    A("| Payload | Symbol | TF | Bars | Coverage (ET) |")
    A("|---|---|---|---|---|")
    A(f"| `DJI_1m_s1..s7 + patch` | ^DJI | 1m | {len(b1)} | {b1.index[0]:%H:%M}–{b1.index[-1]:%H:%M} (full RTH) |")
    A(f"| `DJI_5m_1d.json` (verification counterpart) | ^DJI | 5m | {len(dji5.bars)} | {dji5.bars.index[0]:%H:%M}–{dji5.bars.index[-1]:%H:%M} |")
    A(f"| 5m used for analysis = resample of the 1m above | ^DJI | 5m | {len(b5)} | {b5.index[0]:%H:%M}–{b5.index[-1]:%H:%M} |")
    A(f"| `DJI_30m_5d.json` | ^DJI | 30m | {len(dji30.bars)} | 09-23 → 09-29 |")
    A(f"| `DJI_1d_1mo.json` | ^DJI | 1d | {len(djid.bars)} | 08-31 → 09-29 |")
    A(f"| `YM_5m_on_a/on_b/rth` | YM=F | 5m | {len(bym)} | Mon 18:00 → Tue {bym.index[-1]:%H:%M} |")
    A(f"| `YM_1d_1mo.json` | YM=F | 1d | {len(ymd.bars)} | 08-31 → 09-29 |")
    A("")
    A("### 0.3 Hard limits — what these bars CANNOT establish")
    A("")
    A("1. **No order-book, no tape, no bid/ask, no delta.** Only OHLCV. Every \"liquidity\" statement below "
      "is an inference from *price geometry* (a level was exceeded and price returned), never from observed "
      "resting orders. Absorption, spoofing, iceberg fills, and delta divergence are **not testable here**.")
    A("2. **`^DJI` has no liquidity of its own.** It is a computed average of 30 constituent last-trade prices. "
      "There are no stops resting \"at\" 51,129 on the index. Cash-index wicks are an *artifact of the averaging*, "
      "not a stop run. **Sweep claims are therefore made on `YM=F`, where the book actually is, and the cash "
      "index is used only for corroboration.**")
    A("3. **Session scope.** The cash session is closed, so ^DJI statements are final for 2026-09-29. "
      f"The futures picture is NOT final — YM Globex runs to 17:00 ET and my last YM bar is {bym.index[-1]:%H:%M}, "
      "so any futures level can still be revisited tonight."
      if session_complete else
      f"3. **The session is not finished.** {mins_left} minutes of RTH remain plus the close auction.")
    A("4. **Volume caveats.** `^DJI` volume is summed constituent share volume — usable for *relative* activity only. "
      "Yahoo's `YM=F` volume is known to be partial (it reports "
      f"{int(ym5.meta.get('regularMarketVolume', 0)):,} contracts for a full Globex day, which is implausibly low "
      "for the front Dow contract). **No conclusion below depends on YM volume.**")
    zv = [f"{t:%H:%M}" for t in b1.index[b1["volume"].fillna(0) == 0]]
    A(f"5. **1-minute volume has a known source artifact.** Yahoo zeroes the first bar of every "
      f"`period1/period2` window; {len(zv)} bars ({', '.join(zv)}) carry `volume=0`. "
      "*Prices on those bars are verified correct* by the redundancy check. All volume statements use the "
      "`range=1d` 5-minute payload instead.")
    A(f"6. **Closing-auction snapshot excluded from the bar series.** Yahoo emits the official close as a "
      f"grid-aligned 16:00 row with `open==high==low==close=={official_close:,.2f}` and `volume=0`. That is a "
      "settlement print, not a traded minute, and leaving it in manufactures a phantom 3-bar FVG. It is removed "
      "from all detectors (rule: flat OHLC **and** zero volume) and reported separately as the close.")
    A("7. **Futures daily bars are ET calendar-day buckets, not 18:00–17:00 exchange sessions.** Verified by "
      "reconciliation: my 5-minute YM bars grouped by ET date give "
      f"{day_by_day.loc[pd.Timestamp('2026-09-29').date(), 'h']:.0f}/"
      f"{day_by_day.loc[pd.Timestamp('2026-09-29').date(), 'l']:.0f} for 09-29, exactly matching the daily "
      "payload. Prior-day futures levels below are therefore labelled \"ET calendar day\".")
    A("")
    A("### 0.4 Detector definitions and parameters")
    A("")
    A("All events come from `engine/lane7_structure.py`. Definitions are mechanical:")
    A("")
    A("| Event | Definition |")
    A("|---|---|")
    A("| Swing (fractal) | high beats all *k* bars each side (strict). `*` = edge pivot, provisional. |")
    A("| FVG / imbalance | 3-bar gap: bullish `low[i] > high[i-2]`; bearish `high[i] < low[i-2]`. Fill measured by later bars re-entering the band. |")
    A("| Displacement | run of ≤ *maxbars* with \\|net\\| ≥ *mult* × ATR(n) measured **before** the run, directional efficiency ≥ 0.70, **and** containing a same-direction FVG. |")
    A("| SWEEP | wick pierces level, **same bar closes back inside**, stays inside for *confirm* bars. |")
    A("| FAILED BREAK | ≥1 bar **closes** beyond level, then closes back inside within *confirm* bars. |")
    A("| BREAK+HOLD | closes beyond and is still beyond after *confirm* bars. |")
    A("| RECLAIM | ≥ *away* closes on the wrong side, then a close back that holds *hold* bars. |")
    A("| Consolidation | *window*-bar stretch with Kaufman ER ≤ *er_max* **and** range ≤ *range_atr* × ATR. |")
    A("| BOS / CHoCH | close beyond the last confirmed swing (pivot only usable *k* bars after it prints — no look-ahead). |")
    A("")
    A("Parameters used: `" + ", ".join(f"{k}={v}" for k, v in P.items()) + "`")
    A("")
    A("---")
    A("")
    A("# PART A — VERIFIED OBSERVATIONS")
    A("")
    A("Everything in Part A is a direct arithmetic consequence of the captured bars. "
      "Each row names the bar, the level, the timeframe and the payload.")
    A("")
    A("## A1. Reference levels (with provenance)")
    A("")
    A("**^DJI cash**")
    A("")
    A("| Level | Price | Source |")
    A("|---|---:|---|")
    for lv in dlv:
        A(f"| {lv.name} | {lv.price:,.2f} | {lv.origin} |")
    A("")
    A("**YM=F futures (Dec-26)**")
    A("")
    A("| Level | Price | Source |")
    A("|---|---:|---|")
    for lv in ylv:
        A(f"| {lv.name} | {lv.price:,.0f} | {lv.origin} |")
    A("")
    A("## A2. Session skeleton (^DJI, 1m + 5m)")
    A("")
    A(f"- **RTH open** {float(b5['open'].iloc[0]):,.2f} at 09:30 — opened **below** PDC {float(djid.bars.iloc[-2]['close']):,.2f} "
      f"and **above** PDL {float(djid.bars.iloc[-2]['low']):,.2f}.")
    A(f"- **HOD {hod:,.2f} at {hod_ts:%H:%M}** (1m bar, `DJI_1m_s1.json`; confirmed on 5m bar 2 09:40 high {float(b5['high'].iloc[2]):,.2f}).")
    A(f"- **LOD {lod:,.2f} at {lod_ts:%H:%M}** (1m bar; confirmed on 5m bar 30 12:00 low {float(b5['low'].iloc[30]):,.2f}).")
    A(f"- **Session range: {hod - lod:,.2f} points** ({(hod-lod)/lod*100:.2f}%). Time from HOD to LOD: "
      f"{int((lod_ts-hod_ts).total_seconds()//60)} minutes.")
    A(f"- **Initial Balance (09:30–10:30, 5m bars 0–11): {ib_lo:,.2f} – {ib_hi:,.2f}** (height {ib_hi-ib_lo:,.2f}). "
      f"The IB low was broken at 10:30+ and the session low printed {lod:,.2f}, i.e. an **IB-low breakout day**; "
      f"the IB high was never revisited after {hod_ts:%H:%M}.")
    A(f"- **Official close {official_close:,.2f}** (16:00 auction print, `regularMarketPrice`), "
      f"{official_close - float(djid.bars.iloc[-2]['close']):+,.2f} vs PDC — "
      f"closed **back above** the IB low ({official_close - ib_lo:+,.2f}) but "
      f"{ib_hi - official_close:,.2f} pts below the IB high, and "
      f"{official_close - lod:+,.2f} pts off the session low.")
    A(f"- **Close location in range: {(official_close - lod) / (hod - lod) * 100:.1f}%** of the "
      f"{hod - lod:,.2f}-pt session range — upper-middle, i.e. the day closed nearer its high than its low "
      f"despite being a net down day.")
    A("")
    A("## A3. Confirmed swing points")
    A("")
    A(f"**^DJI 5m, k={P['swing_k_5m']}** ({SRC5}):")
    A("")
    A("| # | Type | Bar | Time | Price |")
    A("|---|---|---:|---|---:|")
    for n, s in enumerate(sw5):
        A(f"| {n} | {'Swing High' if s.kind=='high' else 'Swing Low'}{' (edge, provisional)' if s.edge else ''} "
          f"| {s.bar} | {s.ts:%H:%M} | {s.price:,.2f} |")
    A("")
    A(f"^DJI 1m k={P['swing_k_1m']} produced {len(sw1)} pivots (see `bars_dji_1m.csv`).")
    A("")
    A(f"*Edge pivots* are the first and last extremes: they lack {P['swing_k_5m']} confirming bars on one side, so "
      "they are reported but never used to trigger a BOS/CHoCH in A9. With the session closed, the trailing edge "
      "pivots can no longer be confirmed on cash at all — nothing trades until 09:30 tomorrow.")
    A("")
    A("## A4. Displacement legs")
    A("")
    A("### ^DJI 5m")
    A("")
    A(md_table(events_to_frame(disp5)))
    A("Reading: the **only** qualifying down-leg of the day is **11:00→11:20, −125.08 pts at 2.23× the "
      "pre-leg ATR with efficiency 1.00** (five consecutive lower closes, zero retracement). Everything "
      "before it was a *grind*, not displacement — the largest 3-bar down-run in the 09:30–11:00 window "
      "reached only ~1.8× ATR, below the 2.0 threshold, because morning ATR was elevated (~56–66 pts). "
      "Four qualifying up-legs then cluster between 13:20 and 14:40.")
    A("")
    A("### ^DJI 1m")
    A("")
    A(md_table(events_to_frame(disp1)))
    A("")
    A("### YM=F 5m (RTH only)")
    A("")
    A(md_table(events_to_frame(ym_disp)))
    A("")
    A("## A5. Imbalance / Fair-Value Gaps — only where bars actually gap")
    A("")
    A(f"Strict 3-bar gaps, ^DJI 5m, ≥ {P['fvg_min_5m']:.0f} pts:")
    A("")
    A(md_table(events_to_frame(fvg5)))
    A("**Unfilled or partially filled at the close (5m):**")
    live5 = [e for e in fvg5 if e.detail["status"] != "FILLED"]
    for e in live5:
        A(f"- `{e.kind}` **{e.detail['gap_low']:,.2f} – {e.detail['gap_high']:,.2f}** "
          f"({e.detail['size_pts']:.2f} pts, created by the {e.detail['displacement_bar']} bar, "
          f"{e.detail['pct_filled']}% filled).")
    A("")
    A(f"^DJI 1m, ≥ {P['fvg_min_1m']:.0f} pts — {len(fvg1)} gaps; unfilled/partial only:")
    A("")
    A(md_table(events_to_frame([e for e in fvg1 if e.detail["status"] != "FILLED"])))
    A("")
    A("YM=F 5m RTH, ≥ 5 pts — unfilled/partial only:")
    A("")
    A(md_table(events_to_frame([e for e in ym_fvg if e.detail["status"] != "FILLED"])))
    A("")
    A("## A6. Consolidations / balance areas (^DJI 5m)")
    A("")
    A(md_table(events_to_frame(cons5)))
    A("")
    A("## A7. Level interactions — sweeps, failed breaks, breaks that held")
    A("")
    A("### ^DJI cash, 5m")
    A("")
    A(md_table(events_to_frame(dji_inter)))
    A("")
    A("### YM=F futures, 5m, RTH")
    A("")
    A(md_table(events_to_frame(ym_inter)))
    A("")
    A("## A8. The one genuine liquidity event of the session")
    A("")
    A("This is the single observation where cash and futures **disagree**, and it is the most load-bearing "
      "fact in this report.")
    A("")
    A("| | Futures `YM=F` | Cash `^DJI` |")
    A("|---|---:|---:|")
    A(f"| 09-24 low (prior swing low) | {ym_sep24:,.0f} | {sep24_cash_low:,.2f} |")
    A(f"| Today's low | {ym_lod:,.0f} @ {ym_lod_ts:%H:%M} | {lod:,.2f} @ {lod_ts:%H:%M} |")
    A(f"| Difference | **{ym_lod - ym_sep24:+,.0f} pts (TAKEN)** | **{lod - sep24_cash_low:+,.2f} pts (NOT taken)** |")
    A("")
    A(f"- **Futures took the sell-side.** YM traded to {ym_lod:,.0f} at {ym_lod_ts:%H:%M}, i.e. "
      f"**{ym_sep24 - ym_lod:.0f} points through** the 09-24 calendar-day low of {ym_sep24:,.0f}, then closed "
      f"the session back above it and sat {float(bym['close'].iloc[-1]) - ym_sep24:+,.0f} pts above it at my "
      f"last futures bar ({bym.index[-1]:%H:%M}). "
      f"That is a completed penetrate-and-reverse at a multi-day reference low.")
    A(f"- **Cash did not.** ^DJI bottomed at {lod:,.2f}, which is **{lod - sep24_cash_low:.2f} points ABOVE** the "
      f"09-24 cash low of {sep24_cash_low:,.2f} — a gap of {(lod-sep24_cash_low)/lod*1e4:.1f} basis points. "
      f"The cash index printed an *equal-lows* structure, not a sweep.")
    A(f"- **Timing corroborates.** Both instruments bottomed in the same 5-minute bucket "
      f"({ym_lod_ts:%H:%M} futures / {lod_ts:%H:%M} cash), so this is one event, not two.")
    A("")
    A(f"Also on futures: the Globex overnight low **{on_low:,.0f} ({on_low_ts:%a %H:%M})** was broken decisively "
      f"during RTH (down to {ym_lod:,.0f}, {on_low - ym_lod:.0f} pts through) — a break-and-hold, *not* a sweep — "
      f"and was then **reclaimed**: YM last {float(bym['close'].iloc[-1]):,.0f} is "
      f"{float(bym['close'].iloc[-1]) - on_low:+,.0f} pts back above it.")
    A("")
    A("## A8b. Timeframe sensitivity — the same contact, classified two ways")
    A("")
    A("Sweep-vs-failed-break is **resolution dependent**, and pretending otherwise is how these reports go "
      "wrong. The clearest case today is the prior-day close:")
    A("")
    A("| Timeframe | Classification | Why |")
    A("|---|---|---|")
    A("| ^DJI 5m | `SWEEP_high` | no 5-minute bar *closed* above 51,481.51 |")
    A("| ^DJI 1m | `FAILED_BREAK_high` | two 1-minute bars closed above it — 09:41 @ 51,490.14 and 09:42 @ 51,494.47 — before 09:43 closed back at 51,447.55 |")
    A("")
    A("Both are correct for their timeframe. Stated plainly: **buy-side above the prior close was taken and "
      "rejected inside three minutes**; on a 5-minute chart that leaves only a wick. Full 1-minute episode table: "
      "`events_dji_level_interactions_1m.csv`.")
    A("")
    A(md_table(events_to_frame(dji_inter_1m)))
    A("")
    A("## A9. Market-structure shifts (^DJI 5m, no look-ahead)")
    A("")
    A(md_table(events_to_frame(shifts5)))
    A("")
    A("## A10. Reclaims / regains")
    A("")
    A("**^DJI cash, 5m** — a reclaim requires >= "
      f"{P['reclaim_away']} closes on the wrong side followed by a close back that holds "
      f"{P['reclaim_hold']} bars:")
    A("")
    A(md_table(events_to_frame(reclaims)))
    A("")
    A("**YM=F futures, 5m RTH:**")
    A("")
    A(md_table(events_to_frame(ym_reclaims)))
    A("")
    # ---- A10b. closing hour -------------------------------------------------
    lh = b1.loc["2026-09-29 15:00":]
    lh_hi, lh_lo = float(lh["high"].max()), float(lh["low"].min())
    last5 = b1.tail(5)
    A("## A10b. The closing hour and the 16:00 auction")
    A("")
    A(f"The final 60 minutes (15:00–15:59, {len(lh)} 1m bars) traded **{lh_lo:,.2f} – {lh_hi:,.2f}**, a range of "
      f"**{lh_hi - lh_lo:,.2f} pts = {(lh_hi - lh_lo) / (hod - lod) * 100:.0f}% of the day's {hod - lod:,.2f}-pt range**. "
      f"High {lh_hi:,.2f} at {lh['high'].idxmax():%H:%M}, low {lh_lo:,.2f} at {lh['low'].idxmin():%H:%M}. "
      "There was **no closing drive** — the day ended inside the balance it built after 14:40.")
    A("")
    A("Volume ramp into the bell (1m, ^DJI summed constituent volume):")
    A("")
    A("| bar | close | volume |")
    A("|---|---:|---:|")
    for t, r in b1.loc["2026-09-29 15:53":].iterrows():
        A(f"| {t:%H:%M} | {r['close']:,.2f} | {int(r['volume']):,} |")
    A("")
    A(f"- The 15:59 bar alone traded **{int(last5['volume'].iloc[-1]):,}** — "
      f"**{last5['volume'].iloc[-1] / float(lh['volume'].iloc[0]):.1f}×** the 15:00 bar — and had the widest range "
      f"of the closing hour ({float(last5['high'].iloc[-1]) - float(last5['low'].iloc[-1]):,.2f} pts: "
      f"{float(last5['low'].iloc[-1]):,.2f}–{float(last5['high'].iloc[-1]):,.2f}).")
    A(f"- **The auction printed {official_close:,.2f}, which is {official_close - float(b1['close'].iloc[-1]):+,.2f} pts "
      f"versus the 15:59 close of {float(b1['close'].iloc[-1]):,.2f}** — a small sell imbalance on the cross. "
      f"The print sits *inside* the 15:59 bar's range, so it is consistent with the tape rather than a gap.")
    _close_meta = load_chart("DJI_1m_s7_close.json").meta
    _vfin = int(_close_meta.get("regularMarketVolume", 0))
    _vbars = int(b1["volume"].sum())
    A(f"- The last seven 1m bars (15:53–15:59) carry **{int(b1.loc['2026-09-29 15:53':, 'volume'].sum()):,}** of the "
      f"**{_vbars:,}** summed across all {len(b1)} bars — "
      f"**{b1.loc['2026-09-29 15:53':, 'volume'].sum() / _vbars * 100:.1f}% of the session's bar volume in the last "
      "7 minutes.** Front-loading into the bell is normal auction mechanics and is **not** evidence of directional "
      "intent; it is reported here only so the wide 15:59 range is not mistaken for a displacement leg.")
    A(f"- Yahoo's post-close `regularMarketVolume` is **{_vfin:,}** (meta timestamp 16:02:48), materially above the "
      f"{_vbars:,} summed from bars. The difference is the closing cross, which settles after 16:00 and is never "
      "attributed to an intraday bar. **Do not reconcile these two numbers** — they measure different things.")
    A("")
    A("## A11. Levels never traded through today (pools still resting)")
    A("")
    A("**^DJI cash** (vs 09:30-" + f"{now_bar:%H:%M} bars):")
    A("")
    if dji_untouched:
        A("| Level | Price | Side | Source |")
        A("|---|---:|---|---|")
        for lv in dji_untouched:
            A(f"| {lv.name} | {lv.price:,.2f} | {lv.side} | {lv.origin} |")
    else:
        A("_(every cash reference level was traded through at least once)_")
    A("")
    A("**YM=F futures** (vs RTH bars):")
    A("")
    if ym_untouched:
        A("| Level | Price | Side | Source |")
        A("|---|---:|---|---|")
        for lv in ym_untouched:
            A(f"| {lv.name} | {lv.price:,.0f} | {lv.side} | {lv.origin} |")
    else:
        A("_(every futures reference level was traded through at least once)_")
    A("")
    A("---")
    A("")
    A("# PART B — INFERRED STRUCTURE")
    A("")
    A("Part B is interpretation. It is consistent with Part A but is **not** proved by it.")
    A("")
    A("## B1. The day in one sentence")
    A("")
    A(f"A failed opening push above the prior close, a single genuine down-displacement at 11:00–11:20 that "
      f"delivered price into the 09-24 low region, a two-hour base that *stopped {lod - sep24_cash_low:.2f} points "
      f"short of the obvious cash liquidity*, and an afternoon repair driven by four stacked up-displacements — "
      f"closing at {official_close:,.2f}, {(official_close - lod) / (hod - lod) * 100:.0f}% of the way up "
      f"the session range, back above the initial-balance low but still below the prior day's low, "
      f"with the sell-side pool under {sep24_cash_low:,.2f} still intact.")
    A("")
    A("## B2. Phase map (inferred boundaries)")
    A("")
    A("| Phase | Window | Character | Evidence from Part A |")
    A("|---|---|---|---|")
    A(f"| 1. Open / failed extension | 09:30–09:42 | Push to {hod:,.2f}, above PDC, immediately rejected | A2, unfilled bearish 1m FVG 51,443.57–51,480.95 from 09:43 |")
    A("| 2. Grind lower | 09:42–11:00 | Trend, but *below* displacement threshold | A4 — no qualifying 5m down-leg |")
    A("| 3. Displacement down | 11:00–11:20 | −125.08 pts, ER 1.00, 2.23× ATR | A4 |")
    A(f"| 4. Base / accumulation | 12:10–13:25 | ER 0.01–0.17, 56.31-pt box {float(cons5[0].detail['lo']):,.2f}–{float(cons5[0].detail['hi']):,.2f} | A6 |")
    A("| 5. Repair | 13:20–14:40 | Four up-displacements, BOS_up ×2 | A4, A9 |")
    A(f"| 6. Balance at highs | 14:40–{now_bar:%H:%M} | ER 0.07, 61.12-pt box {float(cons5[-1].detail['lo']):,.2f}–{float(cons5[-1].detail['hi']):,.2f} | A6 |")
    A("")
    A("## B3. Inferred liquidity map")
    A("")
    A("Ranked by how well the bars support each pool.")
    A("")
    A("| Pool | Cash level | Futures level | Strength of evidence |")
    A("|---|---:|---:|---|")
    A(f"| Untaken sell-side under the double bottom | **< {sep24_cash_low:,.2f}** | — (already taken) | **Strong on cash.** Two session lows {(lod-sep24_cash_low):.2f} pts apart, 3 sessions apart, neither breached. |")
    A(f"| Buy-side over today's high | **> {hod:,.2f}** | > {float(ym_rth['high'].max()):,.0f} | **Strong.** Single rejected extreme, never revisited for the remaining {int((now_bar-hod_ts).total_seconds()//60)} min of the session. |")
    A(f"| Buy-side over PDC | **> {float(djid.bars.iloc[-2]['close']):,.2f}** | — | Moderate. Rejected once at the open. |")
    A(f"| Buy-side over ON high | — | **> {on_high:,.0f}** ({on_high_ts:%H:%M}) | Moderate. Globex extreme, not revisited in RTH. |")
    A("")
    A("**Directional read (low confidence):** futures already ran the sell-side and reversed, cash left its pool "
      "untouched. That asymmetry usually resolves one of two ways — either the futures sweep was the low and cash "
      "simply never needed to print the extra 5 points, or the cash pool below "
      f"{sep24_cash_low:,.2f} remains a magnet into a later session. **The bars on hand cannot distinguish these.**")
    A("")
    A("## B4. Structural invalidation levels")
    A("")
    A("These are the prices at which the Part-B reading is **wrong**, not stop-loss advice.")
    A("")
    A("| The claim | Invalidated by | Level |")
    A("|---|---|---:|")
    A(f"| \"Afternoon recovery is intact\" | 5m **close** below the 14:55 swing low | **{[s for s in sw5 if s.ts.strftime('%H:%M')=='14:55'][0].price:,.2f}** (^DJI) |")
    A(f"| \"The 12:00 low is the session low\" | any trade below it | **{lod:,.2f}** (^DJI) / **{ym_lod:,.0f}** (YM) |")
    A(f"| \"The double bottom holds\" | trade below the 09-24 low | **{sep24_cash_low:,.2f}** (^DJI) |")
    A(f"| \"Balance at highs, not breakout\" | 5m close above the 15:30 high | **{float(b5['high'].max()):,.2f}** (^DJI) |")
    A(f"| \"Day stays below prior close\" | 5m close above PDC | **{float(djid.bars.iloc[-2]['close']):,.2f}** (^DJI) |")
    A(f"| \"ON low reclaim is real\" (futures) | YM close back below it | **{on_low:,.0f}** (YM) |")
    A("")
    A("## B5. Structures I looked for and did NOT find")
    A("")
    A("Stated explicitly so absence is not mistaken for oversight:")
    A("")
    A("- **No sweep of PDH** — 51,780.50 was never approached; today's high fell "
      f"{float(djid.bars.iloc[-2]['high']) - hod:,.2f} pts short.")
    A("- **No qualifying morning displacement leg** on 5m despite a ~376-pt decline: the move was delivered as a "
      "grind. Calling 09:42–11:00 \"displacement\" would not survive an ATR-relative test.")
    A("- **No large unfilled 5m FVG below price** — the morning bearish gaps (11:05, 11:10, 11:15, 11:20, 11:55) "
      "are **100% filled**, so they are spent and carry no forward inference.")
    A("- **No verifiable absorption / delta divergence** anywhere — requires tape or footprint data that does not exist in this dataset.")
    A("")
    A("---")
    A("")
    A("# PART C — DECLARED INSUFFICIENCIES")
    A("")
    A("| Question | Status | Why |")
    A("|---|---|---|")
    A("| Where were resting stops actually clustered? | **Cannot answer** | No book/tape. Price geometry only. |")
    A("| Was the 12:00 low absorbed or just exhausted? | **Cannot answer** | Needs footprint/delta. |")
    A("| Did the CFD (broker \"US30\") print the same wicks? | **Cannot answer** | No broker feed; CFD wicks differ from both cash and futures. |")
    A("| What is the true YM traded volume? | **Cannot answer** | Yahoo futures volume is partial (see 0.3 #4). |")
    A("| What is the session close / final structure? | **Answered** | "
      f"Cash closed at {official_close:,.2f}; all 390 RTH minutes captured. |"
      if session_complete else
      f"| What is the session close / final structure? | **Not yet knowable** | {mins_left} min of RTH remain. |")
    A("| Does the futures picture hold overnight? | **Cannot answer** | "
      f"YM Globex trades until 17:00 ET and reopens 18:00; captured only to {bym.index[-1]:%H:%M}. |")
    A("| Overnight ^DJI structure | **Does not exist** | Cash index is only computed 09:30–16:00. Overnight structure is a futures-only concept — that is why Globex levels are quoted on YM. |")
    A("| Multi-day 1m/5m cash structure | **Not captured** | Only today at 1m/5m; 09-23→09-29 available at 30m, 08-31→09-29 at 1d. |")
    A("")
    A("---")
    A("")
    A("## Reproduce")
    A("")
    A("```bash")
    A("python -m engine.lane7_verify                      # integrity gate")
    A("python -m experiments.lane7_us30_structure         # this report")
    A("```")
    A("")
    A("Raw payloads: `data/raw/*.json` (verbatim Yahoo `/v8/finance/chart` responses). "
      "Derived bars and every event table: `results/lane7_us30_structure/*.csv`.")

    path = os.path.join(OUT, "LANE7_MARKET_STRUCTURE.md")
    with open(path, "w") as fh:
        fh.write("\n".join(L))
    print(f"wrote {path}  ({len(L)} lines)")
    for name, f in frames.items():
        if len(f):
            print(f"  {name}.csv  ({len(f)} rows)")


if __name__ == "__main__":
    main()
