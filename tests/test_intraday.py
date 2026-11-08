import pandas as pd
import pytest

from stockbot.broker import Order
from stockbot.daytrader import DayTrader
from stockbot.intraday import ORBConfig, backtest_orb, orb_entry, simulate_day
from stockbot.sim import SimBroker


def make_day(closes, date="2026-06-01"):
    idx = pd.date_range(f"{date} 09:30", periods=len(closes), freq="5min", tz="America/New_York")
    opens = [closes[0]] + list(closes[:-1])
    return pd.DataFrame({"Open": opens,
                         "High": [max(o, c) + 0.05 for o, c in zip(opens, closes)],
                         "Low": [min(o, c) - 0.05 for o, c in zip(opens, closes)],
                         "Close": closes, "Volume": 1000.0}, index=idx)


OR = [100, 100.2, 100, 99.8, 100, 100.1]


def up_day():
    return make_day(OR + [100.1 + 0.15 * i for i in range(1, 40)] + [106.0] * 33)


def down_day():
    return make_day(OR + [100.1 + 0.15 * i for i in range(1, 4)] + [99.0] * 69)


def test_breakout_signal_detected():
    sig = orb_entry(up_day(), ORBConfig())
    assert sig is not None and sig.idx >= 6 and sig.or_low < 100


def test_no_signal_when_range_never_breaks():
    flat = make_day([100, 100.2, 100, 99.8, 100, 100.1] + [100.0] * 72)
    assert orb_entry(flat, ORBConfig()) is None


def test_target_and_stop_mechanics():
    t = simulate_day(up_day(), ORBConfig(), cost_bps=0)
    assert t.reason == "target" and t.ret > 0
    s = simulate_day(down_day(), ORBConfig(), cost_bps=0)
    assert s.reason == "stop" and s.ret < 0


def test_signal_uses_no_future_bars():
    day = up_day()
    sig = orb_entry(day, ORBConfig())
    truncated = orb_entry(day.iloc[: sig.idx + 1], ORBConfig())
    assert truncated is not None and truncated.idx == sig.idx


def test_backtest_runs_and_costs_hurt():
    data = {"AAA": up_day(), "BBB": pd.concat([up_day()])}
    a = backtest_orb(data, cost_bps=0)
    b = backtest_orb(data, cost_bps=50)
    assert a.stats["trades"] == 2 and a.stats["total return"] > b.stats["total return"]


def test_daytrader_refuses_real_brokers():
    class Real:
        pass

    with pytest.raises(TypeError):
        DayTrader(Real(), ["AAA"])


def test_daytrader_enters_and_exits(tmp_path):
    day = up_day()
    sig = orb_entry(day, ORBConfig())
    state = {"n": sig.idx + 1}  # bars "available" so far

    def fetch(tickers, period="1d", interval="5m"):
        return {"AAA": day.iloc[: state["n"]]}

    now = day.index[sig.idx] + pd.Timedelta(minutes=5)  # signal bar just completed
    clock = {"t": now}
    b = SimBroker(path=tmp_path / "d.json", slippage_bps=0, ignore_hours=True,
                  quote_fn=lambda s: {k: float(day["Close"].iloc[state["n"] - 1]) for k in s})
    logs = []
    dt = DayTrader(b, ["AAA"], countdown_s=0, log=logs.append, fetch=fetch, now_fn=lambda: clock["t"])
    dt.tick()
    assert "AAA" in b.state["positions"], logs
    dt.tick()  # same bar again: must not double-enter
    assert dt.n_trades == 1
    state["n"], clock["t"] = len(day), day.index[-1] + pd.Timedelta(minutes=5)
    dt.tick()  # price long past target -> exit
    assert "AAA" not in b.state["positions"] and any("EXIT" in m for m in logs)
