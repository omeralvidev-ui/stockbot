import pandas as pd
import pytest

from stockbot import autopilot as ap
from stockbot.broker import Order
from stockbot.ensemble import Ensemble
from stockbot.risk import RiskConfig, apply_sentiment_overlay, daily_loss_halt, stop_loss_exits
from stockbot.sentiment import Sentiment, score_text
from stockbot.strategies import Momentum
from test_core import synth


def test_sentiment_scoring():
    assert score_text("Company beats estimates, shares surge on record profit") > 0.8
    assert score_text("Regulators open probe as stock plunges after lawsuit") < -0.8
    assert score_text("Company does not beat expectations") < 0
    assert score_text("Quarterly meeting scheduled") == 0


def test_sentiment_veto_needs_enough_evidence():
    w = pd.Series({"AAA": 0.5, "BBB": 0.5})
    sent = {"AAA": Sentiment("AAA", -0.8, 10), "BBB": Sentiment("BBB", -0.9, 2)}
    out, notes = apply_sentiment_overlay(w, sent, RiskConfig())
    assert out["AAA"] == 0 and out["BBB"] == 0.5 and len(notes) == 1


def test_stop_loss_and_halt():
    pos = [{"symbol": "A", "avg_entry_price": "100", "current_price": "85"},
           {"symbol": "B", "avg_entry_price": "100", "current_price": "95"}]
    assert [s for s, _ in stop_loss_exits(pos, RiskConfig())] == ["A"]
    assert daily_loss_halt(96, 100, RiskConfig()) and not daily_loss_halt(99, 100, RiskConfig())


def test_ensemble_valid_and_vol_capped():
    px, bench = synth()
    w = Ensemble([Momentum(top_n=5), Momentum(top_n=8)], target_vol=0.05)(px, bench)
    assert (w >= 0).all() and w.sum() <= 1 + 1e-9
    port = px.pct_change().iloc[-63:].fillna(0) @ w
    assert port.std() * 252 ** 0.5 <= 0.05 * 1.01 or w.sum() == 0


class FakeBroker:
    def __init__(self, equity=1000.0, last=1000.0, positions=()):
        self.equity, self.last, self._pos, self.submitted = equity, last, list(positions), []

    def clock(self): return {"is_open": True}
    def account(self): return {"equity": str(self.equity), "last_equity": str(self.last)}
    def positions(self): return self._pos
    def submit(self, o): self.submitted.append(o)


def _autopilot(broker, tmp_path, monkeypatch, logs):
    monkeypatch.setattr(ap, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(ap, "build_rebalance_plan",
                        lambda cfg, b: ap.Plan("rebalance", [Order("AAA", "buy", 100.0)], ["n"], {"AAA": 0.1}))
    return ap.Autopilot(ap.AutoConfig(countdown_s=0), broker, log=logs.append)


def test_autopilot_rebalances_once_per_month(tmp_path, monkeypatch):
    logs, b = [], FakeBroker()
    a = _autopilot(b, tmp_path, monkeypatch, logs)
    a.tick(); a.tick()
    assert len(b.submitted) == 1


def test_autopilot_cancel_skips_trades(tmp_path, monkeypatch):
    logs, b = [], FakeBroker()
    a = _autopilot(b, tmp_path, monkeypatch, logs)
    a.cfg.countdown_s = 5
    import threading
    threading.Timer(0.2, a.cancel_pending).start()
    a.tick()
    assert b.submitted == [] and any("cancelled" in m for m in logs)


def test_autopilot_halts_on_daily_loss_and_stops_out(tmp_path, monkeypatch):
    logs = []
    b = FakeBroker(equity=900, last=1000)
    a = _autopilot(b, tmp_path, monkeypatch, logs)
    a.tick()
    assert b.submitted == [] and any("HALT" in m for m in logs)

    pos = [{"symbol": "ZZZ", "avg_entry_price": "100", "current_price": "80"}]
    b2 = FakeBroker(positions=pos)
    a2 = _autopilot(b2, tmp_path / "x", monkeypatch, [])
    a2.tick()
    assert any(o.symbol == "ZZZ" and o.close_all for o in b2.submitted)


def test_gui_builds():
    tk = pytest.importorskip("tkinter")
    from stockbot.gui import App

    try:
        app = App()
    except tk.TclError:
        pytest.skip("no display")
    app.update()
    app.destroy()


def test_sim_broker_buy_sell_and_persistence(tmp_path):
    from stockbot.sim import SimBroker

    prices = {"AAA": 100.0}
    q = lambda syms: {s: prices[s] for s in syms if s in prices}  # noqa: E731
    b = SimBroker(path=tmp_path / "p.json", start_cash=1000.0, slippage_bps=0.0, quote_fn=q)
    b.submit(Order("AAA", "buy", 500.0))
    assert float(b.account()["cash"]) == pytest.approx(500.0)
    prices["AAA"] = 110.0
    assert float(b.account()["equity"]) == pytest.approx(1050.0)
    assert float(b.positions()[0]["unrealized_plpc"]) == pytest.approx(0.10)
    b2 = SimBroker(path=tmp_path / "p.json", slippage_bps=0.0, quote_fn=q)  # state survives restart
    assert b2.position_values()["AAA"] == pytest.approx(550.0)
    b2.submit(Order("AAA", "sell", 0.0, close_all=True))
    assert b2.positions() == [] and float(b2.account()["cash"]) == pytest.approx(1050.0)
    with pytest.raises(RuntimeError):
        b2.submit(Order("AAA", "sell", 10.0))


def test_sim_cannot_overspend(tmp_path):
    from stockbot.sim import SimBroker

    b = SimBroker(path=tmp_path / "p.json", start_cash=100.0, slippage_bps=0.0, quote_fn=lambda s: {"AAA": 10.0})
    b.submit(Order("AAA", "buy", 5000.0))
    assert float(b.account()["cash"]) >= -1e-9


def test_market_hours():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from stockbot.sim import market_open

    ny = ZoneInfo("America/New_York")
    assert market_open(datetime(2026, 11, 9, 10, 0, tzinfo=ny))  # Monday 10:00
    assert not market_open(datetime(2026, 11, 9, 17, 0, tzinfo=ny))
    assert not market_open(datetime(2026, 11, 8, 11, 0, tzinfo=ny))  # Sunday
