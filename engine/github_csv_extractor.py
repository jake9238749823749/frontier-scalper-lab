"""
========================================================================================
GITHUB DATASET EXTRACTOR & PARSER
========================================================================================
Extracts and parses CSV table data fetched from public GitHub repositories into standard
OHLCV pandas DataFrames and saves them into data/real/ for backtesting.
"""

import os
import io
import re
import pandas as pd
import numpy as np

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "real")
os.makedirs(DATA_DIR, exist_ok=True)

class GitHubDataExtractor:
    @staticmethod
    def parse_markdown_table(table_text: str) -> pd.DataFrame:
        """
        Parses GitHub markdown table format:
        | Line | Date | Open | High | Low | Close | Volume | ... |
        """
        lines = table_text.strip().split("\n")
        records = []
        headers = []

        for line in lines:
            if not line.startswith("|"):
                continue
            cells = [c.strip() for c in line.split("|")[1:-1]]
            if not cells or "---" in cells[0]:
                continue
            
            # Check header
            if any(h in cells for h in ["Date", "date", "Open", "open", "Close", "close"]):
                headers = cells
                continue

            if headers and len(cells) == len(headers):
                records.append(cells)

        if not records or not headers:
            return pd.DataFrame()

        df = pd.DataFrame(records, columns=headers)
        
        # Clean column names
        df.columns = [c.strip().lower() for c in df.columns]
        
        # Find date col
        date_col = next((c for c in df.columns if "date" in c or "time" in c), None)
        if date_col:
            df["timestamp"] = pd.to_datetime(df[date_col], errors="coerce", utc=True)
            df = df.dropna(subset=["timestamp"])
            df = df.set_index("timestamp").sort_index()

        for c in ["open", "high", "low", "close", "volume"]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")

        req = [c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]
        return df[req].dropna()

    @staticmethod
    def save_real_dataset(symbol: str, df: pd.DataFrame) -> str:
        safe_sym = symbol.replace("^", "IDX_").replace("=", "_").replace("/", "_").replace("-", "_")
        filepath = os.path.join(DATA_DIR, f"{safe_sym}_real.parquet")
        df.to_parquet(filepath)
        print(f"[DATA] Saved real historical dataset for {symbol} ({len(df)} bars) to {filepath}")
        return filepath
