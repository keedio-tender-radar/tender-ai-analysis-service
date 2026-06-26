from fastapi.testclient import TestClient

from tender_ai_analysis import drafts
from tender_ai_analysis.config import settings
from tender_ai_analysis.web import app

client = TestClient(app)

_KINDS = {
    "go_no_go",
    "checklist_administrativo",
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
    assert len(resp.json()["drafts"]) == 5
