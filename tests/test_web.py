from fastapi.testclient import TestClient

from tender_ai_analysis.config import settings
from tender_ai_analysis.web import app

client = TestClient(app)


def test_analyze_endpoint(monkeypatch):
    monkeypatch.setattr(settings, "openrouter_api_key", "")  # rule-based determinista
    tender = {"title": "Plataforma de datos", "cpv": ["72300000"], "budget_amount": 620000}
    resp = client.post("/analyze", json={"tender": tender})
    assert resp.status_code == 200
    body = resp.json()
    assert body["score"]["total"] == body["score"]["total"]  # presente
    assert "recommendation" in body["score"]
    assert body["used_document"] is False


def test_analyze_with_document_raises_score(monkeypatch):
    monkeypatch.setattr(settings, "openrouter_api_key", "")
    tender = {"title": "Servicio", "cpv": [], "budget_amount": 200000}
    plain = client.post("/analyze", json={"tender": tender}).json()
    withdoc = client.post(
        "/analyze",
        json={"tender": tender, "document_text": "datos integración api cloud machine learning"},
    ).json()
    assert withdoc["used_document"] is True
    base_fit = plain["score"]["breakdown"]["technical_fit"]
    assert withdoc["score"]["breakdown"]["technical_fit"] >= base_fit
