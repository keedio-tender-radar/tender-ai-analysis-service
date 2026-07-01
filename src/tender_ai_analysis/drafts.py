"""Generación de borradores de oferta a partir de la licitación + pliego (LLM con fallback).

Documentos deterministas (Go/No-Go, checklist) se construyen sin LLM; los redactados (resumen
ejecutivo, memoria técnica, matriz de cumplimiento) usan OpenRouter y caen a plantilla si no hay
clave o el LLM falla. La presentación final SIEMPRE requiere revisión humana.
"""

from __future__ import annotations

from tender_ai_analysis import llm
from tender_ai_analysis.config import settings

# Un documento por llamada de TEXTO (no JSON): pedir 3 markdown en un solo JSON hacía que
# `json.loads` fallara con saltos de línea/tablas → se caía a plantilla genérica (memoria "no según
# el pliego"). Con call_text cada documento es independiente y anclado al pliego.
_DRAFT_SYSTEM = (
    "Eres consultor de ofertas a licitaciones públicas para Keedio (datos, IA, integración, "
    "cloud, ciberseguridad). Redacta en español, concreto y basado EXCLUSIVAMENTE en el anuncio y "
    "el pliego proporcionados (no inventes datos que no consten). Devuelve SOLO el documento "
    "pedido en markdown, sin texto introductorio ni explicaciones alrededor."
)

_LLM_DRAFTS = [
    (
        "resumen_ejecutivo",
        "Resumen ejecutivo",
        "Redacta el RESUMEN EJECUTIVO de la oferta (markdown). Incluye: objeto del contrato, "
        "PLAZOS CLAVE (presentación y ejecución), LOTES y presupuesto por lote si los hay, y "
        "CRITERIOS DE SOLVENCIA técnica y económica exigidos en el pliego.",
    ),
    (
        "memoria_tecnica",
        "Memoria técnica (esquema)",
        "Redacta un ESQUEMA DE MEMORIA TÉCNICA (markdown) alineado con los requisitos REALES del "
        "pliego (no genérico): objeto, metodología, arquitectura/solución propuesta, equipo, plan "
        "de trabajo y cronograma, plan de calidad, seguridad, pruebas y transición/soporte. En "
        "cada apartado referencia los requisitos concretos del pliego que cubre.",
    ),
    (
        "matriz_cumplimiento",
        "Matriz de cumplimiento",
        "Genera la MATRIZ DE CUMPLIMIENTO como tabla markdown con columnas EXACTAMENTE "
        "`| Requisito | Cumple | Evidencia |`, una fila por cada requisito REAL del pliego "
        "(técnicos, de solvencia y administrativos), lo más exhaustiva posible; en 'Evidencia' "
        "indica cómo lo cubre Keedio. Devuelve SOLO la tabla.",
    ),
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


def _market_strategy(tender: dict, score: dict | None, market: dict | None) -> str:
    """Estrategia de puja a partir de la inteligencia de mercado (baja esperada + competidores).

    Determinista: la baja esperada y los adjudicatarios vienen del histórico de adjudicaciones
    (MVP-5). Si no hay muestra de mercado para la categoría, lo indica y no inventa cifras.
    """
    lines = ["# Estrategia de puja", ""]
    budget = tender.get("budget_amount")
    baja = (market or {}).get("expected_baja")
    sample = (market or {}).get("sample_size") or 0

    if not market or sample == 0:
        lines.append(
            "Sin histórico de adjudicaciones para esta categoría CPV todavía; no hay baja de "
            "referencia. Fija la oferta económica según margen objetivo y coste estimado."
        )
        return "\n".join(lines)

    lines.append(f"- **Muestra de mercado:** {sample} adjudicaciones de la categoría "
                 f"CPV {market.get('cpv_division') or 's/d'}.")
    if baja is not None:
        lines.append(f"- **Baja media esperada:** {baja * 100:.1f}%")
    if budget and baja is not None:
        suggested = round(budget * (1 - baja), 2)
        cur = tender.get("currency", "EUR")
        budget_txt = f"{budget:,.0f}".replace(",", ".")
        suggested_txt = f"{suggested:,.0f}".replace(",", ".")
        lines.append(f"- **Presupuesto base:** {budget_txt} {cur}")
        lines.append(f"- **Puja sugerida (baja media):** ~{suggested_txt} {cur}")
        lines.append(
            "  > Referencia de partida: para competir por precio hay que igualar o superar la baja "
            "media; pondera con el margen objetivo y la solvencia técnica valorada."
        )
    winners = (market or {}).get("likely_winners") or []
    if winners:
        lines.append("")
        lines.append("## Quién suele ganar esto")
        for w in winners[:5]:
            b = w.get("avg_baja")
            baja_txt = f", baja media {b * 100:.1f}%" if b is not None else ""
            lines.append(f"- {w.get('supplier')} — {w.get('wins')} contrato(s){baja_txt}")
    if score and score.get("recommendation"):
        lines.append("")
        lines.append(f"_Recomendación del radar: {score.get('recommendation', '').upper()} "
                     f"({score.get('total', '?')}/100)._")
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
    tender: dict,
    document_text: str | None,
    score: dict | None,
    client_factory=None,
    market_context: dict | None = None,
) -> list[dict]:
    """Devuelve [{kind, title, content}] con los borradores de oferta.

    `market_context` (inteligencia de mercado, MVP-5) añade una estrategia de puja determinista.
    """
    drafts = [
        {"kind": "go_no_go", "title": "Informe Go/No-Go", "content": _go_no_go(tender, score)},
        {"kind": "checklist_administrativo", "title": "Checklist administrativo",
         "content": _checklist()},
        {"kind": "estrategia_puja", "title": "Estrategia de puja",
         "content": _market_strategy(tender, score, market_context)},
    ]

    context = (
        f"Título: {tender.get('title', '')}\n"
        f"Resumen: {tender.get('summary', '')}\n"
        f"CPV: {', '.join(tender.get('cpv', []) or [])}\n"
        f"Presupuesto: {tender.get('budget_amount')}\n"
    )
    if document_text:
        context += f"\nTexto del pliego:\n{document_text[:14000]}\n"

    use_llm = settings.openrouter_api_key or client_factory is not None
    for kind, title, instruction in _LLM_DRAFTS:
        body = None
        if use_llm:
            res = llm.call_text(_DRAFT_SYSTEM, f"{context}\n\n{instruction}", client_factory)
            if res:
                body = res[0]
        drafts.append({"kind": kind, "title": title, "content": body or _template(kind, tender)})
    return drafts
