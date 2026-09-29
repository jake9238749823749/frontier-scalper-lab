# -*- coding: utf-8 -*-
"""Renders US30_MARKET_STATE.md from us30_market_state.json."""
import json

P = json.load(open("us30_market_state.json"))
V, D, I, S = P["VERIFIED"], P["DERIVED"], P["INFERRED"], P["SESSION"]
L = []
w = L.append

w(f"# US30 / DJIA / YM — Verified Market-State Packet")
w("")
w(f"**Acquisition window (UTC):** `{P['acquisition_window_utc']}`  ")
w(f"**Trading date:** {S['trading_date_et']} · **Exchange TZ:** {S['exchange_timezone']}  ")
w(f"**Confidence:** {P['confidence']}")
w("")
w("> Everything under VERIFIED is a value that appears verbatim in a cited provider payload.")
w("> Everything under DERIVED is a deterministic recomputation of those values (`build_packet.py` reproduces it).")
w("> Everything under INFERRED is judgement and carries no evidentiary weight. No candle or indicator was invented.")
w("")

# ---------------------------------------------------------------- session
w("## 1. Session status — VERIFIED")
w("")
w("| field | value |")
w("|---|---|")
for k in ["venue_status","rth_open_et","rth_close_et","snapshot_et","snapshot_utc",
          "minutes_elapsed","minutes_remaining","session_pct_complete",
          "pre_market_window_et","post_market_window_et","futures_status"]:
    w(f"| {k} | {S[k]} |")
w("")

# ------------------------------------------------------------ price state
w("## 2. Current price state — VERIFIED")
w("")
c, f = V["cash_index"], V["futures"]
fx, cap = V["cfd"]["FOREXCOM:US30"], V["cfd"]["CAPITALCOM:US30"]
w("| | **DJIA cash** `^DJI` | **E-mini Dow** `YM=F` (Dec 26) | **FOREXCOM:US30** (CFD) | **CAPITALCOM:US30** (CFD) |")
w("|---|---|---|---|---|")
w(f"| Venue | {c['venue']} | {f['venue']} | FOREX.com | Capital.com |")
w(f"| Feed stamp (ET) | {c['feed_timestamp_et'][11:19]} | {f['feed_timestamp_et'][11:19]} | 15:39 | 15:39 |")
w(f"| **Last** | **{c['last']:,.2f}** | **{f['last']:,.0f}** | **{fx['last']:,.1f}** | **{cap['last']:,.1f}** |")
w(f"| Change | {c['change']:+,.2f} ({c['change_pct']:+.3f}%) | {f['change']:+,.0f} ({f['change_pct']:+.3f}%) | {fx['change']:+,.1f} ({fx['change_pct']:+.2f}%) | {cap['change']:+,.1f} ({cap['change_pct']:+.2f}%) |")
w(f"| Open | {c['session_open']:,.2f} | {f['session_open']:,.0f} | {fx['open']:,.1f} | {cap['open']:,.1f} |")
w(f"| Day high | {c['day_high']:,.2f} | {f['day_high']:,.0f} | {fx['day_high']:,.1f} | {cap['day_high']:,.1f} |")
w(f"| Day low | {c['day_low']:,.2f} | {f['day_low']:,.0f} | {fx['day_low']:,.1f} | {cap['day_low']:,.1f} |")
w(f"| Prev close | {c['previous_close']:,.2f} | {f['previous_close']:,.0f} | {fx['previous_close']:,.1f} | {cap['previous_close']:,.1f} |")
w(f"| Day range (pts) | {c['day_range_points']:,.2f} | {f['day_range_points']:,.0f} | {fx['day_high']-fx['day_low']:,.1f} | {cap['day_high']-cap['day_low']:,.1f} |")
w(f"| Volume | {c['volume_composite']:,} (composite) | {f['volume_contracts']:,} contracts | — (not published) | {cap['volume']:,} ticks |")
w(f"| 52w high | {c['fifty_two_week_high']:,.2f} | {f['fifty_two_week_high']:,.0f} | — | — |")
w(f"| 52w low | {c['fifty_two_week_low']:,.2f} | {f['fifty_two_week_low']:,.0f} | — | — |")
w("")
w("**The CFD day range is wider than the cash range because the CFD day includes the overnight session. These are different products — do not merge the series.**")
w("")

# ------------------------------------------------- cross-source + ladder
w("### 2a. Independent cash-index confirmation — VERIFIED")
w("")
w("| source | symbol | feed stamp | last | day high | day low | prev close |")
w("|---|---|---|---|---|---|---|")
w(f"| Yahoo Finance | ^DJI | {c['feed_timestamp_et'][11:19]} ET | {c['last']:,.2f} | {c['day_high']:,.2f} | {c['day_low']:,.2f} | {c['previous_close']:,.2f} |")
for x in V["cross_source_cash_confirmation"]:
    x = dict(x, as_of_text=x["as_of_text"].replace("|", "/").strip())
    hi = f"{x['day_high']:,.2f}" if x['day_high'] else "—"
    lo = f"{x['day_low']:,.2f}" if x['day_low'] else "—"
    pc = f"{x['previous_close']:,.2f}" if x['previous_close'] else "—"
    w(f"| {x['source']} | {x['symbol']} | {x['as_of_text']} | {x['last']:,.2f} | {hi} | {lo} | {pc} |")
w("")
w(f"Spread across the four cash prints: **{D['cross_source_cash_spread']['max_minus_min_points']} pts** — "
  + D["cross_source_cash_spread"]["note"] + ".")
w("")
w("### 2b. Poll ladder (feed liveness proof) — VERIFIED")
w("")
w("Nine consecutive `^DJI` calls, each returning its own feed stamp and monotonically rising cumulative volume:")
w("")
w("| feed stamp (ET) | price | cumulative volume |")
w("|---|---|---|")
for p in V["quote_poll_ladder_dji"]:
    w(f"| {p['feed_et'][11:19]} | {p['price']:,.2f} | {p['cum_volume']:,} |")
w("")

# ------------------------------------------------------------ timeframes
w("## 3. Timeframe coverage")
w("")
w("| TF | DJIA cash | E-mini YM | notes |")
w("|---|---|---|---|")
tfc, tff = V["timeframes_cash"], V["timeframes_futures"]
def st(d, k):
    x = d.get(k)
    if not x: return "—"
    s = x["status"]
    return f"{s} ({x['bars']} bars)" if "bars" in x else s
w(f"| 1m | {st(tfc,'1m')} | {st(tff,'1m')} | cash window targeted to the last ~46 min |")
w(f"| 5m | {st(tfc,'5m')} | {st(tff,'5m')} | YM 5m response truncated by retrieval layer → excluded |")
w(f"| 15m | {st(tfc,'15m')} | {st(tff,'15m')} | both full today |")
w(f"| 30m | {st(tfc,'30m')} | {st(tff,'30m')} | cash covers 5 sessions |")
w(f"| 1h | {st(tfc,'1h')} | {st(tff,'1h')} | YM payload has a weekend null block |")
w(f"| **4h** | **DERIVED** ({len(D['cash_4h_blocks'])} blocks) | **DERIVED** ({len(D['futures_4h_blocks'])} blocks) | **no provider serves native 4h — aggregated from verified 60m** |")
w(f"| 1D | {st(tfc,'1D')} | {st(tff,'1D')} | + today's forming bar, flagged separately |")
w(f"| 1W | {st(tfc,'1W')} | {st(tff,'1W')} | + current week reconstructed |")
w("")

w("### 3a. Cash index — today's 15m RTH candles (VERIFIED, closed bars only)")
w("")
w("| time ET | open | high | low | close | volume |")
w("|---|---|---|---|---|---|")
for b in tfc["15m"]["bars_data"]:
    w(f"| {b['t_et'][11:16]} | {b['o']:,.2f} | {b['h']:,.2f} | {b['l']:,.2f} | {b['c']:,.2f} | {b['v']:,} |")
lp = tfc["15m"]["live_partial"]
if lp: w(f"| *{lp['t_et'][11:16]}* | *{lp['o']:,.2f}* | *{lp['h']:,.2f}* | *{lp['l']:,.2f}* | *{lp['c']:,.2f}* | *live partial* |")
w("")

w("### 3b. Cash index — last 10 completed daily bars (VERIFIED)")
w("")
w("| date | open | high | low | close | volume |")
w("|---|---|---|---|---|---|")
for b in tfc["1D"]["bars_data"][-10:]:
    w(f"| {b['t_et'][:10]} | {b['o']:,.2f} | {b['h']:,.2f} | {b['l']:,.2f} | {b['c']:,.2f} | {b['v']:,} |")
fb = tfc["1D"]["forming_bar"]
w(f"| *{fb['t_et'][:10]}* | *{fb['o']:,.2f}* | *{fb['h']:,.2f}* | *{fb['l']:,.2f}* | *{fb['c']:,.2f}* | *{fb['v']:,} — FORMING* |")
w("")

w("### 3c. Cash index — last 8 completed weekly bars (VERIFIED)")
w("")
w("| week of | open | high | low | close |")
w("|---|---|---|---|---|")
for b in tfc["1W"]["bars_data"][-8:]:
    w(f"| {b['t_et'][:10]} | {b['o']:,.2f} | {b['h']:,.2f} | {b['l']:,.2f} | {b['c']:,.2f} |")
cw = D["current_week_bar_cash"]
w(f"| *2026-09-28* | *{cw['o']:,.2f}* | *{cw['h']:,.2f}* | *{cw['l']:,.2f}* | *{cw['c']:,.2f}* — **IN PROGRESS (2/5 sessions), DERIVED** |")
w("")

w("### 3d. E-mini YM — last 8 completed daily bars (VERIFIED)")
w("")
w("| date | open | high | low | close | volume |")
w("|---|---|---|---|---|---|")
for b in tff["1D"]["bars_data"][-8:]:
    w(f"| {b['t_et'][:10]} | {b['o']:,.0f} | {b['h']:,.0f} | {b['l']:,.0f} | {b['c']:,.0f} | {b['v']:,} |")
yb = tff["1D"]["forming_bar"]
w(f"| *{yb['t_et'][:10]}* | *{yb['o']:,.0f}* | *{yb['h']:,.0f}* | *{yb['l']:,.0f}* | *{yb['c']:,.0f}* | *{yb['v']:,} — FORMING* |")
w("")

# --------------------------------------------------------------- derived
w("## 4. DERIVED — computed from verified candles, nothing invented")
w("")
w("| metric | value | basis |")
w("|---|---|---|")
w(f"| Cash/futures basis | {D['cash_futures_basis_points']:+,.2f} pts | YM last − cash last, {D['basis_stamp_gap_sec']}s stamp gap |")
w(f"| RTH VWAP proxy (5m) | {D['rth_vwap_proxy_5m']:,.2f} | 75 verified 5m bars, composite volume |")
w(f"| Last vs VWAP proxy | {D['last_vs_vwap_points']:+,.2f} pts | |")
w(f"| Position in day range | {D['position_in_day_range_pct']}% | (last − low) / (high − low) |")
w(f"| Open → last | {D['open_to_last_points']:+,.2f} pts | |")
w(f"| ATR(14) daily | {D['atr14_daily_points']:,.2f} pts | {D['atr14_note']} |")
w(f"| Below 52w high | {D['pct_below_52w_high']}% | |")
w(f"| Above 52w low | {D['pct_above_52w_low']}% | |")
w("")
w(f"*{D['rth_vwap_note']}*")
w("")
w(f"**4H caveat.** {D['note_4h']}. Cash rule: the seven 60m RTH bars per day grouped 4+3 → `09:30–13:30` and `13:30–16:00`. "
  "Futures rule: ET 4-hour buckets anchored 00/04/08/12/16/20 — note most brokers anchor futures 4H at 18:00 ET, so these edges will NOT line up with a TradingView 4H chart.")
w("")
w("Last 6 derived cash 4H blocks:")
w("")
w("| block | open | high | low | close | src 60m bars | complete |")
w("|---|---|---|---|---|---|---|")
for b in D["cash_4h_blocks"][-6:]:
    w(f"| {b['label']} | {b['o']:,.2f} | {b['h']:,.2f} | {b['l']:,.2f} | {b['c']:,.2f} | {b['src_60m_bars']} | {b['complete']} |")
w("")

# -------------------------------------------------------------- inferred
w("## 5. INFERRED — judgement, not measurement")
w("")
for k, v in I.items():
    if k.startswith("_"): continue
    w(f"- **{k}** — {v}")
w("")

# --------------------------------------------------------------- missing
w("## 6. Explicit missing-data list")
w("")
w("| severity | field | reason |")
w("|---|---|---|")
for m in sorted(P["MISSING"], key=lambda x: {"high":0,"medium":1,"low":2,"info":3}[x["severity"]]):
    w(f"| {m['severity'].upper()} | {m['field']} | {m['reason']} |")
w("")

# --------------------------------------------------------------- caveats
w("## 7. Data-quality caveats")
w("")
for x in P["CAVEATS"]: w(f"- {x}")
w("")

w("## 8. Source URLs")
w("")
for k, v in P["SOURCES"].items(): w(f"- `{k}` — {v}")
w("")
w("---")
w("")
w(f"Reproduce: `cd results/us30_packet && python3 build_packet.py && python3 render_report.py`. "
  f"`raw_capture.py` holds the verbatim provider values; this report and `us30_market_state.json` are generated from it.")

open("US30_MARKET_STATE.md","w").write("\n".join(L) + "\n")
print("wrote US30_MARKET_STATE.md", len(L), "lines")
