"""Normaliza una entrada cruda de TED a TenderPayload."""

from __future__ import annotations

from tender_ingestion.normalizers import common_normalizer as cn
from tender_ingestion.types import TenderPayload


def normalize(raw: dict) -> TenderPayload:
    return TenderPayload(
        source="ted",
        source_id=str(raw.get("source_id") or "").strip(),
        title=(raw.get("title") or "").strip(),
        summary=(raw.get("summary") or None),
        cpv=cn.clean_cpv(raw.get("cpv") or []),
        buyer=(raw.get("buyer") or None),
        budget_amount=cn.to_float(raw.get("budget_amount")),
        currency="EUR",
        publication_date=cn.to_date(raw.get("publication_date")),
        deadline=cn.to_datetime(raw.get("deadline")),
        url=(raw.get("url") or None),
    )
