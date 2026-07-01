from __future__ import annotations

import logging
from dataclasses import dataclass

import finnhub
import requests

from config import settings

logger = logging.getLogger(__name__)

_finnhub_client = finnhub.Client(api_key=settings.finnhub_api_key)

# Current (2026) FMP endpoint: note there is NO /api/v3 and NO /stock_market segment.
_FMP_GAINERS_URL = "https://financialmodelingprep.com/stable/biggest-gainers"


@dataclass(frozen=True)
class Quote:
    symbol: str
    current: float
    prev_close: float
    percent_change: float


@dataclass(frozen=True)
class Gainer:
    symbol: str
    name: str
    price: float
    change: float
    percent_change: float


def get_quote(symbol: str) -> Quote | None:
    try:
        data = _finnhub_client.quote(symbol)
    except Exception as exc:
        logger.warning("Finnhub quote(%s) failed: %s", symbol, exc)
        return None

    # Finnhub returns zeros for unknown symbols; treat that as "no data".
    current = float(data.get("c") or 0.0)
    if current <= 0.0:
        return None

    return Quote(
        symbol=symbol,
        current=current,
        prev_close=float(data.get("pc") or 0.0),
        percent_change=float(data.get("dp") or 0.0),
    )


def get_top_gainers(limit: int) -> list[Gainer]:
    gainers: list[Gainer] = []
    if settings.has_fmp:
        gainers = _gainers_from_fmp()
    if not gainers:
        gainers = _gainers_from_yfinance()

    gainers.sort(key=lambda g: g.percent_change, reverse=True)
    return gainers[:limit]


def _gainers_from_fmp() -> list[Gainer]:
    try:
        resp = requests.get(_FMP_GAINERS_URL, params={"apikey": settings.fmp_api_key}, timeout=15)
        resp.raise_for_status()
        rows = resp.json()
    except Exception as exc:
        logger.warning("FMP biggest-gainers failed: %s", exc)
        return []

    if not isinstance(rows, list):
        return []

    result: list[Gainer] = []
    for row in rows:
        try:
            result.append(
                Gainer(
                    symbol=str(row["symbol"]).upper(),
                    name=str(row.get("name") or row["symbol"]),
                    price=float(row.get("price") or 0.0),
                    change=float(row.get("change") or 0.0),
                    percent_change=_coerce_percent(row.get("changesPercentage")),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return result


def _gainers_from_yfinance() -> list[Gainer]:
    try:
        import yfinance as yf

        response = yf.screen("day_gainers", count=25)
        quotes = response.get("quotes", []) if isinstance(response, dict) else []
    except Exception as exc:
        logger.warning("yfinance screener fallback failed: %s", exc)
        return []

    result: list[Gainer] = []
    for q in quotes:
        try:
            symbol = str(q.get("symbol", "")).upper()
            if not symbol:
                continue
            result.append(
                Gainer(
                    symbol=symbol,
                    name=str(q.get("shortName") or q.get("longName") or symbol),
                    price=float(q.get("regularMarketPrice") or 0.0),
                    change=float(q.get("regularMarketChange") or 0.0),
                    percent_change=float(q.get("regularMarketChangePercent") or 0.0),
                )
            )
        except (TypeError, ValueError):
            continue
    return result


def _coerce_percent(value) -> float:
    # FMP returns a number on /stable, but a string like "5.26%" on the legacy endpoint.
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = str(value).replace("%", "").replace("(", "").replace(")", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return 0.0
