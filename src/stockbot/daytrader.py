"""EXPERIMENTAL live day trader. SIMULATION ONLY: it refuses to run against any real broker.

Every minute (during US market hours) it looks for opening-range breakouts on a watchlist,
announces each entry with a short cancel window, manages stop/target, and flattens all
positions before the close. Hard limits: max trades per day, per-trade risk, position cap,
and a daily-loss halt.
"""
from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path

import pandas as pd

from .broker import Order
from .intraday import NY, ORBConfig, fetch_intraday, intraday_quotes, orb_entry
from .risk import RiskConfig, daily_loss_halt
from .sim import SimBroker

DT_PATH = Path.home() / ".stockbot" / "sim_daytrade.json"


def make_day_broker(ignore_hours: bool = False, start_cash: float = 100_000.0) -> SimBroker:
    return SimBroker(path=DT_PATH, start_cash=start_cash, ignore_hours=ignore_hours, quote_fn=intraday_quotes)


class DayTrader(threading.Thread):
    def __init__(self, broker, watchlist, cfg: ORBConfig | None = None, risk: RiskConfig | None = None,
                 risk_per_trade: float = 0.005, max_position: float = 0.20, max_trades_per_day: int = 6,
                 countdown_s: int = 10, poll_s: int = 60, log=print, fetch=fetch_intraday, now_fn=None):
        super().__init__(daemon=True)
        if not isinstance(broker, SimBroker):
            raise TypeError("Day trading is simulation-only; it will not run against a real broker.")
        self.broker, self.watchlist = broker, list(watchlist)
        self.cfg, self.risk = cfg or ORBConfig(), risk or RiskConfig(daily_loss_halt=0.02)
        self.risk_per_trade, self.max_position, self.max_trades = risk_per_trade, max_position, max_trades_per_day
        self.countdown_s, self.poll_s, self.log, self.fetch = countdown_s, poll_s, log, fetch
        self.now_fn = now_fn or (lambda: pd.Timestamp.now(tz=NY))
        self.stop_event, self.cancel_event = threading.Event(), threading.Event()
        self._day, self.meta, self.traded, self.n_trades = None, {}, set(), 0

    def cancel_pending(self) -> None:
        self.cancel_event.set()

    def stop(self) -> None:
        self.stop_event.set()
        self.cancel_event.set()

    def _new_day(self, now) -> None:
        if self._day != now.date():
            self._day, self.traded, self.n_trades = now.date(), set(), 0
            self.meta = {s: m for s, m in self.meta.items() if s in self.broker.state["positions"]}

    def _close(self, sym: str, why: str) -> None:
        self.log(f"EXIT {sym}: {why}")
        try:
            self.broker.submit(Order(sym, "sell", 0.0, close_all=True))
        except Exception as e:
            self.log(f"  failed to close {sym}: {e}")
        self.meta.pop(sym, None)

    def tick(self) -> None:
        now = self.now_fn()
        self._new_day(now)
        if not self.broker.clock().get("is_open"):
            self.log("Market closed; waiting.")
            return
        data = self.fetch(self.watchlist, period="1d", interval="5m")
        acct = self.broker.account()
        equity, cash = float(acct["equity"]), float(acct["cash"])
        halted = daily_loss_halt(equity, float(acct["last_equity"]), self.risk)

        for p in self.broker.positions():  # manage open positions first
            sym, df = p["symbol"], data.get(p["symbol"])
            if df is None or df.empty:
                continue
            last, m = float(df["Close"].iloc[-1]), self.meta.get(sym)
            if now.time() >= self.cfg.flat_time:
                self._close(sym, "end-of-day flatten")
            elif m and last <= m["stop"]:
                self._close(sym, f"stop hit ({last:.2f} <= {m['stop']:.2f})")
            elif m and last >= m["target"]:
                self._close(sym, f"target hit ({last:.2f} >= {m['target']:.2f})")

        if halted:
            self.log("DAILY LOSS HALT: no new entries today.")
            return
        if now.time() >= self.cfg.entry_cutoff or self.n_trades >= self.max_trades:
            return
        held = set(self.broker.state["positions"])
        for sym, df in data.items():
            if sym in held or sym in self.traded or self.n_trades >= self.max_trades:
                continue
            day = df[df.index.date == now.date()]
            if len(day) and now < day.index[-1] + pd.Timedelta(minutes=5):
                day = day.iloc[:-1]  # drop the still-forming bar
            sig = orb_entry(day, self.cfg)
            if sig is None or sig.idx != len(day) - 1:
                continue  # no breakout, or it already happened earlier (we missed it)
            last = float(day["Close"].iloc[-1])
            risk = last - sig.or_low
            notional = min(self.max_position * equity, self.risk_per_trade * equity * last / risk, cash)
            if notional < 100:
                continue
            target = last + self.cfg.target_r * risk
            self.cancel_event.clear()
            self.log(f"ABOUT TO BUY {sym} ${notional:,.0f} @ ~{last:.2f}; stop {sig.or_low:.2f}, target {target:.2f} "
                     f"(cancel within {self.countdown_s}s)")
            if self.cancel_event.wait(self.countdown_s):
                self.log("Entry cancelled.")
                self.traded.add(sym)
                continue
            try:
                self.broker.submit(Order(sym, "buy", notional))
            except Exception as e:
                self.log(f"  buy failed: {e}")
                continue
            self.meta[sym] = {"stop": sig.or_low, "target": target}
            self.traded.add(sym)
            self.n_trades += 1
            cash -= notional

    def run(self) -> None:
        self.log(f"Day trader (SIM) started on {len(self.watchlist)} stocks. Experimental; unproven strategy.")
        while not self.stop_event.is_set():
            try:
                self.tick()
            except Exception as e:
                self.log(f"Error: {type(e).__name__}: {e}")
            self.stop_event.wait(self.poll_s)
        self.log("Day trader stopped.")
