# -*- coding: utf-8 -*-
"""
Mechanics verification for the US30 sweep-and-reclaim strategy.
===============================================================

These tests check that the machine does what the specification says BEFORE
anyone looks at a performance number. They target the failure modes that
silently inflate backtests: lookahead, same-bar execution, wrong-session
levels, DST drift, optimistic ambiguous fills, and sizing that ignores lot
granularity.

Runs with pytest or standalone:

    python3 tests/test_us30_sweep_reclaim.py
    python3 -m pytest tests/test_us30_sweep_reclaim.py -q

No third-party dependency is required; Backtrader is stubbed so the exact
file that gets pasted into TradeLocker Studio is the file under test.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.join(ROOT, "strategies", "us30_sweep_reclaim")
sys.path.insert(0, PKG)

import research_backtest as rb          # noqa: E402  (installs the bt stub)

STUDIO = rb.STUDIO
Engine = rb.US30RuleEngine
Bar = rb.Bar
ny_parts = STUDIO.ny_parts
days_from_civil = STUDIO._days_from_civil


# ---------------------------------------------------------------------------
# fixtures: hand-built sessions, every bar explicit
# ---------------------------------------------------------------------------

def rth_open_epoch(y, m, d):
    """UTC epoch of 09:30 New York on the given calendar date."""
    base = days_from_civil(y, m, d) * 86400
    return base - STUDIO.ny_utc_offset_seconds(base) + 9 * 3600 + 30 * 60


def make_session(y, m, d, price=42000.0, n=390, overrides=None, spread=0.5):
    """A flat session of `n` one-minute bars, with explicit overrides.

    overrides maps minute-index (0 == 09:30 ET) -> (o, h, l, c).
    """
    start = rth_open_epoch(y, m, d)
    out = []
    for i in range(n):
        if overrides and i in overrides:
            o, h, l, c = overrides[i]
        else:
            o = c = price
            h = price + spread
            l = price - spread
        out.append(Bar(start + i * 60, o, h, l, c, 100.0))
    return out


def run(bars, **params):
    cfg = dict(rb.BASELINE)
    cfg.update(params)
    eng = Engine(**cfg)
    events = []
    for b in bars:
        for it in eng.on_bar(b.ts, b.o, b.h, b.l, b.c):
            events.append(it)
    return eng, events


def entries(events):
    return [e for e in events if e.kind.startswith("ENTER")]


def exits(events):
    return [e for e in events if e.kind == "EXIT"]


# ---------------------------------------------------------------------------
# 1. TIME: DST transitions and New York mapping
# ---------------------------------------------------------------------------

def test_dst_transition_boundaries_exact():
    # 2026 DST: starts Sun 8 Mar, ends Sun 1 Nov.
    assert STUDIO._nth_sunday_day(2026, 3, 2) == 8
    assert STUDIO._nth_sunday_day(2026, 11, 1) == 1
    start = days_from_civil(2026, 3, 8) * 86400 + 7 * 3600
    end = days_from_civil(2026, 11, 1) * 86400 + 6 * 3600
    assert STUDIO.ny_utc_offset_seconds(start - 1) == -5 * 3600
    assert STUDIO.ny_utc_offset_seconds(start) == -4 * 3600
    assert STUDIO.ny_utc_offset_seconds(end - 1) == -4 * 3600
    assert STUDIO.ny_utc_offset_seconds(end) == -5 * 3600


def test_rth_open_is_0930_both_sides_of_dst():
    # EST date and EDT date must both map 09:30 ET correctly.
    for (y, m, d, utc_hour) in ((2026, 2, 10, 14), (2026, 7, 14, 13)):
        ts = rth_open_epoch(y, m, d)
        assert ts % 3600 == 30 * 60
        assert (ts // 3600) % 24 == utc_hour
        key, minute = ny_parts(ts)
        assert key == "%04d-%02d-%02d" % (y, m, d)
        assert minute == 570


def test_offsets_match_zoneinfo_when_available():
    try:
        from zoneinfo import ZoneInfo
        import datetime as dtmod
    except Exception:                                   # pragma: no cover
        return
    tz = ZoneInfo("America/New_York")
    ts = days_from_civil(2024, 1, 1) * 86400
    checked = 0
    while ts < days_from_civil(2028, 1, 1) * 86400:
        dt = dtmod.datetime.fromtimestamp(ts, tz)
        assert int(dt.utcoffset().total_seconds()) == STUDIO.ny_utc_offset_seconds(ts), ts
        checked += 1
        ts += 3 * 3600
    assert checked > 10000


# ---------------------------------------------------------------------------
# 2. CAUSAL LEVELS
# ---------------------------------------------------------------------------

def test_first_session_never_trades():
    bars = make_session(2026, 4, 6, overrides={100: (42000, 42000, 41000, 42000)})
    eng, events = run(bars)
    assert entries(events) == []
    assert eng.stats["skipped_no_prior"] > 0


def test_levels_come_from_the_previous_session_not_the_current_one():
    day1 = make_session(2026, 4, 6, price=42000.0,
                        overrides={10: (42000, 42100, 42000, 42000),     # high 42100
                                   20: (42000, 42000, 41900, 42000)})    # low  41900
    day2 = make_session(2026, 4, 7, price=42050.0)
    eng, _ = run(day1 + day2)
    assert eng.prior_high == 42100.0
    assert eng.prior_low == 41900.0
    assert eng.prior_key == "2026-04-06"


def test_incomplete_previous_session_blocks_trading_under_skip_policy():
    day1 = make_session(2026, 4, 6, n=200,                     # early close
                        overrides={10: (42000, 42100, 42000, 42000),
                                   20: (42000, 42000, 41900, 42000)})
    day2 = make_session(2026, 4, 7, price=42000.0,
                        overrides={15: (42000, 42000, 41890, 41990),
                                   16: (41990, 41990, 41890, 41950),
                                   29: (41950, 41960, 41940, 41955)})
    eng, events = run(day1 + day2)
    assert eng.stats["incomplete_prior_sessions"] == 1
    assert entries(events) == [], "a half day must not seed the next day's levels"


def test_extended_hours_only_date_does_not_destroy_levels():
    day1 = make_session(2026, 4, 6,
                        overrides={10: (42000, 42100, 42000, 42000),
                                   20: (42000, 42000, 41900, 42000)})
    # a date carrying only pre-market bars (03:00 ET) must be ignored entirely
    base = days_from_civil(2026, 4, 7) * 86400
    pre = base - STUDIO.ny_utc_offset_seconds(base) + 3 * 3600
    ghost = [Bar(pre + i * 60, 42010, 42011, 42009, 42010, 1.0) for i in range(30)]
    eng, _ = run(day1 + ghost)
    assert eng.prior_high == 42100.0 and eng.prior_low == 41900.0
    assert eng.prior_key == "2026-04-06"


# ---------------------------------------------------------------------------
# 3. SIGNAL TIMING: 15m construction and no same-bar execution
# ---------------------------------------------------------------------------

def _two_day_long_setup(**over):
    """Day 2 sweeps below the prior low inside [09:45,10:00) and reclaims."""
    day1 = make_session(2026, 4, 6, price=42000.0,
                        overrides={10: (42000, 42100, 42000, 42000),
                                   20: (42000, 42000, 41900, 42000)})
    ov = {
        16: (42000, 42000, 41880, 41900),   # 09:46 sweep to 41880
        17: (41900, 41960, 41900, 41950),
        29: (41950, 41960, 41940, 41955),   # 09:59 close of the 09:45 bucket
    }
    ov.update(over)
    day2 = make_session(2026, 4, 7, price=41950.0, overrides=ov)
    return day1, day2


def test_entry_is_the_open_of_the_bar_after_the_confirming_bucket():
    day1, day2 = _two_day_long_setup()
    eng, events = run(day1 + day2)
    ents = entries(events)
    assert len(ents) == 1, ents
    e = ents[0]
    assert e.kind == "ENTER_LONG"
    # confirming bucket is [09:45,10:00); entry must be the 10:00 bar's open
    key, minute = ny_parts(e.ts)
    assert (key, minute) == ("2026-04-07", 600)
    assert e.ts % 900 == 0
    entry_bar = [b for b in day2 if b.ts == e.ts][0]
    assert e.price_ref == entry_bar.o


def test_no_signal_is_taken_from_an_unfinished_bucket():
    """Truncating the data one bar before the bucket closes kills the signal."""
    day1, day2 = _two_day_long_setup()
    truncated = [b for b in day2 if ny_parts(b.ts)[1] < 600]
    _, events = run(day1 + truncated)
    assert entries(events) == []


def test_fifteen_minute_bucket_is_an_exact_aggregation():
    day1, day2 = _two_day_long_setup()
    eng = Engine(**rb.BASELINE)
    captured = {}
    original = eng._on_completed_bucket

    def spy(ts, bar_open, bucket, minute):
        captured[ts] = bucket
        return original(ts, bar_open, bucket, minute)

    eng._on_completed_bucket = spy
    for b in day1 + day2:
        eng.on_bar(b.ts, b.o, b.h, b.l, b.c)

    bucket_ts = rth_open_epoch(2026, 4, 7) + 30 * 60          # 10:00 -> closes [09:45,10:00)
    members = [b for b in day2 if bucket_ts - 900 <= b.ts < bucket_ts]
    assert len(members) == 15
    o, h, l, c, n = captured[bucket_ts]
    assert n == 15
    assert o == members[0].o and c == members[-1].c
    assert h == max(b.h for b in members) and l == min(b.l for b in members)


def test_short_setup_requires_a_later_bar_to_confirm():
    day1 = make_session(2026, 4, 6, price=42000.0,
                        overrides={10: (42000, 42100, 42000, 42000),
                                   20: (42000, 42000, 41900, 42000)})
    # 09:45 bucket taps the resistance zone and closes back below it
    day2 = make_session(2026, 4, 7, price=42050.0, overrides={
        16: (42050, 42098, 42050, 42060),
        29: (42060, 42060, 42040, 42050),
    })
    # stop feeding just before the next bucket closes: the setup is armed but
    # has had no later bar to confirm on
    truncated = [b for b in day2 if ny_parts(b.ts)[1] < 615]
    eng, events = run(day1 + truncated)
    # the arming bucket itself must never also be the confirming bucket
    assert entries(events) == []
    assert eng.short_setup is not None


def test_short_confirms_on_a_later_bucket_and_enters_next_bar():
    day1 = make_session(2026, 4, 6, price=42000.0,
                        overrides={10: (42000, 42100, 42000, 42000),
                                   20: (42000, 42000, 41900, 42000)})
    ov = {16: (42050, 42098, 42030, 42060),      # arm: tap zone, close below
          29: (42060, 42060, 42030, 42050)}
    for i in range(30, 45):                       # next bucket breaks down
        ov[i] = (42000, 42005, 41990, 41995)
    day2 = make_session(2026, 4, 7, price=42050.0, overrides=ov)
    eng, events = run(day1 + day2)
    ents = entries(events)
    assert len(ents) == 1 and ents[0].kind == "ENTER_SHORT"
    key, minute = ny_parts(ents[0].ts)
    assert minute == 615                          # 10:15, the bar after [10:00,10:15)
    assert ents[0].stop > 42098                   # beyond the rejection extreme


# ---------------------------------------------------------------------------
# 4. STOP / TARGET / AMBIGUITY / GAPS
# ---------------------------------------------------------------------------

def test_stop_sits_beyond_the_sweep_extreme():
    day1, day2 = _two_day_long_setup()
    _, events = run(day1 + day2, stop_buffer_pts=7.0)
    e = entries(events)[0]
    assert abs(e.stop - (41880.0 - 7.0)) < 1e-9
    assert abs(e.target - (e.price_ref + 2.0 * (e.price_ref - e.stop))) < 1e-9


def test_ambiguous_bar_resolves_to_the_stop_and_is_counted():
    day1, day2 = _two_day_long_setup()
    _, ev = run(day1 + day2)
    entry = entries(ev)[0]
    # rebuild day 2 so the bar AFTER entry spans both the stop and the target
    ov = {16: (42000, 42000, 41880, 41900), 17: (41900, 41960, 41900, 41950),
          29: (41950, 41960, 41940, 41955)}
    lo = entry.stop - 5.0
    hi = entry.target + 5.0
    ov[31] = (41955, hi, lo, 41955)
    day2b = make_session(2026, 4, 7, price=41950.0, overrides=ov)
    eng, events = run(day1 + day2b)
    xs = exits(events)
    assert xs and xs[0].reason == "stop_ambiguous"
    assert eng.stats["ambiguous_bars"] == 1


def test_gap_through_the_stop_fills_at_the_open_not_the_stop():
    day1, day2 = _two_day_long_setup()
    _, ev = run(day1 + day2)
    entry = entries(ev)[0]
    ov = {16: (42000, 42000, 41880, 41900), 17: (41900, 41960, 41900, 41950),
          29: (41950, 41960, 41940, 41955)}
    gapped = entry.stop - 40.0
    ov[31] = (gapped, gapped + 1, gapped - 1, gapped)
    day2b = make_session(2026, 4, 7, price=41950.0, overrides=ov)
    _, events = run(day1 + day2b)
    x = exits(events)[0]
    assert x.reason == "stop"
    assert x.price_ref == gapped, "a gap must fill at the open, not at the stop"


def test_missing_bars_force_a_flat_position_and_clear_setups():
    day1, day2 = _two_day_long_setup()
    kept = [b for b in day2 if not (605 <= ny_parts(b.ts)[1] < 625)]   # 20-minute hole
    eng, events = run(day1 + kept)
    xs = exits(events)
    assert eng.stats["gaps"] == 1
    assert xs and xs[0].reason == "data_gap"


def test_end_of_day_flattening_is_unconditional():
    day1, day2 = _two_day_long_setup()
    eng, events = run(day1 + day2, target_r=500.0, max_gap_minutes=600)
    x = exits(events)[-1]
    assert x.reason == "flat_by_time"
    assert ny_parts(x.ts)[1] == 955          # 15:55 New York


def test_no_new_entry_after_the_cutoff():
    day1 = make_session(2026, 4, 6, price=42000.0,
                        overrides={10: (42000, 42100, 42000, 42000),
                                   20: (42000, 42000, 41900, 42000)})
    late = {}
    for i in range(360, 375):                    # 15:30 bucket
        late[i] = (42000, 42000, 41880, 41890)
    for i in range(375, 380):
        late[i] = (41890, 41990, 41890, 41985)
    day2 = make_session(2026, 4, 7, price=41950.0, overrides=late)
    _, events = run(day1 + day2)
    assert entries(events) == []


def test_one_position_at_a_time_and_session_trade_cap():
    day1 = make_session(2026, 4, 6, price=42000.0,
                        overrides={10: (42000, 42100, 42000, 42000),
                                   20: (42000, 42000, 41900, 42000)})
    ov = {}
    for blk in range(0, 20):                    # repeated sweep/reclaim cycles
        s = 15 + blk * 15
        for i in range(s, s + 15):
            ov[i] = (41950, 41960, 41880, 41890)
        for i in range(s + 15, s + 30):
            ov[i] = (41890, 41990, 41890, 41985)
    day2 = make_session(2026, 4, 7, price=41950.0, overrides=ov)
    eng, events = run(day1 + day2, max_trades_per_session=2)
    assert len(entries(events)) <= 2
    assert eng.trades_this_session <= 2


def test_setup_expires_after_the_configured_number_of_buckets():
    day1 = make_session(2026, 4, 6, price=42000.0,
                        overrides={10: (42000, 42100, 42000, 42000),
                                   20: (42000, 42000, 41900, 42000)})
    # day 2 idles just above the prior low (41900) so nothing re-arms, then
    # sweeps once in [09:45,10:00) and only reclaims six buckets later.
    ov = {16: (41900, 41900, 41880, 41890)}      # sweep in [09:45,10:00)
    reclaim_at = 15 + 15 * 6                     # bucket index 8
    for i in range(reclaim_at, reclaim_at + 15):
        ov[i] = (41900, 41990, 41899.6, 41985)
    day2 = make_session(2026, 4, 7, price=41900.0, overrides=ov, spread=0.5)
    _, ev_long = run(day1 + day2, setup_expiry_bars=8)
    _, ev_short = run(day1 + day2, setup_expiry_bars=1)
    assert len(entries(ev_long)) == 1
    assert entries(ev_short) == [], "an expired setup must not fire"


def test_short_setup_is_invalidated_by_a_close_back_above_the_rejection_high():
    day1 = make_session(2026, 4, 6, price=42000.0,
                        overrides={10: (42000, 42100, 42000, 42000),
                                   20: (42000, 42000, 41900, 42000)})
    ov = {16: (42050, 42098, 42030, 42060), 29: (42060, 42060, 42030, 42050)}
    for i in range(30, 45):
        ov[i] = (42100, 42150, 42100, 42140)     # closes back above the rejection high
    day2 = make_session(2026, 4, 7, price=42050.0, overrides=ov)
    eng, events = run(day1 + day2)
    assert eng.stats["invalidated_short"] >= 1


# ---------------------------------------------------------------------------
# 5. EXECUTION MODEL: sizing, costs, rounding
# ---------------------------------------------------------------------------

def test_position_size_follows_risk_and_actual_stop_distance():
    day1, day2 = _two_day_long_setup()
    spec = dict(rb.DEFAULT_SPEC)
    spec.update({"spread_pts": 0.0, "slippage_pts": 0.0, "lot_step": 0.01,
                 "value_per_point_per_lot": 1.0, "risk_per_trade_pct": 0.5,
                 "starting_equity": 100000.0})
    res = rb.simulate(day1 + day2, spec, rb.BASELINE)
    t = res["trades"][0]
    stop_dist = abs(t.fill_in - t.stop)
    expected = int((500.0 / stop_dist) / 0.01) * 0.01
    assert abs(t.lots - expected) < 1e-9
    assert t.risk_cash <= 500.0 + 1e-9, "rounding must never increase risk"


def test_size_below_the_minimum_lot_is_skipped_not_rounded_up():
    day1, day2 = _two_day_long_setup()
    spec = dict(rb.DEFAULT_SPEC)
    spec.update({"min_lot": 50.0, "lot_step": 1.0, "risk_per_trade_pct": 0.001})
    res = rb.simulate(day1 + day2, spec, rb.BASELINE)
    assert res["trades"] == []
    assert res["skipped_min_size"] == 1


def test_costs_are_charged_once_per_round_trip():
    day1, day2 = _two_day_long_setup()
    base = dict(rb.DEFAULT_SPEC)
    base.update({"spread_pts": 0.0, "slippage_pts": 0.0, "price_basis": "bid",
                 "commission_per_lot_per_side": 0.0})
    with_cost = dict(base)
    with_cost.update({"spread_pts": 2.0, "slippage_pts": 0.5})

    r0 = rb.simulate(day1 + day2, base, rb.BASELINE)["trades"][0]
    r1 = rb.simulate(day1 + day2, with_cost, rb.BASELINE)["trades"][0]
    # long on a bid series: pay spread+slip on entry, slip on exit
    assert abs((r1.fill_in - r0.fill_in) - 2.5) < 1e-6
    assert abs((r0.fill_out - r1.fill_out) - 0.5) < 1e-6


def test_mid_basis_splits_the_spread_without_double_counting():
    day1, day2 = _two_day_long_setup()
    bid = dict(rb.DEFAULT_SPEC)
    bid.update({"price_basis": "bid", "spread_pts": 2.0, "slippage_pts": 0.0})
    mid = dict(bid)
    mid["price_basis"] = "mid"
    tb = rb.simulate(day1 + day2, bid, rb.BASELINE)["trades"][0]
    tm = rb.simulate(day1 + day2, mid, rb.BASELINE)["trades"][0]
    round_trip_bid = (tb.fill_in - tb.ref_in) + (tb.ref_out - tb.fill_out)
    round_trip_mid = (tm.fill_in - tm.ref_in) + (tm.ref_out - tm.fill_out)
    assert abs(round_trip_bid - 2.0) < 1e-6
    assert abs(round_trip_mid - 2.0) < 1e-6


def test_fills_are_rounded_to_the_tick():
    day1, day2 = _two_day_long_setup()
    spec = dict(rb.DEFAULT_SPEC)
    spec.update({"tick_size": 0.25, "spread_pts": 1.13, "slippage_pts": 0.07})
    for t in rb.simulate(day1 + day2, spec, rb.BASELINE)["trades"]:
        for px in (t.fill_in, t.fill_out):
            assert abs(px / 0.25 - round(px / 0.25)) < 1e-9


# ---------------------------------------------------------------------------
# 6. DATA HYGIENE
# ---------------------------------------------------------------------------

def test_non_monotonic_input_is_rejected_loudly():
    bars = make_session(2026, 4, 6, n=10)
    eng = Engine(**rb.BASELINE)
    for b in bars:
        eng.on_bar(b.ts, b.o, b.h, b.l, b.c)
    try:
        eng.on_bar(bars[-1].ts - 60, 1, 1, 1, 1)
    except ValueError:
        return
    raise AssertionError("out-of-order bar must raise")


def test_duplicate_and_malformed_rows_are_classified(tmp_path=None):
    import tempfile
    path = os.path.join(tempfile.mkdtemp(), "m1.csv")
    t0 = rth_open_epoch(2026, 4, 6)
    with open(path, "w") as fh:
        fh.write("timestamp,open,high,low,close,volume\n")
        fh.write("%d,100,101,99,100,5\n" % (t0 * 1000))
        fh.write("%d,100,101,99,100,5\n" % (t0 * 1000))            # identical dup
        fh.write("%d,100,101,99,100,5\n" % ((t0 + 60) * 1000))
        fh.write("%d,111,112,110,111,5\n" % ((t0 + 60) * 1000))    # conflicting dup
        fh.write("%d,100,90,99,100,5\n" % ((t0 + 120) * 1000))     # high < low
    bars, rep = rb.load_m1_csv(path)
    assert rep["duplicates_identical"] == 1
    assert rep["duplicates_conflicting"] == 1
    assert rep["ohlc_violations"] == 1
    assert len(bars) == 2
    assert bars[0].ts == t0 and bars[1].ts == t0 + 60


def test_epoch_ms_and_iso_timestamps_agree():
    import tempfile
    d = tempfile.mkdtemp()
    t0 = 1775568600                      # 2026-04-07 13:30:00Z
    p1 = os.path.join(d, "ms.csv")
    p2 = os.path.join(d, "iso.csv")
    with open(p1, "w") as fh:
        fh.write("timestamp,open,high,low,close,volume\n%d,1,2,0.5,1.5,3\n" % (t0 * 1000))
    with open(p2, "w") as fh:
        fh.write("time,open,high,low,close\n2026-04-07T13:30:00Z,1,2,0.5,1.5\n")
    assert rb.load_m1_csv(p1)[0][0].ts == rb.load_m1_csv(p2)[0][0].ts == t0


# ---------------------------------------------------------------------------
# 7. STUDIO INTERFACE CONTRACT
# ---------------------------------------------------------------------------

def test_studio_params_is_a_dict_and_declares_a_supported_sizer():
    params = STUDIO.US30SweepReclaimStrategy.params
    assert isinstance(params, dict), "Studio expects params as a dict"
    assert params["sizer"] in ("FixedLotSizer", "FixedCashSizer",
                               "AssignedMarginPercentSizer", "CustomSizer")
    sizer_value_key = {"FixedLotSizer": "sizer_lots",
                       "FixedCashSizer": "sizer_cash",
                       "AssignedMarginPercentSizer": "sizer_assigned_margin_percent",
                       "CustomSizer": "sizer_value"}[params["sizer"]]
    assert sizer_value_key in params


def test_every_engine_parameter_is_exposed_in_the_studio_params():
    params = STUDIO.US30SweepReclaimStrategy.params
    keys = set(STUDIO.US30SweepReclaimStrategy.ENGINE_KEYS)
    assert keys == set(STUDIO.DEFAULTS), "engine defaults and ENGINE_KEYS drifted"
    missing = keys - set(params)
    assert not missing, "params missing engine keys: %s" % sorted(missing)
    for k in keys:
        assert params[k] == STUDIO.DEFAULTS[k] or k in ("target_r",), \
            "studio param %s (%r) disagrees with engine default %r" % (k, params[k], STUDIO.DEFAULTS[k])


def test_engine_rejects_unknown_parameters():
    try:
        Engine(nonexistent_param=1)
    except ValueError:
        return
    raise AssertionError("unknown parameters must not be silently ignored")


def test_research_harness_and_studio_share_one_engine():
    assert rb.US30RuleEngine is STUDIO.US30RuleEngine
    assert set(rb.BASELINE) == set(STUDIO.DEFAULTS)


# ---------------------------------------------------------------------------
# 7b. PASTE INTEGRITY  -  the failure mode that actually bites in Studio
# ---------------------------------------------------------------------------

STUDIO_FILE = os.path.join(PKG, "tradelocker_studio_us30.py")


def test_studio_file_parses_exactly_as_studio_checks_it():
    """Studio's bot check parses the source. A truncated paste fails there."""
    import ast
    src = open(STUDIO_FILE, encoding="utf-8").read()
    ast.parse(src)                      # raises SyntaxError if truncated


def test_studio_file_is_pure_ascii_and_ends_with_the_sentinel():
    src = open(STUDIO_FILE, encoding="utf-8").read()
    bad = sorted({c for c in src if ord(c) > 127})
    assert not bad, "non-ASCII characters survive paste badly: %s" % bad
    lines = src.splitlines()
    assert "END OF FILE" in src, "the paste-integrity sentinel is missing"
    advertised = None
    for line in lines:
        if "expected total lines" in line:
            advertised = int(line.split(":")[1].strip())
    assert advertised == len(lines), \
        "sentinel advertises %s lines but the file has %s" % (advertised, len(lines))


def test_studio_file_imports_only_backtrader():
    """Anything else invites a code-checker rejection and a runtime surprise."""
    import ast
    tree = ast.parse(open(STUDIO_FILE, encoding="utf-8").read())
    mods = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            mods.update(a.name.split(".")[0] for a in n.names)
        elif isinstance(n, ast.ImportFrom) and n.module:
            mods.add(n.module.split(".")[0])
    assert mods == {"backtrader"}, "unexpected imports: %s" % sorted(mods)


def test_studio_file_uses_no_function_blocked_by_studios_security_policy():
    """Studio rejects reflection/eval builtins outright.

    Observed verbatim from the desktop app:
        Security policy violated in strategy |
        Use of functions is not allowed: ['getattr']

    TradeLocker publishes no denylist, so this is the conservative superset of
    reflection, dynamic-execution and I/O builtins. The same message confirmed
    that dict/tuple/sorted/print/min/max/divmod/float/int ARE permitted --
    they were present in the same file and went unreported.
    """
    import ast
    blocked = {
        "getattr", "setattr", "delattr", "hasattr",
        "eval", "exec", "compile", "__import__", "importlib",
        "globals", "locals", "vars", "dir", "open", "input",
        "breakpoint", "exit", "quit", "help", "memoryview",
    }
    tree = ast.parse(open(STUDIO_FILE, encoding="utf-8").read())
    used = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
            used.add(n.func.id)
        elif isinstance(n, ast.Name):
            used.add(n.id)
    offending = sorted(used & blocked)
    assert not offending, \
        "Studio's security check will reject these: %s" % offending


def test_engine_construction_in_studio_file_matches_the_engine_parameters():
    """The explicit constructor call cannot silently drift.

    Because getattr() is banned, the strategy must name all 19 parameters by
    hand. This parses that call and compares it against DEFAULTS, so adding an
    engine parameter without wiring it through fails here instead of silently
    running on a default in Studio.
    """
    import ast
    tree = ast.parse(open(STUDIO_FILE, encoding="utf-8").read())
    call = None
    for n in ast.walk(tree):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id == "US30RuleEngine"):
            call = n
    assert call is not None, "no US30RuleEngine(...) construction found"
    assert not call.args, "pass engine parameters by keyword, not positionally"
    passed = sorted(kw.arg for kw in call.keywords if kw.arg)
    assert None not in [kw.arg for kw in call.keywords], \
        "**kwargs unpacking defeats the drift check"
    assert passed == sorted(STUDIO.DEFAULTS), (
        "constructor call and engine DEFAULTS disagree; missing=%s extra=%s"
        % (sorted(set(STUDIO.DEFAULTS) - set(passed)),
           sorted(set(passed) - set(STUDIO.DEFAULTS))))
    # every value must come straight off self.p, not be hard-coded
    for kw in call.keywords:
        assert isinstance(kw.value, ast.Attribute), \
            "%s is not read from the params dict" % kw.arg
        assert kw.value.attr == kw.arg, \
            "%s is wired to self.p.%s" % (kw.arg, kw.value.attr)


# ---------------------------------------------------------------------------
# 8. RECONCILIATION: a trade recomputed by hand from the bars
# ---------------------------------------------------------------------------

def test_trade_pnl_reconciles_against_the_underlying_bars():
    day1, day2 = _two_day_long_setup()
    spec = dict(rb.DEFAULT_SPEC)
    spec.update({"spread_pts": 2.0, "slippage_pts": 0.5, "tick_size": 0.01,
                 "value_per_point_per_lot": 1.0, "commission_per_lot_per_side": 3.0})
    res = rb.simulate(day1 + day2, spec, rb.BASELINE)
    t = res["trades"][0]
    entry_bar = [b for b in day2 if b.ts == t.ts_in][0]
    exit_bar = [b for b in day2 if b.ts == t.ts_out][0]
    assert t.ref_in == entry_bar.o
    assert round(t.fill_in, 2) == round(entry_bar.o + 2.0 + 0.5, 2)
    if t.reason_out == "target":
        assert exit_bar.h >= t.target
    elif t.reason_out == "stop":
        assert exit_bar.l <= t.stop
    expected_pnl = ((t.fill_out - t.fill_in) * t.side * 1.0 * t.lots) - 3.0 * t.lots * 2
    assert abs(t.pnl - expected_pnl) < 1e-6
    assert abs(t.r - t.pnl / t.risk_cash) < 1e-9


# ---------------------------------------------------------------------------

def _run_all():
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in fns:
        try:
            fn()
            print("PASS  %s" % name)
        except Exception as exc:
            failed += 1
            import traceback
            print("FAIL  %s: %s" % (name, exc))
            traceback.print_exc()
    print("\n%d/%d passed" % (len(fns) - failed, len(fns)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_run_all())
