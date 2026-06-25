"""Conector base.

Un conector sabe (1) descargar el contenido crudo de una fuente y (2) parsearlo a una lista
de entradas crudas (dicts). La separación permite testear `parse()` con fixtures sin red.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import httpx


class BaseConnector(ABC):
    name: str = "base"

    def __init__(self, url: str, *, timeout: float = 30.0) -> None:
        self.url = url
        self.timeout = timeout

    def fetch_raw(self) -> str:
        """Descarga el contenido crudo de la fuente. Sobreescribible/mockeable en tests."""
        headers = {"User-Agent": "KeedioTenderRadar/1.0 (+ingestion)", "Accept": "*/*"}
        with httpx.Client(timeout=self.timeout, follow_redirects=True, headers=headers) as client:
            resp = client.get(self.url)
            resp.raise_for_status()
            return resp.text

    @abstractmethod
    def parse(self, raw: str) -> list[dict]:
        """Convierte el contenido crudo en una lista de entradas (dicts) de la fuente."""

    def fetch(self) -> list[dict]:
        return self.parse(self.fetch_raw())
