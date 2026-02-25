from __future__ import annotations

import pandas as pd


def ema(close: pd.Series, period: int) -> pd.Series:
    """
    Exponential Moving Average.
    Uses min_periods=period so early values are NaN until enough bars exist.
    """
    close = close.astype("float64")
    return close.ewm(span=period, adjust=False, min_periods=period).mean()
