"""Ontology candidate filter: extraction, backends, and Hybrid integration (offline)."""

import unittest

from src.hybrid.bm25_reranker import SpanDocument
from src.hybrid.bm25_retriever import BM25SpanRetriever
from src.hybrid.config import HybridConfig
from src.hybrid.ontology_filter import (
    FilterDecision,
    LocalOntologyIndex,
    MuseumFacts,
    Neo4jOntologyIndex,
    OntologyCandidateFilter,
    StructuredConditions,
    default_candidate_filter,
    extract_conditions,
)
from src.hybrid.service import HybridSearchService


def facts(mid, sido, amenities=(), weekdays=(), status="parsed", all_year=False):
    return MuseumFacts(
        museum_id=mid,
        sido=sido,
        amenities={name: (name,) for name in amenities},
        closure={"closure_weekdays": list(weekdays), "open_all_year": all_year, "closure_parse_status": status},
    )


class ExtractionTests(unittest.TestCase):
    def test_amenity_and_weekday_conditions_with_region(self) -> None:
        c = extract_conditions("제주에서 수유실 있고 월요일에도 여는 미술관")
        self.assertEqual(c.amenities, ("수유실",))
        self.assertEqual(c.open_weekdays, ("월",))
        self.assertEqual(c.sido, "제주특별자치도")

    def test_modifier_word_and_weekend(self) -> None:
        c = extract_conditions("주말에 문 여는 서울 박물관 중 휠체어 대여 되는 곳")
        self.assertEqual(c.amenities, ("휠체어 대여·이용",))
        self.assertEqual(c.open_weekdays, ("토", "일"))

    def test_disabled_parking_does_not_also_require_general_parking(self) -> None:
        self.assertEqual(extract_conditions("장애인 주차 가능한 곳").amenities, ("장애인 주차구역",))

    def test_descriptive_words_and_counts_are_not_hard_conditions(self) -> None:
        for question in (
            "경기도 권에 있고 자연과 관련된 곳이면 좋겠음",          # theme stays semantic
            "고려청자를 볼 수 있는 미술관은?",                     # facility word stays semantic
            "창원시립진해박물관의 장애인 전용 주차면은 몇 면인가요?",  # a count, not a presence
            "박진전쟁기념관이 오늘 임시 휴관하는지 실시간으로 확인해줘.",
        ):
            self.assertFalse(extract_conditions(question).has_hard_conditions, question)
            self.assertIsNone(extract_conditions(question).sido)

    def test_existing_evaluation_questions_are_untouched(self) -> None:
        import csv
        from pathlib import Path

        root = Path(__file__).resolve().parents[3] / "evaluations" / "datasets"
        files = [root / "archive" / "v1_2026-11-13" / "langgraph" / "LangGraph_Ragas_평가셋_30문항.csv",
                 root / "archive" / "v1_2026-11-13" / "langgraph" / "LangGraph_Ragas_150_draft.csv",
                 root / "neo4j" / "Neo4j_multihop_core10_draft.csv"]
        for path in files:
            with path.open(encoding="utf-8-sig", newline="") as file:
                for row in csv.DictReader(file):
                    self.assertFalse(extract_conditions(row["user_input"]).has_hard_conditions, row["user_input"])


class LocalIndexTests(unittest.TestCase):
    def setUp(self) -> None:
        self.index = LocalOntologyIndex([
            facts("A", "세종특별시", amenities=("수유실",)),
            facts("B", "세종특별자치시", amenities=("수유실",), weekdays=("월",)),
            facts("C", "세종특별자치시", amenities=("수유실",), status="unparsed"),
            facts("D", "세종특별자치시", amenities=("수유실",), status="parsed", all_year=True),
            facts("E", "경기도", amenities=("수유실",)),
            facts("F", "전라북도", amenities=("카페",)),
        ])

    def test_region_spellings_amenity_and_open_day(self) -> None:
        found = self.index.candidates(StructuredConditions(amenities=("수유실",), open_weekdays=("월",),
                                                           sido="세종특별자치시"))
        # B closes on Monday, C has no parsed schedule, E is elsewhere.
        self.assertEqual(sorted(found), ["A", "D"])
        self.assertEqual(found["A"]["amenities"], {"수유실": ["수유실"]})

    def test_team_alias_family(self) -> None:
        found = self.index.candidates(StructuredConditions(amenities=("카페",), sido="전북특별자치도"))
        self.assertEqual(sorted(found), ["F"])

    def test_real_csv_builds(self) -> None:
        index = LocalOntologyIndex.from_csv()
        found = index.candidates(StructuredConditions(open_weekdays=("월",), sido="세종특별자치시"))
        self.assertTrue(found)


class FakeDriver:
    def __init__(self, records):
        self.records = records
        self.calls = []

    def execute_query(self, query, **params):
        self.calls.append((query, params))
        return self.records, None, None


class Neo4jIndexTests(unittest.TestCase):
    def test_parameters_and_evidence_shape(self) -> None:
        driver = FakeDriver([{"museum_id": "M1", "amenities": [["수유실", ["수유실"]]],
                              "closure_weekdays": ["월"], "open_all_year": False}])
        index = Neo4jOntologyIndex(driver, "db")
        found = index.candidates(StructuredConditions(amenities=("수유실",), open_weekdays=("화",),
                                                      sido="전북특별자치도"))
        params = driver.calls[0][1]
        self.assertIn("전라북도", params["sidos"])
        self.assertEqual(params["amenities"], ["수유실"])
        self.assertEqual(params["open_days"], ["화"])
        self.assertEqual(found["M1"]["amenities"], {"수유실": ["수유실"]})


class RecordingVector:
    def __init__(self, hits, accepts_ids=True):
        self.hits = hits
        self.received = "unset"
        if not accepts_ids:
            self.search = self._search_without_ids

    def prepare(self, query):
        return None

    def search(self, query, *, top_k, prepared_plan=None, candidate_ids=None):
        self.received = candidate_ids
        hits = self.hits if candidate_ids is None else [h for h in self.hits if h["museum_id"] in candidate_ids]
        return {"results": hits}

    def _search_without_ids(self, query, *, top_k, prepared_plan=None):
        return {"results": list(self.hits)}


class FixedReranker:
    def score(self, query, passages):
        return [float(len(passages) - i) for i in range(len(passages))]


class FixedFilter:
    def __init__(self, decision):
        self.decision = decision

    def resolve(self, question):
        return self.decision


def hit(mid, name):
    return {"museum_id": mid, "name": name, "document": f"{name} 설명", "metadata": {"name": name}}


def bm25():
    spans = [SpanDocument(mid, f"{mid}:000", f"{name} 수유실 미술관") for mid, name in
             (("A", "가"), ("B", "나"), ("C", "다"))]
    return BM25SpanRetriever(spans, metadata_by_museum={m: {"name": m, "sido": "경기도"} for m in "ABC"},
                             tokenize=str.split)


class HybridIntegrationTests(unittest.TestCase):
    def config(self):
        return HybridConfig(vector_top_k=5, bm25_top_k=5, fusion_top_k=5, final_top_k=3, parallel_retrieval=False)

    def applied(self, ids):
        conditions = StructuredConditions(amenities=("수유실",))
        return FilterDecision("applied", conditions, "test", ids,
                              {mid: {"amenities": {"수유실": ["수유실"]}} for mid in ids})

    def test_candidates_limit_both_retrievers_and_tag_metadata(self) -> None:
        vector = RecordingVector([hit("A", "가"), hit("B", "나"), hit("C", "다")])
        service = HybridSearchService(bm25_retriever=bm25(), vector_retriever=vector, reranker=FixedReranker(),
                                      config=self.config(), candidate_filter=FixedFilter(self.applied(["A", "C"])))
        result = service.search("수유실 미술관")
        self.assertEqual(vector.received, ["A", "C"])
        self.assertEqual(set(result["source_ids"]), {"A", "C"})
        self.assertTrue(all("수유실" in r["metadata"]["structured_match"] for r in result["results"]))
        self.assertEqual(result["search_summary"]["ontology_filter"]["candidate_count"], 2)

    def test_retriever_without_candidate_ids_is_post_filtered(self) -> None:
        vector = RecordingVector([hit("A", "가"), hit("B", "나")], accepts_ids=False)
        service = HybridSearchService(bm25_retriever=bm25(), vector_retriever=vector, reranker=FixedReranker(),
                                      config=self.config(), candidate_filter=FixedFilter(self.applied(["B"])))
        self.assertEqual(service.search("수유실 미술관")["source_ids"], ["B"])

    def test_empty_candidates_return_no_results_instead_of_dropping_conditions(self) -> None:
        decision = FilterDecision("empty", StructuredConditions(amenities=("수유실",)), "test", [], {})
        service = HybridSearchService(bm25_retriever=bm25(), vector_retriever=RecordingVector([hit("A", "가")]),
                                      reranker=FixedReranker(), config=self.config(),
                                      candidate_filter=FixedFilter(decision))
        result = service.search("수유실 미술관")
        self.assertEqual(result["status"], "no_results")
        self.assertTrue(any("구조 조건" in w for w in result["warnings"]))

    def test_not_applicable_keeps_previous_behavior(self) -> None:
        vector = RecordingVector([hit("A", "가"), hit("B", "나")])
        decision = FilterDecision("not_applicable", StructuredConditions())
        service = HybridSearchService(bm25_retriever=bm25(), vector_retriever=vector, reranker=FixedReranker(),
                                      config=self.config(), candidate_filter=FixedFilter(decision))
        result = service.search("미술관")
        self.assertIsNone(vector.received)
        self.assertNotIn("structured_match", result["results"][0]["metadata"])

    def test_bm25_candidate_ids(self) -> None:
        retriever = bm25()
        self.assertEqual([r["museum_id"] for r in retriever.search("가 나", top_k=5)], ["A", "B"])
        self.assertEqual([r["museum_id"] for r in retriever.search("가 나", top_k=5, candidate_ids=["B"])], ["B"])


class DefaultFilterTests(unittest.TestCase):
    def test_env_switch(self) -> None:
        import os
        from unittest import mock

        with mock.patch.dict(os.environ, {"HYBRID_ONTOLOGY_FILTER": "off"}):
            self.assertIsNone(default_candidate_filter())
        with mock.patch.dict(os.environ, {"HYBRID_ONTOLOGY_FILTER": "on"}):
            self.assertIsInstance(default_candidate_filter(), OntologyCandidateFilter)


if __name__ == "__main__":
    unittest.main()


class SupervisorNoRecordTests(unittest.TestCase):
    def controller(self):
        from src.agent.supervisor.nodes import SupervisorController

        controller = object.__new__(SupervisorController)
        controller.max_retries = 1
        return controller

    def test_empty_filter_gives_korean_reason(self) -> None:
        from src.agent.supervisor.nodes import SupervisorController

        reason = SupervisorController._no_record_reason({"ontology_filter": {
            "status": "empty", "conditions": {"sido": "서울특별시", "amenities": ["휠체어 대여·이용"],
                                              "open_weekdays": ["토", "일"]}}})
        self.assertIn("서울특별시", reason)
        self.assertIn("휠체어 대여·이용", reason)
        self.assertIn("토일요일 개관", reason)
        self.assertEqual(SupervisorController._no_record_reason({"ontology_filter": {"status": "applied"}}), "")

    def test_no_record_abstains_without_retry_and_explains(self) -> None:
        state = {"verified": False, "retry_count": 0, "no_record_reason": "기록된 데이터에서 조건(…)을 모두 만족하는 시설을 찾지 못했습니다.",
                 "trace": []}
        controller = self.controller()
        self.assertEqual(controller.review(state)["next_action"], "abstain")
        self.assertIn("기록이 없다고 실제로 없다는 뜻은 아닙니다", controller.abstain(state)["answer"])

    def test_normal_failure_still_retries(self) -> None:
        state = {"verified": False, "retry_count": 0, "no_record_reason": "", "trace": []}
        self.assertEqual(self.controller().review(state)["next_action"], "retry")
