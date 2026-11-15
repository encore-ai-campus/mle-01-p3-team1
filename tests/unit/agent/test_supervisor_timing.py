from types import SimpleNamespace

from src.agent.supervisor import AnswerDraft, RouteDecision, VerificationResult, build_supervisor
from src.agent.supervisor.adapters import adapt_graph
from src.agent.supervisor.run import print_timings


def test_workflow_records_each_attempt_and_guard_times():
    class Guard:
        def check_input(self, question): return SimpleNamespace(allowed=True)
        def check_output(self, question, answer): return SimpleNamespace(allowed=True)
    app = build_supervisor(
        hybrid_search=lambda s, c: {"evidence": [{"museum_id": "M1", "text": "x", "source_doc_ids": ["D1"]}],
            "hybrid_search_diagnostics": {"search_summary": {"total_duration_ms": 4, "stages": [
                {"stage": "cross_encoder_rerank", "duration_ms": 3, "model_load_ms": 1, "inference_ms": 2}]}}},
        route_question=lambda s, c: RouteDecision("hybrid", "test"),
        answer_question=lambda s, c: AnswerDraft("x [E1]", ["E1"]),
        verify_answer=lambda s, c: VerificationResult(s["retry_count"] == 1, "test", []),
        guardrails_factory=Guard,
    )
    result = app.invoke({"question": "test"})
    events = result["trace"]
    for step in ("guard_input", "supervisor", "hybrid_search", "answer", "verify", "guard_output"):
        assert all(e["duration_ms"] >= 0 for e in events if e["step"] == step)
        assert any(e["step"] == step for e in events)
    searches = [e for e in events if e["step"] == "hybrid_search"]
    assert len(searches) == 2
    assert searches[0]["search_timings"]["stages"][0]["model_load_ms"] == 1
    print_timings(result, 20)


def test_graph_adapter_forwards_request_local_timings():
    class Graph:
        def search(self, question, k=5, *, timings=None):
            timings.update(cypher_generation_ms=11, neo4j_query_ms=22)
            return [{"museum_id": "M1", "text": "x", "source_doc_ids": ["D1"]}]
    output = adapt_graph(Graph())({"question": "q", "top_k": 5})
    assert output["graph_search_diagnostics"]["cypher_generation_ms"] == 11
    assert output["graph_search_diagnostics"]["neo4j_query_ms"] == 22


def test_timing_report_shows_each_attempt_and_nested_stages(capsys):
    result = {"trace": [
        {"step": "hybrid_search", "retry_count": 0, "duration_ms": 15,
         "search_timings": {"stages": [{"stage": "cross_encoder_rerank", "duration_ms": 10,
                                          "model_load_ms": 3, "inference_ms": 7}]}},
        {"step": "graph_search", "retry_count": 1, "duration_ms": 20,
         "search_timings": {"cypher_generation_ms": 5, "neo4j_query_ms": 11}},
    ]}
    print_timings(result, 50)
    printed = capsys.readouterr().out
    for term in ("1차", "2차", "모델 로딩", "추론", "Cypher", "Neo4j"):
        assert term in printed


def test_neo4j_timing_counts_query_repair(monkeypatch):
    from neo4j.exceptions import CypherSyntaxError
    from src.agent.neo4j_text2cypher import Neo4jText2Cypher, REQUIRED_RESULT_FIELDS

    class Driver:
        calls = 0
        def execute_query(self, *args, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise CypherSyntaxError("bad query")
            return [], None, list(REQUIRED_RESULT_FIELDS)
    agent = Neo4jText2Cypher(Driver(), "neo4j", client=object())
    monkeypatch.setattr(agent, "generate_cypher", lambda *a, **k: ("query", {}))
    timings = {}
    assert agent.search("question", timings=timings) == []
    assert timings["cypher_generation_calls"] == 2
    assert timings["neo4j_query_calls"] == 2
    assert timings["cypher_generation_ms"] >= 0
    assert timings["neo4j_query_ms"] >= 0
