"""Independent BM25 + Vector -> weighted RRF -> Cross-Encoder retrieval.

No answer generation, agent planning, or autonomous retries. Both search
pipelines operate independently; graph-oriented diagnostics are returned
without changing the response's existing public keys.

Optional ontology candidate filter (stage 0): hard, recorded conditions in the
question (amenities, an open weekday) become a museum_id set, and Vector and
BM25 search only inside it. See ontology_filter.py.

After fusion, a facility named verbatim in the question is always a candidate
(name_match.py), and a Cross-Encoder order is only trusted when its best score
reaches HybridConfig.rerank_min_confidence; otherwise the RRF order is kept.
"""

from __future__ import annotations

import inspect
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


def _accepts_keyword(fn: Any, name: str) -> bool:
    try:
        parameters = inspect.signature(fn).parameters.values()
    except (TypeError, ValueError):
        return False
    return any(p.name == name or p.kind is inspect.Parameter.VAR_KEYWORD for p in parameters)


def _search_within(fn: Callable[..., Any], candidate_ids: list[str] | None, **kwargs: Any) -> Any:
    """Pass candidate_ids when the retriever supports it; otherwise post-filter."""
    if candidate_ids is None:
        return fn(**kwargs)
    if _accepts_keyword(fn, "candidate_ids"):
        return fn(candidate_ids=list(candidate_ids), **kwargs)
    hits, warnings = _normalize_retriever_response(fn(**kwargs), "retriever")
    allowed = set(candidate_ids)
    return {"results": [hit for hit in hits if str(hit.get("museum_id", "")) in allowed], "warnings": warnings}


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
        candidate_filter: Any | None = None,
        name_index: Any | None = None,
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
        if candidate_filter is not None and not callable(getattr(candidate_filter, "resolve", None)):
            raise TypeError("candidate_filter must expose .resolve(question)")
        self.candidate_filter = candidate_filter
        if name_index is not None and not callable(getattr(name_index, "match", None)):
            raise TypeError("name_index must expose .match(question)")
        self.name_index = name_index

    def _ensure_named(
        self, query: str, fused: list[dict[str, Any]], candidate_ids: list[str] | None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Put facilities named verbatim in the question at the front of the candidates."""
        matches = self.name_index.match(query)
        summary: dict[str, Any] = {"names": [name for name, _ in matches], "promoted": [],
                                   "injected": [], "unavailable": []}
        if not matches:
            return fused, {"status": "not_applicable", **summary}
        allowed = None if candidate_ids is None else set(candidate_ids)
        by_id = {str(hit["museum_id"]): hit for hit in fused}
        get_document = getattr(self.bm25_retriever, "document", None)
        front: list[dict[str, Any]] = []
        for _, museum_ids in matches:
            for museum_id in museum_ids:
                if (allowed is not None and museum_id not in allowed) or any(
                        hit["museum_id"] == museum_id for hit in front):
                    continue
                if museum_id in by_id:
                    front.append(by_id[museum_id])
                    summary["promoted"].append(museum_id)
                    continue
                hit = get_document(museum_id) if callable(get_document) else None
                text = str((hit or {}).get("document") or "")
                if not text.strip():
                    summary["unavailable"].append(museum_id)
                    continue
                front.append({
                    "museum_id": museum_id, "name": hit.get("name"), "document": text,
                    "metadata": dict(hit.get("metadata") or {}),
                    "vector_rank": None, "bm25_rank": None, "vector_distance": None,
                    "vector_score": None, "bm25_score": None,
                    "vector_document": "", "bm25_document": text,
                    "best_span_id": hit.get("best_span_id"), "best_span_text": hit.get("best_span_text"),
                    "fusion_score": 0.0, "retrieved_by": ["name_match"],
                })
                summary["injected"].append(museum_id)
        if not front:
            return fused, {"status": "no_candidate", **summary}
        front_ids = {hit["museum_id"] for hit in front}
        merged = front + [hit for hit in fused if hit["museum_id"] not in front_ids]
        merged = merged[: self.config.fusion_top_k]
        result = []
        for rank, hit in enumerate(merged, 1):
            item = dict(hit, fusion_rank=rank)
            if hit["museum_id"] in front_ids:
                item["name_match"] = True
            result.append(item)
        return result, {"status": "applied", **summary}

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
        include_full_retrieval_candidates: bool = False,
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
        if not isinstance(include_full_retrieval_candidates, bool):
            raise TypeError("include_full_retrieval_candidates must be a boolean")
        warnings: list[str] = []
        stages: list[dict[str, Any]] = []

        # 0: Ontology candidate filter. Hard recorded conditions -> museum_id set.
        stage_start = perf_counter()
        decision = self.candidate_filter.resolve(query) if self.candidate_filter is not None else None
        candidate_ids = decision.candidate_ids if decision is not None and decision.status != "not_applicable" else None
        if decision is not None:
            stages.append({"stage": "ontology_filter", "duration_ms": _elapsed_ms(stage_start), **decision.summary()})
            if decision.status == "empty":
                warnings.append(
                    f"구조 조건({decision.conditions.describe()})을 만족하는 기록이 있는 시설이 없습니다; "
                    "조건을 빼고 검색하지 않았습니다."
                )

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
        analysis_status = (
            "disabled" if plan_details["status"] == "disabled"
            else "ok" if prepared_plan is not None
            else "not_used"
        )
        stages.append({
            "stage": "query_analysis",
            "status": analysis_status,
            "duration_ms": _elapsed_ms(stage_start),
            "filters": filters,
            **plan_details,
        })

        # 2: Independent BM25 and Vector retrieval, parallel by default.
        def get_vector() -> Any:
            return _search_within(
                self.vector_retriever.search, candidate_ids,
                query=query, top_k=cfg.vector_top_k, prepared_plan=prepared_plan,
            )

        def get_bm25() -> Any:
            return _search_within(
                self.bm25_retriever.search, candidate_ids,
                query=query, top_k=cfg.bm25_top_k, filters=dict(filters),
            )

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

        # 3b: A facility named verbatim in the question is always a candidate.
        name_summary = None
        if self.name_index is not None:
            stage_start = perf_counter()
            fused, name_summary = self._ensure_named(query, fused, candidate_ids)
            stages.append({"stage": "name_match", "duration_ms": _elapsed_ms(stage_start), **name_summary})

        # 4: Cross-Encoder reranking, with explicitly reported fallback.
        ranked: list[dict[str, Any]] = [dict(hit, rerank_score=None) for hit in fused]
        rerank_applied = False
        rerank_failure = False
        rerank_low_confidence = False
        rerank_best_score = None
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
                rerank_best_score = max(hit["rerank_score"] for hit in ranked)
                if cfg.rerank_min_confidence > 0 and rerank_best_score < cfg.rerank_min_confidence:
                    # No confident candidate: near-zero scores are noise, keep the RRF order.
                    ranked.sort(key=lambda hit: hit["fusion_rank"])
                    rerank_low_confidence = True
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
            "status": ("failed_fallback" if rerank_failure else "low_confidence_rrf_order" if rerank_low_confidence
                       else "ok" if rerank_applied else "skipped"),
            "duration_ms": _elapsed_ms(stage_start),
            "requested": len(fused) if rerank else 0,
            "returned": len(ranked),
            "best_score": rerank_best_score,
            "min_confidence": cfg.rerank_min_confidence,
            **rerank_diagnostics,
        })

        # 5: Final candidates. Do not synthesize results to reach top_k.
        results = []
        for rank, hit in enumerate(ranked[:final_k], 1):
            final_hit = dict(hit)
            final_hit["rank"] = rank
            trusted = rerank_applied and not rerank_low_confidence
            final_hit["score"] = final_hit["rerank_score"] if trusted else final_hit["fusion_score"]
            final_hit["score_type"] = ("cross_encoder" if trusted else
                                       "rrf_low_confidence_rerank" if rerank_low_confidence else "rrf")
            # Preserve the vector tool's familiar optional result keys without
            # pretending Cross-Encoder scores are its 0/1/2 LLM grades.
            final_hit.setdefault("distance", final_hit.get("vector_distance"))
            final_hit.setdefault("relevance", None)
            final_hit.setdefault("relevance_reason", None)
            if decision is not None and decision.status == "applied":
                # The answer/verifier LLM reads metadata; this is the basis for
                # the structured conditions, separate from the passage text.
                from .ontology_filter import describe_match

                metadata = dict(final_hit.get("metadata") or {})
                metadata["structured_match"] = describe_match(
                    decision.conditions, decision.evidence.get(str(final_hit.get("museum_id")), {})
                )
                final_hit["metadata"] = metadata
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
            "ontology_filter": decision.summary() if decision is not None else None,
            "name_match": name_summary,
            "rerank_low_confidence": rerank_low_confidence,
            "rerank_best_score": rerank_best_score,
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
        if include_full_retrieval_candidates:
            response["retrieval_candidates_full"] = {
                "vector": [dict(hit) for hit in vector_hits],
                "bm25": [dict(hit) for hit in bm25_hits],
            }
        return response
