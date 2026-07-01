from __future__ import annotations

import asyncio
import datetime as dt
import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    filters,
)

from config import settings
from formatting import format_alert
from reporter import build_daily_report
from scanner import ScannerState, scan_watchlist

logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    level=getattr(logging, settings.log_level, logging.INFO),
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logger = logging.getLogger("scrapfi")

# Telegram's hard message limit is 4096 chars; split with a margin.
_TELEGRAM_MAX = 4000

_scanner_state = ScannerState()

# Reused on every command handler so the bot ignores everyone but the owner.
_owner_only = filters.Chat(chat_id=settings.allowed_chat_id)


async def send_html(bot, chat_id: int, text: str) -> None:
    for chunk in _split_message(text):
        await bot.send_message(chat_id=chat_id, text=chunk, parse_mode=ParseMode.HTML)


def _split_message(text: str) -> list[str]:
    if len(text) <= _TELEGRAM_MAX:
        return [text]
    chunks, current = [], ""
    for line in text.split("\n"):
        if len(current) + len(line) + 1 > _TELEGRAM_MAX:
            if current:
                chunks.append(current)
            current = line
        else:
            current = f"{current}\n{line}" if current else line
    if current:
        chunks.append(current)
    return chunks


async def daily_report_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = context.job.chat_id
    try:
        # Networking (finance + AI) is blocking, so run it off the event loop.
        report = await asyncio.to_thread(build_daily_report)
        await send_html(context.bot, chat_id, report)
    except Exception as exc:
        logger.exception("Daily report failed.")
        await context.bot.send_message(chat_id=chat_id, text=f"⚠️ Nie udało się wygenerować raportu: {exc}")


async def scanner_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = context.job.chat_id
    try:
        alerts = await asyncio.to_thread(scan_watchlist, _scanner_state)
        for alert in alerts:
            await send_html(context.bot, chat_id, format_alert(alert, settings.scanner_interval_minutes))
    except Exception:
        logger.exception("Scanner cycle failed.")


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "👋 <b>ScrapFi</b> działa.\n\n"
        "Dostępne komendy:\n"
        "/status — ustawienia i stan\n"
        "/report — wygeneruj raport Top Gainers teraz\n"
        "/scan — wykonaj skan watchlisty teraz\n"
        "/watchlist — pokaż obserwowane spółki\n"
        "/help — ta pomoc",
        parse_mode=ParseMode.HTML,
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_start(update, context)


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    t = settings.daily_report_time
    text = (
        "⚙️ <b>Status ScrapFi</b>\n"
        f"• Obserwowane spółki: {len(settings.watchlist)}\n"
        f"• Interwał skanera: co {settings.scanner_interval_minutes} min\n"
        f"• Próg alertu: {settings.scanner_threshold_pct:.2f}%"
        f" (spadki: {'tak' if settings.scanner_alert_on_drops else 'nie'})\n"
        f"• Cooldown alertu: {settings.scanner_cooldown_minutes} min\n"
        f"• Raport dzienny: {t.strftime('%H:%M')} ({t.tzinfo})\n"
        f"• Model AI: {settings.gemini_model}\n"
        f"• Źródło Top Gainers: {'FMP' if settings.has_fmp else 'yfinance (fallback)'}"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def cmd_watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tickers = ", ".join(settings.watchlist) or "(pusta)"
    await update.message.reply_text(f"👀 Watchlista: {tickers}")


async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("⏳ Generuję raport Top Gainers...")
    report = await asyncio.to_thread(build_daily_report)
    await send_html(context.bot, update.effective_chat.id, report)


async def cmd_scan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("⏳ Skanuję watchlistę...")
    alerts = await asyncio.to_thread(scan_watchlist, _scanner_state)
    if not alerts:
        await update.message.reply_text("✅ Brak skoków powyżej progu w tym cyklu.")
        return
    for alert in alerts:
        await send_html(context.bot, update.effective_chat.id, format_alert(alert, settings.scanner_interval_minutes))


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Handler exception:", exc_info=context.error)


async def on_startup(app: Application) -> None:
    await app.bot.send_message(
        chat_id=settings.allowed_chat_id,
        text="✅ ScrapFi uruchomiony. Wpisz /status aby sprawdzić ustawienia.",
    )

    # JobQueue jobs are in-memory, so (re)schedule them on every startup.
    jq = app.job_queue
    jq.run_repeating(
        scanner_job,
        interval=dt.timedelta(minutes=settings.scanner_interval_minutes),
        first=15,
        chat_id=settings.allowed_chat_id,
        name="scanner",
    )
    jq.run_daily(
        daily_report_job,
        time=settings.daily_report_time,  # already carries tzinfo
        days=settings.daily_report_days,
        chat_id=settings.allowed_chat_id,
        name="daily_report",
    )


def main() -> None:
    app = ApplicationBuilder().token(settings.telegram_bot_token).post_init(on_startup).build()

    app.add_handler(CommandHandler("start", cmd_start, filters=_owner_only))
    app.add_handler(CommandHandler("help", cmd_help, filters=_owner_only))
    app.add_handler(CommandHandler("status", cmd_status, filters=_owner_only))
    app.add_handler(CommandHandler("watchlist", cmd_watchlist, filters=_owner_only))
    app.add_handler(CommandHandler("report", cmd_report, filters=_owner_only))
    app.add_handler(CommandHandler("scan", cmd_scan, filters=_owner_only))
    app.add_error_handler(on_error)

    logger.info("Starting bot (Ctrl+C to stop)...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
