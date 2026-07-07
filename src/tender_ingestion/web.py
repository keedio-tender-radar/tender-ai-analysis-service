"""Envoltura HTTP para disparar la ingesta desde un scheduler (InsForge schedules).

`POST /run` ejecuta el job de ingesta una vez. Si `RUN_TOKEN` está definido, exige el header
`X-Run-Token`. El job en sí está en jobs/daily_ingestion_job.py (reutilizado).
"""

from __future__ import annotations

from fastapi import Depends, FastAPI, Header, HTTPException

from tender_ingestion.config import settings
from tender_ingestion.jobs.daily_ingestion_job import run_ingestion
from tender_ingestion.main import build_filter_config, build_sources
from tender_ingestion.publishers.api_client import ApiClient

app = FastAPI(title=settings.app_name, version=settings.version)


def _auth(x_run_token: str | None = Header(default=None)) -> None:
    if settings.run_token and x_run_token != settings.run_token:
        raise HTTPException(status_code=401, detail="Token de ejecución inválido o ausente.")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": settings.app_name, "version": settings.version}


@app.post("/run", dependencies=[Depends(_auth)])
def run() -> dict:
    api = ApiClient(settings.api_url)
    result = run_ingestion(build_sources(), api, build_filter_config())
    # Reporta a observabilidad: status=error si alguna fuente falló → dispara alerta Telegram.
    try:
        api.report_run(
            "ingestion",
            "error" if result.errors else "ok",
            detail="; ".join(result.errors)[:500] or None,
            count=result.published,
            run_token=settings.run_token,
        )
    except Exception:  # noqa: BLE001 — el reporte no debe tumbar la respuesta de la ingesta
        pass
    return {
        "fetched": result.fetched,
        "relevant": result.relevant,
        "published": result.published,
        "duplicates": result.duplicates,
        "filtered_out": result.filtered_out,
        "errors": result.errors,
    }
