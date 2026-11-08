"""Alpaca equities broker (paper trading by default). Stocks only - no crypto endpoints.

Credentials come from the environment: ALPACA_KEY_ID and ALPACA_SECRET_KEY.
Live trading additionally requires STOCKBOT_ALLOW_LIVE=yes plus the --live flag.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

PAPER_URL = "https://paper-api.alpaca.markets"
LIVE_URL = "https://api.alpaca.markets"


@dataclass
class Order:
    symbol: str
    side: str  # "buy" | "sell"
    notional: float
    close_all: bool = False


def plan_orders(target_weights: dict, position_values: dict, equity: float, managed: set,
                min_trade: float = 5.0, cash_buffer: float = 0.01) -> list:
    """Diff target weights against current holdings; sells come first to free cash.

    Only symbols in ``managed`` are touched, so unrelated holdings are never liquidated.
    """
    investable = equity * (1 - cash_buffer)
    sells, buys = [], []
    for sym in sorted(managed):
        target = target_weights.get(sym, 0.0) * investable
        current = position_values.get(sym, 0.0)
        diff = target - current
        if target == 0 and current > 0:
            sells.append(Order(sym, "sell", current, close_all=True))
        elif diff <= -min_trade:
            sells.append(Order(sym, "sell", -diff))
        elif diff >= min_trade:
            buys.append(Order(sym, "buy", diff))
    return sells + buys


class Alpaca:
    def __init__(self, live: bool = False):
        key, secret = os.environ.get("ALPACA_KEY_ID"), os.environ.get("ALPACA_SECRET_KEY")
        if not key or not secret:
            raise RuntimeError("Set ALPACA_KEY_ID and ALPACA_SECRET_KEY (a free paper-trading account works).")
        if live and os.environ.get("STOCKBOT_ALLOW_LIVE", "").lower() != "yes":
            raise RuntimeError("Live trading blocked. Set STOCKBOT_ALLOW_LIVE=yes if you really mean it.")
        self.base = LIVE_URL if live else PAPER_URL
        self.live = live
        self.headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}

    def _req(self, method: str, path: str, **kw):
        import requests

        r = requests.request(method, self.base + path, headers=self.headers, timeout=30, **kw)
        r.raise_for_status()
        return r.json() if r.content else None

    def account(self) -> dict:
        return self._req("GET", "/v2/account")

    def clock(self) -> dict:
        return self._req("GET", "/v2/clock")

    def position_values(self) -> dict:
        return {p["symbol"]: float(p["market_value"]) for p in self._req("GET", "/v2/positions")
                if p.get("asset_class", "us_equity") == "us_equity"}

    def submit(self, order: Order):
        if order.close_all:
            return self._req("DELETE", f"/v2/positions/{order.symbol}")
        body = {"symbol": order.symbol, "side": order.side, "type": "market",
                "time_in_force": "day", "notional": f"{order.notional:.2f}"}
        return self._req("POST", "/v2/orders", json=body)
