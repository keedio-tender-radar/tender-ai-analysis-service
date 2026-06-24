"""Punto de entrada: analiza y puntúa las licitaciones pendientes.

Uso:  python -m tender_ai_analysis.main   (one-shot; programado por cron/scheduler en infra).
"""

from __future__ import annotations

import logging

from tender_ai_analysis.api_client import ApiClient
from tender_ai_analysis.job import run
from tender_ai_analysis.profile import from_settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger("tender_ai_analysis")


def main() -> None:
    result = run(ApiClient(), from_settings())
    logger.info(
        "análisis: processed=%d scored=%d go=%d errors=%d",
        result.processed,
        result.scored,
        result.go,
        len(result.errors),
    )
    for err in result.errors:
        logger.warning("error: %s", err)


if __name__ == "__main__":
    main()
