from __future__ import annotations

import threading
import time
from datetime import datetime, timezone, timedelta

import pandas as pd
import yfinance as yf

from data.bar_builder import MinuteBarBuilder
from data.store import ParquetBarStore
from data.yahoo_live import YahooLiveClient
from strategies.simple_strategy import SimpleRsiEmaMacdStrategy


def main() -> None:
    symbols = ["AAPL", "AMZN", "GOOG", "NVDA", "AVGO", "MSFT", "RHM.DE"]
    interval = "1m"

    store = ParquetBarStore()
    strategy = SimpleRsiEmaMacdStrategy()

    for s in symbols:
        hist = yf.Ticker(s).history(period="7d", interval=interval, prepost=True)
        if hist is not None and not hist.empty:
            store.upsert(s, interval, hist[["Open", "High", "Low", "Close", "Volume"]])

    def on_bar_close(symbol: str, bar_df: pd.DataFrame):
        on_bar_close_indicator(store, interval, symbol, bar_df, strategy)

    builder = MinuteBarBuilder(
        on_bar_close=on_bar_close,
        debug_ticks=True,
        emit_empty_minutes=True,
        close_grace_seconds=2.0,
    )

    stop = threading.Event()

    def heartbeat():
        while not stop.is_set():
            builder.on_timer(datetime.now(timezone.utc))
            time.sleep(0.5)

    t = threading.Thread(target=heartbeat, daemon=True)
    t.start()

    client = YahooLiveClient(symbols=symbols)
    try:
        client.run(builder.on_message)
    finally:
        stop.set()
        t.join(timeout=1.0)


def on_bar_close_indicator(store, interval, symbol, bar_df, strategy) -> None:
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


if __name__ == "__main__":
    main()
