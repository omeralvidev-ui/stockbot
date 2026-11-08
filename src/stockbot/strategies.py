"""Rule-based strategy: cross-sectional momentum + trend regime filter + inverse-vol sizing.

A strategy is any callable ``(prices, bench) -> pd.Series`` of target weights (sum <= 1,
remainder is cash). It only ever receives history up to "today"; never future data.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def regime_on(bench: pd.Series, window: int = 200) -> bool:
    """True when the benchmark closes above its long moving average (risk-on)."""
    if len(bench) < window:
        return False
    return bool(bench.iloc[-1] > bench.iloc[-window:].mean())


def inverse_vol_weights(prices: pd.DataFrame, picks, window: int = 63, max_weight: float = 0.25) -> pd.Series:
    picks = list(picks)
    if not picks:
        return pd.Series(dtype=float)
    vol = prices[picks].pct_change().iloc[-window:].std().replace(0, np.nan)
    w = (1.0 / vol).fillna(0.0)
    if w.sum() == 0:
        w = pd.Series(1.0, index=picks)
    w = w / w.sum()
    for _ in range(20):  # cap single-name weight, redistribute the excess
        over = w > max_weight + 1e-12
        if not over.any():
            break
        excess = (w[over] - max_weight).sum()
        w[over] = max_weight
        under = ~over
        if w[under].sum() <= 0:
            break
        w[under] += excess * w[under] / w[under].sum()
    return w.clip(upper=max_weight)


def finalize(prices: pd.DataFrame, w: pd.Series, exposure: float) -> pd.Series:
    return (w * exposure).reindex(prices.columns).fillna(0.0)


class Momentum:
    """12-1 month momentum: hold the top-N winners with positive absolute momentum."""

    name = "momentum"

    def __init__(self, top_n: int = 10, lookback: int = 252, skip: int = 21, max_weight: float = 0.25,
                 regime_window: int = 200, risk_off_exposure: float = 0.0):
        self.top_n, self.lookback, self.skip = top_n, lookback, skip
        self.max_weight, self.regime_window, self.risk_off = max_weight, regime_window, risk_off_exposure

    def __call__(self, prices: pd.DataFrame, bench: pd.Series) -> pd.Series:
        if len(prices) <= self.lookback:
            return pd.Series(0.0, index=prices.columns)
        exposure = 1.0 if regime_on(bench, self.regime_window) else self.risk_off
        if exposure <= 0:
            return pd.Series(0.0, index=prices.columns)
        score = (prices.iloc[-1 - self.skip] / prices.iloc[-1 - self.lookback] - 1).dropna()
        picks = score[score > 0].nlargest(self.top_n).index
        w = inverse_vol_weights(prices, picks, max_weight=self.max_weight)
        return finalize(prices, w, exposure)
