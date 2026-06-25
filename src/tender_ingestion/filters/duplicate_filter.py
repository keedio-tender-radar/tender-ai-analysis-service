"""Deduplicación dentro de una ejecución por (source, source_id).

La deduplicación entre ejecuciones la garantiza la idempotencia de tender-api (upsert por
source+source_id); este filtro evita reprocesar la misma entrada dentro del mismo lote.
"""

from __future__ import annotations

from tender_ingestion.types import TenderPayload


class DuplicateFilter:
    def __init__(self) -> None:
        self._seen: set[tuple[str, str]] = set()

    def is_new(self, payload: TenderPayload) -> bool:
        key = (payload.source, payload.source_id)
        if key in self._seen:
            return False
        self._seen.add(key)
        return True
