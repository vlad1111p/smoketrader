from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Dict, Optional

import pandas as pd


class MinuteBarBuilder:
    """
    Converts streaming messages into 1-minute OHLCV bars.

    Calls `on_bar_close(symbol, bar_df)` when a minute closes.
    """

    def __init__(self, on_bar_close: Callable[[str, pd.DataFrame], None], debug_ticks: bool = True):
        self.on_bar_close = on_bar_close
        self.debug_ticks = debug_ticks
        self.current: Dict[str, Dict] = {}

    @staticmethod
    def _to_utc_minute(ts: datetime) -> datetime:
        ts = ts.astimezone(timezone.utc)
        return ts.replace(second=0, microsecond=0)

    @staticmethod
    def _parse_ts(message: dict) -> Optional[datetime]:
        t = message.get("time") or message.get("timestamp")
        if t is None:
            return None
        if isinstance(t, str):
            t = t.strip()
            try:
                t = int(t)
            except ValueError:
                try:
                    t = float(t)
                except ValueError:
                    return None

        if isinstance(t, (int, float)):
            if t > 10_000_000_000:
                t = t / 1000.0
            return datetime.fromtimestamp(t, tz=timezone.utc)

        if isinstance(t, datetime):
            return t if t.tzinfo else t.replace(tzinfo=timezone.utc)

        return None

    @staticmethod
    def _parse_symbol(message: dict) -> Optional[str]:
        return message.get("id") or message.get("symbol") or message.get("ticker")

    @staticmethod
    def _parse_price(message: dict) -> Optional[float]:
        for k in ("price", "last", "lastPrice", "regularMarketPrice"):
            v = message.get(k)
            if isinstance(v, (int, float)):
                return float(v)
        return None

    @staticmethod
    def _parse_volume(message: dict) -> float:
        for k in ("volume", "lastSize", "size"):
            v = message.get(k)
            if isinstance(v, (int, float)):
                return float(v)
        return 0.0

    def on_message(self, message: dict) -> None:
        if self.debug_ticks:
            print("TICK:", message)

        sym = self._parse_symbol(message)
        price = self._parse_price(message)
        ts = self._parse_ts(message)

        if not sym or price is None or ts is None:
            return

        minute = self._to_utc_minute(ts)
        vol = self._parse_volume(message)

        st = self.current.get(sym)
        if st is None:
            self.current[sym] = {
                "minute": minute,
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "volume": vol,
            }
            return

        if minute > st["minute"]:
            closed_minute = st["minute"]
            bar = pd.DataFrame(
                {
                    "Open": [st["open"]],
                    "High": [st["high"]],
                    "Low": [st["low"]],
                    "Close": [st["close"]],
                    "Volume": [st["volume"]],
                },
                index=pd.DatetimeIndex([closed_minute], tz=timezone.utc),
            )
            self.on_bar_close(sym, bar)

            self.current[sym] = {
                "minute": minute,
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "volume": vol,
            }
            return

        st["high"] = max(st["high"], price)
        st["low"] = min(st["low"], price)
        st["close"] = price
        st["volume"] += vol
