from datetime import UTC, datetime, timedelta

import httpx
import pytest

from tender_ai_analysis.profile import KeedioProfile


@pytest.fixture
def profile() -> KeedioProfile:
    return KeedioProfile(
        cpv_preferred=["72", "48"],
        cpv_excluded=["45", "90"],
        keywords_positive=["datos", "ia", "integración", "inteligencia artificial"],
        keywords_negative=["obra", "construcción", "mobiliario"],
        budget_min=50000.0,
        budget_target_low=150000.0,
        budget_target_high=800000.0,
        deadline_min_days=7,
        deadline_comfortable_days=21,
    )


def deadline_in(days: int) -> str:
    return (datetime.now(UTC) + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


def tender(**overrides) -> dict:
    base = {
        "id": "t1",
        "source": "placsp",
        "source_id": "X",
        "title": "Plataforma de datos e inteligencia artificial",
        "summary": "Analítica avanzada de datos.",
        "cpv": ["72300000"],
        "budget_amount": 620000.0,
        "deadline": deadline_in(30),
    }
    base.update(overrides)
    return base


def chat(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def factory_for(handler):
    def make():
        return httpx.Client(transport=httpx.MockTransport(handler), base_url="http://llm")

    return make
