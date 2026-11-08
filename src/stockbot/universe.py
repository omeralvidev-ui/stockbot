"""Stock universe and ticker validation. Equities/ETFs only - crypto is rejected."""
from __future__ import annotations

import re

BENCHMARK = "SPY"

# Large-cap US stocks. NOTE: this is today's list, so backtests carry survivorship bias.
DEFAULT_UNIVERSE = (
    "AAPL MSFT NVDA AMZN GOOGL META AVGO TSLA LLY JPM V UNH XOM MA COST HD PG JNJ ABBV WMT "
    "NFLX BAC CRM ORCL CVX KO MRK AMD PEP TMO ADBE LIN CSCO ACN MCD ABT WFC DIS GE TXN QCOM "
    "CAT INTU IBM AMGN VZ DHR NOW PFE UNP GS ISRG SPGI LOW HON AMAT BKNG T RTX NEE PGR AXP ETN"
).split()

_TICKER_RE = re.compile(r"^[A-Z]{1,5}([.-][A-Z])?$")
_CRYPTO_SUFFIXES = ("-USD", "-USDT", "-USDC", "-BTC", "-ETH", "/", "=X", "=F")
_CRYPTO_SYMBOLS = {"BTC", "ETH", "XRP", "DOGE", "SOL", "ADA", "USDT", "USDC", "BNB", "LTC", "DOT", "SHIB"}


def validate_tickers(tickers: list[str]) -> list[str]:
    """Normalise and validate tickers; raise ValueError on crypto or malformed symbols."""
    out: list[str] = []
    for raw in tickers:
        t = raw.strip().upper()
        if not t:
            continue
        if t.endswith(_CRYPTO_SUFFIXES) or t in _CRYPTO_SYMBOLS:
            raise ValueError(f"Crypto is not supported (stocks only): {raw!r}")
        if not _TICKER_RE.match(t):
            raise ValueError(f"Not a plain stock/ETF ticker: {raw!r}")
        if t not in out:
            out.append(t)
    if not out:
        raise ValueError("No tickers given")
    return out
