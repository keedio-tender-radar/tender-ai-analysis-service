"""Chat documental: síntesis de una respuesta anclada a los fragmentos del pliego.

RAG por expediente (ADR-004): la API recupera los fragmentos relevantes de UN expediente y este
módulo redacta la respuesta citando SOLO ese contexto. Con LLM (OpenRouter) genera prosa con citas
`[n]`; sin key, cae a un modo extractivo que devuelve el fragmento más relevante.
"""

from __future__ import annotations

from pydantic import BaseModel

from tender_ai_analysis import llm


class AnswerResult(BaseModel):
    answer: str = ""
    grounded: bool = False  # True si la respuesta la generó el LLM sobre el contexto
    generated_by: str = "rule-based"


_SYSTEM = (
    "Eres un asistente que responde preguntas sobre el pliego de UNA licitación pública, para el "
    "equipo de Keedio. Responde EXCLUSIVAMENTE con la información del contexto numerado que se te "
    "da; no inventes ni uses conocimiento externo. Cita las fuentes usadas con su número entre "
    "corchetes, p. ej. [1] o [2]. Si el contexto no contiene la respuesta, dilo con claridad "
    "('El pliego facilitado no especifica…'). Responde en español, de forma concisa y concreta."
)


def _format_context(chunks: list[dict]) -> str:
    parts = []
    for c in chunks:
        n = c.get("n")
        section = c.get("section")
        header = f"[{n}]" + (f" ({section})" if section else "")
        parts.append(f"{header}\n{(c.get('content') or '').strip()}")
    return "\n\n".join(parts)


def _fallback(chunks: list[dict]) -> AnswerResult:
    """Sin LLM: devuelve el fragmento más relevante (ya vienen ordenados por relevancia)."""
    if not chunks:
        return AnswerResult(answer="No hay fragmentos del pliego para responder.", grounded=False)
    top = chunks[0]
    n = top.get("n")
    text = (top.get("content") or "").strip()[:800]
    return AnswerResult(answer=f"{text}\n\n[{n}]", grounded=False, generated_by="rule-based")


def answer(question: str, chunks: list[dict], client_factory=None) -> AnswerResult:
    """Redacta la respuesta a `question` anclada a `chunks` (cada uno con n/section/content)."""
    from tender_ai_analysis.config import settings

    if not chunks:
        return AnswerResult(
            answer="El pliego facilitado no contiene información para responder.", grounded=False
        )
    if not settings.openrouter_api_key and client_factory is None:
        return _fallback(chunks)

    user = f"Pregunta: {question}\n\nContexto del pliego (numerado):\n{_format_context(chunks)}\n"
    res = llm.call_text(_SYSTEM, user, client_factory=client_factory)
    if res is None:
        return _fallback(chunks)
    text, model = res
    return AnswerResult(answer=text, grounded=True, generated_by=f"llm:{model}")
