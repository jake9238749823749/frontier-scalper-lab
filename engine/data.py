import os
import pandas as pd
import numpy as np
import yfinance as yf
import requests
import io
from datetime import datetime, timezone
from typing import Optional, Union, Tuple, List

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

class DataLoader:
    """
    Robust multi-source market data loader with validation and caching.
    Supports Equities, FX, Commodities, Cryptos, Indices across various timeframes.
    """
    def __init__(self, cache_dir: str = CACHE_DIR):
        self.cache_dir = cache_dir
        os.makedirs(self.cache_dir, exist_ok=True)

    def fetch_yahoo(self, symbol: str, start: Optional[str] = None, end: Optional[str] = None, interval: str = "1d", force_refresh: bool = False) -> pd.DataFrame:
        """
        Fetch OHLCV data from Yahoo Finance.
        Supported intervals: 1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo.
        """
        cache_filename = f"{symbol.replace('^', 'IDX_').replace('=', '_').replace('/', '_')}_{interval}_{start or 'all'}_{end or 'latest'}.parquet"
        cache_path = os.path.join(self.cache_dir, cache_filename)

        if not force_refresh and os.path.exists(cache_path):
            df = pd.read_parquet(cache_path)
            return self._validate_and_clean(df, symbol)

        ticker = yf.Ticker(symbol)
        df = ticker.history(start=start, end=end, interval=interval, auto_adjust=False)
        if df.empty:
            # Fallback without date limits if intraday
            df = ticker.history(period="max", interval=interval, auto_adjust=False)

        if df.empty:
            raise ValueError(f"No data returned for symbol '{symbol}' from Yahoo Finance (interval={interval}).")

        # Standardize column names
        df = df.rename(columns={
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Adj Close": "adj_close",
            "Volume": "volume"
        })

        if "adj_close" not in df.columns and "close" in df.columns:
            df["adj_close"] = df["close"]

        cols = [c for c in ["open", "high", "low", "close", "adj_close", "volume"] if c in df.columns]
        df = df[cols]
        df = self._validate_and_clean(df, symbol)

        try:
            df.to_parquet(cache_path)
        except Exception:
            pass

        return df

    def fetch_binance_public(self, symbol: str = "BTCUSDT", interval: str = "1h", limit: int = 1000) -> pd.DataFrame:
        """
        Fetch crypto klines directly from public Binance REST endpoint (no API key required).
        """
        url = "https://api.binance.com/api/v3/klines"
        params = {"symbol": symbol.upper(), "interval": interval, "limit": limit}
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        cols = ["open_time", "open", "high", "low", "close", "volume", "close_time",
                "quote_asset_volume", "number_of_trades", "taker_buy_base", "taker_buy_quote", "ignore"]
        df = pd.DataFrame(data, columns=cols)
        df["timestamp"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
        df.set_index("timestamp", inplace=True)

        for c in ["open", "high", "low", "close", "volume"]:
            df[c] = df[c].astype(float)

        df["adj_close"] = df["close"]
        return self._validate_and_clean(df[["open", "high", "low", "close", "adj_close", "volume"]], symbol)

    def load_custom_csv(self, filepath: str, datetime_col: str = "Date", ohlcv_cols: Optional[dict] = None) -> pd.DataFrame:
        """
        Load custom CSV file and conform to standard OHLCV format.
        """
        df = pd.read_csv(filepath)
        if datetime_col in df.columns:
            df["timestamp"] = pd.to_datetime(df[datetime_col], utc=True)
            df.set_index("timestamp", inplace=True)
        else:
            df.index = pd.to_datetime(df.index, utc=True)

        if ohlcv_cols:
            df = df.rename(columns=ohlcv_cols)
        else:
            df.columns = [c.strip().lower() for c in df.columns]

        if "adj_close" not in df.columns and "close" in df.columns:
            df["adj_close"] = df["close"]

        req_cols = ["open", "high", "low", "close", "adj_close", "volume"]
        existing = [c for c in req_cols if c in df.columns]
        return self._validate_and_clean(df[existing], filepath)

    def _validate_and_clean(self, df: pd.DataFrame, source_id: str) -> pd.DataFrame:
        """
        Validate OHLC relationships, check for non-negativity, deduplicate timestamps, and sort.
        """
        if df.empty:
            raise ValueError(f"Market data for {source_id} is empty.")

        # Sort index
        df = df.sort_index()
        # Remove duplicate index timestamps
        df = df[~df.index.duplicated(keep="last")]

        # Ensure numeric
        for col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        # Drop rows where critical price columns are NaN
        df = df.dropna(subset=["open", "high", "low", "close"])

        # Check OHLC anomalies
        invalid_high = df["high"] < df[["open", "low", "close"]].max(axis=1)
        invalid_low = df["low"] > df[["open", "high", "close"]].min(axis=1)

        if invalid_high.any():
            # Fix anomalies conservatively
            df.loc[invalid_high, "high"] = df.loc[invalid_high, ["open", "close"]].max(axis=1)
        if invalid_low.any():
            df.loc[invalid_low, "low"] = df.loc[invalid_low, ["open", "close"]].min(axis=1)

        # Check positive prices
        if (df[["open", "high", "low", "close"]] <= 0).any().any():
            df = df[(df["open"] > 0) & (df["high"] > 0) & (df["low"] > 0) & (df["close"] > 0)]

        return df
