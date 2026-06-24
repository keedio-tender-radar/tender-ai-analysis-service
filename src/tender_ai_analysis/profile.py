"""Perfil de Keedio que alimenta el scoring (desacoplado de settings para testear)."""

from __future__ import annotations

from dataclasses import dataclass, field

from tender_ai_analysis.config import settings


@dataclass
class KeedioProfile:
    cpv_preferred: list[str] = field(default_factory=list)
    cpv_excluded: list[str] = field(default_factory=list)
    keywords_positive: list[str] = field(default_factory=list)
    keywords_negative: list[str] = field(default_factory=list)
    budget_min: float = 50000.0
    budget_target_low: float = 150000.0
    budget_target_high: float = 800000.0
    deadline_min_days: int = 7
    deadline_comfortable_days: int = 21


def from_settings() -> KeedioProfile:
    return KeedioProfile(
        cpv_preferred=settings.cpv_preferred_list,
        cpv_excluded=settings.cpv_excluded_list,
        keywords_positive=settings.keywords_positive_list,
        keywords_negative=settings.keywords_negative_list,
        budget_min=settings.budget_min,
        budget_target_low=settings.budget_target_low,
        budget_target_high=settings.budget_target_high,
        deadline_min_days=settings.deadline_min_days,
        deadline_comfortable_days=settings.deadline_comfortable_days,
    )
