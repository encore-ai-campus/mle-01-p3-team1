"""The Ragas judge must be able to tell which facility a graph relation row is about (offline)."""

from src.evaluation.hybrid.ragas_eval import ragas_context


def test_graph_row_without_facility_name_in_text_gets_a_name_line():
    row = {"retriever": "graph", "name": "허준박물관",
           "text": "{anchor_raw_name: 서울특별시 강서문화원, relation: OPERATED_BY}"}
    context = ragas_context(row)
    assert context.startswith("[시설명] 허준박물관\n")
    assert "OPERATED_BY" in context


def test_graph_text_that_already_names_the_facility_is_left_alone():
    row = {"retriever": "graph", "name": "부산박물관", "text": "부산박물관의 운영기관 기록: 부산광역시"}
    assert ragas_context(row) == "부산박물관의 운영기관 기록: 부산광역시"


def test_name_from_metadata_is_used_when_the_graph_row_has_none():
    row = {"retriever": "graph", "text": "관계 기록", "metadata": {"name": "고성탈박물관"}}
    assert ragas_context(row).startswith("[시설명] 고성탈박물관\n")


def test_document_passage_is_never_changed():
    row = {"retriever": "hybrid", "name": "성북선잠박물관", "text": "조선시대 서릉씨를 모시고 제사를 지냈다."}
    assert ragas_context(row) == "조선시대 서릉씨를 모시고 제사를 지냈다."


def test_graph_row_without_any_name_is_unchanged():
    assert ragas_context({"retriever": "graph", "text": "본문"}) == "본문"


def test_name_line_comes_before_structured_records():
    row = {"retriever": "graph", "name": "성북선잠박물관", "text": "소개 본문",
           "metadata": {"structured_match": {"장애인 화장실": "CSV 항목"}}}
    context = ragas_context(row)
    assert context.splitlines()[0] == "[시설명] 성북선잠박물관"
    assert "[구조화 조건 근거]" in context
