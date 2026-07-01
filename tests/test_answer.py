import httpx

from tender_ai_analysis import answer as answer_mod
from tender_ai_analysis.config import settings
from tests.conftest import chat, factory_for

_CHUNKS = [
    {"n": 1, "section": "Objeto", "content": "Plataforma de datos sanitarios."},
    {"n": 2, "section": "Solvencia", "content": "Se exige solvencia técnica con tres proyectos."},
]


def test_answer_fallback_without_llm(monkeypatch):
    monkeypatch.setattr(settings, "openrouter_api_key", "")
    out = answer_mod.answer("¿Qué solvencia exige?", _CHUNKS)
    assert out.grounded is False
    assert out.generated_by == "rule-based"
    # Devuelve el fragmento más relevante (el primero, ya ordenado por la API) con su cita.
    assert "[1]" in out.answer


def test_answer_llm_grounded_with_citation(monkeypatch):
    monkeypatch.setattr(settings, "openrouter_models", "model-x")
    factory = factory_for(lambda req: chat("Exige solvencia con 3 proyectos [2]."))
    out = answer_mod.answer("¿solvencia?", _CHUNKS, client_factory=factory)
    assert out.grounded is True
    assert out.generated_by == "llm:model-x"
    assert "[2]" in out.answer


def test_answer_empty_chunks():
    out = answer_mod.answer("¿algo?", [])
    assert out.grounded is False
    assert "no contiene" in out.answer.lower()


def test_answer_llm_failure_falls_back(monkeypatch):
    monkeypatch.setattr(settings, "openrouter_models", "m1")
    factory = factory_for(lambda req: httpx.Response(500, json={"error": "boom"}))
    out = answer_mod.answer("¿solvencia?", _CHUNKS, client_factory=factory)
    assert out.grounded is False
    assert out.generated_by == "rule-based"
