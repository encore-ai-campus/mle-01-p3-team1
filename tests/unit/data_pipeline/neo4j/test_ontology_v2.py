"""Ontology v2 rule and Cypher generation tests (no database access)."""

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_ROOT))

from src.data_pipeline.neo4j.ontology_v2 import apply_cypher, build_cypher  # noqa: E402
from src.data_pipeline.neo4j.ontology_v2.rules import (  # noqa: E402
    classify_facility_type,
    classify_org_type,
    is_self_named,
    map_amenity_token,
    match_topics,
    parse_closure,
    resolve_org,
    split_amenity_tokens,
)

CSV_PATH = PROJECT_ROOT / "data" / "processed" / "museum_final_738.csv"


class OrganizationRuleTests(unittest.TestCase):
    def test_city_hall_spellings_share_one_local_government(self) -> None:
        a = resolve_org("경기도 구리시청", "경기도")
        b = resolve_org("경기도 구리시", "경기도")
        self.assertEqual(a.org.org_key, b.org.org_key)
        self.assertEqual(a.org.level, "기초지자체")

    def test_department_is_separate_node_linked_to_parent(self) -> None:
        result = resolve_org("경기도 부천시청 문화예술과 문화종무팀", "경기도")
        self.assertEqual(result.org.level, "지자체 부서")
        self.assertEqual(result.parent.name, "경기도 부천시")
        self.assertNotEqual(result.org.org_key, result.parent.org_key)

    def test_sido_is_borrowed_from_museum_row_when_missing(self) -> None:
        result = resolve_org("홍성군", "충청남도")
        self.assertEqual(result.org.name, "충청남도 홍성군")
        self.assertIn("sido_from_museum_row", result.notes)

    def test_generic_affiliate_is_qualified_by_parent(self) -> None:
        a = resolve_org("경기도 고양시 농업기술센터", "경기도")
        b = resolve_org("고양시 농업기술센터", "경기도")
        self.assertEqual(a.org.name, "경기도 고양시 농업기술센터")
        self.assertEqual(a.org.org_key, b.org.org_key)

    def test_affiliate_department_builds_two_level_chain(self) -> None:
        result = resolve_org("대전광역시 교육청 교육정책과", "대전광역시")
        names = [(child.name, parent.name) for child, parent in result.edges]
        self.assertIn(("대전광역시 교육청", "대전광역시"), names)
        self.assertIn(("대전광역시 교육청 교육정책과", "대전광역시 교육청"), names)

    def test_university_is_not_attached_to_province(self) -> None:
        result = resolve_org("경상남도 인제대학교 박물관", "경상남도")
        self.assertIsNone(result.parent)
        self.assertEqual(result.org.org_type, "대학·학교법인")

    def test_non_org_value_is_skipped(self) -> None:
        self.assertIsNone(resolve_org("사립", "서울특별시"))

    def test_org_type_keywords_do_not_misfire_on_museum_names(self) -> None:
        self.assertEqual(classify_org_type("부산현대미술관"), "문화시설")
        self.assertEqual(classify_org_type("현대백화점"), "기업")
        self.assertEqual(classify_org_type("(주)아트507"), "기업")
        self.assertEqual(classify_org_type("국립중앙극장"), "국립기관")

    def test_self_named_operator(self) -> None:
        self.assertTrue(is_self_named("다도박물관", "다도박물관"))
        self.assertFalse(is_self_named("경기도 수원시", "수원시립미술관"))


class FacilityAmenityOpeningTests(unittest.TestCase):
    def test_facility_type_uses_last_keyword(self) -> None:
        self.assertEqual(classify_facility_type("박진전쟁기념관")[0], "기념관")
        self.assertEqual(classify_facility_type("성산패총(유물전시관)")[0], "전시관")
        self.assertEqual(classify_facility_type("넥슨뮤지엄"), ("박물관", "name_keyword"))

    def test_amenity_tokens_map_to_controlled_vocabulary(self) -> None:
        tokens = split_amenity_tokens("장애인화장실+유모차/휠체어 대여+카페, 주차장, 무선인터넷")
        mapped = {name for token in tokens for name in map_amenity_token(token)}
        self.assertEqual(mapped, {"장애인 화장실", "휠체어 대여·이용", "유모차 대여", "카페", "주차장", "무선인터넷"})
        self.assertEqual(map_amenity_token("없음"), [])
        self.assertEqual(map_amenity_token("전시실"), [])
        self.assertEqual(map_amenity_token("강아지의무실"), [])

    def test_closure_rule_parsing(self) -> None:
        parsed = parse_closure("월(단, 월요일이 공휴일인 경우 당일은 개관하고 그 다음날 휴관)+1월1일+설+추석 당일")
        self.assertEqual(parsed["closure_weekdays"], ["월"])
        self.assertTrue(parsed["holiday_closure_exception"])
        self.assertTrue(parsed["closed_new_year"] and parsed["closed_seollal"] and parsed["closed_chuseok"])
        self.assertFalse(parsed["closed_public_holidays"])
        self.assertTrue(parse_closure("연중무휴")["open_all_year"])
        self.assertEqual(parse_closure("주말+공휴일")["closure_weekdays"], ["토", "일"])
        self.assertEqual(parse_closure("첫·셋째주월요일")["closure_parse_status"], "unparsed")
        self.assertFalse(parse_closure("월+명절당일+공휴일 익일")["closed_public_holidays"])


class TopicTests(unittest.TestCase):
    def test_topic_needs_name_hit_or_repeated_evidence(self) -> None:
        spans = [("X:000", "6·25전쟁 당시 격전지였다."), ("X:001", "한국전쟁 전투를 재현한다.")]
        topics = {m.topic: m for m in match_topics("어느기념관", spans)}
        self.assertIn("6·25전쟁", topics)
        self.assertEqual(topics["6·25전쟁"].span_ids, ("X:000", "X:001"))
        single = match_topics("어느박물관", [("Y:000", "사진 한 장이 남아 있다.")])
        self.assertEqual(single, [])

    def test_short_keywords_do_not_match_inside_other_words(self) -> None:
        spans = [("Z:000", "미술과 예술, 기술을 다룬다. 화장실이 있다.")] * 3
        topics = {m.topic for m in match_topics("미술관", spans)}
        self.assertNotIn("음식·차", topics)
        self.assertNotIn("복식·화장", topics)


class CypherGenerationTests(unittest.TestCase):
    def test_literal_escaping(self) -> None:
        self.assertEqual(build_cypher.lit({"a": 'x"y', "b": [1, None, True]}), '{a: "x\\"y", b: [1, null, true]}')

    def test_build_is_additive_and_consistent_with_csv(self) -> None:
        before = CSV_PATH.read_bytes()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            summary = build_cypher.build(CSV_PATH, out)
            scripts = {path.name: path.read_text(encoding="utf-8") for path in out.glob("*.cypher")}
        self.assertEqual(CSV_PATH.read_bytes(), before, "CSV must stay unchanged")
        self.assertEqual(summary["expected"]["Museums with facility_type"], 738)
        self.assertGreater(summary["expected"]["OPERATED_BY"], 700)
        for name, text in scripts.items():
            if name == "99_rollback.cypher":
                continue
            self.assertNotRegex(text, r"\b(DELETE|REMOVE|DETACH)\b", name)
            self.assertNotRegex(text, r"MERGE \((?:s|g):(?:Sido|Sigungu)", name)
        rollback = scripts["99_rollback.cypher"]
        self.assertIn("ontology_version = 'v2'", rollback)
        self.assertNotRegex(rollback, r"DETACH DELETE m\b")

    def test_apply_splits_generated_scripts_and_verify_aggregates_first(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            summary = build_cypher.build(CSV_PATH, out)
            for name, count in summary["statements"].items():
                statements = apply_cypher.read_statements(out / name)
                self.assertEqual(len(statements), count, name)
                self.assertTrue(all(not s.endswith(";") and not s.startswith("//") for s in statements))
            verify_query = apply_cypher.read_statements(out / "90_verify.cypher")[0]
        # A constant beside count() would be a grouping key and return no row when empty.
        self.assertNotRegex(verify_query, r"RETURN \"[^\"]+\" AS check, count\(")

    def test_rollback_requires_explicit_confirmation(self) -> None:
        with self.assertRaises(SystemExit):
            apply_cypher.main(["--rollback"])


if __name__ == "__main__":
    unittest.main()
