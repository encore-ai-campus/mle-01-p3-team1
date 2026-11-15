"""Routing, guardrail retry and evaluation-context fixes after the 2026-11-14 run (offline)."""

from src.agent.supervisor.nodes import SupervisorController
from src.agent.supervisor.state import RouteDecision


def controller(graph=True):
    ctl = object.__new__(SupervisorController)
    ctl.searchers = {"hybrid": object(), "vector": None, "graph": object() if graph else None}
    ctl.region_theme_routing = True
    ctl.route_question = lambda state, config: RouteDecision("hybrid", "llm router")
    return ctl


def state(question, retry=0, route="hybrid", override="auto"):
    return {"question": question, "retry_count": retry, "route": route, "route_override": override,
            "missing_aspects": [], "feedback": "", "trace": []}


def test_failed_graph_attempt_retries_with_hybrid():
    update = controller().supervisor(state("판교박물관은 몇 년에 개관하였나요?", retry=1, route="graph"))
    assert update["route"] == "hybrid"


def test_explicit_graph_override_still_retries_graph():
    update = controller().supervisor(state("질문", retry=1, route="graph", override="graph"))
    assert update["route"] == "graph"


def test_prepared_graph_question_skips_llm_router():
    update = controller().supervisor(state("창녕박물관과 같은 기관이 운영하는 다른 시설은?"))
    assert update["route"] == "graph"
    assert "same_operator" in update["route_reason"]


def test_prepared_graph_shortcut_needs_connected_graph():
    update = controller(graph=False).supervisor(state("창녕박물관과 같은 기관이 운영하는 다른 시설은?"))
    assert update["route"] == "hybrid"


def test_descriptive_question_goes_to_llm_router():
    update = controller().supervisor(state("판교박물관은 몇 년에 개관하였나요?"))
    assert update["route_reason"] == "llm router"


def test_router_prompt_no_longer_prefers_graph_for_regions():
    from src.agent.supervisor.llm import ROUTE_PROMPT

    assert "prefer graph when connected" not in ROUTE_PROMPT
    assert "A region alone is not a reason to choose graph" in ROUTE_PROMPT


def test_guardrail_check_retries_once(monkeypatch):
    from src.guardrails import guard

    class Rails:
        calls = 0

        async def check_async(self, messages, rail_types):
            Rails.calls += 1
            if Rails.calls == 1:
                raise TimeoutError("first check during start-up")
            from nemoguardrails.rails.llm.options import RailStatus
            return type("R", (), {"status": RailStatus.PASSED, "rail": None})()

    g = guard.Guardrails(rails=Rails(), use_llm=True)
    result = g.check_input("박물관 추천해줘")
    assert result.allowed and Rails.calls == 2


def test_ragas_context_includes_structured_records_and_ranking_skips_anchor():
    from src.evaluation.hybrid.ragas_eval import ragas_context, ranking_scores

    item = {"text": "본문", "metadata": {"structured_match": "편의시설 '카페': CSV amenities_raw의 '카페테리아' 항목"},
            "metadata_provenance": {"fields": {"amenities_raw": "주차장+카페테리아", "closure_rule_raw": "월"}}}
    context = ragas_context(item)
    assert "카페테리아" in context and "[CSV 휴관 규칙 기록] 월" in context
    evidence = [{"museum_id": "ANCHOR", "evidence_role": "anchor"}, {"museum_id": "GOLD"}]
    assert ranking_scores(["GOLD"], evidence, True)["hit_at_1"] == 1
