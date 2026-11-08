"""Price download (Yahoo Finance via yfinance) with a small on-disk cache."""
from __future__ import annotations

import hashlib
import time
from pathlib import Path

import pandas as pd

CACHE_DIR = Path.home() / ".cache" / "stockbot"
CACHE_MAX_AGE_S = 12 * 3600


def load_prices(tickers: list[str], start: str, end: str | None = None, use_cache: bool = True) -> pd.DataFrame:
    """Adjusted daily closes, one column per ticker (ffilled over short gaps)."""
    key = hashlib.md5(f"{sorted(tickers)}|{start}|{end}".encode()).hexdigest()[:16]
    path = CACHE_DIR / f"prices_{key}.csv"
    if use_cache and path.exists() and time.time() - path.stat().st_mtime < CACHE_MAX_AGE_S:
        return pd.read_csv(path, index_col=0, parse_dates=True)

    import yfinance as yf

    raw = yf.download(tickers, start=start, end=end, auto_adjust=True, progress=False, threads=True)
    if raw is None or raw.empty:
        raise RuntimeError("No price data returned (network problem or bad tickers).")
    close = raw["Close"]
    if isinstance(close, pd.Series):
        close = close.to_frame(tickers[0])
    close = close.dropna(how="all").sort_index().ffill(limit=5)
    close.index = pd.to_datetime(close.index).tz_localize(None)
    if use_cache:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        close.to_csv(path)
    return close
