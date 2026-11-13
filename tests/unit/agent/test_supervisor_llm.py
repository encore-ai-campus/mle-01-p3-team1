"""Test LLM boundary conversion with scripted model responses, no API calls."""


class ScriptedModel:
    def __init__(self):
        self.calls = []

    def with_structured_output(self, schema, **kwargs):
        parent = self
        class Structured:
            def invoke(self, messages, config=None):
                parent.calls.append((schema.__name__, messages, config))
                if schema.__name__ == "RoutingSchema":
                    return schema(route="hybrid", reason="Both meaning and location")
                if schema.__name__ == "AnswerSchema":
                    return schema(answer="Relevant evidence [E1]", cited_evidence_ids=["E1"])
                return schema(passed=False, reason="Required date is unsupported", missing_aspects=["date"])
        return Structured()


def test_llm_routing_and_verification_are_structured_and_config_is_forwarded():
    from src.agent.supervisor.llm import LLMNodes
    from src.agent.supervisor.state import RouteDecision, AnswerDraft, VerificationResult
    model = ScriptedModel()
    nodes = LLMNodes(model)
    state = {"question": "Find a museum today", "top_k": 5, "evidence": [],
             "vector_search_status": "partial", "vector_search_diagnostics": {"unsupported_constraints": ["date"]},
             "candidate_answer": "Relevant evidence [E1]", "cited_evidence_ids": ["E1"]}
    config = {"tags": ["supervisor"]}
    route = nodes.route(state, config)
    draft = nodes.answer(state, config)
    verdict = nodes.verify(state, config)
    assert isinstance(route, RouteDecision) and route.route == "hybrid"
    assert isinstance(draft, AnswerDraft) and draft.cited_evidence_ids == ["E1"]
    assert isinstance(verdict, VerificationResult) and not verdict.passed
    assert verdict.missing_aspects == ["date"]
    assert all(call[2] == config for call in model.calls)
    assert "unsupported_constraints" in str(model.calls[-1][1])
    assert "Find a museum today" in str(model.calls[0][1])


def test_llm_validation_rejects_unknown_route():
    from src.agent.supervisor.llm import RoutingSchema
    from pydantic import ValidationError
    import pytest
    with pytest.raises(ValidationError):
        RoutingSchema(route="delete_database", reason="bad")
