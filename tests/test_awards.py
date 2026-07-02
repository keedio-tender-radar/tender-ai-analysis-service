import json

from tender_ingestion.connectors.base_connector import BaseConnector
from tender_ingestion.connectors.ted_awards_connector import TedAwardsConnector
from tender_ingestion.jobs.awards_job import run_awards


def test_ted_awards_parse():
    raw = json.dumps(
        {
            "notices": [
                {
                    "publication-number": "123456-2026",
                    "notice-title": {"spa": "Adjudicación servicios de datos"},
                    "buyer-name": {"spa": ["Ayuntamiento de Bilbao"]},
                    "classification-cpv": ["72000000", "72000000"],
                    "estimated-value-proc": 100000,
                    "total-value": 82000,
                    "result-value-notice": 82000,
                    "organisation-name-tenderer": {"spa": ["Empresa Alfa SL"]},
                    "publication-date": "2026-02-10+01:00",
                    "links": {"html": {"SPA": "https://ted.europa.eu/es/notice/123456-2026/html"}},
                }
            ]
        }
    )
    awards = TedAwardsConnector("http://ted").parse(raw)
    assert len(awards) == 1
    a = awards[0]
    assert a["source"] == "ted"
    assert a["source_id"] == "123456-2026"
    assert a["awarded_supplier"] == "Empresa Alfa SL"
    assert a["awarded_amount"] == 82000.0
    assert a["budget_amount"] == 100000.0  # presupuesto base = estimated-value-proc → baja real
    assert a["buyer"] == "Ayuntamiento de Bilbao"
    assert a["award_date"] == "2026-02-10"
    assert a["cpv"] == ["72000000", "72000000"]


def test_ted_awards_budget_falls_back_to_lot_sum():
    # Sin estimated-value-proc, el presupuesto base = suma de estimados por lote (casa con total).
    raw = json.dumps({"notices": [{
        "publication-number": "L-1",
        "estimated-value-lot": [100000, 50000],
        "result-value-notice": 90000,
    }]})
    a = TedAwardsConnector("http://ted").parse(raw)[0]
    assert a["budget_amount"] == 150000.0  # 100000 + 50000
    assert a["awarded_amount"] == 90000.0


def test_fetch_enriches_budget_from_cn(monkeypatch):
    # Adjudicación sin presupuesto pero con procedure-identifier → se recupera del anuncio CN.
    raw = json.dumps({"notices": [{
        "publication-number": "E-1",
        "result-value-notice": 80000,
        "procedure-identifier": "PID-1",
    }]})
    c = TedAwardsConnector("http://ted")
    monkeypatch.setattr(c, "fetch_raw", lambda: raw)
    monkeypatch.setattr(c, "_fetch_cn_budgets", lambda ids: {"PID-1": 100000.0})
    awards = c.fetch()
    assert len(awards) == 1
    a = awards[0]
    assert a["budget_amount"] == 100000.0  # recuperado del CN por procedure-identifier
    assert a["awarded_amount"] == 80000.0
    assert "_procedure_id" not in a  # campo transitorio eliminado antes de publicar


def test_ted_awards_parse_missing_winner_is_none():
    raw = json.dumps({"notices": [{"publication-number": "999", "total-value": 5000}]})
    a = TedAwardsConnector("http://ted").parse(raw)[0]
    assert a["awarded_supplier"] is None
    # Sin result-value-notice, el importe adjudicado cae a total-value (nota de formalización).
    assert a["awarded_amount"] == 5000.0
    # Sin estimated-value-proc no hay presupuesto base → baja no calculable (None, no 0% falso).
    assert a["budget_amount"] is None


class _FakeConnector(BaseConnector):
    name = "ted"

    def __init__(self, awards):
        super().__init__("http://x")
        self._awards = awards

    def parse(self, raw):  # no usado
        return self._awards

    def fetch(self):
        return self._awards


class _FakePublisher:
    def __init__(self):
        self.sent = None

    def publish(self, awards):
        self.sent = awards
        return {"created": len(awards), "updated": 0, "total": len(awards)}


def test_run_awards_publishes_valid():
    conn = _FakeConnector(
        [
            {"source_id": "A-1", "awarded_supplier": "Alfa"},
            {"source_id": "", "awarded_supplier": "Sin id"},  # se descarta
        ]
    )
    pub = _FakePublisher()
    result = run_awards([conn], pub)
    assert result.fetched == 2
    assert result.published == 1
    assert len(pub.sent) == 1
    assert not result.errors


def test_run_awards_isolates_failing_source():
    class Boom(BaseConnector):
        name = "ted"

        def parse(self, raw):
            return []

        def fetch(self):
            raise RuntimeError("caído")

    result = run_awards([Boom("http://x")], _FakePublisher())
    assert result.fetched == 0
    assert result.errors and "caído" in result.errors[0]
