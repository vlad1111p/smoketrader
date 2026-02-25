from __future__ import annotations

import pandas as pd


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """
    Average True Range (Wilder's smoothing).
    Returns a Series; first values are NaN until warmup.
    """
    high = high.astype("float64")
    low = low.astype("float64")
    close = close.astype("float64")

    prev_close = close.shift(1)

    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()

    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    return true_range.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
