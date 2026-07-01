from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import time as dt_time
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()


class ConfigError(RuntimeError):
    pass


def _require(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigError(
            f"Missing required variable '{name}' in .env. "
            f"Copy .env.example to .env and fill in the keys."
        )
    return value


def _optional(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"'{name}' must be an integer, got: {raw!r}") from exc


def _float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw.replace(",", "."))
    except ValueError as exc:
        raise ConfigError(f"'{name}' must be a number, got: {raw!r}") from exc


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "y", "tak"}


def _list(name: str, default: list[str] | None = None) -> list[str]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return list(default or [])
    return [item.strip().upper() for item in raw.split(",") if item.strip()]


@dataclass(frozen=True)
class Config:
    telegram_bot_token: str
    allowed_chat_id: int

    finnhub_api_key: str
    fmp_api_key: str
    gemini_api_key: str
    gemini_model: str

    watchlist: list[str]
    scanner_interval_minutes: int
    scanner_threshold_pct: float
    scanner_alert_on_drops: bool
    scanner_cooldown_minutes: int
    scanner_call_delay_seconds: float

    daily_report_time: dt_time
    daily_report_days: tuple[int, ...]
    top_gainers_count: int
    news_lookback_days: int
    news_max_headlines: int

    log_level: str

    @property
    def has_fmp(self) -> bool:
        return bool(self.fmp_api_key)


def load_config() -> Config:
    raw_chat_id = _require("TELEGRAM_ALLOWED_CHAT_ID")
    try:
        allowed_chat_id = int(raw_chat_id)
    except ValueError as exc:
        raise ConfigError(
            f"TELEGRAM_ALLOWED_CHAT_ID must be a number (e.g. 123456789), got: {raw_chat_id!r}"
        ) from exc

    tz_name = _optional("DAILY_REPORT_TIMEZONE", "America/New_York")
    try:
        tzinfo = ZoneInfo(tz_name)
    except Exception as exc:
        # On Windows zoneinfo needs the 'tzdata' package (included in requirements.txt).
        raise ConfigError(f"Unknown timezone DAILY_REPORT_TIMEZONE={tz_name!r}.") from exc

    hh_mm = _optional("DAILY_REPORT_TIME", "08:30")
    try:
        hour_str, minute_str = hh_mm.split(":")
        report_time = dt_time(hour=int(hour_str), minute=int(minute_str), tzinfo=tzinfo)
    except Exception as exc:
        raise ConfigError(f"DAILY_REPORT_TIME must be HH:MM, got: {hh_mm!r}") from exc

    # python-telegram-bot v20+ weekday numbering: 0=Sunday ... 6=Saturday.
    # Trading days (Monday-Friday) are therefore 1,2,3,4,5 (NOT 0,1,2,3,4).
    days_raw = _list("DAILY_REPORT_DAYS", ["1", "2", "3", "4", "5"])
    try:
        report_days = tuple(sorted({int(d) for d in days_raw if 0 <= int(d) <= 6}))
    except ValueError as exc:
        raise ConfigError("DAILY_REPORT_DAYS must be comma-separated integers 0-6.") from exc

    return Config(
        telegram_bot_token=_require("TELEGRAM_BOT_TOKEN"),
        allowed_chat_id=allowed_chat_id,
        finnhub_api_key=_require("FINNHUB_API_KEY"),
        fmp_api_key=_optional("FMP_API_KEY"),
        gemini_api_key=_require("GEMINI_API_KEY"),
        gemini_model=_optional("GEMINI_MODEL", "gemini-2.5-flash"),
        watchlist=_list("WATCHLIST", ["AAPL", "MSFT", "NVDA", "TSLA"]),
        scanner_interval_minutes=_int("SCANNER_INTERVAL_MINUTES", 3),
        scanner_threshold_pct=_float("SCANNER_THRESHOLD_PCT", 1.5),
        scanner_alert_on_drops=_bool("SCANNER_ALERT_ON_DROPS", False),
        scanner_cooldown_minutes=_int("SCANNER_COOLDOWN_MINUTES", 15),
        scanner_call_delay_seconds=_float("SCANNER_CALL_DELAY_SECONDS", 0.5),
        daily_report_time=report_time,
        daily_report_days=report_days,
        top_gainers_count=_int("TOP_GAINERS_COUNT", 5),
        news_lookback_days=_int("NEWS_LOOKBACK_DAYS", 3),
        news_max_headlines=_int("NEWS_MAX_HEADLINES", 6),
        log_level=_optional("LOG_LEVEL", "INFO").upper(),
    )


settings = load_config()
