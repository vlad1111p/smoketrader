from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Protocol, List

import pandas as pd

from data.bar_builder import MinuteBarBuilder


class TickHandler(Protocol):
    def __call__(self, message: dict) -> None: ...


class BarCloseHandler(Protocol):
    def __call__(self, symbol: str, bar_df: pd.DataFrame) -> None: ...


@dataclass
class StreamPipeline:
    """
    Root pipeline object.
    - pass `pipeline.on_message` to the websocket client
    - call `pipeline.on_timer` from heartbeat

    Internally uses MinuteBarBuilder, but lets you add more handlers over time.
    """
    emit_empty_minutes: bool = True
    close_grace_seconds: float = 2.0

    pre_tick_handlers: List[TickHandler] = field(default_factory=list)
    post_tick_handlers: List[TickHandler] = field(default_factory=list)
    bar_close_handlers: List[BarCloseHandler] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.builder = MinuteBarBuilder(
            on_bar_close=self.on_bar_close,
            emit_empty_minutes=self.emit_empty_minutes,
            close_grace_seconds=self.close_grace_seconds,
        )

    def add_pre_tick(self, h: TickHandler) -> None:
        self.pre_tick_handlers.append(h)

    def add_post_tick(self, h: TickHandler) -> None:
        self.post_tick_handlers.append(h)

    def add_on_bar_close(self, h: BarCloseHandler) -> None:
        self.bar_close_handlers.append(h)

    def on_message(self, message: dict) -> None:
        for h in self.pre_tick_handlers:
            h(message)

        self.builder.on_message(message)

        for h in self.post_tick_handlers:
            h(message)

    def on_timer(self, now_utc: Optional[datetime] = None) -> None:
        self.builder.on_timer(now_utc)

    def on_bar_close(self, symbol: str, bar_df: pd.DataFrame) -> None:
        for h in self.bar_close_handlers:
            h(symbol, bar_df)
