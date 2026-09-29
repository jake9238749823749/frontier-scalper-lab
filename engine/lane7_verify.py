"""
Lane 7 data-integrity gate.

Every raw payload under data/raw/ was captured by hand (sandbox egress is
allowlisted, so the analysis host cannot call Yahoo directly). Hand-capture can
corrupt digits, so before ANY structural claim is made we prove the capture is
faithful by an independent redundancy check:

    the 1-minute slices, resampled to 5 minutes, must reproduce the separately
    fetched 5-minute payload bar-for-bar, OHLC-exact.

Two independent downloads agreeing to the tick is strong evidence neither was
mis-transcribed. Anything that fails here is reported, not silently patched.
"""
from __future__ import annotations

import sys

import pandas as pd

from engine.yahoo_chart_ingest import load_chart, load_and_stitch

DJI_1M_SLICES = [
    "DJI_1m_s1.json",
    "DJI_1m_patch_1044.json",
    "DJI_1m_s2.json",
    "DJI_1m_s3.json",
    "DJI_1m_s4.json",
    "DJI_1m_s5.json",
    "DJI_1m_s6.json",
    "DJI_1m_s7_close.json",
]
DJI_5M = "DJI_5m_1d.json"
YM_SLICES = ["YM_5m_on_a.json", "YM_5m_on_b.json", "YM_5m_rth.json", "YM_5m_close.json"]

RTH_OPEN = "09:30"
RTH_CLOSE = "16:00"


def build_dji_1m():
    return load_and_stitch(DJI_1M_SLICES)


def check_continuity(df: pd.DataFrame, step_min: int, label: str) -> list[str]:
    """Report gaps in the bar grid."""
    notes = []
    deltas = df.index.to_series().diff().dropna()
    bad = deltas[deltas != pd.Timedelta(minutes=step_min)]
    if len(bad):
        for ts, d in bad.items():
            notes.append(f"  GAP {label}: {ts:%H:%M} preceded by {d} (expected {step_min}m)")
    else:
        notes.append(f"  {label}: contiguous {step_min}m grid, no gaps, {len(df)} bars")
    return notes


def main() -> int:
    failures = 0
    print("=" * 78)
    print("LANE 7 DATA INTEGRITY GATE")
    print("=" * 78)

    m1 = build_dji_1m()
    m5 = load_chart(DJI_5M)

    print(f"\n[1] ^DJI 1m stitched : {len(m1.bars)} bars  {m1.bars.index[0]:%H:%M} -> {m1.bars.index[-1]:%H:%M}")
    print(f"    sources: {m1.source_file}")
    print(f"[2] ^DJI 5m payload  : {len(m5.bars)} bars  {m5.bars.index[0]:%H:%M} -> {m5.bars.index[-1]:%H:%M}")
    print(f"    source : {m5.source_file}")

    print("\n[3] Bar-grid continuity")
    for line in check_continuity(m1.bars, 1, "^DJI 1m"):
        print(line)
    for line in check_continuity(m5.bars, 5, "^DJI 5m"):
        print(line)

    # --- redundancy check -------------------------------------------------
    print("\n[4] Independent redundancy check: resample(1m -> 5m) vs fetched 5m")
    agg = m1.bars.resample("5min", closed="left", label="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}
    ).dropna()

    common = agg.index.intersection(m5.bars.index)
    a = agg.loc[common]
    b = m5.bars.loc[common, ["open", "high", "low", "close"]]
    print(f"    overlapping 5m bars compared: {len(common)}")

    for col in ["open", "high", "low", "close"]:
        diff = (a[col] - b[col]).abs()
        worst = diff.max()
        n_bad = int((diff > 1e-6).sum())
        status = "OK  " if n_bad == 0 else "FAIL"
        print(f"    [{status}] {col:<5} mismatched_bars={n_bad:<3} max_abs_diff={worst:.10f}")
        if n_bad:
            failures += 1
            for ts in diff[diff > 1e-6].index[:10]:
                print(f"           {ts:%H:%M}  1m->5m={a.loc[ts, col]:.4f}  5m={b.loc[ts, col]:.4f}")

    # --- session aggregate check -----------------------------------------
    print("\n[5] Session aggregates vs Yahoo meta (independent field)")
    meta = m5.meta
    checks = [
        ("day high", m1.bars["high"].max(), meta["regularMarketDayHigh"]),
        ("day low", m1.bars["low"].min(), meta["regularMarketDayLow"]),
        ("session open", m1.bars["open"].iloc[0], m5.bars["open"].iloc[0]),
    ]
    for name, got, exp in checks:
        ok = abs(got - exp) < 0.02
        if not ok:
            failures += 1
        print(f"    [{'OK  ' if ok else 'FAIL'}] {name:<13} computed={got:.2f}  meta={exp:.2f}")

    # --- known artifacts ---------------------------------------------------
    print("\n[6] Known source artifacts (declared, not repaired)")
    zero_vol = m1.bars.index[m1.bars["volume"] == 0]
    print(f"    ^DJI 1m bars with volume==0: {len(zero_vol)} -> {[f'{t:%H:%M}' for t in zero_vol]}")
    print("      cause: Yahoo zeroes the first bar of every period1/period2 window.")
    print("      effect: 1m VOLUME is unusable on those bars; 1m PRICE is unaffected")
    print("              (proved by the OHLC redundancy check above).")
    print("      mitigation: all volume statements use the DJI_5m_1d.json range=1d payload.")

    # --- YM ---------------------------------------------------------------
    ym = load_and_stitch(YM_SLICES)
    print(f"\n[7] YM=F 5m stitched : {len(ym.bars)} bars  "
          f"{ym.bars.index[0]:%a %H:%M} -> {ym.bars.index[-1]:%a %H:%M}")
    print(f"    contract: {ym.meta.get('shortName')}")
    ym_meta_hi, ym_meta_lo = ym.meta["regularMarketDayHigh"], ym.meta["regularMarketDayLow"]
    sess = ym.bars.loc["2026-09-29 00:00":]
    got_hi, got_lo = sess["high"].max(), sess["low"].min()
    for name, got, exp in [("YM day high", got_hi, ym_meta_hi), ("YM day low", got_lo, ym_meta_lo)]:
        ok = abs(got - exp) < 1.0
        if not ok:
            failures += 1
        print(f"    [{'OK  ' if ok else 'FAIL'}] {name:<12} computed={got:.0f}  meta={exp:.0f}")

    print("\n" + "=" * 78)
    if failures:
        print(f"RESULT: {failures} INTEGRITY FAILURE(S) — do not publish levels from this capture.")
    else:
        print("RESULT: PASS — capture is faithful; levels are safe to cite.")
    print("=" * 78)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
