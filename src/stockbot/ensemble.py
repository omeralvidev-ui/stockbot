"""Blend several strategies and scale exposure to a volatility target."""
from __future__ import annotations

import numpy as np
import pandas as pd


class Ensemble:
    name = "ensemble"

    def __init__(self, strategies, target_vol: float = 0.15, vol_window: int = 63):
        self.strategies = list(strategies)
        self.target_vol, self.vol_window = target_vol, vol_window

    def __call__(self, prices: pd.DataFrame, bench: pd.Series) -> pd.Series:
        w = sum(s(prices, bench) for s in self.strategies) / len(self.strategies)
        if w.sum() <= 0:
            return w
        port = prices.pct_change().iloc[-self.vol_window:].fillna(0.0) @ w
        vol = port.std() * np.sqrt(252)
        if vol > 0:
            w = w * min(1.0, self.target_vol / vol)
        return w
