import httpx

from tender_ai_analysis import analysis as analysis_mod
from tender_ai_analysis import llm
from tender_ai_analysis.config import settings
from tests.conftest import chat, factory_for, tender


def test_fallback_without_llm(monkeypatch):
    monkeypatch.setattr(settings, "openrouter_api_key", "")
    out = analysis_mod.analyze(tender())
    assert out.generated_by == "rule-based"
    assert "datos" in out.summary.lower() or out.summary  # resumen del anuncio


def test_llm_enriches(monkeypatch):
    monkeypatch.setattr(settings, "openrouter_models", "model-x")
    payload = (
        '{"summary": "Resumen IA", "functional_requirements": ["F1"], '
        '"risks": [{"risk": "r", "mitigation": "m"}], '
        '"hints": {"solvency_risk": "high", "partner_needed": true}}'
    )
    out = analysis_mod.analyze(tender(), client_factory=factory_for(lambda req: chat(payload)))
    assert out.generated_by == "llm:model-x"
    assert out.summary == "Resumen IA"
    assert out.functional_requirements == ["F1"]
    assert out.hints.solvency_risk == "high"
    assert out.hints.partner_needed is True


def test_llm_failure_falls_back(monkeypatch):
    monkeypatch.setattr(settings, "openrouter_models", "m1,m2")
    factory = factory_for(lambda req: httpx.Response(429, json={"error": "rate"}))
    out = analysis_mod.analyze(tender(), client_factory=factory)
    assert out.generated_by == "rule-based"


def test_extract_json():
    assert llm.extract_json('{"a": 1}') == {"a": 1}
    assert llm.extract_json("```json\n{\"a\": 2}\n```") == {"a": 2}
    assert llm.extract_json("nada") is None
