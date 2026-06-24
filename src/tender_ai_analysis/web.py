"""Envoltura HTTP para disparar el análisis+scoring desde un scheduler (InsForge schedules).

`POST /run` analiza y puntúa las licitaciones pendientes una vez. Si `RUN_TOKEN` está definido,
exige el header `X-Run-Token`. El job está en job.py (reutilizado).
"""

from __future__ import annotations

from fastapi import Depends, FastAPI, Header, HTTPException

from tender_ai_analysis.api_client import ApiClient
from tender_ai_analysis.config import settings
from tender_ai_analysis.job import run
from tender_ai_analysis.profile import from_settings

app = FastAPI(title=settings.app_name, version=settings.version)


def _auth(x_run_token: str | None = Header(default=None)) -> None:
    if settings.run_token and x_run_token != settings.run_token:
        raise HTTPException(status_code=401, detail="Token de ejecución inválido o ausente.")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": settings.app_name, "version": settings.version}


@app.post("/run", dependencies=[Depends(_auth)])
def run_analysis() -> dict:
    result = run(ApiClient(), from_settings())
    return {
        "processed": result.processed,
        "scored": result.scored,
        "go": result.go,
        "errors": result.errors,
    }
