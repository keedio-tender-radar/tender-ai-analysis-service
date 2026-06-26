"""Configuración del servicio de ingesta.

Las listas (CPV/keywords) son una base inicial alineada con keedio-company-profile.md; se
pueden sobreescribir por variables de entorno separadas por comas.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


def _csv(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


class Settings(BaseSettings):
    app_name: str = "tender-ingestion-service"
    version: str = "0.1.0"

    # Backend al que se publican las licitaciones.
    api_url: str = "http://localhost:8000"

    # Token opcional para proteger POST /run (el scheduler envía X-Run-Token).
    run_token: str = ""

    # Fuentes.
    # Open data de PLACSP (sin certificado). El feed agregado publica todas las licitaciones.
    placsp_feed_url: str = (
        "https://contrataciondelestado.es/sindicacion/sindicacion_1044/"
        "PlataformasAgregadasSinMenores.atom"
    )
    ted_api_url: str = "https://api.ted.europa.eu/v3/notices/search"
    # Consulta en sintaxis "expert" de TED v3 (POST). Por defecto: anuncios de licitación
    # ABIERTOS (cn-standard, no adjudicaciones) de TI+software en España, últimos 30 días,
    # más recientes primero. Ajustable por entorno (TED_QUERY).
    ted_query: str = (
        "classification-cpv IN (72000000 48000000) AND place-of-performance IN (ESP) "
        "AND notice-type IN (cn-standard) AND publication-date>=today(-30) "
        "SORT BY publication-date DESC"
    )
    ted_scope: str = "ACTIVE"
    ted_limit: int = 50

    # Filtros (CPV por prefijo). Coma-separados en env: CPV_PREFERRED="72,48".
    cpv_preferred: str = "72,48"
    cpv_excluded: str = "45,90,79710000"

    keywords_positive: str = (
        "datos,big data,analítica,inteligencia artificial,machine learning,integración,"
        "api,cloud,kubernetes,devops,plataforma,rag,etl"
    )
    keywords_negative: str = (
        "obra civil,construcción,limpieza,vigilancia,catering,jardinería,mobiliario,transporte"
    )

    # Portales extra configurables (autonómicos/sectoriales). Lista JSON; vacío = ninguno.
    extra_portal_feeds_json: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def cpv_preferred_list(self) -> list[str]:
        return _csv(self.cpv_preferred)

    @property
    def cpv_excluded_list(self) -> list[str]:
        return _csv(self.cpv_excluded)

    @property
    def keywords_positive_list(self) -> list[str]:
        return _csv(self.keywords_positive.lower())

    @property
    def keywords_negative_list(self) -> list[str]:
        return _csv(self.keywords_negative.lower())


settings = Settings()
