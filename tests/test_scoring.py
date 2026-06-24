from tender_ai_analysis.analysis import AnalysisHints, AnalysisResult
from tender_ai_analysis.scoring import score
from tests.conftest import deadline_in, tender


def _analysis(**hints) -> AnalysisResult:
    return AnalysisResult(hints=AnalysisHints(**hints))


def test_total_equals_breakdown(profile):
    r = score(tender(), _analysis(), profile)
    assert r.total == r.breakdown.total()


def test_high_fit_is_go(profile):
    r = score(tender(), _analysis(solvency_risk="low"), profile)
    assert r.recommendation.value == "go"
    assert r.total >= 80
    assert any("CPV" in f.message for f in r.factors)


def test_excluded_cpv_is_no_go(profile):
    r = score(tender(cpv=["45000000"]), _analysis(), profile)
    assert r.recommendation.value == "no_go"
    assert "cpv_excluded" in r.hard_rules
    assert r.breakdown.technical_fit == 0


def test_urgent_deadline_downgrades_go(profile):
    # encaje alto pero plazo por debajo del mínimo → no puede quedar GO
    r = score(tender(deadline=deadline_in(2)), _analysis(solvency_risk="low"), profile)
    assert "deadline_below_min" in r.hard_rules
    assert r.recommendation.value == "revisar"


def test_partner_needed_overrides(profile):
    r = score(tender(), _analysis(solvency_risk="low", partner_needed=True), profile)
    assert r.recommendation.value == "partner"
    assert "partner_needed" in r.hard_rules
    assert r.breakdown.partner_need == 2


def test_low_budget_penalised(profile):
    r = score(tender(budget_amount=10000.0), _analysis(), profile)
    assert r.breakdown.budget_fit == 3


def test_incompatibility_zeroes_dimension(profile):
    r = score(tender(), _analysis(incompatibility=True), profile)
    assert r.breakdown.incompatibility_risk == 0


def test_no_signals_low_score(profile):
    t = tender(title="Servicio genérico", summary="", cpv=[], budget_amount=None)
    r = score(t, _analysis(), profile)
    assert r.breakdown.technical_fit == 0
