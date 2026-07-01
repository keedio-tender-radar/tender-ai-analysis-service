"""Conector de ADJUDICACIONES TED v3 (notas de formalización, `notice-type=can-standard`).

Inteligencia de mercado (MVP-5): quién gana qué y a qué baja. TED v3 search es POST sin auth.
Los campos de ganador/importe adjudicado en eForms son por lote y su nombre varía; el parseo es
**best-effort**: si un campo no viene, queda en None (la analítica lo tolera). Con datos reales
puede haber que afinar los nombres de campo en `_FIELDS`/`_pick`.
"""

from __future__ import annotations

import json

import httpx

from tender_ingestion.config import settings

from .base_connector import BaseConnector
from .ted_connector import _html_url, _ml

# Campos solicitados (superset best-effort: TED varía los nombres de ganador/valor por versión).
_FIELDS = [
    "publication-number",
    "notice-title",
    "buyer-name",
    "classification-cpv",
    "total-value",
    "winner-name",
    "organisation-name-serv-prov",
    "awarded-value",
    "result-value",
    "publication-date",
    "links",
]


def _num(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, dict):  # {amount, currency} u otras formas
        for k in ("amount", "value"):
            if k in value:
                return _num(value[k])
        return None
    if isinstance(value, list):
        return _num(value[0]) if value else None
    try:
        return float(str(value).replace(",", "."))
    except (ValueError, TypeError):
        return None


def _pick(notice: dict, *keys):
    """Primer valor no vacío entre varias claves alternativas (nombres de campo varían)."""
    for k in keys:
        if k in notice and notice[k]:
            return notice[k]
    return None


class TedAwardsConnector(BaseConnector):
    name = "ted"

    def __init__(self, url: str, *, query: str | None = None, limit: int | None = None) -> None:
        super().__init__(url)
        self.query = query or settings.ted_awards_query
        self.limit = limit or settings.ted_awards_limit

    def fetch_raw(self) -> str:
        body = {
            "query": self.query,
            "fields": _FIELDS,
            "page": 1,
            "limit": self.limit,
            "scope": settings.ted_awards_scope,
        }
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(self.url, json=body, headers={"Accept": "application/json"})
            resp.raise_for_status()
            return resp.text

    def parse(self, raw: str) -> list[dict]:
        data = json.loads(raw)
        notices = data.get("notices") or []
        results: list[dict] = []
        for n in notices:
            pub = str(n.get("publication-number") or "")
            supplier = _ml(_pick(n, "winner-name", "organisation-name-serv-prov"))
            awarded = _num(_pick(n, "awarded-value", "result-value"))
            budget = _num(n.get("total-value"))
            results.append(
                {
                    "source": "ted",
                    "source_id": pub,
                    "title": _ml(n.get("notice-title")),
                    "buyer": _ml(n.get("buyer-name")),
                    "cpv": n.get("classification-cpv") or [],
                    "budget_amount": budget,
                    "awarded_amount": awarded,
                    "awarded_supplier": supplier,
                    "num_bidders": None,
                    "award_date": (n.get("publication-date") or "")[:10] or None,
                    "url": _html_url(n.get("links"), pub),
                }
            )
        return results
