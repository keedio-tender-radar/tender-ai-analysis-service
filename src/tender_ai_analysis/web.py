"""Envoltura HTTP para disparar el análisis+scoring desde un scheduler (InsForge schedules).

`POST /run` analiza y puntúa las licitaciones pendientes una vez. Si `RUN_TOKEN` está definido,
exige el header `X-Run-Token`. El job está en job.py (reutilizado).
"""

from __future__ import annotations

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from tender_ai_analysis import analysis as analysis_mod
from tender_ai_analysis.api_client import ApiClient
from tender_ai_analysis.config import settings
from tender_ai_analysis.job import run
from tender_ai_analysis.profile import from_settings
from tender_ai_analysis.scoring import score as score_tender

app = FastAPI(title=settings.app_name, version=settings.version)


class AnalyzeRequest(BaseModel):
    tender: dict = Field(default_factory=dict)
    document_text: str | None = None


def _auth(x_run_token: str | None = Header(default=None)) -> None:
    if settings.run_token and x_run_token != settings.run_token:
        raise HTTPException(status_code=401, detail="Token de ejecución inválido o ausente.")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": settings.app_name, "version": settings.version}


@app.post("/analyze", dependencies=[Depends(_auth)])
def analyze_one(payload: AnalyzeRequest) -> dict:
    """Analiza y puntúa una licitación concreta, opcionalmente con el texto del pliego."""
    analysis = analysis_mod.analyze(payload.tender, document_text=payload.document_text)
    result = score_tender(payload.tender, analysis, from_settings(), payload.document_text)
    return {
        "analysis": {
            "summary": analysis.summary,
            "generated_by": analysis.generated_by,
        },
        "score": {
            "total": result.total,
            "breakdown": result.breakdown.model_dump(),
            "recommendation": result.recommendation.value,
            "hard_rules": result.hard_rules,
            "factors": [f.model_dump() for f in result.factors],
        },
        "used_document": bool(payload.document_text),
    }


@app.post("/run", dependencies=[Depends(_auth)])
def run_analysis() -> dict:
    result = run(ApiClient(), from_settings())
    return {
        "processed": result.processed,
        "scored": result.scored,
        "go": result.go,
        "errors": result.errors,
    }
