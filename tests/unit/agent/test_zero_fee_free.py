"""A recorded zero adult base fee supports a dataset-level free admission answer."""

import pytest

pytest.importorskip("langgraph.graph")

from src.agent.neo4j_text2cypher import Neo4jText2Cypher, _prepare_common_query
from src.agent.supervisor import AnswerDraft, RouteDecision, VerificationResult, build_supervisor


def test_zero_fee_graph_answer_can_finish_when_verified():
    app = build_supervisor(
        hybrid_search=lambda state, config: {"evidence": []},
        graph_search=lambda state, config: {"evidence": [{
            "museum_id": "M1", "name": "무료 미술관", "text": "adult_fee: 0",
            "adult_fee": 0, "adult_fee_status": "BASE_FEE_ZERO_CHECK_EXCEPTIONS",
            "source_doc_ids": ["D1"], "evidence_kind": "regional_zero_base_fee",
        }]},
        route_question=lambda state, config: RouteDecision("graph", "fee"),
        answer_question=lambda state, config: AnswerDraft("자료상 성인 기본 관람료가 무료입니다. [E1]", ["E1"]),
        verify_answer=lambda state, config: VerificationResult(True, "기록된 요금 확인", []),
    )

    result = app.invoke({"question": "무료 미술관은?"})

    assert result["status"] == "answered"
    assert result["verified"] is True
    assert result["sources"][0]["adult_fee"] == 0


def test_same_province_excluded_district_free_art_uses_parameterized_query():
    prepared = _prepare_common_query(
        "서울역사박물관과 같은 서울특별시에 있으면서 종로구가 아닌 무료 미술관은?", 5
    )

    assert prepared is not None
    name, query, params = prepared
    assert name == "same_sido_excluded_sigungu_free_art"
    assert params["target_name"] == "서울역사박물관"
    assert params["excluded_sigungu"] == "종로구"
    assert params["regions"] == ["서울특별시"]
    assert params["require_free"] is True
    assert "candidate.adult_fee = 0" in query
    assert "candidate_region.name <> $excluded_sigungu" in query
    assert "source_locators" in query


def test_composite_free_art_shortcut_does_not_drop_other_constraints():
    prepared = _prepare_common_query(
        "서울역사박물관과 같은 서울특별시에 있으면서 종로구가 아닌 무료 미술관 중 야간 전시하는 곳은?", 5
    )

    assert prepared is None


def test_incheon_same_province_outside_district_returns_anchor_and_art_museum(monkeypatch):
    question = "인천광역시립박물관과 같은 인천광역시에 있지만 연수구 밖에 있는 미술관은?"
    candidate = {
        "museum_id": "M2", "name": "송암미술관", "text": "인천 미술관",
        "span_id": None, "source_doc_ids": ["D2"], "source_urls": [],
        "source_locators": ["data.csv#row=2"], "sido": "인천광역시", "sigungu": "미추홀구",
    }
    anchor = {
        "museum_id": "M1", "name": "인천광역시립박물관",
        "source_doc_ids": ["D1"], "source_urls": [],
        "source_locators": ["data.csv#row=1"], "sido": "인천광역시", "sigungu": "연수구",
    }

    class Driver:
        def execute_query(self, query, **kwargs):
            if "target.name = $target_name" in query:
                return [anchor], None, list(anchor)
            assert "candidate_region.name <> $excluded_sigungu" in query
            assert kwargs["parameters_"]["excluded_sigungu"] == "연수구"
            return [candidate], None, list(candidate)

    agent = Neo4jText2Cypher(Driver(), "neo4j", client=object())
    monkeypatch.setattr(agent, "generate_cypher", lambda *args, **kwargs: pytest.fail("prepared query expected"))

    evidence = agent.search(question, 5)

    assert agent.last_query_template == "same_sido_excluded_sigungu_art"
    assert agent.last_parameters["require_free"] is False
    assert [item["museum_id"] for item in evidence] == ["M1", "M2"]
    assert evidence[0]["evidence_role"] == "anchor"
    assert evidence[0]["source_doc_ids"] == ["D1"]
    assert evidence[1]["sigungu"] == "미추홀구"
