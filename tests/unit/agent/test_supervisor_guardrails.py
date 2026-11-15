from types import SimpleNamespace

from src.agent.supervisor import AnswerDraft, RouteDecision, VerificationResult, build_supervisor


class Guard:
    def __init__(self, input_allowed=True, output_allowed=True):
        self.input_allowed = input_allowed
        self.output_allowed = output_allowed

    def check_input(self, question):
        return SimpleNamespace(allowed=self.input_allowed, message="입력 차단")

    def check_output(self, question, answer):
        return SimpleNamespace(allowed=self.output_allowed, message="출력 차단")


def make_app(guard, calls):
    def search(state, config):
        calls.append("search")
        return {"evidence": [{"museum_id": "M1", "text": "전시", "source_doc_ids": ["D1"]}]}
    return build_supervisor(
        hybrid_search=search,
        route_question=lambda s, c: RouteDecision("hybrid", ""),
        answer_question=lambda s, c: AnswerDraft("전시 [E1]", ["E1"]),
        verify_answer=lambda s, c: VerificationResult(True, "확인", []),
        guardrails_factory=lambda: guard,
    )


def test_blocked_input_does_not_search():
    calls = []
    result = make_app(Guard(input_allowed=False), calls).invoke({"question": "질문"})
    assert calls == []
    assert result["status"] == "blocked"
    assert result["answer"] == "입력 차단"


def test_blocked_output_is_not_returned_with_sources():
    calls = []
    result = make_app(Guard(output_allowed=False), calls).invoke({"question": "질문"})
    assert calls == ["search"]
    assert result["status"] == "blocked"
    assert result["answer"] == "출력 차단"
    assert result["sources"] == []
    assert result["candidate_answer"] == ""


def test_allowed_request_preserves_answer_and_sources():
    result = make_app(Guard(), []).invoke({"question": "질문"})
    assert result["status"] == "answered"
    assert result["answer"] == "전시 [E1]"
    assert result["sources"][0]["museum_id"] == "M1"


def test_guard_failure_blocks_before_search():
    class BrokenGuard(Guard):
        def check_input(self, question):
            raise RuntimeError("unavailable")

    calls = []
    result = make_app(BrokenGuard(), calls).invoke({"question": "질문"})
    assert result["status"] == "blocked"
    assert calls == []


def test_connected_supervisor_runs_injected_guard_before_retrieval(monkeypatch):
    from src.agent.supervisor import connect, llm

    class FakeNodes:
        def __init__(self, _llm):
            pass

        route = staticmethod(lambda s, c: RouteDecision("hybrid", ""))
        answer = staticmethod(lambda s, c: AnswerDraft("", []))
        verify = staticmethod(lambda s, c: VerificationResult(False, "", []))

    monkeypatch.setattr(llm, "LLMNodes", FakeNodes)
    calls = []
    app = connect.build_connected_supervisor(
        hybrid_node=lambda state: calls.append("search"), llm=object(),
        guardrails_factory=lambda: Guard(input_allowed=False),
    )
    result = app.invoke({"question": "질문"})
    assert result["status"] == "blocked"
    assert calls == []
