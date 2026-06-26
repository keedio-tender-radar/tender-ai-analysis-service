"""Job: analizar y puntuar las licitaciones pendientes, publicando el score en tender-api."""

from __future__ import annotations

from dataclasses import dataclass, field

from tender_ai_analysis import analysis as analysis_mod
from tender_ai_analysis.profile import KeedioProfile
from tender_ai_analysis.scoring import score


@dataclass
class AnalysisJobResult:
    processed: int = 0
    scored: int = 0
    go: int = 0
    errors: list[str] = field(default_factory=list)


def run(api_client, profile: KeedioProfile, *, client_factory=None) -> AnalysisJobResult:
    result = AnalysisJobResult()
    pending = api_client.list_pending()

    for tender in pending:
        result.processed += 1
        try:
            analysis = analysis_mod.analyze(tender, client_factory=client_factory)
            score_result = score(tender, analysis, profile)
            api_client.put_score(tender["id"], score_result, summary=analysis.summary)
            result.scored += 1
            if score_result.recommendation.value == "go":
                result.go += 1
        except Exception as exc:  # noqa: BLE001 — una licitación con error no tumba el lote
            result.errors.append(f"{tender.get('id', '?')}: {type(exc).__name__}: {exc}")

    return result
