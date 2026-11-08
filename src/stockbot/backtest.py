"""Event-driven daily backtest with monthly rebalancing and transaction costs.

Signals are computed from data through the close of the last trading day of each month and
executed at the NEXT trading day's close (one-day lag, so no look-ahead).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class BacktestResult:
    equity: pd.Series
    bench_equity: pd.Series
    weights: dict = field(default_factory=dict)  # signal date -> target weights
    turnover: float = 0.0  # average one-way turnover per rebalance


def run_backtest(prices: pd.DataFrame, bench: pd.Series, strategy, cost_bps: float = 5.0,
                 warmup: int = 260) -> BacktestResult:
    prices = prices.sort_index()
    bench = bench.reindex(prices.index).ffill()
    dates = prices.index
    rets = prices.pct_change().fillna(0.0).to_numpy()
    n, m = rets.shape
    month = dates.to_period("M")
    is_month_end = np.r_[np.asarray(month[1:] != month[:-1]), False]

    pos = np.zeros(m)
    cash = 1.0
    equity = np.full(n, np.nan)
    pending = None
    first = None
    weights: dict = {}
    turnovers: list = []

    for i in range(n):
        pos *= 1.0 + rets[i]
        total = pos.sum() + cash
        if pending is not None:
            trade = np.abs(pending * total - pos).sum()
            total -= trade * cost_bps / 1e4
            turnovers.append(trade / (2 * total) if total > 0 else 0.0)
            pos = pending * total
            cash = total - pos.sum()
            pending = None
        equity[i] = total
        if i >= warmup and is_month_end[i]:
            w = strategy(prices.iloc[: i + 1], bench.iloc[: i + 1]).reindex(prices.columns).fillna(0.0)
            if w.sum() > 1 + 1e-9 or (w < -1e-12).any():
                raise ValueError("Strategy returned invalid weights (must be long-only, sum <= 1)")
            pending = w.to_numpy()
            weights[dates[i]] = w[w > 0]
            if first is None:
                first = i

    if first is None:
        raise ValueError("Not enough history to run the backtest (need > warmup days).")
    eq = pd.Series(equity, index=dates).iloc[first:]
    be = bench.iloc[first:]
    return BacktestResult(eq / eq.iloc[0], be / be.iloc[0], weights,
                          float(np.mean(turnovers)) if turnovers else 0.0)
