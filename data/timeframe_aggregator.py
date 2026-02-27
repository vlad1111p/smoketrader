# data/timeframe_aggregator.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

import pandas as pd


@dataclass
class _AggState:
    bucket_start: pd.Timestamp
    open: float
    high: float
    low: float
    close: float
    volume: float


class TimeframeAggregator:
    """
    Incrementally aggregates base bars (1m) into higher timeframes (e.g., 5m, 15m).
    """

    def __init__(self, timeframes: Tuple[str, ...] = ("5m", "15m")):
        self.timeframes = timeframes
        self._states: Dict[str, Dict[str, _AggState]] = {}

    @staticmethod
    def _tf_to_pandas_freq(tf: str) -> str:
        tf = tf.lower().strip()
        if tf.endswith("m"):
            return f"{int(tf[:-1])}min"
        raise ValueError(f"Unsupported timeframe: {tf}")

    @staticmethod
    def _bar_from_state(st: _AggState) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "Open": [st.open],
                "High": [st.high],
                "Low": [st.low],
                "Close": [st.close],
                "Volume": [st.volume],
            },
            index=pd.DatetimeIndex([st.bucket_start], tz=st.bucket_start.tz),
        )

    def on_1m_close(self, symbol: str, bar_1m: pd.DataFrame) -> List[Tuple[str, pd.DataFrame]]:
        """
        Input: a single-row 1m OHLCV DataFrame with tz-aware index.
        Output: list of (timeframe, closed_bar_df) for any timeframes that closed.
        """
        if bar_1m is None or bar_1m.empty:
            return []

        ts = pd.Timestamp(bar_1m.index[-1])
        if ts.tz is None:
            ts = ts.tz_localize("UTC")
        else:
            ts = ts.tz_convert("UTC")

        o = float(bar_1m["Open"].iloc[-1])
        h = float(bar_1m["High"].iloc[-1])
        l = float(bar_1m["Low"].iloc[-1])
        c = float(bar_1m["Close"].iloc[-1])
        v = float(bar_1m["Volume"].iloc[-1])

        sym_states = self._states.setdefault(symbol, {})
        out: List[Tuple[str, pd.DataFrame]] = []

        for tf in self.timeframes:
            freq = self._tf_to_pandas_freq(tf)
            bucket = ts.floor(freq)

            st = sym_states.get(tf)
            if st is None:
                sym_states[tf] = _AggState(bucket, o, h, l, c, v)
                continue

            if bucket < st.bucket_start:
                continue

            if bucket == st.bucket_start:
                st.high = max(st.high, h)
                st.low = min(st.low, l)
                st.close = c
                st.volume += v
                continue

            out.append((tf, self._bar_from_state(st)))
            sym_states[tf] = _AggState(bucket, o, h, l, c, v)

        return out
