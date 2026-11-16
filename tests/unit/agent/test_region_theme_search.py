import pytest

from src.agent.supervisor import RouteDecision
from src.agent.supervisor.nodes import SupervisorController
from src.hybrid.adapters import ExistingVectorRetriever
from src.hybrid.region_theme import Region, recognize_region, simple_region_theme


@pytest.mark.parametrize("question, expected", [
    ("경기도 권에 있고 자연과 관련된 곳이면 좋겠음", "경기도"),
    ("서울에 있는 역사와 관련된 박물관 추천해줘", "서울특별시"),
    ("부산에 있는 사진 관련 미술관 알려줘", "부산광역시"),
])
def test_recognizes_unambiguous_region_and_theme(question, expected):
    assert simple_region_theme(question) == expected


@pytest.mark.parametrize("question", [
    "경기도에 있는 자연 관련 무료 박물관", "경기도에 있는 자연 관련 장소와 부산에 있는 곳",
    "경기도가 아닌 자연과 관련된 곳",
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


@pytest.mark.parametrize("question, expected", [
    ("경기도에서 역사를 알 수 있는 곳 10개 추천", Region("경기도")),
    ("경주에 있는 박물관이나 미술관을 알려줘", Region("경상북도", "경주시")),
    ("가평에 있는 미술관은?", Region("경기도", "가평군")),
    ("경기도 수원시에 있는 자연 관련 박물관", Region("경기도", "수원시")),
    ("제주도에서 아이랑 갈 박물관", Region("제주특별자치도")),
    ("서울특별시 박물관 추천", Region("서울특별시")),
])
def test_region_is_recognized_without_a_fixed_sentence_form(question, expected):
    assert recognize_region(question) == expected


@pytest.mark.parametrize("question", [
    "경기도박물관 위치 알려줘",          # region word is part of a facility name
    "서울대학교박물관 어디야",
    "수원시립박물관 어때",
    "경주에서 부산까지 가는 박물관",       # two regions
    "경기도 경주 박물관",                 # sido and district do not belong together
    "광주에 있는 박물관",                 # 광주광역시 or 경기도 광주시
    "경주 근처에 있는 박물관",            # nearby is a different question
    "허준박물관과 같은 시군구에 있는 시설",  # relation question
    "경기도에 있는 무료 박물관",           # fee is not expressible by this filter
    "옹기를 전시하는 박물관이 있어?",       # no region
])
def test_unclear_regions_are_not_guessed(question):
    assert recognize_region(question) is None


def test_district_reaches_both_searches_before_fusion():
    from src.hybrid.service import HybridSearchService
    from src.service.vector_search_service import VectorSearchService
    observed = {}
    class Service:
        def plan_without_analysis(self, query): return VectorSearchService.plan_without_analysis(query)
        def execute_plan(self, plan, *, top_k, rerank):
            from types import SimpleNamespace
            observed["vector"] = (plan.filters.sido, plan.filters.sigungu)
            return SimpleNamespace(results=[], warnings=[], candidate_count=0, reranked=False)
    class BM25:
        def search(self, query, *, top_k, filters):
            observed["bm25"] = (filters.get("sido"), filters.get("sigungu"))
            return []
    service = HybridSearchService(bm25_retriever=BM25(), vector_retriever=ExistingVectorRetriever(Service()))
    service.search("경주에 있는 박물관이나 미술관을 알려줘", rerank=False)
    assert observed == {"vector": ("경상북도", "경주시"), "bm25": ("경상북도", "경주시")}


@pytest.mark.parametrize("question", [
    "서울에서 무료로 갈 수 있는 박물관 추천해줘",
    "부산 입장료 무료인 미술관 알려줘",
    "경주에 있는 유료 박물관",
])
def test_region_with_fee_is_recognized_for_the_graph_route(question):
    from src.hybrid.region_theme import region_with_fee
    assert region_with_fee(question) is not None
    assert recognize_region(question) is None  # the search filter still ignores fee questions


@pytest.mark.parametrize("question", [
    "서울에 있는 박물관 추천",              # no fee condition
    "무료 박물관 알려줘",                    # no region
    "서울이 아닌 무료 박물관",               # negation
    "서울 무료 박물관 근처 맛집",             # nearby
    "서울에서 부산까지 무료인 곳",            # two regions
])
def test_region_with_fee_needs_exactly_one_clear_region_and_a_fee_word(question):
    from src.hybrid.region_theme import region_with_fee
    assert region_with_fee(question) is None


def _controller(graph):
    return SupervisorController(
        hybrid_search=lambda s, c: {}, graph_search=graph,
        route_question=lambda s, c: RouteDecision("hybrid", "llm"),
        answer_question=lambda s, c: None, verify_answer=lambda s, c: None, region_theme_routing=True)


def test_region_fee_question_goes_to_graph_every_time():
    ctl = _controller(lambda s, c: {})
    for _ in range(5):
        state = ctl.initialize({"question": "서울에서 무료로 갈 수 있는 박물관 추천해줘"})
        decision = ctl.supervisor(state)
        assert decision["route"] == "graph"


def test_region_fee_question_falls_back_when_graph_is_not_connected():
    ctl = _controller(None)
    state = ctl.initialize({"question": "서울에서 무료로 갈 수 있는 박물관 추천해줘"})
    assert ctl.supervisor(state)["route"] == "hybrid"  # the LLM router decides


def test_region_fee_question_asking_for_exhibits_is_left_to_the_router():
    ctl = _controller(lambda s, c: {})
    state = ctl.initialize({"question": "서울에서 무료로 볼 수 있는 전시가 있는 박물관"})
    assert ctl.supervisor(state)["route"] == "hybrid"


@pytest.mark.parametrize("question, expected", [
    ("서울에서 무료로 갈 수 있는 박물관 추천해줘", True),
    ("무료인 곳 추천해줘", True),                 # no region: the whole country
    ("국립중앙박물관 무료야?", True),
    ("경주에서 부산까지 무료인 곳", False),         # two regions
    ("서울 무료 박물관 근처 맛집", False),          # nearby
    ("서울 무료 관람일이 언제야", False),           # a date, not a fee list
    ("서울에 있는 박물관 추천", False),             # no fee
])
def test_fee_question_detection(question, expected):
    from src.hybrid.region_theme import is_fee_question
    assert is_fee_question(question) is expected


def test_fee_question_without_a_region_goes_to_graph():
    ctl = _controller(lambda s, c: {})
    state = ctl.initialize({"question": "무료인 곳 추천해줘"})
    assert ctl.supervisor(state)["route"] == "graph"
