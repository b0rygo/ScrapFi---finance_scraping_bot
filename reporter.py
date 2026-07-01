from __future__ import annotations

import logging

from ai_analysis import analyze_gainers
from config import settings
from formatting import format_daily_report
from market_data import Gainer, get_top_gainers
from news import Headline, get_company_news

logger = logging.getLogger(__name__)


def build_daily_report() -> str:
    gainers = get_top_gainers(limit=settings.top_gainers_count)
    if not gainers:
        logger.warning("No top gainers data; sending empty report.")
        return format_daily_report([], "")

    items: list[tuple[Gainer, list[Headline]]] = []
    for gainer in gainers:
        headlines = get_company_news(
            gainer.symbol,
            lookback_days=settings.news_lookback_days,
            max_headlines=settings.news_max_headlines,
        )
        items.append((gainer, headlines))

    # Single AI call for all symbols to conserve the free-tier quota.
    ai_text = analyze_gainers(items)
    return format_daily_report(items, ai_text)
