"""Job de ingesta de adjudicaciones (inteligencia de mercado, MVP-5).

Descarga notas de formalización (TED), las publica idempotentemente en tender-api y devuelve
estadísticas. Un conector caído se aísla (no tumba el job).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from tender_ingestion.connectors.base_connector import BaseConnector
from tender_ingestion.publishers.awards_publisher import AwardsPublisher


@dataclass
class AwardsResult:
    fetched: int = 0
    published: int = 0
    created: int = 0
    updated: int = 0
    errors: list[str] = field(default_factory=list)


def run_awards(connectors: list[BaseConnector], publisher: AwardsPublisher) -> AwardsResult:
    """Ejecuta la ingesta de adjudicaciones de todas las fuentes."""
    result = AwardsResult()
    batch: list[dict] = []
    for connector in connectors:
        try:
            for award in connector.fetch():
                result.fetched += 1
                if award.get("source_id"):
                    batch.append(award)
        except Exception as exc:  # noqa: BLE001 — fuente caída aislada
            result.errors.append(f"{connector.name}: {type(exc).__name__}: {exc}")

    if batch:
        try:
            res = publisher.publish(batch)
            result.published = res.get("total", len(batch))
            result.created = res.get("created", 0)
            result.updated = res.get("updated", 0)
        except Exception as exc:  # noqa: BLE001
            result.errors.append(f"publish: {type(exc).__name__}: {exc}")
    return result
