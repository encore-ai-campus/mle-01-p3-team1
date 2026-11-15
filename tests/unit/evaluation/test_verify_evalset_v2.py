"""The label checker reads raw CSV values with its own simple patterns (offline)."""

from src.evaluation.verify_evalset_v2 import Verifier, amenity_hit, closed_days, crude_org_key, sido_key


def test_closed_days_reads_weekday_words_and_single_letters():
    assert closed_days("매주 월요일+1월 1일+설날+추석날") == {"월"}
    assert closed_days("월+토+일") == {"월", "토", "일"}
    assert closed_days("매주 월요일(공휴일인 월요일 제외), 1월 1일") == {"월"}
    assert closed_days("연중무휴") == set()


def test_closed_days_ignores_opening_hours():
    assert closed_days("일요일·법정공휴일 휴관; 토요일 10:00~13:00") == {"일"}


def test_amenity_patterns_match_raw_wording_not_mapped_labels():
    assert amenity_hit("은서네집 매점+공동취사장+수유실", "수유실") is True
    assert amenity_hit("한식당+통찻집", "카페") is False
    assert amenity_hit("주차장(26대)+카페테리아", "카페") is True
    assert amenity_hit("anything", "알 수 없는 항목") is None


def test_organization_keys_ignore_region_prefix_and_office_suffix():
    assert crude_org_key("경상남도 창녕군청") == crude_org_key("창녕군") == "창녕군"
    assert crude_org_key("(재)인천중구문화재단") == crude_org_key("재단법인 인천중구문화재단")


def test_old_and_new_region_spellings_are_one_region():
    assert sido_key("전라북도") == sido_key("전북특별자치도")


def make_verifier():
    museums = [
        {"museum_id": "A", "name": "가박물관", "sido": "서울특별시", "amenities_raw": "수유실", "closure_rule_raw": "매주 월요일",
         "operator_name": "서울특별시 강서문화원", "manager_name": "", "text": "가박물관은 근대 유물을 전시한다."},
        {"museum_id": "B", "name": "나박물관", "sido": "서울특별시", "amenities_raw": "수유실+카페", "closure_rule_raw": "월",
         "operator_name": "강서문화원", "manager_name": "", "text": "나박물관 소개"},
    ]
    return Verifier(museums)


def label(**values):
    base = {"question_id": "Q", "category": "", "source_set": "v2", "answerable": "yes", "user_input": "", "reference": "x",
            "reference_contexts": "[\"c\"]", "gold_museum_ids": "", "gold_museum_names": "", "evidence_quote": ""}
    base.update(values)
    return base


def test_common_check_flags_unknown_ids_and_name_mismatch():
    verifier = make_verifier()
    problems = verifier.check_common(label(gold_museum_ids="A;Z", gold_museum_names="가박물관;다박물관"))
    assert any("Z" in problem and "없음" in problem for problem in problems)
    assert verifier.check_common(label(gold_museum_ids="A", gold_museum_names="나박물관"))


def test_same_operator_check_finds_the_other_facility():
    verifier = make_verifier()
    good = label(user_input="가박물관과 같은 기관이 운영하는 다른 시설은?", gold_museum_ids="B")
    bad = label(user_input="가박물관과 같은 기관이 운영하는 다른 시설은?", gold_museum_ids="")
    assert verifier.check_org(good, "operator_name") == []
    assert "정답에 없음" in verifier.check_org(bad, "operator_name")[0]


def test_amenity_check_compares_gold_with_the_raw_columns():
    verifier = make_verifier()
    reference = "서울특별시에서 편의시설 기록에 '수유실'이(가) 있는 시설은 가박물관, 나박물관입니다."
    assert verifier.check_amenity(label(reference=reference, gold_museum_ids="A;B")) == []
    assert verifier.check_amenity(label(reference=reference, gold_museum_ids="A"))


def test_v1_quote_must_appear_in_the_museum_text():
    verifier = make_verifier()
    assert verifier.check_v1_quote(label(source_set="v1", gold_museum_ids="A", evidence_quote="근대 유물을 전시한다")) == []
    assert verifier.check_v1_quote(label(source_set="v1", gold_museum_ids="A", evidence_quote="전혀 다른 문장"))
