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
