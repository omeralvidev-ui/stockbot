"""Performance statistics versus a benchmark."""
from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS = 252
_PCT = {"CAGR", "Volatility", "Max drawdown", "Alpha (ann.)", "Total return"}


def perf_stats(eq: pd.Series, bench_eq: pd.Series) -> dict:
    r = eq.pct_change().dropna()
    b = bench_eq.reindex(eq.index).pct_change().dropna()
    r, b = r.align(b, join="inner")
    years = max((eq.index[-1] - eq.index[0]).days / 365.25, 1e-9)
    cagr = (eq.iloc[-1] / eq.iloc[0]) ** (1 / years) - 1
    sd = r.std()
    down = r[r < 0].std()
    var_b = b.var()
    beta = r.cov(b) / var_b if var_b > 0 else np.nan
    excess = r - b
    maxdd = (eq / eq.cummax() - 1).min()
    return {
        "CAGR": cagr,
        "Volatility": sd * np.sqrt(TRADING_DAYS),
        "Sharpe": r.mean() / sd * np.sqrt(TRADING_DAYS) if sd > 0 else np.nan,
        "Sortino": r.mean() / down * np.sqrt(TRADING_DAYS) if down and down > 0 else np.nan,
        "Max drawdown": maxdd,
        "Calmar": cagr / abs(maxdd) if maxdd < 0 else np.nan,
        "Beta": beta,
        "Alpha (ann.)": (r.mean() - beta * b.mean()) * TRADING_DAYS if beta == beta else np.nan,
        "Info ratio": excess.mean() / excess.std() * np.sqrt(TRADING_DAYS) if excess.std() > 0 else np.nan,
        "Total return": eq.iloc[-1] / eq.iloc[0] - 1,
    }


def compare(eq: pd.Series, bench_eq: pd.Series, bench_name: str = "SPY") -> pd.DataFrame:
    return pd.DataFrame({"Strategy": perf_stats(eq, bench_eq), bench_name: perf_stats(bench_eq, bench_eq)})


def format_table(df: pd.DataFrame) -> str:
    out = df.copy().astype(object)
    for idx in df.index:
        for col in df.columns:
            v = df.loc[idx, col]
            out.loc[idx, col] = "n/a" if v != v else (f"{v:.1%}" if idx in _PCT else f"{v:.2f}")
    return out.to_string()
