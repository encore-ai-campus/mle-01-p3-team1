import unittest

from src.agent.graph import build_graph


class AgentGraphTests(unittest.TestCase):
    def build(self, *, route="vector", verified=True, **kwargs):
        def search(source):
            return lambda question, k: [
                {
                    "museum_id": "M1",
                    "text": "박물관 근거",
                    "chunk_id": "span-1",
                    "source_doc_ids": ["doc-1"],
                    "retriever": source,
                }
            ]

        return build_graph(
            vector_search=search("vector"),
            graph_search=search("graph"),
            route_question=lambda question: route,
            make_answer=lambda question, evidence: "근거 기반 답변" if evidence else "",
            verify_answer=lambda question, answer, evidence: verified,
            **kwargs,
        )

    def test_vector_route_trims_question_before_callbacks(self):
        seen = []

        def vector(question, k):
            seen.append(("search", question))
            return [{"museum_id": "M1", "text": "근거", "retriever": "vector"}]

        app = build_graph(
            vector_search=vector,
            graph_search=lambda question, k: self.fail("graph route must not run"),
            route_question=lambda question: seen.append(("route", question)) or "vector",
            make_answer=lambda question, evidence: seen.append(("answer", question)) or "답변",
            verify_answer=lambda question, answer, evidence: seen.append(("verify", question)) or True,
        )

        result = app.invoke({"question": "  전통문화 박물관  "})

        self.assertEqual(result["question"], "전통문화 박물관")
        self.assertEqual(seen, [
            ("route", "전통문화 박물관"),
            ("search", "전통문화 박물관"),
            ("answer", "전통문화 박물관"),
            ("verify", "전통문화 박물관"),
        ])

    def test_graph_route_runs_graph_search_only(self):
        called = []
        app = build_graph(
            vector_search=lambda question, k: self.fail("vector route must not run"),
            graph_search=lambda question, k: called.append(question) or [
                {"museum_id": "M2", "text": "그래프 근거", "retriever": "graph"}
            ],
            route_question=lambda question: "graph",
            make_answer=lambda question, evidence: "답변",
            verify_answer=lambda question, answer, evidence: True,
        )

        result = app.invoke({"question": "같은 지역의 박물관"})

        self.assertEqual(called, ["같은 지역의 박물관"])
        self.assertEqual(result["route_trace"], ["graph"])
        self.assertTrue(result["verified"])

    def test_hybrid_deduplicates_same_evidence_and_keeps_both_sources(self):
        result = self.build(route="hybrid").invoke({"question": "지역과 주제"})

        self.assertEqual(len(result["evidence"]), 1)
        self.assertEqual(result["evidence"][0]["retriever"], "hybrid")
        self.assertEqual(result["evidence"][0]["retrievers"], ["vector", "graph"])

    def test_failed_verification_retries_hybrid_once_then_abstains(self):
        app = build_graph(
            vector_search=lambda question, k: [{"museum_id": "M1", "text": "벡터 근거"}],
            graph_search=lambda question, k: [{"museum_id": "M2", "text": "그래프 근거"}],
            route_question=lambda question: "vector",
            make_answer=lambda question, evidence: "검증 실패 답변",
            verify_answer=lambda question, answer, evidence: False,
            max_retries=1,
        )
        result = app.invoke({"question": "검증할 질문"})

        self.assertEqual(result["route_trace"], ["vector", "hybrid"])
        self.assertEqual(result["retry_count"], 1)
        self.assertFalse(result["verified"])
        self.assertIn("확인할 수 없습니다", result["answer"])

    def test_empty_question_is_rejected(self):
        app = self.build()
        for question in ("", "   ", None):
            with self.subTest(question=question):
                with self.assertRaises(ValueError):
                    app.invoke({"question": question})

    def test_missing_evidence_keeps_a_specific_failure_reason(self):
        app = build_graph(
            vector_search=lambda question, k: [],
            graph_search=lambda question, k: [],
            route_question=lambda question: "vector",
            make_answer=lambda question, evidence: "답변",
            verify_answer=lambda question, answer, evidence: True,
            max_retries=0,
        )

        result = app.invoke({"question": "근거 없는 질문"})

        self.assertFalse(result["verified"])
        self.assertEqual(result["failure_reason"], "검색된 근거가 없음")
        self.assertIn("확인할 수 없습니다", result["answer"])

    def test_non_integer_search_limits_are_rejected(self):
        for options in ({"top_k": True}, {"top_k": 1.5}, {"max_retries": True}, {"max_retries": 1.5}):
            with self.subTest(options=options):
                with self.assertRaises(ValueError):
                    self.build(**options)


if __name__ == "__main__":
    unittest.main()
