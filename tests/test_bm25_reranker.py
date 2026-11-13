"""Behavior tests for the standalone museum BM25/RRF ranking module."""

import unittest

from src.agent.bm25_reranker import BM25Reranker, SpanDocument


def words(text: str) -> list[str]:
    return text.casefold().split()


class BM25RerankerTests(unittest.TestCase):
    def test_lexical_match_can_reorder_vector_candidates_and_select_its_span(self):
        ranker = BM25Reranker(
            [
                SpanDocument("M1", "M1:0", "현대 미술 전시"),
                SpanDocument("M2", "M2:0", "일반 전시 안내"),
                SpanDocument("M2", "M2:1", "공룡 화석 연구"),
                SpanDocument("M3", "M3:0", "전통 음악 공연"),
            ],
            tokenize=words,
        )

        result = ranker.rerank("공룡", ["M1", "M2"], top_k=2)

        self.assertEqual([item.museum_id for item in result], ["M2", "M1"])
        self.assertEqual(result[0].best_span_id, "M2:1")
        self.assertEqual(result[0].best_span_text, "공룡 화석 연구")
        self.assertEqual(result[0].vector_rank, 2)
        self.assertEqual(result[0].bm25_rank, 1)
        self.assertAlmostEqual(result[0].rrf_score, 1 / 62 + 1 / 61)
        self.assertGreater(result[0].rrf_score, result[1].rrf_score)
        self.assertIsNone(result[1].bm25_rank)

    def test_empty_lexical_query_keeps_vector_order_and_no_best_span(self):
        ranker = BM25Reranker(
            [
                SpanDocument("M1", "S1", "현대 미술"),
                SpanDocument("M2", "S2", "전통 음악"),
            ],
            tokenize=lambda text: [] if text == "?!" else words(text),
        )

        result = ranker.rerank("?!", ["M2", "M1"], top_k=2)

        self.assertEqual([item.museum_id for item in result], ["M2", "M1"])
        self.assertTrue(all(item.bm25_score == 0 for item in result))
        self.assertTrue(all(item.best_span_id is None for item in result))

    def test_museum_without_span_remains_vector_candidate(self):
        ranker = BM25Reranker(
            [SpanDocument("M1", "S1", "공룡 전시"), SpanDocument("M3", "S3", "민속 전시"),
             SpanDocument("M4", "S4", "미술 전시")],
            tokenize=words,
        )

        result = ranker.rerank("공룡", ["M2", "M1"], top_k=2)

        self.assertEqual([item.museum_id for item in result], ["M1", "M2"])
        self.assertIsNone(result[1].best_span_id)
        self.assertEqual(result[1].bm25_score, 0)

    def test_duplicate_vector_ids_do_not_create_duplicate_results(self):
        ranker = BM25Reranker(
            [SpanDocument("M1", "S1", "현대 미술")], tokenize=words
        )

        result = ranker.rerank("작품", ["M1", "M1", "M2"], top_k=3)

        self.assertEqual([item.museum_id for item in result], ["M1", "M2"])
        self.assertEqual([item.vector_rank for item in result], [1, 2])

    def test_default_kiwi_tokenizer_matches_inflected_korean_terms(self):
        ranker = BM25Reranker([
            SpanDocument("M1", "S1", "공룡 화석을 전시합니다."),
            SpanDocument("M2", "S2", "현대 미술 작품을 전시합니다."),
            SpanDocument("M3", "S3", "전통 음악 공연을 안내합니다."),
        ])

        result = ranker.rerank("공룡의 화석", ["M2", "M1"], top_k=2)

        self.assertEqual(result[0].museum_id, "M1")
        self.assertGreater(result[0].bm25_score, 0)

    def test_rejects_duplicate_span_ids_and_invalid_ranking_settings(self):
        with self.assertRaises(TypeError):
            BM25Reranker([object()], tokenize=words)
        with self.assertRaises(ValueError):
            BM25Reranker([
                SpanDocument("M1", "same", "공룡"),
                SpanDocument("M2", "same", "미술"),
            ], tokenize=words)

        ranker = BM25Reranker([SpanDocument("M1", "S1", "공룡")], tokenize=words)
        with self.assertRaises(ValueError):
            ranker.rerank("공룡", ["M1"], top_k=0)
        with self.assertRaises(ValueError):
            ranker.rerank("공룡", ["M1"], rrf_constant=0)
        with self.assertRaises(ValueError):
            ranker.rerank("공룡", ["M1"], bm25_weight=-1)
        with self.assertRaises(ValueError):
            ranker.rerank("공룡", "M1")


if __name__ == "__main__":
    unittest.main()
