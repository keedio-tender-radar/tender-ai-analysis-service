"""Configuración del servicio de análisis IA + scoring.

Incluye el perfil Keedio que alimenta el scoring (CPV/keywords/umbrales). Mismos valores base
que keedio-company-profile.md; sobreescribibles por entorno (coma-separados).
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


def _csv(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


class Settings(BaseSettings):
    app_name: str = "tender-ai-analysis-service"
    version: str = "0.1.0"

    api_url: str = "http://localhost:8000"
    score_model_version: str = "1.0.0"

    # Token opcional para proteger POST /run (el scheduler envía X-Run-Token).
    run_token: str = ""

    # LLM (OpenRouter). Sin key → análisis rule-based.
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_models: str = (
        "meta-llama/llama-3.3-70b-instruct:free,qwen/qwen3-next-80b-a3b-instruct:free"
    )

    # Perfil Keedio (scoring).
    cpv_preferred: str = "72,48"
    cpv_excluded: str = "45,90,79710000"
    keywords_positive: str = (
        "datos,big data,analítica,inteligencia artificial,machine learning,integración,"
        "api,cloud,kubernetes,devops,plataforma,rag,etl"
    )
    keywords_negative: str = (
        "obra civil,construcción,limpieza,vigilancia,catering,jardinería,mobiliario,transporte"
    )
    budget_min: float = 50000.0
    budget_target_low: float = 150000.0
    budget_target_high: float = 800000.0
    deadline_min_days: int = 7
    deadline_comfortable_days: int = 21

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
