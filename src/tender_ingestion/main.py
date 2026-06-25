"""Punto de entrada del servicio de ingesta.

Ejecuta el job de ingesta diaria contra las fuentes configuradas y publica en tender-api.
Uso:  python -m tender_ingestion.main   (o vía el job programado / cron en infra).
"""

from __future__ import annotations

import logging

from tender_ingestion.config import settings
from tender_ingestion.connectors.placsp_connector import PlacspConnector
from tender_ingestion.connectors.ted_connector import TedConnector
from tender_ingestion.jobs.daily_ingestion_job import (
    FilterConfig,
    Source,
    run_ingestion,
)
from tender_ingestion.normalizers import placsp_normalizer, ted_normalizer
from tender_ingestion.publishers.api_client import ApiClient

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger("tender_ingestion")


def build_sources() -> list[Source]:
    return [
        Source(PlacspConnector(settings.placsp_feed_url), placsp_normalizer.normalize),
        Source(TedConnector(settings.ted_api_url), ted_normalizer.normalize),
    ]


def build_filter_config() -> FilterConfig:
    return FilterConfig(
        cpv_preferred=settings.cpv_preferred_list,
        cpv_excluded=settings.cpv_excluded_list,
        keywords_positive=settings.keywords_positive_list,
        keywords_negative=settings.keywords_negative_list,
    )


def main() -> None:
    api = ApiClient(settings.api_url)
    result = run_ingestion(build_sources(), api, build_filter_config())
    logger.info(
        "ingesta: fetched=%d relevant=%d published=%d duplicates=%d filtered=%d errors=%d",
        result.fetched,
        result.relevant,
        result.published,
        result.duplicates,
        result.filtered_out,
        len(result.errors),
    )
    for err in result.errors:
        logger.warning("error: %s", err)


if __name__ == "__main__":
    main()
