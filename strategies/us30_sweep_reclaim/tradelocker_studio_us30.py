# -*- coding: utf-8 -*-
"""
US30 SWEEP-AND-RECLAIM / REJECTION-AND-CONFIRMATION  -  TradeLocker Studio bot
=============================================================================

PASTE-READY for TradeLocker Studio (desktop app). Studio strategies are Python
+ Backtrader: `import backtrader as bt`, `class X(bt.Strategy)`, and a `params`
DICT that also selects a sizer. See README.md for the source citations.

RUN CONFIGURATION (set in the Studio UI, not in this file):
    Instrument : your broker's US30 / DJ30 CFD
    Resolution : 1 minute            <-- REQUIRED. 15m bars are built in-code.
    Period     : your chosen date range
    Margin     : your chosen margin assigned to the bot

DESIGN CONTRACT
    * Signals are confirmed only on COMPLETED 15-minute bars, aggregated here
      from completed 1-minute bars. Nothing is ever decided on a forming bar.
    * Entry is the open of the first 1-minute bar at/after the confirming
      15-minute bar's close boundary. Same-bar execution is structurally
      impossible: the bucket is finalised before the current bar is consumed.
    * Levels are causal: the PREVIOUS completed New York regular session's
      high and low. No future information is referenced anywhere.
    * One position at a time, capped trades per session, hard flat-by time.
    * Everything below `US30RuleEngine` is pure Python with no Backtrader and
      no third-party imports, so the identical decision logic is replayed by
      research_harness.py offline. One engine, two runners.

WHAT THIS FILE DOES NOT DO (verify in Studio before trusting live):
    * It does not attach broker-native stop-loss / take-profit orders. Exits
      are emitted as market closes when a 1-minute bar trades through the
      level. At 1-minute resolution the worst-case protection latency is one
      bar. See ASSUMPTIONS.md item A-09.
    * It does not set instrument contract value; sizing correctness depends on
      `value_per_point_per_lot` matching your broker's US30 specification.
"""

import backtrader as bt


# =============================================================================
# 1. TIME  -  self-contained UTC <-> America/New_York with real DST handling
# =============================================================================
# Implemented without zoneinfo/pytz so behaviour is identical in Studio's
# runtime, in the offline harness, and in CI. Verified against zoneinfo in
# tests/test_us30_sweep_reclaim.py when that module is available.

_SEC_DAY = 86400


def _days_from_civil(y, m, d):
    """Days since 1970-01-01 (proleptic Gregorian). Hinnant's algorithm."""
    y -= m <= 2
    era = (y if y >= 0 else y - 399) // 400
    yoe = y - era * 400
    doy = (153 * (m + (-3 if m > 2 else 9)) + 2) // 5 + d - 1
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    return era * 146097 + doe - 719468


def _civil_from_days(z):
    z += 719468
    era = (z if z >= 0 else z - 146096) // 146097
    doe = z - era * 146097
    yoe = (doe - doe // 1460 + doe // 36524 - doe // 146096) // 365
    y = yoe + era * 400
    doy = doe - (365 * yoe + yoe // 4 - yoe // 100)
    mp = (5 * doy + 2) // 153
    d = doy - (153 * mp + 2) // 5 + 1
    m = mp + (3 if mp < 10 else -9)
    return (y + (m <= 2), m, d)


def _nth_sunday_day(year, month, nth):
    """Day-of-month of the nth Sunday (1-based) of year/month."""
    first = _days_from_civil(year, month, 1)
    weekday = (first + 4) % 7            # 1970-01-01 was a Thursday -> 0 == Sunday
    offset = (-weekday) % 7              # days forward to the first Sunday
    return 1 + offset + 7 * (nth - 1)


def ny_utc_offset_seconds(ts):
    """US Eastern UTC offset for a UTC epoch second (post-2007 DST rule).

    DST starts 2nd Sunday of March 02:00 EST (07:00 UTC) and ends 1st Sunday
    of November 02:00 EDT (06:00 UTC).
    """
    year = _civil_from_days(ts // _SEC_DAY)[0]
    start = _days_from_civil(year, 3, _nth_sunday_day(year, 3, 2)) * _SEC_DAY + 7 * 3600
    end = _days_from_civil(year, 11, _nth_sunday_day(year, 11, 1)) * _SEC_DAY + 6 * 3600
    return -4 * 3600 if start <= ts < end else -5 * 3600


def ny_parts(ts):
    """(date_key 'YYYY-MM-DD', minute_of_day) in New York wall-clock time."""
    local = ts + ny_utc_offset_seconds(ts)
    days, rem = divmod(local, _SEC_DAY)
    y, m, d = _civil_from_days(days)
    return ("%04d-%02d-%02d" % (y, m, d), rem // 60)


def hhmm(text):
    h, m = text.split(":")
    return int(h) * 60 + int(m)


# =============================================================================
# 2. RULE ENGINE  -  pure python, no framework, no I/O, fully deterministic
# =============================================================================

BUCKET_SECONDS = 900          # 15 minutes
BAR_SECONDS = 60              # 1 minute


class Intent(object):
    """A decision emitted by the engine. The runner turns it into an order."""

    __slots__ = ("kind", "reason", "price_ref", "stop", "target", "ts", "meta")

    def __init__(self, kind, ts, price_ref, reason="", stop=None, target=None, meta=None):
        self.kind = kind                # ENTER_LONG | ENTER_SHORT | EXIT
        self.ts = ts
        self.price_ref = price_ref      # price on the DATA series (pre-cost)
        self.reason = reason
        self.stop = stop
        self.target = target
        self.meta = meta or {}

    def __repr__(self):
        return "Intent(%s @%s %.2f %s)" % (self.kind, self.ts, self.price_ref, self.reason)


DEFAULTS = {
    # --- session (New York wall clock) ---
    "rth_start": "09:30",
    "rth_end": "16:00",
    "entry_cutoff": "15:30",       # no NEW entries at/after this time
    "flat_by": "15:55",            # force flat at/after this time
    # --- causal level construction ---
    "min_prior_session_bars": 300,  # else the day is skipped (fail-closed)
    # what to do when the previous session is incomplete (half day / outage):
    #   "skip"  = trade nothing the next day (literal "previous COMPLETE session")
    #   "carry" = keep the last complete session's levels, flagged as stale
    "incomplete_prior_policy": "skip",
    # --- bullish sweep & reclaim ---
    "sweep_min_pts": 1.0,          # min penetration below support to arm
    "reclaim_buffer_pts": 1.0,     # close must exceed support by this
    "allow_same_bar_reclaim": True,  # one bar may both sweep and reclaim
    # --- bearish rejection & confirmation ---
    "rejection_zone_pts": 15.0,    # high within [R - zone, inf) touches the zone
    "rejection_close_buffer_pts": 1.0,   # arming close must be below R - this
    "confirm_buffer_pts": 1.0,     # confirming close below rejection low - this
    # --- shared lifecycle ---
    "setup_expiry_bars": 8,        # 15m bars an armed setup stays valid
    "stop_buffer_pts": 5.0,
    "target_r": 2.0,
    "min_stop_pts": 5.0,
    "max_stop_pts": 150.0,
    "max_trades_per_session": 2,
    "max_gap_minutes": 3,          # larger hole => invalidate / force flat
}


class US30RuleEngine(object):
    """Consumes completed 1-minute bars, emits trade intents.

    The engine owns every *decision* (entry, stop, target, exit reason). It
    owns no money: fills, spread, slippage, commission and position size are
    the runner's job. That split is what lets Studio and the offline research
    harness share one rule implementation.
    """

    def __init__(self, **kw):
        cfg = dict(DEFAULTS)
        unknown = [k for k in kw if k not in cfg]
        if unknown:
            raise ValueError("unknown engine parameter(s): %s" % sorted(unknown))
        cfg.update(kw)
        self.cfg = cfg
        self.rth_start = hhmm(cfg["rth_start"])
        self.rth_end = hhmm(cfg["rth_end"])
        self.entry_cutoff = hhmm(cfg["entry_cutoff"])
        self.flat_by = hhmm(cfg["flat_by"])

        # session state
        self.session_key = None
        self.session_high = None
        self.session_low = None
        self.session_bars = 0
        self.prior_high = None
        self.prior_low = None
        self.prior_bars = 0
        self.prior_key = None
        self.trades_this_session = 0

        # 15m aggregation
        self.bucket_start = None
        self.bucket = None            # [o, h, l, c, n]
        self.bucket_index = 0         # count of completed buckets this session

        # setups
        self.long_setup = None        # {'sweep_low', 'expiry'}
        self.short_setup = None       # {'rej_high', 'confirm_level', 'expiry'}

        # position (decision-level mirror)
        self.pos_side = 0             # 0 flat, +1 long, -1 short
        self.pos_stop = None
        self.pos_target = None
        self.pos_entry_ref = None
        self.pos_entry_ts = None

        # diagnostics
        self.last_ts = None
        self.last_rth_ts = None
        self.stats = {
            "bars": 0, "rth_bars": 0, "sessions": 0, "skipped_no_prior": 0,
            "gaps": 0, "ambiguous_bars": 0, "expired_long": 0, "expired_short": 0,
            "invalidated_short": 0, "rejected_stop_bounds": 0, "blocked_conflict": 0,
            "incomplete_prior_sessions": 0, "stale_levels_sessions": 0,
        }
        if cfg["incomplete_prior_policy"] not in ("skip", "carry"):
            raise ValueError("incomplete_prior_policy must be 'skip' or 'carry'")

    # ---------------------------------------------------------------- helpers
    def _reset_session(self, key):
        """Roll the finishing session's high/low forward as the next day's levels.

        Three cases, all explicit:
          complete session   -> becomes the level source
          partial session    -> "skip": becomes the level source but fails the
                                completeness test, so the next day stands down;
                                "carry": ignored, last complete session is kept
                                and the next day is flagged as using stale levels
          no RTH bars at all -> ignored entirely (holiday, or a date that only
                                carried extended-hours bars); levels untouched
        """
        if self.session_key is not None and self.session_bars > 0:
            self.stats["sessions"] += 1
            complete = self.session_bars >= self.cfg["min_prior_session_bars"]
            if complete or self.cfg["incomplete_prior_policy"] == "skip":
                self.prior_high = self.session_high
                self.prior_low = self.session_low
                self.prior_bars = self.session_bars
                self.prior_key = self.session_key
            if not complete:
                self.stats["incomplete_prior_sessions"] += 1
                if self.cfg["incomplete_prior_policy"] == "carry":
                    self.stats["stale_levels_sessions"] += 1
        self.session_key = key
        self.last_rth_ts = None
        self.session_high = None
        self.session_low = None
        self.session_bars = 0
        self.trades_this_session = 0
        self.bucket_start = None
        self.bucket = None
        self.bucket_index = 0
        self.long_setup = None
        self.short_setup = None

    def _levels_ready(self):
        return (self.prior_high is not None and self.prior_low is not None
                and self.prior_bars >= self.cfg["min_prior_session_bars"])

    def _clear_setups(self):
        self.long_setup = None
        self.short_setup = None

    # ------------------------------------------------------------------- main
    def on_bar(self, ts, o, h, l, c):
        """Feed one COMPLETED 1-minute bar. `ts` is the bar's UTC open epoch."""
        out = []
        self.stats["bars"] += 1

        if self.last_ts is not None and ts <= self.last_ts:
            raise ValueError("non-monotonic bar at %s (previous %s)" % (ts, self.last_ts))

        key, minute = ny_parts(ts)
        if key != self.session_key:
            # a new calendar day: force flat before rolling state over
            if self.pos_side != 0:
                out.append(self._exit(ts, o, "session_rollover"))
            self._reset_session(key)

        in_rth = self.rth_start <= minute < self.rth_end
        if not in_rth:
            if self.pos_side != 0:
                out.append(self._exit(ts, o, "outside_rth"))
            self.last_ts = ts
            return out

        self.stats["rth_bars"] += 1

        # ---- data-gap handling: fail closed, never interpolate --------------
        gap = (self.last_rth_ts is not None
               and (ts - self.last_rth_ts) > self.cfg["max_gap_minutes"] * BAR_SECONDS)
        if gap:
            self.stats["gaps"] += 1
            self._clear_setups()
            self.bucket_start = None
            self.bucket = None
            if self.pos_side != 0:
                out.append(self._exit(ts, o, "data_gap"))

        # ---- finalise the previous 15m bucket, then decide ------------------
        if ts % BUCKET_SECONDS == 0 and self.bucket is not None:
            completed = tuple(self.bucket)
            self.bucket = None
            self.bucket_start = None
            entry = self._on_completed_bucket(ts, o, completed, minute)
            if entry is not None:
                out.append(entry)

        # ---- manage an open position on this bar ----------------------------
        if self.pos_side != 0:
            ex = self._check_exit(ts, o, h, l, c, minute)
            if ex is not None:
                out.append(ex)

        # ---- consume the current bar (never used by the decision above) -----
        self._accumulate(ts, o, h, l, c)
        self.last_ts = ts
        self.last_rth_ts = ts
        return out

    def _accumulate(self, ts, o, h, l, c):
        start = ts - (ts % BUCKET_SECONDS)
        if self.bucket is None or self.bucket_start != start:
            self.bucket_start = start
            self.bucket = [o, h, l, c, 1]
        else:
            b = self.bucket
            if h > b[1]:
                b[1] = h
            if l < b[2]:
                b[2] = l
            b[3] = c
            b[4] += 1
        self.session_high = h if self.session_high is None else max(self.session_high, h)
        self.session_low = l if self.session_low is None else min(self.session_low, l)
        self.session_bars += 1

    # ------------------------------------------------------- setup evaluation
    def _on_completed_bucket(self, ts, bar_open, bucket, minute):
        """Evaluate both state machines on a completed 15m bar.

        Returns an entry Intent priced at `bar_open` (the first executable
        price strictly after the bucket closed) or None.
        """
        bo, bh, bl, bc, n = bucket
        self.bucket_index += 1
        idx = self.bucket_index

        if not self._levels_ready():
            self.stats["skipped_no_prior"] += 1
            return None

        support = self.prior_low
        resistance = self.prior_high
        cfg = self.cfg

        # ---------------- bullish: sweep below support, then reclaim ---------
        if self.long_setup is not None and idx > self.long_setup["expiry"]:
            self.long_setup = None
            self.stats["expired_long"] += 1
        armed_long_now = False
        if self.long_setup is None:
            if bl <= support - cfg["sweep_min_pts"]:
                self.long_setup = {"sweep_low": bl, "expiry": idx + cfg["setup_expiry_bars"]}
                armed_long_now = True
        else:
            if bl < self.long_setup["sweep_low"]:
                self.long_setup["sweep_low"] = bl

        long_confirmed = (self.long_setup is not None
                          and bc > support + cfg["reclaim_buffer_pts"]
                          and (cfg["allow_same_bar_reclaim"] or not armed_long_now))

        # ---------------- bearish: reject the zone, then break down ----------
        if self.short_setup is not None and idx > self.short_setup["expiry"]:
            self.short_setup = None
            self.stats["expired_short"] += 1
        if self.short_setup is not None and bc > self.short_setup["rej_high"]:
            self.short_setup = None           # structure failed upward
            self.stats["invalidated_short"] += 1
        if self.short_setup is None:
            touched = bh >= resistance - cfg["rejection_zone_pts"]
            rejected = bc < resistance - cfg["rejection_close_buffer_pts"]
            if touched and rejected:
                self.short_setup = {"rej_high": bh,
                                    "confirm_level": bl - cfg["confirm_buffer_pts"],
                                    "expiry": idx + cfg["setup_expiry_bars"]}
                return None                   # arming bar cannot also confirm
        else:
            if bh > self.short_setup["rej_high"]:
                self.short_setup["rej_high"] = bh

        short_confirmed = (self.short_setup is not None
                           and bc < self.short_setup["confirm_level"])

        # ---------------- gating -------------------------------------------
        if long_confirmed and short_confirmed:
            self.stats["blocked_conflict"] += 1   # contradictory: take neither
            self._clear_setups()
            return None
        if not (long_confirmed or short_confirmed):
            return None
        if self.pos_side != 0:
            return None                           # one position at a time
        if minute >= self.entry_cutoff:
            return None
        if self.trades_this_session >= cfg["max_trades_per_session"]:
            return None

        if long_confirmed:
            stop = self.long_setup["sweep_low"] - cfg["stop_buffer_pts"]
            dist = bar_open - stop
            if not self._stop_ok(dist):
                self.long_setup = None
                return None
            target = bar_open + cfg["target_r"] * dist
            self.long_setup = None
            return self._enter(+1, ts, bar_open, stop, target, "sweep_reclaim",
                               {"support": support, "prior_session": self.prior_key,
                                "sweep_low": stop + cfg["stop_buffer_pts"]})

        stop = self.short_setup["rej_high"] + cfg["stop_buffer_pts"]
        dist = stop - bar_open
        if not self._stop_ok(dist):
            self.short_setup = None
            return None
        target = bar_open - cfg["target_r"] * dist
        self.short_setup = None
        return self._enter(-1, ts, bar_open, stop, target, "rejection_confirm",
                           {"resistance": resistance, "prior_session": self.prior_key,
                            "rej_high": stop - cfg["stop_buffer_pts"]})

    def _stop_ok(self, dist):
        if dist < self.cfg["min_stop_pts"] or dist > self.cfg["max_stop_pts"]:
            self.stats["rejected_stop_bounds"] += 1
            return False
        return True

    def _enter(self, side, ts, price, stop, target, reason, meta):
        self.pos_side = side
        self.pos_stop = stop
        self.pos_target = target
        self.pos_entry_ref = price
        self.pos_entry_ts = ts
        self.trades_this_session += 1
        return Intent("ENTER_LONG" if side > 0 else "ENTER_SHORT",
                      ts, price, reason, stop, target, meta)

    def _exit(self, ts, price, reason):
        intent = Intent("EXIT", ts, price, reason,
                        meta={"side": self.pos_side, "entry_ts": self.pos_entry_ts})
        self.pos_side = 0
        self.pos_stop = None
        self.pos_target = None
        self.pos_entry_ref = None
        self.pos_entry_ts = None
        return intent

    def _check_exit(self, ts, o, h, l, c, minute):
        """Stop / target / end-of-session, evaluated on the DATA series.

        Gap-through fills at the bar open. When one 1-minute bar contains both
        the stop and the target we cannot know the order without tick data, so
        we take the pessimistic branch (stop) and count the occurrence.
        """
        if minute >= self.flat_by:
            return self._exit(ts, o, "flat_by_time")

        if self.pos_side > 0:
            hit_stop = l <= self.pos_stop
            hit_target = h >= self.pos_target
            if hit_stop and hit_target:
                self.stats["ambiguous_bars"] += 1
                return self._exit(ts, min(o, self.pos_stop), "stop_ambiguous")
            if hit_stop:
                return self._exit(ts, min(o, self.pos_stop), "stop")
            if hit_target:
                return self._exit(ts, max(o, self.pos_target), "target")
            return None

        hit_stop = h >= self.pos_stop
        hit_target = l <= self.pos_target
        if hit_stop and hit_target:
            self.stats["ambiguous_bars"] += 1
            return self._exit(ts, max(o, self.pos_stop), "stop_ambiguous")
        if hit_stop:
            return self._exit(ts, max(o, self.pos_stop), "stop")
        if hit_target:
            return self._exit(ts, min(o, self.pos_target), "target")
        return None


# =============================================================================
# 3. TRADELOCKER STUDIO STRATEGY
# =============================================================================

class US30SweepReclaimStrategy(bt.Strategy):
    """Studio entry point. Run on 1-minute resolution."""

    params = {
        # ---- Studio sizer (see https://tradelocker.com/how-to/use-a-bot-sizer/)
        "sizer": "FixedLotSizer",
        "sizer_lots": 0.10,

        # ---- data/time contract -------------------------------------------
        # 0 when the feed's bar datetimes are UTC. If your Studio feed is
        # broker local time, set the offset in MINUTES (e.g. -300 for EST).
        # Verify once with the log line printed on the first bar.
        "data_utc_offset_minutes": 0,
        "verbose": True,

        # ---- session ------------------------------------------------------
        "rth_start": "09:30",
        "rth_end": "16:00",
        "entry_cutoff": "15:30",
        "flat_by": "15:55",
        "min_prior_session_bars": 300,
        "incomplete_prior_policy": "skip",

        # ---- signals ------------------------------------------------------
        "sweep_min_pts": 1.0,
        "reclaim_buffer_pts": 1.0,
        "allow_same_bar_reclaim": True,
        "rejection_zone_pts": 15.0,
        "rejection_close_buffer_pts": 1.0,
        "confirm_buffer_pts": 1.0,
        "setup_expiry_bars": 8,

        # ---- risk ---------------------------------------------------------
        "stop_buffer_pts": 5.0,
        "target_r": 2.0,
        "min_stop_pts": 5.0,
        "max_stop_pts": 150.0,
        "max_trades_per_session": 2,
        "max_gap_minutes": 3,
    }

    ENGINE_KEYS = ("rth_start", "rth_end", "entry_cutoff", "flat_by",
                   "min_prior_session_bars", "incomplete_prior_policy", "sweep_min_pts", "reclaim_buffer_pts",
                   "allow_same_bar_reclaim", "rejection_zone_pts", "rejection_close_buffer_pts",
                   "confirm_buffer_pts", "setup_expiry_bars", "stop_buffer_pts",
                   "target_r", "min_stop_pts", "max_stop_pts",
                   "max_trades_per_session", "max_gap_minutes")

    def __init__(self):
        self.engine = US30RuleEngine(**dict((k, getattr(self.p, k))
                                            for k in self.ENGINE_KEYS))
        self.order = None
        self._logged_first_bar = False

    # -- utilities ----------------------------------------------------------
    def log(self, msg):
        if self.p.verbose:
            print("[US30] %s" % msg)

    def _bar_epoch(self):
        """Bar open time as a UTC epoch second.

        Backtrader hands us a float ordinal; `num2date` yields a naive
        datetime in whatever timezone the feed used. We convert with the
        declared offset so the session logic is unambiguous.
        """
        dt = self.datas[0].datetime.datetime(0)
        epoch = (_days_from_civil(dt.year, dt.month, dt.day) * _SEC_DAY
                 + dt.hour * 3600 + dt.minute * 60 + dt.second)
        return epoch - int(self.p.data_utc_offset_minutes) * 60

    def notify_order(self, order):
        if order.status in (order.Submitted, order.Accepted):
            return
        if order.status in (order.Completed,):
            self.log("fill %s size=%s price=%.2f" %
                     ("BUY" if order.isbuy() else "SELL", order.size, order.executed.price))
        elif order.status in (order.Canceled, order.Margin, order.Rejected):
            self.log("order not filled: status=%s" % order.getstatusname())
        self.order = None

    # -- main loop ----------------------------------------------------------
    def next(self):
        d = self.datas[0]
        ts = self._bar_epoch()

        if not self._logged_first_bar:
            self._logged_first_bar = True
            key, minute = ny_parts(ts)
            self.log("first bar: feed_dt=%s -> assumed UTC epoch=%s -> NY %s %02d:%02d "
                     "(if this is not the true New York time, fix "
                     "data_utc_offset_minutes)" %
                     (d.datetime.datetime(0), ts, key, minute // 60, minute % 60))

        if self.order is not None:
            return                      # never stack orders on an unresolved one

        try:
            intents = self.engine.on_bar(ts, float(d.open[0]), float(d.high[0]),
                                         float(d.low[0]), float(d.close[0]))
        except ValueError as exc:
            self.log("engine rejected bar: %s" % exc)
            return

        for intent in intents:
            if intent.kind == "EXIT":
                if self.position:
                    self.order = self.close()
                    self.log("EXIT %s @~%.2f" % (intent.reason, intent.price_ref))
            elif intent.kind == "ENTER_LONG":
                if not self.position:
                    self.order = self.buy()
                    self.log("LONG %s entry~%.2f stop=%.2f target=%.2f"
                             % (intent.reason, intent.price_ref, intent.stop, intent.target))
            elif intent.kind == "ENTER_SHORT":
                if not self.position:
                    self.order = self.sell()
                    self.log("SHORT %s entry~%.2f stop=%.2f target=%.2f"
                             % (intent.reason, intent.price_ref, intent.stop, intent.target))

    def stop(self):
        s = self.engine.stats
        self.log("done: sessions=%d rth_bars=%d gaps=%d ambiguous_bars=%d "
                 "conflict_blocked=%d stop_bounds_rejected=%d"
                 % (s["sessions"], s["rth_bars"], s["gaps"], s["ambiguous_bars"],
                    s["blocked_conflict"], s["rejected_stop_bounds"]))


# =============================================================================
# END OF FILE - paste integrity check
# -----------------------------------------------------------------------------
# If the LAST line visible in the Studio editor is not the "# END OF FILE"
# banner above, your paste was TRUNCATED and Studio will report a syntax error
# such as "'(' was never closed". Re-copy the whole file and paste again.
#   expected total lines : 638
#   expected imports     : backtrader only
# =============================================================================
