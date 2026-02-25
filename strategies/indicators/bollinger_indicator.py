from __future__ import annotations

import pandas as pd


def bollinger_bands(
        close: pd.Series,
        period: int = 20,
        stddev: float = 2.0,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """
    Bollinger Bands:
      mid   = SMA(period)
      upper = mid + stddev * rolling_std(period)
      lower = mid - stddev * rolling_std(period)

    Returns: (mid, upper, lower) as Series aligned to `close`.
    First values are NaN until warmup (period) is reached.
    """
    close = close.astype("float64")

    mid = close.rolling(window=period, min_periods=period).mean()
    sd = close.rolling(window=period, min_periods=period).std(ddof=0)

    upper = mid + stddev * sd
    lower = mid - stddev * sd

    return mid, upper, lower
