"""Análisis IA del anuncio (resumen, requisitos, riesgos) con fallback rule-based.

Si hay LLM disponible (OpenRouter) enriquece el análisis; si no, devuelve un análisis básico
derivado de los campos de la licitación. Las *pistas* (hints) son opcionales y, si existen,
afinan el scoring (solvencia/partner/riesgos). El scoring funciona con o sin LLM.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from tender_ai_analysis import llm


class AnalysisHints(BaseModel):
    """Pistas cualitativas que afinan el scoring (todas opcionales)."""

    solvency_risk: str | None = None  # low | medium | high
    partner_needed: bool | None = None
    contractual_risk: str | None = None  # low | medium | high
    incompatibility: bool | None = None


class AnalysisResult(BaseModel):
    summary: str = ""
    functional_requirements: list[str] = Field(default_factory=list)
    risks: list[dict] = Field(default_factory=list)
    hints: AnalysisHints = Field(default_factory=AnalysisHints)
    generated_by: str = "rule-based"


_SYSTEM = (
    "Eres un analista de licitaciones públicas para Keedio (datos, IA, integración, cloud). "
    "Dado el anuncio de una licitación, devuelve EXCLUSIVAMENTE un objeto JSON (sin markdown) "
    "con: summary (string), functional_requirements (array de strings), risks (array de "
    "objetos {risk, mitigation}), hints (objeto {solvency_risk: low|medium|high, partner_needed: "
    "bool, contractual_risk: low|medium|high, incompatibility: bool}). En español."
)


def _fallback(tender: dict) -> AnalysisResult:
    summary = (tender.get("summary") or tender.get("title") or "").strip()[:500]
    return AnalysisResult(summary=summary, generated_by="rule-based")


def analyze(tender: dict, document_text: str | None = None, client_factory=None) -> AnalysisResult:
    """Devuelve el análisis del anuncio; LLM si está disponible, si no rule-based.

    Si se aporta `document_text` (texto del pliego), se incluye un extracto en el prompt para un
    análisis más fundado.
    """
    from tender_ai_analysis.config import settings

    if not settings.openrouter_api_key and client_factory is None:
        return _fallback(tender)

    user = (
        f"Título: {tender.get('title', '')}\n"
        f"Resumen: {tender.get('summary', '')}\n"
        f"CPV: {', '.join(tender.get('cpv', []) or [])}\n"
        f"Presupuesto: {tender.get('budget_amount')}\n"
    )
    if document_text:
        user += f"\nExtracto del pliego:\n{document_text[:6000]}\n"
    data = llm.call_json(_SYSTEM, user, client_factory=client_factory)
    if data is None:
        return _fallback(tender)

    try:
        result = AnalysisResult(
            summary=data.get("summary") or _fallback(tender).summary,
            functional_requirements=data.get("functional_requirements") or [],
            risks=[r for r in (data.get("risks") or []) if isinstance(r, dict)],
            hints=AnalysisHints(**(data.get("hints") or {})),
            generated_by=f"llm:{data.get('_model', 'unknown')}",
        )
    except Exception:  # noqa: BLE001 — respuesta LLM malformada → fallback
        return _fallback(tender)
    return result
