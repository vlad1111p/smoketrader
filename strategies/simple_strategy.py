from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, Tuple

import pandas as pd

from strategies.indicators.atr_indicator import atr
from strategies.indicators.bollinger_indicator import bollinger_bands
from strategies.indicators.ema_indicator import ema
from strategies.indicators.macd_indicator import macd
from strategies.indicators.rsi_indicator import rsi


class Action(str, Enum):
    BUY = "BUY"
    HOLD = "HOLD"
    SELL = "SELL"


@dataclass
class SimpleRsiEmaMacdStrategy:
    """
    Momentum-flavored RSI strategy:
      - BUY on RSI crossing up through 50 with trend/momentum confirmation
      - SELL on RSI crossing down through 50 or trend/momentum breakdown
    """

    rsi_mid: float = 50.0
    rsi_take_profit: float = 70.0
    in_position: Dict[str, bool] = field(default_factory=dict)

    def decide(
            self,
            symbol: str,
            rsi_now: float,
            rsi_prev: float,
            ema9: float,
            ema20: float,
            macd_hist: float,
    ) -> Tuple[Action, str]:
        have_pos = self.in_position.get(symbol, False)

        uptrend = ema9 > ema20
        downtrend = ema9 < ema20
        bull_momo = macd_hist > 0
        bear_momo = macd_hist < 0

        cross_up = (rsi_prev < self.rsi_mid) and (rsi_now >= self.rsi_mid)
        cross_down = (rsi_prev > self.rsi_mid) and (rsi_now <= self.rsi_mid)

        # BUY: RSI crosses above 50 + trend + momentum
        if (not have_pos) and cross_up and uptrend and bull_momo:
            self.in_position[symbol] = True
            return Action.BUY, "RSI crossed above 50 + EMA9>EMA20 + HIST>0"

        # SELL: RSI crosses below 50 OR trend/momentum breaks
        if have_pos and (cross_down or (downtrend and bear_momo) or bear_momo):
            self.in_position[symbol] = False
            return Action.SELL, "RSI crossed below 50 OR momentum/trend broke"

        # Optional take-profit style exit if you want it:
        # if have_pos and rsi_now >= self.rsi_take_profit and bear_momo:
        #     self.in_position[symbol] = False
        #     return Action.SELL, "RSI>=70 and HIST<0 (take profit)"

        return Action.HOLD, "no signal"

    def decide_from_df(
            self,
            symbol: str,
            df: pd.DataFrame,
            last_ts: datetime,
            lag: timedelta,
    ) -> str:
        tail_df = df.tail(300)
        close = tail_df["Close"]

        # Indicators
        rsi14_s = rsi(close, period=14)
        ema9_s = ema(close, period=9)
        ema20_s = ema(close, period=20)
        atr14_s = atr(tail_df["High"], tail_df["Low"], tail_df["Close"], period=14)

        macd_line_s, macd_signal_s, macd_hist_s = macd(close, fast=12, slow=26, signal=9)
        bb_mid_s, bb_upper_s, bb_lower_s = bollinger_bands(close, period=20, stddev=2.0)

        latest_close = float(close.iloc[-1])

        latest_rsi = rsi14_s.iloc[-1]
        prev_rsi = rsi14_s.iloc[-2] if len(rsi14_s) >= 2 else pd.NA

        latest_ema9 = ema9_s.iloc[-1]
        latest_ema20 = ema20_s.iloc[-1]
        latest_atr = atr14_s.iloc[-1]

        latest_macd = macd_line_s.iloc[-1]
        latest_signal = macd_signal_s.iloc[-1]
        latest_hist = macd_hist_s.iloc[-1]

        latest_bb_mid = bb_mid_s.iloc[-1]
        latest_bb_upper = bb_upper_s.iloc[-1]
        latest_bb_lower = bb_lower_s.iloc[-1]

        action_str = "ACTION=warming-up"
        reason_str = ""

        ready = not (
                pd.isna(latest_rsi)
                or pd.isna(prev_rsi)
                or pd.isna(latest_ema9)
                or pd.isna(latest_ema20)
                or pd.isna(latest_hist)
        )

        if ready:
            action, reason = self.decide(
                symbol=symbol,
                rsi_now=float(latest_rsi),
                rsi_prev=float(prev_rsi),
                ema9=float(latest_ema9),
                ema20=float(latest_ema20),
                macd_hist=float(latest_hist),
            )
            action_str = f"ACTION={action.value}"
            reason_str = f"REASON={reason}"

        parts = [
            f"[{symbol}] bar @ {last_ts} | lag={lag}",
            f"CLOSE={latest_close:.2f}",
            "RSI14=warming-up" if pd.isna(latest_rsi) else f"RSI14={float(latest_rsi):.2f}",
            "EMA9=warming-up" if pd.isna(latest_ema9) else f"EMA9={float(latest_ema9):.2f}",
            "EMA20=warming-up" if pd.isna(latest_ema20) else f"EMA20={float(latest_ema20):.2f}",
            "ATR14=warming-up" if pd.isna(latest_atr) else f"ATR14={float(latest_atr):.4f}",
            "MACD=warming-up" if pd.isna(latest_macd) else f"MACD={float(latest_macd):.4f}",
            "SIGNAL=warming-up" if pd.isna(latest_signal) else f"SIGNAL={float(latest_signal):.4f}",
            "HIST=warming-up" if pd.isna(latest_hist) else f"HIST={float(latest_hist):.4f}",
            "BBMID=warming-up" if pd.isna(latest_bb_mid) else f"BBMID={float(latest_bb_mid):.2f}",
            "BBU=warming-up" if pd.isna(latest_bb_upper) else f"BBU={float(latest_bb_upper):.2f}",
            "BBL=warming-up" if pd.isna(latest_bb_lower) else f"BBL={float(latest_bb_lower):.2f}",
            action_str,
        ]
        if reason_str:
            parts.append(reason_str)

        return " | ".join(parts)
