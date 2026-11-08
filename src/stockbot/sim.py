"""Local simulated broker: virtual money, real yfinance prices, runs entirely on your computer.

Same interface as the Alpaca broker, so the autopilot, CLI and desktop app use it unchanged.
Fills use the latest yfinance price (can be ~15 min delayed) plus a small slippage. Nothing
here touches a real brokerage or real money. US market holidays are not modelled.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime, time
from pathlib import Path

from .broker import Order

DEFAULT_PATH = Path.home() / ".stockbot" / "sim_portfolio.json"


def market_open(now: datetime | None = None) -> bool:
    from zoneinfo import ZoneInfo

    ny = now or datetime.now(ZoneInfo("America/New_York"))
    return ny.weekday() < 5 and time(9, 30) <= ny.time() < time(16, 0)


def yf_quotes(symbols) -> dict:
    import pandas as pd
    import yfinance as yf

    symbols = list(symbols)
    if not symbols:
        return {}
    df = yf.download(symbols, period="5d", progress=False, auto_adjust=True)["Close"]
    if isinstance(df, pd.Series):
        df = df.to_frame(symbols[0])
    return {s: float(df[s].dropna().iloc[-1]) for s in df.columns if df[s].notna().any()}


class SimBroker:
    def __init__(self, path=None, start_cash: float = 100_000.0, slippage_bps: float = 5.0,
                 ignore_hours: bool = False, quote_fn=yf_quotes):
        self.path = Path(path) if path else DEFAULT_PATH
        self.start_cash, self.slip = start_cash, slippage_bps / 1e4
        self.ignore_hours, self.quote_fn = ignore_hours, quote_fn
        self.state = self._load()

    # ---- persistence ----
    def _load(self) -> dict:
        try:
            return json.loads(self.path.read_text())
        except Exception:
            return {"cash": self.start_cash, "positions": {}, "day": "", "day_start_equity": self.start_cash,
                    "trades": [], "start_cash": self.start_cash}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state, indent=1))
        os.replace(tmp, self.path)

    def reset(self) -> None:
        self.state = {"cash": self.start_cash, "positions": {}, "day": "", "day_start_equity": self.start_cash,
                      "trades": [], "start_cash": self.start_cash}
        self._save()

    # ---- cash movements (used by the wallet) ----
    def _base(self) -> float:
        """Net external deposits: the money you put in, excluding profits."""
        return self.state.get("base", self.state.get("start_cash", self.start_cash))

    def withdraw_cash(self, amount: float) -> float:
        amount = min(float(amount), self.state["cash"])
        if amount < 0.01:
            raise RuntimeError("No free cash to move")
        self.state["cash"] -= amount
        self.state["day_start_equity"] = self.state.get("day_start_equity", 0.0) - amount  # not a trading loss
        self._save()
        return amount

    def deposit_cash(self, amount: float) -> None:
        self.state["cash"] += amount
        self.state["base"] = self._base() + amount  # new principal, not profit
        self.state["day_start_equity"] = self.state.get("day_start_equity", 0.0) + amount
        self._save()

    def sweepable_profit(self, pct: float) -> float:
        """pct% of equity above principal, limited to free cash (we never force-sell to bank)."""
        profit = float(self.account()["equity"]) - self._base()
        return max(0.0, min(profit * pct / 100.0, self.state["cash"]))

    # ---- broker interface ----
    def clock(self) -> dict:
        return {"is_open": self.ignore_hours or market_open()}

    def _equity(self, quotes: dict) -> float:
        return self.state["cash"] + sum(p["qty"] * quotes.get(s, p["avg"]) for s, p in self.state["positions"].items())

    def account(self) -> dict:
        quotes = self.quote_fn(self.state["positions"].keys())
        eq = self._equity(quotes)
        today = date.today().isoformat()
        if self.state["day"] != today:
            self.state["day"], self.state["day_start_equity"] = today, eq
            self._save()
        return {"equity": f"{eq:.2f}", "cash": f"{self.state['cash']:.2f}",
                "last_equity": f"{self.state['day_start_equity']:.2f}"}

    def positions(self) -> list:
        quotes = self.quote_fn(self.state["positions"].keys())
        out = []
        for s, p in sorted(self.state["positions"].items()):
            cur = quotes.get(s, p["avg"])
            out.append({"symbol": s, "qty": f"{p['qty']:.4f}", "avg_entry_price": f"{p['avg']:.4f}",
                        "current_price": f"{cur:.4f}", "market_value": f"{p['qty'] * cur:.2f}",
                        "unrealized_plpc": f"{cur / p['avg'] - 1:.6f}", "asset_class": "us_equity"})
        return out

    def position_values(self) -> dict:
        return {p["symbol"]: float(p["market_value"]) for p in self.positions()}

    def submit(self, order: Order):
        sym = order.symbol
        price = self.quote_fn([sym]).get(sym)
        if not price:
            raise RuntimeError(f"No price available for {sym}")
        pos = self.state["positions"].get(sym)
        if order.side == "buy":
            fill = price * (1 + self.slip)
            notional = min(order.notional, self.state["cash"])
            if notional < 1:
                raise RuntimeError("Not enough cash")
            qty = notional / fill
            if pos:
                total = pos["qty"] + qty
                pos["avg"] = (pos["qty"] * pos["avg"] + qty * fill) / total
                pos["qty"] = total
            else:
                self.state["positions"][sym] = {"qty": qty, "avg": fill}
            self.state["cash"] -= notional
        else:
            if not pos:
                raise RuntimeError(f"No {sym} position to sell")
            fill = price * (1 - self.slip)
            qty = pos["qty"] if order.close_all else min(pos["qty"], order.notional / fill)
            self.state["cash"] += qty * fill
            pos["qty"] -= qty
            if pos["qty"] < 1e-9:
                del self.state["positions"][sym]
        self.state["trades"].append({"t": datetime.now().isoformat(timespec="seconds"), "side": order.side,
                                     "symbol": sym, "qty": round(qty, 6), "price": round(fill, 4)})
        self._save()
        return self.state["trades"][-1]
