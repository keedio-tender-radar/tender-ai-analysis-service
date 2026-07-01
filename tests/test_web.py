from fastapi.testclient import TestClient

from tender_ai_analysis.config import settings
from tender_ai_analysis.web import app

client = TestClient(app)


def test_analyze_endpoint(monkeypatch):
    monkeypatch.setattr(settings, "openrouter_api_key", "")  # rule-based determinista
    monkeypatch.setattr(settings, "api_url", "")  # sin fetch de perfil remoto en tests
    tender = {"title": "Plataforma de datos", "cpv": ["72300000"], "budget_amount": 620000}
    resp = client.post("/analyze", json={"tender": tender})
    assert resp.status_code == 200
    body = resp.json()
    assert body["score"]["total"] == body["score"]["total"]  # presente
    assert "recommendation" in body["score"]
    assert body["used_document"] is False


def test_answer_endpoint_fallback(monkeypatch):
    monkeypatch.setattr(settings, "openrouter_api_key", "")  # sin LLM → extractivo
    chunks = [{"n": 1, "section": "Solvencia", "content": "Se exige solvencia técnica."}]
    resp = client.post("/answer", json={"question": "¿solvencia?", "chunks": chunks})
    assert resp.status_code == 200
    body = resp.json()
    assert body["grounded"] is False
    assert "[1]" in body["answer"]


def test_analyze_with_document_raises_score(monkeypatch):
    monkeypatch.setattr(settings, "openrouter_api_key", "")
    monkeypatch.setattr(settings, "api_url", "")
    tender = {"title": "Servicio", "cpv": [], "budget_amount": 200000}
    plain = client.post("/analyze", json={"tender": tender}).json()
    withdoc = client.post(
        "/analyze",
        json={"tender": tender, "document_text": "datos integración api cloud machine learning"},
    ).json()
    assert withdoc["used_document"] is True
    base_fit = plain["score"]["breakdown"]["technical_fit"]
    assert withdoc["score"]["breakdown"]["technical_fit"] >= base_fit
