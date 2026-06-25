"""Tipos del pipeline de ingesta."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class TenderPayload(BaseModel):
    """Licitación normalizada lista para publicar en tender-api (POST /api/tenders)."""

    source: str
    source_id: str
    title: str
    summary: str | None = None
    cpv: list[str] = Field(default_factory=list)
    buyer: str | None = None
    budget_amount: float | None = None
    currency: str = "EUR"
    publication_date: date | None = None
    deadline: datetime | None = None
    url: str | None = None
