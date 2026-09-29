"""
Lane 7 — market-structure & liquidity event detectors.

Design rules (this is what makes an event "defensible"):
  * Every detector is a pure function of OHLC bars. No discretion, no redrawing.
  * Every returned event carries: bar index, exchange-local timestamp, the exact
    price level(s), the timeframe, and the source payload it came from.
  * Thresholds are explicit arguments and are printed with the results, so a
    reader can re-run with their own parameters and see what changes.
  * Nothing is emitted unless the bars support it. Detectors return empty lists
    rather than "best guesses".
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Literal, Optional

import numpy as np
import pandas as pd


# --------------------------------------------------------------------------
# primitives
# --------------------------------------------------------------------------
def true_range(df: pd.DataFrame) -> pd.Series:
    pc = df["close"].shift(1)
    return pd.concat(
        [df["high"] - df["low"], (df["high"] - pc).abs(), (df["low"] - pc).abs()],
        axis=1,
    ).max(axis=1)


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    return true_range(df).rolling(n, min_periods=max(2, n // 2)).mean()


def efficiency_ratio(close: pd.Series, n: int) -> pd.Series:
    """Kaufman ER: |net move| / sum|bar-to-bar move| over n bars. 1=trend, 0=chop."""
    net = (close - close.shift(n)).abs()
    gross = close.diff().abs().rolling(n).sum()
    return net / gross.replace(0, np.nan)


@dataclass
class Swing:
    kind: Literal["high", "low"]
    bar: int
    ts: pd.Timestamp
    price: float
    edge: bool = False

    def label(self) -> str:
        tag = "*" if self.edge else ""
        return f"{'SH' if self.kind == 'high' else 'SL'}@{self.ts:%H:%M}={self.price:.2f}{tag}"


def swings(df: pd.DataFrame, k: int = 3, include_edges: bool = True) -> list[Swing]:
    """
    Strict fractal pivots: the extreme must beat all k bars on BOTH sides.

    include_edges=True also admits pivots inside the first/last k bars, judged
    against however many bars actually exist on the short side. Those are marked
    `edge=True` because they are provisional (a later bar can still invalidate
    the right-hand side). A session high printed in the first k bars is a real,
    tradeable level, so silently dropping it would be the bigger error.
    """
    out: list[Swing] = []
    h, l = df["high"].to_numpy(), df["low"].to_numpy()
    n = len(df)
    lo_i, hi_i = (0, n) if include_edges else (k, n - k)
    for i in range(lo_i, hi_i):
        ls, rs = max(0, i - k), min(n, i + k + 1)
        left_h, right_h = h[ls:i], h[i + 1:rs]
        left_l, right_l = l[ls:i], l[i + 1:rs]
        edge = (i < k) or (i >= n - k)
        if (left_h.size == 0 or h[i] > left_h.max()) and (right_h.size == 0 or h[i] > right_h.max()):
            if left_h.size or right_h.size:
                out.append(Swing("high", i, df.index[i], float(h[i]), edge))
        if (left_l.size == 0 or l[i] < left_l.min()) and (right_l.size == 0 or l[i] < right_l.min()):
            if left_l.size or right_l.size:
                out.append(Swing("low", i, df.index[i], float(l[i]), edge))
    return sorted(out, key=lambda s: s.bar)


# --------------------------------------------------------------------------
# events
# --------------------------------------------------------------------------
@dataclass
class Event:
    kind: str
    tf: str
    source: str
    bar: int
    ts: pd.Timestamp
    detail: dict = field(default_factory=dict)

    def row(self) -> dict:
        d = {"kind": self.kind, "tf": self.tf, "bar": self.bar,
             "time": f"{self.ts:%H:%M}", "source": self.source}
        d.update({k: (round(v, 2) if isinstance(v, float) else v)
                  for k, v in self.detail.items()})
        return d


# ---- fair value gaps / imbalance -----------------------------------------
def detect_fvg(df: pd.DataFrame, tf: str, source: str, min_pts: float = 0.0) -> list[Event]:
    """
    Strict 3-bar imbalance (the only definition that is checkable from OHLC):
      bullish : low[i]  > high[i-2]   -> unfilled band (high[i-2], low[i])
      bearish : high[i] < low[i-2]    -> unfilled band (high[i], low[i-2])
    The middle bar i-1 is the displacement bar. Fill is measured by later bars
    trading back into the band.
    """
    ev: list[Event] = []
    hi, lo = df["high"].to_numpy(), df["low"].to_numpy()
    for i in range(2, len(df)):
        bull = lo[i] - hi[i - 2]
        bear = lo[i - 2] - hi[i]
        if bull > min_pts:
            top, bot, side = float(lo[i]), float(hi[i - 2]), "bullish"
        elif bear > min_pts:
            top, bot, side = float(lo[i - 2]), float(hi[i]), "bearish"
        else:
            continue

        size = top - bot
        after = df.iloc[i + 1:]
        if side == "bullish":
            deepest = after["low"].min() if len(after) else np.nan
            filled = 0.0 if np.isnan(deepest) else float(np.clip((top - deepest) / size, 0, 1))
        else:
            deepest = after["high"].max() if len(after) else np.nan
            filled = 0.0 if np.isnan(deepest) else float(np.clip((deepest - bot) / size, 0, 1))

        ev.append(Event(
            f"FVG_{side}", tf, source, i, df.index[i],
            {"gap_low": bot, "gap_high": top, "size_pts": size,
             "displacement_bar": f"{df.index[i-1]:%H:%M}",
             "pct_filled": round(filled * 100, 1),
             "status": "FILLED" if filled >= 0.999 else ("PARTIAL" if filled > 0 else "UNFILLED")},
        ))
    return ev


# ---- displacement ---------------------------------------------------------
def detect_displacement(df: pd.DataFrame, tf: str, source: str,
                        atr_n: int = 14, body_mult: float = 2.0,
                        max_bars: int = 3, min_er: float = 0.70) -> list[Event]:
    """
    A displacement leg = a short, one-directional, outsized expansion.

    Conditions (all must hold) for a run of L bars (1..max_bars) ending at i:
      1. |close[i] - open[i-L+1]| >= body_mult * ATR(atr_n) measured at i-L
      2. directional efficiency of the run >= min_er
         (net move / sum of absolute bar moves)
      3. the run contains a 3-bar FVG in the same direction
         -> this is what separates displacement from a wide but two-sided bar
    Only the longest qualifying run starting at a given bar is kept.
    """
    a = atr(df, atr_n)
    o, c = df["open"].to_numpy(), df["close"].to_numpy()
    fvgs = detect_fvg(df, tf, source)
    bull_fvg_bars = {e.bar for e in fvgs if e.kind == "FVG_bullish"}
    bear_fvg_bars = {e.bar for e in fvgs if e.kind == "FVG_bearish"}

    ev: list[Event] = []
    used: set[int] = set()
    for i in range(len(df) - 1, -1, -1):
        if i in used:
            continue
        for L in range(max_bars, 0, -1):
            s = i - L + 1
            if s < atr_n or s < 2:
                continue
            ref_atr = a.iloc[s - 1]
            if not np.isfinite(ref_atr) or ref_atr <= 0:
                continue
            net = c[i] - o[s]
            if abs(net) < body_mult * ref_atr:
                continue
            steps = np.abs(np.diff(np.concatenate([[o[s]], c[s:i + 1]])))
            gross = steps.sum()
            er = abs(net) / gross if gross > 0 else 0.0
            if er < min_er:
                continue
            up = net > 0
            span = set(range(s, i + 3))
            has_fvg = bool(span & (bull_fvg_bars if up else bear_fvg_bars))
            if not has_fvg:
                continue
            ev.append(Event(
                "displacement_up" if up else "displacement_down", tf, source, s, df.index[s],
                {"from_bar": f"{df.index[s]:%H:%M}", "to_bar": f"{df.index[i]:%H:%M}",
                 "bars": L, "open": float(o[s]), "close": float(c[i]),
                 "net_pts": float(net), "atr_ref": float(ref_atr),
                 "atr_mult": round(abs(net) / ref_atr, 2), "efficiency": round(er, 3)},
            ))
            used.update(range(s, i + 1))
            break
    return sorted(ev, key=lambda e: e.bar)


# ---- level interaction: sweep / failed break / reclaim --------------------
@dataclass
class Level:
    name: str
    price: float
    side: Literal["high", "low"]   # which side liquidity rests on
    origin: str                    # provenance string


def classify_level_interaction(df: pd.DataFrame, lvl: Level, tf: str, source: str,
                               tol: float = 0.0, confirm_bars: int = 6) -> list[Event]:
    """
    Episode-based classification of every contact with `lvl`.

    An EPISODE starts on the first bar that trades beyond the level and ends on
    the first bar that neither trades nor closes beyond it. Classifying whole
    episodes (rather than single bars) is what stops a shallow wick and the deep
    break that follows it from being collapsed into one misleading "sweep".

      SWEEP               no bar in the episode CLOSED beyond -> wick only.
      FAILED_BREAK        closed beyond, but the episode resolved back inside
                          within `confirm_bars`.
      BREAK_then_RECLAIM  closed beyond and stayed beyond longer than
                          `confirm_bars`, then price came back inside.
      BREAK_HOLD          closed beyond and is STILL beyond at the last bar
                          (unresolved / ongoing).

    Reported penetration is the episode MAXIMUM, and the reaction is measured
    from the episode extreme, not from the first bar.
    """
    ev: list[Event] = []
    hi, lo, cl = df["high"].to_numpy(), df["low"].to_numpy(), df["close"].to_numpy()
    n, p = len(df), lvl.price
    high_side = lvl.side == "high"

    def wick_beyond(i):  return (hi[i] > p + tol) if high_side else (lo[i] < p - tol)
    def close_beyond(i): return (cl[i] > p + tol) if high_side else (cl[i] < p - tol)

    i = 0
    while i < n:
        if not wick_beyond(i):
            i += 1
            continue
        j = i
        while j + 1 < n and (wick_beyond(j + 1) or close_beyond(j + 1)):
            j += 1

        seg = df.iloc[i:j + 1]
        n_close_beyond = sum(close_beyond(x) for x in range(i, j + 1))
        max_pen = float(seg["high"].max() - p) if high_side else float(p - seg["low"].min())
        extreme = float(seg["high"].max()) if high_side else float(seg["low"].min())
        unresolved = (j == n - 1) and close_beyond(j)
        ep_len = j - i + 1

        if n_close_beyond == 0:
            kind = "SWEEP"
        elif unresolved:
            kind = "BREAK_HOLD"
        elif ep_len <= confirm_bars:
            kind = "FAILED_BREAK"
        else:
            kind = "BREAK_then_RECLAIM"

        after = df.iloc[j + 1:min(j + 1 + confirm_bars, n)]
        if len(after):
            reaction = float(extreme - after["low"].min()) if high_side else float(after["high"].max() - extreme)
        else:
            reaction = float("nan")

        ev.append(Event(
            f"{kind}_{lvl.side}", tf, source, i, df.index[i],
            {"level": lvl.name, "level_price": p, "origin": lvl.origin,
             "from": f"{df.index[i]:%H:%M}", "to": f"{df.index[j]:%H:%M}", "bars": ep_len,
             "max_penetration_pts": max_pen, "episode_extreme": extreme,
             "bars_closed_beyond": int(n_close_beyond),
             f"reaction_next_{confirm_bars}b_pts": reaction},
        ))
        i = j + 1
    return ev


def untouched_levels(df: pd.DataFrame, levels: list[Level], tol: float = 0.0) -> list[Level]:
    """Levels the bar series never traded through — i.e. pools still resting."""
    out = []
    for lv in levels:
        hit = (df["high"] > lv.price + tol).any() if lv.side == "high" else (df["low"] < lv.price - tol).any()
        if not hit:
            out.append(lv)
    return out


def detect_reclaim(df: pd.DataFrame, lvl: Level, tf: str, source: str,
                   away_bars: int = 5, hold_bars: int = 5) -> list[Event]:
    """
    Reclaim / regain, in BOTH directions.

    `lvl.side == 'high'`  level acts as resistance: price must close BELOW it for
                          >= away_bars, then close back ABOVE and hold.
    `lvl.side == 'low'`   level acts as support: price must close ABOVE it for
                          >= away_bars... i.e. the reclaim is of LOST support:
                          close BELOW for >= away_bars, then close back ABOVE.

    In both cases the interesting event is "price spent real time on the wrong
    side of the level and then took it back", so the test is the same: a run of
    closes on the wrong side, then a qualifying close back.
    """
    ev: list[Event] = []
    cl = df["close"].to_numpy()
    p, n = lvl.price, len(df)
    wrong_side = cl < p          # 'wrong side' is below for both roles
    run = 0
    for i in range(n):
        if wrong_side[i]:
            run += 1
            continue
        if run >= away_bars:
            end = min(i + hold_bars, n)
            window = cl[i:end]
            held = bool((window >= p).all()) and (end - i) == hold_bars
            ev.append(Event(
                "RECLAIM_confirmed" if held else "RECLAIM_attempt_unconfirmed",
                tf, source, i, df.index[i],
                {"level": lvl.name, "level_price": p, "origin": lvl.origin,
                 "bars_below_before": run, "reclaim_close": float(cl[i]),
                 "closes_held_above": int((window >= p).sum()),
                 "hold_required": hold_bars,
                 "note": "insufficient bars remaining to confirm" if (n - i) < hold_bars else ""},
            ))
        run = 0
    return ev


# ---- consolidation / balance ---------------------------------------------
def detect_consolidation(df: pd.DataFrame, tf: str, source: str,
                         window: int = 12, er_max: float = 0.30,
                         range_atr_max: float = 3.0, atr_n: int = 14) -> list[Event]:
    """
    Balance area = a `window`-bar stretch that is both directionless and
    range-compressed:
        efficiency_ratio(window) <= er_max         (goes nowhere)
        (window high - window low) <= range_atr_max * ATR   (stays tight)
    Overlapping qualifying windows are merged into one region.
    """
    a = atr(df, atr_n)
    er = efficiency_ratio(df["close"], window)
    rng = df["high"].rolling(window).max() - df["low"].rolling(window).min()
    ok = (er <= er_max) & (rng <= range_atr_max * a) & er.notna() & a.notna()

    # collect raw qualifying spans, each expanded back over its lookback window
    spans: list[tuple[int, int]] = []
    idx = ok.to_numpy()
    i = 0
    while i < len(idx):
        if not idx[i]:
            i += 1
            continue
        j = i
        while j + 1 < len(idx) and idx[j + 1]:
            j += 1
        spans.append((max(0, i - window + 1), j))
        i = j + 1

    # merge overlapping / touching spans so a region is reported once
    merged: list[tuple[int, int]] = []
    for s, e in spans:
        if merged and s <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))

    ev: list[Event] = []
    for s, e in merged:
        seg = df.iloc[s:e + 1]
        ev.append(Event(
            "consolidation", tf, source, s, df.index[s],
            {"from_bar": f"{df.index[s]:%H:%M}", "to_bar": f"{df.index[e]:%H:%M}",
             "bars": e - s + 1, "hi": float(seg["high"].max()), "lo": float(seg["low"].min()),
             "height_pts": float(seg["high"].max() - seg["low"].min()),
             "height_atr": round(float((seg["high"].max() - seg["low"].min()) / a.iloc[s]), 2)
             if np.isfinite(a.iloc[s]) and a.iloc[s] > 0 else None,
             "min_er": round(float(er.iloc[s:e + 1].min()), 3),
             "max_er": round(float(er.iloc[s:e + 1].max()), 3)},
        ))
    return ev


# ---- market structure shift ----------------------------------------------
def structure_shifts(df: pd.DataFrame, tf: str, source: str, k: int = 3) -> list[Event]:
    """
    BOS  = close beyond the most recent confirmed swing in the trend direction.
    CHoCH= first close beyond the most recent opposing swing after a sequence
           of same-direction swings (the trend-direction flip).
    Swings are only usable k bars after they print — we respect that lag, so no
    look-ahead.
    """
    sw = [s for s in swings(df, k, include_edges=False)]
    ev: list[Event] = []
    cl = df["close"].to_numpy()
    last_dir: Optional[str] = None
    broken: set[int] = set()

    for i in range(len(df)):
        # a pivot at bar b is only *knowable* at bar b+k — enforce that lag
        usable = [s for s in sw if s.bar + k <= i and s.bar not in broken]
        hs = [s for s in usable if s.kind == "high"]
        ls = [s for s in usable if s.kind == "low"]

        if hs and cl[i] > hs[-1].price:
            ref = hs[-1]
            kind = "CHoCH_up" if last_dir == "down" else "BOS_up"
            ev.append(Event(kind, tf, source, i, df.index[i],
                            {"broken_swing": ref.label(), "swing_price": ref.price,
                             "close": float(cl[i]),
                             "swing_confirmed_at": f"{df.index[min(ref.bar + k, len(df)-1)]:%H:%M}"}))
            broken.add(ref.bar)
            last_dir = "up"
            continue

        if ls and cl[i] < ls[-1].price:
            ref = ls[-1]
            kind = "CHoCH_down" if last_dir == "up" else "BOS_down"
            ev.append(Event(kind, tf, source, i, df.index[i],
                            {"broken_swing": ref.label(), "swing_price": ref.price,
                             "close": float(cl[i]),
                             "swing_confirmed_at": f"{df.index[min(ref.bar + k, len(df)-1)]:%H:%M}"}))
            broken.add(ref.bar)
            last_dir = "down"

    return ev


def events_to_frame(ev: list[Event]) -> pd.DataFrame:
    if not ev:
        return pd.DataFrame()
    return pd.DataFrame([e.row() for e in ev])
