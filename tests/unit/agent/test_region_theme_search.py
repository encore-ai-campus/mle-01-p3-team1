import pytest

from src.agent.supervisor import RouteDecision
from src.agent.supervisor.nodes import SupervisorController
from src.hybrid.adapters import ExistingVectorRetriever
from src.hybrid.region_theme import simple_region_theme


@pytest.mark.parametrize("question, expected", [
    ("경기도 권에 있고 자연과 관련된 곳이면 좋겠음", "경기도"),
    ("서울에 있는 역사와 관련된 박물관 추천해줘", "서울특별시"),
    ("부산에 있는 사진 관련 미술관 알려줘", "부산광역시"),
])
def test_recognizes_unambiguous_region_and_theme(question, expected):
    assert simple_region_theme(question) == expected


@pytest.mark.parametrize("question", [
    "경기도에 있는 자연 관련 무료 박물관", "경기도에 있는 자연 관련 장소와 부산에 있는 곳",
    "경기도가 아닌 자연과 관련된 곳", "경기도 수원시에 있는 자연 관련 박물관",
    "경기도에 있는 자연 관련 박물관 근처에 있는 곳", "서울에 있는 역사와 관련된 유료 박물관",
])
def test_complex_conditions_are_not_silently_dropped(question):
    assert simple_region_theme(question) is None


def test_prepared_plan_has_hard_region_filter_without_llm():
    from src.service.vector_search_service import VectorSearchService
    class LocalService:
        def is_query_analysis_enabled(self): return False
        def plan_without_analysis(self, query): return VectorSearchService.plan_without_analysis(query)
    plan = ExistingVectorRetriever(LocalService()).prepare("경기도 권에 있고 자연과 관련된 곳이면 좋겠음")
    assert plan.filters.sido == "경기도"
    assert plan.expanded_query == "경기도 권에 있고 자연과 관련된 곳이면 좋겠음"


def test_supervisor_uses_hybrid_for_clear_region_theme():
    ctl = SupervisorController(hybrid_search=lambda s, c: {}, graph_search=lambda s, c: {},
        route_question=lambda s, c: RouteDecision("graph", "wrong"),
        answer_question=lambda s, c: None, verify_answer=lambda s, c: None, region_theme_routing=True)
    state = ctl.initialize({"question": "경기도 권에 있고 자연과 관련된 곳이면 좋겠음"})
    assert ctl.supervisor(state)["route"] == "hybrid"
    state["route_override"] = "graph"
    assert ctl.supervisor(state)["route"] == "graph"


def test_region_filter_reaches_both_searches_before_fusion():
    from src.hybrid.service import HybridSearchService
    from src.service.vector_search_service import VectorSearchService
    observed = {}
    class Service:
        def plan_without_analysis(self, query): return VectorSearchService.plan_without_analysis(query)
        def execute_plan(self, plan, *, top_k, rerank):
            from types import SimpleNamespace
            observed["vector_region"] = plan.filters.sido
            return SimpleNamespace(results=[], warnings=[], candidate_count=0, reranked=False)
    class BM25:
        def search(self, query, *, top_k, filters):
            observed["bm25_region"] = filters.get("sido")
            return []
    service = HybridSearchService(bm25_retriever=BM25(), vector_retriever=ExistingVectorRetriever(Service()))
    service.search("경기도 권에 있고 자연과 관련된 곳이면 좋겠음", rerank=False)
    assert observed == {"vector_region": "경기도", "bm25_region": "경기도"}
