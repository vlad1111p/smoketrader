from __future__ import annotations

from datetime import datetime, timezone

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

    builder = MinuteBarBuilder(on_bar_close=on_bar_close, debug_ticks=True)
    client = YahooLiveClient(symbols=symbols)
    client.run(builder.on_message)


def on_bar_close_indicator(
        store: ParquetBarStore,
        interval: str,
        symbol: str,
        bar_df: pd.DataFrame,
        strategy: SimpleRsiEmaMacdStrategy,
) -> None:
    merged = store.upsert(symbol, interval, bar_df)

    last_ts = merged.index[-1].to_pydatetime()
    lag = datetime.now(timezone.utc) - last_ts.astimezone(timezone.utc)

    line = strategy.decide_from_df(symbol=symbol, df=merged, last_ts=last_ts, lag=lag)
    print(line)


if __name__ == "__main__":
    main()
