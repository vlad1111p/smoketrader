from __future__ import annotations

from datetime import datetime, timezone, timedelta
from threading import Lock
from typing import Callable, Dict, Optional

import pandas as pd


def _init_state(minute: datetime, price: float, vol: float, had_tick: bool) -> Dict:
    return {
        "minute": minute,
        "open": price,
        "high": price,
        "low": price,
        "close": price,
        "volume": vol,
        "had_tick": had_tick,
    }


class MinuteBarBuilder:
    """
    Converts streaming messages into 1-minute OHLCV bars.

    Calls `on_bar_close(symbol, bar_df)` when a minute closes.

    Important:
    - `on_message()` updates bars from ticks.
    - `on_timer()` force-closes bars on time boundaries, even if no tick arrives.
    """

    def __init__(
            self,
            on_bar_close: Callable[[str, pd.DataFrame], None],
            emit_empty_minutes: bool = True,
            close_grace_seconds: float = 2.0,
    ):
        self.on_bar_close = on_bar_close
        self.emit_empty_minutes = emit_empty_minutes
        self.close_grace_seconds = float(close_grace_seconds)

        # per-symbol state
        self.current: Dict[str, Dict] = {}
        self._lock = Lock()

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
            # ms -> s
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

    def _emit_close(self, sym: str, st: Dict) -> None:
        """
        Emit current state's minute bar (if allowed), using the state's stored OHLCV.
        """
        if (not st.get("had_tick", True)) and (not self.emit_empty_minutes):
            return

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

    def _advance_to(self, sym: str, target_minute: datetime) -> None:
        """
        Force-close and advance symbol state up to target_minute (exclusive),
        creating empty minutes if emit_empty_minutes=True.
        """
        st = self.current.get(sym)
        if st is None:
            return

        while st["minute"] < target_minute:
            prev_close = st["close"]
            self._emit_close(sym, st)

            next_minute = st["minute"] + timedelta(minutes=1)
            # create the next minute as "empty" (flat price, 0 volume) until a tick arrives
            st = _init_state(next_minute, prev_close, 0.0, had_tick=False)
            self.current[sym] = st

    def on_timer(self, now_utc: Optional[datetime] = None) -> None:
        """
        Call periodically (e.g. every 0.5s) to close minutes on time boundaries.

        Uses a grace window to reduce the chance of closing a minute before late ticks arrive.
        """
        if now_utc is None:
            now_utc = datetime.now(timezone.utc)
        else:
            now_utc = now_utc.astimezone(timezone.utc)

        cutoff = now_utc - timedelta(seconds=self.close_grace_seconds)
        cutoff_minute = self._to_utc_minute(cutoff)

        with self._lock:
            for sym, st in list(self.current.items()):
                # if state is older than cutoff minute, advance it
                if st["minute"] < cutoff_minute:
                    self._advance_to(sym, cutoff_minute)

    def on_message(self, message: dict) -> None:
        sym = self._parse_symbol(message)
        price = self._parse_price(message)
        ts = self._parse_ts(message)

        if not sym or price is None or ts is None:
            return

        minute = self._to_utc_minute(ts)
        vol = self._parse_volume(message)

        with self._lock:
            st = self.current.get(sym)
            if st is None:
                self.current[sym] = _init_state(minute, price, vol, had_tick=True)
                return

            # Late tick (older minute) after we've moved on (timer or other ticks)
            if minute < st["minute"]:
                # simplest policy: ignore. If you want to support late ticks, we can extend with a small "revision window".
                return

            # If tick is in a future minute, close/advance (and optionally fill empty minutes)
            if minute > st["minute"]:
                self._advance_to(sym, minute)
                st = self.current[sym]  # refreshed state at 'minute' (empty placeholder)

            # Now minute == st["minute"]
            if not st.get("had_tick", True):
                # first real tick of this minute: reset OHLC to the tick price
                st["open"] = price
                st["high"] = price
                st["low"] = price
                st["close"] = price
                st["volume"] = vol
                st["had_tick"] = True
                return

            st["high"] = max(st["high"], price)
            st["low"] = min(st["low"], price)
            st["close"] = price
            st["volume"] += vol
