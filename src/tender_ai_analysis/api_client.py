"""Cliente HTTP hacia tender-api: leer licitaciones pendientes y publicar el score."""

from __future__ import annotations

import httpx

from tender_ai_analysis.config import settings
from tender_ai_analysis.scoring import ScoreResult


class ApiClient:
    def __init__(self, base_url: str | None = None, *, timeout: float = 30.0) -> None:
        self.base_url = (base_url or settings.api_url).rstrip("/")
        self.timeout = timeout

    def _client(self) -> httpx.Client:
        """Crea el cliente httpx. Monkeypatcheable en tests."""
        return httpx.Client(base_url=self.base_url, timeout=self.timeout)

    def list_pending(self, *, status: str = "discovered", limit: int = 50) -> list[dict]:
        with self._client() as client:
            resp = client.get("/api/tenders", params={"status": status, "limit": limit})
            resp.raise_for_status()
            return resp.json()

    def put_score(self, tender_id: str, result: ScoreResult) -> dict:
        payload = {
            "total": result.total,
            "breakdown": result.breakdown.model_dump(),
            "recommendation": result.recommendation.value,
            "hard_rules": result.hard_rules,
            "factors": [f.model_dump() for f in result.factors],
            "model_version": settings.score_model_version,
        }
        with self._client() as client:
            resp = client.put(f"/api/tenders/{tender_id}/score", json=payload)
            resp.raise_for_status()
            return resp.json()
