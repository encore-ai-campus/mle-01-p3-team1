"""Graph-independent Hybrid RAG rank diagnostics for Langfuse.

Prepared for a future LangGraph refactor. This module has no LangGraph/Langfuse
imports on the pure parsing path, and NEVER returns retrieved document text.

Contract: input is an existing HybridRAGAgent.retrieve / HybridSearchService.search
response, optionally extended with ``rerank_candidates`` (a proposed opt-in key).
Nothing here changes retrieval results, weights, ranking or answer generation.
"""
from __future__ import annotations

import inspect
import math
import os
import re
from collections.abc import Callable, Mapping, Sequence
from contextlib import contextmanager
from typing import Any

_SCHEMA = "mle3.hybrid-ranking.v1"
_MUSEUM_ID = re.compile(r"^[a-zA-Z0-9._:-]{1,100}$")
_TRUE = {"1", "true", "yes", "on"}
_STAGE_ORDER = ("vector", "bm25", "rrf", "pre_rerank", "rerank", "final")
_STAGE_NAMES = {
    "vector": "vector_retrieval",
    "bm25": "bm25_retrieval",
    "rrf": "rrf_fusion",
    "pre_rerank": "name_match",
    "rerank": "cross_encoder_rerank",
    "final": "final_selection",
}
_SAFE_SCORE_FIELDS = {
    "vector": ("distance", "score"),
    "bm25": ("score",),
    "rrf": ("fusion_score", "vector_rank", "bm25_rank", "vector_distance", "bm25_score"),
    "pre_rerank": ("fusion_score", "vector_rank", "bm25_rank"),
    "rerank": ("rerank_score", "fusion_rank", "model_score_rank"),
    "final": ("score", "rerank_score", "fusion_score", "fusion_rank", "vector_rank", "bm25_rank"),
}
_ALLOWED_STAGE_STATUS = {
    "ok", "failed", "failed_fallback", "low_confidence_rrf_order",
    "skipped", "empty", "partial", "not_applicable", "applied",
}
_ALLOWED_FINAL_SCORE_TYPES = {"rrf", "cross_encoder", "rrf_low_confidence_rerank"}


def rank_trace_enabled() -> bool:
    """Separate opt-in: only when Langfuse is on AND detailed tracing is on."""
    from src.observability.langfuse_support import detailed_retrieval_enabled

    return (
        detailed_retrieval_enabled()
        and os.getenv("LANGFUSE_RANK_TRACE", "false").strip().casefold() in _TRUE
    )


def candidate_limit() -> int:
    try:
        return max(1, min(30, int(os.getenv("LANGFUSE_MAX_CANDIDATES", "20"))))
    except ValueError:
        return 20


def _sequence(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _number(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value):
        return None
    return value


def _positive_rank(value: Any) -> int | None:
    return value if type(value) is int and value > 0 else None


def _id_from(row: Mapping[str, Any]) -> str | None:
    value = row.get("museum_id")
    if not isinstance(value, (int, str)) or isinstance(value, bool):
        return None
    candidate = str(value).strip()
    return candidate if _MUSEUM_ID.fullmatch(candidate) else None


def _stage_rows(values: Any, stage: str, *, limit: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    rank_key = {"rrf": "fusion_rank", "pre_rerank": "fusion_rank", "rerank": "effective_rank"}.get(stage, "rank")
    for index, raw in enumerate(_sequence(values), start=1):
        if not isinstance(raw, Mapping):
            continue
        key = _id_from(raw)
        if key is None or key in seen:
            continue
        seen.add(key)
        rank = _positive_rank(raw.get(rank_key)) or _positive_rank(raw.get("rank")) or index
        entry: dict[str, Any] = {"museum_id": key, "rank": rank}
        for field in _SAFE_SCORE_FIELDS[stage]:
            if field in {"fusion_rank", "vector_rank", "bm25_rank", "model_score_rank"}:
                number = _positive_rank(raw.get(field))
            else:
                number = _number(raw.get(field))
            if number is not None:
                entry[field] = number
        if stage == "rerank" and type(raw.get("selected")) is bool:
            entry["selected"] = raw["selected"]
        if stage == "final" and raw.get("score_type") in _ALLOWED_FINAL_SCORE_TYPES:
            entry["score_type"] = raw["score_type"]
        rows.append(entry)
        if len(rows) >= limit:
            break
    return rows


def _stage_timings(summary: Any) -> list[dict[str, Any]]:
    if not isinstance(summary, Mapping):
        return []
    allowed_names = set(_STAGE_NAMES.values()) | {
        "ontology_filter", "graph_restriction", "query_analysis", "name_match"
    }
    out: list[dict[str, Any]] = []
    for stage in _sequence(summary.get("stages"))[:20]:
        if not isinstance(stage, Mapping) or stage.get("stage") not in allowed_names:
            continue
        item: dict[str, Any] = {"stage": stage["stage"]}
        if stage.get("status") in _ALLOWED_STAGE_STATUS:
            item["status"] = stage["status"]
        for k in ("duration_ms", "requested", "returned", "model_load_ms", "inference_ms"):
            val = _number(stage.get(k))
            if val is not None:
                item[k] = val
        out.append(item)
    return out


def _rank_policy(summary: Any) -> str:
    if not isinstance(summary, Mapping):
        return "unknown"
    if summary.get("rerank_failed") is True:
        return "rrf_due_to_reranker_failure"
    if summary.get("rerank_low_confidence") is True:
        return "rrf_due_to_low_confidence"
    if summary.get("rerank_applied") is True:
        return "cross_encoder_applied"
    if summary.get("rerank_requested") is False:
        return "not_requested"
    return "unknown_or_skipped"


def build_rank_report(response: Mapping[str, Any], *, limit: int | None = None) -> dict[str, Any]:
    """Build bounded, text-free rank snapshots from ONE retrieval response.

    ``rerank_candidates`` is a *future* opt-in field from HybridSearchService.
    Without it, the Rerank stage is explicitly marked final_only (top_k only).
    Empty present lists are distinguished from missing optional lists.
    """
    if not isinstance(response, Mapping):
        raise TypeError("response must be a mapping")
    row_limit = min(30, max(1, limit if limit is not None else candidate_limit()))
    retrieval = response.get("retrieval_candidates")
    if not isinstance(retrieval, Mapping):
        retrieval = response.get("retrieval_candidates_full")
    retrieval = retrieval if isinstance(retrieval, Mapping) else {}
    available: dict[str, bool] = {
        "vector": "vector" in retrieval,
        "bm25": "bm25" in retrieval,
        "rrf": "rrf_raw_candidates" in response or "fusion_candidates" in response,
        "pre_rerank": "fusion_candidates" in response,
        "rerank": "rerank_candidates" in response,
        "final": "results" in response,
    }
    raw_stages: dict[str, list] = {
        "vector": _sequence(retrieval.get("vector")),
        "bm25": _sequence(retrieval.get("bm25")),
        "rrf": _sequence(response.get("rrf_raw_candidates", response.get("fusion_candidates"))),
        "pre_rerank": _sequence(response.get("fusion_candidates")),
        "rerank": _sequence(response.get("rerank_candidates")),
        "final": _sequence(response.get("results")),
    }
    summary = response.get("search_summary")
    summary = summary if isinstance(summary, Mapping) else {}
    stages: dict[str, Any] = {}
    for stage in _STAGE_ORDER:
        rows = _stage_rows(raw_stages[stage], stage, limit=row_limit)
        coverage = "complete" if available[stage] else "missing"
        if stage == "rerank" and not available[stage] and raw_stages["final"]:
            # Reranker score/rank are visible for selected final top_k only.
            coverage = "final_only"
            rows = _stage_rows(raw_stages["final"], "rerank", limit=row_limit)
        stages[stage] = {
            "coverage": coverage,
            "total": len(raw_stages[stage]) if available[stage] else (
                len(raw_stages["final"]) if stage == "rerank" and coverage == "final_only" else None
            ),
            "rows": rows,
            "truncated": available[stage] and len(raw_stages[stage]) > row_limit,
        }

    positions: dict[str, dict[str, Any]] = {}
    for stage in _STAGE_ORDER:
        for row in stages[stage]["rows"]:
            d = positions.setdefault(row["museum_id"], {"museum_id": row["museum_id"]})
            d[f"{stage}_rank"] = row["rank"]
            for field in ("distance", "fusion_score", "rerank_score", "model_score_rank"):
                if field in row and field not in d:
                    d[field] = row[field]
    transitions: list[dict[str, Any]] = []
    for row in sorted(
        positions.values(),
        key=lambda item: (
            0 if "final_rank" in item else 1,
            item.get("final_rank", 10**6), item.get("rrf_rank", 10**6),
            item.get("vector_rank", 10**6), item.get("bm25_rank", 10**6),
            item["museum_id"],
        ),
    )[:row_limit]:
        row = dict(row)
        if "rrf_rank" in row and "pre_rerank_rank" in row:
            row["rrf_to_pre_rerank_delta"] = row["rrf_rank"] - row["pre_rerank_rank"]
        if "rrf_rank" in row and "rerank_rank" in row:
            # Overall movement since raw RRF (including name_match if present).
            row["rrf_to_rerank_delta"] = row["rrf_rank"] - row["rerank_rank"]
        if "pre_rerank_rank" in row and "rerank_rank" in row:
            # Cross-Encoder effect excluding name_match reordering.
            row["pre_rerank_to_rerank_delta"] = row["pre_rerank_rank"] - row["rerank_rank"]
        transitions.append(row)

    config = summary.get("config")
    config = config if isinstance(config, Mapping) else {}
    safe_config = {key: _number(config[key]) for key in (
        "vector_weight", "bm25_weight", "rrf_k", "vector_top_k", "bm25_top_k", "fusion_top_k", "rerank_min_confidence"
    ) if key in config and _number(config[key]) is not None}

    return {
        "schema": _SCHEMA,
        "status": response.get("status") if response.get("status") in {"ok", "partial", "no_results", "error"} else "unknown",
        "rerank_order_policy": _rank_policy(summary),
        "source_coverage": {s: stages[s]["coverage"] for s in _STAGE_ORDER},
        "stages": stages,
        "rank_transitions": transitions,
        "reported_stage_timings": _stage_timings(summary),
        "config": safe_config,
        "notes": [
            "Times in reported_stage_timings come from the retriever, not from post-hoc Langfuse spans.",
            "Raw RRF and pre-rerank (after name_match) are separate if raw RRF is supplied.",
            "No pre-fusion/rerank stage is inferred when it was not returned by the retriever.",
        ],
    }


def _supported_options(call: Callable[..., Any], options: dict[str, Any]) -> dict[str, Any]:
    try:
        parameters = inspect.signature(call).parameters
    except (TypeError, ValueError):
        return options
    safe = dict(options)
    for key in ("include_retrieval_candidates", "include_fusion_candidates", "include_rerank_candidates"):
        if key in parameters and key not in safe:
            safe[key] = True
    return safe


def traced_hybrid_call(
    retrieval: Callable[..., Any], *, query: str, top_k: int,
    **kwargs: Any,
) -> Any:
    """Exactly ONE search; opt into candidate data only while rank tracing is enabled.

    Works with ``HybridRAGAgent.retrieve`` or ``HybridSearchService.search``.
    Use within the existing LangGraph/Langfuse parent trace, not as a new root.
    When disabled, delegate the original kwargs untouched.
    """
    if not rank_trace_enabled():
        return retrieval(query=query, top_k=top_k, **kwargs)
    passed = _supported_options(retrieval, kwargs)
    from src.observability.langfuse_support import _safe_update, observation

    with observation(
        "hybrid-candidate-ranking", as_type="retriever",
        input={"top_k": top_k}, metadata={"rank_contract": _SCHEMA},
    ) as span:
        result = retrieval(query=query, top_k=top_k, **passed)
        if span is not None and isinstance(result, Mapping):
            try:
                _safe_update(span, output=build_rank_report(result))
            except Exception:
                # Instrumentation must never break a real retrieval or change its result.
                pass
        return result


async def atraced_hybrid_call(
    retrieval: Callable[..., Any], *, query: str, top_k: int,
    **kwargs: Any,
) -> Any:
    """Async counterpart for a refactored async retrieval tool (one awaited call)."""
    if not rank_trace_enabled():
        return await retrieval(query=query, top_k=top_k, **kwargs)
    passed = _supported_options(retrieval, kwargs)
    from src.observability.langfuse_support import _safe_update, observation

    with observation(
        "hybrid-candidate-ranking", as_type="retriever",
        input={"top_k": top_k}, metadata={"rank_contract": _SCHEMA},
    ) as span:
        result = await retrieval(query=query, top_k=top_k, **passed)
        if span is not None and isinstance(result, Mapping):
            try:
                _safe_update(span, output=build_rank_report(result))
            except Exception:
                pass
        return result


class _StageRecorder:
    def __init__(self, span: Any, stage: str, *, limit: int):
        self._span = span
        self._stage = stage
        self._limit = limit

    def record_candidates(self, rows: Sequence[Mapping[str, Any]], *, status: str = "ok") -> None:
        """Record stage's actual output while the stage's span is active."""
        if self._span is None:
            return
        if status not in _ALLOWED_STAGE_STATUS:
            status = "unknown"
        from src.observability.langfuse_support import _safe_update

        _safe_update(self._span, output={
            "stage": self._stage,
            "status": status,
            "total": len(rows),
            "candidates": _stage_rows(rows, self._stage, limit=self._limit),
        })


@contextmanager
def traced_actual_stage(stage: str, *, requested: int | None = None):
    """Optional true-duration span; call INSIDE the actual stage, not afterward.

    For parallel Vector/BM25, propagate tracing context per worker (see docs).
    """
    if stage not in _STAGE_ORDER:
        raise ValueError(f"Unknown stage: {stage}")
    if not rank_trace_enabled():
        yield _StageRecorder(None, stage, limit=candidate_limit())
        return
    from src.observability.langfuse_support import observation

    with observation(
        f"hybrid-{_STAGE_NAMES[stage]}", as_type="retriever" if stage in {"vector", "bm25"} else "span",
        input={"requested": requested} if requested is not None else None,
        metadata={"rank_contract": _SCHEMA},
    ) as span:
        yield _StageRecorder(span, stage, limit=candidate_limit())


class ObservedHybridAgent:
    """Graph-facing wrapper for the *existing* HybridRAGAgent.

    It is installed after the Supervisor's deterministic-routing decision has
    been calculated. In normal/disabled mode the original agent receives the
    exact same arguments. In ranking mode the same lazy HybridSearchService
    executes once, with opt-in diagnostic outputs; the public answer contract
    and search decisions are unchanged.
    """

    def __init__(self, agent: Any):
        self._agent = agent

    def __getattr__(self, key: str) -> Any:
        return getattr(self._agent, key)

    def retrieve(
        self, query: str, top_k: int = 10, *, rerank: bool = True,
        include_fusion_candidates: bool = False,
        include_retrieval_candidates: bool = False,
        restrict_to_museum_ids: list[str] | None = None,
    ) -> Any:
        if not rank_trace_enabled():
            return self._agent.retrieve(
                query=query, top_k=top_k, rerank=rerank,
                include_fusion_candidates=include_fusion_candidates,
                include_retrieval_candidates=include_retrieval_candidates,
                restrict_to_museum_ids=restrict_to_museum_ids,
            )
        # Preserve the exact public input validation normally performed by
        # HybridRAGAgent.retrieve before calling its underlying search service.
        from src.hybrid.hybrid_rag_agent import _validate_input
        original = _validate_input(query, top_k)
        if type(rerank) is not bool:
            raise TypeError("rerank는 bool이어야 합니다.")
        extra: dict[str, Any] = {
            "rerank": rerank,
            "restrict_to_museum_ids": restrict_to_museum_ids,
        }
        if include_fusion_candidates:
            extra["include_fusion_candidates"] = True
        if include_retrieval_candidates:
            extra["include_retrieval_candidates"] = True
        return traced_hybrid_call(self._agent.service.search, query=original, top_k=top_k, **extra)
