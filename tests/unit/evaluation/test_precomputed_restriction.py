from src.evaluation.hybrid.ragas_eval import PrecomputedHybridRetriever, _query_key


class FakeService:
    def __init__(self):
        self.calls = []

    def search(self, query, **kwargs):
        self.calls.append((query, kwargs))
        return {"results": [], "live": True}


def test_restricted_search_runs_live_instead_of_replaying_the_cache():
    service = FakeService()
    cached = {_query_key("q"): {"response": {"results": ["cached"], "search_summary": {}}}}
    retriever = PrecomputedHybridRetriever(cached, live_service=service)

    result = retriever.retrieve("q", top_k=5, restrict_to_museum_ids=["M1", "M2"])

    assert result["live"] is True
    assert service.calls[0][1]["restrict_to_museum_ids"] == ["M1", "M2"]


def test_unrestricted_search_still_replays_the_cache():
    service = FakeService()
    cached = {_query_key("q"): {"response": {"results": ["cached"], "search_summary": {}}}}
    retriever = PrecomputedHybridRetriever(cached, live_service=service)

    assert retriever.retrieve("q", top_k=10)["results"] == ["cached"]
    assert service.calls == []
