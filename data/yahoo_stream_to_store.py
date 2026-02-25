from __future__ import annotations

import threading
import time
from datetime import datetime, timezone, timedelta

import pandas as pd
import yfinance as yf

from data.bar_builder import MinuteBarBuilder
from data.store import ParquetBarStore
from data.stream_pipeline import StreamPipeline
from data.yahoo_live import YahooLiveClient
from strategies.simple_strategy import SimpleRsiEmaMacdStrategy


def tick_logger(message: dict) -> None:
    sym = message.get("id") or message.get("symbol") or message.get("ticker")
    price = message.get("price")
    t = message.get("time") or message.get("timestamp")

    ts_str = "NO_TS"
    if t is not None:
        try:
            t = int(t)
            if t > 10_000_000_000:  # ms
                t = t / 1000.0
            ts_str = datetime.fromtimestamp(t, tz=timezone.utc).isoformat()
        except Exception:
            ts_str = str(t)

    print(f"TICK [{sym}] [{ts_str}] price={price} raw={message}")


def make_bar_close_handler(store: ParquetBarStore, interval: str, strategy: SimpleRsiEmaMacdStrategy):
    def on_bar_close(symbol: str, bar_df: pd.DataFrame) -> None:
        merged = store.upsert(symbol, interval, bar_df)

        bar_start = bar_df.index[-1].to_pydatetime()
        bar_end_utc = bar_start.astimezone(timezone.utc) + timedelta(minutes=1)

        now_utc = datetime.now(timezone.utc)
        lag = now_utc - bar_end_utc

        cutoff = pd.Timestamp(bar_start).tz_convert("UTC")
        merged_upto = merged.copy()
        merged_upto.index = pd.to_datetime(merged_upto.index, utc=True)
        merged_upto = merged_upto.loc[:cutoff]

        line = strategy.decide_from_df(symbol=symbol, df=merged_upto, last_ts=bar_start, lag=lag)
        print(line)

    return on_bar_close


def main() -> None:
    symbols = ["AAPL", "AMZN", "GOOG", "NVDA", "AVGO", "MSFT"]
    interval = "1m"

    store = ParquetBarStore()
    strategy = SimpleRsiEmaMacdStrategy()

    # preload history (same as before)
    for s in symbols:
        hist = yf.Ticker(s).history(period="7d", interval=interval, prepost=True)
        if hist is not None and not hist.empty:
            store.upsert(s, interval, hist[["Open", "High", "Low", "Close", "Volume"]])

    # create pipeline first (needs builder), but builder needs pipeline callback:
    # easiest: create builder with pipeline callback after pipeline exists.
    # So: create a dummy builder first, then replace? Instead we do a 2-step:
    # 1) create builder with a placeholder lambda
    # 2) create pipeline
    # 3) wire builder.on_bar_close to pipeline._on_bar_close by recreating builder
    # We'll do the cleanest: create pipeline after builder, but pass pipeline._on_bar_close using a forward-declared function.

    # forward declaration holder
    pipeline_ref = {"pipeline": None}

    def bar_close_proxy(symbol: str, bar_df: pd.DataFrame) -> None:
        pipeline_ref["pipeline"]._on_bar_close(symbol, bar_df)

    builder = MinuteBarBuilder(
        on_bar_close=bar_close_proxy,
        debug_ticks=False,
        emit_empty_minutes=True,
        close_grace_seconds=2.0,
    )

    pipeline = StreamPipeline(builder=builder)
    pipeline_ref["pipeline"] = pipeline

    pipeline.add_pre_tick(tick_logger)
    pipeline.add_on_bar_close(make_bar_close_handler(store, interval, strategy))

    stop = threading.Event()

    def heartbeat():
        while not stop.is_set():
            pipeline.on_timer(datetime.now(timezone.utc))
            time.sleep(0.5)

    t = threading.Thread(target=heartbeat, daemon=True)
    t.start()

    client = YahooLiveClient(symbols=symbols)
    try:
        client.run(pipeline.on_message)
    finally:
        stop.set()
        t.join(timeout=1.0)


if __name__ == "__main__":
    main()
