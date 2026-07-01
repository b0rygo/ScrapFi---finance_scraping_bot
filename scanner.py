from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from config import settings
from market_data import get_quote

logger = logging.getLogger(__name__)


@dataclass
class ScannerState:
    last_prices: dict[str, float] = field(default_factory=dict)
    last_alert_ts: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class Alert:
    symbol: str
    previous: float
    current: float
    pct_change: float
    is_up: bool


def scan_watchlist(state: ScannerState) -> list[Alert]:
    threshold = settings.scanner_threshold_pct
    cooldown_s = settings.scanner_cooldown_minutes * 60
    delay = settings.scanner_call_delay_seconds
    now = time.time()

    alerts: list[Alert] = []
    watchlist = settings.watchlist
    logger.info("Scanning %d symbols (threshold %.2f%%)...", len(watchlist), threshold)

    for i, symbol in enumerate(watchlist):
        quote = get_quote(symbol)
        # Space out requests to stay under Finnhub's 60/min and 30/sec limits.
        if delay > 0 and i < len(watchlist) - 1:
            time.sleep(delay)

        if quote is None:
            continue

        previous = state.last_prices.get(symbol)
        state.last_prices[symbol] = quote.current

        # First time we see this symbol: set the baseline, don't alert.
        if previous is None or previous <= 0:
            continue

        pct = (quote.current - previous) / previous * 100.0
        is_up = pct > 0
        crossed = pct >= threshold if is_up else (
            settings.scanner_alert_on_drops and pct <= -threshold
        )
        if not crossed:
            continue

        # Cooldown: don't re-alert the same symbol within the cooldown window.
        if now - state.last_alert_ts.get(symbol, 0.0) < cooldown_s:
            continue

        state.last_alert_ts[symbol] = now
        alerts.append(Alert(symbol=symbol, previous=previous, current=quote.current,
                            pct_change=pct, is_up=is_up))
        logger.info("ALERT %s: %.2f -> %.2f (%+.2f%%)", symbol, previous, quote.current, pct)

    return alerts
