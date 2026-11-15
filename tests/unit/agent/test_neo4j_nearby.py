import pytest

from src.agent.neo4j_text2cypher import Neo4jText2Cypher, _prepare_common_query


QUESTION = "부산 서구에 있는 곳 하나 추천해주고 그 주위 근처에 있는 곳도 추천"


def test_nearby_region_query_returns_sourced_pair_with_distance():
    class Driver:
        def execute_query(self, query, **kwargs):
            assert "point.distance" in query
            assert "HAS_SOURCE" in query
            assert kwargs["parameters_"]["sigungu"] == "서구"
            common = {"text": "graph properties", "span_id": None, "source_urls": [],
                      "sido": "부산광역시", "sigungu": "서구", "distance_m": 0.0}
            rows = [{**common, "museum_id": "M1", "name": "첫 장소", "source_doc_ids": ["D1"],
                     "source_locators": ["file#1"], "evidence_role": "nearby_origin"},
                    {**common, "museum_id": "M2", "name": "근처 장소", "source_doc_ids": ["D2"],
                     "source_locators": ["file#2"], "evidence_role": "nearby_candidate"}]
            return rows, None, list(rows[0])
    agent = Neo4jText2Cypher(Driver(), "neo4j", client=object())
    evidence = agent.search(QUESTION)
    assert [row["evidence_role"] for row in evidence] == ["nearby_origin", "nearby_candidate"]
    assert evidence[1]["distance_m"] == 0.0
    assert evidence[1]["source_locator"] == "file#2"


@pytest.mark.parametrize("question", [
    "부산 서구에 있는 무료인 곳 하나 추천해주고 그 주위 근처에 있는 곳도 추천",
    "부산 서구에 있는 곳 하나 추천해주고 그 주위 근처에 있는 곳도 추천 1km 이내",
    "부산 서구에 있는 박물관 하나 추천해주고 그 주위 근처에 있는 곳도 추천",
])
def test_nearby_shortcut_never_discards_extra_constraints(question):
    assert _prepare_common_query(question, 5) is None


def test_nearby_without_eligible_pair_does_not_invent_fallback(monkeypatch):
    class Driver:
        def execute_query(self, query, **kwargs):
            from src.agent.neo4j_text2cypher import REQUIRED_RESULT_FIELDS
            return [], None, list(REQUIRED_RESULT_FIELDS)
    agent = Neo4jText2Cypher(Driver(), "neo4j", client=object())
    monkeypatch.setattr(agent, "generate_cypher", lambda *a, **kw: pytest.fail("no unsafe fallback"))
    assert agent.search(QUESTION) == []
