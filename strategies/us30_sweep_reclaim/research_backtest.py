# -*- coding: utf-8 -*-
"""
Offline research harness for the US30 sweep-and-reclaim strategy.
=================================================================

This harness does NOT re-implement the strategy. It imports `US30RuleEngine`
straight out of `tradelocker_studio_us30.py` -- the same file you paste into
TradeLocker Studio -- so signal logic cannot drift between research and
deployment. What the harness adds is everything Studio hides from us:

    * explicit 1-minute CSV ingestion with integrity checks,
    * an explicit fill / spread / slippage / commission model,
    * explicit risk-based position sizing on a simulated account,
    * metrics in R with session-block bootstrap uncertainty,
    * chronological dev / validation / untouched-test splits,
    * a predeclared parameter grid where EVERY configuration is logged.

Standard library only (no pandas / numpy), so it runs anywhere.

Usage
-----
    python3 research_backtest.py --csv M1.csv --mode baseline
    python3 research_backtest.py --csv M1.csv --mode grid --out grid_log.csv
    python3 research_backtest.py --csv M1.csv --mode costs
    python3 research_backtest.py --self-test        # synthetic mechanics demo

CSV formats accepted (header required):
    Dukascopy-node : timestamp,open,high,low,close,volume   (epoch ms, UTC)
    Generic ISO    : time|datetime|timestamp,open,high,low,close[,volume]
                     with ISO-8601 values, e.g. 2026-09-29T13:30:00Z
Use --tz-offset-min if the file's clock is not UTC.
"""

import argparse
import csv
import json
import math
import os
import random
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))


# ---------------------------------------------------------------------------
# Import the Studio file without requiring Backtrader to be installed.
# ---------------------------------------------------------------------------
def load_studio_module():
    if "backtrader" not in sys.modules:
        stub = types.ModuleType("backtrader")

        class _Order(object):
            Submitted = 0
            Accepted = 1
            Completed = 2
            Canceled = 3
            Margin = 4
            Rejected = 5

        class _Strategy(object):
            params = {}

        stub.Strategy = _Strategy
        stub.Sizer = object
        stub.Order = _Order
        stub.indicators = types.SimpleNamespace()
        stub.__stub__ = True
        sys.modules["backtrader"] = stub
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    import tradelocker_studio_us30 as studio
    return studio


STUDIO = load_studio_module()
US30RuleEngine = STUDIO.US30RuleEngine
ny_parts = STUDIO.ny_parts


# ===========================================================================
# 1. INSTRUMENT + EXECUTION SPECIFICATION
# ===========================================================================
# Every one of these is broker-specific. There is no universal US30 CFD
# contract. They are REQUIRED INPUTS, not defaults you should trust. The
# values below are placeholders that make the arithmetic run; override them
# from your broker's contract specification before believing any output.

DEFAULT_SPEC = {
    "symbol": "US30",
    "account_currency": "USD",
    "value_per_point_per_lot": 1.0,   # REQUIRED: account-currency P/L per 1.0 index point per 1.0 lot
    "tick_size": 0.01,                # REQUIRED: minimum price increment
    "lot_step": 0.01,                 # REQUIRED: minimum lot increment
    "min_lot": 0.01,                  # REQUIRED
    "max_lot": 100.0,                  # REQUIRED
    "price_basis": "bid",             # "bid" or "mid": what the CSV close represents
    "spread_pts": 2.0,                # REQUIRED: typical RTH spread in index points
    "slippage_pts": 0.5,              # per fill, both directions
    "commission_per_lot_per_side": 0.0,
    "starting_equity": 100000.0,
    "risk_per_trade_pct": 0.5,
}

SPEC_PROVENANCE = {k: "PLACEHOLDER - must be replaced with broker contract spec"
                   for k in ("value_per_point_per_lot", "tick_size", "lot_step",
                             "min_lot", "max_lot", "spread_pts", "slippage_pts",
                             "commission_per_lot_per_side")}


# ===========================================================================
# 2. DATA INGESTION AND INTEGRITY
# ===========================================================================

class Bar(object):
    __slots__ = ("ts", "o", "h", "l", "c", "v")

    def __init__(self, ts, o, h, l, c, v=0.0):
        self.ts = ts
        self.o = o
        self.h = h
        self.l = l
        self.c = c
        self.v = v


def _parse_iso_to_epoch(text):
    t = text.strip().replace("T", " ").replace("Z", "")
    if "+" in t[10:]:
        t = t[:10] + t[10:].split("+")[0]
    date_part, _, time_part = t.partition(" ")
    y, m, d = [int(x) for x in date_part.split("-")]
    hh = mm = ss = 0
    if time_part:
        bits = time_part.split(":")
        hh = int(bits[0])
        mm = int(bits[1]) if len(bits) > 1 else 0
        ss = int(float(bits[2])) if len(bits) > 2 else 0
    return STUDIO._days_from_civil(y, m, d) * 86400 + hh * 3600 + mm * 60 + ss


def load_m1_csv(path, tz_offset_min=0):
    """Read a 1-minute OHLC CSV. Returns (bars, integrity_report)."""
    rows = []
    with open(path, "r") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            raise ValueError("empty CSV: %s" % path)
        cols = [c.strip().lower() for c in reader.fieldnames]
        reader.fieldnames = cols
        tcol = None
        for cand in ("timestamp", "epoch", "time", "datetime", "timestamp_utc",
                     "date_time", "open_time", "date"):
            if cand in cols:
                tcol = cand
                break
        if tcol is None:
            raise ValueError("no timestamp column in %s (found %s)" % (path, cols))
        dropped_incomplete = 0
        for row in reader:
            raw = (row[tcol] or "").strip()
            if not raw:
                continue
            # never ingest a forming bar if the file tells us it is one
            status = (row.get("bar_status") or "").strip().upper()
            if status and status != "COMPLETED":
                dropped_incomplete += 1
                continue
            try:
                num = float(raw)
                ts = int(num / 1000) if num > 1e11 else int(num)
            except ValueError:
                ts = _parse_iso_to_epoch(raw)
            ts -= tz_offset_min * 60
            rows.append(Bar(ts, float(row["open"]), float(row["high"]),
                            float(row["low"]), float(row["close"]),
                            float(row.get("volume") or 0.0)))

    rows.sort(key=lambda b: b.ts)
    report = {"rows_read": len(rows), "incomplete_bars_dropped": dropped_incomplete,
              "duplicates_identical": 0,
              "duplicates_conflicting": 0, "ohlc_violations": 0,
              "misaligned_to_minute": 0, "bars_kept": 0}
    clean = []
    for b in rows:
        if b.ts % 60 != 0:
            report["misaligned_to_minute"] += 1
        if not (b.l <= b.o <= b.h and b.l <= b.c <= b.h):
            report["ohlc_violations"] += 1
            continue
        if clean and clean[-1].ts == b.ts:
            prev = clean[-1]
            if (prev.o, prev.h, prev.l, prev.c) == (b.o, b.h, b.l, b.c):
                report["duplicates_identical"] += 1
            else:
                report["duplicates_conflicting"] += 1
            continue
        clean.append(b)
    report["bars_kept"] = len(clean)

    sessions = {}
    for b in clean:
        key, minute = ny_parts(b.ts)
        if 570 <= minute < 960:
            sessions.setdefault(key, 0)
            sessions[key] += 1
    report["rth_sessions"] = len(sessions)
    report["rth_bars"] = sum(sessions.values())
    report["sessions_below_300_bars"] = sum(1 for n in sessions.values() if n < 300)
    report["first_session"] = min(sessions) if sessions else None
    report["last_session"] = max(sessions) if sessions else None
    report["session_bar_counts"] = sessions
    return clean, report


# ===========================================================================
# 3. EXECUTION / COST / SIZING MODEL
# ===========================================================================

def _round_tick(price, tick):
    return round(round(price / tick) * tick, 10)


class Trade(object):
    def __init__(self):
        self.session = None
        self.side = 0
        self.reason_in = ""
        self.reason_out = ""
        self.ts_in = 0
        self.ts_out = 0
        self.ref_in = 0.0
        self.fill_in = 0.0
        self.ref_out = 0.0
        self.fill_out = 0.0
        self.stop = 0.0
        self.target = 0.0
        self.lots = 0.0
        self.risk_cash = 0.0
        self.pnl = 0.0
        self.r = 0.0
        self.minutes = 0
        self.ambiguous = False

    def as_row(self):
        return {
            "session": self.session, "side": "LONG" if self.side > 0 else "SHORT",
            "ts_in": self.ts_in, "ts_out": self.ts_out,
            "reason_in": self.reason_in, "reason_out": self.reason_out,
            "ref_in": round(self.ref_in, 2), "fill_in": round(self.fill_in, 2),
            "ref_out": round(self.ref_out, 2), "fill_out": round(self.fill_out, 2),
            "stop": round(self.stop, 2), "target": round(self.target, 2),
            "lots": self.lots, "risk_cash": round(self.risk_cash, 2),
            "pnl": round(self.pnl, 2), "r": round(self.r, 4),
            "minutes": self.minutes, "ambiguous": int(self.ambiguous),
        }


def simulate(bars, spec, engine_params):
    """Replay the engine over bars and apply the execution model.

    Returns a result dict with trades, per-session R, and diagnostics.
    """
    eng = US30RuleEngine(**engine_params)
    tick = spec["tick_size"]
    vpp = spec["value_per_point_per_lot"]
    basis = spec["price_basis"]
    buy_adj = spec["spread_pts"] if basis == "bid" else spec["spread_pts"] / 2.0
    sell_adj = 0.0 if basis == "bid" else spec["spread_pts"] / 2.0
    slip = spec["slippage_pts"]

    equity = spec["starting_equity"]
    trades = []
    open_trade = None
    skipped_min_size = 0
    clamped_max_size = 0
    minutes_in_pos = 0
    rth_minutes = 0
    equity_curve = [(None, equity)]

    for b in bars:
        key, minute = ny_parts(b.ts)
        if 570 <= minute < 960:
            rth_minutes += 1
        if open_trade is not None:
            minutes_in_pos += 1

        for it in eng.on_bar(b.ts, b.o, b.h, b.l, b.c):
            if it.kind in ("ENTER_LONG", "ENTER_SHORT"):
                side = 1 if it.kind == "ENTER_LONG" else -1
                fill = (it.price_ref + buy_adj + slip) if side > 0 else (it.price_ref - sell_adj - slip)
                fill = _round_tick(fill, tick)
                stop_dist = abs(fill - it.stop)
                if stop_dist <= 0:
                    continue
                risk_cash = equity * spec["risk_per_trade_pct"] / 100.0
                raw_lots = risk_cash / (stop_dist * vpp)
                lots = math.floor(raw_lots / spec["lot_step"]) * spec["lot_step"]
                lots = round(lots, 8)
                if lots > spec["max_lot"]:
                    lots = spec["max_lot"]
                    clamped_max_size += 1
                if lots < spec["min_lot"]:
                    skipped_min_size += 1
                    # the engine believes it is in a position; flatten its mirror
                    eng.pos_side = 0
                    eng.pos_stop = eng.pos_target = None
                    continue
                t = Trade()
                t.session = key
                t.side = side
                t.reason_in = it.reason
                t.ts_in = it.ts
                t.ref_in = it.price_ref
                t.fill_in = fill
                t.stop = it.stop
                t.target = it.target
                t.lots = lots
                t.risk_cash = stop_dist * vpp * lots
                open_trade = t

            elif it.kind == "EXIT":
                if open_trade is None:
                    continue
                t = open_trade
                fill = (it.price_ref - sell_adj - slip) if t.side > 0 else (it.price_ref + buy_adj + slip)
                t.fill_out = _round_tick(fill, tick)
                t.ref_out = it.price_ref
                t.ts_out = it.ts
                t.reason_out = it.reason
                t.ambiguous = it.reason == "stop_ambiguous"
                gross = (t.fill_out - t.fill_in) * t.side * vpp * t.lots
                commission = spec["commission_per_lot_per_side"] * t.lots * 2
                t.pnl = gross - commission
                t.r = t.pnl / t.risk_cash if t.risk_cash else 0.0
                t.minutes = max(1, (t.ts_out - t.ts_in) // 60)
                equity += t.pnl
                equity_curve.append((t.ts_out, equity))
                trades.append(t)
                open_trade = None

    return {
        "trades": trades,
        "equity_final": equity,
        "equity_curve": equity_curve,
        "skipped_min_size": skipped_min_size,
        "clamped_max_size": clamped_max_size,
        "minutes_in_position": minutes_in_pos,
        "rth_minutes": rth_minutes,
        "engine_stats": dict(eng.stats),
    }


# ===========================================================================
# 4. METRICS
# ===========================================================================

def _mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def _stdev(xs):
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def session_block_bootstrap(trades, iterations=2000, seed=20260929):
    """Resample whole sessions with replacement.

    Trades inside one session share the same regime and the same levels, so
    they are not independent. Blocking by session is the honest unit.
    """
    by_session = {}
    for t in trades:
        by_session.setdefault(t.session, []).append(t.r)
    blocks = [by_session[k] for k in sorted(by_session)]
    if len(blocks) < 2:
        return None
    rng = random.Random(seed)
    means = []
    n = len(blocks)
    for _ in range(iterations):
        pool = []
        for _ in range(n):
            pool.extend(blocks[rng.randrange(n)])
        if pool:
            means.append(_mean(pool))
    means.sort()
    lo = means[int(0.025 * len(means))]
    hi = means[int(0.975 * len(means)) - 1]
    return {"n_sessions": n, "ci95_low": lo, "ci95_high": hi,
            "bootstrap_mean": _mean(means), "iterations": iterations}


def metrics(result):
    trades = result["trades"]
    rs = [t.r for t in trades]
    n = len(rs)
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r <= 0]
    gross_win = sum(wins)
    gross_loss = -sum(losses)

    peak = 0.0
    cum = 0.0
    maxdd = 0.0
    for r in rs:
        cum += r
        peak = max(peak, cum)
        maxdd = max(maxdd, peak - cum)

    sorted_wins = sorted(wins, reverse=True)
    top1 = (sorted_wins[0] / gross_win) if gross_win > 0 and sorted_wins else 0.0
    top5 = (sum(sorted_wins[:5]) / gross_win) if gross_win > 0 and sorted_wins else 0.0

    sd = _stdev(rs)
    m = {
        "trades": n,
        "expectancy_r": _mean(rs),
        "stdev_r": sd,
        "stderr_r": sd / math.sqrt(n) if n > 1 else None,
        "total_r": sum(rs),
        "win_rate": (len(wins) / n) if n else 0.0,
        "avg_win_r": _mean(wins),
        "avg_loss_r": _mean(losses),
        "profit_factor": (gross_win / gross_loss) if gross_loss > 0 else None,
        "max_drawdown_r": maxdd,
        "exposure_pct": (100.0 * result["minutes_in_position"] / result["rth_minutes"])
                        if result["rth_minutes"] else 0.0,
        "sessions_traded": len(set(t.session for t in trades)),
        "top1_win_share": top1,
        "top5_win_share": top5,
        "ambiguous_exits": sum(1 for t in trades if t.ambiguous),
        "gap_exits": sum(1 for t in trades if t.reason_out == "data_gap"),
        "eod_exits": sum(1 for t in trades if t.reason_out == "flat_by_time"),
        "stop_exits": sum(1 for t in trades if t.reason_out.startswith("stop")),
        "target_exits": sum(1 for t in trades if t.reason_out == "target"),
        "skipped_min_size": result["skipped_min_size"],
        "clamped_max_size": result["clamped_max_size"],
        "equity_final": result["equity_final"],
    }
    boot = session_block_bootstrap(trades)
    m["bootstrap"] = boot
    if n:
        m["trades_per_session_traded"] = n / max(1, m["sessions_traded"])
    return m


def format_metrics(name, m, engine_stats=None):
    lines = ["", "=" * 74, name, "=" * 74]
    if m["trades"] == 0:
        lines.append("  NO TRADES. Nothing to report. Check the integrity report above:")
        lines.append("  the most common causes are too little history (the first session")
        lines.append("  can never trade) and sessions with fewer than min_prior_session_bars.")
    else:
        lines.append("  trades                 %d  (over %d sessions traded)"
                     % (m["trades"], m["sessions_traded"]))
        lines.append("  net expectancy         %+.4f R / trade" % m["expectancy_r"])
        if m["stderr_r"]:
            lines.append("  std dev / std error    %.3f R  /  %.4f R" % (m["stdev_r"], m["stderr_r"]))
        b = m["bootstrap"]
        if b:
            lines.append("  session-block 95%% CI   [%+.4f, %+.4f] R  (%d session blocks, %d resamples)"
                         % (b["ci95_low"], b["ci95_high"], b["n_sessions"], b["iterations"]))
        else:
            lines.append("  session-block 95% CI   n/a (fewer than 2 sessions with trades)")
        lines.append("  total R                %+.2f" % m["total_r"])
        lines.append("  win rate               %.1f%%   avg win %+.2fR   avg loss %+.2fR"
                     % (100 * m["win_rate"], m["avg_win_r"], m["avg_loss_r"]))
        pf = m["profit_factor"]
        lines.append("  profit factor          %s" % ("inf (no losers)" if pf is None else "%.3f" % pf))
        lines.append("  max drawdown           %.2f R" % m["max_drawdown_r"])
        lines.append("  exposure               %.2f%% of RTH minutes" % m["exposure_pct"])
        lines.append("  concentration          top1 %.1f%% / top5 %.1f%% of gross profit"
                     % (100 * m["top1_win_share"], 100 * m["top5_win_share"]))
        lines.append("  exits                  target %d | stop %d | EOD %d | gap %d | ambiguous %d"
                     % (m["target_exits"], m["stop_exits"], m["eod_exits"],
                        m["gap_exits"], m["ambiguous_exits"]))
        lines.append("  size rejections        below min lot %d | clamped to max lot %d"
                     % (m["skipped_min_size"], m["clamped_max_size"]))
    if engine_stats:
        lines.append("  engine                 sessions=%d rth_bars=%d gaps=%d conflicts_blocked=%d "
                     "stop_bounds_rejected=%d expired(L/S)=%d/%d"
                     % (engine_stats["sessions"], engine_stats["rth_bars"],
                        engine_stats["gaps"], engine_stats["blocked_conflict"],
                        engine_stats["rejected_stop_bounds"],
                        engine_stats["expired_long"], engine_stats["expired_short"]))
    return "\n".join(lines)


# ===========================================================================
# 5. BASELINE PARAMETERS AND THE PREDECLARED GRID
# ===========================================================================
# Declared BEFORE looking at any result. Nothing is added later; if a value
# outside this grid is ever tried it must be appended to the log with a note
# explaining why, so the true number of comparisons stays visible.

BASELINE = {
    "rth_start": "09:30", "rth_end": "16:00",
    "entry_cutoff": "15:30", "flat_by": "15:55",
    "min_prior_session_bars": 300, "incomplete_prior_policy": "skip",
    "sweep_min_pts": 1.0, "reclaim_buffer_pts": 1.0, "allow_same_bar_reclaim": True,
    "rejection_zone_pts": 15.0, "rejection_close_buffer_pts": 1.0,
    "confirm_buffer_pts": 1.0, "setup_expiry_bars": 8,
    "stop_buffer_pts": 5.0, "target_r": 2.0,
    "min_stop_pts": 5.0, "max_stop_pts": 150.0,
    "max_trades_per_session": 2, "max_gap_minutes": 3,
}

GRID = {
    "target_r": [1.5, 2.0, 3.0],
    "stop_buffer_pts": [3.0, 5.0, 10.0],
    "rejection_zone_pts": [10.0, 15.0, 25.0],
    "setup_expiry_bars": [4, 8],
}   # 3 * 3 * 3 * 2 = 54 configurations, all logged


def grid_configs():
    keys = sorted(GRID)
    out = [{}]
    for k in keys:
        out = [dict(base, **{k: v}) for base in out for v in GRID[k]]
    return [dict(BASELINE, **cfg) for cfg in out]


def split_bars(bars, dev=0.5, val=0.25):
    """Chronological split by SESSION, never by bar, never shuffled."""
    keys = sorted(set(ny_parts(b.ts)[0] for b in bars))
    n = len(keys)
    d_end = int(n * dev)
    v_end = int(n * (dev + val))
    dev_k = set(keys[:d_end])
    val_k = set(keys[d_end:v_end])
    test_k = set(keys[v_end:])
    out = {"dev": [], "val": [], "test": []}
    for b in bars:
        k = ny_parts(b.ts)[0]
        if k in dev_k:
            out["dev"].append(b)
        elif k in val_k:
            out["val"].append(b)
        else:
            out["test"].append(b)
    out["_keys"] = {"dev": sorted(dev_k), "val": sorted(val_k), "test": sorted(test_k)}
    return out


# ===========================================================================
# 6. SYNTHETIC FIXTURE  -  mechanics demonstration only, NOT a market
# ===========================================================================

def synthetic_sessions(n_sessions=12, seed=7, start_date=(2026, 3, 2), drift_scale=0.05):
    """Deterministic fake 1-minute US30-like bars.

    THIS IS NOT MARKET DATA. It exists so the plumbing (levels, state
    machines, fills, sizing, metrics, reporting) can be exercised end to end
    and reconciled by hand. Any performance number produced from it describes
    the generator, not the Dow.

    drift_scale=0.0 gives a driftless random walk, which is the correct
    negative control: a harness with lookahead would show positive zero-cost
    expectancy on it, and a correct one must not.
    """
    rng = random.Random(seed)
    bars = []
    day = STUDIO._days_from_civil(*start_date)
    price = 42000.0
    made = 0
    while made < n_sessions:
        wd = (day + 4) % 7
        if wd >= 5:
            day += 1
            continue
        base = day * 86400
        offset = -STUDIO.ny_utc_offset_seconds(base)
        open_ts = base + offset + 9 * 3600 + 30 * 60
        drift = rng.choice([-1, 1]) * rng.uniform(0.0, drift_scale)
        for i in range(390):
            ts = open_ts + i * 60
            shock = rng.gauss(0.0, 4.0) + drift
            o = price
            c = o + shock
            wick = abs(rng.gauss(0.0, 3.0))
            h = max(o, c) + wick
            l = min(o, c) - wick
            bars.append(Bar(ts, round(o, 2), round(h, 2), round(l, 2), round(c, 2), 1000.0))
            price = c
        made += 1
        day += 1
    return bars


# ===========================================================================
# 7. CLI
# ===========================================================================

def write_trades_csv(path, trades):
    if not trades:
        return
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(trades[0].as_row().keys()))
        w.writeheader()
        for t in trades:
            w.writerow(t.as_row())


def run_negative_control(spec, seeds=12, sessions=150):
    """Driftless random walk, zero cost: expectancy must NOT come out positive.

    A backtester that peeks at the future, executes on the signal bar, or
    resolves ambiguous bars optimistically will print a positive edge here.
    A correct one prints zero or slightly negative (our EOD truncation and
    pessimistic ambiguous-bar rule both cost a little).
    """
    s = dict(spec)
    s.update({"spread_pts": 0.0, "slippage_pts": 0.0,
              "commission_per_lot_per_side": 0.0})
    es, total = [], 0
    for seed in range(1, seeds + 1):
        bars = synthetic_sessions(sessions, seed=seed, drift_scale=0.0)
        m = metrics(simulate(bars, s, BASELINE))
        if m["trades"]:
            es.append(m["expectancy_r"])
            total += m["trades"]
    print("\n" + "=" * 74)
    print("NEGATIVE CONTROL: driftless random walk, zero cost")
    print("=" * 74)
    print("  %d seeds x %d sessions, %d trades" % (seeds, sessions, total))
    print("  mean expectancy        %+.4f R" % _mean(es))
    print("  stdev across seeds     %.4f R" % _stdev(es))
    print("  seeds positive         %d / %d" % (sum(1 for e in es if e > 0), len(es)))
    print("  per-seed               %s" % ", ".join("%+.3f" % e for e in es))
    verdict = "PASS" if _mean(es) <= 0 else "FAIL - the harness shows edge on noise"
    print("  verdict                %s" % verdict)
    return 0 if _mean(es) <= 0 else 1


def print_integrity(rep):
    print("-" * 74)
    print("DATA INTEGRITY")
    print("-" * 74)
    for k in ("rows_read", "incomplete_bars_dropped", "bars_kept",
              "duplicates_identical", "duplicates_conflicting",
              "ohlc_violations", "misaligned_to_minute", "rth_sessions", "rth_bars",
              "sessions_below_300_bars", "first_session", "last_session"):
        print("  %-26s %s" % (k, rep[k]))
    if rep["duplicates_conflicting"]:
        print("  WARNING: conflicting duplicate timestamps were DROPPED (first kept).")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", help="1-minute OHLC CSV")
    ap.add_argument("--tz-offset-min", type=int, default=0,
                    help="minutes to subtract to convert file clock to UTC")
    ap.add_argument("--spec", help="JSON file overriding the instrument spec")
    ap.add_argument("--mode", default="baseline",
                    choices=["baseline", "grid", "costs", "splits", "control"])
    ap.add_argument("--out", default=None, help="write trades / grid log here")
    ap.add_argument("--self-test", action="store_true",
                    help="run on SYNTHETIC bars (mechanics demo, not a market)")
    ap.add_argument("--sessions", type=int, default=40, help="synthetic session count")
    args = ap.parse_args(argv)

    spec = dict(DEFAULT_SPEC)
    if args.spec:
        with open(args.spec) as fh:
            spec.update(json.load(fh))
        print("instrument spec overridden from %s" % args.spec)
    else:
        print("!! USING PLACEHOLDER INSTRUMENT SPEC. value_per_point_per_lot=%s, "
              "spread=%.2f pts, slippage=%.2f pts. Replace via --spec before "
              "drawing any conclusion about money." %
              (spec["value_per_point_per_lot"], spec["spread_pts"], spec["slippage_pts"]))

    if args.mode == "control":
        return run_negative_control(spec)

    if args.self_test:
        bars = synthetic_sessions(args.sessions)
        print("\n*** SYNTHETIC DATA (%d sessions, %d bars) - mechanics demo only ***"
              % (args.sessions, len(bars)))
        rep = {"rows_read": len(bars), "incomplete_bars_dropped": 0,
               "bars_kept": len(bars), "duplicates_identical": 0,
               "duplicates_conflicting": 0, "ohlc_violations": 0, "misaligned_to_minute": 0,
               "rth_sessions": args.sessions, "rth_bars": len(bars),
               "sessions_below_300_bars": 0,
               "first_session": ny_parts(bars[0].ts)[0],
               "last_session": ny_parts(bars[-1].ts)[0]}
    elif args.csv:
        bars, rep = load_m1_csv(args.csv, args.tz_offset_min)
    else:
        ap.error("supply --csv PATH or --self-test")
        return 2

    print_integrity(rep)

    if args.mode == "baseline":
        res = simulate(bars, spec, BASELINE)
        print(format_metrics("BASELINE" + (" (SYNTHETIC)" if args.self_test else ""),
                             metrics(res), res["engine_stats"]))
        if args.out:
            write_trades_csv(args.out, res["trades"])
            print("\ntrades written to %s" % args.out)
        if res["trades"]:
            print("\nfirst 5 trades for hand reconciliation against the bars:")
            for t in res["trades"][:5]:
                print("  %s" % json.dumps(t.as_row()))

    elif args.mode == "splits":
        sp = split_bars(bars)
        for name in ("dev", "val", "test"):
            k = sp["_keys"][name]
            print("\n%s: %d sessions (%s .. %s)"
                  % (name, len(k), k[0] if k else "-", k[-1] if k else "-"))
            if name == "test":
                print("  TEST SPLIT DELIBERATELY NOT EVALUATED HERE.")
                continue
            res = simulate(sp[name], spec, BASELINE)
            print(format_metrics("BASELINE on %s" % name, metrics(res), res["engine_stats"]))

    elif args.mode == "grid":
        sp = split_bars(bars)
        cfgs = grid_configs()
        print("\npredeclared grid: %d configurations, all logged, evaluated on DEV only"
              % len(cfgs))
        rows = []
        for i, cfg in enumerate(cfgs):
            res = simulate(sp["dev"], spec, cfg)
            m = metrics(res)
            row = {"config_id": i,
                   "target_r": cfg["target_r"], "stop_buffer_pts": cfg["stop_buffer_pts"],
                   "rejection_zone_pts": cfg["rejection_zone_pts"],
                   "setup_expiry_bars": cfg["setup_expiry_bars"],
                   "trades": m["trades"], "expectancy_r": round(m["expectancy_r"], 4),
                   "total_r": round(m["total_r"], 3),
                   "win_rate": round(m["win_rate"], 4),
                   "profit_factor": (None if m["profit_factor"] is None
                                     else round(m["profit_factor"], 3)),
                   "max_dd_r": round(m["max_drawdown_r"], 3),
                   "ci_low": (None if not m["bootstrap"] else round(m["bootstrap"]["ci95_low"], 4)),
                   "ci_high": (None if not m["bootstrap"] else round(m["bootstrap"]["ci95_high"], 4))}
            rows.append(row)
            print("  cfg %2d  %s" % (i, json.dumps(row)))
        out = args.out or "grid_log.csv"
        with open(out, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print("\nfull grid log written to %s (every configuration, not just the best)" % out)
        usable = [r for r in rows if r["trades"] >= 30]
        if not usable:
            print("NO configuration reached 30 dev trades. Ranking is not supportable; "
                  "no selection is made.")
        else:
            usable.sort(key=lambda r: r["expectancy_r"], reverse=True)
            print("top dev configs by expectancy (NOT a recommendation until the "
                  "validation split and the neighbourhood check agree):")
            for r in usable[:5]:
                print("  %s" % json.dumps(r))

    elif args.mode == "costs":
        for mult, label in ((0.0, "zero cost (diagnostic only)"), (1.0, "baseline costs"),
                            (2.0, "2x spread+slippage"), (3.0, "3x spread+slippage")):
            s = dict(spec)
            s["spread_pts"] = spec["spread_pts"] * mult
            s["slippage_pts"] = spec["slippage_pts"] * mult
            res = simulate(bars, s, BASELINE)
            m = metrics(res)
            print("  %-28s trades=%4d  expectancy=%+.4fR  totalR=%+.2f  PF=%s"
                  % (label, m["trades"], m["expectancy_r"], m["total_r"],
                     "n/a" if m["profit_factor"] is None else "%.3f" % m["profit_factor"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
