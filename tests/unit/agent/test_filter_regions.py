"""District-level region, natural amenity wording and clearer abstain messages (offline, real CSV)."""

import pytest

from src.agent.supervisor.nodes import SupervisorController
from src.hybrid.ontology_filter import (
    LocalOntologyIndex,
    OntologyCandidateFilter,
    StructuredConditions,
    extract_conditions,
)


@pytest.fixture(scope="module")
def local_filter():
    return OntologyCandidateFilter(LocalOntologyIndex.from_csv())


# --------------------------------------------------------------------------- district names
def test_city_name_scopes_the_condition_to_that_city():
    conditions = extract_conditions("주차장 있는 경주 박물관 추천해 줘")
    assert conditions.amenities == ("주차장",)
    assert (conditions.sido, conditions.sigungu) == ("경상북도", "경주시")
    assert "경상북도 경주시" in conditions.describe()


def test_district_name_with_its_region_is_understood():
    conditions = extract_conditions("서울 종로구에 주차장이 있는 박물관")
    assert (conditions.sido, conditions.sigungu) == ("서울특별시", "종로구")


def test_full_district_name_is_understood():
    assert extract_conditions("경주시에 주차장이 있는 박물관").sigungu == "경주시"


def test_region_that_conflicts_with_the_district_is_not_narrowed():
    conditions = extract_conditions("서울에 경주 주차장이 있는 박물관")
    assert conditions.sido == "서울특별시" and conditions.sigungu is None


@pytest.mark.parametrize("question", [
    "광주에 주차장이 있는 박물관",   # 광주광역시 or 경기 광주시: do not guess
    "중구에 주차장이 있는 박물관",   # exists in many regions
])
def test_ambiguous_district_names_are_ignored(question):
    assert extract_conditions(question).sigungu is None


def test_district_alone_is_not_a_condition():
    assert not extract_conditions("경주에 있는 박물관 알려줘").has_hard_conditions


def test_gyeongju_has_no_parking_record_so_the_filter_is_empty(local_filter):
    decision = local_filter.resolve("주차장 있는 경주 박물관 추천해 줘")
    assert decision.status == "empty"
    assert decision.conditions.sigungu == "경주시"


def test_district_filter_keeps_only_that_district(local_filter):
    decision = local_filter.resolve("월요일에 문 여는 경주 박물관")
    assert decision.status == "applied"
    index = LocalOntologyIndex.from_csv()
    assert decision.candidate_ids
    assert all(index._facts[museum_id].sigungu == "경주시" for museum_id in decision.candidate_ids)


def test_district_cases_keep_both_backends_comparable():
    from src.hybrid.ontology_filter import parity_conditions

    cases = [case for case in parity_conditions() if case.sigungu]
    assert len(cases) >= 6 and all(case.sido for case in cases)


# --------------------------------------------------------------------------- natural wording
@pytest.mark.parametrize("question, amenity", [
    ("휠체어로 관람 가능한 서울 박물관이 있을까?", "휠체어 대여·이용"),
    ("주차할 수 있는 부산 박물관", "주차장"),
    ("강원도에서 월요일에 열고 주차되는 박물관 있어?", "주차장"),
    ("엘리베이터가 있는 서울 박물관", "엘리베이터·리프트"),
])
def test_natural_amenity_wording_is_understood(question, amenity):
    assert amenity in extract_conditions(question).amenities


def test_amenity_word_without_a_request_is_still_ignored():
    assert not extract_conditions("주차장 근처 박물관 이야기").has_hard_conditions


# --------------------------------------------------------------------------- messages
def test_no_record_message_names_the_district():
    summary = {"ontology_filter": {"status": "empty",
                                   "conditions": {"sido": "경상북도", "sigungu": "경주시", "amenities": ["주차장"]}}}
    message = SupervisorController._no_record_reason(summary)
    assert "경상북도 경주시" in message and "주차장" in message


def make_controller():
    ctl = object.__new__(SupervisorController)
    return ctl


def test_abstain_message_lists_what_could_not_be_confirmed():
    update = make_controller().abstain({"missing_aspects": ["전시 공간이 실내인지 여부", "운영 시간"], "trace": []})
    assert update["status"] == "abstained"
    assert "확인하지 못한 내용: 전시 공간이 실내인지 여부, 운영 시간." in update["answer"]


def test_abstain_message_without_missing_aspects_stays_short():
    update = make_controller().abstain({"missing_aspects": [], "trace": []})
    assert update["answer"] == "확인 가능한 근거가 부족하여 답변을 보류했습니다."


def test_abstain_keeps_the_no_record_explanation():
    update = make_controller().abstain({"missing_aspects": ["x"], "no_record_reason": "기록된 데이터에서 조건(지역 경상북도 경주시)을 찾지 못했습니다.",
                                        "trace": []})
    assert update["answer"].startswith("기록된 데이터에서 조건(지역 경상북도 경주시)")
    assert "확인하지 못한 내용" not in update["answer"]


def test_structured_conditions_default_has_no_district():
    assert StructuredConditions().sigungu is None
