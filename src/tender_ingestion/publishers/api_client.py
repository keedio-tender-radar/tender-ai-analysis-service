"""Cliente HTTP hacia tender-api para publicar licitaciones."""

from __future__ import annotations

import httpx

from tender_ingestion.types import TenderPayload


class ApiClient:
    def __init__(self, base_url: str, *, timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _client(self) -> httpx.Client:
        """Crea el cliente httpx. Monkeypatcheable en tests."""
        return httpx.Client(base_url=self.base_url, timeout=self.timeout)

    def publish(self, payload: TenderPayload) -> dict:
        """POST /api/tenders (upsert idempotente). Devuelve la licitación creada/actualizada."""
        with self._client() as client:
            resp = client.post(
                "/api/tenders", json=payload.model_dump(mode="json")
            )
            resp.raise_for_status()
            return resp.json()
