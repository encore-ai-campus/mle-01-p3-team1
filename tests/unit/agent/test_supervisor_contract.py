"""Contract tests: use fake external services, but exercise real supervisor logic."""
from copy import deepcopy
import pytest


def evidence(text="Historical printing collection", *, span="S1", museum="M1", doc="D1"):
    return {"museum_id": museum, "text": text, "span_id": span,
            "source_doc_ids": [doc], "name": "Museum", "retriever": "graph"}


def imports():
    from src.agent.supervisor.state import AnswerDraft, RouteDecision, VerificationResult
    from src.agent.supervisor.nodes import SupervisorController
    return AnswerDraft, RouteDecision, VerificationResult, SupervisorController


def controller(*, hybrid=None, vector=None, graph=None, route="hybrid", passed=True,
               retries=1, answerer=None, verifier=None, router=None):
    Draft, Route, Verify, Controller = imports()
    return Controller(
        hybrid_search=hybrid or (lambda s, c: {"evidence": [evidence()]}),
        vector_search=vector, graph_search=graph,
        route_question=router or (lambda s, c: Route(route, "test route")),
        answer_question=answerer or (lambda s, c: Draft("Collection [E1]", ["E1"])),
        verify_answer=verifier or (lambda s, c: Verify(passed, "test verdict", [])),
        max_retries=retries,
    )


def run_nodes(ctl, request, config=None):
    """Pure-node test driver; deliberately NOT a LangGraph replacement."""
    state = dict(request)
    state.update(ctl.initialize(state))
    for _ in range(4):
        state.update(ctl.supervisor(state, config))
        if state["route"] == "abstain":
            state.update(ctl.abstain(state))
            return state
        state.update(ctl.search(state, config))
        state.update(ctl.answer(state, config))
        state.update(ctl.verify(state, config))
        state.update(ctl.review(state))
        if state["next_action"] == "finish":
            state.update(ctl.finish(state))
            return state
        if state["next_action"] == "abstain":
            state.update(ctl.abstain(state))
            return state
        state.update(ctl.retry(state))
    raise AssertionError("unbounded retry")


def test_vector_adapter_maps_document_and_keeps_museum_ids_separate_from_doc_ids():
    from src.agent.supervisor.adapters import adapt_vector, normalize_result
    class Retriever:
        def retrieve(self, *, query, top_k):
            assert (query, top_k) == ("printing", 5)
            return {"results": [{"museum_id": "M1", "document": "printing",
                    "metadata": {"source_doc_ids": '["D1"]', "sido": "Gyeonggi"}}],
                    "source_ids": ["M1"], "status": "partial", "warnings": ["review"],
                    "unsupported_constraints": ["today"], "search_summary": {"candidates": 7}}
    out = normalize_result("vector", adapt_vector(Retriever())({"question": "printing", "top_k": 5}, None), 5)
    assert out["evidence"][0]["text"] == "printing"
    assert out["evidence"][0]["source_doc_ids"] == ["D1"]
    assert out["vector_source_ids"] == ["M1"]
    assert out["vector_search_diagnostics"]["unsupported_constraints"] == ["today"]
    assert out["vector_search_status"] == "partial"


def test_museum_ids_are_never_invented_as_document_ids():
    from src.agent.supervisor.adapters import normalize_result
    out = normalize_result("vector", {"evidence": [{"museum_id": "M1", "text": "x"}],
                                     "vector_source_ids": ["M1"]}, 5)
    assert out["evidence"][0]["source_doc_ids"] == []


def test_same_museum_distinct_spans_survive_and_exact_duplicate_provenance_is_merged():
    from src.agent.supervisor.adapters import normalize_result
    a = evidence()
    b = evidence(doc="D2")
    c = evidence("Different historical event", span="S2")
    out = normalize_result("hybrid", {"evidence": [a, b, c]}, 5)
    assert len(out["evidence"]) == 2
    assert out["evidence"][0]["source_doc_ids"] == ["D1", "D2"]
    assert out["evidence"][1]["span_id"] == "S2"
    assert "evidence_id" not in a


def test_top_k_is_enforced_after_deduplication_without_score_mixing():
    from src.agent.supervisor.adapters import normalize_result
    hits = [evidence(), evidence(), evidence("two", span="S2"), evidence("three", span="S3")]
    out = normalize_result("hybrid", {"evidence": hits}, 2)
    assert [x["text"] for x in out["evidence"]] == ["Historical printing collection", "two"]


def test_hybrid_without_evidence_is_contract_error_not_silent_union():
    from src.agent.supervisor.adapters import normalize_result, ContractError
    with pytest.raises(ContractError):
        normalize_result("hybrid", {"vector_evidence": [evidence()]}, 5)


def test_invalid_evidence_fails_instead_of_fabricating_facility():
    from src.agent.supervisor.adapters import normalize_result, ContractError
    with pytest.raises(ContractError):
        normalize_result("graph", {"evidence": [{"text": "missing museum"}]}, 5)


def test_graph_adapter_uses_documented_k_parameter():
    from src.agent.supervisor.adapters import adapt_graph
    class Graph:
        def search(self, question, k):
            assert (question, k) == ("region", 3)
            return [evidence()]
    assert adapt_graph(Graph())({"question": "region", "top_k": 3}, None)["graph_evidence"][0]["museum_id"] == "M1"


def test_hybrid_adapter_passes_original_question_and_feedback():
    from src.agent.supervisor.adapters import adapt_hybrid
    seen = []
    def hybrid(state):
        seen.append(deepcopy(state))
        state["question"] = "tampered"
        return {"evidence": [evidence()]}
    request = {"question": "original", "top_k": 5, "retry_count": 1, "feedback": "missing location"}
    adapt_hybrid(hybrid)(request, None)
    assert request["question"] == "original"
    assert seen[0]["feedback"] == "missing location"


@pytest.mark.parametrize("route", ["vector", "graph", "hybrid"])
def test_route_invokes_only_selected_external_backend(route):
    seen = []
    def backend(label):
        def call(s, c):
            seen.append(label)
            return {"evidence": [evidence()]}
        return call
    ctl = controller(route=route, vector=backend("vector"), graph=backend("graph"), hybrid=backend("hybrid"))
    out = run_nodes(ctl, {"question": "test"})
    assert seen == [route]
    assert out["status"] == "answered"
    assert out["verified"] is True
    assert out["sources"][0]["source_doc_ids"] == ["D1"]


def test_missing_single_backend_falls_back_to_actual_hybrid():
    out = run_nodes(controller(route="vector"), {"question": "test"})
    assert out["route"] == "hybrid"
    assert "unavailable" in out["route_reason"]


def test_partial_alone_does_not_block_answer_when_verifier_accepts():
    def hybrid(s, c):
        return {"evidence": [evidence()], "vector_search_status": "partial",
                "vector_search_diagnostics": {"unsupported_constraints": ["location"]},
                "hybrid_search_diagnostics": {"resolved_constraints": ["location"]}}
    def verify(s, c):
        _, _, Verify, _ = imports()
        assert s["vector_search_status"] == "partial"
        assert s["hybrid_search_diagnostics"]["resolved_constraints"] == ["location"]
        return Verify(True, "location supported by graph", [])
    out = run_nodes(controller(hybrid=hybrid, verifier=verify), {"question": "test"})
    assert out["status"] == "answered"
    assert out["retry_count"] == 0


def test_vector_no_results_can_be_answered_from_graph_evidence_in_hybrid():
    def hybrid(s, c):
        return {"evidence": [evidence()], "graph_evidence": [evidence()],
                "vector_evidence": [], "vector_search_status": "no_results"}
    out = run_nodes(controller(hybrid=hybrid), {"question": "test"})
    assert out["verified"] is True


def test_retry_is_hybrid_keeps_question_and_forwards_failure_feedback():
    calls = []
    def vector(s, c):
        calls.append(("vector", s["question"]))
        return {"evidence": []}
    def hybrid(s, c):
        calls.append(("hybrid", s["question"]))
        assert s["feedback"]
        assert s["retry_count"] == 1
        return {"evidence": [evidence()]}
    out = run_nodes(controller(route="vector", vector=vector, hybrid=hybrid), {"question": "fixed original"})
    assert calls == [("vector", "fixed original"), ("hybrid", "fixed original")]
    assert out["retry_count"] == 1
    assert out["status"] == "answered"


@pytest.mark.parametrize("retries", [0, 1, 2])
def test_retry_budget_is_exact_and_exhaustion_abstains(retries):
    calls = []
    def hybrid(s, c):
        calls.append(s["retry_count"])
        return {"evidence": []}
    out = run_nodes(controller(hybrid=hybrid, retries=retries), {"question": "test"})
    assert len(calls) == retries + 1
    assert out["status"] == "abstained"
    assert out["answer"] and not out["verified"]
    assert out["sources"] == []


def test_unresolved_constraint_fails_even_with_verifier_pass_true():
    _, _, Verify, _ = imports()
    out = run_nodes(controller(retries=0, verifier=lambda s,c: Verify(True, "review", ["current opening"])), {"question": "today"})
    assert out["status"] == "abstained"
    assert "current opening" in out["failure_reason"]


@pytest.mark.parametrize("answer,ids", [("wrong [E999]", ["E999"]), ("no marker", ["E1"]), ("text [E1]", [])])
def test_bad_citations_cannot_be_approved(answer, ids):
    Draft, _, _, _ = imports()
    out = run_nodes(controller(retries=0, answerer=lambda s,c: Draft(answer, ids)), {"question": "test"})
    assert out["status"] == "abstained"


def test_missing_provenance_cannot_be_approved():
    out = run_nodes(controller(retries=0, hybrid=lambda s,c: {"evidence": [{"museum_id":"M1", "text":"x"}]}), {"question":"test"})
    assert not out["verified"]
    assert "provenance" in out["failure_reason"]


def test_external_exception_does_not_leak_secret_or_leave_old_evidence():
    def broken(s, c):
        raise RuntimeError("password=do-not-print-me")
    ctl = controller(hybrid=broken, retries=0)
    out = run_nodes(ctl, {"question": "test", "evidence": [evidence()], "verified": True})
    assert out["evidence"] == []
    assert out["status"] == "abstained"
    assert "do-not-print-me" not in repr(out)
    assert "RuntimeError" in repr(out["errors"])


def test_search_cannot_overwrite_control_state():
    def hybrid(s, c):
        return {"evidence": [evidence()], "question": "evil", "retry_count": 999, "verified": True}
    out = run_nodes(controller(hybrid=hybrid, passed=False, retries=0), {"question": "original"})
    assert out["question"] == "original"
    assert out["retry_count"] == 0
    assert out["status"] == "abstained"


def test_retry_replaces_not_appends_evidence():
    def hybrid(s, c):
        return {"evidence": [evidence("first")] if s["retry_count"] == 0 else []}
    out = run_nodes(controller(hybrid=hybrid, passed=False), {"question": "test"})
    assert out["evidence"] == []
    assert out["vector_search_diagnostics"] == {}
    assert out["status"] == "abstained"


@pytest.mark.parametrize("payload", [{"question":""}, {"question":"x","top_k":0}, {"question":"x","top_k":True}, {"question":"x","top_k":51}])
def test_invalid_request_is_rejected(payload):
    with pytest.raises(ValueError):
        controller().initialize(payload)


def test_config_reaches_backend_router_answerer_and_verifier():
    Draft, Route, Verify, _ = imports()
    seen = []
    config = {"tags": ["trace-test"]}
    def router(s, c):
        seen.append(c); return Route("hybrid", "test")
    def search(s, c):
        seen.append(c); return {"evidence": [evidence()]}
    def answer(s, c):
        seen.append(c); return Draft("test [E1]", ["E1"])
    def verify(s, c):
        seen.append(c); return Verify(True, "test", [])
    out = run_nodes(controller(router=router, hybrid=search, answerer=answer, verifier=verify), {"question":"test"}, config)
    assert out["status"] == "answered"
    assert seen == [config] * 4


def test_original_question_is_not_mutated_by_router():
    _, Route, _, _ = imports()
    def router(s, c):
        s["question"] = "modified"
        return Route("hybrid", "test")
    out = run_nodes(controller(router=router), {"question":"original"})
    assert out["question"] == "original"
