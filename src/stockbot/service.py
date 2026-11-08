"""Shared helpers used by the CLI, autopilot and desktop app."""
from __future__ import annotations

from .data import load_prices
from .ensemble import Ensemble
from .strategies import Momentum
from .universe import BENCHMARK, DEFAULT_UNIVERSE, validate_tickers

STRATEGIES = ["momentum", "ml", "ensemble"]


def make_strategy(name: str, top: int = 10, risk_off: float = 0.0):
    if name == "momentum":
        return Momentum(top_n=top, risk_off_exposure=risk_off)
    from .ml import MLRank

    ml = MLRank(top_n=top, risk_off_exposure=risk_off)
    if name == "ml":
        return ml
    if name == "ensemble":
        return Ensemble([Momentum(top_n=top, risk_off_exposure=risk_off), ml])
    raise ValueError(f"Unknown strategy {name!r}")


def load_universe(tickers_csv: str | None = None, start: str = "2008-01-01", use_cache: bool = True):
    tickers = validate_tickers(tickers_csv.split(",")) if tickers_csv else list(DEFAULT_UNIVERSE)
    tickers = [t for t in tickers if t != BENCHMARK]
    px = load_prices(tickers + [BENCHMARK], start=start, use_cache=use_cache)
    return px.drop(columns=[BENCHMARK]).dropna(axis=1, how="all"), px[BENCHMARK]
