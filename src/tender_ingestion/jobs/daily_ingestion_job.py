"""Job de ingesta diaria: fuentes → normalizar → filtrar → deduplicar → publicar.

Diseñado para ser testeable: recibe las fuentes (conector + normalizador) y el cliente de API,
de modo que en tests se inyectan dobles sin red.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from tender_ingestion.connectors.base_connector import BaseConnector
from tender_ingestion.filters import cpv_filter, keyword_filter
from tender_ingestion.filters.duplicate_filter import DuplicateFilter
from tender_ingestion.types import TenderPayload

logger = logging.getLogger("tender_ingestion")

Normalizer = Callable[[dict], TenderPayload]


@dataclass
class Source:
    connector: BaseConnector
    normalize: Normalizer


@dataclass
class IngestionResult:
    fetched: int = 0
    duplicates: int = 0
    filtered_out: int = 0
    relevant: int = 0
    published: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class FilterConfig:
    cpv_preferred: list[str]
    cpv_excluded: list[str]
    keywords_positive: list[str]
    keywords_negative: list[str]


def _fetch_with_retry(connector: BaseConnector, attempts: int, delay: float) -> list[dict]:
    """Fetch con reintentos y backoff exponencial (absorbe fallos transitorios de la fuente).

    Reintenta ante cualquier excepción; agotados los intentos, propaga la última (el llamador la
    registra como dead-letter). Con attempts=1 no reintenta (útil en tests).
    """
    last: Exception | None = None
    for i in range(max(1, attempts)):
        try:
            return connector.fetch()
        except Exception as exc:  # noqa: BLE001 — reintentable; se propaga si se agotan intentos
            last = exc
            if i < attempts - 1:
                wait = delay * (2**i)
                logger.warning(
                    "fetch %s falló (intento %d/%d): %s — reintento en %.1fs",
                    connector.name, i + 1, attempts, type(exc).__name__, wait,
                )
                time.sleep(wait)
    raise last  # type: ignore[misc]


def run_ingestion(
    sources: list[Source],
    api_client,
    cfg: FilterConfig,
    *,
    fetch_attempts: int = 3,
    retry_delay: float = 1.0,
) -> IngestionResult:
    result = IngestionResult()
    dedupe = DuplicateFilter()

    for source in sources:
        try:
            raws = _fetch_with_retry(source.connector, fetch_attempts, retry_delay)
        except Exception as exc:  # noqa: BLE001 — fuente caída tras reintentos → dead-letter
            result.errors.append(f"{source.connector.name}: fetch {type(exc).__name__}: {exc}")
            continue

        for raw in raws:
            result.fetched += 1
            try:
                payload = source.normalize(raw)
            except Exception as exc:  # noqa: BLE001
                result.errors.append(f"{source.connector.name}: normalize {type(exc).__name__}")
                continue

            if not payload.source_id or not payload.title:
                result.filtered_out += 1
                continue
            if not dedupe.is_new(payload):
                result.duplicates += 1
                continue
            if not cpv_filter.passes(payload, cfg.cpv_preferred, cfg.cpv_excluded):
                result.filtered_out += 1
                continue
            if not keyword_filter.passes(
                payload, cfg.keywords_positive, cfg.keywords_negative
            ):
                result.filtered_out += 1
                continue

            result.relevant += 1
            try:
                api_client.publish(payload)
                result.published += 1
            except Exception as exc:  # noqa: BLE001
                result.errors.append(f"{source.connector.name}: publish {type(exc).__name__}")

    return result
