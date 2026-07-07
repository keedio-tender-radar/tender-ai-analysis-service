from tender_ingestion.jobs.daily_ingestion_job import (
    FilterConfig,
    Source,
    _fetch_with_retry,
    run_ingestion,
)
from tender_ingestion.types import TenderPayload

_CFG = FilterConfig(
    cpv_preferred=[], cpv_excluded=[], keywords_positive=["datos"], keywords_negative=[]
)


class _Flaky:
    """Conector que falla `fail_times` veces y luego devuelve un resultado."""

    name = "flaky"

    def __init__(self, fail_times: int):
        self.fail_times = fail_times
        self.calls = 0

    def fetch(self):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise ConnectionError("transitorio")
        return [{"ok": True}]


class _AlwaysFail:
    name = "dead"

    def fetch(self):
        raise ConnectionError("fuente caída")


def _norm(_raw) -> TenderPayload:
    return TenderPayload(source="test", source_id="X1", title="Servicio de datos", cpv=["72"])


class _Api:
    def __init__(self):
        self.published = []

    def publish(self, payload):
        self.published.append(payload)
        return {"id": "t1"}


def test_fetch_with_retry_recovers():
    c = _Flaky(fail_times=2)
    got = _fetch_with_retry(c, attempts=3, delay=0)
    assert c.calls == 3 and got == [{"ok": True}]


def test_run_ingestion_retries_then_publishes():
    src = Source(connector=_Flaky(fail_times=1), normalize=_norm)
    r = run_ingestion([src], _Api(), _CFG, fetch_attempts=3, retry_delay=0)
    assert r.published == 1 and r.errors == []  # el reintento absorbió el fallo transitorio


def test_run_ingestion_deadletters_after_retries():
    src = Source(connector=_AlwaysFail(), normalize=_norm)
    r = run_ingestion([src], _Api(), _CFG, fetch_attempts=2, retry_delay=0)
    assert r.published == 0
    assert any("dead" in e for e in r.errors)  # queda registrado como dead-letter
