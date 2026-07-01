"""Cliente HTTP hacia tender-api para publicar adjudicaciones (inteligencia de mercado)."""

from __future__ import annotations

import httpx


class AwardsPublisher:
    def __init__(self, base_url: str, *, run_token: str = "", timeout: float = 60.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.run_token = run_token
        self.timeout = timeout

    def _client(self) -> httpx.Client:
        """Crea el cliente httpx. Monkeypatcheable en tests."""
        headers = {"X-Run-Token": self.run_token} if self.run_token else {}
        return httpx.Client(base_url=self.base_url, timeout=self.timeout, headers=headers)

    def publish(self, awards: list[dict]) -> dict:
        """POST /api/market/awards (upsert idempotente por source+source_id)."""
        with self._client() as client:
            resp = client.post("/api/market/awards", json=awards)
            resp.raise_for_status()
            return resp.json()
