"""The verifier is separate from the Supervisor: rule checks first, then the LLM judge."""
import pytest

from src.agent.supervisor.state import VerificationResult
from src.agent.supervisor.verifier import AnswerVerifier, LLMVerifier


def _state(**override):
    state = {
        "question": "q", "failure_reason": "",
        "candidate_answer": "A museum [E1]", "cited_evidence_ids": ["E1"],
        "evidence": [{"evidence_id": "E1", "source_locator": "data/x.csv#row=1"}],
    }
    state.update(override)
    return state


class Judge:
    def __init__(self, result):
        self.result, self.calls = result, 0

    def __call__(self, state, config=None):
        self.calls += 1
        return self.result


def test_passing_answer_reaches_the_judge_and_passes():
    judge = Judge(VerificationResult(True, "supported", []))
    outcome = AnswerVerifier(judge).verify(_state())
    assert outcome.verified and outcome.reason == "supported" and judge.calls == 1


@pytest.mark.parametrize("override, reason", [
    ({"evidence": []}, "No evidence returned"),
    ({"candidate_answer": "  "}, "Empty answer"),
    ({"candidate_answer": "A museum [E2]", "cited_evidence_ids": ["E2"]}, "Missing, unknown, or inconsistent evidence citations"),
    ({"candidate_answer": "A museum"}, "Missing, unknown, or inconsistent evidence citations"),
    ({"evidence": [{"evidence_id": "E1"}]}, "Cited evidence has no source provenance"),
])
def test_rule_failures_never_call_the_judge(override, reason):
    judge = Judge(VerificationResult(True, "supported", []))
    outcome = AnswerVerifier(judge).verify(_state(**override))
    assert not outcome.verified and outcome.structural_failure and outcome.reason == reason
    assert judge.calls == 0


def test_missing_aspects_fail_even_if_the_judge_said_passed():
    outcome = AnswerVerifier(Judge(VerificationResult(True, "ok", ["fee"]))).verify(_state())
    assert not outcome.verified and outcome.missing_aspects == ["fee"]
    assert outcome.reason == "ok; unresolved: fee"


def test_judge_failure_is_reported_as_an_error_not_a_crash():
    def broken(state, config=None):
        raise TimeoutError("slow")

    outcome = AnswerVerifier(broken).verify(_state())
    assert not outcome.verified and isinstance(outcome.error, TimeoutError)
    assert outcome.reason == "Verification failed (TimeoutError)"


def test_wrong_judge_result_type_is_an_error():
    outcome = AnswerVerifier(lambda s, c=None: True).verify(_state())
    assert isinstance(outcome.error, TypeError)


def test_llm_verifier_sends_the_shared_evidence_json_and_the_answer():
    class Model:
        def __init__(self):
            self.messages = None

        def with_structured_output(self, schema, **kwargs):
            parent = self

            class Chain:
                def invoke(self, messages, config=None):
                    parent.messages = messages
                    return schema(passed=True, reason="supported", missing_aspects=[])

            return Chain()

    model = Model()
    verdict = LLMVerifier(model)(_state(evidence=[{"evidence_id": "E1", "name": "Museum", "text": "body",
                                                    "bm25_score": 9.9}]))
    assert verdict.passed
    human = model.messages[1][1]
    assert "grounded-evidence-v2" in human and "Museum" in human and "A museum [E1]" in human
    assert "bm25_score" not in human
