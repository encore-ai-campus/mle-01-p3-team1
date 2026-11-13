"""Adapters to existing VectorSearchService and optional custom BM25 callable."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any


class ExistingVectorRetriever:
    """Reuse the EXISTING VectorSearchService; never invoke its LLM reranker.

    prepare() uses its already implemented LLM query analysis/metadata extraction.
    The BM25 retriever gets the ORIGINAL question, not the expanded semantic query.
    """

    def __init__(self, service: Any | None = None) -> None:
        self._service = service

    @property
    def service(self) -> Any:
        if self._service is None:
            # Import lazily: offline fusion/tests need no OpenAI, Chroma or DB.
            from src.service.vertor_search_service import VectorSearchService

            self._service = VectorSearchService()
        return self._service

    def prepare(self, query: str) -> Any:
        return self.service.analyze_query(query)

    def search(self, query: str, *, top_k: int, prepared_plan: Any | None = None) -> dict[str, Any]:
        if prepared_plan is None:
            result = self.service.search(query, top_k=top_k, rerank=False)
        else:
            result = self.service.execute_plan(prepared_plan, top_k=top_k, rerank=False)
        return {
            "results": result.results,
            "warnings": list(result.warnings),
            "candidate_count": result.candidate_count,
            "reranked": result.reranked,
        }


class BM25CallableAdapter:
    """For teams that supply a plain function rather than an object with search().

    Required callable signature:
      fn(query: str, *, top_k: int, filters: dict[str, Any]) -> list[dict] | {results: list}
    """

    def __init__(self, fn: Callable[..., Any]):
        if not callable(fn):
            raise TypeError("BM25CallableAdapter requires a callable")
        self._fn = fn

    def search(self, query: str, *, top_k: int, filters: Mapping[str, Any]) -> Any:
        return self._fn(query, top_k=top_k, filters=dict(filters))
