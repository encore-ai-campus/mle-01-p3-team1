"""Text2Cypher support for the ontology v2 labels (offline)."""

import csv
from pathlib import Path

import pytest

from src.agent.neo4j_text2cypher import (
    _organization_relation,
    _prepare_common_query,
    validate_read_only_cypher,
)

ROOT = Path(__file__).resolve().parents[3]
BASE_RETURN = """
RETURN m.museum_id AS museum_id, m.name AS name, m.amenities_raw AS text, null AS span_id,
       [] AS source_doc_ids, [] AS source_urls, m.sido AS sido, m.sigungu AS sigungu
LIMIT $top_k"""


def test_v2_labels_and_typed_relationships_are_allowed():
    query = "MATCH (m:Museum)-[r:HAS_AMENITY]->(a:Amenity)\nWHERE a.name = $amenity" + BASE_RETURN
    validated, params = validate_read_only_cypher(query, {"amenity": "수유실"}, top_k=3)
    assert "HAS_AMENITY" in validated and params["amenity"] == "수유실"


@pytest.mark.parametrize("pattern", ["[r:LIKES]", "[:HAS_SPAN|LIKES]", "[r:HAS_SPAN|:LIKES]"])
def test_unknown_relationship_is_rejected_with_variable_or_alternatives(pattern):
    query = f"MATCH (m:Museum)-{pattern}->(a:Amenity)\nWHERE a.name = $amenity" + BASE_RETURN
    with pytest.raises(ValueError, match="관계 유형"):
        validate_read_only_cypher(query, {"amenity": "x"}, top_k=3)


def test_organization_questions_use_prepared_templates():
    template, query, params = _prepare_common_query("창녕박물관과 같은 기관이 운영하는 다른 시설은?", 5)
    assert template == "same_operator"
    assert "[anchor_link:OPERATED_BY]" in query and params["relation"] == "OPERATED_BY"
    template, _, params = _prepare_common_query("박진전쟁기념관과 같은 기관이 관리하는 시설", 5)
    assert template == "same_manager" and params["relation"] == "MANAGED_BY"


def test_ownership_classification_wording_is_not_an_organization_question():
    assert _organization_relation("수원시립미술관과 같은 시도·시군구 조합에 있으면서 데이터의 운영주체 분류가 국립인 다른 시설은?") is None


def test_existing_neo4j_evaluation_questions_keep_their_templates():
    path = ROOT / "evaluations" / "datasets" / "neo4j" / "Neo4j_multihop_core10_draft.csv"
    with path.open(encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            assert _organization_relation(row["user_input"]) is None, row["user_input"]


class _FakeDriver:
    """Answers the organization template first, then the anchor query."""

    def __init__(self):
        self.queries = []

    def execute_query(self, query, **kwargs):
        self.queries.append(query)
        if "AS anchor_operator_raw_name" in query:
            row = {"museum_id": "M0001", "name": "박진전쟁기념관", "text": "{relation: OPERATED_BY}",
                   "span_id": None, "source_doc_ids": ["D1"], "source_urls": [], "source_locators": ["f#1"],
                   "sido": "경상남도", "sigungu": "창녕군", "relation": "OPERATED_BY",
                   "organization": "경상남도 창녕군", "org_type": "지방자치단체",
                   "operator_raw_name": "경상남도 창녕군", "anchor_operator_raw_name": "경상남도 창녕군청",
                   "verification_status": "SOURCE_RECORDED", "facility_type": "기념관", "graph_path": "p"}
            return [row], None, list(row)
        row = {"museum_id": "M0003", "name": "창녕박물관", "sido": "경상남도", "sigungu": "창녕군",
               "organization": "경상남도 창녕군", "org_key": "경상남도창녕군", "org_type": "지방자치단체",
               "raw_name": "경상남도 창녕군청", "verification_status": "SOURCE_RECORDED",
               "source_doc_ids": ["D3"], "source_urls": [], "source_locators": ["f#3"]}
        return [row], None, list(row)


def test_organization_answer_includes_anchor_link_as_separate_evidence():
    from src.agent.neo4j_text2cypher import Neo4jText2Cypher

    driver = _FakeDriver()
    agent = Neo4jText2Cypher(driver, "neo4j", client=object())
    evidence = agent.search("창녕박물관과 같은 기관이 운영하는 다른 시설은?", k=5)
    assert agent.last_query_template == "same_operator"
    assert [e["museum_id"] for e in evidence] == ["M0003", "M0001"]
    anchor = evidence[0]
    assert anchor["evidence_role"] == "anchor"
    assert anchor["organization"] == evidence[1]["organization"] == "경상남도 창녕군"
    assert "경상남도 창녕군청" in anchor["text"]
    assert len(driver.queries) == 2  # no LLM Cypher generation
