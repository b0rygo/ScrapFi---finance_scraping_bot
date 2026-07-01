from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta

from config import settings
from market_data import _finnhub_client  # reuse the same client/key

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Headline:
    title: str
    summary: str
    source: str
    url: str


def get_company_news(symbol: str, lookback_days: int, max_headlines: int) -> list[Headline]:
    headlines = _news_from_finnhub(symbol, lookback_days, max_headlines)
    if not headlines:
        headlines = _news_from_ddgs(symbol, max_headlines)
    return headlines[:max_headlines]


def _news_from_finnhub(symbol: str, lookback_days: int, max_headlines: int) -> list[Headline]:
    today = date.today()
    since = today - timedelta(days=lookback_days)
    try:
        # Param is `_from` because `from` is a reserved Python keyword.
        # Note: Finnhub company-news covers North American (US/Canada) tickers only.
        articles = _finnhub_client.company_news(symbol, _from=since.isoformat(), to=today.isoformat())
    except Exception as exc:
        logger.warning("Finnhub company_news(%s) failed: %s", symbol, exc)
        return []

    if not isinstance(articles, list):
        return []

    result: list[Headline] = []
    for a in articles:
        title = str(a.get("headline") or "").strip()
        if not title:
            continue
        result.append(
            Headline(
                title=title,
                summary=str(a.get("summary") or "").strip(),
                source=str(a.get("source") or "Finnhub").strip(),
                url=str(a.get("url") or "").strip(),
            )
        )
        if len(result) >= max_headlines:
            break
    return result


def _news_from_ddgs(symbol: str, max_headlines: int) -> list[Headline]:
    try:
        # New package name; the old 'duckduckgo_search' is frozen/deprecated.
        from ddgs import DDGS

        with DDGS() as ddgs:
            items = ddgs.news(
                query=f"{symbol} stock",
                region="us-en",
                safesearch="off",
                timelimit="w",
                max_results=max_headlines,
            )
    except Exception as exc:
        logger.warning("ddgs.news(%s) fallback failed: %s", symbol, exc)
        return []

    result: list[Headline] = []
    for it in items or []:
        title = str(it.get("title") or "").strip()
        if not title:
            continue
        result.append(
            Headline(
                title=title,
                summary=str(it.get("body") or "").strip(),
                source=str(it.get("source") or "DuckDuckGo").strip(),
                url=str(it.get("url") or "").strip(),
            )
        )
    return result
