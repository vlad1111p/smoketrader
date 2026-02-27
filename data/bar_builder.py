# smoketrader/data/bar_builder.py
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from threading import Lock
from typing import Callable, Dict, Optional, List, Tuple

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
    - on_message() updates bars from ticks
    - on_timer() force-closes bars on time boundaries, even if no tick arrives
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
            if t > 10_000_000_000:  # ms -> s
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
        for k in ("volume", "last_size", "lastSize", "size"):
            v = message.get(k)
            if isinstance(v, (int, float)):
                return float(v)
            if isinstance(v, str) and v.isdigit():
                return float(v)
        return 0.0

    def _build_bar_df(self, st: Dict) -> pd.DataFrame:
        closed_minute = st["minute"]
        return pd.DataFrame(
            {
                "Open": [st["open"]],
                "High": [st["high"]],
                "Low": [st["low"]],
                "Close": [st["close"]],
                "Volume": [st["volume"]],
            },
            index=pd.DatetimeIndex([closed_minute], tz=timezone.utc),
        )

    def _emit_close_locked(self, sym: str, st: Dict) -> Optional[Tuple[str, pd.DataFrame]]:
        if (not st.get("had_tick", True)) and (not self.emit_empty_minutes):
            return None
        return sym, self._build_bar_df(st)

    def _advance_to_locked(self, sym: str, target_minute: datetime) -> List[Tuple[str, pd.DataFrame]]:
        """
        Force-close and advance symbol state up to target_minute (exclusive),
        creating empty minutes if emit_empty_minutes=True.

        LOCK MUST BE HELD by caller.
        """
        out: List[Tuple[str, pd.DataFrame]] = []
        st = self.current.get(sym)
        if st is None:
            return out

        while st["minute"] < target_minute:
            prev_close = st["close"]
            evt = self._emit_close_locked(sym, st)
            if evt is not None:
                out.append(evt)

            next_minute = st["minute"] + timedelta(minutes=1)
            st = _init_state(next_minute, prev_close, 0.0, had_tick=False)
            self.current[sym] = st

        return out

    def on_timer(self, now_utc: Optional[datetime] = None) -> None:
        if now_utc is None:
            now_utc = datetime.now(timezone.utc)
        else:
            now_utc = now_utc.astimezone(timezone.utc)

        cutoff = now_utc - timedelta(seconds=self.close_grace_seconds)
        cutoff_minute = self._to_utc_minute(cutoff)

        events: List[Tuple[str, pd.DataFrame]] = []
        with self._lock:
            for sym, st in list(self.current.items()):
                if st["minute"] < cutoff_minute:
                    events.extend(self._advance_to_locked(sym, cutoff_minute))

        # callbacks outside lock
        for sym, bar_df in events:
            self.on_bar_close(sym, bar_df)

    def on_message(self, message: dict) -> None:
        sym = self._parse_symbol(message)
        price = self._parse_price(message)
        ts = self._parse_ts(message)

        if not sym or price is None or ts is None:
            return

        minute = self._to_utc_minute(ts)
        vol = self._parse_volume(message)

        events: List[Tuple[str, pd.DataFrame]] = []
        with self._lock:
            st = self.current.get(sym)
            if st is None:
                self.current[sym] = _init_state(minute, price, vol, had_tick=True)
                return

            if minute < st["minute"]:
                return

            if minute > st["minute"]:
                events.extend(self._advance_to_locked(sym, minute))
                st = self.current[sym]

            if not st.get("had_tick", True):
                st["open"] = price
                st["high"] = price
                st["low"] = price
                st["close"] = price
                st["volume"] = vol
                st["had_tick"] = True
            else:
                st["high"] = max(st["high"], price)
                st["low"] = min(st["low"], price)
                st["close"] = price
                st["volume"] += vol

        for sym, bar_df in events:
            self.on_bar_close(sym, bar_df)
