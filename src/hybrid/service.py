"""Independent BM25 + Vector -> weighted RRF -> Cross-Encoder retrieval.

No Neo4j queries, answer generation, agent planning, or autonomous retries.
Both search pipelines operate independently; graph-oriented diagnostics are
returned without changing the response's existing public keys.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from threading import Lock
from time import perf_counter
from typing import Any

from .adapters import ExistingVectorRetriever
from .config import HybridConfig
from .fusion import fuse_rrf
from .reranker import CrossEncoderReranker, build_passage


def _normalize_retriever_response(response: Any, retriever: str) -> tuple[list[Mapping[str, Any]], list[str]]:
    """Accept list[dict], {'results': list[dict]}, or result object with .results."""
    warnings: list[str] = []
    if isinstance(response, Mapping):
        warnings = [str(w) for w in (response.get("warnings") or [])]
        response = response.get("results")
    elif hasattr(response, "results"):
        warnings = [str(w) for w in (getattr(response, "warnings", ()) or ())]
        response = response.results
    if not isinstance(response, Sequence) or isinstance(response, (str, bytes)):
        raise ValueError(f"{retriever} must return a list of result dicts or {{'results': [...]}}")
    if any(not isinstance(hit, Mapping) for hit in response):
        raise ValueError(f"{retriever} returned a non-dictionary result")
    return list(response), warnings


def _filters_from_plan(plan: Any | None) -> tuple[dict[str, Any], list[str]]:
    if plan is None:
        return {}, []
    filters = getattr(plan, "filters", None)
    if filters is None and isinstance(plan, Mapping):
        filters = plan.get("filters")
    if filters is None:
        clean_filters: dict[str, Any] = {}
    elif hasattr(filters, "model_dump"):
        clean_filters = dict(filters.model_dump(exclude_none=True))
    elif isinstance(filters, Mapping):
        clean_filters = {k: v for k, v in filters.items() if v is not None}
    else:
        raise TypeError("Prepared vector query filters must be a dict or Pydantic model")
    unsupported = getattr(plan, "unsupported_constraints", None)
    if unsupported is None and isinstance(plan, Mapping):
        unsupported = plan.get("unsupported_constraints")
    return clean_filters, list(unsupported or ())


def _plan_value(plan: Any | None, field: str, default: Any = None) -> Any:
    if plan is None:
        return default
    if isinstance(plan, Mapping):
        return plan.get(field, default)
    return getattr(plan, field, default)


def _elapsed_ms(started_at: float) -> float:
    return round((perf_counter() - started_at) * 1000, 2)


def _candidate_preview(hits: Sequence[Mapping[str, Any]], source: str) -> list[dict[str, Any]]:
    """Compact inspectable candidates; avoid duplicating full text in the trace."""
    preview: list[dict[str, Any]] = []
    for rank, hit in enumerate(hits, 1):
        metadata = hit.get("metadata") or {}
        preview.append({
            "rank": rank,
            "museum_id": str(hit.get("museum_id", "")),
            "name": hit.get("name") or (metadata.get("name") if isinstance(metadata, Mapping) else None),
            "score": hit.get("score") if source == "bm25" else None,
            "distance": hit.get("distance") if source == "vector" else None,
            "document_preview": str(hit.get("document") or hit.get("text") or "")[:160],
        })
    return preview


class HybridSearchService:
    """One-shot hybrid retrieval service with reusable BM25 and reranker instances.

    BM25 interface: search(query, *, top_k=20, filters={...}) -> list[dict]
    Vector interface: prepare(query) -> optional plan;
                      search(query, *, top_k, prepared_plan=plan) -> list | dict
    """

    def __init__(
        self,
        *,
        bm25_retriever: Any,
        vector_retriever: Any | None = None,
        reranker: Any | None = None,
        config: HybridConfig | None = None,
    ) -> None:
        if bm25_retriever is None or not callable(getattr(bm25_retriever, "search", None)):
            raise TypeError("bm25_retriever must expose .search(query, *, top_k, filters)")
        self.bm25_retriever = bm25_retriever
        self.vector_retriever = vector_retriever if vector_retriever is not None else ExistingVectorRetriever()
        if not callable(getattr(self.vector_retriever, "search", None)):
            raise TypeError("vector_retriever must expose .search(query, *, top_k, prepared_plan)")
        self.config = config if config is not None else HybridConfig.from_env()
        self._reranker = reranker
        self._rerank_lock = Lock()

    @property
    def reranker(self) -> Any:
        if self._reranker is None:
            self._reranker = CrossEncoderReranker(
                model_name=self.config.reranker_model,
                batch_size=self.config.reranker_batch_size,
                local_model_dir=self.config.reranker_local_dir,
                revision=self.config.reranker_revision,
            )
        return self._reranker

    def search(
        self,
        query: str,
        *,
        top_k: int | None = None,
        rerank: bool = True,
        include_fusion_candidates: bool = False,
        include_retrieval_candidates: bool = False,
    ) -> dict[str, Any]:
        """Search once, returning final candidates and stage-level observations.

        top_k overrides ONLY the final output limit, never BM25/Vector pools or
        fusion_top_k. This avoids rebuilding the BM25 index for graph tool calls.
        """
        started_at = perf_counter()
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must be a non-empty string")
        query = " ".join(query.split())
        cfg = self.config
        final_k = cfg.final_top_k if top_k is None else top_k
        if type(final_k) is not int or not 1 <= final_k <= cfg.fusion_top_k:
            raise ValueError(f"top_k must be between 1 and fusion_top_k ({cfg.fusion_top_k})")
        if not isinstance(rerank, bool):
            raise TypeError("rerank must be a boolean")
        warnings: list[str] = []
        stages: list[dict[str, Any]] = []

        # 1: Shared query plan + metadata filters. The original query goes to BM25.
        stage_start = perf_counter()
        prepared_plan = None
        prepare = getattr(self.vector_retriever, "prepare", None)
        if callable(prepare):
            prepared_plan = prepare(query)
        filters, unsupported = _filters_from_plan(prepared_plan)
        warnings.extend(str(text) for text in unsupported)
        plan_details = {
            "expanded_query": _plan_value(prepared_plan, "expanded_query", query),
            "mode": _plan_value(prepared_plan, "mode", "unavailable"),
            "status": _plan_value(prepared_plan, "status", "not_used"),
            "model": _plan_value(prepared_plan, "model"),
        }
        stages.append({
            "stage": "query_analysis",
            "status": "ok" if prepared_plan is not None else "not_used",
            "duration_ms": _elapsed_ms(stage_start),
            "filters": filters,
            **plan_details,
        })

        # 2: Independent BM25 and Vector retrieval, parallel by default.
        def get_vector() -> Any:
            return self.vector_retriever.search(query, top_k=cfg.vector_top_k, prepared_plan=prepared_plan)

        def get_bm25() -> Any:
            return self.bm25_retriever.search(query, top_k=cfg.bm25_top_k, filters=dict(filters))

        def measured_task(task: Callable[[], Any]) -> tuple[Any, Exception | None, float]:
            task_start = perf_counter()
            try:
                return task(), None, _elapsed_ms(task_start)
            except Exception as exc:
                return None, exc, _elapsed_ms(task_start)

        responses: dict[str, Any] = {}
        errors: dict[str, Exception] = {}
        retrieval_ms: dict[str, float] = {}
        jobs = {"vector": get_vector, "bm25": get_bm25}
        if cfg.parallel_retrieval:
            with ThreadPoolExecutor(max_workers=2, thread_name_prefix="hybrid-retrieval") as executor:
                futures = {source: executor.submit(measured_task, task) for source, task in jobs.items()}
                for source, future in futures.items():
                    response, error, elapsed = future.result()
                    retrieval_ms[source] = elapsed
                    if error is not None:
                        errors[source] = error
                    else:
                        responses[source] = response
        else:
            for source, task in jobs.items():
                response, error, elapsed = measured_task(task)
                retrieval_ms[source] = elapsed
                if error is not None:
                    errors[source] = error
                else:
                    responses[source] = response

        if errors and (cfg.retriever_failure_policy == "raise" or len(errors) == 2):
            source = sorted(errors)[0]
            raise RuntimeError(f"{source} retrieval failed: {type(errors[source]).__name__}") from errors[source]
        for source, exc in errors.items():
            warnings.append(f"{source} retrieval failed ({type(exc).__name__}); partial retrieval only")
        vector_hits, vector_warnings = _normalize_retriever_response(responses.get("vector", []), "vector")
        bm25_hits, bm25_warnings = _normalize_retriever_response(responses.get("bm25", []), "bm25")
        warnings.extend(vector_warnings)
        warnings.extend(bm25_warnings)

        for source, hits in (("vector", vector_hits), ("bm25", bm25_hits)):
            stages.append({
                "stage": f"{source}_retrieval",
                "status": "failed" if source in errors else ("ok" if hits else "empty"),
                "duration_ms": retrieval_ms.get(source),
                "requested": getattr(cfg, f"{source}_top_k"),
                "returned": len(hits),
            })

        # 3: Weighted Reciprocal Rank Fusion. No LLM calls here.
        stage_start = perf_counter()
        fused = fuse_rrf(vector_hits, bm25_hits, config=cfg)
        stages.append({
            "stage": "rrf_fusion",
            "status": "ok" if fused else "empty",
            "duration_ms": _elapsed_ms(stage_start),
            "requested": cfg.fusion_top_k,
            "returned": len(fused),
        })

        # 4: Cross-Encoder reranking, with explicitly reported fallback.
        ranked: list[dict[str, Any]] = [dict(hit, rerank_score=None) for hit in fused]
        rerank_applied = False
        rerank_failure = False
        rerank_diagnostics: dict[str, Any] = {}
        stage_start = perf_counter()
        if rerank and ranked:
            try:
                passages = [build_passage(hit, max_chars=cfg.reranker_max_chars) for hit in ranked]
                if any(not text.strip() for text in passages):
                    raise ValueError("at least one candidate has no name or text to rerank")
                # A shared model is reused across graph calls; protect lazy load
                # and prediction from concurrent use on the same model instance.
                with self._rerank_lock:
                    scores = self.reranker.score(query, passages)
                    diagnostics = getattr(self.reranker, "last_score_timings", None)
                    if isinstance(diagnostics, Mapping):
                        rerank_diagnostics = dict(diagnostics)
                if len(scores) != len(ranked):
                    raise ValueError(f"reranker returned {len(scores)} scores for {len(ranked)} hits")
                for hit, score in zip(ranked, scores):
                    value = float(score)
                    if not math.isfinite(value):
                        raise ValueError("reranker produced NaN/Inf")
                    hit["rerank_score"] = value
                ranked.sort(key=lambda hit: (-hit["rerank_score"], hit["fusion_rank"], hit["museum_id"]))
                rerank_applied = True
            except Exception as exc:
                if cfg.rerank_failure_policy == "raise":
                    raise RuntimeError(f"Cross-Encoder reranking failed ({type(exc).__name__})") from exc
                warnings.append(f"Cross-Encoder reranking failed ({type(exc).__name__}); RRF order retained")
                rerank_failure = True
                for hit in ranked:
                    hit["rerank_score"] = None
                ranked.sort(key=lambda hit: hit["fusion_rank"])
        stages.append({
            "stage": "cross_encoder_rerank",
            "status": "failed_fallback" if rerank_failure else ("ok" if rerank_applied else "skipped"),
            "duration_ms": _elapsed_ms(stage_start),
            "requested": len(fused) if rerank else 0,
            "returned": len(ranked),
            **rerank_diagnostics,
        })

        # 5: Final candidates. Do not synthesize results to reach top_k.
        results = []
        for rank, hit in enumerate(ranked[:final_k], 1):
            final_hit = dict(hit)
            final_hit["rank"] = rank
            final_hit["score"] = final_hit["rerank_score"] if rerank_applied else final_hit["fusion_score"]
            final_hit["score_type"] = "cross_encoder" if rerank_applied else "rrf"
            # Preserve the vector tool's familiar optional result keys without
            # pretending Cross-Encoder scores are its 0/1/2 LLM grades.
            final_hit.setdefault("distance", final_hit.get("vector_distance"))
            final_hit.setdefault("relevance", None)
            final_hit.setdefault("relevance_reason", None)
            results.append(final_hit)

        if not fused:
            warnings.append("No candidates were returned with positive retrieval signal")
        elif len(results) < final_k:
            warnings.append(f"Only {len(results)} candidates available; no artificial padding")

        stages.append({
            "stage": "final_selection",
            "status": "ok" if results else "empty",
            "requested": final_k,
            "returned": len(results),
        })
        summary = {
            # Keep original keys for existing consumers.
            "mode": "hybrid",
            "filters": filters,
            "candidate_count": len(fused),
            "requested_candidate_k": cfg.fusion_top_k,
            "returned_count": len(results),
            "reranked": rerank_applied,
            "vector_returned": len(vector_hits),
            "bm25_returned": len(bm25_hits),
            "fused_returned": len(fused),
            "final_returned": len(results),
            "rerank_requested": bool(rerank),
            "rerank_applied": rerank_applied,
            "rerank_failed": rerank_failure,
            "fusion_method": "weighted_rrf",
            "config": asdict(cfg),
            "metadata_filters": filters,
            "retriever_errors": sorted(errors),
            # Additional graph/CLI observability.
            "requested_final_top_k": final_k,
            "expanded_query": plan_details["expanded_query"],
            "query_mode": plan_details["mode"],
            "analysis_status": plan_details["status"],
            "unsupported_constraints": list(unsupported),
            "stages": stages,
            "total_duration_ms": _elapsed_ms(started_at),
        }
        response = {
            "tool": "museum_hybrid_retrieve",
            "status": "no_results" if not results else ("partial" if warnings else "ok"),
            "query": query,
            "results": results,
            "source_ids": [hit["museum_id"] for hit in results],
            "warnings": list(dict.fromkeys(warnings)),
            "unsupported_constraints": list(unsupported),
            "search_summary": summary,
        }
        if include_fusion_candidates:
            response["fusion_candidates"] = fused
        if include_retrieval_candidates:
            response["retrieval_candidates"] = {
                "vector": _candidate_preview(vector_hits, "vector"),
                "bm25": _candidate_preview(bm25_hits, "bm25"),
            }
        return response
