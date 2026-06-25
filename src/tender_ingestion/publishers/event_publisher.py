"""Publicación de eventos de dominio (MVP: log).

Usa el contrato `DomainEvent` de tender-shared-contracts. En el MVP solo registra; cuando exista
un bus (Redis Streams, etc.) este es el punto donde emitir.
"""

from __future__ import annotations

import logging

from tender_contracts import DomainEvent, EventType, make_event

logger = logging.getLogger("tender_ingestion.events")


def emit(event_type: EventType, tender_id: str, **payload: object) -> DomainEvent:
    event = make_event(
        event_type, tender_id, producer="tender-ingestion-service", **payload
    )
    logger.info("event %s tender=%s", event.event_type, tender_id)
    return event
