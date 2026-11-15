"""Actual LangGraph invoke tests. Explicit skip when dependency is absent.

No fake StateGraph is substituted. External retrieval/LLM responses are fixtures.
"""
import pytest
pytest.importorskip("langgraph.graph", reason="Real LangGraph dependency is not installed")

from src.agent.supervisor import build_supervisor, AnswerDraft, RouteDecision, VerificationResult
from src.agent.supervisor.run import build_demo_supervisor


def test_actual_graph_can_finish_and_stream_node_updates():
    app = build_demo_supervisor()
    result = app.invoke({"question": "demo"})
    assert result["status"] == "answered"
    assert result["sources"][0]["museum_id"] == "DEMO_M1"
    updates = list(app.stream({"question": "demo"}, stream_mode="updates"))
    assert any("hybrid_search" in update for update in updates)
    assert "finish" in updates[-1]


def test_actual_graph_retries_once_then_abstains_without_recursion_error():
    result = build_demo_supervisor(empty=True).invoke({"question": "missing"})
    assert result["status"] == "abstained"
    assert result["retry_count"] == 1
    assert [e["step"] for e in result["trace"]].count("hybrid_search") == 2


def test_graph_verification_retry_keeps_graph_route_for_missing_structured_fact():
    calls = []
    def graph_search(state, config):
        calls.append("graph")
        return {"evidence": [{"museum_id": "M1", "text": "adult_fee: 1000", "source_doc_ids": ["D1"]}]}
    def hybrid_search(state, config):
        calls.append("hybrid")
        return {"evidence": []}
    def verify(state, config):
        return VerificationResult(state["retry_count"] > 0, "review", [] if state["retry_count"] else ["관람료"])
    app = build_supervisor(
        hybrid_search=hybrid_search, graph_search=graph_search,
        route_question=lambda s,c: RouteDecision("graph", "fees"),
        answer_question=lambda s,c: AnswerDraft("1000원 [E1]", ["E1"]),
        verify_answer=verify,
    )
    result = app.invoke({"question": "관람료"})
    assert calls == ["graph", "graph"]
    assert result["status"] == "answered"


def test_graph_retry_falls_back_to_hybrid_for_descriptive_gap():
    # 2026-11-14 eval: repeated graph attempts on descriptive questions abstained.
    calls = []
    def graph_search(state, config):
        calls.append("graph")
        return {"evidence": [{"museum_id": "M1", "text": "region only", "source_doc_ids": ["D1"]}]}
    def hybrid_search(state, config):
        calls.append("hybrid")
        return {"evidence": [{"museum_id": "M1", "text": "전시 설명", "source_doc_ids": ["D1"]}]}
    def verify(state, config):
        return VerificationResult(state["retry_count"] > 0, "review", [] if state["retry_count"] else ["전시 내용"])
    app = build_supervisor(
        hybrid_search=hybrid_search, graph_search=graph_search,
        route_question=lambda s,c: RouteDecision("graph", "llm"),
        answer_question=lambda s,c: AnswerDraft("설명 [E1]", ["E1"]),
        verify_answer=verify,
    )
    result = app.invoke({"question": "어떤 전시가 있나요?"})
    assert calls == ["graph", "hybrid"]
    assert result["status"] == "answered"


def test_zero_fee_still_abstains_when_verifier_rejects_other_required_conditions():
    def graph_search(state, config):
        return {"evidence": [{"museum_id": "M1", "name": "강원 박물관", "text": "adult_fee: 0",
                "sido": "강원도", "sigungu": "강릉시", "source_doc_ids": ["D1"],
                "adult_fee": 0, "adult_fee_status": "BASE_FEE_ZERO_CHECK_EXCEPTIONS",
                "evidence_kind": "regional_zero_base_fee"}]}
    app = build_supervisor(
        hybrid_search=lambda s,c: {"evidence": []}, graph_search=graph_search,
        route_question=lambda s,c: RouteDecision("graph", "fee"),
        answer_question=lambda s,c: AnswerDraft("무료 [E1]", ["E1"]),
        verify_answer=lambda s,c: VerificationResult(False, "조건 미확인", ["무료 여부"]),
    )
    result = app.invoke({"question": "강원도 무료인 곳"})
    assert result["status"] == "abstained"
    assert result["verified"] is False
    assert result["sources"] == []


def test_unconfirmed_zero_without_source_still_abstains():
    def graph_search(state, config):
        return {"evidence": [{"museum_id": "M1", "name": "강원 박물관", "text": "adult_fee: 0",
                "adult_fee": 0, "adult_fee_status": "BASE_FEE_ZERO_CHECK_EXCEPTIONS",
                "evidence_kind": "regional_zero_base_fee"}]}
    app = build_supervisor(
        hybrid_search=lambda s,c: {"evidence": []}, graph_search=graph_search,
        route_question=lambda s,c: RouteDecision("graph", "fee"),
        answer_question=lambda s,c: AnswerDraft("무료 [E1]", ["E1"]),
        verify_answer=lambda s,c: VerificationResult(False, "조건 미확인", []),
        max_retries=0,
    )
    assert app.invoke({"question": "강원도 무료인 곳"})["status"] == "abstained"


def test_recorded_zero_fee_can_answer_when_verifier_accepts_draft():
    def graph_search(state, config):
        return {"evidence": [{"museum_id": "M1", "name": "강원 박물관", "text": "adult_fee: 0",
                "sido": "강원도", "sigungu": "강릉시", "source_doc_ids": ["D1"],
                "adult_fee": 0, "adult_fee_status": "BASE_FEE_ZERO_CHECK_EXCEPTIONS",
                "evidence_kind": "regional_zero_base_fee"}]}
    app = build_supervisor(
        hybrid_search=lambda s,c: {"evidence": []}, graph_search=graph_search,
        route_question=lambda s,c: RouteDecision("graph", "fee"),
        answer_question=lambda s,c: AnswerDraft("0원 후보 [E1]", ["E1"]),
        verify_answer=lambda s,c: VerificationResult(True, "조건부 후보", []),
    )
    result = app.invoke({"question": "강원도 무료인 곳"})
    assert result["status"] == "answered"
    assert result["verified"] is True
    assert result["cited_evidence_ids"] == ["E1"]


@pytest.mark.parametrize("route", ["vector", "graph", "hybrid"])
def test_actual_graph_routes_and_passes_runtime_config(route):
    called = []
    def search(label):
        def run(s, config):
            called.append(label)
            assert "unit-runtime" in config["tags"]
            return {"evidence": [{"museum_id": "M1", "text": "sample", "source_doc_ids": ["D1"]}]}
        return run
    app = build_supervisor(
        hybrid_search=search("hybrid"), vector_search=search("vector"), graph_search=search("graph"),
        route_question=lambda s,c: RouteDecision(route, "test"),
        answer_question=lambda s,c: AnswerDraft("sample [E1]", ["E1"]),
        verify_answer=lambda s,c: VerificationResult(True, "fixture", []),
    )
    out = app.invoke({"question": "query"}, config={"tags": ["unit-runtime"]})
    assert out["verified"] and called == [route]
