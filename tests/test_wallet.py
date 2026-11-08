import pytest

from stockbot.broker import Order
from stockbot.sim import SimBroker
from stockbot.wallet import Wallet


def broker(tmp_path, prices):
    return SimBroker(path=tmp_path / "s.json", start_cash=1000.0, slippage_bps=0.0,
                     quote_fn=lambda syms: {s: prices[s] for s in syms if s in prices})


def test_bank_profits_protects_gains_from_later_losses(tmp_path):
    prices = {"AAA": 100.0}
    b, w = broker(tmp_path, prices), Wallet(tmp_path / "w.json")
    b.submit(Order("AAA", "buy", 500.0))
    prices["AAA"] = 140.0  # +40% on 500 -> equity 1200, profit 200, cash 500
    assert float(b.account()["equity"]) == pytest.approx(1200.0)
    banked = w.bank_profits(b, 50)  # bank half the profit
    assert banked == pytest.approx(100.0) and w.balance == pytest.approx(100.0)
    prices["AAA"] = 50.0  # crash
    assert float(b.account()["equity"]) < 1000.0  # trading account suffers
    assert w.balance == pytest.approx(100.0)  # wallet doesn't
    assert b.sweepable_profit(50) == 0.0  # no profit left to bank
    assert [h["kind"] for h in w.history] == ["bank"]


def test_banking_is_not_a_trading_loss(tmp_path):
    b, w = broker(tmp_path, {"AAA": 100.0}), Wallet(tmp_path / "w.json")
    b.account()
    w.bank(b, 300.0)
    acct = b.account()
    assert float(acct["equity"]) / float(acct["last_equity"]) == pytest.approx(1.0)


def test_wallet_limits_and_persistence(tmp_path):
    w = Wallet(tmp_path / "w.json")
    w.deposit(50.0, "x")
    with pytest.raises(ValueError):
        w.withdraw(60.0)
    with pytest.raises(ValueError):
        w.deposit(-1)
    w.withdraw(20.0, "cash out")
    assert Wallet(tmp_path / "w.json").balance == pytest.approx(30.0)


def test_fund_moves_money_back_as_principal(tmp_path):
    b, w = broker(tmp_path, {"AAA": 100.0}), Wallet(tmp_path / "w.json")
    w.deposit(200.0)
    w.fund(b, 200.0)
    assert float(b.account()["cash"]) == pytest.approx(1200.0) and w.balance == 0
    assert b.sweepable_profit(100) == 0.0  # funded money is principal, not profit
