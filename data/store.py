from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Union

import pandas as pd

Interval = Union[int, str]


@dataclass
class ParquetBarStore:
    """
    Stores OHLCV bars per (symbol, interval) in parquet files.
    """
    root: Path = field(default_factory=lambda: Path(__file__).resolve().parent / "bars")

    @staticmethod
    def _safe_symbol(symbol: str) -> str:
        return symbol.replace("/", "_").replace("\\", "_").replace(":", "_")

    @staticmethod
    def _interval_label(interval: Interval) -> str:
        """
        Canonical label used in both folder + filename.
        """
        if isinstance(interval, int):
            if interval <= 0:
                raise ValueError(f"interval must be > 0, got {interval}")
            return f"{interval}minute"

        s = str(interval).strip().lower()

        if s.isdigit():
            n = int(s)
            if n <= 0:
                raise ValueError(f"interval must be > 0, got {interval}")
            return f"{n}minute"

        if s.endswith("m") and s[:-1].isdigit():
            n = int(s[:-1])
            if n <= 0:
                raise ValueError(f"interval must be > 0, got {interval}")
            return f"{n}minute"

        if s.endswith("h") and s[:-1].isdigit():
            n = int(s[:-1])
            if n <= 0:
                raise ValueError(f"interval must be > 0, got {interval}")
            return f"{n}hour"

        if s.endswith("d") and s[:-1].isdigit():
            n = int(s[:-1])
            if n <= 0:
                raise ValueError(f"interval must be > 0, got {interval}")
            return f"{n}day"

        raise ValueError(f"Unsupported interval format: {interval!r}")

    def _dir_for_interval(self, interval: Interval) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        label = self._interval_label(interval)
        d = self.root / f"_{label}"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _path(self, symbol: str, interval: Interval) -> Path:
        safe = self._safe_symbol(symbol)
        label = self._interval_label(interval)
        return self._dir_for_interval(interval) / f"{safe}__{label}.parquet"

    def load(self, symbol: str, interval: Interval) -> pd.DataFrame:
        p = self._path(symbol, interval)
        if not p.exists():
            return pd.DataFrame()

        df = pd.read_parquet(p)
        df = df[~df.index.duplicated(keep="last")].sort_index()
        return df

    def upsert(self, symbol: str, interval: Interval, new_df: pd.DataFrame) -> pd.DataFrame:
        if new_df is None or new_df.empty:
            return self.load(symbol, interval)

        if not isinstance(new_df.index, pd.DatetimeIndex):
            new_df = new_df.copy()
            new_df.index = pd.to_datetime(new_df.index, utc=True)

        old = self.load(symbol, interval)
        merged = pd.concat([old, new_df]).sort_index()
        merged = merged[~merged.index.duplicated(keep="last")]

        merged.to_parquet(self._path(symbol, interval))
        return merged
