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
    Orchestrates the streaming pipeline.

    You pass:
      - pipeline.on_message to the websocket client
      - pipeline.on_timer to a heartbeat loop

    Internally it delegates bar-building to MinuteBarBuilder,
    but lets you attach arbitrary tick/bar handlers without modifying the builder.
    """
    builder: MinuteBarBuilder

    pre_tick_handlers: List[TickHandler] = field(default_factory=list)
    post_tick_handlers: List[TickHandler] = field(default_factory=list)
    bar_close_handlers: List[BarCloseHandler] = field(default_factory=list)

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

    def _on_bar_close(self, symbol: str, bar_df: pd.DataFrame) -> None:
        for h in self.bar_close_handlers:
            h(symbol, bar_df)
