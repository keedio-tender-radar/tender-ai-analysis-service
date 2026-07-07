"""Envoltura HTTP para disparar el análisis+scoring desde un scheduler (InsForge schedules).

`POST /run` analiza y puntúa las licitaciones pendientes una vez. Si `RUN_TOKEN` está definido,
exige el header `X-Run-Token`. El job está en job.py (reutilizado).
"""

from __future__ import annotations

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from tender_ai_analysis import analysis as analysis_mod
from tender_ai_analysis import answer as answer_mod
from tender_ai_analysis import drafts as drafts_mod
from tender_ai_analysis.api_client import ApiClient
from tender_ai_analysis.config import settings
from tender_ai_analysis.job import run
from tender_ai_analysis.profile import from_settings
from tender_ai_analysis.scoring import score as score_tender

app = FastAPI(title=settings.app_name, version=settings.version)


class AnalyzeRequest(BaseModel):
    tender: dict = Field(default_factory=dict)
    document_text: str | None = None


class DraftsRequest(BaseModel):
    tender: dict = Field(default_factory=dict)
    document_text: str | None = None
    score: dict | None = None
    market_context: dict | None = None  # inteligencia de mercado (MVP-5) → estrategia de puja
    buyer_profile: dict | None = None  # inteligencia del órgano → contexto de redacción


class AnswerRequest(BaseModel):
    """Pregunta + fragmentos numerados del pliego de UN expediente (RAG por expediente)."""

    question: str
    chunks: list[dict] = Field(default_factory=list)  # [{n, section, content}]


class EmbedRequest(BaseModel):
    texts: list[str] = Field(default_factory=list)


def _auth(x_run_token: str | None = Header(default=None)) -> None:
    if settings.run_token and x_run_token != settings.run_token:
        raise HTTPException(status_code=401, detail="Token de ejecución inválido o ausente.")


def _report_run(job: str, status: str, detail: str | None = None, count: int | None = None) -> None:
    """Reporta el resultado del job a tender-api (/api/runs) para observabilidad. Best-effort."""
    if not settings.api_url:
        return
    try:
        import httpx

        headers = {"X-Run-Token": settings.run_token} if settings.run_token else {}
        httpx.post(
            f"{settings.api_url.rstrip('/')}/api/runs",
            json={"job": job, "status": status, "detail": detail, "count": count},
            headers=headers,
            timeout=10,
        )
    except Exception:  # noqa: BLE001
        pass


@app.get("/health")
def health() -> dict:
    from tender_ai_analysis.llm import _models

    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.version,
        "llm_enabled": bool(settings.openrouter_api_key),
        "llm_models": _models() if settings.openrouter_api_key else [],
    }


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


@app.post("/generate-drafts", dependencies=[Depends(_auth)])
def generate_drafts(payload: DraftsRequest) -> dict:
    """Genera borradores de oferta (Go/No-Go, checklist, resumen, memoria, matriz)."""
    drafts = drafts_mod.generate_drafts(
        payload.tender, payload.document_text, payload.score,
        market_context=payload.market_context, buyer_profile=payload.buyer_profile,
    )
    return {"drafts": drafts}


@app.post("/embed", dependencies=[Depends(_auth)])
def embed_texts(payload: EmbedRequest) -> dict:
    """Embeddings de una lista de textos (OpenRouter). embeddings=null si está desactivado/falla."""
    from tender_ai_analysis.llm import embed

    return {"embeddings": embed(payload.texts), "model": settings.embedding_model or None}


@app.post("/answer", dependencies=[Depends(_auth)])
def answer_question(payload: AnswerRequest) -> dict:
    """Chat documental: redacta la respuesta anclada a los fragmentos del pliego, con citas [n]."""
    result = answer_mod.answer(payload.question, payload.chunks)
    return {
        "answer": result.answer,
        "grounded": result.grounded,
        "generated_by": result.generated_by,
    }


@app.post("/run", dependencies=[Depends(_auth)])
def run_analysis() -> dict:
    try:
        result = run(ApiClient(), from_settings())
    except Exception as exc:  # noqa: BLE001
        _report_run("analisis", "error", detail=f"{type(exc).__name__}: {exc}")
        raise
    _report_run(
        "analisis", "error" if result.errors else "ok",
        detail=f"{len(result.errors)} errores" if result.errors else None,
        count=result.scored,
    )
    return {
        "processed": result.processed,
        "scored": result.scored,
        "go": result.go,
        "errors": result.errors,
    }


@app.post("/run-awards", dependencies=[Depends(_auth)])
def run_awards_job() -> dict:
    """Ingesta de adjudicaciones (mercado): TED formalizaciones → tender-api /api/market/awards."""
    from tender_ingestion.config import settings as ing_settings
    from tender_ingestion.connectors.ted_awards_connector import TedAwardsConnector
    from tender_ingestion.jobs.awards_job import run_awards
    from tender_ingestion.publishers.awards_publisher import AwardsPublisher

    connectors = [TedAwardsConnector(ing_settings.ted_api_url)]
    publisher = AwardsPublisher(settings.api_url, run_token=settings.run_token)
    try:
        result = run_awards(connectors, publisher)
    except Exception as exc:  # noqa: BLE001
        _report_run("adjudicaciones", "error", detail=f"{type(exc).__name__}: {exc}")
        raise
    _report_run(
        "adjudicaciones", "error" if result.errors else "ok",
        detail=f"{len(result.errors)} errores" if result.errors else None,
        count=result.published,
    )
    return {
        "fetched": result.fetched,
        "published": result.published,
        "created": result.created,
        "updated": result.updated,
        "errors": result.errors,
    }


@app.post("/run-ingestion", dependencies=[Depends(_auth)])
def run_ingestion_job() -> dict:
    """Job de ingesta (fusionado en este servicio para ahorrar un slot de compute)."""
    from tender_ingestion.jobs.daily_ingestion_job import run_ingestion
    from tender_ingestion.main import build_filter_config, build_sources
    from tender_ingestion.publishers.api_client import ApiClient as IngestApiClient

    api = IngestApiClient(settings.api_url)
    try:
        result = run_ingestion(build_sources(), api, build_filter_config())
    except Exception as exc:  # noqa: BLE001
        _report_run("ingesta", "error", detail=f"{type(exc).__name__}: {exc}")
        raise
    _report_run(
        "ingesta", "error" if result.errors else "ok",
        detail=f"{len(result.errors)} errores" if result.errors else None,
        count=result.published,
    )
    return {
        "fetched": result.fetched,
        "relevant": result.relevant,
        "published": result.published,
        "duplicates": result.duplicates,
        "filtered_out": result.filtered_out,
        "errors": result.errors,
    }
