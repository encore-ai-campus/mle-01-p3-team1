"""Adapters to existing VectorSearchService and optional custom BM25 callable."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace
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
            from src.service.vector_search_service import VectorSearchService

            self._service = VectorSearchService()
        return self._service

    def prepare(self, query: str) -> Any:
        service = self.service
        from .region_theme import simple_region_theme
        region = simple_region_theme(query)
        if region:
            from src.service.vector_search_analyzer import MetadataFilters
            return replace(service.plan_without_analysis(query), filters=MetadataFilters(sido=region))
        if service.is_query_analysis_enabled():
            return service.analyze_query(query)
        return service.plan_without_analysis(query)

    def search(
        self,
        query: str,
        *,
        top_k: int,
        prepared_plan: Any | None = None,
        candidate_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """candidate_ids limits Chroma to the ontology filter's museum IDs.

        It is forwarded only when set, so services without the argument keep working.
        """
        extra = {} if candidate_ids is None else {"candidate_ids": list(candidate_ids)}
        if prepared_plan is None:
            result = self.service.search(query, top_k=top_k, rerank=False, **extra)
        else:
            result = self.service.execute_plan(prepared_plan, top_k=top_k, rerank=False, **extra)
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
