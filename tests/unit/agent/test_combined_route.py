"""Combined (document + graph) route and the Neo4j-first ontology filter (offline)."""

import os
from unittest import mock

import pytest

from src.agent.supervisor.nodes import DESCRIPTIVE_CUE, SupervisorController
from src.agent.supervisor.state import RouteDecision
from src.hybrid.ontology_filter import (
    FallbackIndex,
    LocalOntologyIndex,
    MuseumFacts,
    OntologyCandidateFilter,
    StructuredConditions,
    build_candidate_filter,
    default_candidate_filter,
)


# --------------------------------------------------------------------------- helpers
def hybrid_result(rows, no_record=False):
    summary = {"ontology_filter": {"status": "empty", "conditions": {"amenities": ["주차장"]}}} if no_record else {}
    return {
        "status": "ok" if rows else "no_results",
        "results": rows,
        "search_summary": summary,
        "warnings": [],
        "unsupported_constraints": [],
    }


def doc_row(museum_id, text):
    return {"museum_id": museum_id, "text": text, "name": museum_id}


def graph_row(museum_id, text):
    return {"museum_id": museum_id, "text": text, "name": museum_id}


def make_controller(*, hybrid, graph):
    ctl = object.__new__(SupervisorController)
    ctl.searchers = {"hybrid": hybrid, "vector": None, "graph": graph}
    ctl.region_theme_routing = True
    ctl.metadata_provenance = None
    ctl.route_question = lambda state, config: RouteDecision("hybrid", "llm router")
    return ctl


def combined_state(question="같은 기관 시설 중 신라 유물을 볼 수 있는 곳"):
    return {"question": question, "top_k": 5, "route": "combined", "route_override": "auto",
            "retry_count": 0, "missing_aspects": [], "feedback": "", "trace": [], "errors": []}


def fake_hybrid(rows, seen=None):
    # Fake backends return already-normalized evidence rows through normalize_result's contract.
    def call(state, config=None):
        if seen is not None:
            seen.append(state.get("candidate_museum_ids"))
        return {"evidence": rows, "hybrid_search_diagnostics": {"search_summary": {}}}
    return call


def fake_graph(rows):
    def call(state, config=None):
        return {"graph_evidence": rows, "evidence": rows, "graph_search_diagnostics": {"template": "same_operator"}}
    return call


# --------------------------------------------------------------------------- combined search
def test_combined_appends_document_then_graph_and_renumbers():
    ctl = make_controller(
        hybrid=fake_hybrid([doc_row("M1", "신라 유물 전시"), doc_row("M2", "신라 토기")]),
        graph=fake_graph([graph_row("M3", "같은 기관이 운영")]),
    )
    update = ctl._search_combined(combined_state(), {})
    evidence = update["evidence"]
    assert [row["museum_id"] for row in evidence] == ["M1", "M2", "M3"]
    assert [row["evidence_id"] for row in evidence] == ["E1", "E2", "E3"]
    assert [row["retrieval_branch"] for row in evidence] == ["document", "document", "graph"]
    assert len(update["graph_evidence"]) == 1
    assert update["trace"][-1]["document_evidence"] == 2 and update["trace"][-1]["graph_evidence"] == 1


def test_combined_drops_graph_row_that_repeats_document_text():
    ctl = make_controller(
        hybrid=fake_hybrid([doc_row("M1", "신라 유물 전시")]),
        graph=fake_graph([graph_row("M1", "신라  유물 전시"), graph_row("M1", "다른 내용")]),
    )
    update = ctl._search_combined(combined_state(), {})
    assert [row["text"] for row in update["evidence"]] == ["신라 유물 전시", "다른 내용"]


def test_combined_keeps_document_evidence_when_graph_fails():
    def broken(state, config=None):
        raise RuntimeError("neo4j down")

    ctl = make_controller(hybrid=fake_hybrid([doc_row("M1", "신라 유물 전시")]), graph=broken)
    update = ctl._search_combined(combined_state(), {})
    assert [row["museum_id"] for row in update["evidence"]] == ["M1"]
    assert update["errors"] == [{"step": "graph_search", "type": "RuntimeError"}]
    assert update["trace"][-1]["branch_errors"] == ["graph"]
    assert update["failure_reason"] == ""


def test_combined_keeps_graph_evidence_when_document_search_fails():
    def broken(state, config=None):
        raise RuntimeError("chroma down")

    ctl = make_controller(hybrid=broken, graph=fake_graph([graph_row("M3", "같은 기관이 운영")]))
    update = ctl._search_combined(combined_state(), {})
    assert [row["museum_id"] for row in update["evidence"]] == ["M3"]
    assert update["trace"][-1]["branch_errors"] == ["document"]


def test_combined_reports_failure_when_both_fail():
    def broken(state, config=None):
        raise ValueError("x")

    ctl = make_controller(hybrid=broken, graph=broken)
    update = ctl._search_combined(combined_state(), {})
    assert update["evidence"] == []
    assert update["failure_reason"].startswith("Search failed")


def test_document_search_is_limited_to_the_museums_the_graph_found():
    seen = []
    anchor = {**graph_row("M3", "기준 시설"), "evidence_role": "anchor"}
    ctl = make_controller(
        hybrid=fake_hybrid([doc_row("M1", "신라 유물 전시")], seen),
        graph=fake_graph([anchor, graph_row("M1", "같은 기관"), graph_row("M2", "같은 기관"), graph_row("M1", "또 다른 근거")]),
    )
    ctl._search_combined(combined_state(), {})
    assert seen == [["M1", "M2"]]  # anchor excluded, duplicates dropped, order kept


def test_document_search_is_unrestricted_when_graph_finds_nothing():
    seen = []
    ctl = make_controller(hybrid=fake_hybrid([doc_row("M1", "a")], seen), graph=fake_graph([]))
    update = ctl._search_combined(combined_state(), {})
    assert seen == [None]
    assert update["trace"][-1]["restricted_to"] == 0


def test_document_search_is_unrestricted_when_graph_fails():
    seen = []

    def broken(state, config=None):
        raise RuntimeError("neo4j down")

    ctl = make_controller(hybrid=fake_hybrid([doc_row("M1", "a")], seen), graph=broken)
    ctl._search_combined(combined_state(), {})
    assert seen == [None]


def test_hybrid_adapter_forwards_graph_museums_only_when_retriever_accepts_them():
    from src.agent.supervisor.adapters import adapt_hybrid_retriever

    captured = {}

    class Restrictable:
        def retrieve(self, query, top_k=10, restrict_to_museum_ids=None):
            captured["ids"] = restrict_to_museum_ids
            raise RuntimeError("stop")

    class Plain:
        def retrieve(self, query, top_k=10):
            captured["plain"] = True
            raise RuntimeError("stop")

    state = {"question": "q", "top_k": 5, "candidate_museum_ids": ["M1", "M2"]}
    for retriever in (Restrictable(), Plain()):
        with pytest.raises(RuntimeError):
            adapt_hybrid_retriever(retriever)(state)
    assert captured == {"ids": ["M1", "M2"], "plain": True}


def test_search_node_dispatches_combined_route():
    ctl = make_controller(hybrid=fake_hybrid([doc_row("M1", "a")]), graph=fake_graph([graph_row("M2", "b")]))
    update = ctl.search(combined_state())
    assert update["trace"][-1]["step"] == "combined_search"
    assert len(update["evidence"]) == 2


# --------------------------------------------------------------------------- routing
def routing_state(question, retry=0, route="hybrid", override="auto"):
    return {"question": question, "retry_count": retry, "route": route, "route_override": override,
            "missing_aspects": [], "feedback": "", "trace": []}


def test_relation_question_with_description_routes_to_combined():
    ctl = make_controller(hybrid=object(), graph=object())
    update = ctl.supervisor(routing_state("창녕박물관과 같은 기관이 운영하는 시설 중 유물을 볼 수 있는 곳은?"))
    assert update["route"] == "combined"
    assert "same_operator" in update["route_reason"]


def test_plain_relation_question_stays_graph():
    ctl = make_controller(hybrid=object(), graph=object())
    update = ctl.supervisor(routing_state("창녕박물관과 같은 기관이 운영하는 다른 시설은?"))
    assert update["route"] == "graph"


def test_combined_falls_back_to_hybrid_without_graph():
    ctl = make_controller(hybrid=object(), graph=None)
    ctl.route_question = lambda state, config: RouteDecision("combined", "llm")
    update = ctl.supervisor(routing_state("질문"))
    assert update["route"] == "hybrid"


def test_router_may_choose_combined_when_graph_is_connected():
    ctl = make_controller(hybrid=object(), graph=object())
    seen = {}

    def router(state, config):
        seen["routes"] = state["available_routes"]
        return RouteDecision("combined", "llm")

    ctl.route_question = router
    update = ctl.supervisor(routing_state("판교박물관은 몇 년에 개관하였나요?"))
    assert "combined" in seen["routes"]
    assert update["route"] == "combined"


def test_retry_after_combined_goes_to_hybrid():
    ctl = make_controller(hybrid=object(), graph=object())
    assert ctl.supervisor(routing_state("질문", retry=1, route="combined"))["route"] == "hybrid"


def test_unverified_combined_answer_abstains_without_retry():
    ctl = make_controller(hybrid=object(), graph=object())
    ctl.max_retries = 1
    state = {"route": "combined", "verified": False, "retry_count": 0, "trace": []}
    assert ctl.review(state)["next_action"] == "abstain"
    assert ctl.review({**state, "route": "hybrid"})["next_action"] == "retry"
    assert ctl.review({**state, "verified": True})["next_action"] == "finish"


def test_explicit_combined_override_retries_combined():
    ctl = make_controller(hybrid=object(), graph=object())
    update = ctl.supervisor(routing_state("질문", retry=1, route="combined", override="combined"))
    assert update["route"] == "combined"


def test_initialize_accepts_combined_override():
    ctl = make_controller(hybrid=object(), graph=object())
    assert ctl.initialize({"question": "q", "route_override": "combined"})["route_override"] == "combined"


def test_route_decision_accepts_combined():
    assert RouteDecision("combined", "x").route == "combined"


def test_descriptive_cue_examples():
    assert DESCRIPTIVE_CUE.search("신라 유물을 볼 수 있는 곳")
    assert not DESCRIPTIVE_CUE.search("같은 기관이 운영하는 다른 시설은?")


def test_router_prompt_explains_combined_route():
    from src.agent.supervisor.llm import ROUTE_PROMPT

    assert "Return combined only when" in ROUTE_PROMPT


# --------------------------------------------------------------------------- Neo4j-first filter
class BrokenIndex:
    backend = "neo4j_v2"

    def candidates(self, conditions):
        raise RuntimeError("connection refused")


class StubIndex:
    def __init__(self, backend, ids):
        self.backend = backend
        self.ids = ids

    def candidates(self, conditions):
        return {museum_id: {} for museum_id in self.ids}


def parking_conditions():
    return StructuredConditions(amenities=("주차장",), sido="서울특별시")


def test_fallback_index_uses_primary_when_it_works():
    index = FallbackIndex(StubIndex("neo4j_v2", ["A"]), StubIndex("local_csv", ["B"]))
    assert list(index.candidates(parking_conditions())) == ["A"]
    assert index.backend == "neo4j_v2"


def test_fallback_index_uses_local_table_when_neo4j_raises():
    index = FallbackIndex(BrokenIndex(), StubIndex("local_csv", ["B"]))
    assert list(index.candidates(parking_conditions())) == ["B"]
    assert index.backend == "local_csv (neo4j unavailable)"


def test_filter_decision_reports_backend_used():
    facts = [MuseumFacts("B", "서울특별시", {"주차장": ("주차장",)}, parse_closure_stub())]
    local = LocalOntologyIndex(facts)
    decision = OntologyCandidateFilter(FallbackIndex(BrokenIndex(), local)).resolve("주차장이 있는 서울 박물관")
    assert decision.status == "applied"
    assert decision.candidate_ids == ["B"]
    assert decision.backend == "local_csv (neo4j unavailable)"


def parse_closure_stub():
    from src.data_pipeline.neo4j.ontology_v2.rules import parse_closure

    return parse_closure("")


def test_build_filter_local_mode_never_touches_neo4j():
    local = StubIndex("local_csv", ["B"])
    with mock.patch("src.hybrid.ontology_filter._neo4j_index", side_effect=AssertionError("must not connect")):
        built = build_candidate_filter("local", local_index=local)
    assert built.index is local


def test_build_filter_auto_without_neo4j_uses_local_table():
    local = StubIndex("local_csv", ["B"])
    with mock.patch("src.hybrid.ontology_filter._neo4j_index", return_value=None):
        built = build_candidate_filter("auto", local_index=local)
    assert built.index is local


def test_build_filter_auto_with_neo4j_wraps_both():
    local, graph = StubIndex("local_csv", ["B"]), StubIndex("neo4j_v2", ["A"])
    built = build_candidate_filter("auto", local_index=local, graph_index=graph)
    assert isinstance(built.index, FallbackIndex)
    assert built.index.primary is graph and built.index.fallback is local


def test_neo4j_index_is_skipped_without_connection_settings():
    from src.hybrid import ontology_filter

    with mock.patch.dict(os.environ, {"NEO4J_URI": "", "NEO4J_PASSWORD": ""}):
        assert ontology_filter._neo4j_index() is None


def test_default_filter_backend_switch(monkeypatch):
    from src.hybrid import ontology_filter

    monkeypatch.setattr(ontology_filter, "_DEFAULT_FILTER", None)
    monkeypatch.setenv("HYBRID_ONTOLOGY_FILTER", "on")
    monkeypatch.setenv("HYBRID_ONTOLOGY_BACKEND", "local")
    built = default_candidate_filter()
    assert isinstance(built.index, LocalOntologyIndex)
    monkeypatch.setattr(ontology_filter, "_DEFAULT_FILTER", None)
