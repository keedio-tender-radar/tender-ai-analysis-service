"""Generación de borradores de oferta a partir de la licitación + pliego (LLM con fallback).

Documentos deterministas (Go/No-Go, checklist) se construyen sin LLM; los redactados (resumen
ejecutivo, memoria técnica, matriz de cumplimiento) usan OpenRouter y caen a plantilla si no hay
clave o el LLM falla. La presentación final SIEMPRE requiere revisión humana.
"""

from __future__ import annotations

import re

from tender_ai_analysis import llm
from tender_ai_analysis.config import settings

# Palabras que delatan los requisitos REALES del pliego (suelen ir en el PPT, no al principio).
_REQ_KEYWORDS = (
    "solvencia", "criterio", "prescripci", "requisit", "técnic", "tecnic", "adjudicaci",
    "puntuaci", "valoraci", "plazo", "penalizaci", "obligaci", "experiencia", "certificad",
    "cláusula", "clausula", "mejora", "umbral", "lote", "objeto del contrato", "presupuesto",
    "acreditar", "deberá", "debera", "exig",
)


def _relevant_pliego(text: str, max_chars: int = 26000) -> str:
    """Selecciona las secciones del pliego con más carga de requisitos (no solo el principio).

    Los pliegos empiezan por la parte administrativa (PCAP); los requisitos técnicos y de solvencia
    reales suelen ir después. Truncar por el principio los deja fuera. Aquí se conserva el objeto
    (cabecera) y se priorizan los bloques densos en requisitos de TODO el documento.
    """
    if len(text) <= max_chars:
        return text
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
    if len(blocks) <= 3:
        return text[:max_chars]
    head, budget = [], max_chars
    for b in blocks[:3]:  # el objeto/introducción siempre entra
        head.append(b)
        budget -= len(b) + 2
    scored = []
    for i, b in enumerate(blocks[3:], start=3):
        low = b.lower()
        s = sum(low.count(k) for k in _REQ_KEYWORDS)
        if s:
            scored.append((s, i, b))
    scored.sort(key=lambda x: (-x[0], x[1]))
    picked: dict[int, str] = {}
    for _s, i, b in scored:
        if budget - len(b) - 2 < 0:
            continue
        picked[i] = b
        budget -= len(b) + 2
        if budget < 500:
            break
    ordered = head + [picked[i] for i in sorted(picked)]  # reordena por posición original
    return "\n\n".join(ordered)[:max_chars]

# Un documento por llamada de TEXTO (no JSON): pedir 3 markdown en un solo JSON hacía que
# `json.loads` fallara con saltos de línea/tablas → se caía a plantilla genérica (memoria "no según
# el pliego"). Con call_text cada documento es independiente y anclado al pliego.
_DRAFT_SYSTEM = (
    "Eres consultor de ofertas a licitaciones públicas para Keedio (datos, IA, integración, "
    "cloud, ciberseguridad). Redacta en español, concreto y basado EXCLUSIVAMENTE en el anuncio y "
    "el pliego proporcionados (no inventes datos que no consten). Recoge las cifras, plazos, "
    "umbrales, criterios de adjudicación con su ponderación y requisitos de solvencia TAL COMO "
    "aparecen en el pliego, citando el apartado o cláusula cuando sea posible. Si un dato no "
    "consta en el texto, escribe «no especificado en el pliego» en vez de inventarlo. Devuelve "
    "SOLO el documento pedido en markdown, sin texto introductorio ni explicaciones alrededor."
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
        "cada apartado referencia los requisitos concretos del pliego que cubre. "
        "INCLUYE DOS diagramas en bloques de código ```mermaid VÁLIDOS y anclados a la solución: "
        "(1) en 'Arquitectura', un `flowchart LR` con los componentes y flujos de datos de la "
        "solución propuesta para este pliego; (2) en 'Plan de trabajo', un `flowchart TD` con las "
        "FASES del proyecto en orden. Usa identificadores simples (A, B, C…) y etiquetas entre "
        "corchetes `[Texto]`; evita comillas, paréntesis y acentos dentro de las etiquetas para "
        "no romper la sintaxis Mermaid.",
    ),
    (
        "matriz_cumplimiento",
        "Matriz de cumplimiento",
        "Genera la MATRIZ DE CUMPLIMIENTO como tabla markdown con columnas EXACTAMENTE "
        "`| Requisito | Cumple | Evidencia |`, una fila por cada requisito REAL del pliego "
        "(técnicos, de solvencia y administrativos), lo más exhaustiva posible; en 'Evidencia' "
        "indica cómo lo cubre Keedio. Devuelve SOLO la tabla.",
    ),
    (
        "documentos_requeridos",
        "Documentos exigidos por el pliego",
        "Extrae del pliego la LISTA de documentos que hay que APORTAR en la oferta de ESTA "
        "licitación (sobre administrativo, técnico y económico): declaraciones responsables / "
        "DEUC, poderes, certificados (ISO, ROLECE, AEAT, Seg. Social), acreditación de solvencia "
        "técnica y económica CON SUS UMBRALES concretos, avales/garantías con su importe, modelos "
        "oficiales de oferta, y cualquier anexo exigido. Devuelve SOLO una lista markdown con "
        "viñetas; en cada una el documento y, si consta, su requisito/umbral exacto. No inventes "
        "documentos que no consten en el pliego.",
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


def _incumbent_line(market: dict | None) -> str | None:
    """Línea de incumbente (adjudicatario del último contrato del órgano), o None si no hay."""
    inc = (market or {}).get("incumbent")
    if not inc or not inc.get("supplier"):
        return None
    extra = f", {inc['award_date']}" if inc.get("award_date") else ""
    return f"- **Incumbente a batir (último contrato del órgano):** {inc['supplier']}{extra}"


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
        lines.append(_incumbent_line(market))
        return "\n".join(line for line in lines if line is not None)

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
    conc = (market or {}).get("concentration") or {}
    if conc.get("label"):
        lines.append(
            f"- **Concentración del mercado:** {conc['label']} "
            f"({conc.get('competitors')} competidores) — "
            + (
                "abierto, hay hueco para entrar."
                if conc["label"] == "fragmentado"
                else "dominado por pocos; incumbente fuerte."
            )
        )
    inc_line = _incumbent_line(market)
    if inc_line:
        lines.append(inc_line)
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
    if kind == "documentos_requeridos":
        return (
            "# Documentos exigidos por el pliego\n\n"
            "_Pendiente de extraer del pliego (analiza el pliego para obtener la lista concreta)._"
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
        relevant = _relevant_pliego(document_text)
        context += f"\nTexto del pliego (secciones relevantes):\n{relevant}\n"

    use_llm = settings.openrouter_api_key or client_factory is not None
    for kind, title, instruction in _LLM_DRAFTS:
        body = None
        if use_llm:
            res = llm.call_text(_DRAFT_SYSTEM, f"{context}\n\n{instruction}", client_factory)
            if res:
                body = res[0]
        drafts.append({"kind": kind, "title": title, "content": body or _template(kind, tender)})
    return drafts
