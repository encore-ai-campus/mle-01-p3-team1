"""A verification failure on the wording gets one rewrite from the same evidence."""
from src.agent.supervisor import AnswerDraft, RouteDecision, VerificationResult, build_supervisor

ROW = {"museum_id": "M1", "name": "박진전쟁기념관", "text": "월요일 휴관", "source_locator": "data/x.csv#row=1",
       "retriever": "hybrid"}


class Recorder:
    def __init__(self, verdicts, route="hybrid"):
        self.verdicts, self.route = list(verdicts), route
        self.searches = self.answers = self.verifies = 0
        self.seen_feedback = []

    def search(self, state, config=None):
        self.searches += 1
        return {"evidence": [dict(ROW)], "hybrid_search_diagnostics": {"search_summary": {}}}

    def answer(self, state, config=None):
        self.answers += 1
        self.seen_feedback.append((state.get("feedback", ""), state.get("previous_answer", "")))
        return AnswerDraft(f"답변 v{self.answers} [E1]", ["E1"])

    def verify(self, state, config=None):
        self.verifies += 1
        passed, reason = self.verdicts.pop(0)
        return VerificationResult(passed, reason, [])

    def graph(self, **kwargs):
        return build_supervisor(
            hybrid_search=self.search, graph_search=self.search if self.route == "combined" else None,
            route_question=lambda s, c: RouteDecision(self.route, "test"),
            answer_question=self.answer, verify_answer=self.verify, **kwargs)


def test_wording_error_is_rewritten_from_the_same_evidence():
    rec = Recorder([(False, "'매일'은 월요일 휴관 기록과 모순"), (True, "supported")])
    result = rec.graph(max_retries=1).invoke({"question": "q", "top_k": 5})
    assert result["status"] == "answered" and result["answer"].startswith("답변 v2")
    assert rec.searches == 1 and rec.answers == 2 and rec.verifies == 2
    assert rec.seen_feedback[0] == ("", "")
    assert rec.seen_feedback[1] == ("'매일'은 월요일 휴관 기록과 모순", "답변 v1 [E1]")
    assert any(step["step"] == "revise" for step in result["trace"])


def test_combined_route_is_rewritten_without_searching_again():
    rec = Recorder([(False, "wording"), (True, "supported")], route="combined")
    result = rec.graph(max_retries=1).invoke({"question": "q", "top_k": 5})
    assert result["status"] == "answered"
    assert rec.answers == 2
    assert rec.searches == 2  # the combined search itself runs graph + document once each


def test_only_one_rewrite_then_the_normal_path_continues():
    rec = Recorder([(False, "still wrong"), (False, "still wrong")], route="combined")
    result = rec.graph(max_retries=1).invoke({"question": "q", "top_k": 5})
    assert result["status"] == "abstained"
    assert rec.answers == 2 and rec.searches == 2  # no repeated search for combined


def test_rewrite_can_be_turned_off():
    rec = Recorder([(False, "wording")])
    result = rec.graph(max_retries=0, max_revisions=0).invoke({"question": "q", "top_k": 5})
    assert result["status"] == "abstained" and rec.answers == 1


def test_missing_citation_is_not_rewritten():
    class BadAnswer(Recorder):
        def answer(self, state, config=None):
            self.answers += 1
            return AnswerDraft("근거 번호 없는 답변", [])

    rec = BadAnswer([])
    result = rec.graph(max_retries=0).invoke({"question": "q", "top_k": 5})
    assert result["status"] == "abstained" and rec.answers == 1 and rec.verifies == 0


def test_search_is_repeated_after_a_rewrite_that_still_fails_on_a_non_combined_route():
    rec = Recorder([(False, "a"), (False, "b"), (True, "supported")])
    result = rec.graph(max_retries=1).invoke({"question": "q", "top_k": 5})
    assert result["status"] == "answered"
    assert rec.searches == 2 and rec.answers == 3  # rewrite once, search again, new answer
