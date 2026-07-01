from __future__ import annotations

import logging

from google import genai

from config import settings
from market_data import Gainer
from news import Headline

logger = logging.getLogger(__name__)

_client = genai.Client(api_key=settings.gemini_api_key)

_SYSTEM_INSTRUCTION = (
    "Jesteś analitykiem rynku akcji. Na podstawie podanych nagłówków wiadomości "
    "wyjaśnij zwięźle i po polsku, DLACZEGO dana spółka dziś rośnie oraz czy zbliża "
    "się jakieś ważne wydarzenie (wyniki, produkt, przejęcie, decyzja regulatora). "
    "Dla każdej spółki napisz 2-3 zdania. Jeśli newsy nie tłumaczą wzrostu, napisz "
    "to wprost. Nie udzielaj porad inwestycyjnych i nie zmyślaj faktów spoza newsów."
)


def analyze_gainers(items: list[tuple[Gainer, list[Headline]]]) -> str:
    if not items:
        return "Brak danych do analizy."

    prompt = _build_prompt(items)
    try:
        response = _client.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config={"system_instruction": _SYSTEM_INSTRUCTION},
        )
        text = (response.text or "").strip()
        return text or "Model nie zwrócił treści analizy."
    except Exception as exc:
        logger.error("Gemini analysis failed: %s", exc)
        return f"⚠️ Analiza AI niedostępna ({type(exc).__name__}). Dane rynkowe powyżej są aktualne."


def _build_prompt(items: list[tuple[Gainer, list[Headline]]]) -> str:
    blocks: list[str] = [
        "Przeanalizuj poniższe spółki (dzisiejsze największe wzrosty na giełdzie US).",
        "Dla każdej podano zmianę procentową i najnowsze nagłówki.\n",
    ]
    for gainer, headlines in items:
        blocks.append(f"### {gainer.symbol} ({gainer.name}) — wzrost {gainer.percent_change:+.2f}%")
        if headlines:
            for h in headlines:
                line = f"- {h.title}"
                if h.summary:
                    # Trim summaries to save tokens against the free-tier limit.
                    line += f" — {h.summary[:200]}"
                blocks.append(line)
        else:
            blocks.append("- (brak dostępnych nagłówków)")
        blocks.append("")
    return "\n".join(blocks)
