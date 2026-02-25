from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import yfinance as yf


@dataclass
class YahooLiveClient:
    """
    Thin wrapper around yfinance WebSocket.
    Keeps your script clean and makes it easier to later swap providers.
    """
    symbols: list[str]

    def run(self, on_message: Callable[[dict], None]) -> None:
        with yf.WebSocket() as ws:
            ws.subscribe(self.symbols)
            ws.listen(on_message)
