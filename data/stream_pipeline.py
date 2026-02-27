# smoketrader/data/stream_pipeline.py
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from queue import Queue, Full, Empty
from threading import Event, Thread
from typing import Optional, Protocol, List, Tuple

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

    This version prevents websocket ping timeouts by:
    - enqueueing ticks (so ws thread never blocks)
    - enqueueing bar-close events (so IO/strategy doesn't block bar building)
    """
    emit_empty_minutes: bool = True
    close_grace_seconds: float = 2.0

    async_ticks: bool = True
    tick_queue_max: int = 200_000
    bar_queue_max: int = 20_000
    drop_ticks_when_full: bool = True

    tick_thread: Optional[Thread] = field(init=False, default=None, repr=False)
    bar_thread: Optional[Thread] = field(init=False, default=None, repr=False)

    pre_tick_handlers: List[TickHandler] = field(default_factory=list)
    post_tick_handlers: List[TickHandler] = field(default_factory=list)
    bar_close_handlers: List[BarCloseHandler] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._stop = Event()

        self._tick_q: Queue[dict] = Queue(maxsize=self.tick_queue_max)
        self._bar_q: Queue[Tuple[str, pd.DataFrame]] = Queue(maxsize=self.bar_queue_max)

        self.tick_thread: Optional[Thread] = None
        self.bar_thread: Optional[Thread] = None

        self.builder = MinuteBarBuilder(
            on_bar_close=self.on_bar_close,  # enqueue bars here
            emit_empty_minutes=self.emit_empty_minutes,
            close_grace_seconds=self.close_grace_seconds,
        )

    def start(self) -> None:
        if not self.async_ticks:
            return
        if self.tick_thread and self.tick_thread.is_alive():
            return

        self._stop.clear()

        self.tick_thread = Thread(target=self._tick_worker, name="tick-worker", daemon=True)
        self.bar_thread = Thread(target=self._bar_worker, name="bar-worker", daemon=True)

        self.tick_thread.start()
        self.bar_thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self.tick_thread:
            self.tick_thread.join(timeout=2.0)
        if self.bar_thread:
            self.bar_thread.join(timeout=2.0)

    def add_pre_tick(self, h: TickHandler) -> None:
        self.pre_tick_handlers.append(h)

    def add_post_tick(self, h: TickHandler) -> None:
        self.post_tick_handlers.append(h)

    def add_on_bar_close(self, h: BarCloseHandler) -> None:
        self.bar_close_handlers.append(h)

    def on_message(self, message: dict) -> None:
        if not self.async_ticks:
            self._process_tick(message)
            return

        try:
            self._tick_q.put_nowait(message)
        except Full:
            if not self.drop_ticks_when_full:
                try:
                    self._tick_q.put(message, timeout=0.2)
                except Full:
                    pass

    def on_timer(self, now_utc: Optional[datetime] = None) -> None:
        self.builder.on_timer(now_utc)

    def on_bar_close(self, symbol: str, bar_df: pd.DataFrame) -> None:
        if not self.async_ticks:
            for h in self.bar_close_handlers:
                h(symbol, bar_df)
            return

        try:
            self._bar_q.put((symbol, bar_df), timeout=1.0)
        except Full:
            print(f"[StreamPipeline] bar queue FULL - dropping bar for {symbol}")

    def _process_tick(self, message: dict) -> None:
        for h in self.pre_tick_handlers:
            h(message)

        self.builder.on_message(message)

        for h in self.post_tick_handlers:
            h(message)

    def _tick_worker(self) -> None:
        while not self._stop.is_set():
            try:
                msg = self._tick_q.get(timeout=0.5)
            except Empty:
                continue
            try:
                self._process_tick(msg)
            finally:
                self._tick_q.task_done()

    def _bar_worker(self) -> None:
        while not self._stop.is_set():
            try:
                sym, bar_df = self._bar_q.get(timeout=0.5)
            except Empty:
                continue
            try:
                for h in self.bar_close_handlers:
                    h(sym, bar_df)
            finally:
                self._bar_q.task_done()
