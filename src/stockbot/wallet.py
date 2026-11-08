"""Virtual wallet: a safe place for simulated profits.

Money moved here is out of the trading account, so later trading losses can't touch it.
This is a LOCAL LEDGER of virtual money. It does not hold, move or custody real money; with a
real broker your actual funds stay at that broker.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

DEFAULT_PATH = Path.home() / ".stockbot" / "wallet.json"


class Wallet:
    def __init__(self, path=None):
        self.path = Path(path) if path else DEFAULT_PATH
        try:
            self.data = json.loads(self.path.read_text())
        except Exception:
            self.data = {"balance": 0.0, "history": []}

    @property
    def balance(self) -> float:
        return float(self.data["balance"])

    @property
    def history(self) -> list:
        return self.data["history"]

    def _record(self, kind: str, amount: float, note: str) -> None:
        self.data["history"].append({"t": datetime.now().isoformat(timespec="seconds"), "kind": kind,
                                     "amount": round(amount, 2), "balance_after": round(self.balance, 2),
                                     "note": note})
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=1))
        os.replace(tmp, self.path)

    def deposit(self, amount: float, note: str = "", kind: str = "deposit") -> None:
        if amount <= 0:
            raise ValueError("Amount must be positive")
        self.data["balance"] = self.balance + amount
        self._record(kind, amount, note)

    def withdraw(self, amount: float, note: str = "", kind: str = "cash-out") -> None:
        if amount <= 0:
            raise ValueError("Amount must be positive")
        if amount > self.balance + 1e-9:
            raise ValueError(f"Wallet only has ${self.balance:,.2f}")
        self.data["balance"] = self.balance - amount
        self._record(kind, -amount, note)

    def bank(self, broker, amount: float, note: str = "manual") -> float:
        """Move cash from the simulated trading account into the wallet."""
        amount = broker.withdraw_cash(amount)
        self.deposit(amount, f"banked from trading ({note})", kind="bank")
        return amount

    def fund(self, broker, amount: float) -> float:
        """Move wallet money back into the simulated trading account."""
        self.withdraw(amount, "funded trading account", kind="fund")
        broker.deposit_cash(amount)
        return amount

    def bank_profits(self, broker, pct: float) -> float:
        """Bank `pct` percent of current profit (equity above net deposits), limited to free cash."""
        return self.bank(broker, broker.sweepable_profit(pct), f"{pct:.0f}% of profit") if pct > 0 and \
            broker.sweepable_profit(pct) >= 1 else 0.0
