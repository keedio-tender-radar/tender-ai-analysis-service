"""Filtro por keywords del perfil Keedio."""

from __future__ import annotations

from tender_ingestion.types import TenderPayload


def _text(payload: TenderPayload) -> str:
    return f"{payload.title or ''} {payload.summary or ''}".lower()


def passes(payload: TenderPayload, positive: list[str], negative: list[str]) -> bool:
    """True si la licitación es relevante por keywords.

    - Rechaza si tiene keyword negativa y ninguna positiva.
    - Acepta si tiene alguna keyword positiva.
    - Si no hay ninguna (ni positiva ni negativa) → rechaza (radar enfocado).
    """
    text = _text(payload)
    has_pos = any(k in text for k in positive)
    has_neg = any(k in text for k in negative)
    if has_pos:
        return True
    if has_neg:
        return False
    return False
