from tender_ai_analysis.job import run
from tests.conftest import tender


class FakeApi:
    def __init__(self, pending):
        self._pending = pending
        self.scored = []

    def list_pending(self, **kwargs):
        return self._pending

    def put_score(self, tender_id, result, summary=None):
        self.scored.append((tender_id, result))
        return {"id": "score-" + tender_id}


def test_job_scores_pending(profile):
    api = FakeApi([tender(id="a"), tender(id="b", cpv=["45000000"])])
    result = run(api, profile)
    assert result.processed == 2
    assert result.scored == 2
    assert result.go == 1  # 'a' encaja (GO); 'b' tiene CPV excluido (NO-GO)
    assert {tid for tid, _ in api.scored} == {"a", "b"}


def test_job_isolates_errors(profile):
    class BadApi(FakeApi):
        def put_score(self, tender_id, result, summary=None):
            if tender_id == "boom":
                raise RuntimeError("api down")
            return super().put_score(tender_id, result)

    api = BadApi([tender(id="ok"), tender(id="boom")])
    result = run(api, profile)
    assert result.scored == 1
    assert any("boom" in e for e in result.errors)
