"""EXPERIMENTAL intraday research: opening-range breakout (ORB), long-only, flat by the close.

Strategy: the first 30 minutes (6 five-minute bars) set the opening range. Go long when a bar
closes above the range high AND above VWAP (before 15:00), enter at the next bar's open,
stop at the range low, target at R x risk, otherwise exit at the close. One trade per
stock per day. Costs are charged on both sides.

Yahoo only serves ~60 days of 5-minute data, so any backtest here covers about 3 months.
That is far too little to prove an edge; treat results as a smoke test, not evidence.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import time

import numpy as np
import pandas as pd

NY = "America/New_York"
DEFAULT_WATCHLIST = "AAPL MSFT NVDA AMZN GOOGL META TSLA AMD NFLX AVGO JPM XOM COST CRM ORCL".split()


@dataclass
class ORBConfig:
    or_bars: int = 6
    entry_cutoff: time = time(15, 0)
    flat_time: time = time(15, 55)
    target_r: float = 2.0
    min_risk_pct: float = 0.001  # skip degenerate tiny ranges
    max_risk_pct: float = 0.03  # skip ranges so wide the stop is huge


@dataclass
class Signal:
    idx: int  # position of the signal bar within the day's bars
    or_high: float
    or_low: float


def fetch_intraday(tickers, period: str = "60d", interval: str = "5m") -> dict:
    """{ticker: DataFrame[Open, High, Low, Close, Volume]} in New York time, regular hours only."""
    import yfinance as yf

    tickers = list(tickers)
    raw = yf.download(tickers, period=period, interval=interval, auto_adjust=True, progress=False,
                      threads=True, group_by="ticker")
    out = {}
    for t in tickers:
        try:
            df = raw[t] if isinstance(raw.columns, pd.MultiIndex) else raw
            df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
            idx = pd.DatetimeIndex(df.index)
            idx = idx.tz_localize("UTC") if idx.tz is None else idx
            df.index = idx.tz_convert(NY)
            df = df.between_time("09:30", "15:59")
            if len(df):
                out[t] = df
        except KeyError:
            continue
    return out


def vwap(day: pd.DataFrame) -> pd.Series:
    tp = (day["High"] + day["Low"] + day["Close"]) / 3
    vol = day["Volume"].replace(0, np.nan)
    return ((tp * vol).cumsum() / vol.cumsum()).ffill().fillna(day["Close"])


def orb_entry(day: pd.DataFrame, cfg: ORBConfig) -> Signal | None:
    """First qualifying breakout bar of the day (using only that bar and earlier bars)."""
    if len(day) <= cfg.or_bars:
        return None
    orng = day.iloc[: cfg.or_bars]
    orh, orl = float(orng["High"].max()), float(orng["Low"].min())
    vw = vwap(day)
    for i in range(cfg.or_bars, len(day)):
        bar_time = day.index[i].time()
        if bar_time >= cfg.entry_cutoff:
            return None
        c = float(day["Close"].iloc[i])
        if c > orh and c > float(vw.iloc[i]):
            risk_pct = (c - orl) / c
            if cfg.min_risk_pct <= risk_pct <= cfg.max_risk_pct:
                return Signal(i, orh, orl)
            return None  # breakout happened but the stop is unusable; skip the day
    return None


@dataclass
class Trade:
    date: object
    ticker: str
    entry: float
    exit: float
    ret: float  # net of costs
    risk_pct: float
    reason: str


def simulate_day(day: pd.DataFrame, cfg: ORBConfig, cost_bps: float) -> Trade | None:
    sig = orb_entry(day, cfg)
    if sig is None or sig.idx + 1 >= len(day):
        return None
    c = cost_bps / 1e4
    entry_raw = float(day["Open"].iloc[sig.idx + 1])  # next bar's open: one-bar execution lag
    stop = sig.or_low
    risk = entry_raw - stop
    if risk <= 0:
        return None
    target = entry_raw + cfg.target_r * risk
    exit_raw, reason = float(day["Close"].iloc[-1]), "close"
    for j in range(sig.idx + 1, len(day)):
        o, h, l = (float(day[k].iloc[j]) for k in ("Open", "High", "Low"))
        if j > sig.idx + 1 and o <= stop:
            exit_raw, reason = o, "stop"
            break
        if l <= stop:  # if stop and target are both inside one bar, assume the stop hit first
            exit_raw, reason = stop, "stop"
            break
        if h >= target:
            exit_raw, reason = target, "target"
            break
        if day.index[j].time() >= cfg.flat_time:
            exit_raw, reason = float(day["Close"].iloc[j]), "close"
            break
    entry, exit_ = entry_raw * (1 + c), exit_raw * (1 - c)
    return Trade(day.index[0].date(), "", entry, exit_, exit_ / entry - 1, risk / entry_raw, reason)


@dataclass
class DayResult:
    trades: pd.DataFrame
    equity: pd.Series
    bench: pd.Series
    stats: dict = field(default_factory=dict)


def backtest_orb(data: dict, cfg: ORBConfig | None = None, cost_bps: float = 5.0,
                 risk_per_trade: float = 0.005, max_position: float = 0.20) -> DayResult:
    cfg = cfg or ORBConfig()
    rows = []
    bench_days = {}
    for tkr, df in data.items():
        for d, day in df.groupby(df.index.date):
            if len(day) < cfg.or_bars + 5:
                continue
            bench_days.setdefault(d, []).append(float(day["Close"].iloc[-1]) / float(day["Open"].iloc[0]) - 1)
            t = simulate_day(day, cfg, cost_bps)
            if t:
                t.ticker = tkr
                rows.append(t.__dict__)
    trades = pd.DataFrame(rows)
    days = sorted(bench_days)
    if not days:
        raise ValueError("No intraday data to test.")
    bench = pd.Series({d: np.mean(v) for d, v in bench_days.items()}).sort_index()
    rets = pd.Series(0.0, index=days)
    if len(trades):
        trades["frac"] = np.minimum(max_position, risk_per_trade / trades["risk_pct"])
        for d, g in trades.groupby("date"):
            scale = min(1.0, 1.0 / g["frac"].sum())  # never use more than 100% of capital
            rets[d] = float((g["frac"] * scale * g["ret"]).sum())
    equity = (1 + rets).cumprod()
    bench_eq = (1 + bench).cumprod()

    stats = {"trading days": len(days), "trades": len(trades)}
    if len(trades):
        wins, losses = trades.loc[trades["ret"] > 0, "ret"], trades.loc[trades["ret"] <= 0, "ret"]
        stats.update({
            "win rate": len(wins) / len(trades),
            "avg trade return": trades["ret"].mean(),
            "profit factor": wins.sum() / abs(losses.sum()) if losses.sum() < 0 else float("inf"),
            "exits (target/stop/close)": "/".join(str(int((trades["reason"] == r).sum())) for r in ("target", "stop", "close")),
        })
    sd = rets.std()
    stats.update({
        "total return": equity.iloc[-1] - 1,
        "max drawdown": float((equity / equity.cummax() - 1).min()),
        "daily Sharpe (ann.)": rets.mean() / sd * np.sqrt(252) if sd > 0 else float("nan"),
        "buy&hold (equal-weight, open->close daily)": bench_eq.iloc[-1] - 1,
    })
    return DayResult(trades, equity, bench_eq, stats)


def intraday_quotes(symbols) -> dict:
    """Latest 5-minute close per symbol (falls back to daily quotes)."""
    symbols = list(symbols)
    if not symbols:
        return {}
    data = fetch_intraday(symbols, period="1d")
    out = {s: float(df["Close"].iloc[-1]) for s, df in data.items()}
    if len(out) < len(symbols):
        from .sim import yf_quotes

        for s, p in yf_quotes([s for s in symbols if s not in out]).items():
            out[s] = p
    return out
