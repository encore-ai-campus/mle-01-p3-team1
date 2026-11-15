"""Only Neo4j syntax errors should trigger one Cypher regeneration."""

import json
import pytest
from neo4j.exceptions import CypherSyntaxError, ServiceUnavailable

from src.agent.neo4j_text2cypher import (
    Neo4jText2Cypher, REQUIRED_RESULT_FIELDS, _prepare_common_query,
    _same_region_text_source_terms,
)


@pytest.mark.parametrize("word", ["갖춘다고", "갖췄다고"])
def test_same_region_text_terms_match_inflected_description(word):
    question = (
        "안산산업역사박물관과 같은 시도·시군구 조합에 있는 다른 시설 중, "
        f"어린이 미술관과 한옥체험장을 함께 {word} 소개하는 곳은 어디인가요? "
        "해당 설명을 인용해주세요."
    )
    description = "어린이 미술관, 전통놀이 체험장, 한옥체험장을 갖추고 있으며"

    terms = _same_region_text_source_terms(question)

    assert terms
    assert all(term in description for term in terms)


def test_quoted_source_count_after_museum_name_uses_prepared_query():
    question = (
        '홍주성역사관 본문에서 "홍성과 충남 내포지역의 특색 있는 역사와 문화"를 '
        '소개하는 구간에 연결된 출처는 몇 개인가요? 각 문서 ID와 원본 위치를 알려주세요.'
    )

    prepared = _prepare_common_query(question, 5)

    assert prepared is not None
    template, query, params = prepared
    assert template == "quoted_source_count"
    assert params["target_name"] == "홍주성역사관"
    assert "SUPPORTED_BY" in query


class Driver:
    def __init__(self, error):
        self.error = error
        self.calls = 0

    def execute_query(self, *args, **kwargs):
        self.calls += 1
        if self.calls == 1:
            raise self.error
        return [], None, list(REQUIRED_RESULT_FIELDS)


def test_syntax_error_regenerates_and_executes_once(monkeypatch):
    driver = Driver(CypherSyntaxError("invalid WHERE"))
    agent = Neo4jText2Cypher(driver, "neo4j", client=object())
    repairs = []

    def generate(question, top_k, *, repair_error=None):
        repairs.append(repair_error)
        return "MATCH (n) RETURN n LIMIT $top_k", {"top_k": top_k}

    monkeypatch.setattr(agent, "generate_cypher", generate)
    assert agent.search("question") == []
    assert driver.calls == 2
    assert repairs[0] is None
    assert "invalid WHERE" in repairs[1]


def test_connection_error_does_not_trigger_query_repair(monkeypatch):
    driver = Driver(ServiceUnavailable("connection failed"))
    agent = Neo4jText2Cypher(driver, "neo4j", client=object())
    monkeypatch.setattr(agent, "generate_cypher", lambda *args, **kwargs: ("query", {}))
    with pytest.raises(ServiceUnavailable):
        agent.search("question")
    assert driver.calls == 1


def test_explicit_museum_names_exclude_fee_words_from_name_search(monkeypatch):
    agent = Neo4jText2Cypher(object(), "neo4j", client=object())
    fields = ", ".join(f"museum.name AS {field}" for field in sorted(REQUIRED_RESULT_FIELDS))
    query = ("MATCH (museum:Museum) WHERE any(term IN $terms WHERE "
             "toLower(museum.name) CONTAINS toLower(term)) RETURN " + fields + " LIMIT $top_k")
    monkeypatch.setattr(agent, "_chat", lambda *args, **kwargs: json.dumps({"cypher": query, "parameters": {"terms": ["어린"]}}))
    _, params = agent.generate_cypher("여주미술관과 만해기념관의 성인, 청소년, 어린이 관람료를 알려줘", 10)
    assert params["terms"] == ["여주미술관", "만해기념관"]


def test_span_search_keeps_other_terms_when_name_only_appears_in_return(monkeypatch):
    agent = Neo4jText2Cypher(object(), "neo4j", client=object())
    fields = ", ".join(f"museum.name AS {field}" for field in sorted(REQUIRED_RESULT_FIELDS))
    query = ("MATCH (museum:Museum)-[:HAS_SPAN]->(span:TextSpan) "
             "WHERE any(term IN $terms WHERE toLower(span.text) CONTAINS toLower(term)) "
             "RETURN " + fields + " LIMIT $top_k")
    monkeypatch.setattr(agent, "_chat", lambda *args, **kwargs: json.dumps({"cypher": query, "parameters": {"terms": ["전시"]}}))
    _, params = agent.generate_cypher("여주미술관 어린이 전시", 10)
    assert "어린" in params["terms"]


def test_separate_name_parameter_does_not_narrow_span_terms(monkeypatch):
    agent = Neo4jText2Cypher(object(), "neo4j", client=object())
    fields = ", ".join(f"museum.name AS {field}" for field in sorted(REQUIRED_RESULT_FIELDS))
    query = ("MATCH (museum:Museum)-[:HAS_SPAN]->(span:TextSpan) "
             "WHERE museum.name CONTAINS $name AND any(term IN $terms WHERE "
             "toLower(span.text) CONTAINS toLower(term)) RETURN " + fields + " LIMIT $top_k")
    monkeypatch.setattr(agent, "_chat", lambda *args, **kwargs: json.dumps({"cypher": query, "parameters": {"name": "여주미술관", "terms": ["전시"]}}))
    _, params = agent.generate_cypher("여주미술관 어린이 전시", 10)
    assert "어린" in params["terms"]


def test_graph_evidence_preserves_fee_text_and_source_ids(monkeypatch):
    row = {"museum_id": "M0316", "name": "여주미술관", "text": "adult_fee: 12000, youth_fee: 8000, child_fee: 6000",
           "span_id": None, "source_doc_ids": ["DOC-B0316-BASE"], "source_urls": [], "sido": "경기도", "sigungu": "여주시"}
    class FeeDriver:
        def execute_query(self, *args, **kwargs):
            return [row], None, list(row)
    agent = Neo4jText2Cypher(FeeDriver(), "neo4j", client=object())
    monkeypatch.setattr(agent, "generate_cypher", lambda *args, **kwargs: ("query", {}))
    evidence = agent.search("여주미술관 관람료")
    assert evidence[0]["text"] == row["text"]
    assert evidence[0]["source_doc_ids"] == ["DOC-B0316-BASE"]
    assert evidence[0]["source_urls"] == []


def test_same_region_query_includes_sourced_target_as_separate_evidence(monkeypatch):
    candidate = {"museum_id": "M2", "name": "후보 박물관", "text": "전시 설명", "span_id": "S2",
                 "source_doc_ids": ["D2"], "source_urls": [], "sido": "경기도", "sigungu": "여주시"}
    anchor = {"museum_id": "M1", "name": "여주박물관", "sido": "경기도", "sigungu": "여주시",
              "source_doc_ids": ["D1"], "source_urls": []}
    class Driver:
        def execute_query(self, query, **kwargs):
            if "target.name = $target_name" in query:
                assert kwargs["parameters_"] == {"target_name": "여주박물관"}
                return [anchor], None, list(anchor)
            return [candidate], None, list(candidate)
    agent = Neo4jText2Cypher(Driver(), "neo4j", client=object())
    monkeypatch.setattr(agent, "generate_cypher", lambda *args, **kwargs: ("candidate query", {"target_name": "여주박물관", "top_k": 10}))
    evidence = agent.search("여주박물관과 같은 지역에 있는 곳", 10)
    assert evidence[0]["evidence_role"] == "anchor"
    assert evidence[0]["museum_id"] == "M1"
    assert evidence[0]["sigungu"] == evidence[1]["sigungu"] == "여주시"
    assert evidence[0]["source_doc_ids"] == ["D1"]


def test_free_region_search_returns_recorded_zero_with_status_and_sources(monkeypatch):
    row = {"museum_id": "M1", "name": "강원 박물관", "text": "adult_fee: 0, adult_fee_status: BASE_FEE_ZERO_CHECK_EXCEPTIONS",
           "span_id": None, "source_doc_ids": ["D1"], "source_urls": [], "sido": "강원도", "sigungu": "강릉시",
           "adult_fee": 0, "adult_fee_status": "BASE_FEE_ZERO_CHECK_EXCEPTIONS", "fee_notes": "예외 확인"}
    class Driver:
        def execute_query(self, query, **kwargs):
            assert "museum.adult_fee = 0" in query
            assert kwargs["parameters_"]["regions"] == ["강원"]
            return [row], None, list(row)
    agent = Neo4jText2Cypher(Driver(), "neo4j", client=object())
    monkeypatch.setattr(agent, "generate_cypher", lambda *args, **kwargs: pytest.fail("region query should not need generated Cypher"))
    evidence = agent.search("강원도에 있고 무료인 곳 알려줘", 10)
    assert evidence[0]["adult_fee"] == 0
    assert evidence[0]["adult_fee_status"] == "BASE_FEE_ZERO_CHECK_EXCEPTIONS"
    assert evidence[0]["evidence_kind"] == "regional_zero_base_fee"
    assert evidence[0]["source_doc_ids"] == ["D1"]


@pytest.mark.parametrize("question", [
    "강원도 강릉시 무료인 곳", "강원도 어린이 무료 박물관", "강원도 무료와 유료를 비교해줘",
    "강원도 여주박물관 무료인가요", "강원도 무료 주차 가능한 박물관", "강원도 무료 체험 프로그램",
    "강원도 무료 미술관", "강원도 무료 국립 시설",
])
def test_free_region_shortcut_does_not_drop_specific_constraints(question):
    from src.agent.neo4j_text2cypher import _free_region
    assert _free_region(question) is None
