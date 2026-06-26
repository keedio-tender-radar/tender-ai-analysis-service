"""Normaliza una entrada ATOM genérica (portal extra) a TenderPayload."""

from __future__ import annotations

from tender_ingestion.normalizers import common_normalizer as cn
from tender_ingestion.types import TenderPayload


def normalize(raw: dict) -> TenderPayload:
    return TenderPayload(
        source=str(raw.get("source") or "portal").strip(),
        source_id=str(raw.get("source_id") or "").strip(),
        title=(raw.get("title") or "").strip(),
        summary=(raw.get("summary") or None),
        cpv=[],
        buyer=None,
        budget_amount=None,
        currency="EUR",
        publication_date=cn.to_date(raw.get("updated")),
        deadline=None,
        url=(raw.get("url") or None),
    )
