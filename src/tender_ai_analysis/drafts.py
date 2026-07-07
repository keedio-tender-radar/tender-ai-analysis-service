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
    "Eres consultor sénior de propuestas a licitaciones públicas para Keedio, consultora española "
    "de datos, IA, integración, cloud y ciberseguridad (ingeniería de datos, plataformas "
    "analíticas, MLOps, RAG, migración y modernización cloud, gobierno del dato y seguridad). "
    "Redactas documentos de NIVEL DE PRESENTACIÓN: desarrollados, minuciosos y persuasivos, en "
    "español profesional. NORMAS: (1) desarrolla cada apartado EN PROFUNDIDAD con prosa completa, "
    "nunca esquemas ni listas de titulares vacías; (2) ANCLA todo al pliego: recoge cifras, "
    "plazos, umbrales y criterios de adjudicación con su ponderación TAL COMO constan, citando el "
    "apartado o cláusula; (3) cuando el brief liste los CRITERIOS DE ADJUDICACIÓN, responde punto "
    "por punto a cada uno para MAXIMIZAR la puntuación, explicando cómo la solución de Keedio los "
    "satisface y supera; (4) tiene en cuenta el PERFIL DEL ÓRGANO y el MERCADO del brief para "
    "calibrar el enfoque y diferenciarse del incumbente; (5) NO inventes: si un dato no consta, "
    "escribe «no especificado en el pliego». Devuelve SOLO el documento en markdown, sin texto "
    "introductorio ni explicaciones alrededor."
)

_LLM_DRAFTS = [
    (
        "resumen_ejecutivo",
        "Resumen ejecutivo",
        "Redacta un RESUMEN EJECUTIVO persuasivo y de nivel de presentación (markdown, 3-5 "
        "párrafos desarrollados). Demuestra comprensión de la necesidad del órgano y presenta la "
        "PROPUESTA DE VALOR de Keedio: por qué es la mejor opción para ESTE contrato, con qué "
        "enfoque y qué diferenciadores frente al incumbente/competencia del brief. Cita objeto, "
        "plazos clave y lotes, y cómo la oferta cubre los criterios de adjudicación y la solvencia "
        "exigida. Anclado al pliego; concreto, no genérico.",
    ),
    (
        "memoria_tecnica",
        "Memoria técnica",
        "Redacta una MEMORIA TÉCNICA COMPLETA Y DESARROLLADA (markdown), de nivel de presentación, "
        "alineada con los requisitos REALES del pliego (nunca genérica ni un esquema): desarrolla "
        "EN PROFUNDIDAD, con prosa completa, objeto y comprensión de la necesidad, "
        "metodología, arquitectura/solución propuesta, equipo y perfiles, plan de trabajo y "
        "cronograma, plan de calidad, plan de seguridad, plan de pruebas y transición/soporte. "
        "ESTRUCTÚRALA para RESPONDER PUNTO POR PUNTO a cada criterio de adjudicación "
        "del brief (especialmente los de juicio de valor), explicando de forma concreta cómo la "
        "solución satisface y SUPERA cada criterio y sus umbrales de solvencia; incorpora "
        "mejoras que sumen puntos. Cita el apartado/cláusula del pliego al referenciar requisitos. "
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
    (
        "carta_presentacion",
        "Carta de presentación",
        "Redacta una CARTA DE PRESENTACIÓN formal (markdown) dirigida al órgano de contratación "
        "para acompañar la oferta. Incluye: encabezado con el órgano y el número de expediente, "
        "referencia al OBJETO concreto de esta licitación, un cuerpo que presente a Keedio "
        "(consultora de datos, IA, integración, cloud y ciberseguridad) y su idoneidad para este "
        "contrato, el compromiso con los plazos y la calidad, y un cierre cordial con fórmula de "
        "despedida. Tono profesional e institucional; usa los datos reales del pliego.",
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


def _strip_fence(text: str) -> str:
    """Quita el envoltorio ```markdown … ``` que el LLM añade a veces alrededor de TODA la
    respuesta y que rompe el render.

    Si la primera línea es una valla ```markdown/```md, es siempre un envoltorio → se quita
    aunque dentro haya diagramas ```mermaid (se preservan). Para otras etiquetas (o sin etiqueta)
    solo se quita si no hay vallas anidadas, para no romper un bloque de código legítimo."""
    t = (text or "").strip()
    if not (t.startswith("```") and t.endswith("```")):
        return text
    nl = t.find("\n")
    if nl == -1:
        return text
    tag = t[3:nl].strip().lower()
    inner = t[nl + 1 : -3]
    if tag in ("markdown", "md") or "```" not in inner:
        return inner.strip()
    return text


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
    if kind == "carta_presentacion":
        return (
            "# Carta de presentación\n\n"
            "A la atención del órgano de contratación,\n\n"
            f"Keedio presenta su oferta para «{title}». "
            "(Redacción pendiente: analiza el pliego para personalizarla.)"
        )
    return "# Matriz de cumplimiento\n\n| Requisito | Cumple | Evidencia |\n|---|---|---|\n"


# --- Etapa 1: comprensión estructurada del pliego (esqueleto de toda la redacción) ---

_PLIEGO_SYSTEM = (
    "Eres analista experto en pliegos de contratación pública española (Ley 9/2017, LCSP). Lee el "
    "pliego y extrae su estructura EXACTA en JSON. Usa SOLO lo que conste literalmente; "
    "deja la lista vacía o el valor null si un dato no aparece. No inventes ni generalices."
)
_PLIEGO_INSTRUCTION = (
    "Devuelve un JSON con estas claves exactas: "
    "objeto (str), tipo_contrato (servicios|suministro|obra|mixto|s/d), "
    "procedimiento (abierto|restringido|negociado|s/d), "
    "criterios_adjudicacion (lista de {criterio, ponderacion, tipo} con tipo en "
    "precio|juicio_valor|automatico), "
    "solvencia_tecnica (lista de str con requisitos y sus umbrales exactos), "
    "solvencia_economica (lista de str con umbrales), plazos (lista de {hito, plazo}), "
    "lotes (lista de str), penalizaciones (lista de str), "
    "obligaciones_especiales (lista de str), documentacion_exigida (lista de str). "
    "Devuelve SOLO el JSON."
)


def analyze_pliego(document_text: str | None, client_factory=None) -> dict:
    """Extrae la estructura del pliego (criterios, solvencia, plazos…). {} si no hay LLM/pliego."""
    if not document_text:
        return {}
    relevant = _relevant_pliego(document_text, max_chars=30000)
    data = llm.call_json(
        _PLIEGO_SYSTEM, f"PLIEGO:\n{relevant}\n\n{_PLIEGO_INSTRUCTION}", client_factory
    )
    return data or {}


def _fmt_list(vals: list) -> str:
    out = []
    for v in vals or []:
        if isinstance(v, dict):
            out.append(" — ".join(str(x) for x in v.values() if x))
        elif v:
            out.append(str(v))
    return "; ".join(out)


def _format_pliego_md(pliego: dict, title: str) -> str:
    """Documento visible «Análisis del pliego» a partir de la extracción estructurada."""
    if not pliego:
        return (
            f"# Análisis del pliego — {title}\n\n"
            "_Pendiente: analiza el pliego (extráelo) para obtener el análisis estructurado._"
        )
    lines = [f"# Análisis del pliego — {title}", ""]
    if pliego.get("objeto"):
        lines += [f"**Objeto:** {pliego['objeto']}", ""]
    meta = " · ".join(
        x for x in [pliego.get("tipo_contrato"), pliego.get("procedimiento")] if x and x != "s/d"
    )
    if meta:
        lines += [f"**Tipo / procedimiento:** {meta}", ""]
    crits = pliego.get("criterios_adjudicacion") or []
    if crits:
        lines += ["## Criterios de adjudicación", "", "| Criterio | Ponderación | Tipo |",
                  "|---|---|---|"]
        for c in crits:
            lines.append(
                f"| {c.get('criterio', '')} | {c.get('ponderacion', '')} | {c.get('tipo', '')} |"
            )
        lines.append("")
    for key, label in [
        ("solvencia_tecnica", "Solvencia técnica"),
        ("solvencia_economica", "Solvencia económica"),
        ("plazos", "Plazos"),
        ("lotes", "Lotes"),
        ("penalizaciones", "Penalizaciones"),
        ("obligaciones_especiales", "Obligaciones especiales"),
        ("documentacion_exigida", "Documentación exigida"),
    ]:
        vals = pliego.get(key) or []
        if vals:
            lines += [f"## {label}", ""]
            for v in vals:
                item = _fmt_list([v]) if isinstance(v, dict) else str(v)
                lines.append(f"- {item}")
            lines.append("")
    return "\n".join(lines)


def _drafting_brief(
    tender: dict, pliego: dict, buyer_profile: dict | None, market_context: dict | None
) -> str:
    """Brief de redacción: destila pliego + órgano + mercado en instrucciones accionables."""
    parts = [
        f"LICITACIÓN: {tender.get('title', '')}",
        f"Órgano: {tender.get('buyer') or 's/d'} · CPV: {', '.join(tender.get('cpv', []) or [])} "
        f"· Presupuesto: {tender.get('budget_amount')}",
    ]
    if pliego:
        crits = pliego.get("criterios_adjudicacion") or []
        if crits:
            parts.append(
                "CRITERIOS DE ADJUDICACIÓN (la oferta DEBE responder punto por punto a cada uno "
                "para maximizar la puntuación):"
            )
            for c in crits:
                parts.append(
                    f"  · {c.get('criterio', '')} — {c.get('ponderacion', '')} "
                    f"[{c.get('tipo', '')}]"
                )
        for key, label in [
            ("solvencia_tecnica", "SOLVENCIA TÉCNICA exigida"),
            ("solvencia_economica", "SOLVENCIA ECONÓMICA exigida"),
            ("plazos", "PLAZOS"),
            ("penalizaciones", "PENALIZACIONES"),
            ("obligaciones_especiales", "OBLIGACIONES ESPECIALES"),
        ]:
            v = _fmt_list(pliego.get(key))
            if v:
                parts.append(f"{label}: {v}")
    if buyer_profile:
        bp = buyer_profile
        line = f"PERFIL DEL ÓRGANO: {bp.get('tenders_seen', 0)} licitaciones observadas"
        if bp.get("recurring_cpv"):
            line += f", CPV recurrentes {', '.join(bp['recurring_cpv'])}"
        if bp.get("awards_count"):
            line += (
                f"; histórico de {bp['awards_count']} adjudicaciones, baja media "
                f"{bp.get('avg_baja')}, media de {bp.get('avg_bidders')} licitadores"
            )
        parts.append(line)
        if bp.get("top_winners"):
            parts.append(
                "Adjudicatarios habituales del órgano: "
                + ", ".join(f"{w['supplier']} ({w['wins']})" for w in bp["top_winners"])
            )
    if market_context and (market_context.get("sample_size") or 0) > 0:
        inc = market_context.get("incumbent") or {}
        conc = market_context.get("concentration") or {}
        m = f"MERCADO: baja esperada {market_context.get('expected_baja')}"
        if conc.get("label"):
            m += f", mercado {conc['label']}"
        if inc.get("supplier"):
            m += f"; incumbente a batir: {inc['supplier']}"
        parts.append(m)
    return "\n".join(parts)


# --- Segunda pasada: crítica y mejora del documento (revisor experto) ---

_REFINABLE = {"memoria_tecnica", "resumen_ejecutivo"}

_REFINE_SYSTEM = (
    "Eres revisor experto de propuestas a licitaciones públicas, simulas la mesa de contratación. "
    "Recibes un borrador y el brief con los criterios de adjudicación del pliego. Detecta sus "
    "debilidades: afirmaciones genéricas sin concreción, criterios de adjudicación poco o nada "
    "cubiertos, ausencia de cifras/plazos/umbrales del pliego, y mejoras que sumarían puntos. "
    "Reescribe el documento CORRIGIENDO esas debilidades: más concreto y anclado al pliego, con "
    "mejor cobertura punto por punto de CADA criterio, y más persuasivo, conservando o ampliando "
    "su extensión. NO expliques la crítica ni añadas comentarios; devuelve SOLO el documento "
    "MEJORADO en markdown, conservando su estructura y cualquier bloque ```mermaid tal cual."
)


def _refine_draft(draft: str, brief: str, client_factory=None) -> str:
    """Segunda pasada: critica el borrador contra los criterios y devuelve una versión mejorada.

    Conserva el original si el refinado falla o resulta sospechosamente corto (evita truncados).
    """
    prompt = (
        f"{brief}\n\nBORRADOR ACTUAL A MEJORAR:\n{draft}\n\n"
        "Devuelve el documento MEJORADO (solo el documento)."
    )
    res = llm.call_text(_REFINE_SYSTEM, prompt, client_factory)
    if res:
        improved = _strip_fence(res[0])
        if improved and len(improved) >= 0.6 * len(draft):
            return improved
    return draft


def generate_drafts(
    tender: dict,
    document_text: str | None,
    score: dict | None,
    client_factory=None,
    market_context: dict | None = None,
    buyer_profile: dict | None = None,
) -> list[dict]:
    """Devuelve [{kind, title, content}] con los borradores de oferta.

    `market_context` (inteligencia de mercado, MVP-5) añade una estrategia de puja determinista.
    """
    title = tender.get("title", "")
    use_llm = settings.openrouter_api_key or client_factory is not None

    # Etapa 1: comprensión estructurada del pliego (esqueleto de todos los documentos).
    pliego = analyze_pliego(document_text, client_factory) if use_llm else {}

    drafts = [
        {"kind": "go_no_go", "title": "Informe Go/No-Go", "content": _go_no_go(tender, score)},
        {"kind": "analisis_pliego", "title": "Análisis del pliego",
         "content": _format_pliego_md(pliego, title)},
        {"kind": "checklist_administrativo", "title": "Checklist administrativo",
         "content": _checklist()},
        {"kind": "estrategia_puja", "title": "Estrategia de puja",
         "content": _market_strategy(tender, score, market_context)},
    ]

    # Etapa 2+3: brief rico (pliego estructurado + órgano + mercado) para una redacción minuciosa.
    brief = _drafting_brief(tender, pliego, buyer_profile, market_context)
    context = brief
    if document_text:
        context += (
            "\n\nTEXTO DEL PLIEGO (secciones relevantes, cita el apartado al referenciar):\n"
            f"{_relevant_pliego(document_text)}\n"
        )

    for kind, title_d, instruction in _LLM_DRAFTS:
        body = None
        if use_llm:
            res = llm.call_text(_DRAFT_SYSTEM, f"{context}\n\nTAREA: {instruction}", client_factory)
            if res:
                body = _strip_fence(res[0])
                # Segunda pasada de crítica y mejora en los documentos de más valor.
                if settings.draft_refine_pass and kind in _REFINABLE:
                    body = _refine_draft(body, brief, client_factory)
        drafts.append(
            {"kind": kind, "title": title_d, "content": body or _template(kind, tender)}
        )
    return drafts
