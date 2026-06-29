"""Generación de borradores de oferta a partir de la licitación + pliego (LLM con fallback).

Documentos deterministas (Go/No-Go, checklist) se construyen sin LLM; los redactados (resumen
ejecutivo, memoria técnica, matriz de cumplimiento) usan OpenRouter y caen a plantilla si no hay
clave o el LLM falla. La presentación final SIEMPRE requiere revisión humana.
"""

from __future__ import annotations

from tender_ai_analysis import llm
from tender_ai_analysis.config import settings

_SYSTEM = (
    "Eres consultor de ofertas a licitaciones públicas para Keedio (datos, IA, integración, "
    "cloud, ciberseguridad). Dado el anuncio y el texto del pliego, redacta borradores de oferta. "
    "Devuelve EXCLUSIVAMENTE un objeto JSON (sin markdown alrededor) con claves: "
    "resumen_ejecutivo, memoria_tecnica, matriz_cumplimiento. Todo en español, concreto, basado "
    "en el PLIEGO (no inventes). "
    "- resumen_ejecutivo (markdown): incluye objeto del contrato, PLAZOS CLAVE (presentación y "
    "ejecución), LOTES y presupuesto por lote si los hay, y CRITERIOS DE SOLVENCIA técnica y "
    "económica exigidos. "
    "- memoria_tecnica (markdown): esquema de propuesta alineado con los requisitos del pliego. "
    "- matriz_cumplimiento: tabla markdown con columnas EXACTAMENTE "
    "`| Requisito | Cumple | Evidencia |`, una fila por cada requisito REAL del pliego (técnicos, "
    "de solvencia y administrativos), lo más exhaustiva posible; en 'Evidencia' indica cómo lo "
    "cubre Keedio."
)

_LLM_DRAFTS = [
    ("resumen_ejecutivo", "Resumen ejecutivo"),
    ("memoria_tecnica", "Memoria técnica (esquema)"),
    ("matriz_cumplimiento", "Matriz de cumplimiento"),
]


def _go_no_go(tender: dict, score: dict | None) -> str:
    if not score:
        return "# Informe Go/No-Go\n\nSin score todavía. Ejecuta el scoring antes de decidir."
    lines = [
        "# Informe Go/No-Go",
        "",
        f"- **Licitación:** {tender.get('title', '')}",
        f"- **Recomendación:** {score.get('recommendation', '?').upper()}",
        f"- **Score:** {score.get('total', '?')}/100",
        f"- **Presupuesto:** {tender.get('budget_amount', 's/d')} {tender.get('currency', 'EUR')}",
        "",
        "## Factores",
    ]
    for f in score.get("factors", []):
        mark = "✅" if f.get("kind") == "positive" else "⚠️"
        lines.append(f"- {mark} {f.get('message', '')}")
    if score.get("hard_rules"):
        lines.append("")
        lines.append("## Reglas duras")
        lines.extend(f"- {r}" for r in score["hard_rules"])
    return "\n".join(lines)


def _checklist() -> str:
    items = [
        "Declaración responsable (DEUC si aplica)",
        "Poderes / representación",
        "Solvencia técnica (proyectos similares)",
        "Solvencia económica (cifra de negocio / seguros)",
        "Certificados (ROLECE, AEAT, Seguridad Social)",
        "Anexos y modelos firmados",
        "Oferta económica en el modelo oficial",
    ]
    return "# Checklist administrativo\n\n" + "\n".join(f"- [ ] {i}" for i in items)


def _template(kind: str, tender: dict) -> str:
    title = tender.get("title", "")
    if kind == "resumen_ejecutivo":
        return f"# Resumen ejecutivo\n\nPropuesta de Keedio para «{title}». (Pendiente.)"
    if kind == "memoria_tecnica":
        return (
            "# Memoria técnica (esquema)\n\n## Objeto\n## Metodología\n## Arquitectura\n"
            "## Equipo\n## Plan de trabajo y cronograma\n## Plan de calidad\n## Plan de seguridad\n"
            "## Plan de pruebas\n## Transición y soporte"
        )
    return "# Matriz de cumplimiento\n\n| Requisito | Cumple | Evidencia |\n|---|---|---|\n"


def generate_drafts(
    tender: dict, document_text: str | None, score: dict | None, client_factory=None
) -> list[dict]:
    """Devuelve [{kind, title, content}] con los borradores de oferta."""
    drafts = [
        {"kind": "go_no_go", "title": "Informe Go/No-Go", "content": _go_no_go(tender, score)},
        {"kind": "checklist_administrativo", "title": "Checklist administrativo",
         "content": _checklist()},
    ]

    user = (
        f"Título: {tender.get('title', '')}\n"
        f"Resumen: {tender.get('summary', '')}\n"
        f"CPV: {', '.join(tender.get('cpv', []) or [])}\n"
        f"Presupuesto: {tender.get('budget_amount')}\n"
    )
    if document_text:
        user += f"\nTexto del pliego:\n{document_text[:14000]}\n"

    data = None
    if settings.openrouter_api_key or client_factory is not None:
        data = llm.call_json(_SYSTEM, user, client_factory)

    for kind, title in _LLM_DRAFTS:
        content = (data or {}).get(kind)
        body = str(content) if content else _template(kind, tender)
        drafts.append({"kind": kind, "title": title, "content": body})
    return drafts
