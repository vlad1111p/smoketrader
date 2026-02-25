from __future__ import annotations

from dataclasses import dataclass
from typing import List, Literal, Optional, Tuple

import numpy as np
import pandas as pd

from strategies.indicators.ema_indicator import ema
from strategies.indicators.macd_indicator import macd
from strategies.indicators.rsi_indicator import rsi
from strategies.simple_strategy import Action, SimpleRsiEmaMacdStrategy

Execution = Literal["close", "next_open"]


@dataclass(frozen=True)
class BacktestConfig:
    initial_cash: float = 100.0
    fee_rate: float = 0.0  # 0.001 = 0.1% per trade
    allow_fractional: bool = True
    execution: Execution = "next_open"
    force_flat_at_end: bool = True


@dataclass(frozen=True)
class Trade:
    ts: pd.Timestamp
    side: Literal["BUY", "SELL"]
    price: float
    qty: float
    fee: float
    cash_after: float
    reason: str


@dataclass(frozen=True)
class BacktestResult:
    symbol: str
    initial_cash: float
    final_equity: float
    total_return_pct: float
    max_drawdown_pct: float
    trades: List[Trade]
    equity_curve: pd.DataFrame

    def summary_line(self) -> str:
        return (
            f"[{self.symbol}] initial=${self.initial_cash:.2f} -> "
            f"final=${self.final_equity:.2f} | return={self.total_return_pct:.2f}% | "
            f"maxDD={self.max_drawdown_pct:.2f}% | trades={len(self.trades)}"
        )


def _ensure_utc_index(df: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("DataFrame index must be a DatetimeIndex")

    if df.index.tz is None:
        df = df.copy()
        df.index = df.index.tz_localize("UTC")
    else:
        df = df.copy()
        df.index = df.index.tz_convert("UTC")
    return df.sort_index()


def _max_drawdown_pct(equity: pd.Series) -> float:
    # equity: positive series
    roll_max = equity.cummax()
    dd = (equity / roll_max) - 1.0
    return float(dd.min() * 100.0)


class Backtester:
    def __init__(self, config: Optional[BacktestConfig] = None):
        self.config = config or BacktestConfig()

    def run(self, symbol: str, df: pd.DataFrame, strategy: SimpleRsiEmaMacdStrategy) -> BacktestResult:
        """
        df must contain at least: Open, High, Low, Close, Volume (Volume can be ignored).
        Uses strategy.decide(...) candle-by-candle (no look-ahead; execution configurable).
        """
        df = _ensure_utc_index(df)

        required = {"Open", "High", "Low", "Close"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"Missing columns: {sorted(missing)}")

        # Reset strategy state for a clean run (it is stateful via in_position) :contentReference[oaicite:2]{index=2}
        strategy.in_position.clear()

        close = df["Close"].astype(float)
        open_ = df["Open"].astype(float)

        # Precompute indicators (fast + deterministic)
        rsi14 = rsi(close, period=14)
        ema9 = ema(close, period=9)
        ema20 = ema(close, period=20)
        _, _, hist = macd(close, fast=12, slow=26, signal=9)

        cash = float(self.config.initial_cash)
        qty = 0.0
        trades: List[Trade] = []

        equity_rows: List[Tuple[pd.Timestamp, float]] = []

        n = len(df)
        if n < 3:
            raise ValueError("Not enough bars to simulate")

        # iterate bars; if execution is next_open, we cannot execute on the last bar
        last_i = n - 2 if self.config.execution == "next_open" else n - 1

        for i in range(1, last_i + 1):
            ts = df.index[i]

            # skip until indicators are ready
            if any(pd.isna(x) for x in (rsi14.iloc[i], rsi14.iloc[i - 1], ema9.iloc[i], ema20.iloc[i], hist.iloc[i])):
                # still record equity curve
                equity = cash + qty * float(close.iloc[i])
                equity_rows.append((ts, equity))
                continue

            action, reason = strategy.decide(
                symbol=symbol,
                rsi_now=float(rsi14.iloc[i]),
                rsi_prev=float(rsi14.iloc[i - 1]),
                ema9=float(ema9.iloc[i]),
                ema20=float(ema20.iloc[i]),
                macd_hist=float(hist.iloc[i]),
            )

            # Determine execution price
            if self.config.execution == "close":
                px = float(close.iloc[i])
                exec_ts = ts
            else:
                px = float(open_.iloc[i + 1])
                exec_ts = df.index[i + 1]

            # Execute
            if action == Action.BUY and qty <= 0.0:
                if px <= 0:
                    continue

                raw_qty = cash / (px * (1.0 + self.config.fee_rate))

                if not self.config.allow_fractional:
                    raw_qty = float(np.floor(raw_qty))

                if raw_qty > 0:
                    cost = raw_qty * px
                    fee = cost * self.config.fee_rate
                    total = cost + fee

                    if total <= cash + 1e-9:
                        cash -= total
                        qty += raw_qty
                        trades.append(Trade(exec_ts, "BUY", px, raw_qty, fee, cash, reason))

            elif action == Action.SELL and qty > 0.0:
                proceeds = qty * px
                fee = proceeds * self.config.fee_rate
                cash += (proceeds - fee)
                trades.append(Trade(exec_ts, "SELL", px, qty, fee, cash, reason))
                qty = 0.0

            # Mark-to-market at bar close time (equity curve uses close)
            equity = cash + qty * float(close.iloc[i])
            equity_rows.append((ts, equity))

        # Force flat at end (optional)
        final_ts = df.index[-1]
        final_px = float(close.iloc[-1])
        if self.config.force_flat_at_end and qty > 0:
            proceeds = qty * final_px
            fee = proceeds * self.config.fee_rate
            cash += (proceeds - fee)
            trades.append(Trade(final_ts, "SELL", final_px, qty, fee, cash, "force_flat_at_end"))
            qty = 0.0

        final_equity = cash
        eq_df = pd.DataFrame(equity_rows, columns=["ts", "equity"]).set_index("ts")
        if not eq_df.empty:
            max_dd = _max_drawdown_pct(eq_df["equity"])
        else:
            max_dd = 0.0

        total_return = ((final_equity / self.config.initial_cash) - 1.0) * 100.0

        return BacktestResult(
            symbol=symbol,
            initial_cash=self.config.initial_cash,
            final_equity=final_equity,
            total_return_pct=float(total_return),
            max_drawdown_pct=float(max_dd),
            trades=trades,
            equity_curve=eq_df,
        )
