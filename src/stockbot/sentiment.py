"""News/social sentiment from Google News RSS (no key) and X/Twitter (optional bearer token).

IMPORTANT: free feeds give no deep history, so this signal cannot be backtested. It is used
only as a *safety overlay* (veto buying a stock drowning in bad news), never as a predictor.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from urllib.parse import quote

POS = set("""beat beats surge surges soar soars jump jumps rally rallies gain gains rise rises record strong
growth upgrade upgraded outperform bullish profit profits boost boosts expands approval approved wins
raises raised buyback optimistic breakthrough exceeds tops""".split())
NEG = set("""miss misses plunge plunges fall falls drop drops slump slumps crash lawsuit probe investigation
downgrade downgraded underperform bearish loss losses cut cuts layoffs recall fraud bankruptcy weak
warning warns decline declines fine fined sec scandal halt delay delays resigns resign sinks tumbles""".split())
_NEGATORS = {"not", "no", "never", "without", "fails", "failed"}


def score_text(text: str) -> float:
    """Score in [-1, 1] using a small finance word list with simple negation handling."""
    toks = re.findall(r"[a-z']+", text.lower())
    pos = neg = 0
    for i, t in enumerate(toks):
        flip = i > 0 and toks[i - 1] in _NEGATORS
        if t in POS:
            neg, pos = (neg + 1, pos) if flip else (neg, pos + 1)
        elif t in NEG:
            pos, neg = (pos + 1, neg) if flip else (pos, neg + 1)
    return (pos - neg) / (pos + neg) if pos + neg else 0.0


@dataclass
class Sentiment:
    ticker: str
    score: float = 0.0  # mean item score in [-1, 1]
    n: int = 0
    items: list = field(default_factory=list)  # (source, text, score)
    notes: list = field(default_factory=list)


def fetch_google_news(ticker: str, limit: int = 20) -> list:
    import requests

    url = f"https://news.google.com/rss/search?q={quote(ticker + ' stock when:3d')}&hl=en-US&gl=US&ceid=US:en"
    r = requests.get(url, timeout=15, headers={"User-Agent": "stockbot/0.2"})
    r.raise_for_status()
    root = ET.fromstring(r.content)
    return [(it.findtext("title") or "").strip() for it in root.iter("item")][:limit]


def fetch_x(ticker: str, token: str, limit: int = 50) -> list:
    import requests

    r = requests.get("https://api.twitter.com/2/tweets/search/recent", timeout=15,
                     headers={"Authorization": f"Bearer {token}"},
                     params={"query": f"${ticker} lang:en -is:retweet", "max_results": max(10, min(limit, 100))})
    r.raise_for_status()
    return [t["text"] for t in r.json().get("data", [])]


def ticker_sentiment(ticker: str, x_token: str | None = None) -> Sentiment:
    s = Sentiment(ticker)
    sources = [("Google News", lambda: fetch_google_news(ticker))]
    if x_token:
        sources.append(("X", lambda: fetch_x(ticker, x_token)))
    else:
        s.notes.append("X/Twitter off (no bearer token)")
    for name, fn in sources:
        try:
            for text in fn():
                s.items.append((name, text, score_text(text)))
        except Exception as e:  # network/API problems must never crash trading logic
            s.notes.append(f"{name} unavailable: {type(e).__name__}")
    if s.items:
        s.n = len(s.items)
        s.score = sum(i[2] for i in s.items) / s.n
    return s


def scan(tickers, x_token: str | None = None, workers: int = 8) -> dict:
    tickers = list(tickers)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        return dict(zip(tickers, ex.map(lambda t: ticker_sentiment(t, x_token), tickers)))
