"""Fail-open, opt-in Langfuse v5 instrumentation centered on LangGraph Supervisor.

Existing application behavior and return shapes are not changed. No documents,
API keys or full Cypher queries are added to *manual* retrieval spans. Note that
LangGraph/LangChain CallbackHandler automatically captures model prompts and
inputs, which may contain original questions and retrieved passages.
"""
from __future__ import annotations

import logging
import math
import os
from collections.abc import Callable, Mapping
from contextlib import contextmanager, nullcontext
import sys
from typing import Any

LOG = logging.getLogger(__name__)
_WARNED: set[str] = set()


def _warn_once(key: str, message: str) -> None:
    if key not in _WARNED:
        _WARNED.add(key)
        LOG.warning("Langfuse: %s", message)


def is_enabled() -> bool:
    """Require an explicit opt-in; also accept Langfuse's standard tracing flag."""
    value = os.getenv("LANGFUSE_ENABLED")
    if value is None:
        value = os.getenv("LANGFUSE_TRACING_ENABLED", "false")
    return str(value).strip().casefold() in {"1", "true", "yes", "on"}


def _client():
    if not is_enabled():
        return None
    if not os.getenv("LANGFUSE_PUBLIC_KEY") or not os.getenv("LANGFUSE_SECRET_KEY"):
        _warn_once("keys", "enabled but keys are missing; tracing skipped")
        return None
    try:
        from langfuse import get_client
        return get_client()
    except Exception as exc:
        _warn_once("sdk", f"SDK unavailable ({type(exc).__name__}); tracing skipped")
        return None


def new_handler():
    """One handler per graph/stream invocation; no process-wide shared run state."""
    if _client() is None:
        return None
    try:
        from langfuse.langchain import CallbackHandler
        return CallbackHandler()
    except Exception as exc:
        _warn_once("handler", f"CallbackHandler unavailable ({type(exc).__name__})")
        return None


def _safe_update(span: Any, **kwargs: Any) -> None:
    if span is not None:
        try:
            span.update(**kwargs)
        except Exception as exc:
            _warn_once("update", f"failed to update an observation ({type(exc).__name__})")


@contextmanager
def observation(name: str, *, as_type: str = "span", input: Any = None, metadata: dict | None = None):
    """Create an optional span without turning a telemetry failure into an app error."""
    client = _client()
    if client is None:
        yield None
        return
    try:
        scope = client.start_as_current_observation(
            as_type=as_type, name=name, input=input, metadata=metadata,
        )
        span = scope.__enter__()
    except Exception as exc:
        _warn_once("start", f"failed to start an observation ({type(exc).__name__})")
        yield None
        return
    try:
        yield span
    except BaseException as exc:
        _safe_update(span, level="ERROR", metadata={"error_type": type(exc).__name__})
        try:
            # Preserve the real error status inside the SDK span.
            scope.__exit__(*sys.exc_info())
        except Exception as telemetry_exc:
            _warn_once("finish", f"failed to finish a failed span ({type(telemetry_exc).__name__})")
        raise
    else:
        try:
            scope.__exit__(None, None, None)
        except Exception as exc:
            _warn_once("finish", f"failed to finish an observation ({type(exc).__name__})")


def _attributes(*, trace_name: str, session_id: str | None = None, metadata: dict | None = None):
    if _client() is None:
        return nullcontext()
    try:
        from langfuse import propagate_attributes
        args: dict[str, Any] = {"trace_name": trace_name, "tags": ["mle3", "museum-rag"]}
        if session_id:
            args["session_id"] = str(session_id)
        if metadata:
            # Propagated attributes have a 200-char/JSON-value limit in SDK v5.
            args["metadata"] = {str(k): str(v)[:150] for k, v in metadata.items()}
        return propagate_attributes(**args)
    except Exception as exc:
        _warn_once("attributes", f"cannot propagate attributes ({type(exc).__name__})")
        return nullcontext()


def compact_trajectory(result: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Extract bounded node diagnostics without echoing full retrieved documents.

    These are results of the *actual* LangGraph run, not synthetic steps.
    Durations are measured by existing Supervisor instrumentation.
    """
    allowed = ("step", "retry_count", "duration_ms", "route", "passed", "skipped", "action", "evidence_count", "error")
    out: list[dict[str, Any]] = []
    for item in (result.get("trace") or [])[:50]:
        if not isinstance(item, Mapping):
            continue
        event = {key: item[key] for key in allowed if key in item}
        if item.get("step") == "supervisor" and isinstance(item.get("reason"), str):
            event["route_reason"] = item["reason"][:180]
        timings = item.get("search_timings")
        if isinstance(timings, Mapping):
            summary = timings.get("search_summary")
            summary = summary if isinstance(summary, Mapping) else {}
            stages = timings.get("stages") or summary.get("stages") or []
            stages = stages if isinstance(stages, (list, tuple)) else []
            event["search_stages"] = [
                {key: stage[key] for key in ("stage", "status", "duration_ms", "requested", "returned", "model_load_ms", "inference_ms") if key in stage}
                for stage in stages[:20] if isinstance(stage, Mapping)
            ]
            event["graph_timings"] = {
                key: timings[key] for key in ("cypher_generation_ms", "neo4j_query_ms", "cypher_generation_calls", "neo4j_query_calls") if key in timings
            }
        out.append(event)
    return out


def invoke_traced_graph(
    app: Any, request: Mapping[str, Any], *, config: Mapping[str, Any] | None = None,
    name: str = "museum-supervisor", session_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict:
    """Run the real graph with a Langfuse root span + LangChain callback.

    Unchanged semantics when disabled. A single graph call creates one trace.
    """
    # Compatibility with the previous installer-based patch: if a caller still
    # wraps this connected graph manually, keep ONE top-level Langfuse trace.
    if getattr(app, "_lf_observed_wrapper", False):
        app = app._graph
    actual_config = dict(config or {})
    # The existing input includes a public museum question; CallbackHandler may
    # also trace LLM prompts/evidence. Never pass an API key to this function.
    root_input = {k: request.get(k) for k in ("question", "top_k", "route_override") if k in request}
    with observation(name, input=root_input, metadata=metadata) as span:
        with _attributes(trace_name=name, session_id=session_id, metadata=metadata):
            handler = new_handler()
            if handler is not None:
                callbacks = list(actual_config.get("callbacks") or [])
                callbacks.append(handler)
                actual_config["callbacks"] = callbacks
            result = app.invoke(dict(request), config=actual_config)
        if isinstance(result, Mapping):
            try:
                summary = {
                    "status": result.get("status"),
                    "route": result.get("route"),
                    "verified": result.get("verified"),
                    "retry_count": result.get("retry_count", 0),
                    "evidence_count": len(result.get("evidence") or []),
                    "errors": [item.get("type") for item in (result.get("errors") or []) if isinstance(item, Mapping)],
                    "route_reason": str(result.get("route_reason") or "")[:180],
                    "trajectory": compact_trajectory(result),
                }
            except Exception as exc:
                _warn_once("summary", f"failed to compact graph output ({type(exc).__name__})")
            else:
                _safe_update(span, output=summary)
        return result


def detailed_retrieval_enabled() -> bool:
    """Opt-in ranked candidate lists; never send passage text to manual spans."""
    return is_enabled() and os.getenv("LANGFUSE_DETAILED_RETRIEVAL", "true").strip().casefold() in {"1", "true", "yes", "on"}


def _ranked_rows(rows: Any) -> list[dict[str, Any]]:
    if not isinstance(rows, (list, tuple)):
        return []
    fields = (
        "museum_id", "rank", "vector_rank", "bm25_rank", "fusion_rank", "fusion_score",
        "rerank_score", "score_type", "score", "distance", "vector_distance", "bm25_score",
    )
    return [
        {key: row[key] for key in fields if key in row}
        for row in rows[:_limit()] if isinstance(row, Mapping)
    ]


def _limit() -> int:
    try:
        return min(30, max(1, int(os.getenv("LANGFUSE_MAX_CANDIDATES", "10"))))
    except ValueError:
        return 10


def _number(value: Any) -> float | int | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    return value if math.isfinite(value) else None


def compact_retrieval(result: Any, *, kind: str, diagnostics: Mapping | None = None) -> dict:
    """Only IDs/ranks/timings; no full passages or credentials."""
    if isinstance(result, Mapping):
        items = result.get("results") or result.get("evidence") or []
        summary = result.get("search_summary") or {}
        record: dict[str, Any] = {
            "status": result.get("status", "ok"),
            "count": len(items) if isinstance(items, (list, tuple)) else 0,
            "source_ids": [str(v) for v in (result.get("source_ids") or [])[:_limit()]],
        }
        if isinstance(summary, Mapping):
            record["rerank_applied"] = summary.get("rerank_applied")
            record["rerank_failed"] = summary.get("rerank_failed")
            record["rerank_low_confidence"] = summary.get("rerank_low_confidence")
            record["total_duration_ms"] = _number(summary.get("total_duration_ms"))
            record["stages"] = []
            allowed = {"stage", "status", "duration_ms", "requested", "returned", "best_score", "min_confidence", "model_load_ms", "inference_ms", "candidate_count", "backend"}
            for stage in (summary.get("stages") or [])[:20]:
                if isinstance(stage, Mapping):
                    record["stages"].append({k: stage[k] for k in allowed if k in stage})
        if isinstance(items, (list, tuple)):
            record["candidates"] = _ranked_rows(items)
        if result.get("retrieval_candidates") and isinstance(result["retrieval_candidates"], Mapping):
            record["retrieval_candidates"] = {
                name: _ranked_rows(rows)
                for name, rows in result["retrieval_candidates"].items()
                if name in {"vector", "bm25"}
            }
        if result.get("fusion_candidates"):
            record["fusion_candidates"] = _ranked_rows(result["fusion_candidates"])
    elif isinstance(result, (list, tuple)):
        record = {"status": "ok", "count": len(result), "source_ids": [str(r.get("museum_id")) for r in result[:_limit()] if isinstance(r, Mapping)]}
    else:
        record = {"status": "unknown", "type": type(result).__name__}
    if diagnostics:
        record["diagnostics"] = {
            k: v for k, v in diagnostics.items()
            if k in {"cypher_generation_ms", "neo4j_query_ms", "prepared_query_ms", "cypher_generation_calls", "neo4j_query_calls", "query_template"}
        }
    return record


def observed_retrieval_call(
    name: str, fn: Callable[[], Any], *, query: str, top_k: int,
    kind: str = "hybrid", diagnostics: Callable[[], Mapping] | None = None,
) -> Any:
    with observation(name, as_type="retriever", input={"query": query, "top_k": top_k}, metadata={"kind": kind}) as span:
        result = fn()
        if span is not None:
            details = None
            if diagnostics is not None:
                try:
                    details = diagnostics()
                except Exception:
                    details = None
            _safe_update(span, output=compact_retrieval(result, kind=kind, diagnostics=details))
        return result



def flush_if_enabled() -> None:
    """Useful at the end of a short CLI execution. Never needed per Streamlit rerun."""
    client = _client()
    if client is not None:
        try:
            client.flush()
        except Exception as exc:
            _warn_once("flush", f"failed to flush traces ({type(exc).__name__})")


# The SDK batches telemetry in the background. The terminal CLI can exit right
# after a single question, so register one process-level shutdown/flush hook.
import atexit
from threading import Lock

_SHUTDOWN_REGISTERED = False
_SHUTDOWN_LOCK = Lock()


def _shutdown_client() -> None:
    client = _client()
    if client is None:
        return
    try:
        client.shutdown()
    except Exception as exc:
        _warn_once("shutdown", f"SDK shutdown failed ({type(exc).__name__})")


def register_shutdown() -> None:
    global _SHUTDOWN_REGISTERED
    with _SHUTDOWN_LOCK:
        if _SHUTDOWN_REGISTERED:
            return
        atexit.register(_shutdown_client)
        _SHUTDOWN_REGISTERED = True


def compact_search_node(result: Any, *, kind: str) -> dict[str, Any]:
    """Summarize a Supervisor adapter result without transmitting source text.

    The Hybrid adapter already includes final ranked evidence and
    search_summary['stages']; Graph adapter carries query-generation/DB timings.
    Whole Vector/BM25 *pre-fusion* hit lists are not present in this contract.
    """
    if not isinstance(result, Mapping):
        return {"kind": kind, "result_type": type(result).__name__}
    evidence = result.get("evidence") or []
    if not isinstance(evidence, (list, tuple)):
        evidence = []
    data: dict[str, Any] = {
        "kind": kind,
        "evidence_count": len(evidence),
        "museum_ids": [str(r.get("museum_id", "")) for r in evidence[:_limit()]
                       if isinstance(r, Mapping)],
        "final_candidates": _ranked_rows(evidence),
    }
    if kind == "hybrid":
        diagnostics = result.get("hybrid_search_diagnostics") or {}
        if isinstance(diagnostics, Mapping):
            data["status"] = diagnostics.get("status")
            summary = diagnostics.get("search_summary") or {}
            if isinstance(summary, Mapping):
                data.update({key: summary[key] for key in (
                    "total_duration_ms", "candidate_count", "vector_returned",
                    "bm25_returned", "fused_returned", "final_returned",
                    "rerank_applied", "rerank_failed", "rerank_low_confidence",
                    "rerank_best_score", "analysis_status") if key in summary})
                stages = summary.get("stages") or []
                allowed = (
                    "stage", "status", "duration_ms", "requested", "returned",
                    "best_score", "min_confidence", "model_load_ms", "inference_ms",
                    "candidate_count", "backend",
                )
                data["stages"] = [
                    {key: row[key] for key in allowed if key in row}
                    for row in stages[:20] if isinstance(row, Mapping)
                ]
    elif kind == "graph":
        diagnostics = result.get("graph_search_diagnostics") or {}
        if isinstance(diagnostics, Mapping):
            data["timings"] = {key: diagnostics[key] for key in (
                "cypher_generation_ms", "neo4j_query_ms", "prepared_query_ms",
                "cypher_generation_calls", "neo4j_query_calls") if key in diagnostics}
    elif kind == "vector":
        data["status"] = result.get("vector_search_status", "unknown")
        diagnostics = result.get("vector_search_diagnostics") or {}
        if isinstance(diagnostics, Mapping):
            data["diagnostics"] = {key: diagnostics[key] for key in (
                "candidate_count", "requested_candidate_k", "reranked", "status",
            ) if key in diagnostics}
    return data
