"""Autopilot: checks the market on a timer, announces what it is about to do, waits a
cancel window, then trades. Stop-losses and a daily-loss halt run on every check.

It rebalances once per calendar month on the first open-market check of the month, using
data through the previous close (the same timing the backtest assumes).
"""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .broker import Order, plan_orders
from .risk import RiskConfig, apply_sentiment_overlay, daily_loss_halt, stop_loss_exits
from .sentiment import scan
from .service import load_universe, make_strategy

STATE_FILE = Path.home() / ".cache" / "stockbot" / "autopilot_state.json"


@dataclass
class AutoConfig:
    strategy: str = "ensemble"
    top: int = 10
    tickers: str | None = None
    start: str = "2008-01-01"
    x_token: str | None = None
    use_sentiment: bool = True
    countdown_s: int = 60
    poll_minutes: int = 15
    bank_pct: float = 0.0  # % of profit to move into the virtual wallet after each monthly rebalance (sim only)
    risk: RiskConfig = field(default_factory=RiskConfig)


@dataclass
class Plan:
    kind: str  # "rebalance" | "stop-loss"
    orders: list
    notes: list = field(default_factory=list)
    weights: dict = field(default_factory=dict)

    def describe(self) -> str:
        lines = [f"{self.kind.upper()}: {len(self.orders)} order(s)"]
        lines += [f"  {o.side.upper():<4} {o.symbol:<6} ${o.notional:,.2f}" for o in self.orders]
        lines += [f"  note: {n}" for n in self.notes]
        return "\n".join(lines)


def build_rebalance_plan(cfg: AutoConfig, broker) -> Plan:
    stocks, bench = load_universe(cfg.tickers, cfg.start)
    w = make_strategy(cfg.strategy, cfg.top)(stocks, bench)
    notes = []
    if cfg.use_sentiment and (w > 0).any():
        sent = scan(list(w[w > 0].index), cfg.x_token)
        w, notes = apply_sentiment_overlay(w, sent, cfg.risk)
    equity = float(broker.account()["equity"])
    orders = plan_orders(w[w > 0].to_dict(), broker.position_values(), equity, set(stocks.columns))
    if (w > 0).sum() == 0:
        notes.append("No holdings qualify (risk-off regime or vetoed): moving to cash")
    return Plan("rebalance", orders, notes, w[w > 0].to_dict())


def _load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state))
    except OSError:
        pass


class Autopilot(threading.Thread):
    def __init__(self, cfg: AutoConfig, broker, log=print, announce=None):
        super().__init__(daemon=True)
        self.cfg, self.broker, self.log = cfg, broker, log
        self.announce = announce or (lambda plan, secs: None)
        self.stop_event = threading.Event()
        self.cancel_event = threading.Event()

    def cancel_pending(self) -> None:
        self.cancel_event.set()

    def stop(self) -> None:
        self.stop_event.set()
        self.cancel_event.set()

    def _execute(self, plan: Plan) -> bool:
        if not plan.orders:
            self.log(f"{plan.kind}: nothing to trade. " + "; ".join(plan.notes))
            return True
        self.cancel_event.clear()
        self.log("ABOUT TO TRADE in %ds (cancel to stop):\n%s" % (self.cfg.countdown_s, plan.describe()))
        self.announce(plan, self.cfg.countdown_s)
        if self.cancel_event.wait(self.cfg.countdown_s):
            self.log("Trades cancelled.")
            return False
        for o in plan.orders:
            try:
                self.broker.submit(o)
                self.log(f"  placed {o.side} {o.symbol} ${o.notional:,.2f}")
            except Exception as e:
                self.log(f"  FAILED {o.side} {o.symbol}: {e}")
        return True

    def tick(self) -> None:
        if not self.broker.clock().get("is_open"):
            self.log("Market closed; waiting.")
            return
        acct = self.broker.account()
        equity, last = float(acct["equity"]), float(acct.get("last_equity", acct["equity"]))
        if daily_loss_halt(equity, last, self.cfg.risk):
            self.log(f"DAILY LOSS HALT: account is {equity / last - 1:.1%} today. No trading until tomorrow.")
            return

        exits = stop_loss_exits(self.broker.positions(), self.cfg.risk)
        if exits:
            orders = [Order(s, "sell", 0.0, close_all=True) for s, _ in exits]
            notes = [f"{s} is {loss:.1%} from entry (stop-loss {self.cfg.risk.stop_loss:.0%})" for s, loss in exits]
            self._execute(Plan("stop-loss", orders, notes))

        month = datetime.now().strftime("%Y-%m")
        state = _load_state()
        if state.get("last_rebalance") == month:
            self.log(f"Already handled {month} rebalance. Next check in {self.cfg.poll_minutes} min.")
            return
        self.log("Building monthly rebalance plan (downloading prices, scanning news)...")
        plan = build_rebalance_plan(self.cfg, self.broker)
        self._execute(plan)  # a cancelled plan is skipped for the month on purpose
        _save_state({"last_rebalance": month})
        self._bank()

    def _bank(self) -> None:
        if self.cfg.bank_pct <= 0 or not hasattr(self.broker, "sweepable_profit"):
            return
        from .wallet import Wallet

        try:
            moved = Wallet().bank_profits(self.broker, self.cfg.bank_pct)
            self.log(f"Banked ${moved:,.2f} of profit into the wallet." if moved else "No profit to bank this month.")
        except Exception as e:
            self.log(f"Banking skipped: {e}")

    def run(self) -> None:
        self.log(f"Autopilot started ({self.cfg.strategy}, top {self.cfg.top}). Checks every {self.cfg.poll_minutes} min.")
        while not self.stop_event.is_set():
            try:
                self.tick()
            except Exception as e:
                self.log(f"Error during check: {type(e).__name__}: {e}")
            self.stop_event.wait(self.cfg.poll_minutes * 60)
        self.log("Autopilot stopped.")
