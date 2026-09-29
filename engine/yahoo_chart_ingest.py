"""
Yahoo Finance /v8/finance/chart JSON -> tidy OHLCV frame.

Raw payloads are captured out-of-band (sandbox egress is allowlisted) and stored
verbatim under data/raw/. This module is the ONLY place raw JSON is interpreted,
so every downstream level is traceable to a specific file + bar index.

No synthetic fallback. If a payload is missing or malformed we raise.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Optional

import pandas as pd

RAW_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "raw")


@dataclass
class ChartPayload:
    symbol: str
    granularity: str
    tz: str
    gmtoffset: int
    regular_market_time: int
    meta: dict
    bars: pd.DataFrame
    source_file: str
    snapshots: pd.DataFrame = None

    @property
    def provenance(self) -> str:
        return (
            f"{self.symbol} {self.granularity} | Yahoo Finance /v8/finance/chart | "
            f"file={os.path.basename(self.source_file)} | bars={len(self.bars)}"
        )


def load_chart(filename: str, drop_partial: bool = True) -> ChartPayload:
    """Parse a captured chart payload into a bar frame indexed by exchange-local time."""
    path = filename if os.path.isabs(filename) else os.path.join(RAW_DIR, filename)
    if not os.path.exists(path):
        raise FileNotFoundError(f"raw payload not found: {path}")

    with open(path, "r") as fh:
        blob = json.load(fh)

    chart = blob["chart"]
    if chart.get("error"):
        raise ValueError(f"payload carries an error: {chart['error']}")

    res = chart["result"][0]
    meta = res["meta"]
    ts = res.get("timestamp")
    if not ts:
        raise ValueError(f"payload has no timestamp array: {path}")

    q = res["indicators"]["quote"][0]
    df = pd.DataFrame(
        {
            "open": q.get("open"),
            "high": q.get("high"),
            "low": q.get("low"),
            "close": q.get("close"),
            "volume": q.get("volume"),
        },
        index=pd.to_datetime(ts, unit="s", utc=True),
    )
    df.index.name = "ts_utc"

    tz = meta.get("exchangeTimezoneName", "America/New_York")
    df = df.tz_convert(tz)

    # Yahoo appends a synthetic "live snapshot" row whose epoch is not aligned to the
    # bar grid (it equals regularMarketTime). It is not a closed bar -> drop it.
    gran = meta.get("dataGranularity", "")
    step = _granularity_seconds(gran)
    if drop_partial and step:
        aligned = (pd.Series(ts).astype("int64") % step) == 0
        df = df[aligned.to_numpy()]

    before = len(df)
    df = df.dropna(subset=["open", "high", "low", "close"])
    dropped_nan = before - len(df)

    # Yahoo also emits an official closing/settlement print as a grid-aligned row at
    # the session boundary: open==high==low==close with volume 0. It is a snapshot,
    # not a traded minute, and it manufactures phantom gaps in 3-bar FVG logic.
    # Remove it from the bar series and surface the price separately.
    snapshots = pd.DataFrame()
    if drop_partial and step and len(df):
        flat = (df["open"] == df["high"]) & (df["high"] == df["low"]) & (df["low"] == df["close"])
        zero = df["volume"].fillna(0) == 0
        mask = flat & zero
        if mask.any():
            snapshots = df[mask].copy()
            df = df[~mask]

    df = df[~df.index.duplicated(keep="last")].sort_index()

    # OHLC sanity — do not silently repair, report instead.
    bad_hi = (df["high"] < df[["open", "close", "low"]].max(axis=1)).sum()
    bad_lo = (df["low"] > df[["open", "close", "high"]].min(axis=1)).sum()
    if bad_hi or bad_lo:
        raise ValueError(f"{path}: OHLC integrity violated (bad_high={bad_hi}, bad_low={bad_lo})")

    df.attrs["dropped_nan_rows"] = dropped_nan
    df.attrs["n_snapshot_rows"] = int(len(snapshots))
    df.attrs["symbol"] = meta.get("symbol")
    df.attrs["granularity"] = gran

    return ChartPayload(
        symbol=meta.get("symbol", "?"),
        granularity=gran,
        tz=tz,
        gmtoffset=meta.get("gmtoffset", 0),
        regular_market_time=meta.get("regularMarketTime", 0),
        meta=meta,
        bars=df,
        source_file=path,
        snapshots=snapshots,
    )


def load_and_stitch(filenames: list[str], drop_partial: bool = True) -> ChartPayload:
    """Concatenate several time-sliced payloads of the same symbol/granularity."""
    parts = [load_chart(f, drop_partial=drop_partial) for f in filenames]
    syms = {p.symbol for p in parts}
    grans = {p.granularity for p in parts}
    if len(syms) != 1 or len(grans) != 1:
        raise ValueError(f"cannot stitch heterogeneous payloads: symbols={syms} granularities={grans}")

    frame = pd.concat([p.bars for p in parts]).sort_index()
    frame = frame[~frame.index.duplicated(keep="last")]
    frame.index.name = "ts_utc"

    snaps = [p.snapshots for p in parts if p.snapshots is not None and len(p.snapshots)]
    snap = pd.concat(snaps).sort_index() if snaps else pd.DataFrame()
    if len(snap):
        snap = snap[~snap.index.duplicated(keep="last")]

    head = parts[0]
    return ChartPayload(
        symbol=head.symbol,
        granularity=head.granularity,
        tz=head.tz,
        gmtoffset=head.gmtoffset,
        regular_market_time=max(p.regular_market_time for p in parts),
        meta=head.meta,
        bars=frame,
        source_file=" + ".join(os.path.basename(p.source_file) for p in parts),
        snapshots=snap,
    )


def _granularity_seconds(gran: str) -> Optional[int]:
    table = {
        "1m": 60, "2m": 120, "5m": 300, "15m": 900, "30m": 1800,
        "60m": 3600, "1h": 3600, "90m": 5400, "1d": None,
    }
    return table.get(gran)


def bar_table(df: pd.DataFrame, fmt: str = "%H:%M") -> pd.DataFrame:
    """Human-checkable view: integer bar index + local clock + OHLC."""
    out = df.copy()
    out.insert(0, "bar", range(len(out)))
    out.insert(1, "clock", out.index.strftime(fmt))
    return out
