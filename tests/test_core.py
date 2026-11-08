import numpy as np
import pandas as pd
import pytest

from stockbot.backtest import run_backtest
from stockbot.broker import plan_orders
from stockbot.metrics import compare
from stockbot.ml import MLRank, build_panel
from stockbot.strategies import Momentum, inverse_vol_weights
from stockbot.universe import validate_tickers


def synth(n_days=1600, n_stocks=20, seed=1):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2015-01-01", periods=n_days)
    drift = rng.normal(0.0004, 0.0003, n_stocks)
    rets = rng.normal(drift, 0.015, (n_days, n_stocks))
    px = pd.DataFrame(100 * np.cumprod(1 + rets, axis=0), index=idx,
                      columns=[f"S{chr(65 + i)}" for i in range(n_stocks)])
    bench = pd.Series(100 * np.cumprod(1 + rng.normal(0.0004, 0.01, n_days)), index=idx)
    return px, bench


def test_rejects_crypto():
    for bad in ["BTC-USD", "eth-usd", "BTC", "DOGE", "EURUSD=X", "BTC/USD", "not a ticker"]:
        with pytest.raises(ValueError):
            validate_tickers([bad])
    assert validate_tickers(["aapl", "MSFT", "aapl"]) == ["AAPL", "MSFT"]


def test_weights_valid_and_capped():
    px, bench = synth()
    w = Momentum(top_n=8)(px, bench)
    assert (w >= 0).all() and w.sum() <= 1 + 1e-9 and w.max() <= 0.25 + 1e-9
    iv = inverse_vol_weights(px, px.columns[:3], max_weight=0.4)
    assert iv.max() <= 0.4 + 1e-9


def test_no_lookahead_strategy_sees_only_history():
    px, bench = synth()
    seen = []

    def spy(prices, b):
        seen.append(prices.index[-1])
        assert len(prices) == len(b)
        return pd.Series(1.0 / prices.shape[1], index=prices.columns)

    res = run_backtest(px, bench, spy, warmup=300)
    # every signal date is a month-end strictly before the last bar
    assert all(d < px.index[-1] for d in seen)
    assert res.equity.index[0] == seen[0]


def test_equal_weight_no_cost_tracks_buy_and_hold_scale():
    px, bench = synth()
    ew = lambda prices, b: pd.Series(1.0 / prices.shape[1], index=prices.columns)  # noqa: E731
    res = run_backtest(px, bench, ew, cost_bps=0.0, warmup=300)
    assert res.equity.iloc[0] == pytest.approx(1.0)
    assert 0.2 < res.equity.iloc[-1] < 20


def test_costs_reduce_returns():
    px, bench = synth()
    a = run_backtest(px, bench, Momentum(top_n=5), cost_bps=0.0)
    b = run_backtest(px, bench, Momentum(top_n=5), cost_bps=50.0)
    assert b.equity.iloc[-1] < a.equity.iloc[-1]


def test_metrics_table():
    px, bench = synth()
    res = run_backtest(px, bench, Momentum(top_n=5))
    t = compare(res.equity, res.bench_equity)
    assert {"CAGR", "Sharpe", "Max drawdown", "Beta"} <= set(t.index)
    assert t.loc["Beta", "SPY"] == pytest.approx(1.0)


def test_ml_panel_target_is_future_and_training_is_causal():
    px, bench = synth()
    panel = build_panel(px, bench)
    assert {"mom_12_1", "target"} <= set(panel.columns)
    # truncating future data must not change features at earlier dates
    d = panel.index.get_level_values("date").unique()[-8]  # a true month-end
    sub = build_panel(px.loc[:d], bench.loc[:d])
    a = sub.xs(d, level="date").drop(columns="target")
    b = panel.xs(d, level="date").drop(columns="target")
    pd.testing.assert_frame_equal(a, b)


def test_ml_strategy_produces_valid_weights():
    px, bench = synth()
    w = MLRank(top_n=5, min_train_rows=100)(px, bench)
    assert (w >= 0).all() and w.sum() <= 1 + 1e-9


def test_plan_orders_sells_first_and_only_managed():
    orders = plan_orders({"AAA": 0.5, "BBB": 0.0}, {"AAA": 100.0, "BBB": 400.0, "ZZZ": 999.0},
                         equity=1000.0, managed={"AAA", "BBB"})
    assert [o.side for o in orders] == ["sell", "buy"]
    assert orders[0].symbol == "BBB" and orders[0].close_all
    assert all(o.symbol != "ZZZ" for o in orders)
