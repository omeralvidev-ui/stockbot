"""Machine-learning stock ranker, evaluated walk-forward (never trained on the future).

Each month-end we build momentum/volatility/relative-strength features per stock, convert
them to cross-sectional ranks, and train a gradient-boosted model to predict the rank of
each stock's next-month return. Only rows whose outcome was already known on the
decision date are used for training.
"""
from __future__ import annotations

import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from .strategies import finalize, inverse_vol_weights, regime_on

FEATURES = ["mom_1m", "mom_3m", "mom_6m", "mom_12_1", "vol_3m", "dist_high", "rel_3m", "rel_12_1"]


def _month_end_dates(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    s = pd.Series(index, index=index)
    return pd.DatetimeIndex(s.groupby(index.to_period("M")).max().values)


def build_panel(prices: pd.DataFrame, bench: pd.Series) -> pd.DataFrame:
    """Long panel indexed by (date, ticker).

    Includes the final date even if it is mid-month (its target is NaN, so it can be
    predicted but never trained on).
    """
    p = prices
    b = bench.reindex(p.index).ffill()
    rets = p.pct_change()
    raw = {
        "mom_1m": p.pct_change(21),
        "mom_3m": p.pct_change(63),
        "mom_6m": p.pct_change(126),
        "mom_12_1": p.shift(21) / p.shift(252) - 1,
        "vol_3m": rets.rolling(63).std(),
        "dist_high": p / p.rolling(252).max() - 1,
    }
    raw["rel_3m"] = raw["mom_3m"].sub(b.pct_change(63), axis=0)
    raw["rel_12_1"] = raw["mom_12_1"].sub(b.shift(21) / b.shift(252) - 1, axis=0)

    me = _month_end_dates(p.index)
    dates = me if me[-1] == p.index[-1] else me.append(pd.DatetimeIndex([p.index[-1]]))

    cols = {}
    for name, df in raw.items():
        cols[name] = df.loc[dates].rank(axis=1, pct=True).stack()
    panel = pd.DataFrame(cols)
    panel.index.names = ["date", "ticker"]

    me_ret = p.loc[me].pct_change().shift(-1)  # return from this month-end to the next
    target = me_ret.rank(axis=1, pct=True).stack()
    target.index.names = ["date", "ticker"]
    panel["target"] = target.reindex(panel.index)
    return panel


class MLRank:
    name = "ml"

    def __init__(self, top_n: int = 10, min_train_rows: int = 1500, retrain_every_months: int = 6,
                 max_weight: float = 0.25, regime_window: int = 200, risk_off_exposure: float = 0.0,
                 seed: int = 0):
        self.top_n, self.min_train_rows = top_n, min_train_rows
        self.retrain_every = retrain_every_months
        self.max_weight, self.regime_window, self.risk_off = max_weight, regime_window, risk_off_exposure
        self.seed = seed
        self._model = None
        self._trained_at = None

    def _fit(self, train: pd.DataFrame):
        m = HistGradientBoostingRegressor(max_iter=150, learning_rate=0.05, max_depth=3,
                                          min_samples_leaf=50, l2_regularization=1.0,
                                          random_state=self.seed)
        m.fit(train[FEATURES], train["target"])
        return m

    def __call__(self, prices: pd.DataFrame, bench: pd.Series) -> pd.Series:
        zero = pd.Series(0.0, index=prices.columns)
        if len(prices) < 300:
            return zero
        today = prices.index[-1]
        exposure = 1.0 if regime_on(bench, self.regime_window) else self.risk_off
        if exposure <= 0:
            return zero

        panel = build_panel(prices, bench)
        dates = panel.index.get_level_values("date")
        train = panel[(dates < today) & panel["target"].notna() & panel["mom_12_1"].notna()]
        if len(train) < self.min_train_rows:
            return zero

        stale = self._trained_at is None or (today - self._trained_at).days > 30 * self.retrain_every
        if self._model is None or stale:
            self._model = self._fit(train)
            self._trained_at = today

        now = panel.xs(today, level="date")
        now = now[now["mom_12_1"].notna()]
        if now.empty:
            return zero
        pred = pd.Series(self._model.predict(now[FEATURES]), index=now.index)
        picks = pred.nlargest(self.top_n).index
        w = inverse_vol_weights(prices, picks, max_weight=self.max_weight)
        return finalize(prices, w, exposure)
