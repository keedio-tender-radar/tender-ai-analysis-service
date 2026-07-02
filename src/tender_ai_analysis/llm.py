"""Cliente OpenRouter con cadena de modelos y fallback. Robusto por diseño.

`make_client` es el punto de parcheo en tests (httpx.MockTransport). No parchear el
httpx.Client global para evitar recursión.
"""

from __future__ import annotations

import json
import re

import httpx

from tender_ai_analysis.config import settings


def make_client() -> httpx.Client:
    return httpx.Client(
        base_url=settings.openrouter_base_url,
        headers={
            "Authorization": f"Bearer {settings.openrouter_api_key}",
            "Content-Type": "application/json",
        },
        timeout=60,
    )


def _models() -> list[str]:
    return [m.strip() for m in settings.openrouter_models.split(",") if m.strip()]


def call_json(system: str, user: str, client_factory=None) -> dict | None:
    """Llama a OpenRouter probando la cadena de modelos. Devuelve el JSON (con `_model`) o None."""
    factory = client_factory or make_client
    with factory() as client:
        for model in _models():
            try:
                resp = client.post(
                    "/chat/completions",
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ],
                        "temperature": 0.2,
                    },
                )
            except httpx.HTTPError:
                continue
            if resp.status_code != 200:
                continue
            text = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "")
            parsed = extract_json(text)
            if parsed is not None:
                parsed["_model"] = model
                return parsed
    return None


def call_text(system: str, user: str, client_factory=None) -> tuple[str, str] | None:
    """Como `call_json` pero devuelve texto libre: (respuesta, modelo) o None.

    Para respuestas en prosa (chat documental) donde no queremos forzar JSON.
    """
    factory = client_factory or make_client
    with factory() as client:
        for model in _models():
            try:
                resp = client.post(
                    "/chat/completions",
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ],
                        "temperature": 0.1,
                    },
                )
            except httpx.HTTPError:
                continue
            if resp.status_code != 200:
                continue
            text = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "")
            if text and text.strip():
                return text.strip(), model
    return None


def embed(inputs: list[str], client_factory=None) -> list[list[float]] | None:
    """Embeddings vía OpenRouter (modelo de pago). Devuelve un vector por texto, o None si falla.

    Desactivado si no hay `embedding_model` configurado (el RAG cae a BM25).
    """
    if not settings.embedding_model or not inputs:
        return None
    factory = client_factory or make_client
    with factory() as client:
        try:
            resp = client.post(
                "/embeddings", json={"model": settings.embedding_model, "input": inputs}
            )
        except httpx.HTTPError:
            return None
        if resp.status_code != 200:
            return None
        data = resp.json().get("data") or []
        vectors = [row.get("embedding") for row in data if row.get("embedding")]
        return vectors if len(vectors) == len(inputs) else None


def extract_json(text: str) -> dict | None:
    if not text:
        return None
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None
