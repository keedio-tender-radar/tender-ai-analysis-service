"""Conector TED (Tenders Electronic Daily, UE) — API v3.

La API v3 de búsqueda es **POST** `/v3/notices/search` (sin auth) con una consulta en sintaxis
"expert". Devuelve `notices[]` con campos multilingües (`notice-title`, `buyer-name` como mapas
por idioma) y `total-value` numérico. El plazo no viene a nivel de nota (es por lote en eForms),
así que queda en None hasta enriquecer con el pliego.
"""

from __future__ import annotations

import json

import httpx

from tender_ingestion.config import settings

from .base_connector import BaseConnector

# Campos solicitados a la API (los que el normalizador necesita).
_FIELDS = [
    "publication-number",
    "notice-title",
    "buyer-name",
    "classification-cpv",
    "total-value",
    "publication-date",
    "links",
]

_PREFERRED_LANGS = ("spa", "eng")


def _ml(value) -> str | None:
    """Extrae un texto de un campo multilingüe TED ({lang: str} o {lang: [str]})."""
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, dict):
        keys = [*_PREFERRED_LANGS, *value.keys()]
        for k in keys:
            if k in value and value[k]:
                v = value[k]
                if isinstance(v, list):
                    v = v[0] if v else None
                return str(v).strip() if v else None
    return None


def _html_url(links: dict | None, pub: str) -> str:
    if isinstance(links, dict):
        for group in ("htmlDirect", "html"):
            g = links.get(group)
            if isinstance(g, dict):
                for lang in (*_PREFERRED_LANGS, *(g.keys())):
                    lang = lang.upper()
                    if lang in g and g[lang]:
                        return g[lang]
    return f"https://ted.europa.eu/es/notice/{pub}/html"


class TedConnector(BaseConnector):
    name = "ted"

    def __init__(self, url: str, *, query: str | None = None, limit: int | None = None) -> None:
        super().__init__(url)
        self.query = query or settings.ted_query
        self.limit = limit or settings.ted_limit

    def fetch_raw(self) -> str:
        body = {
            "query": self.query,
            "fields": _FIELDS,
            "page": 1,
            "limit": self.limit,
            "scope": settings.ted_scope,
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
            results.append(
                {
                    "source_id": pub,
                    "title": _ml(n.get("notice-title")),
                    "summary": None,
                    "url": _html_url(n.get("links"), pub),
                    "cpv": n.get("classification-cpv") or [],
                    "budget_amount": n.get("total-value"),
                    "buyer": _ml(n.get("buyer-name")),
                    "publication_date": n.get("publication-date"),
                    "deadline": None,
                }
            )
        return results
