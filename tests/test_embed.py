import httpx

from tender_ai_analysis import llm
from tender_ai_analysis.config import settings
from tests.conftest import factory_for


def test_embed_disabled_without_model(monkeypatch):
    monkeypatch.setattr(settings, "embedding_model", "")
    assert llm.embed(["hola"]) is None


def test_embed_returns_vectors(monkeypatch):
    monkeypatch.setattr(settings, "embedding_model", "openai/text-embedding-3-small")

    def handler(req):
        return httpx.Response(
            200, json={"data": [{"embedding": [0.1, 0.2]}, {"embedding": [0.3, 0.4]}]}
        )

    out = llm.embed(["a", "b"], client_factory=factory_for(handler))
    assert out == [[0.1, 0.2], [0.3, 0.4]]


def test_embed_none_on_mismatch(monkeypatch):
    monkeypatch.setattr(settings, "embedding_model", "m")

    def handler(req):
        return httpx.Response(200, json={"data": [{"embedding": [0.1]}]})

    assert llm.embed(["a", "b"], client_factory=factory_for(handler)) is None
