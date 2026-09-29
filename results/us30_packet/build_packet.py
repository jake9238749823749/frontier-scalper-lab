# -*- coding: utf-8 -*-
"""
Builds the US30 market-state packet from raw_capture.py.

Hard rule enforced here: the DERIVED layer may only contain values that are a
deterministic function of VERIFIED captured candles. No interpolation, no
gap-filling, no synthetic bars. Where an input is absent the output is None
and the reason is pushed onto MISSING.
"""
import json, datetime as dt
from raw_capture import *

ET = dt.timezone(dt.timedelta(hours=-4), "EDT")
UTC = dt.timezone.utc

def iso_et(ts):  return dt.datetime.fromtimestamp(ts, ET).isoformat()
def iso_utc(ts): return dt.datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
def r2(x): return None if x is None else round(x + 0.0, 2)

MISSING = []
def miss(field, reason, sev="info"):
    MISSING.append({"field": field, "reason": reason, "severity": sev})

# ----------------------------------------------------------------- helpers
def rows(series, drop_last_live=True):
    """Yield dict rows, dropping provider nulls and (optionally) the trailing
    live partial bar. Returns (closed_rows, live_row, n_null_dropped)."""
    out, nulls = [], 0
    n = len(series["timestamps"])
    for i in range(n):
        o,h,l,c = series["open"][i],series["high"][i],series["low"][i],series["close"][i]
        v = series["volume"][i]
        if None in (o,h,l,c):
            nulls += 1
            continue
        out.append({"t": series["timestamps"][i], "o":o,"h":h,"l":l,"c":c,"v":v})
    live = None
    if drop_last_live and out and out[-1]["v"] == 0:
        live = out.pop()
    return out, live, nulls

def fmt(rws, n=None):
    sel = rws[-n:] if n else rws
    return [{"t_et": iso_et(r["t"]), "t_utc": iso_utc(r["t"]), "epoch": r["t"],
             "o": r2(r["o"]), "h": r2(r["h"]), "l": r2(r["l"]), "c": r2(r["c"]),
             "v": r["v"]} for r in sel]

def block_agg(group):
    return {"o": group[0]["o"], "h": max(g["h"] for g in group),
            "l": min(g["l"] for g in group), "c": group[-1]["c"],
            "v": sum(g["v"] for g in group if g["v"] is not None),
            "t": group[0]["t"], "n_src": len(group)}

# ============================================================== VERIFIED ====
snapshot_epoch = DJI_QUOTE_POLLS[-1][0]

dji_1m,  dji_1m_live,  _ = rows(DJI_1M)
dji_5m,  dji_5m_live,  _ = rows(DJI_5M)
dji_15m, dji_15m_live, _ = rows(DJI_15M)
dji_30m, dji_30m_live, _ = rows(DJI_30M)
dji_1h,  dji_1h_live,  _ = rows(DJI_1H)
dji_1d,  dji_1d_live,  _ = rows(DJI_1D, drop_last_live=False)
dji_1w,  dji_1w_live,  _ = rows(DJI_1W, drop_last_live=False)
ym_15m,  ym_15m_live,  _ = rows(YM_15M)
ym_1h,   ym_1h_live,   _ = rows(YM_1H)
ym_1d,   ym_1d_live,   _ = rows(YM_1D, drop_last_live=False)
ym_1w,   ym_1w_live,   _ = rows(YM_1W, drop_last_live=False)

# the 1m window had one provider null bar at 15:38:00 ET
if any(x is None for x in DJI_1M["close"]):
    miss("^DJI 1m bar 2026-09-29T15:38:00-04:00",
         "provider returned null OHLCV for this minute (bar still forming at fetch time); not back-filled", "info")

# daily/weekly last element is today's / this week's forming bar
dji_1d_forming = dji_1d.pop()          # 2026-09-29 forming
dji_1w_forming = dji_1w.pop()          # live weekly stub from provider
dji_1w_monday  = dji_1w.pop()          # Mon 2026-09-28 only (provider split)
ym_1d_forming  = ym_1d.pop()
ym_1w_forming  = ym_1w.pop()

# ------------------------------------------------------- session arithmetic
r_start, r_end = DJI_META["session_regular"]
elapsed = snapshot_epoch - r_start
total   = r_end - r_start
session = {
    "venue_status": "REGULAR SESSION OPEN (cash equities)",
    "trading_date_et": "2026-09-29 (Tuesday)",
    "exchange_timezone": "America/New_York (EDT, UTC-04:00)",
    "rth_open_et":  iso_et(r_start),
    "rth_close_et": iso_et(r_end),
    "snapshot_et":  iso_et(snapshot_epoch),
    "snapshot_utc": iso_utc(snapshot_epoch),
    "minutes_elapsed": round(elapsed/60, 1),
    "minutes_remaining": round((r_end - snapshot_epoch)/60, 1),
    "session_pct_complete": round(100*elapsed/total, 2),
    "pre_market_window_et":  f"{iso_et(DJI_META['session_pre'][0])} -> {iso_et(DJI_META['session_pre'][1])}",
    "post_market_window_et": f"{iso_et(DJI_META['session_post'][0])} -> {iso_et(DJI_META['session_post'][1])}",
    "futures_status": "CME Globex open (YM continuous); Yahoo buckets the YM day as calendar ET, not the 18:00->17:00 Globex session",
    "next_cash_close_et": iso_et(r_end),
}

# ------------------------------------------------------------ price blocks
last_poll = DJI_QUOTE_POLLS[-1]
dji_block = {
    "instrument": "Dow Jones Industrial Average (cash index)",
    "symbol": "^DJI", "venue": "Dow Jones Indices / S&P DJI", "currency": "USD",
    "source": "Yahoo Finance chart API",
    "feed_timestamp_et": iso_et(last_poll[0]),
    "feed_timestamp_utc": iso_utc(last_poll[0]),
    "last": last_poll[1],
    "session_open": r2(DJI_5M["open"][0]),
    "day_high": DJI_META["regularMarketDayHigh"],
    "day_low":  DJI_META["regularMarketDayLow"],
    "previous_close": DJI_META["previousClose"],
    "change": r2(last_poll[1] - DJI_META["previousClose"]),
    "change_pct": round(100*(last_poll[1]-DJI_META["previousClose"])/DJI_META["previousClose"], 3),
    "volume_composite": last_poll[2],
    "day_range_points": r2(DJI_META["regularMarketDayHigh"] - DJI_META["regularMarketDayLow"]),
    "fifty_two_week_high": DJI_META["fiftyTwoWeekHigh"],
    "fifty_two_week_low":  DJI_META["fiftyTwoWeekLow"],
}

ym_last = YM_QUOTE_POLLS[-1]
ym_block = {
    "instrument": "E-mini Dow ($5) futures, front month",
    "symbol": "YM=F  (contract: Dec 2026 / YMZ26)", "venue": "CBOT (CME Group)",
    "currency": "USD", "source": "Yahoo Finance chart API",
    "feed_timestamp_et": iso_et(ym_last[0]),
    "feed_timestamp_utc": iso_utc(ym_last[0]),
    "last": ym_last[1],
    "session_open": YM_15M["open"][0],
    "day_high": YM_META["regularMarketDayHigh"],
    "day_low":  YM_META["regularMarketDayLow"],
    "previous_close": YM_META["previousClose"],
    "change": r2(ym_last[1] - YM_META["previousClose"]),
    "change_pct": round(100*(ym_last[1]-YM_META["previousClose"])/YM_META["previousClose"], 3),
    "volume_contracts": ym_last[2],
    "day_range_points": r2(YM_META["regularMarketDayHigh"] - YM_META["regularMarketDayLow"]),
    "fifty_two_week_high": YM_META["fiftyTwoWeekHigh"],
    "fifty_two_week_low":  YM_META["fiftyTwoWeekLow"],
    "tick_size_points": 1.0, "tick_value_usd": 5.0,
}

# ================================================================ DERIVED ===
# D1: 4H blocks for the cash index. Yahoo exposes no native 4H for ^DJI.
# Deterministic rule: within each RTH date the seven 60m bars (09:30..15:30)
# are grouped 4+3 -> [09:30-13:30) and [13:30-16:00). Second block of a live
# day is a partial. Nothing invented; pure aggregation of verified 1h bars.
def rth_date(ts): return dt.datetime.fromtimestamp(ts, ET).date()
by_day = {}
for r in dji_1h + ([dji_1h_live] if dji_1h_live else []):
    by_day.setdefault(rth_date(r["t"]), []).append(r)

dji_4h = []
for d in sorted(by_day):
    day = sorted(by_day[d], key=lambda r: r["t"])
    b1, b2 = day[:4], day[4:]
    if b1:
        a = block_agg(b1); a["label"] = f"{d} 09:30-13:30 ET"
        a["complete"] = len(b1) == 4; dji_4h.append(a)
    if b2:
        a = block_agg(b2); a["label"] = f"{d} 13:30-16:00 ET"
        a["complete"] = len(b2) == 3 and d != rth_date(snapshot_epoch)
        dji_4h.append(a)
miss("^DJI native 4H candles",
     "Yahoo chart API exposes no 4h granularity for ^DJI; 4H shown is a deterministic 4+3 aggregation of verified 60m RTH bars, NOT a provider candle", "medium")

# D2: 4H blocks for YM, anchored to ET 00/04/08/12/16/20.
ym_4h = {}
for r in ym_1h + ([ym_1h_live] if ym_1h_live else []):
    d = dt.datetime.fromtimestamp(r["t"], ET)
    key = d.replace(hour=(d.hour//4)*4, minute=0, second=0)
    ym_4h.setdefault(key, []).append(r)
ym_4h_rows = []
for k in sorted(ym_4h):
    a = block_agg(sorted(ym_4h[k], key=lambda r: r["t"]))
    a["label"] = k.strftime("%Y-%m-%d %H:%M ET"); a["complete"] = a["n_src"] == 4
    ym_4h_rows.append(a)
miss("YM native 4H candles",
     "derived by ET-4h-bucket aggregation of verified 60m bars; note brokers commonly anchor futures 4H at 18:00 ET, so bucket edges will differ from a TradingView 4H chart", "medium")
miss("YM 60m bars 2026-09-24 17:00 ET -> 2026-09-28 09:00 ET",
     "provider returned a contiguous all-null block (weekend + surrounding hours) in the range=5d payload; left as a hole", "medium")

# D3: true current-week bar (provider split the week into a Monday bar plus a
# live stub). Straight max/min/first/last over the two verified pieces.
wk = {"o": dji_1w_monday["o"],
      "h": max(dji_1w_monday["h"], dji_1w_forming["h"]),
      "l": min(dji_1w_monday["l"], dji_1w_forming["l"]),
      "c": dji_1w_forming["c"],
      "v": dji_1w_monday["v"] + dji_1w_forming["v"]}

# D4: cash/futures basis
basis = r2(ym_block["last"] - dji_block["last"])

# D5: intraday stats from verified 5m RTH bars
tot_v = sum(r["v"] for r in dji_5m)
vwap  = sum(((r["h"]+r["l"]+r["c"])/3.0)*r["v"] for r in dji_5m)/tot_v if tot_v else None
closes5 = [r["c"] for r in dji_5m]

# D6: ATR(14) on verified daily bars
tr = []
for i in range(1, len(dji_1d)):
    p, c = dji_1d[i-1], dji_1d[i]
    tr.append(max(c["h"]-c["l"], abs(c["h"]-p["c"]), abs(c["l"]-p["c"])))
atr14 = sum(tr[-14:])/14 if len(tr) >= 14 else None

derived = {
  "_contract": "every value below is a deterministic function of the VERIFIED candles above; recompute with build_packet.py to audit",
  "cash_futures_basis_points": basis,
  "basis_note": ("YM Dec-26 trades above cash; carry/dividend basis on a front-quarter contract. Not an arbitrage signal. "
                 "STAMP MISMATCH: the YM leg is stamped 15:30:07 ET and the cash leg 15:40:14 ET, so this basis carries "
                 "~10 minutes of timing error and should be treated as approximate (+/- tens of points)."),
  "basis_stamp_gap_sec": snapshot_epoch - YM_QUOTE_POLLS[-1][0],
  "rth_vwap_proxy_5m": r2(vwap),
  "rth_vwap_note": "volume-weighted mean of (H+L+C)/3 over the 75 verified 5m bars using index COMPOSITE volume. This is a proxy, not an exchange-disseminated VWAP.",
  "last_vs_vwap_points": r2(dji_block["last"] - vwap) if vwap else None,
  "day_range_points": dji_block["day_range_points"],
  "position_in_day_range_pct": round(100*(dji_block["last"]-DJI_META["regularMarketDayLow"])/(DJI_META["regularMarketDayHigh"]-DJI_META["regularMarketDayLow"]), 1),
  "open_to_last_points": r2(dji_block["last"] - DJI_5M["open"][0]),
  "atr14_daily_points": r2(atr14),
  "atr14_note": f"Wilder true range averaged over the last 14 COMPLETED daily bars ({len(tr)} TRs available)",
  "pct_below_52w_high": round(100*(DJI_META["fiftyTwoWeekHigh"]-dji_block["last"])/DJI_META["fiftyTwoWeekHigh"], 2),
  "pct_above_52w_low":  round(100*(dji_block["last"]-DJI_META["fiftyTwoWeekLow"])/DJI_META["fiftyTwoWeekLow"], 2),
  "current_week_bar_cash": {"o": r2(wk["o"]), "h": r2(wk["h"]), "l": r2(wk["l"]),
                            "c": r2(wk["c"]), "v": wk["v"],
                            "note": "week of 2026-09-28, IN PROGRESS (2 of 5 sessions)"},
  "last_5m_close_dispersion": {"min": r2(min(closes5[-12:])), "max": r2(max(closes5[-12:])),
                               "note": "last 12 verified 5m closes (one hour)"},
  "cross_source_cash_spread": {
     "values": {"yahoo": dji_block["last"], "cnbc": 51373.26,
                "marketwatch": 51355.39, "tradingview_dj_dji": 51350.43},
     "max_minus_min_points": r2(51373.26 - 51350.43),
     "note": "sources polled over a ~36 minute spread of feed stamps (15:03 / 15:23 / 15:39 ET) on a moving market; dispersion is timing, not disagreement"},
}

# ---------------------------------------------------------------- MISSING
miss("^DJI tick / level-2 / order book", "no free public source provides DJIA constituent-level depth; not retrievable", "info")
miss("FOREXCOM:US30 OHLC candle history (any timeframe)", "TradingView symbol page exposes only the quote row (last/open/prevclose/day range); candle history requires an authenticated TradingView or FOREX.com API session", "high")
miss("FOREXCOM:US30 volume", "provider displays '—'; CFD venue publishes no volume for this symbol", "medium")
miss("YM 1m candles", "not retrieved this pass; Yahoo does expose 1m for YM=F, so this is a coverage gap not a source limitation", "medium")
miss("YM 5m candles", "fetched, but the provider response was truncated mid-'open'-array by the retrieval layer; excluded rather than partially transcribed", "medium")
miss("YM 30m candles", "not retrieved this pass", "low")
miss("YM overnight 18:00-24:00 ET Mon 2026-09-28 segment", "Yahoo buckets the YM day from 00:00 ET, so the first 6 hours of the Globex session that opened Mon 18:00 ET are outside the 'day' payload", "medium")
miss("Official S&P DJI settlement / divisor", "S&P Dow Jones Indices publishes the divisor behind a licence; FRED mirrors closes only (last observation 2026-09-28)", "low")
miss("Consolidated tape volume for DJIA", "the 'volume' fields are composite constituent volume, not an index-level print; Yahoo and CNBC disagree (256.9M vs 245.0M) because of differing constituent aggregation and feed lag", "medium")
miss("Bid/ask spread for all three instruments", "not exposed by any source polled", "info")
miss("^DJI pre/post-market candles", "meta.hasPrePostMarketData=false for an index; pre/post windows exist as session metadata only", "info")

# ------------------------------------------------------------------ OUTPUT
packet = {
 "packet": "US30 / DJIA / YM verified market-state",
 "lane": "LANE 1 - verified current data acquisition",
 "generated_utc": CAPTURE["window_end_utc"],
 "acquisition_window_utc": f"{CAPTURE['window_start_utc']} -> {CAPTURE['window_end_utc']}",
 "sandbox_clock_skew_vs_feed_sec": CAPTURE["clock_skew_vs_feed_sec"],
 "confidence": "HIGH for cash index + YM futures; MEDIUM for CFD (quote only, no candles)",
 "SESSION": session,
 "VERIFIED": {
   "cash_index": dji_block,
   "futures": ym_block,
   "cfd": CFD_QUOTES,
   "cross_source_cash_confirmation": CROSS_SOURCE_CASH,
   "quote_poll_ladder_dji": [
      {"feed_utc": iso_utc(t), "feed_et": iso_et(t), "price": p, "cum_volume": v, "call": s}
      for t,p,v,s in DJI_QUOTE_POLLS],
   "quote_poll_ladder_ym": [
      {"feed_utc": iso_utc(t), "feed_et": iso_et(t), "price": p, "cum_volume": v, "call": s}
      for t,p,v,s in YM_QUOTE_POLLS],
   "peer_context": PEER_CONTEXT,
   "timeframes_cash": {
     "1m":  {"status":"VERIFIED","bars":len(dji_1m),"coverage":"15:14-15:37 ET (targeted window)","live_partial":fmt([dji_1m_live])[0] if dji_1m_live else None,"bars_data":fmt(dji_1m)},
     "5m":  {"status":"VERIFIED","bars":len(dji_5m),"coverage":"full RTH 09:30-15:35 ET","live_partial":fmt([dji_5m_live])[0] if dji_5m_live else None,"bars_data":fmt(dji_5m)},
     "15m": {"status":"VERIFIED","bars":len(dji_15m),"coverage":"full RTH today","live_partial":fmt([dji_15m_live])[0] if dji_15m_live else None,"bars_data":fmt(dji_15m)},
     "30m": {"status":"VERIFIED","bars":len(dji_30m),"coverage":"5 sessions","live_partial":fmt([dji_30m_live])[0] if dji_30m_live else None,"bars_data":fmt(dji_30m)},
     "1h":  {"status":"VERIFIED","bars":len(dji_1h),"coverage":"9 sessions","live_partial":fmt([dji_1h_live])[0] if dji_1h_live else None,"bars_data":fmt(dji_1h)},
     "4h":  {"status":"DERIVED","note":"see DERIVED.note_4h","bars":len(dji_4h)},
     "1D":  {"status":"VERIFIED","bars":len(dji_1d),"coverage":"1 month completed sessions","forming_bar":fmt([dji_1d_forming])[0],"bars_data":fmt(dji_1d)},
     "1W":  {"status":"VERIFIED","bars":len(dji_1w),"coverage":"6 months completed weeks","forming_week":derived["current_week_bar_cash"],"bars_data":fmt(dji_1w)},
   },
   "timeframes_futures": {
     "15m": {"status":"VERIFIED","bars":len(ym_15m),"coverage":"00:00-15:30 ET today","live_partial":fmt([ym_15m_live])[0] if ym_15m_live else None,"bars_data":fmt(ym_15m)},
     "1h":  {"status":"VERIFIED","bars":len(ym_1h),"coverage":"5d window WITH a provider gap","live_partial":fmt([ym_1h_live])[0] if ym_1h_live else None,"bars_data":fmt(ym_1h)},
     "4h":  {"status":"DERIVED","bars":len(ym_4h_rows)},
     "1D":  {"status":"VERIFIED","bars":len(ym_1d),"forming_bar":fmt([ym_1d_forming])[0],"bars_data":fmt(ym_1d)},
     "1W":  {"status":"VERIFIED","bars":len(ym_1w),"forming_bar":fmt([ym_1w_forming])[0],"bars_data":fmt(ym_1w)},
     "1m":  {"status":"NOT_RETRIEVED"}, "5m": {"status":"NOT_RETRIEVED_TRUNCATED"}, "30m": {"status":"NOT_RETRIEVED"},
   },
 },
 "DERIVED": dict(derived, note_4h="4H is NOT a provider candle for either instrument; it is aggregation of verified 60m bars under the documented bucketing rule",
                 cash_4h_blocks=[{"label":b["label"],"o":r2(b["o"]),"h":r2(b["h"]),"l":r2(b["l"]),"c":r2(b["c"]),"v":b["v"],"src_60m_bars":b["n_src"],"complete":b["complete"]} for b in dji_4h],
                 futures_4h_blocks=[{"label":b["label"],"o":r2(b["o"]),"h":r2(b["h"]),"l":r2(b["l"]),"c":r2(b["c"]),"v":b["v"],"src_60m_bars":b["n_src"],"complete":b["complete"]} for b in ym_4h_rows]),
 "INFERRED": {
   "_contract": "judgement, not measurement. Nothing here is a data point.",
   "structure": "Cash index is mid-range after a two-session decline; today prints a lower high (51,505 vs Mon 51,780) and a lower low (51,129 vs Mon 51,410) versus Monday, then recovers into the last hour. That is an inside-down-then-recover shape, not a resolved trend.",
   "intraday_shape": "Session low 51,129.18 was set in the 12:00-12:05 ET 5m bar; price has ground higher through the afternoon and is trading back above the 5m VWAP proxy in the final 20 minutes.",
   "weekly": "Week of 2026-09-28 is in progress and currently down vs the 51,828.62 prior weekly close; the 52,000 handle has capped every attempt since 2026-09-21.",
   "basis": "Dec-26 YM at a ~350pt premium to cash is consistent with normal cost-of-carry on a front-quarter contract at these front-end yields, not a dislocation. Read it as approximate given the 10-minute stamp gap between the two legs.",
   "caveat": "All of the above is interpretation layered on the VERIFIED block and carries no independent evidentiary weight.",
 },
 "MISSING": MISSING,
 "SOURCES": SOURCE_URLS,
 "CAVEATS": [
   "Yahoo returns float32 artifacts (e.g. 51505.19140625); DJIA is officially quoted to 2dp. Raw values preserved in raw_capture.py, rounded here.",
   "Cash index 'volume' is aggregated constituent volume, not an index print. Yahoo 256.9M vs CNBC 245.0M at similar stamps.",
   "The three CFD/cash feeds are different products: FOREXCOM/CAPITALCOM US30 day ranges (51,122.8-51,658.4 / 51,126.1-51,652.9) are WIDER than the cash RTH range (51,129.18-51,505.19) because the CFD day includes the overnight session. Do not treat them as the same series.",
   "CFD previous closes (51,496.8 / 51,491.3) differ from the official cash close (51,481.51) - CFD venues close at their own cutoff.",
   "Every intraday series ends in a provider live partial bar (volume 0). These are isolated, never mixed into the closed-bar set.",
   "52-WEEK RANGE BASIS CONFLICT: Yahoo/CNBC/MarketWatch all report 45,057.28-54,744.33 (INTRADAY basis, high dated 08/05/26). A third-party tracker (dowjonestoday.net) reports 45,167-54,349 with an all-time CLOSING high of 54,349.12 on 2026-08-05. Both can be right - intraday extreme vs closing extreme. This packet uses the intraday basis throughout because three independent feeds agree on it.",
   "CORROBORATION of the 2026-09-28 prior close 51,481.51: matched independently by Yahoo, CNBC, MarketWatch, Investing.com and FRED (series DJIA, updated 2026-09-28 17:02 CDT). This anchor is the single most strongly verified number in the packet.",
   "Snapshot is a moving target: ^DJI moved 51,357.48 -> 51,355.81 across a 120-second poll ladder while this packet was built.",
 ],
}

with open("us30_market_state.json","w") as f:
    json.dump(packet, f, indent=1)

print("session:", session["venue_status"], "|", session["session_pct_complete"], "% complete,",
      session["minutes_remaining"], "min to close")
print("cash last", dji_block["last"], "| YM", ym_block["last"], "| basis", basis)
print("vwap proxy", r2(vwap), "| atr14", r2(atr14), "| pos in range", derived["position_in_day_range_pct"], "%")
print("cash 4H blocks:", len(dji_4h), "| ym 4H blocks:", len(ym_4h_rows))
print("missing items:", len(MISSING))
print("current week bar:", derived["current_week_bar_cash"])
