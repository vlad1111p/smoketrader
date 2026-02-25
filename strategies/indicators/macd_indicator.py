from __future__ import annotations

import pandas as pd


def macd(
        close: pd.Series,
        fast: int = 12,
        slow: int = 26,
        signal: int = 9,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """
    MACD indicator:
      macd_line   = EMA(fast) - EMA(slow)
      signal_line = EMA(signal) of macd_line
      hist        = macd_line - signal_line

    Returns: (macd_line, signal_line, hist)
    """
    close = close.astype("float64")

    ema_fast = close.ewm(span=fast, adjust=False, min_periods=fast).mean()
    ema_slow = close.ewm(span=slow, adjust=False, min_periods=slow).mean()

    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False, min_periods=signal).mean()

    hist = macd_line - signal_line
    return macd_line, signal_line, hist
