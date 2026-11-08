"""Risk controls applied on top of strategy weights."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class RiskConfig:
    sentiment_veto: float = -0.35  # skip stocks with mean sentiment at/below this ...
    min_items: int = 5  # ... when at least this many headlines/posts back it up
    stop_loss: float = 0.12  # exit a position down this much from its average entry
    daily_loss_halt: float = 0.03  # stop all trading if the account is down this much today


def apply_sentiment_overlay(weights: pd.Series, sentiments: dict, cfg: RiskConfig):
    """Zero out vetoed names (they stay as cash). Returns (weights, human-readable notes)."""
    w, notes = weights.copy(), []
    for sym, wt in weights[weights > 0].items():
        s = sentiments.get(sym)
        if s is not None and s.n >= cfg.min_items and s.score <= cfg.sentiment_veto:
            w[sym] = 0.0
            notes.append(f"Skipping {sym}: negative news/social sentiment {s.score:+.2f} across {s.n} items")
    return w, notes


def stop_loss_exits(positions: list, cfg: RiskConfig) -> list:
    """positions: dicts with symbol, avg_entry_price, current_price. Returns (symbol, loss) to exit."""
    out = []
    for p in positions:
        entry, cur = float(p["avg_entry_price"]), float(p["current_price"])
        if entry > 0 and cur / entry - 1 <= -cfg.stop_loss:
            out.append((p["symbol"], cur / entry - 1))
    return out


def daily_loss_halt(equity: float, last_equity: float, cfg: RiskConfig) -> bool:
    return last_equity > 0 and equity / last_equity - 1 <= -cfg.daily_loss_halt
