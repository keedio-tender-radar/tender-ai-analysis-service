"""Scoring Go/No-Go rule-based (ver tender-platform-docs/scoring-model.md).

Determinista: dadas la licitación, el análisis (pistas opcionales) y el perfil Keedio, calcula
las 9 dimensiones, aplica reglas duras y produce la recomendación con factores explicativos.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from tender_contracts import FactorKind, Recommendation, ScoreBreakdown, ScoreFactor

from tender_ai_analysis.analysis import AnalysisResult
from tender_ai_analysis.profile import KeedioProfile


@dataclass
class ScoreResult:
    breakdown: ScoreBreakdown
    total: int
    recommendation: Recommendation
    hard_rules: list[str] = field(default_factory=list)
    factors: list[ScoreFactor] = field(default_factory=list)


def _text(tender: dict) -> str:
    return f"{tender.get('title', '')} {tender.get('summary', '')}".lower()


def _cpv_matches(cpvs: list[str], prefixes: list[str]) -> bool:
    return any(c.startswith(p) for c in cpvs for p in prefixes)


def _days_to_deadline(tender: dict) -> int | None:
    raw = tender.get("deadline")
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return (dt - datetime.now(UTC)).days


def _technical_fit(tender: dict, profile: KeedioProfile, factors: list[ScoreFactor]) -> int:
    cpvs = tender.get("cpv") or []
    text = _text(tender)
    score = 0
    if _cpv_matches(cpvs, profile.cpv_preferred):
        score += 18
        factors.append(ScoreFactor(kind=FactorKind.POSITIVE, message="CPV en los preferidos."))
    hits = [k for k in profile.keywords_positive if k in text]
    if hits:
        score += min(12, 4 * len(hits))
        factors.append(
            ScoreFactor(
                kind=FactorKind.POSITIVE,
                message=f"Keywords de encaje: {', '.join(hits[:5])}.",
            )
        )
    if score == 0:
        factors.append(
            ScoreFactor(kind=FactorKind.NEGATIVE, message="Sin señales claras de encaje técnico.")
        )
    return min(30, score)


def _budget_fit(tender: dict, p: KeedioProfile, factors: list[ScoreFactor]) -> int:
    amount = tender.get("budget_amount")
    if amount is None:
        return 8
    if amount < p.budget_min:
        factors.append(
            ScoreFactor(kind=FactorKind.NEGATIVE, message="Presupuesto por debajo del mínimo.")
        )
        return 3
    if p.budget_target_low <= amount <= p.budget_target_high:
        factors.append(
            ScoreFactor(kind=FactorKind.POSITIVE, message="Presupuesto en la banda objetivo.")
        )
        return 15
    if amount > p.budget_target_high:
        return 11
    return 9


def _solvency_scores(hints) -> tuple[int, int]:
    risk = (hints.solvency_risk or "").lower()
    table = {"low": (15, 10), "medium": (10, 7), "high": (5, 4)}
    return table.get(risk, (10, 7))


def _deadline_score(days: int | None, p: KeedioProfile, factors: list[ScoreFactor]) -> int:
    if days is None:
        return 5
    if days < p.deadline_min_days:
        factors.append(
            ScoreFactor(kind=FactorKind.NEGATIVE, message=f"Plazo muy ajustado ({days} días).")
        )
        return 3
    if days >= p.deadline_comfortable_days:
        return 10
    return 7


def score(tender: dict, analysis: AnalysisResult, profile: KeedioProfile) -> ScoreResult:
    factors: list[ScoreFactor] = []
    hints = analysis.hints
    cpvs = tender.get("cpv") or []
    days = _days_to_deadline(tender)

    excluded = _cpv_matches(cpvs, profile.cpv_excluded)
    technical = 0 if excluded else _technical_fit(tender, profile, factors)
    tech_solv, econ_solv = _solvency_scores(hints)
    contractual = {"high": 2, "medium": 3, "low": 5}.get((hints.contractual_risk or "").lower(), 4)

    breakdown = ScoreBreakdown(
        technical_fit=technical,
        budget_fit=_budget_fit(tender, profile, factors),
        technical_solvency=tech_solv,
        economic_solvency=econ_solv,
        deadline=_deadline_score(days, profile, factors),
        partner_need=2 if hints.partner_needed else 5,
        documental_complexity=4,
        contractual_risk=contractual,
        incompatibility_risk=0 if hints.incompatibility else 5,
    )
    total = breakdown.total()

    hard_rules: list[str] = []
    if excluded:
        recommendation = Recommendation.NO_GO
        hard_rules.append("cpv_excluded")
        factors.append(
            ScoreFactor(kind=FactorKind.NEGATIVE, message="CPV en la lista de excluidos.")
        )
    else:
        recommendation = _band(total)
        if hints.partner_needed:
            recommendation = Recommendation.PARTNER
            hard_rules.append("partner_needed")
        if days is not None and days < profile.deadline_min_days:
            hard_rules.append("deadline_below_min")
            if recommendation == Recommendation.GO:
                recommendation = Recommendation.REVISAR

    return ScoreResult(
        breakdown=breakdown,
        total=total,
        recommendation=recommendation,
        hard_rules=hard_rules,
        factors=factors,
    )


def _band(total: int) -> Recommendation:
    if total >= 80:
        return Recommendation.GO
    if total >= 40:
        return Recommendation.REVISAR
    return Recommendation.NO_GO
