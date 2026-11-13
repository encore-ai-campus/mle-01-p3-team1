"""Offline wiring example; no actual BM25/Chroma/API/model calls.

Run from project root: python -m src.hybrid.demo
"""

from __future__ import annotations

import json

from . import HybridConfig, HybridSearchService


class FakeVector:
    def prepare(self, query):
        return {"filters": {"sido": "서울특별시"}}

    def search(self, query, *, top_k, prepared_plan=None):
        assert top_k == 20
        return [{
            "museum_id": f"M{i:03}",
            "document": f"독립운동 근대 역사 관련 설명 {i}",
            "metadata": {"name": f"예시 박물관 {i}", "sido": "서울특별시"},
            "distance": 0.01 * i,
        } for i in range(1, 21)]


class FakeBM25:
    def search(self, query, *, top_k, filters):
        assert top_k == 20
        assert filters == {"sido": "서울특별시"}
        # Different candidate pool; both shared and sparse-only museums appear.
        return [{
            "museum_id": f"M{i:03}",
            "document": f"일제강점기 역사 독립운동 기록 {i}",
            "metadata": {"name": f"예시 박물관 {i}", "sido": "서울특별시"},
            "score": 30.0 / i,
        } for i in range(10, 30)]


class FakeReranker:
    """TEST STUB ONLY. Not a substitute for the real CrossEncoder."""

    def score(self, query, passages):
        return [float(index) for index, _passage in enumerate(passages)]


def main():
    service = HybridSearchService(
        bm25_retriever=FakeBM25(),
        vector_retriever=FakeVector(),
        reranker=FakeReranker(),
        config=HybridConfig(vector_weight=0.8, bm25_weight=1.2),
    )
    output = service.search("서울 독립운동 박물관")
    print(json.dumps({
        "search_summary": output["search_summary"],
        "results": [{
            "museum_id": item["museum_id"],
            "rank": item["rank"],
            "bm25_rank": item["bm25_rank"],
            "vector_rank": item["vector_rank"],
            "fusion_score": item["fusion_score"],
            "rerank_score": item["rerank_score"],
        } for item in output["results"]],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
