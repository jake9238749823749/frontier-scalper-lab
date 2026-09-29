"""
Offline integrity tests for the LANE 2 US30/Dow intraday dataset.

These tests re-derive everything from the raw captured payloads and assert the
published CSV/JSON artefacts agree. They require no network and no third-party
packages, so they can be run any time to prove the dataset was not hand-edited.

    python3 -m pytest tests/test_us30_intraday_dataset.py -q
    python3 tests/test_us30_intraday_dataset.py          # plain runner
"""

from __future__ import annotations

import csv
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DS = os.path.join(ROOT, "datasets", "us30_20260929")
RAW = os.path.join(DS, "raw")
TFS = ["1m", "3m", "5m", "15m", "30m"]
STEP = {"1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800}
EPS = 0.011  # values are published rounded to 2dp


def _json(name):
    with open(os.path.join(DS, name)) as fh:
        return json.load(fh)


def _raw(tf):
    with open(os.path.join(RAW, f"yahoo_dji_{tf}.json")) as fh:
        return json.load(fh)


def _bars(tf):
    with open(os.path.join(DS, f"bars_{tf}.csv")) as fh:
        return list(csv.DictReader(fh))


def test_raw_payload_arrays_are_rectangular():
    for tf in ("1m", "5m", "15m", "30m"):
        r = _raw(tf)
        n = len(r["timestamp"])
        for k in ("open", "high", "low", "close", "volume"):
            assert len(r[k]) == n, f"{tf}: {k} array length {len(r[k])} != {n}"


def test_every_published_bar_traces_back_to_raw():
    """No invented bars: each native CSV row must exist in the raw payload."""
    for tf in ("1m", "5m", "15m", "30m"):
        r = _raw(tf)
        raw_by_ts = {t: i for i, t in enumerate(r["timestamp"])}
        for row in _bars(tf):
            ts = int(row["epoch"])
            assert ts in raw_by_ts, f"{tf}: published bar {ts} absent from raw payload"
            i = raw_by_ts[ts]
            for col, key in (("open", "open"), ("high", "high"), ("low", "low"), ("close", "close")):
                assert abs(float(row[col]) - r[key][i]) < EPS, f"{tf} {ts} {col} mismatch"


def test_ohlc_internal_consistency():
    for tf in TFS:
        for row in _bars(tf):
            o, h, l, c = (float(row[k]) for k in ("open", "high", "low", "close"))
            assert h >= l - EPS, f"{tf} {row['epoch']}: high < low"
            assert h >= max(o, c) - EPS, f"{tf} {row['epoch']}: high < max(o,c)"
            assert l <= min(o, c) + EPS, f"{tf} {row['epoch']}: low > min(o,c)"


def test_derived_columns_recompute():
    for tf in TFS:
        prev_close = None
        for row in _bars(tf):
            o, h, l, c = (float(row[k]) for k in ("open", "high", "low", "close"))
            assert abs(float(row["range_pts"]) - (h - l)) < EPS
            assert abs(float(row["body_pts"]) - (c - o)) < EPS
            assert abs(float(row["upper_wick_pts"]) - (h - max(o, c))) < EPS
            assert abs(float(row["lower_wick_pts"]) - (min(o, c) - l)) < EPS
            if row["close_pos_in_range"]:
                assert abs(float(row["close_pos_in_range"]) - (c - l) / (h - l)) < 0.01
                assert 0.0 <= float(row["close_pos_in_range"]) <= 1.0
            if prev_close is not None and row["ret_pts"]:
                assert abs(float(row["ret_pts"]) - (c - prev_close)) < EPS
            expect = "UP" if c > o else ("DOWN" if c < o else "FLAT")
            assert row["direction"] == expect
            prev_close = c


def test_completed_flag_matches_vendor_snapshot_time():
    """A bar may only be COMPLETED if it closed at or before the vendor snapshot."""
    summary = _json("dataset_summary.json")
    for tf in TFS:
        as_of_src = "1m" if tf == "3m" else tf
        as_of = _raw(as_of_src)["meta"]["regularMarketTime"]
        for row in _bars(tf):
            end = int(row["epoch"]) + STEP[tf]
            if row["bar_status"] == "COMPLETED":
                assert end <= as_of, f"{tf} {row['epoch']} flagged COMPLETED but closes after snapshot"
            else:
                assert end > as_of, f"{tf} {row['epoch']} flagged IN_PROGRESS but already closed"
        assert summary["timeframes"][tf]["completed_bars"] == sum(
            1 for r in _bars(tf) if r["bar_status"] == "COMPLETED")


def test_3m_is_exact_aggregation_of_1m():
    m1 = {int(r["epoch"]): r for r in _bars("1m")}
    checked = 0
    for row in _bars("3m"):
        ts = int(row["epoch"])
        members = [m1[ts + k * 60] for k in range(3) if ts + k * 60 in m1]
        assert len(members) == 3, f"3m bar {ts} not backed by 3 native 1m bars"
        assert abs(float(row["open"]) - float(members[0]["open"])) < EPS
        assert abs(float(row["close"]) - float(members[-1]["close"])) < EPS
        assert abs(float(row["high"]) - max(float(m["high"]) for m in members)) < EPS
        assert abs(float(row["low"]) - min(float(m["low"]) for m in members)) < EPS
        if row["volume"]:
            assert int(row["volume"]) == sum(int(m["volume"]) for m in members)
        assert row["origin"] == "DERIVED"
        checked += 1
    assert checked > 0


def test_native_series_are_labelled_verified():
    for tf in ("1m", "5m", "15m", "30m"):
        assert all(r["origin"] == "VERIFIED" for r in _bars(tf))


def test_swings_satisfy_the_fractal_definition():
    k = 2
    for tf in TFS:
        bars = [r for r in _bars(tf) if r["bar_status"] == "COMPLETED"]
        highs = [float(b["high"]) for b in bars]
        lows = [float(b["low"]) for b in bars]
        with open(os.path.join(DS, f"swings_{tf}.csv")) as fh:
            swings = list(csv.DictReader(fh))
        idx = {int(b["epoch"]): i for i, b in enumerate(bars)}
        for sw in swings:
            i = idx[int(sw["epoch"])]
            assert k <= i < len(bars) - k, f"{tf}: swing at unconfirmable index {i}"
            if sw["swing_type"] == "SWING_HIGH":
                assert all(highs[i] > highs[i - j] and highs[i] > highs[i + j]
                           for j in range(1, k + 1)), f"{tf}: bad swing high at {sw['epoch']}"
            else:
                assert all(lows[i] < lows[i - j] and lows[i] < lows[i + j]
                           for j in range(1, k + 1)), f"{tf}: bad swing low at {sw['epoch']}"
        # completeness: every qualifying bar must be published as a swing
        published = {(int(s["epoch"]), s["swing_type"]) for s in swings}
        for i in range(k, len(bars) - k):
            ts = int(bars[i]["epoch"])
            if all(highs[i] > highs[i - j] and highs[i] > highs[i + j] for j in range(1, k + 1)):
                assert (ts, "SWING_HIGH") in published, f"{tf}: unpublished swing high at {ts}"
            if all(lows[i] < lows[i - j] and lows[i] < lows[i + j] for j in range(1, k + 1)):
                assert (ts, "SWING_LOW") in published, f"{tf}: unpublished swing low at {ts}"


def test_structural_verification_checks_pass():
    summary = _json("dataset_summary.json")
    must_pass = [
        "1m aggregation reproduces native 5m OHLC (overlap window)",
        "15m aggregation reproduces native 30m OHLC+volume",
        "session high/low from 5m tape vs vendor regularMarketDayHigh/Low",
        "cross-source session OHL (Yahoo tape vs CNBC exchange feed)",
        "cross-timeframe session volume reconciliation (5m vs 15m vs 30m, common cutoff)",
        "derived change (last - previousClose) vs vendor fulldayChange field",
    ]
    by_name = {c["check"]: c for c in summary["verification"]}
    for name in must_pass:
        assert name in by_name, f"missing check: {name}"
        assert by_name[name]["status"] == "PASS", f"{name} -> {by_name[name]['status']}"


def test_known_discrepancies_are_flagged_not_hidden():
    """The two unreconciled volume issues must stay visible in the artefacts."""
    summary = _json("dataset_summary.json")
    by_name = {c["check"]: c for c in summary["verification"]}
    head = by_name["headline regularMarketVolume vs sum of 5m bar volumes"]
    assert head["status"].startswith("FLAG")
    assert head["residual_vs_vendor"] > 0
    onem = by_name["1m volume sum vs native 5m volume sum (same window)"]
    assert onem["status"].startswith("FLAG")
    assert onem["residual_fully_attributed"] is True
    with open(os.path.join(DS, "US30_INTRADAY_TAPE.md")) as fh:
        report = fh.read()
    assert "## 3. MISSING" in report
    assert "left unreconciled" in report


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\n{len(fns)} checks passed")
