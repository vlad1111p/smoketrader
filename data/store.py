from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass
class ParquetBarStore:
    """
    Stores OHLCV bars per (symbol, interval) in one parquet file.

    Index must be a DatetimeIndex (ideally tz-aware).
    """
    root: Path = Path("data/bars")

    def _path(self, symbol: str, interval: str) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        safe = symbol.replace("/", "_")
        return self.root / f"{safe}__{interval}.parquet"

    def load(self, symbol: str, interval: str) -> pd.DataFrame:
        p = self._path(symbol, interval)
        if not p.exists():
            return pd.DataFrame()

        df = pd.read_parquet(p)
        df = df[~df.index.duplicated(keep="last")].sort_index()
        return df

    def upsert(self, symbol: str, interval: str, new_df: pd.DataFrame) -> pd.DataFrame:
        if new_df is None or new_df.empty:
            return self.load(symbol, interval)

        old = self.load(symbol, interval)
        merged = pd.concat([old, new_df]).sort_index()
        merged = merged[~merged.index.duplicated(keep="last")]

        merged.to_parquet(self._path(symbol, interval))
        return merged
