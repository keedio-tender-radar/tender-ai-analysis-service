from fastapi.testclient import TestClient

from tender_ai_analysis import drafts
from tender_ai_analysis.config import settings
from tender_ai_analysis.web import app
from tests.conftest import chat, factory_for

client = TestClient(app)

_KINDS = {
    "go_no_go",
    "checklist_administrativo",
    "estrategia_puja",
    "resumen_ejecutivo",
    "memoria_tecnica",
    "matriz_cumplimiento",
}


def test_drafts_fallback_without_llm(monkeypatch):
    monkeypatch.setattr(settings, "openrouter_api_key", "")
    t = {"title": "Plataforma de datos", "cpv": ["72300000"], "budget_amount": 620000}
    score = {
        "total": 88,
        "recommendation": "go",
        "factors": [{"kind": "positive", "message": "encaje"}],
        "hard_rules": [],
    }
    out = drafts.generate_drafts(t, "Solvencia: tres proyectos.", score)
    assert _KINDS <= {d["kind"] for d in out}
    gng = next(d for d in out if d["kind"] == "go_no_go")
    assert "88/100" in gng["content"]


def test_generate_drafts_endpoint(monkeypatch):
    monkeypatch.setattr(settings, "openrouter_api_key", "")
    resp = client.post(
        "/generate-drafts",
        json={"tender": {"title": "X"}, "score": {"total": 70, "recommendation": "revisar"}},
    )
    assert resp.status_code == 200
    assert len(resp.json()["drafts"]) == 6


def test_bid_strategy_uses_market_context(monkeypatch):
    monkeypatch.setattr(settings, "openrouter_api_key", "")
    t = {"title": "Datos", "cpv": ["72300000"], "budget_amount": 100000, "currency": "EUR"}
    market = {
        "cpv_division": "72",
        "sample_size": 4,
        "expected_baja": 0.20,
        "likely_winners": [{"supplier": "Alfa", "wins": 3, "avg_baja": 0.18}],
        "concentration": {"hhi": 0.4, "label": "concentrado", "competitors": 3},
        "incumbent": {"supplier": "Incumbente SL", "award_date": "2026-05-01"},
    }
    out = drafts.generate_drafts(t, None, {"total": 80, "recommendation": "go"},
                                 market_context=market)
    strat = next(d for d in out if d["kind"] == "estrategia_puja")
    assert "20.0%" in strat["content"]
    assert "80.000" in strat["content"]  # puja sugerida = 100.000 * (1 - 0.20)
    assert "Alfa" in strat["content"]
    assert "concentrado" in strat["content"]
    assert "Incumbente SL" in strat["content"]  # incumbente a batir


def test_llm_drafts_grounded_in_pliego(monkeypatch):
    # Con LLM, la memoria/resumen/matriz se redactan por documento (call_text), ancladas al pliego.
    monkeypatch.setattr(settings, "openrouter_models", "m")
    factory = factory_for(lambda req: chat("## Metodología\nSegún el pliego: RAG con citas."))
    out = drafts.generate_drafts(
        {"title": "X", "cpv": ["72300000"]}, "PLIEGO: se exige RAG con citas", None,
        client_factory=factory,
    )
    memoria = next(d for d in out if d["kind"] == "memoria_tecnica")
    assert "Según el pliego" in memoria["content"]
    assert "(Pendiente.)" not in memoria["content"]  # no es la plantilla genérica


def test_relevant_pliego_surfaces_deep_requirements():
    # Objeto al principio; los requisitos técnicos REALES van al final (más allá del corte antiguo).
    head = "Objeto del contrato: servicio de plataforma de datos."
    filler = "\n\n".join(
        f"Apartado administrativo {i}: procedimiento y garantías." for i in range(500)
    )
    reqs = (
        "Prescripciones técnicas: se exige solvencia técnica con tres proyectos similares y "
        "criterios de adjudicación ponderados por calidad."
    )
    text = f"{head}\n\n{filler}\n\n{reqs}"
    assert len(text) > 26000  # obliga a seleccionar
    sel = drafts._relevant_pliego(text, max_chars=8000)
    assert "Objeto del contrato" in sel  # conserva el principio (objeto)
    assert "solvencia técnica con tres proyectos" in sel  # rescata los requisitos del final


def test_bid_strategy_without_market_is_graceful():
    out = drafts.generate_drafts({"title": "X", "budget_amount": 100000}, None, None)
    strat = next(d for d in out if d["kind"] == "estrategia_puja")
    assert "Sin histórico" in strat["content"]
