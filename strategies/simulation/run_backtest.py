from __future__ import annotations

from data.store import ParquetBarStore
from strategies.simple_strategy import SimpleRsiEmaMacdStrategy
from strategies.simulation.backtester import Backtester, BacktestConfig


def main() -> None:
    symbol = "AMZN"
    interval = "1m"

    store = ParquetBarStore()
    df = store.load(symbol, interval)
    if df is None or df.empty:
        print(f"No data found for {symbol} {interval}. Run yahoo_stream_to_store first.")
        return

    bt = Backtester(
        BacktestConfig(
            initial_cash=100.0,
            fee_rate=0.001,
            allow_fractional=True,
            execution="next_open",
            force_flat_at_end=True,
        )
    )

    strategy = SimpleRsiEmaMacdStrategy()
    result = bt.run(symbol=symbol, df=df, strategy=strategy)

    print(result.summary_line())
    print("\nLast 10 trades:")
    for t in result.trades:
        print(
            f"{t.ts} {t.side:4} px={t.price:.2f} qty={t.qty:.6f} fee={t.fee:.4f} cash={t.cash_after:.2f} | {t.reason}")


if __name__ == "__main__":
    main()
