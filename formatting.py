from __future__ import annotations

from datetime import date
from html import escape

from market_data import Gainer
from news import Headline
from scanner import Alert


def esc(text: str) -> str:
    return escape(str(text), quote=False)


def format_alert(alert: Alert, interval_minutes: int) -> str:
    arrow = "📈" if alert.is_up else "📉"
    verb = "wzrosła" if alert.is_up else "spadła"
    return (
        f"🚨 <b>UWAGA:</b> {esc(alert.symbol)} {verb} o "
        f"<b>{alert.pct_change:+.2f}%</b> w ciągu {interval_minutes} min!\n"
        f"{arrow} {alert.previous:.2f} → <b>{alert.current:.2f}</b> USD"
    )


def format_daily_report(items: list[tuple[Gainer, list[Headline]]], ai_text: str) -> str:
    today = date.today().isoformat()
    lines = [
        "📊 <b>Poranny raport — Top Gainers (US)</b>",
        f"<i>{today}</i>",
        "",
    ]

    if not items:
        lines.append("Nie udało się pobrać listy największych wzrostów. Spróbuj później.")
        return "\n".join(lines)

    for idx, (gainer, _headlines) in enumerate(items, start=1):
        lines.append(
            f"{idx}. <b>{esc(gainer.symbol)}</b> "
            f"({esc(gainer.name)}) — <b>{gainer.percent_change:+.2f}%</b> "
            f"@ {gainer.price:.2f} USD"
        )

    lines.append("")
    lines.append("🤖 <b>Analiza AI — dlaczego rosną?</b>")
    lines.append(esc(ai_text))

    return "\n".join(lines)
